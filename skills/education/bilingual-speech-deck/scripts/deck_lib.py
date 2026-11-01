#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layout helpers for the Wukang Road deck (with scene recording for QA render)."""
import os, hashlib
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from lxml import etree
from PIL import Image

PAPER = RGBColor(0xFA, 0xF8, 0xF5)
INK = RGBColor(0x1C, 0x1A, 0x17)
MUTED = RGBColor(0x7D, 0x76, 0x6C)
SOFT = RGBColor(0x4A, 0x44, 0x3C)
BRICK = RGBColor(0x9C, 0x3D, 0x2E)
SAGE = RGBColor(0x6E, 0x7F, 0x6E)
LINE = RGBColor(0xDE, 0xD7, 0xCB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Helvetica Neue"
FONT_B = "Helvetica Neue"
W, H = 13.333, 7.5
M = 0.86  # side margin

TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
os.makedirs(TMP, exist_ok=True)

SCENE = []
ALIGN = {PP_ALIGN.LEFT: "left", PP_ALIGN.CENTER: "center", PP_ALIGN.RIGHT: "right"}


def new_deck():
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    return prs


def blank(prs, color=PAPER):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(W), Inches(H))
    r.fill.solid()
    r.fill.fore_color.rgb = color
    r.line.fill.background()
    r.shadow.inherit = False
    SCENE.append(dict(op="slide", color=color))
    return s


def txt(slide, x, y, w, h, text, size=14, color=INK, bold=False, font=FONT,
        align=PP_ALIGN.LEFT, spacing=1.18, spc=None, anchor=MSO_ANCHOR.TOP,
        italic=False, caps=False):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run()
        r.text = line
        f = r.font
        f.name = font
        f.size = Pt(size)
        f.bold = bold
        f.italic = italic
        f.color.rgb = color
        if spc is not None:
            f._rPr.set("spc", str(int(spc)))
        if caps:
            f._rPr.set("cap", "all")
    SCENE.append(dict(op="text", x=x, y=y, w=w, h=h, text=text, size=size, color=color,
                      bold=bold, spacing=spacing, align=ALIGN.get(align, "left"),
                      italic=italic))
    return tb


def rule(slide, x, y, w, color=LINE, pt=0.75):
    ln = slide.shapes.add_connector(1, Inches(x), Inches(y), Inches(x + w), Inches(y))
    ln.line.color.rgb = color
    ln.line.width = Pt(pt)
    SCENE.append(dict(op="line", x=x, y=y, x2=x + w, y2=y, color=color, pt=pt))
    return ln


def vrule(slide, x, y, h, color=LINE, pt=0.75):
    ln = slide.shapes.add_connector(1, Inches(x), Inches(y), Inches(x), Inches(y + h))
    ln.line.color.rgb = color
    ln.line.width = Pt(pt)
    SCENE.append(dict(op="line", x=x, y=y, x2=x, y2=y + h, color=color, pt=pt))
    return ln


def link(slide, x1, y1, x2, y2, color=MUTED, pt=1.1):
    ln = slide.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    ln.line.color.rgb = color
    ln.line.width = Pt(pt)
    SCENE.append(dict(op="line", x=x1, y=y1, x2=x2, y2=y2, color=color, pt=pt))
    return ln


def rect(slide, x, y, w, h, fill=None, line=None, pt=0.75, shape=MSO_SHAPE.RECTANGLE,
         radius=None):
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.shadow.inherit = False
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(pt)
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sp.adjustments[0] = radius
    SCENE.append(dict(op="rect", x=x, y=y, w=w, h=h, fill=fill, line=line,
                      oval=(shape == MSO_SHAPE.OVAL)))
    return sp


def _crop(path, w, h, fx, fy):
    im = Image.open(path)
    iw, ih = im.size
    target = w / h
    src = iw / ih
    if src > target:
        nw = int(ih * target)
        left = int((iw - nw) * fx)
        box = (left, 0, left + nw, ih)
    else:
        nh = int(iw / target)
        top = int((ih - nh) * fy)
        box = (0, top, iw, top + nh)
    im = im.crop(box).convert("RGB")
    key = hashlib.md5((os.path.basename(path) + str(box) + str(w) + str(h)).encode()).hexdigest()[:12]
    out = os.path.join(TMP, f"c_{key}.jpg")
    if not os.path.exists(out):
        im.save(out, "JPEG", quality=92)
    return out


def shade(slide, x, y, w, h, color=INK, alpha=0.6):
    """Translucent ink panel over a photo."""
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.shadow.inherit = False
    sp.line.fill.background()
    sp.fill.solid()
    sp.fill.fore_color.rgb = color
    solid = sp.fill._xPr.find(qn("a:solidFill"))
    srgb = solid.find(qn("a:srgbClr"))
    a = etree.SubElement(srgb, qn("a:alpha"))
    a.set("val", str(int(alpha * 100000)))
    SCENE.append(dict(op="rect", x=x, y=y, w=w, h=h, fill=color, line=None, alpha=alpha))
    return sp


def photo(slide, path, x, y, w, h, fx=0.5, fy=0.5):
    out = _crop(path, w, h, fx, fy)
    slide.shapes.add_picture(out, Inches(x), Inches(y), Inches(w), Inches(h))
    SCENE.append(dict(op="photo", x=x, y=y, w=w, h=h, file=out))
    return out


def pic_fit(slide, path, x, y, maxw, maxh, halign="left", valign="top"):
    im = Image.open(path)
    iw, ih = im.size
    r = iw / ih
    w, h = maxw, maxw / r
    if h > maxh:
        h, w = maxh, maxh * r
    if halign == "center":
        x = x + (maxw - w) / 2
    elif halign == "right":
        x = x + (maxw - w)
    if valign == "middle":
        y = y + (maxh - h) / 2
    elif valign == "bottom":
        y = y + (maxh - h)
    slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    SCENE.append(dict(op="photo", x=x, y=y, w=w, h=h, file=path))
    return w, h


def eyebrow(slide, x, y, text, color=BRICK):
    txt(slide, x, y, 8.0, 0.24, text, size=9.5, color=color, bold=True, spc=180, caps=True)


def pagenum(slide, n, total=14, color=MUTED):
    txt(slide, W - M - 0.9, H - 0.52, 0.9, 0.25, f"{n:02d} / {total}",
        size=8.5, color=color, align=PP_ALIGN.RIGHT, spc=60)


def caption(slide, x, y, w, text, color=MUTED):
    txt(slide, x, y, w, 0.5, text, size=8.5, color=color, spacing=1.35)


def kpi(slide, x, y, w, num, label, num_size=30, color=INK):
    txt(slide, x, y, w, 0.55, num, size=num_size, color=color, bold=True, spacing=1.0)
    txt(slide, x, y + 0.52, w, 0.5, label, size=9.5, color=MUTED, spacing=1.3)


def note(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def _border(cell, color="DED7CB", pt=0.75, edges="B"):
    tcPr = cell._tc.get_or_add_tcPr()
    for e in ["L", "R", "T", "B"]:
        if e not in edges:
            continue
        tag = "a:ln" + e
        for old in tcPr.findall(qn(tag)):
            tcPr.remove(old)
        ln = etree.SubElement(tcPr, qn(tag))
        ln.set("w", str(int(pt * 12700)))
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")
        sf = etree.SubElement(ln, qn("a:solidFill"))
        c = etree.SubElement(sf, qn("a:srgbClr"))
        c.set("val", str(color))
        etree.SubElement(ln, qn("a:prstDash")).set("val", "solid")
    for el in ["B", "T", "R", "L"]:
        node = tcPr.find(qn("a:ln" + el))
        if node is not None:
            tcPr.remove(node)
            tcPr.insert(0, node)


def table(slide, x, y, w, rows, col_w, row_h=0.62, head_h=0.42,
          body_size=12.5, head_size=8.8, first_bold=True):
    nrows, ncols = len(rows), len(rows[0])
    shp = slide.shapes.add_table(nrows, ncols, Inches(x), Inches(y), Inches(w),
                                 Inches(head_h + row_h * (nrows - 1)))
    tbl = shp.table
    tbl.first_row = False
    tbl.horz_banding = False
    for i, cw in enumerate(col_w):
        tbl.columns[i].width = Inches(cw)
    tbl.rows[0].height = Inches(head_h)
    for r in range(1, nrows):
        tbl.rows[r].height = Inches(row_h)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.background()
            cell.margin_left = Inches(0.02 if c == 0 else 0.10)
            cell.margin_right = Inches(0.10)
            cell.margin_top = Inches(0.09)
            cell.margin_bottom = Inches(0.06)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.line_spacing = 1.12
            run = p.add_run()
            run.text = val
            f = run.font
            f.name = FONT
            if r == 0:
                f.size = Pt(head_size)
                f.bold = True
                f.color.rgb = MUTED
                f._rPr.set("spc", "140")
                f._rPr.set("cap", "all")
            else:
                f.size = Pt(body_size)
                f.bold = (c == 0 and first_bold)
                f.color.rgb = INK if c == 0 else SOFT
            _border(cell, color="DED7CB", pt=0.75, edges="B")
    rule(slide, x, y - 0.02, w, color=RGBColor(0x1C, 0x1A, 0x17), pt=1.0)
    SCENE.append(dict(op="table", x=x, y=y, w=w, rows=rows, col_w=col_w,
                      row_h=row_h, head_h=head_h, body_size=body_size,
                      head_size=head_size))
    return tbl
