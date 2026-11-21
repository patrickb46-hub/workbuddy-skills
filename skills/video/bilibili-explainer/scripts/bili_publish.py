#!/usr/bin/env python3
"""B 站网页投稿（cookies 模式，2026-11 版页面结构）。

比 web_upload.py 多的东西：
  · 分区：走 .select-controller → .drop-list-v2-item 的 .item-cont-main（旧脚本按文字点，点不中）
  · 封面：先开编辑器 → 选图 → 打开「双比例同步改动」→ 完成 → 确认同步
  · 每一步落一张截图，失败能看出卡在哪

用法：
  python3 bili_publish.py --video x.mp4 --title "..." --desc-file d.txt \
      --tags "a,b" --cover c.jpg --partition 人工智能 [--submit]
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

CK = os.path.expanduser(os.environ.get("BILI_SECRET_DIR", "~/.workbuddy/secrets/bili") + "/cookies.json")
EXE = ("$HOME/Library/Caches/ms-playwright/chromium-1234/chrome-mac-x64/"
       "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FRAME = "https://member.bilibili.com/platform/upload/video/frame"


def log(*a):
    print(*a, flush=True)


def shot(pg, name):
    try:
        pg.screenshot(path=f"qc-{name}.png", full_page=False)
        log(f"   · 截图 qc-{name}.png")
    except Exception:
        pass


def kill_masks(pg):
    n = pg.evaluate("""() => {
      let n = 0;
      document.querySelectorAll('.cover-editor, .mask, .el-dialog__wrapper, .bcc-mask').forEach(e => {
        if (e.className.includes('cover-editor') || e.className.includes('center-mask')) { e.remove(); n++; }
      });
      return n;
    }""")
    if n:
        log(f"→ 移除遮罩 {n}")


def pick_partition(pg, name):
    pg.locator(".select-controller").first.click()
    pg.wait_for_timeout(1200)
    items = pg.locator(".drop-list-v2-item")
    for i in range(items.count()):
        it = items.nth(i)
        try:
            t = (it.locator(".item-cont-main").first.inner_text() or "").strip()
        except Exception:
            continue
        if t == name:
            it.click()
            pg.wait_for_timeout(800)
            log(f"→ 分区：{name}")
            return True
    log(f"! 没找到分区 {name}")
    return False


def set_declaration(pg, text="内容无需标注"):
    """创作声明是必填项；控件是自绘的 .bcc-select，选项是 li.bcc-option。"""
    try:
        inp = pg.locator("input[placeholder*='创作声明']").first
        if not inp.count():
            log("! 没找到创作声明控件")
            return False
        if inp.input_value():
            log("→ 创作声明已有值：", inp.input_value())
            return True
        inp.click()
        pg.wait_for_timeout(1000)
        opts = pg.locator("li.bcc-option")
        for i in range(opts.count()):
            o = opts.nth(i)
            t = (o.inner_text() or "").strip()
            if text in t:
                o.click()
                pg.wait_for_timeout(900)
                log(f"→ 创作声明：{t}")
                return True
        log("! 创作声明没选中")
        return False
    except Exception as e:
        log("! 创作声明异常", str(e)[:70])
        return False


def upload_cover_file(pg, path):
    with pg.expect_file_chooser(timeout=15000) as fc:
        pg.get_by_text("上传封面", exact=False).first.click()
    fc.value.set_files(os.path.abspath(path))
    pg.wait_for_timeout(4500)
    log("   · 已选", os.path.basename(path))


def set_cover(pg, path43, path169):
    """B 站封面有两块画布：首页推荐 4:3 / 个人空间 16:9，两张都要给。"""
    pg.get_by_text("添加封面", exact=False).first.click()
    pg.wait_for_timeout(3800)
    ok = True
    try:
        upload_cover_file(pg, path43)          # 默认作用于 4:3
    except Exception as e:
        log("! 4:3 封面失败", str(e)[:70]); ok = False
    if path169:
        try:
            pg.locator(".editor_16_9").first.click(timeout=5000)
            pg.wait_for_timeout(1800)
            upload_cover_file(pg, path169)
        except Exception as e:
            log("! 16:9 封面失败", str(e)[:70]); ok = False
    # 完成 → 可能弹「未修改是否同步」，选不修改 / 确认
    for txt in ("完成",):
        try:
            pg.get_by_text(txt, exact=True).last.click(timeout=6000)
            pg.wait_for_timeout(2500)
            break
        except Exception:
            pass
    for txt in ("确认同步", "不同步，手动编辑", "确定"):
        try:
            btn = pg.get_by_text(txt, exact=True).first
            if btn.is_visible(timeout=1200):
                btn.click()
                pg.wait_for_timeout(1800)
                log(f"   · 弹窗点「{txt}」")
                break
        except Exception:
            continue
    pg.wait_for_timeout(1200)
    left = pg.get_by_text("添加封面", exact=False).count()
    log("→ 封面已设置" if left == 0 else "! 封面可能没生效")
    shot(pg, "cover")
    return ok and left == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--desc-file", default="")
    ap.add_argument("--desc", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--cover", default="")
    ap.add_argument("--cover43", default="")
    ap.add_argument("--partition", default="人工智能")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--wait-min", type=int, default=6)
    a = ap.parse_args()

    desc = a.desc or (open(a.desc_file, encoding="utf-8").read().strip() if a.desc_file else "")
    ck = json.load(open(CK))
    cookies = [{"name": k, "value": v, "domain": ".bilibili.com", "path": "/"} for k, v in ck.items()]

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, executable_path=EXE, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1440, "height": 960}, user_agent=UA,
                            locale="zh-CN", timezone_id="Asia/Shanghai")
        ctx.add_cookies(cookies)
        pg = ctx.new_page()
        pg.goto(FRAME, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(6000)

        pg.locator("input[type=file]").first.set_input_files(os.path.abspath(a.video))
        log("→ 上传中…")
        for _ in range(90):
            pg.wait_for_timeout(2000)
            if pg.locator("input[placeholder='请输入稿件标题']").count():
                break
        else:
            shot(pg, "no-editor")
            sys.exit("编辑页没出现")
        log("→ 编辑页就绪")
        kill_masks(pg)

        pg.locator("input[placeholder='请输入稿件标题']").fill(a.title)
        log("→ 标题 ok")

        if desc:
            pg.locator("div[contenteditable='true']").first.click()
            pg.keyboard.type(desc, delay=1)
            pg.wait_for_timeout(600)
            log("→ 简介 ok")

        if a.tags:
            box = pg.locator(".tag-input, input[placeholder*='标签']").first
            box.click()
            for _ in range(14):
                pg.keyboard.press("Backspace")
            pg.wait_for_timeout(600)
            for t in [x.strip() for x in a.tags.split(",") if x.strip()]:
                pg.keyboard.type(t, delay=30)
                pg.wait_for_timeout(650)
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(350)
            log("→ 标签 ok")

        pick_partition(pg, a.partition)
        set_declaration(pg)

        if a.cover:
            set_cover(pg, a.cover43 or a.cover, a.cover)

        shot(pg, "form")
        if not a.submit:
            log("（未提交）")
            ctx.close()
            return

        for _ in range(3):
            try:
                pg.get_by_text("立即投稿", exact=True).first.click(timeout=8000)
                log("→ 已点「立即投稿」")
                break
            except Exception:
                log("! 按钮被遮挡，滚到底再试")
                pg.mouse.wheel(0, 2000)
                pg.wait_for_timeout(2000)

        for i in range(a.wait_min * 12):
            pg.wait_for_timeout(5000)
            try:
                u = pg.url
                if "/archive-process" in u or "/upload-manager" in u:
                    log(f"SUCCESS @{i*5}s →", u)
                    shot(pg, "success")
                    break
                body = pg.inner_text("body")
                if "投稿成功" in body:
                    log(f"SUCCESS @{i*5}s（页面提示投稿成功）")
                    shot(pg, "success")
                    break
                if "验证" in body and i > 2:
                    log(f"⚠ 可能在等人机验证 @{i*5}s")
                    shot(pg, "verify")
                    break
            except Exception:
                log("窗口已关闭")
                break
        log("FINAL URL:", pg.url)
        ctx.close()


if __name__ == "__main__":
    main()
