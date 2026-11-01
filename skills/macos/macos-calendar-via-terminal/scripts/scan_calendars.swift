import EventKit
import Foundation

// 通用只读扫描脚本：列出所有日历及每条日程，输出到 ~/Desktop/日历扫描结果.txt
// 用法：swift 本文件  （首次运行会弹日历授权，点「允许」）

let store = EKEventStore()
let sem = DispatchSemaphore(value: 0)

store.requestFullAccessToEvents { granted, error in
    if let error = error { print("❌ 错误: \(error.localizedDescription)"); sem.signal(); return }
    guard granted else { print("❌ 未授权，请在弹窗点「允许」后重跑"); sem.signal(); return }

    var lines: [String] = []
    func log(_ s: String) { lines.append(s); print(s) }

    var comp = DateComponents()
    comp.year = 2026; comp.month = 1; comp.day = 1
    let start = Calendar.current.date(from: comp)!
    comp.year = 2028; comp.month = 1; comp.day = 1
    let end = Calendar.current.date(from: comp)!

    let df = DateFormatter()
    df.locale = Locale(identifier: "zh_CN")
    df.dateFormat = "yyyy-MM-dd"
    df.timeZone = TimeZone.current

    func alarmDesc(_ e: EKEvent) -> String {
        guard let alarms = e.alarms, !alarms.isEmpty else { return "无提醒" }
        return alarms.map { a in
            switch a.relativeOffset {
            case -86400: return "提前1天"
            case -1800:  return "提前30分"
            case -900:   return "提前15分"
            case 0:      return "正点"
            default:     return "偏移\(Int(a.relativeOffset))秒"
            }
        }.joined(separator: "、")
    }

    let calendars = store.calendars(for: .event)
    log("════════ 日历扫描结果 ════════\n")
    log("共 \(calendars.count) 个日历\n")

    for c in calendars {
        let ro = c.allowsContentModifications ? "" : "（只读，无法修改）"
        let pred = store.predicateForEvents(withStart: start, end: end, calendars: [c])
        let events = store.events(matching: pred).sorted { $0.startDate < $1.startDate }
        log("【\(c.title)】\(ro)  日程数=\(events.count)")
        for e in events {
            let days = Int(e.endDate.timeIntervalSince(e.startDate) / 86400.0)
            let allDay = e.isAllDay ? "全天" : "时段"
            log("   • \(e.title ?? "（无标题）")  \(df.string(from: e.startDate)) ~ \(df.string(from: e.endDate))  [\(allDay),\(days)天]  提醒=\(alarmDesc(e))")
        }
        log("")
    }

    let outPath = NSHomeDirectory() + "/Desktop/日历扫描结果.txt"
    do {
        try lines.joined(separator: "\n").write(toFile: outPath, atomically: true, encoding: .utf8)
        log("✅ 已写入 \(outPath)")
    } catch {
        log("⚠️ 写文件失败：\(error.localizedDescription)")
    }
    sem.signal()
}

sem.wait()
