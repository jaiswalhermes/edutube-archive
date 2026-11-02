#!/usr/bin/env python3
"""Dogfood: consume the site's export exactly as an outside agent would.

No repo imports, no local data files. It fetches data/catalog.json over HTTP,
validates the schema it claims to ship, and builds something the site itself
does not have: a printable lesson sheet. If this works, the export is genuinely
sufficient for "give it to your agent and easily create your own version".
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
OUT = Path(__file__).resolve().parents[1] / "data" / "dogfood"
REQUIRED = {
    "id": str, "title": str, "subject": str, "level": str, "channel": str,
    "thumb": str, "duration": str, "score": (int, float),
}


def main() -> int:
    with urllib.request.urlopen(f"{BASE}/data/catalog.json", timeout=30) as r:
        cat = json.loads(r.read())

    videos = cat["videos"]
    schema = cat.get("schema", {})
    declared = set(schema.get("fields", {}))

    missing_fields = {k: t.__name__ for k, t in REQUIRED.items() if not all(isinstance(v.get(k), t) for v in videos[:50] if v)}
    undeclared = sorted({k for v in videos for k in v} - declared)

    # what an agent could build from this file alone
    by_subject: dict[str, list] = {}
    for v in videos:
        if (v.get("classroom") or 0) >= 0.6 and (v.get("evergreen") or 0) >= 0.6:
            by_subject.setdefault(v["subject"], []).append(v)

    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lesson sheet, built only from the exported catalog.json",
        "",
        f"Source: {BASE}/data/catalog.json · {len(videos)} records · schema v{schema.get('version')}",
        "",
        "Selection rule: classroom readiness >= 0.6 and evergreen >= 0.6, ranked by catalogue score.",
        "",
    ]
    picked = 0
    for subject in sorted(by_subject, key=lambda s: -len(by_subject[s])):
        rows = sorted(by_subject[subject], key=lambda v: -v["score"])[:3]
        if not rows:
            continue
        lines += [f"## {subject} ({len(by_subject[subject])} qualified)", ""]
        for v in rows:
            lines.append(f"- **{v['title']}** · {v['duration'] or 'n/a'} · {v['channel']} · classroom {v['classroom']:.2f}")
            picked += 1
        lines.append("")
    (OUT / "lesson-sheet.md").write_text("\n".join(lines))
    (OUT / "summary.json").write_text(json.dumps({
        "records": len(videos),
        "schema_version": schema.get("version"),
        "declared_fields": len(declared),
        "fields_on_records": len({k for v in videos for k in v}),
        "undeclared_fields": undeclared,
        "type_violations": missing_fields,
        "subjects_with_qualified_lessons": len(by_subject),
        "lessons_in_sheet": picked,
    }, indent=2))

    print(f"fetched {len(videos)} records over HTTP")
    print(f"schema declares {len(declared)} fields; records use {len({k for v in videos for k in v})}")
    print(f"undeclared: {undeclared or 'none'} | type violations: {missing_fields or 'none'}")
    print(f"lesson sheet: {picked} lessons across {len(by_subject)} subjects -> {OUT/'lesson-sheet.md'}")
    return 0 if not missing_fields else 1


if __name__ == "__main__":
    raise SystemExit(main())
