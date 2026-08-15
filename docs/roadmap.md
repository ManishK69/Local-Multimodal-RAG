# Roadmap

Each phase ships working, demoable software. Do not start Phase N+1 until Phase N’s acceptance checks pass.

## Phase 0 — Foundation

Repo skeleton, Compose (Postgres + Redis), FastAPI health, Next.js shell, Alembic empty head, config.

**Exit:** `GET /health` reports postgres + redis. Web loads. Ollama may be `degraded`.

## Phase 1 — Durable documents

Upload PDF, SHA-256 dedup, blob storage, `documents` rows, list/delete, file download endpoint.

**Exit:** Round-trip a PDF through API without parsing.

## Phase 2 — Parse and chunk

Arq worker, PyMuPDF parse, pages + text/table chunks with bboxes, status machine through `chunking` (embeddings still null).

**Exit:** After upload, DB has page rows and chunks; UI shows Parsing → Chunking.

## Phase 3 — Embed + vector chat

Ollama embeddings, HNSW query, LlamaIndex-or-custom prompt, SSE generation, persist messages.

**Exit:** Ask a question on a ready PDF; streamed answer with at least page-level citations.

## Phase 4 — Hybrid retrieval

Lexical `tsvector` channel + RRF. Eval script comparing vector-only vs hybrid hit-rate@k.

**Exit:** Eval shows hybrid ≥ vector on the fixture set; at least one query where hybrid wins.

## Phase 5 — Multimodal captions + PDF overlay

Vision captions for extracted images; `image_caption` chunks; pdf.js preview; bbox overlay; citation click-through.

**Exit:** The 3-minute demo in the product brief works.

## Phase 6 — Hardening (resume polish)

Retry failed ingest, retrieval traces in README, eval numbers, settings/health banner, fixture corpus documented, architecture diagram in README.

**Exit:** A stranger can clone, compose up, pull models, and reproduce the demo from README alone.

## Deferred (not in the MVP plan)

| Item | Why later |
| --- | --- |
| Unstructured / Office files | PDF provenance is the product; Office is a parser expansion |
| ParadeDB true BM25 | tsvector + RRF is enough to teach hybrid retrieval |
| Cross-encoder rerank | Extra model + latency; add after eval plateau |
| Auth / multi-user | Conflicts with “localhost single operator” |
| Cloud LLM fallback | Conflicts with privacy story unless feature-flagged off by default |
| Eval dashboard UI | CLI eval is enough |
| Kubernetes | Not a laptop demo |

## Suggested calendar (part-time, 10–12 hours/week)

| Week | Phase |
| --- | --- |
| 1 | 0–1 |
| 2 | 2 |
| 3 | 3 |
| 4 | 4 |
| 5 | 5 |
| 6 | 6 + README + recordings |

## Follow-on plans

When Phase 5 is done, write a new implementation plan for the next slice (Office ingest **or** rerank **or** collections) — not all three.
