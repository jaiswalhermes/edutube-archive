#!/usr/bin/env python3
"""Parity audit: edutube.org section by section, judged against the rebuild.

For every section extracted from the live site, jev answers two questions:
  - coverage: does the rebuild have an equivalent? (direct / adapted / missing / not applicable)
  - need: should it? (essential / useful / not applicable)

A section is a gap only when jev says it is missing AND essential or useful.
Output: data/parity.json
"""
from __future__ import annotations

import collections
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# what the rebuild currently provides, described plainly for the judge
REBUILD = {
    "home": "A hero with the source quote and archive stats, then a 670-video grid ranked by editorial index, reach and Jev's classroom verdict; subject and level chips filter it.",
    "about": "A long page: what EduTube was (sourced from edutube.org/about), Karpathy's quotes, the pipeline, claim verification and a fidelity audit.",
    "browse_category": "Fourteen subject hubs (#/subject/<name>) plus a subject list in the sidebar with counts.",
    "browse_level": "Level filters (Pre-school, Primary, Secondary, University, General) in the sidebar and as chips.",
    "search": "A search box in the header over titles, descriptions, channels, subjects and legacy tags, with a results page.",
    "item_detail": "A watch page per video: embedded player, title, views per day from the old archive, channel name and avatar, archived description, subject, educational level, classroom-readiness and evergreen probabilities, the archive's original tag, its editorial index, an Up next rail, a share button and a link to watch on YouTube. No comments (no accounts) and no download links (media is not hosted).",
    "for_you": "A local-session feed that weights subjects and channels the visitor has opened, mixing three familiar picks to one discovery pick; no accounts.",
    "export": "A downloadable catalog.json with schema and provenance blocks.",
    "comments": "None. The archive's comments were not harvested and there are no accounts to comment with.",
    "blog": "None. The rebuild has a page about the project but no news feed.",
    "account": "None by design: no login, no accounts.",
    "download": "None. The rebuild links out to YouTube and does not host video files.",
    "browse_genre": "None. Videos are tagged by subject, level and classroom readiness, not by a genre or format taxonomy.",
    "browse_platform": "None. Every item comes from YouTube, so a platform facet would have one value.",
}

SECTIONS = [
    ("home", "Home", "Featured games, category tiles, blog teasers, a search box and the curated pitch.", "home"),
    ("about", "About", "Mission, who runs the site, the 2008 origin and the 2021 reinvention, and the vacuum-tube etymology.", "about"),
    ("blog", "Blog", "News posts with dates and categories (News). The two 2018 posts are placeholder lorem ipsum text, not articles.", "blog"),
    ("games_index", "Games by Categories", "Seven category tiles (Geography, History, ICT/Computer Science, Math, Physics, Science, Space) leading to category listings.", "browse_category"),
    ("category_math", "Category page (Math)", "A single category listing with a short description and the games filed under it.", "browse_category"),
    ("genre_strategy", "Genre page (Strategy)", "A genre listing: Adventure, Coding, Creative, Mapping, Puzzle, RPG, Sandbox, Simulation, Strategy, Turn-based strategy.", "browse_genre"),
    ("platform_online", "Platform page (Online browser)", "A listing filtered by how the item runs: online browser, offline version, DOSBox.", "browse_platform"),
    ("search", "Search", "A search page over games.", "search"),
    ("game_page", "Item page", "A page per item: title, description, poster, genre, platforms, modes.", "item_detail"),
    ("game_extras", "Download links and comments", "Links to download the game files, and a WordPress comment thread under each item.", "comments"),
]


def ask(state: str, instructions: str, options: dict, runs: int = 3) -> dict:
    """Majority of three runs: single judgments drift between adjacent options."""
    q = {"q": {"type": "choice", "instructions": instructions, "criteria": options}}
    votes, ps = [], []
    for _ in range(runs):
        p = subprocess.run(["jev", "--raw", "ask", "--questions", json.dumps(q)],
                           input=state, text=True, capture_output=True, timeout=90)
        if p.returncode != 0:
            raise RuntimeError(p.stderr[:300])
        a = json.loads(p.stdout)["answers"]["q"]
        votes.append(a.get("choice"))
        ps.append((a.get("probabilities") or {}).get(a.get("choice"), 0))
    choice = collections.Counter(votes).most_common(1)[0][0]
    return {"choice": choice, "p": round(sum(ps) / len(ps), 3), "votes": votes}


def main() -> int:
    extract = json.loads((DATA / "site_extract.json").read_text())
    by_id = {s["id"]: s for s in extract["sections"]}
    rows = []
    for sid, label, purpose, mine_key in SECTIONS:
        src = by_id.get(sid) or {}
        state = (
            f"Live section: {label}\n"
            f"Purpose on the current site: {purpose}\n"
            f"Text sample: {(src.get('excerpt') or '')[:400]}\n\n"
            f"Rebuild equivalent ({mine_key}): {REBUILD[mine_key]}\n"
        )
        cov = ask(state,
                  "Does the rebuild provide an equivalent for this section of the current site? "
                  "Adapted is fine if the function survives; missing means the visitor cannot do that thing here.",
                  {"direct": "A direct equivalent exists",
                   "adapted": "An adapted equivalent exists and preserves the function",
                   "missing": "No equivalent exists",
                   "not_applicable": "Not applicable to this rebuild"})
        need = ask(state,
                   "Should this rebuild have this section, given it reconstructs a 2008-2021 archive of educational videos "
                   "and deliberately has no accounts?",
                   {"essential": "Essential to a usable rebuild",
                    "useful": "Useful if cheap to add",
                    "not_applicable": "Not applicable to an archive of videos",
                    "scope_creep": "Would be scope creep"})
        gap = cov["choice"] == "missing" and need["choice"] in ("essential", "useful")
        rows.append({"section": sid, "label": label, "coverage": cov["choice"], "coverage_p": cov["p"],
                     "need": need["choice"], "need_p": need["p"], "gap": gap})
        print(f"  {label:26} coverage={cov['choice']:<14} need={need['choice']:<13} {'GAP' if gap else ''}", file=sys.stderr)

    out = {
        "source": "https://www.edutube.org",
        "sections": rows,
        "gaps": [r["label"] for r in rows if r["gap"]],
        "covered": sum(1 for r in rows if r["coverage"] in ("direct", "adapted")),
        "total": len(rows),
    }
    blob = json.dumps(out, indent=2, ensure_ascii=False)
    (DATA / "parity.json").write_text(blob)
    (ROOT / "site" / "data" / "parity.json").write_text(blob)
    print(f"\ncovered {out['covered']}/{out['total']} · gaps: {out['gaps'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
