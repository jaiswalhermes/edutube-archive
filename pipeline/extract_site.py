#!/usr/bin/env python3
"""Extract edutube.org section by section, as it exists today.

The current site is a WordPress games directory. This walks its top-level
sections, its three browse taxonomies, a few item pages and the blog, and
records what each section actually contains: headings, taxonomies, counts and
the text it uses to describe itself.

Output: data/site_extract.json

Usage: python3 pipeline/extract_site.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "site_extract.json"
BASE = "https://www.edutube.org"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

PAGES = [
    ("home", "/"),
    ("about", "/about/"),
    ("blog", "/blog/"),
    ("games_index", "/free-educational-games/games-by-categories"),
    ("category_math", "/game-category/math/"),
    ("genre_strategy", "/genre/strategy/"),
    ("platform_online", "/platform/online-browser/"),
    ("platform_offline", "/platform/offline-version/"),
    ("platform_dosbox", "/platform/doxbox/"),
    ("search", "/search/"),
    ("game_civ", "/game/civilization/"),
    ("game_minecraft", "/game/minecraft-education/"),
    ("game_prodigy", "/game/prodigy-math-game/"),
]


def fetch(path: str, timeout: int = 25) -> tuple[int, str]:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def text_of(html: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'")
         .replace("&quot;", '"').replace("&#8211;", "-").replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", s).strip()


def headings(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<h([1-3])[^>]*>(.*?)</h\1>", html, re.S | re.I):
        t = text_of(m.group(2))
        if t and len(t) < 120:
            out.append({"level": int(m.group(1)), "text": t})
    return out[:24]


def links(html: str, pattern: str) -> list[str]:
    return sorted(set(re.findall(pattern, html)))


def main() -> int:
    sections = []
    for name, path in PAGES:
        status, html = fetch(path)
        if status != 200 or not html:
            sections.append({"id": name, "path": path, "status": status})
            print(f"  {name:16} {status}", file=sys.stderr)
            time.sleep(1.2)
            continue
        body = text_of(html)
        rec = {
            "id": name,
            "path": path,
            "status": status,
            "title": (re.search(r"<title>(.*?)</title>", html, re.S) or [None, ""])[1].strip(),
            "h1": [h["text"] for h in headings(html) if h["level"] == 1][:3],
            "headings": headings(html),
            "categories": links(html, r"/game-category/([a-z0-9-]+)"),
            "genres": links(html, r"/genre/([a-z0-9-]+)"),
            "platforms": links(html, r"/platform/([a-z0-9-]+)"),
            "ages": links(html, r"/age/([a-z0-9-]+)"),
            "games": links(html, r"/game/([a-z0-9-]+)/"),
            "posts": links(html, r"/(20\d\d/\d\d/\d\d/[a-z0-9-]+)/"),
            "excerpt": body[:900],
            "word_count": len(body.split()),
        }
        sections.append(rec)
        print(f"  {name:16} {status} words={rec['word_count']} games={len(rec['games'])}", file=sys.stderr)
        time.sleep(1.2)

    # one blog post, to know what the blog section is
    blog = next((s for s in sections if s["id"] == "blog" and s.get("posts")), None)
    if blog and blog["posts"]:
        status, html = fetch("/" + blog["posts"][0])
        if status == 200:
            sections.append({
                "id": "blog_post", "path": "/" + blog["posts"][0], "status": status,
                "title": (re.search(r"<title>(.*?)</title>", html, re.S) or [None, ""])[1].strip(),
                "headings": headings(html), "excerpt": text_of(html)[:900],
                "word_count": len(text_of(html).split()),
            })

    tax = {
        "categories": sorted({c for s in sections for c in s.get("categories", [])}),
        "genres": sorted({g for s in sections for g in s.get("genres", [])}),
        "platforms": sorted({p for s in sections for p in s.get("platforms", [])}),
        "ages": sorted({a for s in sections for a in s.get("ages", [])}),
    }
    data = {"base": BASE, "sections": sections, "taxonomy": tax,
            "section_count": len(sections)}
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(json.dumps(tax, indent=2))
    print(f"wrote {OUT} ({len(sections)} sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
