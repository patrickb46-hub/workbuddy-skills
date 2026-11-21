#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分层出题生成器（exam-paper-solutions · 出题分支 B 的双卷版）

用法：
    python build_layered_quiz.py <papers.json> [--html-only | --docx-only]

输入 JSON 约定见 assets/quiz-bank-template.json。
产物：
    · 每份卷一个自包含 HTML（沿用 quiz-template.html 的 CSS，左侧目录 + 题面 + 折叠答案）
    · 一份合并 DOCX（仅题目，A4，按卷分页，可直接打印）

依赖：python-docx；SVG→PNG 用本机 Chrome / Chromium（没有 Chrome 时可用预先备好的同名 PNG）。
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


# ---------------------------------------------------------------- 通用
def esc(text: str) -> str:
    """转义 HTML 并把换行变成 <br>。"""
    return html.escape(str(text), quote=False).replace("\n", "<br>")


def read_svg(path: Path) -> str:
    svg = path.read_text(encoding="utf-8").strip()
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg).strip()
    if "style=" not in svg.split(">", 1)[0]:
        svg = svg.replace("<svg ", '<svg style="max-width:100%;height:auto" ', 1)
    return svg


def svg_size(path: Path):
    head = path.read_text(encoding="utf-8")[:600]
    w = re.search(r'width="([\d.]+)"', head)
    h = re.search(r'height="([\d.]+)"', head)
    return (int(float(w.group(1))), int(float(h.group(1)))) if w and h else (600, 400)


def ensure_png(svg_path: Path) -> Path:
    """把 SVG 渲染成 2x PNG；已有更新的 PNG 就直接用。"""
    png = svg_path.with_suffix(".png")
    if png.exists() and png.stat().st_mtime >= svg_path.stat().st_mtime:
        return png
    chrome = next((c for c in CHROME_CANDIDATES if os.path.exists(c)), None)
    if not chrome:
        if png.exists():
            return png
        raise SystemExit(f"找不到 Chrome，无法渲染 {svg_path.name}；请先手动导出同名 PNG。")
    w, h = svg_size(svg_path)
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         "--force-device-scale-factor=2", f"--window-size={w},{h}",
         f"--screenshot={png}", svg_path.resolve().as_uri()],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return png


# ---------------------------------------------------------------- HTML
def build_html(paper: dict, base: Path, template_css: str, outdir: Path) -> Path:
    questions = paper["questions"]
    total = len(questions)
    levels = paper.get("levels", [])
    coverage = paper.get("coverage", [])
    sections = paper["sections"]

    toc = ['<div class="h">目录</div>', '<a href="#s0">00　考点分布与用法</a>']
    for sec in sections:
        toc.append(f'<a href="#{sec["id"]}">{sec["num"]}　{sec["title"]}</a>')

    body = []
    body.append(f'<h2 id="s0"><span class="num">00</span>考点分布与用法</h2>')
    body.append(f'<p class="lead">{esc(paper["lead"])}</p>')
    body.append(f'<div class="note">{esc(paper["note"])}</div>')

    if levels:
        rows = "".join(
            f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td><td>{esc(d)}</td></tr>"
            for a, b, c, d in levels
        )
        body.append(
            '<h3>难度与分值</h3><div class="tw"><table>'
            "<thead><tr><th>难度</th><th>题号</th><th>每题分值</th><th>小计</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )

    if coverage:
        rows = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in coverage)
        body.append(
            '<h3>考点 × 题号</h3><div class="tw"><table>'
            "<thead><tr><th>覆盖的知识点</th><th>对应题号</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )

    for si, sec in enumerate(sections):
        body.append(f'<h2 id="{sec["id"]}"><span class="num">{sec["num"]}</span>{esc(sec["title"])}</h2>')
        if sec.get("note"):
            body.append(f'<div class="note">{esc(sec["note"])}</div>')
        start = sec["from"]
        later = [s["from"] for s in sections[si + 1:]]
        end = min(later) if later else 10 ** 9
        for q in questions:
            if not (start <= q["n"] < end):
                continue
            block = [
                f'<div class="q"><span class="idx">{q["n"]}.</span>'
                f'【{esc(q["label"])}】{esc(q["stem"])}</div>'
            ]
            if q.get("fig"):
                svg = read_svg(base / "figs" / f'{q["fig"]}.svg')
                block.append(f'<div style="margin:16px 0 4px;text-align:center">{svg}</div>')
            block.append(
                f'<div class="ans">\n  <input type="checkbox" id="an{q["n"]}">\n'
                f'  <label for="an{q["n"]}">答案与解析</label>\n  <div class="ans-body">\n'
                f'    <span class="final">{esc(q["answer"])}</span>\n'
                f'    <p>{esc(q["explain"])}</p>\n  </div>\n</div>'
            )
            if q.get("fig"):
                body.append(
                    '<div class="qblock" style="break-inside:avoid;page-break-inside:avoid">'
                    + "".join(block)
                    + "</div>"
                )
            else:
                body.extend(block)

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(paper['h1'])}</title>
<style>
{template_css}
</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <div class="kicker">{esc(paper['kicker'])}</div>
  <h1>{esc(paper['h1'])}</h1>
  <div class="sub">{esc(paper['sub'])}</div>
  <div class="src">{esc(paper['source'])}</div>
</header>

<nav class="toc">
  {'  '.join(toc)}
</nav>

<main>
{chr(10).join(body)}
</main>

<footer class="end">共 {total} 题 ｜ 满分 100 分 ｜ 建议 60 分钟。难度按题量 10 : 8 : 2 分布。本卷为自编题，非原卷；答案与解析在每题下方，点开即看。</footer>
</div>

<button class="expand" id="expandAll">展开全部答案</button>
<script>
(function(){{var b=document.getElementById('expandAll');if(!b)return;
b.addEventListener('click',function(){{var xs=document.querySelectorAll('.ans > input');
var closed=false;xs.forEach(function(i){{if(!i.checked)closed=true;}});
xs.forEach(function(i){{i.checked=closed;}});
b.textContent=closed?'收起全部答案':'展开全部答案';}});}})();
</script>
</body>
</html>
"""
    out = outdir / paper["html_name"]
    out.write_text(doc, encoding="utf-8")
    return out


# ---------------------------------------------------------------- DOCX
def set_run_font(run, size=10.5, bold=False, color=None, east="宋体"):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), east)


def add_bottom_border(paragraph, sz=6, color="1A1A1A"):
    ppr = paragraph._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(sz))
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), color)
    pbdr.append(bottom)
    # 按 OOXML 顺序插到 spacing / ind / jc 之前，避免 Word 报“需要修复”
    ppr.insert_element_before(
        pbdr,
        "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
        "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
        "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
        "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
        "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
        "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
    )


def add_page_field(paragraph):
    run = paragraph.add_run("第 ")
    set_run_font(run, 9, color=(0x6B, 0x6B, 0x72))
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "1"
    r.append(t)
    fld.append(r)
    paragraph._p.append(fld)
    run2 = paragraph.add_run(" 页")
    set_run_font(run2, 9, color=(0x6B, 0x6B, 0x72))


def build_docx(papers, outdir: Path, name: str, base: Path) -> Path:
    doc = Document()

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(1.9)
    sec.left_margin = sec.right_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.paragraph_format.line_spacing = 1.4
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    add_page_field(sec.footer.paragraphs[0])
    sec.footer.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    for idx, paper in enumerate(papers):
        if idx:
            doc.add_page_break()

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        set_run_font(p.add_run(paper["docx_title"]), 18, bold=True)

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(10)
        set_run_font(p.add_run(paper["sub"]), 9, color=(0x6B, 0x6B, 0x72))

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        set_run_font(p.add_run("姓名：＿＿＿＿＿＿＿＿　　班级：＿＿＿＿＿＿　　得分：＿＿＿＿＿＿"), 10.5)

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(4)
        set_run_font(p.add_run("本卷只含题目；答案与解析见同目录的 HTML 试卷。"), 9, color=(0x6B, 0x6B, 0x72))
        add_bottom_border(p)

        for sec_def in paper["sections"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.keep_with_next = True
            set_run_font(p.add_run(sec_def["title"]), 12, bold=True)

            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_with_next = True
            set_run_font(p.add_run(sec_def["note"]), 9, color=(0x6B, 0x6B, 0x72))

            start = sec_def["from"]
            later = [s["from"] for s in paper["sections"] if s["from"] > start]
            end = min(later) if later else 10 ** 9

            for q in paper["questions"]:
                if not (start <= q["n"] < end):
                    continue
                lines = str(q["stem"]).split("\n")
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.8)
                p.paragraph_format.first_line_indent = Cm(-0.8)
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.line_spacing = 1.45
                p.paragraph_format.tab_stops.add_tab_stop(Cm(0.8))
                p.paragraph_format.keep_with_next = True
                set_run_font(p.add_run(f'{q["n"]}．\t【{q["label"]}】'), 10.5, bold=True)
                set_run_font(p.add_run(lines[0]), 10.5)

                for line in lines[1:]:
                    p2 = doc.add_paragraph()
                    p2.paragraph_format.left_indent = Cm(0.8)
                    p2.paragraph_format.line_spacing = 1.45
                    p2.paragraph_format.keep_with_next = True
                    set_run_font(p2.add_run(line), 10.5)

                if q.get("fig"):
                    png = ensure_png(base / "figs" / f'{q["fig"]}.svg')
                    pf = doc.add_paragraph()
                    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    pf.paragraph_format.space_before = Pt(4)
                    pf.paragraph_format.space_after = Pt(2)
                    pf.paragraph_format.keep_with_next = True
                    pf.add_run().add_picture(str(png), width=Cm(q.get("fig_w", 6.6)))

                space = int(q.get("space", 3))
                for i in range(space):
                    blank = doc.add_paragraph()
                    blank.paragraph_format.line_spacing = 1.45
                    blank.paragraph_format.keep_with_next = i < space - 1
                    set_run_font(blank.add_run(""), 10.5)

    out = outdir / name
    doc.save(out)
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--docx-only", action="store_true")
    args = ap.parse_args()

    cfg_path = Path(args.json).resolve()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    base = cfg_path.parent
    outdir = Path(cfg.get("outdir", base)).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    template = Path(cfg["template"]).read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", template, re.S).group(1).strip()

    made = []
    if not args.docx_only:
        for paper in cfg["papers"]:
            made.append(build_html(paper, base, css, outdir))
    if not args.html_only:
        made.append(build_docx(cfg["papers"], outdir, cfg["docx_name"], base))

    for m in made:
        print("wrote", m)


if __name__ == "__main__":
    main()
