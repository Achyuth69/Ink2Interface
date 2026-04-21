"""
Step 3 — Build a HuggingFace Dataset from rendered pairs.

Combines:
  - Common Crawl rendered pairs  (data/pairs/)
  - WebSight synthetic pairs     (streamed from HuggingFace)
  - Your custom pairs            (data/pairs/ .png + .html added manually)

Saves a local HuggingFace Dataset to data/dataset/ ready for training.

Usage:
  python build_dataset.py --pairs ../data/pairs --websight 30000 --output ../data/dataset
"""

import argparse
import io
import json
from pathlib import Path

from datasets import Dataset, DatasetDict, concatenate_datasets, load_dataset
from PIL import Image


def load_pairs_from_dir(pairs_dir: Path) -> list[dict]:
    """Load all .png + .html pairs from a directory."""
    pairs = []
    for img_path in sorted(pairs_dir.glob("*.png")) + sorted(pairs_dir.glob("*.jpg")):
        html_path = img_path.with_suffix(".html")
        if not html_path.exists():
            continue
        try:
            img  = Image.open(img_path).convert("RGB")
            html = html_path.read_text(encoding="utf-8", errors="replace")
            if len(html) < 500:
                continue
            pairs.append({"image": img, "html": html, "source": "crawl"})
        except Exception:
            pass
    print(f"  Loaded {len(pairs)} pairs from {pairs_dir}")
    return pairs


def load_websight_pairs(num_samples: int) -> list[dict]:
    """Load screenshot/HTML pairs from WebSight."""
    if num_samples <= 0:
        return []
    print(f"  Loading {num_samples} WebSight pairs...")
    ds = load_dataset(
        "HuggingFaceM4/WebSight",
        split=f"train[:{num_samples}]",
        trust_remote_code=True,
    )
    pairs = []
    for ex in ds:
        img = ex["image"]
        if isinstance(img, bytes):
            img = Image.open(io.BytesIO(img)).convert("RGB")
        if not isinstance(img, Image.Image):
            continue
        pairs.append({"image": img, "html": ex["text"], "source": "websight"})
    print(f"  Loaded {len(pairs)} WebSight pairs.")
    return pairs


def build(pairs_dir: Path, websight_samples: int, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all sources
    crawl_pairs   = load_pairs_from_dir(pairs_dir)
    websight_pairs = load_websight_pairs(websight_samples)

    all_pairs = crawl_pairs + websight_pairs

    if not all_pairs:
        print("No pairs found! Run crawl_extract.py and render_screenshots.py first.")
        return

    print(f"\nTotal pairs: {len(all_pairs)}")
    print(f"  Common Crawl: {len(crawl_pairs)}")
    print(f"  WebSight:     {len(websight_pairs)}")

    # Shuffle and split
    import random
    random.seed(42)
    random.shuffle(all_pairs)

    split = max(1, int(len(all_pairs) * 0.02))
    train_pairs = all_pairs[split:]
    eval_pairs  = all_pairs[:split]

    print(f"\nSplit: {len(train_pairs)} train / {len(eval_pairs)} eval")

    # Save as HuggingFace Dataset
    def to_hf(pairs):
        return Dataset.from_list([
            {"image": p["image"], "html": p["html"], "source": p["source"]}
            for p in pairs
        ])

    dataset = DatasetDict({
        "train": to_hf(train_pairs),
        "eval":  to_hf(eval_pairs),
    })

    dataset.save_to_disk(str(output_dir))
    print(f"\nDataset saved to {output_dir}")
    print(f"  Use in train.py with: --dataset {output_dir}")

    # Save stats
    stats = {
        "total": len(all_pairs),
        "train": len(train_pairs),
        "eval":  len(eval_pairs),
        "sources": {
            "crawl":    len(crawl_pairs),
            "websight": len(websight_pairs),
        }
    }
    (output_dir / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs",    default="../data/pairs",   help="Directory with PNG+HTML pairs")
    parser.add_argument("--websight", type=int, default=30_000,  help="WebSight samples to include (0=none)")
    parser.add_argument("--output",   default="../data/dataset", help="Output dataset directory")
    args = parser.parse_args()
    build(Path(args.pairs), args.websight, Path(args.output))
