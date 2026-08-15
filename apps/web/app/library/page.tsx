import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UploadDropzone } from "@/components/upload-dropzone";
import { getHealth } from "@/lib/api";

function statusLabel(status: string): string {
  if (status === "ok") return "ok";
  if (status === "degraded") return "degraded";
  return "unreachable";
}

export default async function LibraryPage() {
  let health: Awaited<ReturnType<typeof getHealth>> | null = null;
  try {
    health = await getHealth();
  } catch {
    health = null;
  }

  const label = health ? statusLabel(health.status) : "unreachable";

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Local PDFs stay on this machine.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-base">
            API health
            <Badge variant={label === "ok" ? "default" : "secondary"}>{label}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          {health
            ? `postgres ${health.postgres} · redis ${health.redis} · ollama ${health.ollama}`
            : "Could not reach the API at /backend/health."}
        </CardContent>
      </Card>
      <UploadDropzone />
    </main>
  );
}
