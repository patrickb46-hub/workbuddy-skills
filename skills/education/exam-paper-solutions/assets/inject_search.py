#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给试卷全解 / 考点知识点 / 练习卷 HTML 注入或升级「站内搜索」组件（幂等）。

用法：
  python3 inject_search.py <文件或目录> [...]
  python3 inject_search.py ~/Desktop/Recently/日常作业                 # 递归处理该目录下所有 .html
  python3 inject_search.py --check ~/Desktop/Recently/日常作业        # 只报告，不写文件

行为：
  · 片段来自同目录的 search-widget.html（本脚本与它同在 assets/）
  · 文件无组件            → 在最后一个 </body> 前插入
  · 文件已有旧版本组件    → 原地替换为新版本（按片段首行的 vN 判断）
  · 文件已是当前版本      → 跳过
  · 只在内容真正变化时才写回磁盘
退出码：0 正常；1 参数问题或片段缺失。
"""
import re
import sys
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIDGET = HERE / "search-widget.html"
HTML_SUFFIX = {".html", ".htm"}

BLOCK_RE = re.compile(r"<!-- WBS-SEARCH-WIDGET.*?<!-- /WBS-SEARCH-WIDGET -->", re.S)
VER_RE = re.compile(r"WBS-SEARCH-WIDGET\s+(v\d+)")


def iter_html(targets):
    for raw in targets:
        p = Path(raw).expanduser()
        if p.is_dir():
            for f in sorted(p.rglob("*.html")):
                if f.name.startswith("."):
                    continue
                yield f
        elif p.suffix.lower() in HTML_SUFFIX:
            yield p
        else:
            print(f"  ! 跳过（不是 .html）：{p}")


def inject_one(path, snippet, want_ver, check_only):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "err", "非 UTF-8，跳过"

    m = BLOCK_RE.search(text)
    if m:
        have = VER_RE.search(m.group(0))
        have_ver = have.group(1) if have else "v?"
        if have_ver == want_ver:
            return "skip", f"已是 {want_ver}"
        if check_only:
            return "stale", f"{have_ver} → {want_ver} 待升级"
        new = text[:m.start()] + snippet + text[m.end():]
        path.write_text(new, encoding="utf-8")
        return "upd", f"{have_ver} → {want_ver} 已升级"

    idx = text.lower().rfind("</body>")
    if idx >= 0:
        new = text[:idx] + snippet + "\n" + text[idx:]
    else:
        new = text.rstrip() + "\n" + snippet + "\n"

    if check_only:
        return "miss", "缺少搜索组件"

    path.write_text(new, encoding="utf-8")
    return "done", f"已注入 {want_ver}"


def main():
    ap = argparse.ArgumentParser(description="给 HTML 注入/升级站内搜索组件（幂等）")
    ap.add_argument("targets", nargs="+", help="HTML 文件或目录（目录会递归）")
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    ap.add_argument("--quiet", action="store_true", help="只输出统计")
    args = ap.parse_args()

    if not WIDGET.exists():
        print(f"✗ 找不到片段文件：{WIDGET}")
        return 1

    snippet = WIDGET.read_text(encoding="utf-8").strip()
    vm = VER_RE.search(snippet.split("\n", 1)[0])
    want_ver = vm.group(1) if vm else "v1"

    stat = {"done": 0, "upd": 0, "skip": 0, "miss": 0, "stale": 0, "err": 0}
    icons = {"done": "✓", "upd": "↑", "skip": "·", "miss": "!", "stale": "!", "err": "✗"}

    for f in iter_html(args.targets):
        kind, msg = inject_one(f, snippet, want_ver, args.check)
        stat[kind] += 1
        if not args.quiet:
            print(f"  {icons[kind]} {f.name}  {msg}")

    if args.check:
        todo = stat["miss"] + stat["stale"]
        print(f"\n目标版本 {want_ver} ｜ 待处理 {todo} 个（缺失 {stat['miss']} / 待升级 {stat['stale']}）"
              f" ｜ 已最新 {stat['skip']} 个 ｜ 出错 {stat['err']} 个")
    else:
        print(f"\n目标版本 {want_ver} ｜ 新注入 {stat['done']} 个 ｜ 升级 {stat['upd']} 个"
              f" ｜ 跳过 {stat['skip']} 个 ｜ 出错 {stat['err']} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
