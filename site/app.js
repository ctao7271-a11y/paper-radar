(() => {
  "use strict";
  // ---------------------------------------------------------------- config
  // Public project URL + publishable (anon) key. Safe to ship: row-level security limits what it can do.
  const SB_URL = "https://gabsjglbryeftyolopev.supabase.co";
  const SB_KEY = "sb_publishable_ExR78YJCTpzaDXYbncU3PA_XKAmAK7B";
  const SCHOOL = { tsinghua: "清华", pku: "北大", buaa: "北航" };
  const TOPIC = { cockpit: "智能座舱", embodied: "具身智能", edge: "端侧·智能体" };
  const INTEREST = { edge: "端侧部署", compress: "模型压缩/加速", memory: "智能体记忆", xdevice: "跨设备协同", agent: "智能体",
    cockpit: "座舱交互", vla: "VLA/具身大模型", world: "世界模型", dex: "机器人操作", nav: "导航", humanoid: "人形/足式" };
  const SIG = { code: "开源/项目页", real: "真实设备/真机实验", numbers: "延迟/显存等数据", deploy: "面向部署", plug: "免训练/即插即用", open_model: "基于开源模型" };
  const SRC = { pdf: "PDF 首页", openalex: "OpenAlex", arxiv: "arXiv" };
  const WD = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const st = { view: "list", topic: "all", onlyFlag: false, schools: new Set(["tsinghua", "pku", "buaa"]), q: "", it: "" };
  let manifest = null, loaded = 0, papers = [], picks = [];
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const byId = (id) => papers.find((x) => x.id === id) || picks.find((x) => x.id === id);
  const cardsOf = (id) => document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"]`);

  // ---------------------------------------------------------------- local storage
  const LS_LIST = "paperRadar.readingList.v1", LS_PENDING = "paperRadar.pendingOps.v1", LS_MERGED = "paperRadar.mergedUser.v1", LS_THROTTLE = "paperRadar.clickThrottle.v1";
  const lsGet = (k, d = {}) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage full / disabled */ } };
  let myList = lsGet(LS_LIST);   // {id: {at, read, readAt?, p: {t, au, d, tp}}}
  const mine = { sort: "new", show: "all" };
  const snap = (p) => ({ t: p.t, au: p.au.slice(0, 12), d: p.d, tp: p.tp });

  // ---------------------------------------------------------------- cloud (optional)
  let sb = null, user = null, gOK = false;
  const gcount = {};   // arxiv id -> total opens by all visitors
  try {
    if (window.supabase && SB_URL && SB_KEY) {
      sb = window.supabase.createClient(SB_URL, SB_KEY, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "implicit" } });
    }
  } catch (e) { sb = null; }

  // ---- global click counter (everyone, no login)
  async function loadGlobalCounts() {
    if (!sb) return;
    try {
      for (let from = 0; ; from += 1000) {
        const { data, error } = await sb.from("global_clicks").select("arxiv_id,count").range(from, from + 999);
        if (error) throw error;
        data.forEach((r) => { gcount[r.arxiv_id] = Number(r.count); });
        if (data.length < 1000) break;
      }
      gOK = true;
    } catch (e) { gOK = false; }
    document.body.classList.toggle("no-gc", !gOK);
  }
  const opensHTML = (id) => (gOK ? `<span class="opens${gcount[id] ? "" : " zero"}" title="所有访客点击标题、arXiv 或 PDF 链接的总次数">打开 <b>${gcount[id] || 0}</b> 次</span>` : "");
  function paintCount(id) { cardsOf(id).forEach((c) => { const el = c.querySelector(".opens"); if (el) el.outerHTML = opensHTML(id); }); }
  function countClick(id) {
    if (!sb || !gOK) return;
    const th = lsGet(LS_THROTTLE), now = Date.now();
    if (th[id] && now - th[id] < 30000) return;            // same browser + same paper: at most once per 30 s
    th[id] = now;
    for (const k in th) if (now - th[k] > 60000) delete th[k];
    lsSet(LS_THROTTLE, th);
    gcount[id] = (gcount[id] || 0) + 1; paintCount(id);     // optimistic
    sb.rpc("increment_global_click", { p_arxiv_id: id }).then(({ data, error }) => {
      if (!error && data != null) { gcount[id] = Number(data); paintCount(id); }
    });
  }

  // ---- reading list sync (owner only)
  const rowToItem = (r) => ({ at: r.checked_at, read: !!r.read, readAt: r.read_at || undefined, p: r.snap || {} });
  function queue(op) { const q = lsGet(LS_PENDING, []); q.push(op); lsSet(LS_PENDING, q.slice(-500)); }
  async function cloudOp(op) {
    if (op.op === "add") return sb.from("reading_list").upsert({ arxiv_id: op.id, checked_at: op.v.at, read: op.v.read, read_at: op.v.readAt || null, snap: op.v.p || {} }, { onConflict: "user_id,arxiv_id" });
    if (op.op === "del") return sb.from("reading_list").delete().eq("arxiv_id", op.id);
    if (op.op === "read") return sb.from("reading_list").update({ read: op.read, read_at: op.readAt || null, updated_at: new Date().toISOString() }).eq("arxiv_id", op.id);
    return { error: null };
  }
  async function push(op) {
    if (!user) return;
    try { const { error } = await cloudOp(op); if (error) throw error; } catch (e) { queue(op); setSyncState("有改动待同步（网络恢复后自动重试）"); }
  }
  let syncing = false;
  async function syncNow() {
    if (!sb || !user || syncing) return;
    syncing = true; $("#sync-btn").classList.add("busy");
    try {
      if (lsGet(LS_MERGED, "") !== user.id) {             // first login on this device: union local list into the cloud
        const { error } = await sb.rpc("merge_my_list", { p_list: myList });
        if (error) throw error;
        lsSet(LS_MERGED, user.id);
      }
      const pend = lsGet(LS_PENDING, []);
      const left = [];
      for (const op of pend) { try { const { error } = await cloudOp(op); if (error) left.push(op); } catch (e) { left.push(op); } }
      lsSet(LS_PENDING, left);
      const { data, error } = await sb.from("reading_list").select("arxiv_id,checked_at,read,read_at,snap").limit(5000);
      if (error) throw error;
      myList = {};
      data.forEach((r) => { myList[r.arxiv_id] = rowToItem(r); });
      lsSet(LS_LIST, myList);
      setSyncState(`已同步 ${data.length} 篇 · ${fmtTime(new Date().toISOString())}`);
      badge(); render();
    } catch (e) {
      setSyncState("同步失败：" + (e.message || e) + "（数据仍保存在本浏览器）");
    } finally { syncing = false; $("#sync-btn").classList.remove("busy"); }
  }
  function setSyncState(s) { const el = $("#auth-state"); if (el) el.textContent = s; }
  function paintAuth() {
    const b = $("#sync-btn");
    if (!sb) { b.hidden = true; return; }
    b.classList.toggle("on", !!user);
    b.textContent = user ? "已同步" : "登录同步";
    b.title = user ? "已登录：" + (user.email || "") + "（点击管理）" : "登录后阅读清单可在多台设备间同步";
    $("#auth-out").hidden = !!user; $("#auth-in").hidden = !user;
    if (user) $("#auth-who").textContent = user.email || user.id;
  }
  async function finishLogin(raw) {
    const s = raw.trim(), msg = $("#auth-msg");
    msg.textContent = "正在登录…";
    try {
      let res;
      const hash = s.includes("#") ? new URLSearchParams(s.split("#")[1]) : null;
      const query = s.includes("?") ? new URLSearchParams(s.split("?")[1].split("#")[0]) : null;
      if (hash && hash.get("access_token") && hash.get("refresh_token")) {
        res = await sb.auth.setSession({ access_token: hash.get("access_token"), refresh_token: hash.get("refresh_token") });
      } else if (query && query.get("token")) {
        const t = query.get("type");
        res = await sb.auth.verifyOtp({ token_hash: query.get("token"), type: ["signup", "magiclink", "invite", "email"].includes(t) ? (t === "signup" || t === "magiclink" ? "email" : t) : "email" });
      } else if (/^\d{6,10}$/.test(s)) {
        res = await sb.auth.verifyOtp({ email: $("#auth-email").value.trim(), token: s, type: "email" });
      } else { msg.textContent = "没认出来：请粘贴完整网址（以 http 开头）或验证码。"; return; }
      if (res.error) throw res.error;
      msg.textContent = "";
    } catch (e) { msg.textContent = "登录失败：" + (e.message || e) + "。链接只能用一次，可重新发送登录邮件。"; }
  }

  // ---------------------------------------------------------------- reading list (local first)
  function setChecked(id, on) {
    if (on) {
      if (!myList[id]) { const p = byId(id); myList[id] = { at: new Date().toISOString(), read: false, p: p ? snap(p) : { t: id, au: [], d: "", tp: [] } }; }
      push({ op: "add", id, v: myList[id] });
    } else { delete myList[id]; push({ op: "del", id }); }
    lsSet(LS_LIST, myList);
    cardsOf(id).forEach((c) => { c.classList.toggle("saved", !!on); const i = c.querySelector("input[data-save]"); if (i) i.checked = !!on; });
    badge();
  }
  function setRead(id, read) {
    const v = myList[id]; if (!v) return;
    v.read = read; v.readAt = read ? new Date().toISOString() : undefined;
    lsSet(LS_LIST, myList); push({ op: "read", id, read, readAt: v.readAt });
  }
  function badge() { const n = Object.keys(myList).length, b = $("#mine-n"); b.textContent = n; b.hidden = n === 0; }
  function fmtTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  function exportData() {
    const data = { app: "paper-radar", version: 2, exported: new Date().toISOString(), readingList: myList };
    const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `paper-radar-reading-list-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function importData(file) {
    const r = new FileReader();
    r.onload = async () => {
      let d;
      try { d = JSON.parse(r.result); } catch (e) { alert("导入失败：不是有效的 JSON 文件。"); return; }
      const L = d.readingList || {};
      let added = 0;
      for (const [id, v] of Object.entries(L)) {
        if (!v || typeof v !== "object" || !/^[\w.\/-]{4,32}$/.test(id)) continue;
        const cur = myList[id];
        if (!cur) added++;
        myList[id] = cur ? { ...cur, read: cur.read || !!v.read, at: v.at && v.at < cur.at ? v.at : cur.at } : { at: v.at || new Date().toISOString(), read: !!v.read, readAt: v.readAt, p: v.p || {} };
      }
      lsSet(LS_LIST, myList);
      if (user) { try { await sb.rpc("merge_my_list", { p_list: myList }); } catch (e) { /* retried on next sync */ } await syncNow(); }
      badge(); render();
      alert(`导入完成：新增 ${added} 篇，阅读清单共 ${Object.keys(myList).length} 篇。`);
    };
    r.readAsText(file);
  }

  // ---------------------------------------------------------------- URL state
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get("access_token")) return;    // auth redirect: handled by the client
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

  // ---------------------------------------------------------------- data
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
  }

  // ---------------------------------------------------------------- render
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
    return `${x.getUTCFullYear()}-${String(x.getUTCMonth() + 1).padStart(2, "0")}-${String(x.getUTCDate()).padStart(2, "0")} ${WD[x.getUTCDay()]}`;
  }
  function authors(p) {
    const hl = new Set(Object.values(p.fl).flat());
    const MAX = 10, list = p.au;
    const shown = list.slice(0, MAX), extra = list.slice(MAX).filter((a) => hl.has(a));
    const rest = list.length - MAX - extra.length;
    return shown.concat(extra).map((a) => (hl.has(a) ? `<mark>${esc(a)}</mark>` : esc(a))).join("，") + (rest > 0 ? ` 等 ${list.length} 人` : "");
  }
  function badges(p) {
    return Object.entries(p.fl).filter(([k]) => SCHOOL[k]).map(([k, who]) => {
      const names = who.length ? who.slice(0, 4).join("、") + (who.length > 4 ? ` 等${who.length}人` : "") : "作者待确认";
      return `<span class="badge" title="${esc(SCHOOL[k])}作者：${esc(who.join(", ") || "未能定位到具体作者")}">${SCHOOL[k]} <em>${esc(names)}</em></span>`;
    }).join("");
  }
  function sigs(p) {
    const out = (p.sig || []).map((k) => `<span>${SIG[k]}</span>`);
    if (p.th) out.push('<span class="th">偏理论</span>');
    return `<div class="sig"><span class="rec" title="按研究兴趣与可落地信号计算的推荐度">推荐度 ${Math.round(p.r || 0)}</span>${out.join("")}</div>`;
  }
  function why(p) {
    const k = p.pk;
    return `<div class="why"><p class="line">${esc(k.line)}</p><dl>
      <dt>解决什么</dt><dd>${esc(k.solve)}</dd>
      <dt>为何可落地</dt><dd>${esc(k.why)}</dd>
      <dt>可以用来做</dt><dd>${esc(k.use)}</dd></dl></div>`;
  }
  function head(id, extra) {
    const saved = !!myList[id];
    return `<div class="cardhead"><label class="pick-box" title="加入/移出我的阅读清单"><input type="checkbox" data-save="${esc(id)}"${saved ? " checked" : ""}><span>阅读清单</span></label>${extra || ""}<span class="grow"></span>${opensHTML(id)}<span class="idc">${esc(id)}</span></div>`;
  }
  function links(id, right) {
    return `<div class="links"><a href="https://arxiv.org/abs/${esc(id)}" target="_blank" rel="noopener" data-open="${esc(id)}">arXiv</a><a href="https://arxiv.org/pdf/${esc(id)}" target="_blank" rel="noopener" data-open="${esc(id)}">PDF</a>${right}</div>`;
  }
  function card(p, showWhy) {
    const flag = Object.keys(p.fl).length > 0;
    const src = p.src && p.src !== "pending" ? "机构来源：" + p.src.split("+").map((s) => SRC[s] || s).join(" + ") : "机构信息待解析";
    const pk = showWhy && p.pk;
    const sum = p.zh ? `<p class="sum"><span class="k">简介</span>${esc(p.zh)}</p>` : "";
    const en = p.en ? `<p class="en"><span class="k">要点</span>${esc(p.en)}</p>` : "";
    return `<article class="card${flag ? " flag" : ""}${pk ? " pick" : ""}${myList[p.id] ? " saved" : ""}" data-id="${esc(p.id)}">
      ${head(p.id)}
      <div class="cardhead">${p.pk ? `<span class="pill pick">★ 推荐${pk ? "" : " " + esc(p.pk.date.slice(5))}</span>` : ""}${p.tp.map((t) => `<span class="pill">${TOPIC[t]}</span>`).join("")}${badges(p)}${p.v ? `<span class="pill venue">${esc(p.v)}</span>` : ""}</div>
      <h3><a href="https://arxiv.org/abs/${esc(p.id)}" target="_blank" rel="noopener" data-open="${esc(p.id)}">${esc(p.t)}</a></h3>
      <p class="au">${authors(p)}</p>
      ${pk ? why(p) : ""}
      ${sigs(p)}
      ${pk ? "" : sum}${pk || p.zh ? "" : en}
      ${p.tg.length ? `<div class="tags">${p.tg.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}
      <details><summary>${p.zh && p.en ? "英文要点与摘要" : "摘要原文"}</summary>${p.zh && p.en ? `<p class="en">${esc(p.en)}</p>` : ""}<p class="ab">${esc(p.ab)}</p></details>
      ${links(p.id, `<span class="src">${esc(src)}</span>`)}
    </article>`;
  }
  function fmtShort(d) { const x = new Date(d + "T00:00:00Z"); return `${x.getUTCMonth() + 1}月${x.getUTCDate()}日`; }
  function renderToday() {
    const box = $("#today");
    if (st.view !== "list" || st.q || st.onlyFlag || !picks.length) { box.hidden = true; return; }
    const pool = picks.filter((p) => st.topic === "all" || p.tp.includes(st.topic));
    const days = [...new Set(pool.map((p) => p.pk.date))].sort().reverse();
    const use = [];
    let n = 0;
    for (const d of days) { use.push(d); n += pool.filter((p) => p.pk.date === d).length; if (n >= 3) break; }
    const items = pool.filter((p) => use.includes(p.pk.date)).sort((a, b) => (b.pk.date > a.pk.date) - (b.pk.date < a.pk.date) || a.pk.rank - b.pk.rank);
    if (!items.length) { box.hidden = true; return; }
    box.hidden = false;
    const label = use.length > 1 ? `${fmtShort(use[use.length - 1])}–${fmtShort(use[0])}` : fmtShort(use[0]);
    box.innerHTML = `<div class="hd"><h2><i>★</i>最新重点推荐 · ${label}</h2><span>按研究兴趣与可落地程度自动挑选</span><a id="go-picks">往期推荐 →</a></div>${items.map((p) => card(p, true)).join("")}`;
    $("#go-picks").addEventListener("click", () => { st.view = "picks"; update(); window.scrollTo(0, 0); });
  }
  function mineCard(id, v) {
    const p = byId(id);
    const s = p || { id, ...(v.p || {}) };
    return `<article class="card mine-item saved${v.read ? " is-read" : ""}" data-id="${esc(id)}">
      ${head(id, `<label class="read-box"><input type="checkbox" data-read="${esc(id)}"${v.read ? " checked" : ""}><span>已读</span></label>`)}
      <div class="cardhead">${(s.tp || []).map((t) => `<span class="pill">${TOPIC[t] || esc(t)}</span>`).join("")}${p ? badges(p) : ""}</div>
      <h3><a href="https://arxiv.org/abs/${esc(id)}" target="_blank" rel="noopener" data-open="${esc(id)}">${esc(s.t || id)}</a></h3>
      <p class="au">${esc((s.au || []).slice(0, 8).join("，"))}${(s.au || []).length > 8 ? " 等" : ""}</p>
      ${p && p.zh ? `<p class="sum"><span class="k">简介</span>${esc(p.zh)}</p>` : ""}
      ${links(id, `<span class="src mono">${s.d ? "论文 " + esc(s.d) + " · " : ""}加入 ${esc(fmtTime(v.at))}${v.read && v.readAt ? " · 读完 " + esc(fmtTime(v.readAt)) : ""}</span><button class="rm" data-rm="${esc(id)}">移除</button>`)}
    </article>`;
  }
  function renderMine() {
    let items = Object.entries(myList);
    const total = items.length, nRead = items.filter(([, v]) => v.read).length;
    if (mine.show === "unread") items = items.filter(([, v]) => !v.read);
    if (mine.show === "read") items = items.filter(([, v]) => v.read);
    if (st.q) {
      const ws = st.q.toLowerCase().split(/\s+/).filter(Boolean);
      items = items.filter(([id, v]) => { const p = byId(id) || v.p || {}; const hay = (id + " " + (p.t || "") + " " + (p.au || []).join(" ") + " " + (p.zh || "")).toLowerCase(); return ws.every((w) => hay.includes(w)); });
    }
    const cmpAt = (a, b) => (a[1].at < b[1].at ? -1 : a[1].at > b[1].at ? 1 : 0);
    items.sort((a, b) => (mine.sort === "new" ? -cmpAt(a, b) : mine.sort === "old" ? cmpAt(a, b) : (gcount[b[0]] || 0) - (gcount[a[0]] || 0)));
    const syncLine = !sb ? "阅读清单保存在当前浏览器（localStorage）。"
      : user ? `已登录同步（${esc(user.email || "")}）：阅读清单保存在云端，并在登录的各设备间同步。`
      : "未登录：阅读清单只保存在当前浏览器（localStorage），清除浏览器数据会丢失。点右上角“登录同步”可在手机、电脑间同步。";
    const tools = `<div class="mine-tools">
      <label>排序 <select id="mine-sort"><option value="new"${mine.sort === "new" ? " selected" : ""}>最近加入</option><option value="old"${mine.sort === "old" ? " selected" : ""}>最早加入</option>${gOK ? `<option value="opens"${mine.sort === "opens" ? " selected" : ""}>打开次数</option>` : ""}</select></label>
      <div class="seg mini">${[["all", "全部"], ["unread", "未读"], ["read", "已读"]].map(([k, l]) => `<button data-show="${k}" aria-selected="${mine.show === k}">${l}</button>`).join("")}</div>
      <span class="grow"></span>
      <button class="tool" id="mine-export">导出</button>
      <label class="tool">导入<input type="file" id="mine-import" accept="application/json,.json" hidden></label>
    </div>
    <p class="hint">${syncLine}“导出”可下载 JSON 备份，“导入”与当前清单合并。</p>`;
    $("#list").innerHTML = tools + (items.length ? items.map(([id, v]) => mineCard(id, v)).join("")
      : `<p class="empty">${total ? "没有符合条件的论文。" : "阅读清单为空 · 在任意论文卡片左上角勾选“阅读清单”即可加入"}</p>`);
    $("#count").textContent = `阅读清单 ${total} 篇 · 已读 ${nRead} · 未读 ${total - nRead} · 显示 ${items.length}`;
    $("#more").hidden = true;
    $("#mine-sort").addEventListener("change", (e) => { mine.sort = e.target.value; render(); });
    document.querySelectorAll(".mine-tools [data-show]").forEach((b) => b.addEventListener("click", () => { mine.show = b.dataset.show; render(); }));
    $("#mine-export").addEventListener("click", exportData);
    $("#mine-import").addEventListener("change", (e) => { if (e.target.files[0]) importData(e.target.files[0]); e.target.value = ""; });
  }
  function render() {
    if (!manifest) return;
    renderToday();
    if (st.view === "mine") { renderMine(); return; }
    if (st.view === "picks") {
      const items = picks.filter(match);
      const groups = new Map();
      for (const p of items) { if (!groups.has(p.pk.date)) groups.set(p.pk.date, []); groups.get(p.pk.date).push(p); }
      let html = "";
      for (const d of [...groups.keys()].sort().reverse()) {
        const g = groups.get(d).sort((a, b) => a.pk.rank - b.pk.rank);
        html += `<section><div class="day"><h2>★ ${fmtDay(d)}</h2><span>${g.length} 篇推荐</span></div>${g.map((p) => card(p, true)).join("")}</section>`;
      }
      $("#list").innerHTML = html || '<p class="empty">没有符合条件的推荐论文。</p>';
      $("#count").textContent = `往期推荐 ${picks.length} 篇 · 显示 ${items.length} · 可按方向或兴趣标签筛选`;
      $("#more").hidden = true;
      return;
    }
    $("#more").hidden = loaded >= manifest.months.length;
    const items = papers.filter(match);
    const groups = new Map();
    for (const p of items) { if (!groups.has(p.d)) groups.set(p.d, []); groups.get(p.d).push(p); }
    let html = "";
    for (const d of [...groups.keys()].sort().reverse()) {
      const g = groups.get(d).sort((a, b) => (!!b.pk - !!a.pk) || (b.r || 0) - (a.r || 0));
      html += `<section><div class="day"><h2>${fmtDay(d)}</h2><span>${g.length} 篇 · 按推荐度排序</span></div>${g.map((p) => card(p, false)).join("")}</section>`;
    }
    $("#list").innerHTML = html || `<p class="empty">没有符合条件的论文${loaded < manifest.months.length ? "，可尝试加载更早的月份" : ""}。</p>`;
    const nFlag = items.filter((p) => Object.keys(p.fl).length).length;
    $("#count").textContent = `显示 ${items.length} 篇 · 清华/北大/北航 ${nFlag} 篇 · 已加载 ${loaded}/${manifest.months.length} 个月`;
  }

  // ---------------------------------------------------------------- events
  function bind() {
    document.querySelectorAll(".seg button[data-topic]").forEach((b) => b.addEventListener("click", () => { st.topic = b.dataset.topic; update(); }));
    document.querySelectorAll(".views button").forEach((b) => b.addEventListener("click", () => { st.view = b.dataset.view; update(); window.scrollTo(0, 0); }));
    $("#interests").innerHTML = '<button class="chip" data-it="">全部兴趣</button>' + Object.entries(INTEREST).map(([k, v]) => `<button class="chip" data-it="${k}">${v}</button>`).join("");
    document.querySelectorAll("#interests .chip").forEach((c) => c.addEventListener("click", () => { st.it = c.dataset.it; update(); }));
    $("#only-flag").addEventListener("change", (e) => { st.onlyFlag = e.target.checked; update(); });
    document.querySelectorAll("#schools .chip").forEach((c) => c.addEventListener("click", () => {
      const k = c.dataset.school;
      if (st.schools.has(k) && st.schools.size > 1) st.schools.delete(k); else st.schools.add(k);
      update();
    }));
    // event delegation: covers every card rendered later (lists, picks, archive, search, reading list)
    const onOpen = (e) => {
      const a = e.target.closest("a[data-open]");
      if (!a || (e.type === "auxclick" && e.button !== 1)) return;
      countClick(a.dataset.open);      // never preventDefault: navigation goes ahead normally
    };
    document.addEventListener("click", onOpen, true);
    document.addEventListener("auxclick", onOpen, true);
    document.addEventListener("change", (e) => {
      const t = e.target;
      if (t.matches("input[data-save]")) { setChecked(t.dataset.save, t.checked); if (st.view === "mine" && !t.checked) render(); }
      else if (t.matches("input[data-read]")) { setRead(t.dataset.read, t.checked); render(); }
    });
    document.addEventListener("click", (e) => { const b = e.target.closest("button[data-rm]"); if (b) { setChecked(b.dataset.rm, false); render(); } });
    window.addEventListener("storage", (e) => { if (e.key === LS_LIST) { myList = lsGet(LS_LIST); badge(); render(); } });
    let t;
    $("#q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { st.q = e.target.value.trim(); update(); }, 150); });
    $("#more").addEventListener("click", async () => { $("#more").disabled = true; await loadMore(1); $("#more").disabled = false; render(); });
    // auth modal
    const open = () => { $("#auth").hidden = false; paintAuth(); (user ? $("#auth-resync") : $("#auth-email")).focus(); };
    const close = () => { $("#auth").hidden = true; };
    $("#sync-btn").addEventListener("click", open);
    $("#auth-close").addEventListener("click", close);
    $("#auth").addEventListener("click", (e) => { if (e.target.id === "auth") close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    $("#auth-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = $("#auth-email").value.trim(), msg = $("#auth-msg");
      msg.textContent = "正在发送…";
      const { error } = await sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin + location.pathname } });
      if (error) { msg.textContent = /restricted|database error|not allowed|signups/i.test(error.message) ? "该邮箱未开通同步。" : "发送失败：" + error.message; return; }
      msg.textContent = "已发送，请查收邮件（可能在垃圾箱）。"; $("#auth-step2").hidden = false;
    });
    $("#auth-paste").addEventListener("submit", (e) => { e.preventDefault(); finishLogin($("#auth-code").value); });
    $("#auth-resync").addEventListener("click", syncNow);
    $("#auth-logout").addEventListener("click", async () => {
      lsSet(LS_MERGED, ""); user = null; paintAuth(); render(); setSyncState("");
      try { const { error } = await sb.auth.signOut(); if (error) await sb.auth.signOut({ scope: "local" }); } catch (e) { try { await sb.auth.signOut({ scope: "local" }); } catch (_) {} }
      lsSet(LS_MERGED, ""); user = null; paintAuth(); render();
    });
  }
  function update() { syncControls(); writeHash(); render(); }

  async function init() {
    readHash(); bind(); syncControls(); badge(); paintAuth();
    if (sb) {
      sb.auth.onAuthStateChange((ev, session) => {
        const was = user && user.id;
        user = session ? session.user : null;
        paintAuth();
        if (user && user.id !== was) { setTimeout(syncNow, 0); if (!$("#auth").hidden && ev === "SIGNED_IN") setSyncState("登录成功，正在同步…"); }
        if (!user && was) render();
        if (location.hash.includes("access_token")) writeHash();
      });
    }
    let gc = Promise.resolve();
    if (sb) gc = loadGlobalCounts();
    else document.body.classList.add("no-gc");
    try { manifest = await getJSON("manifest.json"); }
    catch (e) { $("#list").innerHTML = '<p class="empty">数据加载失败，请稍后刷新。</p>'; return; }
    $("#s-total").textContent = manifest.total;
    $("#s-cockpit").textContent = manifest.counts.cockpit;
    $("#s-embodied").textContent = manifest.counts.embodied;
    $("#s-edge").textContent = manifest.counts.edge ?? 0;
    $("#s-picks").textContent = manifest.counts.picks ?? 0;
    $("#s-flag").textContent = manifest.counts.flagged;
    $("#updated").textContent = "LAST UPDATE " + fmtTime(manifest.updated) + " (UTC+8)";
    const [, pk] = await Promise.all([loadMore(Math.min(2, manifest.months.length)), getJSON("picks.json").catch(() => []),
      Promise.race([gc, new Promise((r) => setTimeout(r, 2500))])]);    // don't wait forever for counts
    picks = pk;
    render();
    gc.then(() => { if (gOK) render(); });
  }
  init();
})();
