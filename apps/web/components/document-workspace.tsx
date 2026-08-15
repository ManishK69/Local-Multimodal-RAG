"use client";

import { useEffect, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { PdfPreview } from "@/components/pdf-preview";
import type { Citation } from "@/lib/api";
import { getDocumentPages } from "@/lib/api";

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

  return (
    <div className="grid min-h-[70vh] gap-6 md:grid-cols-2">
      <section>
        <h2 className="mb-3 text-sm font-medium">{filename}</h2>
        <PdfPreview
          documentId={documentId}
          pages={pages}
          activeCitation={citation}
        />
      </section>
      <section>
        <ChatPanel documentId={documentId} onCitation={setCitation} />
      </section>
    </div>
  );
}
