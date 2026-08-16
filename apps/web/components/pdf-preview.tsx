"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";

import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api";
import { documentFileUrl } from "@/lib/api";
import { pdfToViewport } from "@/lib/pdf/bbox";
import { cn } from "@/lib/utils";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

type PageDim = { pageNumber: number; widthPt: number; heightPt: number };

export function PdfPreview({
  documentId,
  pages,
  activeCitation,
  filename,
  className,
}: {
  documentId: number;
  pages: PageDim[];
  activeCitation: Citation | null;
  filename?: string;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pdfPageCount, setPdfPageCount] = useState(0);
  const [flash, setFlash] = useState(false);
  const [displayScale, setDisplayScale] = useState(1);
  const scale = 1.25;
  const totalPages = pages.length || pdfPageCount;

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
    pdfjs
      .getDocument({ url })
      .promise.then(async (pdf) => {
        if (cancelled) return;
        setPdfPageCount(pdf.numPages);
        const page = await pdf.getPage(pageNumber);
        if (cancelled) return;
        const viewport = page.getViewport({ scale });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const context = canvas.getContext("2d");
        if (!context) return;
        await page.render({ canvasContext: context, viewport, canvas }).promise;
        if (!cancelled && canvas.width) {
          setDisplayScale(canvas.clientWidth / canvas.width);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [documentId, pageNumber]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const sync = () => {
      if (canvas.width) setDisplayScale(canvas.clientWidth / canvas.width);
    };
    const observer = new ResizeObserver(sync);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [documentId, pageNumber]);

  useEffect(() => {
    overlayRef.current?.scrollIntoView({ block: "center", inline: "nearest" });
  }, [activeCitation, displayScale]);

  const overlay =
    activeCitation?.bbox && activeCitation.pageNumber === pageNumber
      ? pdfToViewport(activeCitation.bbox, scale, displayScale)
      : null;

  return (
    <div className={cn("flex h-full min-h-0 flex-col gap-3", className)}>
      <div className="flex shrink-0 items-center justify-between gap-3">
        <p className="text-muted-foreground min-w-0 truncate text-xs">
          {filename ?? "PDF"}
        </p>
        <div className="flex items-center gap-1">
          <Button
            size="icon-sm"
            variant="ghost"
            disabled={pageNumber <= 1}
            aria-label="Previous page"
            onClick={() => setPageNumber((n) => Math.max(1, n - 1))}
          >
            <ChevronLeft />
          </Button>
          <span className="text-muted-foreground min-w-16 text-center font-mono text-xs">
            {pageNumber} / {totalPages || "—"}
          </span>
          <Button
            size="icon-sm"
            variant="ghost"
            disabled={totalPages > 0 && pageNumber >= totalPages}
            aria-label="Next page"
            onClick={() => setPageNumber((n) => n + 1)}
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
      <div
        className={cn(
          "relative min-h-0 flex-1 overflow-auto rounded-xl bg-[var(--paper)] shadow-[inset_0_0_0_1px_oklch(0.2_0.02_72_/_0.08)]",
          flash && "ring-2 ring-[var(--brass)]",
        )}
      >
        <div className="relative mx-auto w-max max-w-full">
          <canvas ref={canvasRef} className="block h-auto max-w-full" />
          {overlay ? (
            <div
              ref={overlayRef}
              className="pointer-events-none absolute border-2 border-[var(--brass)] bg-[var(--brass)]/20"
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
    </div>
  );
}
