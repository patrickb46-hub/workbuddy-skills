#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""web_upload.py — B 站网页投稿（真实 Chromium + 已有 cookie）

## 为什么需要它

`biliup 0.2.4`（当前最新）已经和 B 站接口脱节，实测三处全挂：
  · 登录：走 `passport-tv-login/qrcode`，该接口已废弃 → 扫码永远拿不到 access_token
  · 投稿：`preupload` 恒返回 `{"code":-400}`，换 bda2/qn/alia 三条线路一样
  · 直接调 member.bilibili.com：WAF 按 TLS 指纹拦截，curl / urllib 都是 403 HTML
所以投稿只能走真实浏览器内核。本脚本用 Playwright 驱动 Chrome for Testing，
复用 `bilibili-studio/data/cookies.json` 的登录态，走网页 UI 完成投稿。

## 用法

  # 只填表不提交（先看一眼）
  python web_upload.py --video out.mp4 --title "标题" --desc-file desc.txt \
      --tags "a,b,c" --cover cover.png

  # 提交
  python web_upload.py --video out.mp4 --title "标题" --desc-file desc.txt \
      --tags "a,b,c" --cover cover.png --submit

## 分工

  · 视频上传 / 标题 / 简介 / 标签 / 分区 / 封面：脚本自动
  · 「立即投稿」后的短信或人机验证：**必须人来做**，脚本不绕过
  · 因此 --submit 时用 --headful，窗口置顶，等人点完验证

## 已知坑

  1. 首次投稿会弹「投稿须知」遮罩 → 脚本自动找「我已知晓/确定/关闭」
  2. 封面上传后会弹「16:9 未修改，是否同步」→ 必须点「确认同步」再点「完成」，
     否则封面弹窗不关，「立即投稿」永远点不到
  3. 分区没有二级，选到「知识」就是终点（2026-10 实测）
  4. 窗口太矮会导致底部按钮不在视口 → 点之前先 scrollTo 底部
"""
import argparse, json, os, sys
from playwright.sync_api import sync_playwright

EXE_DEFAULT = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/"
    "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
CK_DEFAULT = os.path.expanduser("~/.workbuddy/skills/bilibili-studio/data/cookies.json")
PROFILE_DEFAULT = os.path.expanduser("~/.workbuddy/skills/bilibili-studio/data/pw-profile")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FRAME = "https://member.bilibili.com/platform/upload/video/frame"


def log(*a):
    print(*a, flush=True)


def close_popups(pg):
    """关掉「投稿须知」一类遮罩弹窗"""
    for _ in range(4):
        closed = False
        for txt in ["我已知晓", "我知道了", "知道了", "确定", "同意", "不再提示", "关闭"]:
            btn = pg.get_by_text(txt, exact=True)
            if btn.count() > 0:
                try:
                    if btn.first.is_visible():
                        btn.first.click(); pg.wait_for_timeout(900)
                        log("  关闭弹窗:", txt); closed = True; break
                except Exception:
                    pass
        if not closed:
            for sel in [".bcc-dialog__close", ".bcc-dialog-close", ".close-icon"]:
                x = pg.locator(sel)
                if x.count() > 0:
                    try:
                        x.first.click(); pg.wait_for_timeout(800); closed = True; break
                    except Exception:
                        pass
        if not closed:
            break


def click_text_any(pg, texts, exact=False, timeout=6000):
    """跨主文档 / iframe / 弹窗页找按钮——封面编辑器是覆盖层，元素常常不在主 frame 里"""
    pages = list(pg.context.pages) if pg.context else [pg]
    for txt in texts:
        for one in pages:
            frames = [one.main_frame] + [f for f in one.frames if f != one.main_frame]
            for fr in frames:
                try:
                    loc = fr.get_by_text(txt, exact=exact)
                    if loc.count() == 0:
                        continue
                    el = loc.first
                    if el.is_visible():
                        el.click(timeout=timeout)
                        log(f"→ 点击「{txt}」@ {fr.url[:40]}")
                        return True
                except Exception:
                    continue
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--desc", default="")
    ap.add_argument("--desc-file", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--cover", default="")
    ap.add_argument("--partition", default="知识", help="一级分区名，2026-10 起无二级")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--headful", action="store_true", help="--submit 时建议开启，便于人工过验证")
    ap.add_argument("--profile", default=PROFILE_DEFAULT)
    ap.add_argument("--wait-min", type=int, default=15, help="提交后等人工验证的分钟数")
    a = ap.parse_args()

    desc = a.desc
    if a.desc_file:
        desc = open(a.desc_file, encoding="utf-8").read().strip()

    ck = json.load(open(CK_DEFAULT))
    cookies = [{"name": k, "value": v, "domain": ".bilibili.com", "path": "/"} for k, v in ck.items()]

    with sync_playwright() as p:
        if a.headful:
            ctx = p.chromium.launch_persistent_context(
                a.profile, executable_path=EXE_DEFAULT, headless=False,
                viewport={"width": 1280, "height": 760}, user_agent=UA,
                locale="zh-CN", timezone_id="Asia/Shanghai",
                args=["--no-sandbox", "--window-size=1280,820", "--window-position=40,30"])
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            b = p.chromium.launch(headless=True, executable_path=EXE_DEFAULT, args=["--no-sandbox"])
            ctx = b.new_context(viewport={"width": 1280, "height": 760}, user_agent=UA, locale="zh-CN")
            pg = ctx.new_page()
        ctx.add_cookies(cookies)
        pg.goto(FRAME, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(6000)

        pg.locator("input[type=file]").first.set_input_files(a.video)
        log("→ 上传中…")
        for _ in range(90):
            pg.wait_for_timeout(2000)
            if pg.locator("input[placeholder='请输入稿件标题']").count() > 0:
                break
        else:
            sys.exit("编辑页没出现")
        log("→ 编辑页就绪")

        close_popups(pg)

        # 标题
        ti = pg.locator("input[placeholder='请输入稿件标题']").first
        ti.click(); ti.fill(""); ti.type(a.title, delay=8)

        # 创作声明（必填）
        try:
            pg.locator("input[placeholder*='创作声明']").first.click()
            pg.wait_for_timeout(900)
            op = pg.locator(".bcc-option")
            for i in range(op.count()):
                if "无需标注" in op.nth(i).inner_text():
                    op.nth(i).click(); break
            pg.wait_for_timeout(400)
        except Exception as e:
            log("! 创作声明:", str(e)[:60])

        # 分区（一级即终点）
        try:
            pg.locator(".select-container").first.click()
            pg.wait_for_timeout(1500)
            pg.get_by_text(a.partition, exact=True).first.click()
            pg.wait_for_timeout(800)
            log("→ 分区:", a.partition)
        except Exception as e:
            log("! 分区:", str(e)[:80])

        # 标签
        if a.tags:
            tag = pg.locator("input[placeholder='按回车键Enter创建标签']").first
            tag.click()
            for _ in range(8):
                tag.press("Backspace")
            for t in [x.strip() for x in a.tags.split(",") if x.strip()]:
                tag.fill(t); pg.wait_for_timeout(300); tag.press("Enter"); pg.wait_for_timeout(200)
            log("→ 标签:", len(a.tags.split(",")))

        # 简介
        if desc:
            try:
                pg.locator("div[contenteditable='true']").first.click()
                pg.keyboard.type(desc, delay=1)
                log("→ 简介 ok")
            except Exception as e:
                log("! 简介:", str(e)[:60])

        # 封面：B 站封面编辑器会弹「4:3 与 16:9 未同步，是否同步」→ 必须点「确认同步」再「完成」，
        # 否则编辑器的弹窗不关、封面不会被保存（2026-11 实测：点早了会扑空）
        if a.cover:
            try:
                pg.get_by_text("添加封面", exact=False).first.click()
                pg.wait_for_timeout(3200)
                with pg.expect_file_chooser(timeout=20000) as fc:
                    pg.get_by_text("上传封面", exact=False).first.click()
                fc.value.set_files(a.cover)
                log("→ 封面已选，等编辑器加载")
                pg.wait_for_timeout(8000)

                if click_text_any(pg, ["确认同步", "确定同步"]):
                    pg.wait_for_timeout(3200)
                else:
                    log("! 没找到「确认同步」")

                if click_text_any(pg, ["完成"], exact=True):
                    pg.wait_for_timeout(3200)
                else:
                    log("! 没找到「完成」")

                # 收尾：编辑器可能还有一层「确定/关闭」
                close_popups(pg)
                pg.wait_for_timeout(1500)
                pg.screenshot(path="qc-cover-step.png", full_page=False)
                log("→ 封面步骤截图 qc-cover-step.png")
            except Exception as e:
                log("! 封面:", str(e)[:100])

        pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        pg.wait_for_timeout(1200)
        if a.headful:
            pg.bring_to_front()
        pg.screenshot(path="qc-web-form.png", full_page=True)

        if not a.submit:
            log("（未提交，截图 qc-web-form.png）")
            ctx.close(); return

        for _ in range(2):
            try:
                pg.get_by_text("立即投稿", exact=True).first.click(timeout=8000)
                log("→ 已点投稿")
                break
            except Exception:
                log("→ 投稿被遮挡，请在窗口里手动点「立即投稿」")
                pg.wait_for_timeout(3000)

        # 等人工过验证
        for i in range(a.wait_min * 12):
            try:
                pg.wait_for_timeout(5000)
                if "/archive-process" in pg.url or "/upload-manager" in pg.url:
                    log(f"SUCCESS @{i*5}s →", pg.url)
                    pg.screenshot(path="qc-web-success.png", full_page=True)
                    break
                if "投稿成功" in pg.inner_text("body"):
                    log(f"SUCCESS @{i*5}s")
                    break
            except Exception:
                log("窗口已关闭")
                break
        log("FINAL URL:", pg.url)
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
