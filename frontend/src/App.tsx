import { useState, useCallback, useEffect, useRef } from "react";
import { useDropzone } from "react-dropzone";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  Upload, Code2, Loader2, Copy, Check,
  Trash2, Globe, Wand2, Download, RotateCcw, Zap, FileCode, RefreshCw,
} from "lucide-react";
import { generateCode, GenerateResponse } from "./api";

const MODEL_TIERS = [
  { id: "ink2interface-fast",     label: "Fast",     sub: "2B",  activeBg: "bg-emerald-600 border-emerald-500", inactiveBg: "bg-emerald-950/40 border-emerald-800", color: "text-emerald-400" },
  { id: "ink2interface-balanced", label: "Balanced", sub: "7B",  activeBg: "bg-violet-600 border-violet-500",   inactiveBg: "bg-violet-950/40 border-violet-800",   color: "text-violet-400"  },
  { id: "ink2interface-pro",      label: "Pro",      sub: "72B", activeBg: "bg-amber-600 border-amber-500",     inactiveBg: "bg-amber-950/40 border-amber-800",     color: "text-amber-400"   },
];

type SourceMode = "screenshot" | "html";

// ── Preview: blob URL — immune to any escaping issues ──
function usePreviewUrl(code: string) {
  const [url, setUrl] = useState("");

  useEffect(() => {
    if (!code.trim()) { setUrl(""); return; }

    let html = code.trim();

    // Strip markdown fences if model leaked them
    const fenceMatch = html.match(/```[a-zA-Z]*\n?([\s\S]*?)```/);
    if (fenceMatch) html = fenceMatch[1].trim();
    html = html.replace(/^```[a-zA-Z]*\s*\n?/, "").replace(/\n?\s*```\s*$/, "");

    // Trim anything before <!DOCTYPE or <html
    const docStart = html.search(/<!DOCTYPE\s+html|<html/i);
    if (docStart > 0) html = html.slice(docStart);

    // Always inject Tailwind CDN
    const tailwind = '<script src="https://cdn.tailwindcss.com"></script>';
    if (!html.includes("tailwindcss")) {
      html = html.includes("</head>")
        ? html.replace("</head>", `  ${tailwind}\n</head>`)
        : `${tailwind}\n` + html;
    }

    // Inject base reset so unstyled HTML at least looks decent
    const baseStyle = `<style>
      body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; }
      img { max-width: 100%; }
      a { color: #0073b1; }
      * { box-sizing: border-box; }
    </style>`;
    if (!html.includes("<style")) {
      html = html.includes("</head>")
        ? html.replace("</head>", `  ${baseStyle}\n</head>`)
        : baseStyle + html;
    }

    // Allow external resources (LinkedIn CDN images etc)
    html = html.replace(
      /<head>/i,
      `<head><meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;">`
    );

    const blob = new Blob([html], { type: "text/html" });
    const blobUrl = URL.createObjectURL(blob);
    setUrl(blobUrl);
    return () => URL.revokeObjectURL(blobUrl);
  }, [code]);

  return url;
}

export default function App() {
  const [sourceMode, setSourceMode] = useState<SourceMode>("screenshot");
  const [images, setImages]         = useState<File[]>([]);
  const [previews, setPreviews]     = useState<string[]>([]);
  const [sourceHtml, setSourceHtml] = useState("");
  const [prompt, setPrompt]         = useState("");
  const [sourceUrl, setSourceUrl]   = useState("");
  const [modelTier, setModelTier]   = useState("ink2interface-balanced");
  const [loading, setLoading]       = useState(false);
  const [result, setResult]         = useState<GenerateResponse | null>(null);
  const [error, setError]           = useState("");
  const [copied, setCopied]         = useState(false);
  const [tab, setTab]               = useState<"code" | "preview">("preview");
  const iframeRef                   = useRef<HTMLIFrameElement>(null);
  const [expiresAt, setExpiresAt]   = useState<number | null>(null);
  const [timeLeft, setTimeLeft]     = useState<string>("");

  const previewUrl = usePreviewUrl(result?.code ?? "");

  // 1-hour TTL countdown
  useEffect(() => {
    if (!expiresAt) return;
    const tick = () => {
      const diff = expiresAt - Date.now();
      if (diff <= 0) { setResult(null); setExpiresAt(null); setTimeLeft(""); return; }
      const m = Math.floor(diff / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setTimeLeft(`${m}:${s.toString().padStart(2, "0")}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  const onDrop = useCallback((accepted: File[]) => {
    setImages((p) => [...p, ...accepted]);
    accepted.forEach((f) => setPreviews((p) => [...p, URL.createObjectURL(f)]));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { "image/*": [] }, multiple: true,
  });

  const removeImage = (i: number) => {
    URL.revokeObjectURL(previews[i]);
    setImages((p) => p.filter((_, idx) => idx !== i));
    setPreviews((p) => p.filter((_, idx) => idx !== i));
  };

  const reset = () => {
    previews.forEach(URL.revokeObjectURL);
    setImages([]); setPreviews([]); setSourceHtml(""); setPrompt(""); setSourceUrl("");
    setResult(null); setError(""); setExpiresAt(null); setTimeLeft("");
  };

  const handleGenerate = async () => {
    const hasSource = sourceMode === "screenshot" ? images.length > 0 : sourceHtml.trim().length > 0;
    if (!hasSource && !prompt && !sourceUrl) {
      setError(sourceMode === "screenshot"
        ? "Upload a screenshot, paste a URL, or add a prompt."
        : "Paste HTML source or add a prompt.");
      return;
    }
    setError(""); setLoading(true); setResult(null);
    setResult({ code: "", tech_stack: "html-tailwind", model: "...", tier: null });
    setTab("code");
    try {
      const res = await generateCode(
        {
          images: sourceMode === "screenshot" ? images : [],
          prompt, sourceUrl,
          sourceHtml: sourceMode === "html" ? sourceHtml : "",
          techStack: "html-tailwind",
          modelTier,
        },
        (token) => setResult((prev) => prev ? { ...prev, code: prev.code + token } : null)
      );
      setResult(res);
      setExpiresAt(Date.now() + 60 * 60 * 1000);
      setTab("preview");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed. Check your API key.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const copyCode = () => {
    if (!result) return;
    navigator.clipboard.writeText(result.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadCode = () => {
    if (!result) return;
    const blob = new Blob([result.code], { type: "text/html" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = "ink2interface-output.html"; a.click();
    URL.revokeObjectURL(url);
  };

  const downloadSplit = () => {
    if (!result) return;
    const styleMatch = result.code.match(/<style[^>]*>([\s\S]*?)<\/style>/i);
    const css = styleMatch ? styleMatch[1].trim() : "";
    const htmlWithoutStyle = result.code
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
      .replace("</head>", '  <link rel="stylesheet" href="styles.css">\n</head>');
    const dl = (content: string, name: string) => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
      a.download = name; a.click();
    };
    dl(htmlWithoutStyle, "index.html");
    setTimeout(() => dl(css, "styles.css"), 200);
  };

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-violet-600 rounded-lg flex items-center justify-center">
            <Zap size={16} className="text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white leading-none">Ink2Interface</h1>
            <p className="text-[11px] text-gray-500 mt-0.5">Screenshot → HTML + CSS</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse inline-block" />
          Powered by Groq
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Left panel ── */}
        <aside className="w-[380px] border-r border-gray-800 flex flex-col overflow-y-auto">
          <div className="p-4 flex flex-col gap-4 flex-1">

            {/* Source mode toggle */}
            <div>
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 block">Source Input</label>
              <div className="flex rounded-lg overflow-hidden border border-gray-700">
                <button
                  onClick={() => setSourceMode("screenshot")}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors
                    ${sourceMode === "screenshot" ? "bg-violet-600 text-white" : "bg-gray-900 text-gray-400 hover:text-gray-200"}`}
                >
                  <Upload size={12} /> Screenshot
                </button>
                <button
                  onClick={() => setSourceMode("html")}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors border-l border-gray-700
                    ${sourceMode === "html" ? "bg-violet-600 text-white" : "bg-gray-900 text-gray-400 hover:text-gray-200"}`}
                >
                  <FileCode size={12} /> HTML Source
                </button>
              </div>
            </div>

            {/* Screenshot dropzone */}
            {sourceMode === "screenshot" && (
              <div>
                <div
                  {...getRootProps()}
                  className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all
                    ${isDragActive ? "border-violet-500 bg-violet-950/30 scale-[1.01]" : "border-gray-700 hover:border-gray-500 hover:bg-gray-900/50"}`}
                >
                  <input {...getInputProps()} />
                  <Upload className="mx-auto mb-2 text-gray-500" size={20} />
                  <p className="text-sm text-gray-400">{isDragActive ? "Drop screenshots here" : "Drag & drop or click to upload"}</p>
                  <p className="text-xs text-gray-600 mt-1">PNG, JPG, WebP — multiple allowed</p>
                </div>
                {previews.length > 0 && (
                  <div className="mt-2 grid grid-cols-3 gap-1.5">
                    {previews.map((src, i) => (
                      <div key={i} className="relative group aspect-video">
                        <img src={src} className="w-full h-full object-cover rounded-lg" alt="" />
                        <button onClick={() => removeImage(i)} className="absolute top-1 right-1 bg-red-600 rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Trash2 size={10} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* HTML paste panel */}
            {sourceMode === "html" && (
              <div>
                <div className="mb-2 bg-blue-950/40 border border-blue-800 rounded-lg px-3 py-2 text-[11px] text-blue-300 leading-relaxed">
                  <strong>How to get the HTML:</strong><br />
                  1. Open the site in Chrome / Edge<br />
                  2. Press <kbd className="bg-blue-900 px-1 rounded">F12</kbd> → Elements tab<br />
                  3. Right-click the <code className="bg-blue-900 px-1 rounded">&lt;html&gt;</code> tag<br />
                  4. <strong>Copy → Copy outerHTML</strong><br />
                  5. Paste below ↓
                </div>
                <textarea
                  value={sourceHtml}
                  onChange={(e) => setSourceHtml(e.target.value)}
                  rows={10}
                  placeholder="<!DOCTYPE html><html>...</html>"
                  spellCheck={false}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-green-300 font-mono placeholder-gray-600 focus:outline-none focus:border-violet-500 resize-y"
                />
                <div className="flex items-center justify-between mt-1">
                  <span className="text-[10px] text-gray-600 font-mono">{sourceHtml.length.toLocaleString()} chars</span>
                  {sourceHtml.length > 0 && (
                    <button onClick={() => setSourceHtml("")} className="text-[10px] text-gray-600 hover:text-red-400 transition-colors">Clear</button>
                  )}
                </div>
              </div>
            )}

            {/* Reference URL */}
            <div>
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                <Globe size={11} /> Reference URL
                <span className="text-gray-600 font-normal normal-case tracking-normal ml-1">(optional)</span>
              </label>
              <input
                type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="https://example.com"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-violet-500 transition-colors"
              />
            </div>

            {/* Prompt */}
            <div>
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5 block">
                Extra Instructions
                <span className="text-gray-600 font-normal normal-case tracking-normal ml-1">(optional)</span>
              </label>
              <textarea
                value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
                placeholder="e.g. Make it dark mode, add animations..."
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-violet-500 resize-none transition-colors"
              />
            </div>

            {/* Model Tier */}
            <div>
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5 block">
                Model Tier
                <span className="text-gray-600 font-normal normal-case tracking-normal ml-1">(local GPU only)</span>
              </label>
              <div className="flex gap-1.5">
                {MODEL_TIERS.map((t) => (
                  <button key={t.id} onClick={() => setModelTier(t.id)}
                    className={`flex-1 flex flex-col items-center py-2 px-1 rounded-xl border text-xs font-semibold transition-all
                      ${modelTier === t.id ? t.activeBg + " text-white shadow-lg scale-[1.03]" : t.inactiveBg + " text-gray-500 hover:text-gray-300"}`}
                  >
                    <span className={`font-bold ${modelTier === t.id ? "text-white" : t.color}`}>{t.label}</span>
                    <span className="text-[9px] font-normal opacity-60 mt-0.5">{t.sub}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Output label */}
            <div className="bg-violet-950/30 border border-violet-800 rounded-lg px-3 py-2 text-[11px] text-violet-300">
              Output: <strong>HTML + CSS</strong> — self-contained, ready to open in any browser
            </div>

            {error && (
              <div className="text-red-400 text-xs bg-red-950/40 border border-red-800 rounded-lg px-3 py-2">{error}</div>
            )}
          </div>

          {/* Action buttons */}
          <div className="p-4 border-t border-gray-800 flex gap-2">
            <button onClick={reset} title="Reset all" className="p-2.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors">
              <RotateCcw size={16} />
            </button>
            <button onClick={handleGenerate} disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 active:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg transition-colors text-sm"
            >
              {loading
                ? <><Loader2 size={16} className="animate-spin" /> Generating{result?.code ? ` · ${result.code.length} chars` : "..."}</>
                : <><Wand2 size={16} /> Generate Code</>}
            </button>
          </div>
        </aside>

        {/* ── Right panel ── */}
        <main className="flex-1 flex flex-col overflow-hidden bg-gray-950">
          {result ? (
            <>
              {result.code.trim() === "" && !loading && (
                <div className="mx-4 mt-4 flex items-center gap-2 bg-amber-950/40 border border-amber-800 rounded-lg px-3 py-2 text-xs text-amber-400">
                  ⚠️ The model returned empty output. Try adding more detail to your prompt.
                </div>
              )}

              {/* Toolbar */}
              <div className="flex items-center justify-between border-b border-gray-800 px-4 py-2.5 bg-gray-900/50">
                <div className="flex gap-1">
                  {(["code", "preview"] as const).map((t) => (
                    <button key={t} onClick={() => setTab(t)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize
                        ${tab === t ? "bg-gray-700 text-white" : "text-gray-500 hover:text-gray-300"}`}
                    >{t}</button>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-gray-600 hidden sm:block">{result.model}</span>
                  {timeLeft && (
                    <span className="text-[10px] text-amber-500 bg-amber-950/40 border border-amber-800 px-2 py-1 rounded-md font-mono">
                      🕐 {timeLeft}
                    </span>
                  )}
                  {tab === "preview" && (
                    <button
                      onClick={() => { if (iframeRef.current && previewUrl) { iframeRef.current.src = ""; iframeRef.current.src = previewUrl; } }}
                      className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 px-2.5 py-1.5 rounded-lg transition-colors text-gray-300"
                      title="Reload preview"
                    >
                      <RefreshCw size={12} />
                    </button>
                  )}
                  <button onClick={downloadCode} className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 px-2.5 py-1.5 rounded-lg transition-colors text-gray-300">
                    <Download size={12} /> Download
                  </button>
                  <button onClick={downloadSplit} className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 px-2.5 py-1.5 rounded-lg transition-colors text-gray-300" title="Download as separate HTML + CSS files">
                    <FileCode size={12} /> HTML+CSS
                  </button>
                  <button onClick={copyCode} className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 px-2.5 py-1.5 rounded-lg transition-colors text-gray-300">
                    {copied ? <><Check size={12} className="text-emerald-400" /> Copied!</> : <><Copy size={12} /> Copy</>}
                  </button>
                </div>
              </div>

              {tab === "code" ? (
                <div className="flex-1 overflow-auto">
                  <SyntaxHighlighter
                    language="html"
                    style={vscDarkPlus}
                    customStyle={{ margin: 0, minHeight: "100%", fontSize: "12.5px", background: "#030712" }}
                    showLineNumbers
                    lineNumberStyle={{ color: "#374151", minWidth: "2.5em" }}
                  >
                    {result.code || " "}
                  </SyntaxHighlighter>
                </div>
              ) : (
                <iframe
                  ref={iframeRef}
                  key={previewUrl}
                  src={previewUrl}
                  className="flex-1 w-full bg-white"
                  title="Preview"
                  sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                />
              )}
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center gap-5 text-gray-700 select-none">
              <div className="w-20 h-20 rounded-2xl bg-gray-900 border border-gray-800 flex items-center justify-center">
                <Code2 size={36} strokeWidth={1.2} className="text-gray-600" />
              </div>
              <div className="text-center">
                <p className="text-base font-medium text-gray-500">Generated code appears here</p>
                <p className="text-sm text-gray-700 mt-1">Upload a screenshot or paste HTML from DevTools</p>
              </div>
              <div className="flex gap-3 text-xs text-gray-700">
                <span className="px-3 py-1.5 bg-gray-900 rounded-lg border border-gray-800 text-gray-500">HTML + CSS</span>
                <span className="px-3 py-1.5 bg-gray-900 rounded-lg border border-gray-800 text-gray-500">Self-contained</span>
                <span className="px-3 py-1.5 bg-gray-900 rounded-lg border border-gray-800 text-gray-500">Pixel-perfect</span>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
