#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from deck_lib import *
import content as C

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
J = lambda f: os.path.join(A, f)

prs = new_deck()
TOTAL = 14

# ───────────────────────── 1 · TITLE ─────────────────────────
s = blank(prs)
photo(s, J("now_crowd.jpg"), 4.45, 0, W - 4.45, H, fx=0.62)
txt(s, 0.86, 1.42, 3.2, 0.25, "THEN AND NOW  ·  XUHUI, SHANGHAI", size=9.5, color=BRICK,
    bold=True, spc=180)
txt(s, 0.86, 1.78, 3.3, 1.85, "Wukang\nRoad", size=50, bold=True, spacing=0.92)
rule(s, 0.86, 3.72, 1.1, color=BRICK, pt=1.6)
txt(s, 0.86, 3.96, 3.30, 1.3,
    "Fifteen years that turned a quiet\nlane into a city landmark —\nand what it cost.",
    size=13, color=SOFT, spacing=1.5)
txt(s, 0.86, 6.38, 3.2, 0.3, "2010  →  2026", size=10, color=MUTED, spc=120)
note(s, C.SLIDES[0]["en"])

# ───────────────────────── 2 · THE PLACE ─────────────────────────
s = blank(prs)
photo(s, J("plane_trees.jpg"), 8.05, 0, W - 8.05, H, fx=0.5, fy=0.45)
eyebrow(s, M, 1.02, "The place")
txt(s, M, 1.36, 6.6, 1.35, "One lane,\na hundred years", size=38, bold=True, spacing=1.0)
txt(s, M, 3.28, 6.30, 0.9,
    "Built in 1907. Renamed Wukang in 1943. For decades it was simply "
    "Route Ferguson — a quiet lane of plane trees and old villas.",
    size=12.5, color=SOFT, spacing=1.55)
xs = [M, M + 2.28, M + 4.56]
kpi(s, xs[0], 4.55, 2.05, "1.17 km", "length of the road")
kpi(s, xs[1], 4.55, 2.05, "51", "protected historic buildings")
kpi(s, xs[2], 4.55, 2.05, "30", "former homes of famous people")
rule(s, M, 5.95, 6.5, color=LINE)
caption(s, M, 6.12, 6.4,
        "Sources: Xuhui District Government (14 listed + 37 preserved historic buildings); "
        "CCTV documentary on the historical street.")
pagenum(s, 2, TOTAL)
note(s, C.SLIDES[1]["en"])

# ───────────────────────── 3 · THEN ─────────────────────────
s = blank(prs)
photo(s, J("then_cables.jpg"), 0, 0, 7.55, H, fy=0.30)
txt(s, 8.0, 1.02, 4.5, 0.25, "AROUND 2010  ·  THEN", size=9.5, color=BRICK, bold=True, spc=180)
txt(s, 8.0, 1.36, 4.6, 1.3, "A quiet\nresidential lane", size=36, bold=True, spacing=1.0)
words = [("Quiet.", "Neighbours left doors unlocked."),
         ("Local.", "A market, a grocery, a barber."),
         ("Wired.", "Overhead cables cut the sky.")]
yy = 3.22
for i, (w_, d_) in enumerate(words):
    txt(s, 8.0, yy, 4.4, 0.42, w_, size=21, bold=True)
    txt(s, 8.0, yy + 0.40, 4.4, 0.3, d_, size=10.5, color=MUTED)
    rule(s, 8.0, yy + 0.78, 4.35, color=LINE)
    yy += 1.06
caption(s, 8.0, 6.28, 4.42,
        "To photograph the mansion you waited for a red light — and still lost the top of the building. "
        "Photo: Wenhui Daily")
pagenum(s, 3, TOTAL)
note(s, C.SLIDES[2]["en"])

# ───────────────────────── 4 · NOW ─────────────────────────
s = blank(prs)
photo(s, J("now_crowd.jpg"), 8.75, 0, W - 8.75, H, fx=0.74)
txt(s, M, 1.02, 5.0, 0.25, "2026  ·  NOW", size=9.5, color=BRICK, bold=True, spc=180)
txt(s, M, 1.36, 7.0, 1.3, "A landmark\nwith a queue", size=36, bold=True, spacing=1.0)
pic_fit(s, J("chart_visitors.png"), M, 3.18, 7.35, 2.45)
caption(s, M, 5.74, 7.3,
        "Daily footfall, 2024–2026 estimates: a holiday brings about four times an ordinary day. "
        "Dragon Boat holiday 2021: 400,000+ visitors in three days.")
rule(s, M, 6.42, 7.2, color=LINE)
txt(s, M, 6.56, 7.3, 0.3,
    "Named the city's No.1 “City Walk”  ·  peak days bring temporary traffic control",
    size=9.5, color=MUTED)
pagenum(s, 4, TOTAL)
note(s, C.SLIDES[3]["en"])

# ───────────────────────── 5 · FIVE CHANGES ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.95, "The shift")
txt(s, M, 1.28, 8.0, 0.7, "Five things that changed", size=34, bold=True)
rows = [
    ["Aspect of change", "Then  ·  around 2010", "Now  ·  2026"],
    ["Tourism", "Local residents walking by", "Thousands of visitors a day"],
    ["Buildings", "Old, run-down, little known", "Restored and protected"],
    ["Business", "Market, grocery, barber", "Cafés, bookstores, boutiques"],
    ["Transport", "Residents and local traffic", "Walking, cycling, City Walk"],
    ["Image", "Known inside Shanghai", "A national landmark"],
]
table(s, M, 2.42, 11.55, rows, [2.55, 4.35, 4.65], row_h=0.80, head_h=0.44,
      body_size=13, head_size=8.8)
pagenum(s, 5, TOTAL)
note(s, C.SLIDES[4]["en"])

# ───────────────────────── 6 · SKYLINE ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.92, "Change 01  ·  Skyline")
txt(s, M, 1.22, 7.0, 0.6, "The wires came down", size=34, bold=True)
txt(s, W - M - 2.1, 1.28, 2.1, 0.5, "0", size=42, bold=True, color=BRICK, align=PP_ALIGN.RIGHT)
txt(s, W - M - 2.4, 1.82, 2.4, 0.3, "cables left in the sky", size=9, color=MUTED, align=PP_ALIGN.RIGHT)

txt(s, M, 2.08, 3.0, 0.28, "2018  ·  spider web", size=9, color=MUTED, bold=True, spc=120)
txt(s, 6.78, 2.08, 3.0, 0.28, "2019  ·  clear sky", size=9, color=MUTED, bold=True, spc=120)
photo(s, J("then_cables.jpg"), M, 2.42, 5.60, 3.55, fy=0.02)
photo(s, J("now_clean.jpg"), 6.78, 2.42, 5.60, 3.55, fx=0.5)
rule(s, M, 6.22, 11.55, color=LINE)
caption(s, M, 6.38, 8.1,
        "Cables buried from March 2018 — the first such project in central Shanghai; "
        "the last two came down on 25 January 2019.  Photos: Wenhui Daily")
txt(s, 9.20, 6.34, 3.2, 0.3, "“Photo it against the sky.”", size=11, color=BRICK,
    italic=True, align=PP_ALIGN.RIGHT)
pagenum(s, 6, TOTAL)
note(s, C.SLIDES[5]["en"])

# ───────────────────────── 7 · BUILDINGS ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.92, "Change 02  ·  Buildings")
txt(s, M, 1.22, 6.4, 0.6, "Restored, not replaced", size=34, bold=True)
photo(s, J("plaque.png"), M, 2.05, 5.9, 3.95, fx=0.5)
caption(s, M, 6.12, 5.9, "Heritage plaque at No.129 Wukang Road — one of the 51 protected buildings. "
                         "Photo: Huanqiu / People's Daily")
xx = 7.25
stats = [("2009", "first restoration of the block"),
         ("2019", "four months of “building archaeology”"),
         ("51", "protected buildings kept standing")]
yy = 2.12
for num, lab in stats:
    txt(s, xx, yy, 1.55, 0.5, num, size=25, bold=True, color=BRICK)
    txt(s, xx + 1.62, yy + 0.06, 3.55, 0.7, lab, size=11.5, color=SOFT, spacing=1.35)
    rule(s, xx, yy + 0.78, 5.15, color=LINE)
    yy += 1.02
txt(s, xx, 5.42, 5.2, 1.0,
    "“All the repairs had to be invisible —\nmake it look as if it was never repaired.”",
    size=13, color=INK, italic=True, spacing=1.5)
txt(s, xx, 6.34, 5.2, 0.3, "Chen Zhongwei, restoration designer", size=9, color=MUTED)
pagenum(s, 7, TOTAL)
note(s, C.SLIDES[6]["en"])

# ───────────────────────── 8 · BUSINESS ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.92, "Change 03  ·  Business")
txt(s, M, 1.22, 7.6, 0.6, "From vegetables to flat whites", size=34, bold=True)
pic_fit(s, J("chart_business.png"), M - 0.05, 2.10, 3.45, 3.45)
txt(s, M + 0.10, 5.62, 3.4, 0.55, "of the 25 most popular\nplaces to eat", size=9, color=MUTED,
    spacing=1.35)
photo(s, J("bookstore.jpg"), 5.55, 2.05, 3.6, 2.4, fx=0.35)
caption(s, 5.55, 4.55, 3.6, "Dayin Bookmall on the ground floor of the mansion. Photo: Xinhua")
xs = 9.62
lines = [("85%", "are home-grown brands"), ("144", "firms in the block"),
         ("¥100m", "in tax, 2023")]
yy = 2.12
for num, lab in lines:
    txt(s, xs, yy, 2.85, 0.5, num, size=24, bold=True)
    txt(s, xs, yy + 0.46, 2.85, 0.3, lab, size=9.5, color=MUTED)
    yy += 1.02
rule(s, M, 6.28, 11.55, color=LINE)
txt(s, M, 6.42, 11.55, 0.3,
    "Rent for a street-level unit rose from ¥15 to ¥50–60 per m² per month between 2020 and 2023.",
    size=9.5, color=MUTED)
pagenum(s, 8, TOTAL)
note(s, C.SLIDES[7]["en"])

# ───────────────────────── 9 · STREET SPACE ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.92, "Change 04  ·  Street space")
txt(s, M, 1.14, 5.6, 1.05, "Room to stand,\nroom to walk", size=31, bold=True, spacing=1.0)
photo(s, J("bike_lane.jpg"), 6.95, 1.35, 5.5, 3.85, fx=0.5)
caption(s, 6.95, 5.32, 5.5, "Cycle lane under the plane trees. Photo: Sina News / Wukang Road")
stats = [("+3.6 m", "pavement widened for viewers"),
         ("+500 m²", "new standing space at the best angle"),
         ("109", "poles, boxes and units removed")]
yy = 2.62
for num, lab in stats:
    txt(s, M, yy, 2.6, 0.55, num, size=27, bold=True, color=BRICK)
    txt(s, M + 2.65, yy + 0.10, 3.1, 0.7, lab, size=10.5, color=SOFT, spacing=1.35)
    rule(s, M, yy + 0.85, 5.6, color=LINE)
    yy += 1.06
txt(s, M, 5.72, 5.7, 0.8,
    "The city did not ban the photographers.\nIt rebuilt the street around them.",
    size=13, color=INK, spacing=1.5)
pagenum(s, 9, TOTAL)
note(s, C.SLIDES[8]["en"])

# ───────────────────────── 10 · WHY (MIND MAP) ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.92, "The cause")
txt(s, M, 1.22, 8.0, 0.6, "Why did it happen?", size=34, bold=True)

cx, cy, R = 6.66, 4.02, 0.72
boxes = [
    (1.92, 2.12, "1  ·  Policy", "A 2008 protection plan;\nrestoration step by step"),
    (8.05, 2.12, "2  ·  Renewal", "Cables, pavements,\ngreenery, street furniture"),
    (1.92, 4.98, "3  ·  Culture", "A history boom; old buildings\nopened to the public"),
    (8.05, 4.98, "4  ·  Social media", "One phone photo can make\na street famous overnight"),
]
bw, bh = 3.36, 1.12
for bx, by, _, _ in boxes:
    tx = bx if bx > cx else bx + bw
    ty = by + bh / 2
    link(s, cx, cy, tx, ty, color=RGBColor(0xB9, 0xAF, 0x9F), pt=1.1)

for bx, by, head, sub in boxes:
    rect(s, bx, by, bw, bh, fill=PAPER, line=LINE, pt=1.0)
    txt(s, bx + 0.20, by + 0.15, bw - 0.36, 0.3, head, size=11.5, bold=True, color=BRICK, spc=40)
    txt(s, bx + 0.20, by + 0.50, bw - 0.36, 0.55, sub, size=10, color=SOFT, spacing=1.4)

rect(s, cx - R, cy - R, R * 2, R * 2, fill=INK, line=None, shape=MSO_SHAPE.OVAL)
txt(s, cx - R, cy - 0.16, R * 2, 0.35, "WHY", size=16, bold=True, color=PAPER,
    align=PP_ALIGN.CENTER, spc=120)
pagenum(s, 10, TOTAL)
note(s, C.SLIDES[9]["en"])

# ───────────────────────── 11 · WHO GAINED ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.95, "The impact")
txt(s, M, 1.28, 8.0, 0.6, "Who gained what", size=34, bold=True)
rows = [
    ["Group", "What changed for them"],
    ["Residents", "Safer streets, cleaner surroundings, better lighting"],
    ["Shop owners", "More customers, higher income, stronger brands"],
    ["Students", "History and architecture you can walk through"],
    ["Tourists", "Old Shanghai, in one place, in one afternoon"],
    ["The city", "A brand people photograph — and a tax base"],
]
table(s, M, 2.35, 11.55, rows, [2.35, 9.2], row_h=0.76, head_h=0.42,
      body_size=13.5, head_size=8.8)
pagenum(s, 11, TOTAL)
note(s, C.SLIDES[10]["en"])

# ───────────────────────── 12 · THE COST ─────────────────────────
s = blank(prs)
eyebrow(s, M, 0.92, "The cost")
txt(s, M, 1.22, 7.0, 0.6, "Fame has a bill", size=34, bold=True)
photo(s, J("bow_grandma.png"), M, 2.02, 3.05, 3.55, fx=0.5)
photo(s, J("bow_crowd.png"), 4.12, 2.02, 4.15, 3.55, fx=0.45, fy=0.4)
caption(s, M, 5.74, 7.4,
        "The pink bow at No.129, 2021: an 80-year-old resident, and the crowd below her window. "
        "Photos: People's Daily / Huanqiu")
txt(s, 8.85, 2.02, 3.7, 0.85, "1,000", size=54, bold=True, color=BRICK, spacing=0.95)
txt(s, 8.85, 2.92, 3.7, 0.6, "photographs a day,\nunder one balcony", size=11.5, color=SOFT,
    spacing=1.4)
rule(s, 8.85, 3.78, 3.65, color=LINE)
points = ["Visitors stood in the road; residents stayed indoors.",
          "The resident was moved out by her family.",
          "Cheap shops were priced out as rent tripled."]
yy = 3.96
for p_ in points:
    txt(s, 8.85, yy, 3.65, 0.62, "—  " + p_, size=9.8, color=SOFT, spacing=1.4)
    yy += 0.72
pagenum(s, 12, TOTAL)
note(s, C.SLIDES[11]["en"])

# ───────────────────────── 13 · WHAT I LEARNED ─────────────────────────
s = blank(prs)
photo(s, J("leaves_walk.jpg"), 0, 4.86, W, H - 4.86, fx=0.5, fy=0.55)
eyebrow(s, M, 0.92, "The lesson")
txt(s, M, 1.22, 8.0, 0.6, "What I learned", size=34, bold=True)
blocks = [("01", "History and development\ncan grow together."),
          ("02", "Protection creates long-term\nvalue, not just a photo."),
          ("03", "A community's treasure is\nits stories, not its new towers.")]
xs = [M, M + 3.86, M + 7.72]
for (num, t_), x_ in zip(blocks, xs):
    rule(s, x_, 2.28, 3.3, color=RGBColor(0x1C, 0x1A, 0x17), pt=1.2)
    txt(s, x_, 2.44, 3.2, 0.35, num, size=10, color=BRICK, bold=True, spc=120)
    txt(s, x_, 2.82, 3.3, 1.3, t_, size=14.5, color=INK, spacing=1.5)
txt(s, M, 4.10, 9.0, 0.45, "Respect the past. Embrace the future.", size=19, color=INK,
    italic=True)
pagenum(s, 13, TOTAL, color=RGBColor(0x4A, 0x44, 0x3C))
note(s, C.SLIDES[12]["en"])

# ───────────────────────── 14 · THANK YOU ─────────────────────────
s = blank(prs)
photo(s, J("street_crowd.png"), 0, 0, W, H, fx=0.5, fy=0.45)
shade(s, 0, 0, W, H, color=INK, alpha=0.86)
txt(s, M, 1.42, 6.0, 0.25, "THANK YOU", size=9.5, color=RGBColor(0xD8, 0xB6, 0xA6),
    bold=True, spc=200)
txt(s, M, 1.78, 6.2, 0.85, "Thank you.", size=46, bold=True, color=WHITE)
rule(s, M, 2.86, 1.1, color=RGBColor(0xD8, 0xB6, 0xA6), pt=1.6)
txt(s, M, 3.10, 5.6, 0.9,
    "Questions are welcome — about the street,\nthe data, or the people who live there.",
    size=13, color=RGBColor(0xEC, 0xE6, 0xDC), spacing=1.5)
txt(s, M, 6.30, 5.4, 0.3, "Zhang San  ·  Wukang Road: Then and Now", size=9,
    color=RGBColor(0xC5, 0xBC, 0xAF))

vrule(s, 8.10, 1.42, 4.28, color=RGBColor(0x6A, 0x61, 0x57))
txt(s, 8.50, 1.42, 4.1, 0.3, "IMAGES  ·  all photographs are real, editorial sources", size=8,
    color=RGBColor(0xD8, 0xB6, 0xA6), bold=True, spc=120)
credits = [
    "Xinhua News Agency — Wukang Mansion, Dayin Bookmall",
    "Wenhui Daily — overhead cables, clear skyline, leaves",
    "CCTV — the “bow balcony” report",
    "People's Daily · Huanqiu — bow balcony, heritage plaque",
    "Sina News — cycle lane",
    "Data — Xuhui District Government, People's Daily Online, Xinhua",
]
yy = 1.80
for c_ in credits:
    txt(s, 8.50, yy, 4.05, 0.5, c_, size=8.4, color=RGBColor(0xD6, 0xCE, 0xC2), spacing=1.35)
    yy += 0.52
pagenum(s, 14, TOTAL, color=RGBColor(0xB5, 0xAC, 0x9F))
note(s, C.SLIDES[13]["en"])

out = "./out/Wukang_Road_Then_and_Now.pptx"
os.makedirs(os.path.dirname(out), exist_ok=True)
prs.save(out)
print("saved", out, os.path.getsize(out) // 1024, "KB")

if os.environ.get("QA"):
    from deck_lib import SCENE
    from render_scene import render
    from PIL import Image
    d = os.path.join(os.path.dirname(out), "qa")
    slides = render(SCENE, d, ppi=110)
    cols, rows = 2, (len(slides) + 1) // 2
    tw, th = 660, 371
    sheet = Image.new("RGB", (cols * (tw + 10) + 10, rows * (th + 10) + 10), "white")
    for i, sp in enumerate(slides):
        im = Image.open(sp); im.thumbnail((tw, th))
        sheet.paste(im, (10 + (i % cols) * (tw + 10), 10 + (i // cols) * (th + 10)))
    sheet.save(os.path.join(d, "contact.jpg"), quality=90)
    print("qa sheets:", len(slides))
