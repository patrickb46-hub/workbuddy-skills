#!/usr/bin/env bash
# 上传前环境与仓库体检。只做检查，不改任何东西。
# 用法：bash preflight.sh <项目根目录>

set -uo pipefail
ROOT="${1:-.}"
cd "$ROOT" 2>/dev/null || { echo "目录不存在：$ROOT"; exit 2; }

echo "项目根：$(pwd)"
echo

echo "── 1. gh 登录状态 ──"
if ! command -v gh >/dev/null 2>&1; then
  echo "  ✗ 没装 gh（brew install gh）"
else
  gh auth status 2>&1 | sed 's/^/  /'
fi
echo

echo "── 2. git 身份 ──"
NAME="$(git config user.name 2>/dev/null)"
MAIL="$(git config user.email 2>/dev/null)"
LOGIN="$(gh api user --jq .login 2>/dev/null)"
[ -n "$NAME" ] && echo "  user.name  = $NAME" || echo "  ✗ user.name 为空（提交会失败或用错身份）"
if [ -n "$MAIL" ]; then
  echo "  user.email = $MAIL"
  case "$MAIL" in
    *users.noreply.github.com) : ;;
    *) echo "  ⚠️  不是 GitHub noreply 邮箱，提交会暴露真实邮箱。建议改用 ${LOGIN:-<login>}@users.noreply.github.com" ;;
  esac
else
  echo "  ✗ user.email 为空 → 建议设为 ${LOGIN:-<login>}@users.noreply.github.com"
fi
echo

echo "── 3. 是否已是 git 仓库 ──"
if [ -d .git ]; then
  echo "  已有 .git"
  git remote -v | sed 's/^/    /'
  echo "  分支：$(git branch --show-current 2>/dev/null)"
  echo "  未提交改动：$(git status --porcelain | wc -l | tr -d ' ') 个文件"
else
  echo "  还没有 .git（稍后 git init）"
fi
echo

echo "── 4. 不该进库的文件 ──"
JUNK="$(find . -name '.DS_Store' -o -name '*.swp' -o -name 'Thumbs.db' 2>/dev/null | grep -v '^./.git/' | head -20)"
[ -n "$JUNK" ] && echo "$JUNK" | sed 's/^/  ⚠️  /' || echo "  没发现 .DS_Store 之类"

echo
echo "── 5. 大文件（>20MB）──"
BIG="$(find . -type f -size +20M 2>/dev/null | grep -v '^./.git/' | head -20)"
[ -n "$BIG" ] && echo "$BIG" | sed 's/^/  ⚠️  /' || echo "  没有"

echo
echo "── 6. 敏感目录 ──"
for d in .workbuddy .claude .codex .agents .ssh node_modules; do
  [ -d "./$d" ] && echo "  ⚠️  存在 $d/ —— 确认已写进 .gitignore"
done
echo

echo "── 7. 有无 .gitignore / LICENSE / README ──"
for f in .gitignore LICENSE README.md; do
  [ -f "./$f" ] && echo "  ✓ $f" || echo "  ✗ 缺 $f"
done
