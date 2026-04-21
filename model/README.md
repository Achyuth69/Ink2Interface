# Ink2Interface — Local Model Training

Fine-tunes Qwen2-VL on real screenshot→HTML pairs from **Common Crawl** + WebSight.

---

## GPU Requirements

| Tier     | Model         | VRAM   | GPU Example          |
|----------|---------------|--------|----------------------|
| fast     | Qwen2-VL-2B   | ~6GB   | RTX 3060 / 4060      |
| balanced | Qwen2-VL-7B   | ~16GB  | RTX 3090 / 4090      |
| pro      | Qwen2-VL-7B+  | ~24GB  | A100 / H100          |

---

## Full Pipeline

### Step 0 — Install

```bash
cd Ink2Interface/model
pip install -r requirements.txt
playwright install chromium
```

---

### Step 1 — Extract HTML from Common Crawl

Downloads real web pages (login pages, dashboards, landing pages, etc.)
from the Common Crawl WARC archive and inlines their CSS.

```bash
# Extract 50,000 pages (takes ~2-4 hours, uses ~5GB disk)
python data_pipeline/crawl_extract.py --output data/raw --limit 50000 --workers 8

# Faster test run
python data_pipeline/crawl_extract.py --output data/raw --limit 5000 --workers 4
```

Output: `data/raw/000001.html` ... `data/raw/050000.html`

---

### Step 2 — Render Screenshots

Renders each HTML file to a 1280×800 PNG using headless Chromium (Playwright).

```bash
# Render all extracted pages
python data_pipeline/render_screenshots.py --input data/raw --output data/pairs --workers 4

# Render only first 10,000
python data_pipeline/render_screenshots.py --input data/raw --output data/pairs --limit 10000
```

Output: `data/pairs/000001.png` + `data/pairs/000001.html` pairs

---

### Step 3 — Build Dataset (optional but faster training)

Combines Common Crawl pairs + WebSight into a single HuggingFace Dataset.

```bash
python data_pipeline/build_dataset.py \
  --pairs data/pairs \
  --websight 30000 \
  --output data/dataset
```

---

### Step 4 — Train

```bash
# Option A: WebSight only (no rendering needed, good starting point)
python train.py --tier fast --websight 20000

# Option B: Common Crawl pairs + WebSight
python train.py --tier fast --pairs data/pairs --websight 20000

# Option C: Pre-built dataset (fastest)
python train.py --tier fast --dataset data/dataset

# Balanced tier (better quality, needs 16GB VRAM)
python train.py --tier balanced --pairs data/pairs --websight 50000

# Resume from checkpoint
python train.py --tier balanced --resume ./checkpoints/ink2interface-balanced/checkpoint-400
```

Checkpoints → `checkpoints/<tier>/`
Final model → `checkpoints/<tier>/final/`

---

### Step 5 — Use the Model

Edit `backend/.env`:

```env
MODEL_BACKEND=local
INK2INTERFACE_FAST_PATH=E:/E/AI-DAYS_EXPO/Ink2Interface/model/checkpoints/ink2interface-fast/final
INK2INTERFACE_BALANCED_PATH=E:/E/AI-DAYS_EXPO/Ink2Interface/model/checkpoints/ink2interface-balanced/final
```

Restart backend:
```bash
python main.py
```

---

### Step 6 — Evaluate

```bash
python evaluate.py ./checkpoints/ink2interface-fast/final --samples 200
```

Metrics: BLEU score, HTML tag recall, style block coverage.

---

## Add Your Own Pages

```bash
# Add a specific page by URL
python add_custom_data.py --url https://ilearn.rocks/login/index.php --screenshot shot.png

# Add screenshot + HTML directly
python add_custom_data.py --screenshot login.png --html login.html

# Scan a folder
python add_custom_data.py --scan-dir ./my_pages/

# List all custom pairs
python add_custom_data.py --list
```

Custom pairs are stored in `data/pairs/` and automatically included in training.
They are weighted 3× higher than WebSight pairs since they're real-world examples.

---

## Data Sources

| Source        | Size    | Quality  | Notes                          |
|---------------|---------|----------|--------------------------------|
| Common Crawl  | 3B pages| High     | Real websites, real CSS        |
| WebSight      | 823K    | Medium   | Synthetic, good for diversity  |
| Custom pairs  | You add | Highest  | Your specific use case         |

---

## Tips

- Start with `--tier fast --websight 20000` to verify your setup works
- Add custom pairs of the exact sites you want to clone — huge quality boost
- Common Crawl extraction is resumable — re-run if interrupted
- Screenshot rendering is also resumable — already-rendered pages are skipped
- Training on 50K pairs takes ~4-6h on an RTX 3090
