"use client";

import { FileText, LoaderCircle, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DocumentRecord, FolderRecord } from "@/lib/api";
import {
  deleteDocument,
  getDocument,
  listDocuments,
  listFolders,
  patchDocument,
  uploadDocument,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  parsing: "Parsing",
  captioning: "Captioning figures",
  chunking: "Chunking",
  embedding: "Embedding",
  ready: "Ready",
  failed: "Failed",
};

function isTerminal(status: string) {
  return status === "ready" || status === "failed";
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "ready") return "outline";
  if (status === "failed") return "destructive";
  return "secondary";
}

export function UploadDropzone({
  folderId,
  unfiled = false,
  heading = "Documents",
  emptyLabel = "No items yet. Upload a PDF to create one.",
  hrefFor,
  actions,
  onMutate,
}: {
  folderId?: number;
  unfiled?: boolean;
  heading?: string;
  emptyLabel?: string;
  hrefFor?: (doc: DocumentRecord) => string | null;
  actions?: (doc: DocumentRecord, refresh: () => Promise<void>) => ReactNode;
  onMutate?: () => void;
}) {
  const [items, setItems] = useState<DocumentRecord[]>([]);
  const [folders, setFolders] = useState<FolderRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const payload = await listDocuments({
      folderId,
      unfiled: unfiled && folderId == null,
    });
    setItems(payload.items);
    if (unfiled && folderId == null) {
      const listed = await listFolders();
      setFolders(listed.items ?? []);
    }
  }, [folderId, unfiled]);

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  useEffect(() => {
    if (!(unfiled && folderId == null)) return;
    listFolders()
      .then((payload) => setFolders(payload.items ?? []))
      .catch((err: Error) => setError(err.message));
  }, [folderId, unfiled]);

  useEffect(() => {
    const pending = items.filter((item) => !isTerminal(item.status));
    if (pending.length === 0) return;
    const timer = window.setInterval(async () => {
      const updates = await Promise.all(
        pending.map(async (item) => {
          try {
            return await getDocument(item.id);
          } catch {
            return item;
          }
        }),
      );
      setItems((current) =>
        current.map((item) => updates.find((row) => row.id === item.id) ?? item),
      );
    }, 1500);
    return () => window.clearInterval(timer);
  }, [items]);

  async function handleFiles(files: FileList | File[]) {
    const picked = Array.from(files);
    if (fileRef.current) fileRef.current.value = "";
    setError(null);
    for (const file of picked) {
      const isPdf =
        file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
      if (!isPdf) {
        setError("Only PDF files are accepted.");
        continue;
      }
      const optimistic: DocumentRecord = {
        id: -Date.now(),
        filename: file.name,
        contentSha256: "",
        byteSize: file.size,
        status: "queued",
        pageCount: null,
        folderId: folderId ?? null,
        errorCode: null,
        errorMessage: null,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      setItems((current) => [optimistic, ...current]);
      try {
        const saved = await uploadDocument(file, folderId);
        setItems((current) =>
          current.map((item) => (item.id === optimistic.id ? saved : item)),
        );
        onMutate?.();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
        setItems((current) => current.filter((item) => item.id !== optimistic.id));
      }
    }
  }

  async function removeDocument(documentId: number) {
    try {
      await deleteDocument(documentId);
      setConfirmId(null);
      setItems((current) => current.filter((item) => item.id !== documentId));
      onMutate?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete PDF");
    }
  }

  return (
    <div className="space-y-6">
      <div
        className={cn(
          "border-border bg-card/60 relative flex flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-12 text-center transition-[border-color,background-color,transform] duration-200 ease-[var(--ease-out-strong)]",
          drag ? "border-primary bg-primary/8 scale-[0.99]" : "hover-fine:hover:border-primary/50",
        )}
        onDragOver={(event) => {
          event.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDrag(false);
          if (event.dataTransfer.files) void handleFiles(event.dataTransfer.files);
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          className="absolute inset-0 z-10 cursor-pointer opacity-0"
          aria-label="Upload a PDF"
          onChange={(event) => {
            if (event.target.files) void handleFiles(event.target.files);
          }}
        />
        <span className="pointer-events-none bg-primary/12 text-primary mb-4 flex size-12 items-center justify-center rounded-xl">
          <Upload className="size-5" aria-hidden="true" />
        </span>
        <span className="pointer-events-none text-sm font-medium">
          Drop a PDF, or click to browse
        </span>
        <span className="pointer-events-none text-muted-foreground mt-1 max-w-sm text-sm">
          Files stay in this machine’s data folder. Ready documents open in the reading desk.
        </span>
      </div>
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
      <section aria-labelledby="library-list-heading">
        <div className="mb-3 flex items-end justify-between gap-3">
          <h2 id="library-list-heading" className="text-sm font-medium">
            {heading}
          </h2>
          <p className="text-muted-foreground text-xs">
            {items.length === 0 ? "None yet" : `${items.length} on this shelf`}
          </p>
        </div>
        {items.length === 0 ? (
          <p className="text-muted-foreground rounded-xl border border-dashed px-4 py-8 text-center text-sm">
            {emptyLabel}
          </p>
        ) : (
          <ul className="space-y-2">
            {items.map((item, index) => {
              const ready = item.id > 0 && item.status === "ready";
              const pending = !isTerminal(item.status);
              const href = hrefFor
                ? hrefFor(item)
                : ready
                  ? `/library/${item.id}`
                  : null;
              const body = (
                <>
                  <span className="bg-muted text-muted-foreground flex size-10 shrink-0 items-center justify-center rounded-lg">
                    {pending ? (
                      <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                    ) : (
                      <FileText className="size-4" aria-hidden="true" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{item.filename}</p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {item.byteSize ? formatBytes(item.byteSize) : "—"}
                      {item.pageCount ? ` · ${item.pageCount} pages` : null}
                      {item.status === "failed" && item.errorMessage
                        ? ` · ${item.errorMessage}`
                        : null}
                    </p>
                  </div>
                </>
              );
              return (
                <li key={item.id}>
                  <div
                    className={cn(
                      "enter-up bg-card flex items-center gap-3 rounded-xl px-3 py-3 ring-1 ring-foreground/8",
                      href &&
                        "hover-fine:hover:ring-primary/30 transition-[transform,box-shadow] duration-150 ease-[var(--ease-out-strong)] hover-fine:hover:-translate-y-px",
                    )}
                    style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
                  >
                    {href ? (
                      <Link
                        href={href}
                        className="flex min-w-0 flex-1 items-center gap-3 rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        {body}
                      </Link>
                    ) : (
                      <div className="flex min-w-0 flex-1 items-center gap-3">{body}</div>
                    )}
                    <Badge variant={statusVariant(item.status)}>
                      {STATUS_LABELS[item.status] ?? item.status}
                    </Badge>
                    {item.id > 0 && unfiled && folders.length > 0 ? (
                      <label className="relative z-20 flex shrink-0 items-center">
                        <span className="sr-only">Move {item.filename} to folder</span>
                        <select
                          className="border-input bg-background text-foreground h-7 max-w-36 rounded-md border px-1.5 text-xs outline-none"
                          defaultValue=""
                          onChange={(event) => {
                            const next = Number(event.target.value);
                            if (!next) return;
                            void patchDocument(item.id, next)
                              .then(() => refresh())
                              .catch((err: Error) => setError(err.message));
                          }}
                        >
                          <option value="">Move to…</option>
                          {folders.map((folder) => (
                            <option key={folder.id} value={folder.id}>
                              {folder.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    {item.id > 0 && actions ? actions(item, refresh) : null}
                    {item.id > 0 ? (
                      confirmId === item.id ? (
                        <span className="relative z-20 flex shrink-0 items-center gap-1">
                          <Button
                            type="button"
                            size="xs"
                            variant="destructive"
                            onClick={() => void removeDocument(item.id)}
                          >
                            Delete
                          </Button>
                          <Button
                            type="button"
                            size="xs"
                            variant="ghost"
                            onClick={() => setConfirmId(null)}
                          >
                            Cancel
                          </Button>
                        </span>
                      ) : (
                        <Button
                          type="button"
                          size="icon-xs"
                          variant="ghost"
                          className="relative z-20"
                          aria-label={`Delete ${item.filename}`}
                          onClick={() => setConfirmId(item.id)}
                        >
                          <Trash2 />
                        </Button>
                      )
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
