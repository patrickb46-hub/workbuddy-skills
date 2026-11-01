#!/usr/bin/env python3
"""
bili.py — B 站拉片工具（零登录、零依赖直连 B 站公开接口）

子命令:
  probe                         环境自检（ffmpeg / Pillow / 接口连通性）
  info   BV号                   视频元数据 + 分P + 简介
  sheet  BV号 [--times ...]     拉预览雪碧图并按秒裁帧（核心能力：看画面）
  download BV号 --out f.mp4     下载直链（默认 360P，免登录）
  clip   BV号 --from 10 --to 20 截取片段（需 ffmpeg 可用）

输出统一为 JSON（便于下游解析）；--human 输出人类可读摘要。

设计取舍:
  - 不用 yt-dlp / 不依赖登录 cookie，只用官方 web 接口
  - 抽帧走 videoshot 雪碧图：一次请求拿全片 100 帧，比逐段 ffmpeg 便宜几个数量级
  - 所有网络请求带 UA + Referer，缺 Referer 会被 CDN 403
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Referer": "https://www.bilibili.com"}
API = "https://api.bilibili.com"
_BUV = {"done": False}


def ensure_fingerprint():
    """B 站会对无设备指纹的请求偶发返回空数据（videoshot 的 index 为空）。
    取一次 buvid3 挂到 Cookie 上，能显著降低这种空返回的概率。"""
    if _BUV["done"]:
        return
    _BUV["done"] = True
    try:
        req = urllib.request.Request(
            f"{API}/x/frontend/finger/spi", headers={"User-Agent": UA}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            b3 = json.loads(r.read().decode())["data"]["b_3"]
        if b3:
            HEADERS["Cookie"] = f"buvid3={b3}"
            _BUV["b3"] = b3
    except Exception:  # noqa: BLE001  指纹是可选项，拿不到也别中断
        pass


MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]
_WBI = {"key": None, "ts": 0}


def wbi_key(force=False):
    """取 wbi 签名用的 mixin key（有效期内缓存 30 分钟）。"""
    if not force and _WBI["key"] and time.time() - _WBI["ts"] < 1800:
        return _WBI["key"]
    ensure_fingerprint()
    req = urllib.request.Request(f"{API}/x/web-interface/nav", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        nav = json.loads(r.read().decode())["data"]["wbi_img"]
    img = nav["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub = nav["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    orig = img + sub
    _WBI["key"] = "".join(orig[i] for i in MIXIN_TAB)[:32]
    _WBI["ts"] = time.time()
    return _WBI["key"]


def wbi_sign(params):
    """按 B 站规则对参数签名，返回完整 query string。"""
    key = wbi_key()
    p = dict(params)
    p["wts"] = int(time.time())
    items = sorted(p.items())
    clean = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*") for k, v in items
    }
    q = urllib.parse.urlencode(clean)
    p["w_rid"] = hashlib.md5((q + key).encode()).hexdigest()
    return urllib.parse.urlencode(sorted(p.items()))


def wbi_api(path, **params):
    """带 wbi 签名的接口调用（搜索、UP主作品列表都要）。"""
    ensure_fingerprint()
    for attempt in range(2):
        raw = fetch(f"{API}{path}?{wbi_sign(params)}")
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            die(f"返回非 JSON（疑似被拦截）: {raw[:160]}")
        if obj.get("code") in (-352, -403):  # 签名过期/风控
            wbi_key(force=True)
            time.sleep(1.0)
            continue
        if obj.get("code") != 0:
            die(f"接口 {path} code={obj.get('code')} message={obj.get('message')}")
        data = obj["data"]
        if isinstance(data, dict) and set(data.keys()) == {"v_voucher"}:
            die(
                "触发风控（只返回 v_voucher）：搜索/空间类接口需要登录态，加指纹也没用。"
                "可用替代：WebFetch 直接打开 https://search.bilibili.com/all?keyword=关键词 "
                "（页面是服务端渲染，能读到 UP主、UID、BV号、播放量）；"
                "拿到 BV 号后 info / sheet / download 全部正常。"
            )
        return data
    die(f"接口 {path} 连续失败（wbi 签名或风控问题）")


def die(msg, code=1):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False, indent=2))
    sys.exit(code)


def fetch(url, binary=False, retries=2, timeout=25):
    """GET with UA+Referer. Returns bytes(str) or bytes."""
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if binary:
                return data
            return data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {url}"
            if e.code in (403, 412):
                die(
                    f"{last} — 触发风控。搜索类接口必须 wbi 签名，请改用 WebSearch 或浏览器自动化。"
                )
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e} — {url}"
        time.sleep(1.2 * (i + 1))
    die(f"请求失败: {last}")


def api(path, **params):
    ensure_fingerprint()
    q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    raw = fetch(f"{API}{path}?{q}" if q else f"{API}{path}")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        die(f"返回非 JSON（很可能被反爬拦截）: {raw[:160]}")
    if obj.get("code") != 0:
        die(f"接口 {path} 返回 code={obj.get('code')} message={obj.get('message')}")
    return obj["data"]


import urllib.parse  # noqa: E402  (used in api())


def bv_to_aid(bvid):
    return api("/x/web-interface/view", bvid=bvid)["aid"]


def get_view(bvid):
    return api("/x/web-interface/view", bvid=bvid)


def get_cid(bvid, page=1):
    pages = api("/x/player/pagelist", bvid=bvid)
    page = max(1, min(page, len(pages)))
    return pages[page - 1]["cid"], pages


def fmt_dur(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


# ---------------- subcommands ----------------


def cmd_probe(args):
    out = {"ok": True, "checks": {}}

    # Pillow
    try:
        from PIL import Image  # noqa: F401

        out["checks"]["pillow"] = {"ok": True}
    except ImportError:
        out["checks"]["pillow"] = {
            "ok": False,
            "hint": "本解释器没有 Pillow。用 python3 运行。",
        }

    # ffmpeg
    try:
        p = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=10, text=True
        )
        ok = p.returncode == 0
        out["checks"]["ffmpeg"] = {
            "ok": ok,
            "detail": (p.stdout.splitlines() or [""])[0][:80] if ok else (p.stderr.strip().splitlines() or [""])[-1][:160],
        }
        if not ok:
            out["checks"]["ffmpeg"]["hint"] = "ffmpeg 不可用（常见原因：缺 libxcb.1.dylib）。用 sheet 子命令抽帧不需要 ffmpeg。"
    except FileNotFoundError:
        out["checks"]["ffmpeg"] = {"ok": False, "hint": "未安装 ffmpeg"}
    except Exception as e:  # noqa: BLE001
        out["checks"]["ffmpeg"] = {"ok": False, "detail": str(e)[:160]}

    # API
    try:
        v = api("/x/web-interface/view", bvid="BV1GJ411x7h7")
        out["checks"]["api_view"] = {"ok": True, "sample": v["title"][:40]}
    except SystemExit:
        out["checks"]["api_view"] = {"ok": False}
        out["ok"] = False

    # videoshot
    try:
        s = api(
            "/x/player/videoshot",
            bvid="BV1GJ411x7h7",
            cid=get_cid("BV1GJ411x7h7")[0],
            index=1,
        )
        out["checks"]["api_videoshot"] = {
            "ok": True,
            "frames": len(s.get("index", [])),
            "sheets": len(s.get("image", [])),
        }
    except SystemExit:
        out["checks"]["api_videoshot"] = {"ok": False}

    return out


def cmd_info(args):
    v = get_view(args.bvid)
    pages = v.get("pages") or api("/x/player/pagelist", bvid=args.bvid)
    return {
        "ok": True,
        "bvid": v["bvid"],
        "aid": v["aid"],
        "title": v["title"],
        "owner": v["owner"]["name"],
        "duration": v["duration"],
        "duration_text": fmt_dur(v["duration"]),
        "pubdate": time.strftime("%Y-%m-%d", time.localtime(v["pubdate"])),
        "stat": {k: v["stat"].get(k) for k in ("view", "like", "coin", "favorite", "danmaku", "reply")},
        "desc": (v.get("desc") or "").strip()[:1200],
        "cover": "https:" + v["pic"] if v["pic"].startswith("//") else v["pic"],
        "pages": [
            {"page": p["page"], "cid": p["cid"], "title": p["part"], "duration": p["duration"]}
            for p in pages
        ],
    }


def cmd_sheet(args):
    """核心：videoshot 雪碧图 → 按秒裁帧"""
    info = get_view(args.bvid)
    duration = info["duration"]
    cid, pages = get_cid(args.bvid, args.page)

    shot = None
    for attempt in range(4):
        shot = api("/x/player/videoshot", bvid=args.bvid, cid=cid, index=1)
        if shot.get("index"):
            break
        # 空返回多是节点抖动：换一个新指纹再试
        _BUV["done"] = False
        HEADERS.pop("Cookie", None)
        time.sleep(1.2 * (attempt + 1))
    cols = int(shot.get("img_x_len") or 10)
    rows = int(shot.get("img_y_len") or 10)
    fw = int(shot.get("img_x_size") or 480)
    fh = int(shot.get("img_y_size") or 270)
    secs = shot.get("index") or []
    images = shot.get("image") or []
    estimated = False
    if images and not secs:
        # 降级：拿得到图但拿不到时间轴，按等间隔估算（多数稿件是匀速取样）
        n = cols * rows
        secs = [round(i * duration / max(1, n - 1), 1) for i in range(n)]
        estimated = True
    if not images or not secs:
        die(
            "该视频没有可用的 videoshot 雪碧图（部分番剧/付费稿件关闭了预览图）。"
            "改用 clip 子命令走 ffmpeg 抽帧，或换一个 BV 号。"
        )

    per_sheet = cols * rows

    # 决定要哪几帧
    if args.times:
        targets = [float(x) for x in str(args.times).replace(" ", "").split(",") if x]
    elif args.all:
        targets = None
    else:
        step = args.every or max(1, duration // 12)
        targets = list(range(0, duration, step))

    # 需要哪里就下哪里（按帧号 -> sheet 索引）
    def pick(t):
        return min(range(len(secs)), key=lambda i: abs(secs[i] - t))

    need_frames = list(range(len(secs))) if targets is None else [pick(t) for t in targets]
    need_sheets = sorted({n // per_sheet for n in need_frames})

    outdir = args.out or os.path.join(
        os.getcwd(), "bili_frames", re.sub(r"[^\w\-]", "_", args.bvid)
    )
    os.makedirs(outdir, exist_ok=True)

    try:
        from PIL import Image
    except ImportError:
        die(
            "缺少 Pillow。用 python3 运行本脚本。"
        )

    cache = {}
    for si in need_sheets:
        if si >= len(images):
            continue
        url = images[si]
        if url.startswith("//"):
            url = "https:" + url
        raw_path = os.path.join(outdir, f"_sprite_{si:03d}.jpg")
        if not (os.path.exists(raw_path) and os.path.getsize(raw_path) > 1024):
            with open(raw_path, "wb") as f:
                f.write(fetch(url, binary=True))
        cache[si] = Image.open(raw_path).convert("RGB")

    written = []
    pairs = (
        list(zip(need_frames, range(len(need_frames))))
        if targets is None
        else [(n, i) for i, n in enumerate(need_frames)]
    )
    for n, i in pairs:
        if n >= len(secs):
            continue
        si, within = n // per_sheet, n % per_sheet
        if si not in cache:
            continue
        col, row = within % cols, within // cols
        box = (col * fw, row * fh, col * fw + fw, row * fh + fh)
        # 大图裁完再放大一点，便于读字幕/UI；--scale 控制
        img = cache[si].crop(box)
        if args.scale and args.scale != 1:
            img = img.resize(
                (int(fw * args.scale), int(fh * args.scale)), Image.LANCZOS
            )
        sec = secs[n]
        name = f"t{int(sec):04d}.jpg"
        img.save(os.path.join(outdir, name), quality=90)
        written.append({"sec": sec, "file": os.path.join(outdir, name)})

    manifest = {
        "ok": True,
        "bvid": args.bvid,
        "title": info["title"],
        "owner": info["owner"]["name"],
        "duration": duration,
        "page": args.page,
        "cid": cid,
        "sprite": {"cols": cols, "rows": rows, "frame": [fw, fh], "sheets": len(images), "total_frames": len(secs)},
        "frame_interval_sec": (
            sorted(
                b - a for a, b in zip(secs, secs[1:]) if b > a
            )[len([1 for a, b in zip(secs, secs[1:]) if b > a]) // 2]
            if len(secs) > 1
            else None
        ),
        "coverage": f"每 {round(duration / max(1, len(secs)), 1)}s 一帧" if secs else None,
        "frames": written,
        "outdir": outdir,
        "timeline_estimated": estimated,
        "tip": "用 Read 工具直接读 frames[].file 里的 jpg 就能看到画面（含硬字幕）。",
    }
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def cmd_download(args):
    cid, _ = get_cid(args.bvid, args.page)
    qn = {"360": 16, "480": 32, "720": 64}.get(str(args.qn), 16)
    d = api(
        "/x/player/playurl",
        bvid=args.bvid,
        cid=cid,
        qn=qn,
        fnval=1,
        platform="html5",
    )
    durls = d.get("durl") or []
    if not durls:
        die("拿不到 durl（可能该稿件限制直链）。")
    out = args.out or f"{args.bvid}.mp4"
    parts = []
    if len(durls) == 1:
        with open(out, "wb") as f:
            f.write(fetch(durls[0]["url"], binary=True, timeout=60, retries=3))
        parts.append(out)
    else:
        base = os.path.splitext(out)[0]
        for i, seg in enumerate(durls, 1):
            p = f"{base}_part{i:02d}.mp4"
            with open(p, "wb") as f:
                f.write(fetch(seg["url"], binary=True, timeout=60, retries=3))
            parts.append(p)
    return {
        "ok": True,
        "quality": d.get("quality"),
        "files": parts,
        "size_mb": round(sum(os.path.getsize(p) for p in parts) / 1048576, 1),
        "note": "免登录通常只有 360P/480P。高清需登录 cookie，本工具不接管账号。",
    }


def cmd_clip(args):
    cid, _ = get_cid(args.bvid, args.page)
    d = api("/x/player/playurl", bvid=args.bvid, cid=cid, qn=64, fnval=1, platform="html5")
    url = (d.get("durl") or [{}])[0].get("url")
    if not url:
        die("拿不到直链。")
    out = args.out or f"{args.bvid}_clip.mp4"
    span = f"{args.start}-{args.end}" if args.end else str(args.start)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-headers", "Referer: https://www.bilibili.com\r\n",
        "-ss", str(args.start), "-i", url, "-t", str(max(1, (args.end or args.start + 20) - args.start)),
        "-c", "copy", "-y", out,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        die(f"调用 ffmpeg 失败: {e}")
    if p.returncode != 0:
        err = (p.stderr or "").strip()
        hint = ""
        if "libxcb" in err or "dyld" in err:
            hint = "ffmpeg 本身坏了（缺动态库），先 brew reinstall ffmpeg；或改用 sheet 子命令抽帧，不需要 ffmpeg。"
        die(f"ffmpeg 退出码 {p.returncode}: {err[-400:]} {hint}")
    return {"ok": True, "file": os.path.abspath(out), "cli": " ".join(cmd[:6]) + " ...", "span": span}


def _clean(s):
    return re.sub(r"<[^>]+>", "", s or "").replace("&quot;", '"').strip()


def cmd_search(args):
    data = wbi_api(
        "/x/web-interface/wbi/search/type",
        search_type="video",
        keyword=args.keyword,
        page=args.page,
    )
    items = data.get("result") or []
    return {
        "ok": True,
        "keyword": args.keyword,
        "results": [
            {
                "bvid": it.get("bvid"),
                "title": _clean(it.get("title")),
                "author": it.get("author"),
                "mid": it.get("mid"),
                "play": it.get("play"),
                "danmaku": it.get("video_review"),
                "favorite": it.get("favorites"),
                "duration": it.get("duration"),
                "pubdate": time.strftime(
                    "%Y-%m-%d", time.localtime(it.get("pubdate", 0))
                ),
            }
            for it in items[: args.limit]
        ],
    }


def cmd_up(args):
    data = wbi_api(
        "/x/web-interface/wbi/search/type",
        search_type="bili_user",
        keyword=args.keyword,
        page=1,
    )
    items = data.get("result") or []
    return {
        "ok": True,
        "keyword": args.keyword,
        "users": [
            {
                "mid": it.get("mid"),
                "uname": _clean(it.get("uname")),
                "fans": it.get("fans"),
                "videos": it.get("videos"),
                "level": it.get("level"),
                "sign": _clean(it.get("usign"))[:120],
                "space": f"https://space.bilibili.com/{it.get('mid')}",
            }
            for it in items[: args.limit]
        ],
    }


def cmd_videos(args):
    data = wbi_api(
        "/x/space/wbi/arc/search",
        mid=args.mid,
        ps=args.limit,
        pn=args.page,
        order=args.order,
        platform="web",
    )
    vlist = ((data.get("list") or {}).get("vlist")) or []
    return {
        "ok": True,
        "mid": args.mid,
        "order": args.order,
        "total": (data.get("page") or {}).get("count"),
        "videos": [
            {
                "bvid": v.get("bvid"),
                "title": v.get("title"),
                "play": v.get("play"),
                "length": v.get("length"),
                "created": time.strftime("%Y-%m-%d", time.localtime(v.get("created", 0))),
                "desc": (v.get("description") or "")[:100],
            }
            for v in vlist
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="B 站拉片工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe")

    p = sub.add_parser("info")
    p.add_argument("bvid")

    p = sub.add_parser("sheet")
    p.add_argument("bvid")
    p.add_argument("--times", help="逗号分隔的秒数，如 12,74,293")
    p.add_argument("--every", type=int, help="等间隔取样秒数")
    p.add_argument("--all", action="store_true", help="导出全部预览帧")
    p.add_argument("--page", type=int, default=1, help="第几个分P，默认 1")
    p.add_argument("--out", help="输出目录")
    p.add_argument("--scale", type=float, default=1.0, help="裁剪后放大倍数，读字幕用 1.8 更清楚")

    p = sub.add_parser("download")
    p.add_argument("bvid")
    p.add_argument("--out")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--qn", default="360", choices=["360", "480", "720"])

    p = sub.add_parser("clip")
    p.add_argument("bvid")
    p.add_argument("--from", dest="start", type=float, required=True)
    p.add_argument("--to", dest="end", type=float)
    p.add_argument("--out")
    p.add_argument("--page", type=int, default=1)

    p = sub.add_parser("search")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--page", type=int, default=1)

    p = sub.add_parser("up")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=8)

    p = sub.add_parser("videos")
    p.add_argument("mid")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--order", default="pubdate", choices=["pubdate", "click", "stow"])

    args = ap.parse_args()
    fn = {
        "probe": cmd_probe,
        "info": cmd_info,
        "sheet": cmd_sheet,
        "download": cmd_download,
        "clip": cmd_clip,
        "search": cmd_search,
        "up": cmd_up,
        "videos": cmd_videos,
    }[args.cmd]
    res = fn(args)
    if args.cmd == "info" and not args.__dict__.get("json_only", False):
        pass
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
