from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_session
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Chunk, DocumentPage, Message, RetrievalTrace
from app.db.repositories import conversations as conv_repo
from app.services.citations import parse_markers
from app.services.generate import build_messages, citation_payloads
from app.services.ollama import OllamaClient
from app.services.retrieval import vector_search

router = APIRouter(tags=["chat"])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ConversationCreate(CamelModel):
    title: str | None = None


class ChatRequest(CamelModel):
    content: str
    document_ids: list[int] | None = None
    top_k: int = Field(default=8, ge=1, le=20)


def _serialize_dt(value: datetime) -> str:
    iso = value.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    return iso


def conversation_out(conversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "createdAt": _serialize_dt(conversation.created_at),
        "updatedAt": _serialize_dt(conversation.updated_at),
    }


async def message_out(session: AsyncSession, message: Message) -> dict[str, Any]:
    citations = []
    if message.citations:
        chunk_ids = [item.chunk_id for item in message.citations]
        rows = (
            await session.execute(
                select(Chunk, DocumentPage.page_number)
                .join(DocumentPage, DocumentPage.id == Chunk.page_id)
                .where(Chunk.id.in_(chunk_ids))
            )
        ).all()
        by_id = {chunk.id: (chunk, page_number) for chunk, page_number in rows}
        for item in sorted(message.citations, key=lambda c: c.marker_index):
            chunk, page_number = by_id.get(item.chunk_id, (None, None))
            if chunk is None:
                continue
            citations.append(
                {
                    "markerIndex": item.marker_index,
                    "chunkId": chunk.id,
                    "documentId": chunk.document_id,
                    "pageNumber": int(page_number),
                    "bbox": chunk.bbox,
                    "snippet": chunk.content[:240],
                }
            )
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "citations": citations,
        "createdAt": _serialize_dt(message.created_at),
    }


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/conversations", status_code=201)
async def create_conversation(
    body: ConversationCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conversation = await conv_repo.create_conversation(session, body.title)
    return conversation_out(conversation)


@router.get("/conversations")
async def list_conversations(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    rows, next_cursor = await conv_repo.list_conversations(
        session, limit=limit, cursor=cursor
    )
    return {
        "items": [conversation_out(row) for row in rows],
        "nextCursor": next_cursor,
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conversation = await conv_repo.get_conversation(session, conversation_id)
    if conversation is None:
        raise AppError("not_found", "Conversation not found.", status_code=404)
    messages = []
    for message in sorted(conversation.messages, key=lambda item: item.created_at):
        messages.append(await message_out(session, message))
    payload = conversation_out(conversation)
    payload["messages"] = messages
    return payload


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    conversation = await conv_repo.get_conversation(session, conversation_id)
    if conversation is None:
        raise AppError("not_found", "Conversation not found.", status_code=404)
    await conv_repo.delete_conversation(session, conversation)
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: int,
    body: ChatRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    conversation = await conv_repo.get_conversation(session, conversation_id)
    if conversation is None:
        raise AppError("not_found", "Conversation not found.", status_code=404)

    async def events() -> AsyncIterator[str]:
        client = OllamaClient()
        try:
            await conv_repo.add_message(
                session, conversation_id, "user", body.content
            )
            yield sse("status", {"stage": "retrieving"})
            embed_started = time.perf_counter()
            query_vec = (await client.embed([body.content]))[0]
            latency_embed_ms = int((time.perf_counter() - embed_started) * 1000)
            retrieve_started = time.perf_counter()
            ranked = await vector_search(
                session,
                query_vec,
                k=20,
                document_ids=body.document_ids or None,
            )
            fused_k = body.top_k
            ranked = ranked[:fused_k]
            latency_retrieve_ms = int(
                (time.perf_counter() - retrieve_started) * 1000
            )
            citations = citation_payloads(ranked)
            yield sse("citations", {"citations": citations})
            messages = build_messages(body.content, ranked)
            generate_started = time.perf_counter()
            parts: list[str] = []
            stream = client.chat(messages, stream=True)
            async for token in stream:
                if await request.is_disconnected():
                    return
                parts.append(token)
                yield sse("token", {"text": token})
            answer = "".join(parts)
            latency_generate_ms = int(
                (time.perf_counter() - generate_started) * 1000
            )
            assistant = await conv_repo.add_message(
                session, conversation_id, "assistant", answer
            )
            marker_ids = parse_markers(answer)
            pairs: list[tuple[int, int]] = []
            for marker in marker_ids:
                if 1 <= marker <= len(ranked):
                    pairs.append((marker, ranked[marker - 1].chunk_id))
            await conv_repo.add_citations(session, assistant.id, pairs)
            session.add(
                RetrievalTrace(
                    conversation_id=conversation_id,
                    message_id=assistant.id,
                    query=body.content,
                    embed_model=settings.embed_model,
                    generate_model=settings.generate_model,
                    vector_chunk_ids=[item.chunk_id for item in ranked],
                    lexical_chunk_ids=[],
                    fused_chunk_ids=[item.chunk_id for item in ranked],
                    fused_scores=[item.score for item in ranked],
                    latency_embed_ms=latency_embed_ms,
                    latency_retrieve_ms=latency_retrieve_ms,
                    latency_generate_ms=latency_generate_ms,
                )
            )
            await session.commit()
            yield sse("done", {"messageId": assistant.id})
        except Exception as exc:
            yield sse(
                "error",
                {
                    "code": "dependency_unavailable",
                    "message": str(exc)[:500],
                },
            )

    return StreamingResponse(events(), media_type="text/event-stream")
