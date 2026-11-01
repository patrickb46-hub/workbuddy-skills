---
name: imessage-photo-archive
description: 从 macOS「信息」App（iMessage）按日期或联系人导出照片附件，并按每条消息随图发送的文字分组归档到文件夹，可选转出 JPG 副本、再按 HEIC/JPG 分子目录。当用户说"整理信息里的照片""iMessage 照片导出/归档""苹果短信里发的照片整理到某个文件夹""按消息文字建文件夹分照片"时使用。
agent_created: true
---

# iMessage 照片按消息文字归档

把「信息」App 里收到/发出的图片，按**每条消息的文字**分组，落到指定目录。

## 何时用

- 「把信息里某人发的照片整理到 XX 文件夹」
- 「每一组照片建一个文件夹，用一起发送的文字做文件夹名」
- 「iMessage 里的照片导出来分好类」

## 关键事实（先读，能省大量试错）

| 事项 | 结论 |
|---|---|
| 数据库 | `~/Library/Messages/chat.db`（+ `-wal` / `-shm`） |
| 只读打开 | `sqlite3.connect("file:<abs path>?mode=ro", uri=True)` —— **能读到 WAL 里的最新消息**，不会漏掉几分钟前刚到的那条 |
| 打不开时 | 把 `chat.db` + `-wal` + `-shm` 复制到临时目录再读；用完删掉副本 |
| 时间字段 | `message.date` 是 Apple epoch（**纳秒**）：`date/1000000000 + 978307200` 才是 Unix 秒 |
| ⚠️ 大坑 | `attachment.created_date` **全为 0**，**不能**用它筛日期！必须经 `message_attachment_join` 按 `message.date` 关联 |
| 联系人姓名 | `chat.db` 里**只有地址**（如 `<handle>@icloud.com`），姓名在 `~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb`（同样用只读 URI 打开） |
| 附件路径 | `attachment.filename` 常以 `~` 开头，需 `os.path.expanduser`；实体在 `~/Library/Messages/Attachments/<2位>/<2位>/<UUID>/IMG_xxxx.HEIC` |
| 消息文本 | `message.text` 里含 `U+FFFC`（对象替换符，代表内嵌图片），比较前要 `replace("\ufffc","").strip()` |
| ⚠️ 大坑 | macOS APFS **默认不区分大小写**：想建 `wp` 而 `WP` 已存在 → 是**同一个文件夹**。要独立就必须换名（如 `wp二练`） |
| HEIC→JPG | `sips -s format jpeg -s formatOptions 92 in.HEIC --out out.jpg`，保持全分辨率；`sips -Z 260` 出缩略图 |
| 只读保证 | 只 `cp` / `mv`，**绝不删源文件**——源照片留在 `Messages/Attachments` 是最硬的备份层 |

## 标准流程

1. **摸清需求**：目标目录？是否按学科/分类再分组？重名怎么处理？HEIC 是否要 JPG 副本？是否再分 HEIC/JPG 子目录？
   （这几项直接决定产物形态，务必先问，别猜。）
2. **只读建映射**：按 `message.date` 筛日期 → 取 `text` + 该消息的图片附件列表 → 用「(文字, 张数)」唯一匹配到目标文件夹。
3. **dry-run 预检**：打印映射表；校验 ① 张数与预期一致 ② 源文件存在且非 0 字节 ③ 目标目录无同名冲突 ④ 映射规则没有「未被命中的条目」也没有歧义命中。**任一不符就停**。
4. **落地**：`mkdir -p` → `shutil.copy2`（保留 mtime）→ `sips` 转 JPG。
5. **验证**：逐文件夹计数（应 = 张数 × 副本数）；`sips -g pixelWidth` 抽查可解码；核对被保护文件（PDF、已有 HTML）的 md5 未变；确认源目录张数不变。

## 现成脚本

`scripts/archive.py` —— 已跑通，参数见 `--help`。基本用法：

```bash
# 只看不写（强烈建议先跑）
python3 scripts/archive.py --date 2026-09-30 --out /path/to/目标目录

# 实做：复制 + 出 JPG + 再分 HEIC/JPG 子目录
python3 scripts/archive.py --date 2026-09-30 --out /path/to/目标目录 \
        --apply --jpg --split-format
```

脚本会打印映射表、`(文字, 张数)` 唯一匹配失败时**直接中止**，不做静默猜测。
目标文件夹名默认取消息文字本身；重名或需要套学科层时，用 `--map 文字=相对路径` 覆盖。

## 避坑清单（实战踩过的）

- Bash 里 **`for x in $VAR` 不会按空格分词**（部分环境 IFS 被改过）。遍历清单用数组：`S=( "a|1" "b|2" ); for x in "${S[@]}"`。
- 移动文件用 `find <dir> -maxdepth 1 -type f -iname "*.heic" -exec mv -n {} "<dir>/HEIC/" \;`，比通配符稳。
- 先建 `HEIC`/`JPG` 再移，别先移再建。
- 汇总行别忘 `wc -l | tr -d ' '` 去掉前导空格，否则字符串比较会失败。
