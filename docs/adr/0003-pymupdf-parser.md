# ADR 0003: PyMuPDF as the v1 parser

## Status

Accepted

## Context

Citation highlighting needs page numbers and bounding boxes. Unstructured is strong at mixed office formats but is heavier and less predictable for PDF geometry.

## Decision

**PyMuPDF (`fitz`) is the only parser in v1.** It extracts text dicts, tables (or table-like blocks), and image bytes with bboxes.

Unstructured is deferred to a later ADR when DOCX/PPTX matter.

## Consequences

- Fast, local, no extra service
- Good provenance for pdf.js overlays
- Scanned PDFs without a text layer will yield empty text; OCR is deferred (optional later: Tesseract stage)
- Table quality will be imperfect; we store tables as markdown when extraction works, otherwise as image + caption

## Alternatives

- **Unstructured-only:** broader formats, weaker bbox control
- **PDF + vision-only (page screenshots):** expensive, loses selectable text
