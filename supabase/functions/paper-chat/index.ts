// paper-chat — AI chat over the Paper Radar archive.
// Auth: caller must send a logged-in Supabase session JWT of an allowlisted user (same allowlist as the reading list).
// Retrieval: BM25 over the site's own data files (title ×3, zh summary ×2, tags ×2, abstract, key sentence, authors),
//            with Chinese→English query expansion, CJK bigrams and small topic/recency boosts. Data is re-read from
//            GitHub Pages every 10 minutes, so the daily build keeps the chat current without any sync job.
// LLM: DeepSeek (OpenAI-compatible). Key from the function secret DEEPSEEK_API_KEY, else Vault ('deepseek_api_key').
// Response: NDJSON stream — {"type":"refs",papers:[…]}, {"type":"delta",t:"…"}…, {"type":"done"} | {"type":"error",msg}
import { createClient } from "npm:@supabase/supabase-js@2.119.2";

const DATA = "https://ctao7271-a11y.github.io/paper-radar/data/";
const ALLOWED_ORIGINS = ["https://ctao7271-a11y.github.io", "http://localhost:8766", "http://127.0.0.1:8766"];
const DAILY_LIMIT = 60;
const TOPK = 12;
const MODEL = "deepseek-chat";
const SB_URL = Deno.env.get("SUPABASE_URL")!;
const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

function cors(req: Request): Record<string, string> {
  const o = req.headers.get("origin") || "";
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(o) ? o : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}
const json = (req: Request, status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors(req), "Content-Type": "application/json; charset=utf-8" } });

// ------------------------------------------------------------------ retrieval
type Doc = { id: string; t: string; au: string[]; d: string; tp: string[]; zh: string; en: string; ab: string; tg: string[];
             r: number; pk: unknown; fl: Record<string, string[]>; tf: Map<string, number>; len: number };
let CACHE: { at: number; docs: Doc[]; df: Map<string, number>; avg: number } | null = null;

const SYN: [RegExp, string][] = [
  [/座舱|车内|车载|舱内/, "cockpit in-cabin in-vehicle in-car driver passenger occupant infotainment"],
  [/语音|说话|对话/, "voice speech spoken dialogue conversational assistant"],
  [/端侧|本地|边缘|设备端|芯片/, "on-device edge deployment embedded jetson npu mobile smartphone latency"],
  [/具身/, "embodied robot manipulation"], [/机器人/, "robot robotic"], [/人形/, "humanoid"],
  [/智能体|agent/i, "agent agentic"], [/记忆/, "memory long-term"], [/量化/, "quantization low-bit"],
  [/压缩|剪枝|蒸馏/, "compression pruning distillation"], [/推理加速|加速|低延迟/, "efficient inference latency speedup"],
  [/驾驶员|司机/, "driver"], [/疲劳|困倦/, "drowsiness fatigue"], [/分心/, "distraction distracted"],
  [/视线|注视|眼动/, "gaze eye-tracking"], [/情绪|情感/, "emotion affective"], [/接管/, "takeover"], [/手势/, "gesture"],
  [/抬头显示|hud/i, "head-up display hud ar-hud"], [/世界模型/, "world model"], [/导航/, "navigation vln"],
  [/抓取/, "grasp grasping"], [/操作|操控/, "manipulation"], [/灵巧手|灵巧/, "dexterous hand"], [/触觉/, "tactile touch"],
  [/大模型|大语言模型/, "llm large language model"], [/多模态/, "multimodal vision-language vlm mllm"],
  [/视觉语言动作|vla/i, "vision-language-action vla"], [/部署/, "deployment deploy"], [/落地|demo|实机|真机/i, "real-world real robot deployment open-source"],
  [/仿真/, "simulation sim-to-real"], [/数据集/, "dataset benchmark"], [/跨设备|多设备/, "cross-device multi-device"],
  [/安全/, "safety"], [/生理|心率|脑电/, "physiological heart rate eeg"],
];
const STOP = new Set("the a an of for and or in on to with by from is are be we our this that via using based towards toward into at as its their these those can".split(" "));

function tokens(s: string): string[] {
  const out: string[] = [];
  const low = (s || "").toLowerCase();
  for (const m of low.matchAll(/[a-z0-9][a-z0-9\-\.]*[a-z0-9]|[a-z0-9]/g)) {
    const w = m[0];
    if (!STOP.has(w)) out.push(w);
    if (w.includes("-")) for (const part of w.split("-")) if (part && !STOP.has(part)) out.push(part);
  }
  for (const m of low.matchAll(/[\u4e00-\u9fff]+/g)) {
    const c = m[0];
    if (c.length === 1) out.push(c);
    for (let i = 0; i + 1 < c.length; i++) out.push(c.slice(i, i + 2));
  }
  return out;
}

async function load() {
  if (CACHE && Date.now() - CACHE.at < 10 * 60 * 1000) return CACHE;
  const man = await (await fetch(DATA + "manifest.json", { cache: "no-store" })).json();
  const files: string[] = man.months.map((m: { file: string }) => m.file);
  const parts = await Promise.all(files.map(async (f) => (await fetch(DATA + f, { cache: "no-store" })).json()));
  const docs: Doc[] = [];
  const df = new Map<string, number>();
  let total = 0;
  for (const arr of parts) for (const p of arr) {
    const tf = new Map<string, number>();
    const add = (s: string, w: number) => { for (const t of tokens(s)) tf.set(t, (tf.get(t) || 0) + w); };
    add(p.t, 3); add(p.zh || "", 2); add((p.tg || []).join(" "), 2); add(p.ab || "", 1); add(p.en || "", 1); add((p.au || []).join(" "), 1);
    let len = 0; for (const v of tf.values()) len += v;
    for (const k of tf.keys()) df.set(k, (df.get(k) || 0) + 1);
    total += len;
    docs.push({ ...p, tf, len });
  }
  CACHE = { at: Date.now(), docs, df, avg: total / Math.max(1, docs.length) };
  return CACHE;
}

function search(c: NonNullable<typeof CACHE>, q: string, n: number, must: string[]) {
  let expanded = q;
  for (const [rx, add] of SYN) if (rx.test(q)) expanded += " " + add;
  const qt = [...new Set(tokens(expanded))];
  const N = c.docs.length, k1 = 1.2, b = 0.75;
  const wantTopic = /座舱|车内|车载|舱内|cockpit/i.test(q) ? "cockpit" : /具身|机器人|robot|embodied/i.test(q) ? "embodied" : /端侧|边缘|on-device|edge/i.test(q) ? "edge" : "";
  const recent = /最近|最新|近期|这周|本周|今天|recent|latest/i.test(q);
  const school = /清华/.test(q) ? "tsinghua" : /北大|北京大学/.test(q) ? "pku" : /北航/.test(q) ? "buaa" : "";
  const wantPick = /推荐|值得|重点|精选/.test(q);
  const newest = c.docs.reduce((m, d) => (d.d > m ? d.d : m), "");
  const scored = c.docs.map((d) => {
    let s = 0;
    for (const t of qt) {
      const f = d.tf.get(t); if (!f) continue;
      const idf = Math.log(1 + (N - (c.df.get(t) || 0) + 0.5) / ((c.df.get(t) || 0) + 0.5));
      s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * d.len / c.avg));
    }
    if (s > 0) {
      if (wantTopic && d.tp.includes(wantTopic)) s *= 1.35;
      if (school && d.fl && d.fl[school]) s *= 1.6;
      if (wantPick && d.pk) s *= 1.25;
      if (recent) s *= 1 + Math.max(0, 1 - (Date.parse(newest) - Date.parse(d.d)) / (21 * 864e5)) * 0.5;
      s *= 1 + Math.min(d.r || 0, 25) / 100;
    }
    return { d, s };
  }).filter((x) => x.s > 0).sort((a, b2) => b2.s - a.s);
  const out: Doc[] = [];
  const seen = new Set<string>();
  for (const id of must) { const d = c.docs.find((x) => x.id === id); if (d && !seen.has(id)) { out.push(d); seen.add(id); } }
  for (const x of scored) { if (out.length >= n) break; if (!seen.has(x.d.id)) { out.push(x.d); seen.add(x.d.id); } }
  return { docs: out, best: scored.length ? scored[0].s : 0 };
}

const TOPIC: Record<string, string> = { cockpit: "智能座舱", embodied: "具身智能", edge: "端侧·智能体" };
function ctx(d: Doc, i: number) {
  const ab = (d.ab || "").replace(/\s+/g, " ");
  return `[${i + 1}] arXiv:${d.id} | ${d.t}\n日期 ${d.d} | 方向 ${d.tp.map((t) => TOPIC[t] || t).join("/")} | 推荐度 ${d.r ?? "-"}${d.pk ? " | 重点推荐" : ""}` +
    `${Object.keys(d.fl || {}).length ? " | 作者单位含 " + Object.keys(d.fl).map((k) => ({ tsinghua: "清华", pku: "北大", buaa: "北航" } as Record<string, string>)[k] || k).join("/") : ""}\n` +
    `作者 ${(d.au || []).slice(0, 6).join(", ")}${(d.au || []).length > 6 ? " 等" : ""}\n` +
    (d.zh ? `中文简介 ${d.zh}\n` : "") + (d.tg?.length ? `标签 ${d.tg.join("、")}\n` : "") +
    `摘要 ${ab.length > 1100 ? ab.slice(0, 1100) + "…" : ab}\n链接 https://arxiv.org/abs/${d.id}`;
}

const SYSTEM = `你是“论文雷达”的研究助理，帮助用户在一个 arXiv 论文库（智能座舱、具身智能、端侧部署与智能体方向）里查找和分析论文。
规则：
1. 用用户提问的语言回答（默认简体中文），简洁、有条理，可用小标题和列表。
2. 只依据下面“检索到的论文”里的标题、简介和摘要作答；不要编造论文、作者、数字或结论。摘要没写的内容要说明“摘要未提及”。
3. 每次提到一篇论文，都写出它的 arXiv 编号，格式如 [2611.12345]，方便用户点击。
4. 如果检索结果与问题都不相关，直接说明“论文库里没找到相关论文”，并建议换个关键词；不要硬凑。
5. 对比或分析时，突出：解决什么问题、方法要点、实验/实机验证情况、是否开源、是否适合做端侧/实机 Demo。
6. 论文库只包含网站已收录的论文（主要是近几个月），不代表全部文献。`;

// ------------------------------------------------------------------ handler
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(req) });
  if (req.method !== "POST") return json(req, 405, { error: "method not allowed" });

  const jwt = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (!jwt || jwt.startsWith("sb_")) return json(req, 401, { error: "login required" });
  const uc = createClient(SB_URL, ANON, { global: { headers: { Authorization: `Bearer ${jwt}` } }, auth: { persistSession: false } });
  const { data: ud, error: ue } = await uc.auth.getUser(jwt);
  if (ue || !ud?.user) return json(req, 401, { error: "login required" });

  let body: { q?: string; history?: { role: string; content: string }[]; focus?: string[] };
  try { body = await req.json(); } catch { return json(req, 400, { error: "bad json" }); }
  const q = String(body.q || "").trim().slice(0, 1000);
  if (!q) return json(req, 400, { error: "empty question" });
  const hist = (Array.isArray(body.history) ? body.history : []).filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
    .slice(-6).map((m) => ({ role: m.role, content: m.content.slice(0, 1500) }));
  const idRx = /\b\d{4}\.\d{4,5}\b/g;
  const focus = [...new Set([...(Array.isArray(body.focus) ? body.focus : []), ...(q.match(idRx) || [])].filter((x) => /^\d{4}\.\d{4,5}$/.test(String(x))))].slice(0, 6);
  // follow-ups ("对比这两篇") keep the papers the previous answer talked about
  const lastA = [...hist].reverse().find((m) => m.role === "assistant");
  const carried = /这|那|上面|刚才|它们|两篇|几篇|对比|比较|继续|详细/.test(q) && lastA ? [...new Set(lastA.content.match(idRx) || [])].slice(0, 4) : [];

  const svc = createClient(SB_URL, SERVICE, { auth: { persistSession: false } });
  const { data: quota, error: qe } = await uc.rpc("chat_take_quota", { p_limit: DAILY_LIMIT });
  if (qe) return json(req, 403, { error: "not allowed" });
  if (quota === -1) return json(req, 429, { error: `今天的提问次数已用完（每天 ${DAILY_LIMIT} 次）` });

  let key = (Deno.env.get("DEEPSEEK_API_KEY") || "").trim();
  let envNames: string[] = [];
  try { envNames = Object.keys(Deno.env.toObject()); } catch (_) { /* ignore */ }
  if (!key) {   // tolerate a secret name with stray spaces / lower case
    const alt = envNames.find((n) => n.trim().toUpperCase() === "DEEPSEEK_API_KEY") || envNames.find((n) => /DEEPSEEK/i.test(n));
    if (alt) key = (Deno.env.get(alt) || "").trim();
  }
  if (!key) { const { data } = await svc.rpc("chat_llm_key"); key = (data as string) || ""; }

  const c = await load();
  const lastQ = [...hist].reverse().find((m) => m.role === "user");
  const query = q + (carried.length || q.length < 12 ? " " + (lastQ?.content || "").slice(0, 200) : "");
  const { docs, best } = search(c, query, TOPK, [...focus, ...carried]);
  const refs = docs.map((d) => ({ id: d.id, t: d.t, d: d.d, tp: d.tp, zh: d.zh || "" }));

  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(ctrl) {
      const send = (o: unknown) => ctrl.enqueue(enc.encode(JSON.stringify(o) + "\n"));
      send({ type: "refs", papers: refs, n: c.docs.length, weak: best < 2 && !focus.length && !carried.length, quota_used: quota, quota_limit: DAILY_LIMIT });
      if (!key) { send({ type: "error", msg: "AI 服务尚未配置密钥（DEEPSEEK_API_KEY）。检索结果见下方。", custom_secret_names: envNames.filter((n) => !/^(SUPABASE_|DENO_|SB_)/.test(n) && !["PATH","HOME","HOSTNAME","PWD","LANG","TZ","NODE_ENV"].includes(n)) }); ctrl.close(); return; }
      const context = docs.length ? docs.map(ctx).join("\n\n") : "（没有检索到相关论文）";
      const messages = [{ role: "system", content: SYSTEM }, ...hist,
        { role: "user", content: `检索到的论文（共 ${docs.length} 篇，论文库共 ${c.docs.length} 篇）：\n\n${context}\n\n---\n我的问题：${q}` }];
      try {
        const r = await fetch("https://api.deepseek.com/chat/completions", {
          method: "POST",
          headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
          body: JSON.stringify({ model: MODEL, messages, stream: true, temperature: 0.3, max_tokens: 1600, stream_options: { include_usage: true } }),
        });
        if (!r.ok || !r.body) { send({ type: "error", msg: `AI 服务返回错误 ${r.status}` }); ctrl.close(); return; }
        const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = ""; let used = 0;
        for (;;) {
          const { value, done } = await reader.read(); if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
            if (!line.startsWith("data:")) continue;
            const data = line.slice(5).trim(); if (data === "[DONE]") continue;
            try {
              const j = JSON.parse(data);
              const t = j.choices?.[0]?.delta?.content; if (t) send({ type: "delta", t });
              if (j.usage?.total_tokens) used = j.usage.total_tokens;
            } catch { /* partial line */ }
          }
        }
        if (used) await svc.rpc("chat_add_tokens", { p_user: ud.user.id, p_tokens: used });
        send({ type: "done", tokens: used });
      } catch (e) { send({ type: "error", msg: "AI 服务连接失败：" + String((e as Error).message || e) }); }
      ctrl.close();
    },
  });
  return new Response(stream, { headers: { ...cors(req), "Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-store" } });
});
