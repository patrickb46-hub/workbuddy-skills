#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给试卷全解 / 考点知识点 / 练习卷 HTML 注入「选中提问」（DeepSeek 侧栏）组件（幂等）。

用法：
  python3 inject_ask.py <文件或目录> [...]
  python3 inject_ask.py ~/Desktop/Recently/日常作业                 # 递归处理该目录下所有 .html
  python3 inject_ask.py --check ~/Desktop/Recently/日常作业        # 只报告，不写文件
  python3 inject_ask.py --strip-key <文件或目录>                   # 抹掉文件里的 api key（分享前用）
  python3 inject_ask.py --save-key                                # 把当前 key 存成本地文件（600）
  python3 inject_ask.py --where                                   # 只说 key 从哪来，不动文件

行为：
  · 片段来自同目录的 ask-widget.html（本脚本与它同在 assets/）
  · 文件无组件            → 在最后一个 </body> 前插入
  · 文件已有旧版本组件    → 原地替换为新版本（按片段首行的 vN 判断）
  · 文件已是当前版本      → 只补 key（若文件里 key 为空且有可用 key）
  · api key 来源（按优先级）：
        --key 参数  >  --key-file 参数  >  $WBS_KEY_FILE  >  ~/.workbuddy/secrets/deepseek.key
        >  环境变量 DEEPSEEK_API_KEY / DS_API_KEY / COPILOT_PROVIDER_API_KEY
  · 脚本自己读 key 文件，**不打印 key 本身**，只打印来源路径与掩码 —— agent 全程不接触明文
  · key 写在 <script id="waskCfg"> 的 JSON 里；localStorage 里的值优先级更高
退出码：0 正常；1 参数问题或片段缺失。
"""
import json
import os
import re
import sys
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIDGET = HERE / "ask-widget.html"
HTML_SUFFIX = {".html", ".htm"}
KEY_FILE_DEFAULT = Path("~/.workbuddy/secrets/deepseek.key").expanduser()

BLOCK_RE = re.compile(r"<!-- WBS-ASK-WIDGET.*?<!-- /WBS-ASK-WIDGET -->", re.S)
VER_RE = re.compile(r"WBS-ASK-WIDGET\s+(v\d+)")
CFG_RE = re.compile(r'(<script type="application/json" id="waskCfg">)(.*?)(</script>)', re.S)


def env_key():
    for name in ("DEEPSEEK_API_KEY", "DS_API_KEY", "COPILOT_PROVIDER_API_KEY"):
        v = (os.environ.get(name) or "").strip()
        if v:
            return v, "环境变量 " + name
    return "", ""


def read_key_file(p):
    """一行密文即可：裸 key、KEY=value、带引号都能认；# 开头是注释。"""
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip().strip("\"'")
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            head = line.split("=", 1)[0].strip().upper()
            if head.endswith("API_KEY") or head == "KEY":
                line = line.split("=", 1)[1].strip().strip("\"'")
        if line:
            return line
    return ""


def mask(k):
    if not k:
        return "（无）"
    if len(k) <= 14:
        return k[:4] + "…"
    return k[:7] + "…" + k[-4:]


def candidates(args):
    out = []
    if args.key_file:
        out.append(Path(args.key_file).expanduser())
    if os.environ.get("WBS_KEY_FILE"):
        out.append(Path(os.environ["WBS_KEY_FILE"]).expanduser())
    out.append(KEY_FILE_DEFAULT)
    # 去重保序
    seen, uniq = set(), []
    for p in out:
        s = str(p)
        if s not in seen:
            seen.add(s)
            uniq.append(p)
    return uniq


def resolve_key(args):
    """返回 (key, 来源说明)。都不打印明文。"""
    if args.key is not None:
        return args.key.strip(), "--key 参数"
    for p in candidates(args):
        k = read_key_file(p)
        if k:
            return k, str(p).replace(str(Path.home()), "~")
    return env_key()


def loose_perm(p):
    try:
        return bool(p.stat().st_mode & 0o077)
    except OSError:
        return False


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


def set_key(block, key):
    """把 key 写进片段的 waskCfg JSON；key 为空表示清空。返回 (新片段, 原值)。"""
    m = CFG_RE.search(block)
    if not m:
        return block, None
    try:
        cfg = json.loads(m.group(2) or "{}")
    except json.JSONDecodeError:
        cfg = {}
    old = cfg.get("key", "")
    if old == key:
        return block, old
    cfg["key"] = key
    new_cfg = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
    return block[:m.start(2)] + new_cfg + block[m.end(2):], old


def inject_one(path, snippet, want_ver, check_only, key, strip):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "err", "非 UTF-8，跳过"

    m = BLOCK_RE.search(text)
    if m:
        have = VER_RE.search(m.group(0))
        have_ver = have.group(1) if have else "v?"
        block = m.group(0)
        if have_ver != want_ver:
            if check_only:
                return "stale", f"{have_ver} → {want_ver} 待升级"
            new_block, _ = set_key(snippet, key)
            path.write_text(text[:m.start()] + new_block + text[m.end():], encoding="utf-8")
            return "upd", f"{have_ver} → {want_ver} 已升级"
        # 版本已最新：只处理 key
        if strip:
            new_block, old = set_key(block, "")
            if old:
                if check_only:
                    return "stale", "含明文 key，待清除"
                path.write_text(text[:m.start()] + new_block + text[m.end():], encoding="utf-8")
                return "upd", "已清除明文 key"
            return "skip", f"已是 {want_ver}（无 key）"
        if key:
            new_block, old = set_key(block, key)
            if old != key:
                if check_only:
                    return "stale", "文件里没有 key，待写入"
                path.write_text(text[:m.start()] + new_block + text[m.end():], encoding="utf-8")
                return "upd", "已写入 key" if not old else "已更新 key"
            return "skip", f"已是 {want_ver}（key 已就位）"
        has_key = bool(CFG_RE.search(block)) and '"key":""' not in (CFG_RE.search(block).group(2) or "")
        return "skip", f"已是 {want_ver}" + ("（key 已内置）" if has_key else "（无 key，首次使用需粘贴）")

    idx = text.lower().rfind("</body>")
    new_block, _ = set_key(snippet, "" if strip else key)
    if idx >= 0:
        new = text[:idx] + new_block + "\n" + text[idx:]
    else:
        new = text.rstrip() + "\n" + new_block + "\n"

    if check_only:
        return "miss", "缺少提问组件"

    path.write_text(new, encoding="utf-8")
    return "done", f"已注入 {want_ver}" + ("（带 key）" if (key and not strip) else "")


def main():
    ap = argparse.ArgumentParser(description="给 HTML 注入/升级「选中提问」侧栏（幂等）")
    ap.add_argument("targets", nargs="*", help="HTML 文件或目录（目录会递归）")
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    ap.add_argument("--strip-key", action="store_true", help="清除文件里的明文 api key")
    ap.add_argument("--key", default=None, help="显式指定 key（不建议：会进 shell 历史）")
    ap.add_argument("--key-file", default=None, help="指定 key 文件路径")
    ap.add_argument("--save-key", action="store_true", help="把当前可用的 key 存成本地文件（600）")
    ap.add_argument("--where", action="store_true", help="只报告 key 从哪来")
    ap.add_argument("--quiet", action="store_true", help="只输出统计")
    args = ap.parse_args()

    # --- 只要看 key 来源 ---
    if args.where:
        k, src = resolve_key(args)
        if not k:
            print("✗ 没有可用的 key。先跑 --save-key，或把 key 写进 %s" % KEY_FILE_DEFAULT)
            for p in candidates(args):
                print("  查过：%s%s" % (p, "（不存在）" if not p.exists() else ""))
            return 1
        print("key 来源：%s ｜ 掩码 %s ｜ 长度 %d" % (src, mask(k), len(k)))
        for p in candidates(args):
            if p.exists():
                flag = "⚠ 权限宽松，建议 chmod 600" if loose_perm(p) else "权限 OK"
                print("  文件 %s（%s）" % (p, flag))
        return 0

    # --- 把 key 落到本地文件 ---
    if args.save_key:
        k, src = resolve_key(args)
        if not k:
            print("✗ 没找到可保存的 key：环境变量为空，key 文件也不存在。")
            print("  手工建一个即可（内容只放一行 key）：")
            print("    mkdir -p ~/.workbuddy/secrets && chmod 700 ~/.workbuddy/secrets")
            print("    printf '%s' 'sk-你的key' > ~/.workbuddy/secrets/deepseek.key")
            print("    chmod 600 ~/.workbuddy/secrets/deepseek.key")
            return 1
        p = Path(args.key_file).expanduser() if args.key_file else KEY_FILE_DEFAULT
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(p.parent, 0o700)
        except OSError:
            pass
        p.write_text(k.strip() + "\n", encoding="utf-8")
        os.chmod(p, 0o600)
        print("✓ key 已保存：%s（掩码 %s，来源 %s，权限 600）" % (p, mask(k), src))
        print("  之后 inject_ask.py 会优先读这个文件，不用再靠环境变量。")
        return 0

    if not args.targets:
        print("✗ 没给目标文件/目录（只想存 key 就加 --save-key）")
        return 1

    if not WIDGET.exists():
        print(f"✗ 找不到片段文件：{WIDGET}")
        return 1

    snippet = WIDGET.read_text(encoding="utf-8").strip()
    vm = VER_RE.search(snippet.split("\n", 1)[0])
    want_ver = vm.group(1) if vm else "v1"

    if args.strip_key:
        key, ksrc = "", ""
    else:
        key, ksrc = resolve_key(args)
    if not key and not args.strip_key:
        print("! 没有可用 key（文件与环境变量都没找到）——组件会退回「首次使用时手动粘贴」模式。")
        print("  要固化下来就运行：inject_ask.py --save-key")

    stat = {"done": 0, "upd": 0, "skip": 0, "miss": 0, "stale": 0, "err": 0}
    icons = {"done": "✓", "upd": "↑", "skip": "·", "miss": "!", "stale": "!", "err": "✗"}

    for f in iter_html(args.targets):
        kind, msg = inject_one(f, snippet, want_ver, args.check, key, args.strip_key)
        stat[kind] += 1
        if not args.quiet:
            print(f"  {icons[kind]} {f.name}  {msg}")

    if key and not args.quiet:
        print("  key：%s（%s）" % (mask(key), ksrc))

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
