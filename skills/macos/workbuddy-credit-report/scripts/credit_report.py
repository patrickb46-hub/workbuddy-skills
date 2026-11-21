#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 积分消耗统计器
=======================

数据源（本机，全部离线，不联网、不读 Cookie）：
  1. ~/.workbuddy/workbuddy.db  -> session_usage 表
     每个会话一条记录：credit_json = {请求ID: 积分}，updated_at = 最后活动时间。
     这是**总量最完整**的来源（App 自己持久化），用于算总额与逐日趋势。
  2. ~/.workbuddy/logs/YYYY-MM-DD/*.log（含 *.old.log）
     逐条模型调用的 credit 事件 + qua.start/qua.end 里的 model / token / scene。
     日志会轮转，**只覆盖最近数日**，用于拆模型、场景、时段与单次成本。

用法：
  python3 credit_report.py                      # 近 7 天 + 近 30 天，控制台表格
  python3 credit_report.py --days 7 --md        # 输出可嵌入周报的 Markdown 片段
  python3 credit_report.py --from 2026-10-27 --to 2026-11-02 --md
  python3 credit_report.py --days 30 --json     # 完整 JSON（给上层二次加工）
  python3 credit_report.py --days 7 --html out.html
  python3 credit_report.py --days 7 --detail    # 额外附上模型/token 明细（需读日志，慢几秒）

口径与已知偏差（写报告时必须保留这类限定语）：
  · 「积分」= session_usage.credit_json 求和，单位为 WorkBuddy 积分。
  · 会话积分按该会话**最后活动时间**归日，跨零点的长会话会整体落在结束那天；
    单日偏差通常在 ±5% 内，趋势判断不受影响。
  · 「对话轮次」= credit_json 的 key 数量（根请求数），不等于消息条数；
    一轮对话内可能有几十次模型调用，日志里的调用次数是另一个量级。
  · 日志缺失时，模型/token/时段维度会标注「本区间日志未覆盖」，不要编造。
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import defaultdict

DB_PATH = os.path.expanduser("~/.workbuddy/workbuddy.db")
LOG_DIR = os.path.expanduser("~/.workbuddy/logs")

TS_RE = re.compile(
    r"\[(\d{1,2})/(\d{1,2})/(\d{4}),\s*(\d{1,2}:\d{2}:\d{2})\s*([AP]M)\.\d{3}\]"
)
CREDIT_RE = re.compile(
    r"CreditUsageSource\] source=modelUsage sessionId=(\S+) requestId=(\S+) "
    r"messageId=(\S+) credit=([0-9.]+)"
)

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- 数据加载

def load_sessions(db_path=DB_PATH):
    """从 session_usage ⨝ sessions 读出每个会话的积分与元信息。"""
    if not os.path.exists(db_path):
        sys.exit(f"[错误] 找不到数据库：{db_path}")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT s.id, s.title, s.cwd, s.model, s.mode,
               u.updated_at, u.credit_json
        FROM session_usage u
        LEFT JOIN sessions s ON s.id = u.session_id
        """
    ).fetchall()
    con.close()

    recs = []
    for r in rows:
        try:
            cj = json.loads(r["credit_json"]) if r["credit_json"] else {}
        except (json.JSONDecodeError, TypeError):
            cj = {}
        credit = sum(float(v) for v in cj.values() if isinstance(v, (int, float)))
        when = dt.datetime.fromtimestamp(r["updated_at"] / 1000)
        cwd = (r["cwd"] or "").rstrip("/")
        recs.append(
            dict(
                id=r["id"],
                title=(r["title"] or "").strip(),
                cwd=cwd,
                project=_project_name(cwd),
                model=(r["model"] or "unknown").strip() or "unknown",
                credit=credit,
                when=when,
                day=when.strftime("%Y-%m-%d"),
                rounds=len(cj),
                requests=list(cj.keys()),
            )
        )
    return recs


def _project_name(cwd):
    """把会话目录压成可读的项目名。

    App 自动建的一次性会话目录形如 2026-11-01-20-07-50，直接展示没有信息量，
    统一归为「临时工作区」，让命名项目（YSFLIGHT / String Gear 等）浮上来。
    """
    if not cwd:
        return "(无目录)"
    name = os.path.basename(cwd)
    if name in ("Work Buddy", ""):
        name = os.path.basename(os.path.dirname(cwd)) or name
    if re.match(r"^\d{4}-\d{2}-\d{2}(-\d{2}-\d{2}-\d{2})?$", name or ""):
        return "临时工作区"
    return name or "(无目录)"


def load_log_detail(d0, d1):
    """解析日志，返回 messageId -> {credit, model, scene, tin, tout, cached, when}。

    只读日期落在 [d0, d1] 区间内的日志文件；*.old.log 无目录名，靠行内时间戳定位。
    """
    files = []
    for day_dir in sorted(glob.glob(os.path.join(LOG_DIR, "20*-*-*"))):
        base = os.path.basename(day_dir)
        try:
            fd = dt.date.fromisoformat(base)
        except ValueError:
            continue
        if d0 <= fd <= d1:
            files += glob.glob(os.path.join(day_dir, "*.log"))
    files += glob.glob(os.path.join(LOG_DIR, "*.old.log"))

    events = {}
    for path in files:
        try:
            fh = open(path, "r", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if "CreditUsageSource" in line:
                    tm, cm = TS_RE.search(line), CREDIT_RE.search(line)
                    if not (tm and cm):
                        continue
                    mo, da, yr, clock, ap = tm.groups()
                    try:
                        when = dt.datetime.strptime(
                            f"{yr}-{int(mo):02d}-{int(da):02d} {clock} {ap}",
                            "%Y-%m-%d %H:%M:%S %p",
                        )
                    except ValueError:
                        continue
                    if not (d0 <= when.date() <= d1):
                        continue
                    sid, rid, mid, cr = cm.groups()
                    if mid not in events:
                        events[mid] = dict(
                            when=when, day=when.strftime("%Y-%m-%d"),
                            session=sid, request=rid, credit=float(cr),
                            model=None, scene=None, tin=0, tout=0, cached=0,
                        )
                    continue

                if "qua.start:" in line or "qua.end:" in line:
                    idx = line.find("qua.start:")
                    if idx < 0:
                        idx = line.find("qua.end:")
                    try:
                        obj = json.loads(line[idx:].split(": ", 1)[1].strip())
                    except (json.JSONDecodeError, IndexError):
                        continue
                    mid = obj.get("message_id")
                    if not mid:
                        continue
                    ev = events.get(mid)
                    if ev is None:
                        continue
                    ev["model"] = obj.get("model") or ev["model"]
                    ev["scene"] = obj.get("scene") or ev["scene"]
                    if "completion_tokens" in obj:
                        ev["tin"] = int(obj.get("prompt_tokens") or 0)
                        ev["tout"] = int(obj.get("completion_tokens") or 0)
                        ev["cached"] = int(obj.get("cached_read_tokens") or 0)
    return events


# ---------------------------------------------------------------- 统计

def _quantile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def summarize(recs, d0, d1, label, detail=None):
    span_days = (d1 - d0).days + 1
    start = dt.datetime.combine(d0, dt.time.min)
    end = dt.datetime.combine(d1, dt.time.max)
    sel = [r for r in recs if start <= r["when"] <= end and r["credit"] > 0]
    total = round(sum(r["credit"] for r in sel), 2)

    by_day = defaultdict(float)
    for r in sel:
        by_day[r["day"]] += r["credit"]
    series_keys = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(span_days)]
    series = [round(by_day.get(k, 0.0), 2) for k in series_keys]
    active = [v for v in series if v > 0]

    credits = sorted((r["credit"] for r in sel), reverse=True)
    share = lambda n: round(sum(credits[:n]) / total * 100, 1) if total else 0.0

    projects = defaultdict(lambda: {"credit": 0.0, "sessions": 0})
    models = defaultdict(float)
    for r in sel:
        projects[r["project"]]["credit"] += r["credit"]
        projects[r["project"]]["sessions"] += 1
        models[r["model"]] += r["credit"]

    peak = max(by_day.items(), key=lambda kv: kv[1]) if by_day else ("-", 0.0)

    out = dict(
        label=label,
        start=d0.isoformat(),
        end=d1.isoformat(),
        days=span_days,
        total=total,
        sessions=len(sel),
        rounds=sum(r["rounds"] for r in sel),
        active_days=len(active),
        silent_days=span_days - len(active),
        avg_per_active=round(total / len(active), 2) if active else 0.0,
        avg_per_day=round(total / span_days, 2),
        median_day=round(statistics.median(active), 2) if active else 0.0,
        peak_day=peak[0],
        peak_value=round(peak[1], 2),
        peak_ratio=round(peak[1] / statistics.median(active), 1)
        if active and statistics.median(active) > 0 else 0.0,
        per_session_median=_quantile([r["credit"] for r in sel], 50),
        per_session_p90=_quantile([r["credit"] for r in sel], 90),
        per_session_max=credits[0] if credits else 0.0,
        credit_per_round=round(total / sum(r["rounds"] for r in sel), 2)
        if sum(r["rounds"] for r in sel) else 0.0,
        top1_share=share(1),
        top3_share=share(3),
        top5_share=share(5),
        heavy_sessions=sum(1 for c in credits if c >= 100),
        heavy_share=round(sum(c for c in credits if c >= 100) / total * 100, 1)
        if total else 0.0,
        daily=dict(zip(series_keys, series)),
        projects=sorted(
            [
                dict(name=k, credit=round(v["credit"], 2), sessions=v["sessions"])
                for k, v in projects.items()
            ],
            key=lambda x: -x["credit"],
        ),
        models={k: round(v, 2) for k, v in sorted(models.items(), key=lambda kv: -kv[1])},
        top_sessions=[
            dict(
                title=r["title"][:70] or "(无标题)",
                credit=round(r["credit"], 2),
                day=r["day"],
                rounds=r["rounds"],
                model=r["model"],
                project=r["project"],
            )
            for r in sorted(sel, key=lambda r: -r["credit"])[:8]
        ],
    )

    # ---- 日志明细维度（可能为空）
    if detail:
        dsel = [ev for ev in detail.values() if d0 <= ev["when"].date() <= d1]
        if dsel:
            log_total = sum(ev["credit"] for ev in dsel)
            per_model = defaultdict(
                lambda: dict(credit=0.0, calls=0, tin=0, tout=0, cached=0)
            )
            hours = defaultdict(float)
            scenes = defaultdict(float)
            for ev in dsel:
                m = per_model[ev["model"] or "unknown"]
                m["credit"] += ev["credit"]
                m["calls"] += 1
                m["tin"] += ev["tin"]
                m["tout"] += ev["tout"]
                m["cached"] += ev["cached"]
                hours[ev["when"].hour] += ev["credit"]
                scenes[ev["scene"] or "unknown"] += ev["credit"]
            out["detail"] = dict(
                log_total=round(log_total, 2),
                coverage=round(log_total / total * 100, 1) if total else 0.0,
                calls=len(dsel),
                models={
                    k: dict(
                        credit=round(v["credit"], 2),
                        calls=v["calls"],
                        tin=v["tin"],
                        tout=v["tout"],
                        cached=v["cached"],
                        credit_per_ktok=round(
                            v["credit"] / ((v["tin"] + v["tout"]) / 1000), 4
                        )
                        if (v["tin"] + v["tout"]) else 0.0,
                    )
                    for k, v in sorted(per_model.items(), key=lambda kv: -kv[1]["credit"])
                },
                scenes={k: round(v, 2) for k, v in sorted(scenes.items(), key=lambda kv: -kv[1])},
                hours={f"{h:02d}": round(v, 2) for h, v in sorted(hours.items())},
            )
    return out


def previous_window(d0, d1):
    span = (d1 - d0).days + 1
    return d0 - dt.timedelta(days=span), d1 - dt.timedelta(days=span)


# ---------------------------------------------------------------- 评价

def evaluate(cur, prev, ref30=None):
    """规则化生成观察，不做价值判断的口水话，每条都能落到数字。"""
    obs = []
    if prev and prev["total"]:
        delta = (cur["total"] / prev["total"] - 1) * 100
        trend = "上升" if delta > 0 else "下降"
        obs.append(
            f"环比上个同长周期（{prev['start']} ~ {prev['end']}，{prev['total']:.0f} 分）"
            f"{trend} {abs(delta):.1f}%，本期 {cur['total']:.0f} 分。"
        )

    if cur["top3_share"] >= 50:
        obs.append(
            f"支出高度集中：Top3 会话占 {cur['top3_share']:.1f}%，"
            f"中位数会话仅 {cur['per_session_median']:.1f} 分——日常使用很省，"
            f"预算主要被少数几次重活吃掉。"
        )
    elif cur["top3_share"] >= 30:
        obs.append(
            f"支出较集中：Top3 会话占 {cur['top3_share']:.1f}%，"
            f"中位数会话 {cur['per_session_median']:.1f} 分。"
        )
    else:
        obs.append(
            f"支出分散：Top3 会话仅占 {cur['top3_share']:.1f}%，"
            f"没有明显的「吞金」任务，消耗来自高频小任务。"
        )

    if cur["peak_ratio"] >= 5:
        obs.append(
            f"节奏是脉冲式的：峰值日 {cur['peak_day']} 花 {cur['peak_value']:.0f} 分，"
            f"是活跃日中位数（{cur['median_day']:.0f} 分）的 {cur['peak_ratio']:.0f} 倍。"
        )

    if cur["heavy_sessions"]:
        obs.append(
            f"重型会话（单会话 ≥100 分）{cur['heavy_sessions']} 个，"
            f"合计占 {cur['heavy_share']:.1f}%。"
        )

    if cur["top_sessions"]:
        top = cur["top_sessions"][0]
        share = top["credit"] / cur["total"] * 100 if cur["total"] else 0
        if share >= 15:
            obs.append(
                f"单笔最大：「{top['title']}」（{top['day'][5:]}，{top['model']}，"
                f"{top['rounds']} 轮）花 {top['credit']:.0f} 分，占本期 {share:.0f}%。"
            )

    if cur["silent_days"]:
        obs.append(f"有 {cur['silent_days']} 天完全没用，"
                   f"另有 {sum(1 for v in cur['daily'].values() if 0 < v < 10)} 天低于 10 分。")

    if cur["models"]:
        top_model, top_credit = next(iter(cur["models"].items()))
        pct = top_credit / cur["total"] * 100 if cur["total"] else 0
        obs.append(f"主力模型 {top_model}，占 {pct:.1f}%。")

    det = cur.get("detail")
    if det:
        mix = "、".join(
            f"{m} {v['credit']:.0f} 分 / {v['calls']} 次调用"
            for m, v in list(det["models"].items())[:3]
        )
        obs.append(
            f"日志可核对的调用共 {det['calls']} 次，覆盖本期 {det['coverage']:.0f}% 积分：{mix}。"
            + ("（日志按日轮转，低于 100% 属正常，不是漏账）" if det["coverage"] < 90 else "")
        )
        per_call = {
            m: v["credit"] / v["calls"] for m, v in det["models"].items() if v["calls"]
        }
        if len(per_call) > 1:
            lo = min(per_call, key=per_call.get)
            hi = max(per_call, key=per_call.get)
            obs.append(
                f"单次调用成本：{lo} {per_call[lo]:.2f} 分/次，"
                f"{hi} {per_call[hi]:.2f} 分/次——贵的那个适合留给真正需要它的重活。"
            )
    return obs


def suggestions(cur, ref30=None):
    tips = []
    if cur["top3_share"] >= 50 and cur["heavy_sessions"]:
        tips.append(
            "拆重活：把「一次给六份试卷 / 整个游戏代码库」这类超大输入拆成 2—3 次，"
            "每次只喂必要上下文，单次积分通常能降一半以上。"
        )
    if cur["peak_ratio"] >= 5:
        tips.append(
            "给重活设闸：单会话超过 50 分就停下来确认方向，避免在一个错误方向上反复重跑。"
        )
    if cur["silent_days"] >= 5:
        tips.append("低耗日不少，说明预算不是被「每天聊两句」用掉的，不必为日常问答节省。")
    if ref30 and ref30["total"]:
        pace = cur["total"] / ref30["total"] * 100
        tips.append(
            f"按当前节奏，本期占近 30 天总量的 {pace:.1f}%；"
            f"若余额按 30 天均速（{ref30['avg_per_day']:.0f} 分/天）估算，可自行外推可用天数。"
        )
    return tips


# ---------------------------------------------------------------- 定时任务

def load_automation_runs(db_path=DB_PATH):
    """读 automation_runs：每条运行记录对应一个会话，用 metadata_json.sessionId 关联积分。

    返回 (runs, schedules)：
      runs      = [{name, when, credit, status}]
      schedules = [{name, status, deleted, rrule, per_week}]  仅未删除的自动化
    """
    if not os.path.exists(db_path):
        return [], []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    credits = {}
    for r in con.execute("SELECT session_id, credit_json FROM session_usage"):
        try:
            cj = json.loads(r["credit_json"]) if r["credit_json"] else {}
        except (json.JSONDecodeError, TypeError):
            cj = {}
        credits[r["session_id"]] = sum(
            float(v) for v in cj.values() if isinstance(v, (int, float))
        )

    runs = []
    for r in con.execute(
        """
        SELECT r.created_at, r.metadata_json, a.name
        FROM automation_runs r LEFT JOIN automations a ON a.id = r.automation_id
        """
    ):
        try:
            md = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        except (json.JSONDecodeError, TypeError):
            md = {}
        sid = md.get("sessionId") or md.get("conversationId")
        runs.append(
            dict(
                name=(r["name"] or "(已删除的自动化)").strip(),
                when=dt.datetime.fromtimestamp(r["created_at"] / 1000),
                credit=credits.get(sid, 0.0),
                has_session=sid in credits,
            )
        )
    runs.sort(key=lambda x: x["when"])

    schedules = []
    for r in con.execute("SELECT name, status, deleted_at, rrule FROM automations"):
        if r["deleted_at"]:
            continue
        schedules.append(
            dict(name=(r["name"] or "").strip(), status=r["status"],
                 rrule=r["rrule"] or "", per_week=_runs_per_week(r["rrule"] or ""))
        )
    con.close()
    return runs, schedules


def _runs_per_week(rrule):
    """把 RRULE 折算成「每周跑几次」。只覆盖本工具会遇到的几种频率。"""
    if not rrule:
        return 0.0
    f = dict(kv.split("=", 1) for kv in rrule.split(";") if "=" in kv)
    freq = f.get("FREQ", "")
    try:
        interval = max(int(f.get("INTERVAL", 1)), 1)
    except ValueError:
        interval = 1
    if freq == "HOURLY":
        return 7 * 24 / interval
    if freq == "DAILY":
        return 7 / interval
    if freq == "WEEKLY":
        n = len([d for d in (f.get("BYDAY") or "").split(",") if d]) or 1
        return n / interval
    if freq == "MONTHLY":
        n = len([d for d in (f.get("BYMONTHDAY") or "1").split(",") if d]) or 1
        return n / interval / 4.345
    if freq == "YEARLY":
        return 1 / 52
    return 0.0


def summarize_automations(runs, schedules, d0, d1):
    """定时任务的区间消耗 + 按排期推算的稳态周消耗。"""
    start = dt.datetime.combine(d0, dt.time.min)
    end = dt.datetime.combine(d1, dt.time.max)
    sel = [r for r in runs if start <= r["when"] <= end]
    span = (d1 - d0).days + 1
    total = round(sum(r["credit"] for r in sel), 2)

    per = defaultdict(lambda: dict(runs=0, credit=0.0, zero=0, first=None, last=None))
    for r in sel:
        a = per[r["name"]]
        a["runs"] += 1
        a["credit"] += r["credit"]
        if r["credit"] == 0:
            a["zero"] += 1
        a["first"] = a["first"] or r["when"]
        a["last"] = r["when"]

    # 稳态估算用的单次成本：取该自动化全部历史消耗的**中位数**，
    # 比窗口均值稳（不受窗口长短和单次异常值影响）。
    hist = defaultdict(list)
    for r in runs:
        hist[r["name"]].append(r["credit"])
    avg_cost = {}
    for name, vals in hist.items():
        avg_cost[name] = statistics.median(vals) if vals else 0.0
    for name, a in per.items():
        avg_cost.setdefault(name, a["credit"] / a["runs"] if a["runs"] else 0.0)

    active = [s for s in schedules if s["status"] == "ACTIVE"]
    steady = [
        dict(name=s["name"], per_week=round(s["per_week"], 2),
             cost=round(avg_cost.get(s["name"], 0.0), 2),
             weekly=round(avg_cost.get(s["name"], 0.0) * s["per_week"], 2))
        for s in active
    ]
    steady.sort(key=lambda x: -x["weekly"])

    return dict(
        start=d0.isoformat(), end=d1.isoformat(), days=span,
        runs=len(sel), total=total,
        per_day=round(total / span, 2),
        per_week=round(total / span * 7, 2),
        per_run=round(total / len(sel), 2) if sel else 0.0,
        zero_runs=sum(1 for r in sel if r["credit"] == 0),
        items=sorted(
            [dict(name=k, runs=v["runs"], credit=round(v["credit"], 2),
                  avg=round(v["credit"] / v["runs"], 2) if v["runs"] else 0.0,
                  zero=v["zero"]) for k, v in per.items()],
            key=lambda x: -x["credit"],
        ),
        steady=steady,
        steady_week=round(sum(s["weekly"] for s in steady), 2),
        steady_day=round(sum(s["weekly"] for s in steady) / 7, 2),
    )


# ---------------------------------------------------------------- 输出

def fmt_markdown(w7, w30, prev7, obs, tips, note="", single=False):
    """Markdown 片段。

    single=True 时是「指定区间」口径（周报用），两列变成「本期 / 上期」；
    single=False 时是默认的「近 7 天 / 近 30 天」双列。
    """
    def table(rows, header):
        out = ["| " + " | ".join(header) + " |",
               "|" + "|".join(["---"] * len(header)) + "|"]
        out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
        return "\n".join(out)

    delta = ""
    if prev7["total"]:
        delta = f"{(w7['total'] / prev7['total'] - 1) * 100:+.1f}%"

    if single:
        c, p = w7, prev7
        rows = [
            ["总积分", f"**{c['total']:.0f}**", f"{p['total']:.0f}"],
            ["日均（自然日）", f"{c['avg_per_day']:.1f}", f"{p['avg_per_day']:.1f}"],
            ["活跃 / 静默天数", f"{c['active_days']} / {c['silent_days']}",
             f"{p['active_days']} / {p['silent_days']}"],
            ["峰值日", f"{c['peak_day'][5:]}（{c['peak_value']:.0f}）",
             f"{p['peak_day'][5:]}（{p['peak_value']:.0f}）"],
            ["会话数 / 对话轮", f"{c['sessions']} / {c['rounds']}",
             f"{p['sessions']} / {p['rounds']}"],
            ["单会话中位 / 最大", f"{c['per_session_median']:.1f} / {c['per_session_max']:.0f}",
             f"{p['per_session_median']:.1f} / {p['per_session_max']:.0f}"],
            ["Top3 会话占比", f"{c['top3_share']:.0f}%", f"{p['top3_share']:.0f}%"],
            ["环比上期", delta or "—", "—"],
        ]
        head = "花在哪儿（本期 Top5 会话）"
        tops = c["top_sessions"][:5]
        day_line = " · ".join(f"{d[5:]} {v:.0f}" for d, v in c["daily"].items())
        lines = [
            "### 积分消耗（数据源：本机 workbuddy.db + 运行日志，离线统计）\n",
            table(rows, ["指标",
                         f"本期 {c['start'][5:]} ~ {c['end'][5:]}（{c['days']} 天）",
                         f"上期 {p['start'][5:]} ~ {p['end'][5:]}"]),
            "\n**逐日明细（分）**\n",
            day_line,
        ]
    else:
        days7 = list(w7["daily"].items())
        days30 = list(w30["daily"].items())
        rows = [
            ["统计区间", f"{w7['start']} ~ {w7['end']}（{w7['days']} 天）",
             f"{w30['start']} ~ {w30['end']}（{w30['days']} 天）"],
            ["总积分", f"**{w7['total']:.0f}**", f"**{w30['total']:.0f}**"],
            ["日均（自然日）", f"{w7['avg_per_day']:.1f}", f"{w30['avg_per_day']:.1f}"],
            ["日均（活跃日）", f"{w7['avg_per_active']:.1f}", f"{w30['avg_per_active']:.1f}"],
            ["活跃 / 静默天数", f"{w7['active_days']} / {w7['silent_days']}",
             f"{w30['active_days']} / {w30['silent_days']}"],
            ["峰值日", f"{w7['peak_day']}（{w7['peak_value']:.0f}）",
             f"{w30['peak_day']}（{w30['peak_value']:.0f}）"],
            ["会话数 / 对话轮", f"{w7['sessions']} / {w7['rounds']}",
             f"{w30['sessions']} / {w30['rounds']}"],
            ["单会话中位 / 最大", f"{w7['per_session_median']:.1f} / {w7['per_session_max']:.0f}",
             f"{w30['per_session_median']:.1f} / {w30['per_session_max']:.0f}"],
            ["Top3 会话占比", f"{w7['top3_share']:.0f}%", f"{w30['top3_share']:.0f}%"],
            ["环比上期", delta or "—", "—"],
        ]
        head = "花在哪儿（近 30 天 Top5 会话）"
        tops = w30["top_sessions"][:5]
        lines = [
            "### 积分消耗（数据源：本机 workbuddy.db + 运行日志，离线统计）\n",
            table(rows, ["指标", "近 7 天", "近 30 天"]),
            "\n**逐日明细（分）**\n",
            "近 7 天：" + " · ".join(f"{d[5:]} {v:.0f}" for d, v in days7),
            "\n近 30 天：" + " · ".join(f"{d[5:]} {v:.0f}" for d, v in days30),
        ]

    lines.append(f"\n**{head}**\n")
    lines.append(
        table(
            [[s["title"], s["day"][5:], f"{s['credit']:.0f}", s["rounds"], s["model"]]
             for s in tops],
            ["任务", "日期", "积分", "轮次", "模型"],
        )
    )
    lines.append("\n**观察**\n")
    lines += [f"- {o}" for o in obs]
    if tips:
        lines.append("\n**建议**\n")
        lines += [f"- {t}" for t in tips]
    if note:
        lines.append(f"\n> {note}")
    return "\n".join(lines)


def fmt_console(w):
    print(f"\n【{w['label']}】{w['start']} ~ {w['end']}（{w['days']} 天）")
    print(f"  总积分 {w['total']:.2f} | 会话 {w['sessions']} | 对话轮 {w['rounds']} "
          f"| 活跃 {w['active_days']}/{w['days']} 天")
    print(f"  日均 {w['avg_per_day']:.2f}（活跃日均 {w['avg_per_active']:.2f}）"
          f"| 中位日 {w['median_day']:.2f} | 峰值 {w['peak_day']} {w['peak_value']:.2f}")
    print(f"  单会话 中位 {w['per_session_median']:.2f} / P90 {w['per_session_p90']:.2f} "
          f"/ 最大 {w['per_session_max']:.2f} | 每轮 {w['credit_per_round']:.2f}")
    print(f"  集中度 Top1 {w['top1_share']:.0f}% · Top3 {w['top3_share']:.0f}% "
          f"· Top5 {w['top5_share']:.0f}%")
    print("  模型：" + "、".join(f"{k} {v:.0f}" for k, v in w["models"].items()))
    print("  项目 Top5：")
    for p in w["projects"][:5]:
        print(f"    {p['name'][:30]:32s}{p['credit']:9.2f}  ({p['sessions']} 会话)")
    ds = w["daily"]
    peak = max(ds.values()) if ds else 0
    for d, v in ds.items():
        bar = "#" * int(v / peak * 40) if peak else ""
        print(f"    {d} {v:8.2f} {bar}")
    if "detail" in w:
        det = w["detail"]
        print(f"  日志明细：{det['calls']} 次调用，覆盖 {det['coverage']:.0f}% 积分")
        for m, v in det["models"].items():
            print(f"    {m:28s}{v['credit']:9.2f}  {v['calls']:5d}次  "
                  f"{v['credit_per_ktok']:.4f} 分/千tok")
        print("    时段：" + " ".join(f"{h}h={v:.0f}" for h, v in det["hours"].items()))


def fmt_html(w7, w30, prev7, obs, tips, verdict="", auto=None):
    """独立单页 HTML（浅色杂志风），供直接打开查看。"""
    def bars(series, step=1):
        peak = max(series.values()) or 1
        cells = []
        for i, (d, v) in enumerate(series.items()):
            h = max(int(v / peak * 104), 2)
            cells.append(
                f'<div class="b" title="{d} {v:.1f} 分">'
                f'<div class="bar" style="height:{h}px;'
                f'opacity:{0.35 + 0.65 * v / peak:.2f}"></div>'
                f'<span>{d[5:] if i % step == 0 else ""}</span></div>'
            )
        return "".join(cells)

    def rows(items, cols):
        return "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            for r in ([c(i) for c in cols] if False else [[str(x) for x in row] for row in items])
        )

    delta = f"{(w7['total'] / prev7['total'] - 1) * 100:+.1f}%" if prev7["total"] else "—"
    proj_rows = "".join(
        f"<tr><td>{p['name']}</td><td class='num'>{p['credit']:.0f}</td><td class='num'>{p['sessions']}</td></tr>"
        for p in w30["projects"][:6]
    )
    sess_rows = "".join(
        f"<tr><td>{s['title']}</td><td class='num'>{s['day'][5:]}</td>"
        f"<td class='num'>{s['credit']:.0f}</td><td class='num'>{s['rounds']}</td>"
        f"<td>{s['model']}</td></tr>"
        for s in w30["top_sessions"][:6]
    )
    if auto:
        auto_rows = "".join(
            f"<tr><td>{i['name']}</td><td class='num'>{i['runs']}</td>"
            f"<td class='num'>{i['credit']:.0f}</td><td class='num'>{i['avg']:.2f}</td></tr>"
            for i in auto["items"]
        )
        steady_rows = "".join(
            f"<tr><td>{s['name']}</td><td class='num'>{s['per_week']:g}</td>"
            f"<td class='num'>{s['cost']:.2f}</td><td class='num'>{s['weekly']:.1f}</td></tr>"
            for s in auto["steady"]
        )
        auto_html = (
            f"<div class='cards' style='grid-template-columns:repeat(3,1fr);margin:18px 0 16px'>"
            f"<div class='card'><div class='k'>定时任务 · 日均</div>"
            f"<div class='v'>{auto['per_day']:.1f}<small>分/天</small></div></div>"
            f"<div class='card'><div class='k'>定时任务 · 周均</div>"
            f"<div class='v'>{auto['per_week']:.0f}<small>分/周</small></div></div>"
            f"<div class='card'><div class='k'>按排期稳态（周）</div>"
            f"<div class='v'>{auto['steady_week']:.0f}<small>分/周</small></div></div></div>"
            f"<table><tr><th>自动化</th><th style='text-align:right'>运行</th>"
            f"<th style='text-align:right'>积分</th><th style='text-align:right'>均次</th></tr>"
            f"{auto_rows}</table>"
            f"<p style='font-size:12px;color:var(--sub);margin:10px 0 6px'>"
            f"按当前 RRULE 推算的稳态周消耗（仅启用中）：</p>"
            f"<table><tr><th>自动化</th><th style='text-align:right'>次/周</th>"
            f"<th style='text-align:right'>均次成本</th><th style='text-align:right'>周消耗</th></tr>"
            f"{steady_rows}</table>"
        )
        auto_head = (f'<h2>06 定时任务（{auto["start"][5:]} ~ {auto["end"][5:]}）</h2>')
        auto_note = ("<p style='font-size:12px;color:var(--sub);margin:8px 0 0'>"
                     "实测周均是「这段时间实际跑了多少」，稳态是按 RRULE 推算的「全开之后每周会花多少」；"
                     "两者差距通常来自新排期的自动化还没跑满一个周期。</p>")
        n_obs, n_tips = "07", "08"
    else:
        auto_html = ""
        auto_head = ""
        auto_note = ""
        n_obs, n_tips = "06", "07"

    obs_html = "".join(f"<li>{o}</li>" for o in obs)
    tips_html = "".join(f"<li>{t}</li>" for t in tips)
    model_html = "".join(
        f"<div class='mrow'><div class='mtop'><span>{k}</span>"
        f"<b>{v:.0f} 分 · {v / w30['total'] * 100:.0f}%</b></div>"
        f"<div class='mtrack'><i style='width:{v / w30['total'] * 100:.1f}%'></i></div></div>"
        for k, v in w30["models"].items()
    )
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>WorkBuddy 积分消耗报告</title>
<style>
:root{{--ink:#1b1b1b;--sub:#6b6b6b;--line:#e2ddd6;--accent:#9c2f2f;--bg:#faf8f5;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
line-height:1.7;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:860px;margin:0 auto;padding:56px 32px 80px}}
h1{{font-size:32px;margin:0 0 6px;letter-spacing:-.5px;font-weight:700}}
.sub{{color:var(--sub);font-size:13px;letter-spacing:.5px;margin-bottom:36px}}
h2{{font-size:15px;letter-spacing:2px;color:var(--accent);margin:44px 0 14px;font-weight:600}}
h2::before{{content:"—— ";opacity:.5}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0 8px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
.card .k{{font-size:11px;color:var(--sub);letter-spacing:1px}}
.card .v{{font-size:26px;font-weight:700;margin-top:4px;letter-spacing:-1px}}
.card .v small{{font-size:12px;font-weight:400;color:var(--sub);margin-left:4px}}
.up{{color:#b02a2a}}.down{{color:#2f7a4f}}
.verdict{{margin:22px 0 4px;padding:16px 20px;background:#fff;border:1px solid var(--line);
border-left:3px solid var(--accent);border-radius:6px;font-size:14.5px;line-height:1.75}}
.verdict span{{display:block;font-size:11px;letter-spacing:2px;color:var(--accent);
margin-bottom:6px;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;background:#fff;
border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th{{text-align:left;font-weight:600;font-size:11.5px;letter-spacing:1px;color:var(--sub);
background:#f4f1ec;padding:10px 14px;border-bottom:1px solid var(--line)}}
td{{padding:10px 14px;border-bottom:1px solid #f0ece6}}
tr:last-child td{{border-bottom:none}}
.num{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
.chart{{display:flex;align-items:flex-end;gap:3px;height:150px;padding:16px 12px 0;
background:#fff;border:1px solid var(--line);border-radius:10px}}
.b{{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}}
.b .bar{{width:100%;border-radius:2px 2px 0 0;min-height:2px;background:var(--accent)}}
.b span{{font-size:9px;color:var(--sub);margin-top:6px;white-space:nowrap;
letter-spacing:-.2px}}
.mline{{display:none}}
.mrow{{margin-bottom:11px}}
.mtop{{display:flex;justify-content:space-between;align-items:baseline;
font-size:12.5px;margin-bottom:5px}}
.mtop span{{color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.mtop b{{font-variant-numeric:tabular-nums;font-weight:600;font-size:12px;flex:none;margin-left:8px}}
.mtrack{{height:6px;background:#efeae3;border-radius:3px;overflow:hidden}}
.mtrack i{{display:block;height:100%;background:var(--accent);opacity:.75;border-radius:3px}}
ul{{padding-left:20px;margin:8px 0}}li{{margin:7px 0;font-size:14px}}
.note{{font-size:12px;color:var(--sub);border-left:2px solid var(--line);padding-left:12px;margin-top:32px}}
</style></head><body><div class="wrap">
<h1>WorkBuddy 积分消耗报告</h1>
<div class="sub">统计时间 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据源：本机 workbuddy.db 与运行日志（离线，未联网）</div>

<div class="cards">
  <div class="card"><div class="k">近 7 天</div><div class="v">{w7['total']:.0f}<small>分</small></div></div>
  <div class="card"><div class="k">近 30 天</div><div class="v">{w30['total']:.0f}<small>分</small></div></div>
  <div class="card"><div class="k">日均（30 天）</div><div class="v">{w30['avg_per_day']:.0f}<small>分/天</small></div></div>
  <div class="card"><div class="k">环比上 7 天</div><div class="v {'up' if delta.startswith('+') else 'down'}">{delta}</div></div>
</div>

{f'<div class="verdict"><span>一句话判断</span>{verdict}</div>' if verdict else ''}

<h2>01 近 7 天逐日</h2>
<div class="chart">{bars(w7['daily'])}</div>

<h2>02 近 30 天逐日</h2>
<div class="chart">{bars(w30['daily'], step=3)}</div>

<h2>03 关键指标</h2>
<table>
<tr><th>指标</th><th style="text-align:right">近 7 天</th><th style="text-align:right">近 30 天</th></tr>
<tr><td>总积分</td><td class="num">{w7['total']:.0f}</td><td class="num">{w30['total']:.0f}</td></tr>
<tr><td>活跃 / 静默天数</td><td class="num">{w7['active_days']} / {w7['silent_days']}</td><td class="num">{w30['active_days']} / {w30['silent_days']}</td></tr>
<tr><td>日均（自然日）</td><td class="num">{w7['avg_per_day']:.1f}</td><td class="num">{w30['avg_per_day']:.1f}</td></tr>
<tr><td>中位活跃日</td><td class="num">{w7['median_day']:.1f}</td><td class="num">{w30['median_day']:.1f}</td></tr>
<tr><td>峰值日</td><td class="num">{w7['peak_day'][5:]} · {w7['peak_value']:.0f}</td><td class="num">{w30['peak_day'][5:]} · {w30['peak_value']:.0f}</td></tr>
<tr><td>会话数 / 对话轮</td><td class="num">{w7['sessions']} / {w7['rounds']}</td><td class="num">{w30['sessions']} / {w30['rounds']}</td></tr>
<tr><td>单会话中位 / P90 / 最大</td><td class="num">{w7['per_session_median']:.1f} / {w7['per_session_p90']:.0f} / {w7['per_session_max']:.0f}</td><td class="num">{w30['per_session_median']:.1f} / {w30['per_session_p90']:.0f} / {w30['per_session_max']:.0f}</td></tr>
<tr><td>Top3 会话占比</td><td class="num">{w7['top3_share']:.0f}%</td><td class="num">{w30['top3_share']:.0f}%</td></tr>
</table>

<h2>04 积分去向（近 30 天）</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
<div><table><tr><th>项目</th><th style="text-align:right">积分</th><th style="text-align:right">会话</th></tr>{proj_rows}</table></div>
<div>{model_html}</div>
</div>

<h2>05 单笔最大消耗</h2>
<table><tr><th>任务</th><th style="text-align:right">日期</th><th style="text-align:right">积分</th><th style="text-align:right">轮次</th><th>模型</th></tr>{sess_rows}</table>

{auto_head}{auto_html}{auto_note}
<h2>{n_obs} 观察</h2><ul>{obs_html}</ul>
<h2>{n_tips} 建议</h2><ul>{tips_html}</ul>

<div class="note">口径说明：「积分」取自 session_usage 的请求级积分求和；会话按其最后活动时间归日，跨零点长会话会整体计入结束日。「对话轮次」为根请求数，不等于消息条数。日志会轮转，模型/时段维度仅覆盖最近数日，明细覆盖率已在观察中标出。</div>
</div></body></html>"""


def fmt_automations(auto, md=False):
    """定时任务一节的文本输出。md=True 出 Markdown，否则出控制台文本。"""
    lines = []
    head = f"定时任务消耗（{auto['start']} ~ {auto['end']}，{auto['days']} 天）"
    if md:
        lines.append(f"\n**{head}**\n")
        lines.append("| 指标 | 数值 |")
        lines.append("|---|---|")
        lines += [
            f"| 运行次数 | {auto['runs']} 次（其中 {auto['zero_runs']} 次零消耗） |",
            f"| 总积分 | **{auto['total']:.0f}** |",
            f"| 日均 | {auto['per_day']:.1f} |",
            f"| 周均 | {auto['per_week']:.1f} |",
            f"| 单次均摊 | {auto['per_run']:.2f} |",
        ]
        if auto["items"]:
            lines.append("\n| 自动化 | 运行 | 积分 | 均次 |")
            lines.append("|---|---|---|---|")
            lines += [
                f"| {i['name']} | {i['runs']} | {i['credit']:.1f} | {i['avg']:.2f} |"
                for i in auto["items"]
            ]
        if auto["steady"]:
            lines.append(
                f"\n按当前排期推算（仅计启用中的 {len(auto['steady'])} 个）："
                f"**每周约 {auto['steady_week']:.0f} 分，每天约 {auto['steady_day']:.1f} 分**。\n"
            )
            lines.append("| 自动化 | 次/周 | 均次成本 | 周消耗 |")
            lines.append("|---|---|---|---|")
            lines += [
                f"| {s['name']} | {s['per_week']:g} | {s['cost']:.2f} | {s['weekly']:.1f} |"
                for s in auto["steady"]
            ]
        return "\n".join(lines)

    print(f"\n【{head}】")
    print(f"  运行 {auto['runs']} 次（零消耗 {auto['zero_runs']}）| 总 {auto['total']:.2f} 分 "
          f"| 日均 {auto['per_day']:.2f} | 周均 {auto['per_week']:.2f} | 均次 {auto['per_run']:.2f}")
    for i in auto["items"]:
        print(f"    {i['name'][:32]:34s}{i['runs']:3d}次 {i['credit']:8.2f} 分  均 {i['avg']:5.2f}")
    if auto["steady"]:
        print(f"  按排期推算（启用中 {len(auto['steady'])} 个）："
              f"每周约 {auto['steady_week']:.1f} 分 / 每天约 {auto['steady_day']:.1f} 分")
        for s in auto["steady"]:
            print(f"    {s['name'][:32]:34s}{s['per_week']:5g} 次/周 × {s['cost']:5.2f} "
                  f"= {s['weekly']:7.2f}/周")
    return ""


# ---------------------------------------------------------------- 入口

def main():
    ap = argparse.ArgumentParser(description="WorkBuddy 积分消耗统计")
    ap.add_argument("--days", type=int, default=None, help="统计最近 N 天（含今天）")
    ap.add_argument("--from", dest="d_from", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--to", dest="d_to", help="结束日期 YYYY-MM-DD")
    ap.add_argument("--detail", action="store_true", help="解析日志补充模型/token/时段明细")
    ap.add_argument("--md", action="store_true", help="输出 Markdown 片段")
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    ap.add_argument("--html", metavar="PATH", help="输出独立 HTML 报告到指定路径")
    ap.add_argument("--verdict", default="", help="一句话判断，写到报告顶部")
    ap.add_argument("--automations", action="store_true",
                    help="追加定时任务（自动化）消耗拆分与稳态估算")
    ap.add_argument("--no-compare", action="store_true", help="跳过环比与 30 天参照")
    args = ap.parse_args()

    recs = load_sessions()

    if args.d_from and args.d_to:
        d0 = dt.date.fromisoformat(args.d_from)
        d1 = dt.date.fromisoformat(args.d_to)
        single = True
    else:
        n = args.days or 7
        d1 = dt.date.today()
        d0 = d1 - dt.timedelta(days=n - 1)
        single = False

    auto = None
    if args.automations:
        _runs, _sched = load_automation_runs()
        auto = summarize_automations(_runs, _sched, d0, d1)

    if single:
        detail = load_log_detail(d0, d0) if args.detail else None
        # 单区间模式下仍需全区间日志
        if args.detail:
            detail = load_log_detail(d0, d1)
        cur = summarize(recs, d0, d1, f"{d0} ~ {d1}", detail)
        p0, p1 = previous_window(d0, d1)
        pre = summarize(recs, p0, p1, f"{p0} ~ {p1}")
        obs, tips = evaluate(cur, pre), suggestions(cur)
        cur["evaluation"] = obs
        cur["suggestions"] = tips
        if auto:
            cur["automations"] = auto
        if args.json:
            json.dump(cur, sys.stdout, indent=2, ensure_ascii=False)
        elif args.md:
            print(fmt_markdown(cur, cur, pre, obs, tips, single=True))
            if auto:
                print(fmt_automations(auto, md=True))
        elif args.html:
            open(args.html, "w").write(fmt_html(cur, cur, pre, obs, tips, args.verdict, auto))
            print(f"[ok] {args.html}")
        else:
            fmt_console(cur)
            print("\n观察：")
            for o in obs:
                print("  ·", o)
            print("\n建议：")
            for t in tips:
                print("  ·", t)
            if auto:
                fmt_automations(auto)
        return

    d30_0 = dt.date.today() - dt.timedelta(days=29)
    d30_1 = dt.date.today()
    detail = load_log_detail(d0, d30_1) if args.detail else None
    w7 = summarize(recs, d0, d1, "近 7 天", detail)
    w30 = summarize(recs, d30_0, d30_1, "近 30 天", detail)
    p0, p1 = previous_window(d0, d1)
    prev7 = summarize(recs, p0, p1, "上个 7 天")
    obs = evaluate(w7, prev7, w30)
    tips = suggestions(w7, w30)

    if args.json:
        payload = dict(generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                       w7=w7, prev7=prev7, w30=w30, evaluation=obs, suggestions=tips)
        if auto:
            payload["automations"] = auto
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    elif args.md:
        print(fmt_markdown(w7, w30, prev7, obs, tips))
        if auto:
            print(fmt_automations(auto, md=True))
    elif args.html:
        open(args.html, "w").write(fmt_html(w7, w30, prev7, obs, tips, args.verdict, auto))
        print(f"[ok] {args.html}")
    else:
        fmt_console(w30)
        fmt_console(w7)
        print("\n观察：")
        for o in obs:
            print("  ·", o)
        print("\n建议：")
        for t in tips:
            print("  ·", t)
        if auto:
            fmt_automations(auto)


if __name__ == "__main__":
    main()
