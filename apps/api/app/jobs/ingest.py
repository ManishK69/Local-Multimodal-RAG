from datetime import datetime, timezone
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from arq.constants import default_queue_name, job_key_prefix, result_key_prefix
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Chunk, Document, DocumentPage, IngestCheckpoint
from app.db.session import SessionLocal
from app.services.chunker import chunk_pages
from app.services.parser import image_manifest, parse_pdf
from app.services.storage import pdf_path, save_image

STATUS_ORDER = (
    "queued",
    "parsing",
    "captioning",
    "chunking",
    "embedding",
    "ready",
)


def next_status(status: str) -> str:
    try:
        index = STATUS_ORDER.index(status)
    except ValueError as exc:
        raise ValueError(f"unknown ingest status: {status}") from exc
    if index >= len(STATUS_ORDER) - 1:
        raise ValueError(f"no transition from {status}")
    return STATUS_ORDER[index + 1]


def ingest_job_id(document_id: int) -> str:
    return f"ingest-document-{document_id}"


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def _drop_job(redis: Any, document_id: int) -> None:
    job_id = ingest_job_id(document_id)
    await redis.delete(job_key_prefix + job_id, result_key_prefix + job_id)
    await redis.zrem(default_queue_name, job_id)


async def enqueue_ingest(document_id: int) -> str:
    redis = await create_pool(_redis_settings())
    try:
        await _drop_job(redis, document_id)
        job_id = ingest_job_id(document_id)
        job = await redis.enqueue_job(
            "ingest_document",
            document_id,
            _job_id=job_id,
        )
        return job.job_id if job is not None else job_id
    finally:
        await redis.aclose()


async def abort_ingest(document_id: int) -> None:
    redis = await create_pool(_redis_settings())
    try:
        await _drop_job(redis, document_id)
    except Exception:
        return
    finally:
        await redis.aclose()


async def run_parse(session: AsyncSession, document: Document) -> None:
    parsed = parse_pdf(pdf_path(document.content_sha256))
    await session.execute(
        delete(DocumentPage).where(DocumentPage.document_id == document.id)
    )
    for page in parsed.pages:
        session.add(
            DocumentPage(
                document_id=document.id,
                page_number=page.page_number,
                width_pt=page.width_pt,
                height_pt=page.height_pt,
            )
        )
    document.page_count = len(parsed.pages)

    images = []
    for item in image_manifest(parsed):
        save_image(item["bytes"], item["sha256"])
        images.append(
            {
                "page_number": item["page_number"],
                "bbox": item["bbox"],
                "sha256": item["sha256"],
            }
        )

    checkpoint = await session.scalar(
        select(IngestCheckpoint).where(
            IngestCheckpoint.document_id == document.id,
            IngestCheckpoint.stage == "parsing",
        )
    )
    if checkpoint is None:
        session.add(
            IngestCheckpoint(
                document_id=document.id,
                stage="parsing",
                last_completed_index=len(parsed.pages),
                payload={"images": images},
            )
        )
    else:
        checkpoint.last_completed_index = len(parsed.pages)
        checkpoint.payload = {"images": images}
        checkpoint.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def run_caption(session: AsyncSession, document: Document) -> None:
    return


async def run_chunk(session: AsyncSession, document: Document) -> None:
    parsed = parse_pdf(pdf_path(document.content_sha256))
    drafts = chunk_pages(parsed.pages)
    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    pages = {
        page.page_number: page
        for page in (
            await session.scalars(
                select(DocumentPage).where(DocumentPage.document_id == document.id)
            )
        ).all()
    }
    for draft in drafts:
        page = pages[draft.page_number]
        session.add(
            Chunk(
                document_id=document.id,
                page_id=page.id,
                chunk_index=draft.chunk_index,
                content=draft.content,
                modality=draft.modality,
                bbox=draft.bbox.as_dict() if draft.bbox else None,
                token_count=draft.token_count,
            )
        )
    await session.commit()


async def run_embed(session: AsyncSession, document: Document) -> None:
    return


def _touch(document: Document, status: str) -> None:
    document.status = status
    document.updated_at = datetime.now(timezone.utc)


async def ingest_document(ctx: dict[str, Any], document_id: int) -> None:
    async with SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        try:
            if document.status == "queued":
                _touch(document, next_status(document.status))
                await session.commit()

            stages = (
                ("parsing", run_parse),
                ("captioning", run_caption),
                ("chunking", run_chunk),
                ("embedding", run_embed),
            )
            for expected, stage in stages:
                if document.status != expected:
                    continue
                await stage(session, document)
                _touch(document, next_status(expected))
                await session.commit()
        except Exception as exc:
            document.status = "failed"
            document.error_code = "ingest_error"
            document.error_message = str(exc)[:2000]
            document.updated_at = datetime.now(timezone.utc)
            await session.commit()
