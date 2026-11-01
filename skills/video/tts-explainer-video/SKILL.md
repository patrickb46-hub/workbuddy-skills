---
name: tts-explainer-video
description: 用中文配音驱动、代码绘制画面的讲解短片生产流水线——edge-tts 逐句配音（晓晓 B / 晓伊 E）、按实测时长对帧、Remotion 画图表与示意、FFmpeg 合成质检。触发词：做科普视频、讲解短片、知识视频、配音视频、生成旁白、中文配音、给视频配旁白、做个讲原理的视频、数据可视化短片、把这份材料做成视频、Remotion 渲染、edge-tts。
agent_created: true
---

# 配音驱动的讲解短片

> **做科普片 / 要投 B 站，先看 `bilibili-explainer`。** 那个技能把本技能包在里面（事实核查 → 六段式旁白 →
> 配音 → 画面 → 生成封面 → 投稿 → 复盘），产物固定落在 `~/BilibiliVideos/<slug>/`。
> 本技能保留为底层能力：只想单独做一段配音短片、不需要投稿时，直接按下面三步走。

## 何时用

要做一段**讲清一件事**的短片（60–150 秒）：原理讲解、数据对比、实验复盘、课程汇报、
技术科普。画面靠代码画（图表、示意、流程、文字动效），配音靠 TTS，全程零成本。

**不适用**：需要真人出镜、实拍质感、长镜头叙事的片子。那些要走付费视频模型。

## 三步流水线

```
旁白稿(一行一句) → tts_narrate.py → timing.ts + narration.wav → 改 4 个 Scene
                                                          → build_video.sh（打磨 + 配乐 + 合轨）→ out.mp4
```

### 0. 先算清时长，别写完才发现要 4 分钟

中文 TTS 的自然语速是 **4.1 字/秒**（实测值）：

| 语速 | 感觉 |
|---|---|
| 4.0–4.3 字/秒 | **自然**，有呼吸，句间留 0.6 秒 |
| 4.5–4.8 | 偏快，适合信息密集的段落 |
| 5.4 以上 | **机械**，逗号被吃掉、句子挤成一串 —— 这是"配音很假"的头号原因 |

时长公式：`总秒数 ≈ 旁白字数 ÷ 4.1 + 场数 × 0.6`

### 1. 写旁白稿

一行一句，空行和 `#` 开头会被忽略。每句**不超过 25 字**，超过就拆——
长句断句 TTS 处理得不如人自然。存成 `script.txt` 放工程根目录。

**数字必须写成汉字「百分之五十三」**，原因见踩坑第 1 条。

### 2. 配音 + 出时长表

```bash
python3 <skill>/scripts/tts_narrate.py script.txt --voice B --out ~/Desktop/my-video
```

| 参数 | 说明 |
|---|---|
| `--voice B` | 晓晓，女，温和 —— **科普默认** |
| `--voice E` | 晓伊，女，活泼一点 |
| `--voice C` / `D` | 云健（男，纪录片解说感）/ 云希（男，年轻）。备用 |
| `--rate -6%` | 默认。更慢用 -10%，信息更密用 -2% |
| `--gap 0.6` | 句间留白。叙述型 0.6，教学型 0.8 |
| `--piper` | 强制走离线 Piper（快、平、机械感明显，只在断网时用） |

脚本会打印每句的**字/秒**，超过 4.8 会标警告，那就把 `--rate` 再放慢。

产出：`narration/<NN>.wav`、`narration.wav`、`timing.ts`、`scenes.json`。

### 3. 画画面

把 `assets/remotion-template/` 两个文件拷进 Remotion 工程的 `src/`：

```bash
cp <skill>/assets/remotion-template/ExplainerTemplate.tsx <remotion>/src/MyVideo.tsx
cp <skill>/assets/remotion-template/dv-index.tsx          <remotion>/src/my-index.tsx
```

拷完**先改 import**：`my-index.tsx` 里 `from './ExplainerTemplate'` 要改成 `from './MyVideo'`，
否则渲染时报 `Module not found`（这是改名后唯一必须同步的地方）。

改 `MyVideo.tsx` 里的 4 个 Scene（标题页 / 对照 / 柱状图 / 结论）。
需要的零件已写好：`Reveal` `Head` `Chart` `Arrow` `Box` `SceneShell`。
`COMPONENTS` 的 key 必须和 `SCENES` 的 id 一一对应（`s1`→`s1`），多出来的场景不会渲染。

**用独立入口 `my-index.tsx`，不要动工程原有的 `Root.tsx`** —— 多个视频各自一个入口，互不干扰。

设计约束（与 diagram-design 一致，别凭感觉突破）：
- 一屏最多 6 个视觉元素，密度 4/10
- 强调色只给 1–2 处，其余灰阶；不用阴影、不用渐变
- 4px 网格；中文显式写 `fontFamily: '"PingFang SC", sans-serif'`（不写会渲染成方块）
- 数字用等宽体（`MONO`），中文用黑体，两者别混用同一个 fontFamily

### 4. 渲染 + 合成 + 质检

```bash
bash <skill>/scripts/build_video.sh --project ~/Desktop/my-video --comp MyVideo \
     --entry src/my-index.tsx --qc
```

脚本做的事：同步 `timing.ts` → 无音轨渲染 → 人声打磨 → 配乐混音（ducking）→ 合轨 → 打印时长/帧数/音量 → 抽 3 帧。

只改声音不想重渲染：加 `--skip-render`，复用 `render/silent.mp4`，省 3–6 分钟。调音时全靠它。

必查三项：**末帧不能是纯背景**（空白拖尾）、**中文字形不是方块**、**整体响度 ≈ −16 LUFS**
（`max_volume` 有配乐时约 −4 dB、无配乐时约 −1.5 dB，都是正常的）。

### 5. 人声打磨（`build_video.sh` 默认已执行）

`polish_audio.sh` 在合轨前跑一条 DSP 链，纯 CPU、几秒完事，不需要 GPU 或模型：

| 环节 | 参数 | 作用 |
|---|---|---|
| 高通 | 80 Hz | 去掉低频轰鸣、口水音 |
| EQ | 280 Hz −1.5 dB | 去「箱音」的闷感 |
| EQ | 3.2 kHz +1.8 dB | 字头、辅音的**清晰度**，最听得出来的一档 |
| EQ | 9 kHz +1.0 dB | 一点空气感，再多就发虚 |
| deesser | i=0.45 | 压掉 s / sh / c 的刺耳 |
| 压缩 | 2.5:1 / −18 dB 起 / 8ms 攻 / 180ms 放 | 把每句的音量差压平 |
| loudnorm | 两遍，−16 LUFS / TP −1.5 | 一遍测、一遍应用，比单遍准 |

实测（`mc-launcher-ban` 的 187 秒旁白，走同一条链）：

| 指标 | 原始 | 打磨后 |
|---|---|---|
| 整体响度 | −19.5 LUFS | −16.0 LUFS |
| 真峰值 | −0.4 dBFS | −1.5 dBFS |
| 2.5–5 kHz（相对宽带）| −14.0 dB | −11.8 dB |
| LRA | 3.5 LU | 3.0 LU |

只用一档时优先动 **3.2 kHz 的 +1.8 dB**，那是"清晰"和"闷"的分界线。

参数：`--lufs -14`（B 站偏响）/ `--denoise`（**自己录音**、底噪明显时才开 `afftdn`；edge-tts 干声开了只掉细节）/ `--dry`（只处理 15 秒导 m4a 试听）。
`build_video.sh` 里想关掉：`--no-polish`。

> **别在 Intel Mac 上指望 VoiceStudio（debpalash/VoiceStudio）做这一步。** 官方硬件表写明
> `Intel Mac | App UI only; connect to a remote backend` —— 这台 2018 款 MBP 只能跑界面，
> 推理要连远程后端。它擅长的是克隆音色、视频配音换语种，不是给已有旁白做母带处理；
> 音质打磨用 FFmpeg 更准、更快、更可控。

### 6. 配乐（默认自动加）

`build_video.sh` 默认 `--bgm auto`：从 `assets/bgm/` 随机挑一条铺底，**没人声时自动升回来、
人一开口自动退 16–20 dB**。目录空着就静默不加。

| 参数 | 说明 |
|---|---|
| `--bgm <文件>` | 指定这一条（想要特定情绪时用） |
| `--bgm auto` | 默认：从 `assets/bgm/` 随机 |
| `--bgm-lufs -33` | 配乐垫底响度。−30 存在感更强，−36 几乎只留氛围 |
| `--no-bgm` | 这条片子不要配乐（严肃实验/数据片可以不铺） |

**ducking 是这套东西唯一不能省的一步。** 人声一响，`sidechaincompress` 按人声电平压配乐
（attack 15ms 抢在人声前面，release 400ms 避免一停一顿地抽气）；人声停，配乐自己回来。
不做这一步就只能把配乐压到听不见 —— 那等于没加。

实测（同一段 187 秒旁白 + 氛围垫）：

| 时段 | 未 duck | 已 duck | 变化 |
|---|---|---|---|
| 说话中 3.0s | −33.7 dB | −49.6 dB | −15.9 dB |
| 停顿中 11.0s | −38.0 dB | −38.0 dB | ±0 |
| 说话中 100s | −31.9 dB | −51.3 dB | −19.4 dB |

曲目要求、去哪找、CC 授权红线（**CC-BY-NC 不能接商单**）都写在 `assets/bgm/README.md`。
没有合适音乐时自己合成一条：`bash scripts/make_pad.sh --key A --dur 180`（无旋律 drone，
零版权风险，`assets/bgm/ambient-A.m4a` 就是这么来的）。

> 两个容易翻车的点：① 配乐**必须无人声**，有歌词会和旁白抢语言通道，ducking 救不了；
> ② 片头 3 秒和片尾 3 秒留**只有配乐**的空白（`tts_narrate.py` 的 `--tail` 已经在管片尾），
> 一开口就压着音乐进来会显得挤。

## 踩坑（全部真实踩过）

1. **「五成三」会被听成「五乘三」。** 中文"成"和"乘"同音，数学语境下歧义致命。
   旁白一律写「百分之五十三」。「是零」也会被听成「失灵」，改用「是零分」这类不易混的说法。
   自检：用 `AudioTranscribe` 回听 `narration.wav`，看数字有没有听错、断句有没有落在标点上。
2. **渲染必须 `env -u NODE_OPTIONS`。** 否则 Remotion 打包报 `EEXIST` / broker policy error。
   换 node 版本没用——那是环境变量注入，不是二进制问题。`build_video.sh` 已内置。
3. **片尾静默会变成空白拖尾。** `TOTAL_FRAMES` 含 `--tail`（默认 1.3 秒），但 `SCENES` 帧数之和不含它。
   装配时**必须让最后一场吞掉这段**：`frames = TOTAL_FRAMES - from`。
4. **整段合成无法对齐。** 必须逐句合成、逐句量时长、按 `frames` 给每句补静音或截尾，
   音画天然同步，不必手工估每句话多长。
5. **场景变长后画面会干等。** 旁白放慢后场景可能到 14 秒，而入场动画 1 秒就结束了。
   柱状图用 `stagger`（默认 30 帧 ≈ 1 秒）让柱子按旁白念到的顺序逐根长出，图和声就同步了。6. **`select='eq(n,X)+eq(n,Y)'` 输出按 n 升序，不是书写顺序。** 抽帧检查按顺序读图会误判。
   新版 ffmpeg 用 `-fps_mode passthrough`，`-vsync` 已弃用。
7. **ffprobe 别用系统的。** Intel Mac 上 `/usr/local/Cellar/ffmpeg@7` 的 ffprobe 可能缺 `libxcb` 起不来，
   用 `~/Desktop/Tools/AI开源工具/bin/ffprobe`（`build_video.sh` 已优先用它）。
8. **本机 shell 是 zsh。** `rm -f dir/*.wav` 在无匹配时整条命令失败，会中断 `&&` 链并让后续变量赋值不执行。
   多步脚本写成 `.sh` 用 `bash script.sh` 跑，别用 `&&` 串一长条。

## 交付

`out.mp4`（1920×1080，AAC 192k）+ `分镜脚本.md`（每镜时长、语速、旁白、关键数字、数据口径）。
分镜表里的时长直接抄 `scenes.json` 每场的 `sec`，不要手写——旁白一改全变。

## 相关

- 设计与版式细节：`references/design-rules.md`
- Remotion 工程：`~/Desktop/Tools/AI开源工具/OpenMontage/remotion-composer`
- 完整样板（10 场景、柱状图硬切反转、118 秒）：`distill-vs-rl-video/`
- 纯离线（不联网）路线：`~/.workbuddy/skills/zero-cost-video`
