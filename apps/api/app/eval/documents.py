from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.models import Document
from app.db.repositories import documents as docs_repo
from app.db.session import SessionLocal
from app.jobs.ingest import ingest_document
from app.services.hashing import sha256_bytes
from app.services.storage import save_pdf


async def ensure_document_ready(fixture_dir: Path, filename: str) -> int:
    """Ingest a fixture PDF unless it is already ready; return its document id.

    Documents are deduplicated by content hash, so re-running is cheap.
    """
    data = (fixture_dir / filename).read_bytes()
    digest = sha256_bytes(data)
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(Document).where(Document.content_sha256 == digest)
        )
        if existing is None:
            save_pdf(data, digest)
            existing = await docs_repo.create_document(
                session,
                filename=filename,
                content_sha256=digest,
                byte_size=len(data),
            )
        doc_id = existing.id
        status = existing.status
    if status != "ready":
        await ingest_document({}, doc_id)
    async with SessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if doc is None or doc.status != "ready":
            status = getattr(doc, "status", None)
            raise SystemExit(f"document {doc_id} is not ready (status={status})")
    return doc_id
