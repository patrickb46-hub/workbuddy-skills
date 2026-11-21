#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr.py — 用 macOS Vision 把整页照片转成「带坐标的文字」，给读图做导航。

  ocr.py a.jpg b.jpg            # 每页一行文字，前面是纵坐标，用来定位
  ocr.py a.jpg --find 第3题      # 直接给出这一行在哪，并打印可粘贴的 crop 命令
  ocr.py a.jpg --json           # 机读

定位用途（省 token）：先用它拿到「第 3 题在 y≈1180」这种坐标，再 crop 一次，
就不用 lines/grid 反复试比例了。纯文字页（英语阅读、语文）可以直接读文本，
不必整页读图。

**它不是权威文本**：数字、上下标、数学符号（△ ∠ ⊥ 平方）容易认错，
凡是要写进全解的题干数值，必须回原图 crop 核对。
"""
import argparse
import json
import sys
import time


def load(path):
    import Quartz
    from Foundation import NSURL
    url = NSURL.fileURLWithPath_(path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        raise RuntimeError("读不了这张图：%s" % path)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    return img, Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)


def ocr(path, langs):
    import Vision
    img, W, H = load(path)
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)              # accurate
    req.setRecognitionLanguages_(langs)
    req.setUsesLanguageCorrection_(True)
    h.performRequests_error_([req], None)
    rows = []
    for o in (req.results() or []):
        cand = o.topCandidates_(1)
        if not cand:
            continue
        txt = cand[0].string()
        bb = o.boundingBox()
        x0 = bb.origin.x * W
        y0 = (1 - bb.origin.y - bb.size.height) * H
        rows.append({"x": int(x0), "y": int(y0),
                     "w": int(bb.size.width * W), "h": int(bb.size.height * H),
                     "t": txt})
    rows.sort(key=lambda r: (r["y"], r["x"]))
    return rows, W, H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--find", help="只找含这个词的行，并给出 crop 参数")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lang", default="zh-Hans,en-US")
    ap.add_argument("--merge", type=float, default=0.75,
                    help="纵向间距小于行高的这个倍数就并成同一段（默认 0.75）")
    a = ap.parse_args()

    try:
        import Vision  # noqa: F401
        import Quartz  # noqa: F401
    except ImportError:
        sys.exit("ocr.py 需要 pyobjc：用 ~/.workbuddy/binaries/python/envs/default/bin/python 跑")

    langs = [x.strip() for x in a.lang.split(",") if x.strip()]
    allout = []
    for path in a.paths:
        t0 = time.time()
        try:
            rows, W, H = ocr(path, langs)
        except Exception as e:
            print("! %s：%s" % (path, e))
            continue
        ms = int((time.time() - t0) * 1000)

        if a.find:
            hits = [r for r in rows if a.find in r["t"]]
            if a.json:
                allout.append({"path": path, "size": [W, H], "hits": hits})
                continue
            print("== %s  %dx%d" % (path, W, H))
            if not hits:
                print("  没找到「%s」；最接近的几行：" % a.find)
                for r in rows[:0]:
                    pass
                continue
            for r in hits:
                y0 = max(0, r["y"] - 24)
                hh = r["h"] + 48
                print("  y=%d  x=%d  %s" % (r["y"], r["x"], r["t"]))
                print("    crop --box 0,%d,%d,%d --to-width 2000" % (y0, W, hh))
                print("    crop --rel 0,%.3f,1.0,%.3f --to-width 2000"
                      % (y0 / H, (y0 + hh) / H))
            continue

        if a.json:
            allout.append({"path": path, "size": [W, H], "lines": rows})
            continue

        print("== %s  %dx%d  %d 行  %dms" % (path, W, H, len(rows), ms))
        prev = None
        for r in rows:
            gap = "" if prev is None else ("·" if r["y"] - prev < r["h"] * a.merge else "")
            print("  [%5d]%s %s" % (r["y"], gap, r["t"]))
            prev = r["y"] + r["h"]
        print()

    if a.json:
        print(json.dumps(allout, ensure_ascii=False))


if __name__ == "__main__":
    main()
