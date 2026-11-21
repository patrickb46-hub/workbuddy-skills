#!/usr/bin/env python3
"""轻快电子配乐合成器 —— 100% 原创，无版权风险。

设计原则（按 bilibili-explainer/assets/bgm/README 的约束）：
  · 无人声，只有器乐
  · 120-128 BPM，律动清楚但不抢画面
  · 结尾可循环、无突兀终止感

音色全部用加法合成 + 包络做出来：铃音（marimba/bell）、拨弦（pluck）、
贝斯、软底鼓、踩镲、铺底 pad。混音走一路乒乓延迟代替混响，省算力。
"""
import numpy as np
import wave
import sys
import pathlib

SR = 48000


def env_ad(n, attack, decay, curve=3.0):
    """attack/decay 包络，length = n 采样。"""
    a = max(1, int(attack * SR))
    d = max(1, n - a)
    e = np.empty(n, dtype=np.float32)
    e[:a] = np.linspace(0, 1, a, dtype=np.float32) ** 0.6
    e[a:] = np.exp(-curve * np.linspace(0, 1, d, dtype=np.float32))
    return e


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def bell(f, dur=0.9, amp=0.5):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    x = (np.sin(2 * np.pi * f * t) * 1.0
         + np.sin(2 * np.pi * f * 2.0 * t) * 0.22
         + np.sin(2 * np.pi * f * 3.01 * t) * 0.10
         + np.sin(2 * np.pi * f * 4.16 * t) * 0.05)
    return (x * env_ad(n, 0.004, dur, 4.2) * amp).astype(np.float32)


def pluck(f, dur=0.55, amp=0.4, bright=0.55):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    x = np.zeros(n, dtype=np.float32)
    for k in range(1, 10):
        if f * k > SR / 2.2:
            break
        x += (np.sin(2 * np.pi * f * k * t) * (bright ** (k - 1)) / k ** 1.15).astype(np.float32)
    return x * env_ad(n, 0.003, dur, 5.0) * amp


def bass(f, dur=0.42, amp=0.55):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    e = env_ad(n, 0.006, dur, 3.4)
    return np.tanh(x * 1.3) * e * amp


def kick(dur=0.30, amp=0.85):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    f = 118 * np.exp(-t * 26) + 46
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t * 9.0)
    click = np.random.RandomState(3).randn(n).astype(np.float32) * np.exp(-t * 260) * 0.25
    return ((x + click) * amp).astype(np.float32)


def hat(dur=0.07, amp=0.20, seed=0):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    nz = np.random.RandomState(seed).randn(n).astype(np.float32)
    nz = np.diff(nz, prepend=0.0)  # 简陋高通
    return (nz * np.exp(-t * 70) * amp).astype(np.float32)


def pad(freqs, dur, amp=0.16):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    x = np.zeros(n, dtype=np.float32)
    for f in freqs:
        for det in (-0.12, 0.0, 0.13):
            ff = f * (1 + det / 100)
            x += np.sin(2 * np.pi * ff * t + det).astype(np.float32)
    a = int(0.35 * SR)
    e = np.ones(n, dtype=np.float32)
    aa = min(a, n // 2)
    e[:aa] = np.linspace(0, 1, aa) ** 1.4
    e[-aa:] *= np.linspace(1, 0, aa) ** 1.2
    return x * e * amp / (len(freqs) * 3)


def pingpong(x, delay=0.34, fb=0.32, mix=0.30, taps=4):
    """简易乒乓延迟，代替混响。"""
    d = int(delay * SR)
    out = np.zeros_like(x)
    tmp = x.copy()
    for i in range(1, taps + 1):
        shifted = np.zeros_like(x)
        shifted[i * d:] = tmp[: len(x) - i * d] * (fb ** i)
        out += shifted
        tmp = x
    return x + out * mix


class Track:
    def __init__(self, seconds, bpm, key=60):
        self.n = int(seconds * SR)
        self.buf = np.zeros((2, self.n), dtype=np.float32)
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.key = key

    def add(self, sig, at, pan=0.0, gain=1.0):
        i = int(at * SR)
        if i < 0 or i >= self.n:
            return
        m = min(len(sig), self.n - i)
        l = gain * (1 - max(0.0, pan)) ** 0.5
        r = gain * (1 + min(0.0, pan)) ** 0.5
        self.buf[0, i:i + m] += sig[:m] * l
        self.buf[1, i:i + m] += sig[:m] * r

    def render(self):
        x = pingpong(self.buf)
        # 软限幅 + 归一
        x = np.tanh(x * 1.05) * 0.92
        pk = np.max(np.abs(x)) or 1.0
        return x / pk * 0.89


CHORDS = {  # 级数 -> 半音偏移（相对 key）
    "I": [0, 4, 7, 11], "V": [7, 11, 14, 17], "vi": [9, 12, 16, 19], "IV": [5, 9, 12, 16],
}
PROG = ["I", "V", "vi", "IV"]


def build(seconds=32, bpm=124, key=60, variant=0):
    tr = Track(seconds, bpm, key)
    bar = tr.beat * 4
    nbar = int(seconds / bar) + 1
    rng = np.random.RandomState(7 + variant)

    # 段落划分：intro → build → main → break → outro
    for b in range(nbar):
        t0 = b * bar
        ch = PROG[b % 4]
        notes = [key + s for s in CHORDS[ch]]
        short = nbar < 12
        if b < 2:
            section = "intro"
        elif b < (3 if short else 4):
            section = "build"
        elif b >= nbar - 2:
            section = "outro"
        elif (not short) and b >= nbar - 5:
            section = "break"
        else:
            section = "main"

        g = {"intro": dict(pad=0.26, arp=0.10, bass=0.0, kick=0.0, hat=0.0, bell=0.10),
             "build": dict(pad=0.16, arp=0.20, bass=0.34, kick=0.40, hat=0.10, bell=0.0),
             "main":  dict(pad=0.10, arp=0.30, bass=0.50, kick=0.80, hat=0.15, bell=0.26),
             "break": dict(pad=0.30, arp=0.12, bass=0.0, kick=0.0, hat=0.0, bell=0.32),
             "outro": dict(pad=0.18, arp=0.26, bass=0.44, kick=0.66, hat=0.12, bell=0.24)}[section]

        # 铺底
        tr.add(pad([hz(notes[0]), hz(notes[1]), hz(notes[2])], bar * 1.02, g["pad"]), t0, 0.0)

        # 贝斯：八分音符
        if g["bass"]:
            for e in range(8):
                f = hz(notes[0] - 12 + (12 if e % 4 == 3 else 0))
                tr.add(bass(f, 0.30, g["bass"]), t0 + e * tr.beat / 2, 0.0)

        # 拨弦琶音：十六分
        pattern = [0, 2, 1, 3, 2, 0, 3, 1, 0, 2, 3, 1, 2, 0, 1, 3]
        for s_ in range(16):
            if section == "break" and s_ % 2:
                continue
            if section == "intro" and s_ % 4:
                continue
            note = notes[pattern[s_] % len(notes)] + (12 if variant and s_ % 8 in (3, 7) else 0)
            tr.add(pluck(hz(note), 0.42, g["arp"], 0.5), t0 + s_ * tr.beat / 4,
                   pan=0.35 * np.sin(s_ * 1.3))

        # 铃音旋律
        if g["bell"] and b % 2 == 0:
            mel = [notes[2] + 12, notes[1] + 12, notes[0] + 12, notes[2] + 12]
            for i, m in enumerate(mel):
                tr.add(bell(hz(m), 0.85, g["bell"]), t0 + i * tr.beat, pan=-0.25 + 0.15 * i)

        # 鼓组
        if g["kick"]:
            for k in range(4):
                if g["kick"] < 0.5 and k % 2:
                    continue
                tr.add(kick(0.28, g["kick"]), t0 + k * tr.beat, 0.0)
        if g["hat"]:
            for h in range(8):
                tr.add(hat(0.06, g["hat"] if h % 2 else g["hat"] * 0.6, seed=b * 8 + h),
                       t0 + h * tr.beat / 2, 0.15)

    # 进入主歌前一小节的上升噪声
    for at in (2 * bar, bar * (nbar - 2)):
        dur = bar * 0.95
        n = int(dur * SR)
        nz = np.random.RandomState(11).randn(n).astype(np.float32)
        nz = np.diff(nz, prepend=0.0) * (np.linspace(0, 1, n) ** 2.4) * 0.22
        tr.add(nz, at, 0.0)

    # 结尾长音，接缝柔和
    tr.add(pad([hz(key + s) for s in CHORDS["I"]], 2.4, 0.30), seconds - 2.2, 0.0)
    tr.add(bell(hz(key + 24), 1.8, 0.26), seconds - 2.1, 0.0)

    return tr.render()


def save(path, x, fade=0.35):
    n = x.shape[1]
    f = int(fade * SR)
    env = np.ones(n, dtype=np.float32)
    env[:f] = np.linspace(0, 1, f) ** 1.5
    env[-f:] *= np.linspace(1, 0, f) ** 1.2
    y = (np.clip(x * env, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(y.T.tobytes())
    print("  →", path, "%.1fs" % (n / SR))


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    jobs = [("bgm-agentbar.wav", 26, 124, 60, 0),
            ("bgm-skills.wav", 22, 126, 67, 1),
            ("bgm-dsh.wav", 20, 120, 62, 2)]
    for name, sec, bpm, key, v in jobs:
        print(f"{name}  {bpm}BPM  {sec}s")
        save(out / name, build(sec, bpm, key, v))
