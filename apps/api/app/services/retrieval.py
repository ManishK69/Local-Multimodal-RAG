from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, DocumentPage
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


async def vector_search(
    session: AsyncSession,
    query_vec: list[float],
    k: int = 20,
    document_ids: list[int] | None = None,
) -> list[RankedChunk]:
    distance = Chunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(Chunk, DocumentPage.page_number, distance.label("distance"))
        .join(DocumentPage, DocumentPage.id == Chunk.page_id)
        .where(Chunk.embedding.isnot(None))
        .order_by(distance)
        .limit(k)
    )
    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))
    rows = (await session.execute(stmt)).all()
    ranked: list[RankedChunk] = []
    for index, (chunk, page_number, dist) in enumerate(rows, start=1):
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
        select(Chunk, DocumentPage.page_number, rank.label("rank_score"))
        .join(DocumentPage, DocumentPage.id == Chunk.page_id)
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
    for index, (chunk, page_number, score) in enumerate(rows, start=1):
        ranked.append(
            RankedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                page_number=int(page_number),
                content=chunk.content,
                bbox=chunk.bbox,
                rank=index,
                score=float(score or 0.0),
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
            )
        )
    return HybridResult(fused=fused, vector=vector, lexical=lexical)
