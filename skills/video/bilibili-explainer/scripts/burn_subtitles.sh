#!/bin/bash
# burn_subtitles.sh — 给无声画面烧字幕 + 铺配乐，出「纯字幕 + 配乐」版
#
# 为什么字幕要烧进画面而不是外挂 SRT：
#   B 站外挂字幕要单独上传、审核、还可能被观众关掉；
#   这一版是「纯字幕承载信息」，字幕本身就是主要内容，必须烧死。
#
# 为什么用 ffmpeg 而不是回 Remotion 重渲：
#   silent.mp4 已经渲染好了，烧字幕 + 混音是纯后期，秒级完成；
#   回 Remotion 加字幕层要再跑一遍 3–6 分钟渲染，不值得。
#
# 用法：
#   bash burn_subtitles.sh --video silent.mp4 --srt subs.srt --out out-subtitled.mp4
#   bash burn_subtitles.sh --video silent.mp4 --srt subs.srt --bgm bgm.m4a --out out-subtitled.mp4
#
# 可选：
#   --fontsize 32        字幕字号（1080p 建议 30–36）
#   --margin-v 58        距底部像素
#   --font "PingFang SC" 字体名（必须系统里有；找不到会退成默认字体）
#   --lufs -16           成品响度
set -u

VIDEO=""; SRT=""; BGM=""; OUT=""
FONTSIZE=32; MARGINV=58; FONT="PingFang SC"; LUFS=-16
FONTDIR="/System/Library/Fonts"

while [ $# -gt 0 ]; do
  case "$1" in
    --video)    VIDEO="$2"; shift 2;;
    --srt)      SRT="$2"; shift 2;;
    --bgm)      BGM="$2"; shift 2;;
    --out)      OUT="$2"; shift 2;;
    --fontsize) FONTSIZE="$2"; shift 2;;
    --margin-v) MARGINV="$2"; shift 2;;
    --font)     FONT="$2"; shift 2;;
    --lufs)     LUFS="$2"; shift 2;;
    *) echo "未知参数 $1"; exit 1;;
  esac
done

[ -z "$VIDEO" ] || [ -z "$SRT" ] || [ -z "$OUT" ] && {
  echo "必须给 --video、--srt、--out"; exit 1; }
[ -f "$VIDEO" ] || { echo "找不到视频：$VIDEO"; exit 1; }
[ -f "$SRT" ]   || { echo "找不到字幕：$SRT"; exit 1; }

BIN="$HOME/Desktop/Tools/AI开源工具/bin"
FF="$BIN/ffmpeg"; FP="$BIN/ffprobe"
[ -x "$FF" ] || FF="$(command -v ffmpeg)"
[ -x "$FP" ] || FP="$(command -v ffprobe)"
[ -x "$FF" ] || { echo "找不到 ffmpeg"; exit 1; }

DUR=$("$FP" -v error -show_entries format=duration -of csv=p=0 "$VIDEO")
echo "== 画面时长 ${DUR}s =="

# 字幕样式：navy 底用浅蓝白字、2px 深蓝描边
# ASS 颜色是 &HAABBGGRR：#E6F0FF -> FFF0E6；#0A1628 -> 28160A
STYLE="FontName=${FONT},Fontsize=${FONTSIZE},PrimaryColour=&H00FFF0E6,OutlineColour=&H0028160A,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=${MARGINV}"
case "$SRT" in
  *.ass|*.ASS)
    # ASS 自带 PlayResX/Y 与完整样式，不要再叠 force_style，否则字号会被二次解释
    SUB_FILTER="subtitles=${SRT}:fontsdir=${FONTDIR}"
    ;;
  *)
    SUB_FILTER="subtitles=${SRT}:fontsdir=${FONTDIR}:force_style='${STYLE}'"
    ;;
esac

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

echo "== 1/2 烧字幕（libass · ${FONT} ${FONTSIZE}px）=="
if [ -z "$BGM" ]; then
  "$FF" -y -hide_banner -loglevel error -i "$VIDEO" \
    -vf "$SUB_FILTER" -c:v libx264 -crf 18 -pix_fmt yuv420p -an "$OUT" || exit 1
else
  [ -f "$BGM" ] || { echo "找不到配乐：$BGM"; exit 1; }
  echo "== 2/2 铺配乐（循环 + 淡入淡出 + 响度归一）=="
  FADE_OUT_ST=$(python3 -c "print(max(0, $DUR - 3.0))")
  "$FF" -y -hide_banner -loglevel error \
    -i "$VIDEO" -stream_loop -1 -i "$BGM" -t "$DUR" \
    -filter_complex "\
[0:v]${SUB_FILTER}[v];\
[1:a]aformat=sample_rates=48000:channel_layouts=stereo,\
loudnorm=I=-28:TP=-6:LRA=11,\
afade=t=in:st=0:d=2.0,afade=t=out:st=${FADE_OUT_ST}:d=3.0[a]" \
    -map "[v]" -map "[a]" \
    -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k "$OUT" || exit 1
fi

echo "== 质检 =="
"$FP" -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height -of default=nw=1 "$OUT"
"$FF" -hide_banner -nostats -i "$OUT" -af ebur128=peak=true -f null - 2>&1 \
  | sed -n '/Summary:/,$p' | grep -E "I:|Peak:" | sed 's/^ */   /'
echo "完成：$OUT"
