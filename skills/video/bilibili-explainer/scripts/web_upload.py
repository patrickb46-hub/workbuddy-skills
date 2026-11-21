#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""web_upload.py — B 站网页投稿（真实 Chromium + 已有 cookie）

## 为什么需要它

`biliup 0.2.4`（当前最新）已经和 B 站接口脱节，实测三处全挂：
  · 登录：走 `passport-tv-login/qrcode`，该接口已废弃 → 扫码永远拿不到 access_token
  · 投稿：`preupload` 恒返回 `{"code":-400}`，换 bda2/qn/alia 三条线路一样
  · 直接调 member.bilibili.com：WAF 按 TLS 指纹拦截，curl / urllib 都是 403 HTML
所以投稿只能走真实浏览器内核。

## 登录态：两种取法（2026-11-14 改）

1. **CDP 优先（默认）**：如果 Chrome 是带 `--remote-debugging-port=9222` 启动的，
   脚本直接 `connect_over_cdp` 接上去，**用你自己浏览器里已登录的会话**，完全不碰 cookie 文件。
   启动方式见 `scripts/启动Chrome调试模式.command`。
2. **cookies 回退**：CDP 连不上时，退回读 `bilibili-studio/data/cookies.json`，
   自己 launch 一个 Chrome for Testing 注入 cookie。
3. `--no-cdp` 可强制走第 2 种。

注意：**不要**改用 Playwright 的持久化 profile（`launch_persistent_context`）——上一次的
封面编辑器状态会被带进来，一开页就盖住表单，分区/标签点击全被 canvas 拦走（2026-11 实测）。
CDP 连的是用户真实浏览器，没有这个残留问题。

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

EXE_DEFAULT = ("$HOME/Library/Caches/ms-playwright/chromium-1234/"
               "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
# 2026-11-15：凭证移出技能目录（BILI_SECRET_DIR 可覆盖）
_SECRETS = os.path.expanduser(
    os.environ.get("BILI_SECRET_DIR", "~/.workbuddy/secrets/bili"))
CK_DEFAULT = os.path.join(_SECRETS, "cookies.json")
PROFILE_DEFAULT = os.path.join(_SECRETS, "pw-profile")
CDP_DEFAULT = "http://127.0.0.1:9222"
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


def click_deep(pg, text):
    """深度查找并点击：穿透 shadow DOM。B 站封面弹窗的按钮就在 shadow root 里"""
    js = """
    (t) => {
      const vis = (el) => {
        const r = el.getBoundingClientRect();
        return r.width > 4 && r.height > 4;
      };
      function deep(root) {
        const sel = 'button, [role=button], .bcc-button, .vui_button, a, div, span';
        const cands = root.querySelectorAll ? root.querySelectorAll(sel) : [];
        for (const el of cands) {
          if (el.shadowRoot) { const r = deep(el.shadowRoot); if (r) return r; }
          const txt = (el.innerText || el.textContent || '').trim();
          if (txt === t && vis(el)) return el;
        }
        return null;
      }
      const el = deep(document);
      if (el) { el.click(); return true; }
      return false;
    }
    """
    try:
        return bool(pg.evaluate(js, text))
    except Exception:
        return False


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


def nuke_masks(pg):
    """移除封面编辑器那层全屏遮罩。

    2026-11 实测：headful 模式下投稿页一加载就会自动弹出封面编辑器，
    并挂一层 .bcc-dialog__wrap-mask 全屏遮罩，导致标题/分区/标签全部点不进去。
    投稿表单不在这个 dialog 内，移除它不影响填表。
    """
    try:
        n = pg.evaluate("""() => {
          let n = 0;
          document.querySelectorAll('.cover-editor').forEach(e => { e.remove(); n++; });
          document.querySelectorAll('.bcc-dialog__wrap-mask').forEach(e => { e.remove(); n++; });
          document.body.style.overflow = '';
          document.documentElement.style.overflow = '';
          return n;
        }""")
        log("→ 移除遮罩节点:", n)
    except Exception as e:
        log("! 移除遮罩:", str(e)[:60])


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
    ap.add_argument("--no-cdp", action="store_true", help="跳过 CDP，强制用 cookies 模式")
    a = ap.parse_args()

    desc = a.desc
    if a.desc_file:
        desc = open(a.desc_file, encoding="utf-8").read().strip()

    with sync_playwright() as p:
        # ---- 登录态：CDP 优先，cookies 回退 ----
        cdp_mode = False
        b = ctx = None
        if not a.no_cdp:
            try:
                b = p.chromium.connect_over_cdp(CDP_DEFAULT, timeout=6000)
                ctx = b.contexts[0] if b.contexts else b.new_context()
                # 用一个轻量请求确认登录态真的在
                probe = ctx.new_page()
                probe.goto("https://api.bilibili.com/x/web-interface/nav",
                           wait_until="domcontentloaded", timeout=20000)
                txt = probe.inner_text("body")
                probe.close()
                if '"isLogin":true' in txt:
                    cdp_mode = True
                    log("→ 已接管你已登录的 Chrome（CDP 模式，不用 cookie 文件）")
                else:
                    log("! CDP 连通但 B 站未登录，回退 cookies 模式")
                    try: b.close()
                    except Exception: pass
                    b = ctx = None
            except Exception as e:
                log(f"! CDP 不可用（{type(e).__name__}），回退 cookies 模式")
                b = ctx = None

        if ctx is None:
            ck = json.load(open(CK_DEFAULT))
            cookies = [{"name": k, "value": v, "domain": ".bilibili.com", "path": "/"} for k, v in ck.items()]
            # 用干净的 new_context + 手动注入 cookie。
            # 持久化 profile 会把上一次的封面编辑器状态带进来，一开页就盖住表单，
            # 导致分区/标签点击全被 canvas 拦走（2026-11 实测踩过）。
            extra = ["--window-size=1280,900", "--window-position=60,40"] if a.headful else []
            b = p.chromium.launch(headless=not a.headful, executable_path=EXE_DEFAULT,
                                  args=["--no-sandbox"] + extra)
            ctx = b.new_context(viewport={"width": 1280, "height": 760},
                                user_agent=UA, locale="zh-CN", timezone_id="Asia/Shanghai")
            ctx.add_cookies(cookies)
            log("→ cookies 模式启动 Chrome for Testing")

        pg = ctx.new_page()
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
        nuke_masks(pg)
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(900)

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

                # 先破 shadow DOM 找「确认同步」；找不到再用坐标兜底（1280×760 视口实测位置）
                ok = click_deep(pg, "确认同步")
                log("→ 深度点击「确认同步」:", ok)
                if not ok:
                    # 坐标兜底：先问 elementFromPoint 拿到了什么，再决定怎么点
                    try:
                        info = pg.evaluate("""
                        ([x,y]) => {
                          const el = document.elementFromPoint(x,y);
                          if (!el) return 'none';
                          const t = (el.innerText || el.value || '').trim().slice(0,24);
                          const cls = String(el.className || '').slice(0,30);
                          el.click();
                          return el.tagName + '|' + cls + '|' + t;
                        }
                        """, [810, 494])
                        log("→ elementFromPoint(810,494):", info)
                    except Exception as e:
                        log("! elementFromPoint:", str(e)[:60])
                    pg.wait_for_timeout(600)
                    # 再补一次真实鼠标分步点击
                    pg.mouse.move(810, 494)
                    pg.wait_for_timeout(300)
                    pg.mouse.down()
                    pg.wait_for_timeout(120)
                    pg.mouse.up()
                    log("→ 分步鼠标点击 (810,494)")
                pg.wait_for_timeout(3500)

                ok2 = click_deep(pg, "完成")
                if not ok2:
                    ok2 = click_text_any(pg, ["完成"], exact=True)
                log("→ 点击「完成」:", ok2)
                pg.wait_for_timeout(3200)

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
            try:
                pg.close()
            except Exception:
                pass
            if not cdp_mode:
                ctx.close()
            return

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
        # CDP 模式只关自己开的标签页，绝不关用户整个浏览器
        try:
            pg.close()
        except Exception:
            pass
        if not cdp_mode:
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
