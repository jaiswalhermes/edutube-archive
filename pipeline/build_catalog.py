#!/usr/bin/env python3
"""Join the three layers into the catalogue the site renders.

listing.jsonl  -> what the 2008-2021 site published (title, description, duration,
                  views/day, editorial index, subject tag)
enriched.jsonl -> what YouTube says today (playable?, channel, thumbnail)
judgments.jsonl-> what Jev decided (subject, level, classroom-ready, evergreen)

Output: site/data/catalog.json
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "site" / "data" / "catalog.json"

LEGACY_TO_SUBJECT = {
    "mathematics": "Mathematics", "math-statistics": "Mathematics",
    "physics": "Physics", "chemistry": "Chemistry", "biology": "Biology",
    "space-astronomy": "Earth and Space", "geology-earth": "Earth and Space",
    "environment": "Earth and Space",
    "computer-science": "Computer Science and Software", "software": "Computer Science and Software",
    "technology": "Engineering and Technology", "development": "Engineering and Technology",
    "history": "History", "politics": "Geography and Society", "religion": "Geography and Society",
    "anthropology": "Geography and Society", "economics": "Economics and Business",
    "language": "Language and Literature",
    "art": "Arts, Music and Culture", "music": "Arts, Music and Culture", "film-media": "Arts, Music and Culture",
    "health": "Health and Psychology", "psychology": "Health and Psychology",
    "diy-how-to": "Life Skills and DIY", "food-cooking": "Life Skills and DIY",
    "agriculture": "Life Skills and DIY", "education": "Life Skills and DIY",
    "sports-martial-arts": "Health and Psychology", "animals-wildlife": "Biology",
}


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def dur_seconds(s: str) -> int:
    parts = [int(x) for x in re.findall(r"\d+", s or "")][:3]
    if not parts:
        return 0
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0]


def snapshot_year(row: dict) -> int | None:
    m = re.search(r"/web/(\d{4})\d{10}", row.get("source_snapshot") or "")
    return int(m.group(1)) if m else None


def main() -> int:
    listing = read_jsonl(DATA / "listing.jsonl")
    enriched = {r["youtube_id"]: r for r in read_jsonl(DATA / "enriched.jsonl")}
    judged = {r["youtube_id"]: r for r in read_jsonl(DATA / "judgments.jsonl") if r.get("ok")}
    thumbs = {r["youtube_id"]: r for r in read_jsonl(DATA / "thumbs.jsonl")}
    # frames jev rejected as blank/fade/logo cards, replaced by a better candidate
    fixes = {r["youtube_id"]: r for r in read_jsonl(DATA / "thumb_fix.jsonl")}

    videos = []
    drops = {"ad": 0, "not_a_lesson": 0, "editorially_worthless": 0}
    for row in listing:
        vid = row["youtube_id"]
        meta = enriched.get(vid)
        if meta is not None and not meta.get("alive"):
            continue  # dead / private / embedding disabled
        j = judged.get(vid, {})
        # Spam removal is deliberately more than one threshold on one question:
        # an ad, a clip that is neither teachable nor classroom-safe, or something
        # the editors scored zero that Jev also reads as promotional.
        promo = j.get("promotional") or 0
        room = j.get("classroom_ok")
        ever = j.get("evergreen")
        if j and promo >= 0.6:
            drops["ad"] += 1
            continue
        if j and room is not None and room < 0.30 and (ever or 0) < 0.5:
            drops["not_a_lesson"] += 1
            continue
        if j and (row.get("edutube_index") or 0) == 0 and promo >= 0.4:
            drops["editorially_worthless"] += 1
            continue
        title = (meta or {}).get("yt_title") or row.get("title") or ""
        if not title:
            continue
        desc = row.get("description") or ""
        if len(desc) < 40 and (meta or {}).get("yt_title"):
            desc = desc
        videos.append({
            "id": vid,
            "slug": row["slug"],
            "title": title,
            "title_legacy": row.get("title") or "",
            "description": desc,
            "duration": row.get("duration") or "",
            "dur": dur_seconds(row.get("duration") or ""),
            "channel": (meta or {}).get("channel") or "Unknown channel",
            "channel_url": (meta or {}).get("channel_url") or "",
            "thumb": (fixes.get(vid) or {}).get("thumb") or (thumbs.get(vid) or {}).get("thumb") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "subject": j.get("subject") or LEGACY_TO_SUBJECT.get(row.get("category_legacy", ""), "Life Skills and DIY"),
            "subject_confidence": j.get("subject_p"),
            "level": j.get("level") or "General",
            "classroom": j.get("classroom_ok"),
            "evergreen": j.get("evergreen"),
            "legacy_category": row.get("category_legacy"),
            "index": row.get("edutube_index"),
            "views_day": row.get("views_day"),
            "archived": snapshot_year(row),
            "judged": bool(j),
            "live": bool(meta),
        })

    # one record per video: the archive listed a few videos under several slugs
    seen_ids, unique = set(), []
    for v in sorted(videos, key=lambda x: -(x["score"] if x.get("score") else 0)):
        if v["id"] in seen_ids:
            continue
        seen_ids.add(v["id"])
        unique.append(v)
    videos = unique

    # ---- ranking
    # The archive's own editorial index is the strongest signal: 0.0 there means the
    # editors scored it zero (usually advertising), not "unrated" — those are kept
    # low even when their view counts are enormous. A missing index is neutral.
    # Reach is log-normalised so one viral number cannot dominate, and Jev's
    # classroom verdict nudges genuinely teachable videos up.
    for v in videos:
        idx = v["index"] if v["index"] is not None else 4.0
        reach = min(math.log10((v["views_day"] or 1) + 1) / 6.0, 1.0)
        room = v["classroom"] if v["classroom"] is not None else 0.5
        ever = v["evergreen"] if v["evergreen"] is not None else 0.5
        v["score"] = round(100 * (0.50 * (idx / 10) + 0.22 * reach + 0.18 * room + 0.10 * ever), 2)

    videos.sort(key=lambda v: v["score"], reverse=True)

    subjects: dict[str, dict] = {}
    for v in videos:
        s = subjects.setdefault(v["subject"], {"name": v["subject"], "count": 0, "top": []})
        s["count"] += 1
    for v in videos[:600]:
        s = subjects[v["subject"]]
        if len(s["top"]) < 4:
            s["top"].append(v["id"])
    subject_list = sorted(subjects.values(), key=lambda s: -s["count"])

    levels = {}
    for v in videos:
        levels[v["level"]] = levels.get(v["level"], 0) + 1

    classroom_ready = sum(1 for v in videos if (v["classroom"] or 0) >= 0.5)
    evergreen = sum(1 for v in videos if (v["evergreen"] or 0) >= 0.5)
    dead = len(enriched) - sum(1 for e in enriched.values() if e.get("alive"))
    midframe = sum(1 for v in videos if (thumbs.get(v["id"]) or {}).get("is_midframe"))

    # The export is the deliverable Karpathy describes ("give it to your agent"):
    # a single self-describing file, so it ships with its own field docs and provenance.
    schema = {
        "version": 1,
        "description": "One record per playable video in the rebuilt EduTube catalogue.",
        "fields": {
            "id": "YouTube video id (11 chars)",
            "title": "Current YouTube title (oEmbed), falling back to the 2008-2021 archive title",
            "title_legacy": "Title as EduTube published it",
            "description": "Archive teaser, plain text",
            "duration": "mm:ss exactly as the archive listed it; `dur` is seconds",
            "channel": "Current YouTube channel name (oEmbed)",
            "thumb": "Thumbnail URL; 50%-of-video frame where available (maxres2/sd2/hq2), uploaded art otherwise",
            "subject": "The judge's subject classification (14 values)",
            "subject_confidence": "Judge probability for that subject",
            "level": "The judge's educational-level classification: Pre-school | Primary | Secondary | University | General",
            "classroom": "Probability (0-1) that a teacher can play it in K-12 without caveats",
            "evergreen": "Probability (0-1) that it is still teaching material, not a dated artifact",
            "legacy_category": "EduTube's own 2008-2021 subject tag, unmodified",
            "index": "EduTube editorial index (0-10); 0.0 means the editors scored it zero",
            "views_day": "Views per day as recorded by EduTube before 2021",
            "archived": "Year of the Wayback capture the record came from",
            "score": "Blend used for ranking: 0.50*index/10 + 0.22*log views + 0.18*classroom + 0.10*evergreen (x100)",
            "judged": "True if the judge scored this record (vs. metadata-only fallback)",
            "slug": "EduTube archive slug for the video page",
            "channel_url": "YouTube channel URL from oEmbed, empty if unresolved",
            "dur": "Duration in seconds (integer), parsed from `duration`",
            "live": "True if oEmbed confirmed the video is still playable at build time",
        },
    }
    provenance = {
        "catalogue": "EduTube.org 2008-2021, via the Internet Archive (web.archive.org CDX + /en/category/* tables)",
        "liveness": "youtube.com/oembed, checked at build time",
        "thumbnails": "i.ytimg.com, HEAD-probed; 50% frame preferred",
        "judgments": "Typed judgments from a language model: subject, level, classroom_ok, evergreen, promotional intent",
        "rights": "Videos belong to their channels and stream from YouTube; nothing is re-hosted",
        "rebuild": "pipeline/ in this repo: harvest_listing.py -> enrich.py -> thumbs.py -> judge.py -> build_catalog.py",
    }
    catalog = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "schema": schema,
        "provenance": provenance,
        "videos": videos,
        "subjects": subject_list,
        "levels": sorted(levels.items(), key=lambda kv: -kv[1]),
        "stats": {
            "videos": len(videos),
            "harvested": len(listing),
            "judged": len(judged),
            "channels": len({v["channel"] for v in videos}),
            "subjects": len(subject_list),
            "classroom_ready": classroom_ready,
            "evergreen": evergreen,
            "dead_links": max(dead, 0),
            "spam_dropped": sum(drops.values()),
            "spam_rules": drops,
            "midframe_thumbs": midframe,
            "thumbs_replaced": len(fixes),
            "median_duration": sorted([v["dur"] for v in videos if v["dur"]])[len([v for v in videos if v["dur"]]) // 2] if videos else 0,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
    mb = OUT.stat().st_size / 1e6
    print(json.dumps(catalog["stats"], indent=2))
    print(f"wrote {OUT} ({mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
