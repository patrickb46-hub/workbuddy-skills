#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 macOS「信息」App（iMessage）按日期导出图片附件，并按消息文字分组归档。

默认 dry-run（只打印映射表，不碰任何文件）。

示例
----
# 1) 只看不写
python3 archive.py --date 2026-09-30 --out ~/Desktop/某目录

# 2) 实做：复制 + 出 JPG + 再分 HEIC/JPG 子目录
python3 archive.py --date 2026-09-30 --out ~/Desktop/某目录 \
        --apply --jpg --split-format

# 3) 自定义分组路径（覆盖默认的「文件夹名=消息文字」）
python3 archive.py --date 2026-09-30 --out ~/Desktop/x \
        --map "wp[11]=英语/wp二练" --map "勾股=数学/勾股"

--map 的键：写「文字」即可；若同名文字有多组，用「文字[张数]」消歧。
"""
import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta

HOME = os.path.expanduser("~")
DEFAULT_DB = os.path.join(HOME, "Library/Messages/chat.db")
APPLE_EPOCH_OFFSET = 978307200


def norm_text(t):
    if not t:
        return ""
    t = unicodedata.normalize("NFC", t)
    return t.replace("\ufffc", "").replace("\u200b", "").strip()


def connect_ro(db):
    """只读打开 chat.db（含 WAL 中的最新数据）"""
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        con.execute("select count(*) from message").fetchone()
        return con
    except sqlite3.Error as e:
        print("直接只读打开失败（%s），回退到临时快照…" % e)
        tmp = "/tmp/_imsg_snapshot"
        os.makedirs(tmp, exist_ok=True)
        for suf in ("", "-wal", "-shm"):
            if os.path.exists(db + suf):
                shutil.copy2(db + suf, os.path.join(tmp, "chat.db" + suf))
        return sqlite3.connect(os.path.join(tmp, "chat.db"))


def fetch(con, day=None, days=1, handle=None):
    """取指定日期范围内、带图片附件的消息"""
    cur = con.cursor()
    if day:
        start = datetime.strptime(day, "%Y-%m-%d")
    else:
        start = (datetime.now() - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    ts = start.timestamp() - APPLE_EPOCH_OFFSET

    sql = """
        SELECT m.ROWID, m.text,
               datetime(m.date/1000000000 + 978307200,'unixepoch','localtime') AS t,
               h.id
        FROM message m LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE m.date/1000000000 >= ?
        ORDER BY m.date ASC
    """
    rows = cur.execute(sql, (ts,)).fetchall()

    out = []
    for rid, text, when, sender in rows:
        if handle and handle not in (sender or ""):
            continue
        atts = cur.execute("""
            SELECT a.filename, a.mime_type
            FROM attachment a
            JOIN message_attachment_join j ON j.attachment_id = a.ROWID
            WHERE j.message_id = ?
        """, (rid,)).fetchall()
        atts = [(f, mt) for f, mt in atts if (mt or "").startswith("image/") and f]
        if not atts:
            continue
        out.append({"rid": rid, "text": norm_text(text), "raw": text,
                    "when": when, "sender": sender, "atts": atts})
    return out


def build_map(msgs, overrides):
    """把 (文字[, 张数]) -> 目标相对路径。返回 (mapping, problems)"""
    problems = []
    # 重名检测：同一文字出现多次且没给张数限定 -> 需要用 --map 文字[张数] 消歧
    by_text = {}
    for m in msgs:
        by_text.setdefault(m["text"], []).append(m)

    mapping = []
    for m in msgs:
        key_count = "%s[%d]" % (m["text"], len(m["atts"]))
        if key_count in overrides:
            dest = overrides[key_count]
        elif m["text"] in overrides:
            dest = overrides[m["text"]]
        else:
            if len(by_text[m["text"]]) > 1:
                problems.append(
                    "文字 %r 出现 %d 次（张数 %s），需要 --map \"%s[张数]=路径\" 消歧"
                    % (m["text"], len(by_text[m["text"]]),
                       [len(x["atts"]) for x in by_text[m["text"]]], m["text"]))
                continue
            dest = m["text"]
        if not dest:
            problems.append("rowid %s 没有可用文字，且未在 --map 中指定目标" % m["rid"])
            continue
        m["dest"] = dest
        mapping.append(m)

    seen = {}
    for m in mapping:
        if m["dest"] in seen:
            problems.append("目标重复：%s（rowid %s 与 %s）"
                            % (m["dest"], m["rid"], seen[m["dest"]]))
        seen[m["dest"]] = m["rid"]
    return mapping, problems


def main():
    ap = argparse.ArgumentParser(description="iMessage 图片按消息文字分组归档")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--date", help="YYYY-MM-DD，从该日 00:00 起")
    ap.add_argument("--days", type=int, default=1, help="不指定 --date 时取最近 N 天")
    ap.add_argument("--handle", help="只取该联系人的地址（如 <handle>@icloud.com）")
    ap.add_argument("--out", required=True, help="目标根目录")
    ap.add_argument("--map", action="append", default=[],
                    metavar="文字[张数]=相对路径", help="可多次；覆盖默认的分组名")
    ap.add_argument("--apply", action="store_true", help="真的写入（默认 dry-run）")
    ap.add_argument("--jpg", action="store_true", help="额外转出同名 .jpg 副本")
    ap.add_argument("--quality", default="92", help="JPG 质量，默认 92")
    ap.add_argument("--split-format", action="store_true",
                    help="在每个分组文件夹内再分 HEIC/ 与 JPG/ 两级")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit("找不到数据库：%s" % args.db)

    overrides = {}
    for item in args.map:
        if "=" not in item:
            sys.exit("--map 格式应为 文字[张数]=相对路径，收到：%r" % item)
        k, v = item.split("=", 1)
        overrides[k.strip()] = v.strip()

    con = connect_ro(args.db)
    msgs = fetch(con, day=args.date, days=args.days, handle=args.handle)
    if not msgs:
        sys.exit("没有找到带图片的消息。")

    total = sum(len(m["atts"]) for m in msgs)
    print("带图片的消息：%d 条，共 %d 张\n" % (len(msgs), total))

    mapping, problems = build_map(msgs, overrides)

    for m in mapping:
        print("组 %-24s <- %2d 张  [%s]  %s"
              % (m["dest"], len(m["atts"]), m["rid"], m["when"]))
        for f, _ in m["atts"]:
            p = os.path.expanduser(f) if f.startswith("~") else f
            if not os.path.exists(p):
                problems.append("源文件不存在：%s" % p)
            elif os.path.getsize(p) == 0:
                problems.append("源文件为空：%s" % p)

    # 目标同名冲突
    for m in mapping:
        d = os.path.join(os.path.expanduser(args.out), m["dest"])
        for f, _ in m["atts"]:
            p = os.path.expanduser(f) if f.startswith("~") else f
            base = os.path.basename(p)
            for target in ([os.path.join(d, "HEIC", base)] if args.split_format
                           else [os.path.join(d, base)]):
                if os.path.exists(target):
                    problems.append("目标已存在同名文件：%s" % target)

    if problems:
        print("\n!!! 预检发现问题，已中止：")
        for p in problems:
            print("  - %s" % p)
        sys.exit(1)

    print("\n预检通过：%d 组 / %d 张" % (len(mapping), total))

    if not args.apply:
        print("（dry-run，未做任何改动。加 --apply 执行）")
        return

    root = os.path.expanduser(args.out)
    n_h = n_j = 0
    for m in mapping:
        d = os.path.join(root, m["dest"])
        if args.split_format:
            hdir = os.path.join(d, "HEIC")
            os.makedirs(hdir, exist_ok=True)
            if args.jpg:
                os.makedirs(os.path.join(d, "JPG"), exist_ok=True)
        else:
            hdir = d
            os.makedirs(d, exist_ok=True)

        for f, _ in m["atts"]:
            p = os.path.expanduser(f) if f.startswith("~") else f
            base = os.path.basename(p)
            heic_dst = os.path.join(hdir, base)
            shutil.copy2(p, heic_dst)
            n_h += 1
            if args.jpg:
                jpg_dir = os.path.join(d, "JPG") if args.split_format else d
                jpg = os.path.join(jpg_dir, os.path.splitext(base)[0] + ".jpg")
                r = subprocess.run(
                    ["sips", "-s", "format", "jpeg",
                     "-s", "formatOptions", str(args.quality), heic_dst, "--out", jpg],
                    capture_output=True, text=True)
                if r.returncode != 0 or not os.path.exists(jpg):
                    sys.exit("JPG 转换失败：%s\n%s%s" % (heic_dst, r.stdout, r.stderr))
                n_j += 1
        print("OK  %-24s %2d 张 -> %s" % (m["dest"], len(m["atts"]), d))

    print("\n完成：HEIC %d 张，JPG %d 张（源文件未删除）" % (n_h, n_j))


if __name__ == "__main__":
    main()
