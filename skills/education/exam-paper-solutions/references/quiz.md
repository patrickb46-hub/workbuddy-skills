# 出题分支（B）

没有源图：**不读图、不做预处理、不出考点知识点**（用户另要除外）。

## 单卷

- `cp ~/.workbuddy/skills/exam-paper-solutions/assets/quiz-template.html <目标>.html`，**CSS 一行都不改**。
- 版式定死：左侧两级固定目录（`<a href="#s1">` 必须对上正文 `id="s1"`，这是唯一易错点）＋右侧题面＋每题下折叠答案。
- 答案折叠用 `.ans`（checkbox＋label＋`.ans-body`），**禁用 `<details>`**；`id` 递增唯一（`an1`…）。
- 填空线一律 `＿＿＿＿`（U+FF3F 四个），**不许用全角空格拼**（打印是空白）。
- 题量 20–30，难度 基础:中等:较难 ≈ 5:4:1；每题给答案＋解析（踩分点／易错点／为什么）；超纲工具禁用（如学生没学二次函数就别出）；自编题在 `.src` 注明。
- 产物放 `$BASE_DIR/<学科>/出题-<主题>/`，桌面建一个快捷方式；**收尾不碰 `~/Downloads`**。
- 题目默认不带提问侧栏（`quiz-template.html` 未内置）；学生要"边做题边问"时再跑一次
  `$PY "$SK/assets/inject_ask.py" "$GROUP_DIR"`，其余不动。

## 双卷分层（代数 ＋ 几何）

题目写进 `papers.json`，跑 `assets/build_layered_quiz.py`，**不要手写其中任何一份**：

- 每卷 20 题，10/8/2（基础/中等/较难），分值 50/40/10。
- 产出：代数卷 HTML ＋ 几何卷 HTML ＋ 纯题 DOCX（DOCX 只含题目，不含答案）。
- 目录锚点、答案折叠、填空线全部由脚本保证，交付前用 `check.py --kind quiz` 过一遍。

## 校对

`check.py` 会查：`<details>` 残留、`.ans` 数量、填空线是否存在、目录 `href` 与正文 `id` 是否一一对应。
