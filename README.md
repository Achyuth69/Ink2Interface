# Ink2Interface

**Convert any website screenshot or URL into pixel-perfect HTML + CSS — instantly.**

Powered by Groq's ultra-fast AI vision models, Ink2Interface takes a screenshot or a URL and reconstructs the full frontend code in seconds. No design tools. No manual coding. Just paste and generate.

---

## What It Does

| Input | Output |
|---|---|
| Screenshot of any webpage | Self-contained HTML + CSS file |
| URL of any website | Reconstructed frontend code |
| Pasted HTML source | Styled, complete HTML page |
| Text prompt | Custom UI from description |

The generated output is a **single HTML file** with all CSS embedded — open it in any browser, no dependencies needed.

---

## Live Demo

- **Frontend:** https://ink-2-interface.onrender.com
- **Backend API:** https://ink2interface.onrender.com/docs

---

## Features

- **Screenshot → Code** — upload a PNG/JPG and get the full HTML+CSS back
- **URL → Code** — paste any URL, the backend fetches the HTML and inlines the CSS
- **HTML Source → Code** — paste raw HTML from DevTools, get a fully styled clone
- **Live streaming** — code streams token by token as it's generated
- **Live preview** — see the rendered result instantly in the browser
- **Download** — save as a single `.html` file or split `index.html` + `styles.css`
- **Copy to clipboard** — one click copy of the full generated code
- **1-hour TTL** — generated results auto-expire after 1 hour

---

## How to Use

1. Open the app at https://ink-2-interface.onrender.com
2. Choose your input mode — **Screenshot**, **HTML Source**, or **Reference URL**
3. Upload a screenshot or paste a URL / HTML
4. Optionally add extra instructions (e.g. "make it dark mode")
5. Click **Generate Code**
6. Switch between **Code** and **Preview** tabs
7. Download or copy the result

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Tailwind CSS + Vite |
| Backend | FastAPI + Python |
| AI Model | Groq API — `llama-4-scout-17b` (vision) |
| Deployment | Render (Docker) |
| Streaming | Server-Sent Events (SSE) |

---

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Add your GROQ_API_KEY to .env
python main.py
# Runs on http://localhost:8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

Get a free Groq API key at [console.groq.com](https://console.groq.com)

---

## Local Model Training (Optional)

Train your own local vision model on real website data using Common Crawl + WebSight.

```bash
cd model
pip install -r requirements.txt
playwright install chromium

# Build dataset from 150 real websites
python demo_dataset.py --priority high

# Train fast tier (~6GB VRAM)
python train.py --tier fast --pairs data/pairs --websight 0
```

See `model/README.md` for the full training pipeline.

---

## Project Structure

```
Ink2Interface/
├── backend/          # FastAPI backend + Groq AI integration
│   ├── main.py       # API endpoints
│   ├── generator.py  # Prompt builder + model backends
│   └── Dockerfile
├── frontend/         # React + Tailwind UI
│   ├── src/
│   │   ├── App.tsx   # Main UI
│   │   └── api.ts    # API client with SSE streaming
│   └── Dockerfile
└── model/            # Local model training pipeline
    ├── train.py      # QLoRA fine-tuning
    ├── demo_dataset.py  # Dataset builder (150 websites)
    ├── websites.csv  # 150 curated URLs
    └── data_pipeline/   # Common Crawl extraction + rendering
```

---

## Environment Variables

### Backend
| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq API key from console.groq.com |
| `MODEL_BACKEND` | `groq` (default) or `local` |
| `GROQ_MODEL` | Model ID (default: `meta-llama/llama-4-scout-17b-16e-instruct`) |

### Frontend (build time)
| Variable | Description |
|---|---|
| `VITE_API_URL` | Backend URL for production (e.g. `https://ink2interface.onrender.com`) |

---

## License

MIT
