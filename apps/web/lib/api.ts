export const API_BASE =
  typeof window === "undefined" ? "http://127.0.0.1:8000" : "/backend";

export type Health = {
  status: string;
  postgres: string;
  redis: string;
  ollama: string;
  models: { embed: boolean; vision: boolean; generate: boolean };
};

export type DocumentRecord = {
  id: number;
  filename: string;
  contentSha256: string;
  byteSize: number;
  status: string;
  pageCount: number | null;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
};

export type Citation = {
  markerIndex: number;
  chunkId: number;
  documentId: number;
  pageNumber: number;
  bbox: { x: number; y: number; w: number; h: number } | null;
  snippet: string;
};

export type Conversation = {
  id: number;
  title: string;
  createdAt: string;
  messages?: Array<{
    id: number;
    role: "user" | "assistant";
    content: string;
    citations: Citation[];
  }>;
};

export type Settings = {
  embedModel: string;
  visionModel: string;
  generateModel: string;
  maxUploadBytes: number;
  embeddingDim: number;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`${path} failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function getHealth() {
  return api<Health>("/health");
}

export async function listDocuments() {
  return api<{ items: DocumentRecord[]; nextCursor: string | null }>(
    "/documents",
  );
}

export async function getDocument(id: number) {
  return api<DocumentRecord>(`/documents/${id}`);
}

export async function uploadDocument(file: File) {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    body,
  });
  if (!res.ok) throw new Error("upload failed");
  return res.json() as Promise<DocumentRecord>;
}

export async function createConversation(title?: string) {
  return api<Conversation>("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? "New conversation" }),
  });
}

export async function getConversation(id: number) {
  return api<Conversation>(`/conversations/${id}`);
}

export function documentFileUrl(id: number) {
  return `${API_BASE}/documents/${id}/file`;
}

export async function getDocumentPages(id: number) {
  return api<{
    pages: Array<{ pageNumber: number; widthPt: number; heightPt: number }>;
  }>(`/documents/${id}/pages`);
}

export async function getSettings() {
  return api<Settings>("/settings");
}

export async function streamChatMessage(args: {
  conversationId: number;
  content: string;
  documentIds?: number[];
  topK?: number;
}) {
  const res = await fetch(
    `${API_BASE}/conversations/${args.conversationId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: args.content,
        documentIds: args.documentIds,
        topK: args.topK ?? 8,
      }),
    },
  );
  if (!res.ok || !res.body) {
    throw new Error("chat stream failed");
  }
  return res.body;
}
