#!/usr/bin/env python3
"""Bing image search -> download candidates + contact sheet (for real-photo sourcing)."""
import re, os, sys, json, html, subprocess, urllib.parse, hashlib
from PIL import Image, ImageDraw

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
ROOT = os.path.dirname(os.path.abspath(__file__))


def search(q, n=35):
    url = "https://cn.bing.com/images/search?q=" + urllib.parse.quote(q) + "&form=HDRSC2&first=1&count=%d" % n
    r = subprocess.run(["curl", "-sSLk", "--max-time", "30", "-A", UA,
                        "-H", "Accept-Language: zh-CN,zh;q=0.9", url],
                       capture_output=True)
    t = r.stdout.decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r'm="(\{&quot;.*?\})"', t):
        try:
            d = json.loads(html.unescape(m.group(1)))
        except Exception:
            continue
        if d.get("murl"):
            out.append((d["murl"], d.get("purl", ""), d.get("t", "")))
    return out


def run(tag, q, limit=10, min_px=500):
    d = os.path.join(ROOT, "cand", tag)
    os.makedirs(d, exist_ok=True)
    res = search(q)
    print(f"[{tag}] {q} -> {len(res)} hits")
    kept = []
    for i, (murl, purl, title) in enumerate(res[:limit]):
        ext = os.path.splitext(urllib.parse.urlparse(murl).path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        p = os.path.join(d, f"{i:02d}{ext}")
        subprocess.run(["curl", "-sSLk", "--max-time", "20", "-A", UA,
                        "-e", "https://cn.bing.com/", murl, "-o", p], capture_output=True)
        try:
            im = Image.open(p)
            if im.width < min_px or im.height < min_px:
                os.remove(p)
                continue
            kept.append((p, purl, title, im.size))
        except Exception:
            if os.path.exists(p):
                os.remove(p)
    # contact sheet
    if kept:
        W = 320
        cols = 4
        rows = (len(kept) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * W, rows * 300), "white")
        dr = ImageDraw.Draw(sheet)
        for i, (p, purl, title, size) in enumerate(kept):
            im = Image.open(p).convert("RGB")
            im.thumbnail((W - 12, 260))
            x = (i % cols) * W
            y = (i // cols) * 300
            sheet.paste(im, (x + 6, y + 6))
            dr.text((x + 6, y + 272), f"{os.path.basename(p)} {size[0]}x{size[1]}", fill="black")
        sp = os.path.join(ROOT, f"sheet_{tag}.jpg")
        sheet.save(sp, quality=88)
        json.dump([{"file": p, "purl": purl, "title": title} for p, purl, title, _ in kept],
                  open(os.path.join(ROOT, f"meta_{tag}.json"), "w"), ensure_ascii=False, indent=1)
        print(f"  kept {len(kept)} -> {sp}")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12)
