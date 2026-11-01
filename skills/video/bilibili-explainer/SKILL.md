---
name: bilibili-explainer
description: 科普讲解短片的一条龙流水线——核实事实 → 写六段式旁白 → edge-tts 配音 → Remotion 代码画图 → FFmpeg 合成 → 生成封面 → 投稿 B 站。所有产物固定落在 `~/BilibiliVideos/<slug>/`。触发词：做科普视频、讲解视频、B站投稿、发视频到B站、热点科普、事件解读、做个讲原理的视频、把这份材料做成视频、生成旁白、中文配音、Remotion 渲染、edge-tts、科普短片、辟谣视频。
version: 1.0.0
---

# 科普短片 · 制作到投稿

一条命令到成片，最后一步上传要人点头。核心不是"自动生成视频"，而是**先保证讲的是真的，再保证讲得清**。

## 一条流水线

```
选题 → 事实分级 → 六段式旁白(script.json) → 配音(timing.ts) → 7 个 Scene → 渲染 → 质检 → 封面 → 投稿
```

产物根目录**固定**：

```
~/BilibiliVideos/<slug>/
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
PY=python3
$PY -c "import edge_tts; print(edge_tts.__version__)"       # 配音
ls ~/Desktop/Tools/AI开源工具/OpenMontage/remotion-composer  # 渲染工程
$PY -c "import playwright; print('playwright ok')"           # 网页投稿（biliup 已废弃）
ls ~/Library/Caches/ms-playwright/chromium-*/chrome-mac-x64/  # 浏览器内核，必须有 Chrome for Testing
$PY ~/.workbuddy/skills/bilibili-studio/scripts/bili.py auth-check   # 数据/复盘用，投稿不依赖它
```

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
$PY ~/.workbuddy/skills/tts-explainer-video/scripts/tts_narrate.py \
    "~/BilibiliVideos/<slug>/script.json" \
    --voice B --out "~/BilibiliVideos/<slug>"
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

## 阶段 4 · 画画面

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

## 阶段 5 · 渲染 + 合成 + 质检

```bash
bash ~/.workbuddy/skills/tts-explainer-video/scripts/build_video.sh \
  --project "~/BilibiliVideos/<slug>" \
  --comp MyVideo --entry src/dv-index.tsx --qc
```

脚本做的事：同步 `timing.ts` → 无音轨渲染 → 人声打磨（EQ/去齿音/压缩）→ 配乐铺底 + ducking → 合轨 → 打印时长/帧数/音量 → 抽 3 帧。

配乐默认自动加（`assets/bgm/` 里随机挑一条，`--no-bgm` 关掉，`--bgm-lufs -30` 更明显）。
只调声音、画面没改时加 `--skip-render`，复用 `render/silent.mp4`，省一次 3–6 分钟。

**必查四项**：

1. 末帧不是纯背景（空白拖尾）
2. 中文字形不是方块
3. 整体响度 ≈ −16 LUFS（有配乐时 max 约 −4 dB，无配乐时约 −1.5 dB，都正常）
4. 时长和预算差 ≤ 5 秒

回听校验（强烈建议）：用 `AudioTranscribe` 转写 `narration.wav`，看数字有没有听错、断句有没有落在标点上。**自己听不出来，转写能听出来。**

## 阶段 6 · 封面

三选一，按顺序试：

1. **代码画**（最可控）：在同一个 Remotion 工程加一个 `Cover` 组合，1920×1080 单帧 `npx remotion still`。风格和正片一致。
2. `ImageGen` 生成主视觉，再用代码压标题字。
3. 从正片抽一帧 + 文字。

封面硬要求：**≤5MB、16:9、文字 ≤2 行、主视觉占 60% 以上**。标题字要能在手机小图上读清——把它缩到 300px 宽看一眼，读不清就加大。

## 阶段 7 · 投稿

> **`biliup` 这条路已经断了（2026-10 实测）。** 它的登录走废弃的 `passport-tv-login/qrcode`，
> 扫码永远拿不到 token；投稿 `preupload` 恒返回 `-400`；而直接调 `member.bilibili.com` 会被 WAF
> 按 TLS 指纹挡住（curl/urllib 都是 403）。**不要再折腾 biliup，直接用浏览器脚本。**

先用 `scripts/web_upload.py` 做一次不提交的填表，把计划摆给用户看：

```bash
PY=python3
SK=~/.workbuddy/skills/bilibili-explainer
P="~/BilibiliVideos/<slug>"

# ① 先读策略库，决定这次验证什么
cat ~/.workbuddy/skills/bilibili-studio/references/playbook.md

# ② 只填表不提交，产出 qc-web-form.png 给用户过目
$PY $SK/scripts/web_upload.py \
  --video "$P/out.mp4" --title "标题" --desc-file "$P/简介.txt" \
  --tags "我的世界,MC启动器,科普,PCL,HMCL,游戏资讯,事件解读" \
  --partition 知识 --cover "$P/cover.png"

# ③ 用户明确说「发」之后，开有头窗口提交
$PY $SK/scripts/web_upload.py \
  --video "$P/out.mp4" --title "标题" --desc-file "$P/简介.txt" \
  --tags "我的世界,MC启动器,科普" --partition 知识 \
  --cover "$P/cover.png" --submit --headful --wait-min 15
```

**必经的一道人工关**：点「立即投稿」后 B 站会弹**短信或人机验证**（异地/新设备风控）。
这个脚本不绕过，也不该绕过。`--headful` 会让窗口置顶，你只需要在窗口里把验证点完。

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
├── render/silent.mp4  无音轨画面
└── qc/                抽帧质检图
```

`分镜脚本.md` 的时长**直接抄 `scenes.json`**，不要手写——旁白一改全变。

最后：`present_files` 把 `out.mp4` 和 `cover.png` 给用户看，并说清"投不投、什么时候投"由他定。

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

## 安全红线

1. **不把未证实信息讲成事实。** 这是科普片的底线，也是唯一不能妥协的一条。
2. **发布必须二次确认。** 先用 `web_upload.py` 不带 `--submit` 跑一遍填表，把标题/简介/标签/分区/封面给用户看，明确说"发"之后才加 `--submit`。
3. **不刷量、不互赞。** 被识别后掉权重比没流量更严重。
4. **凭证只存在本地** `bilibili-studio/data/cookies.json`（600），不进对话、不进日志。
5. **不绕过验证码。** 风控验证是 B 站合规要求，绕过一次可能直接封号。
6. **遇 `-352 / -412 / -509` 风控码立即停**，别重试，告知用户稍后再试。

## 文件结构

```
~/.workbuddy/skills/bilibili-explainer/
├── SKILL.md
├── scripts/
│   ├── new_project.sh              建标准工程骨架
│   └── web_upload.py               网页投稿（biliup 已失效后的唯一路径）
├── assets/SceneKit.tsx             7 场景零件库（改文案即可复用）
└── references/
    ├── narrative-structure.md      六段式叙事 + 事实分级 + 判读四问
    └── publishing-pitfalls.md      投稿踩坑手册（biliup 四条死路 / 五个卡点）
```

底层复用：`tts-explainer-video/scripts/{tts_narrate.py,build_video.sh}`、`bilibili-studio/scripts/bili.py`（仅复盘与台账）。

## 一条命令复现本次成果

```bash
bash ~/.workbuddy/skills/bilibili-explainer/scripts/new_project.sh <slug>   # 建工程
# 填 sources.md → 写 script.json → tts_narrate.py → 改 CONTENT → build_video.sh
$PY ~/.workbuddy/skills/bilibili-explainer/scripts/web_upload.py \
  --video out.mp4 --title "..." --desc-file 简介.txt --tags "..." \
  --partition 知识 --cover cover.png --submit --headful
```

## 相关技能

- 配音/渲染底层：`tts-explainer-video`（本技能调用它的两个脚本）
- 投稿/复盘/策略库：`bilibili-studio`（本技能调用它的 `bili.py`）
- 纯离线（断网可用）：`zero-cost-video`
- 设计规范：`references/design-rules.md`（在 tts-explainer-video 里）
