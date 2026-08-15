from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Document, IngestCheckpoint
from app.db.repositories import documents as docs_repo
from app.jobs import ingest as ingest_jobs
from app.services.hashing import sha256_bytes
from app.services.storage import delete_pdf, pdf_path, save_pdf

router = APIRouter(prefix="/documents", tags=["documents"])

PDF_MAGIC = b"%PDF"
READ_CHUNK = 1024 * 1024


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class CheckpointOut(CamelModel):
    stage: str
    last_completed_index: int
    updated_at: datetime


class DocumentOut(CamelModel):
    id: int
    filename: str
    content_sha256: str
    byte_size: int
    status: str
    page_count: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    latest_checkpoint: CheckpointOut | None = None


class DocumentListOut(CamelModel):
    items: list[DocumentOut]
    next_cursor: str | None = None


class PageDimOut(CamelModel):
    page_number: int
    width_pt: float
    height_pt: float


class DocumentPagesOut(CamelModel):
    pages: list[PageDimOut]


def _serialize_dt(value: datetime) -> str:
    iso = value.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    return iso


def document_to_out(
    doc: Document, checkpoint: IngestCheckpoint | None = None
) -> dict[str, Any]:
    payload = DocumentOut(
        id=doc.id,
        filename=doc.filename,
        content_sha256=doc.content_sha256,
        byte_size=doc.byte_size,
        status=doc.status,
        page_count=doc.page_count,
        error_code=doc.error_code,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        latest_checkpoint=(
            CheckpointOut.model_validate(checkpoint) if checkpoint else None
        ),
    )
    data = payload.model_dump(by_alias=True)
    data["createdAt"] = _serialize_dt(doc.created_at)
    data["updatedAt"] = _serialize_dt(doc.updated_at)
    if checkpoint is not None and data.get("latestCheckpoint"):
        data["latestCheckpoint"]["updatedAt"] = _serialize_dt(checkpoint.updated_at)
    return data


def document_response(doc: Document, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=document_to_out(doc))


async def _read_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(READ_CHUNK)
        if not piece:
            break
        total += len(piece)
        if total > settings.max_upload_bytes:
            raise AppError(
                "too_large",
                "File exceeds the maximum upload size.",
                status_code=413,
            )
        chunks.append(piece)
    return b"".join(chunks)


@router.post("")
async def upload_document(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    data = await _read_upload(file)
    if not data.startswith(PDF_MAGIC):
        raise AppError("invalid_pdf", "File is not a PDF.")

    digest = sha256_bytes(data)
    filename = Path(file.filename or "upload.pdf").name
    existing = await docs_repo.get_by_sha256(session, digest)

    if existing is not None and existing.status == "ready":
        return document_response(existing, status_code=200)

    save_pdf(data, digest)

    if existing is not None and existing.status == "failed":
        doc = await docs_repo.reset_failed_for_reingest(session, existing)
        try:
            await ingest_jobs.enqueue_ingest(doc.id)
        except Exception as exc:
            raise AppError(
                "dependency_unavailable",
                "Could not enqueue ingest job.",
                status_code=503,
                details={"reason": str(exc)},
            ) from exc
        return document_response(doc, status_code=202)

    if existing is not None:
        return document_response(existing, status_code=202)

    doc = await docs_repo.create_document(
        session,
        filename=filename,
        content_sha256=digest,
        byte_size=len(data),
    )
    try:
        await ingest_jobs.enqueue_ingest(doc.id)
    except Exception as exc:
        raise AppError(
            "dependency_unavailable",
            "Could not enqueue ingest job.",
            status_code=503,
            details={"reason": str(exc)},
        ) from exc
    return document_response(doc, status_code=202)


@router.get("")
async def list_documents(
    session: AsyncSession = Depends(get_session),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    rows, next_cursor = await docs_repo.list_documents(
        session, status=status, limit=limit, cursor=cursor
    )
    return {"items": [document_to_out(row) for row in rows], "nextCursor": next_cursor}


@router.get("/{document_id}")
async def get_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    doc = await docs_repo.get_by_id(session, document_id)
    if doc is None:
        raise AppError("not_found", "Document not found.", status_code=404)
    checkpoint = await docs_repo.latest_checkpoint(session, document_id)
    return document_to_out(doc, checkpoint)


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: int,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    doc = await docs_repo.get_by_id(session, document_id)
    if doc is None:
        raise AppError("not_found", "Document not found.", status_code=404)
    path = pdf_path(doc.content_sha256)
    if not path.is_file():
        raise AppError("not_found", "Document file is missing.", status_code=404)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=doc.filename,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/pages")
async def get_document_pages(
    document_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    doc = await docs_repo.get_by_id(session, document_id)
    if doc is None:
        raise AppError("not_found", "Document not found.", status_code=404)
    pages = sorted(doc.pages, key=lambda page: page.page_number)
    return DocumentPagesOut(
        pages=[
            PageDimOut(
                page_number=page.page_number,
                width_pt=float(page.width_pt),
                height_pt=float(page.height_pt),
            )
            for page in pages
        ]
    ).model_dump(by_alias=True)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    doc = await docs_repo.get_by_id(session, document_id)
    if doc is None:
        raise AppError("not_found", "Document not found.", status_code=404)
    sha256 = doc.content_sha256
    try:
        await ingest_jobs.abort_ingest(document_id)
    except Exception:
        pass
    await docs_repo.delete_document(session, doc)
    delete_pdf(sha256)
    return Response(status_code=204)
