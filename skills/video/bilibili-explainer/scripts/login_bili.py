#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""login_bili.py — 打开 B 站扫码登录页，等扫码成功，把 cookie 导出给 web_upload.py。

为什么用扫码而不是账号密码：
  1. 自动化浏览器里走账密登录极易触发滑块/短信风控，严重时会影响账号；
  2. 扫码是用户在自己手机上确认，脚本全程不接触密码；
  3. 登录态直接写进持久化 profile + cookies.json，后续投稿复用。

用法：
  python login_bili.py            # 弹出窗口 + 存二维码截图，等登录
  python login_bili.py --timeout 600
"""
import argparse
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

EXE = ("$HOME/Library/Caches/ms-playwright/chromium-1234/"
       "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
# 2026-11-15：登录态移出技能目录（BILI_SECRET_DIR 可覆盖）
_SECRETS = os.path.expanduser(
    os.environ.get("BILI_SECRET_DIR", "~/.workbuddy/secrets/bili"))
PROFILE = os.path.join(_SECRETS, "pw-profile")
COOKIES = os.path.join(_SECRETS, "cookies.json")
SHOT = "$HOME/Desktop/AI/Bilibili Videos/ai-geometry-figcheck/qr-login.png"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=600, help="等扫码的秒数")
    a = ap.parse_args()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            executable_path=EXE,
            headless=False,
            viewport={"width": 1280, "height": 860},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--no-sandbox", "--window-size=1280,900", "--window-position=60,40"],
        )
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 已有登录态就直接走
        pg.goto("https://www.bilibili.com/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(3000)
        names = {c["name"] for c in ctx.cookies()}
        if "SESSDATA" in names and "DedeUserID" in names:
            print("ALREADY-LOGGED-IN", flush=True)

        pg.goto("https://passport.bilibili.com/login", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(4000)
        try:
            pg.screenshot(path=SHOT)
            print("QR-SAVED", SHOT, flush=True)
        except Exception as e:
            print("QR-SHOT-FAIL", str(e)[:80], flush=True)

        deadline = time.time() + a.timeout
        while time.time() < deadline:
            pg.wait_for_timeout(2000)
            cks = ctx.cookies()
            nm = {c["name"] for c in cks}
            if "SESSDATA" in nm and "DedeUserID" in nm:
                flat = {c["name"]: c["value"] for c in cks
                        if c["domain"].endswith("bilibili.com")}
                Path(COOKIES).write_text(json.dumps(flat, ensure_ascii=False), encoding="utf-8")
                Path(COOKIES).chmod(0o600)
                uname = next((c["value"] for c in cks if c["name"] == "DedeUserID"), "?")
                print(f"LOGIN-OK uid={uname} cookies={len(flat)}", flush=True)
                pg.wait_for_timeout(1500)
                break
        else:
            print("LOGIN-TIMEOUT", flush=True)

        ctx.close()


if __name__ == "__main__":
    main()
