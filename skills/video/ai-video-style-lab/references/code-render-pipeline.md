# 代码渲染管线（怎么真的做出来）

三家共同的技术底牌只有一句：**不是文生视频，是让模型写渲染代码，逐帧确定性出片。**
好处：每个像素、每个数字、每个时间点都可控可改；坏处：要先会写代码。
本文给三条可落地的路线，按"可控性"排序。

## 路线一：Python 逐帧渲染 + ffmpeg 合成（最可控，推荐）

适合：线稿风、数据图表、字幕密集型（风格 B / C）。

```
for frame in range(total_frames):
    img = draw_frame(t=frame/fps)      # PIL 画一帧
    img.save(f"./frames/{frame:05d}.png")
ffmpeg -framerate 30 -i ./frames/%05d.png -i voice.wav -c:v libx264 -pix_fmt yuv420p out.mp4
```

优点：所见即所得，改一个数字重渲即可；不需要浏览器；不吃显卡。
注意：`draw_frame(t)` 必须是**纯函数**（只依赖 t），否则改一处会连带毁掉别的帧。

## 路线二：单文件 HTML（Canvas/WebGL）+ 浏览器录制

适合：粒子、着色器、透视隧道、实时音频（风格 A）。

```html
<canvas id=c width=1920 height=1080></canvas>
<script>
const ctx = c.getContext('2d');
function frame(t){ /* 全部绘制逻辑，只依赖 t */ }
// 固定帧率驱动，不要用 requestAnimationFrame 的真实时间
let f=0; const FPS=30;
setInterval(()=>{ frame(f/FPS); f++; }, 1000/FPS);
</script>
```

录制：用 Chrome 无头 + CDP `Page.startScreencast`，或 Playwright 的 `recordVideo`。
优点：能做实时音频合成（Web Audio 现场生成配乐，正是风格 A 的做法）。
风险：录屏会掉帧。**必须校验**：渲染完后抽帧数，确认 `帧数 ≈ 时长 × FPS`。

## 路线三：Remotion（React → 逐帧 mp4）

适合：复杂排版、需要复用组件、要 React 生态。
需要 Node（本机 v22.22.2 可用）+ Chromium 下载。优点是天然逐帧、无掉帧。
代价：首次安装较重，调试比纯 HTML 慢。

## 本机环境现状（实测于 2026-10-22）

| 项 | 状态 | 备注 |
|---|---|---|
| `ffmpeg` | ❌ **坏的** | 缺 `libxcb.1.dylib`。修复：`brew reinstall ffmpeg` |
| `say`（TTS） | ✅ 可用 | 中文音色：Eddy / Flo / Grandma / Grandpa（zh_CN）、Meijia（zh_TW） |
| Node | ✅ v22.22.2 | 路径 `~/.workbuddy/binaries/node/versions/22.22.2-6/bin/node` |
| Python + Pillow | ✅ | `python3` |
| Chrome / 豆包浏览器 | ✅ | 可做无头录制 |

**动手前第一条命令**：`ffmpeg -version`。坏了先修，否则整条链路断在最后一步。

## 音频三选一

1. `say -v Flo "文本" -o line.aiff` → 逐句合成 → 按时间码拼接。零成本、离线、音色一般。
2. 外部 TTS（Gemini Flash TTS / 各家 API）→ 质量高、要联网要钱。
3. Web Audio 现场合成 BGM（120 BPM 电子底 + 噪声混响）→ 完全原创、零素材，风格 A 的做法。

混音铁律：旁白比 BGM 高 **12–18 dB**；BGM 在旁白段落压到 −24 LUFS 左右；片尾留 1.5 秒纯静音。

## 渲染前必须过的 8 条

- [ ] `draw_frame(t)` 是纯函数，没有随机数（要随机就固定 seed）
- [ ] 分辨率 1920×1080 或 1080×1920，帧率锁定 30（不要 29.97）
- [ ] 字幕距底边 ≥ 8%，距左右 ≥ 6%（手机竖屏要看一遍）
- [ ] 全片颜色数 ≤ 3（底 + 主 + 辅）
- [ ] 单帧信息块 ≤ 2（风格 C 是 1）
- [ ] 每个数字都有单位
- [ ] 结尾有 1.5 秒静默/黑场，不加关注口播
- [ ] 导出后抽 5 帧回看，确认没有糊字、没有偏色、没有掉帧

## 成本参考

| 路线 | 5 分钟片的实际耗时 | 金钱成本 |
|---|---|---|
| Python 逐帧 | 写代码 2–4 小时 + 渲染 5–15 分钟 | 0 |
| HTML + 录屏 | 写代码 2–4 小时 + 录制 1 倍时长 | 0 |
| Remotion | 写代码 3–5 小时 + 渲染 10–20 分钟 | 0 |
| 文生视频抽卡 | 剪 2 小时，但反复抽卡不可控 | 按秒计费 |

这张表是三家 UP 主选代码路线的真正原因：**不是省钱，是可控**。
