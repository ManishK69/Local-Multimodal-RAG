# ADR 0006: Vision at ingest, not at query time

## Status

Accepted

## Context

Vision models are slow. Calling them on every question would dominate latency and VRAM.

## Decision

Extract images (and difficult tables as pixmaps) **once** during ingest. Store `modality = image_caption` chunks. Query path is text-only RAG over those captions plus text/table chunks.

## Consequences

- Captions can be stale if we change vision models (re-ingest)
- Questions like “what color is the line in figure 2?” work only as well as the caption
- Query latency stays in “stream within a few seconds” territory on tier B

## Alternatives

- **Page-screenshot VLM on each question:** higher fidelity, poor UX on a laptop
- **CLIP dual embeddings:** different architecture; deferred
