#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
试卷图片处理工具 · 本地图形界面后端

只监听 127.0.0.1（本机回环），不对外暴露、不联网、不依赖任何云服务。
图像处理全部复用 imgtool.py 的引擎（Pillow + macOS 自带 sips）。

常用启动方式
    ./启动工具.command          # 桌面版，双击即可
    python gui_server.py --port 8765
    python gui_server.py --no-open      # 不自动开浏览器

接口一览（都是给同目录下 gui/index.html 用的）
    GET  /                      图形界面
    GET  /api/caps              引擎能力
    GET  /api/roots             常用起始目录
    GET  /api/list?path=…       列目录（含每个图片文件的元信息）
    GET  /api/thumb?path=…      小缩略图（磁盘缓存）
    GET  /api/preview?path=…    大预览图（裁切面板用）
    POST /api/preview-ops       把当前工序先渲染出来看一眼（不落盘）
    POST /api/process           真正执行并落盘
    POST /api/zip               把若干输出文件打包成 zip
    POST /api/reveal            在访达里定位某个文件
    GET  /api/download?path=…   下载单个文件
    POST /api/quit              关掉这个本地服务
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, quote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import imgtool  # noqa: E402  （与后端同目录的核心引擎）

VERSION = "1.0.0"
GUI_DIR = HERE / "gui"
CACHE_ROOT = Path.home() / "Library" / "Caches" / "试卷图片处理工具"
THUMB_DIR = CACHE_ROOT / "thumbs"
PREVIEW_DIR = CACHE_ROOT / "previews"
EXPORT_DIR = CACHE_ROOT / "exports"

HOME = Path.home().resolve()
#: 允许访问的范围：用户主目录、临时目录、外接磁盘。其它位置一律拒绝。
ALLOWED_ROOTS = [HOME]
for _extra in ("/tmp", "/private/tmp", "/Volumes"):
    _p = Path(_extra)
    if _p.exists():
        ALLOWED_ROOTS.append(_p.resolve())

IMAGE_EXTS = imgtool.IMAGE_EXTS
DIR_JUNK = {".DS_Store", ".localized", "$RECYCLE.BIN", "System Volume Information"}


# ---------------------------------------------------------------- 工具函数

def is_allowed(path: Path) -> bool:
    try:
        p = path.resolve()
    except OSError:
        return False
    return any(p == r or r in p.parents for r in ALLOWED_ROOTS)


def safe_path(raw: str) -> Path:
    if not raw:
        raise imgtool.ToolError("缺少 path 参数")
    p = Path(unquote(str(raw))).expanduser()
    if not p.is_absolute():
        p = (HOME / p)
    p = p.resolve()
    if not is_allowed(p):
        raise imgtool.ToolError(f"只能操作本机用户目录内的文件：{p}")
    return p


def human_size(n) -> str:
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def list_dir(path: Path) -> dict:
    dirs, files = [], []
    try:
        entries = sorted(path.iterdir(), key=lambda q: imgtool.natkey(q.name))
    except PermissionError:
        raise imgtool.ToolError(f"没有权限读取：{path}")
    for e in entries:
        if e.name.startswith(".") or e.name in DIR_JUNK:
            continue
        try:
            if e.is_dir():
                dirs.append({"name": e.name, "path": str(e)})
            elif e.suffix.lower() in IMAGE_EXTS:
                rec = imgtool.describe(e)
                rec["size_h"] = human_size(rec.get("bytes"))
                rec["mtime"] = e.stat().st_mtime
                files.append(rec)
        except OSError:
            continue
    return {
        "ok": True,
        "path": str(path),
        "name": path.name or str(path),
        "parent": str(path.parent) if path.parent != path else None,
        "dirs": dirs,
        "files": files,
        "count": len(files),
        "need_convert": sum(1 for f in files if f.get("needs_convert")),
    }


def cached_jpeg(src: Path, cache_dir: Path, key_extra: str, max_side: int, quality: int,
                ops: dict | None = None) -> Path:
    """生成（并缓存）一张 JPEG。缓存键含原文件 mtime+size+参数，原图改了会自动失效。"""
    st = src.stat()
    key = f"{src}|{st.st_mtime_ns}|{st.st_size}|{max_side}|{quality}|{key_extra}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    out = cache_dir / f"{digest}.jpg"
    if out.exists():
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    im = imgtool.load_image(src, respect_orientation=True)
    if ops:
        im, _ = imgtool.apply_ops(im, {**ops, "max": None, "w": None, "h": None, "pct": None})
    im = imgtool.op_resize(im, max_side=max_side, box_mode="lanczos")
    imgtool.save_image(im, out, fmt="jpeg", quality=quality, force=True)
    return out


def export_dir_for(item_path: Path, mode: str, custom: str | None, subdir: str) -> Path:
    """把界面上的输出位置选项翻译成真实目录。"""
    if mode == "custom":
        if not custom:
            raise imgtool.ToolError("选择了自定义目录但没填路径")
        d = Path(os.path.expanduser(custom)).resolve()
        if not is_allowed(d):
            raise imgtool.ToolError("自定义目录必须在本机用户目录内")
        return d
    if mode == "same-folder":
        return item_path.parent
    if mode == "export":
        return EXPORT_DIR
    # 默认：jpg-folder / auto
    parent = item_path.parent
    if parent.name.lower() in imgtool.JUNK_DIR_NAMES:
        return parent.parent / subdir
    return parent / subdir


# ---------------------------------------------------------------- 请求处理

class Handler(BaseHTTPRequestHandler):
    server_version = f"ExamPaperImgtool/{VERSION}"
    protocol_version = "HTTP/1.1"

    # ---- 基础响应 ----
    def log_message(self, fmt, *args):  # 静音，避免刷屏
        if self.server.verbose:  # type: ignore[attr-defined]
            sys.stderr.write("  · %s\n" % (fmt % args))

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _file(self, path: Path, ctype=None, download=False):
        if not path.exists() or not path.is_file():
            return self._json({"ok": False, "error": f"文件不存在：{path}"}, 404)
        ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        extra = {"Content-Disposition": f'attachment; filename="{path.name}"'} if download else None
        self._send(200, data, ctype, extra)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            raise imgtool.ToolError("请求体不是合法 JSON")

    def _err(self, exc, code=400):
        msg = str(exc)
        sys.stderr.write(f"  ! {msg}\n")
        self._json({"ok": False, "error": msg}, code)

    # ---- 路由 ----
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._file(GUI_DIR / "index.html")
            if u.path == "/favicon.ico":
                return self._send(204, b"")
            if u.path.startswith("/static/"):
                rel = u.path[len("/static/"):]
                target = (GUI_DIR / rel).resolve()
                if GUI_DIR.resolve() not in target.parents and target.parent != GUI_DIR.resolve():
                    return self._err("非法路径")
                return self._file(target)
            if u.path == "/api/caps":
                return self._json({**imgtool.caps(), "gui_version": VERSION,
                                   "cache": str(CACHE_ROOT)})
            if u.path == "/api/roots":
                roots = [("主目录", HOME)]
                for label, sub in (("桌面", "Desktop"), ("下载", "Downloads"),
                                   ("文稿", "Documents"), ("图片", "Pictures")):
                    d = HOME / sub
                    if d.is_dir():
                        roots.append((label, d))
                return self._json({"ok": True,
                                   "roots": [{"label": l, "path": str(p)} for l, p in roots]})
            if u.path == "/api/list":
                p = safe_path(q.get("path") or str(HOME))
                if p.is_file():
                    p = p.parent
                return self._json(list_dir(p))
            if u.path == "/api/thumb":
                src = safe_path(q.get("path"))
                w = int(q.get("w") or 320)
                out = cached_jpeg(src, THUMB_DIR, "thumb", max(80, min(w, 1200)), 78)
                return self._file(out, "image/jpeg")
            if u.path == "/api/preview":
                src = safe_path(q.get("path"))
                m = int(q.get("max") or 1600)
                ops = json.loads(q["ops"]) if q.get("ops") else None
                key = json.dumps(ops, sort_keys=True) if ops else "plain"
                out = cached_jpeg(src, PREVIEW_DIR, key, max(400, min(m, 4000)), 88, ops)
                return self._file(out, "image/jpeg")
            if u.path == "/api/download":
                return self._file(safe_path(q.get("path")), download=True)
            if u.path == "/api/zip":
                return self._zip(q.get("paths", "").split("|") if q.get("paths") else [])
            return self._json({"ok": False, "error": f"没有这个接口：{u.path}"}, 404)
        except imgtool.ToolError as exc:
            return self._err(exc)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        try:
            body = self._body()
            if u.path == "/api/preview-ops":
                return self._preview_ops(body)
            if u.path == "/api/process":
                return self._process(body)
            if u.path == "/api/zip":
                return self._zip(body.get("paths") or [])
            if u.path == "/api/reveal":
                return self._reveal(body)
            if u.path == "/api/quit":
                self._json({"ok": True, "message": "服务已停止，可以关掉这个页面了"})
                threading.Timer(0.4, self.server.shutdown).start()  # type: ignore[attr-defined]
                return
            return self._json({"ok": False, "error": f"没有这个接口：{u.path}"}, 404)
        except imgtool.ToolError as exc:
            return self._err(exc)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    # ---- 业务 ----
    def _preview_ops(self, body):
        """把工序先渲染成一张预览图返回（base64），不落盘。"""
        src = safe_path(body.get("path"))
        ops = body.get("ops") or {}
        max_side = int(body.get("max") or 1600)
        im = imgtool.load_image(src, respect_orientation=not ops.get("no_orient"))
        before = im.size
        im, log = imgtool.apply_ops(im, {**ops, "max": None, "w": None, "h": None, "pct": None})
        shown = im.size
        im = imgtool.op_resize(im, max_side=max_side, box_mode="lanczos")
        buf = io.BytesIO()
        out = im.convert("RGB") if im.mode not in ("RGB", "L") else im
        out.save(buf, "JPEG", quality=88, optimize=True)
        import base64
        return self._json({
            "ok": True,
            "data_url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            "ops": log,
            "size_before": {"w": before[0], "h": before[1]},
            "size_after": {"w": shown[0], "h": shown[1]},
        })

    def _process(self, body):
        items = body.get("items") or []
        if not items:
            raise imgtool.ToolError("没有选中任何图片")
        out_cfg = body.get("output") or {}
        mode = out_cfg.get("mode") or "jpg-folder"
        subdir = out_cfg.get("subdir") or "JPG"
        fmt = imgtool.FORMAT_ALIAS.get((out_cfg.get("format") or "jpg").lower(), "jpeg")
        quality = int(out_cfg.get("quality") or 92)
        suffix = out_cfg.get("suffix") or ""
        force = bool(out_cfg.get("overwrite"))
        dry = bool(body.get("dry_run"))
        ext = imgtool.EXT_OF_FORMAT[fmt]
        results = []
        for it in items:
            src = safe_path(it.get("path"))
            ops = dict(it.get("ops") or {})
            split = ops.pop("split", None)
            # 「分栏」= 一张图按比例切成两份分别输出，其余工序照常套用
            parts = [("", ops)]
            if split == "vertical":
                parts = [("-上", {**ops, "rel": "0,0,1,0.5"}),
                         ("-下", {**ops, "rel": "0,0.5,1,1"})]
            elif split == "horizontal":
                parts = [("-左", {**ops, "rel": "0,0,0.5,1"}),
                         ("-右", {**ops, "rel": "0.5,0,1,1"})]
            for tag, part_ops in parts:
                try:
                    outdir = export_dir_for(src, mode, out_cfg.get("dir"), subdir)
                    target = outdir / f"{src.stem}{suffix}{tag}{ext}"
                    if dry:
                        results.append({"ok": True, "dry": True, "name": src.name,
                                        "src": str(src), "path": str(target)})
                        continue
                    info = imgtool.process_one(src, target, ops=part_ops, fmt=fmt,
                                               quality=quality, force=force)
                    info.update({"ok": True, "name": src.name,
                                 "size_h": human_size(info.get("bytes"))})
                    results.append(info)
                except Exception as exc:  # noqa: BLE001
                    results.append({"ok": False, "src": str(src), "name": src.name,
                                    "error": f"{type(exc).__name__}: {exc}"})
        good = [r for r in results if r.get("ok")]
        return self._json({
            "ok": bool(good),
            "count": len(results),
            "ok_count": len(good),
            "fail_count": len(results) - len(good),
            "dry_run": dry,
            "outdirs": sorted({str(Path(r["path"]).parent) for r in good if r.get("path")}),
            "paths": [r["path"] for r in good if r.get("path")],
            "results": results,
        })

    def _zip(self, paths):
        if not paths:
            raise imgtool.ToolError("没有要打包的文件")
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        zpath = EXPORT_DIR / f"试卷图片_{time.strftime('%Y%m%d-%H%M%S')}.zip"
        used = set()
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for raw in paths:
                p = safe_path(raw)
                if not p.is_file():
                    continue
                name = p.name
                i = 2
                while name in used:
                    name = f"{p.stem}-{i}{p.suffix}"
                    i += 1
                used.add(name)
                zf.write(p, name)
        return self._json({"ok": True, "zip": str(zpath), "name": zpath.name,
                           "bytes": zpath.stat().st_size,
                           "size_h": human_size(zpath.stat().st_size),
                           "url": "/api/download?path=" + str(zpath)})

    def _reveal(self, body):
        p = safe_path(body.get("path"))
        target = p if p.exists() else p.parent
        try:
            subprocess.run(["open", "-R", str(target)], check=False)
            return self._json({"ok": True, "revealed": str(target)})
        except Exception as exc:  # noqa: BLE001
            raise imgtool.ToolError(f"打开访达失败：{exc}")


# ---------------------------------------------------------------- 启动

def pick_port(preferred: int, tries=20) -> int:
    import socket
    for i in range(tries):
        port = preferred + i
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise imgtool.ToolError("找不到可用端口")


def main() -> int:
    ap = argparse.ArgumentParser(description="试卷图片处理工具 · 本地图形界面")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--verbose", action="store_true", help="打印请求日志")
    args = ap.parse_args()

    if not (GUI_DIR / "index.html").exists():
        sys.stderr.write(f"✗ 界面文件缺失：{GUI_DIR / 'index.html'}\n")
        return 2
    caps = imgtool.caps()
    if not caps["pillow"]["available"]:
        sys.stderr.write(
            "✗ 这个 Python 没有 Pillow，请改用：\n"
            "  python3 "
            f"{Path(__file__).name}\n"
        )
        return 2

    port = pick_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    # 启动器可以通过环境变量指定「打开就定位到这个文件夹」
    start = os.environ.get("IMGTOOL_START_DIR", "").strip()
    if start:
        try:
            sp = safe_path(start)
            if sp.is_dir():
                url += "?dir=" + quote(str(sp), safe="")
        except imgtool.ToolError:
            pass
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.verbose = args.verbose  # type: ignore[attr-defined]
    httpd.daemon_threads = True

    print("┌──────────────────────────────────────────────┐")
    print("│  试卷图片处理工具 · 本地版                    │")
    print("└──────────────────────────────────────────────┘")
    print(f"  地址：{url}")
    print(f"  引擎：Pillow {caps['pillow']['version']}"
          f"{' + sips（HEIC 解码）' if caps['sips']['available'] else ''}")
    print(f"  缓存：{CACHE_ROOT}")
    print("  全部处理都在本机完成，不联网。关掉窗口或按 Control-C 即可退出。")
    print()
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
