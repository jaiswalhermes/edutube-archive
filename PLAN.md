# Can the HackerTube play work for edutube.org?

**Answer: yes, but not with edutube.org's current content. The corpus has to be recovered first, and one of HackerTube's five steps has to be inverted.**

---

## 1. What the tweet actually describes

Min Choi's thread about Andrej Karpathy's HackerTube reduces to five steps:

| # | HackerTube step | What it really is |
|---|---|---|
| 1 | download all HN comments | acquire a corpus of *opinions* |
| 2 | filter with Sonnet down to ~40K comments recommending a video | a semantic pass that turns prose into structured records |
| 3 | 6,454 videos across 150 topics | a catalogue, deduplicated and tagged |
| 4 | Opus builds a YouTube-style UI | a shell over the catalogue |
| 5 | deploy to a VPS, secure and harden | hosting |

Two things make it work: the corpus is **enormous and noisy** (millions of comments), and the signal is **implicit** (a human said "watch this"). Everything else is engineering.

## 2. Transfer test against edutube.org

The site today is a WordPress install whose public catalogue is **10 game pages** (9 real games plus a placeholder). Its `game` post type is not even exposed over REST; the only REST collection is `product`, which is merchandise. There is no corpus to mine.

What does exist is the *previous* EduTube (2008–2021): a hand-curated directory of free educational videos, abandoned when the site pivoted to games in 2021. Its pages survive in the Wayback Machine: 3,258 archived `/en/video/` URLs and 28 subject tables.

So the mapping is:

| HackerTube | EduTube rebuild | Verdict |
|---|---|---|
| corpus of opinions | archived catalogue tables | **substitute**: the corpus is a catalogue, not opinions |
| Sonnet filters prose → records | archive rows are already semi-structured | **inverted**: the model is needed to *repair* tags, not extract records |
| YouTube Data API for metadata | YouTube oEmbed (no key, no quota) | **simpler** |
| 50% frame thumbnails, no-account For You, shortcuts, export | all four, per §2b | **copied deliberately** |
| YouTube-style UI | same | **identical** |
| VPS + hardening | not required for this build | **out of scope** (local) |

The important difference: HackerTube *discovers* videos; EduTube *re-verifies* them. A 2008 link is not a video in 2026. In the sample, 21% of archived links were dead. A 2008 subject tag is not a taxonomy either: the editors filed a diamagnetism demo under "animals & wildlife". So the model's job moves from extraction to adjudication.

## 2b. Correction after reading the original post

My first pass was based on the X thread. Reading [karpathy.bearblog.dev/hacker-tube](https://karpathy.bearblog.dev/hacker-tube/) showed four product decisions the thread omits, and the first build got one of them wrong:

- **"Uses the 50% thumbnail instead of the uploaded thumbnail."** The point of the project is escaping clickbait art, so the mid-video frame is the whole aesthetic. My first build used uploaded thumbnails. Fixed: `pipeline/thumbs.py` now probes `maxres2 / sd2 / hq2` first: **663 of 670** cards are mid-frames, 7 fall back to uploaded art, and the About page states the ratio.
- **Custom "For You" with no accounts, state in the local session.** First build had no personalisation at all. Fixed: `#/foryou` ranks by subject/channel affinity stored in `localStorage`, with a clear-history button and no server-side profile.
- **Keyboard shortcuts.** First build had `/` only. Fixed: `j`/`k`/`Enter`/`/`/`?`, with a shortcuts panel.
- **Export of the site's data for an agent.** The catalogue was always a static JSON file, but it is now an explicit download in the sidebar and in the About page.

The other correction is scope: Karpathy's "local" was a VPS with hardening. This one is a local Docker image (`read_only`, caps dropped, healthcheck, CSP) rather than a hardened public box.

## 3. Verification with the judge

Claims were fixed before measuring, then run through the judge on the harvested records. Full output: `data/verify.json`, rendered in the app at `#/about`.

| Claim | Result | Measurement |
|---|---|---|
| There is still a corpus to rebuild from | **pass** | 1,098 archived rows → 815 of 1,084 checked still playable (75%); 269 dead links dropped |
| the judge can replace the taxonomy the archive lost | **pass** | 61% agreement with the 2008 tags across 822 videos; the disagreements are mostly editorial drift |
| Classroom-readiness discriminates | **pass** | 39% below 0.40, 49% in 0.40–0.60, 11% above 0.60; σ = 0.15 |
| the judge separates safe from distressing footage | **pass** | benign 0.46 vs distressing 0.25 (gap 0.21, 3-run average); strict per-item 6/8 |

Caveats worth stating plainly:

- The gap is measured on 4+4 hand-labelled videos. It is a sanity check, not a benchmark.
- Subject agreement is 61%, not higher, mostly because the 2008 tags are genuinely wrong in places (a diamagnetism demo filed under *animals & wildlife*). Agreement is a floor, not a ceiling.
- One real false negative: an Attenborough nature film scored 0.32 on classroom-readiness. The judgment is a *signal*, so the UI exposes it as a badge and an optional filter, never a hard gate.
- Single-run judgments move by ±0.05. Anything that needs precision averages runs.

## 4. Build plan

```
pipeline/harvest_listing.py  Wayback CDX → /en/category/* tables → data/listing.jsonl
pipeline/enrich.py           YouTube oEmbed → alive?, channel, canonical thumb
pipeline/thumbs.py           probe hq720 / hqdefault so the UI never 404s
pipeline/judge.py            the judge ask (4 questions, 1 call per video) → data/judgments.jsonl
pipeline/build_catalog.py    join → site/data/catalog.json
pipeline/verify_claims.py    the four claims above → site/data/verify.json
site/                        vanilla JS YouTube-style shell, no build step
```

Runtime rules: one request at a time against the archive (it throttles bursts), 4–6 parallel against YouTube and the judge.

UI scope: home grid, watch page with click-to-play embed, subject hubs, channel pages, search, typed filters (subject / level / classroom-ready), sort, and an `#/about` page that shows the pipeline and the verification table.

## 4b. Fidelity audit (the judge, second pass)

Second pass after reading the original: each requirement quoted from the post, evidence
measured from the running container, adjudicated by the judge (3 runs averaged, threshold 0.60).

| Requirement (from the post) | the judge p | Status |
|---|---|---|
| 50% frame instead of uploaded thumbnail | 0.87 | met (663 of 670) |
| For You, no accounts, local session | 0.89 | met (10/10 Physics after three Physics watches) |
| Keyboard shortcuts | 0.93 | met (`?` panel, j/k, Enter, `/`, watch-page j/k) |
| Export for an agent | 0.81 | met (self-describing file, 18 documented fields, provenance) |
| LLM semantic pass, spam removed | 0.62 | met after fix (149 records dropped by three rules) |
| Quality content instead of slop | 0.55 | **not met**: curation inherited from 2008–2021 |
| Clone over a curated corpus | 0.59 | **not met**: corpus is a catalogue, not HN comments |
| Deployed, secured, hardened | 0.10 | **not met**: local Docker by request, no domain or TLS |

Overall verdict: *"matches the pattern with documented substitutions"*, confidence 0.89.

The first run scored the semantic pass at 0.52 and exposed a real gap: the judge's judgments were
ranking spam down, not removing it. Fixed with a three-rule filter (`promotional >= 0.60`;
`classroom < 0.30 and evergreen < 0.50`; `index == 0 and promotional >= 0.40`), which dropped
149 records: 76 ads, 51 not-a-lesson clips, 22 editorially-worthless ones.

## 4c. Slop pass

The first drafts carried the usual tells: em dashes used as rhetorical connectors, gradient
headline text, a glowing status dot, emoji ticks, a radial background wash. `pipeline/audit_slop.py`
extracts every dash in authored copy and has the judge classify it three ways.

First run: 43 dashes, 17 judged AI connective (for example "This feed is built from what you
open, and it lives in this browser — no account…"). All 43 were rewritten out, along with the
placeholders (`—` became `n/a`) and the decorative glyphs. Second run: 0 dashes, 0 flagged,
0 lexicon hits. Quoted material keeps its punctuation; only my own sentences changed.

## 4d. Section parity with the site as it stands

`pipeline/extract_site.py` walks edutube.org's live sections (14 of them) and records what each
one contains. `pipeline/audit_parity.py` then asks the judge two questions per section, majority of
three runs: is there an equivalent here, and should there be?

| Section | Coverage | Needed |
|---|---|---|
| Home, About, category browse, search, item page | adapted | search and item page essential |
| Blog | missing | not applicable: its posts are lorem ipsum |
| Genre browse, platform browse | missing | not applicable: videos have one platform and no genre taxonomy |
| Download links, comments | missing | not applicable: media is not hosted, accounts do not exist |

Result: 6/10 covered, 0 required gaps. Two things came out of it as product changes: the item
page is now judged separately from its game-only extras, and educational level now carries the
age band it implies (Primary shows as ages 5-11).

## 5. What cannot be reproduced

- **The old look.** Only the data survived; the shell is new.
- **View counts.** The archive stored views/day, not totals; the UI says "views/day" rather than inventing a total.
- **The original ordering.** The blend used here (editorial index + reach + classroom readiness) is a new editorial decision.

## 6. Status

Built, containerised, and running locally:

```
docker compose up -d --build
open http://127.0.0.1:8765
```

nginx:1.27-alpine, read-only rootfs, caps dropped, healthcheck, CSP limited to `i.ytimg.com`
and `youtube-nocookie.com`. 670 videos · 427 channels · 14 subjects · 663 mid-frame thumbnails ·
149 spam records removed · 269 dead links dropped.
Playwright audit against the container: 0 console errors, 0 horizontal overflow at 1440 px and
414 px, embed boots, For You and the shortcuts panel behave.
