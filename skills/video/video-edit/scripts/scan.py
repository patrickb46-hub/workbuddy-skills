#!/usr/bin/env python3
"""素材体检 —— 扫描一个目录里所有视频，出一张清单 + 问题标注。

只读，不修改任何素材文件。

用法:
    python3 scan.py <素材目录> [-o 输出.md]

输出:
    - 终端表格
    - 同目录留一份 素材清单.md（若给了 -o）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts", ".insv", ".3gp", ".wmv", ".flv", ".webm"}

FFMPEG = shutil.which("ffmpeg") or "$HOME/Desktop/Tools/AI开源工具/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "$HOME/Desktop/Tools/AI开源工具/bin/ffprobe"


def hms(sec: float) -> str:
    sec = max(0.0, float(sec))
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def probe(path: Path) -> dict | None:
    cmd = [
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def analyze(path: Path) -> dict:
    info = probe(path)
    rec = {
        "file": path.name,
        "path": str(path),
        "size_mb": round(path.stat().st_size / 1024 / 1024, 1),
        "duration": 0.0,
        "w": 0, "h": 0, "fps": 0.0, "codec": "",
        "has_audio": False, "audio_ch": 0, "audio_sr": 0,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "issues": [],
        "ok": info is not None,
    }
    if not info:
        rec["issues"].append("无法解析（文件损坏或格式不支持）")
        return rec

    fmt = info.get("format", {})
    try:
        rec["duration"] = float(fmt.get("duration", 0))
    except (TypeError, ValueError):
        rec["duration"] = 0.0

    vstreams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    astreams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]

    if vstreams:
        v = vstreams[0]
        rec["w"] = int(v.get("width") or 0)
        rec["h"] = int(v.get("height") or 0)
        rec["codec"] = v.get("codec_name", "")
        # 手机竖拍常靠 rotate 元数据翻转，宽高要交换才是"实际看到的"
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                try:
                    rot = abs(int(float(sd["rotation"])))
                except (TypeError, ValueError):
                    rot = 0
        if rot in (90, 270):
            rec["w"], rec["h"] = rec["h"], rec["w"]
            rec["issues"].append(f"旋转 {rot}°（显示为竖屏）")
        rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/0"
        try:
            num, den = rate.split("/")
            rec["fps"] = round(float(num) / float(den), 2) if float(den) else 0.0
        except (ValueError, ZeroDivisionError):
            rec["fps"] = 0.0
        if rec["fps"] >= 100:
            rec["issues"].append(f"{rec['fps']:.0f}fps 高帧率（慢动作素材，需决定是否降帧）")
    else:
        rec["issues"].append("没有视频轨")

    if astreams:
        a = astreams[0]
        rec["has_audio"] = True
        rec["audio_ch"] = int(a.get("channels") or 0)
        try:
            rec["audio_sr"] = int(a.get("sample_rate") or 0)
        except (TypeError, ValueError):
            rec["audio_sr"] = 0
    else:
        rec["issues"].append("无音轨（剪辑时需补静音轨）")

    if rec["w"] and rec["h"]:
        if rec["h"] > rec["w"]:
            rec["issues"].append("竖屏素材（插入横屏成片需裁切或模糊背景）")
        if min(rec["w"], rec["h"]) < 720:
            rec["issues"].append(f"分辨率偏低 {rec['w']}x{rec['h']}（上大屏会糊）")

    if rec["duration"] > 600:
        rec["issues"].append(f"长素材 {hms(rec['duration'])}（需先拆镜头）")
    if rec["duration"] <= 0.5:
        rec["issues"].append("时长异常（可能只是封面帧）")

    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="素材目录")
    ap.add_argument("-o", "--out", help="输出 markdown 路径")
    ap.add_argument("--min-mb", type=float, default=0.5, help="忽略小于该体积的文件")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"[!] 目录不存在: {root}", file=sys.stderr)
        return 1

    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXT
        and p.stat().st_size / 1024 / 1024 >= args.min_mb
    )
    if not files:
        print(f"[!] {root} 下没找到视频文件", file=sys.stderr)
        return 2

    print(f"扫描 {root} —— 共 {len(files)} 个视频\n")
    recs = []
    total_dur = 0.0
    total_size = 0.0
    for i, f in enumerate(files, 1):
        r = analyze(f)
        recs.append(r)
        total_dur += r["duration"]
        total_size += r["size_mb"]
        flag = "OK " if not r["issues"] else "!! "
        print(f"{flag}[{i}/{len(files)}] {r['file']}  {hms(r['duration'])}  "
              f"{r['w']}x{r['h']}@{r['fps']:.0f}  {r['size_mb']}MB")
        for it in r["issues"]:
            print(f"      - {it}")

    print(f"\n合计: {len(recs)} 段 / {hms(total_dur)} / {total_size/1024:.2f} GB")

    if args.out:
        lines = [
            "# 素材清单",
            "",
            f"- 来源目录: `{root}`",
            f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"- 合计: **{len(recs)} 段 / {hms(total_dur)} / {total_size/1024:.2f} GB**",
            "",
            "| # | 文件 | 时长 | 分辨率 | 帧率 | 体积 | 拍摄/修改 | 问题 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(recs, 1):
            issues = "；".join(r["issues"]) or "—"
            lines.append(
                f"| {i} | {r['file']} | {hms(r['duration'])} | {r['w']}x{r['h']} | "
                f"{r['fps']:.0f} | {r['size_mb']}MB | {r['mtime']} | {issues} |"
            )
        Path(args.out).expanduser().write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"清单已写入: {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
