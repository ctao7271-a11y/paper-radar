"""Headless check of the reading list + open counter (run against a local or live URL)."""
import sys, json, os
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8766/"
SHOTS = "/workspace/paper-radar/shots"
tag = sys.argv[2] if len(sys.argv) > 2 else "local"
res = {}
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1150, "height": 1300}, accept_downloads=True)
    ctx.route("https://arxiv.org/**", lambda r: r.fulfill(status=200, body="stub", content_type="text/html"))  # don't hit arXiv
    pg = ctx.new_page()
    pg.goto(URL); pg.wait_for_selector("#list .card")
    card = pg.locator("#list .card").first
    pid = card.get_attribute("data-id"); res["paper"] = pid
    res["checkbox_on_every_card"] = pg.locator(".card").count() == pg.locator(".card .pick-box input").count()
    res["today_block_has_checkbox"] = pg.locator("#today .card .pick-box input").count() > 0
    # 1) check -> reading list
    card.locator(".pick-box input").check()
    res["badge_after_check"] = pg.locator("#mine-n").inner_text()
    # 2) open counter: title, arXiv link, PDF link (each opens a popup; navigation must not be blocked)
    for sel in ["h3 a", ".links a >> nth=0", ".links a >> nth=1"]:
        with ctx.expect_page() as newp:
            card.locator(sel).click()
        newp.value.close()
    res["count_after_3_clicks"] = card.locator(".opens").inner_text()
    card.scroll_into_view_if_needed(); pg.evaluate("window.scrollBy(0,-90)")
    card.screenshot(path=f"{SHOTS}/{tag}-card-checkbox-count.png")
    # 3) a second paper via search view + picks archive
    pg.goto(URL + "#v=picks"); pg.wait_for_selector("#list .card")
    c2 = pg.locator("#list .card").nth(1); pid2 = c2.get_attribute("data-id"); c2.locator(".pick-box input").check()
    with ctx.expect_page() as newp:
        c2.locator(".links a >> nth=1").click()
    newp.value.close()
    # 4) persistence after reload
    pg.goto(URL + "#v=mine"); pg.reload(); pg.wait_for_selector(".mine-tools")
    res["list_items_after_reload"] = pg.locator(".mine-item").count()
    res["list_ids"] = [x.get_attribute("data-id") for x in pg.locator(".mine-item").all()]
    res["count_persisted"] = pg.locator(f'.mine-item[data-id="{pid}"] .opens').inner_text()
    pg.locator(f'.mine-item[data-id="{pid}"] input[data-read]').check()
    res["read_flag"] = pg.evaluate("JSON.parse(localStorage.getItem('paperRadar.readingList.v1'))")[pid]["read"]
    pg.locator(".mine-tools [data-show=unread]").click(); res["unread_filter_count"] = pg.locator(".mine-item").count()
    pg.locator(".mine-tools [data-show=all]").click()
    pg.select_option("#mine-sort", "old"); res["sorted_old_first"] = pg.locator(".mine-item").first.get_attribute("data-id")
    pg.select_option("#mine-sort", "new")
    pg.screenshot(path=f"{SHOTS}/{tag}-reading-list.png", full_page=False)
    # 5) export
    with pg.expect_download() as dl:
        pg.click("#mine-export")
    path = f"/tmp/{tag}-export.json"; dl.value.save_as(path)
    exp = json.load(open(path)); res["export_ids"] = sorted(exp["readingList"]); res["export_opens"] = exp["openCounts"]
    # 6) remove, then import restores (fresh context = "another device")
    pg.locator(f'.mine-item[data-id="{pid2}"] button[data-rm]').click()
    res["after_remove"] = pg.locator(".mine-item").count()
    ctx2 = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
    p2 = ctx2.new_page(); p2.goto(URL + "#v=mine"); p2.wait_for_selector(".mine-tools")
    res["fresh_device_empty"] = p2.locator(".mine-item").count() == 0
    p2.on("dialog", lambda d: (res.__setitem__("import_msg", d.message), d.accept()))
    p2.set_input_files("#mine-import", path); p2.wait_for_timeout(500)
    res["after_import_items"] = p2.locator(".mine-item").count()
    res["after_import_opens"] = p2.locator(f'.mine-item[data-id="{pid}"] .opens').inner_text()
    p2.screenshot(path=f"{SHOTS}/{tag}-mobile-reading-list.png")
    p2.goto(URL); p2.wait_for_selector("#list .card"); p2.wait_for_timeout(300)
    p2.screenshot(path=f"{SHOTS}/{tag}-mobile-cards.png")
    b.close()
print(json.dumps(res, ensure_ascii=False, indent=1))
