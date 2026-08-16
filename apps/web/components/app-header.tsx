"use client";

import { BookOpen } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { HealthStatus } from "@/components/health-status";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/library", label: "Library" },
  { href: "/settings", label: "Settings" },
];

export function AppHeader() {
  const pathname = usePathname();

  return (
    <header className="border-border/70 bg-background/80 sticky top-0 z-20 border-b backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link
          href="/library"
          className="flex min-w-0 items-center gap-2.5 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <span className="bg-primary/15 text-primary flex size-8 items-center justify-center rounded-lg">
            <BookOpen className="size-4" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <span className="font-heading block truncate text-[1.05rem] leading-none italic tracking-tight">
              Local RAG
            </span>
            <span className="text-muted-foreground mt-0.5 block text-[11px] tracking-wide">
              Stays on this machine
            </span>
          </span>
        </Link>
        <nav aria-label="Primary" className="flex items-center gap-1">
          {NAV.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm outline-none transition-[color,background-color] duration-150 ease-[var(--ease-out-strong)] focus-visible:ring-3 focus-visible:ring-ring/50",
                  active
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover-fine:hover:bg-muted hover-fine:hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
          <HealthStatus />
        </nav>
      </div>
    </header>
  );
}
