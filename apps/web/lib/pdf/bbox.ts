export type PdfBBox = { x: number; y: number; w: number; h: number };

/** Map PyMuPDF / pdf.js top-left point coords onto a rendered canvas. */
export function pdfToViewport(bbox: PdfBBox, scale: number, displayScale = 1) {
  const s = scale * displayScale;
  return {
    x: bbox.x * s,
    y: bbox.y * s,
    w: bbox.w * s,
    h: bbox.h * s,
  };
}
