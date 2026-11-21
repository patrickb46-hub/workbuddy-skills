#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auth_from_chrome.py — 从 Chrome 的 Cookies 库直接提取 B 站登录态，验证后写入 secrets。

场景：浏览器里 B 站还是登录状态，但导出到 secrets/bili/cookies.json 的快照失效了
（Chrome 会不定时轮换 SESSDATA，静态副本不会自动跟着更新）。

用法：
  python3 auth_from_chrome.py            # 解密 → 用 nav 接口验证 → 写回 cookies.json
  python3 auth_from_chrome.py --dry-run  # 只验证，不写文件

依赖：macOS 的 `security`（读 Keychain 里的 Chrome Safe Storage）和 `openssl`。
首次运行可能弹 Keychain 授权框，选「允许」即可；之后不再弹。
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import datetime

SECRETS = os.path.expanduser(
    os.environ.get("BILI_SECRET_DIR", "~/.workbuddy/secrets/bili"))
TARGET = os.path.join(SECRETS, "cookies.json")

CHROME_DIR = os.path.expanduser("~/Library/Application Support/Google/Chrome")
PROFILE_HINTS = ("Default", "Profile 1", "Profile 2", "Profile 3")
WANT = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "buvid3", "buvid4", "buvid_fp")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def find_cookie_db():
    """挑最近活跃、且含 bilibili cookie 的 profile"""
    best = None
    for name in PROFILE_HINTS + tuple(
            d for d in (os.listdir(CHROME_DIR) if os.path.isdir(CHROME_DIR) else [])
            if d.startswith("Profile ")):
        db = os.path.join(CHROME_DIR, name, "Cookies")
        if not os.path.exists(db):
            continue
        try:
            tmp = os.path.join(tempfile.mkdtemp(prefix="bili_ck_"), "Cookies")
            shutil.copy2(db, tmp)
            wal = db + "-wal"
            if os.path.exists(wal):
                shutil.copy2(wal, tmp + "-wal")
            con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
            n = con.execute(
                "select count(*) from cookies where host_key like ? and name='SESSDATA'",
                ("%bilibili.com",)).fetchone()[0]
            con.close()
            if n:
                mtime = os.path.getmtime(db)
                if best is None or mtime > best[0]:
                    best = (mtime, tmp)
        except Exception:
            continue
    return best[1] if best else None


def chrome_key():
    r = subprocess.run(["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return hashlib.pbkdf2_hmac("sha1", r.stdout.strip().encode(), b"saltysalt", 1003, 16).hex()


def aes_decrypt(hexkey, data):
    p = subprocess.run(
        ["openssl", "enc", "-d", "-aes-128-cbc", "-K", hexkey, "-iv", "20" * 16, "-nopad"],
        input=data, capture_output=True)
    return p.stdout if p.returncode == 0 else b""


def strip_prefix(raw, host):
    pad = raw[-1]
    if 1 <= pad <= 16 and raw[-pad:] == bytes([pad]) * pad:
        raw = raw[:-pad]
    if raw[:32] == hashlib.sha256(host.encode()).digest():
        raw = raw[32:]
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    db = find_cookie_db()
    if not db:
        print(json.dumps({"ok": False, "error": "没找到含 B 站 cookie 的 Chrome profile"}))
        return 1

    key = chrome_key()
    if not key:
        print(json.dumps({"ok": False, "error": "读不到 Keychain 里的 Chrome Safe Storage"}))
        return 1

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    sql = ("select host_key,name,encrypted_value from cookies "
           "where host_key like ? and name in (" + ",".join("?" * len(WANT)) + ")")
    rows = con.execute(sql, ("%bilibili.com", *WANT)).fetchall()
    con.close()

    got = {}
    for host, name, enc in rows:
        if not enc or enc[:3] != b"v10":
            continue
        raw = strip_prefix(aes_decrypt(key, enc[3:]), host)
        try:
            val = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if val:
            got[name] = val

    if not got.get("SESSDATA"):
        print(json.dumps({"ok": False, "error": "解出来没有 SESSDATA，Chrome 里可能确实没登录"}))
        return 1

    req = urllib.request.Request(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"Cookie": "; ".join(f"{k}={v}" for k, v in got.items()),
                 "User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    try:
        nav = json.load(urllib.request.urlopen(req, timeout=15))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"nav 接口异常: {e}"}))
        return 1
    d = nav.get("data") or {}
    if not d.get("isLogin"):
        print(json.dumps({"ok": False, "error": "nav 验证未登录",
                          "code": nav.get("code")}, ensure_ascii=False))
        return 1

    result = {"ok": True, "account": d.get("uname"), "mid": d.get("mid"),
              "fields": sorted(got), "dry_run": a.dry_run}
    if a.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    merged = {}
    if os.path.exists(TARGET):
        try:
            old = json.load(open(TARGET, encoding="utf-8"))
            if isinstance(old, dict):
                merged = old
            elif isinstance(old, list):
                merged = {c["name"]: c.get("value", "") for c in old if c.get("name")}
        except Exception:
            pass
    merged.update(got)

    os.makedirs(SECRETS, exist_ok=True)
    bak = os.path.join(SECRETS, "_备份")
    os.makedirs(bak, exist_ok=True)
    if os.path.exists(TARGET):
        shutil.copy2(TARGET, os.path.join(
            bak, "cookies.json." + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))

    with open(TARGET, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    os.chmod(TARGET, 0o600)
    result["written"] = TARGET
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
