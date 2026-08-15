# ADR 0001: PostgreSQL + pgvector over Qdrant

## Status

Accepted

## Context

The blueprint allowed PostgreSQL + pgvector **or** Qdrant. We need vectors, lexical search, document metadata, conversations, and job checkpoints.

## Decision

Use **PostgreSQL 16 with pgvector** as the only durable store. Redis is ephemeral.

## Consequences

- One backup/restore story, one migration tool (Alembic), ACID deletes
- HNSW in-process with chunk rows; no dual-write to a vector DB
- Lexical search via `tsvector` in the same table
- Scale ceiling is “laptop / single node,” which matches the product
- If we ever need specialized vector ops at 10M+ chunks, Qdrant can be added behind the retriever interface — not before

## Alternatives

- **Qdrant + Postgres:** better vector ops, two systems, dual write, worse deletes
- **Chroma / LanceDB:** easier demos, weaker SQL story, worse resume signal for “systems + Postgres”
