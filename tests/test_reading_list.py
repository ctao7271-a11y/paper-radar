"""Headless end-to-end check: reading list (local + cloud sync), global open counter, export/import, mobile.

usage: python tests/test_reading_list.py <site url> <tag> [test-email test-password]
Clicks made here really increment the global counter; the script prints the per-paper deltas so they can be
subtracted afterwards (see RUNBOOK).
"""
import sys, json, re, time
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8766/"
tag = sys.argv[2] if len(sys.argv) > 2 else "local"
EMAIL = sys.argv[3] if len(sys.argv) > 3 else ""
PW = sys.argv[4] if len(sys.argv) > 4 else ""
SHOTS = "/workspace/paper-radar/shots"
SB_URL = "https://gabsjglbryeftyolopev.supabase.co"
SB_KEY = "sb_publishable_ExR78YJCTpzaDXYbncU3PA_XKAmAK7B"
res, deltas = {}, {}

def count_of(card):
    t = card.locator(".opens").inner_text() if card.locator(".opens").count() else ""
    m = re.search(r"(\d+)", t)
    return int(m.group(1)) if m else None

def db_count(pg, pid):
    return pg.evaluate("""async ([u,k,id]) => { const r = await fetch(`${u}/rest/v1/global_clicks?select=count&arxiv_id=eq.${id}`, {headers:{apikey:k}}); const j = await r.json(); return j.length ? Number(j[0].count) : 0; }""", [SB_URL, SB_KEY, pid])

def login(pg):
    pg.evaluate("""async ([u,k,e,p]) => { const c = window.supabase.createClient(u,k,{auth:{autoRefreshToken:false}}); const {error} = await c.auth.signInWithPassword({email:e,password:p}); if (error) throw error; }""", [SB_URL, SB_KEY, EMAIL, PW])
    pg.reload(); pg.wait_for_selector("#sync-btn.on", timeout=15000)
    pg.wait_for_function("""() => (localStorage.getItem('paperRadar.mergedUser.v1')||'').length > 4 && !document.querySelector('#sync-btn').classList.contains('busy')""", timeout=20000)
    pg.wait_for_timeout(800)

def cloud_ids(pg):
    return pg.evaluate("""async ([u,k]) => { const t = JSON.parse(localStorage.getItem("sb-gabsjglbryeftyolopev-auth-token")); const c = window.supabase.createClient(u,k,{auth:{persistSession:false,autoRefreshToken:false},global:{headers:{Authorization:"Bearer "+t.access_token}}}); const {data,error} = await c.from('reading_list').select('arxiv_id,read'); if (error) throw error; return data; }""", [SB_URL, SB_KEY])

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    def ctx_new(**kw):
        c = b.new_context(accept_downloads=True, **kw)
        c.route("https://arxiv.org/**", lambda r: r.fulfill(status=200, body="stub", content_type="text/html"))
        return c
    # ---------------- A. visitor 1, logged out
    ctx = ctx_new(viewport={"width": 1200, "height": 1300})
    pg = ctx.new_page(); pg.goto(URL); pg.wait_for_selector("#list .card .opens", timeout=15000)
    res["checkbox_on_every_card"] = pg.locator(".card").count() == pg.locator(".card input[data-save]").count()
    res["counter_on_every_card"] = pg.locator(".card").count() == pg.locator(".card .opens").count()
    card = pg.locator("#list .card").first; pid = card.get_attribute("data-id"); res["paper"] = pid
    g0 = count_of(card); res["count_before"] = g0
    card.locator("input[data-save]").check(); res["badge_after_check"] = pg.locator("#mine-n").inner_text()
    def click(sel):
        with ctx.expect_page() as np_:
            card.locator(sel).click()
        np_.value.close()
    click("h3 a"); pg.wait_for_timeout(800); res["after_title_click"] = count_of(card)
    click(".links a >> nth=0"); click(".links a >> nth=1"); pg.wait_for_timeout(800)
    res["after_abs+pdf_within_30s(throttled)"] = count_of(card)
    pg.evaluate("localStorage.removeItem('paperRadar.clickThrottle.v1')")
    click(".links a >> nth=1"); pg.wait_for_timeout(1200); res["after_pdf_click_after_throttle_reset"] = count_of(card)
    pg.evaluate("localStorage.removeItem('paperRadar.clickThrottle.v1')")
    click(".links a >> nth=0"); pg.wait_for_timeout(1200); res["after_abs_click"] = count_of(card)
    res["db_count"] = db_count(pg, pid); deltas[pid] = res["db_count"] - (g0 or 0)
    card.scroll_into_view_if_needed(); pg.evaluate("window.scrollBy(0,-120)")
    card.screenshot(path=f"{SHOTS}/{tag}-card-checkbox-count.png")
    # picks archive card
    pg.goto(URL + "#v=picks"); pg.wait_for_selector("#list .card")
    c2 = pg.locator("#list .card").nth(1); pid2 = c2.get_attribute("data-id"); c2.locator("input[data-save]").check()
    # persistence
    pg.goto(URL + "#v=mine"); pg.reload(); pg.wait_for_selector(".mine-tools")
    res["list_after_reload"] = sorted(x.get_attribute("data-id") for x in pg.locator(".mine-item").all())
    res["count_after_reload"] = count_of(pg.locator(f'.mine-item[data-id="{pid}"]'))
    pg.locator(f'.mine-item[data-id="{pid}"] input[data-read]').check()
    pg.locator(".mine-tools [data-show=unread]").click(); res["unread_filter"] = pg.locator(".mine-item").count()
    pg.locator(".mine-tools [data-show=all]").click()
    pg.select_option("#mine-sort", "old"); res["oldest_first"] = pg.locator(".mine-item").first.get_attribute("data-id")
    pg.select_option("#mine-sort", "new")
    pg.screenshot(path=f"{SHOTS}/{tag}-reading-list.png")
    with pg.expect_download() as dl:
        pg.click("#mine-export")
    path = f"/tmp/{tag}-export.json"; dl.value.save_as(path)
    res["export_ids"] = sorted(json.load(open(path))["readingList"])
    pg.locator(f'.mine-item[data-id="{pid2}"] button[data-rm]').click(); res["after_remove"] = pg.locator(".mine-item").count()
    # ---------------- B. visitor 2 (another browser): sees everyone's total; import on mobile
    ctx2 = ctx_new(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
    p2 = ctx2.new_page(); p2.goto(URL + "#q=" + pid); p2.wait_for_selector("#list .card .opens", timeout=15000)
    res["other_visitor_sees_total"] = count_of(p2.locator("#list .card").first)
    p2.goto(URL + "#v=mine"); p2.reload(); p2.wait_for_selector(".mine-tools")
    p2.on("dialog", lambda d: (res.__setitem__("import_msg", d.message), d.accept()))
    p2.set_input_files("#mine-import", path); p2.wait_for_timeout(600)
    res["import_items"] = p2.locator(".mine-item").count()
    p2.screenshot(path=f"{SHOTS}/{tag}-mobile-reading-list.png")
    p2.goto(URL); p2.wait_for_selector("#list .card .opens"); p2.wait_for_timeout(300)
    p2.screenshot(path=f"{SHOTS}/{tag}-mobile.png")
    p2.screenshot(path=f"{SHOTS}/{tag}-mobile-full.png", full_page=False)
    # stranger cannot sign up (no e-mail is sent: the account insert is rejected)
    p2.click("#sync-btn"); p2.fill("#auth-email", f"stranger-{int(time.time())}@example.invalid"); p2.click("#auth-form button")
    p2.wait_for_timeout(2500); res["stranger_login_msg"] = p2.inner_text("#auth-msg")
    # ---------------- C. cloud sync with a temporary allowlisted test account
    if EMAIL:
        d1 = ctx_new(viewport={"width": 1200, "height": 1300}); a = d1.new_page(); a.goto(URL); a.wait_for_selector("#list .card")
        x = a.locator("#list .card").nth(2).get_attribute("data-id")
        a.locator("#list .card").nth(2).locator("input[data-save]").check()      # saved before login (local only)
        login(a)
        res["device1_sync_button"] = a.inner_text("#sync-btn")
        res["cloud_after_first_login_merge"] = cloud_ids(a)
        y = a.locator("#list .card").nth(3).get_attribute("data-id")
        a.locator("#list .card").nth(3).locator("input[data-save]").check(); a.wait_for_timeout(1500)
        res["cloud_after_check_while_logged_in"] = sorted(r["arxiv_id"] for r in cloud_ids(a))
        d2 = ctx_new(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        m = d2.new_page(); m.goto(URL + "#v=mine"); m.wait_for_selector(".mine-tools"); login(m)
        res["device2_list"] = sorted(x_.get_attribute("data-id") for x_ in m.locator(".mine-item").all())
        m.locator(f'.mine-item[data-id="{x}"] input[data-read]').check(); m.wait_for_timeout(800)
        m.locator(f'.mine-item[data-id="{y}"] button[data-rm]').click(); m.wait_for_timeout(1500)
        m.screenshot(path=f"{SHOTS}/{tag}-mobile-synced-list.png")
        a.goto(URL + "#v=mine"); a.reload(); a.wait_for_selector("#sync-btn.on"); a.wait_for_timeout(2500)
        res["device1_after_device2_changes"] = [(i.get_attribute("data-id"), "is-read" in (i.get_attribute("class") or "")) for i in a.locator(".mine-item").all()]
        a.click("#sync-btn"); a.wait_for_timeout(300); a.screenshot(path=f"{SHOTS}/{tag}-sync-panel.png")
        a.click("#auth-logout"); a.wait_for_timeout(800); res["after_logout_button"] = a.inner_text("#sync-btn"); a.reload(); a.wait_for_selector("#sync-btn"); a.wait_for_timeout(1500); res["after_logout_reload_button"] = a.inner_text("#sync-btn"); res["after_logout_local_list_kept"] = a.locator("#mine-n").inner_text()
        m.evaluate("localStorage.clear()")
    b.close()
print(json.dumps(res, ensure_ascii=False, indent=1))
print("GLOBAL_CLICK_DELTAS", json.dumps(deltas))
