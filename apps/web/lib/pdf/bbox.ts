export type PdfBBox = { x: number; y: number; w: number; h: number };

export function pdfToViewport(
  bbox: PdfBBox,
  pageHeightPt: number,
  scale: number,
) {
  return {
    x: bbox.x * scale,
    y: (pageHeightPt - bbox.y - bbox.h) * scale,
    w: bbox.w * scale,
    h: bbox.h * scale,
  };
}
