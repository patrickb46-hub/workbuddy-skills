#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imgtool —— 试卷图片处理内核（AI 版命令行入口）

用途
    把 HEIC / HEIF 等「读不了的格式」转成 JPG / PNG，并提供裁切、旋转、缩放等
    基础图像处理能力，全部在本机完成，**不联网、不依赖任何外部服务**。

引擎分工（自动选择，不需要使用者关心）
    · Pillow —— 处理它认识的格式（JPG / PNG / TIFF / WebP / BMP / GIF / AVIF…）
    · sips  —— macOS 自带系统工具，负责 Pillow 读不了的格式（HEIC / HEIF 等）
    两者都没有时，工具会明确报错并提示；不会静默失败。

调用约定（写给 AI 助手看）
    1. 解释器固定用带 Pillow 的那个：
       python3
    2. 所有子命令 **默认输出一行 JSON**，结构固定含 "ok" 字段，失败时 "ok": false
       并附 "error"；成功时结果放在 "outputs" / "files" 等字段里。
    3. 加 --human 可以换成给人看的中文文本。
    4. 永不覆盖原图：输出撞名会自动加 -2 / -3 后缀，返回值里给的是真实落盘路径。

例子
    imgtool.py deps
    imgtool.py prep ~/Desktop/国庆假期/数学/周末4 -o /tmp/read周末4   # 一条命令：扫描+转码+整页副本
    imgtool.py grid /tmp/read周末4/IMG_4154.jpg -o /tmp/g.jpg       # 叠加百分比网格，用来量坐标
    imgtool.py lines /tmp/read周末4/IMG_4154.jpg -o /tmp/l.jpg      # 自动列出文字行区间(y/比例)
    imgtool.py strip /tmp/read周末4/IMG_4155.jpg --n 5 --max 1800   # 一条长图切 N 条，一次全读
    imgtool.py crop a.jpg -o q16.jpg --rel 0.03,0.26,1.0,0.32 --scale 3
    imgtool.py scan ~/Desktop/国庆假期/数学/周末4 --recursive
    imgtool.py convert ~/Desktop/国庆假期/数学/周末4/HEIC        # 输出到同级 JPG/
    imgtool.py readcopy ~/Desktop/国庆假期/数学/周末4 -o /tmp/read1 --max 2000
    imgtool.py rotate a.jpg -o b.jpg --deg 90
    imgtool.py resize a.jpg -o c.jpg --max 2000
    imgtool.py clean --workspaces                              # 清掉工具自己建的临时工作区
    imgtool.py figcheck 全解.html --src JPG/IMG_4154.jpg --map "1=0.1,0.2,0.95,0.55"
                                                              # 数学图复检：重绘 ↔ 原题并排对照
    imgtool.py gui                                            # 启动图形界面

版本 1.2.0 · 本机离线运行

版本记录
    1.0.0  转码 / 裁切 / 旋转 / 缩放 / 翻转 / 图形界面
    1.1.0  按一次真实全解任务（4 张 HEIC、12 次 crop）里暴露的痛点补的：
           · prep / grid / lines / strip 四个定位命令 —— 治「反复猜相对坐标」
           · crop --to-width —— 治「全宽条带用 --scale 3 放大成 6000px 白放大」
           · readcopy 默认 1500 → 2000，并返回 suggest_max —— 治「1500 看不清、整批重跑」
           · HEIC 解码缓存 —— 同一张反复裁不再重复解码（实测 4.6s → 1.4s）
           · clean + 工作区标记 —— 收工能一键清干净，且只敢删自己建的目录
           · --rel / --box 给混了会回报 warnings，不再静默算错
    1.2.0  figcheck —— 治「图画完没人核对」：抽出每幅内联 SVG 单独渲染，
           与原题对应裁块并排拼成对照图；同时量化字母标注、虚线处数、墨迹占比，
           让「漏连一条线 / 少画一个直角标记 / 左右画反」这类数值自检抓不到的错误，
           变成肉眼一比就能发现的问题。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "1.2.0"

# ---------------------------------------------------------------- 基础工具

#: Pillow 认识的常见格式（小写扩展名）
PILLOW_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".webp", ".bmp",
    ".gif", ".ppm", ".pgm", ".pbm", ".jp2", ".j2k", ".avif", ".ico", ".dds",
}
#: 需要借系统工具（sips）才能读的格式
SYSTEM_ONLY_EXTS = {".heic", ".heif", ".hif", ".heics", ".avifs", ".jxl", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".psd"}
#: 扫描时视为「图片」的全部扩展名
IMAGE_EXTS = PILLOW_EXTS | SYSTEM_ONLY_EXTS

FORMAT_ALIAS = {
    "jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp",
    "tif": "tiff", "tiff": "tiff", "bmp": "bmp", "gif": "gif", "heic": "heic",
}
EXT_OF_FORMAT = {
    "jpeg": ".jpg", "png": ".png", "webp": ".webp",
    "tiff": ".tif", "bmp": ".bmp", "gif": ".gif", "heic": ".heic",
}


class ToolError(Exception):
    """可预期的失败：会以 JSON 形式报出去，退出码 2。"""


# --- 工作区与解码缓存 -----------------------------------------------------
#
# 「工作区」= 工具自己创建的临时输出目录，里面会放一个 .imgtool_workspace 标记。
# 只有带标记的目录才允许被 clean 删除 —— 这样 clean 永远不会碰到用户的真实文件。

WORKSPACE_MARK = ".imgtool_workspace"
CACHE_DIR = Path(os.environ.get("IMGTOOL_CACHE")
                 or (Path.home() / "Library" / "Caches" / "imgtool"))
CACHE_LIMIT_BYTES = 512 * 1024 * 1024      # 缓存上限，超了按最旧淘汰


def tmp_root() -> Path:
    """工具的临时根目录（跟着系统 TMPDIR 走，容器/沙箱里也不会写错地方）。"""
    return Path(os.environ.get("IMGTOOL_TMP") or tempfile.gettempdir()) / "imgtool"


def new_workspace(name="ws") -> Path:
    """建一个带标记的临时工作区，返回路径。"""
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(name))[:40] or "ws"
    d = tmp_root() / f"{time.strftime('%m%d-%H%M%S')}_{safe}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        (d / WORKSPACE_MARK).write_text(
            json.dumps({"tool": "imgtool", "version": VERSION,
                        "created": time.strftime("%Y-%m-%d %H:%M:%S")},
                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except OSError:
        pass
    return d


def mark_workspace(directory) -> None:
    """把一个已存在的目录标记为工作区（仅当它本来就是空目录或已带标记时）。"""
    d = Path(directory)
    mark = d / WORKSPACE_MARK
    if mark.exists():
        return
    try:
        if any(p.name != mark.name for p in d.iterdir()):
            return                       # 非空目录不动它，避免误标用户的目录
        mark.write_text(json.dumps({"tool": "imgtool", "version": VERSION},
                                   ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass


def iter_workspaces() -> list:
    """列出工具自己建过的工作区。"""
    out = []
    root = tmp_root()
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / WORKSPACE_MARK).exists():
            out.append(d)
    return out


def _dir_size(d: Path) -> int:
    total = 0
    for p in d.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


# --- HEIC 解码缓存 --------------------------------------------------------
# HEIC 走 sips 解码很慢（一张 4000px 的要 1 秒上下），而裁一条带只看一小块、
# 反复裁同一张图时每次都要重新解码。这里按「路径+大小+修改时间」缓存解码结果，
# 同一张 HEIC 第二次起直接读缓存。缓存只在工具自己的缓存目录里，不动原图。

def _cache_key(path: Path) -> str:
    try:
        st = path.stat()
        sig = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        sig = str(path)
    return hashlib.sha1(sig.encode("utf-8", "replace")).hexdigest()[:20]


def _cache_get(path: Path):
    if not HAVE_PILLOW:
        return None
    f = CACHE_DIR / f"{_cache_key(path)}.png"
    if f.exists():
        try:
            im = Image.open(f)
            im.load()
            return im
        except Exception:  # noqa: BLE001
            try:
                f.unlink()
            except OSError:
                pass
    return None


def _cache_put(path: Path, png_path: Path) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dest = CACHE_DIR / f"{_cache_key(path)}.png"
        shutil.move(str(png_path), str(dest))
        _cache_trim()
    except OSError:
        pass


def _cache_trim() -> None:
    """缓存超过上限时，按修改时间从最旧的开始删。"""
    try:
        files = sorted((p for p in CACHE_DIR.glob("*.png")),
                       key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for p in files:
            if total <= CACHE_LIMIT_BYTES:
                break
            total -= p.stat().st_size
            p.unlink()
    except OSError:
        pass


def _cache_info() -> dict:
    try:
        files = list(CACHE_DIR.glob("*.png"))
        return {"dir": str(CACHE_DIR), "count": len(files),
                "bytes": sum(p.stat().st_size for p in files)}
    except OSError:
        return {"dir": str(CACHE_DIR), "count": 0, "bytes": 0}


# --- Pillow / sips 可用性 -------------------------------------------------

try:  # pragma: no cover - 环境相关
    from PIL import Image, ImageOps, ImageFile

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    HAVE_PILLOW = True
    PILLOW_VERSION = getattr(Image, "__version__", "?")
    Image.MAX_IMAGE_PIXELS = None
except Exception:  # noqa: BLE001
    Image = ImageOps = None
    HAVE_PILLOW = False
    PILLOW_VERSION = None

SIPS = shutil.which("sips")
HAVE_SIPS = bool(SIPS)


def caps() -> dict:
    chrome = find_chrome()
    return {
        "ok": True,
        "tool": "imgtool",
        "version": VERSION,
        "python": sys.executable,
        "pillow": {"available": HAVE_PILLOW, "version": PILLOW_VERSION},
        "sips": {"available": HAVE_SIPS, "path": SIPS},
        "browser": {"available": bool(chrome), "path": str(chrome) if chrome else None,
                    "used_by": "figcheck（把内联 SVG 渲染成图）"},
        "can_read": sorted(PILLOW_EXTS | (SYSTEM_ONLY_EXTS if HAVE_SIPS else set())),
        "workspace_root": str(tmp_root()),
        "decode_cache": _cache_info(),
        "engine_note": (
            "HEIC/HEIF 走 sips 解码（结果按 路径+大小+修改时间 缓存，重复裁同一张不再重复解码），"
            "其余格式走 Pillow"
            if (HAVE_SIPS and HAVE_PILLOW)
            else "缺少 Pillow 或 sips，功能受限"
        ),
    }


# --- 路径与命名 -----------------------------------------------------------

_NUM_RE = re.compile(r"(\d+)")


def natkey(text) -> list:
    """自然排序键：IMG_2 排在 IMG_10 前面。"""
    return [int(p) if p.isdigit() else p.lower() for p in _NUM_RE.split(str(text))]


def unique_path(path: Path) -> Path:
    """避免覆盖：撞名时依次尝试 -2 / -3 / …（最多 999 次）。"""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    for i in range(2, 1000):
        cand = parent / f"{stem}-{i}{suffix}"
        if not cand.exists():
            return cand
    raise ToolError(f"输出目录里同名文件过多：{path}")


def norm_exts(raw) -> set:
    if not raw:
        return set()
    out = set()
    for item in (raw if isinstance(raw, (list, tuple, set)) else [raw]):
        for piece in str(item).split(","):
            piece = piece.strip().lower()
            if not piece:
                continue
            out.add(piece if piece.startswith(".") else "." + piece)
    return out


def _collect_images(root: Path, depth) -> list:
    """按目录深度收集文件。depth=1 只看直接子项；2 再下一层；None 不限。"""
    out: list[Path] = []

    def walk(d: Path, left, level=0):
        try:
            entries = sorted(d.iterdir(), key=lambda q: natkey(q.name))
        except (OSError, PermissionError):
            return
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                if e.is_dir():
                    if left is None:
                        walk(e, None, level + 1)
                    elif left > 1:
                        walk(e, left - 1, level + 1)
                elif e.is_file():
                    out.append(e)
            except OSError:
                continue

    walk(root, depth)
    return out


def expand_inputs(items, recursive=False, only=None, skip=None) -> list:
    """把「文件 + 目录」摊平成有序的绝对路径列表。

    目录输入的两条实用规则：
      · 先看直接子项；**一个图片都没有时自动下探一层**（这样 `学科/组名/` 能直接找到
        `HEIC/`、`JPG/` 里的照片，不用非得加 -r）。
      · 加了 --recursive 才不限层级。
    """
    only, skip = norm_exts(only), norm_exts(skip)
    files: list[Path] = []
    for raw in items:
        p = Path(os.path.expanduser(str(raw))).resolve()
        if p.is_dir():
            if recursive:
                found = _collect_images(p, None)
            else:
                found = _collect_images(p, 1)
                if not any(f.suffix.lower() in IMAGE_EXTS for f in found):
                    found = _collect_images(p, 2)
            files.extend(found)
        elif p.is_file():
            files.append(p)
        else:
            raise ToolError(f"路径不存在：{p}")
    keep = []
    for f in files:
        ext = f.suffix.lower()
        if ext in skip:
            continue
        if only and ext not in only:
            continue
        # 目录输入时只留下图片；显式指定的单个文件则一律放行
        if not only and ext not in IMAGE_EXTS:
            continue
        keep.append(f)
    return keep


# --- 读盘：Pillow 优先，sips 兜底 ----------------------------------------

def sips_convert(src, dst, fmt="png", quality=None) -> None:
    if not HAVE_SIPS:
        raise ToolError(
            "系统没有 sips，且 Pillow 读不了这个格式。"
            "请在 macOS 上运行，或安装 pillow-heif"
        )
    cmd = [SIPS, "-s", "format", fmt]
    if quality is not None:
        cmd += ["-s", "formatOptions", str(int(quality))]
    cmd += [str(src), "--out", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not Path(dst).exists():
        raise ToolError(
            f"sips 转换失败（{Path(src).name}）：{(proc.stderr or proc.stdout).strip()[:300]}"
        )


def sips_probe(path) -> dict:
    """用 sips 问一下尺寸/格式，用于 Pillow 读不了的文件。"""
    if not HAVE_SIPS:
        return {}
    try:
        proc = subprocess.run(
            [SIPS, "-g", "pixelWidth", "-g", "pixelHeight", "-g", "format", str(path)],
            capture_output=True, text=True,
        )
        info = {}
        for line in proc.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
        return {
            "w": int(info["pixelWidth"]) if info.get("pixelWidth", "").isdigit() else None,
            "h": int(info["pixelHeight"]) if info.get("pixelHeight", "").isdigit() else None,
            "format": info.get("format") or None,
        }
    except Exception:  # noqa: BLE001
        return {}


def load_image(path, respect_orientation=True, use_cache=True):
    """读一张图，返回 PIL.Image（已按 EXIF 方向摆正）。

    Pillow 读不了就借 sips 转成 PNG —— HEIC 走的就是这条路。
    转码结果会按「路径+大小+修改时间」缓存，重复处理同一张 HEIC 不再重复解码。
    """
    if not HAVE_PILLOW:
        raise ToolError("缺少 Pillow，无法处理图片")
    path = Path(path)
    engine = "pillow"
    try:
        im = Image.open(path)
        im.load()
    except Exception:  # noqa: BLE001
        im = _cache_get(path) if use_cache else None
        if im is None:
            tmp_holder = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_holder.close()
            tmp = Path(tmp_holder.name)
            try:
                sips_convert(path, tmp, "png")
            except ToolError:
                tmp.unlink(missing_ok=True)
                raise
            try:
                im = Image.open(tmp)
                im.load()
            except Exception as exc:  # noqa: BLE001
                tmp.unlink(missing_ok=True)
                raise ToolError(f"连 sips 都读不了这个文件：{path.name}（{exc}）") from exc
            if use_cache:
                _cache_put(path, tmp)
            else:
                tmp.unlink(missing_ok=True)
        engine = "sips"
    if respect_orientation:
        try:
            fixed = ImageOps.exif_transpose(im)
            if fixed is not None:
                im = fixed
        except Exception:  # noqa: BLE001
            pass
    im.info["_imgtool_engine"] = engine
    return im


#: 可以直接交给读图工具（视觉模型）看的格式 —— 其它都得先转码
AI_READABLE_FORMATS = {"jpeg", "jpg", "png", "webp", "gif"}


def suggest_max(w, h) -> dict:
    """按经验给出两档阅读尺寸，省得「先 1600 看不清、再重跑 4000」跑两遍。

    overview —— 整页通读、先看版式和有哪些题，够了。
    detail   —— 要看清小字、公式、上下标时用这一档。
    """
    longest = max(int(w or 0), int(h or 0))
    if longest <= 0:
        return {"overview": 2000, "detail": 3000, "note": "尺寸未知，用默认值"}
    if longest <= 2400:
        return {"overview": longest, "detail": longest,
                "note": "原图本身不大，一档就够；再放大只会变糊"}
    return {"overview": 2000, "detail": min(longest, 3400),
            "note": "整页通读用 overview；小字/公式看不清时按 detail 重跑 readcopy 或 prep"}


def describe(path) -> dict:
    """描述一个文件：什么格式、多大、工具能不能解码、要不要先转码。

    readable      —— 本工具能否解码（HEIC 借 sips 也算能）
    needs_convert —— 是否**不能**直接喂给读图工具、建议先转 JPG/PNG
    """
    path = Path(path)
    rec = {
        "path": str(path),
        "name": path.name,
        "ext": path.suffix.lower(),
        "bytes": path.stat().st_size if path.exists() else None,
        "readable": False,
        "engine": None,
        "w": None,
        "h": None,
        "format": None,
        "needs_convert": True,
    }
    if not path.exists():
        rec["error"] = "文件不存在"
        return rec
    try:
        im = Image.open(path)
        rec.update(readable=True, engine="pillow", w=im.width, h=im.height,
                   format=(im.format or "").lower() or None)
        im.close()
    except Exception:  # noqa: BLE001
        probe = sips_probe(path)
        if probe.get("w"):
            rec.update(readable=True, engine="sips", w=probe.get("w"), h=probe.get("h"),
                       format=probe.get("format"))
    fmt = (rec.get("format") or rec["ext"].lstrip(".")).lower()
    rec["needs_convert"] = fmt not in AI_READABLE_FORMATS
    if rec.get("w"):
        rec["suggest_max"] = suggest_max(rec["w"], rec["h"])
    return rec


# --- 图像操作 -------------------------------------------------------------

def op_rotate(im, deg, fill="white"):
    """顺时针旋转 deg 度。

    90 的整数倍走无损路径；其它角度会自动扩大画布并用 fill 补底，不留黑角
    （试卷拍歪了微调 2° 这种场景就靠它）。
    """
    deg = float(deg) % 360
    if abs(deg) < 1e-9:
        return im
    if abs(deg % 90) < 1e-9:
        return im.rotate(-deg, expand=True)  # 正值 = 顺时针，无插值损失
    bg = (255, 255, 255) if fill == "white" else (0, 0, 0)
    return _rot_expand(im, deg, bg)


def _rot_expand(im, deg, bg):
    """任意角度旋转 + 自动扩画布（fill 补底）。"""
    import math
    from PIL import Image as _I

    src = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
    w, h = src.size
    rad = math.radians(deg)
    nw = abs(w * math.cos(rad)) + abs(h * math.sin(rad))
    nh = abs(w * math.sin(rad)) + abs(h * math.cos(rad))
    mode = "RGBA" if src.mode == "RGBA" else "RGB"
    fill = bg + ((255,) if mode == "RGBA" else ())
    canvas = _I.new(mode, (max(1, int(round(nw))), max(1, int(round(nh)))), fill)
    rot = src.rotate(-deg, resample=_I.BICUBIC, expand=True, fillcolor=fill)
    canvas.paste(rot, ((canvas.width - rot.width) // 2,
                       (canvas.height - rot.height) // 2),
                 rot if rot.mode == "RGBA" else None)
    return canvas


def op_flip(im, how):
    if how == "horizontal":
        return ImageOps.mirror(im)
    if how == "vertical":
        return ImageOps.flip(im)
    raise ToolError("flip 只能是 horizontal 或 vertical")


def resolve_box(im, box=None, rel=None, report=None) -> tuple:
    """裁切坐标。box 用像素 l,t,w,h；rel 用比例 x0,y0,x1,y1（0–1）。

    两种参数都接受字符串 "a,b,c,d" 或序列 [a,b,c,d]。
    **--rel 就该给 0–1 的小数，--box 就该给像素**；真给混了会照宽容规则处理，
    但会把提示塞进 report["warnings"]，免得算错了没人知道。
    """
    def _vals(v, what):
        if isinstance(v, (list, tuple)):
            out = [float(x) for x in v]
        else:
            out = [float(x) for x in str(v).replace(" ", "").split(",") if x != ""]
        if len(out) != 4:
            raise ToolError(f"{what} 需要 4 个数")
        return out

    def _note(msg):
        if report is not None:
            report.setdefault("warnings", []).append(msg)

    w, h = im.size
    if box:
        l, t, bw, bh = _vals(box, "--box")
        if max(abs(l), abs(t), abs(bw), abs(bh)) <= 1.5:
            _note(f"--box 收到 0–1 的小数（{box}），像比例不像像素；按比例裁请改用 --rel")
        r, b = l + bw, t + bh
    elif rel:
        x0, y0, x1, y1 = _vals(rel, "--rel")
        if max(abs(v) for v in (x0, y0, x1, y1)) <= 1.5:      # 写成了比例
            l, t, r, b = x0 * w, y0 * h, x1 * w, y1 * h
            if not all(-0.01 <= v <= 1.01 for v in (x0, y0, x1, y1)):
                _note(f"--rel 里有超出 0–1 的值（{rel}），已按像素处理")
                l, t, r, b = x0, y0, x1, y1
        else:                                                 # 给的是像素
            l, t, r, b = x0, y0, x1, y1
            _note(f"--rel 收到像素值（{rel}）；这种写法建议改用 --box")
    else:
        raise ToolError("裁切需要 --box 或 --rel")
    l, t = max(0, min(l, r)), max(0, min(t, b))
    r, b = min(w, max(l, r)), min(h, max(t, b))
    if r - l < 1 or b - t < 1:
        hint = ""
        if report and report.get("warnings"):
            hint = "；提示：" + "；".join(report["warnings"])
        raise ToolError(f"裁切区域为空（原图 {w}×{h}）{hint}")
    if report is not None:
        report["box_px"] = [int(round(l)), int(round(t)), int(round(r)), int(round(b))]
        if w and h:
            report["box_rel"] = [round(l / w, 4), round(t / h, 4),
                                 round(r / w, 4), round(b / h, 4)]
    return (int(round(l)), int(round(t)), int(round(r)), int(round(b)))


def op_crop(im, box):
    return im.crop(box)


def op_resize(im, max_side=None, width=None, height=None, pct=None,
              no_upscale=True, box_mode="lanczos"):
    from PIL import Image as _I
    resample = {"lanczos": _I.LANCZOS, "bicubic": _I.BICUBIC,
                "nearest": _I.NEAREST, "bilinear": _I.BILINEAR}.get(box_mode, _I.LANCZOS)
    w, h = im.size
    if pct:
        tw, th = max(1, round(w * float(pct) / 100)), max(1, round(h * float(pct) / 100))
    elif max_side:
        m = float(max_side)
        scale = m / max(w, h)
        if scale >= 1 and no_upscale:
            return im
        tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    elif width and height:
        tw, th = int(width), int(height)
    elif width:
        tw, th = int(width), max(1, round(h * int(width) / w))
    elif height:
        tw, th = max(1, round(w * int(height) / h)), int(height)
    else:
        return im
    if (tw, th) == (w, h):
        return im
    return im.resize((tw, th), resample)


def op_autolevel(im, cutoff=0.5):
    """轻度自动对比度（试卷照片发灰时很有用）。"""
    try:
        from PIL import Image as _I
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        return ImageOps.autocontrast(im, cutoff=cutoff)
    except Exception:  # noqa: BLE001
        return im


def save_image(im, out_path, fmt=None, quality=92, force=False, bg="white") -> dict:
    out_path = Path(out_path).expanduser()
    fmt = FORMAT_ALIAS.get((fmt or out_path.suffix.lstrip(".")).lower(), None)
    if fmt is None:
        raise ToolError(f"不认识的输出格式：{fmt or out_path.suffix}")
    if not out_path.suffix:
        out_path = out_path.with_suffix(EXT_OF_FORMAT[fmt])
    out_path = out_path if force else unique_path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    im2 = im
    if fmt in ("jpeg", "bmp"):
        if im.mode in ("RGBA", "LA", "P"):
            flat = Image.new("RGB", im.size, bg)
            src = im.convert("RGBA")
            flat.paste(src, (0, 0), src)
            im2 = flat
        elif im.mode != "RGB":
            im2 = im.convert("RGB")
        kwargs = {"quality": int(quality), "optimize": True, "progressive": True}
    elif fmt == "png":
        if im.mode == "P":
            im2 = im.convert("RGBA") if "transparency" in im.info else im.convert("RGB")
        kwargs = {"optimize": True}
    elif fmt == "webp":
        kwargs = {"quality": int(quality), "method": 5}
    elif fmt == "tiff":
        kwargs = {"compression": "tiff_lzw"}
    im2.save(out_path, **kwargs)
    return {
        "path": str(out_path),
        "bytes": out_path.stat().st_size,
        "w": im2.width,
        "h": im2.height,
        "format": fmt,
    }


# --- 处理流水线 -----------------------------------------------------------

def apply_ops(im, ops: dict):
    """按固定顺序施加工序：翻转 → 旋转 → 裁切 → 缩放 → 增强。"""
    log = []
    if ops.get("flip"):
        im = op_flip(im, ops["flip"])
        log.append(f"flip={ops['flip']}")
    if ops.get("rotate"):
        im = op_rotate(im, ops["rotate"], ops.get("fill", "white"))
        log.append(f"rotate={ops['rotate']}")
    if ops.get("box") or ops.get("rel"):
        report = {}
        box = resolve_box(im, ops.get("box"), ops.get("rel"), report=report)
        im = op_crop(im, box)
        log.append("crop=%d,%d,%d,%d" % box)
        log.append("crop_rel=%.4f,%.4f,%.4f,%.4f" % tuple(
            report.get("box_rel") or (0, 0, 0, 0)))
        for wmsg in report.get("warnings", []):
            log.append("warn: " + wmsg)
    if any(ops.get(k) for k in ("max", "w", "h", "pct")):
        im = op_resize(im, max_side=ops.get("max"), width=ops.get("w"),
                       height=ops.get("h"), pct=ops.get("pct"),
                       no_upscale=not ops.get("allow_upscale"),
                       box_mode=ops.get("resample", "lanczos"))
        log.append(f"resize={im.width}x{im.height}")
    if ops.get("autolevel"):
        im = op_autolevel(im)
        log.append("autolevel")
    return im, log


def process_one(src, out_path, ops=None, fmt=None, quality=92, force=False,
                no_cache=False) -> dict:
    """单文件全流程：读 → 加工 → 写。原图只读，不会被改动。"""
    ops = dict(ops or {})
    src = Path(src)
    im = load_image(src, respect_orientation=not ops.get("no_orient"),
                    use_cache=not no_cache)
    before = im.size
    engine = im.info.get("_imgtool_engine", "pillow")
    im, log = apply_ops(im, ops)
    fmt = fmt or FORMAT_ALIAS.get((ops.get("to") or Path(out_path).suffix.lstrip(".")).lower(), None)
    info = save_image(im, out_path, fmt=fmt, quality=quality, force=force)
    tmp = im.info.get("_imgtool_tmp")
    if tmp:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    warns = [x[len("warn: "):] for x in log if x.startswith("warn: ")]
    info.update({
        "src": str(src),
        "engine": engine,
        "in": {"w": before[0], "h": before[1]},
        "ops": log,
        "readback": info["path"],
    })
    if warns:
        info["warnings"] = warns
    return info


# --- 输出目录规则 ---------------------------------------------------------

JUNK_DIR_NAMES = {"heic", "heif", "hif", "原图", "照片", "originals", "raw"}


def default_outdir(src: Path, base_input: Path, mode="auto", outdir=None, subdir="JPG") -> Path:
    """决定输出到哪儿（原图永不覆盖）。

    mode=dir     用 outdir
    mode=alongside  放原图旁边
    mode=auto    目录输入时：名为 HEIC 之类的目录 → 同级 JPG/；否则该目录下 JPG/
    """
    if mode == "dir":
        if not outdir:
            raise ToolError("--outdir 需要给一个目录")
        return Path(outdir).expanduser().resolve()
    if mode == "alongside":
        return src.parent
    if base_input.is_dir() and base_input.resolve() != src.resolve():
        d = base_input.resolve()
        return (d.parent / subdir) if d.name.lower() in JUNK_DIR_NAMES else (d / subdir)
    return src.parent


# --- 各子命令实现 ---------------------------------------------------------

def cmd_deps(args) -> dict:
    return caps()


def cmd_info(args) -> dict:
    files = expand_inputs(args.paths, recursive=False, only=args.only or None)
    if not files:
        files = [Path(os.path.expanduser(p)).resolve() for p in args.paths]
    recs = [describe(f) for f in files]
    return {"ok": True, "files": recs, "readable": sum(1 for r in recs if r.get("readable")),
            "need_convert": [r["path"] for r in recs if not r.get("readable")]}


def cmd_scan(args) -> dict:
    files = expand_inputs([args.path], recursive=args.recursive,
                          only=args.only or None, skip=args.skip or None)
    recs = [describe(f) for f in files]
    return {
        "ok": True,
        "dir": str(Path(args.path).expanduser().resolve()),
        "count": len(recs),
        "ordered": [r["path"] for r in recs],          # 自然序，可直接当页序用
        "need_convert": [r["path"] for r in recs if r.get("needs_convert")],
        "files": recs,
    }


def cmd_readcopy(args) -> dict:
    """生成阅读副本：HEIC 自动转码 + 统一缩到 --max 像素宽，输出可直接喂给读图工具。"""
    files = expand_inputs(args.paths, recursive=args.recursive,
                          only=args.only or None, skip=args.skip or None)
    if not files:
        raise ToolError("没有找到任何图片")
    outdir = Path(os.path.expanduser(args.outdir)).resolve() if args.outdir else \
        new_workspace(f"read_{files[0].parent.name}")
    outdir.mkdir(parents=True, exist_ok=True)
    results, sugg = [], {}
    for f in files:
        try:
            info = process_one(f, outdir / (f.stem + ".jpg"),
                               ops={"max": args.max, "autolevel": args.autolevel},
                               fmt="jpeg", quality=args.quality, force=True,
                               no_cache=args.no_cache)
            info.pop("ops", None)
            info.pop("readback", None)
            info["ok"] = True
            s = suggest_max(info["in"]["w"], info["in"]["h"])
            info["suggest_max"] = s
            sugg[f.name] = s
        except Exception as exc:  # noqa: BLE001
            info = {"ok": False, "src": str(f), "error": str(exc)}
        results.append(info)
    good = [r for r in results if r.get("ok")]
    note = None
    if good and args.max < max((r.get("suggest_max", {}).get("detail", 0) for r in good), default=0):
        note = ("这档只够看版式；要读小字/公式请按每张的 suggest_max.detail 重跑一次"
                "（同一 outdir 加 --force 覆盖，别让它堆 -2 副本）")
    return {
        "ok": bool(good),
        "outdir": str(outdir),
        "max_side": args.max,
        "read_paths": [r["path"] for r in good],   # ← AI 直接拿这串去读图
        "suggest_max": sugg,
        "note": note,
        "outputs": results,
    }


def cmd_convert(args) -> dict:
    files = expand_inputs(args.paths, recursive=args.recursive,
                          only=args.only or None, skip=args.skip or None)
    if not files:
        raise ToolError("没有找到任何图片")
    base = Path(os.path.expanduser(str(args.paths[0]))).resolve()
    fmt = FORMAT_ALIAS.get((args.to or "jpg").lower(), "jpeg")
    ext = EXT_OF_FORMAT[fmt]
    mode = "dir" if args.outdir else ("alongside" if args.alongside else "auto")
    results, skipped = [], []
    for f in files:
        try:
            rec = describe(f)
            if args.skip_readable and rec.get("readable") and f.suffix.lower() in PILLOW_EXTS:
                skipped.append(str(f))
                continue
            outdir = default_outdir(f, base, mode=mode, outdir=args.outdir, subdir=args.subdir)
            # 别把自己上次的产物再转一遍（同目录 + 同扩展名 = 原地重编码，没有意义）
            if outdir == f.parent and f.suffix.lower() == ext:
                skipped.append(str(f))
                continue
            op = {"max": args.max, "pct": args.pct, "autolevel": args.autolevel}
            info = process_one(f, outdir / (f.stem + ext), ops=op, fmt=fmt,
                               quality=args.quality, force=args.force)
            info["ok"] = True
        except Exception as exc:  # noqa: BLE001
            info = {"ok": False, "src": str(f), "error": str(exc)}
        results.append(info)
    good = [r for r in results if r.get("ok")]
    return {
        "ok": bool(good) or bool(skipped),
        "count": len(results),
        "ok_count": len(good),
        "fail_count": len(results) - len(good),
        "outdirs": sorted({str(Path(r["path"]).parent) for r in good}),
        "paths": [r["path"] for r in good],        # ← AI 直接拿这串
        "outputs": results,
        "skipped_readable": skipped,
    }


# --- 定位类工具（2026-10-12 实战后补：专治「反复猜裁切坐标」） --------------

def _resolve_file(raw) -> Path:
    p = Path(os.path.expanduser(str(raw))).resolve()
    if not p.exists():
        raise ToolError(f"路径不存在：{p}")
    if p.is_dir():
        raise ToolError(f"这里要的是单个图片文件，不是目录：{p}")
    return p


def _prepare_outdir(d) -> Path:
    d = Path(os.path.expanduser(str(d))).resolve()
    d.mkdir(parents=True, exist_ok=True)
    mark_workspace(d)          # 只标记空目录，不会动用户已有的文件夹
    return d


def _load_font(size):
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Supplemental/Arial Narrow.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _draw_grid(im, step, every, alpha, font_size, labels=True):
    """在原图上叠加百分比网格（零偏移：图的比例 = 原图比例）。"""
    from PIL import Image as _I, ImageDraw

    base = im.convert("RGB")
    w, h = base.size
    ov = _I.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    a = max(0, min(255, int(round(255 * alpha))))
    thin, thick = (205, 80, 80, int(a * 0.5)), (176, 30, 30, a)

    def is_major(v):
        return abs(v / every - round(v / every)) < 1e-6

    k = 1
    while k * step < 1 - 1e-9:
        v = round(k * step, 6)
        col, wd = (thick, 2) if is_major(v) else (thin, 1)
        x, y = int(round(v * w)), int(round(v * h))
        if 0 < x < w:
            d.line([(x, 0), (x, h)], fill=col, width=wd)
        if 0 < y < h:
            d.line([(0, y), (w, y)], fill=col, width=wd)
        k += 1
    base = _I.alpha_composite(base.convert("RGBA"), ov).convert("RGB")

    if labels:
        d2 = ImageDraw.Draw(base)
        font = _load_font(font_size)
        n = max(1, int(round(1 / every)))
        for i in range(1, n):
            v = i * every
            txt = ("%.2f" % v).rstrip("0").rstrip(".")
            x, y = int(round(v * w)), int(round(v * h))
            try:
                if 0 < x < w - 10:
                    d2.text((x + 4, 4), txt, font=font, fill=(150, 0, 0),
                            stroke_width=3, stroke_fill=(255, 255, 255))
                if 0 < y < h - font_size - 4:
                    d2.text((4, y + 4), txt, font=font, fill=(150, 0, 0),
                            stroke_width=3, stroke_fill=(255, 255, 255))
            except TypeError:      # 老 Pillow 不支持 stroke
                if 0 < x < w - 10:
                    d2.text((x + 4, 4), txt, font=font, fill=(150, 0, 0))
                if 0 < y < h - font_size - 4:
                    d2.text((4, y + 4), txt, font=font, fill=(150, 0, 0))
    return base


def cmd_grid(args) -> dict:
    """给一张图叠加百分比网格，用来一次把目标区域的 rel 坐标量准。

    实战背景：以前找「求证」那一行要连裁 3 次才对准，量完网格一次就中。
    """
    src = _resolve_file(args.src)
    im = load_image(src, respect_orientation=not args.no_orient,
                    use_cache=not args.no_cache)
    in_size = im.size
    base_rel, base_px = None, None
    if args.box or args.rel:
        report = {}
        bx = resolve_box(im, args.box, args.rel, report=report)
        im = op_crop(im, bx)
        base_rel, base_px = report.get("box_rel"), report.get("box_px")
    if args.scale and abs(args.scale - 1) > 1e-9:
        im = im.resize((max(1, int(im.width * args.scale)),
                        max(1, int(im.height * args.scale))), Image.LANCZOS)
    if args.max:
        im = op_resize(im, max_side=args.max)
    if args.autolevel:
        im = op_autolevel(im)

    step = float(args.step)
    if not (0 < step <= 0.5):
        raise ToolError("--step 要在 0 到 0.5 之间（0.05 = 每 5% 一条线）")
    every = float(args.label_every) if args.label_every else min(0.5, max(step, step * 2))
    font_size = args.font_size or max(13, int(min(im.size) / 60))

    out = Path(os.path.expanduser(args.out)).resolve() if args.out else \
        new_workspace("grid") / f"{src.stem}_grid.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    grid_im = _draw_grid(im, step, every, args.alpha, font_size, not args.no_labels)
    info = save_image(grid_im, out, fmt="jpeg", quality=args.quality, force=args.force)
    result = {
        "ok": True,
        "src": str(src),
        "paths": [info["path"]],
        "inputs": {"orig": {"w": in_size[0], "h": in_size[1]}, "grid": {"w": info["w"], "h": info["h"]}},
        "step": step,
        "label_every": every,
        "howto": ("读图上的刻度把目标区域量成 x0,y0,x1,y1（0.05 = 5%），"
                  "直接 crop --rel x0,y0,x1,y1 --scale 2；网格是零偏移叠加，比例与原图一致"),
    }
    if base_rel:
        result["zoomed"] = {
            "from_rel": base_rel, "from_px": base_px,
            "to_full_rel": ("full_x0 = %.4f + x0*%.4f 等（网格比例是这块区域内部的）"
                            % (base_rel[0], base_rel[2] - base_rel[0])),
        }
    return result


def _row_ink_profile(gray, rel_dark=0.78, abs_margin=60, sample=4):
    """每行「墨迹占比」，判断阈值随该行自身的亮度自适应。

    为什么不直接用一个固定灰度阈值：手机拍的试卷有明暗渐变，固定阈值会把
    整片偏暗的纸面判成「有内容」，结果是整页只切出一块（实测踩过）。
    改成「比本行纸面更暗的像素占比」后，明暗渐变的照片也能正常分行。
    """
    w, h = gray.size
    raw = gray.tobytes()
    prof = []
    for i in range(h):
        row = raw[i * w:(i + 1) * w]
        med = sorted(row[::sample])[len(row[::sample]) // 2]
        thr = min(med - abs_margin, med * rel_dark)
        prof.append(sum(1 for v in row if v < thr) / float(w))
    return prof


def _find_line_spans(profile, ratio_thresh, gap, min_h,
                     edge_px=3, edge_thin_pct=0.04):
    spans, start, end, gapn = [], None, None, 0
    for y, v in enumerate(profile):
        if v >= ratio_thresh:
            if start is None:
                start = y
            end, gapn = y, 0
        elif start is not None:
            gapn += 1
            if gapn > gap:
                spans.append((start, end + 1))
                start = None
    if start is not None:
        spans.append((start, end + 1))

    H = len(profile) or 1
    keep = []
    for a, b in spans:
        if b - a < min_h:
            continue
        # 紧贴照片上下边缘的细条，多半是相纸黑边而不是内容，丢掉
        if (a <= edge_px or b >= H - edge_px) and (b - a) < edge_thin_pct * H:
            continue
        keep.append((a, b))
    return keep


def cmd_lines(args) -> dict:
    """自动找出图里的文字行区间，直接给出可用的 crop 参数。

    实战背景：以前靠肉眼估「求证那行大概在 0.19–0.27」，来回裁三次才对准；
    这个命令直接把「第 k 块内容占 rel y0–y1」和现成的 crop 参数报出来。
    """
    src = _resolve_file(args.src)
    im = load_image(src, respect_orientation=not args.no_orient,
                    use_cache=not args.no_cache)
    if args.max:
        im = op_resize(im, max_side=args.max)      # 出图/可视化用这一档
    W, H = im.size

    # 分析在更小的一档上做：比例一致，但快得多
    small = im
    if args.analyze and max(small.size) > args.analyze:
        small = op_resize(small, max_side=args.analyze)
    sw, sh = small.size
    m = max(0.0, min(0.2, float(args.margin)))
    if m > 0:
        small = small.crop((int(sw * m), 0, int(sw * (1 - m)), sh))
    gray = small.convert("L")
    aw, ah = gray.size
    # 自动试几档「墨迹判定强度」，两种情形都算没切好，要加严重试：
    #   · 只切出一块（纸面渐变/背面透印冒充了内容）
    #   · 切出的最大一块占了半页（相邻内容黏在一起了）
    # 实测四张试卷：强度 45 时稀疏页整页糊成 47% 的一块，60 就干净了。
    profile = spans = None
    tried = []
    for am in (args.abs_margin, max(args.abs_margin, 80), max(args.abs_margin, 105)):
        profile = _row_ink_profile(gray, args.rel_dark, am)
        spans = _find_line_spans(profile, args.thresh, args.gap, args.min_h)
        biggest = max((b - a for a, b in spans), default=0) / float(ah or 1)
        tried.append({"abs_margin": am, "blocks": len(spans),
                      "biggest_block": round(biggest, 3)})
        if len(spans) >= 2 and biggest <= 0.45:
            break
    used_margin = tried[-1]["abs_margin"]
    if args.limit:
        spans = spans[:args.limit]

    pad_rel = max(0, int(args.pad)) / float(ah)
    lines = []
    for i, (y0, y1) in enumerate(spans, 1):
        ry0 = max(0.0, y0 / ah - pad_rel)
        ry1 = min(1.0, y1 / ah + pad_rel)
        lines.append({
            "i": i,
            "y0": int(round(ry0 * H)), "y1": int(round(ry1 * H)),
            "ry0": round(ry0, 4), "ry1": round(ry1, 4),
            "dark": round(sum(profile[y0:y1]) / max(1, y1 - y0), 4),
            "crop_arg": f"0,{round(ry0, 4)},1.0,{round(ry1, 4)}",
        })

    out = None
    if args.out:
        from PIL import ImageDraw
        vis = im.convert("RGB")
        d = ImageDraw.Draw(vis)
        font = _load_font(max(13, int(min(vis.size) / 60)))
        for ln in lines:
            d.line([(0, ln["y0"]), (W, ln["y0"])], fill=(200, 40, 40), width=2)
            d.line([(0, ln["y1"]), (W, ln["y1"])], fill=(40, 110, 200), width=2)
            try:
                d.text((4, ln["y0"] + 3), str(ln["i"]), font=font,
                       fill=(150, 0, 0), stroke_width=3, stroke_fill=(255, 255, 255))
            except TypeError:
                d.text((4, ln["y0"] + 3), str(ln["i"]), font=font, fill=(150, 0, 0))
        out = Path(os.path.expanduser(args.out)).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out = save_image(vis, out, fmt="jpeg", quality=args.quality, force=args.force)["path"]

    return {
        "ok": True,
        "src": str(src),
        "size": {"w": W, "h": H},
        "analyzed_at": {"w": aw, "h": ah},
        "abs_margin_used": used_margin,
        "tried": tried,
        "count": len(lines),
        "lines": lines,
        "paths": [out] if out else [],
        "howto": "第 i 块内容占 rel y0–y1（红=上边界 蓝=下边界），用同一行的 crop_arg 喂 crop --rel",
    }


def _strip_spans(H, n=None, height=None, overlap=0):
    if n:
        n = max(1, int(n))
        base = int(math.ceil(H / n))
        spans = [(i * base, min(H, i * base + base)) for i in range(n)]
        spans = [s for s in spans if s[1] > s[0]]
    else:
        hh = max(1, int(height))
        step = max(1, hh - overlap)
        spans, y = [], 0
        while y < H:
            spans.append((y, min(H, y + hh)))
            if y + hh >= H:
                break
            y += step
    half = max(0, int(overlap) // 2)
    return [(max(0, a - half), min(H, b + half)) for a, b in spans]


def _strip_image(src, outdir, n=None, height=None, overlap=60, max_side=1800,
                 prefix=None, autolevel=False, quality=90, no_cache=False,
                 no_orient=False):
    im = load_image(src, respect_orientation=not no_orient, use_cache=not no_cache)
    W, H = im.size
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    segs = []
    for i, (y0, y1) in enumerate(_strip_spans(H, n, height, overlap), 1):
        piece = op_crop(im, (0, y0, W, y1))
        if max_side:
            piece = op_resize(piece, max_side=max_side)
        if autolevel:
            piece = op_autolevel(piece)
        rec = save_image(piece, outdir / f"{prefix or src.stem}_{i:02d}.jpg",
                         fmt="jpeg", quality=quality, force=True)
        rec.update({"src": str(src), "y0": y0, "y1": y1,
                    "rel": [round(y0 / H, 4), round(y1 / H, 4)],
                    "ok": True})
        segs.append(rec)
    return {"src": str(src), "size": {"w": W, "h": H}, "segments": segs}


def cmd_strip(args) -> dict:
    """把一条长图按高度或等份切开，一次返回多条，省去自己写切片脚本。"""
    src = _resolve_file(args.src)
    if not args.n and not args.height:
        args.height = 1600
    outdir = Path(os.path.expanduser(args.outdir)).resolve() if args.outdir \
        else new_workspace(f"strip_{src.stem}")
    res = _strip_image(src, outdir, n=args.n, height=args.height, overlap=args.overlap,
                       max_side=args.max, prefix=args.prefix, autolevel=args.autolevel,
                       quality=args.quality, no_cache=args.no_cache, no_orient=args.no_orient)
    paths = [s["path"] for s in res["segments"]]
    return {
        "ok": bool(paths),
        "src": res["src"],
        "size": res["size"],
        "count": len(paths),
        "outdir": str(outdir),
        "paths": paths,
        "segments": [{"i": i + 1, **{k: s[k] for k in ("path", "y0", "y1", "rel", "w", "h")}}
                     for i, s in enumerate(res["segments"])],
        "howto": "按顺序把 paths 全读一遍即等于整页；--overlap 保证跨界的行不会被切断",
    }


def cmd_prep(args) -> dict:
    """一条命令顶掉 scan + info + readcopy：扫描、转码、整页副本、尺寸与建议一起给。"""
    files = expand_inputs(args.paths, recursive=args.recursive,
                          only=args.only or None, skip=args.skip or None)
    if not files:
        raise ToolError("没有找到任何图片")
    outdir = Path(os.path.expanduser(args.outdir)).resolve() if args.outdir \
        else new_workspace("prep")
    outdir.mkdir(parents=True, exist_ok=True)
    mark_workspace(outdir)

    entries, read_paths = [], []
    for f in files:
        rec = describe(f)
        e = {"src": str(f), "name": f.name, "engine": rec.get("engine"),
             "format": rec.get("format"), "w": rec.get("w"), "h": rec.get("h"),
             "needs_convert": rec.get("needs_convert"),
             "suggest_max": rec.get("suggest_max"), "ok": False}
        try:
            info = process_one(f, outdir / (f.stem + ".jpg"),
                               ops={"max": args.max, "autolevel": args.autolevel},
                               fmt="jpeg", quality=args.quality, force=True)
            e.update({"ok": True, "read_path": info["path"],
                      "read_size": [info["w"], info["h"]],
                      "engine": info.get("engine", e["engine"])})
            read_paths.append(info["path"])
        except Exception as exc:  # noqa: BLE001
            e["error"] = str(exc)
        entries.append(e)

    result = {
        "ok": bool(read_paths),
        "count": len(files),
        "ok_count": len(read_paths),
        "outdir": str(outdir),
        "read_paths": read_paths,          # ← 直接拿去读整页
        "files": entries,
        "next": "整页读 read_paths；细节用 lines 找行 + crop --rel 放大，或 strip 切条",
    }
    if args.strip:
        strips, sdir = {}, outdir / "strips"
        for p in read_paths:
            r = _strip_image(Path(p), sdir, n=args.strip, max_side=args.max,
                             quality=args.quality, no_orient=True)
            strips[Path(p).name] = [s["path"] for s in r["segments"]]
        result["strips"] = strips
        result["strip_dir"] = str(sdir)
    return result


FORBIDDEN_CLEAN = {
    Path("/"), Path.home(), Path.home() / "Desktop", Path.home() / "Documents",
    Path.home() / "Downloads", Path.home() / "Library", Path.home() / "Pictures",
}


def cmd_clean(args) -> dict:
    """只清理工具自己建的工作区和解码缓存 —— 绝不碰用户的真实文件。"""
    targets = []
    want_ws = args.workspaces or args.all or not (args.dirs or args.cache)
    if want_ws:
        targets.extend(iter_workspaces())
    for raw in (args.dirs or []):
        p = Path(os.path.expanduser(str(raw))).resolve()
        if not p.is_dir():
            raise ToolError(f"不是目录：{p}")
        if p in FORBIDDEN_CLEAN:
            raise ToolError(f"拒绝清理系统/用户目录：{p}")
        if not (p / WORKSPACE_MARK).exists():
            raise ToolError(
                f"拒绝清理 {p}：它没有 {WORKSPACE_MARK} 标记，不是本工具建的工作区。"
                "（只清理 imgtool 自己创建的临时目录，避免误删你的文件）")
        targets.append(p)

    removed, freed = [], 0
    for p in sorted(set(targets)):
        if p in FORBIDDEN_CLEAN:
            continue
        size = _dir_size(p)
        if not args.dry_run:
            shutil.rmtree(p, ignore_errors=True)
        freed += size
        removed.append({"path": str(p), "bytes": size})

    cache = {"count": 0, "bytes": 0}
    if args.cache or args.all:
        try:
            files = list(CACHE_DIR.glob("*.png"))
            cache = {"count": len(files), "bytes": sum(f.stat().st_size for f in files)}
            if not args.dry_run:
                for f in files:
                    f.unlink()
        except OSError:
            pass

    return {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "removed": removed,
        "count": len(removed),
        "freed_bytes": freed,
        "freed_mb": round(freed / 1048576, 2),
        "cache": cache,
        "note": "只删除带工作区标记的临时目录；原图和你的输出目录从不受影响",
    }


def cmd_edit(args) -> dict:
    """单图加工：crop / rotate / resize / flip 都走这里（命令名决定默认工序）。"""
    src = Path(os.path.expanduser(args.src)).resolve()
    if not args.out:
        ext = ("." + args.to) if args.to else src.suffix
        args.out = str(src.parent / (src.stem + "_" + args.cmd + ext))
    ops = {
        "rotate": args.deg, "flip": args.flip, "box": args.box, "rel": args.rel,
        "max": args.max, "w": args.w, "h": args.h, "pct": args.pct,
        "autolevel": args.autolevel, "allow_upscale": args.allow_upscale,
        "resample": args.resample, "fill": args.fill,
    }
    if (args.scale or args.to_width) and (args.box or args.rel):
        # 裁完再定尺寸。两种写法：
        #   --scale 2      → 输出 = 裁切块 × 2（倍数，小区域用这个）
        #   --to-width 2000 → 输出宽度锁定 2000（裁全宽长条时用这个；
        #                     直接 --scale 3 会得到 6000px 宽，读图时又会被压回去，白放大）
        im = load_image(src, respect_orientation=not args.no_orient,
                        use_cache=not args.no_cache)
        im, log = apply_ops(im, {**ops, "max": None, "w": None, "h": None, "pct": None})
        if args.scale:
            im = im.resize((max(1, int(im.width * args.scale)),
                            max(1, int(im.height * args.scale))), Image.LANCZOS)
            log.append(f"scale={args.scale}")
        if args.to_width:
            tw = max(1, int(args.to_width))
            th = max(1, int(round(im.height * tw / im.width)))
            im = im.resize((tw, th), Image.LANCZOS)
            log.append(f"to_width={tw}")
        if args.max:
            im = op_resize(im, max_side=args.max)
            log.append(f"resize={im.width}x{im.height}")
        warns = [x[len("warn: "):] for x in log if x.startswith("warn: ")]
        info = save_image(im, Path(args.out), fmt=FORMAT_ALIAS.get(
            (args.to or Path(args.out).suffix.lstrip(".")).lower()), quality=args.quality,
            force=args.force)
        info.update({"ok": True, "src": str(src), "ops": log, "in": None})
        if warns:
            info["warnings"] = warns
        return {"ok": True, "outputs": [info], "paths": [info["path"]]}
    info = process_one(src, Path(args.out), ops=ops,
                       fmt=FORMAT_ALIAS.get((args.to or Path(args.out).suffix.lstrip(".")).lower()),
                       quality=args.quality, force=args.force, no_cache=args.no_cache)
    info["ok"] = True
    return {"ok": True, "outputs": [info], "paths": [info["path"]]}


# ---------------------------------------------------------------------------
# 数学图复检（figcheck）
#
# 为什么要有这条命令：几何图重绘最容易错的地方，全都**不是**数值算错，而是
#   · 拓扑 —— 该连的没连、连错了端点、辅助线穿过了本该空着的区域
#   · 标记 —— 直角方块、等长短线、等角弧、平行箭头，少画一个题意就变了
#   · 线型 —— 原图的虚线段被画成实线（或反之），"延长线"就变成了"边"
#   · 方向 —— 左右被镜像（坐标算反了，面积公式照样对，图却是反的）
# 这四类错误，第 2 步的数值自检一个也查不出来，只有把「原题」和「重绘」
# 摆在一起看才发现。所以这里把这件事做成一条命令：
#   抽出 HTML 里每幅 SVG → 单独渲染成 PNG → 与原题对应裁块并排拼成对照图
# 顺带把「图上有几个字母、几处虚线、墨迹占比」量化出来，供逐项对表。
# ---------------------------------------------------------------------------

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def find_chrome():
    """找一个能跑 --headless=new --screenshot 的浏览器。"""
    env = os.environ.get("IMGTOOL_CHROME")
    for p in ((env,) if env else ()) + CHROME_CANDIDATES:
        try:
            if p and Path(p).exists():
                return Path(p)
        except OSError:
            continue
    return None


_SVG_TAG = re.compile(r"<svg\b|</svg\s*>", re.I)


def extract_svgs(text: str) -> list:
    """按标签深度切出每一幅内联 SVG（不贪心，能扛 <svg> 里再嵌 <svg>）。"""
    out, start, depth = [], None, 0
    for m in _SVG_TAG.finditer(text):
        if m.group().lower().startswith("<svg"):
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth <= 0 and start is not None:
                out.append({"markup": text[start:m.end()], "pos": start})
                start, depth = None, 0
    return out


def _svg_attr(markup: str, name: str):
    m = re.search(rf"[<\s]{name}\s*=\s*[\"']([^\"']*)[\"']", markup[:800], re.I)
    return m.group(1) if m else None


def svg_box(markup: str):
    """取画布尺寸：优先 viewBox，其次 width/height，都没有就按 360×260 兜底。"""
    vb = _svg_attr(markup, "viewBox")
    if vb:
        nums = re.findall(r"-?\d+(?:\.\d+)?", vb)
        if len(nums) == 4:
            w, h = float(nums[2]), float(nums[3])
            if w > 0 and h > 0:
                return w, h, "viewBox"

    def _num(v):
        m = re.match(r"\s*(\d+(?:\.\d+)?)", v or "")
        return float(m.group(1)) if m else None

    w, h = _num(_svg_attr(markup, "width")), _num(_svg_attr(markup, "height"))
    if w and h and w > 0 and h > 0:
        return w, h, "width/height"
    return 360.0, 260.0, "default"


def _caption_before(text: str, pos: int) -> str:
    """在 SVG 前面往回找最近的题号，用来给图起名。"""
    seg = text[max(0, pos - 1600):pos]
    hits = re.findall(r"第\s*\d+\s*题(?:\s*[（(]\s*\d+\s*[）)])?", seg)
    if hits:
        return re.sub(r"\s+", "", hits[-1])
    ids = re.findall(r'id="(q\d+[a-zA-Z]?)"', seg)
    return ids[-1] if ids else ""


def svg_parts(markup: str):
    """从一幅 SVG 里把可核对的硬指标抠出来：文字标注、单字母、虚线处数。"""
    texts = []
    for raw in re.findall(r"<text\b[^>]*>([\s\S]*?)</text>", markup, re.I):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", raw)).strip()
        if t:
            texts.append(t)
    letters = sorted({t for t in texts if re.fullmatch(r"[A-Za-z]", t)})
    dashed = len(re.findall(r"stroke-dasharray\s*[=:]", markup, re.I))
    return {"texts": texts, "letters": letters, "dashed": dashed}


def _ink_ratio(im) -> float:
    """墨迹占比：低于 0.2% 基本等于「这幅图没画出来」。"""
    hist = im.convert("L").histogram()
    total = sum(hist) or 1
    return sum(hist[:205]) / total


def _chrome_shot_once(chrome: Path, html_path: Path, out_png: Path, w: float, h: float) -> bool:
    out_png = Path(out_png)
    if out_png.exists():
        out_png.unlink()
    cmd = [
        str(chrome), "--headless=new", "--no-sandbox", "--disable-gpu",
        "--hide-scrollbars", "--force-device-scale-factor=2",
        f"--window-size={int(math.ceil(w))},{int(math.ceil(h))}",
        f"--screenshot={out_png}",
        # ⚠ 绝对不要加 --user-data-dir：本机加了必被 SIGTERM（退出码 137）
        Path(html_path).resolve().as_uri(),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
    except subprocess.TimeoutExpired:
        pass          # Chrome 有时写完图不退出，图在就算成功
    except Exception:  # noqa: BLE001
        return False
    return out_png.exists() and out_png.stat().st_size > 0


def _chrome_shot(chrome: Path, html_path: Path, out_png: Path, w: float, h: float,
                 retries=2) -> bool:
    """逐幅截图。**会重试**：连着起多个 headless Chrome 时，偶尔有进程
    发现已存在实例就把活儿转过去、自己不截图（表现为「图没生成」）。
    实测 6 次里碰 1 次，隔一下重跑就好，所以失败不算数，重试一次。
    """
    for attempt in range(retries):
        if _chrome_shot_once(chrome, html_path, out_png, w, h):
            return True
        if attempt + 1 < retries:
            time.sleep(0.8)
    return False


def _qlmanage_shot(svg_path: Path, outdir: Path):
    """Chrome 不在时的兜底：用 macOS QuickLook 出缩略图。"""
    try:
        r = subprocess.run(["qlmanage", "-t", "-s", "1600", "-o", str(outdir), str(svg_path)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    cand = sorted(Path(outdir).glob(svg_path.name + ".png"))
    return cand[0] if cand else None


def _cjk_font(size):
    """对照图上要写中文标签，_load_font 只有西文字体，这里单走一套。"""
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/Supplemental/Songti.ttc",
              "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _fit_height(im, target_h):
    from PIL import Image as _I
    if im.height == target_h:
        return im
    r = target_h / max(1, im.height)
    return im.resize((max(1, int(round(im.width * r))), target_h), _I.LANCZOS)


def _fit_box(im, max_w, max_h, upscale_cap=1.8):
    """等比塞进 max_w × max_h 的框里。

    对照图不能简单「等高」：原题裁块常常是横向长条（2000×340），
    等高拉到 760 会得到 4400 宽的画布，整张缩略后什么都看不清。
    所以按「框」收纳，长边先撞线。
    """
    from PIL import Image as _I
    r = min(max_w / max(1, im.width), max_h / max(1, im.height), upscale_cap)
    if abs(r - 1) < 0.01:
        return im
    return im.resize((max(1, int(round(im.width * r))), max(1, int(round(im.height * r)))),
                     _I.LANCZOS)


def compose_pair(orig_path, rend_path, caption: str, out_png: Path,
                 target_h=760, target_w=1200) -> dict:
    """左原题、右重绘，并排拼成一张对照图（两侧各自等比收纳，垂直居中）。"""
    from PIL import Image, ImageDraw
    a = _fit_box(Image.open(orig_path).convert("RGB"), target_w, target_h)
    b = _fit_box(Image.open(rend_path).convert("RGB"), target_w, target_h)
    head, gap, pad = 46, 28, 16
    body_h = max(a.height, b.height)
    W, H = a.width + gap + b.width + pad * 2, head + body_h + pad
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W, head], fill=(246, 239, 239))
    d.rectangle([0, 0, W, 2], fill=(139, 31, 31))
    f, fs = _cjk_font(23), _cjk_font(19)
    title = caption or "题图"
    d.text((pad, 10), title, font=f, fill=(26, 26, 26))
    lx = pad + int(d.textlength(title, font=f)) + 22
    # 标签只用中文：◀ ▶ 这类字符在 PingFang 里缺字形，会渲染成空白
    d.text((lx, 12), "原题（左）", font=fs, fill=(85, 85, 85))
    d.text((pad + a.width + gap, 12), "重绘（右）", font=fs, fill=(139, 31, 31))
    canvas.paste(a, (pad, head))
    canvas.paste(b, (pad + a.width + gap, head + (body_h - b.height) // 2))
    mx = pad + a.width + gap // 2
    d.line([(mx, head), (mx, head + body_h)], fill=(215, 215, 215), width=1)
    canvas.save(str(out_png), optimize=True)
    return {"path": str(out_png), "w": W, "h": H}


def compose_sheet(entries: list, out_png: Path, target_h=420) -> dict:
    """所有重绘图竖排拼成一张总览，一眼看全（有没有少画、比例是否离谱）。"""
    from PIL import Image, ImageDraw
    rows = []
    for e in entries:
        im = _fit_height(Image.open(e["png"]).convert("RGB"), target_h)
        rows.append((f"#{e['i']}  {e.get('caption') or '题图'}", im))
    if not rows:
        raise ToolError("没有可拼总览的图")
    head, pad = 30, 14
    W = max(im.width for _, im in rows) + pad * 2
    W = max(W, 420)
    H = sum(head + target_h + pad for _ in rows) + pad
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)
    f = _cjk_font(18)
    y = pad
    for title, im in rows:
        d.rectangle([pad, y, W - pad, y + head - 6], fill=(246, 239, 239))
        d.text((pad + 8, y + 3), title, font=f, fill=(26, 26, 26))
        canvas.paste(im, (pad, y + head))
        y += head + target_h + pad
    canvas.save(str(out_png), optimize=True)
    return {"path": str(out_png), "w": W, "h": H}


def parse_map(spec: str) -> dict:
    """解析 --map：'1=0.1,0.2,0.9,0.6; 2=px:120,800,900,700'。"""
    out = {}
    for chunk in re.split(r"[;\n]+", spec or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ToolError(f"--map 这一段缺等号：{chunk}")
        k, v = chunk.split("=", 1)
        idx = int(re.sub(r"\D", "", k) or 0)
        v = v.strip()
        mode = "rel"
        if v.lower().startswith("px:"):
            mode, v = "box", v[3:]
        nums = [float(x) for x in re.split(r"[,\s]+", v) if x]
        if len(nums) != 4:
            raise ToolError(f"--map 第 {k} 项的坐标不是 4 个数：{v}")
        out[idx] = (mode, nums)
    return out


def cmd_figcheck(args) -> dict:
    html = Path(os.path.expanduser(args.html)).resolve()
    if not html.exists():
        raise ToolError(f"找不到 HTML：{html}")
    text = html.read_text(encoding="utf-8", errors="replace")
    figs = extract_svgs(text)
    if not figs:
        raise ToolError("这个 HTML 里没有内联 <svg>，没有可复检的图（图是不是用 <img> 贴的原图？）")

    outdir = _prepare_outdir(args.outdir) if args.outdir else new_workspace("figcheck")
    css = "\n".join(m.group(1) for m in
                    re.finditer(r"<style[^>]*>([\s\S]*?)</style>", text, re.I))
    chrome = find_chrome()
    plan = parse_map(args.map) if args.map else {}
    if plan and not args.src:
        raise ToolError("给了 --map 就必须同时给 --src（原题图在哪）")

    warnings, figures, rendered = [], [], []
    for i, fg in enumerate(figs, 1):
        vbw, vbh, how = svg_box(fg["markup"])
        if how == "default":
            warnings.append(f"第 {i} 幅图既没有 viewBox 也没有宽高，按 360×260 渲染，比例可能失真")
        cap = _caption_before(text, fg["pos"])
        parts = svg_parts(fg["markup"])

        page = (f"<!doctype html><meta charset='utf-8'><style>{css}\n"
                "html,body{margin:0;padding:0;background:#fff}\n"
                f"svg{{max-width:none!important;height:auto!important;width:{vbw}px!important;"
                "display:block}}</style>" + fg["markup"])
        hpath = outdir / f"fig{i}.html"
        hpath.write_text(page, encoding="utf-8")
        png = outdir / f"fig{i}.png"

        ok = _chrome_shot(chrome, hpath, png, vbw + 6, vbh + 6) if chrome else False
        if not ok:
            svg_path = outdir / f"fig{i}.svg"
            # 独立 .svg 文件走 XML 解析，缺 xmlns 会直接被拒——内联在 HTML 里时不需要，落地时必须补
            svg_markup = fg["markup"]
            if "xmlns" not in svg_markup[:300].lower():
                svg_markup = re.sub(r"<svg\b", '<svg xmlns="http://www.w3.org/2000/svg"',
                                    svg_markup, count=1, flags=re.I)
            svg_path.write_text(svg_markup, encoding="utf-8")
            alt = _qlmanage_shot(svg_path, outdir)
            if alt:
                shutil.move(str(alt), str(png))
                ok = True
        if not ok:
            warnings.append(
                f"第 {i} 幅图渲染失败：没找到能截图的浏览器（Chrome / Edge / Chromium）。"
                f"可以设 IMGTOOL_CHROME=<浏览器可执行文件路径> 再跑，"
                f"或手动在浏览器里打开 {outdir / f'fig{i}.html'} 检查")

        entry = {"i": i, "caption": cap, "w": round(vbw), "h": round(vbh),
                 "png": str(png) if ok else None, "ok": ok,
                 "texts": parts["texts"], "letters": parts["letters"],
                 "dashed": parts["dashed"]}
        if ok:
            from PIL import Image as _Img
            entry["ink_ratio"] = round(_ink_ratio(_Img.open(png)), 4)
            if entry["ink_ratio"] < 0.002:
                warnings.append(f"第 {i} 幅图几乎全白（墨迹占比 {entry['ink_ratio']:.2%}）"
                                "——可能线没画出来，或 stroke 用了失效的颜色变量")
            if not parts["letters"] and parts["texts"]:
                entry["note"] = "有文字但没有单字母标注，确认原图是不是也这样"
            if plan.get(i):
                mode, nums = plan[i]
                src = load_image(Path(os.path.expanduser(args.src)))
                report = {}
                box = resolve_box(src, box=(nums if mode == "box" else None),
                                  rel=(nums if mode == "rel" else None), report=report)
                crop = op_crop(src, box)
                opath = outdir / f"orig{i}.png"
                crop.save(str(opath))
                pair = outdir / f"pair{i}.png"
                info = compose_pair(opath, png, cap, pair, target_h=args.target_h,
                                    target_w=args.target_w)
                entry["orig"] = str(opath)
                entry["pair"] = info["path"]
                if report.get("warnings"):
                    warnings.extend(report["warnings"])
        figures.append(entry)
        if ok:
            rendered.append(entry)

    sheet = None
    if rendered and not args.no_sheet:
        sheet = compose_sheet(rendered, outdir / "总览.png")["path"]
    if plan and len(plan) < len(figs):
        missing = [i for i in range(1, len(figs) + 1) if i not in plan]
        warnings.append(f"--map 只覆盖了 {len(plan)}/{len(figs)} 幅图，"
                        f"第 {', '.join(map(str, missing))} 幅只出单图"
                        "（图分散在多张照片里时分几次跑，每次 --map 只给这批）")

    res = {
        "ok": True, "html": str(html), "count": len(figs), "outdir": str(outdir),
        "chrome": str(chrome) if chrome else None,
        "css_injected": bool(css), "figures": figures, "sheet": sheet,
        "howto": "逐幅 ViewImage 看对照图：先比连接关系（拓扑），再比字母标注、"
                 "直角/等长/等角标记、实线虚线、图上数值；两边字母集合必须相等",
    }
    if warnings:
        res["warnings"] = warnings
    return res


def cmd_gui(args) -> dict:
    """启动本地图形界面（子进程，前台运行）。"""
    here = Path(__file__).resolve().parent
    server = here / "gui_server.py"
    if not server.exists():
        raise ToolError(f"找不到图形界面后端：{server}")
    cmd = [sys.executable, str(server), "--port", str(args.port)]
    if args.no_open:
        cmd.append("--no-open")
    proc = subprocess.run(cmd)
    return {"ok": proc.returncode == 0, "exit": proc.returncode, "gui_server": str(server)}


# --- 命令行 ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="imgtool",
        description="试卷图片处理内核：HEIC→JPG/PNG、裁切、旋转、缩放（全本地离线）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--human", action="store_true", help="输出给人看的中文文本，而不是 JSON")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--human", action="store_true", default=argparse.SUPPRESS,
                        help="输出给人看的中文文本，而不是 JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    add("deps", help="报告本机图像处理能力").set_defaults(func=cmd_deps)

    sp = add("info", help="查看文件格式/尺寸/能否直接读")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--only", action="append")
    sp.set_defaults(func=cmd_info)

    sp = add("scan", help="扫一个目录，列出图片并标出哪些需要转换")
    sp.add_argument("path")
    sp.add_argument("-r", "--recursive", action="store_true")
    sp.add_argument("--only", action="append")
    sp.add_argument("--skip", action="append")
    sp.set_defaults(func=cmd_scan)

    sp = add("readcopy", help="生成阅读副本（自动转码 + 限宽），返回可直接读的路径")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("-o", "--outdir")
    sp.add_argument("--max", type=int, default=2000)
    sp.add_argument("--quality", type=int, default=88)
    sp.add_argument("--autolevel", action="store_true")
    sp.add_argument("--no-cache", action="store_true", help="解码缓存（本来可读的图不受影响）")
    sp.add_argument("-r", "--recursive", action="store_true")
    sp.add_argument("--only", action="append")
    sp.add_argument("--skip", action="append")
    sp.set_defaults(func=cmd_readcopy)

    sp = add("convert", help="批量转换（HEIC→JPG 等），默认写到同级 JPG/ 目录")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--to", default="jpg", help="目标格式：jpg/png/webp/tiff")
    sp.add_argument("-o", "--outdir", help="指定输出目录")
    sp.add_argument("--alongside", action="store_true", help="输出到原图旁边")
    sp.add_argument("--subdir", default="JPG", help="auto 模式下的子目录名（默认 JPG）")
    sp.add_argument("--max", type=int, help="顺带限制最长边")
    sp.add_argument("--pct", type=float, help="顺带按百分比缩放")
    sp.add_argument("--quality", type=int, default=92)
    sp.add_argument("--autolevel", action="store_true", help="顺带做轻度自动对比度")
    sp.add_argument("--skip-readable", action="store_true", help="跳过本来就能读的图片")
    sp.add_argument("--force", "--overwrite", dest="force", action="store_true",
                    help="覆盖同名产物（默认不覆盖，改为生成 -2 / -3 副本；重复转换同一批时用这个才是幂等的）")
    sp.add_argument("-r", "--recursive", action="store_true")
    sp.add_argument("--only", action="append")
    sp.add_argument("--skip", action="append")
    sp.set_defaults(func=cmd_convert)

    for name, helptext in (("crop", "裁切"), ("rotate", "旋转"), ("resize", "缩放"), ("flip", "翻转")):
        sp = add(name, help=f"{helptext}单张图片")
        sp.add_argument("src")
        sp.add_argument("-o", "--out")
        sp.add_argument("--to", help="输出格式，默认跟扩展名")
        sp.add_argument("--box", help="像素裁切：左,上,宽,高")
        sp.add_argument("--rel", help="比例裁切：x0,y0,x1,y1（0–1）")
        sp.add_argument("--scale", type=float, help="裁完再放大 N 倍（配合 --box/--rel）")
        sp.add_argument("--to-width", type=int, help="裁完把宽度锁到 N 像素（裁全宽长条时比 --scale 好用）")
        sp.add_argument("--no-cache", action="store_true", help="不走 HEIC 解码缓存")
        sp.add_argument("--max", type=int, dest="max", help="限制最长边")
        sp.add_argument("--deg", type=float, default=0, help="旋转角度，顺时针为正")
        sp.add_argument("--fill", default="white", choices=["white", "black"])
        sp.add_argument("--flip", choices=["horizontal", "vertical"], help="翻转方向")
        sp.add_argument("--w", type=int)
        sp.add_argument("--h", type=int)
        sp.add_argument("--pct", type=float)
        sp.add_argument("--autolevel", action="store_true")
        sp.add_argument("--allow-upscale", action="store_true")
        sp.add_argument("--resample", default="lanczos",
                        choices=["lanczos", "bicubic", "bilinear", "nearest"])
        sp.add_argument("--no-orient", action="store_true", help="忽略 EXIF 方向")
        sp.add_argument("--quality", type=int, default=92)
        sp.add_argument("--force", action="store_true")
        sp.set_defaults(func=cmd_edit)

    sp = add("prep", help="一条命令：扫描+转码+整页阅读副本+尺寸建议（替代 scan+info+readcopy）")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("-o", "--outdir")
    sp.add_argument("--max", type=int, default=2000, help="整页副本最长边（默认 2000）")
    sp.add_argument("--quality", type=int, default=88)
    sp.add_argument("--autolevel", action="store_true")
    sp.add_argument("--strip", type=int, metavar="N", help="顺带把每张图等分成 N 条")
    sp.add_argument("-r", "--recursive", action="store_true")
    sp.add_argument("--only", action="append")
    sp.add_argument("--skip", action="append")
    sp.set_defaults(func=cmd_prep)

    sp = add("figcheck", help="数学图复检：把 HTML 里每幅 SVG 单独渲染，与原题并排拼成对照图")
    sp.add_argument("html", help="全解 HTML 的路径")
    sp.add_argument("-o", "--outdir", help="产物目录（默认落在工具工作区，收工 clean 会删）")
    sp.add_argument("--src", help="原题图路径（通常取分组文件夹 JPG/ 里那张）")
    sp.add_argument("--map", help="原题裁块对照表，如 \"1=0.10,0.18,0.95,0.52; 2=px:120,800,900,700\"")
    sp.add_argument("--target-h", type=int, default=760, help="对照图每侧最大高度（默认 760）")
    sp.add_argument("--target-w", type=int, default=1200, help="对照图每侧最大宽度（默认 1200）")
    sp.add_argument("--no-sheet", action="store_true", help="不生成总览拼图")
    sp.set_defaults(func=cmd_figcheck)

    sp = add("grid", help="叠加百分比网格，用来一次量准裁切坐标")
    sp.add_argument("src")
    sp.add_argument("-o", "--out")
    sp.add_argument("--step", default=0.05, type=float, help="网格线间隔，默认 0.05")
    sp.add_argument("--label-every", type=float, help="标数字的间隔，默认是 step 的两倍")
    sp.add_argument("--alpha", type=float, default=0.5, help="网格深浅，默认 0.5")
    sp.add_argument("--no-labels", action="store_true", help="只画线不标数字")
    sp.add_argument("--font-size", type=int)
    sp.add_argument("--box", help="先裁一块再看（像素 l,t,w,h）")
    sp.add_argument("--rel", help="先裁一块再看（比例 x0,y0,x1,y1）")
    sp.add_argument("--scale", type=float, help="先裁后放大")
    sp.add_argument("--max", type=int, help="限制最长边")
    sp.add_argument("--autolevel", action="store_true")
    sp.add_argument("--no-orient", action="store_true")
    sp.add_argument("--no-cache", action="store_true")
    sp.add_argument("--quality", type=int, default=90)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_grid)

    sp = add("lines", help="自动列出文字行区间，直接给出可用的 crop 参数")
    sp.add_argument("src")
    sp.add_argument("-o", "--out", help="顺带出一张标好边界的可视化图")
    sp.add_argument("--max", type=int, default=2400, help="出图/可视化用的最长边")
    sp.add_argument("--analyze", type=int, default=1000, help="分析用的最长边（默认 1000，越快越省）")
    sp.add_argument("--thresh", type=float, default=0.03, help="判定为文字行的墨迹占比阈值")
    sp.add_argument("--rel-dark", type=float, default=0.78,
                    help="比本行纸面暗多少算墨迹（默认 0.78 倍）")
    sp.add_argument("--abs-margin", type=int, default=60,
                    help="与本行纸面亮度相差多少灰度才算墨迹（默认 60，四张试卷实测值；"
                         "切不出多块或最大块占半页时会自动加重试）")
    sp.add_argument("--margin", type=float, default=0.03,
                    help="忽略左右各百分之几的边缘（默认 0.03，避开照片暗边）")
    sp.add_argument("--gap", type=int, default=10, help="行距小于这个像素数就合并成一块")
    sp.add_argument("--min-h", type=int, default=6, help="太矮的块丢掉")
    sp.add_argument("--pad", type=int, default=6, help="每块上下各留的余量")
    sp.add_argument("--limit", type=int, help="只看前 N 块")
    sp.add_argument("--no-orient", action="store_true")
    sp.add_argument("--no-cache", action="store_true")
    sp.add_argument("--quality", type=int, default=88)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_lines)

    sp = add("strip", help="把长图按高度或等份切成多条，一次返回全部")
    sp.add_argument("src")
    sp.add_argument("-o", "--outdir")
    sp.add_argument("--n", type=int, help="等分成 N 条")
    sp.add_argument("--height", type=int, help="每条多高（像素），默认 1600")
    sp.add_argument("--overlap", type=int, default=60, help="相邻条重叠多少像素，防止切断文字行")
    sp.add_argument("--max", type=int, default=1800, help="每条最长边（默认 1800）")
    sp.add_argument("--prefix")
    sp.add_argument("--autolevel", action="store_true")
    sp.add_argument("--no-orient", action="store_true")
    sp.add_argument("--no-cache", action="store_true")
    sp.add_argument("--quality", type=int, default=90)
    sp.set_defaults(func=cmd_strip)

    sp = add("clean", help="清理工具自建的临时工作区与解码缓存（绝不碰原图）")
    sp.add_argument("dirs", nargs="*", help="要清理的工作区目录")
    sp.add_argument("--workspaces", action="store_true", help="清理全部工作区")
    sp.add_argument("--cache", action="store_true", help="清理解码缓存")
    sp.add_argument("--all", action="store_true", help="工作区 + 缓存")
    sp.add_argument("--dry-run", action="store_true", help="只看看会删什么")
    sp.set_defaults(func=cmd_clean)

    sp = add("gui", help="启动本地图形界面（桌面版）")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--no-open", action="store_true")
    sp.set_defaults(func=cmd_gui)
    return p


def fmt_human(result: dict) -> str:
    lines = []
    if not result.get("ok", True):
        return "✗ 失败：" + str(result.get("error"))
    cmd = result.get("_cmd")
    if cmd == "deps":
        lines.append(f"imgtool {result['version']} · {result['python']}")
        for name, key in (("Pillow", "pillow"), ("sips", "sips"), ("浏览器", "browser")):
            info = result.get(key) or {}
            ok = "✓" if info.get("available") else "✗"
            lines.append(f"  {ok} {name}  {info.get('version') or info.get('path') or '不可用'}")
        lines.append(f"  工作区：{result['workspace_root']}")
        lines.append("  " + result.get("engine_note", ""))
    elif cmd == "scan":
        lines.append(f"目录：{result['dir']}")
        lines.append(f"共 {result['count']} 张，建议先转码 {len(result['need_convert'])} 张")
        for r in result["files"]:
            flag = "需转换" if r.get("needs_convert") else "可直接读"
            sm = r.get("suggest_max") or {}
            tip = f"  阅读建议 {sm.get('overview')}/{sm.get('detail')}" if sm else ""
            lines.append(f"  [{flag}] {r['name']}  {r.get('w')}×{r.get('h')}  "
                         f"{r.get('format') or r['ext']}{tip}")
    elif cmd == "readcopy":
        lines.append(f"阅读副本目录：{result['outdir']}")
        for p in result["read_paths"]:
            lines.append("  " + p)
        for name, sm in (result.get("suggest_max") or {}).items():
            lines.append(f"  · {name}：整页用 {sm['overview']}，看小字用 {sm['detail']}")
        if result.get("note"):
            lines.append("  ⚠ " + result["note"])
    elif cmd == "prep":
        lines.append(f"共 {result['count']} 张，成功 {result['ok_count']} 张 → {result['outdir']}")
        for e in result["files"]:
            if e.get("ok"):
                sm = e.get("suggest_max") or {}
                lines.append(f"  ✓ {e['name']}  {e['w']}×{e['h']} → {e['read_path']}"
                             f"（阅读 {sm.get('overview')}／细节 {sm.get('detail')}）")
            else:
                lines.append(f"  ✗ {e['name']}：{e.get('error')}")
        for name, ps in (result.get("strips") or {}).items():
            lines.append(f"  ▸ {name} 切成 {len(ps)} 条")
    elif cmd == "grid":
        lines.append(f"网格图：{result['paths'][0]}")
        lines.append(f"  网格间隔 {result['step']}，标数字每 {result['label_every']}")
        lines.append("  " + result["howto"])
    elif cmd == "lines":
        lines.append(f"共找到 {result['count']} 块内容（图 {result['size']['w']}×{result['size']['h']}）")
        for ln in result["lines"]:
            lines.append(f"  #{ln['i']:>2}  y {ln['y0']}–{ln['y1']}  "
                         f"rel {ln['ry0']}–{ln['ry1']}  → crop --rel {ln['crop_arg']}")
        if result.get("paths"):
            lines.append(f"  可视化：{result['paths'][0]}")
    elif cmd == "strip":
        lines.append(f"{Path(result['src']).name} → {result['count']} 条，输出到 {result['outdir']}")
        for s in result["segments"]:
            lines.append(f"  #{s['i']:>2}  y {s['y0']}–{s['y1']}  {s['w']}×{s['h']}  {s['path']}")
    elif cmd == "figcheck":
        lines.append(f"共 {result['count']} 幅图 → {result['outdir']}")
        eng = Path(result["chrome"]).name if result.get("chrome") else "无（已降级 QuickLook）"
        lines.append(f"  渲染引擎：{eng}")
        for f in result["figures"]:
            mark = "✓" if f.get("ok") else "✗"
            lines.append(f"  {mark} #{f['i']}  {f.get('caption') or '题图'}  "
                         f"{f.get('w')}×{f.get('h')}  墨迹 {f.get('ink_ratio')}")
            if f.get("letters"):
                lines.append(f"      字母：{' '.join(f['letters'])}")
            if f.get("dashed"):
                lines.append(f"      虚线：{f['dashed']} 处")
            if f.get("pair"):
                lines.append(f"      对照图：{f['pair']}")
        if result.get("sheet"):
            lines.append(f"  总览：{result['sheet']}")
        for w in result.get("warnings", []):
            lines.append(f"  ⚠ {w}")
        lines.append("  " + result.get("howto", ""))
    elif cmd == "clean":
        head = "待清理" if result["dry_run"] else "已清理"
        lines.append(f"{head} {result['count']} 个工作区，"
                     f"{'可释放' if result['dry_run'] else '释放'} {result['freed_mb']} MB")
        for r in result["removed"]:
            lines.append(f"  - {r['path']}  {round(r['bytes'] / 1048576, 2)} MB")
        if result["cache"]["count"]:
            lines.append(f"  解码缓存：{result['cache']['count']} 个文件 "
                         f"{round(result['cache']['bytes'] / 1048576, 2)} MB"
                         f"{'（已清）' if not result['dry_run'] else '（待清）'}")
    elif cmd == "convert":
        lines.append(f"成功 {result['ok_count']} / {result['count']}")
        for r in result["outputs"]:
            if r.get("ok"):
                lines.append(f"  ✓ {Path(r['src']).name} → {r['path']}  {r['w']}×{r['h']}")
            else:
                lines.append(f"  ✗ {Path(r['src']).name}：{r.get('error')}")
        if result.get("skipped_readable"):
            lines.append(f"  （跳过本来可读的 {len(result['skipped_readable'])} 张）")
    else:
        for r in result.get("files", result.get("outputs", [])):
            lines.append(f"  {r.get('path')}  {r.get('w')}×{r.get('h')}  {r.get('format')}")
            for wmsg in r.get("warnings", []):
                lines.append(f"    ⚠ {wmsg}")
        if result.get("paths"):
            lines.append("输出：")
            lines.extend("  " + p for p in result["paths"])
    return "\n".join(lines)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except ToolError as exc:
        result = {"ok": False, "error": str(exc)}
    except KeyboardInterrupt:
        result = {"ok": False, "error": "用户中断"}
    except Exception as exc:  # noqa: BLE001
        import traceback
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                  "traceback": traceback.format_exc()[-1200:]}
    result.setdefault("_cmd", args.cmd)
    if args.human:
        print(fmt_human(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    sys.exit(main())
