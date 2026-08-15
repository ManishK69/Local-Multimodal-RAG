"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import type { DocumentRecord } from "@/lib/api";
import { getDocument, listDocuments, uploadDocument } from "@/lib/api";

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

export function UploadDropzone() {
  const [items, setItems] = useState<DocumentRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);

  const refresh = useCallback(async () => {
    const payload = await listDocuments();
    setItems(payload.items);
  }, []);

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

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
    setError(null);
    for (const file of Array.from(files)) {
      if (file.type !== "application/pdf") {
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
        errorCode: null,
        errorMessage: null,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      setItems((current) => [optimistic, ...current]);
      try {
        const saved = await uploadDocument(file);
        setItems((current) =>
          current.map((item) => (item.id === optimistic.id ? saved : item)),
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
        setItems((current) => current.filter((item) => item.id !== optimistic.id));
      }
    }
  }

  return (
    <div className="space-y-4">
      <label
        className={`block cursor-pointer rounded-lg border-2 border-dashed p-8 text-center text-sm ${
          drag ? "border-primary bg-muted/50" : "border-border"
        }`}
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
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(event) => {
            if (event.target.files) void handleFiles(event.target.files);
          }}
        />
        Drop a PDF here or click to upload. Files stay on this machine.
      </label>
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      <ul className="space-y-2">
        {items.map((item) => (
          <li
            key={item.id}
            className="flex items-center justify-between rounded-lg border p-3 text-sm"
          >
            <div>
              {item.id > 0 && item.status === "ready" ? (
                <Link className="font-medium hover:underline" href={`/library/${item.id}`}>
                  {item.filename}
                </Link>
              ) : (
                <span className="font-medium">{item.filename}</span>
              )}
              <p className="text-muted-foreground">
                {STATUS_LABELS[item.status] ?? item.status}
                {item.status === "failed" && item.errorMessage
                  ? ` — ${item.errorMessage}`
                  : null}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
