import { expect, test } from "vitest";

import { pdfToViewport } from "./bbox";

test("keeps top-left origin used by PyMuPDF and pdf.js", () => {
  const r = pdfToViewport({ x: 10, y: 20, w: 100, h: 12 }, 1);
  expect(r).toEqual({ x: 10, y: 20, w: 100, h: 12 });
});

test("applies render scale and display scale", () => {
  const r = pdfToViewport({ x: 10, y: 20, w: 100, h: 12 }, 2, 0.5);
  expect(r).toEqual({ x: 10, y: 20, w: 100, h: 12 });
});
