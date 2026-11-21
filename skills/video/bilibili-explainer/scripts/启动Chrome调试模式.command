#!/bin/bash
# 以调试端口启动 Chrome —— 供 web_upload.py 接管你已登录的会话
# 双击运行。会先退出当前 Chrome 再带参数重启（标签页会自动恢复）。
set -u

PORT=9222

echo "== 检查 Chrome 是否在运行 =="
if pgrep -x "Google Chrome" >/dev/null 2>&1; then
  echo "  Chrome 在运行，先退出（⌘Q 等价的正常退出，会保留会话）…"
  osascript -e 'tell application "Google Chrome" to quit' >/dev/null 2>&1
  # 等最多 15 秒
  for i in $(seq 1 15); do
    pgrep -x "Google Chrome" >/dev/null 2>&1 || break
    sleep 1
  done
  if pgrep -x "Google Chrome" >/dev/null 2>&1; then
    echo "  ! Chrome 没有正常退出，请手动 ⌘Q 后再双击本脚本"
    exit 1
  fi
  echo "  已退出"
fi

echo "== 带调试端口启动 =="
open -a "Google Chrome" --args --remote-debugging-port=$PORT
sleep 3

code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 --noproxy '*' "http://127.0.0.1:$PORT/json/version" 2>/dev/null)

if [ "$code" = "200" ]; then
  echo "== OK 调试端口 $PORT 已就绪，可以跑投稿脚本了 =="
else
  echo "== WARN 端口返回 HTTP $code，未就绪 =="
  echo "   常见原因：Chrome 还有残留进程（等 10 秒再试），或已被别的实例占用端口。"
fi

echo
echo "（本次 Chrome 会一直带着调试端口，直到你完全退出。安全提示：该端口只监听 127.0.0.1。）"
