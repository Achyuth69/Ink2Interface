"""
Add your own screenshot+HTML training pairs.

Usage:
  python add_custom_data.py --url https://example.com
  python add_custom_data.py --screenshot path/to/shot.png --html path/to/page.html
  python add_custom_data.py --scan-dir path/to/folder/with/screenshots

Each pair saved as:
  data/pairs/001.png  ← screenshot
  data/pairs/001.html ← matching HTML
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx
from PIL import Image

PAIRS_DIR = Path(__file__).parent / "data" / "pairs"
PAIRS_DIR.mkdir(parents=True, exist_ok=True)


def next_index() -> str:
    existing = sorted(PAIRS_DIR.glob("*.png")) + sorted(PAIRS_DIR.glob("*.jpg"))
    return str(len(existing) + 1).zfill(4)


async def fetch_page(url: str) -> tuple[str, str]:
    """Fetch HTML + inline CSS from a URL."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        html = r.text

        # Inline linked CSS
        from urllib.parse import urljoin
        css_links = re.findall(
            r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        inlined = ""
        for href in css_links[:8]:
            try:
                css_url = urljoin(url, href)
                cr = await client.get(css_url, headers=headers, timeout=10)
                if cr.status_code == 200:
                    inlined += f"\n/* {href} */\n{cr.text[:30_000]}\n"
            except Exception:
                pass

        if inlined:
            html = html.replace("</head>", f"<style>{inlined}</style>\n</head>", 1)

        return html, url


def add_from_url(url: str, screenshot_path: str | None):
    html, _ = asyncio.run(fetch_page(url))
    idx = next_index()

    html_out = PAIRS_DIR / f"{idx}.html"
    html_out.write_text(html, encoding="utf-8")
    print(f"Saved HTML → {html_out}")

    if screenshot_path:
        img = Image.open(screenshot_path).convert("RGB")
        img_out = PAIRS_DIR / f"{idx}.png"
        img.save(img_out)
        print(f"Saved screenshot → {img_out}")
        print(f"\nPair {idx} ready for training!")
    else:
        print(f"\nHTML saved as {idx}.html")
        print(f"Now take a screenshot of {url} and save it as:")
        print(f"  {PAIRS_DIR / f'{idx}.png'}")


def add_from_files(screenshot: str, html: str):
    idx = next_index()
    img = Image.open(screenshot).convert("RGB")
    img_out = PAIRS_DIR / f"{idx}.png"
    img.save(img_out)

    html_text = Path(html).read_text(encoding="utf-8")
    html_out = PAIRS_DIR / f"{idx}.html"
    html_out.write_text(html_text, encoding="utf-8")

    print(f"Pair {idx} saved:")
    print(f"  Screenshot → {img_out}")
    print(f"  HTML       → {html_out}")


def scan_dir(folder: str):
    """Scan a folder for .png/.jpg files and match with same-name .html files."""
    folder = Path(folder)
    added = 0
    for img_path in sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg")):
        html_path = img_path.with_suffix(".html")
        if html_path.exists():
            add_from_files(str(img_path), str(html_path))
            added += 1
    print(f"\nAdded {added} pairs from {folder}")


def list_pairs():
    pairs = sorted(PAIRS_DIR.glob("*.png")) + sorted(PAIRS_DIR.glob("*.jpg"))
    if not pairs:
        print("No custom pairs yet. Add some with --url or --screenshot + --html")
        return
    print(f"\n{len(pairs)} custom training pairs in {PAIRS_DIR}:")
    for p in pairs:
        html = p.with_suffix(".html")
        status = "✓" if html.exists() else "✗ (missing HTML)"
        print(f"  {p.name}  {status}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add custom training pairs")
    parser.add_argument("--url", help="Fetch HTML from this URL")
    parser.add_argument("--screenshot", help="Path to screenshot image")
    parser.add_argument("--html", help="Path to HTML file")
    parser.add_argument("--scan-dir", help="Scan folder for screenshot+HTML pairs")
    parser.add_argument("--list", action="store_true", help="List existing pairs")
    args = parser.parse_args()

    if args.list:
        list_pairs()
    elif args.scan_dir:
        scan_dir(args.scan_dir)
    elif args.url:
        add_from_url(args.url, args.screenshot)
    elif args.screenshot and args.html:
        add_from_files(args.screenshot, args.html)
    else:
        parser.print_help()
