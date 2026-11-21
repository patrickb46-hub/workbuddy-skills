#!/usr/bin/env python3
"""三条连发：一次短信验证，剩下全自动。

风控弹「请完成短信验证」时需要人手动点一次「获取验证码」并填码；
这一步只能在可见窗口里做，所以用 headful + 持久化 profile（同一会话内后续投稿不再验证）。

用法：
    python3 bili_publish_batch.py --jobs jobs.json [--wait-verify-min 12]
"""
import argparse
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bili_publish import (CK, EXE, UA, FRAME, log, shot,
                          pick_partition, set_declaration, set_cover)

PROFILE = os.path.expanduser(os.environ.get(
    "BILI_SECRET_DIR", "~/.workbuddy/secrets/bili") + "/pw-profile")


def wait_verify(pg, minutes, tag):
    """等用户把短信验证过掉。返回 True 表示已过 / 从未出现。"""
    if not pg.locator(".base-verify").count():
        return True
    log("⚠ 出现短信验证，请在窗口里点「获取验证码」并填码（需要人工）")
    shot(pg, f"verify-{tag}")
    for i in range(minutes * 12):
        pg.wait_for_timeout(5000)
        try:
            if not pg.locator(".base-verify").count():
                log(f"→ 验证已通过（{i*5}s）")
                pg.wait_for_timeout(2000)
                return True
        except Exception:
            return True
    log("! 验证超时")
    return False


def fill_and_submit(pg, job, idx, dry=False):
    log(f"\n=== [{idx}] {job['title']} ===")
    pg.goto(FRAME, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(6000)
    pg.locator("input[type=file]").first.set_input_files(os.path.abspath(job["video"]))
    log("→ 上传中…")
    for _ in range(90):
        pg.wait_for_timeout(2000)
        if pg.locator("input[placeholder='请输入稿件标题']").count():
            break
    else:
        shot(pg, f"no-editor-{idx}")
        return False
    log("→ 编辑页就绪")

    if not wait_verify(pg, job.get("verify_min", 12), idx):
        return False

    pg.locator("input[placeholder='请输入稿件标题']").fill(job["title"])
    desc = open(job["desc_file"], encoding="utf-8").read().strip()
    pg.locator("div[contenteditable='true']").first.click()
    pg.keyboard.type(desc, delay=1)
    pg.wait_for_timeout(600)
    log("→ 标题 / 简介 ok")

    box = pg.locator(".tag-input, input[placeholder*='标签']").first
    box.click()
    for _ in range(14):
        pg.keyboard.press("Backspace")
    pg.wait_for_timeout(500)
    for t in [x.strip() for x in job["tags"].split(",") if x.strip()]:
        pg.keyboard.type(t, delay=30)
        pg.wait_for_timeout(650)
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(350)
    log("→ 标签 ok")

    pick_partition(pg, job.get("partition", "人工智能"))
    set_declaration(pg)
    if job.get("cover"):
        set_cover(pg, job.get("cover43") or job["cover"], job["cover"])
    shot(pg, f"form-{idx}")
    if dry:
        log("（dry-run：不点投稿，只留截图）")
        return True

    for _ in range(3):
        try:
            pg.get_by_text("立即投稿", exact=True).first.click(timeout=8000)
            log("→ 已点「立即投稿」")
            break
        except Exception:
            pg.mouse.wheel(0, 2000)
            pg.wait_for_timeout(2000)

    ok = False
    for i in range(36):
        try:
            pg.wait_for_timeout(5000)
        except Exception:
            # B 站投稿成功后会把页面交给新标签，旧 page 被关掉是正常现象
            log("→ 原页面已关闭（投稿页转到新标签），按提交成功处理")
            ok = True
            break
        try:
            if "/archive-process" in pg.url or "/upload-manager" in pg.url:
                log(f"SUCCESS @{i*5}s → {pg.url}")
                ok = True
                break
            if "投稿成功" in pg.inner_text("body"):
                log(f"SUCCESS @{i*5}s（页面提示）")
                ok = True
                break
        except Exception:
            break
    shot(pg, f"result-{idx}")
    if not ok:
        log("! 未确认成功，FINAL URL:", pg.url)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--headful", action="store_true", default=True)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", type=int, default=0)
    a = ap.parse_args()

    jobs = json.load(open(a.jobs, encoding="utf-8"))
    ck = json.load(open(CK))
    cookies = [{"name": k, "value": v, "domain": ".bilibili.com", "path": "/"} for k, v in ck.items()]

    results = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False, executable_path=EXE,
            args=["--no-sandbox", "--window-size=1440,960", "--window-position=40,40"],
            viewport={"width": 1440, "height": 900}, user_agent=UA,
            locale="zh-CN", timezone_id="Asia/Shanghai", accept_downloads=True)
        ctx.add_cookies(cookies)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        if a.only:
            jobs = jobs[a.only-1:a.only]
        for i, job in enumerate(jobs, 1):
            try:
                results.append((job["title"], fill_and_submit(pg, job, i, a.dry)))
            except Exception as e:
                log(f"! 第 {i} 条异常：{type(e).__name__} {str(e)[:120]}")
                results.append((job["title"], False))
        ctx.close()

    log("\n=== 汇总 ===")
    for t, ok in results:
        log(("✅ " if ok else "❌ ") + t)


if __name__ == "__main__":
    main()
