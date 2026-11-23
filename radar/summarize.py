"""Short per-paper summaries without an LLM.

- key_en: the most informative 1–2 abstract sentences (the "we propose / we present" sentence,
  falling back to the first sentence), trimmed. Faithful because it is extracted, not generated.
- zh_summary: optional, human/agent-written Chinese one-liner stored in data/zh_summaries.json
  (id -> text). The pipeline never invents Chinese text; if no entry exists the site shows
  Chinese keyword tags + the extracted English key sentence.
"""
import re

CUE = re.compile(r"\b(we (?:propose|present|introduce|develop|design|build|construct|release|study|investigate|show|demonstrate)|this (?:paper|work|study) (?:proposes|presents|introduces|investigates|studies|develops)|in this (?:paper|work)|our (?:method|approach|framework|system))\b", re.I)

def sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", text)
    return [s.strip() for s in parts if len(s.strip()) > 20]

def key_sentence(abstract, limit=300):
    ss = sentences(abstract)
    if not ss:
        return ""
    idx = next((i for i, s in enumerate(ss) if CUE.search(s)), None)
    if idx is None:
        out = ss[0]
    else:
        out = ss[idx]
    if len(out) > limit:
        cut = out[:limit]
        out = cut[: cut.rfind(" ")] + " …"
    return out
