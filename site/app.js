(() => {
  "use strict";
  const SCHOOL = { tsinghua: "清华", pku: "北大", buaa: "北航" };
  const TOPIC = { cockpit: "智能座舱", embodied: "具身智能", edge: "端侧·智能体" };
  const INTEREST = { edge: "端侧部署", compress: "模型压缩/加速", memory: "智能体记忆", xdevice: "跨设备协同", agent: "智能体",
    cockpit: "座舱交互", vla: "VLA/具身大模型", world: "世界模型", dex: "机器人操作", nav: "导航", humanoid: "人形/足式" };
  const SIG = { code: "✓ 开源/项目页", real: "✓ 真实设备/真机实验", numbers: "✓ 延迟/显存等数据", deploy: "✓ 面向部署", plug: "✓ 免训练/即插即用", open_model: "✓ 基于开源模型" };
  const WD = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const st = { view: "list", topic: "all", onlyFlag: false, schools: new Set(["tsinghua", "pku", "buaa"]), q: "", it: "" };
  let manifest = null, loaded = 0, papers = [], picks = [];

  // ---- personal data, kept only in this browser (localStorage), keyed by arXiv id
  const LS_LIST = "paperRadar.readingList.v1", LS_OPEN = "paperRadar.openCounts.v1";
  const lsGet = (k) => { try { return JSON.parse(localStorage.getItem(k)) || {}; } catch (e) { return {}; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage full / disabled */ } };
  let myList = lsGet(LS_LIST);   // {id: {at: ISO time checked, read: bool, readAt?, p: {t, au, d, tp}}}
  let opens = lsGet(LS_OPEN);    // {id: number}
  const mine = { sort: "new", show: "all" };
  const byId = (id) => papers.find((x) => x.id === id) || picks.find((x) => x.id === id);
  function snap(p) { return { t: p.t, au: p.au.slice(0, 12), d: p.d, tp: p.tp }; }
  function setChecked(id, on) {
    if (on) {
      const p = byId(id);
      myList[id] = myList[id] || { at: new Date().toISOString(), read: false, p: p ? snap(p) : { t: id, au: [], d: "", tp: [] } };
    } else delete myList[id];
    lsSet(LS_LIST, myList);
    document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"] .pick-box input`).forEach((i) => { i.checked = !!on; });
    document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"]`).forEach((c) => c.classList.toggle("saved", !!on));
    badge();
  }
  function bumpOpen(id) {
    opens[id] = (opens[id] || 0) + 1;
    lsSet(LS_OPEN, opens);
    document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"] .opens`).forEach((el) => { el.textContent = openText(id); el.classList.toggle("zero", !opens[id]); });
  }
  const openText = (id) => `打开 ${opens[id] || 0} 次`;
  function badge() {
    const n = Object.keys(myList).length;
    const b = $("#mine-n");
    if (b) { b.textContent = n; b.hidden = n === 0; }
  }
  function fmtTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  function exportData() {
    const data = { app: "paper-radar", version: 1, exported: new Date().toISOString(), readingList: myList, openCounts: opens };
    const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `paper-radar-reading-list-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function importData(file) {
    const r = new FileReader();
    r.onload = () => {
      let d;
      try { d = JSON.parse(r.result); } catch (e) { alert("导入失败：不是有效的 JSON 文件。"); return; }
      const L = d.readingList || {}, O = d.openCounts || {};
      let added = 0;
      for (const [id, v] of Object.entries(L)) {
        if (!v || typeof v !== "object") continue;
        if (!myList[id]) added++;
        const cur = myList[id];
        myList[id] = cur ? { ...cur, read: cur.read || !!v.read, at: cur.at < v.at ? cur.at : v.at || cur.at } : v;   // merge: keep earliest check time
      }
      for (const [id, n] of Object.entries(O)) opens[id] = Math.max(opens[id] || 0, Number(n) || 0);   // merge: keep the larger count
      lsSet(LS_LIST, myList); lsSet(LS_OPEN, opens);
      badge(); render();
      alert(`导入完成：新增 ${added} 篇，阅读清单共 ${Object.keys(myList).length} 篇。`);
    };
    r.readAsText(file);
  }
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---- URL state (shareable filters)
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    if (["all", "cockpit", "embodied", "edge"].includes(h.get("t"))) st.topic = h.get("t");
    st.view = ["picks", "mine"].includes(h.get("v")) ? h.get("v") : "list";
    st.it = INTEREST[h.get("i")] ? h.get("i") : "";
    st.onlyFlag = h.get("f") === "1";
    if (h.get("s")) st.schools = new Set(h.get("s").split(",").filter((x) => SCHOOL[x]));
    st.q = h.get("q") || "";
  }
  function writeHash() {
    const h = new URLSearchParams();
    if (st.view !== "list") h.set("v", st.view);
    if (st.view === "picks" && st.it) h.set("i", st.it);
    if (st.topic !== "all") h.set("t", st.topic);
    if (st.onlyFlag) h.set("f", "1");
    if (st.onlyFlag && st.schools.size < 3) h.set("s", [...st.schools].join(","));
    if (st.q) h.set("q", st.q);
    const s = h.toString();
    history.replaceState(null, "", s ? "#" + s : location.pathname);
  }
  function syncControls() {
    document.querySelectorAll(".views button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === st.view)));
    $("#interests").hidden = st.view !== "picks";
    document.body.classList.toggle("v-mine", st.view === "mine");
    document.querySelectorAll("#interests .chip").forEach((c) => c.classList.toggle("on", c.dataset.it === st.it));
    document.querySelectorAll(".seg button[data-topic]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.topic === st.topic)));
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
    if (st.view === "picks" && st.it && !(p.it || []).includes(st.it)) return false;
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
  function sigs(p) {
    const out = (p.sig || []).map((k) => `<span>${SIG[k]}</span>`);
    if (p.th) out.push('<span class="th">偏理论</span>');
    if (!out.length) return "";
    return `<div class="sig"><span class="rec" title="按研究兴趣与可落地信号计算的推荐度">推荐度 ${Math.round(p.r)}</span>${out.join("")}</div>`;
  }
  function why(p) {
    const k = p.pk;
    if (!k) return "";
    return `<div class="why"><p class="line">一句话：${esc(k.line)}</p><dl>
      <dt>解决什么</dt><dd>${esc(k.solve)}</dd>
      <dt>为什么可落地</dt><dd>${esc(k.why)}</dd>
      <dt>可以用来做</dt><dd>${esc(k.use)}</dd></dl></div>`;
  }
  const SRC = { pdf: "PDF 首页", openalex: "OpenAlex", arxiv: "arXiv" };
  function card(p, showWhy) {
    const flag = Object.keys(p.fl).length > 0;
    const src = p.src && p.src !== "pending" ? "机构来源：" + p.src.split("+").map((s) => SRC[s] || s).join(" + ") : "机构信息待解析";
    const sum = p.zh
      ? `<p class="sum"><span class="k">简介</span>${esc(p.zh)}</p>`
      : "";
    const en = p.en ? `<p class="en"><span class="k sum">要点</span>${esc(p.en)}</p>` : "";
    const pk = showWhy && p.pk;
    const saved = !!myList[p.id];
    return `<article class="card${flag ? " flag" : ""}${pk ? " pick" : ""}${saved ? " saved" : ""}" data-id="${esc(p.id)}">
      <div class="mine-bar"><label class="pick-box" title="加入/移出我的阅读清单"><input type="checkbox" data-save="${esc(p.id)}"${saved ? " checked" : ""}><span>阅读清单</span></label><span class="opens${opens[p.id] ? "" : " zero"}" title="点击标题、arXiv 或 PDF 链接的次数（仅本浏览器）">${openText(p.id)}</span></div>
      <div class="meta">${p.pk ? `<span class="pill pick">★ 重点推荐${pk ? "" : " · " + esc(p.pk.date.slice(5))}</span>` : ""}${p.tp.map((t) => `<span class="pill ${t}">${TOPIC[t]}</span>`).join("")}${badges(p)}${p.v ? `<span class="pill venue">${esc(p.v)}</span>` : ""}</div>
      <h3><a href="https://arxiv.org/abs/${esc(p.id)}" target="_blank" rel="noopener" data-open="${esc(p.id)}">${esc(p.t)}</a></h3>
      <p class="au">${authors(p)}</p>
      ${pk ? why(p) : ""}
      ${sigs(p)}
      ${pk ? "" : sum}${pk || p.zh ? "" : en}
      ${p.tg.length ? `<div class="tags">${p.tg.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}
      <details><summary>${p.zh && p.en ? "英文要点与摘要" : "摘要原文"}</summary>${p.zh && p.en ? `<p class="en">${esc(p.en)}</p>` : ""}<p class="ab">${esc(p.ab)}</p></details>
      <div class="links"><a href="https://arxiv.org/abs/${esc(p.id)}" target="_blank" rel="noopener" data-open="${esc(p.id)}">arXiv:${esc(p.id)}</a><a href="https://arxiv.org/pdf/${esc(p.id)}" target="_blank" rel="noopener" data-open="${esc(p.id)}">PDF</a><span class="src">${esc(src)}</span></div>
    </article>`;
  }
  function fmtShort(d) {
    const x = new Date(d + "T00:00:00Z");
    return `${x.getUTCMonth() + 1}月${x.getUTCDate()}日 ${WD[x.getUTCDay()]}`;
  }
  function renderToday() {
    const box = $("#today");
    if (st.view !== "list" || st.q || st.onlyFlag || !picks.length) { box.hidden = true; return; }
    // newest pick day(s): keep adding earlier days until there are at least 3 picks to show
    const pool = picks.filter((p) => st.topic === "all" || p.tp.includes(st.topic));
    const days = [...new Set(pool.map((p) => p.pk.date))].sort().reverse();
    const use = [];
    let n = 0;
    for (const d of days) { use.push(d); n += pool.filter((p) => p.pk.date === d).length; if (n >= 3) break; }
    const items = pool.filter((p) => use.includes(p.pk.date)).sort((a, b) => (b.pk.date > a.pk.date) - (b.pk.date < a.pk.date) || a.pk.rank - b.pk.rank);
    if (!items.length) { box.hidden = true; return; }
    box.hidden = false;
    const label = use.length > 1 ? `${fmtShort(use[use.length - 1]).split(" ")[0]}–${fmtShort(use[0]).split(" ")[0]}` : fmtShort(use[0]);
    box.innerHTML = `<div class="hd"><h2>★ 最新重点推荐 · ${label}</h2><span>按研究兴趣与可落地程度自动挑选</span><a id="go-picks">查看往期推荐 ›</a></div>${items.map((p) => card(p, true)).join("")}`;
    $("#go-picks").addEventListener("click", () => { st.view = "picks"; update(); window.scrollTo(0, 0); });
  }
  function mineCard(id, v) {
    const p = byId(id);
    const s = p || { id, ...v.p };
    return `<article class="card mine-item${v.read ? " is-read" : ""}" data-id="${esc(id)}">
      <div class="mine-bar"><label class="pick-box" title="移出阅读清单"><input type="checkbox" data-save="${esc(id)}" checked><span>阅读清单</span></label>
        <label class="read-box"><input type="checkbox" data-read="${esc(id)}"${v.read ? " checked" : ""}><span>已读</span></label>
        <span class="opens${opens[id] ? "" : " zero"}">${openText(id)}</span></div>
      <div class="meta">${(s.tp || []).map((t) => `<span class="pill ${t}">${TOPIC[t] || t}</span>`).join("")}${p ? badges(p) : ""}</div>
      <h3><a href="https://arxiv.org/abs/${esc(id)}" target="_blank" rel="noopener" data-open="${esc(id)}">${esc(s.t)}</a></h3>
      <p class="au">${esc((s.au || []).slice(0, 8).join("，"))}${(s.au || []).length > 8 ? " 等" : ""}</p>
      ${p && p.zh ? `<p class="sum"><span class="k">简介</span>${esc(p.zh)}</p>` : ""}
      <div class="links"><a href="https://arxiv.org/abs/${esc(id)}" target="_blank" rel="noopener" data-open="${esc(id)}">arXiv:${esc(id)}</a><a href="https://arxiv.org/pdf/${esc(id)}" target="_blank" rel="noopener" data-open="${esc(id)}">PDF</a>
        <span class="src">${s.d ? "论文日期 " + esc(s.d) + " · " : ""}加入于 ${esc(fmtTime(v.at))}${v.read && v.readAt ? " · 读完于 " + esc(fmtTime(v.readAt)) : ""}</span>
        <button class="rm" data-rm="${esc(id)}">移除</button></div>
    </article>`;
  }
  function renderMine() {
    let items = Object.entries(myList);
    const total = items.length, nRead = items.filter(([, v]) => v.read).length;
    if (mine.show === "unread") items = items.filter(([, v]) => !v.read);
    if (mine.show === "read") items = items.filter(([, v]) => v.read);
    if (st.q) {
      const ws = st.q.toLowerCase().split(/\s+/).filter(Boolean);
      items = items.filter(([id, v]) => { const p = byId(id) || v.p; const hay = (id + " " + p.t + " " + (p.au || []).join(" ") + " " + (p.zh || "")).toLowerCase(); return ws.every((w) => hay.includes(w)); });
    }
    items.sort((a, b) => (mine.sort === "new" ? (a[1].at < b[1].at ? 1 : -1) : mine.sort === "old" ? (a[1].at > b[1].at ? 1 : -1) : (opens[b[0]] || 0) - (opens[a[0]] || 0)));
    const tools = `<div class="mine-tools">
      <label>排序 <select id="mine-sort"><option value="new"${mine.sort === "new" ? " selected" : ""}>最近加入</option><option value="old"${mine.sort === "old" ? " selected" : ""}>最早加入</option><option value="opens"${mine.sort === "opens" ? " selected" : ""}>打开次数</option></select></label>
      <div class="seg mini">${[["all", "全部"], ["unread", "未读"], ["read", "已读"]].map(([k, l]) => `<button data-show="${k}" aria-selected="${mine.show === k}">${l}</button>`).join("")}</div>
      <span class="grow"></span>
      <button class="tool" id="mine-export">导出</button>
      <label class="tool">导入<input type="file" id="mine-import" accept="application/json,.json" hidden></label>
    </div>
    <p class="hint">阅读清单和打开次数只保存在当前浏览器（本机 localStorage），不会上传；换设备或清除浏览器数据前，请用“导出”备份，在另一台设备上“导入”即可合并。</p>`;
    $("#list").innerHTML = tools + (items.length ? items.map(([id, v]) => mineCard(id, v)).join("")
      : `<p class="empty">${total ? "没有符合条件的论文。" : "阅读清单还是空的：在任意论文卡片左上角勾选“阅读清单”即可加入。"}</p>`);
    $("#count").textContent = `阅读清单 ${total} 篇（已读 ${nRead}，未读 ${total - nRead}）· 当前显示 ${items.length} 篇`;
    $("#more").hidden = true;
    $("#mine-sort").addEventListener("change", (e) => { mine.sort = e.target.value; render(); });
    document.querySelectorAll(".mine-tools [data-show]").forEach((b) => b.addEventListener("click", () => { mine.show = b.dataset.show; render(); }));
    $("#mine-export").addEventListener("click", exportData);
    $("#mine-import").addEventListener("change", (e) => { if (e.target.files[0]) importData(e.target.files[0]); e.target.value = ""; });
  }
  function render() {
    renderToday();
    if (st.view === "mine") { renderMine(); return; }
    if (st.view === "picks") {
      const items = picks.filter(match);
      const groups = new Map();
      for (const p of items) {
        if (!groups.has(p.pk.date)) groups.set(p.pk.date, []);
        groups.get(p.pk.date).push(p);
      }
      let html = "";
      for (const d of [...groups.keys()].sort().reverse()) {
        const g = groups.get(d).sort((a, b) => a.pk.rank - b.pk.rank);
        html += `<section><div class="day"><h2>★ ${fmtDay(d)} 推荐</h2><span>${g.length} 篇</span></div>${g.map((p) => card(p, true)).join("")}</section>`;
      }
      $("#list").innerHTML = html || '<p class="empty">没有符合条件的推荐论文。</p>';
      $("#count").textContent = `往期推荐共 ${picks.length} 篇，当前显示 ${items.length} 篇 · 可按方向或兴趣标签筛选`;
      $("#more").hidden = true;
      return;
    }
    $("#more").hidden = loaded >= manifest.months.length;
    const items = papers.filter(match);
    const groups = new Map();
    for (const p of items) {
      if (!groups.has(p.d)) groups.set(p.d, []);
      groups.get(p.d).push(p);
    }
    const days = [...groups.keys()].sort().reverse();
    let html = "";
    for (const d of days) {
      const g = groups.get(d).sort((a, b) => (!!b.pk - !!a.pk) || (b.r || 0) - (a.r || 0));
      html += `<section><div class="day"><h2>${fmtDay(d)}</h2><span>${g.length} 篇 · 按推荐度排序</span></div>${g.map((p) => card(p, false)).join("")}</section>`;
    }
    $("#list").innerHTML = html || `<p class="empty">没有符合条件的论文${loaded < manifest.months.length ? "，可尝试加载更早的月份" : ""}。</p>`;
    const nFlag = items.filter((p) => Object.keys(p.fl).length).length;
    $("#count").textContent = `显示 ${items.length} 篇（其中清华/北大/北航 ${nFlag} 篇）· 已加载 ${loaded}/${manifest.months.length} 个月`;
  }

  // ---- events
  function bind() {
    document.querySelectorAll(".seg button[data-topic]").forEach((b) => b.addEventListener("click", () => { st.topic = b.dataset.topic; update(); }));
    document.querySelectorAll(".views button").forEach((b) => b.addEventListener("click", () => { st.view = b.dataset.view; update(); }));
    $("#interests").innerHTML = '<button class="chip it" data-it="">全部兴趣</button>' +
      Object.entries(INTEREST).map(([k, v]) => `<button class="chip it" data-it="${k}">${v}</button>`).join("");
    document.querySelectorAll("#interests .chip").forEach((c) => c.addEventListener("click", () => { st.it = c.dataset.it; update(); }));
    $("#only-flag").addEventListener("change", (e) => { st.onlyFlag = e.target.checked; update(); });
    document.querySelectorAll("#schools .chip").forEach((c) => c.addEventListener("click", () => {
      const k = c.dataset.school;
      if (st.schools.has(k) && st.schools.size > 1) st.schools.delete(k); else st.schools.add(k);
      update();
    }));
    // event delegation: works for every card rendered later (lists, picks, archive, search, reading list)
    const onOpen = (e) => {
      const a = e.target.closest("a[data-open]");
      if (!a || (e.type === "auxclick" && e.button !== 1)) return;
      bumpOpen(a.dataset.open);   // never preventDefault: navigation goes ahead normally
    };
    document.addEventListener("click", onOpen, true);
    document.addEventListener("auxclick", onOpen, true);
    document.addEventListener("change", (e) => {
      const t = e.target;
      if (t.matches("input[data-save]")) {
        setChecked(t.dataset.save, t.checked);
        if (st.view === "mine" && !t.checked) render();
      } else if (t.matches("input[data-read]")) {
        const v = myList[t.dataset.read];
        if (v) { v.read = t.checked; v.readAt = t.checked ? new Date().toISOString() : undefined; lsSet(LS_LIST, myList); render(); }
      }
    });
    document.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-rm]");
      if (b) { setChecked(b.dataset.rm, false); render(); }
    });
    window.addEventListener("storage", (e) => { if (e.key === LS_LIST || e.key === LS_OPEN) { myList = lsGet(LS_LIST); opens = lsGet(LS_OPEN); badge(); render(); } });
    let t;
    $("#q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { st.q = e.target.value.trim(); update(); }, 150); });
    $("#more").addEventListener("click", async () => { $("#more").disabled = true; await loadMore(1); $("#more").disabled = false; render(); });
  }
  function update() { syncControls(); writeHash(); render(); }

  async function init() {
    readHash(); bind(); syncControls(); badge();
    try {
      manifest = await getJSON("manifest.json");
    } catch (e) {
      $("#list").innerHTML = '<p class="empty">数据加载失败，请稍后刷新。</p>';
      return;
    }
    $("#s-total").textContent = manifest.total;
    $("#s-cockpit").textContent = manifest.counts.cockpit;
    $("#s-embodied").textContent = manifest.counts.embodied;
    $("#s-edge").textContent = manifest.counts.edge ?? 0;
    $("#s-picks").textContent = manifest.counts.picks ?? 0;
    $("#s-flag").textContent = manifest.counts.flagged;
    const u = new Date(manifest.updated);
    $("#updated").textContent = "最近更新：" + u.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) + "（北京时间）";
    const [, pk] = await Promise.all([loadMore(Math.min(2, manifest.months.length)), getJSON("picks.json").catch(() => [])]);
    picks = pk;
    render();
  }
  init();
})();
