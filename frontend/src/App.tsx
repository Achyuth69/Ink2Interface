import { useState, useCallback, useEffect, useRef } from "react";
import { useDropzone } from "react-dropzone";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  Upload, Code2, Loader2, Copy, Check, Menu, X,
  Trash2, Globe, Wand2, Download, RotateCcw, Zap, FileCode, RefreshCw,
} from "lucide-react";
import { generateCode, GenerateResponse } from "./api";

const MODEL_TIERS = [
  { id: "ink2interface-fast",     label: "Fast",     sub: "2B",  activeBg: "bg-emerald-600 border-emerald-500", inactiveBg: "bg-emerald-950/40 border-emerald-800", color: "text-emerald-400" },
  { id: "ink2interface-balanced", label: "Balanced", sub: "7B",  activeBg: "bg-violet-600 border-violet-500",   inactiveBg: "bg-violet-950/40 border-violet-800",   color: "text-violet-400"  },
  { id: "ink2interface-pro",      label: "Pro",      sub: "72B", activeBg: "bg-amber-600 border-amber-500",     inactiveBg: "bg-amber-950/40 border-amber-800",     color: "text-amber-400"   },
];

type SourceMode = "screenshot" | "html";

function usePreviewUrl(code: string) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!code.trim()) { setUrl(""); return; }
    let html = code.trim();
    const fenceMatch = html.match(/```[a-zA-Z]*\n?([\s\S]*?)```/);
    if (fenceMatch) html = fenceMatch[1].trim();
    html = html.replace(/^```[a-zA-Z]*\s*\n?/, "").replace(/\n?\s*```\s*$/, "");
    const docStart = html.search(/<!DOCTYPE\s+html|<html/i);
    if (docStart > 0) html = html.slice(docStart);
    if (!html.includes("tailwindcss")) {
      const tw = '<script src="https://cdn.tailwindcss.com"></script>';
      html = html.includes("</head>") ? html.replace("</head>", `${tw}\n</head>`) : `${tw}\n` + html;
    }
    if (!html.includes("<style")) {
      const base = `<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0}img{max-width:100%}*{box-sizing:border-box}</style>`;
      html = html.includes("</head>") ? html.replace("</head>", `${base}\n</head>`) : base + html;
    }
    html = html.replace(/<head>/i, `<head><meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;">`);
    const blob = new Blob([html], { type: "text/html" });
    const blobUrl = URL.createObjectURL(blob);
    setUrl(blobUrl);
    return () => URL.revokeObjectURL(blobUrl);
  }, [code]);
  return url;
}

// ── Sidebar — defined OUTSIDE App so it never remounts on parent re-render ──
interface SidebarProps {
  sourceMode: SourceMode;
  setSourceMode: (m: SourceMode) => void;
  images: File[];
  previews: string[];
  onDrop: (files: File[]) => void;
  removeImage: (i: number) => void;
  isDragActive: boolean;
  getRootProps: () => object;
  getInputProps: () => object;
  sourceHtml: string;
  setSourceHtml: (v: string) => void;
  sourceUrl: string;
  setSourceUrl: (v: string) => void;
  prompt: string;
  setPrompt: (v: string) => void;
  modelTier: string;
  setModelTier: (v: string) => void;
  loading: boolean;
  result: GenerateResponse | null;
  error: string;
  onReset: () => void;
  onGenerate: () => void;
}

function Sidebar({
  sourceMode, setSourceMode,
  previews, removeImage, isDragActive, getRootProps, getInputProps,
  sourceHtml, setSourceHtml,
  sourceUrl, setSourceUrl,
  prompt, setPrompt,
  modelTier, setModelTier,
  loading, result, error,
  onReset, onGenerate,
}: SidebarProps) {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 flex flex-col gap-4 flex-1 overflow-y-auto min-h-0">

        {/* Source toggle */}
        <div>
          <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 block">Source Input</label>
          <div className="flex rounded-lg overflow-hidden border border-gray-700">
            <button onClick={() => setSourceMode("screenshot")}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors
                ${sourceMode === "screenshot" ? "bg-violet-600 text-white" : "bg-gray-900 text-gray-400 hover:text-gray-200"}`}>
              <Upload size={12} /> Screenshot
            </button>
            <button onClick={() => setSourceMode("html")}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors border-l border-gray-700
                ${sourceMode === "html" ? "bg-violet-600 text-white" : "bg-gray-900 text-gray-400 hover:text-gray-200"}`}>
              <FileCode size={12} /> HTML Source
            </button>
          </div>
        </div>

        {/* Dropzone */}
        {sourceMode === "screenshot" && (
          <div>
            <div {...getRootProps() as React.HTMLAttributes<HTMLDivElement>}
              className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all
                ${isDragActive ? "border-violet-500 bg-violet-950/30" : "border-gray-700 hover:border-gray-500 hover:bg-gray-900/50"}`}>
              <input {...getInputProps() as React.InputHTMLAttributes<HTMLInputElement>} />
              <Upload className="mx-auto mb-2 text-gray-500" size={20} />
              <p className="text-sm text-gray-400">{isDragActive ? "Drop here" : "Tap or drag to upload"}</p>
              <p className="text-xs text-gray-600 mt-1">PNG, JPG, WebP</p>
            </div>
            {previews.length > 0 && (
              <div className="mt-2 grid grid-cols-3 gap-1.5">
                {previews.map((src, i) => (
                  <div key={i} className="relative group aspect-video">
                    <img src={src} className="w-full h-full object-cover rounded-lg" alt="" />
                    <button onClick={() => removeImage(i)}
                      className="absolute top-1 right-1 bg-red-600 rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Trash2 size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* HTML paste */}
        {sourceMode === "html" && (
          <div>
            <div className="mb-2 bg-blue-950/40 border border-blue-800 rounded-lg px-3 py-2 text-[11px] text-blue-300 leading-relaxed">
              F12 → Elements → right-click &lt;html&gt; → Copy outerHTML → paste below
            </div>
            <textarea
              value={sourceHtml}
              onChange={(e) => setSourceHtml(e.target.value)}
              rows={8}
              placeholder="<!DOCTYPE html><html>...</html>"
              spellCheck={false}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-green-300 font-mono placeholder-gray-600 focus:outline-none focus:border-violet-500 resize-y"
            />
            <div className="flex items-center justify-between mt-1">
              <span className="text-[10px] text-gray-600 font-mono">{sourceHtml.length.toLocaleString()} chars</span>
              {sourceHtml.length > 0 && (
                <button onClick={() => setSourceHtml("")} className="text-[10px] text-gray-600 hover:text-red-400">Clear</button>
              )}
            </div>
          </div>
        )}

        {/* URL */}
        <div>
          <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
            <Globe size={11} /> Reference URL
            <span className="text-gray-600 font-normal normal-case ml-1">(optional)</span>
          </label>
          <input
            type="url"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://example.com"
            autoComplete="off"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-violet-500 transition-colors"
          />
        </div>

        {/* Prompt */}
        <div>
          <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5 block">
            Extra Instructions
            <span className="text-gray-600 font-normal normal-case ml-1">(optional)</span>
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            placeholder="e.g. Make it dark mode, add animations..."
            autoComplete="off"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-violet-500 resize-none transition-colors"
          />
        </div>

        {/* Model Tier */}
        <div>
          <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5 block">
            Model Tier
            <span className="text-gray-600 font-normal normal-case ml-1">(local GPU only)</span>
          </label>
          <div className="flex gap-1.5">
            {MODEL_TIERS.map((t) => (
              <button key={t.id} onClick={() => setModelTier(t.id)}
                className={`flex-1 flex flex-col items-center py-2 px-1 rounded-xl border text-xs font-semibold transition-all
                  ${modelTier === t.id ? t.activeBg + " text-white shadow-lg scale-[1.03]" : t.inactiveBg + " text-gray-500 hover:text-gray-300"}`}>
                <span className={`font-bold ${modelTier === t.id ? "text-white" : t.color}`}>{t.label}</span>
                <span className="text-[9px] font-normal opacity-60 mt-0.5">{t.sub}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="bg-violet-950/30 border border-violet-800 rounded-lg px-3 py-2 text-[11px] text-violet-300">
          Output: <strong>HTML + CSS</strong> — self-contained, opens in any browser
        </div>

        {error && (
          <div className="text-red-400 text-xs bg-red-950/40 border border-red-800 rounded-lg px-3 py-2">{error}</div>
        )}
      </div>

      {/* Actions */}
      <div className="p-4 border-t border-gray-800 flex gap-2 flex-shrink-0">
        <button onClick={onReset} title="Reset"
          className="p-2.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors">
          <RotateCcw size={16} />
        </button>
        <button onClick={onGenerate} disabled={loading}
          className="flex-1 flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 active:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg transition-colors text-sm">
          {loading
            ? <><Loader2 size={16} className="animate-spin" /> Generating{result?.code ? ` · ${result.code.length} chars` : "..."}</>
            : <><Wand2 size={16} /> Generate Code</>}
        </button>
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const iframeRef                   = useRef<HTMLIFrameElement>(null);
  const [expiresAt, setExpiresAt]   = useState<number | null>(null);
  const [timeLeft, setTimeLeft]     = useState<string>("");

  const previewUrl = usePreviewUrl(result?.code ?? "");

  // Auto-close sidebar on mobile after result
  useEffect(() => {
    if (result?.code && window.innerWidth < 768) {
      setSidebarOpen(false);
    }
  }, [result?.code]);

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
    setSidebarOpen(true);
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
        { images: sourceMode === "screenshot" ? images : [], prompt, sourceUrl,
          sourceHtml: sourceMode === "html" ? sourceHtml : "",
          techStack: "html-tailwind", modelTier },
        (token) => setResult((prev) => prev ? { ...prev, code: prev.code + token } : null)
      );
      setResult(res);
      setExpiresAt(Date.now() + 60 * 60 * 1000);
      setTab("preview");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed.");
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
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "output.html"; a.click();
    URL.revokeObjectURL(url);
  };

  const downloadSplit = () => {
    if (!result) return;
    const styleMatch = result.code.match(/<style[^>]*>([\s\S]*?)<\/style>/i);
    const css = styleMatch ? styleMatch[1].trim() : "";
    const htmlOut = result.code
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
      .replace("</head>", '  <link rel="stylesheet" href="styles.css">\n</head>');
    const dl = (c: string, n: string) => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([c], { type: "text/plain" }));
      a.download = n; a.click();
    };
    dl(htmlOut, "index.html");
    setTimeout(() => dl(css, "styles.css"), 200);
  };

  return (
    <div className="h-[100dvh] bg-gray-950 flex flex-col overflow-hidden">

      {/* Header */}
      <header className="border-b border-gray-800 px-4 py-3 flex items-center justify-between flex-shrink-0 z-10">
        <div className="flex items-center gap-2">
          <button
            className="md:hidden p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            onClick={() => setSidebarOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <div className="w-8 h-8 bg-violet-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <Zap size={16} className="text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white leading-none">Ink2Interface</h1>
            <p className="text-[10px] text-gray-500 mt-0.5">Screenshot → HTML + CSS</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
          <span className="hidden sm:inline">Groq</span>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden relative">

        {/* Mobile backdrop — only shown on mobile */}
        {sidebarOpen && (
          <div
            className="md:hidden fixed inset-0 bg-black/70 z-20 top-[57px]"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sidebar */}
        <aside className={`
          bg-gray-950 border-r border-gray-800 flex-shrink-0
          md:static md:z-auto md:w-[360px] md:translate-x-0
          fixed top-[57px] left-0 bottom-0 z-30 w-[320px]
          transition-transform duration-300 ease-in-out
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
        `}>
          <div className="w-[320px] md:w-[360px] h-full flex flex-col">
            <Sidebar
              sourceMode={sourceMode} setSourceMode={setSourceMode}
              images={images} previews={previews}
              onDrop={onDrop} removeImage={removeImage}
              isDragActive={isDragActive}
              getRootProps={getRootProps} getInputProps={getInputProps}
              sourceHtml={sourceHtml} setSourceHtml={setSourceHtml}
              sourceUrl={sourceUrl} setSourceUrl={setSourceUrl}
              prompt={prompt} setPrompt={setPrompt}
              modelTier={modelTier} setModelTier={setModelTier}
              loading={loading} result={result} error={error}
              onReset={reset} onGenerate={handleGenerate}
            />
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          {result ? (
            <>
              {result.code.trim() === "" && !loading && (
                <div className="mx-3 mt-3 bg-amber-950/40 border border-amber-800 rounded-lg px-3 py-2 text-xs text-amber-400">
                  ⚠️ Empty output — try adding more detail to your prompt.
                </div>
              )}

              {/* Toolbar */}
              <div className="flex items-center justify-between border-b border-gray-800 px-3 py-2 bg-gray-900/50 flex-shrink-0 gap-2">
                <div className="flex items-center gap-1">
                  <button
                    className="md:hidden p-1.5 rounded-lg bg-gray-800 text-gray-400 mr-1"
                    onClick={() => setSidebarOpen(true)}
                  >
                    <Menu size={14} />
                  </button>
                  {(["code", "preview"] as const).map((t) => (
                    <button key={t} onClick={() => setTab(t)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize
                        ${tab === t ? "bg-gray-700 text-white" : "text-gray-500 hover:text-gray-300"}`}>
                      {t}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1">
                  {timeLeft && (
                    <span className="text-[10px] text-amber-500 bg-amber-950/40 border border-amber-800 px-1.5 py-1 rounded font-mono">
                      🕐 {timeLeft}
                    </span>
                  )}
                  {tab === "preview" && (
                    <button onClick={() => { if (iframeRef.current && previewUrl) { iframeRef.current.src = ""; iframeRef.current.src = previewUrl; } }}
                      className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300">
                      <RefreshCw size={12} />
                    </button>
                  )}
                  <button onClick={downloadCode} className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300" title="Download">
                    <Download size={12} />
                  </button>
                  <button onClick={downloadSplit} className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300" title="HTML+CSS">
                    <FileCode size={12} />
                  </button>
                  <button onClick={copyCode} className="flex items-center gap-1 px-2 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-xs">
                    {copied ? <><Check size={12} className="text-emerald-400" /> Copied</> : <><Copy size={12} /> Copy</>}
                  </button>
                </div>
              </div>

              {tab === "code" ? (
                <div className="flex-1 overflow-auto">
                  <SyntaxHighlighter language="html" style={vscDarkPlus}
                    customStyle={{ margin: 0, minHeight: "100%", fontSize: "11px", background: "#030712" }}
                    showLineNumbers lineNumberStyle={{ color: "#374151", minWidth: "2em" }}>
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
            <div className="flex-1 flex flex-col items-center justify-center gap-4 text-gray-700 select-none px-6">
              <div className="w-16 h-16 rounded-2xl bg-gray-900 border border-gray-800 flex items-center justify-center">
                <Code2 size={28} strokeWidth={1.2} className="text-gray-600" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-gray-500">Generated code appears here</p>
                <p className="text-xs text-gray-700 mt-1">Upload a screenshot or paste HTML</p>
              </div>
              <div className="flex flex-wrap justify-center gap-2 text-xs">
                <span className="px-2.5 py-1 bg-gray-900 rounded-lg border border-gray-800 text-gray-500">HTML + CSS</span>
                <span className="px-2.5 py-1 bg-gray-900 rounded-lg border border-gray-800 text-gray-500">Self-contained</span>
                <span className="px-2.5 py-1 bg-gray-900 rounded-lg border border-gray-800 text-gray-500">Pixel-perfect</span>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
