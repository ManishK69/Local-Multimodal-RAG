# ADR 0005: Ollama for all local inference

## Status

Accepted

## Context

We need embeddings, vision captions, and generation. Hugging Face Transformers in-process would mean GPU driver fights with another stack besides Ollama.

## Decision

**All inference goes through Ollama’s HTTP API:**

- embed: `nomic-embed-text` (768-d, matches `vector(768)`)
- vision: `qwen2.5vl:7b` (tier B default)
- generate: `qwen2.5:7b`

Hugging Face libraries are not used at runtime in v1. Changing `EMBEDDING_DIM` requires a new DB column or a reindex migration — treat dim as a constant for v1.

## Consequences

- One GPU runtime, one `ollama pull`
- Easy model swaps via env
- Quality depends on Ollama quantization
- Embedding model lock-in until a reindex tool exists (Phase 6 can add `scripts/reembed.py`)

## Alternatives

- **sentence-transformers for embeddings:** slightly more control, second inference stack
- **llama.cpp HTTP:** similar to Ollama; Ollama has better UX for vision tags
