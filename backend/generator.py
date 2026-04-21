"""
Ink2Interface — generator.py
Handles both Groq (cloud) and local Qwen2-VL model backends.

MODEL_BACKEND=groq  → uses Groq API (default, no GPU needed)
MODEL_BACKEND=local → uses fine-tuned Qwen2-VL tiers (GPU required)

Model tiers (mirrors YOLOv8 n/s/m philosophy):
  ink2interface-fast     → Qwen2-VL-2B  (~6GB  VRAM)
  ink2interface-balanced → Qwen2-VL-7B  (~16GB VRAM)
  ink2interface-pro      → Qwen2-VL-72B (~80GB VRAM, multi-GPU)
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# ── Env ───────────────────────────────────────────────────────────────────────
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "groq").lower()

# Groq
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL     = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_MODEL_FAST = "meta-llama/llama-4-scout-17b-16e-instruct"

# Local model paths
_LOCAL_PATHS = {
    "ink2interface-fast":     os.getenv("INK2INTERFACE_FAST_PATH",     "Qwen/Qwen2-VL-2B-Instruct"),
    "ink2interface-balanced": os.getenv("INK2INTERFACE_BALANCED_PATH", "Qwen/Qwen2-VL-7B-Instruct"),
    "ink2interface-pro":      os.getenv("INK2INTERFACE_PRO_PATH",      "Qwen/Qwen2-VL-72B-Instruct"),
}

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert frontend developer. You will be given a screenshot of a webpage.
Your task is to write a complete, self-contained HTML file that looks EXACTLY like the screenshot.

RULES:
1. Output ONLY the HTML. Start with <!DOCTYPE html> and end with </html>. Nothing else.
2. NO markdown fences (no ```). NO explanations. NO comments.
3. Put ALL CSS in a <style> block inside <head>. No external CSS links.
4. Match EXACTLY: background colors, text colors, button colors, fonts, layout, spacing, borders, shadows.
5. Use the exact colors you see — if the background is dark navy, use that exact dark navy hex.
6. Reproduce every visible element: header, logo, form fields, buttons, links, images (use the actual src URLs).
7. The result must look identical to the screenshot when opened in a browser."""

# ── Tech-stack instructions ───────────────────────────────────────────────────
STACK_INSTRUCTIONS: dict[str, str] = {
    "html-tailwind": (
        "Output a single self-contained HTML file. "
        "Write ALL CSS inside a <style> block in <head> — use exact hex color values, px/rem sizes. "
        "Do NOT link any external CSS files. Tailwind CDN may be added for utility classes only, "
        "but all brand colors, fonts, and layout must be in the <style> block."
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _image_to_data_url(path: str) -> str:
    """Convert a local image file to a base64 data URL."""
    img = Image.open(path).convert("RGB")
    # Resize if too large (Groq vision limit ~4MB per image)
    max_dim = 1568
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _strip_fences(code: str) -> str:
    """Remove markdown code fences and extract the HTML document."""
    code = code.strip()

    # If wrapped in ```html ... ``` or ``` ... ```, extract the inner content
    fence_match = re.search(r"```[a-zA-Z]*\n?([\s\S]*?)```", code)
    if fence_match:
        code = fence_match.group(1).strip()

    # Remove any remaining leading/trailing fences
    code = re.sub(r"^```[a-zA-Z]*\s*\n?", "", code)
    code = re.sub(r"\n?\s*```\s*$", "", code)

    # If the output starts with garbage before <!DOCTYPE or <html, trim it
    doc_start = re.search(r"(<!DOCTYPE\s+html|<html)", code, re.IGNORECASE)
    if doc_start and doc_start.start() > 0:
        code = code[doc_start.start():]

    return code.strip()


async def _fetch_html(url: str) -> str:
    """Fetch raw HTML + inline linked CSS from a URL (best-effort, 30s timeout)."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            html = r.text

            # Extract and inline linked CSS stylesheets (up to 5 sheets, 20K each)
            import re as _re
            from urllib.parse import urljoin
            css_links = _re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']', html, _re.IGNORECASE)
            css_links += _re.findall(r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']stylesheet["\']', html, _re.IGNORECASE)
            inlined_css = ""
            for href in css_links[:5]:
                try:
                    css_url = urljoin(url, href)
                    cr = await client.get(css_url, headers=headers, timeout=10)
                    if cr.status_code == 200:
                        inlined_css += f"\n/* === {href} === */\n{cr.text[:20_000]}\n"
                except Exception:
                    pass

            result = html[:60_000]
            if inlined_css:
                result += f"\n\n<!-- EXTRACTED CSS STYLESHEETS -->\n<style>\n{inlined_css[:40_000]}\n</style>"
            return result
    except Exception as e:
        return f"<!-- Could not fetch {url}: {e} -->"


# ── Prompt builder ────────────────────────────────────────────────────────────

async def build_prompt(
    image_paths: list[str],
    prompt: str,
    source_url: str,
    source_html: str,
    tech_stack: str,
) -> list[dict]:
    parts: list[dict] = []

    has_images = bool(image_paths and any(Path(p).exists() for p in image_paths))
    has_html   = bool(source_html and source_html.strip())
    has_url    = bool(source_url and source_url.strip())

    # 1. Screenshots first — the primary visual reference
    if has_images:
        parts.append({
            "type": "text",
            "text": "Here is the screenshot of the webpage to clone:"
        })
        for path in image_paths:
            if Path(path).exists():
                data_url = _image_to_data_url(path)
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_url, "detail": "high"},
                })

    # 2. HTML source — structural reference (fetch from URL if needed)
    fetched_html = ""
    if has_url:
        fetched_html = await _fetch_html(source_url)
    
    html_source = source_html if has_html else fetched_html
    if html_source.strip():
        # Truncate to fit context
        if len(html_source) > 30_000:
            html_source = html_source[:28_000] + "\n<!-- truncated -->"
        parts.append({
            "type": "text",
            "text": (
                f"Here is the HTML source of the page (use this for structure and text content, "
                f"but get the visual design from the screenshot above):\n\n{html_source}"
            )
        })

    # 3. Extra user instructions
    if prompt:
        parts.append({"type": "text", "text": f"Additional instructions: {prompt}"})

    # 4. Final command
    instruction = (
        "Now write the complete HTML file.\n"
        "- Start with <!DOCTYPE html>\n"
        "- End with </html>\n"
        "- ALL CSS in a <style> block in <head>\n"
        "- Match the screenshot exactly — colors, layout, fonts, spacing\n"
        "- No markdown, no explanation, just the HTML"
    )
    if not has_images and not html_source.strip():
        instruction = "Generate the requested UI as a complete HTML file with all CSS in a <style> block.\n" + instruction

    parts.append({"type": "text", "text": instruction})
    return parts


# ── Groq backend ──────────────────────────────────────────────────────────────

class GroqGenerator:
    """Wraps the Groq async client."""

    def __init__(self):
        try:
            from groq import AsyncGroq
            self.client = AsyncGroq(api_key=GROQ_API_KEY)
        except ImportError:
            raise RuntimeError("groq package not installed. Run: pip install groq")

    @property
    def model_name(self) -> str:
        return GROQ_MODEL

    async def generate(
        self,
        image_paths: list[str],
        prompt: str,
        source_url: str,
        source_html: str,
        tech_stack: str,
        model_tier: str,
    ) -> dict:
        parts = await build_prompt(image_paths, prompt, source_url, source_html, tech_stack)
        has_images = any(p.get("type") == "image_url" for p in parts)
        model = GROQ_MODEL if has_images else GROQ_MODEL_FAST

        resp = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": parts},
            ],
            max_tokens=8192,
            temperature=0.1,
        )
        code = _strip_fences(resp.choices[0].message.content or "")
        return {"code": code, "tech_stack": tech_stack, "model": model, "tier": model_tier}


# ── Local backend ─────────────────────────────────────────────────────────────

class LocalGenerator:
    """
    Loads a fine-tuned Qwen2-VL model locally.
    Lazy-loads on first call to avoid startup delay.
    """

    def __init__(self):
        self._loaded_tier: str | None = None
        self._processor = None
        self._model = None

    @property
    def model_name(self) -> str:
        return self._loaded_tier or "local (not loaded)"

    def _load(self, tier: str):
        if self._loaded_tier == tier:
            return
        import torch
        from transformers import AutoProcessor, AutoModelForVision2Seq, BitsAndBytesConfig

        model_path = _LOCAL_PATHS.get(tier, _LOCAL_PATHS["ink2interface-balanced"])
        print(f"[LocalGenerator] Loading {tier} from {model_path} ...")

        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        self._processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        self._model = AutoModelForVision2Seq.from_pretrained(
            model_path,
            quantization_config=bnb,
            device_map="auto",
            trust_remote_code=True,
        )
        self._model.eval()
        self._loaded_tier = tier
        print(f"[LocalGenerator] {tier} ready.")

    async def generate(
        self,
        image_paths: list[str],
        prompt: str,
        source_url: str,
        source_html: str,
        tech_stack: str,
        model_tier: str,
    ) -> dict:
        import asyncio, torch
        from PIL import Image as PILImage

        self._load(model_tier)

        stack_hint = STACK_INSTRUCTIONS.get(tech_stack, STACK_INSTRUCTIONS["html-tailwind"])
        user_text = stack_hint
        if source_url:
            html = await _fetch_html(source_url)
            user_text += f"\n\nReference HTML:\n{html[:30_000]}"
        if source_html:
            user_text += f"\n\nHTML source:\n{source_html[:30_000]}"
        if prompt:
            user_text += f"\n\nInstructions: {prompt}"
        user_text += "\n\nOutput the complete code only."

        images = [PILImage.open(p).convert("RGB") for p in image_paths if Path(p).exists()]

        content = []
        for img in images:
            content.append({"type": "image", "image": img})
        content.append({"type": "text", "text": user_text})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": content},
        ]

        text = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._processor(
            text=[text],
            images=images if images else None,
            return_tensors="pt",
        ).to("cuda" if torch.cuda.is_available() else "cpu")

        def _run():
            with torch.no_grad():
                out = self._model.generate(
                    **inputs,
                    max_new_tokens=4096,
                    temperature=0.1,
                    do_sample=False,
                )
            return self._processor.decode(
                out[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

        code = await asyncio.get_event_loop().run_in_executor(None, _run)
        code = _strip_fences(code)
        return {"code": code, "tech_stack": tech_stack, "model": model_tier, "tier": model_tier}


# ── Unified interface ─────────────────────────────────────────────────────────

class UICodeGenerator:
    """
    Single entry point used by main.py.
    Automatically selects Groq or local backend based on MODEL_BACKEND env var.
    """

    def __init__(self):
        if MODEL_BACKEND == "local":
            self._backend = LocalGenerator()
        else:
            self._backend = GroqGenerator()
        print(f"[UICodeGenerator] Backend: {MODEL_BACKEND} | Model: {self._backend.model_name}")

    @property
    def model_name(self) -> str:
        return self._backend.model_name

    async def generate(
        self,
        image_paths: list[str],
        prompt: str = "",
        source_url: str = "",
        source_html: str = "",
        tech_stack: str = "html-tailwind",
        model_tier: str = "ink2interface-balanced",
    ) -> dict:
        return await self._backend.generate(
            image_paths=image_paths,
            prompt=prompt,
            source_url=source_url,
            source_html=source_html,
            tech_stack=tech_stack,
            model_tier=model_tier,
        )
