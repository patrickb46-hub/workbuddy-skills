#!/usr/bin/env python3
"""抽帧雪碧图 —— 把一段视频均匀抽 N 帧拼成一张图，每帧带真实时间码。

用途：不播视频也能"看"清一段素材里发生了什么，据此写镜头表、决定剪哪段。
只读素材，输出图片到指定位置。

用法:
    python3 sheet.py <视频文件> [-n 12] [-o out.jpg] [-w 360] [-c 4]
    python3 sheet.py <目录> [-n 8]          # 批量，每段一张
"""
import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts", ".insv", ".3gp", ".wmv", ".flv", ".webm"}
FFMPEG = shutil.which("ffmpeg") or "$HOME/Desktop/Tools/AI开源工具/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "$HOME/Desktop/Tools/AI开源工具/bin/ffprobe"

FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def get_font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def duration_of(path: Path) -> float:
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return max(0.0, float(out.stdout.strip()))
    except (ValueError, subprocess.SubprocessError):
        return 0.0


def hms(sec: float) -> str:
    sec = max(0.0, float(sec))
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def grab_frame(video: Path, t: float, width: int, out: Path) -> bool:
    cmd = [
        FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
        "-frames:v", "1", "-vf", f"scale={width}:-2",
        "-y", str(out),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        return r.returncode == 0 and out.exists() and out.stat().st_size > 0
    except subprocess.SubprocessError:
        return False


def make_sheet(video: Path, n: int, out: Path, width: int, cols: int) -> Path | None:
    dur = duration_of(video)
    if dur <= 0:
        print(f"  [!] 读不出时长，跳过: {video.name}")
        return None

    # 均匀取点，避开首尾各 1.5%（片头黑场/片尾抖动）
    lo, hi = dur * 0.015, dur * 0.985
    if n == 1:
        points = [(lo + hi) / 2]
    else:
        step = (hi - lo) / (n - 1)
        points = [lo + step * i for i in range(n)]

    tmpdir = Path(tempfile.mkdtemp(prefix="sheet_"))
    frames: list[tuple[float, Path]] = []
    try:
        for t in points:
            fp = tmpdir / f"f_{len(frames):03d}.png"
            if grab_frame(video, t, width, fp):
                frames.append((t, fp))
        if not frames:
            print(f"  [!] 一帧都没抽出来: {video.name}")
            return None

        imgs = []
        for t, fp in frames:
            try:
                im = Image.open(fp).convert("RGB")
                imgs.append((t, im))
            except OSError:
                continue
        if not imgs:
            return None

        cell_w = max(im.width for _, im in imgs)
        cell_h = max(im.height for _, im in imgs)
        pad = 6
        label_h = 26
        rows = math.ceil(len(imgs) / cols)
        head_h = 34

        W = cols * cell_w + (cols + 1) * pad
        H = head_h + rows * (cell_h + label_h) + (rows + 1) * pad
        canvas = Image.new("RGB", (W, H), (18, 18, 20))
        d = ImageDraw.Draw(canvas)
        f_small = get_font(15)
        f_head = get_font(17)

        d.text((pad, 9), f"{video.name}   {hms(dur)}   {len(imgs)} 帧",
               fill=(228, 228, 232), font=f_head)

        for i, (t, im) in enumerate(imgs):
            r, c = divmod(i, cols)
            x = pad + c * (cell_w + pad)
            y = head_h + pad + r * (cell_h + label_h + pad)

            canvas.paste(im, (x, y))
            # 时间码只标在格下方，不压在画面上（压画面会遮住内容）
            stamp = f"[{i+1}] {hms(t)}"
            d.text((x + 1, y + cell_h + 4), stamp, fill=(150, 200, 255), font=f_small)

        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out, quality=88, optimize=True)
        return out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def safe_name(p: Path) -> str:
    keep = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in p.stem)
    return (keep[:60] or "video") + ".sheet.jpg"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="视频文件或目录")
    ap.add_argument("-n", "--frames", type=int, default=12, help="每段抽几帧（默认 12）")
    ap.add_argument("-o", "--out", help="输出图片路径（单文件时）")
    ap.add_argument("-O", "--outdir", help="批量输出目录（默认在源文件同级的 _sheets/）")
    ap.add_argument("-w", "--width", type=int, default=360, help="每格宽度（默认 360）")
    ap.add_argument("-c", "--cols", type=int, default=4, help="列数（默认 4）")
    args = ap.parse_args()

    target = Path(args.target).expanduser().resolve()
    if target.is_file():
        out = Path(args.out).expanduser() if args.out else target.with_name(safe_name(target))
        p = make_sheet(target, args.frames, out, args.width, args.cols)
        if p:
            print(f"已生成: {p}")
            return 0
        return 1

    if not target.is_dir():
        print(f"[!] 路径不存在: {target}", file=sys.stderr)
        return 1

    files = sorted(p for p in target.rglob("*")
                   if p.is_file() and p.suffix.lower() in VIDEO_EXT)
    if not files:
        print(f"[!] {target} 下没有视频", file=sys.stderr)
        return 2

    outdir = Path(args.outdir).expanduser() if args.outdir else target / "_sheets"
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f.name}")
        make_sheet(f, args.frames, outdir / safe_name(f), args.width, args.cols)
    print(f"\n全部完成，图片在: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
