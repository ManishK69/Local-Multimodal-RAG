export const API_BASE =
  typeof window === "undefined" ? "http://127.0.0.1:8000" : "/backend";

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("health failed");
  return res.json() as Promise<{
    status: string;
    postgres: string;
    redis: string;
    ollama: string;
    models: { embed: boolean; vision: boolean; generate: boolean };
  }>;
}
