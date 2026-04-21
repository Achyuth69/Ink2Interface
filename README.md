# Ink2Interface

Convert screenshots & URLs into pixel-perfect HTML+CSS using Groq AI.

## Deploy to Railway (2 services)

### Step 1 — Push to GitHub

```bash
cd Ink2Interface
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/ink2interface.git
git push -u origin main
```

### Step 2 — Deploy Backend on Railway

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select your repo → **Add service** → choose the repo
3. Set **Root Directory** to `backend`
4. Railway auto-detects the Dockerfile
5. Add these **Environment Variables**:

| Variable | Value |
|---|---|
| `GROQ_API_KEY` | `gsk_...` your key from console.groq.com |
| `MODEL_BACKEND` | `groq` |
| `GROQ_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` |

6. Click **Deploy** — copy the generated URL e.g. `https://ink2interface-backend.up.railway.app`

### Step 3 — Deploy Frontend on Railway

1. In the same Railway project → **New Service** → **GitHub repo** again
2. Set **Root Directory** to `frontend`
3. Add this **Environment Variable**:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://ink2interface-backend.up.railway.app` (your backend URL from Step 2) |

4. Click **Deploy** — your frontend URL is live!

### Step 4 — Done

Open the frontend Railway URL in your browser. That's it.

---

## Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY
python main.py         # runs on http://localhost:8080

# Frontend (new terminal)
cd frontend
npm install
npm run dev            # runs on http://localhost:5173
```

## Local Training (optional)

```bash
cd model
pip install -r requirements.txt
playwright install chromium

# Build dataset (150 real websites)
python demo_dataset.py --priority high

# Train fast tier (~6GB VRAM)
python train.py --tier fast --pairs data/pairs --websight 0
```
