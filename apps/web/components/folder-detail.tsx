"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { PdfPreview } from "@/components/pdf-preview";
import { Button } from "@/components/ui/button";
import { UploadDropzone } from "@/components/upload-dropzone";
import type { Citation, FolderRecord } from "@/lib/api";
import { deleteFolder, getDocumentPages, getFolder, patchDocument, renameFolder } from "@/lib/api";

export function FolderDetail({ folderId }: { folderId: number }) {
  const router = useRouter();
  const [folder, setFolder] = useState<FolderRecord | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [pages, setPages] = useState<
    Array<{ pageNumber: number; widthPt: number; heightPt: number }>
  >([]);

  const refresh = useCallback(async () => {
    const payload = await getFolder(folderId);
    setFolder(payload);
    setName(payload.name);
  }, [folderId]);

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  useEffect(() => {
    if (!folder) return;
    const pending = (folder.documents ?? []).some(
      (doc) => doc.status !== "ready" && doc.status !== "failed",
    );
    if (!pending) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [folder, refresh]);

  const previewDoc = (folder?.documents ?? []).find(
    (doc) => doc.id === citation?.documentId,
  );

  useEffect(() => {
    if (!citation) {
      setPages([]);
      return;
    }
    getDocumentPages(citation.documentId)
      .then((payload) => setPages(payload.pages))
      .catch(() => setPages([]));
  }, [citation]);

  const readyIds = useMemo(
    () =>
      (folder?.documents ?? [])
        .filter((doc) => doc.status === "ready" && Boolean(doc.pageCount))
        .map((doc) => doc.id),
    [folder],
  );

  useEffect(() => {
    if (!citation) return;
    const stillHere = (folder?.documents ?? []).some(
      (doc) => doc.id === citation.documentId,
    );
    if (!stillHere) setCitation(null);
  }, [citation, folder]);

  async function onRename() {
    const trimmed = name.trim();
    if (!folder || !trimmed || trimmed === folder.name) return;
    try {
      const updated = await renameFolder(folder.id, trimmed);
      setFolder({ ...folder, ...updated });
      setName(updated.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename");
    }
  }

  async function onDelete() {
    if (!folder) return;
    try {
      await deleteFolder(folder.id);
      router.push("/library");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete folder");
    }
  }

  if (!folder) {
    return (
      <p className="text-muted-foreground text-sm">
        {error ?? "Loading folder…"}
      </p>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <Link
            href="/library"
            className="text-muted-foreground hover-fine:hover:text-foreground mb-3 inline-flex items-center gap-1.5 text-xs outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            Library
          </Link>
          <label className="sr-only" htmlFor="folder-name">
            Folder name
          </label>
          <input
            id="folder-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => void onRename()}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.currentTarget.blur();
              }
            }}
            className="font-heading text-foreground w-full bg-transparent text-3xl tracking-tight italic outline-none sm:text-4xl"
          />
          <p className="text-muted-foreground mt-2 text-sm">
            Ask in the bar below to search every ready PDF. Open a file to read it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {confirmDelete ? (
            <>
              <Button variant="destructive" size="sm" onClick={() => void onDelete()}>
                Files return to library
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>
              Delete folder
            </Button>
          )}
        </div>
      </div>
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
      <UploadDropzone
        folderId={folder.id}
        heading="In this folder"
        emptyLabel="Drop PDFs here to keep them with this set."
        onMutate={() => void refresh()}
        actions={(doc, reload) => (
          <Button
            type="button"
            size="xs"
            variant="ghost"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              void patchDocument(doc.id, null)
                .then(() => reload())
                .then(() => refresh())
                .catch((err: Error) => setError(err.message));
            }}
          >
            Unfile
          </Button>
        )}
      />
      {citation ? (
        <section className="flex h-[22rem] flex-col overflow-hidden rounded-2xl bg-card p-3 ring-1 ring-foreground/8">
          <PdfPreview
            documentId={citation.documentId}
            pages={pages}
            activeCitation={citation}
            filename={previewDoc?.filename ?? citation.filename}
          />
        </section>
      ) : null}
      <section className="flex flex-col overflow-hidden rounded-2xl bg-card ring-1 ring-foreground/8">
        <ChatPanel
          documentIds={readyIds}
          fill={false}
          title="Ask this folder"
          subtitle="Click a citation to open that PDF above this chat."
          emptyHint="Ask every ready PDF, or click Insight for a brief across the set."
          placeholder="Ask across the PDFs in this folder…"
          autoFocus={false}
          onCitation={setCitation}
          showInsight
        />
      </section>
    </div>
  );
}
