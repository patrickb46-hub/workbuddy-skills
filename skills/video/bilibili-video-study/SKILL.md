---
name: bilibili-video-study
description: 在 B 站"拉片"——把参考视频拆成可执行的技法规则，用来提升自己出片的质量。用官方公开接口取元数据、下载直链，尤其是用 videoshot 雪碧图一次抓全片抽帧并逐帧读画面（含硬字幕），产出镜头表、技法清单和出片检查表。触发词：拉片、拆片、扒视频、拆解爆款视频、学习B站视频、看B站教程学到手、分析这个视频怎么剪的、参考样片拆结构、提升视频质量、仿拍、镜头表、分镜分析、分析这个BV号。也用于回答"这个 B 站视频讲了什么/什么风格/节奏多快"。
agent_created: true
---

# B 站拉片学习

## 何时用

- 用户给一个 BV 号或视频链接，问"这视频怎么做的 / 什么风格 / 值不值得学"。
- 用户要提升自己出片质量，想先看别人怎么做（"先去 B 站学学"）。
- 需要把某种视频类型（口播、科普、vlog、测评、项目展示）的通用做法沉淀成规范。

**不适用**：需要实时观看连续画面来判断运镜手感、音效卡点、BGM 情绪——本工具是**离散抽帧**，这些只能间接推断，必须显式标注"未验证"。也不适用于搬运、批量下载、二次上传他人作品。

## 能力边界（已实测，别重复试错）

| 想做 | 走哪条路 | 状态 |
|---|---|---|
| 元数据、分P、简介、封面 | `bili.py info` | ✅ 免登录 |
| 看画面（核心） | `bili.py sheet --times` | ✅ 免登录，一次请求约 100 帧 |
| 下载视频 | `bili.py download` | ✅ 免登录，**只有 360P** |
| 按秒截片段 | `bili.py clip` | ⚠️ 依赖 ffmpeg，可能坏 |
| 关键词搜视频 | `bili.py search` | ❌ 风控返回 `v_voucher` |
| UP主作品列表 | `bili.py videos` | ❌ 同上 |
| 官方 CC 字幕 | — | ❌ 需登录 cookie |

搜索/空间接口就算带 wbi 签名 + buvid 也会被 `v_voucher` 拦（实测 2026-10-22）。**真正好用的是 WebFetch 打开搜索页**——`https://search.bilibili.com/all?keyword=xxx` 和 `/upuser?keyword=xxx` 都是服务端渲染，能直接读到 UP 主名、UID、BV 号、播放量、时长；UP 主主页 `https://space.bilibili.com/{mid}` 也能读到投稿列表。拿到 BV 号后 `info / sheet / download` 全部正常，这才是主力路径。

## 运行环境

**必须用带 Pillow 的解释器**，系统 python3 没有 Pillow：

```bash
PY=python3
S=~/.workbuddy/skills/bilibili-video-study/scripts/bili.py
$PY $S probe          # 先跑这个，确认 Pillow / ffmpeg / 接口三项状态
```

`probe` 报 ffmpeg 不可用是常见情况（本机曾因缺 `libxcb.1.dylib` 挂掉），此时 `clip` 用不了，但**抽帧不需要 ffmpeg**，改用 `sheet` 即可。

**已知抖动**：videoshot 接口偶发返回空时间轴（换节点导致）。脚本会自动取 `buvid3` 设备指纹并重试 4 次；若仍拿不到精确时间轴但拿到了图，会按等间隔估算并置 `timeline_estimated: true`——此时引用具体秒数要说明是估算值。

## 标准流程

1. **锁定样片**：3–5 个同类型视频，别只看一个爆款——单样本学成的是模仿，不是规律。记录 BV 号、播放/点赞比。
2. **取信息**：`info` 拿时长、分P、简介里的章节时间轴（很多 up 会把章节写进简介，这是免费的镜头表）。
3. **抽帧**：
   ```bash
   $PY $S sheet BV1xx --every 10 --scale 1.8 --out ~/Desktop/lapian/BV1xx
   ```
   `--every` 等间隔铺全片看整体节奏；`--times 74,293` 定点看某个技法发生的那一秒。
   `--scale 1.8` 把 480×270 放大到 864 宽，硬字幕才读得清。
4. **读画面**：用 Read 工具逐个打开 `frames[].file`。关键一步——不许用 manifest 里的文字代替真读图。
5. **写成规则**：按 `references/lapian-method.md` 的字段填镜头表，再压缩成 `assets/shooting-spec-template.md` 那份规范。
6. **自检**：出片前拿规范逐条过，不合格不上交。

## 抽帧能读到什么、读不到什么

单帧可读：构图（三分/中心/留白）、字幕层级与位置、配色与色温、UI 密度、画面信息量、是否有进度条/水印/角标、文字排版风格。

帧序列可推：平均镜头时长、切换密度曲线、节奏前松后紧还是匀速、色温漂移、反复出现的视觉母题、信息密度的峰谷。

**读不到**：运镜速度、转场是否用了 J-cut/L-cut、音效与画面卡点、BGM 情绪、口播语速。这些一律标"未验证"，不许编。

## 红线

- 只取少量帧做分析，不整片搬运、不再分发。
- 引用具体视频时标 up 主和 BV 号。
- 学的是技法规律，不是复刻某个人的具体作品。

## 文件

- `scripts/bili.py` — 全部子命令，输出统一 JSON
- `references/lapian-method.md` — 拉片方法论：镜头表字段、拆解维度、从画面到规则的转换
- `assets/shooting-spec-template.md` — 出片规范模板，可直接填
