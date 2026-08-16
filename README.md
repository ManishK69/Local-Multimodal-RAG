# Local Multimodal RAG

Privacy-first PDF question answering on localhost. Documents never leave the machine: parse, caption, embed, retrieve, and generate all run locally.

Retrieval is **hybrid**: pgvector cosine search plus Postgres full-text search (`tsvector` / `ts_rank_cd`), fused with Reciprocal Rank Fusion. This is not BM25.

## Stack

| Layer | Choice |
| --- | --- |
| Web | Next.js 15, React 19, Tailwind v4, shadcn, pdf.js |
| API | FastAPI, SQLAlchemy 2 async, Pydantic v2, uv |
| Inference | Ollama (embed, vision, generate) |
| Data | PostgreSQL 16 + pgvector + `tsvector` |
| Jobs | Redis 7 + Arq |

Published ports bind to `127.0.0.1` only.

## Quick start

Install [Docker](https://docs.docker.com/get-docker/), [Ollama](https://ollama.com/download), [uv](https://docs.astral.sh/uv/), and [Node 22](https://nodejs.org/). Start Docker Desktop and Ollama, then run one command from the repo root:

```bash
# macOS / Linux
./scripts/dev.sh

# Windows (PowerShell)
.\scripts\dev.ps1
```

That copies `.env` if needed, starts Postgres/Redis, pulls the Ollama models, installs API and web deps, migrates the database, and launches the API, ingest worker, and UI. First run can take a while because of the 7B models.

Then open `http://127.0.0.1:3000/library`. Upload `tests/fixtures/sample.pdf`. When status is Ready, open the document and ask a question. Ctrl+C stops the app; Docker stays up so the next start is faster:

```bash
./scripts/dev.sh --skip-setup
```

Useful flags: `--setup-only` (no servers), `--no-pull` (skip model downloads).

### Manual start

If you prefer to run each piece yourself:

1. Copy `.env.example` to `.env`. Default Postgres is **`127.0.0.1:5433`** (host 5432 is often taken).

2. Start Postgres (pgvector image) and Redis:

```bash
docker compose -f infra/docker-compose.yml up -d
```

3. Pull Ollama models (API listens on `http://127.0.0.1:11434`):

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
```

4. API + worker (from `apps/api`, Python 3.12):

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run arq app.worker.WorkerSettings
```

5. Web (from `apps/web`):

```bash
npm install
npm run dev
```

## Retrieval eval

With a ready fixture document and Ollama embeddings:

```bash
apps/api/.venv/Scripts/python.exe scripts/eval_retrieval.py
```

Prints vector vs hybrid hit@k. Hybrid matching vector is acceptable on this tiny set.

## Architecture (short)

```
Browser (Next.js, loopback)
  → FastAPI (upload, chat SSE)
  → Postgres (documents, chunks, pgvector, FTS)
  → Redis/Arq (ingest: parse → caption → chunk → embed)
  → Ollama (nomic-embed-text, vision captions, generate)
```

Ingest writes page-level chunks with bounding boxes. Chat retrieves with RRF, streams tokens, and the UI highlights cited PDF regions.

## Docs

Planning docs live under `docs/` (`architecture.md`, `data-model.md`, `api.md`, ADRs). Application code is in `apps/api` and `apps/web`.
