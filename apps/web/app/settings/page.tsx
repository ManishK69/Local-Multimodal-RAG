import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getHealth, getSettings } from "@/lib/api";
import Link from "next/link";

export default async function SettingsPage() {
  let health: Awaited<ReturnType<typeof getHealth>> | null = null;
  let settings: Awaited<ReturnType<typeof getSettings>> | null = null;
  try {
    [health, settings] = await Promise.all([getHealth(), getSettings()]);
  } catch {
    health = null;
    settings = null;
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-8">
      <div>
        <p className="text-muted-foreground mb-2 text-sm">
          <Link className="hover:underline" href="/library">
            Library
          </Link>
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Read-only. Change models in <code>.env</code> and restart the API.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-base">
            Health
            <Badge variant={health?.status === "ok" ? "default" : "secondary"}>
              {health?.status ?? "unreachable"}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground space-y-1 text-sm">
          <p>postgres {health?.postgres ?? "unknown"}</p>
          <p>redis {health?.redis ?? "unknown"}</p>
          <p>ollama {health?.ollama ?? "unknown"}</p>
          <p>
            models embed={String(health?.models.embed ?? false)} vision=
            {String(health?.models.vision ?? false)} generate=
            {String(health?.models.generate ?? false)}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Models</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground space-y-1 text-sm">
          <p>embed: {settings?.embedModel ?? "—"}</p>
          <p>vision: {settings?.visionModel ?? "—"}</p>
          <p>generate: {settings?.generateModel ?? "—"}</p>
          <p>embedding dim: {settings?.embeddingDim ?? "—"}</p>
          <p>max upload bytes: {settings?.maxUploadBytes ?? "—"}</p>
        </CardContent>
      </Card>
    </main>
  );
}
