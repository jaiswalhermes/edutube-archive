#!/usr/bin/env python3
"""Harvest the archived EduTube.org video catalogue (2008-2021) from the Wayback Machine.

EduTube was a hand-curated directory of free educational videos. In 2021 it pivoted
to games and the video catalogue disappeared. The pages survive in the Wayback
Machine, so we rebuild the corpus from there.

Output: data/raw.jsonl  (one record per archived video page)

Usage:
    python3 pipeline/harvest.py --limit 20          # smoke test
    python3 pipeline/harvest.py --workers 8         # full run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CDX_FILE = DATA / "cdx_videos.json"
RAW_FILE = DATA / "raw.jsonl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

YT_ID = re.compile(r"[\w-]{11}")
PLAYER_V = re.compile(r"youtube(?:-nocookie)?\.com/v/([\w-]{11})")
PLAYER_EMBED = re.compile(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})")
PLAYER_WATCH = re.compile(r"youtube\.com/watch\?v=([\w-]{11})")
THUMB = re.compile(r"(?:img\.youtube\.com|i\.ytimg\.com)/vi/([\w-]{11})")


def fetch(url: str, timeout: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def strip_tags(s: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (
        s.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
        .replace("&apos;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&#8217;", "\u2019")
        .replace("&#8216;", "\u2018")
        .replace("&#8220;", "\u201c")
        .replace("&#8221;", "\u201d")
        .replace("&#8211;", "\u2013")
        .replace("&#8212;", "\u2014")
    )
    return re.sub(r"\s+", " ", s).strip()


def parse_page(html_text: str, url: str, slug: str) -> dict | None:
    if not html_text or "Wayback Machine" in html_text[:400] and "not archived" in html_text:
        return None

    # --- youtube id: prefer the player markup, then the fallback thumbnail
    yt = None
    for rx in (PLAYER_V, PLAYER_EMBED, PLAYER_WATCH, THUMB):
        m = rx.search(html_text)
        if m:
            yt = m.group(1)
            break
    if not yt:
        return None

    # --- title: <title> tag is "Laminar Flow | EduTube Educational Videos"
    title = ""
    m = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    if m:
        title = strip_tags(m.group(1))
        title = re.split(r"\s*\|\s*EduTube", title)[0].strip()
    if not title:
        return None

    # --- description: meta description (clean, no site chrome)
    desc = ""
    m = re.search(r'<meta\s+name="description"\s+content="(.*?)"', html_text, re.S | re.I)
    if m:
        desc = strip_tags(m.group(1))
    if not desc:
        m = re.search(r"<meta\s+property=\"og:description\"\s+content=\"(.*?)\"", html_text, re.S | re.I)
        if m:
            desc = strip_tags(m.group(1))

    # --- breadcrumb: Home > Category > Chemistry > Laminar Flow  (first crumb after Category)
    cat = ""
    m = re.search(r"<h1[^>]*class=\"[^\"]*title[^\"]*\"[^>]*>(.*?)</h1>", html_text, re.S | re.I)
    body = html_text
    crumb = re.search(r"Category</a>\s*›\s*<a[^>]*>([^<]+)</a>", body)
    if crumb:
        cat = strip_tags(crumb.group(1))
    else:
        crumb = re.search(r"/category/([a-z0-9\-]+)", body)
        if crumb:
            cat = crumb.group(1).replace("-", " ").title()

    # --- the metadata block: "Category: ... Video type: ... Level: ..."
    video_type = ""
    level = ""
    m = re.search(r"Video type:\s*(?:<[^>]+>\s*)*([A-Za-z /&-]{2,40})", body)
    if m:
        video_type = strip_tags(m.group(1)).strip(" .|")
    m = re.search(r"Level:\s*(?:<[^>]+>\s*)*([A-Za-z /&'-]{2,60})", body)
    if m:
        level = strip_tags(m.group(1)).strip(" .|")

    # --- views + date
    views = None
    m = re.search(r"Total views:\s*(?:<[^>]+>\s*)*([\d,]+)", body)
    if m:
        try:
            views = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    published = None
    m = re.search(r"(\w{3}), (\d{2})/(\d{2})/(\d{4})", body)
    if m:
        try:
            mon, d, mo, y = m.groups()
            published = f"{y}-{mo}-{d}"
        except Exception:
            pass

    # --- main description body: the first <p> under the player
    long_desc = ""
    m = re.search(r"</object>.*?</div>.*?<p>(.*?)</p>", body, re.S | re.I)
    if m:
        long_desc = strip_tags(m.group(1))
    if not long_desc:
        m = re.search(r'<div class="field field-type-text field-field-description">.*?<div class="field-items">.*?<div class="field-item">(.*?)</div>', body, re.S | re.I)
        if m:
            long_desc = strip_tags(m.group(1))

    # --- related videos on the page = extra ids (we ignore, but count for signal)
    related = list(dict.fromkeys(PLAYER_WATCH.findall(body) + THUMB.findall(body)))
    related = [r for r in related if r != yt][:12]

    return {
        "slug": slug,
        "url": url,
        "youtube_id": yt,
        "title": title,
        "description": long_desc or desc,
        "meta_description": desc,
        "category_legacy": cat,
        "video_type": video_type,
        "level_legacy": level,
        "views_legacy": views,
        "published_legacy": published,
        "related_ids": related,
    }


def load_cdx() -> list[dict]:
    rows = json.loads(CDX_FILE.read_text())
    hdr, rows = rows[0], rows[1:]
    out, seen = [], set()
    for orig, ts, status in rows:
        if not orig.startswith("http://www.edutube.org/en/video/"):
            continue
        if status != "200":
            continue
        slug = urllib.parse.unquote(orig.split("/en/video/")[1]).strip("/")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append({"slug": slug, "original": orig, "timestamp": ts})
    return out


def harvest_one(item: dict, retries: int = 3) -> dict | None:
    slug, orig, ts = item["slug"], item["original"], item["timestamp"]
    for attempt in range(retries):
        url = f"https://web.archive.org/web/{ts}id_/{orig}"
        status, body = fetch(url, timeout=40)
        if status == 200 and body:
            rec = parse_page(body, orig, slug)
            if rec:
                rec["source_snapshot"] = f"https://web.archive.org/web/{ts}/{orig}"
                return rec
        time.sleep(1.2 * (attempt + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(RAW_FILE))
    args = ap.parse_args()

    if not CDX_FILE.exists():
        print(f"missing {CDX_FILE} — run the CDX query first", file=sys.stderr)
        return 2

    items = load_cdx()
    if args.limit:
        items = items[: args.limit]
    print(f"harvesting {len(items)} archived pages with {args.workers} workers", file=sys.stderr)

    done, ok = 0, 0
    started = time.time()
    out_path = Path(args.out)
    tmp = out_path.with_suffix(".part")
    with open(tmp, "w", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(harvest_one, it): it for it in items}
        for fut in as_completed(futs):
            done += 1
            rec = fut.result()
            if rec:
                ok += 1
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if done % 100 == 0:
                rate = done / max(time.time() - started, 1e-9)
                eta = (len(items) - done) / max(rate, 1e-9)
                print(f"  {done}/{len(items)} ok={ok} {rate:.1f}/s eta={eta/60:.1f}m", file=sys.stderr)
    tmp.replace(out_path)
    print(f"wrote {ok} records -> {out_path} in {(time.time()-started)/60:.1f}m", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
