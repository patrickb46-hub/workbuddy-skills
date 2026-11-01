#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把结构化笔记 JSON 渲染成一节课的 HTML（样式取自 assets/template.html）。

用法：
    python3 render_notes.py --data notes.json --out "课堂整理_2026-10-21_第1节.html"
    python3 render_notes.py --data notes.json --out out.html --template 自定义模板.html

输入 JSON：
{
  "date": "2026-10-21",
  "lesson": "第 1 节",
  "subject": "语文",
  "teacher": "黄老师",
  "title": "《与朱元思书》：字词落实与写景手法",
  "summary": "一句话说明这节课重点",
  "examples": [                       // 老师讲解的题
    {"no":"例 1","title":"翻译：风烟俱净，天山共色。",
     "question":"题干原文（可省，与 title 重复时省略）",
     "answer":"解析正文，多段用 \\n 分隔",
     "tags":["文言翻译","实词"],"image":"01_例题.png"}
  ],
  "exercises": [ ... 同 examples，answer 写答案 ... ],
  "points": [ {"title":"通假字","text":"蝉则千转不穷……"} ],
  "methods": [ {"title":"文言翻译四步","steps":["① 留：…","② 删：…"],
                "image":"05_答题方法.png"} ],
  "images": ["01_例题.png","02_例题.png"]      // 原始截图区；省略则自动收集所有引用过的图
}

所有字段除 date/title 外都可省；空板块自动隐藏，目录同步收缩。
"""
import argparse
import html as H
import json
import os
import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parent.parent
DEFAULT_TPL = SK / "assets" / "template.html"


def esc(s):
    return H.escape(str(s or "")).strip()


def nl2br(s):
    """保留换行；已经带 <br> 的原样保留。"""
    raw = str(s or "").strip()
    if "<br" in raw:
        return raw
    return esc(raw).replace("\r\n", "\n").replace("\n", "<br>")


def fig(name, cap=None, big=False):
    if not name:
        return ""
    n = esc(name)
    caption = esc(cap) if cap is not None else ("原图 " + n)
    cls = ' class="big"' if big else ""
    return ('<figure%s><img src="%s" alt="%s" loading="lazy" '
            'onclick="window.open(this.src,\'_blank\')">'
            '<figcaption>%s（点击看大图）</figcaption></figure>' % (cls, n, n, caption))


def build(data, css):
    examples = data.get("examples") or []
    exercises = data.get("exercises") or []
    points = data.get("points") or []
    methods = data.get("methods") or []

    used = []
    for it in examples + exercises + methods:
        if it.get("image"):
            used.append(it["image"])
    images = data.get("images") or used

    def card(it, ans_label):
        no = esc(it.get("no") or "")
        title = esc(it.get("title") or "")
        q = it.get("question") or ""
        title_html = ('<span class="no">%s</span>' % no if no else "") + title
        body = []
        if q and esc(q) != title:
            body.append('<div class="q">%s</div>' % nl2br(q))
        if it.get("answer"):
            body.append('<div class="a"><b>%s：</b><br>%s</div>'
                        % (ans_label, nl2br(it["answer"])))
        if it.get("tags"):
            body.append('<div class="tagset">%s</div>'
                        % "".join('<span class="tag">%s</span>' % esc(t) for t in it["tags"]))
        body.append(fig(it.get("image"), "原图 " + str(it.get("image"))))
        return ('<div class="card"><h4>%s</h4>\n%s\n</div>'
                % (title_html, "\n".join(x for x in body if x)))

    parts, toc = [], []

    if examples:
        toc.append(("ex", "例题", len(examples)))
        parts.append('<h3 class="sec" id="ex">例题<span class="n">%d</span></h3>\n%s'
                     % (len(examples), "\n".join(card(x, "解析") for x in examples)))
    if exercises:
        toc.append(("exe", "习题", len(exercises)))
        parts.append('<h3 class="sec" id="exe">习题<span class="n">%d</span></h3>\n%s'
                     % (len(exercises), "\n".join(card(x, "答案") for x in exercises)))
    if points:
        toc.append(("pt", "知识点", len(points)))
        lis = "".join('<li><b>%s</b>%s</li>' % (
            esc(p.get("title", "")) + ("：" if p.get("title") else ""), nl2br(p.get("text", "")))
            for p in points)
        parts.append('<h3 class="sec" id="pt">知识点<span class="n">%d</span></h3>\n'
                     '<div class="card"><ul class="pt">%s</ul></div>' % (len(points), lis))
    if methods:
        toc.append(("mt", "答题方法", len(methods)))
        blocks = []
        for m in methods:
            steps = m.get("steps") or []
            body = "<br>".join(nl2br(s) if "<br" not in str(s) else str(s) for s in steps) \
                if steps else nl2br(m.get("body", ""))
            blocks.append('<div class="method"><h5>%s</h5><p>%s</p>%s</div>'
                          % (esc(m.get("title", "方法")), body,
                             fig(m.get("image"), "原图 " + str(m.get("image")))
                             if m.get("image") else ""))
        parts.append('<h3 class="sec" id="mt">答题方法<span class="n">%d</span></h3>\n'
                     '<div class="card">%s</div>' % (len(methods), "\n".join(blocks)))

    # 原始截图：只补没被正文引用的图，避免同一张出现两次
    extra = [x for x in images if x not in used]
    if extra:
        toc.append(("raw", "原始截图", len(extra)))
        raw_html = "\n".join(fig(x, x) for x in extra)
        parts.append('<h3 class="sec" id="raw">原始截图<span class="n">%d</span></h3>\n'
                     '<div class="card">%s</div>' % (len(extra), raw_html))

    toc_html = "".join('<a href="#%s">%s<em>%d</em></a>' % (i, n, c) for i, n, c in toc)

    chips = []
    for label, arr in (("例题", examples), ("习题", exercises),
                       ("知识点", points), ("答题方法", methods), ("原图", images)):
        if arr:
            chips.append('<span class="chip">%s %d</span>' % (label, len(arr)))

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>课堂整理 · __DATE__ · __LESSON__</title>
<style>__CSS__</style></head><body>
<header><div class="hin">
  <div><h1>课堂整理 · __DATE__ · __LESSON__</h1>
  <div class="sub">__SUBJECT__ · __TEACHER__ · 由课堂截图 OCR 整理</div></div>
  <div class="sp"></div>
  <button class="btn" onclick="document.body.classList.toggle('hideimg')">只看文字</button>
  <button class="btn" onclick="window.print()">打印 / 存 PDF</button>
</div></header>
<div class="wrap">
  <div class="hero">
    <h2>__TITLE__</h2>
    <p>__SUMMARY__</p>
    <div class="meta">__CHIPS__</div>
  </div>
  <div class="toc"><div class="t">本页目录</div>__TOC__</div>
  __PARTS__
  <footer>本页由 ClassIn 笔记助手 + classin-lesson-digest 技能生成 · 文字来自课堂截图 OCR，
  个别字句可能识别不准，以原图为准</footer>
</div></body></html>""".replace("__CSS__", css) \
        .replace("__DATE__", esc(data.get("date"))) \
        .replace("__LESSON__", esc(data.get("lesson", ""))) \
        .replace("__SUBJECT__", esc(data.get("subject", ""))) \
        .replace("__TEACHER__", esc(data.get("teacher", ""))) \
        .replace("__TITLE__", esc(data.get("title", "课堂整理"))) \
        .replace("__SUMMARY__", esc(data.get("summary", ""))) \
        .replace("__CHIPS__", "".join(chips)) \
        .replace("__TOC__", toc_html) \
        .replace("__PARTS__", "\n".join(parts))


EXTRA_CSS = """
h3.sec .n{font-size:11px;letter-spacing:0;color:#b5aea2;border:1px solid #e3ddd2;
  border-radius:999px;padding:0 7px;font-weight:400}
.toc a em{font-style:normal;color:#b5aea2;font-size:11px;margin-left:4px}
figure.big img{max-height:none}
body.hideimg figure{display:none}
"""


def main():
    ap = argparse.ArgumentParser(description="结构化笔记 JSON → HTML")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=str(DEFAULT_TPL))
    args = ap.parse_args()

    data = json.loads(Path(os.path.expanduser(args.data)).read_text("utf-8"))
    tpl = Path(os.path.expanduser(args.template)).read_text("utf-8")
    m = re.search(r"<style>(.*?)</style>", tpl, re.S)
    css = (m.group(1) if m else "") + EXTRA_CSS

    html = build(data, css)
    out = Path(os.path.expanduser(args.out))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    left = len(re.findall(r"__[A-Z][A-Z_]*__", html))
    print("已生成 → %s（%d 字节）%s" % (out, len(html),
          "" if not left else " ⚠️ 仍有 %d 个占位符" % left))
    return 0


if __name__ == "__main__":
    sys.exit(main())
