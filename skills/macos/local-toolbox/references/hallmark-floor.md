# Hallmark Floor —— 网页版式验收清单

来源：Nutlope/hallmark v2.0.0（MIT），`skills/hallmark/SKILL.md` 的 "The Floor" 段。
**规则来自它，执行器是本机已装的 `impeccable`**（`impeccable detect <file|dir>`）。hallmark 套件不装——它的 scripts 全是 `--render` 链路，且 install-hook.mjs 是 Claude Code hooks，WorkBuddy 不加载。

## 怎么用

交付任何新页面 / 改版页面之前，按下面三栏过一遍：

- **机检**：`impeccable detect 文件.html` 能直接报的 → 以它的输出为准
- **目检**：impeccable 不查、必须人眼或读 CSS 的
- 结果只有三种处置：**改** / **记下豁免理由** / **不动**（模板签名）

冲突裁决：`low-contrast` 是真缺陷，必改；`side-tab`、`numbered-section-labels` 是既有模板签名（周报 00—06 编号、试卷墨黑深红基调在用），**不盲改**。

## 15 条硬规则

| # | 判据 | 怎么验 | 原编号 |
|---|---|---|---|
| 1 | 颜色与字体一律走 `:root`（或主题块）声明的 token；token 块之外不出现字面色值、不出现 `font-family` | 机检：grep 出 token 块后的 `#hex` / `rgb(` / `font-family` | 48 |
| 2 | 不用 `transition: all`；不动画 `width` / `height` / `top` / `left` | 机检：grep CSS。动 `width/height` 会触发重排，这条是真性能问题 | 10a |
| 3 | 罗马（正体）标题里不塞单个斜体词 | 目检：标题里只有一两个词是 italic 就是典型 AI 排版腔 | 38i |
| 4 | `html` 与 `body` 都用 `overflow-x: clip`；不用 `hidden`、不用 `100vw` | 机检：grep。`hidden` 会杀掉 sticky，`100vw` 在有滚动条时必然横向溢出 | 34 |
| 5 | 含图网格轨道用 `minmax(0, 1fr)`；大标题带 `overflow-wrap: break-word; min-width: 0` | 机检：grep `1fr` 是否裸写。裸写 `1fr` 会被图片撑破 | 50 |
| 6 | 每个可交互元素都有 `:focus-visible`，且即时出现（无延迟动画） | 机检：数 `:focus` 与可交互元素个数是否对得上 | 26a, 15 |
| 7 | 每个动画都有 `prefers-reduced-motion: reduce` 回退；关掉 JS 内容仍可见 | 机检：grep `prefers-reduced-motion`；再断网/禁 JS 看一次 | 27, 62 |
| 8 | 不编造指标、证言、logo 墙、案例数量 | 目检：凡是「10,000+ 用户」「客户都说」这类没出处的数字，删 | 46a |
| 9 | 不用 eyebrow 小标；标签/图表头/导航链接不用 tracked 大写或小型大写，用正文字体小一号、句首或全小写、不拉字距 | 目检：`letter-spacing` + `text-transform: uppercase` 同时出现即违规 | 54, 67 |
| 10 | 不用中点连接的 meta 串（`A · B · C`）、不把箭头粘在链接文字上、不用装饰性状态圆点 | 机检：grep `·`；目检箭头与圆点 | 63 |
| 11 | 不用紫→蓝渐变、卡中卡、emoji 当图标、手绘浏览器/系统窗口 | 机检：grep 渐变与 emoji；目检嵌套卡片 | 2a, 4, 30a, 47a |
| 12 | 1280×800 首屏不滚动就能看到：大标题、一句话说明、主操作 | 目检：真开一个 1280×800 视口截图 | 44b |
| 13 | 单屏正文约 80 词；首屏文字只有「标题 + 一句话 + 动作」 | 目检：数首屏字数 | 58 |
| 14 | 容器封顶居中：1920 宽时增的是外边距，正文宽度与网格不变 | 目检：拉宽到 1920 看正文是否变宽 | 44d |
| 15 | CSS 源码第一条非空行是 stamp，然后 critique 行，然后豁免 | 不适用：这是 hallmark 自己的产物约定，本项目不跟 | 20 |

## 它上面还有两层（本次未抄）

- **Reflex gate**：模型默认会掉进去的坑，可带理由豁免 —— 见 upstream `references/gates.md` §1
- **Finish check**：工艺细节，只答复不阻断 —— §2

需要时去读上游原文：`https://github.com/Nutlope/hallmark/blob/main/skills/hallmark/SKILL.md`

## 这套清单查不到的死角

第 8 条（编造指标）、第 12–14 条（首屏与容器）impeccable 报不出来，只能人眼；反过来 impeccable 会报一堆 CSS 层面的细节（对比度、间距），清单里没有。**两者是互补的，别指望一个替另一个。**
