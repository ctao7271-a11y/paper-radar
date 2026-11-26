"""Publish the day's email digest as a static JSON file on the GitHub Pages site.

The user's Google Apps Script fetches  <site>/digest/latest.json  and sends it from her own Gmail.
Files written into <site_dir>/digest/:
  latest.json        {date, id, subject, html, text, count, counts, flagged, picks, site, generated}
  YYYY-MM-DD.json    same content, last KEEP days (so a missed day can still be read)
  index.json         [{date, id, subject, count, file}]  newest first
Nothing is written when the digest is empty or not from today, so the script never sends twice.
"""
import os, json, datetime as dt

KEEP = 7

def write(digest_dir, site_dir, today, keep=KEEP):
    meta = json.load(open(os.path.join(digest_dir, "latest.json"), encoding="utf-8"))
    ids = meta.get("ids") or []
    if not ids:
        return {"published": False, "reason": "no new papers"}
    if meta.get("date") != today:
        return {"published": False, "reason": f"digest is for {meta.get('date')}, not today ({today})"}
    read = lambda ext: open(os.path.join(digest_dir, "latest." + ext), encoding="utf-8").read()
    obj = {"date": today, "id": today, "subject": meta["subject"], "html": read("html"), "text": read("txt"),
           "count": len(ids), "counts": meta.get("counts", {}), "flagged": len(meta.get("flagged", [])),
           "picks": len(meta.get("picks", [])), "site": meta.get("site", ""),
           "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    out = os.path.join(site_dir, "digest")
    os.makedirs(out, exist_ok=True)
    for fn in (f"{today}.json", "latest.json"):
        with open(os.path.join(out, fn), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    days = sorted((f for f in os.listdir(out) if len(f) == 15 and f[:4].isdigit() and f.endswith(".json")), reverse=True)
    for f in days[keep:]:
        os.remove(os.path.join(out, f))
    index = []
    for f in days[:keep]:
        d = json.load(open(os.path.join(out, f), encoding="utf-8"))
        index.append({"date": d["date"], "id": d["id"], "subject": d["subject"], "count": d["count"], "file": f})
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    return {"published": True, "id": today, "count": len(ids), "subject": meta["subject"]}
