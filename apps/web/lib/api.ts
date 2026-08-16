export const API_BASE = "http://127.0.0.1:8000";

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
  folderId: number | null;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
};

export type FolderRecord = {
  id: number;
  name: string;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
  documents?: DocumentRecord[];
};

export type Citation = {
  markerIndex: number;
  chunkId: number;
  documentId: number;
  pageNumber: number;
  bbox: { x: number; y: number; w: number; h: number } | null;
  snippet: string;
  filename?: string;
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

export async function listDocuments(opts?: {
  folderId?: number;
  unfiled?: boolean;
}) {
  const params = new URLSearchParams();
  if (opts?.folderId != null) params.set("folderId", String(opts.folderId));
  if (opts?.unfiled) params.set("unfiled", "true");
  const query = params.toString();
  return api<{ items: DocumentRecord[]; nextCursor: string | null }>(
    `/documents${query ? `?${query}` : ""}`,
  );
}

export async function getDocument(id: number) {
  return api<DocumentRecord>(`/documents/${id}`);
}

export async function uploadDocument(file: File, folderId?: number) {
  const body = new FormData();
  body.append("file", file);
  if (folderId != null) body.append("folderId", String(folderId));
  const res = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    body,
  });
  if (!res.ok) throw new Error("upload failed");
  return res.json() as Promise<DocumentRecord>;
}

export async function patchDocument(id: number, folderId: number | null) {
  return api<DocumentRecord>(`/documents/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folderId }),
  });
}

export async function deleteDocument(id: number) {
  return api<void>(`/documents/${id}`, { method: "DELETE" });
}

export async function listFolders() {
  return api<{ items: FolderRecord[] }>("/folders");
}

export async function getFolder(id: number) {
  return api<FolderRecord>(`/folders/${id}`);
}

export async function createFolder(name: string) {
  return api<FolderRecord>("/folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function renameFolder(id: number, name: string) {
  return api<FolderRecord>(`/folders/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function deleteFolder(id: number) {
  return api<void>(`/folders/${id}`, { method: "DELETE" });
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
  if (typeof window === "undefined") {
    return `${API_BASE}/documents/${id}/file`;
  }
  return `/backend/documents/${id}/file`;
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
  mode?: "ask" | "insight";
}) {
  const res = await fetch(
    `${API_BASE}/conversations/${args.conversationId}/messages`,
    {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        content: args.content,
        documentIds: args.documentIds,
        topK: args.topK ?? (args.mode === "insight" ? 16 : 8),
        mode: args.mode ?? "ask",
      }),
    },
  );
  if (!res.ok || !res.body) {
    throw new Error("chat stream failed");
  }
  return res.body;
}
