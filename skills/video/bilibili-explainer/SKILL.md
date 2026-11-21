---
name: bilibili-explainer
license: Proprietary
description: 科普讲解短片的一条龙流水线——核实事实 → 写六段式旁白 → edge-tts 配音 → 画画面（Remotion SceneKit 手写，或 dsh 里用 DrawAI 出 MG 动效）→ FFmpeg 合成 → 出配音版与纯字幕版 → 双版封面摆到桌面 → 投稿 B 站。全流程只有两处需要人工：扫码登录、上传封面。产物固定落在 `$HOME/Desktop/AI/Bilibili Videos/<slug>/`。触发词：做科普视频、讲解视频、B站投稿、发视频到B站、热点科普、事件解读、做个讲原理的视频、把这份材料做成视频、生成旁白、中文配音、Remotion 渲染、edge-tts、科普短片、辟谣视频、纯字幕版、双版本、MG动效、动态图形、DrawAI、矢量动画画视频。
version: 1.2.0
---

# 科普短片 · 制作到投稿

核心不是"自动生成视频"，而是**先保证讲的是真的，再保证讲得清**。

## 人工只剩两处

整条流水线里只有两件事必须人来做，其余全自动：

| 人工节点 | 为什么必须人做 | 怎么做 |
|---|---|---|
| **① 登录** | 扫码不触发风控，脚本不经手密码 | 跑 `scripts/login_bili.py`，手机 B 站扫窗口里的码 |
| **② 传封面** | 封面编辑器整块是 canvas（fabric.js），按钮不在 DOM，自动化点不进去 | 桌面 `封面_16x9_<slug>.png` / `封面_4x3_<slug>.png` 手动上传 |

登录态一次能用几个月，所以**常态是只人工传封面**。点「立即投稿」若弹短信/人机验证，也需要人过一下——平台风控，不绕。

## 一条流水线

```
选题 → 事实分级 → 六段式旁白(script.json) → 配音(timing.ts) → 6~7 个 Scene
  → 渲染 → 质检 → 双版封面 → 摆到桌面 → 填表投稿 → 记台账
```

产物根目录**固定**：

```
$HOME/Desktop/AI/Bilibili Videos/<slug>/
```

`<slug>` 用英文短横线，如 `mc-launcher-ban`。**不要**往别的目录散落文件。

## 能力边界

| 能做 | 不能做 |
|---|---|
| 热点事件梳理、原理讲解、数据对比、实验复盘 | 替人做实名认证、代填转载授权 |
| 逐句配音、按实测时长对帧、代码画图 | 真人出镜、实拍质感、长镜头叙事 |
| 生成封面、上传/定时发布、抓数据复盘 | 保证过审（B 站人工+机审，不受控） |
| 把"已证实/未证实"分开讲 | 把传言写成结论 |

---

## 阶段 0 · 建工程（30 秒）

```bash
bash ~/.workbuddy/skills/bilibili-explainer/scripts/new_project.sh mc-launcher-ban
```

建出标准骨架并把 `SceneKit.tsx` 拷进工程。**先建目录再写稿**——稿子、音频、帧表都在里面，顺序反了会到处乱放。

环境自检（缺哪个补哪个）：

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
$PY -c "import edge_tts; print(edge_tts.__version__)"       # 配音
ls ~/Desktop/Tools/AI开源工具/OpenMontage/remotion-composer  # 渲染工程
$PY -c "import playwright; print('playwright ok')"           # 网页投稿（biliup 已废弃）
ls ~/Library/Caches/ms-playwright/chromium-*/chrome-mac-x64/  # 浏览器内核，必须有 Chrome for Testing
$PY ~/.workbuddy/skills/bilibili-studio/scripts/bili.py auth-check   # 数据/复盘用，投稿不依赖它
```

---

## 阶段 0.5 · 登录（2026-11-14 改：以你的浏览器为准）

**首选：直接用你自己 Chrome 里的登录态，不碰 cookie 文件。**

```bash
# 双击运行（会先正常退出 Chrome 再带调试端口重启，标签页自动恢复）
~/.workbuddy/skills/bilibili-explainer/scripts/启动Chrome调试模式.command
```

之后 `web_upload.py` 会自动 `connect_over_cdp` 接管这个 Chrome，**用你已登录的会话投稿**，
日志会打 `→ 已接管你已登录的 Chrome（CDP 模式，不用 cookie 文件）`。
你只要保证 Chrome 里 B 站是登录状态即可——**登录态由用户自己管，脚本不参与**。

**回退路径（备份，平时不用管）**：Chrome 没开调试端口时，脚本自动退回读
`~/.workbuddy/secrets/bili/cookies.json`。这份 cookie 过期了，先试着直接从 Chrome 重抓
（`bili.py auth-chrome`），抓不到再重跑扫码：

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
$PY ~/.workbuddy/skills/bilibili-explainer/scripts/login_bili.py --timeout 600
```

**用扫码，不用账号密码**：自动化浏览器里走账密极易触发滑块/短信风控，严重的会影响账号。

**怎么判断登录失效**：上传后卡在「编辑页没出现」，或 `input[type=file]` 30 秒超时。
CDP 模式下先看 Chrome 里 B 站是不是登出了；cookies 模式下就是文件过期，重扫码。

**硬约束（别踩）**：浏览器扩展（`mcp__browser__*`）**没有 `setInputFiles`**，传不了几百 MB 的视频，
所以投稿必须有 Playwright。也别改用 `launch_persistent_context`——上一次的封面编辑器状态会
带进来盖住表单（2026-11 实测）。

---

## 阶段 1 · 先把事实钉死（这一步不能省）

热点科普最容易翻车的地方不是讲不明白，是**把推断讲成了定论**。写稿前必须做一张事实表：

| 级别 | 含义 | 允许的表述 |
|---|---|---|
| **已证实** | 一手来源（官方公告 / 代码提交 / 发布记录 / 监管通报） | 直接陈述，可给版本号、时间 |
| **待核实** | 只有社群转述、单一信源、截图 | 必须带"网传""尚未证实" |
| **已证伪** | 有反证 | 主动辟谣，给出正确版本 |

存成 `sources.md`，**每条事实后面挂来源链接**。三个硬规矩：

1. **能查一手就不引二手。** GitHub release / 官方公告 / 法院文书 > 媒体转述 > 群聊截图。
2. **单一信源不算信源。** 十家媒体转载同一篇帖子，仍然是一个信源。
3. **范围词要小心。** "某个功能没了" ≠ "整个产品没了"。滑坡通常发生在这一层。

> 反例警示：讲"某个启动器关了下载"时，写成"全国 MC 下载被封"——前者是发布记录里的事实，后者没有任何官方通报支撑。一句话之差，性质从科普变成传谣。

## 阶段 2 · 六段式旁白

科普短片按这个骨架写，观众不会走丢（细节见 `references/narrative-structure.md`）：

| 段 | 作用 | 时长占比 | 关键动作 |
|---|---|---|---|
| 1 钩子 | 3 秒内给结论或反差 | 8% | 先泼结论，别铺背景 |
| 2 事实 | 到底发生了什么 | 20% | 时间 + 版本 + 主体，给硬信息 |
| 3 归因 | 为什么会这样 | 22% | 讲机制，不讲情绪 |
| 4 机制 | 怎么做到的 | 18% | 技术细节是可信度的来源 |
| 5 影响 | 跟我有什么关系 | 17% | **分人群**，别一句"影响很大" |
| 6 行动 | 我该怎么办 | 15% | 给可执行路径 + 避坑清单 |

结尾再加一段**判断力**（可选）：教观众下次怎么自己判断同类消息。这是科普片和资讯片的分界线。

### 写旁白的硬约束

- 一句一行，**每句 ≤ 25 字**，超了拆。长句 TTS 断句不如人自然。
- **数字写汉字**："百分之五十三"、"八十九块"。原因见踩坑 ①。
- 中文自然语速 **4.1 字/秒**（`--rate -6%` 实测值）。
- 预算：`总秒数 ≈ 总字数 ÷ 4.1 + 句数 × 0.6`。**先算字数再写**，别写完发现要四分钟。
- 目标时长：科普 100–180 秒。超过 180 秒，先砍"归因"里的支线，别砍"行动"。

存成 `script.json`（带场景 id，方便对画面）：

```json
[
  {"id": "s1", "tts": "第一句旁白"},
  {"id": "s1", "tts": "第二句旁白"}
]
```

同一个 `id` 的多句会合并进同一场，画面不切，旁白连读。

## 阶段 3 · 配音 + 出帧表

```bash
$PY ~/.workbuddy/skills/bilibili-explainer/scripts/tts_narrate.py \
    "$HOME/Desktop/AI/Bilibili Videos/<slug>/script.json" \
    --voice B --out "$HOME/Desktop/AI/Bilibili Videos/<slug>"
```

| 参数 | 说明 |
|---|---|
| `--voice B` | 晓晓，女，温和 —— **科普默认** |
| `--voice C` | 云健，男，纪录片解说感。讲严肃事件更压得住 |
| `--voice E` | 晓伊，女，活泼。轻量话题用 |
| `--rate -6%` | 默认，≈4.1 字/秒。更慢 `-10%`，更密 `-2%` |
| `--gap 0.6` | 句间留白。教学型 0.8 |

脚本会打印每句字数/秒，**超过 4.8 会标警告**——那就把 `--rate` 放慢，别硬上。
产出：`narration.wav` / `timing.ts` / `scenes.json`。`timing.ts` 是唯一时长真相，别手写秒数。

## 阶段 4 · 画画面（先选路线）

同一支片子两条路线二选一，别混用：

| 路线 | 什么时候用 | 画面从哪来 |
|---|---|---|
| **A · SceneKit（默认）** | 讲解型：时间轴、清单、对照面板、人群影响条。改文案十分钟出货 | `SceneKit.tsx` 手写 |
| **B · DrawAI** | 个别镜头要 MG 动效：矢量动画、镜头推拉、整片风格、音乐踩点。**单工程硬上限 60 秒，只能做片段，做不了整片** | dsh 里的 DrawAI 工程，分段渲出后拼接（见本节末尾） |

默认走 A。只有当这一期确实要"动起来"——图形要做连续运动、要整片统一风格、要踩音乐节拍——才把**那几镜**切到 B。B 更慢，但它能做出手写 TSX 做不出的运动质感。

`new_project.sh` 已经把 `SceneKit.tsx` 拷到工程里了。它和 `ExplainerTemplate.tsx` 的区别：
**零件更全**（时间轴、清单、对照面板、人群影响条），7 个场景骨架直接改文案就能用。

```bash
cp "<slug>/SceneKit.tsx" ~/Desktop/Tools/AI开源工具/OpenMontage/remotion-composer/src/MyVideo.tsx
# 入口文件：把 Root.tsx 换成独立入口，别动工程原有的
```

**必须遵守的设计约束**（突破就会显得廉价）：

- 一屏最多 6 个视觉元素，密度 4/10
- 强调色只给 1–2 处，其余灰阶；不用阴影、不用渐变
- 4px 网格
- 中文显式 `fontFamily: '"PingFang SC", sans-serif'`（不写会渲染成方块）
- 数字/版本号用等宽体，中文用黑体，**别混用**
- 旁白提到什么，画面才出现什么（用 `delay` 卡，不是全部一次性铺上）

`COMPONENTS` 的 key 必须和 `SCENES` 的 id 一一对应，多出来的场景不渲染。

### 路线 B · DrawAI（MG 动效）

装的是 `dsh-drawai@0.4.1`，挂在 dsh 的 **web profile**，右侧栏叫「DrawAI 画布」。做视频的操作规范在 `~/.dsh/skills/mg-code-video`，这里是它跟本流水线的对接部分。

**先记住三条硬约束：**

0. **一个视频工程最多 60 秒。** `motionSettings` 会校验 `duration` 落在 2–60（秒）、`fps` ≤30、`width/height` ≤1920，超了直接抛「无效的动效尺寸、帧率或时长」。科普片常规 100–180 秒，所以 DrawAI 在这里**只能做片段**：按「一场 = 一段」切开，一段一个工程，各段帧数加起来等于总帧数，最后拼成一条 `silent.mp4`。别想着建一个 180 秒的工程。
1. **要换宿主。** DrawAI 的 17 个工具（`diagram_read/apply`、`motion_project/preview/render`、`mg_style`、`shotcraft_search`…）只在 dsh 宿主里注册，WorkBuddy 这边调不到。所以路线 B 是"去 dsh 做片段，回 WorkBuddy 合成"。
2. **旁白不走 DrawAI。** edge-tts 产出的 `timing.ts` 仍然是唯一时长真相，DrawAI 只负责**无声画面**。它的 `motion_voice` 一律不用——两套配音一定对不上，最后要在时间轴上手工掰。

**交接契约（缺一条后段必崩）：**

| 项 | 必须 | 为什么 |
|---|---|---|
| 画幅帧率 | 1920×1080 / 30fps | `my-index.tsx` 的 Composition 就是这个；帧率不一致合成时会被 `-shortest` 截尾，且段间无法 `-c copy` 拼 |
| 单段时长 | ≤60 秒（建议 15–40 秒一段） | 插件硬校验；太长的段返工代价高 |
| 各段帧数 | 之和 = `scenes.json` 的总帧数 | 合成靠 `-shortest` 封口：画面长了截画面、短了留黑 |
| 编码 | h264 / yuv420p / **无音轨** | 合成用 `-c:v copy` 不重编，带音轨会串进成片 |
| 落位 | 拼成 `<slug>/render/silent.mp4` | `--skip-render` 认的就是这个路径 |

**四步落地：**

1. 在 dsh 里按 `mg-code-video` 的硬顺序走：`shotcraft_search` 选镜头卡（**选了卡就必须读回配方和 demo 源码照着移植**，只借卡名等于放弃卡里全部调校）→ 写一张【分镜表】（一行一镜，时长写 `172f`，别一镜建一个文本节点）→ 只写 `scene-0` 出定调帧 → **第 1 镜渲成真视频给人看**。别发静帧拼图验收：1920 缩到 650 宽会糊掉细节，双方都会误判。
2. 量产其余镜头 → `motion_render` 出这一段。规格对齐 `spec`：`{width:1920, height:1080, fps:30, duration:<段秒数>}`。**`duration` 是秒**（插件按 fps 对齐到整帧），不是帧数、也不是 `"172f"` 这种字符串——分镜表里写帧，这里换算成秒。渲染用默认 crf 14 就够（比这边 4Mbps 更足）。
3. 拿到各段 mp4 先核规格，再拼到接缝上：

   ```bash
   FF=~/Desktop/Tools/AI开源工具/bin/ffmpeg
   PROBE=~/Desktop/Tools/AI开源工具/bin/ffprobe
   P="$HOME/Desktop/AI/Bilibili Videos/<slug>"
   SEGS=(/path/seg1.mp4 /path/seg2.mp4)   # 按片子顺序排

   # 核规格：每段的宽高帧率必须一致，帧数之和要等于 scenes.json 的总帧数
   for f in "${SEGS[@]}"; do
     $PROBE -v error -select_streams v \
       -show_entries stream=width,height,r_frame_rate,nb_frames -of csv=p=0 "$f"
   done

   # 抽掉音轨 + 按顺序无损拼接（先落到临时目录，别直接覆盖）
   mkdir -p "$P/render/seg"
   i=1; : > "$P/render/seg/list.txt"
   for f in "${SEGS[@]}"; do
     $FF -y -i "$f" -an -c:v copy "$P/render/seg/s$i.mp4"
     echo "file 's$i.mp4'" >> "$P/render/seg/list.txt"
     i=$((i+1))
   done
   $FF -y -f concat -safe 0 -i "$P/render/seg/list.txt" -c:v copy "$P/render/silent.mp4"

   # 后段全部复用：打磨 → 配乐 ducking → 合轨 → 质检
   bash ~/.workbuddy/skills/bilibili-explainer/scripts/build_video.sh \
     --project "$P" --comp MyVideo --skip-render --qc
   ```

   **帧数不对就回 dsh 重渲，不要用 ffmpeg 变速凑**：`setpts` 会把动画节奏整体拉斜，画面里所有缓动都跟旁白错位，而且肉眼看不太出来。
   **拼接时 `-c copy` 报错就用重编兜底**：不同工程出来的 SPS/PPS 可能不同，concat 会把后段花屏。那时去掉 `-c copy`，改 `-c:v libx264 -crf 12 -pix_fmt yuv420p`（一次重编，画质换稳定，值得）。

4. `分镜脚本.md` 用 dsh 那份【分镜表】改写，时长直接从 `scenes.json` 抄——两边对不上时以 `scenes.json` 为准。

**首次会卡在下载**：字体 + 素材库约 145MB（落 `~/.dsh/drawai-assets/v1/`），另有 FFmpeg 和视频运行环境，各自缓存、只需一次。网络不通就用作者的网盘包，然后用 `DRAWAI_ASSETS_DIR` / `DRAWAI_FFMPEG_PATH` 指过去，别去改插件源码。

## 阶段 5 · 渲染 + 合成 + 质检

```bash
bash ~/.workbuddy/skills/bilibili-explainer/scripts/build_video.sh \
  --project "$HOME/Desktop/AI/Bilibili Videos/<slug>" \
  --comp MyVideo --entry src/my-index.tsx --qc
```

**入口是 `src/my-index.tsx`**（注册 `MyVideo` 的那个）；`dv-index.tsx` 是别的片子（DistillVsRL）的入口，写错会报找不到组合。

脚本做的事：同步 `timing.ts` → 无音轨渲染 → 人声打磨（EQ/去齿音/压缩）→ 配乐铺底 + ducking → 合轨 → 打印时长/帧数/音量 → 抽 3 帧。

**渲染规格固定 1920×1080（1080p），不要降。** 分辨率由 Composition 的 width/height 决定（写进 `my-index.tsx`）。同时 **CRF 必须 ≤ 12**：深色纯色画面用默认 CRF 时，x264 会把视频码率压到 120 kbps 左右，中文笔画边缘全糊——`build_video.sh` 已内置 `--crf 12`，改渲染命令时别把它删了。校验办法：

```bash
ffprobe -v error -select_streams v -show_entries stream=bit_rate -of csv=p=0 out.mp4
```

**别只看码率数字。** 深色纯色 + 白字的画面，实测 380 kbps 笔画依然锐利（内容简单，x264 压缩效率极高，码率低不等于糊）。真正的判据是**抽一帧放大 2.5 倍看笔画**：

```bash
ffmpeg -y -i out.mp4 -vf "select=eq(n\,5000)" -frames:v 1 /tmp/f.png
ffmpeg -y -i /tmp/f.png -vf "crop=820:180:100:140,scale=2050:450:flags=neighbor" /tmp/zoom.png
```

笔画边缘有方块或发虚才算糊。Remotion 的 `--video-bitrate` 并不强制码率（实测设 4M 只出 380 kbps），它本质仍是质量模式——所以别指望靠调这个参数救画质，先确认画面内容本身是否够锐。

配乐默认自动加（`assets/bgm/` 里随机挑一条，`--no-bgm` 关掉，`--bgm-lufs -30` 更明显）。
只调声音、画面没改时加 `--skip-render`，复用 `render/silent.mp4`，省一次 3–6 分钟。

**必查四项**：

1. 末帧不是纯背景（空白拖尾）
2. 中文字形不是方块
3. 整体响度 ≈ −16 LUFS（有配乐时 max 约 −4 dB，无配乐时约 −1.5 dB，都正常）
4. 时长和预算差 ≤ 5 秒

回听校验（强烈建议）：用 `AudioTranscribe` 转写 `narration.wav`，看数字有没有听错、断句有没有落在标点上。**自己听不出来，转写能听出来。**

## 阶段 6 · 封面（16:9 + 4:3 两版，都摆到桌面）

B 站封面编辑器要两个比例：**16:9（1920×1080）**用于稿件封面，**4:3（1440×1080）**用于同步。两版都要出；手动上传时，两版都放到桌面，别让人再去工程目录里翻。

三选一，按顺序试：

1. **代码画**（最可控）：同一个 Remotion 工程里加两个 Composition——`MyCover`（1920×1080）和 `MyCover43`（1440×1080）。
   **4:3 必须单独排版渲染**，不能拿 16:9 裁剪或补边：补边会在上下留大片空白，裁剪会切掉标题或主图（2026-11 实测两种都不好看）。
   ```bash
   npx remotion still src/my-index.tsx MyCover --frame=14 --output cover.png
   npx remotion still src/cover43-index.tsx MyCover43 --frame=20 --output cover-43.png
   ```
2. `ImageGen` 生成主视觉（WorkBuddy 专用；dsh 侧无此工具，改用视频截帧、本地 Ollama 生图或纯代码封面），再用代码压标题字。
3. 从正片抽一帧 + 文字。

整理到桌面（命名带 slug，避免多支片子互相覆盖）：

```bash
$PY ~/.workbuddy/skills/bilibili-explainer/scripts/covers_to_desktop.py \
  --cover16 "$P/cover.png" --cover43 "$P/cover-43.png" --slug <slug>
# 产出：~/Desktop/封面_16x9_<slug>.png 与 ~/Desktop/封面_4x3_<slug>.png
```

封面硬要求：**≤5MB、文字 ≤2 行、主视觉占 60% 以上**。标题字要能在手机小图上读清——把它缩到 300px 宽看一眼，读不清就加大。

## 阶段 7 · 投稿

> **`biliup` 这条路已经断了（2026-10 实测）。** 它的登录走废弃的 `passport-tv-login/qrcode`，
> 扫码永远拿不到 token；投稿 `preupload` 恒返回 `-400`；而直接调 `member.bilibili.com` 会被 WAF
> 按 TLS 指纹挡住（curl/urllib 都是 403）。**不要再折腾 biliup，直接用浏览器脚本。**

登录态就绪后（脚本会自动判断：**CDP 接管你已登录的 Chrome**，连不上才回退 cookies），投稿是**全自动**的：填标题/分区/标签/简介 → 点「立即投稿」→ 等跳转。**不要传 `--cover`** —— 封面编辑器一打开就会盖住整个表单（见踩坑 15），而封面本来就要人手动传。

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
SK=~/.workbuddy/skills/bilibili-explainer
P="$HOME/Desktop/AI/Bilibili Videos/<slug>"

# ① 先读策略库，决定这次验证什么
cat ~/.workbuddy/skills/bilibili-studio/references/playbook.md

# ② 提交（默认全自动；想先看一眼表单就去掉 --submit，会产出 qc-web-form.png）
$PY $SK/scripts/web_upload.py \
  --video "$P/out.mp4" --title "标题" --desc-file "$P/简介.txt" \
  --tags "AI,几何,数学,人工智能,科普,学习工具" \
  --partition 知识 --submit --headful --wait-min 25
```

**可能的一道人工关**：点「立即投稿」后如果弹**短信或人机验证**（异地/新设备风控），在窗口里点一下。脚本不绕过。已登录账号通常不弹，日志会直接打 `SUCCESS @60s → .../archive-process?bvid=...`。

**两版一起投**（配音版 + 纯字幕版）：第二版标题加「｜纯字幕版」后缀，简介开头写清区别，否则容易被判重复投稿。

**投完必须用稿件列表确认**——窗口可能被关掉，光看日志不可靠：

```bash
$PY $SK/scripts/check_archives.py
# state：0 = 开放浏览 / -1 = 审核中 / -30、-50 = 未通过或锁定
# 从输出里抄 BVID，接着记台账
```

**分区（2026-10 实测，务必按新的来）**：

| 内容 | 选这个 |
|---|---|
| 科普、原理、事件解读 | **知识**（tid 36） |
| 软件/工具评测 | 科技数码 / 人工智能 |
| 动手做、DIY | 手工 |
| 游戏相关 | 游戏（tid 4） |

**二级分区已经没了。** 界面上点不出来「科学科普/201」，别再照旧表找。

标签结构：2 个大词 + 4~6 个精准词 + 1~2 个系列词。例：
`我的世界,MC启动器,科普,PCL,HMCL,游戏资讯,事件解读`

投稿成功后记台账（BVID 从跳转后的 `?bvid=` 取）：

```bash
$PY ~/.workbuddy/skills/bilibili-studio/scripts/bili.py ledger add \
  --json '{"bvid":"BV1xxxx","title":"...","tid":36,"status":"submitted","hypothesis":"..."}'
```

## 阶段 8 · 交付清单

一个工程目录里应该长这样，缺哪个补哪个：

```
<slug>/
├── out.mp4            成片（1920×1080，AAC 192k）
├── cover.png          封面
├── 分镜脚本.md         每镜时长/旁白/关键数字/数据口径
├── sources.md         事实表：已证实 / 待核实 / 来源链接
├── script.json        旁白稿
├── scenes.json        帧表（tts 产出，分镜表时长从这里抄）
├── timing.ts          帧表（同上，给 Remotion 用）
├── narration.wav      整轨旁白
├── SceneKit.tsx       画面源码（下次改文案复用）
├── render/silent.mp4  无音轨画面（路线 A 由 Remotion 渲染；路线 B 从 dsh 搬进来）
└── qc/                抽帧质检图
```

`.drawai` 画布和 DrawAI 的视频工程**不进这个目录**——它们留在 dsh 的工作区里，只在成片阶段以 `silent.mp4` 的形式进来。想留下可复用的素材就把它拷进 `assets/`，别整个工程塞进来。

`分镜脚本.md` 的时长**直接抄 `scenes.json`**，不要手写——旁白一改全变。

最后：`present_files` 把 `out.mp4` 和 `cover.png` 给用户看（WorkBuddy 专用；dsh 侧改用行内反引号写出这两个文件的绝对路径），并说清"投不投、什么时候投"由他定。

---

## 踩坑（全部真实踩过）

1. **「五成三」会被听成「五乘三」。** 中文"成"和"乘"同音，数学语境下歧义致命。旁白一律写「百分之五十三」。「是零」也会被听成「失灵」，改用「是零分」。所有数字写汉字。
   同音雷区还有：「**为**遵守」和「**未**遵守」完全同音、语义相反，写「按法律法规要求」；「时区」和「十区」同音，加主语说「系统时区东八区」；「开发版」和「开发板」同音，靠上下文能分清就不必改。**改完一定要用 `AudioTranscribe` 回听**，ASR 的误听往往就是观众的误听。
2. **渲染必须 `env -u NODE_OPTIONS`。** 否则 Remotion 打包报 `EEXIST` / broker policy error。换 node 版本没用，那是环境变量注入。`build_video.sh` 已内置。
3. **片尾静默会变成空白拖尾。** `TOTAL_FRAMES` 含 `--tail`（1.3 秒），但 `SCENES` 帧数之和**不含**它。必须让最后一场吞掉：`frames = TOTAL_FRAMES - from`。
4. **整段合成无法对齐。** 必须逐句合成、逐句量时长、按 frames 补静音或截尾。音画天然同步，不用手估。
5. **场景变长后画面会干等。** 旁白放慢后一场可能 14 秒，入场动画 1 秒就演完了。用 `stagger` 让元素按旁白念到的顺序逐个出现。
6. **`select='eq(n,X)+eq(n,Y)'` 输出按 n 升序，不是书写顺序。** 按顺序读抽帧图会误判。新版 ffmpeg 用 `-fps_mode passthrough`，`-vsync` 已弃用。
7. **ffprobe 别用系统的。** Intel Mac 上 `/usr/local/Cellar/ffmpeg@7` 的 ffprobe 可能缺 `libxcb` 起不来。用 `~/Desktop/Tools/AI开源工具/bin/ffprobe`（脚本已优先用它）。
8. **本机 shell 是 zsh。** `rm -f dir/*.wav` 在无匹配时整条失败，会中断 `&&` 链。多步写成 `.sh` 用 `bash` 跑，别用 `&&` 串长条。
9. **标题党会让你死在完播率上。** 高播放 + 低完播 = 算法判定内容不匹配，长期掉权重。热点话题尤其容易手滑。
10. **`tts_narrate.py` 是「一句一场」，不是「一场多句」。** 它给每句都生成一条 SCENES 记录，同一 id 会重复出现 5 次。如果直接 `SCENES.map` 渲染，画面会被切成一句话一场、动画逐句重放。`SceneKit.tsx` 里的 `buildScenes()` 已按 id 合并并记录每句起始帧（`at`），**别把这个函数删了**——它是「旁白念到第几句，画面出第几个元素」的唯一实现。
11. **改了 `SceneKit.tsx` 必须重新拷进 Remotion 的 `src/`。** `build_video.sh` 只同步 `timing.ts`，**不碰 `MyVideo.tsx`**。少拷一次，渲染出来的还是上一版时序——而且看不出来，因为结构一模一样，只是元素晚出现几秒。改完先 `npx remotion still` 抽关键帧确认，再跑全片，能省一次 6 分钟的空等。
12. **`biliup` 已经不能用了，别再试。** 扫码走废弃接口拿不到 token、投稿 `preupload` 恒 `-400`、直连被 WAF 按 TLS 指纹拦。四条路的实测记录在 `references/publishing-pitfalls.md`，投稿一律走 `scripts/web_upload.py`。
13. **网页投稿有三个必踩的卡点**：① 首次投稿弹「投稿须知」遮住全页；② 封面上传后必须点「确认同步」再点「完成」，否则弹窗一直挡着「立即投稿」；③ 点「立即投稿」会触发短信/人机验证，**只能人来过**。所以 `--submit` 一律配 `--headful`，并提前跟用户说清楚"需要你点一下验证"。
14. **开场前 4 秒最容易空屏。** 第一个内容元素如果等第 2 句才出现，画面会有 3–5 秒只有标题。把首元素的 `delay` 提前约 24 帧（0.8 秒），让它在首句念到一半时浮出。
15. **B 站封面编辑器整块是 canvas**（`<canvas data-fabric="top" class="upper-canvas">`），按钮不在 DOM 里。`get_by_text` 找不到、坐标点击被吞、`elementFromPoint` 只返回 canvas。**自动化到这一步必须停手**，要么人手动点，要么跳过自定义封面。别再花时间试选择器。
16. **headful 模式下投稿页会自己弹出封面编辑器 + 全屏遮罩**（`.cover-editor` + `.bcc-dialog__wrap-mask`），把标题/分区/标签全挡死，连标题框都点不动。解法：填表前用 JS 直接 `remove()` 掉这些节点（`web_upload.py` 里的 `nuke_masks()`，日志会打「移除遮罩节点: N」）。移除后表单完全正常。
17. **持久化 profile 会把上一次的页面状态带进 headful**，导致遮罩一开页就出现。headful 也要用 `new_context` + 手动注入 cookie，别用 `launch_persistent_context`。
18. **画质别只看码率。** 深色纯色 + 白字的画面，实测 380 kbps 笔画依然锐利；Remotion 的 `--video-bitrate` 也不强制码率（设 4M 只出 380 kbps）。真判据是抽一帧放大 2.5 倍看笔画有没有方块/发虚。反过来，如果确实糊，别指望调 CRF 或 bitrate 救，先看画面内容本身（字体是否用了细体、是否有大量抗锯齿渐变）。
19. **drawai 0.4.1 对 dsh 版本有要求，本机是擦边过的。** 它的 peerDependency 要 `@deepseek-ai/dsh-tools >=0.1.5-rc.1`，本机 dsh 是 `0.1.3-alpha.1`（源码版，跑在 `~/Desktop/AI/deepseek-harness`）。实测模块能 import、宿主能启动、17 个工具都注册上了，但**工具真跑起来可能踩到还没实现的新 API**。所以先拿一张小图试 `diagram_apply`，别直接开整片；真报 `undefined is not a function` 再考虑升 dsh 源码，别一上来就动环境。
20. **DrawAI 和 SceneKit 不能同时供画面。** 同一支片子画面只能有一个来源，两边都改会得到两套时序，而 `timing.ts` 只对得上其中一套——偏偏结构看着一模一样，出错很难发现。切路线就整条切，别一半一半。
21. **`--skip-render` 仍然要求 `timing.ts` 存在。** 脚本第 42 行无条件检查它，所以路线 B 也必须先跑 edge-tts 出帧表。这正是"旁白是唯一时长真相"的机械保证，别绕。

## 安全红线

1. **不把未证实信息讲成事实。** 这是科普片的底线，也是唯一不能妥协的一条。
2. **发布默认全自动，但用户可随时要求预览。** 用户已授权「登录 + 传封面由人做、其余全自动」，所以默认直接 `--submit`。若他说「先给我看一眼」，就去掉 `--submit` 跑一遍填表，拿 `qc-web-form.png` 给他过目。
3. **不刷量、不互赞。** 被识别后掉权重比没流量更严重。
4. **凭证只存在本地** `~/.workbuddy/secrets/bili/cookies.json`（600），不进对话、不进日志。
5. **不绕过验证码。** 风控验证是 B 站合规要求，绕过一次可能直接封号。
6. **遇 `-352 / -412 / -509` 风控码立即停**，别重试，告知用户稍后再试。

## 文件结构

```
~/.workbuddy/skills/bilibili-explainer/
├── SKILL.md
├── scripts/
│   ├── new_project.sh              建标准工程骨架
│   ├── login_bili.py               扫码登录 + 导出 cookie（人工节点 ①）
│   ├── web_upload.py               网页投稿（biliup 已失效后的唯一路径）
│   ├── make_srt.py                 scenes.json → SRT/ASS 字幕
│   ├── burn_subtitles.sh           烧字幕 + 铺配乐，出纯字幕版
│   ├── covers_to_desktop.py        16:9 + 4:3 封面摆到桌面（配合人工节点 ②）
│   └── check_archives.py           查稿件列表状态（投稿后确认用）
├── assets/
│   ├── SceneKit.tsx                事件解读型 7 场景零件
│   └── GeometryKit.tsx             几何/理科型 6 场景 + 双版封面
└── references/
    ├── narrative-structure.md      六段式叙事 + 事实分级 + 判读四问
    └── publishing-pitfalls.md      投稿踩坑手册（biliup 四条死路 / 五个卡点）
```

底层脚本：`scripts/{tts_narrate.py,build_video.sh}`（2026-11-15 自 tts-explainer-video 并入）、`bilibili-studio/scripts/bili.py`（仅复盘与台账）。

## 完整工作流（照这个顺序走，人工只落在 ⓪ 和 ⑧）

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
SK=~/.workbuddy/skills/bilibili-explainer
P="$HOME/Desktop/AI/Bilibili Videos/<slug>"

# ⓪ 登录检查（人工 ①：手机扫码，几个月一次）
$PY $SK/scripts/login_bili.py --timeout 600

# ① 建工程
bash $SK/scripts/new_project.sh <slug>

# ② 填 sources.md（事实分级）→ 写 script.json（六段式，先算字数）

# ③ 配音 + 帧表
$PY ~/.workbuddy/skills/bilibili-explainer/scripts/tts_narrate.py \
  "$P/script.json" --voice B --out "$P"

# ④ 回听（必做）：AudioTranscribe 转写 narration.wav，查同音误听，有问题改稿重配

# ⑤ 写画面（二选一）
#    A 路由：把模板拷进工程改 CONTENT，再同步进 Remotion
cat $SK/assets/GeometryKit.tsx > ~/Desktop/Tools/AI开源工具/OpenMontage/remotion-composer/src/MyVideo.tsx
#    B 路由：去 dsh 的 DrawAI 分段出（每段 ≤60 秒），抽音轨拼成 $P/render/silent.mp4，
#            然后下面 ⑥ 加 --skip-render。契约见「阶段 4 · 路线 B」

# ⑥ 渲染 + 合成配音版
bash ~/.workbuddy/skills/bilibili-explainer/scripts/build_video.sh \
  --project "$P" --comp MyVideo --entry src/my-index.tsx --qc

# ⑦ 字幕版（画面复用，不重渲）
$PY $SK/scripts/make_srt.py "$P/scenes.json" -o "$P/subs.ass" --fontsize 62 --margin-v 60
bash $SK/scripts/burn_subtitles.sh --video "$P/render/silent.mp4" --srt "$P/subs.ass" \
  --bgm ~/.workbuddy/skills/bilibili-explainer/assets/bgm/ambient-A.m4a \
  --out "$P/out-subtitled.mp4"

# ⑧ 封面：16:9 和 4:3 分别渲染，然后摆到桌面（人工 ② 就是传这两个文件）
cd ~/Desktop/Tools/AI开源工具/OpenMontage/remotion-composer
npx remotion still src/my-index.tsx MyCover --frame=14 --output "$P/cover.png"
npx remotion still src/cover43-index.tsx MyCover43 --frame=20 --output "$P/cover-43.png"
$PY $SK/scripts/covers_to_desktop.py --cover16 "$P/cover.png" --cover43 "$P/cover-43.png" --slug <slug>

# ⑨ 投稿（自动）
$PY $SK/scripts/web_upload.py --video "$P/out.mp4" --title "标题" --desc-file "$P/简介.txt" \
  --tags "..." --partition 知识 --submit --headful --wait-min 25

# ⑩ 确认 + 记账
$PY $SK/scripts/check_archives.py
$PY ~/.workbuddy/skills/bilibili-studio/scripts/bili.py ledger add \
  --json '{"bvid":"BVxxxx","title":"...","tid":36,"status":"submitted","hypothesis":"..."}'
```

**人只出现在两处**：⓪ 扫码登录、⑧→人工传封面。其余 10 步全自动。若 ⑨ 弹验证码，顺手点一下。

## 相关技能

- 配音/渲染脚本：`scripts/{tts_narrate.py,build_video.sh,polish_audio.sh,mix_audio.sh,make_pad.sh}`
- 投稿/复盘/策略库：`bilibili-studio`（本技能调用它的 `bili.py`）
- MG 动效画面（dsh 侧）：`~/.dsh/skills/mg-code-video` —— 配合 `dsh-drawai` 插件用，管镜头卡、整片风格、场景源码和渲染闸门。本技能负责把它产出的无声画面接进合成链
- 纯离线（断网可用）：`zero-cost-video`
- 设计规范：`references/design-rules.md`
