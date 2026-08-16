# API design

Base URL: `http://127.0.0.1:8000`

All JSON request/response bodies are camelCase in the HTTP layer (`filename`, `pageCount`) via Pydantic aliases. Database columns remain snake_case.

Auth: none. The process listens on loopback. CORS allows `http://127.0.0.1:3000` and `http://localhost:3000` only.

## Errors

```json
{
  "error": {
    "code": "parse_error",
    "message": "PyMuPDF could not open this file as a PDF.",
    "details": {}
  }
}
```

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `invalid_pdf` | Magic bytes / extension mismatch |
| 404 | `not_found` | Unknown id |
| 409 | `duplicate_ready` | Same hash already ready (optional; prefer 200 return existing) |
| 413 | `too_large` | Over `MAX_UPLOAD_BYTES` (default 50 MiB) |
| 422 | `validation_error` | Pydantic |
| 503 | `dependency_unavailable` | Postgres, Redis, or Ollama down |
| 500 | `internal` | Unexpected |

## Health

`GET /health`

```json
{
  "status": "ok",
  "postgres": "ok",
  "redis": "ok",
  "ollama": "ok",
  "models": {
    "embed": true,
    "vision": true,
    "generate": true
  }
}
```

`status` is `degraded` if Ollama models are missing but Postgres is up. `ok` only when all three models are present. UI shows a setup banner on `degraded`.

## Documents

### `POST /documents`

`multipart/form-data`: `file` required, `folderId` optional (places the PDF in that folder).

Response `202`:

```json
{
  "id": 1,
  "filename": "attention.pdf",
  "contentSha256": "ab…",
  "byteSize": 123456,
  "status": "queued",
  "pageCount": null,
  "folderId": null,
  "createdAt": "2026-08-15T21:00:00Z"
}
```

If the hash already exists and `status=ready`, return `200` with that document (dedup). If `folderId` is sent, the existing file is moved into that folder. If it exists and is `failed`, return `202` and re-enqueue.

### `GET /documents`

Query: `status`, `limit` (default 50, max 200), `cursor` (created_at,id), `folderId`, `unfiled=true`.

`unfiled=true` returns documents with `folderId` null. `folderId` returns only that folder. Neither returns the full library.

### `PATCH /documents/{id}`

```json
{ "folderId": 3 }
```

`folderId` may be `null` to unfile. Exclusive membership: a document is in at most one folder.

### `GET /documents/{id}`

Includes `errorCode`, `errorMessage`, and latest checkpoint summary.

### `GET /documents/{id}/file`

`application/pdf` stream of the original blob. Used by pdf.js. `Content-Disposition: inline`.

### `GET /documents/{id}/pages`

Page dimensions for overlay math:

```json
{
  "pages": [
    { "pageNumber": 1, "widthPt": 612, "heightPt": 792 }
  ]
}
```

### `DELETE /documents/{id}`

`204`. Cascades DB rows, deletes blob, best-effort abort of Arq job.

## Folders

One-level folders only. Deleting a folder sets `documents.folder_id` to null (files return to the library root).

### `POST /folders`

```json
{ "name": "Q3 filings" }
```

`201` `{ "id": 1, "name": "Q3 filings", "documentCount": 0, "createdAt": "...", "updatedAt": "..." }`

### `GET /folders`

```json
{ "items": [{ "id": 1, "name": "Q3 filings", "documentCount": 2 }] }
```

### `GET /folders/{id}`

Folder plus its documents.

### `PATCH /folders/{id}`

```json
{ "name": "Q3 filings (final)" }
```

### `DELETE /folders/{id}` → `204`

## Conversations

### `POST /conversations`

```json
{ "title": "Attention questions" }
```

`201` `{ "id": 1, "title": "...", "createdAt": "..." }`

### `GET /conversations`

Same cursor pattern.

### `GET /conversations/{id}`

Includes messages **without** streaming internals; citations expanded:

```json
{
  "id": 1,
  "title": "Attention questions",
  "messages": [
    { "id": 10, "role": "user", "content": "What is multi-head attention?", "citations": [] },
    {
      "id": 11,
      "role": "assistant",
      "content": "…",
      "citations": [
        {
          "markerIndex": 1,
          "chunkId": 44,
          "documentId": 1,
          "pageNumber": 4,
          "bbox": { "x": 72, "y": 400, "w": 450, "h": 80 },
          "snippet": "Multi-head attention allows…"
        }
      ]
    }
  ]
}
```

### `DELETE /conversations/{id}` → `204`

## Chat (streaming)

`POST /conversations/{id}/messages`

Request:

```json
{
  "content": "What does Figure 2 show?",
  "documentIds": [1],
  "topK": 8
}
```

`documentIds` optional for `ask`; required for `mode: "insight"`. `topK` is fused_k, clamped 1–20.

`mode` is `ask` (default) or `insight`. Insight retrieves from each listed document, then asks the model for a brief, themes, and where the files agree or differ. The stored user message is `Summarize this folder`.

Response: `text/event-stream`.

Events:

```
event: status
data: {"stage":"retrieving"}

event: citations
data: {"citations":[{"markerIndex":1,"chunkId":44,"documentId":1,"pageNumber":4,"bbox":{...},"snippet":"..."}]}

event: token
data: {"text":"Multi-head "}

event: token
data: {"text":"attention "}

event: done
data: {"messageId":11}

event: error
data: {"code":"dependency_unavailable","message":"Ollama is not running"}
```

Contract:

- `citations` is sent **before** tokens when possible (retrieval known). The model is instructed to use `[1]`, `[2]` matching `markerIndex`. Each citation includes `documentId` and `filename` so a folder-scoped chat can switch the PDF preview.
- If the model emits unknown markers, the UI ignores them.
- `done` always includes the persisted `messageId`.
- Client disconnect cancels the Ollama stream (FastAPI `Request.is_disconnected`).

## Settings (read)

`GET /settings`

```json
{
  "embedModel": "nomic-embed-text",
  "visionModel": "qwen2.5vl:7b",
  "generateModel": "qwen2.5:7b",
  "maxUploadBytes": 52428800,
  "embeddingDim": 768
}
```

Write is env-only in v1 (`PATCH` is out of scope). The web settings page is read-only plus a link to the development guide.

## Versioning

No `/v1` prefix until a breaking public API exists. This is a local app. Breaking changes are allowed before 1.0; document them in ADRs.
