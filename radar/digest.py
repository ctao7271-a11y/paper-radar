"""Daily e-mail digest (Chinese). Writes out-digest/latest.html, latest.txt, latest.json (+ dated copies)."""
import os, json, re, html, datetime as dt
from . import config as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCH = {k: v["zh"] for k, v in C.SCHOOLS.items()}
SCH_COLOR = {"tsinghua": ("#6b21a8", "#f3e8ff"), "pku": ("#9f1239", "#ffe4e6"), "buaa": ("#1d4ed8", "#dbeafe")}
TOPIC = {"cockpit": "智能座舱", "embodied": "具身智能", "edge": "端侧·智能体"}
CN = dt.timezone(dt.timedelta(hours=8))
MAX_OTHER = {"cockpit": 8, "embodied": 10, "edge": 8}   # non-flagged papers in the mail; the rest are on the site
MAX_PICKS = 5
NEW_WINDOW_DAYS = 4  # never e-mail papers first seen more than this many days ago

def site_url():
    try:
        return json.load(open(os.path.join(ROOT, "data", "site.json")))["url"]
    except Exception:
        return ""

def notable(p):
    """Relevance = research-interest score + practicality signals (radar/interest.py); legacy fallback."""
    if "interest" in p:
        return p["interest"]["rec"]
    s = max(p.get("score", {}).get(t, 0) for t in p["topics"])
    if p.get("venue"):
        s += 3
    if re.search(r"github\.com|project page|code (?:is|will be) (?:available|released)|open-?source", p.get("abstract", "") + p.get("comment", ""), re.I):
        s += 1.5
    return s

def one_line(p):
    if p.get("zh_summary"):
        return p["zh_summary"]
    tags = "、".join(p.get("tags", [])[:4])
    key = p.get("key_en", "")
    return (f"[{tags}] " if tags else "") + key

def authors_str(p, hl):
    names = [a["name"] for a in p["authors"]]
    shown = names[:6] + [n for n in names[6:] if n in hl]
    s = ", ".join(shown)
    if len(names) > len(shown):
        s += f" 等{len(names)}人"
    return s

def build(store, digested, out):
    os.makedirs(out, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=NEW_WINDOW_DAYS)
    new = [p for aid, p in store.items() if aid not in digested and not p.get("backfill")
           and dt.datetime.fromisoformat(p["first_seen"]) >= cutoff]   # backfilled older papers: site only, never mailed
    pool = [p for p in new if p.get("pick") and "interest" in p]
    if len(pool) > MAX_PICKS:   # several pick days unsent (e.g. after a weekend): keep the best, with topic variety
        from . import interest
        pool = [p for p, _ in interest.select([(p, p["interest"]) for p in pool])]
    picks = sorted(pool, key=lambda p: (-notable(p), p["id"]))[:MAX_PICKS]
    pick_ids = {p["id"] for p in picks}
    flagged_all = [p for p in new if p.get("flag")]
    flagged = sorted([p for p in flagged_all if p["id"] not in pick_ids], key=lambda p: (-len(p["flag"]), -notable(p)))
    others, placed = {}, set(pick_ids)
    for t in ("cockpit", "edge", "embodied"):
        pool = [p for p in new if t in p["topics"] and not p.get("flag") and p["id"] not in placed]
        others[t] = sorted(pool, key=notable, reverse=True)[: MAX_OTHER[t]]
        placed |= {p["id"] for p in others[t]}
    cnt = {t: sum(t in p["topics"] for p in new) for t in TOPIC}
    url = site_url()
    today = now.astimezone(CN)
    date_s = f"{today:%Y-%m-%d}"
    subject = (f"论文雷达 {today.month}月{today.day}日：" + (f"重点推荐 {len(picks)} 篇 · " if picks else "")
               + f"座舱 {cnt['cockpit']} · 具身 {cnt['embodied']} · 端侧/智能体 {cnt['edge']} · 清北航 {len(flagged_all)} 篇")

    # ---------- HTML (inline styles for mail clients)
    E = html.escape
    def badge(k, who):
        fg, bg = SCH_COLOR[k]
        names = "、".join(who[:5]) + (f" 等{len(who)}人" if len(who) > 5 else "") if who else "作者待确认"
        return (f'<span style="display:inline-block;background:{bg};color:{fg};font-weight:600;font-size:12px;'
                f'padding:2px 7px;border-radius:5px;margin:0 6px 4px 0">{SCH[k]} · {E(names)}</span>')
    def topic_pill(t):
        fg, bg = {"cockpit": ("#0f766e", "#ccfbf1"), "embodied": ("#b45309", "#fef3c7"), "edge": ("#4338ca", "#e0e7ff")}[t]
        return f'<span style="display:inline-block;background:{bg};color:{fg};font-size:12px;padding:2px 7px;border-radius:5px;margin:0 6px 4px 0">{TOPIC[t]}</span>'
    def item(p, show_badges):
        hl = set(n for v in p.get("affil", {}).get("schools", {}).values() for n in v)
        au = E(authors_str(p, hl))
        for n in sorted(hl, key=len, reverse=True):
            au = au.replace(E(n), f'<b style="color:#0f172a">{E(n)}</b>')
        b = "".join(badge(k, p["affil"]["schools"][k]) for k in p.get("flag", [])) if show_badges else ""
        v = f' <span style="color:#64748b;font-size:12px">· {E(p["venue"])}</span>' if p.get("venue") else ""
        return (f'<tr><td style="padding:10px 0;border-bottom:1px solid #e2e8f0">'
                f'<div>{"".join(topic_pill(t) for t in p["topics"])}{b}</div>'
                f'<div style="font-size:15px;font-weight:600;line-height:1.45;margin:2px 0">'
                f'<a href="https://arxiv.org/abs/{p["id"]}" style="color:#0f172a;text-decoration:none">{E(p["title"])}</a>{v}</div>'
                f'<div style="font-size:12.5px;color:#64748b;margin:2px 0">{au}</div>'
                f'<div style="font-size:13.5px;color:#334155;margin:4px 0;line-height:1.55">{E(one_line(p))}</div>'
                f'<div style="font-size:12.5px"><a href="https://arxiv.org/abs/{p["id"]}" style="color:#0369a1">arXiv</a> · '
                f'<a href="https://arxiv.org/pdf/{p["id"]}" style="color:#0369a1">PDF</a></div></td></tr>')
    def pick_item(p):
        k = p["pick"]
        hl = set(n for v in p.get("affil", {}).get("schools", {}).values() for n in v)
        au = E(authors_str(p, hl))
        for n in sorted(hl, key=len, reverse=True):
            au = au.replace(E(n), f'<b style="color:#0f172a">{E(n)}</b>')
        b = "".join(badge(x, p["affil"]["schools"][x]) for x in p.get("flag", []))
        row = lambda lab, txt: (f'<tr><td style="vertical-align:top;color:#c2410c;font-weight:600;font-size:12.5px;white-space:nowrap;padding:2px 10px 2px 0">{lab}</td>'
                                f'<td style="font-size:13.5px;color:#334155;line-height:1.55;padding:2px 0">{E(txt)}</td></tr>')
        return (f'<tr><td style="padding:10px 0;border-bottom:1px solid #fed7aa">'
                f'<div>{"".join(topic_pill(t) for t in p["topics"])}{b}</div>'
                f'<div style="font-size:15px;font-weight:600;line-height:1.45;margin:2px 0">'
                f'<a href="https://arxiv.org/abs/{p["id"]}" style="color:#0f172a;text-decoration:none">{E(p["title"])}</a></div>'
                f'<div style="font-size:12.5px;color:#64748b;margin:2px 0">{au}</div>'
                f'<div style="font-size:14px;font-weight:600;color:#7c2d12;margin:6px 0 4px">一句话：{E(k["line"])}</div>'
                f'<table role="presentation" cellspacing="0" cellpadding="0">{row("解决什么", k["solve"])}{row("为什么可落地", k["why"])}{row("可以用来做", k["use"])}</table>'
                f'<div style="font-size:12.5px;margin-top:4px"><a href="https://arxiv.org/abs/{p["id"]}" style="color:#0369a1">arXiv</a> · '
                f'<a href="https://arxiv.org/pdf/{p["id"]}" style="color:#0369a1">PDF</a></div></td></tr>')
    def section(title, items, show_badges=False, note=""):
        if not items:
            return ""
        return (f'<h2 style="font-size:16px;margin:22px 0 4px;color:#0f172a">{title}</h2>'
                + (f'<div style="font-size:12.5px;color:#64748b">{note}</div>' if note else "")
                + '<table role="presentation" width="100%" cellspacing="0" cellpadding="0">' + "".join(item(p, show_badges) for p in items) + "</table>")

    link = f'<a href="{E(url)}" style="color:#0369a1">{E(url)}</a>' if url else "（网站地址待配置）"
    body = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{E(subject)}</title></head>",
        '<body style="margin:0;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'PingFang SC\',\'Microsoft YaHei\',Arial,sans-serif;color:#0f172a">',
        '<div style="max-width:680px;margin:0 auto;background:#ffffff;padding:20px 22px">',
        f'<div style="font-size:12px;color:#64748b">Paper Radar · {date_s}</div>',
        f'<h1 style="font-size:20px;margin:4px 0 10px">座舱、具身与端侧智能 · 今日新论文</h1>',
        '<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;margin:6px 0 4px"><tr>'
        + "".join(f'<td style="background:#f1f5f9;border-radius:8px;padding:8px 6px;text-align:center;width:25%">'
                  f'<div style="font-size:20px;font-weight:700">{n}</div><div style="font-size:12px;color:#64748b">{lab}</div></td>'
                  f'<td style="width:6px"></td>'
                  for n, lab in [(cnt["cockpit"], "智能座舱"), (cnt["embodied"], "具身智能"), (cnt["edge"], "端侧·智能体"), (len(flagged_all), "清华/北大/北航")])
        + "</tr></table>",
        (f'<p style="font-size:13px;color:#334155;margin:8px 0 0">网站（全部论文、筛选）：{link}</p>' if url else ""),
    ]
    if not new:
        body.append('<p style="font-size:14px;color:#334155">今天没有新的相关论文（arXiv 周末不发布新论文）。</p>')
    if picks:
        body.append('<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:4px 14px 6px;margin-top:16px">'
                    f'<h2 style="font-size:16px;margin:10px 0 2px;color:#7c2d12">★ 重点推荐（{len(picks)}）</h2>'
                    '<div style="font-size:12.5px;color:#64748b">按研究兴趣（端侧部署、模型压缩、智能体记忆、跨设备、座舱、具身）与可落地程度（开源代码、真机实验、效率数据）自动挑选。</div>'
                    '<table role="presentation" width="100%" cellspacing="0" cellpadding="0">' + "".join(pick_item(p) for p in picks) + "</table></div>")
    n_fp = len(flagged_all) - len(flagged)
    body.append(section(f"清华 / 北大 / 北航作者论文（{len(flagged_all)}）", flagged, True,
                        "机构信息自动解析自论文 PDF 首页与 OpenAlex，加粗为对应学校的作者。"
                        + (f"其中 {n_fp} 篇已列入上方重点推荐。" if n_fp else "")))
    def more_note(t):
        n_rest = sum(t in p["topics"] and not p.get("flag") and p["id"] not in pick_ids for p in new)
        if n_rest <= len(others[t]):
            return ""
        return (f"本批{TOPIC[t]}方向非清北航论文共 {n_rest} 篇，以下按相关度挑选 {len(others[t])} 篇；"
                f"其余 {n_rest - len(others[t])} 篇（含与其他方向重复的）见网站{('：' + link) if url else ''}。")
    body.append(section("其他值得关注 · 智能座舱", others["cockpit"], note=more_note("cockpit")))
    body.append(section("其他值得关注 · 端侧部署与智能体", others["edge"], note=more_note("edge")))
    body.append(section("其他值得关注 · 具身智能", others["embodied"], note=more_note("embodied")))
    body.append(f'<p style="font-size:13px;color:#334155;margin-top:22px">完整列表、往期重点推荐与筛选（座舱/具身/端侧、仅看清北航）：{link}</p>')
    body.append('<p style="font-size:11.5px;color:#94a3b8">本邮件由论文追踪脚本自动生成，数据来自 arXiv。“[标签] + 英文句子”为摘要原文中的关键句；推荐理由由规则与中文简介自动生成，仅供快速筛选。</p>')
    body.append("</div></body></html>")
    h = "\n".join(x for x in body if x)

    # ---------- plain text
    T = [subject, "", f"智能座舱 {cnt['cockpit']} 篇｜具身智能 {cnt['embodied']} 篇｜端侧·智能体 {cnt['edge']} 篇｜清华/北大/北航 {len(flagged_all)} 篇", f"网站：{url}" if url else "", ""]
    if picks:
        T.append(f"【★ 重点推荐】({len(picks)})")
        for p in picks:
            k = p["pick"]
            sch = "；".join(f"{SCH[x]}：" + ("、".join(p['affil']['schools'][x][:6]) or "作者待确认") for x in p.get("flag", []))
            T += [f"- {p['title']}" + (f"（{sch}）" if sch else ""), f"  一句话：{k['line']}", f"  解决什么：{k['solve']}",
                  f"  为什么可落地：{k['why']}", f"  可以用来做：{k['use']}", f"  https://arxiv.org/abs/{p['id']}"]
        T.append("")
    def titem(p, show):
        line = [f"- {p['title']}"]
        if show:
            def nm(w):
                return ("、".join(w[:6]) + (f" 等{len(w)}人" if len(w) > 6 else "")) if w else "作者待确认"
            line.append("  " + "；".join(f"{SCH[k]}：{nm(p['affil']['schools'][k])}" for k in p["flag"]))
        line.append(f"  {one_line(p)}")
        line.append(f"  https://arxiv.org/abs/{p['id']}")
        return "\n".join(line)
    if flagged:
        T += [f"【清华/北大/北航作者论文】({len(flagged_all)}" + (f"，另有 {len(flagged_all) - len(flagged)} 篇见重点推荐" if len(flagged_all) > len(flagged) else "") + ")"] + [titem(p, True) for p in flagged] + [""]
    for t in ("cockpit", "edge", "embodied"):
        if others[t]:
            n_rest = sum(t in p["topics"] and not p.get("flag") and p["id"] not in pick_ids for p in new)
            hdr = f"【其他值得关注 · {TOPIC[t]}】" + (f"（共 {n_rest} 篇，列出 {len(others[t])} 篇，其余见网站）" if n_rest > len(others[t]) else "")
            T += [hdr] + [titem(p, False) for p in others[t]] + [""]
    T.append(f"完整列表：{url or '（网站地址待配置）'}")
    txt = "\n".join(T)

    ids = [p["id"] for p in new]
    for name in ("latest", date_s):
        open(os.path.join(out, f"{name}.html"), "w", encoding="utf-8").write(h)
        open(os.path.join(out, f"{name}.txt"), "w", encoding="utf-8").write(txt)
    json.dump({"subject": subject, "date": date_s, "ids": ids, "flagged": [p["id"] for p in flagged_all],
               "picks": [{"id": p["id"], "title": p["title"], "url": f"https://arxiv.org/abs/{p['id']}", "topics": p["topics"],
                          "schools": {x: p["affil"]["schools"][x] for x in p.get("flag", [])}, "rec": notable(p), **p["pick"]} for p in picks],
               "counts": cnt, "site": url}, open(os.path.join(out, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"n": len(new), "flagged": len(flagged_all), "picks": len(picks), "subject": subject}
