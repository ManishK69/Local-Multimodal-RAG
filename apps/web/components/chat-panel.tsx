"use client";

import { ArrowUp, NotebookText, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api";
import { createConversation, streamChatMessage } from "@/lib/api";
import { parseSse } from "@/lib/sse";
import { cn } from "@/lib/utils";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
};

function ThinkingDots() {
  return (
    <p className="text-muted-foreground flex items-center gap-2 text-sm" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        <span className="thinking-dot bg-primary size-1.5 rounded-full" />
        <span
          className="thinking-dot bg-primary size-1.5 rounded-full"
          style={{ animationDelay: "150ms" }}
        />
        <span
          className="thinking-dot bg-primary size-1.5 rounded-full"
          style={{ animationDelay: "300ms" }}
        />
      </span>
      Waiting for the local model
    </p>
  );
}

function shortName(filename: string) {
  const base = filename.replace(/\.pdf$/i, "");
  if (base.length <= 18) return base;
  return `${base.slice(0, 16)}…`;
}

function renderContent(
  content: string,
  citations: Citation[],
  onCite: (citation: Citation) => void,
  showFilenames: boolean,
) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, index) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return <span key={index}>{part}</span>;
    const marker = Number(match[1]);
    const citation =
      citations.find((item) => item.markerIndex === marker) ??
      citations[marker - 1];
    if (!citation) return <span key={index}>{part}</span>;
    const label = showFilenames
      ? `[${marker}] ${shortName(citation.filename ?? `PDF ${citation.documentId}`)}`
      : `[${marker}]`;
    return (
      <button
        key={index}
        type="button"
        className="bg-primary/15 text-primary mx-0.5 cursor-pointer rounded-md px-1 py-0.5 font-mono text-[0.7rem] font-medium outline-none transition-[transform,background-color] duration-150 ease-[var(--ease-out-strong)] hover-fine:hover:bg-primary/25 focus-visible:ring-2 focus-visible:ring-ring/50 active:scale-[0.97]"
        onClick={() => onCite(citation)}
      >
        {label}
      </button>
    );
  });
}

export function ChatPanel({
  documentIds,
  title = "Ask this PDF",
  subtitle = "Answers cite pages. Click a marker to highlight the source.",
  emptyHint = "Ask about a requirement, date, or definition. The model can only use text indexed from this file.",
  placeholder = "What does this document say about…?",
  autoFocus = true,
  fill = true,
  showInsight = false,
  onCitation,
}: {
  documentIds: number[];
  title?: string;
  subtitle?: string;
  emptyHint?: string;
  placeholder?: string;
  autoFocus?: boolean;
  fill?: boolean;
  showInsight?: boolean;
  onCitation?: (citation: Citation | null) => void;
}) {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const scopeKey = documentIds.join(",");
  const showFilenames = documentIds.length > 1;

  useEffect(() => {
    let cancelled = false;
    const ids = scopeKey
      .split(",")
      .filter(Boolean)
      .map((value) => Number(value));
    createConversation(
      ids.length > 1 ? `Folder ${ids.length} PDFs` : `Document ${ids[0] ?? "none"}`,
    )
      .then((conversation) => {
        if (!cancelled) setConversationId(conversation.id);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [scopeKey]);

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages]);

  const canSend = useMemo(
    () =>
      Boolean(conversationId) &&
      input.trim().length > 0 &&
      !busy &&
      documentIds.length > 0,
    [busy, conversationId, documentIds.length, input],
  );

  async function sendMessage(content: string, mode: "ask" | "insight" = "ask") {
    if (!conversationId || !content.trim() || documentIds.length === 0) return;
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
        documentIds,
        mode,
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

  async function send() {
    if (!input.trim()) return;
    await sendMessage(input.trim(), "ask");
  }

  async function insight() {
    await sendMessage("Summarize this folder", "insight");
  }

  async function reset() {
    setMessages([]);
    setError(null);
    setInput("");
    onCitation?.(null);
    try {
      const conversation = await createConversation(
        documentIds.length > 1
          ? `Folder ${documentIds.length} PDFs`
          : `Document ${documentIds[0] ?? "none"}`,
      );
      setConversationId(conversation.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start a new chat");
    }
    inputRef.current?.focus();
  }

  const threadOpen = messages.length > 0 || busy;

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col",
        fill ? "h-full" : threadOpen && "max-h-[min(36rem,70vh)]",
      )}
    >
      <div className="border-border/70 flex shrink-0 items-start justify-between gap-3 border-b px-4 py-3">
        <div>
          <p className="text-sm font-medium">{title}</p>
          <p className="text-muted-foreground text-xs">
            {threadOpen ? subtitle : emptyHint}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {showInsight ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy || documentIds.length === 0 || !conversationId}
              onClick={() => void insight()}
            >
              <NotebookText aria-hidden="true" />
              Insight
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy || messages.length === 0}
            onClick={() => void reset()}
          >
            <RotateCcw aria-hidden="true" />
            Reset
          </Button>
        </div>
      </div>
      {threadOpen ? (
        <div
          ref={scrollerRef}
          className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-4"
          aria-live="polite"
        >
          {messages.map((message, index) => (
            <div
              key={index}
              className={cn(
                "max-w-[92%] text-sm leading-relaxed",
                message.role === "user" ? "ml-auto" : "mr-auto",
              )}
            >
              <p className="text-muted-foreground mb-1 text-[10px] font-medium tracking-wide uppercase">
                {message.role === "user" ? "You" : "Assistant"}
              </p>
              <div
                className={cn(
                  "rounded-2xl px-3 py-2",
                  message.role === "user"
                    ? "bg-primary/12 text-foreground"
                    : "bg-muted/70 text-foreground",
                )}
              >
                {message.role === "assistant" && !message.content && busy ? (
                  <ThinkingDots />
                ) : (
                  <p className="whitespace-pre-wrap">
                    {renderContent(
                      message.content,
                      message.citations,
                      (citation) => onCitation?.(citation),
                      showFilenames,
                    )}
                    {message.role === "assistant" && busy && message.content ? (
                      <span className="bg-primary ml-0.5 inline-block h-3 w-1.5 animate-pulse align-baseline" />
                    ) : null}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {error ? (
        <p className="text-destructive shrink-0 px-4 pb-2 text-sm" role="alert">
          {error}
        </p>
      ) : null}
      <form
        className="border-border/70 shrink-0 border-t p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <label className="sr-only" htmlFor="pdf-question">
          {title}
        </label>
        <div className="flex items-end gap-2">
          <textarea
            id="pdf-question"
            ref={inputRef}
            autoFocus={autoFocus}
            disabled={documentIds.length === 0 || busy}
            rows={2}
            className="border-input bg-background min-h-16 flex-1 resize-none rounded-xl border px-3 py-2 text-sm outline-none transition-[border-color,box-shadow] duration-150 ease-[var(--ease-out-strong)] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={
              documentIds.length === 0
                ? "Wait until a PDF in this set is ready…"
                : placeholder
            }
            autoComplete="off"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
          />
          <Button
            type="submit"
            size="icon"
            disabled={!canSend}
            aria-label="Send question"
          >
            <ArrowUp />
          </Button>
        </div>
      </form>
    </div>
  );
}
