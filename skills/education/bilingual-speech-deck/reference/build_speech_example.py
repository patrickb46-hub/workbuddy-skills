#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the bilingual speech script (.docx), one page per slide.

Typography rules (user, 2026-10-28):
  · nothing smaller than 11 pt
  · body text >= 18 pt, 20 pt preferred
  · sources / labels / captions = 12 pt
  · headings >= 22 pt, 24 pt preferred
  · no meaningless superscript markers
"""
import os, math
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import content as C

INK = RGBColor(0x1C, 0x1A, 0x17)
SOFT = RGBColor(0x3F, 0x39, 0x33)
MUTED = RGBColor(0x7D, 0x76, 0x6C)
BRICK = RGBColor(0x9C, 0x3D, 0x2E)
LINE = "DED7CB"

CN = "PingFang SC"
EN = "Helvetica Neue"

# ── type scale ────────────────────────────────────────────────
S_COVER_TITLE = 22
S_H1 = 16          # section / page titles
S_BODY_EN = 12     # body text (user, 2026-10-28 #2)
S_BODY_EN_MIN = 12
S_BODY_ZH = 12
S_LABEL = 12       # sources, captions, running heads, tips, table
S_COVER_EN = 12
S_MINI = 12        # absolute floor used anywhere

META = [
    ("开场", "上台后站定三秒，环视一圈再开口；说出 Wukang Road 之后停一拍。"),
    ("这条街", "三个数字放慢，每个数字后面微停半秒。"),
    ("十五年前", "说到 spider web 时，抬手指屏幕左侧那张照片。"),
    ("现在", "先低声说 Now look at it，再扬起语调念数字。"),
    ("五个变化", "手依次点表格五行，只念关键词，不要念整句。"),
    ("天际线", "25 January 2019 是全篇最硬的日期，务必说清楚。"),
    ("建筑", "念到 never been repaired 之前停半拍。"),
    ("业态", "念 80% 时用手比一个比例。"),
    ("街道空间", "三个带加号的数字连读，形成节奏感。"),
    ("为什么", "四条原因一口气数完，再回看中心那个圆。"),
    ("谁受益", "语速稍快，像在清点；每条稍作停顿。"),
    ("代价", "全篇最重的一页：放慢、压低，不要笑。"),
    ("我学到什么", "三条之间各停两秒，让观众跟上。"),
    ("收尾", "说完最后一句就停住，不要补话，等掌声。"),
]


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


def bottom_rule(p, color=LINE, size=6):
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    el = OxmlElement("w:bottom")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), "6")
    el.set(qn("w:color"), color)
    pBdr.append(el)
    pPr.append(pBdr)


def para(doc, text="", size=18, bold=False, color=INK, italic=False, align=None,
         before=0, after=0, line=1.5):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    spacing(p, before, after, line)
    if text:
        r = p.add_run(text)
        set_font(r, size, bold, color, italic)
    return p


def page_break(doc):
    p = doc.add_paragraph()
    spacing(p, 0, 0, 1.0)
    p.add_run().add_break(WD_BREAK.PAGE)


# ── fit planner: choose 20 or 18 pt so one slide still fits one page ──
from PIL import ImageFont

WIDTH_PT = (21.0 - 2 * 2.0) / 2.54 * 72       # 17 cm
AVAIL_PT = (29.7 - 2.0 - 1.9) / 2.54 * 72     # usable height
_ENF = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 80, index=0)
EN_LEAD, ZH_LEAD = 1.45, 1.50


def _en_lines(text, size):
    f = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", int(size * 4), index=0)
    w = WIDTH_PT * 4
    n, cur = 1, ""
    for ch in text:
        t = cur + ch
        if f.getlength(t) <= w:
            cur = t
        else:
            n += 1
            cur = ch
    return n


def _zh_lines(text, size=18):
    em = sum(1.0 if ord(c) > 0x2E80 else 0.52 for c in text)
    return math.ceil(em * size / WIDTH_PT)


def plan(en, zh):
    """12 pt body: how many note lines still fit under it."""
    el = _en_lines(en, S_BODY_EN)
    zl = _zh_lines(zh, S_BODY_ZH)
    body_h = el * EN_LEAD * 1.2 * S_BODY_EN + zl * ZH_LEAD * 1.2 * S_BODY_ZH
    chrome = 30 + 12 + 46 + 34 + 20
    left = AVAIL_PT - 14 - body_h - chrome - 20
    notes = max(4, min(10, int(left / 26)))
    return S_BODY_EN, notes, (body_h + chrome + 20 + notes * 26) / AVAIL_PT


doc = Document()
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.left_margin = Cm(2.0)
sec.right_margin = Cm(2.0)
sec.top_margin = Cm(2.0)
sec.bottom_margin = Cm(1.9)

# footer: running title + page number (12 pt label)
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = fp.add_run("武康路 · 演讲稿（中英对照）     ")
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

# ───────────────────────── cover + how to use ─────────────────────────
para(doc, "SPEECH SCRIPT  ·  中英对照  ·  逐页对应", S_LABEL, True, BRICK)
p = para(doc, "武康路：十五年前与现在", S_COVER_TITLE, True, INK, before=28)
para(doc, "Wukang Road: Then and Now", S_COVER_EN, False, MUTED, before=10)
rule = para(doc, "", 8, after=0)
bottom_rule(rule, color="9C3D2E", size=10)

para(doc, "14 slides  ·  about 5 minutes  ·  one page per slide", S_LABEL, False, SOFT,
     before=14)
para(doc, "14 页幻灯片 · 约 5 分钟 · 每页一屏、每屏一页", S_LABEL, False, MUTED, before=4)

para(doc, "怎么用这份稿子", S_H1, True, INK, before=40)
idx = 1
for line in [
    "每一页对应 PPT 的一页，页眉编号一致。上台前只要记住每页的第一句和屏幕关键词。",
    "英文稿是你要说的话；中文是逐句译文，用来确认意思，不要照着念中文。",
    "忘词时先看页眉的 SLIDE 编号，直接翻到那一页。",
    "每页底部的「提示」写的是这一页的表演要点：哪里放慢、哪里停顿、哪里抬手。",
]:
    p = doc.add_paragraph()
    spacing(p, 10, 0, 1.55)
    p.paragraph_format.left_indent = Cm(0.85)
    p.paragraph_format.first_line_indent = Cm(-0.85)
    r = p.add_run(f"{idx:02d}   ")
    set_font(r, S_BODY_ZH, True, BRICK)
    r = p.add_run(line)
    set_font(r, S_BODY_ZH, False, SOFT, cn=True)
    idx += 1

para(doc, "Zhang San  ·  Shanghai World Foreign Language Middle School", S_LABEL, False,
     MUTED, before=30)

page_break(doc)

# ───────────────────────── overview table ─────────────────────────
para(doc, "全程结构  ·  AT A GLANCE", S_LABEL, True, BRICK)
para(doc, "一页看懂整场演讲", S_H1, True, INK, before=4)
para(doc, "时间栏是累计时间，方便在台上估算进度。", S_LABEL, False, MUTED, before=6)

rows = [("SLIDE", "时间", "这一页讲什么", "屏幕关键词")]
for i, s in enumerate(C.SLIDES):
    rows.append((f"{s['n']:02d}", s["t"], META[i][0], " · ".join(s["cue"])))

tbl = doc.add_table(rows=len(rows), cols=4)
tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
widths = [Cm(1.9), Cm(1.8), Cm(3.4), Cm(8.2)]
tbl.autofit = False
for r_, row in enumerate(rows):
    for c, val in enumerate(row):
        cell = tbl.cell(r_, c)
        cell.width = widths[c]
        cp = cell.paragraphs[0]
        spacing(cp, 5, 5, 1.1)
        run = cp.add_run(val)
        if r_ == 0:
            set_font(run, S_LABEL, True, MUTED)
        else:
            set_font(run, S_LABEL, c == 2, INK if c == 2 else SOFT, cn=(c >= 2))

for r_ in range(len(rows)):
    for c in range(4):
        tcPr = tbl.cell(r_, c)._tc.get_or_add_tcPr()
        borders = OxmlElement("w:tcBorders")
        for edge in ("top", "left", "bottom", "right"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "nil")
            borders.append(el)
        b = OxmlElement("w:bottom")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:color"), LINE)
        borders.append(b)
        tcPr.append(borders)

page_break(doc)

# ───────────────────────── 14 sections ─────────────────────────
for i, s in enumerate(C.SLIDES):
    cn_title, tip = META[i]
    body, notes, pct = plan(s["en"], s["zh"])

    head = doc.add_paragraph()
    spacing(head, 0, 2, 1.0)
    r = head.add_run(f"SLIDE {s['n']:02d}   ")
    set_font(r, S_LABEL, True, BRICK)
    r = head.add_run(f"/ {s['t']}")
    set_font(r, S_LABEL, False, MUTED)

    p = doc.add_paragraph()
    spacing(p, 2, 4, 1.1)
    r = p.add_run(cn_title)
    set_font(r, S_H1, True, INK, cn=True)
    bottom_rule(p, color=LINE, size=6)

    p = doc.add_paragraph()
    spacing(p, 0, 2, 1.3)
    r = p.add_run("屏幕关键词   ")
    set_font(r, S_LABEL, True, MUTED, cn=True)
    r = p.add_run(" · ".join(s["cue"]))
    set_font(r, S_LABEL, False, BRICK, cn=True)

    para(doc, s["en"], body, False, INK, before=12, line=EN_LEAD)

    p = para(doc, s["zh"], S_BODY_ZH, False, SOFT, before=14, line=ZH_LEAD)
    shade(p, "F7F2EC")
    left_border(p, "D9B5A6", 18)
    p.paragraph_format.left_indent = Cm(0.40)
    p.paragraph_format.right_indent = Cm(0.20)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)

    p = doc.add_paragraph()
    spacing(p, 14, 0, 1.4)
    r = p.add_run("提示   ")
    set_font(r, S_LABEL, True, MUTED, cn=True)
    r = p.add_run(tip)
    set_font(r, S_LABEL, False, MUTED, cn=True)

    if notes:
        pn = doc.add_paragraph()
        spacing(pn, 16, 4, 1.0)
        r = pn.add_run("笔记  NOTES")
        set_font(r, S_LABEL, True, RGBColor(0xB5, 0xAC, 0x9F))
        for _ in range(notes):
            ln = doc.add_paragraph()
            spacing(ln, 26, 0, 1.0)
            bottom_rule(ln, color="E7E0D4", size=4)

    if i < len(C.SLIDES) - 1:
        page_break(doc)

# ───────────────────────── appendix ─────────────────────────
page_break(doc)
para(doc, "APPENDIX", S_LABEL, True, BRICK)
para(doc, "数据与图片来源", S_H1, True, INK, before=4)
para(doc, "演讲里提到的每个数字，都能在这里找到出处；被问到细节时不必慌。",
     S_LABEL, False, MUTED, before=6)

para(doc, "事实与数据", S_LABEL, True, BRICK, before=14)
facts = [
    ("1.17 km（1182.7 m）；14 处优秀历史建筑 + 37 处保留历史建筑 = 51；30 处名人旧居",
     "徐汇区人民政府 / 徐汇区志"),
    ("1924 年建成，邬达克设计；1907 年筑路，1943 年改名武康路",
     "新华社 2021-06"),
    ("2018 年 3 月架空线入地开工（中心城区第一条），2019 年 1 月 25 日最后两根拆除",
     "文汇报 2019-01；新华社 2021-12"),
    ("2019 年大修历时 4 个多月，修旧如旧，设计者陈中伟称之为「建筑考古」",
     "新华社 2021-12-03"),
    ("日均客流 2–3 万人次，节假日峰值近 10 万；2021 年端午 3 天 40 余万游客",
     "新华社 2021-06-23；极目新闻 2025-01"),
    ("人气前 25 的餐饮店中近 80% 为西餐 / 咖啡 / 冰淇淋；约 85% 为本土新品牌",
     "经济参考报 2023-07"),
    ("2022 年街区税收超 7200 万元，2023 年突破 1 亿元；144 家企业（含 88 家主要商户）",
     "人民网上海 2024-01-12"),
    ("人行道外拓 3.6 米、新增 500 余平方米停留空间；微更新移除城市家具 109 处",
     "新华社 2021-12；人民城市报道"),
    ("商铺租金从 15 元/㎡/月 涨至 50–60 元/㎡/月", "人民网上海 2024-01-12"),
    ("2021 年蝴蝶结阳台每天上千人打卡；80 岁独居老人被家人接走，蝴蝶结被摘除",
     "央视网 2021-05-11；人民日报客户端；环球网 2021-05"),
]
for fact, src in facts:
    p = doc.add_paragraph()
    spacing(p, 6, 2, 1.45)
    p.paragraph_format.left_indent = Cm(0.7)
    p.paragraph_format.first_line_indent = Cm(-0.7)
    r = p.add_run(fact)
    set_font(r, S_LABEL, False, SOFT, cn=True)
    r = p.add_run(f"（{src}）")
    set_font(r, S_LABEL, False, MUTED, cn=True)

para(doc, "图片（全部为真实新闻图片，无 AI 生成）", S_LABEL, True, BRICK, before=16)
imgs = [
    "新华社（王翔 摄）：武康大楼前拍照的游客；武康大楼一层大隐书局",
    "文汇报：架空线密布时期的武康大楼、架空线入地后的天际线、秋日落叶街景",
    "央视网：2021 年蝴蝶结阳台报道画面",
    "人民日报客户端 / 环球网：蝴蝶结阳台、优秀历史建筑铭牌",
    "新浪新闻：梧桐树下的非机动车道",
]
for t in imgs:
    p = doc.add_paragraph()
    spacing(p, 5, 1, 1.45)
    p.paragraph_format.left_indent = Cm(0.7)
    p.paragraph_format.first_line_indent = Cm(-0.7)
    r = p.add_run(t)
    set_font(r, S_LABEL, False, SOFT, cn=True)

para(doc, "制作：Kernel（WorkBuddy）  ·  2026-10", S_LABEL, False, MUTED, before=20)

out = "./out/武康路_演讲稿_中英对照.docx"
doc.save(out)
print("saved", out, os.path.getsize(out) // 1024, "KB")
for s in C.SLIDES[:3]:
    print("plan", s["n"], plan(s["en"], s["zh"]))
for s_ in C.SLIDES:
    b, n_, pct = plan(s_["en"], s_["zh"])
    print(f"  slide {s_['n']:02d}  body={b}pt  notes={n_}  fill={pct*100:.0f}%")
