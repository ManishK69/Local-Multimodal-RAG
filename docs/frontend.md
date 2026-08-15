# Frontend

## Stack

- Next.js 15 App Router, React 19, TypeScript
- Tailwind CSS v4 if stable in the chosen Next template, otherwise v3 — pick one in the first frontend task and stick to it
- shadcn/ui (Radix) for buttons, dialogs, scroll areas, toasts, badges
- pdf.js (`react-pdf` or pdfjs-dist directly) for rendering
- `fetch` + `ReadableStream` for SSE (no extra client library)

## Routes

| Path | Purpose |
| --- | --- |
| `/` | Redirect to `/library` |
| `/library` | Document list + upload dropzone |
| `/library/[id]` | Split view: PDF preview (left) + chat (right) |
| `/chats` | Conversation list |
| `/chats/[id]` | Same split view bound to a conversation; PDF follows active citation |
| `/settings` | Read-only model/health status |

Default reading experience is `/library/[id]`, which creates or reuses a conversation scoped to that document.

## Layout (reader)

```
┌──────────────────────────────────────────────────────────┐
│  filename.pdf          Ready     Health: ok              │
├─────────────────────────────┬────────────────────────────┤
│  PDF toolbar  page 4 / 15   │  Conversation              │
│  ┌───────────────────────┐  │  User: What is Fig 2?      │
│  │  page canvas          │  │  Assistant: … [1] [2]      │
│  │  highlight overlay    │  │                            │
│  └───────────────────────┘  │  [Ask about this PDF…]     │
└─────────────────────────────┴────────────────────────────┘
```

Desktop-first. Below `md`, stack PDF above chat. No native mobile app.

## Upload UX

- Drag-and-drop + file picker, PDF only
- Optimistic row: filename, spinner, status from polling `GET /documents/{id}` every 1.5s until `ready` or `failed`
- Status labels match the state machine: Queued, Parsing, Captioning figures, Chunking, Embedding, Ready, Failed
- Failed: show `errorMessage` + Retry (POST same file again — server re-enqueues)

## Streaming

Custom hook `useChatStream`:

1. POST messages endpoint
2. Read SSE, append `token` text to a local assistant draft
3. On `citations`, store overlay targets
4. On `done`, reconcile with `GET /conversations/{id}`
5. On `error`, toast and keep the user message

Do not use React Server Actions for the stream; this is a browser-to-API event stream.

## Citation highlighting

1. Assistant markdown renders `[n]` as buttons.
2. Click `[n]` or auto-focus the first citation when the stream ends:
   - set `activePage = citation.pageNumber`
   - pdf.js renders that page
   - overlay a rectangle from `bbox` converted to viewport:

```
viewportX = bbox.x * viewport.scale
viewportY = (pageHeightPt - bbox.y - bbox.h) * viewport.scale
viewportW = bbox.w * viewport.scale
viewportH = bbox.h * viewport.scale
```

Y-flip assumes PDF origin bottom-left. Verify against one fixture page in a unit test (`lib/pdf/bbox.ts`). If a citation has `bbox: null`, flash the whole page (amber border) instead of a box.

3. Snippet is shown in a hover card so the user sees the retrieved text, not only the highlight.

## State

- Server state: TanStack Query for documents, conversations, health
- Client: Zustand or React context for `activeCitation` and draft stream — keep it small. Prefer TanStack Query + local component state before adding Zustand. Add Zustand only if three or more distant trees need the same client session.

## Accessibility

- Keyboard: citation buttons are in tab order; `n` / `p` change PDF pages when the preview is focused
- Contrast: highlight overlay uses a semi-transparent accent fill plus a 2px stroke, not color-only meaning
- `prefers-reduced-motion`: no page-flip animation

## Visual direction

Quiet, dense, technical workbench — not a marketing landing page. Neutral surfaces, one accent for citations and primary actions. shadcn defaults are acceptable as a base; do not add decorative gradients or hero sections. The product *is* the reader.

## Out of scope for v1 UI

- Theme marketplace, collaborative cursors, comment threads
- In-browser PDF editing
- Chat sharing links
