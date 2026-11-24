"""Static site builder. Output: site/index.html, site/app.js, site/style.css, site/data/*.json"""
import os, json, datetime as dt, shutil
from . import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

def slim(p):
    af = p.get("affil", {})
    return {
        "id": p["id"],
        "t": p["title"],
        "au": [a["name"] for a in p["authors"]],
        "d": p["published"][:10],
        "fs": p.get("first_seen", "")[:10],
        "tp": p.get("topics", []),
        "fl": {k: v for k, v in af.get("schools", {}).items()},
        "src": af.get("status", "pending"),
        "zh": p.get("zh_summary", ""),
        "en": p.get("key_en", ""),
        "ab": p.get("abstract", ""),
        "tg": p.get("tags", []),
        "v": p.get("venue", ""),
        "c": p.get("primary", ""),
        "r": p.get("interest", {}).get("rec", 0),
        "it": p.get("interest", {}).get("it", []),
        "sig": p.get("interest", {}).get("sig", []),
        "th": int(p.get("interest", {}).get("theory", False)),
        "pk": p.get("pick") or None,
        "s": round(max(p.get("score", {}).get(t, 0) for t in p.get("topics", ["x"])) if p.get("topics") else 0, 1),
    }

def build(store, state, out):
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    import hashlib
    for f in ("app.js", "style.css", "favicon.svg", "supabase-2.119.2.js"):
        shutil.copy(os.path.join(ASSETS, f), os.path.join(out, f))
    for f in os.listdir(out):   # stale vendored library versions
        if f.startswith("supabase-") and f.endswith(".js") and not os.path.exists(os.path.join(ASSETS, f)):
            os.remove(os.path.join(out, f))
    ver = hashlib.md5((open(os.path.join(ASSETS, "app.js"), "rb").read() + open(os.path.join(ASSETS, "style.css"), "rb").read())).hexdigest()[:8]
    html = open(os.path.join(ASSETS, "index.html"), encoding="utf-8").read()
    html = html.replace('href="style.css"', f'href="style.css?v={ver}"').replace('src="app.js"', f'src="app.js?v={ver}"')
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(out, ".nojekyll"), "w").close()
    months = {}
    for p in store.values():
        months.setdefault(p["published"][:7], []).append(slim(p))
    manifest = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "months": [],
                "total": len(store),
                "counts": {"cockpit": sum("cockpit" in p.get("topics", []) for p in store.values()),
                           "embodied": sum("embodied" in p.get("topics", []) for p in store.values()),
                           "edge": sum("edge" in p.get("topics", []) for p in store.values()),
                           "picks": sum(bool(p.get("pick")) for p in store.values()),
                           "flagged": sum(bool(p.get("flag")) for p in store.values())},
                "last_run": state.get("last_run", "")}
    keep = set()
    for m in sorted(months, reverse=True):
        items = sorted(months[m], key=lambda x: (x["d"], x["r"]), reverse=True)
        fn = f"{m}.json"
        keep.add(fn)
        json.dump(items, open(os.path.join(out, "data", fn), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        manifest["months"].append({"m": m, "file": fn, "n": len(items)})
    for f in os.listdir(os.path.join(out, "data")):
        if f.endswith(".json") and f not in keep and f not in ("manifest.json", "picks.json"):
            os.remove(os.path.join(out, "data", f))
    # cumulative top-picks archive (all days, newest first) – loaded independently of the monthly files
    picks = sorted((slim(p) for p in store.values() if p.get("pick")), key=lambda x: (x["pk"]["date"], -x["pk"]["rank"]), reverse=True)
    json.dump(picks, open(os.path.join(out, "data", "picks.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    manifest["pick_days"] = sorted({x["pk"]["date"] for x in picks}, reverse=True)
    json.dump(manifest, open(os.path.join(out, "data", "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
