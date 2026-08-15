from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentPage, IngestCheckpoint
from app.services.ollama import OllamaClient
from app.services.storage import image_path

MIN_SIDE_PX = 16


async def _caption_checkpoint(
    session: AsyncSession, document_id: int
) -> IngestCheckpoint:
    checkpoint = await session.scalar(
        select(IngestCheckpoint).where(
            IngestCheckpoint.document_id == document_id,
            IngestCheckpoint.stage == "captioning",
        )
    )
    if checkpoint is None:
        checkpoint = IngestCheckpoint(
            document_id=document_id,
            stage="captioning",
            last_completed_index=0,
            payload={},
        )
        session.add(checkpoint)
        await session.flush()
    return checkpoint


async def caption_images(session: AsyncSession, document: Document) -> None:
    parsing = await session.scalar(
        select(IngestCheckpoint).where(
            IngestCheckpoint.document_id == document.id,
            IngestCheckpoint.stage == "parsing",
        )
    )
    images = list((parsing.payload or {}).get("images") or []) if parsing else []
    pages = {
        page.page_number: page
        for page in (
            await session.scalars(
                select(DocumentPage).where(DocumentPage.document_id == document.id)
            )
        ).all()
    }
    checkpoint = await _caption_checkpoint(session, document.id)
    client = OllamaClient()
    next_index = await session.scalar(
        select(func.coalesce(func.max(Chunk.chunk_index), -1)).where(
            Chunk.document_id == document.id
        )
    )
    next_index = int(next_index) + 1

    for offset, item in enumerate(images):
        if offset < checkpoint.last_completed_index:
            continue
        bbox = item.get("bbox") or {}
        width = float(bbox.get("w") or 0)
        height = float(bbox.get("h") or 0)
        if width < MIN_SIDE_PX or height < MIN_SIDE_PX:
            checkpoint.last_completed_index = offset + 1
            checkpoint.updated_at = datetime.now(timezone.utc)
            await session.commit()
            continue
        digest = item["sha256"]
        path = image_path(digest)
        if not path.is_file():
            checkpoint.last_completed_index = offset + 1
            await session.commit()
            continue
        caption = await client.vision_caption(path.read_bytes())
        page = pages.get(int(item["page_number"]))
        if page is None:
            checkpoint.last_completed_index = offset + 1
            await session.commit()
            continue
        session.add(
            Chunk(
                document_id=document.id,
                page_id=page.id,
                chunk_index=next_index,
                content=f"Figure caption: {caption}",
                modality="image_caption",
                bbox=bbox or None,
                token_count=len(caption.split()),
                metadata_={"image_sha256": digest},
            )
        )
        next_index += 1
        checkpoint.last_completed_index = offset + 1
        checkpoint.updated_at = datetime.now(timezone.utc)
        await session.commit()
