"""
Ink2Interface — Full Training Pipeline
=======================================
Fine-tunes Qwen2-VL on screenshot→HTML pairs using QLoRA.

Tiers:
  fast     → Qwen2-VL-2B  (~6GB  VRAM)
  balanced → Qwen2-VL-7B  (~16GB VRAM)
  pro      → Qwen2-VL-7B  large LoRA (~24GB VRAM)

Data sources (auto-combined):
  1. Common Crawl rendered pairs  — data/pairs/*.png + *.html
  2. WebSight synthetic pairs     — HuggingFaceM4/WebSight (streamed)
  3. Pre-built dataset            — data/dataset/ (from build_dataset.py)

Usage:
  # Quick start — WebSight only, no GPU-heavy rendering needed
  python train.py --tier fast --websight 20000

  # Full pipeline — Common Crawl + WebSight
  python train.py --tier balanced --pairs data/pairs --websight 30000

  # Use pre-built dataset
  python train.py --tier balanced --dataset data/dataset

  # Resume
  python train.py --tier balanced --resume ./checkpoints/ink2interface-balanced/checkpoint-400
"""

import argparse
import io
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path

import torch
from datasets import Dataset, DatasetDict, load_from_disk, load_dataset
from PIL import Image
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoProcessor,
    BitsAndBytesConfig,
    Qwen2VLForConditionalGeneration,
    TrainingArguments,
)
from trl import SFTTrainer


# ── Tier configs ──────────────────────────────────────────────────────────────

@dataclass
class TierConfig:
    name: str
    base_model: str
    lora_r: int
    lora_alpha: int
    batch_size: int
    grad_accum: int
    max_seq_len: int
    num_epochs: int
    lr: float
    description: str


TIERS = {
    "fast": TierConfig(
        name="ink2interface-fast",
        base_model="Qwen/Qwen2-VL-2B-Instruct",
        lora_r=16, lora_alpha=32,
        batch_size=2, grad_accum=8,
        max_seq_len=2048, num_epochs=3, lr=2e-4,
        description="~6GB VRAM — RTX 3060/4060",
    ),
    "balanced": TierConfig(
        name="ink2interface-balanced",
        base_model="Qwen/Qwen2-VL-7B-Instruct",
        lora_r=32, lora_alpha=64,
        batch_size=1, grad_accum=16,
        max_seq_len=3072, num_epochs=3, lr=1e-4,
        description="~16GB VRAM — RTX 3090/4090/A100",
    ),
    "pro": TierConfig(
        name="ink2interface-pro",
        base_model="Qwen/Qwen2-VL-7B-Instruct",
        lora_r=64, lora_alpha=128,
        batch_size=1, grad_accum=32,
        max_seq_len=4096, num_epochs=5, lr=5e-5,
        description="~24GB VRAM — A100/H100",
    ),
}

SYSTEM_PROMPT = (
    "You are an expert frontend developer. "
    "Given a screenshot of a webpage, output a complete, self-contained HTML file "
    "that looks identical to the screenshot. "
    "Put ALL CSS in a <style> block in <head>. "
    "Output ONLY the HTML — no markdown, no explanation."
)

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_pairs_from_dir(pairs_dir: Path) -> list[dict]:
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
            pairs.append({"image": img, "html": html})
        except Exception:
            pass
    print(f"  Loaded {len(pairs)} pairs from {pairs_dir}")
    return pairs


def load_websight(num_samples: int) -> list[dict]:
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
        pairs.append({"image": img, "html": ex["text"]})
    print(f"  Loaded {len(pairs)} WebSight pairs.")
    return pairs


def load_prebuilt_dataset(dataset_path: str) -> tuple[Dataset, Dataset]:
    print(f"  Loading pre-built dataset from {dataset_path}...")
    ds = load_from_disk(dataset_path)
    return ds["train"], ds["eval"]


def build_datasets(
    pairs_dir: str | None,
    websight_samples: int,
    dataset_path: str | None,
) -> tuple[Dataset, Dataset]:

    # Option A: pre-built dataset
    if dataset_path and Path(dataset_path).exists():
        return load_prebuilt_dataset(dataset_path)

    # Option B: build from sources
    print("\nLoading training data...")
    all_pairs = []

    if pairs_dir and Path(pairs_dir).exists():
        crawl = load_pairs_from_dir(Path(pairs_dir))
        # Repeat custom/crawl pairs 3x — they're higher quality
        all_pairs.extend(crawl * 3)

    websight = load_websight(websight_samples)
    all_pairs.extend(websight)

    if not all_pairs:
        raise ValueError(
            "No training data found!\n"
            "Run: python data_pipeline/crawl_extract.py\n"
            "Then: python data_pipeline/render_screenshots.py\n"
            "Or use --websight 20000 for WebSight-only training."
        )

    print(f"\nTotal pairs: {len(all_pairs)}")
    random.seed(42)
    random.shuffle(all_pairs)

    split = max(1, int(len(all_pairs) * 0.02))
    train_pairs = all_pairs[split:]
    eval_pairs  = all_pairs[:split]

    train_ds = Dataset.from_list(train_pairs)
    eval_ds  = Dataset.from_list(eval_pairs)
    print(f"Split: {len(train_pairs)} train / {len(eval_pairs)} eval\n")
    return train_ds, eval_ds


# ── Collator ──────────────────────────────────────────────────────────────────

class Ink2InterfaceCollator:
    def __init__(self, processor, max_seq_len: int):
        self.processor   = processor
        self.max_seq_len = max_seq_len

    def __call__(self, examples: list[dict]) -> dict:
        texts, images_list = [], []

        for ex in examples:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": ex["image"]},
                        {"type": "text",  "text": "Generate the complete HTML for this screenshot."},
                    ],
                },
                {"role": "assistant", "content": ex["html"]},
            ]
            text = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            texts.append(text)
            images_list.append([ex["image"]])

        batch = self.processor(
            text=texts,
            images=images_list,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_seq_len,
        )

        # Mask everything before the assistant response
        labels = batch["input_ids"].clone()
        asst_ids = self.processor.tokenizer.encode(
            "<|im_start|>assistant", add_special_tokens=False
        )
        for i, row in enumerate(labels):
            masked = False
            for j in range(len(row) - len(asst_ids)):
                if row[j: j + len(asst_ids)].tolist() == asst_ids:
                    labels[i, : j + len(asst_ids)] = -100
                    masked = True
                    break
            if not masked:
                labels[i] = torch.full_like(row, -100)

        batch["labels"] = labels
        return batch


# ── Model ─────────────────────────────────────────────────────────────────────

def build_model(cfg: TierConfig):
    print(f"Loading {cfg.base_model} with 4-bit QLoRA...")

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    processor = AutoProcessor.from_pretrained(
        cfg.base_model, trust_remote_code=True, max_pixels=1024 * 28 * 28
    )
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        cfg.base_model,
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model.config.use_cache = False

    lora_cfg = LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=0.05,
        target_modules=LORA_TARGETS,
        task_type=TaskType.CAUSAL_LM,
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()
    return processor, model


# ── Train ─────────────────────────────────────────────────────────────────────

def train(args):
    cfg = TIERS[args.tier]
    output_dir = f"./checkpoints/{cfg.name}"
    os.makedirs(output_dir, exist_ok=True)

    train_ds, eval_ds = build_datasets(args.pairs, args.websight, args.dataset)
    processor, model  = build_model(cfg)
    collator = Ink2InterfaceCollator(processor, cfg.max_seq_len)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=cfg.num_epochs,
        per_device_train_batch_size=cfg.batch_size,
        per_device_eval_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        learning_rate=cfg.lr,
        bf16=True,
        fp16=False,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        save_strategy="steps",
        save_steps=200,
        eval_strategy="steps",
        eval_steps=200,
        logging_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        dataloader_num_workers=2,
        remove_unused_columns=False,
        report_to="none",
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=collator,
    )

    print(f"\n{'='*55}")
    print(f"  Tier:    {cfg.name}")
    print(f"  Model:   {cfg.base_model}")
    print(f"  VRAM:    {cfg.description}")
    print(f"  Train:   {len(train_ds)} samples")
    print(f"  Eval:    {len(eval_ds)} samples")
    print(f"  Epochs:  {cfg.num_epochs}")
    print(f"  Output:  {output_dir}")
    print(f"{'='*55}\n")

    trainer.train(resume_from_checkpoint=args.resume)

    # Save final model
    final_path = os.path.join(output_dir, "final")
    print(f"\nSaving final model → {final_path}")
    trainer.model.save_pretrained(final_path)
    processor.save_pretrained(final_path)

    meta = {
        "tier": args.tier,
        "base_model": cfg.base_model,
        "lora_r": cfg.lora_r,
        "train_samples": len(train_ds),
    }
    with open(os.path.join(final_path, "ink2interface_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n✓ Done! Set in backend/.env:")
    print(f"  MODEL_BACKEND=local")
    env_key = f"INK2INTERFACE_{args.tier.upper()}_PATH"
    print(f"  {env_key}={os.path.abspath(final_path)}")


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Ink2Interface local model")
    parser.add_argument("--tier",    choices=["fast", "balanced", "pro"], default="fast")
    parser.add_argument("--pairs",   default="data/pairs",   help="Dir with PNG+HTML pairs")
    parser.add_argument("--websight",type=int, default=20_000, help="WebSight samples (0=skip)")
    parser.add_argument("--dataset", default=None,            help="Pre-built HF dataset dir")
    parser.add_argument("--resume",  default=None,            help="Checkpoint path to resume")
    args = parser.parse_args()
    train(args)
