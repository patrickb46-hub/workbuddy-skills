#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diskaudit.py — macOS 磁盘体检（只读）

扫描磁盘构成，按「直接删除 / 备份后删 / 需要你判断 / 别动」四类给出建议。
本工具绝不删除任何文件，只输出报告与可复制的命令。

用法:
    python3 diskaudit.py                 # 标准体检
    python3 diskaudit.py --deep          # 追加全盘大文件扫描（慢）
    python3 diskaudit.py --top 40        # 调整大文件条数
    python3 diskaudit.py --json out.json # 另存 JSON
    python3 diskaudit.py --html out.html # 另存 HTML 报告
    python3 diskaudit.py --no-color      # 关闭颜色

设计要点（血泪教训，别改）:
1. macOS 的 code_sign_clone 等目录是 APFS 克隆，du 报的是逻辑大小，
   真实占用接近 0。绝不能把它当"可释放空间"汇报。
2. 本机 rm 可能被包装成"移到废纸篓"，空间不会释放，提示里必须用 /bin/rm。
3. .DocumentRevisions-V100 / .Spotlight-V100 受 TCC 保护，非 root 读不到，
   必须显式标注"需授权"而不是静默跳过。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
DATA = "/System/Volumes/Data"

# ---------------------------------------------------------------- 颜色

class C:
    on = True
    R = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
    RED = "\033[31m"; GRN = "\033[32m"; YEL = "\033[33m"
    BLU = "\033[34m"; MAG = "\033[35m"; CYN = "\033[36m"; GRY = "\033[90m"

    @classmethod
    def disable(cls):
        cls.on = False
        for k in ("R", "B", "DIM", "RED", "GRN", "YEL", "BLU", "MAG", "CYN", "GRY"):
            setattr(cls, k, "")

def c(txt: str, *styles: str) -> str:
    return "".join(styles) + str(txt) + (C.R if C.on else "")

def human(n: float) -> str:
    """字节 → 人类可读"""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return ("%.0f %s" % (n, unit)) if unit in ("B", "KB") else ("%.2f %s" % (n, unit))
        n /= 1024.0
    return "%.2f TB" % n

# ---------------------------------------------------------------- 系统探测

def run(cmd, timeout=600):
    try:
        p = subprocess.run(cmd, shell=False, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)

def df_info():
    rc, out, _ = run(["df", "-k", DATA])
    if rc != 0:
        return None
    parts = out.strip().splitlines()[-1].split()
    total, used, avail = int(parts[1]) * 1024, int(parts[2]) * 1024, int(parts[3]) * 1024
    return {"total": total, "used": used, "avail": avail,
            "pct": round(used * 100.0 / max(total, 1))}

def apfs_consumed():
    rc, out, _ = run(["diskutil", "apfs", "list"])
    if rc != 0:
        return None
    m = re.search(r"Name:\s+Macintosh HD - Data.*?Capacity Consumed:\s+(\d+)\s*B", out, re.S)
    return int(m.group(1)) if m else None

def du_kb(path, timeout=600):
    """返回 (KB, 是否成功)。du 在权限不足时返回非 0。"""
    if not os.path.exists(path) and not os.path.islink(path):
        return 0, False
    rc, out, _ = run(["du", "-sxk", path], timeout=timeout)
    if rc != 0 and not out.strip():
        return 0, False
    try:
        return int(out.split()[0]), True
    except Exception:  # noqa: BLE001
        return 0, False

# ---------------------------------------------------------------- 规则引擎

GARBAGE, CACHE, REDOWNLOAD, CONFIRM, BACKUP, KEEP = (
    "garbage", "cache", "redownload", "confirm", "backup", "keep")

CAT_LABEL = {
    GARBAGE:    "垃圾残留",
    CACHE:      "可重建缓存",
    REDOWNLOAD: "可重新下载",
    CONFIRM:    "需要你判断",
    BACKUP:     "先备份再删",
    KEEP:       "别动",
}

# (正则, 类别, 理由, 是否克隆嫌疑)
RULES = [
    (r"/com\.[\w.]*(Chrome|doubao|quark|qqbrowser)[\w.]*\.code_sign_clone/?$",
     GARBAGE, "APFS 克隆，与浏览器本体共享数据块，删了几乎不释放空间（但清掉更干净）", True),
    (r"code_sign_clone", GARBAGE, "APFS 克隆残留，真实占用≈0", True),
    (r"/\.Trash$", GARBAGE, "废纸篓，清空即释放", False),
    (r"/\.ollama$", REDOWNLOAD, "本地模型库，可 ollama pull 重拉", False),
    (r"/\.ollama/models/", REDOWNLOAD, "ollama 模型分片，可 ollama pull 重拉", False),
    (r"/\.workbuddy$", CONFIRM, "AI 工具运行环境（Node/Python 运行时、日志、会话），清前确认", False),
    (r"/Library/Application Support$", CONFIRM, "各 App 的数据目录，含聊天记录/配置，需逐项看", False),
    (r"/Library/Containers$", CONFIRM, "沙盒 App 的本地数据，删了会丢该 App 的记录", False),
    (r"/Library/Mobile Documents$", CONFIRM, "iCloud 云盘的本地副本，删本地会连带删云端", False),
    (r"/Library/(Metadata|Developer)$", CACHE, "系统元数据/开发缓存，可重建", False),
    (r"/Library/pnpm$", CACHE, "pnpm 包缓存，删后按需重下", False),
    (r"/Virtual Machines\.localized$", CONFIRM, "虚拟机目录，先确认还需不需要", False),
    (r"/(\.cache|\.npm/_cacache|Library/pnpm/store|Library/Caches/pip)$", CACHE, "包管理器缓存，删后按需重下", False),
    (r"/Library/Caches$", CACHE, "App 缓存，删后自动重建", False),
    (r"/Library/Developer/Xcode/(DerivedData|iOS DeviceSupport|Archives)$", CACHE, "Xcode 编译产物，可重建（Archives 含历史包，删前确认）", False),
    (r"/\.ollama/models$", REDOWNLOAD, "ollama 模型，可 ollama pull 重拉", False),
    (r"/(huggingface|\.cache/huggingface)$", REDOWNLOAD, "HF 模型缓存，可重下", False),
    (r"(node_modules|__pycache__|\.venv|/target|/build|/dist)$", CACHE, "构建产物，可重装/重编译", False),
    (r"/Library/Application Support/MobileSync/Backup$", CONFIRM, "iPhone/iPad 本地备份，删了手机数据就没底了", False),
    (r"\.(vmwarevm|vmdk|vmem|qcow2|utm|pvm|vbox)$", CONFIRM, "虚拟机或虚拟磁盘，先确认还需不需要", False),
    (r"\.(iso|img|toast)$", CONFIRM, "安装介质，装完就没用了", False),
    (r"\.(dmg|pkg)$", CONFIRM, "安装包，装完可删", False),
    (r"\.(7z|zip|rar|tar|gz)(\.\d{3})?$", CONFIRM, "压缩包，解压后可删", False),
    (r"\.(mp4|mov|mkv|avi|m4v|mts)$", BACKUP, "视频原始素材，不可再生，先拷硬盘", False),
    (r"\.(safetensors|gguf|bin|pt|pth|onnx)$", CONFIRM, "模型权重，重新训练/下载代价高", False),
    (r"\.(sparsebundle|sparseimage)$", CONFIRM, "加密/稀疏磁盘映像，整个是一个容器文件", False),
    (r"^/Applications/[^/]+\.app$", REDOWNLOAD, "应用程序，可从官网/商店重装", False),
    (r"^/Users/[^/]+/Desktop$", BACKUP, "桌面：通常是个人文件集中地，逐项确认", False),
    (r"^/Users/[^/]+/Documents$", BACKUP, "文稿：个人文件，先备份再动", False),
    (r"^/Users/[^/]+/Pictures$", BACKUP, "照片图库，不可再生", False),
    (r"^/Users/[^/]+/Downloads$", CONFIRM, "下载目录，多半是装完没删的安装包", False),
    (r"^/Users/[^/]+/Movies$", BACKUP, "影片，多半是素材", False),
    (r"^/(System|usr|bin|sbin|Library|private/var/db|private/var/vm)", KEEP, "系统组件，别手动删", False),
    (r"^/private/var/folders", GARBAGE, "系统临时目录，重启/App 退出后可清", False),
]

GAME_PAT = (r"war\s*thunder|art\s*of\s*rally|ballistic|僵尸|steam|epic\s*games|"
            r"minecraft|ysflight|horizon|racing")
KEEP_APP_PAT = (r"microsoft|pages|keynote|numbers|wps|adobe|dingtalk|wechat|weixin|"
                r"workbuddy|trae|chrome|firefox|quark|doubao|classin|onedrive|icloud|"
                r"baidunetdisk|netease|bilibili|ima\.|listen1|garageband|imovie|"
                r"final\s*cut|xcode|ollama\.app|tilia|qqbrowser|wechatwebdevtools|"
                r"utilities|safari")

def classify_app(path, size):
    """应用单独判断：游戏可卸、生产力工具别动、大的其他应用让人自己看。"""
    name = os.path.basename(path)
    if re.search(GAME_PAT, name, re.I):
        return REDOWNLOAD, "游戏，不玩可卸载，需要时重下"
    if re.search(KEEP_APP_PAT, name, re.I):
        return KEEP, "日常在用的工具/办公软件，不建议删"
    if size >= 2 * 1024 ** 3:
        return CONFIRM, "较大应用，看你是否还在用"
    return KEEP, "占用不大，留着"

def classify(path, is_clone_suspect=None):
    p = path.rstrip("/") or "/"
    for pat, cat, why, clone in RULES:
        if re.search(pat, p, re.I):
            return cat, why, clone
    return CONFIRM, "未归类，需人工判断", False

# ---------------------------------------------------------------- 扫描目标

def candidate_paths():
    """分两组返回：
    roots   —— 互不重叠的顶层，用于算总量与顶层构成
    details —— 互斥的明细桶（不含父目录），用于给建议、避免重复计数
    """
    roots, details = [], []
    rc, us, _ = run(["ls", "-1", "/Users"])
    users = [u for u in (us.split() if rc == 0 else []) if u != "Shared"]

    for p in ["/Applications", "/Library", "/usr", "/opt", "/private/var"] + \
             [os.path.join("/Users", u) for u in users]:
        roots.append({"path": p, "is_root": True})

    # ---- 当前用户明细（互斥，不含 ~/Library 父级）----
    for d in ("Desktop", "Documents", "Downloads", "Movies", "Pictures",
              ".Trash", ".ollama", ".cache", ".npm", ".workbuddy", "My Games"):
        details.append(os.path.join(HOME, d))
    for d in ("Caches", "Containers", "Application Support", "Developer",
              "pnpm", "Mail", "Messages", "Mobile Documents", "Metadata"):
        details.append(os.path.join(HOME, "Library", d))
    details.append("/private/var/folders")

    rc, tmpdir, _ = run(["getconf", "DARWIN_USER_TEMP_DIR"])
    if rc == 0:
        try:
            import glob
            details += [os.path.normpath(p) for p in
                        glob.glob(tmpdir.strip().rstrip("/") + "/../X/*code_sign_clone*")]
        except Exception:  # noqa: BLE001
            pass

    # ---- 其他用户明细 ----
    for u in users:
        base = os.path.join("/Users", u)
        if base == HOME:
            continue
        for d in ("Desktop", "Documents", "Downloads", "Movies", "Pictures",
                  "Virtual Machines.localized"):
            details.append(os.path.join(base, d))

    seen, out = set(), []
    for p in details:
        if p in seen:
            continue
        seen.add(p)
        if os.path.exists(p):
            out.append({"path": p, "is_root": False})
    return roots, out

def app_children():
    """/Applications 下逐个 app（明细用，不参与总量）。"""
    res = []
    try:
        for name in sorted(os.listdir("/Applications")):
            if name.endswith(".app"):
                res.append({"path": os.path.join("/Applications", name), "is_root": False})
    except Exception:  # noqa: BLE001
        pass
    return res

def scan_targets(entries, min_bytes):
    items = []
    for e in entries:
        p, is_root = e["path"], e["is_root"]
        kb, ok = du_kb(p)
        if not ok:
            items.append({"path": p, "bytes": 0, "status": "denied", "is_root": is_root})
            continue
        b = kb * 1024
        if b < min_bytes and not is_root:
            continue
        if p.startswith("/Applications/") and p.endswith(".app"):
            cat, why = classify_app(p, b)
            clone = False
        else:
            cat, why, clone = classify(p)
        items.append({"path": p, "bytes": b, "status": "ok", "is_root": is_root,
                      "category": cat, "reason": why, "clone": clone})
    return items

# ---------------------------------------------------------------- 深扫大文件

DEEP_ROOTS = ["/Users", "/Applications", "/Library", "/private/var"]

def deep_files(top_n=30, min_gb=0.5, timeout=None):
    """大文件扫描。只扫 /Users、/Applications、/Library、/private/var ——
    系统目录里的大文件既删不得，扫它们纯属浪费时间。

    用 Python 自己遍历而不用 find/du 子进程：单进程、无 fork 开销，
    在 macOS 上比 `find -exec du {} +` 快，也不会受 ARG_MAX 影响。
    大小取 st_blocks*512（真实落盘量），比 st_size 更接近 df 口径。"""
    thresh = int(min_gb * 1024 ** 3)
    found = []

    def _walk(root):
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            # 跳过明显无关的目录，省时间
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") or d in (".ollama", ".workbuddy", ".Trash")]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    st = os.lstat(fp)
                except OSError:
                    continue
                if st.st_size < thresh:
                    continue
                alloc = getattr(st, "st_blocks", 0) * 512
                found.append((alloc or st.st_size, fp))

    for root in DEEP_ROOTS:
        if os.path.isdir(root):
            _walk(root)

    found.sort(key=lambda x: -x[0])
    res = []
    for b, p in found[:top_n]:
        cat, why, _clone = classify(p)
        res.append({"path": p, "bytes": b, "category": cat, "reason": why})
    return res

# ---------------------------------------------------------------- 环境检查

def env_checks():
    info = {}
    rc, out, _ = run(["tmutil", "destinationinfo"])
    info["tm"] = "未配置（等于零备份）" if "No destinations" in out or rc != 0 else out.strip()[:200]

    rc, out, _ = run(["tmutil", "listlocalsnapshots", "/"])
    snaps = [l for l in out.splitlines() if "com.apple.TimeMachine" in l]
    info["snapshots"] = len(snaps)

    trash = os.path.join(HOME, ".Trash")
    kb, ok = du_kb(trash)
    info["trash"] = kb * 1024 if ok else 0

    rc, out, _ = run(["which", "rm"])
    info["rm_shim"] = "brokered-bin" in out or "shim" in out
    info["rm_path"] = out.strip()

    rc, out, _ = run(["csrutil", "status"])
    info["sip"] = "enabled" in out.lower() or "启用" in out

    return info

# ---------------------------------------------------------------- 渲染

ACTION_HINT = {
    GARBAGE:    "直接删",
    CACHE:      "直接删（会自动重建）",
    REDOWNLOAD: "直接删（需要时重下）",
    CONFIRM:    "先看内容再决定",
    BACKUP:     "先拷移动硬盘，核对后删本地",
    KEEP:       "不要删",
}

_SEC_N = [0]

def section(title, subtitle=""):
    _SEC_N[0] += 1
    t = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", title)
    print()
    print(c("─" * 72, C.GRY))
    print(c(" %d. %s" % (_SEC_N[0], t), C.B, C.CYN))
    if subtitle:
        print(c(" " + subtitle, C.GRY))
    print(c("─" * 72, C.GRY))

def print_table(items, show_cmd=False, rm_shim=False):
    if not items:
        print(c("   （没有匹配项）", C.GRY))
        return
    width = max((len(i["path"]) for i in items), default=10)
    width = min(width, 62)
    for it in items:
        size = human(it["bytes"])
        cat = it["category"]
        color = {GARBAGE: C.GRY, CACHE: C.GRY, REDOWNLOAD: C.YEL,
                 CONFIRM: C.MAG, BACKUP: C.BLU, KEEP: C.GRN}.get(cat, C.R)
        name = it["path"]
        if len(name) > 62:
            name = "…" + name[-(61):]
        note = ""
        if it.get("clone"):
            note = c("  [克隆·实际≈0]", C.GRY)
        print("  %-9s %s%s" % (c(size, C.B, color), name, note))
        if it.get("reason"):
            print("            %s" % c(it["reason"], C.DIM))

def build_groups(items):
    g = {GARBAGE: [], CACHE: [], REDOWNLOAD: [], CONFIRM: [], BACKUP: [], KEEP: []}
    for it in items:
        if "category" not in it:
            continue
        g.setdefault(it["category"], []).append(it)
    for k in g:
        g[k].sort(key=lambda x: -x["bytes"])
    return g

def render_report(root_items, detail_items, df, consumed, env, deep=None, rm_shim=False):
    total_dup = sum(i["bytes"] for i in root_items if i["status"] == "ok")
    denied = [i for i in root_items + detail_items if i["status"] == "denied"]

    print()
    print(c("  磁盘体检报告", C.B))
    print(c("  %s · %s" % (datetime.now().strftime("%Y-%m-%d %H:%M"), os.uname().nodename), C.GRY))
    print(c("  本工具只读，不删除任何文件。", C.GRY))

    # 概览
    section("① 概览")
    if df:
        bar_w = 40
        filled = int(bar_w * df["used"] / max(df["total"], 1))
        bar = c("█" * filled, C.RED) + c("░" * (bar_w - filled), C.GRY)
        print("  容量 %s   已用 %s   可用 %s" % (
            c(human(df["total"]), C.B), c(human(df["used"]), C.B, C.RED),
            c(human(df["avail"]), C.B, C.GRN)))
        print("  [%s] %d%%" % (bar, df["pct"]))
    print()
    if consumed:
        print("  APFS 数据卷实际消耗  %s" % c(human(consumed), C.B))
        print("  可枚举文件合计        %s" % c(human(total_dup), C.B))
        gap = consumed - total_dup
        if gap > 3 * 1024 ** 3:
            print("  差额（系统保护区）    %s" % c(human(gap), C.B, C.YEL))
            print(c("        这是 TCC 保护的目录，普通权限读不到；", C.GRY))
            print(c("        要看全就 sudo 重跑：sudo python3 diskaudit.py", C.GRY))
    print()
    print(c("  提醒：du 对 APFS 克隆会重复计算逻辑大小，标 [克隆] 的项目真实占用≈0。", C.GRY))
    if denied:
        print(c("        有 %d 个目录无权限读取（多半是其他用户的 Library）。" % len(denied), C.GRY))

    detail_ok = [i for i in detail_items if i["status"] == "ok"]
    g = build_groups(detail_ok)

    # 一、直接删
    section("② 直接删除", "缓存、残留、可重新下载的——删了不心疼")
    direct = sorted(g[GARBAGE] + g[CACHE] + g[REDOWNLOAD], key=lambda x: -x["bytes"])
    print_table(direct)
    real = sum(i["bytes"] for i in direct if not i.get("clone"))
    print()
    print("  本项可释放约 %s%s" % (
        c(human(real), C.B, C.GRN),
        c("（已排除克隆虚数）" if any(i.get("clone") for i in direct) else "", C.GRY)))

    # 二、备份后删
    section("③ 先备份到移动硬盘，再删本地", "不可再生，删了就没了")
    back = g[BACKUP]
    print_table(back)
    if back:
        print()
        print("  合计 %s" % c(human(sum(i["bytes"] for i in back)), C.B, C.BLU))
        print(c("  拷完核对文件数一致，再回删本地。", C.YEL))

    # 三、需确认
    section("④ 需要你自己判断", "体积大，但值不值得只有你知道")
    conf = g[CONFIRM]
    print_table(conf)
    if conf:
        print()
        print("  合计 %s" % c(human(sum(i["bytes"] for i in conf)), C.B, C.MAG))

    # 四、别动
    section("⑤ 不要动", "系统组件与日常工具")
    keep = g[KEEP]
    keep_apps = [i for i in keep if i["path"].startswith("/Applications/")]
    keep_other = [i for i in keep if not i["path"].startswith("/Applications/")]
    if keep_other:
        print_table(keep_other[:10])
    if keep_apps:
        print("  日常应用 %d 个，共 %s —— 都在用，不建议删" % (
            len(keep_apps), c(human(sum(i["bytes"] for i in keep_apps)), C.B)))
    sys_tot = sum(i["bytes"] for i in root_items
                  if i["status"] == "ok" and i["path"] in ("/Library", "/usr", "/opt"))
    if sys_tot:
        print("  系统组件 /Library + /usr + /opt 共 %s —— 别手动删" % c(human(sys_tot), C.B))

    # 顶层构成
    section("⑥ 顶层构成", "整台机器的钱都花在哪了")
    rs = sorted([i for i in root_items if i["status"] == "ok"], key=lambda x: -x["bytes"])
    for i in rs:
        if i["bytes"] < 100 * 1024 ** 2:
            continue
        share = 100.0 * i["bytes"] / max(total_dup, 1)
        bw = int(28 * share / 100)
        print("  %-9s %s %s" % (c(human(i["bytes"]), C.B),
                                c("▇" * bw, C.CYN), i["path"]))
    if consumed and total_dup < consumed:
        print("  %-9s %s %s" % (c(human(consumed - total_dup), C.B, C.YEL),
                                c("▇" * 6, C.YEL), "系统保护区（读不到）"))

    # 深扫
    if deep:
        section("⑦ 全盘最大文件", "按真实落盘量排序")
        for i in deep[:25]:
            cat = i["category"]
            color = {GARBAGE: C.GRY, CACHE: C.GRY, REDOWNLOAD: C.YEL,
                     CONFIRM: C.MAG, BACKUP: C.BLU, KEEP: C.GRN}.get(cat, C.R)
            print("  %-9s %-9s %s" % (c(human(i["bytes"]), C.B, color),
                                      c(CAT_LABEL.get(cat, "?"), color), i["path"]))

    # 环境
    section("⑧ 环境体检")
    tm_ok = "未配置" not in env["tm"]
    print("  Time Machine   %s" % c(env["tm"], C.GRN if tm_ok else C.RED))
    if not tm_ok:
        print(c("                 → 没有任何备份，删东西前先接硬盘配好", C.YEL))
    print("  本地快照       %d 个%s" % (
        env["snapshots"], c("（占用空间）" if env["snapshots"] else "（正常）", C.GRY)))
    print("  废纸篓         %s" % c(human(env["trash"]),
                                  C.YEL if env["trash"] > 1024 ** 3 else C.GRY))
    print("  SIP 完整性保护 %s" % c("已启用" if env["sip"] else "已关闭",
                                  C.GRN if env["sip"] else C.YEL))
    if rm_shim:
        print()
        print(c("  ⚠ 本机 rm 被包装成「移到废纸篓」，不会释放空间：%s" % env["rm_path"], C.YEL))

    # 提示
    section("⑨ 怎么动手")
    rmcmd = "/bin/rm" if rm_shim else "rm"
    print("  %s 删除（确认路径无误再执行）：" % c("①", C.B))
    print(c('     %s -rf "<路径>"' % rmcmd, C.CYN))
    print()
    print("  %s 先拷到移动硬盘：" % c("②", C.B))
    print(c('     rsync -av --progress "<路径>" /Volumes/<硬盘名>/', C.CYN))
    print()
    print("  %s 核对文件数（两边应一致）：" % c("③", C.B))
    print(c('     find "<路径>" -type f | wc -l', C.CYN))
    print(c('     find "/Volumes/<硬盘名>/<目录名>" -type f | wc -l', C.CYN))
    print()
    print(c("  顺序：先配 Time Machine → 再备份不可再生数据 → 最后删可重建的。", C.B))
    print()

def render_json(path, items, df, consumed, env, deep):
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "host": os.uname().nodename,
        "disk": df,
        "apfs_consumed": consumed,
        "env": env,
        "items": items,
        "largest_files": deep or [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def render_html(path, items, df, consumed, env, deep):
    g = build_groups(items)
    def rows(lst):
        out = []
        for i in lst:
            out.append("<tr><td class=s>%s</td><td class=p>%s</td><td>%s</td></tr>" % (
                human(i["bytes"]), html.escape(i["path"]), html.escape(i.get("reason", ""))))
        return "\n".join(out) or "<tr><td colspan=3 class=empty>无</td></tr>"

    def block(title, lst, color, limit=None):
        tot = sum(i["bytes"] for i in lst if not i.get("clone"))
        shown = lst[:limit] if limit else lst
        return """
<h2><span class=dot style="background:%s"></span>%s <span class=sum>%s</span></h2>
<table><thead><tr><th style="width:90px">大小</th><th>路径</th><th style="width:40%%">说明</th></tr></thead>
<tbody>%s</tbody></table>""" % (color, title, human(tot), rows(shown))

    body = ""
    body += block("直接删除", sorted(g[GARBAGE] + g[CACHE] + g[REDOWNLOAD], key=lambda x: -x["bytes"]), "#6b7280")
    body += block("先备份到移动硬盘，再删本地", g[BACKUP], "#2b5cff")
    body += block("需要你自己判断", g[CONFIRM], "#b7791f")
    body += block("不要动", g[KEEP], "#1f7a4d", limit=15)

    pct = df["pct"] if df else 0
    doc = """<!DOCTYPE html><html lang=zh-CN><head><meta charset=utf-8>
<title>磁盘体检报告</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f6f7f9;
color:#1c1f23;margin:0;padding:40px 24px;line-height:1.6}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px}h2{font-size:16px;margin:36px 0 8px;display:flex;align-items:center;gap:8px}
.meta{color:#6b7280;font-size:13px}
.dot{width:8px;height:8px;border-radius:50%%;display:inline-block}
.sum{font-weight:400;color:#6b7280;font-size:13px}
table{width:100%%;border-collapse:collapse;background:#fff;border:1px solid #e4e7ec;
border-radius:8px;overflow:hidden;font-size:13.5px}
th{text-align:left;padding:9px 12px;background:#f1f3f6;font-size:12px;color:#4b5563}
td{padding:9px 12px;border-top:1px solid #e4e7ec;vertical-align:top}
td.s{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
td.p{font-family:ui-monospace,Menlo,monospace;font-size:12px;word-break:break-all}
td.empty{color:#9ca3af}
.bar{height:8px;background:#e4e7ec;border-radius:4px;overflow:hidden;margin:10px 0 4px}
.bar>i{display:block;height:100%%;background:#c0392b;width:%d%%}
</style></head><body><div class=wrap>
<h1>磁盘体检报告</h1>
<div class=meta>%s · %s · 只读扫描，未删除任何文件</div>
<div class=bar><i></i></div>
<div class=meta>已用 %s / %s（%d%%），可用 %s</div>
%s
</div></body></html>""" % (
        pct, datetime.now().strftime("%Y-%m-%d %H:%M"), os.uname().nodename,
        human(df["used"]) if df else "?", human(df["total"]) if df else "?",
        pct, human(df["avail"]) if df else "?", body)

    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)

# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="macOS 磁盘体检（只读）")
    ap.add_argument("--deep", action="store_true", help="追加全盘大文件扫描（较慢）")
    ap.add_argument("--top", type=int, default=30, help="深扫显示条数，默认 30")
    ap.add_argument("--min-gb", type=float, default=0.5, help="深扫最小文件，默认 0.5GB")
    ap.add_argument("--json", metavar="FILE", help="另存 JSON")
    ap.add_argument("--html", metavar="FILE", help="另存 HTML")
    ap.add_argument("--no-color", action="store_true", help="关闭颜色")
    ap.add_argument("--quiet", action="store_true", help="只写文件，不打印")
    args = ap.parse_args()

    if args.no_color or not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        C.disable()

    if not args.quiet:
        print(c("\n  正在体检，可能需要 1–3 分钟…", C.GRY))

    df = df_info()
    consumed = apfs_consumed()
    env = env_checks()

    roots, details = candidate_paths()
    root_items = scan_targets(roots, min_bytes=0)
    detail_items = scan_targets(details + app_children(), min_bytes=200 * 1024 ** 2)

    deep = None
    if args.deep:
        if not args.quiet:
            print(c("  深扫全盘大文件，可能要几分钟…", C.GRY))
        deep = deep_files(top_n=args.top, min_gb=args.min_gb)

    if not args.quiet:
        render_report(root_items, detail_items, df, consumed, env, deep, env.get("rm_shim"))

    if args.json:
        render_json(args.json, root_items + detail_items, df, consumed, env, deep)
        print("  JSON 已保存：%s" % args.json)
    if args.html:
        render_html(args.html, detail_items, df, consumed, env, deep)
        print("  HTML 已保存：%s" % args.html)

    return 0

if __name__ == "__main__":
    sys.exit(main())
