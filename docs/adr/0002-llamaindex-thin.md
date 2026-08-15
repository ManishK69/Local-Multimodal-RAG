# ADR 0002: LlamaIndex as a thin library

## Status

Accepted

## Context

The blueprint allowed LlamaIndex or LangChain. Both can become a second platform (their own stores, agents, callbacks).

## Decision

Use **LlamaIndex only where it shortens prompt/retriever glue**. Postgres remains the index. If LlamaIndex fights that model, delete the dependency and keep `services/retrieval.py` + `services/generate.py`.

LangChain is not a v1 dependency.

## Consequences

- We own retrieval quality (RRF, filters, traces)
- Less magic, more testable functions
- Some community recipes (query engines) may not apply 1:1

## Alternatives

- **LangChain:** stronger agents/tools; we are not building agents in v1
- **No framework:** fully custom prompts; acceptable fallback
