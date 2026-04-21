# Ink2Interface

> **Turn any website screenshot or URL into pixel-perfect HTML + CSS — in seconds.**

---

## What is Ink2Interface?

Ink2Interface is an AI-powered frontend code generator. You give it a **screenshot** of any webpage, a **URL**, or raw **HTML source** — and it instantly produces a complete, self-contained HTML file that looks identical to the original.

No design tools. No manual coding. No dependencies. Just paste and generate.

It uses **Groq's ultra-fast AI vision models** (llama-4-scout) to understand the visual layout, colors, fonts, and structure of any webpage and reconstruct it as clean HTML + CSS code.

---

## The Problem It Solves

Frontend developers and designers often need to:
- Clone a UI for reference or prototyping
- Recreate a design from a screenshot
- Convert a live website into editable HTML
- Quickly scaffold a page that looks like an existing one

Normally this takes hours of manual work. Ink2Interface does it in **under 60 seconds**.

---

## How It Works

```
You provide                    Ink2Interface does              You get
─────────────                  ─────────────────               ────────
Screenshot  ──┐                                                
URL         ──┼──► AI Vision ──► HTML + CSS Generator ──►  Complete HTML file
HTML source ──┘    (Groq API)                               ready to open
```

1. **Input** — Upload a screenshot, paste a URL, or paste raw HTML from DevTools
2. **AI Processing** — Groq's vision model analyzes the visual design and structure
3. **Code Generation** — Streams complete HTML + CSS back in real time
4. **Preview** — See the rendered result instantly in the browser
5. **Download** — Save as a single `.html` file or split `index.html` + `styles.css`

---

## Live Demo

- **App:** https://ink-2-interface.onrender.com
- **API Docs:** https://ink2interface.onrender.com/docs

---

## Features

| Feature | Description |
|---|---|
| Screenshot → Code | Upload any PNG/JPG and get full HTML+CSS |
| URL → Code | Paste any URL, backend fetches and inlines the CSS |
| HTML Source → Code | Paste raw HTML from DevTools, get a styled clone |
| Live Streaming | Code streams token by token as it generates |
| Live Preview | See the rendered page instantly in the browser |
| Download | Single `.html` file or split `index.html` + `styles.css` |
| Mobile Responsive | Works on phone and desktop |
| 1-hour TTL | Results auto-expire after 1 hour |

---

## How to Use

### Option 1 — Screenshot
1. Take a screenshot of any webpage (press `PrtSc` or use Snipping Tool)
2. Open the app → click **Screenshot** tab
3. Upload the image
4. Click **Generate Code**
5. Switch to **Preview** tab to see the result
6. Click **Download** to save the HTML file

### Option 2 — URL
1. Open the app → paste the website URL in **Reference URL**
2. Click **Generate Code**
3. The backend fetches the page HTML + CSS automatically

### Option 3 — HTML Source (most accurate)
1. Open any website in Chrome
2. Press `F12` → Elements tab
3. Right-click the `<html>` tag → **Copy → Copy outerHTML**
4. Open the app → click **HTML Source** tab
5. Paste the HTML → click **Generate Code**

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Tailwind CSS + Vite |
| Backend | FastAPI + Python 3.11 |
| AI | Groq API — `llama-4-scout-17b-16e-instruct` (vision model) |
| Streaming | Server-Sent Events (SSE) — real-time token streaming |
| Deployment | Render.com (Docker containers) |
| Local Training | Qwen2-VL + QLoRA fine-tuning on screenshot→HTML pairs |

---

## Architecture

```
Browser
  │
  ├── React Frontend (Render)
  │     ├── Screenshot upload / URL input / HTML paste
  │     ├── Streams tokens via SSE
  │     └── Live preview in iframe (blob URL)
  │
  └── FastAPI Backend (Render)
        ├── Fetches URL HTML + inlines CSS
        ├── Builds multimodal prompt (image + HTML + instructions)
        ├── Calls Groq API (llama-4-scout vision model)
        └── Streams response back as SSE
```

---

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env → set GROQ_API_KEY=gsk_...
python main.py
# API running at http://localhost:8080
# Docs at http://localhost:8080/docs
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# App running at http://localhost:5173
```

---

## Deploy Your Own

### On Render (free tier)

**Backend:**
1. New Web Service → connect GitHub repo
2. Root Directory: `backend` | Runtime: Docker
3. Add env var: `GROQ_API_KEY=your_key_here`
4. Deploy → copy the URL

**Frontend:**
1. New Web Service → same repo
2. Root Directory: `frontend` | Runtime: Docker
3. Add env var: `VITE_API_URL=https://your-backend.onrender.com`
4. Deploy → done

---

## Local Model Training (Optional)

Train your own local vision model on real website data — no GPU cloud needed if you have an NVIDIA GPU.

```bash
cd model
pip install -r requirements.txt
playwright install chromium

# Step 1: Build dataset from 150 real websites
python demo_dataset.py

# Step 2: Train (needs ~6GB VRAM for fast tier)
python train.py --tier fast --pairs data/pairs --websight 0

# Step 3: Point backend to your model
# Edit backend/.env:
# MODEL_BACKEND=local
# INK2INTERFACE_FAST_PATH=./model/checkpoints/ink2interface-fast/final
```

See `model/README.md` for the full training pipeline including Common Crawl data extraction.

---

## Project Structure

```
Ink2Interface/
├── backend/
│   ├── main.py          # FastAPI endpoints (streaming + non-streaming)
│   ├── generator.py     # Prompt builder + Groq/local model backends
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx      # Main UI (sidebar + preview panel)
│   │   └── api.ts       # SSE streaming client
│   ├── Dockerfile
│   └── nginx.conf
│
└── model/
    ├── train.py             # QLoRA fine-tuning pipeline
    ├── demo_dataset.py      # Dataset builder (150 websites)
    ├── websites.csv         # 150 curated URLs with categories
    ├── evaluate.py          # BLEU + tag recall metrics
    └── data_pipeline/
        ├── crawl_extract.py      # Common Crawl HTML extraction
        ├── render_screenshots.py # Playwright screenshot renderer
        └── build_dataset.py      # HuggingFace dataset builder
```

---

## Environment Variables

### Backend (`backend/.env`)
| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Get free at console.groq.com |
| `MODEL_BACKEND` | `groq` | `groq` or `local` |
| `GROQ_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Vision model ID |

### Frontend (build-time)
| Variable | Description |
|---|---|
| `VITE_API_URL` | Backend URL for production deployment |

---

## License

MIT — free to use, modify, and deploy.
