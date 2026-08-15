"use client";

import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";

import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api";
import { documentFileUrl } from "@/lib/api";
import { pdfToViewport } from "@/lib/pdf/bbox";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

type PageDim = { pageNumber: number; widthPt: number; heightPt: number };

export function PdfPreview({
  documentId,
  pages,
  activeCitation,
}: {
  documentId: number;
  pages: PageDim[];
  activeCitation: Citation | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [flash, setFlash] = useState(false);
  const scale = 1.25;

  useEffect(() => {
    if (activeCitation) {
      setPageNumber(activeCitation.pageNumber);
      if (!activeCitation.bbox) {
        setFlash(true);
        const timer = window.setTimeout(() => setFlash(false), 800);
        return () => window.clearTimeout(timer);
      }
    }
  }, [activeCitation]);

  useEffect(() => {
    let cancelled = false;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const url = documentFileUrl(documentId);
    pdfjs.getDocument({ url }).promise.then(async (pdf) => {
      const page = await pdf.getPage(pageNumber);
      if (cancelled) return;
      const viewport = page.getViewport({ scale });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const context = canvas.getContext("2d");
      if (!context) return;
      await page.render({ canvasContext: context, viewport, canvas }).promise;
    });
    return () => {
      cancelled = true;
    };
  }, [documentId, pageNumber]);

  const pageMeta = pages.find((page) => page.pageNumber === pageNumber);
  const overlay =
    activeCitation?.bbox && pageMeta && activeCitation.pageNumber === pageNumber
      ? pdfToViewport(activeCitation.bbox, pageMeta.heightPt, scale)
      : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-sm">
        <Button
          size="sm"
          variant="outline"
          disabled={pageNumber <= 1}
          onClick={() => setPageNumber((n) => Math.max(1, n - 1))}
        >
          Prev
        </Button>
        <span>
          Page {pageNumber} / {pages.length || "?"}
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={pages.length > 0 && pageNumber >= pages.length}
          onClick={() => setPageNumber((n) => n + 1)}
        >
          Next
        </Button>
      </div>
      <div
        className={`relative overflow-auto rounded-lg border ${flash ? "ring-2 ring-amber-400" : ""}`}
      >
        <canvas ref={canvasRef} className="block max-w-full" />
        {overlay ? (
          <div
            className="pointer-events-none absolute border-2 border-amber-400 bg-amber-300/20"
            style={{
              left: overlay.x,
              top: overlay.y,
              width: overlay.w,
              height: overlay.h,
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
