"use client";

import { FolderPlus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import type { FolderRecord } from "@/lib/api";
import { createFolder, listFolders } from "@/lib/api";

export function LibraryFolders() {
  const [folders, setFolders] = useState<FolderRecord[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const payload = await listFolders();
    setFolders(payload.items);
  }, []);

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  async function onCreate() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await createFolder(trimmed);
      setName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create folder");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">Folders</h2>
          <p className="text-muted-foreground mt-0.5 text-xs">
            Group related PDFs, then ask across the whole folder or one file.
          </p>
        </div>
        <form
          className="flex min-w-0 items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void onCreate();
          }}
        >
          <label className="sr-only" htmlFor="new-folder-name">
            New folder name
          </label>
          <input
            id="new-folder-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="New folder"
            className="border-input bg-background h-8 w-44 rounded-lg border px-2.5 text-sm outline-none transition-[border-color,box-shadow] duration-150 ease-[var(--ease-out-strong)] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40"
          />
          <Button type="submit" size="sm" disabled={busy || name.trim().length === 0}>
            <FolderPlus aria-hidden="true" />
            Create
          </Button>
        </form>
      </div>
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
      {folders.length === 0 ? (
        <p className="text-muted-foreground rounded-xl border border-dashed px-4 py-6 text-center text-sm">
          No folders yet. Create one to query several related PDFs together.
        </p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {folders.map((folder, index) => (
            <li key={folder.id}>
              <Link
                href={`/library/folders/${folder.id}`}
                className="enter-up bg-card hover-fine:hover:ring-primary/30 block rounded-xl px-4 py-3 ring-1 ring-foreground/8 outline-none transition-[transform,box-shadow] duration-150 ease-[var(--ease-out-strong)] hover-fine:hover:-translate-y-px focus-visible:ring-3 focus-visible:ring-ring/50"
                style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
              >
                <p className="truncate text-sm font-medium">{folder.name}</p>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {folder.documentCount === 1
                    ? "1 PDF"
                    : `${folder.documentCount} PDFs`}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
