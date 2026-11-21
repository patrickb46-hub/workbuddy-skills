#!/bin/bash
# mix_audio.sh — 旁白 + 配乐 混音：配乐自动「躲」人声（sidechain ducking）
#
# 为什么要 ducking：解说片的配乐不是拿来听的，是拿来「垫」的。
# 人一开口，配乐自动掉 10~15 dB；人停顿，配乐自己回来。
# 不做这一步，只能把配乐压到几乎听不见 —— 那就白加了。
#
# 用法：
#   bash mix_audio.sh --voice narration.wav --out mix.wav
#   bash mix_audio.sh --voice narration.wav --bgm bgm.mp3 --out mix.wav
#   bash mix_audio.sh --voice v.wav --bgm bgm.mp3 --bgm-lufs -30 --lufs -14 --out mix.wav
#
# 参数：
#   --voice    人声轨（打磨后的 narration.wav）
#   --bgm      配乐文件（mp3/wav/m4a/flac 都行，会自动循环/截断到人声长度）
#   --lufs     成品目标响度，默认 -16（B 站偏响可给 -14）
#   --bgm-lufs 配乐垫底响度，默认 -33（越小越退；-30 明显些，-36 几乎只留氛围）
#   --out      输出（立体声 48k WAV）
set -u

VOICE=""; BGM=""; OUT=""; LUFS=-16; BGM_LUFS=-33
while [ $# -gt 0 ]; do
  case "$1" in
    --voice)    VOICE="$2"; shift 2;;
    --bgm)      BGM="$2"; shift 2;;
    --out)      OUT="$2"; shift 2;;
    --lufs)     LUFS="$2"; shift 2;;
    --bgm-lufs) BGM_LUFS="$2"; shift 2;;
    *) echo "未知参数 $1"; exit 1;;
  esac
done
[ -z "$VOICE" ] || [ -z "$OUT" ] && { echo "必须给 --voice 和 --out"; exit 1; }
[ -f "$VOICE" ] || { echo "找不到人声轨：$VOICE"; exit 1; }
[ -n "$BGM" ] && [ ! -f "$BGM" ] && { echo "找不到配乐：$BGM"; exit 1; }

BIN="$HOME/Desktop/Tools/AI开源工具/bin"
FF="$BIN/ffmpeg"; FP="$BIN/ffprobe"
[ -x "$FF" ] || FF="$(command -v ffmpeg)"
[ -x "$FP" ] || FP="$(command -v ffprobe)"

DUR=$("$FP" -v error -show_entries format=duration -of csv=p=0 "$VOICE")
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

if [ -z "$BGM" ]; then
  echo "== 无人声配乐：只归一化 =="
  # loudnorm 内部会升到 192k 做真峰值检测，末尾必须 aformat 拽回 48k，否则成品是 192k/96k
  "$FF" -y -hide_banner -loglevel error -i "$VOICE" \
    -af "aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I=${LUFS}:TP=-1.5:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo" \
    -ar 48000 -c:a pcm_s16le "$OUT" || exit 1
else
  echo "== 1/2 配乐铺底：循环到 ${DUR}s，压到 ${BGM_LUFS} LUFS =="
  # -stream_loop -1 让短音乐也能铺满全片；afade 出入各留一点，避免硬起硬收
  FADE_OUT_ST=$(python3 -c "print(max(0, $DUR - 2.5))")
  "$FF" -y -hide_banner -loglevel error -stream_loop -1 -i "$BGM" -t "$DUR" \
    -af "aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I=${BGM_LUFS}:TP=-6:LRA=11,afade=t=in:st=0:d=1.5,afade=t=out:st=${FADE_OUT_ST}:d=2.5" \
    -c:a pcm_s16le "$TMP/bed.wav" || exit 1

  echo "== 2/2 混音：人声触发 ducking，压完再归一化 =="
  # threshold 0.02 ≈ -34 dBFS：人声一过这条线，配乐立刻退
  # attack 15ms 要快（别让人声先撞上配乐），release 400ms 要慢（别一停一顿地抽气）
  "$FF" -y -hide_banner -loglevel error -i "$VOICE" -i "$TMP/bed.wav" \
    -filter_complex "\
[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v][sc];\
[1:a][sc]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=400:makeup=1[duck];\
[v][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.9,loudnorm=I=${LUFS}:TP=-1.5:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo[out]" \
    -map "[out]" -ar 48000 -c:a pcm_s16le "$OUT" || exit 1
fi

echo "== 质检 =="
"$FF" -hide_banner -nostats -i "$OUT" -af ebur128=peak=true -f null - 2>&1 \
  | sed -n '/Summary:/,$p' | grep -E "I:|LRA:|Peak:" | sed 's/^ */   /'
echo "完成：$OUT"
