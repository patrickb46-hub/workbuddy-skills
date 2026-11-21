---
name: exam-paper-solutions
license: Proprietary
description: 把试卷/练习册照片整理成"全解"HTML（默认从 ~/Downloads 找最新照片）。触发词：解答这份试卷、全解、完整解答、写出完整推导过程、证明题要写依据、周末卷、练习卷、答案加框、试卷照片整理成答案、考点知识点、整理考点、折叠答案、选中提问、问 AI。产出：自包含 A4 可打印 HTML，每题四段折叠（辅助线 → 思路 → 答案 → 完整解答）＋单题展开按钮＋全部展开/折叠＋右上站内搜索＋选中右键「提问」开 DeepSeek 侧栏。**流程：写一份 .mk 规格 → build.py 渲染 → check.py 自检 → shoot.py 看图**，不要手写 HTML 骨架。归档到 ~/Desktop/Recently/日常作业/<学科>/<组名>/，桌面只留全解快捷方式；另出一份考点知识点 HTML。证明题逐句换行注依据；完整解答开头必须重述辅助线；几何图内联 SVG 且必须 figcheck 复检。英语卷全文中英对照。出题分支用 quiz-template.html。
agent_created: true
---

# 试卷全解 ＋ 出题

**先判分支**：有源图 → A 全解；说"出题" → B 出题（见文末）。

## 核心原则

**不手写 HTML 骨架。** 模板里 40KB 的 CSS 与两个组件是固定资产，写了也是白费；
你只写**内容规格**（`.mk`），`build.py` 负责骨架、id、类名、按钮、重述、
答案三处去重、速查表。手写骨架会带来 id 重复、漏 `fd-sol`、漏 `.restate`、
`<details>` 打不开这类错误，还要多跑几轮修。

```
源图 → 读图 → 写 spec.mk → build.py → check.py → shoot.py（看 1–3 张图）→ 清理 → 交付
```

## 产物位置（最高优先级）

```bash
BASE_DIR="$HOME/Desktop/Recently/日常作业"
GROUP_DIR="$BASE_DIR/<学科>/<组名>"        # 例：$BASE_DIR/数学/第13题-水泵最短路径
```

- 分组夹里：`JPG/` ＋ 两份 HTML（**同级**，不塞子目录）。处理期间临时有 `HEIC/`，收尾删掉。
- 源图默认 `~/Downloads` 最新几张，**`cp` 复制进来，绝不 `mv`**；用户点了路径就以用户的为准。
- 桌面 `~/Desktop` 只建**全解**的符号链接（`ln -sfn`，别名在沙箱里必失败）；考点知识点不建。
- **每次 cp 进来的文件名先记下来**，收尾只删这批。

## 配方：spec.mk 怎么写

用 `build.py sample sol` 打印一份完整样张。指令表：

| 指令 | 写什么 |
|---|---|
| `%title` `%meta` | 标题、题头一行（题型｜单位） |
| `@stem` | 题干原文，一行一段 |
| `@q 1 \| 一句话题型` | 开一道新题；编号可省（默认递增），id 自动 `q1/f1-*` |
| `@aux` | 辅助线，一行一条；**`~` 开头的行＝"为什么画这条"**，不进重述 |
| `@idea` | 思路，`标题 \| 一句话`，一行一小步（3–5 行） |
| `@ans` | 最终答案；多问分行。**只写这一处**，自动铺到三处 |
| `@sol` | 完整解答；`## 标题`＝分步标题；其余一行一段；**行末括号自动变绿色依据**（不想变绿行尾加 `\`） |
| `@fig` / `@cap` | 内联 SVG（原样粘贴）/ 图注 |
| `@err` | 易错表，`错误做法 \| 为什么错` |
| `@alt` | 别解（可省；不写则只有标题） |
| `@quick` | 速查表覆盖（可省，默认按 `@ans` 自动生成，不会丢行） |

考点知识点（`build.py kp`）：

| 指令 | 写什么 |
|---|---|
| `@sect 一、第 1 题：…` | 分节（按题型） |
| `@kp 第 1 题 \| 考点 \| ★★★` | 一个考点块 |
| `@k 知识点① \| 内容` | 知识点（准确表述＋公式） |
| `@tip 易错点…` | 易错（真没有写 `—`） |
| `@eg 例题 1　题干` / `@idea` / `@step` / `@eans` | 例题：思路→步骤→答案 |
| `@q 练习 1　题干` / `@qans` | 练习：只给答案 |

小结表、考点分布表、条形图**全部自动生成**，不要手写。

## 命令

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
SK=~/.workbuddy/skills/exam-paper-solutions

$PY "$SK/tools/build.py" sol "$GROUP_DIR/spec.mk" -o "$GROUP_DIR/xxx全解.html"
$PY "$SK/tools/build.py" kp  "$GROUP_DIR/kp.mk"   -o "$GROUP_DIR/xxx考点知识点.html"
$PY "$SK/assets/inject_ask.py"    "$GROUP_DIR"           # 写 DeepSeek key（模板里是空的，每次都要跑）
$PY "$SK/tools/check.py" "$GROUP_DIR"                    # 必须全 OK，有 FAIL 退出码 1
$PY "$SK/tools/shoot.py" "$GROUP_DIR/xxx全解.html" -o /tmp/shots   # 只留首屏/末屏/有问题的屏
$PY "$SK/assets/inject_search.py" --check "$GROUP_DIR"   # 必须「待处理 0 个」
$PY "$SK/assets/inject_ask.py"    --check "$GROUP_DIR"   # 必须「待处理 0 个」
```

`build.py` 生成的文件**自带**搜索与提问组件（都从 `solution-template.html` 来），
所以注入只是为了把 key 填进去。改过组件才需要重跑别的脚本，见 `references/components.md`。

**key 不经过对话**：`inject_ask.py` 自己按
`--key 参数 > --key-file > $WBS_KEY_FILE > ~/.workbuddy/secrets/deepseek.key > 环境变量`
的顺序读，只回显来源与掩码（`sk-7f81…ea51`），**不要 cat 那个文件、也不要让用户把 key 贴进对话**。
查看来源：`$PY "$SK/assets/inject_ask.py" --where`。

## 四段折叠（不许串味）

| 段 | 内容 | 禁止 |
|---|---|---|
| **辅助线** | 作哪个点／连哪条线／建什么系，一句话一条，附一句"为什么是它" | 写算式、写结论 |
| **思路** | 3–5 个小步，每步标题＝这一步干什么，内容一句话 | 抄推导；给数值 |
| **答案** | 仅最终答案（多问分行） | 夹带过程 |
| **完整解答** | 开头原样重述辅助线，再分步＋逐句，**每句句末括号注依据** | 用"如图""同上""见上"指代；省依据、省单位 |

硬规则（脚本已强制，手写时才需自己盯）：

1. **折叠只用 checkbox，禁用 `<details>`**（关着时打印压不开，答案整块消失——踩过）。
2. id 全局唯一（`f1-aux/-idea/-s1/-ans/-sol`）。多题共用一个 id 会连动。
3. 打印全展开靠模板 `@media print{ .fd-bd{display:block!important} }`，别删。
4. 题号必须写在 `.qhd.q` 里（搜索定位依赖）；「完整解答」那个 `.fd` 必须带 `fd-sol` 类。
5. 默认全部收起——这是"先自己想"的设计，不是 bug。

写作细节（依据怎么注、英语卷中英对照、考点知识点要求、难度星级）→ `references/writing.md`。

## 读图

```bash
IMG_PY=$PY
IMG_TOOL=$SK/tools/imgtool.py
$IMG_PY $IMG_TOOL prep "$GROUP_DIR" -o /tmp/prep --human   # 转码＋整页副本，读 read_paths
```

三条铁律：**① 整页通读用 2000px，别从 1500 试起；② 先定位再 `crop`，不许凭感觉猜比例；③ 原图只读，重复转换加 `--force`。**

**先导航再裁图**（省掉一半试探）：

```bash
$IMG_PY $SK/tools/ocr.py JPG/a.jpg              # 每行文字前面是纵坐标，一眼看出第几题在哪
$IMG_PY $SK/tools/ocr.py JPG/a.jpg --find 第3题  # 直接给出可粘贴的 crop 参数
```

它认不准数学符号（△→A、∠→L、上下标会丢），**不能当题干原文用**，数值一律回图核对；
纯文字页（英语阅读、语文）可以直接读文本，省掉整页读图。
读完立刻把题干写进 `.mk`，后面靠规格不靠图。完整命令表 → `references/pipeline.md`。

## 几何图

内联 SVG 重绘（**不贴原图**）：坐标按真实几何关系算，`屏幕x = ox + s·x`、`屏幕y = oy − s·y`；
关键点实心小圆＋斜体字母；只用 `stroke`；辅助线虚线；直角方块／等长短线／等角弧都要画。

**画完必须复检**（不许跳）：

```bash
$IMG_PY $IMG_TOOL figcheck "$GROUP_DIR/<全解>.html" --src "$GROUP_DIR/JPG/a.jpg" \
  --map "1=0.10,0.18,0.95,0.52; 2=0.08,0.55,0.98,0.92" -o /tmp/figchk --human
```

先看 `总览.png`，再逐张 `ViewImage` 看 `pair*.png`（左原题右重绘）。八项：拓扑 → 点位顺序 → 字母集合相等 → 特殊标记 → 实虚线 → 镜像 → 图上数值 → 坐标轴等比。
改了重跑，直到每幅都过。**复检结论必须写进最终回复**（"2 幅图已逐幅对照，一致"）。细节 → `references/geometry.md`。

## 收尾清理（两份 HTML 与自检都过了才做）

```bash
rm -rf "$GROUP_DIR/HEIC"
mv ~/Downloads/IMG_41xx.HEIC ~/.Trash/          # 只删第 0 步记下的那批
$IMG_PY $IMG_TOOL clean --workspaces
```

三条硬核对：① 两份 HTML 都在且非空；② `JPG/` 与源图张数一一对应；③ Downloads 只动记录过的那批。
用户说"原图留着"就跳过 ①②。

## 交付

`present_files` 一次传两个绝对路径（先全解、后考点知识点），回复里报：
归档路径 ＋ 桌面链接名 ＋ 题量 ＋ 折叠怎么用 ＋ **选中右键「提问」怎么用**（一句话，模型 deepseek-flash），
并提醒"文件里带着你的 API key，别直接发给别人"——**要分享就把文件复制一份再对副本跑 `--strip-key`**，
原件留着方便自己提问。别只说"做好了"。
机上自检结果（`check.py` 通过、图复检结论）一并写进去。

<a id="quiz-branch"></a>
## 出题分支（B）

没有源图：**不读图、不做预处理、不出考点知识点**（用户另要除外）。

- `cp "$SK/assets/quiz-template.html" <目标>.html`，**CSS 一行都不改**；答案用 `.ans`（checkbox），禁用 `<details>`；填空一律 `＿＿＿＿`（U+FF3F 四个）。
- 题量 20–30，难度 5:4:1；产物放 `$BASE_DIR/<学科>/出题-<主题>/`，桌面建快捷方式，**不碰 `~/Downloads`**。
- 双卷分层写 `papers.json` 跑 `assets/build_layered_quiz.py`，不要手写其中任何一份。
- 细节 → `references/quiz.md`。

## 自检

```bash
$PY "$SK/tools/check.py" "$GROUP_DIR"
```

机检覆盖：div 配平、id 唯一、`<details>`、四段/`fd-sol`/`.restate`、禁词、`data-target`、
速查表、考点完备性、配套题数量、组件注入、占位符残留、打印规则。
加 `--secrets` 顺带体检「文件里有没有明文 api key」。
机器查不到的人工项（四段有没有串味、依据够不够具体、图对不对）→ `references/checklist.md`。

## 参考文件

| 文件 | 什么时候读 |
|---|---|
| `references/writing.md` | 判断某段该写什么、依据怎么注、英语卷、考点知识点规则 |
| `references/geometry.md` | 画几何图、figcheck 八项、常见画错 |
| `references/pipeline.md` | imgtool 全命令、Chrome 截图细节、故障排查、清理 |
| `references/components.md` | 要改搜索/提问组件、抹 key |
| `references/quiz.md` | 出题分支细节 |
| `references/checklist.md` | 交付前人工项 |
