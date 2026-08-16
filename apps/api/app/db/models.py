from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="folders_name_chk"),
        Index("folders_created_at_idx", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="folder")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'parsing', 'captioning', 'chunking', "
            "'embedding', 'ready', 'failed')",
            name="documents_status_chk",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[a-f0-9]{64}$'",
            name="documents_sha256_chk",
        ),
        CheckConstraint("byte_size > 0", name="documents_byte_size_chk"),
        Index("documents_sha256_uidx", "content_sha256", unique=True),
        Index("documents_status_idx", "status"),
        Index("documents_created_at_idx", text("created_at DESC")),
        Index("documents_folder_id_idx", "folder_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="application/pdf"
    )
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    folder_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("folders.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    folder: Mapped["Folder | None"] = relationship(back_populates="documents")
    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        CheckConstraint("page_number >= 1", name="document_pages_page_number_chk"),
        CheckConstraint("width_pt > 0", name="document_pages_width_pt_chk"),
        CheckConstraint("height_pt > 0", name="document_pages_height_pt_chk"),
        UniqueConstraint("document_id", "page_number"),
        Index("document_pages_document_id_idx", "document_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(nullable=False)
    width_pt: Mapped[Any] = mapped_column(Numeric, nullable=False)
    height_pt: Mapped[Any] = mapped_column(Numeric, nullable=False)

    document: Mapped[Document] = relationship(back_populates="pages")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="chunks_chunk_index_chk"),
        CheckConstraint("token_count >= 0", name="chunks_token_count_chk"),
        CheckConstraint(
            "modality in ('text', 'table', 'image_caption')",
            name="chunks_modality_chk",
        ),
        CheckConstraint(
            "bbox is null or (jsonb_typeof(bbox) = 'object' "
            "and (bbox ? 'x') and (bbox ? 'y') and (bbox ? 'w') and (bbox ? 'h'))",
            name="chunks_bbox_chk",
        ),
        UniqueConstraint("document_id", "chunk_index"),
        Index("chunks_document_id_idx", "document_id"),
        Index("chunks_page_id_idx", "page_id"),
        Index("chunks_content_tsv_idx", "content_tsv", postgresql_using="gin"),
        Index(
            "chunks_embedding_hnsw_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
    )
    modality: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    token_count: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(768))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    page: Mapped[DocumentPage] = relationship(back_populates="chunks")


class IngestCheckpoint(Base):
    __tablename__ = "ingest_checkpoints"
    __table_args__ = (
        UniqueConstraint("document_id", "stage"),
        Index("ingest_checkpoints_document_id_idx", "document_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    last_completed_index: Mapped[int] = mapped_column(nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    title: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="New conversation"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="messages_role_chk"),
        Index("messages_conversation_id_idx", "conversation_id"),
        Index("messages_created_at_idx", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list["MessageCitation"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageCitation(Base):
    __tablename__ = "message_citations"
    __table_args__ = (
        CheckConstraint("marker_index >= 1", name="message_citations_marker_chk"),
        UniqueConstraint("message_id", "marker_index"),
        Index("message_citations_message_id_idx", "message_id"),
        Index("message_citations_chunk_id_idx", "chunk_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    marker_index: Mapped[int] = mapped_column(nullable=False)

    message: Mapped[Message] = relationship(back_populates="citations")


class RetrievalTrace(Base):
    __tablename__ = "retrieval_traces"
    __table_args__ = (
        Index("retrieval_traces_created_at_idx", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("conversations.id", ondelete="SET NULL")
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    embed_model: Mapped[str] = mapped_column(Text, nullable=False)
    generate_model: Mapped[str] = mapped_column(Text, nullable=False)
    vector_chunk_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False
    )
    lexical_chunk_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False
    )
    fused_chunk_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False
    )
    fused_scores: Mapped[list[Any]] = mapped_column(ARRAY(Numeric), nullable=False)
    latency_embed_ms: Mapped[int | None]
    latency_retrieve_ms: Mapped[int | None]
    latency_generate_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
