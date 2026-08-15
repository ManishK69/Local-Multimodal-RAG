import pytest
from app.core.config import settings
from app.db.models import Chunk, Document, DocumentPage
from app.db.session import SessionLocal, engine
from app.services.embeddings import embed_chunks
from app.services.hashing import sha256_bytes
from app.services.ollama import OllamaClient
from app.services.storage import save_pdf
from sqlalchemy import select

PDF_BYTES = b"%PDF-1.4\n%embed-test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_embed_chunks_stores_768d_vectors(data_dir, monkeypatch):
    async def fake_embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 768 for _ in texts]

    monkeypatch.setattr(OllamaClient, "embed", fake_embed)
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
            filename="embed.pdf",
            content_sha256=digest,
            mime_type="application/pdf",
            byte_size=len(PDF_BYTES),
            status="embedding",
            page_count=1,
        )
        session.add(doc)
        await session.flush()
        page = DocumentPage(
            document_id=doc.id,
            page_number=1,
            width_pt=612,
            height_pt=792,
        )
        session.add(page)
        await session.flush()
        chunk = Chunk(
            document_id=doc.id,
            page_id=page.id,
            chunk_index=0,
            content="hello embedding world",
            modality="text",
            token_count=3,
        )
        session.add(chunk)
        await session.commit()
        doc_id = doc.id
        chunk_id = chunk.id

    async with SessionLocal() as session:
        await embed_chunks(session, doc_id)
        await session.commit()

    async with SessionLocal() as session:
        stored = await session.get(Chunk, chunk_id)
        assert stored is not None
        assert stored.embedding is not None
        assert len(list(stored.embedding)) == 768
        leftover = await session.get(Document, doc_id)
        if leftover is not None:
            await session.delete(leftover)
            await session.commit()
    await engine.dispose()
