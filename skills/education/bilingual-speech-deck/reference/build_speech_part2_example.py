#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speech script, second half only (SLIDE 10–14), continuous flow, bilingual.

Same typography as the full script:
  body 20 pt (EN) / 18 pt (ZH), headings 24 pt, labels 12 pt, no superscripts.
Difference: no page break per slide — sections run on, separated by a hairline.
"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import content as C

INK = RGBColor(0x1C, 0x1A, 0x17)
SOFT = RGBColor(0x3F, 0x39, 0x33)
MUTED = RGBColor(0x7D, 0x76, 0x6C)
BRICK = RGBColor(0x9C, 0x3D, 0x2E)
FAINT = RGBColor(0xB5, 0xAC, 0x9F)
LINE = "DED7CB"

CN = "PingFang SC"
EN = "Helvetica Neue"

S_H1 = 16
S_BODY_EN = 12
S_BODY_ZH = 12
S_LABEL = 12

FIRST, LAST = 10, 14
META = {
    10: ("为什么", "四条原因一口气数完，再回看中心那个圆。"),
    11: ("谁受益", "语速稍快，像在清点；每条稍作停顿。"),
    12: ("代价", "全篇最重的一页：放慢、压低，不要笑。"),
    13: ("我学到什么", "三条之间各停两秒，让观众跟上。"),
    14: ("收尾", "说完最后一句就停住，不要补话，等掌声。"),
}


def set_font(run, size=18, bold=False, color=INK, italic=False, cn=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = EN
    rPr = run._element.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.append(rf)
    rf.set(qn("w:ascii"), EN)
    rf.set(qn("w:hAnsi"), EN)
    rf.set(qn("w:eastAsia"), CN)


def spacing(p, before=0, after=0, line=1.5):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line


def shade(p, fill="F7F2EC"):
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr.append(shd)


def left_border(p, color=LINE, size=18):
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    el = OxmlElement("w:left")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), "10")
    el.set(qn("w:color"), color)
    pBdr.append(el)
    pPr.append(pBdr)


def bottom_rule(p, color=LINE, size=6, space="6"):
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    el = OxmlElement("w:bottom")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), space)
    el.set(qn("w:color"), color)
    pBdr.append(el)
    pPr.append(pBdr)


def para(doc, text="", size=S_BODY_ZH, bold=False, color=INK, italic=False,
         before=0, after=0, line=1.5, align=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    spacing(p, before, after, line)
    if text:
        r = p.add_run(text)
        set_font(r, size, bold, color, italic)
    return p


doc = Document()
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.left_margin = Cm(2.0)
sec.right_margin = Cm(2.0)
sec.top_margin = Cm(2.0)
sec.bottom_margin = Cm(1.9)

# footer: page number
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = fp.add_run("武康路 · 演讲稿 后半段（SLIDE 10–14）     ")
set_font(r, S_LABEL, False, MUTED, cn=True)
fld = OxmlElement("w:fldSimple")
fld.set(qn("w:instr"), " PAGE ")
run_el = OxmlElement("w:r")
rPr = OxmlElement("w:rPr")
sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(S_LABEL * 2)); rPr.append(sz)
col = OxmlElement("w:color"); col.set(qn("w:val"), "7D766C"); rPr.append(col)
run_el.append(rPr)
t = OxmlElement("w:t"); t.text = "1"; run_el.append(t)
fld.append(run_el)
fp._p.append(fld)

style = doc.styles["Normal"]
style.font.name = EN
style.font.size = Pt(S_BODY_ZH)
style.element.rPr.rFonts.set(qn("w:eastAsia"), CN)

# ── head ─────────────────────────────────────────────────────
para(doc, "SPEECH SCRIPT  ·  后半段  ·  中英对照", S_LABEL, True, BRICK)
para(doc, "从代价到收尾", 22, True, INK, before=10)
para(doc, "Wukang Road: Then and Now  ·  SLIDE 10–14", S_LABEL, False, MUTED, before=8)
p = para(doc, "", 8, before=10)
bottom_rule(p, color="9C3D2E", size=10)

para(doc, "5 页幻灯片 · 4:00–5:50 · 约 2 分钟 · 连续排版，不按页分屏", S_LABEL, False, MUTED,
     before=10)

# ── sections, flowing ────────────────────────────────────────
for s in C.SLIDES:
    if s["n"] < FIRST:
        continue
    cn_title, tip = META[s["n"]]

    # divider + slide tag on one line
    head = doc.add_paragraph()
    spacing(head, 26 if s["n"] > FIRST else 22, 0, 1.0)
    r = head.add_run(f"SLIDE {s['n']:02d}   ")
    set_font(r, S_LABEL, True, BRICK)
    r = head.add_run(f"/ {s['t']}")
    set_font(r, S_LABEL, False, MUTED)
    bottom_rule(head, color="E7E0D4", size=4, space="4")

    p = doc.add_paragraph()
    spacing(p, 8, 2, 1.1)
    r = p.add_run(cn_title)
    set_font(r, S_H1, True, INK, cn=True)

    p = doc.add_paragraph()
    spacing(p, 0, 4, 1.3)
    r = p.add_run("屏幕关键词   ")
    set_font(r, S_LABEL, True, MUTED, cn=True)
    r = p.add_run(" · ".join(s["cue"]))
    set_font(r, S_LABEL, False, BRICK, cn=True)

    para(doc, s["en"], S_BODY_EN, False, INK, before=10, line=1.45)

    p = para(doc, s["zh"], S_BODY_ZH, False, SOFT, before=12, line=1.5)
    shade(p, "F7F2EC")
    left_border(p, "D9B5A6", 18)
    p.paragraph_format.left_indent = Cm(0.40)
    p.paragraph_format.right_indent = Cm(0.20)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)

    p = doc.add_paragraph()
    spacing(p, 12, 0, 1.4)
    r = p.add_run("提示   ")
    set_font(r, S_LABEL, True, MUTED, cn=True)
    r = p.add_run(tip)
    set_font(r, S_LABEL, False, MUTED, cn=True)

# ── tail note ────────────────────────────────────────────────
p = doc.add_paragraph()
spacing(p, 30, 0, 1.4)
r = p.add_run("接续自《武康路 · 演讲稿（中英对照）》第 10 页；页码、SLIDE 编号与 PPT 一致。")
set_font(r, S_LABEL, False, FAINT, cn=True)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out",
                   "武康路_演讲稿_第10页起_中英对照.docx")
doc.save(out)
print("saved", out, os.path.getsize(out) // 1024, "KB")
