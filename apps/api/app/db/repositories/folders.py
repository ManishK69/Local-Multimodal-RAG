from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Folder


async def create_folder(session: AsyncSession, name: str) -> Folder:
    folder = Folder(name=name.strip())
    session.add(folder)
    await session.commit()
    await session.refresh(folder)
    return folder


async def list_folders(session: AsyncSession) -> list[tuple[Folder, int]]:
    count = func.count(Document.id)
    stmt = (
        select(Folder, count)
        .outerjoin(Document, Document.folder_id == Folder.id)
        .group_by(Folder.id)
        .order_by(Folder.created_at.desc(), Folder.id.desc())
    )
    return list((await session.execute(stmt)).all())


async def get_folder(session: AsyncSession, folder_id: int) -> Folder | None:
    return await session.scalar(
        select(Folder)
        .options(selectinload(Folder.documents))
        .where(Folder.id == folder_id)
    )


async def rename_folder(session: AsyncSession, folder: Folder, name: str) -> Folder:
    folder.name = name.strip()
    folder.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(folder)
    return folder


async def delete_folder(session: AsyncSession, folder: Folder) -> None:
    await session.delete(folder)
    await session.commit()
