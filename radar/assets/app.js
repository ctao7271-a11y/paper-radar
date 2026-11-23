(() => {
  "use strict";
  const SCHOOL = { tsinghua: "清华", pku: "北大", buaa: "北航" };
  const TOPIC = { cockpit: "智能座舱", embodied: "具身智能" };
  const WD = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const st = { topic: "all", onlyFlag: false, schools: new Set(["tsinghua", "pku", "buaa"]), q: "" };
  let manifest = null, loaded = 0, papers = [];
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---- URL state (shareable filters)
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    if (["all", "cockpit", "embodied"].includes(h.get("t"))) st.topic = h.get("t");
    st.onlyFlag = h.get("f") === "1";
    if (h.get("s")) st.schools = new Set(h.get("s").split(",").filter((x) => SCHOOL[x]));
    st.q = h.get("q") || "";
  }
  function writeHash() {
    const h = new URLSearchParams();
    if (st.topic !== "all") h.set("t", st.topic);
    if (st.onlyFlag) h.set("f", "1");
    if (st.onlyFlag && st.schools.size < 3) h.set("s", [...st.schools].join(","));
    if (st.q) h.set("q", st.q);
    const s = h.toString();
    history.replaceState(null, "", s ? "#" + s : location.pathname);
  }
  function syncControls() {
    document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.topic === st.topic)));
    $("#only-flag").checked = st.onlyFlag;
    $("#schools").hidden = !st.onlyFlag;
    document.querySelectorAll("#schools .chip").forEach((c) => c.classList.toggle("on", st.schools.has(c.dataset.school)));
    $("#q").value = st.q;
  }

  // ---- data
  async function getJSON(f) {
    const r = await fetch("data/" + f, { cache: "no-cache" });
    if (!r.ok) throw new Error(f + " " + r.status);
    return r.json();
  }
  async function loadMore(n = 1) {
    const ms = manifest.months.slice(loaded, loaded + n);
    const parts = await Promise.all(ms.map((m) => getJSON(m.file)));
    parts.forEach((p) => papers.push(...p));
    loaded += ms.length;
    $("#more").hidden = loaded >= manifest.months.length;
  }

  // ---- render
  function match(p) {
    if (st.topic !== "all" && !p.tp.includes(st.topic)) return false;
    if (st.onlyFlag && !Object.keys(p.fl).some((k) => st.schools.has(k))) return false;
    if (st.q) {
      const hay = (p.t + " " + p.au.join(" ") + " " + p.tg.join(" ") + " " + p.zh + " " + p.ab + " " + p.id).toLowerCase();
      if (!st.q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w))) return false;
    }
    return true;
  }
  function fmtDay(d) {
    const x = new Date(d + "T00:00:00Z");
    return `${x.getUTCFullYear()}年${x.getUTCMonth() + 1}月${x.getUTCDate()}日 ${WD[x.getUTCDay()]}`;
  }
  function authors(p) {
    const hl = new Set(Object.values(p.fl).flat());
    const MAX = 10;
    let list = p.au;
    // always show flagged authors even if beyond MAX
    let shown = list.slice(0, MAX);
    const extra = list.slice(MAX).filter((a) => hl.has(a));
    const rest = list.length - MAX - extra.length;
    const out = shown.concat(extra).map((a) => (hl.has(a) ? `<mark>${esc(a)}</mark>` : esc(a)));
    return out.join("，") + (rest > 0 ? ` 等 ${list.length} 人` : "");
  }
  function badges(p) {
    return Object.entries(p.fl)
      .filter(([k]) => SCHOOL[k])
      .map(([k, who]) => {
        const names = who.length ? who.slice(0, 4).join("、") + (who.length > 4 ? ` 等${who.length}人` : "") : "作者待确认";
        return `<span class="badge ${k}" title="${esc(SCHOOL[k])}作者：${esc(who.join(", ") || "未能定位到具体作者")}">${SCHOOL[k]} · <em>${esc(names)}</em></span>`;
      })
      .join("");
  }
  const SRC = { pdf: "PDF 首页", openalex: "OpenAlex", arxiv: "arXiv" };
  function card(p) {
    const flag = Object.keys(p.fl).length > 0;
    const src = p.src && p.src !== "pending" ? "机构来源：" + p.src.split("+").map((s) => SRC[s] || s).join(" + ") : "机构信息待解析";
    const sum = p.zh
      ? `<p class="sum"><span class="k">简介</span>${esc(p.zh)}</p>`
      : "";
    const en = p.en ? `<p class="en"><span class="k sum">要点</span>${esc(p.en)}</p>` : "";
    return `<article class="card${flag ? " flag" : ""}">
      <div class="meta">${p.tp.map((t) => `<span class="pill ${t}">${TOPIC[t]}</span>`).join("")}${badges(p)}${p.v ? `<span class="pill venue">${esc(p.v)}</span>` : ""}</div>
      <h3><a href="https://arxiv.org/abs/${esc(p.id)}" target="_blank" rel="noopener">${esc(p.t)}</a></h3>
      <p class="au">${authors(p)}</p>
      ${sum}${p.zh ? "" : en}
      ${p.tg.length ? `<div class="tags">${p.tg.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}
      <details><summary>${p.zh && p.en ? "英文要点与摘要" : "摘要原文"}</summary>${p.zh && p.en ? `<p class="en">${esc(p.en)}</p>` : ""}<p class="ab">${esc(p.ab)}</p></details>
      <div class="links"><a href="https://arxiv.org/abs/${esc(p.id)}" target="_blank" rel="noopener">arXiv:${esc(p.id)}</a><a href="https://arxiv.org/pdf/${esc(p.id)}" target="_blank" rel="noopener">PDF</a><span class="src">${esc(src)}</span></div>
    </article>`;
  }
  function render() {
    const items = papers.filter(match);
    const groups = new Map();
    for (const p of items) {
      if (!groups.has(p.d)) groups.set(p.d, []);
      groups.get(p.d).push(p);
    }
    const days = [...groups.keys()].sort().reverse();
    let html = "";
    for (const d of days) {
      const g = groups.get(d).sort((a, b) => (Object.keys(b.fl).length > 0) - (Object.keys(a.fl).length > 0) || b.s - a.s);
      html += `<section><div class="day"><h2>${fmtDay(d)}</h2><span>${g.length} 篇</span></div>${g.map(card).join("")}</section>`;
    }
    $("#list").innerHTML = html || `<p class="empty">没有符合条件的论文${loaded < manifest.months.length ? "，可尝试加载更早的月份" : ""}。</p>`;
    const nFlag = items.filter((p) => Object.keys(p.fl).length).length;
    $("#count").textContent = `显示 ${items.length} 篇（其中清华/北大/北航 ${nFlag} 篇）· 已加载 ${loaded}/${manifest.months.length} 个月`;
  }

  // ---- events
  function bind() {
    document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { st.topic = b.dataset.topic; update(); }));
    $("#only-flag").addEventListener("change", (e) => { st.onlyFlag = e.target.checked; update(); });
    document.querySelectorAll("#schools .chip").forEach((c) => c.addEventListener("click", () => {
      const k = c.dataset.school;
      if (st.schools.has(k) && st.schools.size > 1) st.schools.delete(k); else st.schools.add(k);
      update();
    }));
    let t;
    $("#q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { st.q = e.target.value.trim(); update(); }, 150); });
    $("#more").addEventListener("click", async () => { $("#more").disabled = true; await loadMore(1); $("#more").disabled = false; render(); });
  }
  function update() { syncControls(); writeHash(); render(); }

  async function init() {
    readHash(); syncControls(); bind();
    try {
      manifest = await getJSON("manifest.json");
    } catch (e) {
      $("#list").innerHTML = '<p class="empty">数据加载失败，请稍后刷新。</p>';
      return;
    }
    $("#s-total").textContent = manifest.total;
    $("#s-cockpit").textContent = manifest.counts.cockpit;
    $("#s-embodied").textContent = manifest.counts.embodied;
    $("#s-flag").textContent = manifest.counts.flagged;
    const u = new Date(manifest.updated);
    $("#updated").textContent = "最近更新：" + u.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) + "（北京时间）";
    await loadMore(Math.min(2, manifest.months.length));
    render();
  }
  init();
})();
