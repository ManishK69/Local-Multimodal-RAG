"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api";
import { createConversation, streamChatMessage } from "@/lib/api";
import { parseSse } from "@/lib/sse";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
};

function renderContent(
  content: string,
  citations: Citation[],
  onCite: (citation: Citation) => void,
) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, index) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return <span key={index}>{part}</span>;
    const marker = Number(match[1]);
    const citation = citations.find((item) => item.markerIndex === marker);
    if (!citation) return <span key={index}>{part}</span>;
    return (
      <button
        key={index}
        type="button"
        className="text-primary mx-0.5 rounded-sm px-1 font-medium underline-offset-2 hover:underline"
        onClick={() => onCite(citation)}
      >
        [{marker}]
      </button>
    );
  });
}

export function ChatPanel({
  documentId,
  onCitation,
}: {
  documentId: number;
  onCitation?: (citation: Citation) => void;
}) {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    createConversation(`Document ${documentId}`)
      .then((conversation) => {
        if (!cancelled) setConversationId(conversation.id);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const canSend = useMemo(
    () => Boolean(conversationId) && input.trim().length > 0 && !busy,
    [busy, conversationId, input],
  );

  async function send() {
    if (!conversationId || !input.trim()) return;
    const content = input.trim();
    setInput("");
    setBusy(true);
    setError(null);
    setMessages((current) => [
      ...current,
      { role: "user", content, citations: [] },
      { role: "assistant", content: "", citations: [] },
    ]);
    try {
      const stream = await streamChatMessage({
        conversationId,
        content,
        documentIds: [documentId],
      });
      let citations: Citation[] = [];
      for await (const event of parseSse(stream)) {
        if (event.event === "citations") {
          const payload = event.data as { citations?: Citation[] };
          citations = payload.citations ?? [];
          setMessages((current) => {
            const next = [...current];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = { ...last, citations };
            }
            return next;
          });
        } else if (event.event === "token") {
          const payload = event.data as { text?: string };
          const text = payload.text ?? "";
          setMessages((current) => {
            const next = [...current];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = {
                ...last,
                content: last.content + text,
              };
            }
            return next;
          });
        } else if (event.event === "error") {
          const payload = event.data as { message?: string };
          setError(payload.message ?? "Stream error");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-[24rem] flex-col gap-3">
      <div className="flex-1 space-y-3 overflow-auto rounded-lg border p-3 text-sm">
        {messages.length === 0 ? (
          <p className="text-muted-foreground">Ask a question about this PDF.</p>
        ) : null}
        {messages.map((message, index) => (
          <div key={index}>
            <p className="text-muted-foreground mb-1 text-xs uppercase">
              {message.role}
            </p>
            <p className="whitespace-pre-wrap">
              {renderContent(message.content, message.citations, (citation) =>
                onCitation?.(citation),
              )}
            </p>
          </div>
        ))}
      </div>
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      <div className="flex gap-2">
        <textarea
          className="border-input min-h-20 flex-1 rounded-lg border bg-transparent p-2 text-sm"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about this PDF…"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <Button disabled={!canSend} onClick={() => void send()}>
          Send
        </Button>
      </div>
    </div>
  );
}
