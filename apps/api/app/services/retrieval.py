from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentPage
from app.services.rrf import rrf


@dataclass
class RankedChunk:
    chunk_id: int
    document_id: int
    page_number: int
    content: str
    bbox: dict[str, Any] | None
    rank: int
    score: float
    filename: str = ""


async def vector_search(
    session: AsyncSession,
    query_vec: list[float],
    k: int = 20,
    document_ids: list[int] | None = None,
) -> list[RankedChunk]:
    distance = Chunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(
            Chunk,
            DocumentPage.page_number,
            Document.filename,
            distance.label("distance"),
        )
        .join(DocumentPage, DocumentPage.id == Chunk.page_id)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.embedding.isnot(None))
        .order_by(distance)
        .limit(k)
    )
    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))
    rows = (await session.execute(stmt)).all()
    ranked: list[RankedChunk] = []
    for index, (chunk, page_number, filename, dist) in enumerate(rows, start=1):
        cosine_distance = float(dist)
        ranked.append(
            RankedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                page_number=int(page_number),
                content=chunk.content,
                bbox=chunk.bbox,
                rank=index,
                score=max(0.0, 1.0 - cosine_distance),
                filename=str(filename),
            )
        )
    return ranked


async def lexical_search(
    session: AsyncSession,
    query: str,
    k: int = 20,
    document_ids: list[int] | None = None,
) -> list[RankedChunk]:
    if not query.strip():
        return []
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.content_tsv, tsquery)
    stmt = (
        select(
            Chunk,
            DocumentPage.page_number,
            Document.filename,
            rank.label("rank_score"),
        )
        .join(DocumentPage, DocumentPage.id == Chunk.page_id)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.content_tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(k)
    )
    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))
    try:
        rows = (await session.execute(stmt)).all()
    except Exception:
        return []
    ranked: list[RankedChunk] = []
    for index, (chunk, page_number, filename, score) in enumerate(rows, start=1):
        ranked.append(
            RankedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                page_number=int(page_number),
                content=chunk.content,
                bbox=chunk.bbox,
                rank=index,
                score=float(score or 0.0),
                filename=str(filename),
            )
        )
    return ranked


@dataclass
class HybridResult:
    fused: list[RankedChunk]
    vector: list[RankedChunk] = field(default_factory=list)
    lexical: list[RankedChunk] = field(default_factory=list)


async def hybrid_search(
    session: AsyncSession,
    query: str,
    *,
    query_vec: list[float] | None = None,
    k_vector: int = 20,
    k_lexical: int = 20,
    fused_k: int = 8,
    document_ids: list[int] | None = None,
) -> HybridResult:
    if query_vec is None:
        from app.services.ollama import OllamaClient

        query_vec = (await OllamaClient().embed([query]))[0]
    vector = await vector_search(
        session, query_vec, k=k_vector, document_ids=document_ids
    )
    lexical = await lexical_search(
        session, query, k=k_lexical, document_ids=document_ids
    )
    fused_ranks = rrf(
        [[item.chunk_id for item in vector], [item.chunk_id for item in lexical]]
    )
    by_id = {item.chunk_id: item for item in lexical}
    by_id.update({item.chunk_id: item for item in vector})
    fused: list[RankedChunk] = []
    for index, (chunk_id, score) in enumerate(fused_ranks[:fused_k], start=1):
        source = by_id[chunk_id]
        fused.append(
            RankedChunk(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                page_number=source.page_number,
                content=source.content,
                bbox=source.bbox,
                rank=index,
                score=score,
                filename=source.filename,
            )
        )
    return HybridResult(fused=fused, vector=vector, lexical=lexical)


async def diversified_search(
    session: AsyncSession,
    query: str,
    *,
    query_vec: list[float] | None = None,
    document_ids: list[int],
    per_doc: int = 4,
    cap: int = 16,
) -> HybridResult:
    """Hybrid search each document, then round-robin so one PDF cannot fill CONTEXT."""
    if len(document_ids) <= 1:
        return await hybrid_search(
            session,
            query,
            query_vec=query_vec,
            fused_k=cap,
            document_ids=document_ids or None,
        )
    buckets: list[list[RankedChunk]] = []
    vector: list[RankedChunk] = []
    lexical: list[RankedChunk] = []
    for document_id in document_ids:
        result = await hybrid_search(
            session,
            query,
            query_vec=query_vec,
            k_vector=12,
            k_lexical=12,
            fused_k=per_doc,
            document_ids=[document_id],
        )
        buckets.append(result.fused)
        vector.extend(result.vector)
        lexical.extend(result.lexical)
    picked: list[RankedChunk] = []
    seen: set[int] = set()
    slot = 0
    while len(picked) < cap:
        progressed = False
        for bucket in buckets:
            if slot >= len(bucket):
                continue
            chunk = bucket[slot]
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            picked.append(chunk)
            progressed = True
            if len(picked) >= cap:
                break
        if not progressed:
            break
        slot += 1
    fused = [
        RankedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            content=chunk.content,
            bbox=chunk.bbox,
            rank=index,
            score=chunk.score,
            filename=chunk.filename,
        )
        for index, chunk in enumerate(picked, start=1)
    ]
    return HybridResult(fused=fused, vector=vector, lexical=lexical)
