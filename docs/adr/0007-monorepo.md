# ADR 0007: Monorepo with apps/api and apps/web

## Status

Accepted

## Context

Two runtimes (Python, Node). We want one git history for a portfolio project.

## Decision

Single repo:

- `apps/api` — uv project
- `apps/web` — Next.js
- `infra/` — Compose
- `docs/` — this planning set

No npm workspaces, no shared package, no Nx/Turborepo until a third app appears.

## Consequences

- Simple clone
- CI can be two jobs later
- Some DTO duplication between Pydantic and TypeScript types — acceptable; keep payloads small
