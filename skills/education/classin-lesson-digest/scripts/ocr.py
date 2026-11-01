#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量 OCR：用 macOS 自带 Vision 框架识别图片文字，完全离线。

用法：
    python3 ocr.py <目录或图片…> [--json out.json] [--langs zh-Hans,en-US]
                   [--level accurate|fast] [--min-conf 0.2] [--quiet]

输出：
    stdout 打印按图片分块的纯文本（方便直接阅读），--json 另存结构化结果。
    结构化结果：{"generated_at":..., "images":[{"file","width","height","text","lines":[...]}]}

依赖：pyobjc-framework-Vision（已随 ClassIn 笔记助手装好）
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic", ".webp", ".pdf"}


def _iter_files(targets):
    out = []
    for t in targets:
        p = Path(os.path.expanduser(t))
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.suffix.lower() in IMG_EXT and not f.name.startswith("."):
                    out.append(f)
        elif p.exists():
            out.append(p)
        else:
            print("[warn] 找不到 %s" % p, file=sys.stderr)
    return out


def ocr_image(path, langs, level="accurate", min_conf=0.2):
    import Vision
    from Foundation import NSURL
    import Quartz

    url = NSURL.fileURLWithPath_(str(path))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        raise RuntimeError("读不了这张图（格式不支持？）")
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(
        Vision.VNRequestTextRecognitionLevelAccurate if level == "accurate"
        else Vision.VNRequestTextRecognitionLevelFast)
    req.setRecognitionLanguages_(langs)
    req.setUsesLanguageCorrection_(True)
    # 中文竖排/繁体也算上
    try:
        req.setAutomaticallyDetectsLanguage_(True)
    except Exception:
        pass

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError("OCR 失败：%s" % err)

    obs_list = req.results() or []
    rows = []
    for obs in obs_list:
        cands = obs.topCandidates_(1)
        if not cands:
            continue
        c = cands[0]
        conf = float(c.confidence())
        if conf < min_conf:
            continue
        bb = obs.boundingBox()
        x = float(bb.origin.x)
        y = float(bb.origin.y)          # Vision 原点在左下
        w = float(bb.size.width)
        h = float(bb.size.height)
        rows.append({"text": str(c.string()), "conf": round(conf, 3),
                     "x": round(x, 4), "y": round(y, 4),
                     "w": round(w, 4), "h": round(h, 4)})

    # 自上而下、同一行内自左向右
    rows.sort(key=lambda r: (-round(r["y"], 2), r["x"]))

    # 把 y 接近的碎片并成一行，行内按 x 拼接
    lines, cur, cur_y = [], [], None
    for r in rows:
        if cur_y is None or abs(r["y"] - cur_y) <= 0.012:
            cur.append(r)
            cur_y = r["y"] if cur_y is None else (cur_y + r["y"]) / 2
        else:
            lines.append(sorted(cur, key=lambda x: x["x"]))
            cur, cur_y = [r], r["y"]
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x"]))

    text_lines = []
    for ln in lines:
        s = ""
        prev_end = None
        for piece in ln:
            if prev_end is not None and piece["x"] - prev_end > 0.012:
                s += " "
            s += piece["text"]
            prev_end = piece["x"] + piece["w"]
        s = s.strip()
        if s:
            text_lines.append(s)
    return "\n".join(text_lines), rows


def main():
    ap = argparse.ArgumentParser(description="macOS Vision 批量 OCR")
    ap.add_argument("targets", nargs="+", help="目录或图片路径")
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--langs", default="zh-Hans,en-US")
    ap.add_argument("--level", default="accurate", choices=["accurate", "fast"])
    ap.add_argument("--min-conf", type=float, default=0.2)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    files = _iter_files(args.targets)
    if not files:
        print("没有可识别的图片", file=sys.stderr)
        return 2

    langs = [x.strip() for x in args.langs.split(",") if x.strip()]
    result = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
              "langs": langs, "images": []}

    for f in files:
        try:
            text, rows = ocr_image(f, langs, args.level, args.min_conf)
            size = (0, 0)
            try:
                from PIL import Image
                with Image.open(f) as im:
                    size = im.size
            except Exception:
                pass
            result["images"].append({"file": f.name, "path": str(f),
                                     "width": size[0], "height": size[1],
                                     "text": text, "lines": rows})
            if not args.quiet:
                print("===== %s =====" % f.name)
                print(text if text.strip() else "（没识别到文字）")
                print()
        except Exception as e:
            print("[error] %s: %s" % (f.name, e), file=sys.stderr)
            result["images"].append({"file": f.name, "path": str(f),
                                     "error": str(e), "text": ""})

    if args.json_out:
        outp = Path(os.path.expanduser(args.json_out))
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
        if not args.quiet:
            print("结构化结果 → %s" % outp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
