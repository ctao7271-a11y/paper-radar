/* Paper Radar — AI 论文助手 (chat panel). Talks to the Supabase Edge Function `paper-chat` with the user's session.
   The LLM key never reaches the browser. History is kept locally (last 20 messages). */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const LS = "paperRadar.chat.v1";
  const ID_RX = /\b(\d{4}\.\d{4,5})(?:v\d+)?\b/g;
  const SUGGEST = ["最近有哪些座舱语音交互的论文？", "哪些论文适合做端侧 Demo？", "清华北大北航最近在具身智能方向有什么新工作？", "有没有关于智能体长期记忆的论文？"];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let msgs = [];            // {role:'user'|'assistant', content, refs?:[{id,t}], err?}
  try { msgs = JSON.parse(localStorage.getItem(LS)) || []; } catch (e) { msgs = []; }
  let busy = false, focus = [];
  const save = () => { try { localStorage.setItem(LS, JSON.stringify(msgs.slice(-20))); } catch (e) { /* ignore */ } };

  function chip(id, refs) {
    const r = (refs || []).find((x) => x.id === id) || (window.PR && PR.paper(id)) || {};
    const t = r.t ? ` title="${esc(r.t)}"` : "";
    return `<a class="ref" href="https://arxiv.org/abs/${id}" target="_blank" rel="noopener" data-open="${id}" data-ref="${id}"${t}>${id}</a>`;
  }
  // tiny, safe markdown: escape first, then headings, bold, lists, paragraphs; arXiv ids become chips
  function md(text, refs) {
    let h = esc(text);
    h = h.replace(/arXiv[:：]?\s*(?=\d{4}\.\d{4,5})/gi, "");
    h = h.replace(/\[(\d{4}\.\d{4,5})(?:v\d+)?\]/g, "$1");
    h = h.replace(ID_RX, (m, id) => chip(id, refs));
    h = h.replace(/^#{1,4}\s*(.+)$/gm, "<h4>$1</h4>");
    h = h.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
    const lines = h.split("\n"); let out = "", list = null, tbl = null;
    const cells = (ln) => ln.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
    for (const ln of lines) {
      if (/^\s*\|.*\|\s*$/.test(ln)) {                       // markdown table row
        if (list) { out += "</ul>"; list = null; }
        if (/^\s*\|?\s*:?-{2,}/.test(ln)) continue;             // separator row
        if (!tbl) { out += '<div class="tbl"><table><tr>' + cells(ln).map((c) => `<th>${c}</th>`).join("") + "</tr>"; tbl = true; }
        else out += "<tr>" + cells(ln).map((c) => `<td>${c}</td>`).join("") + "</tr>";
        continue;
      }
      if (tbl) { out += "</table></div>"; tbl = null; }
      if (/^\s*(?:-{3,}|\*{3,})\s*$/.test(ln)) { if (list) { out += "</ul>"; list = null; } out += "<hr>"; continue; }
      const m = ln.match(/^\s*(?:[-*•]|\d+[.)、])\s+(.*)$/);
      if (m) { if (!list) { out += "<ul>"; list = true; } out += `<li>${m[1]}</li>`; continue; }
      if (list) { out += "</ul>"; list = null; }
      if (/^<h4>/.test(ln)) out += ln; else if (ln.trim()) out += `<p>${ln}</p>`;
    }
    if (list) out += "</ul>";
    if (tbl) out += "</table></div>";
    return out;
  }
  function refList(m) {
    if (!m.refs || !m.refs.length) return "";
    const cited = [...new Set((m.content.match(ID_RX) || []).map((x) => x.slice(0, 10).replace(/v\d+$/, "")))];
    const show = (cited.length ? m.refs.filter((r) => cited.includes(r.id)) : m.refs.slice(0, 5)).slice(0, 8);
    if (!show.length) return "";
    return `<div class="ai-refs"><span>${cited.length ? "引用的论文" : "检索到的论文"}</span>${show.map((r) =>
      `<div class="ai-ref"><a href="https://arxiv.org/abs/${r.id}" target="_blank" rel="noopener" data-open="${r.id}"><b>${r.id}</b> ${esc(r.t)}</a><button type="button" data-goto="${r.id}" title="在列表中定位">定位</button></div>`).join("")}</div>`;
  }
  function render() {
    const body = $("#ai-body");
    const logged = window.PR && PR.loggedIn();
    let h = "";
    if (!msgs.length) {
      h += `<div class="ai-hello"><div class="ai-orb big">✦</div><h3>想找什么论文？</h3><p>我会先在论文雷达的论文库里检索，再用 AI 帮你总结、对比和分析，并标出 arXiv 编号。</p>
        <div class="ai-sugg">${SUGGEST.map((s) => `<button type="button" data-sugg="${esc(s)}">${esc(s)}</button>`).join("")}</div></div>`;
    }
    for (const m of msgs) {
      if (m.role === "user") h += `<div class="msg-u"><div>${esc(m.content)}</div></div>`;
      else h += `<div class="msg-a">${m.content ? md(m.content, m.refs) : '<p class="typing"><i></i><i></i><i></i></p>'}${m.err ? `<p class="ai-err">${esc(m.err)}</p>` : ""}${m.done || m.err ? refList(m) : ""}</div>`;
    }
    if (!logged) h += `<div class="ai-gate"><b>登录后即可使用 AI 助手</b><span>为保护 AI 额度，仅限已开通同步的账号使用。</span><button type="button" id="ai-login">登录</button></div>`;
    body.innerHTML = h;
    body.scrollTop = body.scrollHeight;
    $("#ai-q").disabled = !logged; $("#ai-send").disabled = !logged || busy;
    $("#ai-q").placeholder = logged ? (focus.length ? "继续问这篇论文…" : "想找什么论文？问我吧…") : "登录后可提问";
  }
  function openPanel() { $("#ai-panel").hidden = false; $("#ai-fab").setAttribute("aria-expanded", "true"); document.body.classList.add("ai-open"); render(); if (!$("#ai-q").disabled) $("#ai-q").focus(); }
  function closePanel() { $("#ai-panel").hidden = true; $("#ai-fab").setAttribute("aria-expanded", "false"); document.body.classList.remove("ai-open"); }

  async function ask(q) {
    q = q.trim(); if (!q || busy) return;
    if (!PR.loggedIn()) { render(); return; }
    busy = true;
    const history = msgs.filter((m) => !m.err).slice(-6).map((m) => ({ role: m.role, content: m.content }));
    msgs.push({ role: "user", content: q });
    const a = { role: "assistant", content: "", refs: [] }; msgs.push(a); render();
    const f = focus; focus = [];
    try {
      const res = await fetch(PR.sbUrl + "/functions/v1/paper-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", apikey: PR.sbKey, Authorization: "Bearer " + (await PR.token()) },
        body: JSON.stringify({ q, history, focus: f }),
      });
      if (!res.ok) {
        let e = ""; try { e = (await res.json()).error; } catch (_) { /* */ }
        a.err = res.status === 401 ? "请先登录。" : res.status === 403 ? "该账号未开通 AI 助手。" : res.status === 429 ? e : "请求失败（" + res.status + "）" + (e ? "：" + e : "");
      } else {
        const rd = res.body.getReader(), dec = new TextDecoder(); let buf = "", last = 0;
        for (;;) {
          const { value, done } = await rd.read(); if (done) break;
          buf += dec.decode(value, { stream: true }); let i;
          while ((i = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, i); buf = buf.slice(i + 1); if (!line.trim()) continue;
            let o; try { o = JSON.parse(line); } catch (_) { continue; }
            if (o.type === "refs") { a.refs = o.papers || []; if (o.quota_limit) $("#ai-sub").textContent = `今日已用 ${o.quota_used}/${o.quota_limit} 次 · 论文库 ${o.n} 篇`; }
            else if (o.type === "delta") { a.content += o.t; if (Date.now() - last > 60) { last = Date.now(); render(); } }
            else if (o.type === "error") a.err = o.msg;
            else if (o.type === "done") a.done = true;
          }
        }
        if (!a.content && !a.err) a.err = "没有收到回答，请重试。";
      }
    } catch (e) { a.err = "网络错误：" + (e.message || e); }
    a.done = true; busy = false; save(); render();
  }

  function goto(id) {
    const el = document.querySelector(`.card[data-id="${CSS.escape(id)}"]`);
    if (!el) { window.open("https://arxiv.org/abs/" + id, "_blank", "noopener"); return; }
    if (matchMedia("(max-width:720px)").matches) closePanel();
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  }

  function init() {
    if (!$("#ai-fab")) return;
    $("#ai-fab").addEventListener("click", () => ($("#ai-panel").hidden ? openPanel() : closePanel()));
    $("#ai-close").addEventListener("click", closePanel);
    $("#ai-new").addEventListener("click", () => { msgs = []; focus = []; save(); render(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#ai-panel").hidden && $("#auth").hidden) closePanel(); });
    $("#ai-form").addEventListener("submit", (e) => { e.preventDefault(); const t = $("#ai-q"); const v = t.value; t.value = ""; t.style.height = ""; ask(v); });
    $("#ai-q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#ai-form").requestSubmit(); } });
    $("#ai-q").addEventListener("input", (e) => { e.target.style.height = ""; e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px"; });
    $("#ai-body").addEventListener("click", (e) => {
      const s = e.target.closest("[data-sugg]"); if (s) { ask(s.dataset.sugg); return; }
      if (e.target.closest("#ai-login")) { PR.openLogin(); return; }
      const g = e.target.closest("[data-goto]"); if (g) { goto(g.dataset.goto); return; }
    });
    document.addEventListener("click", (e) => {     // “问 AI” on a card
      const b = e.target.closest("button[data-ask]"); if (!b) return;
      const id = b.dataset.ask, p = PR.paper(id);
      openPanel();
      if (!PR.loggedIn()) return;
      focus = [id];
      ask(`帮我分析这篇论文 [${id}]${p ? "《" + p.t + "》" : ""}：它解决什么问题、方法要点、实验验证如何、是否适合做端侧或实机 Demo？`);
    });
    document.addEventListener("pr-auth", () => { if (!$("#ai-panel").hidden) render(); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
