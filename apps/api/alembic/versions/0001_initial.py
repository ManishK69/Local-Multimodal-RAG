"""Initial pgvector schema."""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("create extension if not exists vector")
    op.execute(
        """
        create table documents (
          id bigint generated always as identity primary key,
          filename text not null,
          content_sha256 text not null,
          mime_type text not null default 'application/pdf',
          byte_size bigint not null check (byte_size > 0),
          page_count integer,
          status text not null,
          error_code text,
          error_message text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint documents_status_chk check (
            status in (
              'queued', 'parsing', 'captioning', 'chunking',
              'embedding', 'ready', 'failed'
            )
          ),
          constraint documents_sha256_chk check (content_sha256 ~ '^[a-f0-9]{64}$')
        )
        """
    )
    op.execute(
        "create unique index documents_sha256_uidx on documents (content_sha256)"
    )
    op.execute("create index documents_status_idx on documents (status)")
    op.execute(
        "create index documents_created_at_idx on documents (created_at desc)"
    )
    op.execute(
        """
        create table document_pages (
          id bigint generated always as identity primary key,
          document_id bigint not null references documents (id) on delete cascade,
          page_number integer not null check (page_number >= 1),
          width_pt numeric not null check (width_pt > 0),
          height_pt numeric not null check (height_pt > 0),
          unique (document_id, page_number)
        )
        """
    )
    op.execute(
        "create index document_pages_document_id_idx on document_pages (document_id)"
    )
    op.execute(
        """
        create table chunks (
          id bigint generated always as identity primary key,
          document_id bigint not null references documents (id) on delete cascade,
          page_id bigint not null references document_pages (id) on delete cascade,
          chunk_index integer not null check (chunk_index >= 0),
          content text not null,
          content_tsv tsvector generated always as (
            to_tsvector('english', content)
          ) stored,
          modality text not null,
          bbox jsonb,
          token_count integer not null check (token_count >= 0),
          embedding vector(768),
          metadata jsonb not null default '{}'::jsonb,
          unique (document_id, chunk_index),
          constraint chunks_modality_chk check (
            modality in ('text', 'table', 'image_caption')
          ),
          constraint chunks_bbox_chk check (
            bbox is null or (
              jsonb_typeof(bbox) = 'object'
              and (bbox ? 'x') and (bbox ? 'y')
              and (bbox ? 'w') and (bbox ? 'h')
            )
          )
        )
        """
    )
    op.execute("create index chunks_document_id_idx on chunks (document_id)")
    op.execute("create index chunks_page_id_idx on chunks (page_id)")
    op.execute(
        "create index chunks_content_tsv_idx on chunks using gin (content_tsv)"
    )
    op.execute(
        """
        create index chunks_embedding_hnsw_idx on chunks
          using hnsw (embedding vector_cosine_ops)
          with (m = 16, ef_construction = 64)
        """
    )
    op.execute(
        """
        create table ingest_checkpoints (
          id bigint generated always as identity primary key,
          document_id bigint not null references documents (id) on delete cascade,
          stage text not null,
          last_completed_index integer not null default 0,
          payload jsonb not null default '{}'::jsonb,
          updated_at timestamptz not null default now(),
          unique (document_id, stage)
        )
        """
    )
    op.execute(
        "create index ingest_checkpoints_document_id_idx "
        "on ingest_checkpoints (document_id)"
    )
    op.execute(
        """
        create table conversations (
          id bigint generated always as identity primary key,
          title text not null default 'New conversation',
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        """
        create table messages (
          id bigint generated always as identity primary key,
          conversation_id bigint not null references conversations (id)
            on delete cascade,
          role text not null,
          content text not null,
          created_at timestamptz not null default now(),
          constraint messages_role_chk check (role in ('user', 'assistant'))
        )
        """
    )
    op.execute(
        "create index messages_conversation_id_idx on messages (conversation_id)"
    )
    op.execute(
        """
        create index messages_created_at_idx
          on messages (conversation_id, created_at)
        """
    )
    op.execute(
        """
        create table message_citations (
          id bigint generated always as identity primary key,
          message_id bigint not null references messages (id) on delete cascade,
          chunk_id bigint not null references chunks (id) on delete cascade,
          marker_index integer not null check (marker_index >= 1),
          unique (message_id, marker_index)
        )
        """
    )
    op.execute(
        "create index message_citations_message_id_idx "
        "on message_citations (message_id)"
    )
    op.execute(
        "create index message_citations_chunk_id_idx on message_citations (chunk_id)"
    )
    op.execute(
        """
        create table retrieval_traces (
          id bigint generated always as identity primary key,
          conversation_id bigint references conversations (id) on delete set null,
          message_id bigint references messages (id) on delete set null,
          query text not null,
          embed_model text not null,
          generate_model text not null,
          vector_chunk_ids bigint[] not null,
          lexical_chunk_ids bigint[] not null,
          fused_chunk_ids bigint[] not null,
          fused_scores numeric[] not null,
          latency_embed_ms integer,
          latency_retrieve_ms integer,
          latency_generate_ms integer,
          created_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        "create index retrieval_traces_created_at_idx "
        "on retrieval_traces (created_at desc)"
    )


def downgrade() -> None:
    op.execute("drop table if exists retrieval_traces")
    op.execute("drop table if exists message_citations")
    op.execute("drop table if exists messages")
    op.execute("drop table if exists conversations")
    op.execute("drop table if exists ingest_checkpoints")
    op.execute("drop table if exists chunks")
    op.execute("drop table if exists document_pages")
    op.execute("drop table if exists documents")
