from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings


class OllamaClient:
    def __init__(self, host: str | None = None) -> None:
        self.host = (host or settings.ollama_host).rstrip("/")
        self.embed_model = settings.embed_model
        self.vision_model = settings.vision_model
        self.generate_model = settings.generate_model
        self.embedding_dim = settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.host}/api/embed",
                json={"model": self.embed_model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
        vectors = payload.get("embeddings")
        if vectors is None:
            single = payload.get("embedding")
            vectors = [single] if single is not None else []
        if len(vectors) != len(texts):
            raise ValueError(
                "Ollama embed returned a different number of vectors than inputs."
            )
        checked: list[list[float]] = []
        for vector in vectors:
            values = [float(item) for item in vector]
            if len(values) != self.embedding_dim:
                raise ValueError(
                    f"embedding length {len(values)} != {self.embedding_dim}"
                )
            checked.append(values)
        return checked

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = True,
    ) -> AsyncIterator[str] | str:
        body = {
            "model": self.generate_model,
            "messages": messages,
            "stream": stream,
        }
        if stream:
            return self._chat_stream(body)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self.host}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
        return str((payload.get("message") or {}).get("content") or "")

    async def _chat_stream(self, body: dict[str, Any]) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{self.host}/api/chat", json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = (payload.get("message") or {}).get("content") or ""
                    if text:
                        yield text

    async def vision_caption(self, image_bytes: bytes) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        body = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": "Describe this figure for retrieval.",
                    "images": [encoded],
                }
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self.host}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
        return str((payload.get("message") or {}).get("content") or "").strip()

    async def list_tags(self) -> set[str]:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            payload = response.json()
        return {
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
        }
