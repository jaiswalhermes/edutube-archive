#!/usr/bin/env python3
"""Thumbnail quality pass, adjudicated by jev.

The 50% frame is the right rule, but the rule alone does not guarantee a usable
poster: the midpoint of a video can be a black fade, a title card, a white
flash or a flat logo. This measures every thumbnail (mean luminance, detail,
share of dead pixels), asks jev about the borderline ones with that evidence
plus the title and duration, and replaces the frames jev rejects with a better
candidate (25% or 75% frame, then uploaded art).

Output: data/thumb_audit.json, data/thumb_fix.jsonl
"""
from __future__ import annotations

import io
import json
import math
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# frames first: 50% preferred, then 25%/75% at the same quality tiers.
# uploaded art is the last resort, because it is the thing this project escapes.
FRAME_CANDIDATES = ["maxres2", "sd2", "hq2", "maxres1", "sd1", "hq1", "maxres3", "sd3", "hq3"]
UPLOAD_CANDIDATES = ["maxresdefault", "sddefault", "hqdefault"]
CANDIDATES = FRAME_CANDIDATES + UPLOAD_CANDIDATES


def fetch_image(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return Image.open(io.BytesIO(r.read())).convert("L")


def stats(img) -> dict:
    st = ImageStat.Stat(img)
    mean, sd = st.mean[0], st.stddev[0]
    hist = img.histogram()
    n = sum(hist)
    dark = sum(hist[:20]) / n
    bright = sum(hist[235:]) / n
    # detail in the lower two thirds, where a poster's subject usually sits
    w, h = img.size
    body = img.crop((0, int(h * 0.15), w, h))
    body_sd = ImageStat.Stat(body).stddev[0]
    return {
        "mean": round(mean, 1),
        "sd": round(sd, 1),
        "body_sd": round(body_sd, 1),
        "dark_share": round(dark, 3),
        "bright_share": round(bright, 3),
    }


def measure(item: dict) -> dict:
    vid, url = item["id"], item["thumb"]
    try:
        img = fetch_image(url)
        s = stats(img)
        return {"id": vid, "url": url, "ok": True, **s}
    except Exception as e:  # noqa: BLE001
        return {"id": vid, "url": url, "ok": False, "error": str(e)[:100]}


def suspicious(s: dict) -> bool:
    return bool(s.get("ok")) and (s["mean"] < 16 or s["sd"] < 12 or s["dark_share"] > 0.72 or s["bright_share"] > 0.65)


def jev_poster(title: str, duration: str, s: dict) -> float:
    state = (
        f"Video title: {title}\nDuration: {duration}\n"
        f"Thumbnail measurements (greyscale, 0-255): mean luminance {s['mean']}, "
        f"standard deviation {s['sd']}, detail in lower two thirds {s['body_sd']}, "
        f"share of near-black pixels {s['dark_share']}, share of near-white pixels {s['bright_share']}.\n"
        f"The frame is taken at 50% of the video."
    )
    q = {"q": {"type": "noul", "instructions": (
        "Is this frame a poor poster image — a black fade, white flash, logo card, title card or "
        "otherwise blank frame — such that a viewer could not tell what the video is about from it?")}}
    p = subprocess.run(["jev", "--raw", "ask", "--questions", json.dumps(q)],
                       input=state, text=True, capture_output=True, timeout=90)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:200])
    return json.loads(p.stdout)["answers"]["q"].get("noul", 0.0)


def best_candidate(vid: str, reject: str) -> dict | None:
    """Pick the alternative with the most usable tone and detail, frames first."""
    for pool in (FRAME_CANDIDATES, UPLOAD_CANDIDATES):
        best = _best_in(vid, reject, pool)
        if best:
            return best
    return None


def _best_in(vid: str, reject: str, pool: list[str]) -> dict | None:
    best = None
    for kind in pool:
        url = f"https://i.ytimg.com/vi/{vid}/{kind}.jpg"
        if url == reject:
            continue
        try:
            s = stats(fetch_image(url))
        except Exception:
            continue
        if s["mean"] < 14 or s["sd"] < 10:
            continue
        score = s["body_sd"] + min(s["mean"], 150) * 0.25
        if best is None or score > best["score"]:
            best = {"kind": kind, "url": url, "score": round(score, 1), **s}
        if kind in ("maxres2", "sd2", "hq2") and s["mean"] > 30 and s["sd"] > 25:
            break
    return best


def main() -> int:
    app = len(sys.argv) > 1 and sys.argv[1] == "--fix"
    cat = json.loads((ROOT / "site" / "data" / "catalog.json").read_text())
    vids = [{"id": v["id"], "thumb": v["thumb"], "title": v["title"], "duration": v.get("duration") or "?"}
            for v in cat["videos"]]
    print(f"measuring {len(vids)} thumbnails", file=sys.stderr)

    results = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(measure, v) for v in vids]
        for f in as_completed(futs):
            results.append(f.result())
    by_id = {v["id"]: v for v in vids}
    flagged = [r for r in results if suspicious(r)]
    print(f"measured {len(results)} | suspicious {len(flagged)}", file=sys.stderr)

    # jev adjudicates the borderline frames
    for r in flagged:
        meta = by_id[r["id"]]
        try:
            r["p"] = round(jev_poster(meta["title"], meta["duration"], r), 3)
        except Exception as e:  # noqa: BLE001
            r["p"] = None
            r["error"] = str(e)[:120]
    rejected = [r for r in flagged if (r.get("p") or 0) >= 0.5]
    print(f"jev rejects {len(rejected)} of {len(flagged)}", file=sys.stderr)

    fixes = []
    if app:
        for r in rejected:
            best = best_candidate(r["id"], r["url"])
            if best:
                fixes.append({"youtube_id": r["id"], "old": r["url"], "thumb": best["url"],
                              "kind": best["kind"], "p": r["p"], **{k: best[k] for k in ("mean", "sd", "body_sd")}})
                print(f"  fix {r['id']}: {r['url'].split('/')[-1]} -> {best['kind']} (mean {best['mean']}, sd {best['sd']})", file=sys.stderr)
    if fixes:
        # merge with earlier fixes instead of clobbering them
        existing = {}
        if (DATA / "thumb_fix.jsonl").exists():
            for line in (DATA / "thumb_fix.jsonl").read_text().splitlines():
                if line.strip():
                    d = json.loads(line)
                    existing[d["youtube_id"]] = d
        for f in fixes:
            existing[f["youtube_id"]] = f
        with open(DATA / "thumb_fix.jsonl", "w", encoding="utf-8") as fh:
            for d in existing.values():
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        fixes = list(existing.values())

    summary = {
        "measured": len(results),
        "suspicious": len(flagged),
        "rejected_by_jev": len(rejected),
        "fixed": len(fixes),
        "mean_luminance": round(sum(r["mean"] for r in results if r.get("ok")) / max(len(results), 1), 1),
        "too_dark": sum(1 for r in results if r.get("ok") and r["mean"] < 16),
        "too_flat": sum(1 for r in results if r.get("ok") and r["sd"] < 12),
        "rejections": [{k: r[k] for k in ("id", "mean", "sd", "p") if k in r} | {"title": by_id[r["id"]]["title"][:60]}
                       for r in rejected[:12]],
    }
    (DATA / "thumb_audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in summary.items() if k != "rejections"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
