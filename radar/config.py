"""Topic definitions, arXiv queries and school patterns for paper-radar."""
import re

USER_AGENT = "paper-radar/1.0 (research tracker; contact: paper-radar@users.noreply.github.com)"
OPENALEX_MAILTO = "paper-radar@users.noreply.github.com"

FIRST_RUN_DAYS = 7          # lookback on the very first run
OVERLAP_DAYS = 4            # re-query this many days before the last run (arXiv announce lag)
RECHECK_DAYS = 14           # keep re-checking unresolved affiliations for this long

SITE_URL = ""               # filled from data/site.json if present

# ---------------------------------------------------------------- arXiv queries
# Each query is an arXiv API search_query fragment (submittedDate range appended at runtime).
# Recall comes from the queries, precision from the local classifier below.
CATS = ["cs.RO", "cs.AI", "cs.CV", "cs.CL", "cs.HC", "cs.LG", "cs.MA", "cs.SD", "eess.SY", "eess.AS", "eess.IV", "cs.MM"]
_cat = "(" + " OR ".join(f"cat:{c}" for c in CATS) + ")"

def _any(fields, phrases):
    parts = []
    for p in phrases:
        q = f'"{p}"' if " " in p or "-" in p else p
        for f in fields:
            parts.append(f"{f}:{q}")
    return "(" + " OR ".join(parts) + ")"

COCKPIT_PHRASES = [
    "in-cabin", "in cabin", "cockpit", "in-vehicle", "in-car", "driver monitoring", "driver distraction",
    "driver drowsiness", "driver fatigue", "driver state", "occupant", "automotive assistant",
    "vehicle assistant", "car assistant", "automotive voice", "automotive HMI", "takeover request",
    "automotive user interface", "in-vehicle assistant", "driver emotion", "passenger",
]
EMBODIED_PHRASES = [
    "embodied", "vision-language-action", "humanoid", "dexterous", "robot manipulation",
    "robotic manipulation", "sim-to-real", "sim2real", "visuomotor", "diffusion policy",
    "robot learning", "robot policy", "bimanual", "mobile manipulation", "legged robot",
    "quadruped", "vision-language navigation", "world model", "imitation learning", "grasping",
]

QUERIES = {
    # all of cs.RO is fetched and classified locally (≈60–90/day), plus keyword queries elsewhere
    "ro_all": "cat:cs.RO",
    "embodied_kw": _cat + " AND " + _any(["ti", "abs"], EMBODIED_PHRASES),
    "cockpit_hci": "(cat:cs.HC OR cat:cs.CL OR cat:cs.SD OR cat:eess.AS OR cat:cs.MM) AND " + _any(["ti", "abs"], ["vehicle", "driver", "driving", "car", "automotive", "cockpit", "cabin"]),
    "cockpit_kw": _any(["ti", "abs"], COCKPIT_PHRASES),
}

# ---------------------------------------------------------------- local classifier
def _rx(words):
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])", re.I)

COCKPIT_STRONG = _rx([
    r"in-?cabin", r"smart cockpits?", r"intelligent cockpits?", r"vehicle cockpits?", r"automotive cockpits?",
    r"digital cockpits?", r"car cockpits?", r"cockpit (?:agent|assistant|interaction)s?",
    r"in-?car (?:assistant|agent|voice|interaction|interface|conversational|dialog(?:ue)?|infotainment|ai|llm)s?",
    r"in-?vehicle (?:assistant|agent|voice|interaction|interface|conversational|dialog(?:ue)?|infotainment|ai|llm|intelligent agent|user|hmi|speech)s?",
    r"(?:vehicle|car|automotive|driving) (?:voice |virtual |intelligent |conversational |ai |llm |personal )?assistants?",
    r"driver monitoring", r"driver (?:distraction|drowsiness|fatigue|emotion|attention|state|intention|activity|behaviou?r recognition)",
    r"distracted driv(?:ing|ers?)", r"drowsy driv(?:ing|ers?)", r"occupant (?:monitoring|detection|behaviou?r|state|safety)",
    r"automotive (?:hmi|user interfaces?|ux|human-machine|voice|speech|llm|large language|multimodal)",
    r"human-vehicle interaction", r"driver-vehicle interaction", r"take-?over requests?", r"impaired driving", r"driver impairment",
    r"automotive (?:agent|assistant)s?", r"vehicle (?:hmi|human-machine interface)", r"cabin monitoring",
    r"in-?vehicle (?:hmi|human-machine)", r"passenger (?:experience|interaction|comfort|monitoring)",
])
COCKPIT_VEHICLE = _rx([r"vehicles?", r"cars?", r"automotive", r"drivers?", r"driving", r"passengers?", r"cockpits?", r"cabin", r"in-?vehicle", r"in-?car"])
COCKPIT_AI = _rx([r"assistants?", r"agents?", r"llms?", r"large language models?", r"multimodal", r"multi-modal", r"voice", r"speech",
                  r"dialog(?:ue)?s?", r"conversational", r"gestures?", r"gaze", r"emotions?", r"hmi", r"human-machine", r"user interfaces?",
                  r"interaction", r"vision-language", r"vlms?", r"mllms?"])
COCKPIT_EXCLUDE = _rx([r"in-?vehicle networks?", r"can bus", r"controller area network", r"intrusion detection", r"v2x",
                       r"vehicular networks?", r"aircraft", r"aviation", r"flight deck", r"pilots?", r"helicopter",
                       r"electric vehicle charging", r"battery", r"vehicle routing", r"traffic signal", r"spacecraft"])
# Driving-stack papers (perception/planning) are NOT cockpit unless a strong cockpit phrase appears.
# sentence-level co-occurrence: occupant-centric term + human-state / interaction term
COCKPIT_OCC = _rx([r"drivers?", r"passengers?", r"occupants?", r"in-?cabin", r"cabin", r"in-?car", r"in-?vehicle", r"cockpits?", r"vehicle users?", r"car users?"])
COCKPIT_HUMAN = _rx([r"gaze", r"eye[- ]tracking", r"emotions?", r"affective", r"distract\w*", r"drows\w*", r"fatigue", r"impair\w*", r"physiological",
                     r"heart rate", r"respirat\w*", r"vital signs?", r"voice", r"speech", r"spoken", r"dialog(?:ue)?s?", r"conversation\w*",
                     r"assistants?", r"gestures?", r"comfort", r"motion sickness", r"trust", r"hmi", r"human-machine", r"interfaces?",
                     r"wheelchairs?", r"accessib\w*", r"infotainment", r"personali[sz]\w*", r"workload", r"situation(?:al)? awareness",
                     r"take-?over", r"cognitive load", r"stress", r"intentions?", r"user experience", r"llm[- ]based agents?", r"in-?cabin"])
DRIVING_STACK = _rx([r"autonomous driving", r"self-driving", r"trajectory prediction", r"motion planning", r"lidar", r"bev",
                     r"3d object detection", r"end-to-end driving", r"driving policy", r"occupancy"])

EMB_STRONG = _rx([
    r"embodied", r"vision-language-action", r"vlas?", r"humanoids?", r"dexterous", r"(?:robot|robotic) manipulation",
    r"manipulation (?:policy|policies|tasks?|skills?)", r"sim-?to-?real", r"sim2real", r"real-?to-?sim", r"visuomotor",
    r"diffusion polic(?:y|ies)", r"robot learning", r"robot (?:policy|policies)", r"bimanual", r"mobile manipulation",
    r"legged (?:robots?|locomotion)", r"quadrupeds?", r"vision-language navigation", r"vln", r"object-?goal navigation",
    r"grasp(?:ing)?", r"teleoperation", r"robot foundation models?", r"generalist (?:robot )?polic(?:y|ies)",
    r"loco-?manipulation", r"whole-body control", r"in-hand manipulation", r"robotic assembly", r"cross-embodiment",
    r"action (?:chunking|tokeni[sz]ation|experts?)", r"contact-rich", r"locomotion polic(?:y|ies)", r"robot control", r"human-to-robot", r"robot-learning", r"world action models?", r"robot (?:world models?|data)",
    r"pick-and-place", r"articulated objects?", r"deformable object manipulation", r"tactile",
    r"wams?", r"latent actions?", r"robot arms?", r"robotic arms?", r"embodiments?", r"physical ai",
])
EMB_ROBOT = _rx([r"robots?", r"robotic", r"embodied (?:ai|agents?|intelligence|tasks?|navigation|reasoning|planning|models?)", r"manipulat\w*", r"humanoids?", r"quadrupeds?", r"grippers?", r"end-effectors?"])
EMB_WM = _rx([r"world models?", r"world modell?ing", r"world-model"])
EMB_EXCLUDE = _rx([r"deepfakes?", r"stock", r"prices?", r"financ\w*", r"econom\w*", r"language world models?", r"formal verification", r"medical imag\w*", r"protein", r"molecul\w*", r"ultrasound", r"rats?", r"mice", r"neural circuits?"])
EMB_ACT = _rx([r"actions?", r"action-conditioned", r"planning", r"planners?", r"control", r"polic(?:y|ies)", r"agents?", r"driving", r"navigation"])
EMB_RO_LEARN = _rx([r"polic(?:y|ies)", r"learning-based", r"learned", r"diffusion", r"flow matching", r"pre-?train\w*", r"foundation models?",
                    r"transformers?", r"language", r"vlms?", r"llms?", r"reinforcement learning", r"imitation", r"demonstrations?", r"world models?", r"data-driven"])
EMB_CLASSIC = _rx([r"odometry", r"slam", r"lidar", r"path planning", r"trajectory optimization", r"state estimation", r"localization",
                   r"swarms?", r"uavs?", r"auvs?", r"asvs?", r"marine", r"underwater", r"formation", r"autonomous racing"])
EMB_LEARN = _rx([r"world models?", r"imitation learning", r"reinforcement learning", r"policy learning", r"foundation models?",
                 r"vision-language models?", r"vlms?", r"llms?", r"large language models?", r"demonstrations?", r"behavio(?:u)?r cloning"])
EMB_DRIVING_OK = _rx([r"vision-language-action", r"vlas?", r"world models?"])
DRIVING = _rx([r"autonomous driving", r"self-driving", r"end-to-end driving", r"driving"])

# Chinese keyword tags ------------------------------------------------------
TAGS = [
    # (regex, tag, topic or None)
    (r"vision-language-action|(?<![a-z])vlas?(?![a-z])", "VLA 模型", None),
    (r"world (?:action )?models?", "世界模型", None),
    (r"humanoids?", "人形机器人", "embodied"),
    (r"dexterous|in-hand manipulation|multi-fingered", "灵巧手", "embodied"),
    (r"bimanual|dual-arm", "双臂操作", "embodied"),
    (r"mobile manipulation|loco-?manipulation", "移动操作", "embodied"),
    (r"grasp", "抓取", "embodied"),
    (r"manipulat", "机器人操作", "embodied"),
    (r"sim-?to-?real|sim2real|real-?to-?sim", "仿真到真实", "embodied"),
    (r"imitation learning|behaviou?r cloning|demonstrations?", "模仿学习", "embodied"),
    (r"reinforcement learning|(?<![a-z])rl(?![a-z])", "强化学习", None),
    (r"diffusion polic|flow matching", "扩散/流匹配策略", "embodied"),
    (r"legged|quadruped|locomotion", "足式运动", "embodied"),
    (r"navigation|(?<![a-z])vln(?![a-z])", "导航", "embodied"),
    (r"tactile|touch sensing", "触觉", "embodied"),
    (r"teleoperation", "遥操作/数据采集", "embodied"),
    (r"benchmark", "基准评测", None),
    (r"dataset", "数据集", None),
    (r"large language models?|(?<![a-z])llms?(?![a-z])", "大语言模型", None),
    (r"vision-language models?|(?<![a-z])vlms?(?![a-z])|multimodal large language|(?<![a-z])mllms?(?![a-z])", "多模态大模型", None),
    (r"(?<![a-z])agents?(?![a-z])|agentic", "智能体", None),
    (r"driver monitoring|driver (?:distraction|drowsiness|fatigue|state|attention)|distracted driv|drowsy", "驾驶员状态监测", "cockpit"),
    (r"in-?cabin|occupant|cabin monitoring", "舱内感知", "cockpit"),
    (r"voice|speech|spoken|dialog|conversational", "语音/对话交互", "cockpit"),
    (r"gesture|gaze|eye[- ]tracking", "手势/视线交互", "cockpit"),
    (r"emotion|affective", "情感识别", "cockpit"),
    (r"take-?over", "接管请求", "cockpit"),
    (r"(?<![a-z])hmi(?![a-z])|human-machine interface|user interface|(?<![a-z])ux(?![a-z])|user experience", "人机界面/体验", "cockpit"),
    (r"autonomous driving|self-driving|end-to-end driving", "自动驾驶", None),
    (r"safety|safe ", "安全", None),
]
TAGS = [(re.compile(p, re.I), t, topic) for p, t, topic in TAGS]

# ---------------------------------------------------------------- schools
# Strong patterns: valid anywhere on page 1 (header, footnotes, emails).
# Weak patterns (bare words / acronyms): only trusted in the header (before "Abstract").
SCHOOLS = {
    "tsinghua": {
        "zh": "清华", "full_zh": "清华大学",
        "strong": re.compile(r"Tsinghua\s+Univ|清华大学|tsinghua\.edu\.cn|Tsinghua\s+Shenzhen|Shenzhen\s+International\s+Graduate\s+School,?\s+Tsinghua|Institute\s+for\s+AI\s+Industry\s+Research|Institute\s+for\s+Interdisciplinary\s+Information\s+Sciences", re.I),
        "weak": re.compile(r"(?<![A-Za-z])(?:Tsinghua|THU)(?![A-Za-z])"),
    },
    "pku": {
        "zh": "北大", "full_zh": "北京大学",
        "strong": re.compile(r"Peking\s+Univ|北京大学|pku\.edu\.cn|Peking\s+U\.", re.I),
        "weak": re.compile(r"(?<![A-Za-z])PKU(?![A-Za-z])|(?<![A-Za-z])Peking(?![A-Za-z])"),
    },
    "buaa": {
        "zh": "北航", "full_zh": "北京航空航天大学",
        "strong": re.compile(r"Beihang|Beijing\s+University\s+of\s+Aeronautics|北京航空航天大学|buaa\.edu\.cn", re.I),
        "weak": re.compile(r"(?<![A-Za-z])BUAA(?![A-Za-z])"),
    },
}
# strings that look like a school but are not
SCHOOL_FALSE = re.compile(r"Tsinghua[- ]Tencent|Peking\s+Union\s+Medical|Peking\s+Opera|Tsinghua\s+Dog|PKU-?MMD|PKU[- ]DAVIS|THUMOS|THUCNews|Tsinghua\s+Science\s+and\s+Technology", re.I)

OPENALEX_IDS = {  # OpenAlex institution ids (lineage) -> school key
    "I99065089": "tsinghua",
    "I20231570": "pku",
    "I82880672": "buaa",
}

VENUES = re.compile(r"(?<![A-Za-z])(CVPR|ICCV|ECCV|NeurIPS|ICLR|ICML|CoRL|RSS|ICRA|IROS|AAAI|IJCAI|ACL|EMNLP|NAACL|CHI|UIST|ITSC|T-RO|RA-L|TPAMI|IJRR|Science Robotics|AutomotiveUI)(?![A-Za-z])")
