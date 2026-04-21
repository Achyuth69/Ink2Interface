"""
Step 1 — Extract HTML pages from Common Crawl WARC files.

Common Crawl is free, petabyte-scale web crawl data.
We filter for pages that have real CSS (not just bare HTML).

Usage:
  python crawl_extract.py --output ../data/raw --limit 50000
  python crawl_extract.py --output ../data/raw --limit 50000 --workers 8
"""

import argparse
import gzip
import io
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# ── Common Crawl index API ────────────────────────────────────────────────────
# Latest crawl index — update this to the newest at https://index.commoncrawl.org/
CC_INDEX = "CC-MAIN-2024-51"
CC_INDEX_URL = f"https://index.commoncrawl.org/{CC_INDEX}-index"
CC_DATA_URL  = "https://data.commoncrawl.org/"

# Pages we want — UI-heavy sites likely to have good CSS
TARGET_DOMAINS = [
    # Login / auth pages
    "*/login*", "*/signin*", "*/signup*", "*/register*",
    # Dashboards
    "*/dashboard*", "*/admin*", "*/app*",
    # Landing pages
    "*/index.html", "*/home*",
    # E-commerce
    "*/product*", "*/shop*", "*/cart*",
    # SaaS
    "*/pricing*", "*/features*",
]

MIN_CSS_BYTES  = 2_000    # skip pages with almost no CSS
MAX_HTML_BYTES = 500_000  # skip huge pages
MIN_HTML_BYTES = 5_000    # skip tiny/empty pages


def fetch_cc_index(url_pattern: str, limit: int = 1000) -> list[dict]:
    """Query the CC index API for pages matching a URL pattern."""
    results = []
    params = {
        "url": url_pattern,
        "output": "json",
        "limit": min(limit, 1000),
        "fl": "url,filename,offset,length,status,mime",
    }
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(CC_INDEX_URL, params=params)
            if r.status_code != 200:
                return []
            for line in r.text.strip().split("\n"):
                if line.strip():
                    try:
                        results.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        print(f"  Index query failed for {url_pattern}: {e}")
    return results


def fetch_warc_record(record: dict) -> str | None:
    """Fetch a single HTML page from a WARC file using byte-range request."""
    try:
        warc_url = CC_DATA_URL + record["filename"]
        offset = int(record["offset"])
        length = int(record["length"])
        headers = {"Range": f"bytes={offset}-{offset + length - 1}"}

        with httpx.Client(timeout=30) as client:
            r = client.get(warc_url, headers=headers)
            if r.status_code not in (200, 206):
                return None

        # Decompress gzip
        raw = gzip.decompress(r.content)
        text = raw.decode("utf-8", errors="replace")

        # Extract HTTP response body (skip WARC + HTTP headers)
        parts = text.split("\r\n\r\n", 2)
        if len(parts) < 3:
            return None
        html = parts[2]

        if len(html) < MIN_HTML_BYTES or len(html) > MAX_HTML_BYTES:
            return None
        return html

    except Exception:
        return None


def inline_css(html: str, base_url: str) -> str:
    """Fetch and inline external CSS stylesheets into the HTML."""
    soup = BeautifulSoup(html, "html.parser")
    inlined = ""

    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href", "")
        if not href:
            continue
        try:
            css_url = urljoin(base_url, href)
            if not css_url.startswith("http"):
                continue
            with httpx.Client(timeout=10) as client:
                r = client.get(css_url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    inlined += f"\n/* {href} */\n{r.text[:30_000]}\n"
        except Exception:
            pass

    if inlined:
        # Inject as <style> block before </head>
        html = re.sub(
            r"</head>",
            f"<style>{inlined}</style>\n</head>",
            html, count=1, flags=re.IGNORECASE
        )
    return html


def has_enough_css(html: str) -> bool:
    """Check if the page has meaningful CSS."""
    # Count CSS from <style> blocks
    style_content = " ".join(re.findall(r"<style[^>]*>([\s\S]*?)</style>", html, re.IGNORECASE))
    # Count inline style attributes
    inline_styles = re.findall(r'style=["\'][^"\']+["\']', html)
    total_css = len(style_content) + sum(len(s) for s in inline_styles)
    return total_css >= MIN_CSS_BYTES


def clean_html(html: str, url: str) -> str | None:
    """Clean and validate HTML for training."""
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove scripts (we don't need JS for visual reconstruction)
        for tag in soup.find_all("script"):
            tag.decompose()

        # Remove tracking pixels, ads
        for tag in soup.find_all(attrs={"class": re.compile(r"ad|tracking|analytics|cookie", re.I)}):
            tag.decompose()

        cleaned = str(soup)
        if len(cleaned) < MIN_HTML_BYTES:
            return None
        return cleaned
    except Exception:
        return None


def extract_pages(output_dir: Path, limit: int, workers: int):
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    seen_urls = set()

    # Load already-saved URLs to avoid duplicates on resume
    meta_file = output_dir / "meta.jsonl"
    if meta_file.exists():
        for line in meta_file.read_text().strip().split("\n"):
            if line:
                try:
                    seen_urls.add(json.loads(line)["url"])
                except Exception:
                    pass
        saved = len(seen_urls)
        print(f"Resuming — {saved} pages already saved.")

    meta_fh = open(meta_file, "a", encoding="utf-8")

    print(f"Querying Common Crawl index ({CC_INDEX})...")
    all_records = []
    per_pattern = max(100, limit // len(TARGET_DOMAINS))
    for pattern in TARGET_DOMAINS:
        records = fetch_cc_index(pattern, limit=per_pattern)
        all_records.extend(records)
        print(f"  {pattern}: {len(records)} records")
        time.sleep(0.5)  # be polite to CC API

    print(f"\nTotal records to process: {len(all_records)}")

    def process(record: dict) -> dict | None:
        url = record.get("url", "")
        if url in seen_urls:
            return None
        if record.get("status") not in ("200", 200):
            return None
        if record.get("mime", "") not in ("text/html", "application/xhtml+xml", ""):
            return None

        html = fetch_warc_record(record)
        if not html:
            return None

        # Inline external CSS
        html = inline_css(html, url)

        if not has_enough_css(html):
            return None

        html = clean_html(html, url)
        if not html:
            return None

        return {"url": url, "html": html}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process, r): r for r in all_records}
        for future in as_completed(futures):
            if saved >= limit:
                break
            result = future.result()
            if not result:
                continue

            url = result["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)

            idx = str(saved + 1).zfill(6)
            html_path = output_dir / f"{idx}.html"
            html_path.write_text(result["html"], encoding="utf-8")

            meta_fh.write(json.dumps({"idx": idx, "url": url}) + "\n")
            meta_fh.flush()

            saved += 1
            if saved % 100 == 0:
                print(f"  Saved {saved}/{limit} pages...")

    meta_fh.close()
    print(f"\nDone. {saved} pages saved to {output_dir}")
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",  default="../data/raw",  help="Output directory")
    parser.add_argument("--limit",   type=int, default=50_000, help="Max pages to extract")
    parser.add_argument("--workers", type=int, default=8,      help="Parallel download workers")
    args = parser.parse_args()
    extract_pages(Path(args.output), args.limit, args.workers)
