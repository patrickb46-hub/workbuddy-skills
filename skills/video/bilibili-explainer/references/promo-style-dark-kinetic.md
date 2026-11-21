# 深色动能宣传片 · 风格手册

一套为 20–30 秒**无旁白产品宣传片**定的视觉与听觉规则。第一次成型是 2026-11-21 的
三条片子（AgentBar / Skills / dsh），用户明确说「很喜欢这个风格、配乐也很好」。
之后做同类片子**先照这份手册**，不要重新发明。

可直接跑的样例在 `assets/promo-examples/`：三个 HTML 时间轴 + 一个参数化封面。

---

## 一、视觉基调

| 项 | 值 |
|---|---|
| 底色 | `#08090C`（近黑，带一点点蓝） |
| 主文字 | `#F5F7FA` |
| 次级文字 | `#8A93A6` / `#5E687C` |
| 强调色 | 蓝 `#2F6BFF`、青 `#35E0D0`、琥珀 `#FFB020`、紫 `#A78BFA` |
| 字体 | `-apple-system, "SF Pro Display", "PingFang SC"`；代码与标签用 `"SF Mono"` |
| 标题 | `font-weight: 850`，`letter-spacing: -.045em`，行高 1.02–1.1 |
| 标签 | 等宽 + `letter-spacing: .2em` + 全大写，字号 19–22px |

**纹理三件套**（缺一个就会显得平）：
1. `#grid` 点阵：`radial-gradient(circle at 1px 1px, #232a38 1px, transparent 0)`，48px 一格，opacity .5
2. `#vig` 暗角：`radial-gradient(ellipse at 50% 45%, transparent 30%, #000 118%)`
3. `#grain` 扫描线：`repeating-linear-gradient(0deg,#fff 0 1px,transparent 1px 3px)`，opacity .05，`mix-blend-mode: overlay`

**留白**：左右边距 150px（1080p），标题基线不越过 2/3 高度；一屏只放一件事。

---

## 二、节奏表（28 秒标准结构）

| 段落 | 时长 | 画面 | 配乐段落 |
|---|---|---|---|
| 痛点 | 0–2.9s | 3 句硬切，每句 0.9s，第三句换红 `#FF5A4E` + 轻微抖动 | intro（只有 pad+拨弦） |
| 点题 | 2.9–5.8s | **反色硬切**：白底黑字一句话，≤8 字，配一条 10px 蓝线从左画到右 | build（进鼓） |
| 名字 | 5.8–7.7s | 大 logo + 一条发光扫描线从上滑到基线 | main 起点 |
| 证据 | 7.7–11.1s | 真实截图推镜，每 1.1s 换一个焦点（只做 translate + scale） | main |
| 特写 | 11.1–14.0s | 单张截图放大 + 高亮框脉冲 + 左侧两行说明 | main |
| 特性 | 14.0–19.4s | 4 连快切，每段 **1.33s**（不要低于 1.2s，会看不清字），每段换底色 | main |
| 面板 | 19.4–22.2s | 界面截图滑入 + 圆角标签逐颗弹出 | break（自动降下来，方便读字） |
| 收尾 | 22.2–28s | 名字 + 一条安装命令 + 一行署名 | outro（拉满） |

**短版（20–24 秒）**：痛点 → 点题 → 主体 3 段 → 收尾，删掉「名字」独立段，把 logo 放到收尾。

---

## 三、动效语言（只有这几种，别混）

| 名字 | 做法 | 用在 |
|---|---|---|
| slam | `scale 1.06→1` + `translateY 34→0` + opacity，0.16s | 大字进场 |
| mask-up | 容器 `overflow:hidden`，内层 `translateY 110%→0` | 多行标题 |
| wipe | 色块宽度 0→100%，0.5s | 分隔线、进度条 |
| ken-burns | 图 `scale 1.0→1.06`，全程匀速 | 截图 |
| cam-pan | `translate` + 固定 `scale`，段落间用 `inOut` 缓动 | 长截图横移 |
| flash | 全屏白 `opacity .3–.5`，0.03s 衰减 | 每次硬切 |
| pulse | `0.6 + 0.4*sin(t*3)` | 高亮框、光晕 |

缓动只用两个：**`outExpo` 进场**、**`outQuint` 位移**。不要用 bounce、不要用弹簧。

---

## 四、实现方式（关键）

每帧一个纯函数：

```js
function renderAt(t){ ... }   // window.renderAt = renderAt
```

- 不用 CSS animation / transition —— 截图时时间不可控，一定会错帧
- 所有元素 `position:absolute`，靠 JS 改 `transform / opacity / width`
- 段落切换用 `if (t>=a && t<b)`，越界就 `display:none`
- 渲染器：`scripts/render_motion.py`（Playwright 逐帧 JPEG，0.066s/帧）

---

## 五、配乐规格

由 `scripts/make_music.py` 生成，**100% 原创，零版权风险**。

| 片子 | 文件 | BPM | 调 | 特征 |
|---|---|---|---|---|
| AgentBar | `assets/bgm/uplift-C.m4a` | 124 | C | 明亮、推进感强 |
| Skills | `assets/bgm/bright-G.m4a` | 126 | G | 更清脆，拨弦偏多 |
| dsh | `assets/bgm/pulse-D.m4a` | 120 | D | 稳重，适合讲结构 |

**音色配方**（都在 `make_music.py` 里）：
- 铃音：`sin(f) + .22sin(2f) + .10sin(3.01f) + .05sin(4.16f)`，指数衰减 τ≈0.22s
- 拨弦：1–9 次谐波按 `1/k^1.15` 叠，亮度系数 0.5
- 贝斯：`sin + .35sin(2f) + .12sin(3f)`，过 `tanh(1.3x)` 轻饱和
- 底鼓：118→46Hz 扫频 + 高频 click
- 铺底 pad：每个音三个 detune（±0.12%）
- 空间感：**乒乓延迟**（0.34s / 反馈 0.32 / 4 抽头），不用卷积混响

**编曲规则**：
- 和声 `I–V–vi–IV`，一小节一个和弦
- 段落增益必须写死成表（intro 只留 pad+稀疏拨弦，break 抽掉鼓和贝斯），不要全曲一个响度
- 进主歌前一小节加一次上升噪声（`t²·⁴` 包络），这是「抬起来」的关键
- 混完 `loudnorm=I=-16:TP=-1.5:LRA=11`，B 站和网页播放都不会忽大忽小

---

## 六、硬规则（吃过亏的）

1. **每段快切不短于 1.2 秒**——低于这个，观众读不完一行字，只会觉得闪
2. 硬切必须配 1–2 帧白闪，不要用转场特效（缩放转场、模糊转场一律不要）
3. 截图必须来自真实运行结果；不要画示意图，观众看得出真假
4. 白场段落只出现一次，用在「点题」，多了会廉价
5. 一屏只讲一件事，信息密度靠**换屏**堆，不靠在一屏里塞
6. 封面要做 **16:9 和 4:3 两版**（B 站首页推荐是 4:3、个人空间是 16:9），
   同一套设计语言，4:3 版把截图横条挪到标题下方、字号缩到 104px
