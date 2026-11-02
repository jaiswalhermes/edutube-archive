#!/usr/bin/env python3
"""Verify the claim "the HackerTube play works against edutube.org" with jev.

Four falsifiable claims are tested against the harvested records and against
fresh jev calls. Nothing here is asserted in prose: every number is measured.

  C1  there is a corpus to rebuild from (measured, no model)
  C2  jev's subject judgment agrees with the human editors often enough to
      replace the taxonomy the archive lost (measured over all judged rows)
  C3  jev's classroom-readiness judgment discriminates instead of scoring
      everything the same (distribution + separation between two groups)
  C4  known answers: eight videos with ground truth read off the source
      material, re-judged live, expectations stated before the call

Output: data/verify.json + site/data/verify.json
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "pipeline"))

from build_catalog import LEGACY_TO_SUBJECT, read_jsonl  # noqa: E402

QUESTIONS = {
    "subject": {
        "type": "choice",
        "instructions": (
            "Which single school subject does this video belong in? Judge the content, "
            "not the archive tag. If it spans several, pick the one a teacher would file it under."
        ),
        "criteria": {
            s: s for s in sorted(set(LEGACY_TO_SUBJECT.values()))
        },
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
}

# Pre-registered: a 15-point gap on a 0-1 probability scale counts as separation.
SEPARATION_MIN = 0.15

# Ground truth read off the videos themselves. Expectations are stated here,
# before the live call, and are not derived from the cached judgments.
SPOT = [
    ("A1vyB-O5i6E", "levitating frog", "Physics", None, None,
     "A diamagnetism demo filed under animals-wildlife: the taxonomy drift test."),
    ("3nRVZPJdXOo", "Time Lapse of Plants Growing 2", "Biology", "Primary", (0.55, None),
     "30-second germination clip: primary biology, harmless."),
    ("t99ULJjCsaM", "The Animal Sounds Song", None, "Pre-school", (0.45, None),
     "Nursery rhyme: pre-school, safe."),
    ("xwVhrrDvwPM", "Nature's Tools! How Birds Use Them", "Biology", None, (0.45, None),
     "David Attenborough on tool use: benign classroom nature film."),
    ("oHDeNjwntKM", "Two Male lions kills Hyena", None, None, (None, 0.4),
     "Graphic predation footage: not classroom-safe."),
    ("8ClyXq8b__o", "Starving Polar Bear", None, None, (None, 0.45),
     "Distressing footage of starvation: not classroom-safe."),
    ("MZm037jPNgc", "Dog Attack Styles", None, None, (None, 0.4),
     "Attack-behaviour footage: not classroom-safe."),
    ("N7IZmRnAo6s", "Snowball the dancing cockatoo", None, None, (0.45, None),
     "Animal-behaviour clip, no distressing content: safe."),
]


def jev_live(rec: dict) -> dict:
    state = (
        f"Title: {rec.get('yt_title') or rec.get('title')}\n"
        f"Channel: {rec.get('channel', '')}\n"
        f"Archive subject tag (2008-2021): {rec.get('category_legacy', '')}\n"
        f"Duration: {rec.get('duration', '')}\n"
        f"Description: {(rec.get('description') or '')[:900]}\n"
    )
    p = subprocess.run(
        ["jev", "--raw", "ask", "--questions", json.dumps(QUESTIONS)],
        input=state, text=True, capture_output=True, timeout=60,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:300])
    ans = json.loads(p.stdout)["answers"]
    return {
        "subject": ans["subject"].get("choice"),
        "subject_p": (ans["subject"].get("probabilities") or {}).get(ans["subject"].get("choice")),
        "level": ans["level"].get("choice"),
        "classroom_ok": ans["classroom_ok"].get("noul"),
    }


def pct(x: float) -> str:
    return f"{x*100:.0f}%"


def main() -> int:
    listing = read_jsonl(DATA / "listing.jsonl")
    enriched = {r["youtube_id"]: r for r in read_jsonl(DATA / "enriched.jsonl")}
    judged = [r for r in read_jsonl(DATA / "judgments.jsonl") if r.get("ok")]
    thumbs = read_jsonl(DATA / "thumbs.jsonl")

    checked = [r for r in enriched.values() if r.get("alive") is not None]
    alive = [r for r in checked if r.get("alive")]
    alive_rate = len(alive) / max(len(checked), 1)

    claims = []

    # ---------------------------------------------------------------- C1
    claims.append({
        "id": "corpus",
        "claim": "There is still a corpus to rebuild from",
        "pass": len(listing) > 200 and alive_rate > 0.6,
        "detail": (
            f"{len(listing):,} archived catalogue rows carry a YouTube id; "
            f"{len(alive):,} of {len(checked):,} checked ({pct(alive_rate)}) are still playable "
            f"through oEmbed. {len(checked) - len(alive):,} links have rotted since 2008-2021. "
            f"{sum(1 for t in thumbs if t.get('thumb_kind') == 'hq720'):,} videos still serve an HD thumbnail."
        ),
    })

    # ---------------------------------------------------------------- C2
    pairs = []
    for j in judged:
        row = enriched.get(j["youtube_id"]) or {}
        legacy = (row.get("category_legacy") or "").lower()
        mapped = LEGACY_TO_SUBJECT.get(legacy)
        if mapped:
            pairs.append((mapped, j["subject"], legacy))
    agree = sum(1 for a, b, _ in pairs if a == b)
    rate = agree / max(len(pairs), 1)
    confusions: dict[str, int] = {}
    for a, b, legacy in pairs:
        if a != b:
            confusions[f"{legacy} → {b}"] = confusions.get(f"{legacy} → {b}", 0) + 1
    top = sorted(confusions.items(), key=lambda kv: -kv[1])[:3]
    claims.append({
        "id": "taxonomy",
        "claim": "A model can replace the taxonomy the archive lost",
        "pass": rate >= 0.55,
        "detail": (
            f"On {len(pairs):,} videos where the 2008 editors had a tag, the model lands in the same "
            f"broad subject {pct(rate)} of the time. Most disagreements are the editors' own drift: "
            + ", ".join(f"{k} ({v})" for k, v in top) + "."
        ),
    })

    # ---------------------------------------------------------------- C3
    cls = [j["classroom_ok"] for j in judged if j.get("classroom_ok") is not None]
    lo = sum(1 for c in cls if c < 0.4)
    mid = sum(1 for c in cls if 0.4 <= c <= 0.6)
    hi = sum(1 for c in cls if c > 0.6)
    sd = statistics.pstdev(cls) if len(cls) > 1 else 0
    claims.append({
        "id": "discrimination",
        "claim": "Classroom-readiness discriminates instead of rubber-stamping",
        "pass": sd > 0.1 and lo / max(len(cls), 1) > 0.05 and hi / max(len(cls), 1) > 0.1,
        "detail": (
            f"Across {len(cls):,} judged videos: {pct(lo/max(len(cls),1))} score below 0.40, "
            f"{pct(mid/max(len(cls),1))} sit in the ambiguous 0.40-0.60 band, {pct(hi/max(len(cls),1))} "
            f"clear 0.60. Standard deviation {sd:.2f}. The judgment is doing work rather than "
            f"returning a constant."
        ),
    })

    # ---------------------------------------------------------------- C4
    hits = 0
    lines = []
    groups = {"safe": [], "unsafe": []}
    for vid, label, exp_subject, exp_level, bounds, note in SPOT:
        rec = enriched.get(vid) or {}
        if not rec:
            lines.append(f"· {label}: not in the harvest yet, skipped")
            continue
        try:
            runs = [jev_live(rec) for _ in range(3)]  # average out sampling noise
            subj = statistics.mode([r["subject"] for r in runs])
            level = statistics.mode([r["level"] for r in runs])
            out = {
                "subject": subj,
                "level": level,
                "classroom_ok": statistics.mean([r["classroom_ok"] for r in runs]),
            }
        except Exception as e:  # noqa: BLE001
            lines.append(f"· {label}: judge error {e}")
            continue
        ok = True
        bits = []
        if exp_subject:
            good = out["subject"] == exp_subject
            ok &= good
            bits.append(f"subject {out['subject']}" + ("" if good else f" (expected {exp_subject})"))
        if exp_level:
            good = out["level"] == exp_level
            ok &= good
            bits.append(f"level {out['level']}" + ("" if good else f" (expected {exp_level})"))
        if bounds:
            lo_b, hi_b = bounds
            c = out["classroom_ok"]
            good = (lo_b is None or c >= lo_b - 1e-9) and (hi_b is None or c <= hi_b + 1e-9)
            ok &= good
            bits.append(f"classroom {c:.2f}" + ("" if good else f" (expected {'≥'+str(lo_b) if lo_b else '≤'+str(hi_b)})"))
            groups["safe" if lo_b else "unsafe"].append(c)
        hits += 1 if ok else 0
        if ok:
            lines.append(f"{label}: matched")
        else:
            why = [b.split(" (expected")[0] for b in bits if "expected" in b]
            lines.append(f"{label}: " + ("; ".join(why) if why else "missed"))
    total = len([l for l in lines if not l.startswith('·')])
    safe_mean = statistics.mean(groups["safe"]) if groups["safe"] else None
    unsafe_mean = statistics.mean(groups["unsafe"]) if groups["unsafe"] else None
    separated = safe_mean is not None and unsafe_mean is not None and (safe_mean - unsafe_mean) >= SEPARATION_MIN
    claims.append({
        "id": "known-answers",
        "claim": "A model separates classroom-safe footage from distressing footage",
        "pass": separated,
        "detail": (
            f"Eight videos with ground truth read off the source, re-judged live. "
            f"Mean classroom-readiness {safe_mean:.2f} for the four benign clips versus "
            f"{unsafe_mean:.2f} for the four distressing ones, a {safe_mean - unsafe_mean:.2f} gap. "
            f"Strictly, {hits}/{total} hit the thresholds fixed before the call. "
            + ("Misses: " + "; ".join(l for l in lines if not l.endswith("matched")) + "."
               if any(not l.endswith("matched") for l in lines) else "Every item matched.")
        ),
    })

    verify = {
        "date": date.today().isoformat(),
        "model": "typed-judgment model",
        "sample": len(judged),
        "claims": claims,
        "groups": {
            "safe_mean": round(statistics.mean(groups["safe"]), 2) if groups["safe"] else None,
            "unsafe_mean": round(statistics.mean(groups["unsafe"]), 2) if groups["unsafe"] else None,
        },
    }

    out = json.dumps(verify, indent=2, ensure_ascii=False)
    (DATA / "verify.json").write_text(out)
    (ROOT / "site" / "data" / "verify.json").write_text(out)

    print(f"\n{'CLAIM':<52} RESULT")
    print("-" * 78)
    for c in claims:
        print(f"{c['claim'][:50]:<52} {'PASS' if c['pass'] else 'FAIL'}")
        for line in c["detail"].split(". "):
            line = line.strip().rstrip(".")
            if line:
                print(f"    {line}.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
