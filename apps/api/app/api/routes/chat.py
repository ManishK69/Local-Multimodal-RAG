from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Chunk, Document, DocumentPage, Message, RetrievalTrace
from app.db.repositories import conversations as conv_repo
from app.services.citations import parse_markers
from app.services.generate import (
    INSIGHT_RETRIEVAL_QUERY,
    INSIGHT_USER_LABEL,
    build_insight_messages,
    build_messages,
    citation_payloads,
    empty_retrieval_answer,
)
from app.services.ollama import OllamaClient
from app.services.retrieval import diversified_search, hybrid_search

router = APIRouter(tags=["chat"])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ConversationCreate(CamelModel):
    title: str | None = None


class ChatRequest(CamelModel):
    content: str = ""
    document_ids: list[int] | None = None
    top_k: int = Field(default=8, ge=1, le=20)
    mode: Literal["ask", "insight"] = "ask"


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
                select(Chunk, DocumentPage.page_number, Document.filename)
                .join(DocumentPage, DocumentPage.id == Chunk.page_id)
                .join(Document, Document.id == Chunk.document_id)
                .where(Chunk.id.in_(chunk_ids))
            )
        ).all()
        by_id = {
            chunk.id: (chunk, page_number, filename)
            for chunk, page_number, filename in rows
        }
        for item in sorted(message.citations, key=lambda c: c.marker_index):
            found = by_id.get(item.chunk_id)
            if found is None:
                continue
            chunk, page_number, filename = found
            citations.append(
                {
                    "markerIndex": item.marker_index,
                    "chunkId": chunk.id,
                    "documentId": chunk.document_id,
                    "pageNumber": int(page_number),
                    "bbox": chunk.bbox,
                    "snippet": chunk.content[:240],
                    "filename": filename,
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
    insight = body.mode == "insight"
    if insight and not body.document_ids:
        raise AppError(
            "validation_error",
            "Insight requires documentIds.",
            status_code=422,
        )
    user_text = (
        INSIGHT_USER_LABEL
        if insight
        else body.content.strip()
    )
    if not user_text:
        raise AppError(
            "validation_error",
            "Message content is required.",
            status_code=422,
        )

    async def events() -> AsyncIterator[str]:
        client = OllamaClient()
        try:
            await conv_repo.add_message(
                session, conversation_id, "user", user_text
            )
            yield sse("status", {"stage": "retrieving"})
            embed_started = time.perf_counter()
            retrieve_query = INSIGHT_RETRIEVAL_QUERY if insight else user_text
            query_vec = (await client.embed([retrieve_query]))[0]
            latency_embed_ms = int((time.perf_counter() - embed_started) * 1000)
            retrieve_started = time.perf_counter()
            if insight:
                result = await diversified_search(
                    session,
                    retrieve_query,
                    query_vec=query_vec,
                    document_ids=body.document_ids or [],
                    per_doc=4,
                    cap=max(body.top_k, 16),
                )
            else:
                result = await hybrid_search(
                    session,
                    retrieve_query,
                    query_vec=query_vec,
                    k_vector=20,
                    k_lexical=20,
                    fused_k=body.top_k,
                    document_ids=body.document_ids or None,
                )
            ranked = result.fused
            latency_retrieve_ms = int(
                (time.perf_counter() - retrieve_started) * 1000
            )
            citations = citation_payloads(ranked)
            yield sse("citations", {"citations": citations})
            generate_started = time.perf_counter()
            parts: list[str] = []
            if not ranked:
                answer = empty_retrieval_answer()
                parts.append(answer)
                yield sse("token", {"text": answer})
            else:
                messages = (
                    build_insight_messages(ranked)
                    if insight
                    else build_messages(user_text, ranked)
                )
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
                    query=retrieve_query,
                    embed_model=settings.embed_model,
                    generate_model=settings.generate_model,
                    vector_chunk_ids=[item.chunk_id for item in result.vector],
                    lexical_chunk_ids=[item.chunk_id for item in result.lexical],
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

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
