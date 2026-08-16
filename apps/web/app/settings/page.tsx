import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getHealth, getSettings } from "@/lib/api";

export default async function SettingsPage() {
  let health: Awaited<ReturnType<typeof getHealth>> | null = null;
  let settings: Awaited<ReturnType<typeof getSettings>> | null = null;
  try {
    [health, settings] = await Promise.all([getHealth(), getSettings()]);
  } catch {
    health = null;
    settings = null;
  }

  const rows = [
    ["Embed", settings?.embedModel ?? "—"],
    ["Vision", settings?.visionModel ?? "—"],
    ["Generate", settings?.generateModel ?? "—"],
    ["Embedding dim", String(settings?.embeddingDim ?? "—")],
    [
      "Max upload",
      settings?.maxUploadBytes
        ? `${Math.round(settings.maxUploadBytes / (1024 * 1024))} MB`
        : "—",
    ],
  ];

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6">
      <div className="enter-up">
        <p className="text-primary mb-2 text-xs font-medium tracking-[0.18em] uppercase">
          Settings
        </p>
        <h1 className="font-heading text-3xl tracking-tight italic">Machine</h1>
        <p className="text-muted-foreground mt-2 max-w-md text-sm leading-relaxed">
          Read-only. Change models in <code className="font-mono text-foreground/80">.env</code>{" "}
          and restart the API.
        </p>
      </div>
      <Card className="enter-up" style={{ animationDelay: "40ms" }}>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-3 text-base">
            Health
            <Badge variant={health?.status === "ok" ? "outline" : "destructive"}>
              {health?.status ?? "unreachable"}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground grid gap-3 py-4 text-sm sm:grid-cols-3">
          <HealthCell label="Postgres" value={health?.postgres} />
          <HealthCell label="Redis" value={health?.redis} />
          <HealthCell label="Ollama" value={health?.ollama} />
        </CardContent>
      </Card>
      <Card className="enter-up" style={{ animationDelay: "80ms" }}>
        <CardHeader className="border-b">
          <CardTitle className="text-base">Models</CardTitle>
        </CardHeader>
        <CardContent className="divide-border divide-y">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className="flex items-baseline justify-between gap-4 py-3 text-sm"
            >
              <span className="text-muted-foreground">{label}</span>
              <span className="font-mono text-xs sm:text-sm">{value}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </main>
  );
}

function HealthCell({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs tracking-wide uppercase">{label}</p>
      <p className="mt-1 font-medium text-foreground">{value ?? "unknown"}</p>
    </div>
  );
}
