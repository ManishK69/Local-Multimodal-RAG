from datetime import datetime
from urllib.parse import unquote

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Chunk, Document, DocumentPage, IngestCheckpoint


def encode_cursor(created_at: datetime, document_id: int) -> str:
    return f"{created_at.isoformat()}|{document_id}"


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    created_raw, id_raw = unquote(cursor).split("|", 1)
    return datetime.fromisoformat(created_raw), int(id_raw)


async def get_by_id(session: AsyncSession, document_id: int) -> Document | None:
    return await session.scalar(
        select(Document)
        .options(selectinload(Document.pages))
        .where(Document.id == document_id)
    )


async def get_by_sha256(session: AsyncSession, sha256: str) -> Document | None:
    return await session.scalar(
        select(Document).where(Document.content_sha256 == sha256)
    )


async def create_document(
    session: AsyncSession,
    *,
    filename: str,
    content_sha256: str,
    byte_size: int,
    status: str = "queued",
) -> Document:
    doc = Document(
        filename=filename,
        content_sha256=content_sha256,
        mime_type="application/pdf",
        byte_size=byte_size,
        status=status,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def list_documents(
    session: AsyncSession,
    *,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[Document], str | None]:
    stmt = select(Document).order_by(Document.created_at.desc(), Document.id.desc())
    if status:
        stmt = stmt.where(Document.status == status)
    if cursor:
        created_at, document_id = decode_cursor(cursor)
        stmt = stmt.where(
            (Document.created_at < created_at)
            | ((Document.created_at == created_at) & (Document.id < document_id))
        )
    stmt = stmt.limit(limit + 1)
    rows = list(await session.scalars(stmt))
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return rows, next_cursor


async def latest_checkpoint(
    session: AsyncSession, document_id: int
) -> IngestCheckpoint | None:
    return await session.scalar(
        select(IngestCheckpoint)
        .where(IngestCheckpoint.document_id == document_id)
        .order_by(IngestCheckpoint.updated_at.desc())
        .limit(1)
    )


async def reset_failed_for_reingest(session: AsyncSession, doc: Document) -> Document:
    await session.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    await session.execute(
        delete(DocumentPage).where(DocumentPage.document_id == doc.id)
    )
    await session.execute(
        delete(IngestCheckpoint).where(IngestCheckpoint.document_id == doc.id)
    )
    doc.status = "queued"
    doc.error_code = None
    doc.error_message = None
    doc.page_count = None
    await session.commit()
    await session.refresh(doc)
    return doc


async def delete_document(session: AsyncSession, doc: Document) -> None:
    await session.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    await session.execute(
        delete(DocumentPage).where(DocumentPage.document_id == doc.id)
    )
    await session.delete(doc)
    await session.commit()
