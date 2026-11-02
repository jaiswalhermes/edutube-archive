#!/usr/bin/env python3
"""Slop audit: the em-dash connective tic, adjudicated by jev.

Every em dash in authored copy is pulled out with its sentence and classified
three ways: a genuine appositive aside, an AI-style connective dash used to add
a rhetorical beat, or a range/placeholder that is not prose at all. Only the
second category is a defect, and only jev decides which is which.

Also scans for a small lexicon of filler that survives most rewrites.

Output: data/slop.json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FILES = ["site/app.js", "site/index.html", "pipeline/audit_fidelity.py", "pipeline/verify_claims.py", "PLAN.md", "README.md"]

LEXICON = [
    "not just", "isn't just", "is not just", "delve", "seamless", "elevate", "unlock", "leverage",
    "robust", "game-chang", "in a world where", "here's the thing", "let's be honest",
    "it's worth noting", "quietly", "supercharge", "revolutionary", "cutting-edge",
    "the real question", "at the end of the day", "double-edged", "tapestry", "landscape of",
]

CATEGORIES = {
    "appositive": "A genuine aside or appositive that a human editor would write with a dash",
    "ai_connective": "An AI-style connective dash that replaces a comma, colon or full stop to add a rhetorical beat",
    "not_prose": "Not prose: a numeric range, a placeholder for a missing value, or a code comment",
}


def clean(s: str) -> str:
    s = re.sub(r"\$\{[^}]*\}", "X", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract() -> list[dict]:
    out = []
    for f in FILES:
        p = ROOT / f
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*", "#")) or f.endswith(".css"):
                continue
            if "—" not in line:
                continue
            for _ in re.finditer("—", line):
                s = max(0, line.index("—") - 130)
                ctx = clean(line[s:s + 300])
                if len(ctx) < 12:
                    continue
                out.append({"file": f, "line": i, "context": ctx})
                break  # one sample per line is enough to judge the usage
    return out


def jev_choice(context: str) -> dict:
    q = {"q": {"type": "choice",
               "instructions": ("Read this snippet of authored copy. Classify its em dash. "
                                "Judge how a careful human editor would read it, not whether a dash is ever allowed."),
               "criteria": CATEGORIES}}
    p = subprocess.run(["jev", "--raw", "ask", "--questions", json.dumps(q)],
                       input=context, text=True, capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:200])
    a = json.loads(p.stdout)["answers"]["q"]
    return {"choice": a.get("choice"), "p": round((a.get("probabilities") or {}).get(a.get("choice"), 0), 3)}


def main() -> int:
    items = extract()
    print(f"em dashes in authored copy: {len(items)}", file=sys.stderr)
    flagged = []
    for it in items:
        try:
            verdict = jev_choice(it["context"])
        except Exception as e:  # noqa: BLE001
            verdict = {"choice": "error", "p": 0, "error": str(e)[:120]}
        it.update(verdict)
        if it["choice"] == "ai_connective":
            flagged.append(it)
        print(f"  [{it['choice']:<13} {it['p']:.2f}] {it['file']}:{it['line']}  {it['context'][:90]}", file=sys.stderr)

    # lexicon scan over authored copy only
    lex_hits = []
    for f in FILES:
        p = ROOT / f
        if not p.exists():
            continue
        text = p.read_text().lower()
        for term in LEXICON:
            if term in text:
                line = next((n for n, l in enumerate(p.read_text().splitlines(), 1) if term in l.lower()), 0)
                lex_hits.append({"term": term, "file": f, "line": line})

    result = {
        "total_dashes": len(items),
        "by_class": {k: sum(1 for i in items if i["choice"] == k) for k in list(CATEGORIES) + ["error"]},
        "flagged": flagged,
        "lexicon_hits": lex_hits,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "slop.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nflagged as AI connective: {len(flagged)} · lexicon hits: {len(lex_hits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
