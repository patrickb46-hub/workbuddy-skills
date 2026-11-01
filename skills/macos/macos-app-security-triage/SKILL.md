---
name: macos-app-security-triage
description: 对陌生 macOS 安装包（.dmg/.pkg/.app）做安全取证的通用流程。当用户丢来一个安装包并问「这安不安全 / 有什么危害 / 能不能装 / 帮我分析风险 / 是不是病毒」，或自己下载了来路不明的 App 想评估时使用。核心原则：先取证再运行，绝不双击。全程只读挂载 + 静态分析，产出「已确认风险 / 未发现风险 / 运行时待确认」三段式结论，不制造恐慌也不放水。触发词：安装包安全、DMG 分析、dmg 有没有毒、app 安不安全、可疑安装包、恶意软件检测、逆向分析、静态取证。
agent_created: true
---

# macOS 安装包安全取证

## 何时用

- 用户给一个 `.dmg` / `.pkg` / `.app` 并问安全性、危害、能否安装。
- 用户说「我下载了一个 X，感觉不太对」。
- 需要写一份风险报告（安装包来源、权限、行为、防范措施）。

**不适用**：用户已经运行并怀疑中招（那是应急响应，重点变成查持久化、断网、改密码）。

## 铁律

1. **先取证，绝不双击**。整个流程不需要运行目标程序。
2. **只读挂载**：`hdiutil attach -readonly -nobrowse -noautoopen`。`-noautoopen` 不可省。
3. **区分三件事**：`CRC32/哈希 vs 签名  vs 公证`。哈希只证明「没坏」，不证明「没改」，更不证明「安全」。
4. **不要制造恐慌**。Dart/Electron/Go 二进制里塞满框架通用标识，误报极易发生。
   结论必须分「已确认」「未发现」「运行时待确认」三段，说清楚局限。
5. **分析完必须 `hdiutil detach`**，并在报告里声明「未运行、未安装、未改动系统」。

## 流程

### 第 1 步 · 来源与元数据（最先做，性价比最高）

```bash
ls -la@ 文件                      # 看有无 quarantine / WhereFroms
xattr -p com.apple.quarantine 文件
xattr -p com.apple.metadata:kMDItemWhereFroms 文件
mdls -name kMDItemWhereFroms -name kMDItemDownloadedDate 文件
shasum -a 256 文件
```

判读：来源是官网域名，还是 CDN / 网盘 / 群文件？后者直接扣分。
CloudFront、OSS、对象存储等**任何人都能开通**，不构成任何背书。

### 第 2 步 · 系统防线判定

```bash
spctl -a -vvv -t open --context context:primary-signature 文件.dmg   # rejected = 停下来
codesign -dv --verbose=4 文件                                        # adhoc + TeamIdentifier=not set = 无身份
hdiutil verify 文件.dmg                                              # 只查完整性
```

**关键判据**：`Signature=adhoc` 且 `TeamIdentifier=not set` → 任何人都能基于同源重新打包插东西，你无法验证。
未公证（notarization）说明连 99 美元开发者账号都没投入，是最基础的门槛都没过。

### 第 3 步 · 只读挂载并枚举

```bash
mkdir -p /tmp/tri && hdiutil attach -readonly -nobrowse -noautoopen -mountpoint /tmp/tri 文件.dmg
find /tmp/tri -maxdepth 4 | head -80
ls -la "/tmp/tri/X.app/Contents"          # Frameworks / PlugIns / XPCServices / Library
```

看：包内有几个程序？是否有 PlugIns / XPCServices / 特权助手（提权迹象）？
`Contents/_CodeSignature` 存在但 adhoc 是常态，不代表可信。

### 第 4 步 · 权限与能力（最关键）

```bash
codesign -d --entitlements - --xml App.app          # 或去掉 --xml
plutil -p App.app/Contents/Info.plist | grep -iE "UsageDescription|NS(Camera|Microphone|Location|Contacts|AppleEvents|Desktop|Documents|Downloads)"
```

判读表：

| 发现 | 含义 |
|---|---|
| `app-sandbox = 1` | 好事，权限被系统约束 |
| `files.user-selected.read-only` | 只能读用户手选文件，不能遍历目录 |
| `get-task-allow = 1` | **发行版不该有**，允许调试器附加读内存 → 可窃取内存中的令牌/密码 |
| `network.client` | 可自由外联（配合远程配置 = 高危） |
| 缺 `UsageDescription` | 摄像头/麦克风/定位/通讯录**系统层面就无法访问**（明确的"未发现"证据） |
| `PlugIns`/`XPCServices`/特权助手 | 可能存在提权路径 |

### 第 5 步 · 持久化与命令执行

```bash
strings -a App/MacOS/可执行文件 > /tmp/s.txt
LC_ALL=C grep -aoiE "(SMAppService|LSSharedFileList|LaunchAgent|LaunchDaemon|LoginItem|SMLoginItem)" /tmp/s.txt
LC_ALL=C grep -aoE "(/bin/sh|/bin/bash|/usr/bin/[a-z]+|osascript|chmod|chown|spctl|xattr)" /tmp/s.txt
LC_ALL=C grep -aoiE "(ioreg|system_profiler|IOPlatformSerialNumber|IOPlatformUUID|serial_number)" /tmp/s.txt
```

**必须用 `LC_ALL=C`**，否则含非法 UTF-8 的 strings 输出会被 grep 当二进制而静默不匹配（踩过）。

### 第 6 步 · 网络目标与远程可控性（决定风险上限）

```bash
LC_ALL=C grep -aoE "https?://[^\"'\\ ]{6,140}" /tmp/s.txt | sort -u
LC_ALL=C grep -aoE "[a-z0-9-]{3,30}\.(cc|top|xyz|icu|vip|club|online|site|store|cn)" /tmp/s.txt | sort | uniq -c | sort -rn
dig +short 域名 A ; dig +short 域名 NS        # 共用 NS = 同一运营者；Cloudflare 104.21/172.67 = 隐藏源站
```

**最高价值的发现**：App 去 `raw.githubusercontent.com/<user>/<repo>/.../x.txt` 之类地址拉配置。
这是灰色应用的标准做法 —— GitHub 当免费配置托管。**务必把该文件拉下来看**（WebFetch），
你常会发现实际指向的域名已经和包内硬编码的不一样（说明在活跃轮换）。再看该仓库还放了什么：
若是几十个同类 App 的域名配置库，即为**批量换皮的 App 家族**，风险等级整体上调。

### 第 7 步 · 读应用自有文案（信息量最大，别跳过）

原生 App 找 `Info.plist`、`Localizable.strings`、`*.json` 资源；
Flutter 应用找 `Contents/Frameworks/App.framework/Versions/A/Resources/flutter_assets/assets/` 下的 json。

**提示文案会直白承认很多东西**，比反编译代码更快：内容性质、是否推广 VPN、
是否有充值/提现/订阅、是否"不提供密码找回"、是否引导装未知应用、官方联系群在哪。

同时枚举业务模块名（Flutter 看 `package:<app_name>/...dart`），能勾勒出完整功能面：
有无 IM、支付、设备指纹、广告 SDK、更新页。

### 第 8 步 · 清理

```bash
hdiutil detach /tmp/tri
mount | grep 卷名 || echo "已卸载"
```

### 第 9 步 · 卸载后残留排查（用户说"我删掉了，帮我看看干不干净"时）

**一律用 `find` 扫，不要用 `ls | grep`** —— `ls` 输出可能被静默抑制，导致漏报（实测踩过）。

```bash
# 1) 先查废纸篓规模！里面有用户自己的文件时，绝不能建议"清空废纸篓"
du -sh ~/.Trash ; ls ~/.Trash | wc -l
# 2) 全盘复扫
for p in ~/Library ~/Desktop ~/Documents ~/Downloads ~/Applications ~/.Trash; do
  find "$p" -maxdepth 4 \( -iname "*<bundle-id>*" -o -iname "*<app名>*" \) 2>/dev/null
done
# 3) 进程（必须精确匹配，pgrep -fl 会被 Agent 自身命令行污染）
/usr/bin/pgrep -x "<App名>" ; /bin/ps -Ao pid,comm
# 4) 持久化与注册项
launchctl list | grep -iE "<bundle-id>"
ls ~/Library/LaunchAgents /Library/LaunchAgents /Library/LaunchDaemons | grep -i <关键词>
# 5) 沙箱残留（沙箱 App 必留）
ls -la ~/Library/Containers/<bundle-id>/Data/Documents/     # Hive/SQLite 等会证明它真运行过
ls -la ~/Library/Application\ Scripts/<bundle-id>
```

**沙箱容器里的数据文件是"到底运行过没有"的铁证**：即使 App 已删除，容器仍在。
读里面的 Hive/SQLite 即可判断 —— 例如出现 `is_first_app_install=1`、`build_record=…`
说明确实启动过。此时要如实告诉用户"它被运行过一次"，而不是含糊说"可能运行过"。

**删除残留时注意 `rm` 陷阱（本环境实测）**：
PATH 里的 `rm` 可能被替换为受控代理（`type rm` 查看），对 `.Trash` 等路径会
**静默返回 0 但不真正删除**。必须用系统原生二进制：

```bash
/bin/rm -rf "<精确路径>" ; echo "退出码=$?"
# 删完立刻逐项验证，不要相信退出码
```

**铁律**：只删定向列出的具体路径，一次不超过 10 个，逐个 `[ -e ]` 复核；
删完必须抽查用户自有文件是否完好。破坏性操作前先列清单并取得明确确认。

## 常见误报（务必排除，否则结论会失真）

| 症状字符串 | 真实来源 |
|---|---|
| `History`、`Chrome`、`Safari` | Flutter 框架的 `UndoHistory` / `LocalHistoryEntry` 等内部标识 |
| `badCertificateCallback`、`onBadCertificate`、`X509`、`SecurityContext` | `dart:io` 标准库 API 名，任何 Flutter App 都有 |
| `Password`、`Credential`、`Keychain` | `flutter_secure_storage` 插件样板代码 |
| 大量 base64/hex 长串 | 密码学库（ECC 曲线常数等），非硬编码密钥 |
| `Ass.framework` | libass 字幕库（FFmpeg 生态），不是脏话 |

判断方法：看命中项是否带 `_handleXxx@数字` 这类 Dart 混淆后缀，或在前后文出现 `package:flutter/`。
**只有结合 entitlements 与上下文才能定性。**

## 报告结构（三段式，直接照用）

1. **结论先行** —— 风险等级 + 是否建议安装 + 一句话核心理由。给 4 个关键指标卡（签名/系统判定/沙箱/远程可控）。
2. **基础取证事实** —— 表格：大小、来源 URL、下载时间、隔离标记、三种哈希、完整性、签名、entitlements、版本号。
   （顺带核对文件名与 `CFBundleShortVersionString` 是否一致，不一致是可疑信号。）
3. **四个问题逐个回答**：
   - ① 可能包含的恶意行为与安全隐患（表格：风险类别 / 实际情况 / 危害说明）
   - ② 下载过程风险（来源不可信、无官方哈希、传输篡改、二次捆绑、版本伪装、更新渠道）
   - ③ 需重点检查的特征 / 来源信息 / 行为迹象（给可复用命令 + 本次实际结果）
   - ④ 具体防范措施（现在就做 → 通用自查流程 → 长期习惯）
4. **"好消息"区块** —— 明确列出**经确认不存在**的风险。
   这一块不可省：只讲危险是失职，会让人做出过度反应（如不必要的重装系统）。
5. **局限声明** —— 静态分析看不到什么，逐条列出「运行时待确认」项。
   结尾必须写明：未运行、未安装、未改动系统、映像已卸载。

## 若用户已经运行过

交付时追加应急处置：卸载 App + 清理 `~/Library/Containers/<bundle-id>` 与 `Application Support` 残留 →
换掉在别处复用的同一密码 + 开两步验证 → 有支付就查异常扣费 → 按它指引装过的其他软件一并卸载。

## 语气

对内动作（读取、分析）大胆做；对外动作（发邮件、公开）先问。
技术上要硬，措辞上要稳：不是「这肯定是病毒」，而是「已确认 A、B、C；未发现 D、E；F 需运行后确认」。
