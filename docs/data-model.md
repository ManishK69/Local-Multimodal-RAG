# Data model

PostgreSQL 16 is the system of record. Extensions: `vector` (pgvector), `pg_trgm` (optional fuzzy filename search).

Conventions:

- `bigint generated always as identity` primary keys (local single-node; sequential locality)
- `timestamptz` for all timestamps
- `text` instead of `varchar(n)` unless a real cap exists
- lowercase identifiers only
- every foreign key has a supporting btree index
- `on delete cascade` from document → pages → chunks

## ER diagram

```
folders 1───* documents 1───* document_pages 1───* chunks
                    │                                    │
                    └──* ingest_checkpoints              └── embedding vector(768)
                    │                                    └── content_tsv tsvector
                    └──* conversations 1───* messages
                                              └──* message_citations
retrieval_traces (append-only, query analytics)
```

## Tables

### folders

One-level only. A document belongs to at most one folder (`documents.folder_id`). Deleting a folder sets `folder_id` to null.

```sql
create table folders (
  id bigint generated always as identity primary key,
  name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint folders_name_chk check (char_length(btrim(name)) > 0)
);

create index folders_created_at_idx on folders (created_at desc);
```

### documents

```sql
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
  folder_id bigint references folders (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint documents_status_chk check (
    status in (
      'queued', 'parsing', 'captioning', 'chunking',
      'embedding', 'ready', 'failed'
    )
  ),
  constraint documents_sha256_chk check (content_sha256 ~ '^[a-f0-9]{64}$')
);

create unique index documents_sha256_uidx on documents (content_sha256);
create index documents_status_idx on documents (status);
create index documents_created_at_idx on documents (created_at desc);
create index documents_folder_id_idx on documents (folder_id);
```

`page_count` is null until parsing finishes.

### document_pages

```sql
create table document_pages (
  id bigint generated always as identity primary key,
  document_id bigint not null references documents (id) on delete cascade,
  page_number integer not null check (page_number >= 1),
  width_pt numeric not null check (width_pt > 0),
  height_pt numeric not null check (height_pt > 0),
  unique (document_id, page_number)
);

create index document_pages_document_id_idx on document_pages (document_id);
```

PDF user-space points. The frontend converts to canvas pixels using pdf.js viewport.

### chunks

```sql
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
      and (bbox ? 'x') and (bbox ? 'y') and (bbox ? 'w') and (bbox ? 'h')
    )
  )
);

create index chunks_document_id_idx on chunks (document_id);
create index chunks_page_id_idx on chunks (page_id);
create index chunks_content_tsv_idx on chunks using gin (content_tsv);
create index chunks_embedding_hnsw_idx on chunks
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);
```

`embedding` is null until the embed stage writes it. HNSW ignores nulls.

`bbox` shape:

```json
{ "x": 72.0, "y": 400.0, "w": 450.0, "h": 80.0 }
```

Origin: PDF user space, bottom-left, as PyMuPDF reports. The API serializes this unchanged; the frontend flips Y using `page.height_pt`.

`metadata` examples: `{ "block_type": "heading" }`, `{ "image_sha256": "...", "caption_model": "qwen2.5vl:7b" }`.

### ingest_checkpoints

```sql
create table ingest_checkpoints (
  id bigint generated always as identity primary key,
  document_id bigint not null references documents (id) on delete cascade,
  stage text not null,
  last_completed_index integer not null default 0,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique (document_id, stage)
);

create index ingest_checkpoints_document_id_idx on ingest_checkpoints (document_id);
```

Used so caption/embed can resume. `last_completed_index` is the last image or chunk fully persisted.

### conversations / messages

```sql
create table conversations (
  id bigint generated always as identity primary key,
  title text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table messages (
  id bigint generated always as identity primary key,
  conversation_id bigint not null references conversations (id) on delete cascade,
  role text not null,
  content text not null,
  created_at timestamptz not null default now(),
  constraint messages_role_chk check (role in ('user', 'assistant'))
);

create index messages_conversation_id_idx on messages (conversation_id);
create index messages_created_at_idx on messages (conversation_id, created_at);
```

### message_citations

```sql
create table message_citations (
  id bigint generated always as identity primary key,
  message_id bigint not null references messages (id) on delete cascade,
  chunk_id bigint not null references chunks (id) on delete cascade,
  marker_index integer not null check (marker_index >= 1),
  unique (message_id, marker_index)
);

create index message_citations_message_id_idx on message_citations (message_id);
create index message_citations_chunk_id_idx on message_citations (chunk_id);
```

### retrieval_traces

```sql
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
);

create index retrieval_traces_created_at_idx on retrieval_traces (created_at desc);
```

Append-only. Used by `scripts/eval_retrieval.py` and debugging. Not shown in the MVP UI.

## Query patterns

**Vector (semantic):**

```sql
select id, content, page_id, 1 - (embedding <=> :qvec) as cosine_sim
from chunks
where embedding is not null
  and (:document_ids is null or document_id = any(:document_ids))
order by embedding <=> :qvec
limit :k;
```

`<=>` is cosine distance with `vector_cosine_ops`.

**Lexical:**

```sql
select id, content, page_id,
       ts_rank_cd(content_tsv, query) as rank
from chunks,
     websearch_to_tsquery('english', :qtext) query
where content_tsv @@ query
  and (:document_ids is null or document_id = any(:document_ids))
order by rank desc
limit :k;
```

`websearch_to_tsquery` is used so user questions do not need tsquery syntax. This is **Postgres ranking, not textbook BM25**. The product still calls the channel “keyword / lexical search.” True BM25 is a later ADR (ParadeDB). Resume language must not claim BM25 until that ships; claim **hybrid vector + full-text with RRF**.

**Filter by library:** v1 has one library; optional `document_ids` on the chat request scopes retrieval.

## File storage

Not in Postgres. Original PDFs live at:

```
DATA_DIR/files/{content_sha256}.pdf
```

Postgres stores the hash and filename. Deleting a document deletes the row (cascade) and the blob.

## Migrations

Alembic in `apps/api`. One revision per schema change. Enable extensions in the first revision:

```sql
create extension if not exists vector;
```

Do not put application tables in a custom schema for v1 (`public` is fine on a private instance).

## Connection management

- FastAPI: SQLAlchemy `AsyncEngine` + `asyncpg`, pool_size 5, max_overflow 5
- Worker: separate engine, pool_size 3
- Never connect from Next.js to Postgres
- PgBouncer is unnecessary on a laptop; do not add it

## RLS

Not used in v1 (single operator, single DB role `lmrag`). The `lmrag` role owns tables; no superuser from the app. If multi-user is added, enable RLS on `documents` and force a `app.user_id` setting — out of scope now.
