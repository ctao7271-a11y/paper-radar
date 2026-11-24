"""arXiv API fetching + local topic classification."""
import time, re, datetime as dt, urllib.parse
import xml.etree.ElementTree as ET
import requests
from . import config as C

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}
_last = [0.0]

def _get(params, tries=8):
    for i in range(tries):
        r = None
        wait = 3.1 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = requests.get(API, params=params, headers={"User-Agent": C.USER_AGENT}, timeout=60)
            if r.status_code == 200 and "<feed" in r.text:
                return r.text
            ra = r.headers.get("Retry-After", "")
            delay = int(ra) if ra.isdigit() else 20 * (i + 1)
        except requests.RequestException:
            delay = 10 * (i + 1)
        print(f"    arXiv API retry {i+1}/{tries}: {locals().get('r').status_code if locals().get('r') is not None else 'net-error'}; waiting {min(delay,180)}s", flush=True)
        time.sleep(min(delay, 180))
    raise RuntimeError(f"arXiv API failed for {params.get('search_query','')[:80]}")

def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def parse_feed(xml):
    root = ET.fromstring(xml)
    total = int(root.findtext("os:totalResults", "0", NS))
    out = []
    for e in root.findall("a:entry", NS):
        raw_id = e.findtext("a:id", "", NS)
        m = re.search(r"abs/([^v]+)(v\d+)?$", raw_id)
        if not m:
            continue
        aid = m.group(1)
        cats = [c.get("term") for c in e.findall("a:category", NS)]
        prim = e.find("arxiv:primary_category", NS)
        authors = []
        for a in e.findall("a:author", NS):
            authors.append({"name": _clean(a.findtext("a:name", "", NS)),
                            "affil_arxiv": [_clean(x.text) for x in a.findall("arxiv:affiliation", NS) if x.text]})
        out.append({
            "id": aid,
            "version": m.group(2) or "v1",
            "title": _clean(e.findtext("a:title", "", NS)),
            "abstract": _clean(e.findtext("a:summary", "", NS)),
            "authors": authors,
            "published": e.findtext("a:published", "", NS),
            "updated": e.findtext("a:updated", "", NS),
            "categories": cats,
            "primary": prim.get("term") if prim is not None else (cats[0] if cats else ""),
            "comment": _clean(e.findtext("arxiv:comment", "", NS)),
            "journal_ref": _clean(e.findtext("arxiv:journal_ref", "", NS)),
        })
    return total, out

def search(query, start_dt, end_dt, page=200, cap=3000, log=print):
    rng = f"submittedDate:[{start_dt:%Y%m%d%H%M} TO {end_dt:%Y%m%d%H%M}]"
    q = f"({query}) AND {rng}"
    res, start = [], 0
    while True:
        xml = _get({"search_query": q, "start": start, "max_results": page, "sortBy": "submittedDate", "sortOrder": "descending"})
        total, items = parse_feed(xml)
        res.extend(items)
        start += page
        if not items or start >= total or start >= cap:
            break
    log(f"  arXiv query {query[:50]!r}…: {len(res)} / total {total}")
    return res

# ---------------------------------------------------------------- classification
def classify(p):
    """Return (topics:list, score:dict). topics ⊆ {'cockpit','embodied','edge'}"""
    text = f"{p['title']}. {p['abstract']}"
    title = p["title"]
    topics, score = [], {}

    # --- cockpit
    cs = len(set(m.group(0).lower() for m in C.COCKPIT_STRONG.finditer(text)))
    cs_title = bool(C.COCKPIT_STRONG.search(title))
    veh = len(C.COCKPIT_VEHICLE.findall(text))
    ai = len(set(m.group(0).lower() for m in C.COCKPIT_AI.finditer(text)))
    excl = bool(C.COCKPIT_EXCLUDE.search(text))
    stack = len(C.DRIVING_STACK.findall(text))
    # sentence-level co-occurrence of occupant term + human-state/interaction term
    co = 0
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if C.COCKPIT_OCC.search(sent) and C.COCKPIT_HUMAN.search(sent):
            co += 1
    co_title = bool(C.COCKPIT_OCC.search(title) and C.COCKPIT_HUMAN.search(title))
    c_ok = False
    if cs >= 1 and not (excl and cs < 2 and not cs_title):
        c_ok = cs_title or cs >= 2 or stack == 0 or (co >= 2 and stack <= 1)   # one weak cockpit phrase inside a driving-stack paper is not enough
    elif not excl and (co_title or co >= 2) and stack <= 2:
        c_ok = True
    score["cockpit"] = cs * 3 + (2 if cs_title else 0) + min(co, 4) + (2 if co_title else 0) + min(ai, 4) * 0.5
    if c_ok:
        topics.append("cockpit")

    # --- embodied
    es_all = [m.group(0).lower() for m in C.EMB_STRONG.finditer(text)]
    es = set(es_all)
    es_title = bool(C.EMB_STRONG.search(title))
    robot = len(C.EMB_ROBOT.findall(text))
    learn = len(C.EMB_LEARN.findall(text))
    driving = len(C.DRIVING.findall(text))
    weak_only = es and es <= {"grasp", "grasping", "tactile", "teleoperation", "embodiment", "embodiments", "legged robot",
                              "legged robots", "quadruped", "quadrupeds", "sim-to-real", "sim2real", "robot arm", "robot arms",
                              "robotic arm", "robotic arms", "physical ai"}
    e_ok = False
    if es_title and not weak_only:
        e_ok = True
    elif es_title and weak_only:
        e_ok = robot >= 2 and learn >= 1
    elif len(es_all) >= 2 and not weak_only:
        e_ok = robot >= 1 or learn >= 1
    elif len(es_all) >= 1:
        e_ok = robot >= 2 and learn >= 1
    if not e_ok and "cs.RO" in p["categories"]:
        rl = len(C.EMB_RO_LEARN.findall(text))
        classic = len(C.EMB_CLASSIC.findall(text))
        wm = bool(C.EMB_WM.search(text))
        e_ok = ((wm and len(C.EMB_ACT.findall(text)) >= 2) or (len(es_all) >= 1 and rl >= 1) or (robot >= 2 and rl >= 2)) and classic <= 1
    elif not e_ok and C.EMB_WM.search(title) and (robot >= 1 or len(C.EMB_ACT.findall(text)) >= 3):
        e_ok = True
    if not any(c.startswith(("cs.", "eess.")) for c in p["categories"]) or p["primary"] in ("cs.LO", "cs.SE", "cs.CR", "cs.DB"):
        e_ok = False
    if e_ok and C.EMB_EXCLUDE.search(title) and robot < 2:
        e_ok = False
    # driving papers: keep only VLA / world-model ones (tagged 自动驾驶) – plain driving-stack papers are out
    if e_ok and driving >= 2 and robot == 0 and not C.EMB_DRIVING_OK.search(text):
        e_ok = False
    score["embodied"] = (1.5 if C.EMB_WM.search(text) else 0) + len(es) * 2 + (2 if es_title else 0) + min(robot, 5) * 0.3 + min(learn, 3) * 0.5
    if e_ok:
        topics.append("embodied")

    # --- edge: on-device deployment / compression on device chips, agent memory, cross-device agents
    tgt = set(m.group(0).lower() for m in C.EDGE_TARGET.finditer(text))
    tgt_title = bool(C.EDGE_TARGET.search(title))
    eff = len(set(m.group(0).lower() for m in C.EDGE_EFF.finditer(text)))
    net = len(C.EDGE_NET_EXCLUDE.findall(text))
    agent = len(C.AGENT.findall(text))
    mem_sents = sum(1 for s in re.split(r"(?<=[.!?])\s+", text) if C.AGENT_MEM.search(s) and C.AGENT.search(s))
    mem_title = bool(C.AGENT_MEM.search(title)) and agent >= 1
    xdev = len(C.CROSS_DEVICE.findall(text))
    d_ok = False
    model = len(set(m.group(0).lower() for m in C.EDGE_MODEL.finditer(text)))
    if tgt and net <= 1 and model >= 1:
        d_ok = (tgt_title and eff >= 1) or (len(tgt) >= 2 and eff >= 2) or (len(tgt) >= 1 and eff >= 3 and bool(C.EDGE_EFF.search(title)))
    if not d_ok and (mem_title or mem_sents >= 2) and agent >= 2:
        d_ok = True
    if not d_ok and xdev >= 1 and agent >= 1 and net <= 1 and (tgt or C.CROSS_DEVICE.search(title)):
        d_ok = True
    if not any(c.startswith(("cs.", "eess.")) for c in p["categories"]) or p["primary"] in ("cs.LO", "cs.CR", "cs.DB", "cs.NI", "cs.IT", "eess.SP"):
        d_ok = False
    score["edge"] = len(tgt) * 2 + (2 if tgt_title else 0) + min(eff, 5) * 0.5 + min(mem_sents, 3) * 1.5 + (2 if mem_title else 0) + min(xdev, 2) * 2
    if d_ok:
        topics.append("edge")
    return topics, score

def tags_zh(p, topics):
    text = f"{p['title']}. {p['abstract']}"
    out = []
    for rx, tag, topic in C.TAGS:
        if topic and topic not in topics:
            continue
        if rx.search(text) and tag not in out:
            out.append(tag)
    return out[:6]

def venue(p):
    m = C.VENUES.search(p.get("comment", "") + " " + p.get("journal_ref", ""))
    return m.group(1) if m else ""

# ---------------------------------------------------------------- RSS (daily announcements; light on rate limits)
RSS_CATS = ["cs.RO", "cs.AI", "cs.CV", "cs.CL", "cs.HC", "cs.LG", "cs.MA", "eess.SY", "cs.SD", "eess.AS", "cs.MM", "eess.IV", "cs.AR", "cs.DC", "cs.PF", "eess.SP"]

def rss(cats=RSS_CATS, log=print):
    from email.utils import parsedate_to_datetime
    url = "https://rss.arxiv.org/rss/" + "+".join(cats)
    xml = None
    for i in range(4):
        try:
            r = requests.get(url, headers={"User-Agent": C.USER_AGENT}, timeout=90)
            if r.status_code == 200 and "<rss" in r.text[:500]:
                xml = r.text
                break
        except requests.RequestException:
            pass
        time.sleep(15 * (i + 1))
    if xml is None:
        raise RuntimeError("arXiv RSS unavailable")
    root = ET.fromstring(xml)
    ns = {"dc": "http://purl.org/dc/elements/1.1/", "arxiv": "http://arxiv.org/schemas/atom"}
    ch = root.find("channel")
    out = []
    for it in ch.findall("item"):
        atype = (it.findtext("arxiv:announce_type", "", ns) or "").strip()
        if atype not in ("new", "cross"):
            continue
        desc = it.findtext("description", "") or ""
        m = re.match(r"\s*arXiv:(\S+?)(v\d+)\s+Announce Type:\s*\S+\s*Abstract:\s*(.*)", desc, re.S)
        if not m:
            continue
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate", "")).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            pub = ""
        creators = it.findtext("dc:creator", "", ns) or ""
        names = [n.strip() for n in re.split(r",\s*(?:and\s+)?|\s+and\s+", creators) if n.strip()]
        cats = [c.text.strip() for c in it.findall("category") if c.text]
        out.append({"id": m.group(1), "version": m.group(2), "title": _clean(it.findtext("title", "")),
                    "abstract": _clean(m.group(3)), "authors": [{"name": n, "affil_arxiv": []} for n in names],
                    "published": pub, "updated": pub, "categories": cats, "primary": cats[0] if cats else "",
                    "comment": "", "journal_ref": "", "src": "rss"})
    log(f"  arXiv RSS: {len(out)} new/cross-listed announcements")
    return out

def enrich(papers, log=print):
    """Replace RSS metadata with full API metadata (submission date, comments, primary category). Best effort."""
    todo = [p for p in papers if p.get("src") == "rss"]
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        try:
            xml = _get({"id_list": ",".join(p["id"] for p in batch), "max_results": len(batch)}, tries=4)
            _, items = parse_feed(xml)
        except Exception as e:
            log(f"  metadata enrichment skipped ({e})")
            return
        by = {x["id"]: x for x in items}
        for p in batch:
            x = by.get(p["id"])
            if x:
                for k in ("title", "abstract", "authors", "published", "updated", "categories", "primary", "comment", "journal_ref"):
                    if x.get(k):
                        p[k] = x[k]
                p["src"] = "rss+api"
