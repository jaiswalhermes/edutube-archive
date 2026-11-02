#!/usr/bin/env python3
"""Enrich harvested rows with live YouTube metadata via oEmbed (no API key).

oEmbed answers three things the archive cannot: is the video still playable,
what channel actually owns it now, and a canonical thumbnail. Dead/private/
embed-disabled videos are dropped downstream.

Input : data/listing.jsonl   Output: data/enriched.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "listing.jsonl"
OUT = ROOT / "data" / "enriched.jsonl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def oembed(vid: str, retries: int = 3) -> dict:
    url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
                return {
                    "alive": True,
                    "yt_title": d.get("title", ""),
                    "channel": d.get("author_name", ""),
                    "channel_url": d.get("author_url", ""),
                    "thumbnail": d.get("thumbnail_url") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                }
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                return {"alive": False, "http": e.code}
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return {"alive": None, "http": 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = []
    for l in IN.read_text().splitlines():
        try:
            if l.strip():
                rows.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    done = set()
    if OUT.exists():
        done = {json.loads(l)["youtube_id"] for l in OUT.read_text().splitlines() if l.strip()}
    todo = [r for r in rows if r["youtube_id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"enriching {len(todo)} ({len(done)} cached)", file=sys.stderr)

    ok = dead = 0
    t0 = time.time()
    with open(OUT, "a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(oembed, r["youtube_id"]): r for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            meta = fut.result()
            rec = {**r, **meta}
            if meta.get("alive"):
                ok += 1
            else:
                dead += 1
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 200 == 0:
                print(f"  {i}/{len(todo)} alive={ok} dead={dead} {(time.time()-t0)/i:.2f}s/item", file=sys.stderr)
    print(f"done alive={ok} dead={dead} -> {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
