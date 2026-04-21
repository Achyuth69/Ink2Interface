"""
Step 2 — Render HTML pages to screenshots using Playwright (headless Chromium).

Takes the raw HTML files from crawl_extract.py and renders them
at 1280x800 to produce training screenshot+HTML pairs.

Usage:
  pip install playwright && playwright install chromium
  python render_screenshots.py --input ../data/raw --output ../data/pairs
  python render_screenshots.py --input ../data/raw --output ../data/pairs --workers 4
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright, Page


VIEWPORT = {"width": 1280, "height": 800}
TIMEOUT  = 15_000   # 15s per page
SCROLL_PAUSE = 500  # ms — let lazy-loaded content appear


async def render_page(page: Page, html: str, out_png: Path) -> bool:
    """Render HTML string to a PNG screenshot."""
    try:
        await page.set_content(html, wait_until="networkidle", timeout=TIMEOUT)
        await page.wait_for_timeout(SCROLL_PAUSE)

        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
        await page.wait_for_timeout(300)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(200)

        await page.screenshot(path=str(out_png), full_page=False, type="png")
        return True
    except Exception as e:
        print(f"    Render failed: {e}")
        return False


def clean_for_training(html: str) -> str:
    """
    Strip elements that won't render offline:
    - External image src (replace with placeholder)
    - External font @imports (keep, they'll fail gracefully)
    - Remove <script> tags entirely
    """
    # Remove scripts
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    # Remove noscript
    html = re.sub(r"<noscript[\s\S]*?</noscript>", "", html, flags=re.IGNORECASE)
    # Remove iframes
    html = re.sub(r"<iframe[\s\S]*?</iframe>", "", html, flags=re.IGNORECASE)
    return html


async def render_batch(html_files: list[Path], output_dir: Path, batch_size: int = 4):
    output_dir.mkdir(parents=True, exist_ok=True)

    # Track already-rendered
    done = set(p.stem for p in output_dir.glob("*.png"))
    todo = [f for f in html_files if f.stem not in done]
    print(f"  {len(done)} already rendered, {len(todo)} remaining.")

    rendered = 0
    failed   = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",   # allow local file access
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        )

        # Process in batches
        for i in range(0, len(todo), batch_size):
            batch = todo[i: i + batch_size]
            pages = [await browser.new_page() for _ in batch]

            for page in pages:
                await page.set_viewport_size(VIEWPORT)
                # Block external requests that would slow rendering
                await page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in ("media", "websocket", "eventsource")
                    else route.continue_()
                )

            tasks = []
            for page, html_file in zip(pages, batch):
                html = html_file.read_text(encoding="utf-8", errors="replace")
                html = clean_for_training(html)
                out_png = output_dir / f"{html_file.stem}.png"
                tasks.append(render_page(page, html, out_png))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for page, html_file, result in zip(pages, batch, results):
                await page.close()
                if result is True:
                    rendered += 1
                    # Copy HTML to output dir too (cleaned version)
                    out_html = output_dir / f"{html_file.stem}.html"
                    if not out_html.exists():
                        html = html_file.read_text(encoding="utf-8", errors="replace")
                        out_html.write_text(clean_for_training(html), encoding="utf-8")
                else:
                    failed += 1

            total_done = len(done) + rendered
            print(f"  Progress: {total_done}/{len(done) + len(todo)} | rendered={rendered} failed={failed}")

        await browser.close()

    print(f"\nRendering complete: {rendered} new screenshots, {failed} failed.")
    return rendered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   default="../data/raw",   help="Directory with .html files")
    parser.add_argument("--output",  default="../data/pairs", help="Output directory for PNG+HTML pairs")
    parser.add_argument("--workers", type=int, default=4,     help="Parallel browser pages")
    parser.add_argument("--limit",   type=int, default=0,     help="Max pages to render (0=all)")
    args = parser.parse_args()

    input_dir  = Path(args.input)
    output_dir = Path(args.output)

    html_files = sorted(input_dir.glob("*.html"))
    if args.limit > 0:
        html_files = html_files[:args.limit]

    print(f"Found {len(html_files)} HTML files in {input_dir}")
    asyncio.run(render_batch(html_files, output_dir, batch_size=args.workers))


if __name__ == "__main__":
    main()
