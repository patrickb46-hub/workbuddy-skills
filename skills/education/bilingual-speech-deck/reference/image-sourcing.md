# 取图细则（真实图片，零 AI）

## 原则

1. **一张图顶十句话**：优先选能"自己说明问题"的画面（蜘蛛网电线 / 人群围拍 / 空荡的街道）。
2. **可溯源**：每张图必须能指回一个可公开访问的页面（媒体文章 / 政府网站）。存图时同时记 `purl`。
3. **不美化现实**：负面场景（扰民、拥挤、施工）同样用真实新闻图，不用"看起来更美"的替代图。

## 哪些图不要

- AI 生成图、Midjourney/文生图产物。
- 图库预览图（摄图网、视觉中国 watermarked preview）。
- 带播放器控件、点赞数、"小红书"水印、地名贴纸的社媒截图。
- 加了滤镜/后期调色的"网红照"，除非来源本身是媒体。
- 分辨率长边 < 800px（投影会糊）。

## 获取路径（国内网络可用）

### A. 权威媒体文章页 → 提 `<img>`

```bash
python3 scripts/grab.py "<文章URL>" ["<文章URL2>" ...]
```

已知可直连、图片质量好的站点：
`news.cn` / `xinhuanet.com`（相对路径需拼 `https://www.news.cn/<年-月/日>/`）、
`people.com.cn`（需 `curl -k`，证书链问题）、
`cctv.com` / `jingji.cctv.com`（`p2.img.cctvpic.com`）、
`huanqiu.com`（`rs-channel.huanqiucdn.cn`）、
`peopleapp.com`（`rmrbcmsonline.peopleapp.com`）、
`thepaper.cn`、`whb.cn`（文汇报）、`xuhui.gov.cn`。

`news.qq.com` / `new.qq.com` 正文图片由 JS 注入，抓不到——换同题报道的镜像站点。

### B. Bing 图片搜索（拿不到文章页时的主力）

```bash
python3 scripts/bing_img.py <tag> "<中文关键词>" 14
```

产物：
- `cand/<tag>/` 下载的原图
- `sheet_<tag>.jpg` 4 列缩略图对照表（带分辨率）
- `meta_<tag>.json` 每张图的 `purl`（来源页）与标题

关键词写法建议：`地点 + 具体场景 + 时间`，例如
`武康大楼 架空线 电线 改造前`、`武康路 梧桐 街景 老房子`、`武康路 蝴蝶结阳台 人群`。

### C. 被墙的图库（别试）

`commons.wikimedia.org`、`upload.wikimedia.org`、`google.com` 的图片 CDN 在本机会 curl 超时；
`image.baidu.com/search/acjson` 返回 `Forbid spider access`。

## 命名与归档

```
assets/
  then_cables.jpg      # 过去：架空线密布
  now_clean.jpg        # 现在：天际线清朗
  bow_grandma.png      # 事件：蝴蝶结阳台与住户
  bow_crowd.png        # 事件：楼下围拍的人群
  plaque.png           # 证据：优秀历史建筑铭牌
```

文件名用「时间点_主体」或「事件_细节」，让 later 的排版代码可读。

## 署名

- 页脚 caption：`Photo: Xinhua / Wenhui Daily`（一页最多两个来源）。
- 末页专列 `IMAGES` 清单，逐条写"机构 — 拍的是什么"。
- 演讲稿附录再列一遍，方便被问到"这图哪来的"。
