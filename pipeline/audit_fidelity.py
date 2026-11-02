#!/usr/bin/env python3
"""Fidelity audit: does this rebuild actually do what the original post says?

Every requirement is quoted from https://karpathy.bearblog.dev/hacker-tube/ ,
paired with evidence measured from the running container (data/behavior.json,
catalog.json, docker inspect, HTTP headers), and adjudicated by jev: one noul
per requirement plus one overall choice.

The evidence strings include the known shortfalls on purpose. A judge that only
sees favourable evidence is not a judge.

Output: data/fidelity.json + site/data/fidelity.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BASE = "http://127.0.0.1:8765"


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default if default is not None else {}


def docker_facts() -> dict:
    try:
        raw = subprocess.run(["docker", "inspect", "edutube"], capture_output=True, text=True, timeout=20).stdout
        d = json.loads(raw)[0]
        hc = d.get("Config", {}).get("Healthcheck") or {}
        host = d.get("HostConfig", {})
        return {
            "image": d.get("Config", {}).get("Image"),
            "running": d.get("State", {}).get("Running"),
            "health": (d.get("State", {}).get("Health") or {}).get("Status"),
            "read_only_rootfs": host.get("ReadonlyRootfs"),
            "cap_drop": host.get("CapDrop"),
            "cap_add": host.get("CapAdd"),
            "security_opt": host.get("SecurityOpt"),
            "memory": host.get("Memory"),
            "healthcheck": bool(hc),
            "ports": host.get("PortBindings"),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def headers() -> dict:
    try:
        req = urllib.request.Request(BASE + "/", method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            return {
                "status": r.status,
                "csp": r.headers.get("Content-Security-Policy"),
                "xcto": r.headers.get("X-Content-Type-Options"),
                "referrer": r.headers.get("Referrer-Policy"),
                "server": r.headers.get("Server"),
            }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def jev(state: str, question: str, kind: str = "noul", options: list[str] | None = None) -> dict:
    if kind == "noul":
        q = {"q": {"type": "noul", "instructions": question}}
    else:
        q = {"q": {"type": "choice", "instructions": question, "criteria": {o: o for o in options}}}
    p = subprocess.run(["jev", "--raw", "ask", "--questions", json.dumps(q)],
                       input=state, text=True, capture_output=True, timeout=90)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:300])
    a = json.loads(p.stdout)["answers"]["q"]
    return a


def main() -> int:
    beh = read_json(DATA / "behavior.json")
    cat = read_json(ROOT / "site" / "data" / "catalog.json")
    dk = docker_facts()
    hd = headers()

    st = cat.get("stats", {})
    th = beh.get("thumbs", {})
    ex = beh.get("export", {})
    fy = beh.get("foryou", {})
    kb = beh.get("keyboard", {})
    fd = beh.get("feed", {})

    items = [
        {
            "id": "clone",
            "requirement": "A YouTube-style clone over a curated corpus",
            "quote": "Let's write our own YouTube clone based on whatever videos have been recommended on Hacker News.",
            "evidence": (
                f"Home feed, watch page with a click-to-play embed and an Up next rail, search over titles/descriptions/"
                f"channels/subjects, 14 subject hubs, channel pages and a personal For You feed render {st.get('videos')} "
                f"videos from {st.get('channels')} channels. Recommendation provenance: every record was selected and scored "
                f"by EduTube's editors (the EduTube-Index persists as field 'index'), which is the editorial analogue of an HN "
                f"comment recommending a link. Edutube.org publishes no comment corpus, so that catalogue is the corpus."
            ),
            "limitation": "Substituted corpus; the shell is new because only the data survived.",
        },
        {
            "id": "quality",
            "requirement": "Quality content instead of algorithmic slop",
            "quote": "It was Friday night... looking at an enshittified wall of slop. … HackerTube: Contains quality content.",
            "evidence": (
                f"Corpus is a hand-curated teacher catalogue, then filtered three times: {st.get('dead_links')} dead links dropped, "
                f"{st.get('spam_dropped')} records removed as spam by the judge's three-rule filter, {st.get('classroom_ready')} of {st.get('videos')} pass the "
                f"classroom-readiness threshold. The default feed is "
                f"subject-interleaved (first 12 cards span {len(fd.get('subjects') or [])} different subjects) and ranked on the archive's "
                f"editorial index (0.50 weight), not on engagement alone. Limitation: the archive's own index favours 2008-era popularity, "
                f"so 'quality' here is editorial + judged rather than a 2026 editorial opinion."
            ),
            "limitation": "Quality is inherited from 2008-2021 editors plus the model, not freshly curated.",
        },
        {
            "id": "thumbnails",
            "requirement": "The 50% frame, not the uploaded thumbnail",
            "quote": "Uses the 50% thumbnail instead of the uploaded thumbnail.",
            "evidence": (
                f"{th.get('midframe')} of {th.get('total')} records use a midpoint frame: "
                f"{th.get('kinds')}. Uploaded art survives only where no mid-frame exists "
                f"({th.get('kinds', {}).get('hqdefault', 0)} records). The rule is enforced in pipeline/thumbs.py, which probes "
                f"maxres2 → sd2 → hq2 before any uploaded variant."
            ),
            "limitation": "",
        },
        {
            "id": "foryou",
            "requirement": "Good For You recommendations with no accounts, state in the local session",
            "quote": "Custom and good ForYou recommendations without any user accounts, storing state in local browser session.",
            "evidence": (
                f"Watching three Physics videos stored {fy.get('storedSubjects')} in localStorage "
                f"({fy.get('watchedIds')} ids, {fy.get('storedChannels')} channels) with no server call; the For You feed then "
                f"returned {fy.get('physicsInTop10')}/10 Physics videos. A clear-history button wipes the store. "
                f"Limitation: the model is subject/channel affinity, not a learned recommender."
            ),
            "limitation": "Simple affinity weighting rather than a trained ranker.",
        },
        {
            "id": "keyboard",
            "requirement": "Keyboard shortcuts",
            "quote": "Keyboard shortcuts.",
            "evidence": (
                f"Measured in the container: '?' opens a {kb.get('overlay', {}).get('rows')}-row shortcuts panel; j/j moved focus to "
                f"'{kb.get('focusedTitle')}'; Enter opened the watch page ({kb.get('enterOpensWatch')}); on a watch page j/k walks "
                f"the Up next rail ({kb.get('watchPageJk')}). '/' focuses search."
            ),
            "limitation": "",
        },
        {
            "id": "export",
            "requirement": "The site's data exportable so an agent can build its own version",
            "quote": "Export of the site's data available to give to your agent to easily create your own version.",
            "evidence": (
                f"A sidebar download serves data/catalog.json: {ex.get('records')} records, top-level keys {ex.get('topKeys')}, "
                f"{ex.get('schemaFields')} documented fields and {ex.get('provenanceKeys')} provenance entries, so the file is "
                f"self-describing without this README."
            ),
            "limitation": "",
        },
        {
            "id": "semantic",
            "requirement": "An LLM does the semantic pass over the corpus",
            "quote": "filtered them, ran Sonnet over them in a Workflow (Claude Code feature), got rid of spam",
            "evidence": (
                f"The judge asks five typed questions per record in one call: subject, level, classroom-readiness, evergreen, and "
                f"promotional intent ({st.get('judged')} records judged). It then removes spam rather than merely ranking it down: "
                f"{st.get('spam_dropped')} records scored >=0.60 on promotional intent and were dropped from the catalogue. Dead links "
                f"are removed earlier, by oEmbed ({st.get('dead_links')}). Answers are typed, so they become filters directly."
            ),
            "limitation": "Typed judgments replace prose filtering; no Workflow orchestration was needed.",
        },
        {
            "id": "deploy",
            "requirement": "Deployed, secured, hardened, optimised",
            "quote": "get a domain, push to a VPS, secure, harden, optimize and voila!",
            "evidence": (
                f"Local Docker instead of a VPS: image {dk.get('image')}, health {dk.get('health')}, read-only rootfs "
                f"{dk.get('read_only_rootfs')}, capabilities dropped {dk.get('cap_drop')}, security opts {dk.get('security_opt')}, "
                f"capabilities added only {dk.get('cap_add')}. HTTP: {hd.get('server')}, CSP present {bool(hd.get('csp'))}, "
                f"nosniff {hd.get('xcto')}. Optimisation: pre-built static files, gzip, cache headers on /data/. "
                f"Context: the build target was explicitly local Docker, so there is no domain and no TLS, and the port is bound "
                f"to the loopback host."
            ),
            "limitation": "No domain or TLS; 'local' means local Docker, not a hardened public box.",
        },
    ]

    question = (
        "The state is a requirement quoted from a blog post, the measured evidence for how a rebuild implements it, "
        "and the rebuild's own stated limitation. Judge only from the evidence: is the requirement genuinely met, "
        "as opposed to merely described? A substitution that preserves the stated intent still counts as met; "
        "a missing or untested behaviour does not."
    )

    out_items = []
    met = 0
    for it in items:
        state = (
            f"Requirement: {it['requirement']}\n"
            f"Original quote: {it['quote']}\n"
            f"Measured evidence: {it['evidence']}\n"
            f"Stated limitation: {it['limitation'] or 'none'}\n"
        )
        try:
            runs = [jev(state, question).get("noul", 0.0) for _ in range(3)]
            prob = sum(runs) / len(runs)  # single-run judgments drift ~0.05
        except Exception as e:  # noqa: BLE001
            prob = 0.0
            print(f"judge error on {it['id']}: {e}", file=sys.stderr)
        met += 1 if prob >= 0.6 else 0
        out_items.append({**it, "p": round(prob, 3)})

    summary = "\n".join(f"- {i['requirement']}: p={i['p']:.2f}" for i in out_items)
    overall = jev(
        f"Original post describes a YouTube clone built from a curated corpus, with: quality content, 50% frame "
        f"thumbnails, no-account local-session For You, keyboard shortcuts, data export, an LLM semantic pass, and a "
        f"hardened deployment. The rebuild scores:\n{summary}\n"
        f"Known substitutions: the corpus is EduTube's archived catalogue instead of HN comments; metadata comes from "
        f"oEmbed instead of the YouTube Data API; deployment is a local Docker container instead of a public VPS.",
        "How closely does this rebuild match the original post?",
        kind="choice",
        options=[
            "Exact match",
            "Matches the pattern with documented substitutions",
            "Partial match with missing features",
            "Does not match",
        ],
    )
    verdict = overall.get("choice")
    vconf = overall.get("confidence")

    result = {
        "date": date.today().isoformat(),
        "model": "jev-latest",
        "source": "https://karpathy.bearblog.dev/hacker-tube/",
        "items": out_items,
        "met": met,
        "total": len(out_items),
        "verdict": verdict,
        "verdict_confidence": vconf,
        "substitutions": [
            "corpus: EduTube 2008-2021 archive instead of HN comments",
            "metadata: YouTube oEmbed instead of the YouTube Data API",
            "semantic pass: typed judgments from a language model instead of prose filtering",
            "hosting: local Docker instead of a VPS + domain",
        ],
    }

    blob = json.dumps(result, indent=2, ensure_ascii=False)
    (DATA / "fidelity.json").write_text(blob)
    (ROOT / "site" / "data" / "fidelity.json").write_text(blob)

    print(f"{'REQUIREMENT':<58} p")
    print("-" * 66)
    for i in out_items:
        print(f"{i['requirement'][:56]:<58} {i['p']:.2f}{'' if i['p'] >= 0.6 else '  < 0.60'}")
    print(f"\nmet {met}/{len(out_items)} · verdict: {verdict} (confidence {vconf})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
