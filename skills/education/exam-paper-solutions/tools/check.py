#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check.py — 交付前一条命令跑完全部结构自检，替代「grep 配平 + 数 id + 看组件」那串手工动作。

  check.py 全解.html [--kind auto|sol|kp|quiz]
  check.py ./分组目录              # 目录里所有 html 都查

只报结论，不给废话：OK / WARN / FAIL，有 FAIL 时退出码 1。
它把「改完再跑一遍截图」的往返省掉——结构错在这里就拦住。
"""
import argparse
import glob
import os
import re
import sys

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
BANNED = ["如图", "同上", "见上", "见①", "见图1"]
PLACEHOLDER = re.compile(r"【[^】\n]{1,40}】")


def kind_of(s):
    if 'class="qcard"' in s:
        return "sol"
    if 'class="kp-item"' in s:
        return "kp"
    if 'class="ans"' in s or "ans-body" in s:
        return "quiz"
    return "unknown"


def body_of(chunk):
    return re.sub(r"<[^>]+>", " ", chunk)


def cards(s):
    """按 qcard 切开，返回 [(no, chunk)]。"""
    parts = re.split(r'(?=<section class="qcard")', s)
    out = []
    for p in parts[1:]:
        m = re.search(r'<section class="qcard" id="q([^"]+)"', p)
        out.append((m.group(1) if m else "?", p))
    return out


def check_sol(s, res):
    cs = cards(s)
    if not cs:
        res.append((FAIL, "没有 .qcard：题卡一块都没有"))
        return
    res.append((OK, "题卡 %d 块" % len(cs)))

    # 每块四段 + fd-sol
    for no, c in cs:
        n_fd = len(re.findall(r'<div class="fd[ "]', c))
        has_sol = 'fd fd-sol' in c
        seal = c.split('fd fd-sol')[-1] if has_sol else ""
        n_restate = seal.count('class="restate"')
        if n_fd < 4:
            res.append((FAIL, "第 %s 题只有 %d 个折叠段（应为 4）" % (no, n_fd)))
        if not has_sol:
            res.append((FAIL, "第 %s 题的完整解答缺 fd-sol 类，「全部展开解答」抓不到" % no))
        if not n_restate:
            # 纯代数题本来就没有辅助线，别误判成缺陷
            geo = re.search(r"[作连引建画]\s*[^，。；]{0,8}(线|弧|点|系|垂)", body_of(c))
            if geo:
                res.append((FAIL, "第 %s 题缺 .restate（作图重述）——正文里有作图语句" % no))
            else:
                res.append((WARN, "第 %s 题没有作图重述（纯代数题可接受）" % no))
        # 禁止指代
        body = re.sub(r"<[^>]+>", "", seal)
        for w in BANNED:
            if w in body:
                res.append((FAIL, "第 %s 题完整解答里出现「%s」——必须把辅助线重述一遍" % (no, w)))
                break
        if not re.search(r'<span class="final">', c):
            res.append((WARN, "第 %s 题没有 .final 答案框" % no))
        m = re.search(r'<span class="qno">第\s*([^<]+?)\s*题</span>', c)
        if m and m.group(1) != no:
            res.append((WARN, "第 %s 题：id=q%s 与题号「%s」不一致（搜索会定位错）"
                        % (no, no, m.group(1))))

    # data-target
    targets = re.findall(r'data-target="([^"]+)"', s)
    ids = set(re.findall(r'\sid="([^"]+)"', s))
    miss = [t for t in targets if t not in ids]
    if miss:
        res.append((FAIL, "题号旁的展开按钮指向不存在的 id：%s" % ", ".join(miss[:5])))
    if not targets:
        res.append((FAIL, "没有任何 .qbtn 展开按钮"))

    # 搜索定位依赖 .qhd.q
    if 'class="qhd q"' not in s:
        res.append((FAIL, "题号外层缺 .qhd.q 类，站内搜索定位会失效"))
    # 速查表
    if "答案速查表" not in s:
        res.append((FAIL, "没有答案速查表"))
    return


def check_kp(s, res):
    items = s.count('class="kp-item"')
    if not items:
        res.append((FAIL, "没有 .kp-item 考点块"))
    else:
        res.append((OK, "考点块 %d 个" % items))
    for m in re.finditer(r'<div class="kp-item"[^>]*>(.*?)(?=<div class="kp-item"|</div>\s*<h3|</body>)', s, re.S):
        blk = m.group(1)
        no = re.search(r'<span class="kp-no">([^<]*)</span>', blk)
        no = no.group(1) if no else "?"
        if 'class="kp-tag"' not in blk:
            res.append((FAIL, "%s 缺 .kp-tag 考点标签" % no))
        if 'class="kp-row"' not in blk:
            res.append((FAIL, "%s 没有知识点行（.kp-row）" % no))
        eg = blk.count('class="kp-eg"')
        if eg < 2:
            res.append((WARN, "%s 配套题只有 %d 道（要求 2–3 道）" % (no, eg)))
        if 'kp-tip' not in blk:
            res.append((WARN, "%s 没有易错点（.kp-tip），没有也要写一行「—」" % no))
    if "考点分布" not in s:
        res.append((FAIL, "缺全卷考点分布表"))
    if 'class="bars"' not in s and 'class="bar"' not in s:
        res.append((WARN, "分布表上方没有可视化（章节×考点条形图）"))
    if "本节考点小结" not in s:
        res.append((WARN, "缺「本节考点小结」表"))
    return


def check_quiz(s, res):
    if "<details" in s:
        res.append((FAIL, "出现 <details>，打印时答案压不开——必须用 checkbox 折叠"))
    na = s.count('class="ans"')
    res.append((OK if na else FAIL, "答案折叠块 %d 个" % na))
    if "＿＿＿＿" not in s:
        res.append((FAIL, "没找到填空线 ＿＿＿＿（U+FF3F 四个）"))
    hrefs = set(re.findall(r'href="#([^"]+)"', s))
    ids = set(re.findall(r'\sid="([^"]+)"', s))
    miss = hrefs - ids
    if miss:
        res.append((FAIL, "目录锚点没有对应正文 id：%s" % ", ".join(sorted(miss)[:5])))
    return


def check_common(s, res, kind):
    if s.count("<details") and kind != "quiz":
        res.append((FAIL, "出现 <details>：打印时折叠内容会整块消失"))

    # div 配平
    o, c = len(re.findall(r"<div\b", s)), len(re.findall(r"</div>", s))
    if o != c:
        res.append((FAIL, "div 不配平：%d 开 / %d 闭（差 %d）" % (o, c, o - c)))
    else:
        res.append((OK, "div 配平 %d/%d" % (o, c)))

    # id 唯一
    ids = re.findall(r'\sid="([^"]+)"', s)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        res.append((FAIL, "id 重复：%s（折叠会连动）" % ", ".join(dup[:6])))
    else:
        res.append((OK, "id 唯一 %d 个" % len(ids)))

    # 组件
    has_search = "WBS-SEARCH-WIDGET" in s
    has_ask = "waskCfg" in s
    if kind in ("sol", "kp"):
        if not has_search:
            res.append((WARN, "没注入站内搜索 —— 跑 inject_search.py"))
        if not has_ask:
            res.append((WARN, "没注入提问侧栏 —— 跑 inject_ask.py"))
        if has_search and has_ask:
            res.append((OK, "搜索 + 提问组件都在"))
    if 'id="waskCfg"' in s and re.search(r'id="waskCfg">\{"endpoint[^}]*"key":""', s):
        res.append((WARN, "提问侧栏没有 key（学生要手粘）"))

    # 残留占位符（先剥掉组件脚本，里面的【选中原文】是组件自带的，不算）
    body = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    ph = PLACEHOLDER.findall(body)
    ph = [x for x in ph if not re.match(r"^【[^】]{0,3}】$", x)]
    if ph:
        extra = " 等 %d 处" % len(ph) if len(ph) > 4 else ""
        res.append((WARN, "疑似模板占位符没换：%s%s" % ("、".join(ph[:4]), extra)))

    # 打印样式
    if "display:block!important" not in s.replace(" ", ""):
        res.append((WARN, "打印样式里没看到「折叠全展开」规则，检查 @media print"))
    return


def has_plain_key(s):
    m = re.search(r'id="waskCfg">(.*?)</script>', s, re.S)
    if not m:
        return False
    try:
        import json
        return bool(json.loads(m.group(1) or "{}").get("key"))
    except Exception:
        return '"key":"sk-' in s


def run(path, kind=None, secrets=False):
    s = open(path, encoding="utf-8").read()
    k = kind or kind_of(s)
    res = []
    check_common(s, res, k)
    if k == "sol":
        check_sol(s, res)
    elif k == "kp":
        check_kp(s, res)
    elif k == "quiz":
        check_quiz(s, res)
    else:
        res.append((WARN, "认不出类型（没有 qcard / kp-item / ans），只做了通用检查"))

    nfail = sum(1 for st, _ in res if st == FAIL)
    print("── %s  [%s]  %.0f KB" % (os.path.basename(path), k, len(s.encode()) / 1024))
    for st, msg in res:
        print("  %s %s" % (st, msg))
    if secrets:
        print("  %s %s" % (WARN if has_plain_key(s) else OK,
                           "文件里有明文 api key —— 外发前跑 inject_ask.py --strip-key"
                           if has_plain_key(s) else "没有明文 api key"))
    print("  → %s" % ("通过" if not nfail else "%d 项必须修" % nfail))
    return nfail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--kind", default=None, choices=["sol", "kp", "quiz"])
    ap.add_argument("--secrets", action="store_true", help="额外报告文件里有没有明文 api key")
    a = ap.parse_args()

    files = []
    if os.path.isdir(a.path):
        files = sorted(glob.glob(os.path.join(a.path, "*.html")))
        files = [f for f in files if "_备份" not in f]
    else:
        files = [a.path]
    if not files:
        sys.exit("没有 html 可查")

    bad = 0
    for f in files:
        bad += run(f, a.kind, a.secrets)
        print()
    if bad:
        print("共 %d 项 FAIL" % bad)
        sys.exit(1)


if __name__ == "__main__":
    main()
