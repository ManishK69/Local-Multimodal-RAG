# Architecture

## Overview

Local Multimodal RAG is a **localhost platform** with five runtime pieces:

1. **Web** — Next.js 15 App Router UI (library, PDF preview, chat)
2. **API** — FastAPI app: HTTP, orchestration, streaming
3. **Worker** — Arq worker: parse, caption, chunk, embed
4. **PostgreSQL 16 + pgvector** — system of record
5. **Ollama** — local embeddings, vision captions, answer generation
6. **Redis** — Arq broker and short-lived cache (not durable state)

```
Browser (127.0.0.1:3000)
    │  REST + SSE
    ▼
Next.js (BFF: proxies /api/* to FastAPI, serves PDF.js UI)
    │
    ▼
FastAPI (127.0.0.1:8000)
    ├── SQLAlchemy ──► PostgreSQL (documents, chunks, vectors, FTS, chat)
    ├── Arq enqueue ──► Redis
    └── Ollama HTTP   ► generate (query path only)
                              ▲
Arq worker ── parse/caption/embed ──┘
    ├── PyMuPDF (text, tables, images, bboxes)
    ├── Ollama vision (image → caption)
    └── Ollama embeddings (chunk → vector)
```

Next.js does **not** call Ollama. All model I/O goes through the API or the worker so streaming, citations, and privacy controls stay in one place.

## Design principles

1. **Postgres is truth.** Vectors and lexical indexes live next to the chunk rows they describe. Redis jobs may be lost; a worker can rebuild progress from `documents.status`.
2. **Ingest is a state machine.** The HTTP request only stores the file and enqueues work. The UI polls (or later SSE) document status.
3. **Vision at ingest, text at query.** Captioning is expensive and cacheable. Query-time calls a text model with retrieved context.
4. **Provenance on every chunk.** If a bbox cannot be determined, the chunk is still stored with page number and `bbox = null`; the UI falls back to page-level highlight.
5. **Thin RAG framework.** LlamaIndex is used for query planning helpers and prompt assembly, not as a second database. Custom retrievers read Postgres.

## Components

### `apps/web`

Responsibility: presentation and interaction.

- Library: upload, list, status badges, delete
- Reader: pdf.js canvas + highlight overlay
- Chat: composer, streamed markdown, citation chips
- Settings: Ollama host, model names, retrieval `k` (advanced)

Talks only to the FastAPI surface (via Next.js rewrite or `NEXT_PUBLIC_API_URL` on localhost).

### `apps/api` (FastAPI process)

Responsibility: synchronous-looking HTTP, validation, query-path RAG.

Modules (one job each):

| Module | Does |
| --- | --- |
| `api/routes/documents.py` | Upload, list, get, delete, status |
| `api/routes/chat.py` | Create conversation, stream answer |
| `api/routes/health.py` | Liveness + dependency checks (Postgres, Redis, Ollama) |
| `services/storage.py` | Write/read original PDFs from local disk |
| `services/retrieval.py` | Vector query, lexical query, RRF |
| `services/generate.py` | Prompt + Ollama stream + citation parse |
| `services/ollama.py` | Typed client (embed, chat, vision) |
| `db/` | Engine, session, models, migrations |

The FastAPI process **enqueues** ingest; it does not parse PDFs inline.

### `apps/api` worker (Arq)

Same codebase, different entrypoint (`arq app.worker.WorkerSettings`).

Pipeline stages, each resumable:

1. **parse** — PyMuPDF → pages, text blocks, tables, image bytes + bboxes
2. **caption** — for each image/table-as-image, Ollama vision → caption text
3. **chunk** — page-aware overlapping chunks; tables stay intact when small
4. **embed** — batch embeddings into `chunks.embedding`
5. **index** — generated `tsvector` is maintained by Postgres; HNSW is already on the column
6. **ready** or **failed**

Crash recovery: worker loads `documents.status` and `ingest_checkpoints` and continues from the last completed stage.

### PostgreSQL

See [data-model.md](data-model.md). Holds files metadata, pages, chunks (text + vector + tsvector), conversations, messages, ingest checkpoints.

### Redis + Arq

- Queue: `ingest`
- Job uniqueness key: `ingest:{document_id}` so double-clicks do not double-parse
- Optional cache: query embedding for identical strings (TTL 1 hour) — safe because data is local

### Ollama

Three logical models, possibly the same physical tag:

- `embed_model` — `nomic-embed-text` (768-d)
- `vision_model` — `qwen2.5vl:7b` (tier B)
- `generate_model` — `qwen2.5:7b`

Client timeouts are long (minutes) on caption/generate. Health check uses `/api/tags`.

## Data flows

### Ingest

```
POST /documents
  → validate PDF magic bytes + size cap
  → sha256
  → if hash exists and status=ready: return existing (200)
  → write blob to data/files/{sha256}.pdf
  → insert documents (status=queued)
  → enqueue Arq ingest
  → 202 { document }

Worker:
  queued → parsing → captioning → chunking → embedding → ready
```

Idempotency: blob path is content-addressed. Re-enqueue of a `failed` document deletes derived rows (pages, chunks) but not the blob, then restarts the state machine.

### Query

```
POST /conversations/{id}/messages (SSE)
  → persist user message
  → embed question
  → vector top-k (HNSW cosine)
  → lexical top-k (tsvector @@ query, order ts_rank_cd)
  → RRF fuse, take fused_k
  → build context blocks with cite ids
  → stream generate_model
  → parse citation markers
  → persist assistant message + citations JSON
```

No query-time vision unless a later phase adds “look at this page.”

## Reciprocal Rank Fusion

For document id lists `R1` (vector) and `R2` (lexical):

```
score(d) = Σ 1 / (k_rrf + rank_i(d))
```

Default `k_rrf = 60`, `k_vector = 20`, `k_lexical = 20`, `fused_k = 8` context chunks.

RRF is implemented in `services/retrieval.py` with unit tests on known rank lists. It does not live in SQL for v1 (small `k`).

## LlamaIndex role

LlamaIndex is a **library**, not a platform:

- Use `ChatPromptTemplate` / response synthesis helpers if they stay thin
- Custom `PostgresHybridRetriever` implements `retrieve(query) -> list[NodeWithScore]`
- Do **not** use LlamaIndex vector stores as a parallel index
- Do **not** persist a second docstore on disk

If LlamaIndex abstractions fight Postgres, drop them and keep our retriever + prompts. The ADR allows this escape hatch.

## Error handling

| Failure | Behavior |
| --- | --- |
| Ollama down on query | SSE error event; user message kept; no fake answer |
| Ollama down on ingest | Stage stays `captioning`/`embedding`; job retries with backoff |
| Corrupt PDF | `status=failed`, `error_code=parse_error`, human message |
| Oversize upload | 413 before disk write |
| Worker crash mid-embed | Checkpointed chunk index; resume embed from last written id |
| Delete document during job | Job checks `documents.id` still exists; aborts |

## Observability (v1, logs + tables)

Every query writes `retrieval_traces`: question, chunk ids, ranks, fused scores, model names, latency_ms. The eval script reads this table. No third-party APM.

## Deployment topology (local)

`infra/docker-compose.yml`:

| Service | Ports (localhost) |
| --- | --- |
| `web` | 3000 |
| `api` | 8000 |
| `worker` | none |
| `postgres` | 5432 |
| `redis` | 6379 |
| `ollama` | 11434 |

Compose may mount the host Ollama socket/data so models are not re-downloaded inside the container. Document both “Ollama in Compose” and “Ollama on host” in the development guide.

API and web bind `127.0.0.1` in the process, not `0.0.0.0`, when run outside Compose. Compose publishes ports only to the host loopback via `127.0.0.1:8000:8000`.

## Testing strategy

- **Unit:** RRF, chunker boundaries, citation parser, SHA-256 dedup
- **Integration:** API + Postgres (testcontainers or Compose profile `test`) — upload a fixture PDF, wait until ready, query, assert citation page
- **Eval:** `scripts/eval_retrieval.py` on `tests/fixtures/evalset.json`
- **Frontend:** component tests for citation overlay math; Playwright later (Phase 5)

## What we are not building

A plugin host, a multi-tenant SaaS, or an agent graph. Those would collapse the component boundaries above.
