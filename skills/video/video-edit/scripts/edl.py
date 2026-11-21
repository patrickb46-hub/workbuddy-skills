#!/usr/bin/env python3
"""按 EDL 粗剪 —— 把清单里指定的时间段截出来、可调速、统一规格、拼成一条成片。

不碰原素材，只读；所有输出写到 -o 指定位置。

EDL 格式（制表符或逗号分隔，一行一段，顺序即成片顺序）:
    文件路径<TAB>起<TAB>止<TAB>速度<TAB>备注
    速度留空或写 1 = 原速；2 = 二倍速；0.5 = 慢放一半
    第 4 列若不是数字，自动当成备注（兼容旧格式）

时间码支持: 12.5 / 12 / 00:00:12.5 / 1:02:03
以 # 开头的行是注释。

用法:
    python3 edl.py check edl.tsv              # 只校验，不转码
    python3 edl.py run edl.tsv -o out.mp4     # 正式出片
    python3 edl.py run edl.tsv -o out.mp4 --fit blur --fps 30 --lufs -16
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "$HOME/Desktop/Tools/AI开源工具/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "$HOME/Desktop/Tools/AI开源工具/bin/ffprobe"


def parse_tc(s: str) -> float:
    s = s.strip()
    if not s:
        raise ValueError("空时间码")
    if ":" in s:
        parts = [float(p) for p in s.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(s)


def hms(sec: float) -> str:
    sec = max(0.0, float(sec))
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def atempo_chain(speed: float) -> str:
    """atempo 单次只吃 0.5–2.0，超出范围要串联。"""
    parts = []
    s = speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.6f}")
    return ",".join(parts)


def media_info(path: Path) -> dict:
    cmd = [FFPROBE, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return {}
    return json.loads(out.stdout or "{}")


def read_edl(edl_path: Path) -> list[dict]:
    base = edl_path.parent
    rows = []
    for lineno, raw in enumerate(edl_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        sep = "\t" if "\t" in raw else ","
        parts = [p.strip() for p in raw.split(sep)]
        if len(parts) < 3:
            print(f"  [!] 第 {lineno} 行字段不足，跳过: {raw[:60]}")
            continue
        f, a, b = parts[0], parts[1], parts[2]
        speed, note = 1.0, ""
        rest = [p for p in parts[3:]]
        if rest:
            try:
                speed = float(rest[0])
                note = " ".join(rest[1:]).strip()
            except ValueError:
                note = " ".join(rest).strip()
        p = Path(f).expanduser()
        if not p.is_absolute():
            p = (base / p).resolve()
        try:
            start, end = parse_tc(a), parse_tc(b)
        except ValueError as e:
            print(f"  [!] 第 {lineno} 行时间码有问题（{e}），跳过")
            continue
        if speed <= 0:
            speed = 1.0
        rows.append({"line": lineno, "file": p, "start": start, "end": end,
                     "speed": speed, "note": note})
    return rows


def check(rows: list[dict]) -> list[dict]:
    ok = []
    for r in rows:
        tag = f"第{r['line']}行 {r['file'].name[:28]} {hms(r['start'])}→{hms(r['end'])}"
        if not r["file"].exists():
            print(f"  [x] {tag}: 文件不存在")
            continue
        if r["end"] <= r["start"]:
            print(f"  [x] {tag}: 止点早于起点")
            continue
        info = media_info(r["file"])
        try:
            dur = float(info.get("format", {}).get("duration", 0))
        except (TypeError, ValueError):
            dur = 0.0
        if dur and r["end"] > dur + 0.5:
            print(f"  [!] {tag}: 止点超出素材时长 {hms(dur)}，将截到片尾")
            r["end"] = dur
        r["has_audio"] = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        r["raw_duration"] = r["end"] - r["start"]
        r["duration"] = r["raw_duration"] / r["speed"]
        ok.append(r)
        sp = "" if abs(r["speed"] - 1.0) < 1e-6 else f" ×{r['speed']:g}"
        print(f"  [v] {tag}  原长 {r['raw_duration']:.1f}s{sp} → 占片 {r['duration']:.1f}s  {r['note']}")
    return ok


def video_chain(w: int, h: int, fit: str) -> str:
    """返回不含 fps 的视频滤镜链（输出标签统一为 [v]）。"""
    if fit == "cover":
        return (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1")
    if fit == "blur":
        return (f"[0:v]split[bg][fg];"
                f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"gblur=sigma=28,eq=brightness=-0.08[bgb];"
                f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
                f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")


def encode_segment(r: dict, idx: int, tmpdir: Path, args) -> Path | None:
    out = tmpdir / f"seg_{idx:03d}.mp4"
    speed = r["speed"]
    has_audio = r.get("has_audio", False)

    v = video_chain(args.w, args.h, args.fit)
    # 调速放在缩放之后、fps 归一之前：改时间戳 → 重采样到恒定帧率
    v_tail = f",setpts=PTS/{speed:.6f},fps={args.fps}[v]"

    if has_audio:
        chain = f"{atempo_chain(speed)},aresample=48000"
        if args.declick:
            # 硬切的切点会因波形突跳产生"咔"声。首尾各 25ms 淡入淡出消掉。
            # 结尾用 areverse 翻转后再淡入，这样不必预先知道片段时长。
            chain += (",afade=t=in:st=0:d=0.025,"
                      "areverse,afade=t=in:st=0:d=0.025,areverse")
        fc = f"{v}{v_tail};[0:a]{chain}[a]"
    else:
        fc = f"{v}{v_tail};[1:a]aresample=48000[a]"

    # 关键：-ss 和 -t 都必须放在 -i 之前（输入选项）。
    # -t 若放在 -i 之后会变成"输出时长上限"，把 setpts 压缩过的流又拉回原长，
    # 结果就是倍速静默失效（实测：挪前 10.0s，挪后 5.07s）。
    cmd = [FFMPEG, "-v", "error", "-stats", "-ss", f"{r['start']:.3f}",
           "-t", f"{r['raw_duration']:.3f}", "-i", str(r["file"])]
    if not has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
    cmd += [
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-shortest", "-movflags", "+faststart", "-y", str(out),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [x] 第 {idx+1} 段转码失败:\n{res.stderr[-900:]}")
        return None
    return out


def concat(parts: list[Path], out: Path, lufs: float | None, tmpdir: Path) -> bool:
    lst = tmpdir / "concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")

    base = [FFMPEG, "-v", "error", "-stats", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if lufs is None:
        cmd = base + ["-c", "copy", "-movflags", "+faststart", "-y", str(out)]
    else:
        cmd = base + ["-c:v", "copy",
                      "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
                      "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                      "-movflags", "+faststart", "-y", str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [x] 拼接失败:\n{res.stderr[-900:]}")
        return False
    return True


def report(out: Path, expected: float | None = None) -> None:
    info = media_info(out)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), {})
    dur = info.get("format", {}).get("duration", "?")
    size = out.stat().st_size / 1024 / 1024
    print(f"\n成片: {out}")
    print(f"  时长 {float(dur):.1f}s | {v.get('width')}x{v.get('height')} "
          f"| {v.get('codec_name')} | 音频 {a.get('codec_name')} "
          f"{a.get('sample_rate')}Hz {a.get('channels')}ch")
    print(f"  体积 {size:.1f} MB")
    # 倍速失效会静默出一版原长片，这里卡一道
    if expected and abs(float(dur) - expected) / expected > 0.05:
        print(f"  [!] 时长偏差过大：预期 {expected:.1f}s，实际 {float(dur):.1f}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["check", "run"])
    ap.add_argument("edl")
    ap.add_argument("-o", "--out", help="成片输出路径")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fit", choices=["pad", "cover", "blur"], default="pad",
                    help="pad=黑边; cover=裁切填满; blur=模糊背景")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--lufs", type=float, default=-16.0,
                    help="响度目标（-16 现场播放，-14 更响，-24 广播标准）")
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--no-declick", dest="declick", action="store_false",
                    help="关闭切点消爆音（默认开启，每段首尾 25ms 淡入淡出）")
    args = ap.parse_args()

    edl_path = Path(args.edl).expanduser().resolve()
    if not edl_path.exists():
        print(f"[!] EDL 不存在: {edl_path}", file=sys.stderr)
        return 1

    rows = read_edl(edl_path)
    if not rows:
        print("[!] EDL 里没有有效段落", file=sys.stderr)
        return 2

    print(f"EDL: {edl_path.name} —— {len(rows)} 段\n校验中…")
    good = check(rows)
    if not good:
        print("\n[!] 没有可用的段落", file=sys.stderr)
        return 3

    total = sum(r["duration"] for r in good)
    raw = sum(r["raw_duration"] for r in good)
    print(f"\n可用 {len(good)} 段，素材取用 {hms(raw)}，成片 {total:.1f}s ({hms(total)})")

    if args.mode == "check":
        return 0

    if not args.out:
        print("[!] run 模式需要 -o", file=sys.stderr)
        return 4
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    tmpdir = Path(tempfile.mkdtemp(prefix="edl_"))
    parts: list[Path] = []
    try:
        for i, r in enumerate(good):
            sp = "" if abs(r["speed"] - 1.0) < 1e-6 else f" ×{r['speed']:g}"
            print(f"[{i+1}/{len(good)}] {hms(r['start'])}→{hms(r['end'])}{sp}")
            p = encode_segment(r, i, tmpdir, args)
            if p is None:
                print("  中断。临时片段在:", tmpdir)
                return 5
            parts.append(p)

        print("拼接中…")
        lufs = None if args.no_loudnorm else args.lufs
        if not concat(parts, out, lufs, tmpdir):
            return 6
        report(out, total)
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
