# Local Multimodal RAG MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a localhost PDF RAG workbench: async ingest (parse, vision captions, embeddings), hybrid retrieval with RRF, streaming cited answers, and PDF bbox highlighting.

**Architecture:** FastAPI + Arq worker share `apps/api`. Next.js never calls Ollama. PostgreSQL 16 + pgvector is the only durable store. Vision runs at ingest; query path is text-only RAG.

**Tech Stack:** Next.js 15, React 19, Tailwind, shadcn/ui, pdf.js, FastAPI, SQLAlchemy 2 async, Pydantic v2, uv, Alembic, Arq, Redis 7, Ollama, PyMuPDF, LlamaIndex (optional/thin).

**Spec:** `docs/superpowers/specs/2026-08-15-local-multimodal-rag-design.md`

## Global Constraints

- Python 3.12, Node 22, PostgreSQL 16, Redis 7
- Embedding model `nomic-embed-text`, dimension **768** (do not change without a migration)
- Bind published ports to `127.0.0.1`
- No cloud LLM clients, no auth, PDF-only uploads
- HTTP JSON is camelCase; DB columns snake_case
- Do not claim BM25; lexical channel is `tsvector` + `ts_rank_cd`
- LlamaIndex must not persist a second index; Postgres is truth
- `DATA_DIR/files/{sha256}.pdf` is the only blob path scheme
- Tests first for pure functions (RRF, chunker, bbox, hashing, citation parse)
- Ruff + pytest for API; do not add Kubernetes, ParadeDB, or Unstructured in this plan

---

## File map (create as tasks require)

```
.gitignore
.env.example
infra/docker-compose.yml
infra/postgres/init.sql
apps/api/pyproject.toml
apps/api/alembic.ini
apps/api/alembic/env.py
apps/api/alembic/versions/0001_initial.py
apps/api/app/__init__.py
apps/api/app/main.py
apps/api/app/worker.py
apps/api/app/core/config.py
apps/api/app/core/errors.py
apps/api/app/api/deps.py
apps/api/app/api/routes/health.py
apps/api/app/api/routes/documents.py
apps/api/app/api/routes/chat.py
apps/api/app/db/session.py
apps/api/app/db/models.py
apps/api/app/db/repositories/documents.py
apps/api/app/db/repositories/chunks.py
apps/api/app/db/repositories/conversations.py
apps/api/app/services/hashing.py
apps/api/app/services/storage.py
apps/api/app/services/ollama.py
apps/api/app/services/parser.py
apps/api/app/services/chunker.py
apps/api/app/services/captions.py
apps/api/app/services/embeddings.py
apps/api/app/services/rrf.py
apps/api/app/services/retrieval.py
apps/api/app/services/citations.py
apps/api/app/services/generate.py
apps/api/app/jobs/ingest.py
apps/api/tests/test_hashing.py
apps/api/tests/test_rrf.py
apps/api/tests/test_chunker.py
apps/api/tests/test_citations.py
apps/api/tests/test_bbox.py
apps/api/tests/test_health.py
apps/web/app/library/page.tsx
apps/web/app/library/[id]/page.tsx
apps/web/lib/api.ts
apps/web/lib/pdf/bbox.ts
apps/web/lib/sse.ts
apps/web/components/pdf-preview.tsx
apps/web/components/chat-panel.tsx
scripts/eval_retrieval.py
tests/fixtures/evalset.json
```

---

### Task 1: Repo foundation and Compose

**Files:**
- Create: `.gitignore`, `.env.example`, `infra/postgres/init.sql`, `infra/docker-compose.yml`, `apps/api/pyproject.toml`, `apps/api/app/__init__.py`, `apps/api/app/core/config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Settings` loaded from env; Postgres with `vector` extension; Redis

- [ ] **Step 1: Write `.gitignore` and `.env.example`**

```
.env
data/
**/__pycache__/
.venv/
node_modules/
.next/
```

`.env.example` must match `docs/development.md` (POSTGRES_URL, REDIS_URL, OLLAMA_HOST, DATA_DIR, MAX_UPLOAD_BYTES, EMBED_MODEL, VISION_MODEL, GENERATE_MODEL, EMBEDDING_DIM=768).

- [ ] **Step 2: Write `infra/postgres/init.sql`**

```sql
create extension if not exists vector;
```

- [ ] **Step 3: Write `infra/docker-compose.yml`**

Services `postgres` (image `postgres:16`, `127.0.0.1:5432:5432`, volume, init.sql mount) and `redis` (image `redis:7`, `127.0.0.1:6379:6379`). Postgres user/db/password `lmrag`. Do not publish `0.0.0.0`.

- [ ] **Step 4: Write `apps/api/pyproject.toml`**

Dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `arq`, `redis`, `httpx`, `pymupdf`, `python-multipart`. Dev: `pytest`, `pytest-asyncio`, `ruff`. Python `>=3.12`.

- [ ] **Step 5: Write `Settings` in `apps/api/app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    postgres_url: str
    redis_url: str
    ollama_host: str = "http://127.0.0.1:11434"
    data_dir: str = "./data"
    max_upload_bytes: int = 52_428_800
    embed_model: str = "nomic-embed-text"
    vision_model: str = "qwen2.5vl:7b"
    generate_model: str = "qwen2.5:7b"
    embedding_dim: int = 768

settings = Settings()
```

- [ ] **Step 6: Boot Postgres/Redis and verify**

Run: `docker compose -f infra/docker-compose.yml up -d`
Expected: both healthy; `psql` can `\dx` and see `vector`.

- [ ] **Step 7: Commit**

```bash
git add .gitignore .env.example infra apps/api/pyproject.toml apps/api/app/core/config.py apps/api/app/__init__.py
git commit -m "chore: bootstrap api config and local postgres/redis"
```

---

### Task 2: FastAPI health endpoint

**Files:**
- Create: `apps/api/app/main.py`, `apps/api/app/core/errors.py`, `apps/api/app/api/routes/health.py`, `apps/api/app/db/session.py`, `apps/api/tests/test_health.py`
- Modify: `apps/api/app/core/config.py` if CORS origins needed

**Interfaces:**
- Consumes: `settings.postgres_url`, `settings.redis_url`, `settings.ollama_host`
- Produces: `GET /health` JSON `{status, postgres, redis, ollama, models}`; `create_app()`

- [ ] **Step 1: Write failing test `test_health_ok_when_postgres_up`**

Use FastAPI `TestClient` with dependency overrides that fake postgres=ok, redis=ok, ollama=degraded. Assert `status == "degraded"` when models missing, and CORS not required in this test.

```python
from fastapi.testclient import TestClient
from app.main import create_app

def test_health_degraded_without_ollama(monkeypatch):
    app = create_app()
    client = TestClient(app)
    # After implementation, with ollama client stubbed to fail:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["postgres"] in {"ok", "error"}
    assert "models" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_health.py -v`
Expected: FAIL with import error `app.main`

- [ ] **Step 3: Implement engine, error envelope, health router, `create_app`**

`create_app` must:
- mount health router
- CORS allow `http://127.0.0.1:3000` and `http://localhost:3000`
- JSON error shape `{ "error": { "code", "message", "details" } }`

Health checks: `SELECT 1`, Redis `PING`, Ollama `GET /api/tags`. `status` is `ok` only if postgres, redis, and all three model tags exist.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS (stub Ollama if needed; live Postgres from Compose is allowed)

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: add FastAPI health checks for postgres redis ollama"
```

---

### Task 3: Next.js shell

**Files:**
- Create: `apps/web` via `npx create-next-app@15` (TypeScript, App Router, Tailwind, ESLint, `app/` directory, no src dir)
- Create: `apps/web/lib/api.ts`, `apps/web/app/library/page.tsx`
- Modify: `apps/web/next.config.ts` rewrite `/backend/:path*` → `http://127.0.0.1:8000/:path*`

**Interfaces:**
- Consumes: `GET http://127.0.0.1:8000/health`
- Produces: `/library` page showing health pill

- [ ] **Step 1: Scaffold Next.js 15 with Tailwind**

Use React 19. Add shadcn/ui with `button`, `badge`, `card`.

- [ ] **Step 2: `lib/api.ts`**

```typescript
export const API_BASE = "/backend";

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("health failed");
  return res.json() as Promise<{
    status: string;
    postgres: string;
    redis: string;
    ollama: string;
    models: { embed: boolean; vision: boolean; generate: boolean };
  }>;
}
```

- [ ] **Step 3: Library page fetches health and renders a badge** (`ok` / `degraded` / unreachable)

- [ ] **Step 4: Manual check**

Run API + `npm run dev`. Open `http://127.0.0.1:3000/library`. Expected: health badge visible.

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat: add Next.js shell with health badge"
```

---

### Task 4: Documents schema and hashing

**Files:**
- Create: `apps/api/app/db/models.py`, `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/versions/0001_initial.py`, `apps/api/app/services/hashing.py`, `apps/api/tests/test_hashing.py`
- Schema must match `docs/data-model.md` (all tables in 0001)

**Interfaces:**
- Consumes: `Settings.postgres_url`
- Produces: ORM models; `sha256_file(path: Path) -> str`; `sha256_bytes(data: bytes) -> str`

- [ ] **Step 1: Write failing hashing tests**

```python
from app.services.hashing import sha256_bytes

def test_sha256_bytes_stable():
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")
    assert len(sha256_bytes(b"abc")) == 64
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")
```

- [ ] **Step 2: Run test — expect FAIL (`hashing` missing)**

- [ ] **Step 3: Implement `sha256_bytes` / `sha256_file` with `hashlib.sha256` hex digest**

- [ ] **Step 4: Write SQLAlchemy models exactly as `docs/data-model.md`** (documents, document_pages, chunks with `Vector(768)`, generated tsvector via `Computed`, ingest_checkpoints, conversations, messages, message_citations, retrieval_traces). Use `Mapped[...]` style.

- [ ] **Step 5: Alembic `upgrade head` against Compose Postgres**

Expected: `\dt` lists all tables; `\d chunks` shows `embedding vector(768)` and `content_tsv`.

- [ ] **Step 6: Commit**

```bash
git add apps/api
git commit -m "feat: add hashing helpers and initial pgvector schema"
```

---

### Task 5: Upload, blob storage, dedup

**Files:**
- Create: `apps/api/app/services/storage.py`, `apps/api/app/db/repositories/documents.py`, `apps/api/app/api/routes/documents.py`, `apps/api/app/api/deps.py`
- Modify: `apps/api/app/main.py` include documents router
- Test: `apps/api/tests/test_documents.py`

**Interfaces:**
- Consumes: `sha256_bytes`, `settings.data_dir`, `settings.max_upload_bytes`
- Produces:
  - `save_pdf(data: bytes, sha256: str) -> Path`
  - `POST /documents` → 202 queued or 200 existing ready
  - `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/file`, `DELETE /documents/{id}`

- [ ] **Step 1: Write failing tests**

```python
def test_rejects_non_pdf_magic(client):
    files = {"file": ("x.txt", b"not-a-pdf", "text/plain")}
    res = client.post("/documents", files=files)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_pdf"

def test_dedup_ready_returns_200(client, ready_document):
    files = {"file": ("a.pdf", ready_document.bytes, "application/pdf")}
    res = client.post("/documents", files=files)
    assert res.status_code == 200
    assert res.json()["id"] == ready_document.id
```

PDF magic: starts with `%PDF`.

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement storage + routes**

`save_pdf` writes only to `Path(settings.data_dir) / "files" / f"{sha256}.pdf"` (mkdir parents). Reject size > max. On duplicate `ready`, return existing. On duplicate `failed`, set `queued` and return 202.

Implement `enqueue_ingest(document_id: int) -> str` in `app/jobs/ingest.py` now: it enqueues Arq job name `ingest_document`. Task 6 implements the worker function body. Uploads in Task 5 must call `enqueue_ingest` so a running worker can pick jobs up as soon as Task 6 lands.

- [ ] **Step 4: Tests pass; manual upload with `%PDF-1.4` fixture**

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: store PDFs with sha256 dedup and document APIs"
```

---

### Task 6: Arq worker and ingest state machine

**Files:**
- Create: `apps/api/app/worker.py`, `apps/api/app/jobs/ingest.py`
- Modify: `apps/api/app/db/models.py` if checkpoint helpers needed
- Test: `apps/api/tests/test_ingest_state.py`

**Interfaces:**
- Consumes: `Document.status`
- Produces:
  - `async def ingest_document(ctx, document_id: int) -> None`
  - `WorkerSettings` with `functions = [ingest_document]`, `redis_settings` from `settings.redis_url`
  - `enqueue_ingest(document_id: int) -> str` returns Arq job id

- [ ] **Step 1: Write failing unit test for transitions**

```python
from app.jobs.ingest import next_status

def test_next_status_order():
    assert next_status("queued") == "parsing"
    assert next_status("parsing") == "captioning"
    assert next_status("captioning") == "chunking"
    assert next_status("chunking") == "embedding"
    assert next_status("embedding") == "ready"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `next_status` and `ingest_document` skeleton**

Skeleton must: load document; if missing return; set status along the chain; call empty stage functions `run_parse`, `run_caption`, `run_chunk`, `run_embed` defined in the same module as `async def` that currently `return` immediately (filled in later tasks). On exception: `status=failed`, store `error_code='ingest_error'`, `error_message=str(exc)[:2000]`.

- [ ] **Step 4: Run unit test PASS; start worker with `uv run arq app.worker.WorkerSettings`**

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: add Arq ingest worker state machine"
```

---

### Task 7: PyMuPDF parse and chunker

**Files:**
- Create: `apps/api/app/services/parser.py`, `apps/api/app/services/chunker.py`, `apps/api/tests/test_chunker.py`, `tests/fixtures/sample.pdf` (small 2-page PDF committed as a fixture)
- Modify: `apps/api/app/jobs/ingest.py` `run_parse` / `run_chunk`

**Interfaces:**
- Consumes: blob path from storage
- Produces:
  - `parse_pdf(path: Path) -> ParsedDocument`
  - `ParsedDocument` with `pages: list[ParsedPage]` (`page_number`, `width_pt`, `height_pt`, `blocks: list[ParsedBlock]`)
  - `ParsedBlock`: `text`, `modality` (`text`|`table`|`image`), `bbox: BBox | None`, `image_bytes: bytes | None`
  - `chunk_pages(pages, target_tokens=400, overlap_tokens=80) -> list[ChunkDraft]`
  - `ChunkDraft`: `page_number`, `content`, `modality` (`text`|`table`), `bbox`, `token_count`, `chunk_index`

Rules: never merge pages; skip images here (caption task owns images); `token_count` = `len(content.split())` (whitespace tokens are the v1 definition — do not add tiktoken).

- [ ] **Step 1: Write failing chunker tests**

```python
from app.services.chunker import chunk_pages, ParsedPage, ParsedBlock, BBox

def test_chunker_does_not_merge_pages():
    pages = [
        ParsedPage(1, 612, 792, [ParsedBlock("alpha "*50, "text", BBox(0,0,100,20), None)]),
        ParsedPage(2, 612, 792, [ParsedBlock("beta "*50, "text", BBox(0,0,100,20), None)]),
    ]
    drafts = chunk_pages(pages, target_tokens=400, overlap_tokens=80)
    assert {d.page_number for d in drafts} == {1, 2}
    assert [d.chunk_index for d in drafts] == list(range(len(drafts)))
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement parser + chunker; persist pages and chunks in `run_parse`/`run_chunk`**

`run_parse` inserts `document_pages` and sets `page_count`. `run_chunk` inserts `chunks` with `embedding=null`, `modality` text/table. Store image blocks in checkpoint payload `{"images": [{"page_number", "bbox", "sha256"}]}` and write image bytes to `DATA_DIR/images/{sha256}.png` for the caption stage. Update document status via `next_status`.

- [ ] **Step 4: pytest PASS; upload fixture PDF and confirm chunk rows**

- [ ] **Step 5: Commit**

```bash
git add apps/api tests/fixtures
git commit -m "feat: parse PDFs with PyMuPDF and page-aware chunking"
```

---

### Task 8: Ollama client and embeddings

**Files:**
- Create: `apps/api/app/services/ollama.py`, `apps/api/app/services/embeddings.py`
- Modify: `apps/api/app/jobs/ingest.py` `run_embed`
- Test: `apps/api/tests/test_embeddings.py` with httpx mock

**Interfaces:**
- Consumes: `settings.ollama_host`, `settings.embed_model`, `settings.embedding_dim`
- Produces:
  - `class OllamaClient`: `async def embed(self, texts: list[str]) -> list[list[float]]`, `async def chat`, `async def vision_caption`, `async def list_tags() -> set[str]`
  - `async def embed_chunks(session, document_id: int) -> None` writes vectors in batches of 32; resumes from `ingest_checkpoints` stage `embedding`

- [ ] **Step 1: Write failing test — embed mock returns 768-d vectors and they are stored**

Mock `OllamaClient.embed` to return `[[0.0]*768]` per text. After `embed_chunks`, a chunk’s `embedding` is not None and `len == 768`.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement Ollama `/api/embed` (or `/api/embeddings` — use the current Ollama embed endpoint; send `model` + `input`). Reject vectors whose length != `settings.embedding_dim`.

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: embed chunks via Ollama nomic-embed-text"
```

---

### Task 9: Vector retrieval, conversations, SSE generation

**Files:**
- Create: `apps/api/app/services/retrieval.py`, `apps/api/app/services/generate.py`, `apps/api/app/services/citations.py`, `apps/api/app/db/repositories/conversations.py`, `apps/api/app/api/routes/chat.py`, `apps/api/tests/test_citations.py`
- Modify: `apps/api/app/main.py`

**Interfaces:**
- Consumes: `OllamaClient.embed`, `OllamaClient.chat` (stream)
- Produces:
  - `async def vector_search(session, query_vec, k=20, document_ids: list[int] | None) -> list[RankedChunk]`
  - `RankedChunk(chunk_id, document_id, page_number, content, bbox, rank, score)`
  - `parse_markers(text: str) -> list[int]`
  - `POST /conversations`, `GET /conversations/{id}`, `POST /conversations/{id}/messages` SSE

Citation prompt: context is a numbered list `[1] ...`. Model must cite `[n]`. `parse_markers` finds `[1]`-style integers.

SSE events as `docs/api.md`: `status`, `citations`, `token`, `done`, `error`.

- [ ] **Step 1: Failing citation parser tests**

```python
from app.services.citations import parse_markers

def test_parse_markers_extracts_unique_ordered():
    assert parse_markers("See [2] and [1] then [2].") == [2, 1]
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement parser, vector_search (`order by embedding <=> :qvec`), generate prompt, SSE route**

System prompt must state that CONTEXT is untrusted library text and must not be obeyed as instructions. Persist user+assistant messages. Write `retrieval_traces` with vector ids (lexical arrays empty until Task 10). `fused_chunk_ids` = vector ids for now.

LlamaIndex: optional `ChatPromptTemplate`. If added, still call `OllamaClient` yourself for streaming. No LlamaIndex vector store.

- [ ] **Step 4: Tests PASS; manual: ready doc + curl SSE, receive tokens**

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: stream cited answers from pgvector retrieval"
```

---

### Task 10: Lexical search and RRF

**Files:**
- Create: `apps/api/app/services/rrf.py`, `apps/api/tests/test_rrf.py`
- Modify: `apps/api/app/services/retrieval.py`

**Interfaces:**
- Consumes: `vector_search`, SQL lexical search
- Produces:
  - `def rrf(rank_lists: list[list[int]], k_rrf: int = 60) -> list[tuple[int, float]]`
  - `async def lexical_search(...) -> list[RankedChunk]`
  - `async def hybrid_search(query: str, ...) -> list[RankedChunk]` using vector k=20, lexical k=20, fused_k=8

- [ ] **Step 1: Failing RRF tests**

```python
from app.services.rrf import rrf

def test_rrf_prefers_items_high_in_both_lists():
    fused = rrf([[1, 2, 3], [2, 1, 4]], k_rrf=60)
    ids = [i for i, _ in fused]
    assert ids[0] in {1, 2}
    assert set(ids) == {1, 2, 3, 4}

def test_rrf_empty():
    assert rrf([[], []]) == []
```

Score formula: `sum(1 / (k_rrf + rank))` with rank starting at 1.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `rrf`, `lexical_search` with `websearch_to_tsquery('english', query)` and `ts_rank_cd`, `hybrid_search`. Wire generate path to `hybrid_search` only.

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: fuse vector and full-text ranks with RRF"
```

---

### Task 11: Retrieval eval script

**Files:**
- Create: `scripts/eval_retrieval.py`, `tests/fixtures/evalset.json`

**Interfaces:**
- Consumes: running API with at least one ready fixture document whose id is in the eval set (or script uploads the fixture)
- Produces: stdout table: query, vector_hit@k, hybrid_hit@k, overall rates

`evalset.json`:

```json
{
  "documentFilename": "sample.pdf",
  "k": 8,
  "queries": [
    {
      "question": "replace with a string that appears only on page 2 of the fixture",
      "relevantPageNumbers": [2]
    }
  ]
}
```

Hit = any fused chunk’s `page_number` is in `relevantPageNumbers`.

- [ ] **Step 1: Write evalset against the committed fixture (choose real strings from `sample.pdf`)**

- [ ] **Step 2: Implement script using `hybrid_search` and `vector_search` internally via `httpx` **or** importing services. Importing `app.services.retrieval` is preferred (no HTTP flakiness). Print both rates.

- [ ] **Step 3: Run: `uv run python scripts/eval_retrieval.py`**

Expected: script exits 0 and hybrid_hit >= vector_hit on this tiny set (if equal, that is acceptable; do not fake a win).

- [ ] **Step 4: Commit**

```bash
git add scripts tests/fixtures
git commit -m "feat: add retrieval eval comparing vector and hybrid"
```

---

### Task 12: Vision captions

**Files:**
- Create: `apps/api/app/services/captions.py`
- Modify: `apps/api/app/jobs/ingest.py` `run_caption`, `app/services/ollama.py`

**Interfaces:**
- Consumes: checkpoint images from Task 7, `OllamaClient.vision_caption(image_bytes: bytes) -> str`
- Produces: chunks with `modality='image_caption'`, `content` prefixed `Figure caption: `, bbox from the image, metadata `{ "image_sha256": "..." }`

Skip images with width or height < 16 px. Resume via `ingest_checkpoints` stage `captioning`.

- [ ] **Step 1: Test with mocked vision_caption returning `"A bar chart of loss."`**

Assert a chunk is inserted with modality `image_caption` and that text.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement Ollama vision call (`/api/chat` with images array per Ollama vision API). Then `run_caption`.

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: caption extracted figures with local vision model"
```

---

### Task 13: Chat UI streaming

**Files:**
- Create: `apps/web/lib/sse.ts`, `apps/web/components/chat-panel.tsx`, `apps/web/app/library/[id]/page.tsx`
- Modify: `apps/web/lib/api.ts` with document and conversation helpers

**Interfaces:**
- Consumes: SSE contract from Task 9
- Produces: working chat panel on `/library/[id]` scoped with `documentIds: [id]`

- [ ] **Step 1: `parseSse(stream)` yields `{ event, data }` objects; unit-test with a fake stream of two `token` events if you add `vitest`, otherwise a tiny node script. Prefer vitest on `lib/sse.ts`.**

SSE parser must handle `event:` + `data:` + blank line.

- [ ] **Step 2: Chat panel: textarea, send, append tokens, render `[n]` as buttons stored from the `citations` event**

- [ ] **Step 3: Manual: stream visible in UI**

- [ ] **Step 4: Commit**

```bash
git add apps/web
git commit -m "feat: stream RAG answers in the document chat panel"
```

---

### Task 14: PDF preview and bbox overlay

**Files:**
- Create: `apps/web/lib/pdf/bbox.ts`, `apps/web/components/pdf-preview.tsx`, `apps/api/tests/test_bbox.py` is web — put tests next to bbox: `apps/web/lib/pdf/bbox.test.ts`
- Modify: `apps/web/app/library/[id]/page.tsx` split layout
- Also add `GET /documents/{id}/pages` if missing from Task 5

**Interfaces:**
- Consumes: `GET /documents/{id}/file`, page dimensions, citation bbox
- Produces: `pdfToViewport(bbox, pageHeightPt, scale) -> { x, y, w, h }`

Y-flip: `y' = (pageHeightPt - bbox.y - bbox.h) * scale`.

- [ ] **Step 1: Failing test**

```typescript
import { pdfToViewport } from "./bbox";

test("flips y from PDF origin", () => {
  const r = pdfToViewport({ x: 0, y: 0, w: 100, h: 10 }, 792, 1);
  expect(r.y).toBe(782);
  expect(r.h).toBe(10);
});
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement math + pdf.js canvas + overlay div; click citation sets page and rectangle. Null bbox → page border flash.

- [ ] **Step 4: Tests PASS; manual highlight on fixture**

- [ ] **Step 5: Commit**

```bash
git add apps/web apps/api
git commit -m "feat: highlight cited PDF regions from chunk bboxes"
```

---

### Task 15: Library upload UX and ingest polling

**Files:**
- Modify: `apps/web/app/library/page.tsx`
- Create: `apps/web/components/upload-dropzone.tsx`

**Interfaces:**
- Consumes: `POST /documents` multipart, `GET /documents/{id}`
- Produces: dropzone, list with status labels matching the state machine, poll 1500 ms until `ready` or `failed`

- [ ] **Step 1: Dropzone accepts `application/pdf` only**
- [ ] **Step 2: Optimistic row + polling**
- [ ] **Step 3: Failed shows `errorMessage`**
- [ ] **Step 4: Manual upload through UI to Ready**
- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat: poll ingest status from the library dropzone"
```

---

### Task 16: Phase 6 polish (README + settings + re-ingest)

**Files:**
- Modify: `README.md`, `apps/api/app/api/routes/documents.py` (failed re-upload already in Task 5)
- Create: `apps/web/app/settings/page.tsx` (`GET /settings`), `apps/api/app/api/routes/settings.py`

**Interfaces:**
- Produces: `GET /settings` as in `docs/api.md`; README clone-to-demo instructions; architecture summary; honest hybrid-search wording (no BM25)

- [ ] **Step 1: Settings endpoint + read-only UI (models + health)**
- [ ] **Step 2: Rewrite root README for operators (compose, ollama pull, demo script)**
- [ ] **Step 3: Confirm delete document removes blob and cascaded rows**
- [ ] **Step 4: Commit**

```bash
git add README.md apps
git commit -m "docs: add operator README and read-only settings"
```

---

## Self-review

**Spec coverage**

| Spec section | Tasks |
| --- | --- |
| Local isolation / loopback | 1, 2, 16 |
| Ingest state machine | 6–8, 12 |
| PyMuPDF + bboxes | 7, 14 |
| Vision at ingest | 12 |
| pgvector query | 9 |
| Hybrid + RRF | 10 |
| SSE citations | 9, 13 |
| PDF overlay | 14 |
| Eval | 11 |
| Dedup sha256 | 4, 5 |
| No BM25 claim | 10, 16 |
| Health/models | 2, 16 |

**Type names locked:** `Settings`, `ParsedDocument`, `ParsedPage`, `ParsedBlock`, `BBox`, `ChunkDraft`, `RankedChunk`, `OllamaClient`, `ingest_document`, `hybrid_search`, `rrf`, `parse_markers`, `pdfToViewport`.

Do not introduce a second vector table, Unstructured, or cloud providers while executing this plan.
