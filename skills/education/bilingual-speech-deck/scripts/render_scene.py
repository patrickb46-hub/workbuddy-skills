#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render recorded slide scene to PNG with PIL (layout QA proxy)."""
import os
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_BOLD = "/System/Library/Fonts/HelveticaNeue.ttc"


def font(size_pt, bold=False, ppi=110):
    px = max(6, int(round(size_pt / 72.0 * ppi)))
    try:
        return ImageFont.truetype(FONT_PATH, px, index=1 if bold else 0)
    except Exception:
        return ImageFont.load_default()


def _hex(c):
    return (c[0], c[1], c[2]) if isinstance(c, tuple) else (0, 0, 0)


def render(scene, outdir, ppi=110):
    os.makedirs(outdir, exist_ok=True)
    W, H = int(13.333 * ppi), int(7.5 * ppi)
    s_img = Image.new("RGB", (W, H), "#FAF8F5")
    d = ImageDraw.Draw(s_img)
    slides = []
    page = 0
    for rec in scene:
        k = rec["op"]
        if k == "slide":
            if page:
                p = os.path.join(outdir, f"s{page:02d}.png")
                s_img.save(p)
                slides.append(p)
            page += 1
            s_img = Image.new("RGB", (W, H), _hex(rec.get("color", (250, 248, 245))))
            d = ImageDraw.Draw(s_img)
        elif k == "rect":
            x, y, w, h = [v * ppi for v in (rec["x"], rec["y"], rec["w"], rec["h"])]
            fill = _hex(rec["fill"]) if rec["fill"] else None
            outline = _hex(rec["line"]) if rec["line"] else None
            if rec.get("alpha"):
                ov = Image.new("RGBA", s_img.size, (0, 0, 0, 0))
                od = ImageDraw.Draw(ov)
                od.rectangle([x, y, x + w, y + h], fill=fill + (int(rec["alpha"] * 255),))
                s_img = Image.alpha_composite(s_img.convert("RGBA"), ov).convert("RGB")
                d = ImageDraw.Draw(s_img)
            elif rec.get("oval"):
                d.ellipse([x, y, x + w, y + h], fill=fill, outline=outline)
            else:
                d.rectangle([x, y, x + w, y + h], fill=fill, outline=outline)
        elif k == "line":
            x1, y1 = rec["x"] * ppi, rec["y"] * ppi
            x2, y2 = rec["x2"] * ppi, rec["y2"] * ppi
            d.line([x1, y1, x2, y2], fill=_hex(rec["color"]),
                   width=max(1, int(rec.get("pt", 0.75) / 72 * ppi)))
        elif k == "photo":
            im = Image.open(rec["file"]).convert("RGBA")
            tw, th = int(rec["w"] * ppi), int(rec["h"] * ppi)
            im = im.resize((tw, th), Image.LANCZOS)
            s_img.paste(im, (int(rec["x"] * ppi), int(rec["y"] * ppi)), im)
        elif k == "text":
            _draw_text(d, rec, ppi)
        elif k == "table":
            _draw_table(d, rec, ppi)
    if page:
        p = os.path.join(outdir, f"s{page:02d}.png")
        s_img.save(p)
        slides.append(p)
    return slides


def _draw_table(d, rec, ppi):
    x = rec["x"] * ppi
    y = rec["y"] * ppi
    rh = rec["row_h"] * ppi
    hh = rec["head_h"] * ppi
    ytop = y
    for r, row in enumerate(rec["rows"]):
        h = hh if r == 0 else rh
        size = rec["head_size"] if r == 0 else rec["body_size"]
        bold = True if r == 0 else None
        cx = x
        for c, val in enumerate(row):
            cw = rec["col_w"][c] * ppi
            alpha = max(1, int(size / 72 * ppi))
            f = font(size, True if (r == 0 or (c == 0 and bold is None)) else False, ppi)
            col = (125, 118, 108) if r == 0 else ((28, 26, 23) if c == 0 else (74, 68, 60))
            tw = d.textlength(val, font=f)
            ty = ytop + (h - size / 72 * ppi * 1.15) / 2
            d.text((cx + (0.02 if c == 0 else 0.10) * ppi, ty), val, font=f, fill=col)
            cx += cw
        d.line([x, ytop + h, x + rec["w"] * ppi, ytop + h], fill=(222, 215, 203), width=1)
        ytop += h
    d.line([x, y - 0.02 * ppi, x + rec["w"] * ppi, y - 0.02 * ppi], fill=(28, 26, 23), width=2)


def _draw_text(d, rec, ppi):
    size = rec["size"]
    f = font(size, rec.get("bold", False), ppi)
    color = _hex(rec["color"])
    x = rec["x"] * ppi
    y = rec["y"] * ppi
    w = rec["w"] * ppi
    lh = size * 1.2 * rec.get("spacing", 1.18) / 72 * ppi
    align = rec.get("align", "left")
    for line in rec["text"].split("\n"):
        if not line:
            y += lh
            continue
        # wrap
        words = line.split(" ")
        cur = ""
        lines = []
        for wd in words:
            t = (cur + " " + wd).strip()
            if d.textlength(t, font=f) <= w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        for ln in lines:
            tw = d.textlength(ln, font=f)
            tx = x
            if align == "center":
                tx = x + (w - tw) / 2
            elif align == "right":
                tx = x + (w - tw)
            d.text((tx, y), ln, font=f, fill=color)
            y += lh
