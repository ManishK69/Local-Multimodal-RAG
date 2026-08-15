from typing import Any

import httpx
from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter()


def _model_present(names: set[str], wanted: str) -> bool:
    return wanted in names or any(name.startswith(f"{wanted}:") for name in names)


async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def _check_redis() -> str:
    client = Redis.from_url(settings.redis_url)
    try:
        pong = await client.ping()
        return "ok" if pong else "error"
    except Exception:
        return "error"
    finally:
        await client.aclose()


async def _check_ollama() -> tuple[str, dict[str, bool]]:
    models = {"embed": False, "vision": False, "generate": False}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        names = {
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
        }
        models["embed"] = _model_present(names, settings.embed_model)
        models["vision"] = _model_present(names, settings.vision_model)
        models["generate"] = _model_present(names, settings.generate_model)
        ollama = "ok"
    except Exception:
        ollama = "error"
    return ollama, models


@router.get("/health")
async def health() -> dict[str, Any]:
    postgres = await _check_postgres()
    redis = await _check_redis()
    ollama, models = await _check_ollama()
    all_models = all(models.values())
    status = (
        "ok"
        if postgres == "ok" and redis == "ok" and ollama == "ok" and all_models
        else "degraded"
    )
    return {
        "status": status,
        "postgres": postgres,
        "redis": redis,
        "ollama": ollama,
        "models": models,
    }
