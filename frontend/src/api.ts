export interface GenerateRequest {
  images: File[];
  prompt: string;
  sourceUrl: string;
  sourceHtml: string;
  techStack: string;
  modelTier: string;
}

export interface GenerateResponse {
  code: string;
  tech_stack: string;
  model: string;
  tier: string | null;
}

// In dev: Vite proxies /api → localhost:8080
// In prod (Railway): VITE_API_URL is set to the backend Railway URL
const BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, "")
  : "/api";

export async function generateCode(
  req: GenerateRequest,
  onToken?: (token: string) => void
): Promise<GenerateResponse> {
  const form = new FormData();
  form.append("prompt",      req.prompt);
  form.append("tech_stack",  req.techStack);
  form.append("model_tier",  req.modelTier);
  form.append("source_url",  req.sourceUrl);
  form.append("source_html", req.sourceHtml);
  req.images.forEach((img) => form.append("images", img));

  const endpoint = import.meta.env.VITE_API_URL
    ? `${BASE}/generate/stream`
    : `/api/generate/stream`;

  const resp = await fetch(endpoint, { method: "POST", body: form });

  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  if (!resp.body) throw new Error("No response body");

  const reader  = resp.body.getReader();
  const decoder = new TextDecoder();
  let code = "", tech_stack = req.techStack, model = "groq";
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      let data: Record<string, unknown>;
      try { data = JSON.parse(raw); } catch { continue; }
      if (data.error) throw new Error(String(data.error));
      if (data.token && typeof data.token === "string") {
        code += data.token;
        if (onToken) onToken(data.token);
      }
      if (data.done) {
        tech_stack = (data.tech_stack as string) || tech_stack;
        model      = (data.model as string) || model;
      }
    }
  }

  return { code, tech_stack, model, tier: null };
}
