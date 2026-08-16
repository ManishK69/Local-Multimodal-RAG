"use client";

import { useEffect, useState } from "react";

import { getHealth, type Health } from "@/lib/api";
import { cn } from "@/lib/utils";

export function HealthStatus() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      getHealth()
        .then((payload) => {
          if (!cancelled) setHealth(payload);
        })
        .catch(() => {
          if (!cancelled) setHealth(null);
        });
    };
    load();
    const timer = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const ok = health?.status === "ok";
  const label = health?.status ?? "offline";

  return (
    <p
      className="text-muted-foreground ml-2 hidden items-center gap-2 text-xs sm:flex"
      title={
        health
          ? `postgres ${health.postgres} · redis ${health.redis} · ollama ${health.ollama}`
          : "API unreachable"
      }
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          ok ? "bg-emerald-400" : "bg-destructive",
        )}
        aria-hidden="true"
      />
      <span className="sr-only">API health</span>
      {label}
    </p>
  );
}
