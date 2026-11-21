#!/bin/bash
# make_pad.sh — 合成一条中性氛围垫（drone pad），当配乐用或当混音测试素材
#
# 它是什么：几个正弦叠成的长音和弦 + 轻微失谐（产生缓慢的「呼吸」）+ 慢速起伏 + 空间感。
# 它不是什么：不是成品配乐，没有旋律、没有节奏。放在人声下面 30 dB 时，
#             作用是填掉「干声悬空」的空洞感，让片子听起来有制作感。
# 真要做有情绪的段落，还是去素材库拿真音乐（见 assets/bgm/README.md）。
#
# 用法：
#   bash make_pad.sh                          # 默认 A 小调、180 秒、-33 LUFS → assets/bgm/ambient-A.m4a
#   bash make_pad.sh --dur 240 --key C --out ~/my-pad.m4a
#   bash make_pad.sh --key A --bright         # 亮一点（多一层高频泛音）
set -u

DUR=180; KEY=A; OUT=""; BRIGHT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dur)  DUR="$2"; shift 2;;
    --key)  KEY="$2"; shift 2;;
    --out)  OUT="$2"; shift 2;;
    --bright) BRIGHT=1; shift;;
    *) echo "未知参数 $1"; exit 1;;
  esac
done
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -z "$OUT" ] && { OUT="$SELF_DIR/../assets/bgm/ambient-${KEY}.m4a"; mkdir -p "$(dirname "$OUT")"; }

BIN="$HOME/Desktop/Tools/AI开源工具/bin"
FF="$BIN/ffmpeg"; [ -x "$FF" ] || FF="$(command -v ffmpeg)"

case "$KEY" in
  A) ROOT=110.00;  CHORD="164.81 220.00 261.63 329.63";;   # A2 + E3 A3 C4 E4（A 小调）
  C) ROOT=130.81;  CHORD="196.00 261.63 329.63 392.00";;   # C3 + G3 C4 E4 G4（C 大调）
  D) ROOT=146.83;  CHORD="220.00 293.66 369.99 440.00";;   # D3 + A3 D4 F#4 A4（D 大调）
  *) echo "只支持 A / C / D"; exit 1;;
esac

# 两层根音微微失谐（差 0.4Hz）→ 缓慢拍频，听起来像「活的」
FREQS="$ROOT $(python3 -c "print($ROOT+0.4)") $CHORD"
N=$(echo $FREQS | wc -w | tr -d ' ')

FC=""; i=0
for f in $FREQS; do
  FC="${FC}[$i:a]volume=1.0[s$i];"
  i=$((i+1))
done
MIXIN=""; j=0
for f in $FREQS; do MIXIN="${MIXIN}[s$j]"; j=$((j+1)); done

# 越高的音给越小权重，避免刺；亮版把 4kHz 以上放一点回来
if [ "$BRIGHT" = "1" ]; then
  W="1 1 0.75 0.6 0.45 0.4"; POST="highpass=f=40,lowpass=f=4000"
else
  W="1 1 0.6 0.5 0.35 0.25"; POST="highpass=f=38,lowpass=f=1100"
fi

INPUTS=""
k=0
for f in $FREQS; do INPUTS="$INPUTS -f lavfi -t $DUR -i sine=frequency=$f:sample_rate=48000"; k=$((k+1)); done

# shellcheck disable=SC2086
"$FF" -y -hide_banner -loglevel error $INPUTS -filter_complex "\
$FC${MIXIN}amix=inputs=$N:weights=$W:normalize=0[raw];\
[raw]$POST,tremolo=f=0.12:d=0.35,aecho=0.8:0.85:620|1250|2100:0.35|0.22|0.12,\
aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I=-33:TP=-6:LRA=6,afade=t=in:st=0:d=3[out]" \
  -map "[out]" -t "$DUR" -c:a aac -b:a 160k "$OUT" || exit 1

echo "完成：$OUT"
"$BIN/ffprobe" -v error -show_entries format=duration,size -of default=nw=1 "$OUT"
"$FF" -hide_banner -nostats -i "$OUT" -af ebur128=peak=true -f null - 2>&1 \
  | sed -n '/Summary:/,$p' | grep -E "I:|Peak:" | sed 's/^ */   /'
