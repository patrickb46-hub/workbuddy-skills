---
name: local-toolbox
license: Proprietary
description: "本地已装四件 CLI 工具的统一入口与使用规程：graphify（代码/文档知识图谱）、skillspector（AI 技能安全扫描）、deeptutor（出题/对话/解题，走 deepseek-flash）、impeccable（界面「AI 味」检测）。附带一份网页版式验收清单 references/hallmark-floor.md（抄自 hallmark 的 15 条 Floor 硬规则）。当用户说「扫一下技能安不安全」「给这个目录建个代码图谱」「出几道练习题」「看看这页 HTML 有没有 AI 味」「交付前验收版式」「这页哪里像 AI 生成的」时使用。命令都在 ~/Desktop/AI/Tools/bin/，四个工具都已装好，不要重装。"
---

# 本地工具集（local-toolbox）

四条命令，统一入口在 `~/Desktop/AI/Tools/bin/`。四个工具分别装在独立 venv 与全局 npm 里，**不要重复安装**。

## 一句话路由

| 想做的事 | 工具 | 命令 |
|---|---|---|
| 找「我记得见过，但想不起在哪个文件」 | graphify | `~/Desktop/AI/Tools/bin/graphify query "关键词"` |
| 装新技能前查安不安全 | skillspector | `~/Desktop/AI/Tools/bin/scan-skills`（扫全部） |
| 出一套练习题 | deeptutor | `~/Desktop/AI/Tools/bin/deeptutor run deep_question "..." --language zh` |
| 检查 HTML 有没有 AI 生成感 | impeccable | `~/Desktop/AI/Tools/bin/impeccable detect 文件.html` |
| 交付前验收版式过不过关 | impeccable + 清单 | 先跑上面那条，再对照 [`references/hallmark-floor.md`](references/hallmark-floor.md) |

## 各自的坑（都实测踩过）

**graphify**（0.9.97，`~/.local/tools/graphify`）
- `update` 只能增量更新，**不能用来首次建图** —— 会报 EEXIST 且不产出 `graph.json`。首次建图按 `~/.workbuddy/skills/graphify/SKILL.md` 的流程走。
- 纯本地 tree-sitter 解析，无 GPU 依赖，2018 Intel Mac 跑得动。
- 问答优先 `query` / `explain` / `path`，别退回去翻文件。

**skillspector**（v2.12.0，`~/.local/tools/skillspector`）
- **拒绝扫描软链接**：`~/.workbuddy/skills/` 下很多目录是指向 `~/Desktop/Tools/AI开源工具/anthropic-skills/` 的软链，必须先 `os.path.realpath()`。
- `--output` 在本机被禁用（Safe file output unsupported），只能 `> 文件.json` 重定向。
- **退出码 2 = 有发现，不是失败**（CI 门禁语义）。
- ⚠️ 沙箱内扫描会因临时目录被禁而 `completeness=partial`，把每个脚本判成 `Concealed Executable Artifact` HIGH —— 那是假警报级联。**内容级结论必须在用户终端跑**。

**deeptutor**（1.7.0，`~/.local/tools/deeptutor`）
- 运行时 home 固定在 `~/Desktop/AI/DeepTutor`，入口脚本已自动导出 `DEEPTUTOR_HOME`；`doctor` 只认这个环境变量，不认 `--home`。
- 模型 = `deepseek-flash`；配置在 `~/dt-setup.json`，改 `model` 后 `config apply ~/dt-setup.json --home "$DEEPTUTOR_HOME"` 可切 `deepseek-v4-pro`。
- 可用能力只有 `chat` / `ask_questions` / `deep_question`；`mastery_path` 需要 `knowledge` 模块 + 嵌入模型（ollama `nomic-embed-text`），**当前未装**。
- 输出是 LaTeX（`$...$`），进 HTML 要转换；它倾向「多给」，要求简短必须写死。
- 成本：出题一次约 12k tokens / $0.003，对话约 7.6k / $0.0013。

**impeccable**（4.8.0，`~/.npm-global/bin`）
- `detect` 可吃单文件或目录。
- 它报的 `side-tab`（`border-left:3px` + 圆角）、`numbered-section-labels`（01/02/03 编号）属于审美取向，是模板签名，**别盲改**；`low-contrast` 是真缺陷，该修。
- **验收清单在 [`references/hallmark-floor.md`](references/hallmark-floor.md)**：抄自 Nutlope/hallmark 的 15 条 Floor 硬规则，每条标了「机检 / 目检」与原编号。hallmark 套件本身不装（与 impeccable 同功能，且其 scripts 依赖 `--render` 链路）。
- 分工：**规则看清单，执行靠 impeccable**。清单第 8 条（编造指标）与 12–14 条（首屏/容器）impeccable 查不出来，只能人眼——这是两份都要留的原因。
- `frontend-design` 决定「怎么排」，这套清单只管「交付前能不能过」，不抢方向。

## 环境事实（省得重新试错）
- 本机**无** uv / pipx / docker；Python 在 `~/.workbuddy/binaries/python/versions/`（3.13 为默认）。
- pip 已配全局约束 `~/.pip-constraints.txt`（`cryptography==48.0.1`）与清华镜像 `~/.config/pip/pip.conf`。
- Intel Mac 口诀：**看到 `maturin` / `cargo` / `build wheel`，先别装 Rust，去钉一个旧版本**。
