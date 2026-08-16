import pytest
from app.core.config import settings
from app.db.models import Document
from app.db.session import SessionLocal, engine
from app.jobs.ingest import ingest_document
from app.services.hashing import sha256_bytes
from app.services.storage import save_pdf
from sqlalchemy import select

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_ingest_fails_when_parse_produces_no_pages(data_dir, monkeypatch):
    async def _noop_parse(session, document):
        return

    monkeypatch.setattr("app.jobs.ingest.run_parse", _noop_parse)
    await engine.dispose()
    digest = sha256_bytes(PDF_BYTES)
    save_pdf(PDF_BYTES, digest)
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(Document).where(Document.content_sha256 == digest)
        )
        if existing is not None:
            await session.delete(existing)
            await session.commit()
        doc = Document(
            filename="empty-parse.pdf",
            content_sha256=digest,
            mime_type="application/pdf",
            byte_size=len(PDF_BYTES),
            status="queued",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id

    await ingest_document({}, doc_id)

    async with SessionLocal() as session:
        stored = await session.get(Document, doc_id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.page_count is None
        await session.delete(stored)
        await session.commit()
