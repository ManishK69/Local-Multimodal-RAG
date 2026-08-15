from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, DocumentPage


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
