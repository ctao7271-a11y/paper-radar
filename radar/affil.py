"""Author-affiliation resolution for Tsinghua / PKU / Beihang.

Order of evidence:
  1. arXiv <arxiv:affiliation> (rarely present)
  2. First page of the PDF (pdftotext) – header (before Abstract) + footnotes/emails
  3. OpenAlex authorships (institution ids + raw affiliation strings) – precise per-author, but lags days/weeks
Result stored on paper["affil"] = {status, schools:{key:[author names]}, evidence:[...], sources:[...]}.
status: 'pdf' | 'openalex' | 'pdf+openalex' | 'pending' (nothing could be fetched yet)
"""
import os, re, subprocess, time, unicodedata, json
import requests
from . import config as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT_CACHE = os.path.join(ROOT, "cache", "pdf_text")
os.makedirs(TXT_CACHE, exist_ok=True)

MARK = r"[0-9, \t∗*†‡§¶♯♮♭⋆★✉#&∥‖♠♡♣♢♦♥◇◆○●△▲\u2020\u2021\u00a7\u00b6\u2217\u22c6\u2605\u2709]"

def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

# ---------------------------------------------------------------- PDF
_last_pdf = [0.0]
def pdf_text(aid, version="", log=print, layout=False):
    fn = os.path.join(TXT_CACHE, aid.replace("/", "_") + ".txt")
    fl = os.path.join(TXT_CACHE, aid.replace("/", "_") + ".layout.txt")
    want = fl if layout else fn
    if os.path.exists(want) and os.path.getsize(want) > 200:
        return open(want, encoding="utf-8", errors="ignore").read()
    wait = 1.0 - (time.time() - _last_pdf[0])
    if wait > 0:
        time.sleep(wait)
    _last_pdf[0] = time.time()
    url = f"https://arxiv.org/pdf/{aid}{version or ''}"
    try:
        r = requests.get(url, headers={"User-Agent": C.USER_AGENT}, timeout=90)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            log(f"    pdf {aid}: HTTP {r.status_code}")
            return ""
        tmp = fn + ".pdf"
        open(tmp, "wb").write(r.content)
        # first two pages: page 1 holds header+footnotes; page 2 catches long author lists
        out = subprocess.run(["pdftotext", "-l", "2", "-enc", "UTF-8", tmp, "-"], capture_output=True, timeout=60)
        lay = subprocess.run(["pdftotext", "-l", "1", "-layout", "-enc", "UTF-8", tmp, "-"], capture_output=True, timeout=60)
        os.remove(tmp)
        txt = out.stdout.decode("utf-8", "ignore")
        ltxt = lay.stdout.decode("utf-8", "ignore")
        if len(txt) > 200:
            open(fn, "w", encoding="utf-8").write(txt)
        if len(ltxt) > 200:
            open(fl, "w", encoding="utf-8").write(ltxt)
        return ltxt if layout else txt
    except Exception as e:  # network / pdftotext errors -> retry on a later run
        log(f"    pdf {aid}: {e}")
        return ""

def _split_pages(txt):
    pages = txt.split("\f")
    return pages[0], (pages[1] if len(pages) > 1 else "")

def _header(page1):
    m = re.search(r"\n\s*(?:Abstract|ABSTRACT|A\s?B\s?S\s?T\s?R\s?A\s?C\s?T|Abstract[—\-:.])", page1)
    return page1[: m.start()] if m and m.start() > 40 else page1[:2500]

def _affil_lines(text, school):
    """Lines that mention the school (strong pattern, or weak pattern if inside header text)."""
    out = []
    for line in text.splitlines():
        if C.SCHOOL_FALSE.search(line):
            line = C.SCHOOL_FALSE.sub(" ", line)
        if C.SCHOOLS[school]["strong"].search(line):
            out.append(line.strip())
    return out

def _markers_for(line, school, rx=None):
    """Markers (digits / symbols) attached to the school's affiliation in a line like
    '1 Tsinghua University 2 Peking University' or '∗Tsinghua University'."""
    rx = rx or C.SCHOOLS[school]["strong"]
    marks = set()
    # split line into segments that start with a marker
    segs = re.split(r"(?:(?<=\s)|^|(?<=[,;.]))((?:\d{1,2}|[∗*†‡§¶♯⋆★]))\s*(?=[A-Z\u4e00-\u9fff])", line)
    # segs = [pre, mark1, text1, mark2, text2, ...]
    for i in range(1, len(segs) - 1, 2):
        if rx.search(segs[i + 1]):
            marks.add(segs[i])
    # "Tsinghua University 2 Peking University" — leading segment lost its marker (printed on another line)
    if len(segs) >= 3 and rx.search(segs[0]) and segs[1].isdigit() and int(segs[1]) > 1 and len(segs[0]) < 120:
        marks.add(str(int(segs[1]) - 1))
    return marks

def _name_variants(name):
    n = _norm(name).strip()
    parts = [p for p in re.split(r"\s+", n) if p]
    vs = {n}
    if len(parts) >= 2:
        vs.add(f"{parts[-1]} {' '.join(parts[:-1])}")       # Chinese order
        vs.add(f"{parts[0][0]}. {parts[-1]}")               # initial
        vs.add(" ".join(parts[:-1]) + "-" + parts[-1])
    return [v for v in vs if len(v) >= 4]

def _author_marks(text, name):
    t = _norm(text)
    for v in _name_variants(name):
        pat = re.escape(v).replace(r"\ ", r"[\s\-]+")
        m = re.search(pat + r"\s*((?:" + MARK + r"){1,12})", t)
        if m:
            raw = m.group(1)
            return set(re.findall(r"\d{1,2}|[∗*†‡§¶♯⋆★♠♡♣♢♦♥◇◆○●△▲]", raw)), True
        if re.search(pat, t):
            return set(), True
    return set(), False

def _sentence_mentions(text, name, school):
    """IEEE footnote style: 'X and Y are with the Department ..., Tsinghua University'."""
    t = _norm(text)
    found = False
    for sent in re.split(r"(?<=[.;])\s+(?=[A-Z])|\n\s*\n", t):
        if len(sent) < 600 and re.search(r"\b(?:is|are) (?:with|affiliated with|at|from)\b", sent) and C.SCHOOLS[school]["strong"].search(sent):
            for v in _name_variants(name):
                if re.search(re.escape(v).replace(r"\ ", r"[\s\-]+"), sent):
                    found = True
    return found

SYM = "∗*†‡§¶♯⋆★♠♡♣♢♦♥◇◆○●△▲"

def layout_markers(ltxt, key):
    """In `pdftotext -layout` output superscript markers sit on the line above the affiliation,
    at (roughly) the column where the affiliation starts."""
    page = ltxt.split("\f")[0]
    head = _header(page)
    lines = head.splitlines()
    s = C.SCHOOLS[key]
    rx = re.compile(s["strong"].pattern + "|" + s["weak"].pattern)
    marks = set()
    for i, l in enumerate(lines):
        for m in rx.finditer(C.SCHOOL_FALSE.sub(lambda x: " " * len(x.group(0)), l)):
            # the chunk (text separated by >=3 spaces) containing the match
            start = m.start()
            while start > 0 and l[max(0, start - 3):start] != "   ":
                start -= 1
            end = l.find("   ", m.end())
            chunk = l[start:end if end > 0 else len(l)]
            r = _markers_for(chunk.strip(), key, rx)
            if r:
                marks |= r; continue
            if re.match(r"\s*(?:\d{1,2}|[" + SYM + r"])", chunk):
                continue  # chunk starts with a marker belonging to another institution
            cend = end if end > 0 else len(l)
            got = False
            pi = i - 1
            while pi >= 0 and not lines[pi].strip():
                pi -= 1
            if pi >= 0:
                best = None
                for pc in re.finditer(r"\S(?:.*?\S)?(?=\s{3,}|$)", lines[pi]):
                    ov = min(pc.end(), cend) - max(pc.start(), start)
                    txt = pc.group(0)
                    if ov > 0 and re.match(r"(?:\d{1,2}|[" + SYM + r"])\s*[A-Z]", txt) and not rx.search(txt) \
                            and len(txt) > 8 and not re.search(r"(?i)universit|大学", txt) and (best is None or ov > best[0]):
                        best = (ov, re.match(r"(\d{1,2}|[" + SYM + r"])", txt).group(1))
                if best:
                    marks.add(best[1]); got = True
            if got:
                continue
            # marker on the previous non-empty line(s), near the chunk start column
            for j in range(i - 1, max(-1, i - 3), -1):
                prev = lines[j]
                if not prev.strip():
                    continue
                if not re.fullmatch(r"[\s\d" + SYM + r"]+", prev):
                    break
                best = None
                for t in re.finditer(r"\d{1,2}|[" + SYM + r"]", prev):
                    d = start - t.start()
                    if -3 <= d <= 8 and (best is None or abs(d) < abs(best[0])):
                        best = (d, t.group(0))
                if best:
                    marks.add(best[1])
                break
    return marks

INST = re.compile(r"(?i)universit|institute|college|laborator|academy|company|inc\.|ltd|corporation|school of|department|大学|研究院")

def from_pdf(p, txt, ltxt=""):
    """Return (schools{key: [names]}, evidence[str], unresolved_schools[set])."""
    page1, page2 = _split_pages(txt)
    head = _header(page1)
    region = page1
    schools, evidence = {}, []
    names = [a["name"] for a in p["authors"]]
    for key, s in C.SCHOOLS.items():
        clean_head = C.SCHOOL_FALSE.sub(" ", head)
        clean_p1 = C.SCHOOL_FALSE.sub(" ", region)
        hit_strong = bool(s["strong"].search(clean_p1))
        hit_weak_head = bool(s["weak"].search(clean_head))
        # long author lists sometimes spill affiliations onto page 2 before the intro
        if not hit_strong and len(names) > 15 and s["strong"].search(C.SCHOOL_FALSE.sub(" ", page2[:3000])):
            hit_strong = True
            region = page1 + "\n" + page2[:3000]
        if not (hit_strong or hit_weak_head):
            continue
        lines = _affil_lines(region, key) or [l.strip() for l in head.splitlines() if s["weak"].search(l)]
        evidence.append(f"{s['full_zh']}: " + " | ".join(l[:160] for l in lines[:2]))
        marks = set()
        both = re.compile(s["strong"].pattern + "|" + s["weak"].pattern, re.I if False else 0)
        head_lines = set(l.strip() for l in head.splitlines())
        for l in lines:
            marks |= _markers_for(l, key, both if l in head_lines else None)
        # marker lines may be on their own line: "1" newline "Tsinghua University" (fallback only:
        # stacked "3\n4\n5\nTsinghua University" is ambiguous, the -layout text resolves it by column)
        own = set()
        for m in re.finditer(r"(?m)^\s*(\d{1,2}|[∗*†‡§¶])\s*$\n\s*([^\n]+)", region):
            own |= _markers_for(f"{m.group(1)} {m.group(2)}", key, both if m.start() < len(head) else None)
        lay = layout_markers(ltxt, key) if ltxt else set()
        marks |= lay if lay else own
        # symbols (∗ † ‡) usually mean equal contribution / corresponding author: ignore them when digit markers exist
        if any(x.isdigit() for x in marks) or re.search(r"[A-Za-z]\d(?:,\d)*[\s,]", head):
            marks = {x for x in marks if x.isdigit() or x in "♠♡♣♢♦♥◇◆○●△▲"}
        who = []
        for n in names:
            am, present = _author_marks(region, n)
            if marks and am & marks:
                who.append(n)
            elif _sentence_mentions(region, n, key):
                who.append(n)
        # every affiliation line in the header belongs to this school -> all authors
        if not who:
            aff_lines = [l for l in head.splitlines() if INST.search(l)]
            if aff_lines and all(s["strong"].search(l) for l in aff_lines) and \
               not any(INST.search(s["strong"].sub(" ", seg)) for l in aff_lines for seg in re.split(r"\s\d\s|;", l) if not s["strong"].search(seg)):
                who = list(names)
        # e-mail heuristic: liyong07@tsinghua.edu.cn -> "Yong Li"
        dom = {"tsinghua": r"tsinghua\.edu\.cn", "pku": r"pku\.edu\.cn", "buaa": r"buaa\.edu\.cn"}[key]
        emails = re.findall(r"([A-Za-z0-9._\-{},\s]+)@(?:[a-z0-9\-]+\.)*" + dom, region)
        locals_ = []
        for e in emails:
            locals_ += [x.strip().lower() for x in re.split(r"[{},\s]+", e) if x.strip()]
        for n in names:
            parts = [x.lower() for x in re.split(r"[\s\-]+", _norm(n)) if x]
            if len(parts) < 2 or n in who:
                continue
            cands = {parts[-1] + "".join(parts[:-1]), "".join(parts[:-1]) + parts[-1], parts[0][0] + parts[-1], parts[-1] + parts[0][0]}
            if any(re.sub(r"[\d._\-]", "", l) in cands or any(re.sub(r"[\d._\-]", "", l).startswith(c) and len(c) >= 5 for c in cands) for l in locals_):
                who.append(n)
        schools[key] = who
    return schools, evidence

# ---------------------------------------------------------------- OpenAlex
_last_oa = [0.0]
def openalex(aid):
    wait = 0.15 - (time.time() - _last_oa[0])
    if wait > 0:
        time.sleep(wait)
    _last_oa[0] = time.time()
    url = f"https://api.openalex.org/works/doi:10.48550/arXiv.{aid}"
    try:
        r = requests.get(url, params={"mailto": C.OPENALEX_MAILTO}, headers={"User-Agent": C.USER_AGENT}, timeout=30)
        if r.status_code != 200:
            return None
        d = r.json()
    except Exception:
        return None
    if not d.get("authorships"):
        return None
    res = {"schools": {}, "any_inst": False}
    for a in d["authorships"]:
        name = a.get("author", {}).get("display_name") or a.get("raw_author_name", "")
        insts = a.get("institutions") or []
        raw = " ; ".join(a.get("raw_affiliation_strings") or [])
        if insts or raw:
            res["any_inst"] = True
        for key in C.SCHOOLS:
            hit = any(i.get("id", "").rsplit("/", 1)[-1] == oid for i in insts for oid, k in C.OPENALEX_IDS.items() if k == key) \
                  or any(oid in [x.rsplit("/", 1)[-1] for x in (i.get("lineage") or [])] for i in insts for oid, k in C.OPENALEX_IDS.items() if k == key) \
                  or bool(C.SCHOOLS[key]["strong"].search(C.SCHOOL_FALSE.sub(" ", raw)))
            if hit:
                res["schools"].setdefault(key, []).append(name)
    return res

def _match_name(oa_name, arxiv_names):
    a = _norm(oa_name).lower().replace("-", " ").split()
    for n in arxiv_names:
        b = _norm(n).lower().replace("-", " ").split()
        if set(a) == set(b) or (a and b and a[-1] == b[-1] and a[0][0] == b[0][0]) or (a and b and a[0] == b[-1] and a[-1] == b[0]):
            return n
    return oa_name

# ---------------------------------------------------------------- main entry
def resolve(p, log=print, allow_pdf=True):
    names = [a["name"] for a in p["authors"]]
    af = p.get("affil") or {"status": "pending", "schools": {}, "evidence": [], "sources": [], "tries": 0}
    af["tries"] = af.get("tries", 0) + 1
    schools = {k: list(v) for k, v in af.get("schools", {}).items()}
    sources = set(af.get("sources", []))
    evidence = list(af.get("evidence", []))

    # 1. arXiv-provided affiliations
    for a in p["authors"]:
        for s in a.get("affil_arxiv", []):
            for key, sc in C.SCHOOLS.items():
                if sc["strong"].search(s) or sc["weak"].search(s):
                    schools.setdefault(key, [])
                    if a["name"] not in schools[key]:
                        schools[key].append(a["name"])
                    sources.add("arxiv")

    # 2. PDF
    if allow_pdf and "pdf" not in sources:
        txt = pdf_text(p["id"], p.get("version", ""), log=log)
        if txt:
            sources.add("pdf")
            ltxt = pdf_text(p["id"], p.get("version", ""), log=log, layout=True)
            s2, ev = from_pdf(p, txt, ltxt)
            evidence += ev
            for k, who in s2.items():
                cur = schools.setdefault(k, [])
                for w in who:
                    if w not in cur:
                        cur.append(w)

    # 3. OpenAlex — per-author institutions, but for fresh arXiv papers it lags and sometimes copies every
    #    institution to every author. So it only (a) fills schools whose authors the PDF could not pin down,
    #    or (b) adds a school when no PDF text was available.
    need_oa = "openalex" not in sources and ("pdf" not in sources or any(len(v) == 0 for v in schools.values()))
    if need_oa:
        oa = openalex(p["id"])
        if oa and oa["any_inst"]:
            sources.add("openalex")
            for k, who in oa["schools"].items():
                mapped = []
                for w in who:
                    w2 = _match_name(w, names)
                    if w2 not in mapped:
                        mapped.append(w2)
                if len(mapped) == len(names) and len(names) > 3:
                    mapped = []          # "everyone at every institution" pattern: keep the school, not the names
                if "pdf" in sources and k not in schools:
                    continue             # PDF text exists and does not mention this school -> trust the PDF
                cur = schools.setdefault(k, [])
                if not cur:
                    cur.extend(mapped)
    status = "+".join(s for s in ["arxiv", "pdf", "openalex"] if s in sources) or "pending"
    af.update({"status": status, "schools": schools, "evidence": evidence[:6], "sources": sorted(sources)})
    p["affil"] = af
    p["flag"] = sorted(schools.keys(), key=list(C.SCHOOLS).index)
    return p
