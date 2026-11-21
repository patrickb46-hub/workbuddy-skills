#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — 把一份极简规格（.mk）渲染成全解 / 考点知识点 HTML。

用法：
  build.py sol  spec.mk -o 全解.html      [--template assets/solution-template.html]
  build.py kp   spec.mk -o 考点知识点.html
  build.py sample [sol|kp]                 # 打印格式样例

设计要点（都是为了少打字、少犯错）：
  * 骨架、id、class、按钮、折叠层全部由脚本生成 —— 模型只写中文内容。
  * 答案只写一遍（@ans），自动铺到「答案」段、「完整解答」末尾的「答：」、答案速查表。
  * 「完整解答」开头的作图重述自动从 @aux 复制（@aux 里 ~ 开头的说明行不复制），
    结构上根除「如图/同上」那类错误。
  * 站内搜索 / 提问侧栏永远来自模板，不会漏注入。
"""
import argparse
import os
import re
import sys
import html as _html

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
TPL = os.path.join(SKILL, "assets", "solution-template.html")

# ---------------------------------------------------------------- 通用小工具


def die(msg):
    sys.stderr.write("build.py: " + msg + "\n")
    sys.exit(2)


_SAFE_TAG = re.compile(r"<(?=[a-zA-Z/!])")


def safe(s):
    """内容里允许真 HTML；只把不像标签的 '<' 转义，防止 a<b 之类把页面咬坏。"""
    out = []
    for i, ch in enumerate(s):
        if ch == "<":
            nxt = s[i + 1:i + 2]
            out.append("<" if re.match(r"[a-zA-Z/!]", nxt) else "&lt;")
        else:
            out.append(ch)
    return "".join(out)


_PAREN_END = re.compile(r"[（(]")


def auto_rs(s):
    """行末括号 → <span class="rs">。行尾加 \\ 可关闭。"""
    raw = s.rstrip()
    if raw.endswith("\\"):
        return safe(raw[:-1].rstrip())
    if not (raw.endswith("）") or raw.endswith(")")):
        return safe(raw)
    last = _PAREN_END.findall(raw)
    if not last:
        return safe(raw)
    open_ch = last[-1]
    idx = raw.rfind(open_ch)
    if idx <= 0:                      # 整行就是个括号，不处理
        return safe(raw)
    head, tail = raw[:idx], raw[idx:]
    if len(tail) > 40:                # 太长的多半是正文不是依据
        return safe(raw)
    return safe(head) + '<span class="rs">' + safe(tail) + "</span>"


def p(s, cls="pf"):
    return '        <p class="%s">%s</p>' % (cls, s)


# ---------------------------------------------------------------- 规格解析

DIRECTIVES = {
    "title", "meta", "note", "stem", "src", "q", "aux", "idea", "ans",
    "sol", "fig", "cap", "alt", "err", "quick",
    "sect", "kp", "k", "tip", "eg", "q", "qans", "eans", "step", "th",
}


def parse_spec(text):
    """返回 [('dir','title',arg), ('dir','stem','',[lines...])] 顺序流。"""
    items = []          # 每项 (name, arg, [lines])
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("@") or line.startswith("%"):
            m = re.match(r"^[@%]\s*([A-Za-z]+)\s*(.*)$", line)
            if not m:
                if cur:
                    cur[2].append(line)
                continue
            name, arg = m.group(1).lower(), m.group(2).strip()
            if name not in DIRECTIVES:
                die("未知指令：%s（第 %d 行）" % (name, len(items)))
            cur = (name, arg, [])
            items.append(cur)
        else:
            if cur is None:
                if line.strip():
                    die("内容出现在任何指令之前：%r" % line[:40])
                continue
            cur[2].append(line)
    return items


def blocks(items, name):
    return [it for it in items if it[0] == name]


# ---------------------------------------------------------------- 全解渲染


def render_lines(lines, sol_like=False, raw_html=False):
    """把一组文本行转成 HTML。规则：
       ## 标题      -> .step（仅 sol）
       >  开头      -> 原样 HTML
       -  开头      -> 无序列表项（用 .pf 模拟）
       ~  开头      -> 说明行（不加 .rs，不参与重述）
       空行         -> 忽略
    """
    out = []
    for ln in lines:
        if not ln.strip():
            continue
        s = ln.strip()
        if s.startswith(">"):
            out.append("        " + s[1:].strip())
            continue
        if sol_like and s.startswith("##"):
            out.append('        <div class="step">%s</div>' % safe(s.lstrip("#").strip()))
            continue
        if s.startswith("~"):
            out.append(p(safe(s[1:].strip())))
            continue
        if s.startswith("- "):
            out.append(p("·" + s[2:].strip()))
            continue
        out.append(p(auto_rs(s) if sol_like else safe(s)))
    return "\n".join(out)


def fold(label, fid, body, extra_cls="", head_extra=""):
    cls = "fd" + (" " + extra_cls if extra_cls else "")
    return (
        '    <div class="%s">\n'
        '      <input type="checkbox" class="fd-cb" id="%s">\n'
        '      <label class="fd-hd" for="%s"><span class="fd-t">%s</span>%s<span class="fd-ic"></span></label>\n'
        '      <div class="fd-bd">\n%s\n      </div>\n'
        '    </div>' % (cls, fid, fid, label, head_extra, body)
    )


def split_pipe(s, n=2):
    parts = [x.strip() for x in s.split("|")]
    while len(parts) < n:
        parts.append("")
    return parts


def build_question(q):
    no, sub = split_pipe(q["arg"], 2)
    no = no or str(q["idx"])
    fid = "f%s" % no

    aux_lines = q["aux"]
    why = [l for l in aux_lines if l.strip().startswith("~")]
    draw = [l for l in aux_lines if l.strip() and not l.strip().startswith("~")]

    # ① 辅助线
    if draw or why:
        body_aux = render_lines(
            [l if l.strip().startswith("~") else l for l in draw] + why, sol_like=True)
        aux_html = fold("辅助线", fid + "-aux", body_aux)
    else:
        # 纯代数题：保留这一段，写明不需要，别让四段缺一格
        aux_html = fold("辅助线", fid + "-aux",
                        p("本题不需要辅助线，直接按定义与公式推进"))

    # ② 思路（小步）
    idea_html = ""
    steps = [l for l in q["idea"] if l.strip()]
    if steps:
        inner = []
        for i, ln in enumerate(steps, 1):
            t, c = split_pipe(ln, 2)
            inner.append(
                '        <div class="fd fd-sm">\n'
                '          <input type="checkbox" class="fd-cb" id="%s-s%d">\n'
                '          <label class="fd-hd" for="%s-s%d"><span class="fd-t">小步 %d</span>%s<span class="fd-ic"></span></label>\n'
                '          <div class="fd-bd">\n            %s\n          </div>\n'
                '        </div>' % (fid, i, fid, i, i, safe(t), p(safe(c) if c else ""))
            )
        idea_html = fold("思路", fid + "-idea", "\n".join(inner))

    # ③ 答案
    ans = [l.strip() for l in q["ans"] if l.strip()]
    ans_body = "\n".join(
        '        <p class="pf"><span class="final">%s</span></p>' % safe(a) for a in ans)
    ans_html = fold("答案", fid + "-ans", ans_body) if ans else ""

    # ④ 完整解答
    sol_parts = []
    if draw:
        restate = "\n".join(
            '          <p class="pf">%s</p>' % auto_rs(l.strip()) for l in draw)
        sol_parts.append(
            '        <div class="restate">\n'
            '          <span class="restate-t">作图（重述）</span>\n'
            '%s\n'
            '        </div>' % restate)
    if q["sol"]:
        sol_parts.append(render_lines(q["sol"], sol_like=True))
    if q["fig"]:
        fig_lines = [l for l in q["fig"]]
        sol_parts.append('        <div class="fig">\n%s\n        </div>'
                         % "\n".join("          " + l.strip() for l in fig_lines if l.strip()))
    if q["cap"]:
        sol_parts.append('        <div class="cap">%s</div>'
                         % safe(" ".join(l.strip() for l in q["cap"] if l.strip())))
    if ans:
        sol_parts.append('        <p class="pf" style="margin-top:10px"><b>答：</b></p>')
        for a in ans:
            sol_parts.append('        <p class="pf"><span class="final">%s</span></p>' % safe(a))
    sol_html = fold("完整解答", fid + "-sol", "\n".join(sol_parts), "fd-sol")
    if not ans:
        sol_html = sol_html.replace('class="fd fd-sol"', 'class="fd fd-sol"')

    folds = "\n".join(x for x in [aux_html, idea_html, ans_html] if x)
    card = ('  <section class="qcard" id="q%s">\n'
            '    <div class="qhd q">\n'
            '      <span class="qno">第 %s 题</span>\n'
            '      <span class="qsub">%s</span>\n'
            '      <button class="qbtn" type="button" data-target="q%s">展开本题</button>\n'
            '    </div>\n'
            '%s\n%s\n'
            '  </section>') % (no, no, safe(sub), no, folds, sol_html)
    card = re.sub(r"\n{3,}", "\n\n", card)
    return card


DEFAULT_NOTE = """    <b>怎么用这份全解：</b>每题分四段折叠 —— <b>辅助线 → 思路 → 答案 → 完整解答</b>。
    先自己动手，卡住再逐段点开；题号右边的按钮一键展开／折叠本题，
    右下角「全部展开解答」只摊开四段里的完整解答，「全部展开」才连辅助线思路一起摊开；
    右上角可按题号或关键词搜索（打印时四段自动全部展开）。
    <br><b>想问一句：</b>选中正文任意一段 → 右键 →「提问」，右侧会开一个侧栏，可以直接把这段讲透。"""


def build_sol(items, tpl):
    tb = blocks(items, "title")
    title = (tb[0][1] if tb and tb[0][1] else
             " ".join(x.strip() for x in (tb[0][2] if tb else []) if x.strip())) or "全解"
    mb = blocks(items, "meta")
    meta = (mb[0][1] if mb and mb[0][1] else
            " ".join(x.strip() for x in (mb[0][2] if mb else []) if x.strip()))

    # 题干
    stem_items = blocks(items, "stem")
    stem_lines = []
    for it in stem_items:
        stem_lines.extend(it[2])
    stem_html = render_lines(stem_lines, sol_like=False)
    stem_html = stem_html.replace('<p class="pf">', "<p>")

    note_items = blocks(items, "note")
    note_html = ""
    if note_items:
        note_html = render_lines(([note_items[0][1]] if note_items[0][1] else []) +
                                 note_items[0][2], sol_like=False)
    if not note_html.strip():
        note_html = DEFAULT_NOTE

    # 题目：按出现顺序把 aux/idea/ans/sol/fig/cap 归到当前题
    qs = []
    cur = None
    for it in items:
        if it[0] == "q":
            cur = {"arg": it[1], "idx": len(qs) + 1, "aux": [], "idea": [], "ans": [],
                   "sol": [], "fig": [], "cap": []}
            qs.append(cur)
        elif cur is not None and it[0] in ("aux", "idea", "ans", "sol", "fig", "cap"):
            cur[it[0]].extend(it[2])

    if not qs:
        die("规格里没有 @q（至少一道题）")

    nos = [split_pipe(q["arg"], 2)[0] or str(q["idx"]) for q in qs]
    dup = {x for x in nos if nos.count(x) > 1}
    if dup:
        die("题号重复：%s" % ", ".join(sorted(dup)))
    for q, no in zip(qs, nos):
        q["arg"] = q["arg"] if q["arg"].strip() else no

    cards = "\n\n".join(build_question(q) for q in qs)

    # 别解
    alt = blocks(items, "alt")
    alt_html = ""
    if alt:
        alt_html = ('  <h2>二、别解与验算</h2>\n' +
                    fold("别解", "f-alt", render_lines(alt[0][2], sol_like=True),
                         head_extra="换一条路走，答案必须一样"))

    # 易错
    errs = [l for it in blocks(items, "err") for l in it[2] if l.strip()]
    err_html = ""
    if errs:
        rows = []
        for i, ln in enumerate(errs, 1):
            a, b = split_pipe(ln, 2)
            rows.append('    <tr><td class="c">%d</td><td>%s</td><td>%s</td></tr>'
                        % (i, safe(a), safe(b)))
        err_html = ('  <h2>三、易错提醒</h2>\n'
                    '  <table class="kptable">\n'
                    '    <tr><th style="width:6%%">#</th><th style="width:38%%">错误做法</th>'
                    '<th>为什么错 / 正确做法</th></tr>\n%s\n  </table>' % "\n".join(rows))

    # 速查表
    # 速查表：@quick 只覆盖它点名的题号，其余按 @ans/@idea 自动补齐，绝不丢行
    ov = {}
    for it in blocks(items, "quick"):
        for ln in it[2]:
            if ln.strip():
                q_no, q_ans, q_key = split_pipe(ln, 3)
                ov[q_no] = (q_ans, q_key)
    rows = []
    for q, no in zip(qs, nos):
        ans = [l.strip() for l in q["ans"] if l.strip()]
        key = ""
        for ln in q["idea"]:
            if ln.strip():
                key = split_pipe(ln, 2)[0]
                break
        a_val, k_val = ov.get(no, ("；".join(ans) if ans else "—", key))
        rows.append('    <tr><td class="c">%s</td><td><b>%s</b></td><td>%s</td></tr>'
                    % (safe(no), safe(a_val), safe(k_val)))
    quick_html = ('  <h2>四、答案速查表</h2>\n'
                  '  <table class="kptable">\n'
                  '    <tr><th style="width:10%%">题号</th><th style="width:34%%">答案</th>'
                  '<th>关键步骤</th></tr>\n%s\n  </table>' % "\n".join(rows))

    body = """<div class="page">
  <h1>%s</h1>
  <div class="meta">%s</div>

  <h2>一、题目原文</h2>
  <div class="stem">
%s
  </div>

  <div class="note">
%s
  </div>
</div>

<div class="page">
%s
</div>

<div class="page">
%s
%s
%s
</div>""" % (safe(title), safe(meta), stem_html, note_html, cards,
             alt_html or "  <h2>二、别解与验算</h2>", err_html, quick_html)
    return body


# ---------------------------------------------------------------- 考点渲染

KP_CSS = """
/* ---- 考点知识点专用（build.py kp 模式自动注入） ---- */
.kp-item{ border:1px solid var(--line); margin:16px 0 10px; background:#fff; break-inside:avoid; }
.kp-hd{ display:flex; align-items:baseline; gap:10px; flex-wrap:wrap;
        background:var(--accent2); border-bottom:1px solid var(--line); padding:7px 13px; }
.kp-no{ color:var(--accent); font-size:15.5px; font-weight:700; letter-spacing:.4px; }
.kp-tag{ font-size:13px; color:#444; }
.kp-lv{ margin-left:auto; font-size:12px; color:var(--sub); }
.kp-body{ padding:9px 15px 10px; }
.kp-row{ margin:7px 0; }
.kp-k{ font-weight:700; color:var(--accent); margin-right:6px; }
.kp-eg{ margin:9px 0 13px; }
.kp-eg-h{ font-weight:700; color:#333; margin-bottom:3px; }
.kp-ans{ display:inline-block; border:1.5px solid var(--accent); color:var(--accent);
         font-weight:700; padding:2px 12px; border-radius:3px; background:#fff; text-indent:0; }
.kp-q{ border-top:1px dashed var(--line); background:#fbfbf9; padding:9px 15px 12px; }
.kp-q-t{ font-size:13px; font-weight:700; color:var(--sub); letter-spacing:1px; margin-bottom:4px; }
.kp-tip{ background:var(--warnbg); border-left:3px solid #d9b44a; padding:7px 11px;
         margin:9px 0 4px; font-size:14px; }
.bars{ margin:12px 0 6px; }
.bar{ display:flex; align-items:center; gap:9px; margin:6px 0; font-size:13.5px; }
.bar > span:first-child{ width:170px; flex:none; color:var(--sub); }
.bar > i{ display:block; height:15px; background:var(--accent); opacity:.72; border-radius:2px; }
.bar > b{ font-size:12.5px; color:var(--accent); font-weight:700; }
"""


def build_kp(items, tpl):
    tb = blocks(items, "title")
    title = (tb[0][1] if tb and tb[0][1] else
             " ".join(x.strip() for x in (tb[0][2] if tb else []) if x.strip())) or "考点知识点"
    mb = blocks(items, "meta")
    meta = (mb[0][1] if mb and mb[0][1] else
            " ".join(x.strip() for x in (mb[0][2] if mb else []) if x.strip()))

    sections = []      # [(title, [kp...])]
    cur_sec = {"title": "一、考点与知识点", "items": []}
    sections.append(cur_sec)
    cur_kp = None

    for it in items:
        name, arg, lines = it
        if name == "sect":
            cur_kp = None
            if cur_sec["items"]:
                cur_sec = {"title": arg or "继续", "items": []}
                sections.append(cur_sec)
            else:
                cur_sec["title"] = arg or cur_sec["title"]
            continue
        if name == "kp":
            no, tag, lv = split_pipe(arg, 3)
            cur_kp = {"no": no, "tag": tag, "lv": lv or "★★", "rows": [],
                      "tip": [], "eg": []}
            cur_sec["items"].append(cur_kp)
            continue
        if cur_kp is None:
            continue
        if name == "k":
            k, v = split_pipe(arg, 2)
            cur_kp["rows"].append((k, " ".join(x.strip() for x in lines) if lines else v))
            if lines:
                cur_kp["rows"][-1] = (k, " ".join(x.strip() for x in lines))
        elif name == "tip":
            cur_kp["tip"].append(" ".join([arg] + [x.strip() for x in lines]).strip())
        elif name in ("eg", "q"):
            cur_kp["eg"].append({"head": arg, "body": [], "ans": [], "idea": [], "kind": name})
        elif name in ("eans", "qans", "ans"):
            if cur_kp["eg"]:
                cur_kp["eg"][-1]["ans"].append(" ".join([arg] + [x.strip() for x in lines]).strip())
        elif name == "step":
            if cur_kp["eg"]:
                cur_kp["eg"][-1]["body"].extend(([arg] if arg else []) + lines)
        elif name == "idea":
            if cur_kp["eg"]:
                cur_kp["eg"][-1]["idea"].extend(([arg] if arg else []) + lines)

    # 逐块渲染
    out_sections = []
    for si, sec in enumerate(sections):
        if not sec["items"]:
            continue
        parts = ['<div class="page">', '  <h2>%s</h2>' % safe(sec["title"])]
        for ki, kp in enumerate(sec["items"], 1):
            body = []
            for k, v in kp["rows"]:
                body.append('      <p class="kp-row"><span class="kp-k">%s</span>%s</p>'
                            % (safe(k), safe(v)))
            for tip in kp["tip"]:
                body.append('      <p class="kp-tip"><b>易错点：</b>%s</p>' % safe(tip))
            if kp["eg"]:
                eq = ['      <div class="kp-q">', '        <div class="kp-q-t">配套题</div>']
                for eg in kp["eg"]:
                    eq.append('        <div class="kp-eg">')
                    eq.append('          <div class="kp-eg-h">%s</div>' % safe(eg["head"]))
                    for ln in eg.get("idea", []):
                        if ln.strip():
                            eq.append('          <p class="pf"><b>思路：</b>%s</p>'
                                      % auto_rs(ln.strip()))
                    nb = 0
                    for ln in eg["body"]:
                        if not ln.strip():
                            continue
                        pre = '<b>步骤：</b>' if nb == 0 else ""
                        nb += 1
                        eq.append('          <p class="pf">%s%s</p>' % (pre, auto_rs(ln.strip())))
                    for a in eg["ans"]:
                        eq.append('          <p class="pf"><b>答案：</b>'
                                  '<span class="kp-ans">%s</span></p>' % safe(a))
                    eq.append('        </div>')
                eq.append('      </div>')
                body.append("\n".join(eq))
            parts.append(
                '  <div class="kp-item" id="k%d">\n'
                '    <div class="kp-hd">\n'
                '      <span class="kp-no">%s</span>\n'
                '      <span class="kp-tag">考点：%s</span>\n'
                '      <span class="kp-lv">难度 %s</span>\n'
                '    </div>\n'
                '    <div class="kp-body">\n%s\n    </div>\n'
                '  </div>' % (ki, safe(kp["no"] or ("第 %d 题" % ki)),
                              safe(kp["tag"]), safe(kp["lv"]), "\n".join(body)))
        # 本节小结
        rows = []
        for kp in sec["items"]:
            first = kp["rows"][0][1] if kp["rows"] else "—"
            rows.append('    <tr><td class="c">%s</td><td>%s</td><td>%s</td><td class="c">%s</td></tr>'
                        % (safe(kp["no"]), safe(kp["tag"]), safe(first[:60]), safe(kp["lv"])))
        parts.append('  <h3>本节考点小结</h3>\n  <table class="kptable">\n'
                     '    <tr><th style="width:10%%">题号</th><th style="width:30%%">考点</th>'
                     '<th>知识点要点</th><th style="width:12%%">难度</th></tr>\n%s\n  </table>'
                     % "\n".join(rows))
        parts.append('</div>')
        out_sections.append("\n".join(parts))

    # 全卷分布表 + 条形图
    all_kp = [kp for sec in sections for kp in sec["items"]]
    rows, counts = [], {}
    for kp in all_kp:
        rows.append('    <tr><td class="c">%s</td><td>%s</td><td>%s</td><td class="c">%s</td></tr>'
                    % (safe(kp["no"]), safe(kp["tag"]), safe(kp["rows"][0][1][:50] if kp["rows"] else "—"),
                       safe(kp["lv"])))
        counts[kp["tag"]] = counts.get(kp["tag"], 0) + 1
    mx = max(counts.values()) if counts else 1
    bars = "\n".join(
        '  <div class="bar"><span>%s</span><i style="width:%d%%"></i><b>%d</b></div>'
        % (safe(k), int(60 * v / mx), v) for k, v in sorted(counts.items(), key=lambda x: -x[1]))
    dist = ('<div class="page">\n  <h2>全卷考点分布</h2>\n'
            '  <div class="bars">\n%s\n  </div>\n'
            '  <table class="kptable">\n'
            '    <tr><th style="width:10%%">题号</th><th style="width:42%%">考点</th>'
            '<th>知识点/章节</th><th style="width:12%%">难度</th></tr>\n%s\n  </table>\n</div>'
            % (bars, "\n".join(rows)))

    body = """<div class="page">
  <h1>%s</h1>
  <div class="meta">%s</div>
  <div class="note">按题号与全解一一对应。<b>考点</b>是这道题在考什么，<b>知识点</b>是要能背出来的那句话，
  <b>易错点</b>是踩过坑的地方；每条知识点下面配 2–3 道配套题，先自己做再看答案。</div>
</div>

%s

%s""" % (safe(title), safe(meta), "\n\n".join(out_sections), dist)
    return body


# ---------------------------------------------------------------- 套模板


def splice(tpl_text, body, kp_mode=False):
    """把生成的 body 塞进模板：<body> 之后到折叠控制条之前。"""
    i = tpl_text.index("<body>") + len("<body>")
    j = tpl_text.index('<div class="fd-ctl"')
    head, tail = tpl_text[:i], tpl_text[j:]
    if kp_mode:
        head = head.replace("</style>", KP_CSS + "</style>")
        # 考点页没有折叠，去掉三连按钮
        k2 = tail.index("</div>", tail.index('<div class="fd-ctl"')) + len("</div>")
        tail = tail[k2:]
    return head + "\n\n" + body + "\n\n" + tail


SAMPLE_SOL = """%title 数学《思维拓展五》全解
%meta 题型：尺规作图 · 等腰分类 · 互余｜单位：度、cm

@stem
如图，CD 是直角三角形 ABC 斜边 AB 边上的高。
（1）已知等腰 △ABP 的顶点 P 在直线 AC 上，请用圆规和直尺作出满足题意的 △ABP。
（2）若 ∠ABC = 60°，求与 ∠ABC 互余的角。

@q 1 | 尺规作图 ＋ 等腰三角形分类
@aux
作 BD⊥AC，垂足为 D（从 B 向 AC 引垂线）
作 AB 的垂直平分线，交 AC 于 P₁（到 A、B 距离相等的点）
以 A 为圆心 AB 为半径画弧，交 AC 于 P₂（PA = AB）
~ 为什么要三条：等腰没说哪两条边相等，只能按底边分类，一类对应一条轨迹
@idea
把"等腰"翻成三种边相等 | 先定 P 的轨迹，再与 AC 求交
只留不共线的交点 | P 与 A、B 重合时要舍去
@ans
3 个点，图略
@sol
## 第一步　三种情形拆开
△ABP 为等腰，但题目没说哪两条边相等，必须按底边分三类（分类讨论）
① PA = PB：P 在 AB 的垂直平分线上（垂直平分线的性质）
② PA = AB：P 在以 A 为圆心、AB 为半径的圆上（圆的定义）
③ PB = AB：P 在以 B 为圆心、AB 为半径的圆上（圆的定义）
## 第二步　把轨迹落到直线 AC 上
每条轨迹与直线 AC 的交点都可能是所求的 P（交点的意义）
垂直平分线与 AC 交出 1 个点；两个圆与 AC 各交出 2 个点（圆与直线最多 2 个交点）
## 第三步　剔除退化情形
若交点与 A 或 B 重合，三点共线，不能构成三角形（三角形的定义）
把这类点删掉，剩下的才是答案（去重）
@cap
图 1　三条轨迹与直线 AC 的交点；虚线为垂直平分线

@err
只画一种情形的 P 就交卷 | 等腰分类题必须三类走完，缺一类就少解
圆与直线的两个交点只取一个 | 圆心到直线距离小于半径时必有两个交点

@alt
也可以先用尺规作 ∠A 的角平分线，再用对称性找 P₂ 关于 AP₁ 的对称点（对称的性质）
"""

SAMPLE_KP = """%title 数学《思维拓展五》考点知识点
%meta 共 2 题｜考点 3 个｜难度 ★★–★★★

@sect 一、第 1 题：尺规作图 ＋ 等腰分类
@kp 第 1 题 | 尺规作等腰三角形（顶点限定在一条直线上） | ★★★
@k 知识点① | "等腰"没说哪两条边相等时，要按三种情形分类：AB 作底、AB 作腰且 A 为顶角、AB 作腰且 B 为顶角。
@k 知识点② | 三种情形各对应一条轨迹：PA = PB ⇔ P 在 AB 的垂直平分线上；PA = AB ⇔ P 在以 A 为圆心、AB 为半径的圆上。
@tip 只画一种情形的 P 就交卷；圆与直线通常有 0、1、2 个交点，要按圆心到直线的距离判断。
@eg 例题 1　A（0，0）、B（6，0），直线 l：y = 4。在 l 上找点 P 使 △ABP 为等腰，这样的 P 有几个？
@step ① PA = PB：P 在 AB 的垂直平分线 x = 3 上，与 y = 4 交于（3，4），1 个（垂直平分线的意义）
@step ② PA = AB = 6：x² + 16 = 36，x = ±2√5，2 个（圆的定义、勾股定理）
@step 五个点互不重合，也不与 A、B 重合（去重）
@eans 5 个
@q 练习 1　A（0，0）、B（6，0），直线 l：y = 8。使 △ABP 为等腰的点 P 有几个？
@qans 1 个 ——（3，8）（另两种情形的圆半径 6 够不到 y = 8）
"""


def main():
    ap = argparse.ArgumentParser(description="试卷全解 / 考点知识点 渲染器")
    ap.add_argument("mode", choices=["sol", "kp", "sample"])
    ap.add_argument("spec", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--template", default=TPL)
    a = ap.parse_args()

    if a.mode == "sample":
        what = a.spec or "sol"
        print(SAMPLE_KP if what == "kp" else SAMPLE_SOL)
        return

    if not a.spec or not a.out:
        die("用法：build.py sol spec.mk -o 输出.html")

    tpl = open(a.template, encoding="utf-8").read()
    text = open(a.spec, encoding="utf-8").read()
    items = parse_spec(text)

    body = build_kp(items, tpl) if a.mode == "kp" else build_sol(items, tpl)
    html = splice(tpl, body, kp_mode=(a.mode == "kp"))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)

    n = len(blocks(items, "q")) if a.mode == "sol" else len(blocks(items, "kp"))
    print("已生成 %s（%d %s，%.0f KB）" % (
        a.out, n, "题" if a.mode == "sol" else "个考点块",
        len(html.encode("utf-8")) / 1024))


if __name__ == "__main__":
    main()
