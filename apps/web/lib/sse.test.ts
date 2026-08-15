import { expect, test } from "vitest";

import { parseSse } from "./sse";

function streamFrom(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

test("parseSse yields token events", async () => {
  const stream = streamFrom(
    'event: token\ndata: {"text":"Hello "}\n\nevent: token\ndata: {"text":"world"}\n\n',
  );
  const events = [];
  for await (const event of parseSse(stream)) {
    events.push(event);
  }
  expect(events).toEqual([
    { event: "token", data: { text: "Hello " } },
    { event: "token", data: { text: "world" } },
  ]);
});
