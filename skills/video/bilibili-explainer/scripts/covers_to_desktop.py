#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""covers_to_desktop.py — 把封面按 B 站手动上传要求整理到桌面。

B 站封面编辑器要两个比例：16:9（1920×1080）和 4:3（1440×1080）。
手动上传时来回找文件很烦，这个脚本一次性摆到桌面，按 slug 命名。

重要：4:3 **不要**用 16:9 裁剪或补边得到——补边会在上下留大片空白、
裁剪会切掉标题或几何图。正确做法是给 4:3 单独排版渲染一版
（Remotion 里加一个 1440×1080 的 Cover 组合），再用 --cover43 传进来。
没有单独渲染的 4:3 时，本脚本只能退化成补边，会提示你。

用法：
  python covers_to_desktop.py --cover16 cover.png --cover43 cover43.png --slug my-video
  python covers_to_desktop.py --cover16 cover.png --slug my-video      # 4:3 退化为补边
"""
import argparse
from pathlib import Path

from PIL import Image

DESK = Path.home() / "Desktop"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cover16", required=True, help="16:9 封面（1920×1080）")
    ap.add_argument("--cover43", default="", help="单独排版渲染的 4:3 封面（1440×1080）")
    ap.add_argument("--slug", default="", help="工程 slug，用于桌面文件名")
    a = ap.parse_args()

    slug = a.slug or Path(a.cover16).resolve().parent.name
    c16 = Image.open(a.cover16).convert("RGB").resize((1920, 1080), Image.LANCZOS)
    p16 = DESK / f"封面_16x9_{slug}.png"
    c16.save(p16)
    print("16:9 →", p16)

    if a.cover43:
        c43 = Image.open(a.cover43).convert("RGB").resize((1440, 1080), Image.LANCZOS)
        note = "单独渲染"
    else:
        # 退化：等比缩到 1440 宽，上下补背景色。只作兜底，构图会显空。
        scaled = c16.resize((1440, 810), Image.LANCZOS)
        bg = c16.getpixel((4, 4))
        c43 = Image.new("RGB", (1440, 1080), bg)
        c43.paste(scaled, (0, 135))
        note = "补边兜底（建议单独渲染 4:3 重做）"

    p43 = DESK / f"封面_4x3_{slug}.png"
    c43.save(p43)
    print("4:3  →", p43, f"（{note}）")
    print(f"\n手动上传时直接用桌面这两个文件：\n  {p16.name}\n  {p43.name}")


if __name__ == "__main__":
    main()
