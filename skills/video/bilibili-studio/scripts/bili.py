#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bili.py — B 站创作闭环 CLI（投稿 / 复盘 / 台账）

用法速查：
  bili.py auth-check                      # 验证登录态
  bili.py auth-login                      # 扫码登录（调 biliup）
  bili.py auth-sync                       # 把 biliup 凭证同步成内部格式
  bili.py list [--status pubed]           # 稿件列表
  bili.py upload --video A.mp4 --title T  # 投稿（默认 dry-run，加 --yes 才真发）
  bili.py review [--size 10]              # 复盘数据包（JSON）
  bili.py report [--size 10]              # 复盘报告（Markdown，落到 data/reviews/）
  bili.py trend [--days 30]               # 近 30 天趋势
  bili.py ledger add|list                 # 投稿台账
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import bili_api as api  # noqa: E402

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HOME, "data")
BILIUP = os.path.join(HOME, "bin", "biliup")
BILIUP_COOKIE = os.path.join(DATA, "biliup-cookies.json")
LEDGER = os.path.join(DATA, "ledger.jsonl")
REVIEWS = os.path.join(DATA, "reviews")


def out(obj, pretty=True):
    print(json.dumps(obj, ensure_ascii=False, indent=2 if pretty else None))


def ensure_dirs():
    for d in (DATA, REVIEWS):
        os.makedirs(d, exist_ok=True)


def die(msg, code=1):
    out({"ok": False, "error": msg})
    sys.exit(code)


# ---------------------------------------------------------------- auth

def cmd_auth_check(_a):
    try:
        me = api.whoami()
    except api.BiliError as e:
        return out({
            "ok": False, "need_login": e.need_login,
            "code": e.code, "message": e.message,
            "hint": "凭证缺失或过期。运行 bili.py auth-login 扫码，或手动写入 data/cookies.json",
        })
    except Exception as e:
        return die(f"网络异常: {e}")
    out({"ok": True, "account": me})


def cmd_auth_login(_a):
    """调用 biliup 的扫码登录，登录后自动同步凭证"""
    if not os.path.exists(BILIUP):
        die(f"未找到 biliup 二进制: {BILIUP}")
    print("→ 正在拉起扫码登录，请用 B 站 App 扫描终端中出现的二维码…", file=sys.stderr)
    r = subprocess.run([BILIUP, "-u", BILIUP_COOKIE, "login"])
    if r.returncode != 0:
        die(f"biliup login 失败，退出码 {r.returncode}")
    sync_result = _sync_from_biliup()
    out(sync_result)


def _sync_from_biliup():
    if not os.path.exists(BILIUP_COOKIE):
        return {"ok": False, "error": "biliup 未生成 cookie 文件"}
    with open(BILIUP_COOKIE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    flat = {}
    for c in (raw.get("cookie_info", {}).get("cookies") or raw.get("cookies") or []):
        if isinstance(c, dict) and c.get("name"):
            flat[c["name"]] = c.get("value", "")
    if not flat:
        return {"ok": False, "error": "cookie 文件格式无法识别"}
    api.save_cookie(flat)
    return {"ok": True, "saved_to": api.COOKIE_FILE, "cookie_keys": sorted(flat.keys())}


def cmd_auth_sync(_a):
    out(_sync_from_biliup())


def cmd_auth_import(a):
    """从命令行传入的 cookie 串导入：--cookie 'SESSDATA=..; bili_jct=..'"""
    flat = {}
    for part in a.cookie.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            flat[k.strip()] = v.strip()
    if not flat.get("SESSDATA"):
        die("cookie 串中缺少 SESSDATA")
    api.save_cookie(flat)
    try:
        me = api.whoami()
    except api.BiliError as e:
        return out({"ok": False, "saved": True, "verify_failed": e.message})
    out({"ok": True, "saved_to": api.COOKIE_FILE, "account": me})


# ---------------------------------------------------------------- 稿件

def cmd_list(a):
    try:
        data = api.archive_list(status=a.status, pn=a.pn, ps=a.ps)
    except api.BiliError as e:
        if e.need_login:
            die("未登录或凭证过期，先跑 auth-login")
        die(f"[{e.code}] {e.message}")
    arcs = (data or {}).get("arcsinfo") or (data or {}).get("list") or []
    rows = []
    for it in arcs:
        rows.append({
            "bvid": it.get("bvid"),
            "aid": it.get("aid"),
            "title": it.get("title"),
            "state": it.get("state"),
            "state_desc": it.get("state_desc"),
            "pubtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(it["ptime"])) if it.get("ptime") else None,
            "duration": it.get("duration"),
            "play": it.get("stat", {}).get("view") if isinstance(it.get("stat"), dict) else None,
        })
    out({"ok": True, "count": len(rows), "page": (data or {}).get("page"), "items": rows})


# ---------------------------------------------------------------- 投稿

def cmd_upload(a):
    """
    投稿。默认 dry-run，只打印将要提交的内容；必须显式 --yes 才真正上传。
    这是对外发布动作，任何情况下都不静默执行。
    """
    video = os.path.abspath(os.path.expanduser(a.video))
    if not os.path.exists(video):
        die(f"视频文件不存在: {video}")

    size_mb = round(os.path.getsize(video) / 1048576, 1)
    title = a.title.strip()
    if len(title) > 80:
        die(f"标题超长（{len(title)} 字），B 站上限 80 字")

    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    if len(tags) > 10:
        die(f"标签最多 10 个，当前 {len(tags)} 个")

    plan = {
        "video": video,
        "size_mb": size_mb,
        "title": title,
        "title_len": len(title),
        "desc": a.desc or "",
        "tags": tags,
        "tid": a.tid,
        "cover": os.path.abspath(os.path.expanduser(a.cover)) if a.cover else None,
        "copyright": a.copyright,
        "source": a.source or "",
        "dtime": a.dtime or 0,
        "dynamic": a.dynamic or "",
    }

    if a.cover and not os.path.exists(plan["cover"]):
        die(f"封面文件不存在: {plan['cover']}")
    if plan["cover"]:
        cs = round(os.path.getsize(plan["cover"]) / 1048576, 2)
        plan["cover_mb"] = cs
        if cs > 5:
            die(f"封面 {cs}MB 超过 B 站 5MB 上限，先压缩")

    if not a.yes:
        plan["ok"] = None
        plan["mode"] = "dry-run"
        plan["hint"] = "确认无误后追加 --yes 才会真正上传并发布"
        return out(plan)

    if not os.path.exists(BILIUP):
        die(f"未找到 biliup: {BILIUP}")
    if not os.path.exists(BILIUP_COOKIE):
        die("缺少 biliup 凭证，先跑 bili.py auth-login")

    cmd = [BILIUP, "-u", BILIUP_COOKIE, "upload", video,
           "--submit", a.submit,
           "--tid", str(a.tid),
           "--title", title,
           "--copyright", str(a.copyright),
           "--tag", ",".join(tags)]
    if plan["desc"]:
        cmd += ["--desc", plan["desc"]]
    if plan["cover"]:
        cmd += ["--cover", plan["cover"]]
    if a.dtime:
        cmd += ["--dtime", str(a.dtime)]
    if plan["dynamic"]:
        cmd += ["--dynamic", plan["dynamic"]]
    if a.line:
        cmd += ["--line", a.line]
    if a.no_reprint:
        cmd += ["--no-reprint", "1"]

    print("→ 开始上传，进度输出直接透传…", file=sys.stderr)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        die(f"biliup 投稿失败，退出码 {r.returncode}（常见原因：凭证过期 / 分区 tid 错误 / 触发风控）")

    # 落台账，供后续复盘对齐
    _ledger_append({
        "bvid": None,
        "title": title,
        "desc": plan["desc"],
        "tags": tags,
        "tid": a.tid,
        "cover": plan["cover"],
        "duration": None,
        "dtime": a.dtime or 0,
        "submitted_at": int(time.time()),
        "hypothesis": a.hypothesis or "",
        "status": "submitted",
    })
    out({"ok": True, "message": "已提交，去创作中心确认审核状态", "plan": plan})


def cmd_ledger(a):
    ensure_dirs()
    if a.action == "add":
        rec = json.loads(a.json) if a.json else {}
        _ledger_append(rec)
        return out({"ok": True, "appended": rec})
    # list
    if not os.path.exists(LEDGER):
        return out({"ok": True, "count": 0, "items": []})
    items = []
    with open(LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    out({"ok": True, "count": len(items), "items": items[-a.limit:]})


def _ledger_append(rec):
    ensure_dirs()
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 复盘

def _collect_review(size):
    items = api.compare_recent(size=size)
    for it in items:
        it["diagnosis"] = api.diagnose(it)
    base = api.baseline(items)

    # 相对账号基线的表现（倍数），比绝对值更能判断"这条算不算好"
    for it in items:
        rel = {}
        for k, mk in (("play", "play_median"), ("like", "like_median"),
                      ("coin", "coin_median"), ("fav", "fav_median"),
                      ("comment", "comment_median")):
            m = base.get(mk) or 0
            v = it.get(k) or 0
            rel[k] = round(v / m, 2) if m else None
        it["vs_baseline"] = rel
    return {"ok": True, "generated_at": int(time.time()), "baseline": base, "items": items}


def cmd_review(a):
    try:
        pkg = _collect_review(a.size)
    except api.BiliError as e:
        if e.need_login:
            die("未登录或凭证过期，先跑 auth-login")
        die(f"[{e.code}] {e.message}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(pkg, f, ensure_ascii=False, indent=2)
    out(pkg)


def cmd_trend(a):
    try:
        play = api.trend(1)
    except api.BiliError as e:
        if e.need_login:
            die("未登录或凭证过期，先跑 auth-login")
        die(f"[{e.code}] {e.message}")
    out({"ok": True, "days": len(play), "play_daily": play})


def cmd_stat(_a):
    try:
        s = api.account_stat()
    except api.BiliError as e:
        die(f"[{e.code}] {e.message}")
    out({"ok": True, "stat": s})


def cmd_report(a):
    """把复盘数据渲染成可读 Markdown，落到 data/reviews/"""
    ensure_dirs()
    try:
        pkg = _collect_review(a.size)
    except api.BiliError as e:
        if e.need_login:
            die("未登录或凭证过期，先跑 auth-login")
        die(f"[{e.code}] {e.message}")

    b = pkg["baseline"]
    lines = []
    lines.append(f"# B 站复盘报告 · {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"样本：最近 {b.get('sample', 0)} 条稿件")
    lines.append("")
    lines.append("## 账号基线（中位数）")
    lines.append("")
    lines.append("| 指标 | 中位数 |")
    lines.append("|---|---|")
    lines.append(f"| 播放 | {b.get('play_median')} |")
    lines.append(f"| 点赞 | {b.get('like_median')} |")
    lines.append(f"| 投币 | {b.get('coin_median')} |")
    lines.append(f"| 收藏 | {b.get('fav_median')} |")
    lines.append(f"| 评论 | {b.get('comment_median')} |")
    lines.append(f"| 完播率 | {b.get('full_play_ratio_median')}% |")
    lines.append(f"| 互动率 | {b.get('interact_rate_median')}% |")
    lines.append(f"| 时长 | {b.get('duration_median')}s |")
    lines.append("")
    lines.append("## 单稿明细")
    lines.append("")
    lines.append("| 标题 | 播放 | vs基线 | 完播 | 3秒退出 | 互动 | 播转粉 | 时长 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for it in pkg["items"]:
        p = it.get("pct") or {}
        vb = (it.get("vs_baseline") or {}).get("play")
        title = (it.get("title") or "")[:24].replace("|", "｜")
        lines.append(
            f"| {title} | {it.get('play')} | {vb}x | "
            f"{p.get('full_play_ratio')}% | {p.get('crash_rate')}% | "
            f"{p.get('interact_rate')}% | {p.get('play_trans_fan_rate')}% | "
            f"{it.get('duration_str')} |"
        )
    lines.append("")
    lines.append("## 诊断信号")
    lines.append("")
    for it in pkg["items"]:
        sig = it.get("diagnosis") or []
        if not sig:
            continue
        lines.append(f"### {(it.get('title') or '')[:40]}（{it.get('bvid')}）")
        for s in sig:
            mark = {"good": "✅", "warn": "⚠️", "bad": "❌"}.get(s["level"], "·")
            lines.append(f"- {mark} **{s['finding']}** — 推断：{s['cause']}")
        lines.append("")

    md = "\n".join(lines)
    path = os.path.join(REVIEWS, f"{time.strftime('%Y-%m-%d_%H%M')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    # 同时存一份原始数据快照，用于纵向追踪同一条视频的增长曲线
    snap = os.path.join(REVIEWS, f"{time.strftime('%Y-%m-%d_%H%M')}.json")
    with open(snap, "w", encoding="utf-8") as f:
        json.dump(pkg, f, ensure_ascii=False, indent=2)
    out({"ok": True, "report": path, "snapshot": snap})


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="B 站创作闭环 CLI")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("auth-check").set_defaults(fn=cmd_auth_check)
    sub.add_parser("auth-login").set_defaults(fn=cmd_auth_login)
    sub.add_parser("auth-sync").set_defaults(fn=cmd_auth_sync)

    pi = sub.add_parser("auth-import")
    pi.add_argument("--cookie", required=True, help="原始 cookie 串，形如 'SESSDATA=..; bili_jct=..'")
    pi.set_defaults(fn=cmd_auth_import)

    pl = sub.add_parser("list")
    pl.add_argument("--status", default="is_pubing,pubed")
    pl.add_argument("--pn", type=int, default=1)
    pl.add_argument("--ps", type=int, default=20)
    pl.set_defaults(fn=cmd_list)

    pu = sub.add_parser("upload")
    pu.add_argument("--video", required=True)
    pu.add_argument("--title", required=True)
    pu.add_argument("--desc", default="")
    pu.add_argument("--tags", default="")
    pu.add_argument("--tid", type=int, default=201,
                    help="分区 id（默认 201 科学科普）。完整表见 references/tid.md，务必按内容选，别用默认值")
    pu.add_argument("--cover", default="")
    pu.add_argument("--copyright", type=int, default=1, choices=[1, 2])
    pu.add_argument("--source", default="")
    pu.add_argument("--dtime", type=int, default=0, help="定时发布，10 位时间戳，需 >4 小时后")
    pu.add_argument("--dynamic", default="")
    pu.add_argument("--line", default="")
    pu.add_argument("--no-reprint", action="store_true")
    pu.add_argument("--submit", default="client", choices=["client", "app", "web"])
    pu.add_argument("--hypothesis", default="", help="本次投稿的策略假设，写入台账用于后续验证")
    pu.add_argument("--yes", action="store_true", help="真正执行上传（不加则 dry-run）")
    pu.set_defaults(fn=cmd_upload)

    plg = sub.add_parser("ledger")
    plg.add_argument("action", choices=["add", "list"])
    plg.add_argument("--json", default="")
    plg.add_argument("--limit", type=int, default=20)
    plg.set_defaults(fn=cmd_ledger)

    pr = sub.add_parser("review")
    pr.add_argument("--size", type=int, default=10)
    pr.add_argument("--out", default="")
    pr.set_defaults(fn=cmd_review)

    prep = sub.add_parser("report")
    prep.add_argument("--size", type=int, default=10)
    prep.set_defaults(fn=cmd_report)

    pt = sub.add_parser("trend")
    pt.add_argument("--days", type=int, default=30)
    pt.set_defaults(fn=cmd_trend)

    sub.add_parser("stat").set_defaults(fn=cmd_stat)

    a = p.parse_args()
    if not getattr(a, "fn", None):
        p.print_help()
        return
    ensure_dirs()
    a.fn(a)


if __name__ == "__main__":
    main()
