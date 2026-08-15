from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, IngestCheckpoint
from app.services.ollama import OllamaClient

BATCH_SIZE = 32


async def _get_checkpoint(
    session: AsyncSession, document_id: int
) -> IngestCheckpoint:
    checkpoint = await session.scalar(
        select(IngestCheckpoint).where(
            IngestCheckpoint.document_id == document_id,
            IngestCheckpoint.stage == "embedding",
        )
    )
    if checkpoint is None:
        checkpoint = IngestCheckpoint(
            document_id=document_id,
            stage="embedding",
            last_completed_index=0,
            payload={},
        )
        session.add(checkpoint)
        await session.flush()
    return checkpoint


async def embed_chunks(session: AsyncSession, document_id: int) -> None:
    client = OllamaClient()
    checkpoint = await _get_checkpoint(session, document_id)
    chunks = list(
        await session.scalars(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
    )
    pending = [
        chunk
        for chunk in chunks
        if chunk.chunk_index >= checkpoint.last_completed_index
        and chunk.embedding is None
    ]
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        vectors = await client.embed([chunk.content for chunk in batch])
        for chunk, vector in zip(batch, vectors, strict=True):
            chunk.embedding = vector
        checkpoint.last_completed_index = batch[-1].chunk_index + 1
        await session.commit()
