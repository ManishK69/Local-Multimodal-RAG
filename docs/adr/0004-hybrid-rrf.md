# ADR 0004: Hybrid retrieval with RRF (lexical ≠ BM25)

## Status

Accepted

## Context

The blueprint asked for BM25 + vector + Reciprocal Rank Fusion. PostgreSQL built-in FTS is `tsvector` / `ts_rank_cd`, which is **not** BM25. ParadeDB (`pg_search`) provides real BM25 but adds an extension and operational risk on a laptop.

## Decision

v1 hybrid = **pgvector cosine top-k + tsvector top-k + RRF (k=60)** implemented in Python.

Marketing and README language: “hybrid vector and full-text search fused with Reciprocal Rank Fusion.” Do **not** claim BM25 until ParadeDB or an equivalent ships.

## Consequences

- Honest resume wording
- Good enough lexical channel for acronyms, figure numbers, identifiers
- Eval script must compare vector-only vs hybrid so the benefit is measured
- Upgrade path: swap the lexical function for ParadeDB BM25 without changing RRF

## Alternatives

- **rank-bm25 in Python over all chunks:** true BM25, memory-bound, fine for small corpora, extra index to maintain
- **ParadeDB now:** more correct, more moving parts
