# 两个内置组件：站内搜索 ＋ 选中提问

`solution-template.html` 里已经内联了这两个组件，`build.py` 生成的任何文件都自带。
**交付前只校验，不要手写。**

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
SK=~/.workbuddy/skills/exam-paper-solutions
$PY "$SK/assets/inject_search.py" "$GROUP_DIR"          # 站内搜索：缺失就注入，旧版就升级
$PY "$SK/assets/inject_ask.py"    "$GROUP_DIR"          # 选中提问：注入 ＋ 写入 DeepSeek key
$PY "$SK/assets/inject_search.py" --check "$GROUP_DIR"  # 必须「待处理 0 个」
$PY "$SK/assets/inject_ask.py"    --check "$GROUP_DIR"  # 必须「待处理 0 个」
```

## 站内搜索

- 真源 `assets/search-widget.html`（v2）：**改功能改这里并版本号 +1**，别手改各份 HTML。
- 定位依赖 `.q / .kp-item / .kp-no / h2 / h3`，所以题号必须写在 `.qhd.q` 里、考点号写在 `.kp-no` 里（`build.py` 已保证）。
- 手改过 `</body>` 附近的内容后重跑一次注入。
- 命中折叠块内的文字会自动展开该层（模板 MutationObserver 内置）。

## 选中提问（DeepSeek 侧栏）

- 真源 `assets/ask-widget.html`（v1），模板里内联一份完整副本。
  **改完组件必须跑 `$PY "$SK/assets/sync_ask_inline.py"`**，否则模板里那份是旧的。
- 交互：选中正文 → 右键 →「提问」；右下角「提问」按钮也能直接开。Esc 关面板，Enter 发送，Shift+Enter 换行；面板顶部「深想」控制 `reasoning_effort`（关＝`low` 快，开＝不传、走默认 high）。引用哪一段会显示成「第 N 题 · 完整解答」。
- 模型 `deepseek-flash`（1M 上下文、支持图片），接口 `https://api.deepseek.com/chat/completions`，流式 SSE；返回里的 `reasoning_content` 收进「思考中」折叠块。
- **运行时** key 来源：`localStorage`（面板设置里粘，最高优先） > 文件内 `<script id="waskCfg">` 的 `key`。
- **注入时** key 来源（`inject_ask.py` 自己读，不打印明文）：
  `--key` > `--key-file` > `$WBS_KEY_FILE` > `~/.workbuddy/secrets/deepseek.key` > 环境变量 `DEEPSEEK_API_KEY` / `DS_API_KEY` / `COPILOT_PROVIDER_API_KEY`。
  - 想把 key 固化在本地：`inject_ask.py --save-key`（写 `~/.workbuddy/secrets/deepseek.key`，权限 600，目录 700）。
  - 想知道这次用的是哪把：`inject_ask.py --where`（只回显来源路径 + 掩码 `sk-…abcd`）。
  - **agent 不要 `cat` 这个文件、也不要让用户在对话里贴 key** —— 一旦进上下文就收不回来。
    工具读、脚本用，链条就干净了。
- **对外分享前先抹 key**：`$PY "$SK/assets/inject_ask.py" --strip-key "$GROUP_DIR"`；抹完首次提问会让人在面板里粘一次，存 localStorage。
- `file://` 下能直连，靠 DeepSeek 对 `Origin: null` 回 `access-control-allow-origin: null`。**别改 endpoint、别加自定义 header**，否则预检不通过。
