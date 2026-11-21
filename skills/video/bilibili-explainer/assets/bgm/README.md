# assets/bgm/ — 配乐池

`build_video.sh` 默认 `--bgm auto`：从**这个目录**随机挑一条，铺在人声下面并自动 ducking。
目录里没有文件就静默跳过，不会报错。

## 放什么

| 要求 | 说明 |
|---|---|
| **必须无人声** | 有歌词的歌会和旁白打架，ducking 也救不了 —— 观众的大脑会同时追两条语言线 |
| 60–120 BPM，或干脆无节奏 | 快节奏配乐会让 4 字/秒的解说显得赶 |
| 没有突兀的鼓点/转场音效 | 那些音效要在时间轴上对位，随机铺底只会显得脏 |
| 结尾可循环 | 短曲子会被 `-stream_loop` 循环，接缝处有明显终止感的会露馅 |

响度不用管，脚本会把每条都压到 `--bgm-lufs`（默认 −33 LUFS）再混。

## 命名

`情绪-调性.扩展名`，例如：

```
calm-A.m4a        # 平静、偏暖，适合原理讲解
tense-D.m4a       # 紧张、偏暗，适合"问题/风险"段落
uplift-C.m4a      # 明亮、收尾用
```

一个片子只用一条（避免风格跳），所以池子里留 3–6 条够用。当前目录里只有 `ambient-A.m4a`，
是 `make_pad.sh` 合成的氛围垫（无旋律的 drone），能直接用，也能当混音测试素材。

## 去哪找（按省事程度排）

1. **Pixabay Music** — CC0 类授权，商用免署名，量最大，先在这里搜 `ambient` / `documentary` / `corporate minimal`
2. **Free Music Archive** — 按 CC 协议筛，注意每首的授权不同
3. **YouTube Audio Library** — 免费，部分要求署名
4. **Kevin MacLeod (incompetech)** — CC-BY，**必须署名**，科普片常用

## 授权红线（投 B 站尤其注意）

- **CC0 / Pixabay**：随便用，省事首选。
- **CC-BY**：必须在简介里写「音乐：曲名 - 作者 (协议)」，漏了就是侵权。
- **CC-BY-NC**：**不能接商单、不能开创作激励收益**。你这条片子以后要是接广告，NC 授权就作废了。
- **B 站曲库 / 平台内音乐**：只能在该平台站内用，导出去别处就违规。

拿不准就用 `make_pad.sh` 自己合成：100% 自有，零风险。

## 自己合成一条

```bash
bash ../scripts/make_pad.sh --dur 180 --key A            # A 小调，暗一点
bash ../scripts/make_pad.sh --dur 180 --key C --bright   # C 大调，亮一点
```
