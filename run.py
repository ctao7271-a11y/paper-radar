#!/usr/bin/env python3
"""paper-radar daily pipeline.

  python3 run.py                 # fetch new papers since last run, resolve affiliations, rebuild site + digest
  python3 run.py --rebuild       # only rebuild site + digest from the store (e.g. after editing zh_summaries.json)
  python3 run.py --sync URL      # first merge a published store (raw papers.json URL) into the local store
  python3 run.py --mark-sent     # record the current digest as sent (so tomorrow's digest only has newer papers)
  python3 run.py --no-pdf        # skip PDF affiliation parsing (faster, lower coverage)
"""
import os, sys, json, argparse, datetime as dt, time, traceback
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from radar import config as C, arxiv, affil, summarize, site, digest, interest, publish

DATA = os.path.join(ROOT, "data")
STORE = os.path.join(DATA, "papers.json")
STATE = os.path.join(DATA, "state.json")
ZH = os.path.join(DATA, "zh_summaries.json")
REJECT = os.path.join(DATA, "rejected_ids.json")
DIGESTED = os.path.join(DATA, "digested_ids.json")   # local only (gitignored)
LOG = os.path.join(DATA, "run.log")
UTC = dt.timezone.utc

CN = dt.timezone(dt.timedelta(hours=8))

def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default

def save(path, obj):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)

_logf = None
def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    if _logf:
        _logf.write(msg + "\n"); _logf.flush()

def now_utc():
    return dt.datetime.now(UTC)

def fetch(store, state, reject, candidates_file=""):
    last = state.get("last_run")
    end = now_utc() + dt.timedelta(hours=1)
    if last:
        start = dt.datetime.fromisoformat(last) - dt.timedelta(days=C.OVERLAP_DAYS)
    else:
        start = end - dt.timedelta(days=C.FIRST_RUN_DAYS)
    seen = {}
    # 1) today's announcements via RSS (cheap, reliable)
    try:
        for p in arxiv.rss(log=log):
            seen.setdefault(p["id"], p)
    except Exception as e:
        log(f"RSS failed: {e}")
    # 2) API search over the date window (backfill gaps / first run). Best effort: arXiv rate-limits (HTTP 429).
    gap = (not last) or (now_utc() - dt.datetime.fromisoformat(last) > dt.timedelta(hours=30)) or not seen
    if candidates_file:
        for aid, p in load(candidates_file, {}).items():
            if aid not in seen or seen[aid].get("src") == "rss":
                seen[aid] = p
        log(f"Loaded candidates from {candidates_file}")
    elif gap:
        log(f"API backfill window (UTC): {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M}")
        for name, q in C.QUERIES.items():
            try:
                for p in arxiv.search(q, start, end, log=log):
                    if p["id"] not in seen or seen[p["id"]].get("src") == "rss":
                        seen[p["id"]] = p   # API metadata (submission date, comments) beats RSS
            except Exception as e:
                log(f"  API query {name} failed: {e} (continuing)")
    new = []
    for aid, p in seen.items():
        if aid in store or aid in reject:
            continue
        topics, score = arxiv.classify(p)
        if topics:
            new.append(p)
    arxiv.enrich(new, log=log)
    out = []
    for p in new:
        topics, score = arxiv.classify(p)
        if not topics:
            continue
        p["topics"], p["score"] = topics, score
        p["tags"] = arxiv.tags_zh(p, topics)
        p["venue"] = arxiv.venue(p)
        p["key_en"] = summarize.key_sentence(p["abstract"])
        p["first_seen"] = now_utc().isoformat(timespec="seconds")
        out.append(p)
    log(f"Fetched {len(seen)} candidates, {len(out)} new on-topic "
        f"(cockpit {sum('cockpit' in p['topics'] for p in out)}, embodied {sum('embodied' in p['topics'] for p in out)}, "
        f"edge/agents {sum('edge' in p['topics'] for p in out)})")
    return out

def backfill_cockpit(store, reject, days):
    """One-off: search the last `days` days for cockpit papers the daily feed never saw.
    Backfilled papers keep their arXiv date as first_seen and carry backfill=True, so they appear on the site
    but are never mailed and never become a day's picks."""
    end = now_utc() + dt.timedelta(hours=1)
    start = end - dt.timedelta(days=days)
    log(f"Cockpit backfill window (UTC): {start:%Y-%m-%d} → {end:%Y-%m-%d}")
    seen = {}
    for name in ("cockpit_kw", "cockpit_hci", "cockpit_title"):
        try:
            for p in arxiv.search(C.QUERIES[name], start, end, cap=4000, log=log):
                seen.setdefault(p["id"], p)
        except Exception as e:
            log(f"  backfill query {name} failed: {e}")
    cand = [p for aid, p in seen.items() if aid not in store and aid not in reject and "cockpit" in arxiv.classify(p)[0]]
    arxiv.enrich(cand, log=log)
    out = []
    for p in cand:
        topics, score = arxiv.classify(p)
        if "cockpit" not in topics:
            continue
        p["topics"], p["score"] = topics, score
        p["tags"] = arxiv.tags_zh(p, topics)
        p["venue"] = arxiv.venue(p)
        p["key_en"] = summarize.key_sentence(p["abstract"])
        p["first_seen"] = dt.datetime.fromisoformat(p["published"].replace("Z", "+00:00")).isoformat(timespec="seconds")
        p["backfill"] = True
        out.append(p)
    log(f"Backfill: {len(seen)} candidates, {len(out)} new cockpit papers")
    return out

def resolve_affils(papers, allow_pdf=True, label="new"):
    t0 = time.time()
    for i, p in enumerate(papers, 1):
        try:
            affil.resolve(p, log=log, allow_pdf=allow_pdf)
        except Exception as e:
            log(f"  affil error {p['id']}: {e}")
        if i % 25 == 0:
            log(f"  affiliations {label}: {i}/{len(papers)} ({time.time()-t0:.0f}s)")
        if p.get("flag"):
            log(f"  ★ {p['id']} {','.join(p['flag'])}: {p['title'][:70]}")

def recheck(store, allow_pdf=True):
    """Re-try recent papers whose affiliations are pending or whose flagged authors are unknown."""
    cutoff = now_utc() - dt.timedelta(days=C.RECHECK_DAYS)
    todo = []
    for p in store.values():
        af = p.get("affil") or {}
        if dt.datetime.fromisoformat(p["first_seen"]) < cutoff or af.get("tries", 0) >= 8:
            continue
        pending = af.get("status", "pending") == "pending"
        unknown_who = any(len(v) == 0 for v in af.get("schools", {}).values()) and "openalex" not in af.get("sources", [])
        if pending or unknown_who:
            todo.append(p)
    if todo:
        log(f"Re-checking {len(todo)} recent papers with unresolved affiliations")
        resolve_affils(todo, allow_pdf=allow_pdf, label="recheck")

def sync(store, url):
    import requests
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": C.USER_AGENT})
        r.raise_for_status()
        remote = r.json()
    except Exception as e:
        log(f"Sync skipped ({e})")
        return
    added = 0
    for aid, p in remote.items():
        if aid not in store:
            store[aid] = p; added += 1
        else:  # keep the better-resolved / summarized copy
            loc = store[aid]
            if p.get("pick") and not loc.get("pick"):
                loc["pick"] = p["pick"]
            if p.get("zh_summary") and not loc.get("zh_summary"):
                loc["zh_summary"] = p["zh_summary"]
            if len(p.get("affil", {}).get("sources", [])) > len(loc.get("affil", {}).get("sources", [])):
                loc["affil"], loc["flag"] = p["affil"], p.get("flag", [])
    # the published site is authoritative for picks of any day it already has picks for
    rdays = {p["pick"]["date"] for p in remote.values() if p.get("pick")}
    for aid, p in store.items():
        rp = remote.get(aid, {}).get("pick")
        if p.get("pick", {}).get("date") in rdays and not rp:
            p.pop("pick", None)
        elif rp:
            p["pick"] = rp
    log(f"Synced {added} papers from {url}")

def mark_sent():
    cur = load(os.path.join(ROOT, "out-digest", "latest.json"), {})
    done = set(load(DIGESTED, []))
    done |= set(cur.get("ids", []))
    save(DIGESTED, sorted(done))
    log(f"Marked {len(cur.get('ids', []))} papers as sent")

def publish_digest(push=True):
    """Write today's digest to <repo>/site/digest/, commit + push (GitHub Pages redeploys), then mark sent.
    Marking happens at publish time: if the mail script fails that day the papers are not mailed again,
    but the last 7 days stay readable at <site>/digest/YYYY-MM-DD.json."""
    import subprocess
    today = now_utc().astimezone(CN).date().isoformat()
    repo = os.environ.get("PAPER_RADAR_REPO", os.path.join(ROOT, "repo-bundle"))
    git = lambda *args: subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if push:
        git("pull", "-q", "--rebase", "origin", "main")
    r = publish.write(os.path.join(ROOT, "out-digest"), os.path.join(repo, "site"), today)
    if not r["published"]:
        log(f"Digest not published: {r['reason']}")
        return 0
    publish.write(os.path.join(ROOT, "out-digest"), os.path.join(ROOT, "site"), today)   # keep the local copy in step
    log(f"Digest {r['id']} written: {r['count']} papers · {r['subject']}")
    if not push:
        return 0
    git("add", "site/digest")
    if git("diff", "--cached", "--quiet").returncode != 0:
        c = git("-c", "user.name=paper-radar", "-c", "user.email=paper-radar@users.noreply.github.com",
                "commit", "-qm", f"digest {today}")
        if c.returncode != 0:
            log("commit failed: " + c.stderr[-500:]); return 1
    for i in range(3):
        p = git("push", "-q", "origin", "HEAD:main")
        if p.returncode == 0:
            break
        log(f"push failed (try {i + 1}): {p.stderr[-300:]}")
        git("pull", "-q", "--rebase", "origin", "main"); time.sleep(5)
    else:
        log("Digest NOT pushed; not marking sent"); return 1
    log(f"Digest pushed ({git('rev-parse', '--short', 'HEAD').stdout.strip()}); the site redeploys in ~1-2 min")
    mark_sent()
    return 0

def main():
    global _logf
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--sync", default="")
    ap.add_argument("--mark-sent", action="store_true")
    ap.add_argument("--publish-digest", action="store_true", help="put today's digest on the site (digest/latest.json), push, then mark sent")
    ap.add_argument("--no-push", action="store_true", help="with --publish-digest: write files only (no git, no mark-sent)")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--no-digest", action="store_true")
    ap.add_argument("--reseed-picks", action="store_true", help="recompute the whole picks archive (per submission day)")
    ap.add_argument("--candidates", default="", help="(debug) extra candidate JSON {id: paper} to merge")
    ap.add_argument("--backfill-cockpit", type=int, default=0, metavar="DAYS", help="one-off cockpit backfill (site only, never mailed)")
    a = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    _logf = open(LOG, "a", encoding="utf-8")
    log(f"===== run {now_utc().isoformat(timespec='seconds')} args={vars(a)}")

    store, state = load(STORE, {}), load(STATE, {})
    reject = set(load(REJECT, []))

    if a.mark_sent:
        mark_sent()
        return
    if a.publish_digest:
        sys.exit(publish_digest(push=not a.no_push))

    if a.sync:
        sync(store, a.sync)

    if a.backfill_cockpit:
        bf = backfill_cockpit(store, reject, a.backfill_cockpit)
        resolve_affils(bf, allow_pdf=not a.no_pdf, label="backfill")
        for p in bf:
            store[p["id"]] = p
        done = set(load(DIGESTED, []))   # archived: never mailed
        save(DIGESTED, sorted(done | {p["id"] for p in bf}))
        a.rebuild = True

    new_ids = []
    if not a.rebuild:
        new = fetch(store, state, reject, a.candidates)
        resolve_affils(new, allow_pdf=not a.no_pdf)
        for p in new:
            store[p["id"]] = p
        new_ids = [p["id"] for p in new]
        recheck(store, allow_pdf=not a.no_pdf)
        state["last_run"] = now_utc().isoformat(timespec="seconds")
        state.setdefault("runs", []).append({"at": state["last_run"], "new": len(new),
                                            "flagged": sum(bool(p.get("flag")) for p in new)})
        state["runs"] = state["runs"][-60:]

    if a.rebuild:  # re-apply the (possibly updated) classifier to the stored papers
        for aid in list(store):
            topics, score = arxiv.classify(store[aid])
            if not topics:
                log(f"  no longer on-topic, removed: {aid} {store[aid]['title'][:60]}")
                del store[aid]
            else:
                store[aid]["topics"], store[aid]["score"] = topics, score
                store[aid]["tags"] = arxiv.tags_zh(store[aid], topics)
    # apply reviewed Chinese summaries + rejections
    zh = load(ZH, {})
    for aid in list(store):
        if aid in reject:
            del store[aid]
        elif aid in zh:
            store[aid]["zh_summary"] = zh[aid]
    # research-interest relevance score + practicality signals (rule-based)
    for p in store.values():
        p["interest"] = interest.analyze(p)
    if not any(p.get("pick") for p in store.values()) or a.reseed_picks:
        # one-off: seed the picks archive for the backlog, one pick set per arXiv submission day
        byday = {}
        for p in store.values():
            p.pop("pick", None)
            d = dt.datetime.fromisoformat(p["published"].replace("Z", "+00:00")).astimezone(CN).date().isoformat()
            byday.setdefault(d, []).append(p["id"])
        for d in sorted(byday):
            if len(byday[d]) >= 5:
                interest.assign(store, d, byday[d], log=log)
    elif new_ids:
        interest.assign(store, now_utc().astimezone(CN).date().isoformat(), new_ids, log=log)
    for p in store.values():  # refresh reason text (e.g. after a Chinese summary was added)
        if p.get("pick"):
            p["pick"].update(interest.reasons(p, p["interest"]))
    save(STORE, store)
    save(STATE, state)

    site.build(store, state, os.path.join(ROOT, "site"))
    log(f"Site rebuilt: {len(store)} papers")
    if not a.no_digest:
        digested = set(load(DIGESTED, []))
        info = digest.build(store, digested, os.path.join(ROOT, "out-digest"))
        log(f"Digest: {info['n']} papers ({info['flagged']} flagged) -> out-digest/latest.html")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(traceback.format_exc())
        sys.exit(1)
