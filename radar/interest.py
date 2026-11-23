"""Research-interest relevance score, practicality signals, top-pick selection and plain-Chinese reasons.

Everything here is rule-based (no LLM needed), so it runs unattended in GitHub Actions.
Interest areas (weights): on-device deployment & compression, agent memory / cross-device, cockpit interaction,
embodied AI; plus practicality signals (code, real hardware, efficiency numbers, deployment) and a mild
penalty for purely theoretical work (kept visible, just ranked lower).
"""
import re, datetime as dt
from . import config as C

def _rx(words):
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])", re.I)

# interest areas: key -> (label, weight, regex)
INTERESTS = {
    "edge":    ("端侧部署", 3.0, C.EDGE_TARGET),
    "compress":("模型压缩/加速", 2.5, _rx([r"quantiz\w*", r"low-?bit", r"pruning", r"model compression", r"knowledge distillation", r"distill\w* (?:into|to) (?:a )?(?:smaller|compact|lightweight|student)\w*", r"small (?:language |vision-language |multimodal )?models?",
                                          r"slms?", r"kv[- ]cache", r"speculative (?:decoding|inference|execution)", r"efficient inference", r"inference (?:acceleration|latency|speed|efficiency)",
                                          r"stall\w*", r"latency", r"lightweight", r"token pruning", r"early exit\w*", r"asynchronous inference"])),
    "memory":  ("智能体记忆", 3.0, C.AGENT_MEM),
    "xdevice": ("跨设备协同", 3.0, C.CROSS_DEVICE),
    "agent":   ("智能体", 1.5, _rx([r"agents?", r"agentic", r"tool[- ]use", r"tool-calling", r"function calling"])),
    "cockpit": ("座舱交互", 2.0, C.COCKPIT_STRONG),
    "vla":     ("VLA/具身大模型", 1.5, _rx([r"vision-language-action", r"vlas?", r"robot foundation models?", r"generalist (?:robot )?polic(?:y|ies)"])),
    "world":   ("世界模型", 1.0, _rx([r"world models?", r"world-action models?", r"wams?"])),
    "dex":     ("机器人操作", 1.0, _rx([r"manipulation", r"dexterous", r"grasp\w*", r"bimanual", r"tactile"])),
    "nav":     ("导航", 0.8, _rx([r"navigation", r"vln"])),
    "humanoid":("人形/足式", 0.8, _rx([r"humanoids?", r"quadrupeds?", r"legged", r"locomotion"])),
}
SIGNALS = {
    "code":   ("已开源/有项目页", 2.0, re.compile(r"github\.com|gitlab\.com|huggingface\.co|project page|project website|code (?:and \w+ )?(?:is|are|will be) (?:publicly )?(?:available|released)|open-?sourc\w*|we release|publicly available|released at|https?://", re.I)),
    "real":   ("真机/实车实验", 2.0, re.compile(r"real[- ]world (?:experiments?|robots?|deployment|tests?|evaluations?|tasks?|settings?|trials?|vehicles?|driving|data)|real robots?|physical robots?|real hardware|hardware experiments?|on a real|on real|real (?:vehicle|car)s?|on-road|road tests?|field (?:tests?|trials?|experiments?)|user stud(?:y|ies)|participants|commercial smartphones?|on (?:smartphones?|phones?|jetson\w*|orin)\b", re.I)),
    "numbers":("给出延迟/显存等数据", 1.5, re.compile(r"\d+(?:\.\d+)?\s?(?:ms|milliseconds?|hz|fps|gb|mb|w\b|watts?)|\d+(?:\.\d+)?\s?[x×]\s?(?:faster|speed-?up|lower|less|reduction|fewer)|speed-?up of|reduces? (?:latency|memory|inference)|(?:latency|memory|footprint|energy|power)[^.]{0,60}?\d+(?:\.\d+)?\s?%", re.I)),
    "deploy": ("面向部署", 1.5, re.compile(r"\b(?:deploy\w*|real-?time|on-?device|on-?board|edge (?:devices?|deployment|inference|hardware))\b", re.I)),
    "plug":   ("免训练/即插即用", 1.0, re.compile(r"training-free|plug-and-play|plug-in|without (?:any )?(?:re-?)?training|zero-shot|drop-in", re.I)),
    "open_model": ("基于开源模型", 0.5, re.compile(r"π_?\{?0\.?5\}?|pi0|openvla|gr00t|qwen|llama|internvl|deepseek|octo\b|rdt", re.I)),
}
THEORY = re.compile(r"\b(?:theorem|we prove|proof|provabl\w*|theoretical (?:analysis|framework|guarantees?)|convergence (?:rate|analysis|guarantee)|regret bound|upper bound|lower bound|lemma|asymptotic)", re.I)
EMPIRICAL = re.compile(r"experiment|real[- ]world|benchmark|evaluat|simulation|dataset", re.I)

def analyze(p):
    text = f"{p['title']}. {p['abstract']} {p.get('comment','')}"
    title = p["title"]
    it, score = [], 0.0
    for k, (lab, w, rx) in INTERESTS.items():
        found = [m.lower() for m in rx.findall(text)]
        n, distinct = len(found), len(set(found))
        hit_title = bool(rx.search(title))
        # incidental single mentions do not count: need the title, or repeated / varied mentions
        if (n >= 2 and (distinct >= 2 or k not in ("compress", "agent"))) or hit_title or (k == "cockpit" and "cockpit" in p.get("topics", [])):
            s = w * (1.0 + 0.25 * min(n - 1, 3)) + (w * 0.6 if hit_title else 0)
            # agent memory only counts with an agent / assistant context
            if k == "memory" and not C.AGENT.search(text):
                continue
            score += s
            it.append(k)
    sig = []
    for k, (lab, w, rx) in SIGNALS.items():
        if rx.search(text):
            sig.append(k); score += w
    theory = bool(THEORY.search(text)) and len(EMPIRICAL.findall(text)) < 2 and "real" not in sig
    if theory:
        score *= 0.6
    if p.get("flag"):
        score += 1.5
    if p.get("venue"):
        score += 1.0
    return {"rec": round(score, 2), "it": it, "sig": sig, "theory": theory}

# ---------------------------------------------------------------- plain-Chinese reasons
SOLVE = [  # (regex on title + key sentence, goal phrase) — first two matches win
    (r"on-?device|edge (?:ai|inference|deployment|device)|embedded|jetson|orin\b|npus?\b|mobile (?:phone|device|agent)|smartphone", "让模型能在本地设备（车机、手机、机器人芯片）上直接运行"),
    (r"quantiz|low-?bit|compress|pruning|small (?:language )?model|memory footprint|kv[- ]cache", "把模型压缩得更小、更省算力"),
    (r"stall|latency|speed ?up|faster|accelerat|speculative|real-?time|efficient|asynchronous", "让模型反应更快、动作更流畅"),
    (r"long-?term memory|agent memory|episodic memory|memory|remember|experience-driven|self-evol", "让智能体记住过去的经验并持续改进"),
    (r"cross-?device|multi-?device|device-?cloud|edge-?cloud|cloud[- ]edge|handoff", "让多个设备之间协同、接力完成任务"),
    (r"driver|in-?cabin|occupant|cockpit|infotainment|passenger", "让车内系统更好地理解和服务车里的人"),
    (r"tool[- ]use|tool-calling|function calling|self-evol|reflection|harness", "让智能体自己总结经验、学会使用工具"),
    (r"camera (?:pose|shift|bump)|viewpoint", "让机器人在相机位置变化时依然可靠"),
    (r"adversarial|attack|safety|safe|disturbance|interrupt", "让机器人在意外情况下更安全"),
    (r"tactile|touch|contact", "让机器人借助“手感”完成精细操作"),
    (r"dexterous|multi-finger|in-hand", "让多指灵巧手学会复杂操作"),
    (r"human video|egocentric|human demonstration|human data", "用人类视频降低机器人数据采集成本"),
    (r"navigation|vln", "让机器人/无人机听懂指令并找到路"),
    (r"world[- ](?:action )?models?|wams?\b|future|video prediction|penetrat", "让机器人在行动前“预演”结果"),
    (r"loco-?manipulation|long-horizon", "让机器人完成多步骤的长任务"),
    (r"humanoid|legged|quadruped|locomotion", "让腿足/人形机器人走得更稳"),
    (r"vision-language-action|vlas?\b|policy|policies", "让机器人“看懂指令→动手执行”更可靠"),
    (r"benchmark|evaluat", "提供统一、可信的评测方法"),
    (r"dataset|data collection|synthetic data", "补充高质量训练数据"),
]
USE = {
    "edge": "可作为在车机或机器人芯片上跑模型的端侧 Demo 起点",
    "compress": "可参考其压缩/加速方法，评估模型在车载或机器人芯片上的可行性",
    "memory": "可作为“带记忆的智能体”原型参考，例如让助手跨会话记住用户偏好",
    "xdevice": "可作为手机与车机等多设备之间接力任务的原型参考",
    "cockpit": "可作为座舱交互或驾驶员状态监测功能的原型参考",
    "vla": "可作为“看懂指令→动手执行”的具身 PoC 基线",
    "world": "可用于在仿真中先预演、再让机器人执行的方案验证",
    "dex": "可作为机器人抓取/操作类 PoC 的起点",
    "nav": "可作为语音/语言指令导航类 Demo 的参考",
    "humanoid": "可作为人形/足式机器人运动控制方案的参考",
    "agent": "可作为智能体工具调用、任务规划类 Demo 的参考",
}
SHORT_USE = {
    "edge": "适合做端侧 Demo 的起点", "compress": "可用来评估在车载/机器人芯片上的部署可行性",
    "memory": "可做带记忆助手的原型参考", "xdevice": "可做多设备接力的原型参考", "cockpit": "可做座舱交互原型参考",
    "vla": "可做具身 PoC 的基线", "dex": "可做抓取/操作 PoC 的起点", "world": "可做“先预演再执行”的方案验证",
    "nav": "可做指令导航 Demo 的参考", "humanoid": "可做人形/足式运动控制参考", "agent": "可做智能体任务规划 Demo 的参考",
}
SIG_WHY = {
    "code": "已公开代码或项目页，可以直接上手复现",
    "real": "在真实设备、机器人或车辆上做了实验（或有用户测试），不只停留在仿真",
    "numbers": "给出了延迟、速度或显存等可量化的数据",
    "deploy": "从设计上就面向实际部署",
    "plug": "免训练或即插即用，接入成本低",
    "open_model": "基于主流开源模型，便于复用",
}

def _numbers(abstract):
    m = re.findall(r"((?:latency|memory footprint|memory|energy) by up to \d+(?:\.\d+)?%|\d+(?:\.\d+)?\s?(?:ms|Hz|FPS|GB|MB)|\d+(?:\.\d+)?\s?[x×]\s?(?:faster|speed-?up|lower)|\d+(?:\.\d+)?%\s(?:success|fewer|lower|reduction|faster|improvement))", abstract)
    out = []
    for x in m:
        x = re.sub(r"^latency by up to (.+)$", r"延迟最多降低 \1", x)
        x = re.sub(r"^(?:memory footprint|memory) by up to (.+)$", r"内存占用最多降低 \1", x)
        x = re.sub(r"^energy by up to (.+)$", r"能耗最多降低 \1", x)
        x = re.sub(r"^([\d.]+)\s?[x×]\s?(?:faster|speed-?up)$", r"提速 \1 倍", x)
        x = re.sub(r"^([\d.]+)\s?[x×]\s?lower$", r"降低到 1/\1", x)
        x = re.sub(r"^([\d.]+)%\s(?:success)$", r"成功率 \1%", x)
        if re.search(r"[a-z]{4,}", x.replace("FPS", "")) :   # leave untranslatable English out
            continue
        if x not in out:
            out.append(x)
    return out[:2]

def reasons(p, a):
    probs = []
    for text in (p["title"], p.get("key_en", "")):   # the title speaks first, then the key sentence
        for rx, ph in SOLVE:
            if len(probs) < 2 and re.search(r"(?<![a-z])(?:" + rx + ")", text, re.I) and ph not in probs:
                probs.append(ph)
    if p.get("zh_summary"):
        solve = p["zh_summary"].rstrip("。") + "。"
    else:
        solve = ("目标：" + "；".join(probs) + "。") if probs else ""
        solve += "（原文要点：" + (p.get("key_en") or "") + "）"
    why = [SIG_WHY[s] for s in ["code", "real", "numbers", "plug", "deploy", "open_model"] if s in a["sig"]][:3]
    nums = _numbers(p["abstract"])
    if nums and "numbers" in a["sig"]:
        why = [w if w != SIG_WHY["numbers"] else f"给出了可量化的效果数据（如 {'、'.join(nums)}）" for w in why]
    if not why:
        why = ["方法思路清晰，可作为方案选型参考"]
    if a["theory"]:
        why.append("偏理论，落地前需要更多工程验证")
    order = ["edge", "xdevice", "memory", "compress", "cockpit", "vla", "dex", "world", "nav", "humanoid", "agent"]
    use_keys = [k for k in order if k in a["it"]][:2]
    use = "；".join(USE[k] for k in use_keys) if use_keys else "可作为了解该方向进展的参考"
    lab = [INTERESTS[k][0] for k in order if k in a["it"]][:2]
    hl = {"code": "已开源", "real": "有真实设备验证", "numbers": "有实测数据", "plug": "即插即用", "deploy": "面向部署"}
    hi = "、".join([hl[x] for x in ["code", "real", "plug", "numbers", "deploy"] if x in a["sig"]][:2]) or "思路新"
    goal = probs[0] if probs else ("推进" + "/".join(lab) + "方向" if lab else "推进该方向")
    line = f"{goal}；{hi}，{SHORT_USE.get(use_keys[0], '值得了解') if use_keys else '值得了解'}。"
    return {"solve": solve, "why": "；".join(why) + "。", "use": use + "。", "line": line}

# ---------------------------------------------------------------- picks
MIN_PICKS, MAX_PICKS = 3, 5
MIN_REC = 5.0   # below this a paper is never a top pick (a quiet day may have fewer than 3)

def select(cands):
    """cands: list of (paper, analysis). Returns up to MAX_PICKS with simple diversity."""
    ranked = sorted([c for c in cands if c[1]["rec"] >= MIN_REC], key=lambda x: (-x[1]["rec"], x[0]["id"]))
    out, used = [], {}
    for p, a in ranked:
        main = next((k for k in ["edge", "xdevice", "memory", "compress", "cockpit", "vla", "dex", "world", "nav", "humanoid", "agent"] if k in a["it"]), "other")
        if used.get(main, 0) >= 2 and len(ranked) > MAX_PICKS * 2:
            continue
        out.append((p, a)); used[main] = used.get(main, 0) + 1
        if len(out) == MAX_PICKS:
            break
    # cut the tail if clearly weaker (keep at least MIN_PICKS)
    if len(out) > MIN_PICKS:
        top = out[0][1]["rec"]
        out = out[:MIN_PICKS] + [x for x in out[MIN_PICKS:] if x[1]["rec"] >= 0.6 * top]
    return out

def assign(store, day, ids, log=print):
    """(Re)select picks for `day` (YYYY-MM-DD, Beijing) among `ids` + papers already picked for that day."""
    pool = set(ids) | {aid for aid, p in store.items() if (p.get("pick") or {}).get("date") == day}
    cands = [(store[i], store[i]["interest"]) for i in pool if i in store and "interest" in store[i]]
    if not cands:
        return []
    chosen = select(cands)
    chosen_ids = {p["id"] for p, _ in chosen}
    for i in pool:
        if i in store and (store[i].get("pick") or {}).get("date") == day and i not in chosen_ids:
            store[i].pop("pick", None)
    for rank, (p, a) in enumerate(chosen, 1):
        p["pick"] = {"date": day, "rank": rank, **reasons(p, a)}
    log(f"  top picks {day}: " + ", ".join(p["id"] for p, _ in chosen))
    return [p["id"] for p, _ in chosen]
