# Local Multimodal RAG

A privacy-first retrieval-augmented generation platform that runs entirely on your machine. PDFs are parsed locally (text, tables, figures), figures are captioned by a local vision model, and answers are grounded in page-level citations — no document content is sent to a cloud API.

This repository currently contains **architecture and development planning documents**. Application code is not scaffolded yet; follow the implementation plan when you are ready to build.

## Why this exists

Top-tier engineering interviews and resumes reward projects that combine:

- **Privacy-preserving ML** — local inference with Ollama
- **Deep learning systems** — multimodal ingest, embeddings, hybrid retrieval
- **Scalable backend design** — async APIs, job queues, Postgres as system of record

This project is scoped to be demoable on a laptop and designed so the same architecture can grow.

## Documentation map

| Document | What it covers |
| --- | --- |
| [docs/README.md](docs/README.md) | Index of all planning docs |
| [docs/product-brief.md](docs/product-brief.md) | Vision, users, MVP vs later, success criteria |
| [docs/architecture.md](docs/architecture.md) | System design, data flow, component boundaries |
| [docs/data-model.md](docs/data-model.md) | Postgres schema, indexes, vector/FTS design |
| [docs/api.md](docs/api.md) | HTTP contracts, streaming, error model |
| [docs/frontend.md](docs/frontend.md) | Next.js UX, citation highlighting, state |
| [docs/security.md](docs/security.md) | Local-only threat model and controls |
| [docs/development.md](docs/development.md) | Repo layout, tooling, conventions |
| [docs/roadmap.md](docs/roadmap.md) | Phased delivery |
| [docs/adr/](docs/adr/) | Architecture Decision Records |
| [docs/superpowers/specs/2026-08-15-local-multimodal-rag-design.md](docs/superpowers/specs/2026-08-15-local-multimodal-rag-design.md) | Canonical design spec |
| [docs/superpowers/plans/2026-08-15-mvp-implementation.md](docs/superpowers/plans/2026-08-15-mvp-implementation.md) | Bite-sized implementation plan |

## Locked stack (MVP)

| Layer | Choice |
| --- | --- |
| Frontend | Next.js 15 (App Router), React 19, Tailwind CSS, shadcn/ui, pdf.js |
| Backend | FastAPI, async SQLAlchemy 2, Pydantic v2, uv |
| Inference | Ollama — text LLM, vision LLM, embeddings |
| RAG | LlamaIndex (thin adapters; Postgres is source of truth) |
| Data | PostgreSQL 16 + pgvector + `tsvector` |
| Jobs / cache | Redis 7 + Arq |
| Compose | Postgres, Redis, Ollama, API, web |

## Non-goals for v1

Multi-user auth, cloud model providers, Office/HTML ingest, agent tool-use, and production Kubernetes. Those are designed as extension points, not MVP work.

## Status

**Phase: pre-implementation.** Read the product brief, then the architecture doc, then the MVP plan.
