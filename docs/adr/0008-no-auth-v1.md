# ADR 0008: No authentication in v1

## Status

Accepted

## Context

Adding JWT/local users before the RAG loop works delays the demo and invites a false sense of security.

## Decision

No signup, no sessions. Bind API and published Compose ports to **127.0.0.1**. Treat anyone who can run processes on the machine as the operator.

## Consequences

- Fastest path to a real product loop
- README must state: this is not LAN-safe
- Multi-user becomes a new spec (RLS, user_id on documents) rather than a bolt-on middleware
