#!/usr/bin/env python3
"""Pick the thumbnail: the frame at 50% of the video, not the uploaded art.

Karpathy's HackerTube uses the 50% frame precisely because uploaded thumbnails
are the clickbait surface the whole project exists to escape. YouTube exposes
those frames as *2.jpg — maxres2 / sd2 / hq2 are the same mid-video frame at
1280x720 / 640x480 / 480x360; uploaded art is only a fallback.

Input : data/enriched.jsonl   Output: data/thumbs.jsonl
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "enriched.jsonl"
OUT = ROOT / "data" / "thumbs.jsonl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# Karpathy's rule: use the frame at 50% of the video, not the uploaded
# thumbnail. YouTube serves those as *2.jpg — maxres2/sd2/hq2 are the same
# frame at 1280x720 / 640x480 / 480x360. Uploaded art is only a fallback.
KINDS = ["maxres2", "sd2", "hq2", "maxresdefault", "sddefault", "hq720", "hqdefault", "mqdefault"]


def head(url: str, timeout: int = 8) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def best(vid: str) -> dict:
    for k in KINDS:
        if head(f"https://i.ytimg.com/vi/{vid}/{k}.jpg") == 200:
            return {"youtube_id": vid, "thumb_kind": k,
                    "thumb": f"https://i.ytimg.com/vi/{vid}/{k}.jpg",
                    "is_midframe": k.endswith("2")}
    return {"youtube_id": vid, "thumb_kind": None, "thumb": None, "is_midframe": False}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()
    if args.refresh and OUT.exists():
        OUT.unlink()
    rows = []
    for l in IN.read_text().splitlines():
        try:
            if l.strip():
                rows.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    rows = [r for r in rows if r.get("alive")]
    done = set()
    if OUT.exists():
        done = {json.loads(l)["youtube_id"] for l in OUT.read_text().splitlines() if l.strip()}
    todo = [r for r in rows if r["youtube_id"] not in done]
    print(f"thumbs: {len(todo)} to probe ({len(done)} cached)", file=sys.stderr)
    t0 = time.time()
    with open(OUT, "a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(best, r["youtube_id"]) for r in todo]
        for i, f in enumerate(as_completed(futs), 1):
            fh.write(json.dumps(f.result(), ensure_ascii=False) + "\n")
            fh.flush()
    kinds, mid, total = {}, 0, 0
    for line in OUT.read_text().splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        kinds[d.get("thumb_kind")] = kinds.get(d.get("thumb_kind"), 0) + 1
        mid += 1 if d.get("is_midframe") else 0
    print(f"done in {time.time()-t0:.1f}s | mid-frame {mid}/{total} | {kinds}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
