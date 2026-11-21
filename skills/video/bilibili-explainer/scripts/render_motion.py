#!/usr/bin/env python3
"""把 HTML 时间轴逐帧渲染成视频。

用法：
    python3 render.py <html> <out.mp4> <秒数> [--fps 30] [--stills 1.2,3.5]
"""
import argparse
import pathlib
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

FFMPEG = "$HOME/Desktop/Tools/AI开源工具/bin/ffmpeg"
W, H = 1920, 1080


def open_page(p, html):
    b = p.chromium.launch(channel="chrome", args=[
        "--force-color-profile=srgb", "--disable-lcd-text",
        "--hide-scrollbars", "--font-render-hinting=none",
    ])
    pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    pg.goto(pathlib.Path(html).resolve().as_uri())
    pg.wait_for_timeout(700)  # 等字体与图片
    return b, pg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("out")
    ap.add_argument("seconds", type=float)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--stills", default="")
    ap.add_argument("--audio", default="")
    ap.add_argument("--keep-frames", action="store_true")
    a = ap.parse_args()

    root = pathlib.Path(a.out).resolve().parent
    frames = root / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for f in frames.glob("*.jpg"):
        f.unlink()

    n = int(round(a.seconds * a.fps))
    t_start = time.time()
    with sync_playwright() as p:
        b, pg = open_page(p, a.html)
        err = pg.evaluate("() => { try { renderAt(0); return null } catch(e) { return String(e) } }")
        if err:
            print("JS 错误：", err)
            sys.exit(1)
        for i in range(n):
            t = i / a.fps
            pg.evaluate("t => renderAt(t)", t)
            pg.screenshot(path=str(frames / f"{i:05d}.jpg"), type="jpeg", quality=94)
            if i % 60 == 0:
                print(f"  {i}/{n}  {time.time()-t_start:.1f}s", flush=True)
        b.close()

    if a.stills:
        with sync_playwright() as p:
            b, pg = open_page(p, a.html)
            d = root / "stills"
            d.mkdir(exist_ok=True)
            for s in a.stills.split(","):
                t = float(s)
                pg.evaluate("t => renderAt(t)", t)
                pg.screenshot(path=str(d / f"still_{t:05.2f}.png"))
            b.close()
        print("静帧：", d)

    cmd = [FFMPEG, "-y", "-framerate", str(a.fps), "-i", str(frames / "%05d.jpg")]
    if a.audio:
        cmd += ["-i", str(pathlib.Path(a.audio).resolve())]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if a.audio:
        # 配乐统一压到 -16 LUFS，B 站/网页播放都不会忽大忽小
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += [a.out]
    print("编码…")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:])
        sys.exit(1)
    if not a.keep_frames:
        for f in frames.glob("*.jpg"):
            f.unlink()
    print("完成：", a.out, f"{time.time()-t_start:.1f}s")


if __name__ == "__main__":
    main()
