from dataclasses import dataclass

import pytest
from app.core.config import settings
from app.db.models import Document
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.services.hashing import sha256_bytes
from app.services.storage import save_pdf
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@dataclass
class ReadyDocument:
    id: int
    bytes: bytes


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
async def client(data_dir, monkeypatch):
    async def _fake_enqueue(document_id: int) -> str:
        return f"job-{document_id}"

    monkeypatch.setattr("app.jobs.ingest.enqueue_ingest", _fake_enqueue)
    await engine.dispose()
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def ready_document(data_dir) -> ReadyDocument:
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
            filename="a.pdf",
            content_sha256=digest,
            mime_type="application/pdf",
            byte_size=len(PDF_BYTES),
            status="ready",
            page_count=1,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id
    yield ReadyDocument(id=doc_id, bytes=PDF_BYTES)
    await engine.dispose()
    async with SessionLocal() as session:
        leftover = await session.get(Document, doc_id)
        if leftover is not None:
            await session.delete(leftover)
            await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_rejects_non_pdf_magic(client):
    files = {"file": ("x.txt", b"not-a-pdf", "text/plain")}
    res = await client.post("/documents", files=files)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_pdf"


@pytest.mark.asyncio
async def test_dedup_ready_returns_200(client, ready_document):
    files = {"file": ("a.pdf", ready_document.bytes, "application/pdf")}
    res = await client.post("/documents", files=files)
    assert res.status_code == 200
    assert res.json()["id"] == ready_document.id


@pytest.mark.asyncio
async def test_ready_without_pages_is_reingested(client, data_dir):
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
            filename="a.pdf",
            content_sha256=digest,
            mime_type="application/pdf",
            byte_size=len(PDF_BYTES),
            status="ready",
            page_count=None,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id

    files = {"file": ("a.pdf", PDF_BYTES, "application/pdf")}
    res = await client.post("/documents", files=files)
    assert res.status_code == 202
    payload = res.json()
    assert payload["id"] == doc_id
    assert payload["status"] == "queued"

    async with SessionLocal() as session:
        leftover = await session.get(Document, doc_id)
        if leftover is not None:
            await session.delete(leftover)
            await session.commit()
