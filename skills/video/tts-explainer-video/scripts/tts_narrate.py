#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tts_narrate.py — 逐句配音 → 量真实时长 → 拼整轨旁白 → 输出 timing.ts

设计要点（别改坏）：
  * 每句单独合成，量出真实时长，再换算成帧数 frames = round((时长 + gap) * fps)。
  * 拼整轨时按 frames 补静音 / 截尾，让音画天然对齐，不需要手工估时。
  * timing.ts 里的 frames 供 Remotion 决定每个 Scene 的时长。

用法
  python3 tts_narrate.py script.txt                       # 一行一句旁白
  python3 tts_narrate.py script.json --voice E            # [{"id":"s1","tts":"..."}]
  python3 tts_narrate.py script.txt --voice B --rate -8%

音色
  B = zh-CN-XiaoxiaoNeural  晓晓，女，温和，科普默认
  E = zh-CN-XiaoyiNeural    晓伊，女，活泼一点
  也可直接传完整 id，如 zh-CN-YunjianNeural
"""
import argparse, asyncio, json, os, subprocess, sys, wave, array

VOICES = {
    "B": ("zh-CN-XiaoxiaoNeural", "晓晓 · 女 · 温和，科普默认"),
    "E": ("zh-CN-XiaoyiNeural", "晓伊 · 女 · 活泼"),
    "C": ("zh-CN-YunjianNeural", "云健 · 男 · 纪录片解说感"),
    "D": ("zh-CN-YunxiNeural", "云希 · 男 · 年轻"),
}
FFMPEG_CANDIDATES = [
    os.path.expanduser("~/Desktop/Tools/AI开源工具/bin/ffmpeg"),
    "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg",
]


def find_ffmpeg():
    for p in FFMPEG_CANDIDATES:
        if os.path.exists(p):
            return p
    from shutil import which
    p = which("ffmpeg")
    if not p:
        sys.exit("找不到 ffmpeg")
    return p


def dur_of(path):
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def load_lines(path):
    """支持 .json（[{id,tts}]）和纯文本（一行一句，空行忽略）"""
    with open(path, encoding="utf-8") as f:
        raw = f.read().strip()
    if path.endswith(".json"):
        data = json.loads(raw)
        return [(d.get("id") or f"s{i+1}", d["tts"]) for i, d in enumerate(data)]
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append((f"s{len(out)+1}", line))
    return out


def synth_edge(text, out_mp3, voice, rate, tries=3):
    import edge_tts
    last = None
    for _ in range(tries):
        try:
            async def go():
                await edge_tts.Communicate(text, voice, rate=rate).save(out_mp3)
            asyncio.run(go())
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 2000:
                return True
        except Exception as e:
            last = e
    print("  ! edge-tts 失败：", last, file=sys.stderr)
    return False


def synth_piper(text, out_wav):
    piper = os.path.expanduser("~/Desktop/Tools/AI开源工具/OpenMontage/.venv/bin/piper")
    pm = os.path.expanduser("~/Desktop/Tools/AI开源工具/piper-models")
    if not os.path.exists(piper):
        return False
    txt = out_wav + ".txt"
    with open(txt, "w") as f:
        f.write(text)
    r = subprocess.run([piper, "-m", f"{pm}/zh_CN-huayan-medium.onnx",
                        "-c", f"{pm}/zh_CN-huayan-medium.onnx.json",
                        "-i", txt, "-f", out_wav], capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(out_wav)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", help="script.txt 或 script.json")
    ap.add_argument("--voice", default="B", help="B / E / C / D 或完整音色 id")
    ap.add_argument("--rate", default="-6%", help="相对语速，负值放慢；-6%% ≈ 4.1 字/秒")
    ap.add_argument("--gap", type=float, default=0.60, help="句间留白秒数")
    ap.add_argument("--tail", type=float, default=1.30, help="片尾静默秒数")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", default=".", help="输出目录（工程根）")
    ap.add_argument("--piper", action="store_true", help="强制用离线 Piper（语速偏快，自然度低）")
    a = ap.parse_args()

    voice_id = VOICES.get(a.voice, (a.voice, ""))[0]
    out = os.path.abspath(a.out)
    nd = os.path.join(out, "narration")
    os.makedirs(nd, exist_ok=True)
    ff = find_ffmpeg()
    lines = load_lines(a.script)
    if not lines:
        sys.exit("脚本里没有旁白")

    scenes = []
    for idx, (sid, text) in enumerate(lines):
        stem = f"{idx+1:02d}"
        mp3, wav, out48 = (os.path.join(nd, stem + s) for s in ("-raw.mp3", "-raw.wav", ".wav"))
        src = None
        if not a.piper and synth_edge(text, mp3, voice_id, a.rate):
            src = mp3
        if src is None and synth_piper(text, wav):
            src = wav
        if src is None:
            sys.exit(f"第 {idx+1} 句合成失败：{text[:16]}")
        subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", src, "-ar", "48000", "-ac", "1", out48], check=True)
        d = dur_of(out48)
        frames = int(round((d + a.gap) * a.fps))
        scenes.append({"id": sid, "tts": text, "audio": os.path.basename(out48),
                       "audio_sec": round(d, 3), "frames": frames,
                       "sec": round(frames / a.fps, 3),
                       "chars_per_sec": round(len(text) / d, 1) if d else 0})
        cps = len(text) / d if d else 0
        flag = "  ← 偏快，考虑 --rate -10%" if cps > 4.8 else ""
        print(f"{sid:4s} {d:6.2f}s {frames:5d}f  {cps:.1f} 字/秒{flag}")

    total = sum(s["frames"] for s in scenes) + int(round(a.tail * a.fps))
    with open(os.path.join(out, "scenes.json"), "w", encoding="utf-8") as f:
        json.dump({"fps": a.fps, "total": total, "voice": voice_id,
                   "rate": a.rate, "gap": a.gap, "scenes": scenes},
                  f, ensure_ascii=False, indent=2)

    # 拼整轨：每句按自己的帧数对齐
    SR = 48000
    merged = array.array("h")
    for s in scenes:
        with wave.open(os.path.join(nd, s["audio"])) as w:
            data = array.array("h", w.readframes(w.getnframes()))
        target = int(round(s["frames"] / a.fps * SR))
        if len(data) > target:
            data = data[:target]
        merged.extend(data)
        pad = target - len(data)
        if pad > 0:
            merged.extend(array.array("h", [0]) * pad)
    merged.extend(array.array("h", [0]) * int(round(a.tail * SR)))
    with wave.open(os.path.join(out, "narration.wav"), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(merged.tobytes())

    ts = ["// 由 tts_narrate.py 自动生成，勿手改",
          f"export const FPS = {a.fps};", f"export const TOTAL_FRAMES = {total};",
          "export const SCENES = ["]
    for s in scenes:
        ts.append('  { id: %s, frames: %d, audioSec: %.3f },'
                  % (json.dumps(s["id"]), s["frames"], s["audio_sec"]))
    ts.append("] as const;")
    with open(os.path.join(out, "timing.ts"), "w", encoding="utf-8") as f:
        f.write("\n".join(ts) + "\n")

    print(f"\n音色 {voice_id} ｜ 总长 {total} 帧 = {total/a.fps:.1f}s")
    print(f"输出：narration.wav / timing.ts / scenes.json  ->  {out}")
    print("下一步：把 timing.ts 拷进 Remotion 的 src/，再跑 scripts/build_video.sh")


if __name__ == "__main__":
    main()
