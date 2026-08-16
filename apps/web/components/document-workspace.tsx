"use client";

import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { PdfPreview } from "@/components/pdf-preview";
import type { Citation } from "@/lib/api";
import { getDocumentPages } from "@/lib/api";
import { takePendingCitation } from "@/lib/citation";

export function DocumentWorkspace({
  documentId,
  filename,
}: {
  documentId: number;
  filename: string;
}) {
  const [pages, setPages] = useState<
    Array<{ pageNumber: number; widthPt: number; heightPt: number }>
  >([]);
  const [citation, setCitation] = useState<Citation | null>(null);

  useEffect(() => {
    getDocumentPages(documentId)
      .then((payload) => setPages(payload.pages))
      .catch(() => setPages([]));
  }, [documentId]);

  useEffect(() => {
    const pending = takePendingCitation(documentId);
    if (pending) setCitation(pending);
  }, [documentId]);

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]">
      <section className="bg-card/40 flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl p-3 ring-1 ring-foreground/8">
        <PdfPreview
          documentId={documentId}
          pages={pages}
          activeCitation={citation}
          filename={filename}
        />
      </section>
      <section className="relative z-10 flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl bg-card ring-1 ring-foreground/8">
        <ChatPanel
          documentIds={[documentId]}
          onCitation={setCitation}
        />
      </section>
    </div>
  );
}
