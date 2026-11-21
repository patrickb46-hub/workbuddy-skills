---
name: workbuddy-checkin-daemon
license: Proprietary
display_name: WorkBuddy签到助手·守护进程版
display_name_en: WorkBuddy Check-in Daemon Edition
description: WorkBuddy签到助手·守护进程版（「Buddy 加油站」每日签到 + 派猫猫旅行自动化 Skill，token 不落地，兼容新版加密登录态，跨平台支持 Windows / macOS / Linux）。当用户说"每天自动签到 WorkBuddy / 每日签到 / 自动领 Buddy 加油站积分 / 自动领 100 积分 / 设置 WorkBuddy 每日签到 / WorkBuddy 打卡 / 自动打卡 WorkBuddy / 帮我签到一次 / 现在签个到 / 检查签到环境 / 派猫猫旅行 / 猫猫旅行 / 旅行积分 / 领旅行奖励 / Buddy 在旅行吗 / 还有多久回来 / 自动派猫猫"时使用。原理是通过 WorkBuddy 守护进程的 wbipc 命名管道（HMAC 挑战-应答握手认证）让守护进程代为携带登录态调用官方签到接口，本机脚本不读取、不解密、不传输任何 token，比直接读登录态文件的方案更安全，且兼容 accessToken 为 $wbEncrypted 加密信封的新版客户端。支持签到状态查询（幂等防重复）、领取签到、派猫猫旅行全自动闭环（查状态 / 领旅行积分 / 派 Buddy 出门，默认随签到执行）、积分余额与连续签到天数汇报，纯 Python 标准库零依赖，可配合 WorkBuddy 自带自动化设置每日 09:00 定时签到。
description_zh: 通过 WorkBuddy 守护进程 wbipc 管道代理请求完成「Buddy 加油站」每日签到（token 不落地，不读取登录态文件，兼容新版 $wbEncrypted 加密登录态），支持签到状态查询（幂等防重复）、领取签到、派猫猫旅行全自动闭环（查状态 / 领旅行积分 / 派 Buddy 出门，默认随签到执行）、积分余额与连续签到天数汇报，纯 Python 标准库零依赖，可设置每日 09:00 定时自动签到。
description_en: Complete the WorkBuddy Buddy Station daily check-in via the desktop daemon's wbipc named-pipe proxy (token never leaves the daemon; no reading or decrypting local auth files; compatible with new clients where accessToken is a $wbEncrypted envelope). Supports idempotent check-in status queries, claiming daily credit, a full Buddy Travel loop (query status, claim travel credits, dispatch Buddy; runs by default with check-in), plus balance and streak reporting. Pure Python standard library, zero dependencies; pairs with WorkBuddy's built-in automation for a daily 09:00 schedule.
category: 生活服务
version: 1.0.0
author: huakui
agent_created: true
---

# WorkBuddy签到助手·守护进程版（每日自动签到 · 派猫猫旅行 · token 不落地）

WorkBuddy「Buddy 加油站」每日签到本质是一次带登录态的 HTTP 接口请求，**不需要**模拟点击
GUI，也**不需要**读取本地登录态文件。本技能通过 WorkBuddy 守护进程内置的 wbipc 命名管道，
让守护进程**代为携带登录态**发起官方接口请求——本机脚本接触不到 token，且天然兼容新版
客户端（accessToken 为 `$wbEncrypted` 加密信封，直接读文件会拿到密文）。

> 旧版客户端（明文 token）同样适用本方案。若需要多渠道消息推送（钉钉/飞书/邮件等 12 渠道），
> 可与社区技能 totorosir-workbuddy-checkin 搭配，两者互不冲突。

## 核心逻辑

自带脚本 `scripts/wb_checkin_daemon.py`（纯 Python 标准库，零第三方依赖）：

1. 读取 `~/.workbuddy/wbipc/endpoint.json`（管道地址 + 会话票据，由客户端自动生成）。
2. 与守护进程完成 HMAC 挑战-应答握手（协议细节见 `references/wbipc-protocol.md`）。
3. 通过 `wb.request/http.fetch` 让守护进程代发请求（headers 由守护进程注入，脚本接触不到 token）：
   - `POST /v2/billing/meter/checkin-activity-status` 查询签到状态；
   - 若今日未签 → `POST /v2/billing/meter/daily-checkin` 领取（幂等，已签返回 code=10001）；
   - 派猫猫旅行闭环：`GET /activity/growth/buddy/travel/status` → `arrived` 则 `travel/claim` 领取 →
     `idle` 且未达每日上限则 `travel/depart` 派遣（达上限一个写请求都不发）。
4. 输出单行 JSON 结果，全程不打印任何凭据。退出码：成功 0 / 失败 1。

## 调用本 Skill 时的搭建流程

1. **运行脚本验证**（优先用 WorkBuddy 托管 Python `~/.workbuddy/binaries/python/versions/*/python.exe`）：

   ```bash
   python scripts/wb_checkin_daemon.py            # 签到 + 旅行全自动闭环（默认）
   python scripts/wb_checkin_daemon.py --no-travel # 只签到
   python scripts/wb_checkin_daemon.py --location 3 # 指定派遣地点（1-4，缺省随机）
   ```

   - 前提：WorkBuddy 客户端正在运行且已登录（守护进程随客户端启动）。
   - 客户端刚重启过属正常：endpoint/ticket 会轮换，重跑即可。

2. **解读 JSON 结果并汇报**：
   - `action=clicked`：签到成功，领取 `credit_gained` 积分，连续 `streak_days` 天；
     `balance` 非 null 时附「当前积分余额：X」。
   - `action=skip_already_signed`：今日已签到，幂等跳过（附余额与连续天数）。
   - `status=error`：如实报告 `msg` 失败原因（常见：客户端未运行/未登录/未联网），不得谎报成功。
   - `travel` 字段：`traveling` → 正在 `location_name` 旅行，约 `remaining_text` 后到达；
     `arrived` → 已到达，`auto_log` 显示领取结果；`auto_log` 逐条照实转述；
     `travel.available=false` → 只说「旅行状态未能获取」，不要编造状态。

3. **创建每日定时（WorkBuddy 自带自动化，不要用 crontab / 系统计划任务）**：
   用 `automation_update`（mode=create）创建 recurring 自动化：
   - name：`WorkBuddy签到助手 · 每日自动签到`
   - rrule：`FREQ=DAILY;BYHOUR=9;BYMINUTE=0`
   - status：`ACTIVE`
   - prompt 模板与完整约束见 `README.md`「每日 9 点自动签到」一节；要点：运行上述脚本、
     按 JSON 字段汇报、严禁打印任何 token/ticket 凭据、重试不超过 1 次、失败如实报告。

## 排错速查

- `cannot open pipe` / `wbipc frame timeout`：客户端未运行或刚重启（endpoint 已轮换），打开客户端后重跑。
- `wb.request pipe 不可见`：客户端未登录或会话不可用，登录后重试。
- `code=10001`：今日已签到，幂等安全返回，不是错误。
- 「今日派遣次数已用完」：服务端每日限额，次日自动恢复，不是故障。
- `travel.depart` 返回 `400 invalid request`：派遣接口**必须**带 body `{"location_id":1..4}`
  （1 咖啡馆 / 2 商场店铺 / 3 健身房 / 4 古镇客栈，四地收益相同）。v1.0.0 曾发空 body `{}` 导致
  恒定 400，已修复为缺省随机；也可用 `--location N` 指定。
- 脚本偶发被外部 SIGTERM 杀掉：本机安全策略干扰，重跑即可。
- 客户端重启后 `E_REVOKED`：endpoint/ticket 已轮换，重新读 endpoint.json 重连。

## 安全约束（务必遵守）

- 只读取 `wbipc/endpoint.json`；**绝不**打开登录态文件 `workbuddy-desktop.info`，
  绝不修改或删除其内容，任何输出不得包含 token / ticket / 推送凭据。
- 写操作仅限已验证的 3 个端点：`daily-checkin`、`travel/claim`、`travel/depart`；
  不调用兑换、抽奖等未经验证的接口，不为推送额外引入依赖。
- 不修改 `wb_checkin_daemon.py` 以外的任何 WorkBuddy 配置；不做无限重试（内部最多 1 次）。
- 不要在网页版尝试签到（网页版无签到入口，仅 PC 客户端专属）。
