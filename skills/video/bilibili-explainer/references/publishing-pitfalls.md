# 投稿踩坑手册（2026-10 实测）

> 每一条都是真金白银换来的。做之前扫一眼，能省一小时。

## 一、biliup 这条路已经断了

`biliup-rs v0.2.4`（GitHub 上当前最新，2025-07 发布）和 B 站现在的接口脱节，四处全挂：

| 尝试 | 结果 | 根因 |
|---|---|---|
| `biliup login` 扫码 | 终端出二维码，手机扫了没反应，`biliup-cookies.json` 的 `access_token` 始终为空 | 它调 `passport-tv-login/qrcode/auth_code` + `/poll`，这是老 TV 端接口，已被 `passport-login/web/qrcode` 取代 |
| 手工构造 `token_info` 塞进去 | 文件能读，投稿仍失败 | token 是服务端签发的，伪造不出来 |
| `biliup upload --submit client/web/app` | 秒回 `{"code":-400,"message":"请求错误"}`，**没有任何上传进度** | 失败在 `preupload` 阶段，与视频内容无关 |
| `--line bda2 / qn / alia` | 三条线路一样 `-400` | 不是线路问题 |
| curl / urllib 直连 `member.bilibili.com/preupload` | 403 + 阿里云 WAF 的 HTML 页面 | 按 **TLS 指纹**拦，改 UA、补 `buvid4`（`/x/frontend/finger/spi`）都没用 |

**结论：不要在 biliup 上再花时间。** 需要投稿直接走 `scripts/web_upload.py`。

## 二、唯一跑通的链路：真实浏览器 + 已有 cookie

```
Playwright(Chrome for Testing, headful) + cookies.json 注入 → 网页 UI 操作
```

要点：

1. **必须用 Chrome for Testing**，不能用 `chromium_headless_shell`（Playwright 默认会找它，版本对不上还会报
   `Executable doesn't exist`）。路径：
   `~/Library/Caches/ms-playwright/chromium-<ver>/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`
   用 `executable_path=` 显式指定。
2. **cookie 注入**：`cookies.json` 里每个键转成 `{name, value, domain: ".bilibili.com", path: "/"}`。
3. **先验证登录态**：页面出现「成为UP主的第 N 天」就说明 cookie 有效。
4. **文件上传用 `set_input_files`**，不要指望浏览器扩展或页面 JS —— `<input type=file>` 的 value 受安全策略保护，JS 写不进去。

## 三、网页投稿的五个卡点

### 1. 首次投稿会弹「投稿须知」

遮罩层 `videoup-notification-dialog`，把标题输入框和所有按钮都挡住，报错是 `subtree intercepts pointer events`。
处理：依次找「我已知晓 / 我知道了 / 确定 / 同意 / 关闭」点掉。

### 2. 分区没有二级了

点开分区选择器，一级直接列出：娱乐、影视、音乐、舞蹈、动画、绘画、鬼畜、游戏、资讯、知识、人工智能、
科技数码……**没有「科学科普」**。

- 科普 / 原理 / 事件解读 → **知识**
- 软件工具评测 → 科技数码 / 人工智能
- 动手 DIY → 手工
- 游戏 → 游戏

写自动化时别去找「科学科普」的文本，`count() == 0`，会卡满 30 秒超时。
（B 站后台的 tid 仍是 201，所以接口层面还能看到 tid=201，别被这个迷惑。）

### 3. 封面必弹「16:9 是否同步」

上传封面后立刻弹出：

> 检测到个人空间封面（16:9）未修改……是否将 4:3 封面的改动同步到 16:9 封面？

**不点「确认同步」，这个弹窗就一直挡着「立即投稿」**，表现为点击超时。正确顺序：

```
添加封面 → 上传封面（expect_file_chooser 接文件）→ 确认同步 → 完成
```

注意两个按钮都是**异步出现**的，不能用 `count() > 0` 先判断再点，要用
`locator.click(timeout=12000)` 等它出现。

### 4. 窗口太矮看不到底部按钮

投稿页很长，「立即投稿」在底部。视口 1440×900 时可能仍不在视野内。
点之前先 `window.scrollTo(0, document.body.scrollHeight)`，并把 viewport 调到 1280×760。

### 5. 点「立即投稿」会触发风控验证

`<div class="base-verify risk-captcha sms-verify">` —— 短信或人机验证，异地/新设备投稿必触发。

**这一步只能人来做，不要试图绕过。** 所以 `--submit` 一律配 `--headful`，窗口置顶，人点完即可。
过完一次后该设备 30 天内一般不再验证。

## 四、投稿成功后怎么确认

提交成功后页面会跳到：

```
https://member.bilibili.com/platform/upload-manager/archive-process?bvid=BV1xxxxxxxxx
```

**BVID 就在 URL 里**，这是最可靠的抓取点。

`archive_list` 接口在稿件刚投递时可能返回空（`class.is_pubing = 1` 表示正在投递）。
过几分钟 `pubed` 计数 +1 就是过审了。再用公开接口核对：

```
https://api.bilibili.com/x/web-interface/view?bvid=BV1xxxxxxxxx
```

返回 `code: 0` + `state: 0` 即正常公开。

## 五、别踩的红线

1. **不刷量、不互赞、不用脚本制造互动**，被识别掉权重比没流量更惨。
2. **凭证只放 `data/cookies.json`（600）**，不进对话、不进日志、不截图。
3. **不绕过验证码。** 风控验证是 B 站的合规要求，绕过一次可能直接封号。
4. **发布前必须让用户看到完整计划**（标题/简介/标签/分区/封面），确认后才提交。
5. 遇 `-352 / -412 / -509` 立即停手，隔几小时再说，不要连着重试。
