"""Offline tests for radar/publish.py (digest JSON for the Apps Script mailer).  Run: python3 tests/test_publish.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radar import publish

def digest(d, date, ids):
    json.dump({"subject": f"论文雷达 {date}：{len(ids)} 篇", "date": date, "ids": ids, "flagged": ids[:1], "picks": [{}],
               "counts": {"cockpit": 0, "embodied": len(ids), "edge": 0}, "site": "https://example.org/"},
              open(os.path.join(d, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False)
    open(os.path.join(d, "latest.html"), "w", encoding="utf-8").write(f"<p>{date}</p>")
    open(os.path.join(d, "latest.txt"), "w", encoding="utf-8").write(f"text {date}")

def main():
    with tempfile.TemporaryDirectory() as dg, tempfile.TemporaryDirectory() as site:
        out = os.path.join(site, "digest")
        latest = lambda: json.load(open(os.path.join(out, "latest.json"), encoding="utf-8"))
        # 1. normal day
        digest(dg, "2026-11-26", ["2611.00001", "2611.00002"])
        r = publish.write(dg, site, "2026-11-26")
        assert r["published"] and r["id"] == "2026-11-26" and r["count"] == 2, r
        L = latest()
        assert set(L) >= {"date", "id", "subject", "html", "text", "count"}, L.keys()
        assert (L["date"], L["id"], L["count"], L["html"], L["text"]) == ("2026-11-26", "2026-11-26", 2, "<p>2026-11-26</p>", "text 2026-11-26")
        assert os.path.exists(os.path.join(out, "2026-11-26.json"))
        # 2. empty day (weekend): latest.json untouched, so the mailer sends nothing new
        digest(dg, "2026-11-28", [])
        r = publish.write(dg, site, "2026-11-28")
        assert not r["published"] and latest()["date"] == "2026-11-26", r
        # 3. stale digest (not regenerated today) is never published under today's date
        digest(dg, "2026-11-26", ["2611.00003"])
        r = publish.write(dg, site, "2026-11-27")
        assert not r["published"] and latest()["date"] == "2026-11-26", r
        # 4. re-publishing the same day keeps the same id (mailer will not resend)
        digest(dg, "2026-11-26", ["2611.00001", "2611.00002", "2611.00004"])
        assert publish.write(dg, site, "2026-11-26")["id"] == "2026-11-26" and latest()["count"] == 3
        # 5. only the last 7 days are kept; index.json lists them newest first
        for day in range(1, 12):
            date = f"2026-12-{day:02d}"; digest(dg, date, ["2612.00001"]); publish.write(dg, site, date)
        days = sorted(f for f in os.listdir(out) if f.startswith("2026-"))
        assert days == [f"2026-12-{d:02d}.json" for d in range(5, 12)], days
        idx = json.load(open(os.path.join(out, "index.json"), encoding="utf-8"))
        assert [x["date"] for x in idx] == [f"2026-12-{d:02d}" for d in range(11, 4, -1)], idx
        assert latest()["id"] == "2026-12-11"
    print("test_publish: all 5 checks passed")

if __name__ == "__main__":
    main()
