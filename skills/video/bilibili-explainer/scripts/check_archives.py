#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_archives.py — 用现有 cookie 查创作中心稿件列表，确认投稿是否成功。"""
import json
import os

from playwright.sync_api import sync_playwright

EXE = ("$HOME/Library/Caches/ms-playwright/chromium-1234/"
       "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
# 2026-11-15：凭证移出技能目录（BILI_SECRET_DIR 可覆盖）
SECRETS = os.path.expanduser(os.environ.get("BILI_SECRET_DIR", "~/.workbuddy/secrets/bili"))
CK = os.path.join(SECRETS, "cookies.json")

ck = json.load(open(CK))
cookies = [{"name": k, "value": v, "domain": ".bilibili.com", "path": "/"} for k, v in ck.items()]

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, executable_path=EXE, args=["--no-sandbox"])
    ctx = b.new_context()
    ctx.add_cookies(cookies)
    r = ctx.request.get(
        "https://member.bilibili.com/x/web/archives?status=is_pubing,pubed,not_pubed&pn=1&ps=10",
        headers={"Referer": "https://member.bilibili.com/platform/upload-manager/article"},
    )
    print("HTTP", r.status)
    try:
        d = r.json()
        print("code:", d.get("code"), "message:", d.get("message"))
        arc = (d.get("data") or {}).get("arc_audits") or []
        print("稿件数:", len(arc))
        for a in arc:
            ar = a.get("Archive") or {}
            print(" -", ar.get("title"), "| bvid:", ar.get("bvid"),
                  "| state:", ar.get("state"), "| state_desc:", ar.get("state_desc"),
                  "| duration:", ar.get("duration"), "| 提交时间:", ar.get("ctime"))
    except Exception as e:
        print("解析失败:", str(e)[:200])
        print(r.text()[:500])
    b.close()
