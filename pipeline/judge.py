#!/usr/bin/env python3
"""The semantic layer: Jev restores what the 2008-2021 human taxonomy lost.

EduTube's editors tagged each video with a broad subject and an "educational
level", but the level never made it into the listing tables we could recover,
and the subject tags are inconsistent (a fluid-dynamics film is filed under
Chemistry). Jev is asked three typed questions per video, in one request:

  subject        choice  -> 12-way subject for the shelf the video sits on
  level          choice  -> who it is actually for
  classroom_ok   noul    -> could a teacher press play, no caveats?
  evergreen      noul    -> still teaching material in 2026, or a dated artifact?

Unlike a prose model, the answers are typed and composable: they become
filters, sort keys and badges in the UI without any parsing.

Input : data/enriched.jsonl   Output: data/judgments.jsonl
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "enriched.jsonl"
OUT = ROOT / "data" / "judgments.jsonl"

SUBJECTS = [
    "Mathematics",
    "Physics",
    "Chemistry",
    "Biology",
    "Earth and Space",
    "Computer Science and Software",
    "Engineering and Technology",
    "History",
    "Geography and Society",
    "Economics and Business",
    "Language and Literature",
    "Arts, Music and Culture",
    "Health and Psychology",
    "Life Skills and DIY",
]

QUESTIONS = {
    "subject": {
        "type": "choice",
        "instructions": (
            "Which single school subject does this video belong in? Judge the content, "
            "not the archive tag. If it spans several, pick the one a teacher would file it under."
        ),
        "criteria": {s: s for s in SUBJECTS},
    },
    "level": {
        "type": "choice",
        "instructions": (
            "What educational level is this video actually pitched at? Judge vocabulary, "
            "pace and depth, not production quality."
        ),
        "criteria": {
            "Pre-school": "Pre-school (ages 3-5)",
            "Primary": "Primary school (ages 5-11)",
            "Secondary": "Secondary school (ages 11-18)",
            "University": "University or professional study",
            "General": "General adult audience, no curriculum slot",
        },
    },
    "classroom_ok": {
        "type": "noul",
        "instructions": (
            "Could a teacher play this video in a K-12 classroom without caveats "
            "(no advertising, no inappropriate content, no broken/irrelevant footage)?"
        ),
    },
    "evergreen": {
        "type": "noul",
        "instructions": (
            "Is this still usable teaching material today, rather than a dated artifact "
            "(obsolete software demo, old product ad, expired news item)?"
        ),
    },
    "promotional": {
        "type": "noul",
        "instructions": (
            "Is this essentially an advertisement or promotional clip — a school, tutoring company, "
            "product, channel or app selling itself — rather than a lesson that teaches a subject? "
            "Judge intent, not whether a brand is mentioned."
        ),
    },
}


def judge(rec: dict, timeout: int = 60) -> dict:
    state = (
        f"Title: {rec.get('yt_title') or rec.get('title')}\n"
        f"Channel: {rec.get('channel', '')}\n"
        f"Archive subject tag (2008-2021): {rec.get('category_legacy', '')}\n"
        f"Duration: {rec.get('duration', '')}\n"
        f"Description: {(rec.get('description') or '')[:900]}\n"
    )
    cmd = ["jev", "--raw", "ask", "--questions", json.dumps(QUESTIONS)]
    try:
        p = subprocess.run(cmd, input=state, text=True, capture_output=True, timeout=timeout)
        if p.returncode != 0:
            return {"ok": False, "error": (p.stderr or "")[:200]}
        ans = json.loads(p.stdout)["answers"]
        out = {}
        for k, v in ans.items():
            if v.get("type") == "choice":
                out[k] = v.get("choice")
                out[k + "_p"] = round((v.get("probabilities") or {}).get(v.get("choice"), 0.0), 3)
            elif v.get("type") == "noul":
                out[k] = v.get("noul")
        return {"ok": True, **out}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="restrict to these youtube ids (comma separated)")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and re-judge everything")
    args = ap.parse_args()

    rows = []
    for l in IN.read_text().splitlines():
        try:
            if l.strip():
                rows.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    rows = [r for r in rows if r.get("alive")]
    if args.only:
        keep = set(args.only.split(","))
        rows = [r for r in rows if r["youtube_id"] in keep]
    if args.refresh and OUT.exists():
        OUT.unlink()
    done = set()
    if OUT.exists():
        done = {json.loads(l)["youtube_id"] for l in OUT.read_text().splitlines() if l.strip()}
    todo = [r for r in rows if r["youtube_id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"judging {len(todo)} videos ({len(done)} cached)", file=sys.stderr)

    ok = fail = 0
    t0 = time.time()
    with open(OUT, "a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(judge, r): r for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            res = fut.result()
            if res.get("ok"):
                ok += 1
            else:
                fail += 1
            fh.write(json.dumps({"youtube_id": r["youtube_id"], **res}, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} ok={ok} fail={fail} {(time.time()-t0)/i:.2f}s/item", file=sys.stderr)
    print(f"done ok={ok} fail={fail} -> {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
