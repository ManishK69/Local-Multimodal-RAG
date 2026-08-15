from datetime import datetime
from urllib.parse import unquote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Conversation, Message, MessageCitation


def encode_cursor(created_at: datetime, conversation_id: int) -> str:
    return f"{created_at.isoformat()}|{conversation_id}"


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    created_raw, id_raw = unquote(cursor).split("|", 1)
    return datetime.fromisoformat(created_raw), int(id_raw)


async def create_conversation(
    session: AsyncSession, title: str | None = None
) -> Conversation:
    conversation = Conversation(title=title or "New conversation")
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def get_conversation(
    session: AsyncSession, conversation_id: int
) -> Conversation | None:
    return await session.scalar(
        select(Conversation)
        .options(
            selectinload(Conversation.messages).selectinload(Message.citations)
        )
        .where(Conversation.id == conversation_id)
    )


async def list_conversations(
    session: AsyncSession,
    *,
    limit: int,
    cursor: str | None,
) -> tuple[list[Conversation], str | None]:
    stmt = select(Conversation).order_by(
        Conversation.created_at.desc(), Conversation.id.desc()
    )
    if cursor:
        created_at, conversation_id = decode_cursor(cursor)
        stmt = stmt.where(
            (Conversation.created_at < created_at)
            | (
                (Conversation.created_at == created_at)
                & (Conversation.id < conversation_id)
            )
        )
    stmt = stmt.limit(limit + 1)
    rows = list(await session.scalars(stmt))
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return rows, next_cursor


async def add_message(
    session: AsyncSession, conversation_id: int, role: str, content: str
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def add_citations(
    session: AsyncSession, message_id: int, pairs: list[tuple[int, int]]
) -> None:
    for marker_index, chunk_id in pairs:
        session.add(
            MessageCitation(
                message_id=message_id,
                chunk_id=chunk_id,
                marker_index=marker_index,
            )
        )
    await session.commit()


async def delete_conversation(
    session: AsyncSession, conversation: Conversation
) -> None:
    await session.delete(conversation)
    await session.commit()
