#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shoot.py — 渲染自检：整页截图 → 按内容高度切屏 → 只报「有问题的那几屏」。

  shoot.py 全解.html [-o /tmp/wbs-shots] [--width 1000] [--slice 1300] [--keep-all]

输出一段紧凑报告（页面尺寸 / 每屏墨量 / 空白带 / 右侧贴边 / 底边被切），
并只保留「首屏 + 有问题的屏」的切片。模型看 1–3 张图就能判断版式，
不必把十几屏逐张读一遍 —— 这是全流程里最省 token 的一步。

要点：
  * Chrome 窗口高度上限约 16384，超过会静默不出图，所以最大只试 16000。
  * 纸面背景 #f2f2ef(=242)，墨量阈值必须低于它，否则整页都算「有墨」。
  * 右下角折叠按钮是 position:fixed，贴着窗口底部，算内容高度时要排除。
"""
import argparse
import glob
import os
import subprocess
import sys

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HEIGHTS = [14000, 16000]
INK = 235
BAR_RESERVE = 190      # 底部固定按钮区高度


def shoot(html, outdir, w, h):
    for f in glob.glob(os.path.join(outdir, "raw*.png")):
        os.remove(f)
    dst = os.path.join(outdir, "raw.png")
    cmd = [CHROME, "--headless=new", "--no-sandbox", "--hide-scrollbars",
           "--force-device-scale-factor=1", "--virtual-time-budget=6000",
           "--window-size=%d,%d" % (w, h), "--screenshot=" + dst, "file://" + html]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=150)
    except subprocess.TimeoutExpired:
        pass
    return dst if os.path.exists(dst) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("-o", "--out", default="/tmp/wbs-shots")
    ap.add_argument("--width", type=int, default=1000)
    ap.add_argument("--slice", type=int, default=1300)
    ap.add_argument("--keep-all", action="store_true", help="保留全部切片（默认只留有问题的）")
    a = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        sys.exit("shoot.py: 需要 Pillow —— 用 ~/.workbuddy/binaries/python/envs/default/bin/python 跑")

    html = os.path.abspath(a.html)
    if not os.path.exists(html):
        sys.exit("找不到 %s" % html)
    outdir = os.path.abspath(a.out)
    os.makedirs(outdir, exist_ok=True)
    for f in glob.glob(os.path.join(outdir, "s*.png")):
        os.remove(f)

    raw, cut = None, False
    for h in HEIGHTS:
        raw = shoot(html, outdir, a.width, h)
        if not raw:
            sys.exit("Chrome 没出图：确认路径正确、别加 --user-data-dir、窗口高度 ≤16000")
        g = Image.open(raw).convert("L")
        px = g.load()
        W, H = g.size
        last = 0
        for y in range(H - BAR_RESERVE - 1, -1, -1):
            if min(px[x, y] for x in range(0, W, 4)) < INK:
                last = y
                break
        if last < H - 280:
            break
        cut = (h == HEIGHTS[-1])

    im = Image.open(raw).convert("RGB")
    W, H = im.size
    px = im.convert("L").load()
    content_h = min(H, last + 48)

    def ink(y0, y1):
        tot = hit = 0
        for y in range(y0, min(y1, content_h), 2):
            for x in range(0, W, 3):
                tot += 1
                if px[x, y] < INK:
                    hit += 1
        return hit / max(tot, 1)

    def right_edge(y0, y1):
        cnt = 0
        for y in range(y0, min(y1, content_h), 2):
            if min(px[x, y] for x in range(max(0, W - 7), W)) < INK:
                cnt += 1
        return cnt

    n = max(1, (content_h + a.slice - 1) // a.slice)
    rows, flags, bad = [], [], set()
    for i in range(n):
        y0, y1 = i * a.slice, min((i + 1) * a.slice, content_h)
        v, re_ = ink(y0, y1), right_edge(y0, y1)
        rows.append((i + 1, y0, y1, v, re_))
        if v < 0.004:
            bad.add(i + 1)
            flags.append("第 %d 屏（y=%d–%d）几乎空白：多余空页 / 折叠块塌了" % (i + 1, y0, y1))
        if re_ > 6:
            bad.add(i + 1)
            flags.append("第 %d 屏（y=%d）右侧贴边 %d 行：疑似横向溢出（长公式 / 表格 / 代码块）"
                         % (i + 1, y0, re_))

    band, start = [], None
    for y in range(1, content_h - 1, 10):
        has = any(px[x, y] < INK for x in range(0, W, 5))
        if not has and start is None:
            start = y
        elif has and start is not None:
            if y - start >= 500:
                band.append((start, y))
            start = None
    for y0, y1 in band:
        flags.append("空白竖带 y=%d–%d（高 %dpx）：中间有东西没渲染出来" % (y0, y1, y1 - y0))
        for i, sy0, sy1, _, _ in rows:
            if sy0 < y1 and sy1 > y0:
                bad.add(i)
    if cut:
        flags.append("内容顶到 16000px 仍没见底：可能有几百 px 被切掉，按题分两份更稳")

    keep = {1, n} | bad      # 首屏看版式、末屏看速查表，中间只看有问题的
    if a.keep_all:
        keep = set(range(1, n + 1))
    saved = []
    for i, y0, y1, _, _ in rows:
        if i not in keep:
            continue
        path = os.path.join(outdir, "s%02d.png" % i)
        im.crop((0, y0, W, y1)).save(path)
        saved.append(path)
    os.remove(raw)

    print("页面 %dx%d ｜ %d 屏 × %dpx ｜ 目录 %s" % (W, content_h, n, a.slice, outdir))
    print("墨量：" + " ".join("%d:%.1f%%" % (i, v * 100) for i, _, _, v, _ in rows))
    if flags:
        print("⚠ 需要看的：")
        for f in flags:
            print("  · " + f)
    else:
        print("✓ 无空白屏、无竖向断带、无右侧溢出")
    print("切片：" + " ".join(os.path.basename(p) for p in saved))


if __name__ == "__main__":
    main()
