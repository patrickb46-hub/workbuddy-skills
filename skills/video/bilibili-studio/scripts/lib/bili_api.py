#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bili_api.py — Bilibili 创作中心接口封装（零第三方依赖，仅标准库）

设计原则：
1. 只读接口优先，写操作全部交给 biliup 二进制（更稳、有风控处理）
2. 不做重试风暴，B 站对高频请求敏感，默认单次 + 温和退避
3. 所有百分比字段做双份输出：raw（原始）+ pct（换算成 0-100）
"""

import json
import gzip
import io
import os
import time
import urllib.request
import urllib.parse
import urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

HOME = os.path.expanduser("~/.workbuddy/skills/bilibili-studio")
COOKIE_FILE = os.path.join(HOME, "data", "cookies.json")

# 创作中心频率限制较严，两次请求之间至少隔这么久
_MIN_INTERVAL = 0.8
_last_request_at = 0.0


class BiliError(Exception):
    """带错误码的接口异常"""

    def __init__(self, code, message, endpoint=""):
        self.code = code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"[{code}] {message} ({endpoint})")

    @property
    def need_login(self):
        return self.code == -101

    @property
    def is_risk_control(self):
        # -352 风控校验失败, -412 请求被拦截, -509 超出限制
        return self.code in (-352, -412, -509, -799)


# ---------------------------------------------------------------- 凭证

def load_cookie():
    """读取凭证。支持 biliup 的 cookies.json 格式自动转换。"""
    if not os.path.exists(COOKIE_FILE):
        return None
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None

    # 已经是扁平格式
    if isinstance(raw, dict) and "SESSDATA" in raw:
        return raw

    # biliup login 产出的格式：{"cookie_info": {"cookies": [{"name":..,"value":..}]}}
    flat = {}
    cookies = (
        raw.get("cookie_info", {}).get("cookies")
        or raw.get("cookies")
        or []
    )
    for c in cookies:
        if isinstance(c, dict) and c.get("name"):
            flat[c["name"]] = c.get("value", "")
    if not flat and isinstance(raw, dict):
        # 兜底：把顶层字符串值当作 cookie
        flat = {k: v for k, v in raw.items() if isinstance(v, str)}
    return flat or None


def save_cookie(cookie_dict):
    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookie_dict, f, ensure_ascii=False, indent=2)
    os.chmod(COOKIE_FILE, 0o600)


def cookie_header(cookie_dict=None):
    ck = cookie_dict or load_cookie()
    if not ck:
        return ""
    keys = ["SESSDATA", "bili_jct", "buvid3", "buvid4", "DedeUserID",
            "DedeUserID__ckMd5", "sid"]
    parts = [f"{k}={ck[k]}" for k in keys if ck.get(k)]
    # 保留其它未知但在必要清单外的 cookie
    for k, v in ck.items():
        if k not in keys and v:
            parts.append(f"{k}={v}")
    return "; ".join(parts)


# ---------------------------------------------------------------- HTTP

def _throttle():
    global _last_request_at
    gap = time.time() - _last_request_at
    if gap < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - gap)
    _last_request_at = time.time()


def _get(url, params=None, referer="https://member.bilibili.com/", timeout=20):
    _throttle()
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", referer)
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Accept-Encoding", "gzip, deflate")
    ck = cookie_header()
    if ck:
        req.add_header("Cookie", ck)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower()
    except urllib.error.HTTPError as e:
        data = e.read()
        enc = (e.headers.get("Content-Encoding") or "").lower()

    if enc == "gzip":
        try:
            data = gzip.decompress(data)
        except Exception:
            pass
    elif enc == "deflate":
        try:
            data = gzip.decompress(data)
        except Exception:
            data = data
    else:
        # 服务器未声明编码但内容是 gzip 的情况
        if data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except Exception:
                pass

    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        raise BiliError(-1, f"响应非 JSON: {data[:120]!r}", url)

    code = payload.get("code", -1)
    if code != 0:
        raise BiliError(code, payload.get("message", "unknown"), url)
    return payload.get("data")


# ---------------------------------------------------------------- 读接口

def whoami():
    """账号自检：返回 uid / 昵称 / 等级 / 粉丝数。需要 SESSDATA。"""
    url = "https://api.bilibili.com/x/web-interface/nav"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://www.bilibili.com/")
    ck = cookie_header()
    if ck:
        req.add_header("Cookie", ck)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            data = gzip.decompress(data)
    payload = json.loads(data.decode("utf-8"))
    d = payload.get("data") or {}
    if not d.get("isLogin"):
        raise BiliError(-101, "账号未登录或凭证已过期", url)
    return {
        "uid": d.get("mid"),
        "name": d.get("uname"),
        "level": d.get("level"),
        "coins": d.get("money"),
        "vip": (d.get("vipStatus") == 1),
        "fans": d.get("follower"),
        "avatar": d.get("face"),
    }


def account_stat():
    """UP 主总体数据：昨日增量 + 累计（播放/弹幕/评论/收藏/投币/分享/粉丝）"""
    return _get("https://member.bilibili.com/x/web/index/stat", referer="https://member.bilibili.com/platform/home")


def archive_list(status="is_pubing,pubed", pn=1, ps=20):
    """稿件列表。status 可选 is_pubing（审核中）/ pubed（已过审）/ not_pubed（未过审）"""
    return _get("https://member.bilibili.com/x/web/archives",
                {"status": status, "pn": pn, "ps": ps},
                referer="https://member.bilibili.com/platform/upload-manager/article")


def compare_recent(size=10):
    """
    最近 N 条视频横向对比 —— 这是复盘的黄金接口。
    直接给出完播比、3秒退出率、互动率、播转粉率等诊断指标。

    注意：百分比字段原始单位是「万分之一」，100 = 1%。
    这里同时输出 raw 和 pct（百分数，如 35.2 表示 35.2%）。
    """
    data = _get("https://member.bilibili.com/x/web/data/archive_diagnose/compare",
                {"size": size},
                referer="https://member.bilibili.com/platform/data-up")
    items = []
    pct_keys = ["crash_rate", "full_play_ratio", "interact_rate",
                "play_trans_fan_rate", "active_fans_rate", "play_viewer_rate"]
    for it in (data or {}).get("list", []) or []:
        row = dict(it)
        row["pct"] = {}
        for k in pct_keys:
            if isinstance(it.get(k), (int, float)):
                row["pct"][k] = round(it[k] / 100.0, 2)
        # 时长秒转可读
        dur = it.get("duration")
        if isinstance(dur, (int, float)) and dur:
            row["duration_str"] = f"{int(dur) // 60}:{int(dur) % 60:02d}"
        if it.get("pubtime"):
            row["pubtime_str"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(it["pubtime"]))
        items.append(row)
    return items


def trend(type_code=1, referer="https://member.bilibili.com/platform/data-up"):
    """近 30 天日增趋势。type: 1播放 2弹幕 3评论 4分享 5投币 6收藏 7充电 8点赞"""
    data = _get("https://member.bilibili.com/x/web/data/pandect",
                {"type": type_code}, referer=referer)
    rows = []
    for it in data or []:
        rows.append({
            "date": time.strftime("%Y-%m-%d", time.localtime(it.get("date_key", 0))),
            "inc": it.get("total_inc", 0),
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def fan_trend():
    """近 30 天粉丝增长趋势（走稿件数据接口，字段名有差异时容错）"""
    try:
        return trend(type_code=1)  # 占位：粉丝趋势若接口变动则降级
    except BiliError:
        return []


# ---------------------------------------------------------------- 诊断

# 阈值参考 B 站创作者普遍经验值，非官方标准，用于生成提示信号而非判决
THRESHOLDS = {
    "full_play_ratio": {"good": 30.0, "warn": 15.0, "label": "完播率"},
    "crash_rate": {"good": 30.0, "warn": 50.0, "label": "3秒退出率", "reverse": True},
    "interact_rate": {"good": 5.0, "warn": 2.0, "label": "互动率"},
    "play_trans_fan_rate": {"good": 1.0, "warn": 0.3, "label": "播转粉率"},
    "active_fans_rate": {"good": 10.0, "warn": 3.0, "label": "粉丝观看率"},
}


def diagnose(item):
    """
    对单条视频生成结构化诊断信号。
    返回 signals 列表，每条含 level(good/warn/bad) + metric + 结论 + 推断原因。
    """
    pct = item.get("pct") or {}
    sig = []

    def grade(key):
        t = THRESHOLDS[key]
        v = pct.get(key)
        if v is None:
            return None
        if t.get("reverse"):
            level = "good" if v < t["good"] else ("warn" if v < t["warn"] else "bad")
        else:
            level = "good" if v > t["good"] else ("warn" if v > t["warn"] else "bad")
        return level

    fps = grade("full_play_ratio")
    crash = grade("crash_rate")
    inter = grade("interact_rate")
    trans = grade("play_trans_fan_rate")

    # 组合诊断：播放与完播的交叉最能说明问题
    play = item.get("play") or 0
    if crash == "bad":
        sig.append({"level": "bad", "metric": "crash_rate",
                    "finding": "3秒退出率过高，大量观众在开场就划走",
                    "cause": "封面/标题与内容预期不符，或前3秒没有给出留人理由"})
    if fps == "bad":
        sig.append({"level": "bad", "metric": "full_play_ratio",
                    "finding": "完播率偏低，观众中途流失",
                    "cause": "中段节奏拖沓、信息密度不足，或时长超出内容承载力"})
    if inter == "bad" and play > 100:
        sig.append({"level": "bad", "metric": "interact_rate",
                    "finding": "互动率偏低，看完的人不愿点赞/评论",
                    "cause": "缺少引导、缺少观点表达，内容过于平铺"})
    if trans == "bad" and play > 100:
        sig.append({"level": "warn", "metric": "play_trans_fan_rate",
                    "finding": "播转粉率低，看完不关注",
                    "cause": "单条内容自洽但缺少「持续追更理由」，账号人设不清晰"})
    if fps == "good" and play < 200:
        sig.append({"level": "warn", "metric": "play",
                    "finding": "内容留得住人，但拿不到推荐流量",
                    "cause": "冷启动分发不足：封面点击率、标签、分区选择、发布时间"})
    if fps == "good" and inter == "good" and play >= 300:
        sig.append({"level": "good", "metric": "combo",
                    "finding": "内容质量过关（完播+互动双高）",
                    "cause": "这套结构值得复用"})
    elif fps == "good" and inter == "good" and play < 300:
        sig.append({"level": "warn", "metric": "combo",
                    "finding": "小样本范围内指标好看，但播放量太低不足以定论",
                    "cause": "可能是熟人/粉丝撑起的互动，等流量池放大后再看"})

    return sig


def baseline(items):
    """账号基线：给定视频列表算出中位数，用于判断新视频是否跑赢自己"""
    if not items:
        return {}
    def med(vals):
        vals = sorted(v for v in vals if isinstance(v, (int, float)))
        if not vals:
            return 0
        n = len(vals)
        return vals[n // 2] if n % 2 else round((vals[n // 2 - 1] + vals[n // 2]) / 2, 2)
    return {
        "sample": len(items),
        "play_median": med([i.get("play") for i in items]),
        "like_median": med([i.get("like") for i in items]),
        "coin_median": med([i.get("coin") for i in items]),
        "fav_median": med([i.get("fav") for i in items]),
        "comment_median": med([i.get("comment") for i in items]),
        "full_play_ratio_median": med([(i.get("pct") or {}).get("full_play_ratio") for i in items]),
        "interact_rate_median": med([(i.get("pct") or {}).get("interact_rate") for i in items]),
        "duration_median": med([i.get("duration") for i in items]),
    }
