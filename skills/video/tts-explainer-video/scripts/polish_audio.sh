#!/bin/bash
# polish_audio.sh — 旁白人声「打磨」链：EQ + 去齿音 + 压缩 + 两遍响度归一
#
# 为什么不用 AI 模型：edge-tts 合成出来的人声本身是「干声、无底噪」，
# 缺的不是降噪，而是频响、动态和响度的一致性 —— 这正好是 DSP 最擅长的，
# CPU 上几秒钟跑完，不需要 GPU，也不需要下模型。
#
# 用法：
#   bash polish_audio.sh narration.wav                 # 输出 narration-polished.wav
#   bash polish_audio.sh in.wav out.wav --lufs -14      # 改响度目标（B 站常用 -14 ~ -16）
#   bash polish_audio.sh in.wav out.wav --denoise       # 实录人声才需要：先 afftdn 再打磨
#   bash polish_audio.sh in.wav out.wav --dry           # 试听版：只做 15 秒、导出 m4a
#
# 输出统一为 48kHz / 单声道 / 16bit PCM WAV（交付编码在合成那步再做）。
set -u

IN=""; OUT=""; LUFS=-16; DENOISE=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --lufs)    LUFS="$2"; shift 2;;
    --denoise) DENOISE=1; shift;;
    --dry)     DRY=1; shift;;
    *) if [ -z "$IN" ]; then IN="$1"; elif [ -z "$OUT" ]; then OUT="$1"; else echo "多余参数 $1"; exit 1; fi; shift;;
  esac
done
[ -z "$IN" ] && { echo "用法：polish_audio.sh in.wav [out.wav] [--lufs -16] [--denoise] [--dry]"; exit 1; }
[ -f "$IN" ] || { echo "找不到输入：$IN"; exit 1; }
IN="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"

BIN="$HOME/Desktop/Tools/AI开源工具/bin"
FF="$BIN/ffmpeg"; FP="$BIN/ffprobe"
[ -x "$FF" ] || FF="$(command -v ffmpeg)"
[ -x "$FP" ] || FP="$(command -v ffprobe)"
[ -x "$FF" ] || { echo "找不到 ffmpeg"; exit 1; }

DIR="$(dirname "$IN")"; STEM="$(basename "$IN")"; STEM="${STEM%.*}"
[ -z "$OUT" ] && OUT="$DIR/$STEM-polished.wav"
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT";; esac
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# ── 处理链（顺序有讲究：先修频响，再压齿音，最后压动态）
# 80Hz 高通  去低频轰鸣/口水音
# 280Hz -1.5 去「闷」的箱音
# 3.2kHz +1.8 提清晰度（辅音、字头靠这一段）
# 9kHz  +1.0 一点空气感，别多，多了发虚
# deesser     压掉 s / sh / c 的刺耳感
# 压缩 2.5:1 / -18dB 起 / 8ms 攻 / 180ms 放  把忽大忽小的句子压平
CHAIN="highpass=f=80:p=2"
CHAIN="$CHAIN,equalizer=f=280:t=q:w=1.2:g=-1.5"
CHAIN="$CHAIN,equalizer=f=3200:t=q:w=1.0:g=1.8"
CHAIN="$CHAIN,equalizer=f=9000:t=q:w=1.5:g=1.0"
CHAIN="$CHAIN,deesser=i=0.45:m=0.5:f=0.5:s=o"
CHAIN="$CHAIN,acompressor=threshold=0.125:ratio=2.5:attack=8:release=180:knee=6:makeup=1.6:detection=rms:mix=1"

PRE=""
if [ "$DENOISE" = "1" ]; then
  # afftdn 是纯频域降噪，零成本、任意 CPU 都能跑；实录环境底噪明显时才开，干声开了只会掉细节
  PRE="afftdn=nr=12:nf=-40:tn=1,"
fi

SEC=""
if [ "$DRY" = "1" ]; then
  OUT="${OUT%.*}-ab.m4a"
  SEC="-t 15"
fi

echo "== 1/3 处理： EQ → 去齿音 → 压缩 =="
"$FF" -y -hide_banner -loglevel error $SEC -i "$IN" \
  -af "$PRE$CHAIN,aresample=48000" -ac 1 -c:a pcm_s16le "$TMP/stage.wav" || exit 1

echo "== 2/3 响度归一： 两遍 loudnorm 到 ${LUFS} LUFS =="
M=$("$FF" -hide_banner -i "$TMP/stage.wav" -af "loudnorm=I=${LUFS}:TP=-1.5:LRA=11:print_format=json" -f null - 2>&1 \
     | sed -n '/^{/,/^}/p')
get(){ printf '%s' "$M" | tr -d ' \n' | sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p"; }
I=$(get input_i); TP=$(get input_tp); LRA=$(get input_lra); TH=$(get input_thresh); OFF=$(get target_offset)
if [ -z "${I:-}" ]; then echo "! 响度测量失败，退回单遍 loudnorm"; \
  "$FF" -y -hide_banner -loglevel error -i "$TMP/stage.wav" -af "loudnorm=I=${LUFS}:TP=-1.5:LRA=11" -ar 48000 -ac 1 "$OUT" || exit 1
else
  "$FF" -y -hide_banner -loglevel error -i "$TMP/stage.wav" \
    -af "loudnorm=I=${LUFS}:TP=-1.5:LRA=11:measured_I=${I}:measured_TP=${TP}:measured_LRA=${LRA}:measured_thresh=${TH}:offset=${OFF}:linear=true" \
    -ar 48000 -ac 1 $( [ "$DRY" = "1" ] && echo "-c:a aac -b:a 192k" || echo "-c:a pcm_s16le" ) "$OUT" || exit 1
fi

echo "== 3/3 质检 =="
"$FF" -hide_banner -nostats -i "$OUT" -af ebur128=peak=true -f null - 2>&1 \
  | sed -n '/Summary:/,$p' | grep -E "I:|LRA:|Peak:" | sed 's/^ */   /'
echo "完成：$OUT"
