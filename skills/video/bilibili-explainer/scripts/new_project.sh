#!/bin/bash
# new_project.sh — 建一个标准的科普短片工程骨架
#
# 用法：
#   bash new_project.sh mc-launcher-ban
#   bash new_project.sh mc-launcher-ban --title "PCL 关闭下载"
#
# 产物固定落在 ~/BilibiliVideos/<slug>/
set -eu

ROOT="${BILIBILI_VIDEOS_ROOT:-$HOME/BilibiliVideos}"
SKILL="$HOME/.workbuddy/skills/bilibili-explainer"

SLUG="${1:-}"
shift || true
TITLE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --title) TITLE="$2"; shift 2;;
    *) echo "未知参数：$1"; exit 1;;
  esac
done

if [ -z "$SLUG" ]; then
  echo "用法：bash new_project.sh <slug> [--title \"标题\"]"
  echo "  slug 用英文短横线，如 mc-launcher-ban / aero-lift-explained"
  exit 1
fi

DIR="$ROOT/$SLUG"
if [ -d "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null || true)" ]; then
  echo "目录已存在且非空：$DIR"
  echo "想重来先手动清空或换个 slug。"
  exit 1
fi

mkdir -p "$DIR"/{narration,render,qc}

# 画面源码
cp "$SKILL/assets/SceneKit.tsx" "$DIR/SceneKit.tsx"

# 旁白稿骨架
cat > "$DIR/script.json" <<'JSON'
[
  {"id": "s1", "tts": "在这里写第一句旁白，一句一行，每句不超过二十五个字"},
  {"id": "s2", "tts": "同一个 id 的多句会合并进同一场，画面不切，旁白连读"}
]
JSON

# 事实表骨架
cat > "$DIR/sources.md" <<MD
# 事实表 · ${TITLE:-$SLUG}

> 写稿前必须先填这张表。填不满，说明还没到能写稿的程度。

## 已证实（一手来源）

| # | 事实 | 来源 | 时间 |
|---|---|---|---|
| 1 |  |  |  |

## 待核实（单一信源 / 社群转述）

| # | 说法 | 传播范围 | 为什么不能当事实 |
|---|---|---|---|
| 1 |  |  |  |

## 已证伪

| # | 错误说法 | 反证 |
|---|---|---|
| 1 |  |  |

## 数据口径

- 时间统一用北京时间
- 版本号照抄发布页
MD

# 分镜表骨架
cat > "$DIR/分镜脚本.md" <<MD
# 分镜脚本 · ${TITLE:-$SLUG}

> 时长列**必须**从 \`scenes.json\` 抄，不要手写——旁白一改全变。

| 场 | 时长 | 旁白 | 画面 | 关键数字 |
|---|---|---|---|---|
| s1 |  |  |  |  |

## 事实依据

见 \`sources.md\`。

## 投稿计划

- 标题：
- 分区 tid：
- 标签：
- 本次验证的假设：
MD

echo "已建工程：$DIR"
echo ""
echo "下一步："
echo "  1) 填 $DIR/sources.md      ← 事实先钉死"
echo "  2) 写 $DIR/script.json     ← 按六段式，先算字数"
echo "  3) 配音："
echo "     python3 \\"
echo "       ~/.workbuddy/skills/tts-explainer-video/scripts/tts_narrate.py \\"
echo "       \"$DIR/script.json\" --voice B --out \"$DIR\""
