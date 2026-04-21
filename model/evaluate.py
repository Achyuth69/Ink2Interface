"""
Evaluate a fine-tuned Ink2Interface model.

Metrics:
  - BLEU (char-level) — code similarity
  - Tag recall        — structural HTML match
  - Style coverage    — does output contain a <style> block?

Usage:
  python evaluate.py ./checkpoints/ink2interface-fast/final
  python evaluate.py ./checkpoints/ink2interface-fast/final --samples 100
"""

import sys
import io
import argparse
import torch
from pathlib import Path
from html.parser import HTMLParser

from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from datasets import load_dataset
from PIL import Image
from sacrebleu.metrics import BLEU


def extract_tags(html: str) -> set:
    tags = set()
    class _P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            tags.add(tag.lower())
    try:
        _P().feed(html)
    except Exception:
        pass
    return tags


def evaluate(model_path: str, num_samples: int = 200):
    print(f"Loading model from {model_path}...")
    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()

    print(f"Loading {num_samples} eval samples from WebSight...")
    dataset = load_dataset(
        "HuggingFaceM4/WebSight",
        split=f"train[50000:50000+{num_samples}]",
        trust_remote_code=True,
    )

    bleu_metric = BLEU(tokenize="char")
    hypotheses, references = [], []
    tag_scores, style_hits = [], []

    for i, example in enumerate(dataset):
        image = example["image"]
        if isinstance(image, bytes):
            image = Image.open(io.BytesIO(image)).convert("RGB")
        ref_html = example["text"]

        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "Generate the complete HTML for this screenshot."},
            ],
        }]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[image], return_tensors="pt").to("cuda")

        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=3072, temperature=0.1, do_sample=False)
        pred = processor.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        hypotheses.append(pred)
        references.append(ref_html)

        ref_tags = extract_tags(ref_html)
        pred_tags = extract_tags(pred)
        if ref_tags:
            tag_scores.append(len(ref_tags & pred_tags) / len(ref_tags))

        style_hits.append(1 if "<style" in pred.lower() else 0)

        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{num_samples}] tag_recall={sum(tag_scores)/len(tag_scores)*100:.1f}%  style={sum(style_hits)/len(style_hits)*100:.0f}%")

    bleu_score = bleu_metric.corpus_score(hypotheses, [references])
    avg_tag    = sum(tag_scores) / len(tag_scores) if tag_scores else 0
    avg_style  = sum(style_hits) / len(style_hits) if style_hits else 0

    print(f"\n{'='*40}")
    print(f"  BLEU (char):    {bleu_score.score:.2f}")
    print(f"  Tag recall:     {avg_tag*100:.1f}%")
    print(f"  Style coverage: {avg_style*100:.0f}%")
    print(f"{'='*40}")
    return {"bleu": bleu_score.score, "tag_recall": avg_tag, "style_coverage": avg_style}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path", nargs="?", default="./checkpoints/ink2interface-fast/final")
    parser.add_argument("--samples", type=int, default=200)
    args = parser.parse_args()
    evaluate(args.model_path, args.samples)
