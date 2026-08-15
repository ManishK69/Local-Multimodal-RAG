# Product brief

## Problem

Knowledge workers and engineers need to ask questions over private PDFs (research papers, design docs, financial statements, medical records). Cloud RAG products require uploading those files. That is a non-starter for anything confidential, and it hides the systems work that makes retrieval accurate.

## Product

A **local multimodal RAG workbench**:

1. Drop a PDF onto a web UI running on `127.0.0.1`.
2. A background pipeline extracts text, tables, and figures; captions figures with a local vision model; chunks with page + bounding-box provenance; embeds locally.
3. Ask questions in a chat panel. Answers stream token-by-token, cite source chunks, and highlight the corresponding regions on a PDF preview.

Nothing in the document corpus, prompts, or embeddings leaves the machine.

## Primary user (v1)

A single operator on a developer laptop (Windows, macOS, or Linux) with:

- Docker Desktop (or Docker Engine)
- Ollama installed, with enough RAM/VRAM for the chosen model tier
- A browser

No accounts. No internet required after model weights are pulled.

## Jobs to be done

| Job | Acceptance signal |
| --- | --- |
| Ingest a multi-page PDF without blocking the UI | Upload returns immediately; job progress is visible |
| Ask a factual question answered in the PDF | Streamed answer with at least one valid citation |
| Trust the answer | Clicking a citation jumps the preview to the page and highlights the bbox |
| Understand figures/charts | Questions about a chart are answered from the vision caption + nearby text |
| Re-ingest safely | Same file hash is detected as a duplicate; failed jobs can be retried |

## Success criteria (demo / resume)

A 3-minute demo must show:

1. Upload of a 10–30 page PDF with mixed text, a table, and a figure
2. Live ingest stages: `queued → parsing → captioning → embedding → ready`
3. A question whose answer is **not** in the first paragraph of page 1 (forces retrieval)
4. Streaming tokens
5. Two or more inline citations; click highlights the PDF
6. A second question that needs a keyword (acronym, figure number, statute id) so hybrid search is visibly better than vector-only

Engineering bar (not shown in the demo, but in the README and tests):

- Retrieval evaluation script with hit-rate@k on a small labeled set
- Hybrid RRF vs vector-only comparison printed by that script
- Typed API, migrations, and a job that is idempotent on `content_sha256`

## MVP scope (Phase 0–5)

In:

- PDF only
- Single library (no collections/tenants)
- Local Ollama models
- Hybrid search (vector + lexical) fused with Reciprocal Rank Fusion
- Vision captions at ingest time (not during every query)
- Chat with streaming and page-level citation highlighting
- Bind to localhost

Out:

- Auth / multi-user / sharing
- DOCX, PPTX, HTML, images-as-documents
- Cloud LLM fallback
- Agent tools, web search, code execution
- Kubernetes, object storage, multi-node workers

## Later (explicitly deferred)

- Collections and tags
- Cross-encoder rerank
- True BM25 via ParadeDB or a dedicated lexical engine
- Office parsers (Unstructured)
- Eval dashboard UI
- Optional encryption-at-rest for the data directory
- Multi-user with local auth

## Constraints

- **Privacy:** document bytes, derived text, embeddings, and prompts never leave localhost. Model pull from the internet is allowed and explicit.
- **Laptop-class:** default models must run on 16 GB RAM CPU or 8 GB VRAM. Larger models are a documented upgrade, not a requirement.
- **One system of record:** PostgreSQL holds documents, chunks, vectors, FTS, conversations. Redis is ephemeral (jobs + cache), not source of truth.
- **Citations are a product feature, not a prompt afterthought:** every chunk stores `document_id`, `page_number`, and `bbox`.
- **YAGNI:** no plugin marketplace, no multi-agent graph, no custom training loop.

## Hardware tiers

| Tier | Typical hardware | Models (defaults) |
| --- | --- | --- |
| A — CPU / 16 GB RAM | Dev laptop, no GPU | `qwen2.5:3b` generate, skip vision or use tiny captioner, `nomic-embed-text` |
| B — 8 GB VRAM | Default target | `qwen2.5:7b` generate, `qwen2.5vl:7b` captions, `nomic-embed-text` |
| C — 12–24 GB VRAM | Showcase | `llama3.1:8b` or `qwen2.5:14b`, `llama3.2-vision:11b` |

Config selects models. The pipeline does not hard-code names.

## Resume narrative (honest)

This is not “I wrapped ChatGPT around PDFs.” The interesting work is:

- Multimodal ingest with provenance (bboxes, modalities)
- Hybrid retrieval and fusion
- Async job architecture that survives retries
- Streaming grounded generation
- An evaluation loop that measures retrieval, not vibes
