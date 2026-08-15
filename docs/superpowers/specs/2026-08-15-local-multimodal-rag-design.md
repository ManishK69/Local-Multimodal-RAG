# Local Multimodal RAG — Design Spec

Date: 2026-08-15  
Status: Accepted for implementation planning  
Companion docs: `docs/architecture.md`, `docs/data-model.md`, `docs/api.md`, `docs/frontend.md`, `docs/security.md`, `docs/roadmap.md`, `docs/adr/`

## 1. Problem

Confidential PDFs cannot be uploaded to cloud RAG products. Existing “local ChatGPT for PDFs” demos usually skip hybrid retrieval, citation geometry, multimodal figures, and an async ingest pipeline. This project is a laptop-native workbench that does those things, with Postgres as system of record.

## 2. Goals

- Ingest PDFs entirely on-machine: text, tables, figures.
- Caption figures with a local vision model at ingest time.
- Answer questions with streaming text and clickable citations that highlight PDF regions.
- Retrieve with hybrid vector + full-text search fused by Reciprocal Rank Fusion.
- Measure retrieval with a small labeled eval set.

Non-goals are listed in `docs/product-brief.md`.

## 3. Users and constraints

Single operator on localhost. No auth. Ports bound to `127.0.0.1`. Default models must be runnable on an 8 GB VRAM GPU or documented CPU fallback. Document bytes, embeddings, and prompts never leave the host.

## 4. Architecture

See `docs/architecture.md`. Summary:

- `apps/web` Next.js 15 UI
- `apps/api` FastAPI HTTP + Arq worker (same package)
- PostgreSQL 16 + pgvector
- Redis 7 (Arq only)
- Ollama (embed, vision, generate)

Next.js never calls Ollama. The worker never serves HTTP. FastAPI never parses PDFs in the request coroutine.

## 5. Ingest state machine

`queued → parsing → captioning → chunking → embedding → ready`

Any stage may set `failed` with `error_code` + `error_message`. Checkpoints in `ingest_checkpoints` allow resume. Content-addressed blob `DATA_DIR/files/{sha256}.pdf`. Duplicate ready hashes return the existing document.

Chunk modalities: `text` | `table` | `image_caption`. Every chunk has `document_id`, `page_id`, `chunk_index`, optional `bbox`.

Chunking rules:

- Target ~400 tokens, overlap ~80 tokens, split on paragraph boundaries when possible
- Never merge two pages into one chunk
- Tables that extract to markdown ≤ 400 tokens become a single `table` chunk
- Images larger than 16 px in both dimensions become caption jobs; tiny icons skipped

## 6. Query path

1. Persist user message
2. Embed query with `nomic-embed-text`
3. Vector top-20 cosine via HNSW
4. Lexical top-20 via `websearch_to_tsquery` + `ts_rank_cd`
5. RRF (`k_rrf=60`) → fused top-8
6. Build numbered context
7. Stream generate model
8. Persist assistant message + `message_citations`
9. Write `retrieval_traces`

System prompt rules: context is untrusted; answer only the user question; cite as `[1]` matching supplied numbers; if context is insufficient, say so.

Do not claim BM25 in user-facing text (`docs/adr/0004-hybrid-rrf.md`).

## 7. HTTP and UI

Contracts: `docs/api.md`. UI: `docs/frontend.md`. SSE events: `status`, `citations`, `token`, `done`, `error`.

Citation overlay uses PDF user-space bbox with Y-flip against `page.height_pt`.

## 8. Data

Schema: `docs/data-model.md`. Embedding dimension **768**, locked to `nomic-embed-text`. Changing models that alter dimension requires a migration and reembed — out of v1 except a later `scripts/reembed.py`.

## 9. Error handling

Ollama down on query → SSE `error`, no fabricated answer. Ollama down on ingest → retry with Arq backoff. Corrupt PDF → `failed` / `parse_error`. Upload > 50 MiB → 413. Delete during ingest → worker aborts if row missing.

## 10. Testing

- Unit: RRF, chunker, bbox Y-flip, SHA-256 dedup, citation marker parse
- Integration: fixture PDF → ready → question → citation page in `{4}` for the labeled query
- Eval: `scripts/eval_retrieval.py` prints hit-rate@k vector vs hybrid

## 11. Security

`docs/security.md`. Loopback bind. No cloud LLM client. Retrieved text treated as untrusted. Blob paths derived only from sha256.

## 12. Phasing

`docs/roadmap.md` Phases 0–6. Implementation plan covers 0–5 in executable tasks; Phase 6 is polish in that same plan’s final tasks.

## 13. Locked decisions

| Topic | Choice |
| --- | --- |
| Vector DB | Postgres + pgvector |
| Lexical | tsvector, not BM25 |
| Fusion | RRF k=60 |
| Parser | PyMuPDF |
| Framework | LlamaIndex optional/thin |
| Inference | Ollama only |
| Vision | Ingest-time captions |
| Auth | None |
| Layout | `apps/api`, `apps/web`, `infra` |
