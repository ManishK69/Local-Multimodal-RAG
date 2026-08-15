import { expect, test } from "vitest";

import { pdfToViewport } from "./bbox";

test("flips y from PDF origin", () => {
  const r = pdfToViewport({ x: 0, y: 0, w: 100, h: 10 }, 792, 1);
  expect(r.y).toBe(782);
  expect(r.h).toBe(10);
});
