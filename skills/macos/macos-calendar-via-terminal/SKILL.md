---
name: macos-calendar-via-terminal
description: 在 macOS 上操作系统「日历」App（Apple Calendar / EventKit）的技能。当用户需要查看、扫描、添加、删除、修改日历日程，或批量设置/清空提醒、整理压缩日程、导入赛历校历时使用。核心要点：WorkBuddy 沙箱环境无法直接访问日历（EventKit 返回 DENIED），必须写 Swift(EventKit) 脚本放到桌面，让用户在系统「终端」里运行并授权，脚本把结果写入桌面 txt 文件供读取与核对。触发词：日历、日程、校历、提醒、赛历、事件、EventKit、Calendar、提醒事项。
agent_created: true
---

# macOS 日历操作（通过终端跑 Swift 脚本）

## 核心问题（必须先知道）

WorkBuddy 的执行环境被 macOS 安全沙箱锁死，**无法直接访问日历**：

- `EKEventStore.requestFullAccessToEvents` 的授权弹窗会被沙箱吞掉，系统只能返回 `DENIED` / 未授权。
- `osascript` 控制「日历」「终端」等 App 的自动化权限同样被拦（连 `ps` 都返回 `operation not permitted`）。
- 用 `tccutil reset Calendar` 也无济于事——问题不在 TCC 授权记录，而在沙箱本身。

因此**不要反复尝试在本环境里请求日历权限**，直接走下面的「终端代理」方案。

## 标准工作流（终端代理）

1. **写脚本**：把 EventKit Swift 脚本写到 `~/Desktop/<名字>.swift`。
2. **让用户跑**：请用户在系统「终端」里运行 `swift ~/Desktop/<名字>.swift`（提示：`Command+空格` 输入「终端」打开）。
3. **授权**：脚本首次运行会弹出「"终端"想要访问您的日历」，让用户点「允许」。
4. **读结果**：脚本把结果（或计划）写到 `~/Desktop/<名字>.txt`，用户跑完回一声，再读该 txt 核对。
5. **确认式执行**：涉及删除/修改时，脚本内先打印计划，用 `readLine()` 让用户输入 `y` 才真正执行；WorkBuddy 无法代点，务必提示用户输入。

先读 `scripts/scan_calendars.swift` 作为只读扫描的起点（列出所有日历及每条日程，输出到桌面 txt）。操作类脚本在扫描结果基础上按需改写。

## EventKit API 速查

关键 API（Swift + Foundation）：

```swift
import EventKit
let store = EKEventStore()
let sem = DispatchSemaphore(value: 0)   // 用信号量等待异步回调，否则 main 会提前退出

store.requestFullAccessToEvents { granted, error in
    guard granted else { print("未授权"); sem.signal(); return }
    // ... 业务逻辑 ...
    sem.signal()
}
sem.wait()
```

- **列日历**：`store.calendars(for: .event)`，每条 `c.title`、`c.allowsContentModifications`（false = 只读订阅日历，无法修改，必须跳过）。
- **查事件**：`store.predicateForEvents(withStart:end:calendars:)` + `store.events(matching:)`。
- **删除**：`store.remove(e, span: .thisEvent, commit: false)`。
- **修改**：改 `e.startDate` / `e.endDate` / `e.isAllDay` 后 `store.save(e, span: .thisEvent, commit: false)`。
- **提醒（通知）**：先清空旧提醒，再加新的：
  ```swift
  for a in (e.alarms ?? []) { e.removeAlarm(a) }   // 清空旧提醒
  e.addAlarm(EKAlarm(relativeOffset: -86400))       // -86400 秒 = 提前 1 天
  ```
  常用偏移：`-86400`=提前1天，`-1800`=提前30分，`-900`=提前15分，`0`=正点。
- **提交**：所有增删改都设 `commit: false`，最后 `try store.commit()` 一次性落盘。
- **取周日**（压缩跨周日程用）：
  ```swift
  let wd = Calendar.current.component(.weekday, from: date) // 1=周日
  let add = (8 - wd) % 7
  let sunday = Calendar.current.date(byAdding: .day, value: add, to: date)!
  ```
- **全天事件**：`e.isAllDay = true` 且 `startDate` 设为当天 0 点、`endDate` 设为次日 0 点（`Calendar.current.startOfDay(for:)` + `date(byAdding: .day, value: 1, to:)`）。

## 安全铁律

- 删除/移动日程前，**先只读扫描**并把待删项逐条列给用户，讲明后果，**用户确认后才执行**。
- 脚本内用 `readLine()` 二次确认（输入 `y` 才执行），不要无确认直接改。
- 只读订阅日历（`allowsContentModifications == false`，如「中国大陆节假日」）**无法修改**，脚本需 `continue` 跳过并在结果里标注，不要报错中断。
- 压缩/删除只影响目标日历，其余日历不动。

## 已知边界

- 脚本只能由用户在终端手动运行，WorkBuddy 无法代跑、代点授权、代输入确认。
- 脚本运行耗时通常几十秒内，让用户等它打印 `✅ 已写入文件` 再回报。
- 日历事件的中文标题若含英文（如「开学典礼 / Opening Ceremony」），匹配关键词时用 `contains` 模糊匹配更稳。
