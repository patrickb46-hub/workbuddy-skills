---
name: disk-audit
description: >-
  诊断 macOS 磁盘空间占用，输出「哪些直接删、哪些先备份到移动硬盘、哪些需要你判断」的分级清单。
  当用户说「磁盘满了 / 空间不够 / C 盘红了 / 看看谁占了空间 / 清理磁盘 / 大文件在哪 /
  帮我体检一下电脑 / 该删什么」时使用。只读扫描，绝不删除文件。
  内含 macOS 特有的坑：APFS 克隆造成的假占用、rm 被包装成移到废纸篓、TCC 权限拦截。
---

# 磁盘体检（disk-audit）

## 这个技能解决什么

用户的 Mac 空间告急时，凭肉眼在 Finder 里翻是找不到真凶的：
大文件往往藏在 `~/Library`、`/private/var`、其他用户目录、虚拟机镜像里。
这个技能用一条命令扫出真实构成，并按「处置成本」分成四档，让用户能直接照单执行。

## 快速开始

```bash
# 标准体检（1–3 分钟）
python3 ~/.workbuddy/skills/disk-audit/scripts/diskaudit.py

# 看全（含其他用户的 Library，需要管理员密码）
sudo python3 ~/.workbuddy/skills/disk-audit/scripts/diskaudit.py

# 追加全盘最大文件扫描（慢，+2–4 分钟）
python3 ~/.workbuddy/skills/disk-audit/scripts/diskaudit.py --deep --top 30

# 另存交付物
python3 ~/.workbuddy/skills/disk-audit/scripts/diskaudit.py --html ~/Desktop/体检.html --json ~/Desktop/体检.json
```

数据量小的时候用 `--top`、`--min-gb` 控制输出规模。脚本纯标准库，Python 3.9+ 即可。

## 输出结构

| 段落 | 含义 | 用户该做什么 |
| --- | --- | --- |
| ① 概览 | 容量、已用、可用、可枚举合计、差额 | 先看差额，那是 TCC 藏起来的 |
| ② 直接删除 | 缓存、残留、可重下的模型和游戏 | 可立刻动手 |
| ③ 先备份再删 | 桌面、文稿、照片、视频素材 | 必须拷硬盘、核对文件数 |
| ④ 需要你判断 | 虚拟机、App 数据、大型应用 | 逐项问用户 |
| ⑤ 不要动 | 系统组件、日常应用 | 别碰 |
| ⑥ 顶层构成 | 每个顶层目录的占比条 | 一眼看出钱花在哪 |
| ⑦ 环境体检 | Time Machine、快照、废纸篓、SIP、rm 是否被包装 | 备份没配就先配 |

## 关键知识（踩过的坑，别重犯）

### 1. APFS 克隆会让 du 谎报体积

Chrome 等浏览器会在临时目录生成 `*code_sign_clone*`，用 `clonefile()` 创建，
与 App 本体**共享同一批数据块**。`du` 报的是逻辑大小，几十个副本能显示成 76GB，
实际占用接近 0。删掉只释放了 2GB。

**判断真实占用的唯一可靠办法：看 `df` 在删除前后的差值。**
脚本会把这类条目标 `[克隆]` 并在合计里剔除。

### 2. 本机 `rm` 可能被包装成「移到废纸篓」

```
$ type rm
rm is /Applications/WorkBuddy.app/.../brokered-bin/rm
```
这种 shim 只把文件挪进 `~/.Trash`，**空间一点不释放**，用户会以为删了但没效果。
所以脚本输出的删除命令一律用 `/bin/rm`，并检测当前环境是否命中该情况。

### 3. `sudo` 也会被 TCC 拦住

读 `.DocumentRevisions-V100`、`.Spotlight-V100` 报 `Operation not permitted`（EPERM），
不是 Unix 权限不足，是 macOS 的 TCC。`sudo` 无效，必须给 Terminal 授予
**完全磁盘访问权限**（System Settings → Privacy & Security → Full Disk Access → ⌘Q 重启 Terminal）。

### 4. macOS 的 `stat -f` 不能算大小

`stat -f "%b|%z|%N"` 会回退成打印文件系统信息，字段全空。**别用**。
要逐文件算真实占用，用 `find ... -exec du -k {} +`。

### 5. 嵌套目录会重复计数

同时统计 `~/Library` 和 `~/Library/Caches` 会让合计虚高。脚本把「顶层根」和
「互斥明细桶」分开：根只算总量，明细只给建议。

### 6. 文档版本库可能藏着巨量空间

`.DocumentRevisions-V100` 会保存文档的历史版本。实测删掉一个 9.6GB 的加密 sparsebundle，
连带清掉它约 80GB 的版本记录，可用空间从 40GB 跳到 122GB。
所以「可枚举合计」和「系统消耗」的差额，值得用 sudo 查清来源。

## 执行删除前的铁律

1. **先确认有备份**。Time Machine 没配、又没移动硬盘，就不要碰不可再生数据。
2. **备份三件套**：`rsync` 拷 → `find … | wc -l` 两边核对 → 再删本地。
3. **优先顺序**：配 TM → 备份不可再生数据 → 最后删可重建的（缓存、模型、游戏）。
4. **AI 不要代删 ~/Documents、~/Desktop 等个人目录**——这类操作会被安全守则拦截，
   而且拦截是对的。把命令交给用户自己执行。
5. 用户说「都删了不要了」时，仍要先挂载/展开给他看一眼，尤其是加密容器和虚拟机：
   内容不可预知，事后无法恢复。

## 常见误区

- **别清 `/private/var/folders` 里的东西就以为能省很多**：多数是活着的临时文件，且常是克隆。
- **别手删 `.Spotlight-V100`**：索引会重建，重建期间搜索全废。
- **别用 `chflags hidden` 当"藏文件"**：那是障眼法，不是加密。
- **`.sparsebundle` 是单个容器文件**：删里面的东西不会让它变小，得压缩映像。
