import pytest
from app.core.config import settings
from app.db.models import Chunk, Document, DocumentPage, IngestCheckpoint
from app.db.session import SessionLocal, engine
from app.jobs.ingest import run_caption
from app.services.hashing import sha256_bytes
from app.services.ollama import OllamaClient
from app.services.storage import save_image, save_pdf
from sqlalchemy import select

PDF_BYTES = b"%PDF-1.4\n%caption-test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _png_32() -> bytes:
    import pymupdf as fitz

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32), 1)
    pix.clear_with(255)
    return pix.tobytes("png")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_caption_inserts_image_caption_chunk(data_dir, monkeypatch):
    async def fake_caption(self, image_bytes: bytes) -> str:
        return "A bar chart of loss."

    monkeypatch.setattr(OllamaClient, "vision_caption", fake_caption)
    await engine.dispose()
    png = _png_32()
    digest = sha256_bytes(PDF_BYTES)
    image_digest = sha256_bytes(png)
    save_pdf(PDF_BYTES, digest)
    save_image(png, image_digest)

    async with SessionLocal() as session:
        existing = await session.scalar(
            select(Document).where(Document.content_sha256 == digest)
        )
        if existing is not None:
            await session.delete(existing)
            await session.commit()
        doc = Document(
            filename="caption.pdf",
            content_sha256=digest,
            mime_type="application/pdf",
            byte_size=len(PDF_BYTES),
            status="captioning",
            page_count=1,
        )
        session.add(doc)
        await session.flush()
        session.add(
            DocumentPage(
                document_id=doc.id,
                page_number=1,
                width_pt=612,
                height_pt=792,
            )
        )
        session.add(
            IngestCheckpoint(
                document_id=doc.id,
                stage="parsing",
                last_completed_index=1,
                payload={
                    "images": [
                        {
                            "page_number": 1,
                            "bbox": {"x": 10, "y": 20, "w": 100, "h": 80},
                            "sha256": image_digest,
                        }
                    ]
                },
            )
        )
        await session.commit()
        doc_id = doc.id

        document = await session.get(Document, doc_id)
        await run_caption(session, document)
        chunks = list(
            await session.scalars(
                select(Chunk).where(Chunk.document_id == doc_id)
            )
        )
        assert any(
            chunk.modality == "image_caption"
            and "A bar chart of loss." in chunk.content
            for chunk in chunks
        )
        leftover = await session.get(Document, doc_id)
        if leftover is not None:
            await session.delete(leftover)
            await session.commit()
    await engine.dispose()
