"""
Demo Dataset Builder — loads URLs from websites.csv, renders screenshots + inlines CSS.

Usage:
  pip install playwright httpx beautifulsoup4
  playwright install chromium

  # All URLs
  python demo_dataset.py

  # High priority only (faster demo)
  python demo_dataset.py --priority high

  # Specific category
  python demo_dataset.py --category login

  # Limit count


  # Add a new URL to the CSV then re-run
  echo "https://mysite.com,custom,high" >> websites.csv
"""

import asyncio
import csv
import re
import argparse
from pathlib import Path
from urllib.parse import urljoin

import httpx
from playwright.async_api import async_playwright

CSV_FILE = Path(__file__).parent / "websites.csv"
OUTPUT   = Path(__file__).parent / "data" / "pairs"
OUTPUT.mkdir(parents=True, exist_ok=True)

PARALLEL = 4   # browser pages running at once
TIMEOUT  = 20_000


def load_urls(priority: str | None = None, category: str | None = None, limit: int = 0) -> list[dict]:
    """Load URLs from websites.csv with optional filters."""
    rows = []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if priority and row["priority"] != priority:
                continue
            if category and row["category"] != category:
                continue
            rows.append(row)

    # Sort: high first, then medium, then low
    order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda r: order.get(r["priority"], 9))

    if limit > 0:
        rows = rows[:limit]

    print(f"Loaded {len(rows)} URLs from {CSV_FILE}")
    if priority:
        print(f"  Filter: priority={priority}")
    if category:
        print(f"  Filter: category={category}")
    return rows


async def fetch_and_inline_css(url: str) -> str | None:
    """Fetch HTML and inline all linked CSS stylesheets."""
    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            html = r.text

            # Find stylesheet links
            css_links = re.findall(
                r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']',
                html, re.IGNORECASE
            )
            css_links += re.findall(
                r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']stylesheet["\']',
                html, re.IGNORECASE
            )

            inlined = ""
            for href in css_links[:6]:
                try:
                    css_url = urljoin(url, href)
                    if not css_url.startswith("http"):
                        continue
                    cr = await client.get(css_url, timeout=8)
                    if cr.status_code == 200:
                        inlined += f"\n/* {href} */\n{cr.text[:25_000]}\n"
                except Exception:
                    pass

            # Remove scripts — not needed for visual clone training
            html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
            html = re.sub(r"<noscript[\s\S]*?</noscript>", "", html, flags=re.IGNORECASE)

            # Inject inlined CSS before </head>
            if inlined:
                style_block = f"<style>\n{inlined[:40_000]}\n</style>"
                if "</head>" in html:
                    html = html.replace("</head>", f"{style_block}\n</head>", 1)
                else:
                    html = style_block + html

            return html
    except Exception as e:
        print(f"    fetch failed: {e}")
        return None


async def screenshot_url(page, url: str, out_png: Path) -> bool:
    """Render URL in headless browser and save screenshot."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(out_png), full_page=False, type="png")
        return True
    except Exception as e:
        print(f"    screenshot failed: {e}")
        return False


async def process_url(page, row: dict, idx: str) -> bool:
    url      = row["url"]
    category = row["category"]
    priority = row["priority"]
    png_path  = OUTPUT / f"{idx}.png"
    html_path = OUTPUT / f"{idx}.html"

    if png_path.exists() and html_path.exists():
        print(f"  [{idx}] skip (done): {url}")
        return True

    print(f"  [{idx}] [{category}/{priority}] {url}")

    ok = await screenshot_url(page, url, png_path)
    if not ok:
        return False

    html = await fetch_and_inline_css(url)
    if not html:
        png_path.unlink(missing_ok=True)
        return False

    # Save metadata comment at top of HTML for reference
    meta = f"<!-- source: {url} | category: {category} | priority: {priority} -->\n"
    html_path.write_text(meta + html, encoding="utf-8")
    print(f"    ✓ saved pair {idx}")
    return True


async def main(args):
    rows = load_urls(
        priority=args.priority,
        category=args.category,
        limit=args.limit,
    )

    if not rows:
        print("No URLs matched your filters. Check websites.csv")
        return

    print(f"\nStarting — {len(rows)} pages, {PARALLEL} parallel browsers\n")
    saved = 0
    failed = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )

        pages = [await browser.new_page() for _ in range(PARALLEL)]
        for p in pages:
            await p.set_viewport_size({"width": 1280, "height": 800})

        # Process in chunks of PARALLEL
        for chunk_start in range(0, len(rows), PARALLEL):
            chunk = rows[chunk_start: chunk_start + PARALLEL]
            tasks = []
            for j, row in enumerate(chunk):
                idx = str(chunk_start + j + 1).zfill(4)
                tasks.append(process_url(pages[j], row, idx))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if r is True:
                    saved += 1
                else:
                    failed += 1

            print(f"  Progress: {chunk_start + len(chunk)}/{len(rows)} | ✓{saved} ✗{failed}\n")

        for p in pages:
            await p.close()
        await browser.close()

    print(f"\n{'='*50}")
    print(f"  Done! {saved} pairs saved to {OUTPUT}")
    print(f"  Failed: {failed}")
    print(f"{'='*50}")
    print(f"\nNext step — train:")
    print(f"  python train.py --tier fast --pairs data/pairs --websight 0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build demo training dataset from websites.csv")
    parser.add_argument("--priority", choices=["high", "medium", "low"], default=None,
                        help="Filter by priority (default: all)")
    parser.add_argument("--category", default=None,
                        help="Filter by category e.g. login, ecommerce, social")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max URLs to process (0=all)")
    args = parser.parse_args()
    asyncio.run(main(args))
