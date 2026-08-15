from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/settings")
def read_settings() -> dict[str, str | int]:
    return {
        "embedModel": settings.embed_model,
        "visionModel": settings.vision_model,
        "generateModel": settings.generate_model,
        "maxUploadBytes": settings.max_upload_bytes,
        "embeddingDim": settings.embedding_dim,
    }
