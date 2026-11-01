#!/bin/bash
# build_video.sh — 渲染 Remotion 画面 + 合成配音 + 质检
#
# 用法：
#   bash build_video.sh --project ~/Desktop/x/my-video --comp MyVideo
#
# 可选：
#   --entry src/dv-index.tsx     Remotion 入口（默认 src/dv-index.tsx）
#   --remotion <dir>             Remotion 工程目录（默认 OpenMontage 的 remotion-composer）
#   --qc                         额外抽 3 帧到 qc/ 供肉眼检查
#   --no-polish                  跳过人声打磨（默认会跑 polish_audio.sh）
#   --bgm <文件|auto|none>       配乐；默认 auto = 从 assets/bgm/ 随机挑一条，没有则静默跳过
#   --bgm-lufs -33               配乐垫底响度（越小越退；-30 明显些，-36 几乎只留氛围）
#   --skip-render                复用已有的 render/silent.mp4，只重做音频（调音时省 3-6 分钟）
#
# 为什么每一步都这么写，见 SKILL.md 的「踩坑」一节。
set -u

PROJECT=""; COMP=""; ENTRY="src/dv-index.tsx"; DO_QC=0; POLISH=1; NO_RENDER=0
BGM="auto"; BGM_LUFS=-33
REMOTION="$HOME/Desktop/Tools/AI开源工具/OpenMontage/remotion-composer"

while [ $# -gt 0 ]; do
  case "$1" in
    --project)  PROJECT="$2"; shift 2;;
    --comp)     COMP="$2"; shift 2;;
    --entry)    ENTRY="$2"; shift 2;;
    --remotion) REMOTION="$2"; shift 2;;
    --qc)       DO_QC=1; shift;;
    --no-polish) POLISH=0; shift;;
    --bgm)      BGM="$2"; shift 2;;
    --bgm-lufs) BGM_LUFS="$2"; shift 2;;
    --no-bgm)   BGM="none"; shift;;
    --skip-render) NO_RENDER=1; shift;;
    *) echo "未知参数 $1"; exit 1;;
  esac
done

[ -z "$PROJECT" ] || [ -z "$COMP" ] && { echo "必须给 --project 和 --comp"; exit 1; }
PROJECT="${PROJECT/#\~/$HOME}"
[ -d "$REMOTION" ] || { echo "找不到 Remotion 工程：$REMOTION"; exit 1; }
[ -f "$PROJECT/timing.ts" ] || { echo "找不到 $PROJECT/timing.ts，先跑 tts_narrate.py"; exit 1; }

BIN_TOOLS="$HOME/Desktop/Tools/AI开源工具/bin"
FF="$BIN_TOOLS/ffmpeg"; PROBE="$BIN_TOOLS/ffprobe"
[ -x "$FF" ] || FF="$(command -v ffmpeg)"
[ -x "$PROBE" ] || PROBE="$(command -v ffprobe)"

export PATH="$BIN_TOOLS:/usr/local/bin:/usr/bin:/bin"

# 1) 时长表必须和工程里的同步
cp "$PROJECT/timing.ts" "$REMOTION/src/timing.ts" || exit 1

# 2) 渲染（无音轨）
if [ "$NO_RENDER" = "1" ]; then
  [ -f "$PROJECT/render/silent.mp4" ] || { echo "没有 render/silent.mp4，不能 --skip-render"; exit 1; }
  echo "== 跳过渲染，复用 render/silent.mp4 =="
else
  cd "$REMOTION" || exit 1
  echo "== 渲染中（1080p，帧数多时 3-6 分钟）=="
  # ⚠️ 必须 env -u NODE_OPTIONS，否则打包阶段报 EEXIST / broker policy error
  env -u NODE_OPTIONS npx remotion render "$ENTRY" "$COMP" \
    "$PROJECT/render/silent.mp4" --codec h264 --concurrency 2 || exit 1
fi

# 3) 人声打磨 + 配乐混音 + 合成
mkdir -p "$PROJECT/render"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
NARR="$PROJECT/narration.wav"
if [ "$POLISH" = "1" ] && [ -f "$NARR" ]; then
  echo "== 人声打磨（EQ / 去齿音 / 压缩 / 两遍响度归一）=="
  if bash "$SELF_DIR/polish_audio.sh" "$NARR" "$PROJECT/render/narration-polished.wav" --lufs -16; then
    NARR="$PROJECT/render/narration-polished.wav"
  else
    echo "! 打磨失败，退回原始旁白"
  fi
fi

# 配乐：auto 时从 assets/bgm/ 随机挑一条。优先用真音乐（ambient-* 是合成垫音，只当兜底）
if [ "$BGM" = "auto" ]; then
  BGM_DIR="$SELF_DIR/../assets/bgm"
  pick() { awk 'BEGIN{srand()} {a[NR]=$0} END{if(NR>0) print a[int(rand()*NR)+1]}'; }
  REAL=$(find "$BGM_DIR" -maxdepth 1 -type f \( -iname "*.mp3" -o -iname "*.m4a" -o -iname "*.wav" -o -iname "*.flac" -o -iname "*.aac" -o -iname "*.ogg" \) 2>/dev/null \
         | grep -v '/ambient-' | pick)
  if [ -n "$REAL" ]; then
    BGM="$REAL"
  else
    BGM=$(find "$BGM_DIR" -maxdepth 1 -type f \( -iname "*.mp3" -o -iname "*.m4a" -o -iname "*.wav" -o -iname "*.flac" -o -iname "*.aac" -o -iname "*.ogg" \) 2>/dev/null | pick)
  fi
  if [ -n "$BGM" ]; then echo "== 配乐：$(basename "$BGM") =="; else echo "-- assets/bgm/ 里没有音乐，本条无配乐 --"; fi
fi
[ "$BGM" = "none" ] && BGM=""

echo "== 混音（配乐自动躲人声）=="
if [ -n "$BGM" ]; then
  bash "$SELF_DIR/mix_audio.sh" --voice "$NARR" --bgm "$BGM" \
    --bgm-lufs "$BGM_LUFS" --lufs -16 --out "$PROJECT/render/mix.wav" || exit 1
else
  bash "$SELF_DIR/mix_audio.sh" --voice "$NARR" \
    --bgm-lufs "$BGM_LUFS" --lufs -16 --out "$PROJECT/render/mix.wav" || exit 1
fi

echo "== 合成音轨 =="
"$FF" -y -hide_banner -loglevel error -i "$PROJECT/render/silent.mp4" -i "$PROJECT/render/mix.wav" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest "$PROJECT/out.mp4" || exit 1

# 4) 质检
echo "== 质检 =="
"$PROBE" -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,nb_frames -of default=nw=1 "$PROJECT/out.mp4"
"$FF" -hide_banner -i "$PROJECT/out.mp4" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"

if [ "$DO_QC" = "1" ]; then
  mkdir -p "$PROJECT/qc"
  TOTAL=$("$PROBE" -v error -select_streams v -show_entries stream=nb_frames -of csv=p=0 "$PROJECT/out.mp4")
  MID=$((TOTAL / 2)); LAST=$((TOTAL - 3))
  # 注意：select 按 n 升序输出，输出顺序 ≠ 书写顺序
  "$FF" -y -hide_banner -loglevel error -i "$PROJECT/out.mp4" \
    -vf "select='eq(n\,20)+eq(n\,$MID)+eq(n\,$LAST)'" -fps_mode passthrough "$PROJECT/qc/chk-%d.png"
  echo "已抽 3 帧：$PROJECT/qc/chk-1.png(第20帧) chk-2.png(中间) chk-3.png(倒数第3帧)"
  echo "必看：末帧不能是纯背景（空白拖尾）"
fi

echo "完成：$PROJECT/out.mp4"
