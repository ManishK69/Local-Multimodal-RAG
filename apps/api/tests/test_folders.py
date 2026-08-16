import pytest
from app.core.config import settings
from app.db.models import Document, Folder
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.services.hashing import sha256_bytes
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

PDF_A = b"%PDF-1.4\nfolder-a\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PDF_B = b"%PDF-1.4\nfolder-b\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


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


async def _cleanup(*document_ids: int, folder_ids: list[int] | None = None) -> None:
    await engine.dispose()
    async with SessionLocal() as session:
        for document_id in document_ids:
            leftover = await session.get(Document, document_id)
            if leftover is not None:
                await session.delete(leftover)
        if folder_ids:
            for folder_id in folder_ids:
                leftover = await session.get(Folder, folder_id)
                if leftover is not None:
                    await session.delete(leftover)
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_list_and_get_folder(client):
    created = await client.post("/folders", json={"name": "  Q3 filings  "})
    assert created.status_code == 201
    folder = created.json()
    assert folder["name"] == "Q3 filings"
    assert folder["documentCount"] == 0
    folder_id = folder["id"]

    listed = await client.get("/folders")
    assert listed.status_code == 200
    assert any(item["id"] == folder_id for item in listed.json()["items"])

    detail = await client.get(f"/folders/{folder_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["documents"] == []

    await _cleanup(folder_ids=[folder_id])


@pytest.mark.asyncio
async def test_upload_into_folder_and_filter(client):
    created = await client.post("/folders", json={"name": "Contracts"})
    folder_id = created.json()["id"]

    res = await client.post(
        "/documents",
        files={"file": ("a.pdf", PDF_A, "application/pdf")},
        data={"folderId": str(folder_id)},
    )
    assert res.status_code == 202
    doc = res.json()
    assert doc["folderId"] == folder_id
    doc_id = doc["id"]

    in_folder = await client.get("/documents", params={"folderId": folder_id})
    assert [item["id"] for item in in_folder.json()["items"]] == [doc_id]

    unfiled = await client.get("/documents", params={"unfiled": "true"})
    assert doc_id not in [item["id"] for item in unfiled.json()["items"]]

    await _cleanup(doc_id, folder_ids=[folder_id])


@pytest.mark.asyncio
async def test_move_document_and_delete_folder_unfiles(client):
    created = await client.post("/folders", json={"name": "Keep"})
    folder_id = created.json()["id"]
    uploaded = await client.post(
        "/documents",
        files={"file": ("b.pdf", PDF_B, "application/pdf")},
    )
    doc_id = uploaded.json()["id"]
    assert uploaded.json()["folderId"] is None

    moved = await client.patch(
        f"/documents/{doc_id}", json={"folderId": folder_id}
    )
    assert moved.status_code == 200
    assert moved.json()["folderId"] == folder_id

    deleted = await client.delete(f"/folders/{folder_id}")
    assert deleted.status_code == 204

    remaining = await client.get(f"/documents/{doc_id}")
    assert remaining.status_code == 200
    assert remaining.json()["folderId"] is None

    missing = await client.get(f"/folders/{folder_id}")
    assert missing.status_code == 404

    await _cleanup(doc_id)


@pytest.mark.asyncio
async def test_blank_folder_name_rejected(client):
    res = await client.post("/folders", json={"name": "   "})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_upload_into_missing_folder(client):
    res = await client.post(
        "/documents",
        files={"file": ("missing.pdf", PDF_A, "application/pdf")},
        data={"folderId": "999999"},
    )
    assert res.status_code == 404
    leftover = None
    await engine.dispose()
    async with SessionLocal() as session:
        leftover = await session.scalar(
            select(Document).where(Document.content_sha256 == sha256_bytes(PDF_A))
        )
        if leftover is not None:
            await session.delete(leftover)
            await session.commit()
