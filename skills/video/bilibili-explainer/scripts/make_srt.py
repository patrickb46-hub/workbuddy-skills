#!/usr/bin/env python3
"""make_srt.py — 从 scenes.json 生成 SRT 或 ASS 字幕，逐句与画面时间轴对齐。

为什么不用 ASR 重新对时：tts_narrate.py 已经逐句量过时长（frames/sec），
scenes.json 里的 sec 就是唯一真相。照抄它，字幕和画面天然同步。

为什么支持 ASS：SRT 没有画布尺寸，libass 会按默认 384×288 解释字号，
烧到 1080p 上要么过大换行、要么过小看不清。ASS 显式写 PlayResX/Y，
字号和边距才是像素级可控的。纯字幕版必须走 ASS。

用法：
  python make_srt.py <工程>/scenes.json -o subs.srt
  python make_srt.py <工程>/scenes.json -o subs.ass --fontsize 46 --margin-v 48
  python make_srt.py <工程>/scenes.json --gap-hold 0.3 --max-chars 18
"""
import argparse
import json
from pathlib import Path


def fmt_srt(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_ass(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFF0E6,&H00FFF0E6,&H0028160A,&H00000000,0,0,0,0,100,100,1,0,1,3,0,2,90,90,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def split_text(text: str, max_chars: int) -> list[str]:
    if not max_chars or len(text) <= max_chars:
        return [text]
    parts, buf = [], ""
    for ch in text:
        buf += ch
        if ch in "，、；,;" and len(buf) >= max_chars // 2:
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts if len(parts) > 1 else [text]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", help="scenes.json 路径")
    ap.add_argument("-o", "--out", default=None, help="输出路径（.srt 或 .ass）")
    ap.add_argument("--gap-hold", type=float, default=0.0, help="句后字幕多停留秒数")
    ap.add_argument("--max-chars", type=int, default=0, help="超此字数按标点断条（0=不断）")
    ap.add_argument("--fontsize", type=int, default=46, help="ASS 字号（1080p 建议 42–50）")
    ap.add_argument("--margin-v", type=int, default=48, help="ASS 距底像素")
    ap.add_argument("--font", default="PingFang SC", help="ASS 字体名")
    a = ap.parse_args()

    src = Path(a.scenes)
    data = json.loads(src.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    out = Path(a.out) if a.out else src.with_suffix(".srt")
    is_ass = out.suffix.lower() == ".ass"

    entries: list[tuple[float, float, str]] = []
    cur = 0.0
    for sc in scenes:
        dur = float(sc.get("sec", 0))
        text = (sc.get("tts") or "").strip()
        start = cur
        cur += dur
        if not text:
            continue
        chunks = split_text(text, a.max_chars)
        total_chars = sum(len(c) for c in chunks) or 1
        t0 = start
        for c in chunks:
            share = dur * len(c) / total_chars
            entries.append((t0, t0 + share + a.gap_hold, c))
            t0 += share

    if is_ass:
        lines = [ASS_HEADER.format(font=a.font, size=a.fontsize, mv=a.margin_v)]
        for t0, t1, c in entries:
            lines.append(f"Dialogue: 0,{fmt_ass(t0)},{fmt_ass(t1)},Default,,0,0,0,,{c}")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        blocks = []
        for i, (t0, t1, c) in enumerate(entries, 1):
            blocks.append(f"{i}\n{fmt_srt(t0)} --> {fmt_srt(t1)}\n{c}\n")
        out.write_text("\n".join(blocks), encoding="utf-8")

    print(f"字幕已生成（{'ASS' if is_ass else 'SRT'}）：{out}")
    print(f"共 {len(entries)} 条，覆盖 {cur:.2f}s（{cur / 60:.2f} 分钟）")


if __name__ == "__main__":
    main()
