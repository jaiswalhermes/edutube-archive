#!/usr/bin/env python3
"""Harvest EduTube.org's archived *listing* pages (one request -> ~10 videos).

The 2008-2021 EduTube ran on Drupal and exposed each subject as a paginated
table: thumbnail + title + teaser + duration + views/day + "EduTube-Index"
(their editorial quality score). That table is a far richer and cheaper corpus
than fetching 3,000 individual video pages, and it is what we rebuild the
catalogue from.

Output: data/listing.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "listing.jsonl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

CATEGORIES = [
    "agriculture", "animals-wildlife", "anthropology", "art", "biology", "chemistry",
    "computer-science", "development", "diy-how-to", "economics", "education", "environment",
    "film-media", "food-cooking", "geology-earth", "health", "history", "language",
    "math-statistics", "music", "physics", "politics", "psychology", "religion",
    "software", "space-astronomy", "sports-martial-arts", "technology",
]
YEAR_HINTS = ["2015", "2013", "2018", "2011", "2020"]

ROW_RX = re.compile(r'<tr class="(?:odd|even)[^"]*">(.*?)</tr>', re.S)
YT_RX = re.compile(r"(?:img|i)\.ytimg\.com/vi/([\w-]{11})|youtube\.com/vi/([\w-]{11})")
SLUG_RX = re.compile(r'href="/en/video/([^"]+)"')
TITLE_RX = re.compile(r'views-field-title[^>]*>\s*<a[^>]*>(.*?)</a>', re.S)
TEASER_RX = re.compile(r'views-field-teaser[^>]*>(.*?)</td>', re.S)
DUR_RX = re.compile(r'field-durationauto-value[^>]*>\s*([^<]*)', re.S)
VIEWSDAY_RX = re.compile(r'field-views-day-value[^>]*>\s*([^<]*)', re.S)
INDEX_RX = re.compile(r'field-edutube-index-value[^>]*>\s*([^<]*)', re.S)
PAGER_RX = re.compile(r'href="/en/category/[^"]*\?page=(\d+)"')


def fetch(url: str, timeout: int = 35) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def fetch_snapshot(path: str, years: list[str], settle: float = 0.35) -> tuple[str, str]:
    """Try year hints until a capture answers 200."""
    for y in years:
        url = f"https://web.archive.org/web/{y}id_/http://www.edutube.org{path}"
        st, body = fetch(url)
        if st == 200 and "<table" in body:
            return url, body
        if st == 0:  # connection level problem (archive throttling us) -> long back off
            time.sleep(8)
        time.sleep(settle)
    return "", ""


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
         .replace("&#039;", "'").replace("&#8217;", "\u2019").replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", s).strip()


def parse_rows(body: str, category: str, page: int, source: str) -> list[dict]:
    out = []
    for row in ROW_RX.findall(body):
        m = YT_RX.search(row)
        s = SLUG_RX.search(row)
        if not m or not s:
            continue
        yt = m.group(1) or m.group(2)
        t = TITLE_RX.search(row)
        te = TEASER_RX.search(row)
        d = DUR_RX.search(row)
        v = VIEWSDAY_RX.search(row)
        idx = INDEX_RX.search(row)
        dur = clean(d.group(1)) if d else ""
        out.append({
            "slug": s.group(1),
            "youtube_id": yt,
            "title": clean(t.group(1)) if t else "",
            "description": clean(te.group(1)) if te else "",
            "duration": dur if re.match(r"^\d{1,2}:\d{2}", dur) else "",
            "views_day": int(re.sub(r"\D", "", v.group(1))) if v and re.sub(r"\D", "", v.group(1)) else None,
            "edutube_index": float(idx.group(1)) if idx and re.match(r"^[\d.]+$", idx.group(1).strip()) else None,
            "category_legacy": category,
            "page": page,
            "source_snapshot": source,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=80, help="safety cap per category")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between archive requests")
    ap.add_argument("--categories", default="", help="comma separated subset, for testing")
    args = ap.parse_args()

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] or CATEGORIES

    # resume: keep whatever we already have on disk
    seen: dict[str, dict] = {}
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                seen[r["slug"]] = r
        print(f"resuming with {len(seen)} rows", file=sys.stderr)

    started = time.time()
    with open(OUT, "a", encoding="utf-8") as fh:
        for ci, cat in enumerate(cats):
            path0 = f"/en/category/{cat}"
            src, body = fetch_snapshot(path0, YEAR_HINTS)
            if not body:
                print(f"[{ci+1}/{len(cats)}] {cat}: no capture", file=sys.stderr, flush=True)
                time.sleep(args.delay)
                continue
            year = src.split("/web/")[1].split("id_")[0] if "/web/" in src else YEAR_HINTS[0]
            pages = [int(p) for p in PAGER_RX.findall(body)]
            last = min(max(pages) if pages else 0, args.max_pages)
            rows = parse_rows(body, cat, 0, src)
            new0 = 0
            for r in rows:
                if r["slug"] not in seen:
                    seen[r["slug"]] = r
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    new0 += 1
            fh.flush()
            print(f"[{ci+1}/{len(cats)}] {cat}: +{new0} (page0, {last+1} pages)", file=sys.stderr, flush=True)

            for p in range(1, last + 1):
                time.sleep(args.delay)
                path = f"/en/category/{cat}?page={p}"
                src, body = fetch_snapshot(path, [year] + [y for y in (YEAR_HINTS[0], YEAR_HINTS[2]) if y != year])
                if not body:
                    continue
                rows = parse_rows(body, cat, p, src)
                new = 0
                for r in rows:
                    if r["slug"] not in seen:
                        seen[r["slug"]] = r
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                        new += 1
                fh.flush()
                if new:
                    print(f"    {cat} p{p}: +{new} (total {len(seen)})", file=sys.stderr, flush=True)
                if new == 0:
                    break  # past the end of the archived range
    print(f"done: {len(seen)} unique videos in {(time.time()-started)/60:.1f}m -> {OUT}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
