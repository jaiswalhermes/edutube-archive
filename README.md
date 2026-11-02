# EduTube (rebuilt)

A YouTube-style catalogue of the videos EduTube.org published between 2008 and 2021, recovered from the Wayback Machine, re-verified against YouTube, and re-tagged with typed judgments from a language model.

The site today (edutube.org) sells educational games. The video catalogue it abandoned is still in the archive; this rebuild is what it would look like if someone had kept it alive.

## Run it (Docker)

```bash
docker compose up -d --build
# http://127.0.0.1:8765
```

nginx:1.27-alpine, static files baked into the image, read-only rootfs, all capabilities
dropped except what the master process needs, healthcheck on `/healthz`, gzip + a CSP that
allows only `i.ytimg.com` (thumbnails) and `youtube-nocookie.com` (player). Port 8765 because
8080 was already taken on this machine; change the mapping in `docker-compose.yml` if you
prefer another.

Without Docker:

```bash
cd site && python3 -m http.server 8756
```

No build step, no runtime dependencies. `site/data/catalog.json` is the whole dataset.

## Rebuild the data

```bash
python3 pipeline/harvest_listing.py     # Wayback → data/listing.jsonl   (slow: 1 req, paced)
python3 pipeline/enrich.py              # YouTube oEmbed → alive/channel  (data/enriched.jsonl)
python3 pipeline/thumbs.py              # probe hq720/hqdefault         (data/thumbs.jsonl)
python3 pipeline/judge.py               # the judge: 5 typed questions/video  (data/judgments.jsonl)
python3 pipeline/build_catalog.py       # join → site/data/catalog.json
python3 pipeline/verify_claims.py       # the claims → site/data/verify.json
```

Every stage is resumable; each skips ids already present in its output file. If the archive starts refusing connections, the harvester was too fast. Wait a few minutes and rerun, it picks up where it stopped.

## How it works

| Stage | Source | What comes out |
|---|---|---|
| harvest | `web.archive.org` CDX + `/en/category/*` tables | title, teaser, YouTube id, duration, views/day, EduTube-Index, legacy subject |
| enrich | `youtube.com/oembed` | still playable?, current channel, canonical thumbnail |
| thumbs | `i.ytimg.com` HEAD probes | the largest thumbnail that actually exists |
| judge | the judge service | subject, level, classroom-readiness, evergreen, promotional intent, all typed |
| build | join + rank | `catalog.json`: one record per playable video |

Ranking blends the archive's editorial index, log views/day, and the judge's classroom verdict. Nothing is scraped from a YouTube watch page; nothing is re-hosted.

## What this copies from HackerTube

Karpathy's [post](https://karpathy.bearblog.dev/hacker-tube/) lists four things beyond "a YouTube UI". All four are implemented:

| Feature | Here |
|---|---|
| 50% frame instead of the uploaded thumbnail | `maxres2 / sd2 / hq2`: 663 of 670 cards, uploaded art only as fallback (7 videos) |
| For You with no accounts, state in the browser | subject/channel affinity in `localStorage`, wiped by one button, never sent anywhere |
| Keyboard shortcuts | `j`/`k`, `Enter`, `/`, `?` |
| Data export for your own agent | `data/catalog.json`: 670 records in one file |

## Verification

`pipeline/verify_claims.py` re-runs the feasibility claims with live judge calls and writes `data/verify.json` (rendered at `#/about`). Headline numbers at last run:

- 75% of archived links still play: 269 of 1,084 rotted since 2008–2021
- 61% agreement between the judge's subject and the 2008 editors' tags
- classroom-readiness spreads across the corpus (σ = 0.15), and separates benign from distressing footage by 0.20 on a hand-labelled spot check, with one real false negative, which is why the UI treats it as a signal, not a gate

## Fidelity audit against the original post

`tools/behavior.js` measures the running container (thumbnails, export, For You, keyboard,
feed diversity). `pipeline/audit_fidelity.py` feeds that evidence to the judge, one probability per
requirement quoted from the post, 3 runs averaged:

```bash
NODE_PATH=... node tools/behavior.js          # writes data/behavior.json
python3 pipeline/audit_fidelity.py            # writes data/fidelity.json
```

Last run: **5 of 8 requirements met at p ≥ 0.60**, overall verdict *"matches the pattern with
documented substitutions"* (confidence 0.89). The three below the bar:

| Requirement | p | Why |
|---|---|---|
| Quality content instead of slop | 0.55 | curation is inherited from the 2008–2021 editors, not refreshed in 2026 |
| YouTube clone over a curated corpus | 0.59 | corpus is EduTube's catalogue, not HN comments (structural) |
| Deployed, secured, hardened | 0.10 | local Docker on loopback, no domain or TLS, which is the requested scope |

## Section parity with the live site

```bash
python3 pipeline/extract_site.py     # 14 sections -> data/site_extract.json
python3 pipeline/audit_parity.py     # the judge, majority of 3 -> data/parity.json
```

Every section of edutube.org today is extracted (home, about, blog, category/genre/platform
browsing, search, item pages) and judged twice: does the rebuild have an equivalent, and should
it? Last run: **6/10 covered, 0 required gaps**. Blog (its posts are placeholder lorem ipsum),
genre and platform browsing, and download links/comments are missing by design, not by accident.
The table renders on `#/about`.

## Copy and design audit

`pipeline/audit_slop.py` pulls every em dash out of the authored copy, has the judge classify it
(appositive aside / AI connective / not prose), and scans for a small lexicon of filler.

```bash
python3 pipeline/audit_slop.py     # writes data/slop.json
```

Last run: **43 dashes classified, 17 judged AI connective, 0 remaining, 0 lexicon hits.**
The design tells went with them: gradient headline text, glow dot, radial background wash,
emoji checkmarks, and the `✓`/`✗` verdict glyphs are all gone, replaced by PASS/FAIL badges.

## Layout

```
pipeline/   harvest, enrich, thumbs, judge, build, verify
data/       jsonl at every stage + verify.json
site/       index.html, app.js, styles.css, data/catalog.json
tools/      audit.js (Playwright smoke test: layout, routing, console errors)
```

## Credit

Catalogue and editorial index: EduTube.org (2008–2021), via the Internet Archive. Videos belong to their channels and stream from YouTube. The rebuild itself is a re-verification, not a copy.
