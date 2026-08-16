from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routes.documents import document_to_out
from app.core.errors import AppError
from app.db.models import Folder
from app.db.repositories import folders as folder_repo

router = APIRouter(prefix="/folders", tags=["folders"])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class FolderCreate(CamelModel):
    name: str = Field(min_length=1, max_length=200)


class FolderPatch(CamelModel):
    name: str = Field(min_length=1, max_length=200)


def _serialize_dt(value: datetime) -> str:
    iso = value.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    return iso


def folder_out(folder: Folder, document_count: int | None = None) -> dict[str, Any]:
    count = document_count
    if count is None:
        count = len(folder.documents) if folder.documents is not None else 0
    return {
        "id": folder.id,
        "name": folder.name,
        "documentCount": int(count),
        "createdAt": _serialize_dt(folder.created_at),
        "updatedAt": _serialize_dt(folder.updated_at),
    }


@router.post("", status_code=201)
async def create_folder(
    body: FolderCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    name = body.name.strip()
    if not name:
        raise AppError("validation_error", "Folder name is required.", status_code=422)
    folder = await folder_repo.create_folder(session, name)
    return folder_out(folder, 0)


@router.get("")
async def list_folders(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = await folder_repo.list_folders(session)
    return {
        "items": [folder_out(folder, count) for folder, count in rows],
    }


@router.get("/{folder_id}")
async def get_folder(
    folder_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    folder = await folder_repo.get_folder(session, folder_id)
    if folder is None:
        raise AppError("not_found", "Folder not found.", status_code=404)
    documents = sorted(folder.documents, key=lambda item: item.created_at, reverse=True)
    payload = folder_out(folder, len(documents))
    payload["documents"] = [document_to_out(doc) for doc in documents]
    return payload


@router.patch("/{folder_id}")
async def patch_folder(
    folder_id: int,
    body: FolderPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    folder = await folder_repo.get_folder(session, folder_id)
    if folder is None:
        raise AppError("not_found", "Folder not found.", status_code=404)
    name = body.name.strip()
    if not name:
        raise AppError("validation_error", "Folder name is required.", status_code=422)
    folder = await folder_repo.rename_folder(session, folder, name)
    return folder_out(folder)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    folder = await folder_repo.get_folder(session, folder_id)
    if folder is None:
        raise AppError("not_found", "Folder not found.", status_code=404)
    await folder_repo.delete_folder(session, folder)
