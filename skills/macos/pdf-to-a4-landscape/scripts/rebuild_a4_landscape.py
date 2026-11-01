#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 PDF 里内嵌的横版照片重排到 A4 横版页面上（等比放大、不裁切、不重编码）。

策略：纯标准库、字节级重建。
  1) 按源文件里每个图像对象的 /Length 精确切出原始 JPEG 字节流（DCTDecode 直通）；
  2) 新建极简 PDF：每页一张图，MediaBox 改成 A4 横版；
  3) 用 cm 矩阵把图像等比缩放到「尽量大且不裁切」（fit）或「铺满并裁边」（cover）。

用法:
  python3 rebuild_a4_landscape.py <源.pdf> <输出.pdf> [fit|cover]
"""

import re
import sys
import pathlib

# A4 横版（单位 pt）
PAGE_W = 841.89
PAGE_H = 595.28


# ---------------------------------------------------------------- 源文件解析

def find_objects(data: bytes):
    """返回 {对象号: (字典片段 bytes, 数据片段 bytes 或 None)}"""
    objs = {}
    for m in re.finditer(rb"(?m)^(\d+)\s+0\s+obj\b", data):
        num = int(m.group(1))
        body_start = m.end()
        end = data.find(b"endobj", body_start)
        if end < 0:
            continue
        body = data[body_start:end]
        sm = re.search(rb"stream(\r\n|\r|\n)", body)
        if sm:
            raw = body[sm.end():]
            raw = raw[: raw.rfind(b"endstream")] if b"endstream" in raw else raw
            objs[num] = (body[: sm.start()], raw)
        else:
            objs[num] = (body, None)
    return objs


def extract_jpeg(objs, num: int):
    """从图像对象里取出原始 JPEG 字节（严格按 /Length 切）"""
    dic, raw = objs[num]
    if b"/Image" not in dic:
        raise ValueError(f"obj {num} 不是图像对象")
    length = int(re.search(rb"/Length\s+(\d+)", dic).group(1))
    jpg = raw[:length]
    if not (jpg[:2] == b"\xff\xd8" and jpg[-2:] == b"\xff\xd9"):
        raise ValueError(f"obj {num} 的 JPEG 边界异常（SOI/EOI 校验失败）")
    w = int(re.search(rb"/Width\s+(\d+)", dic).group(1))
    h = int(re.search(rb"/Height\s+(\d+)", dic).group(1))
    return w, h, jpg


def collect(data: bytes):
    """按页面顺序返回 [(w, h, jpeg_bytes), ...]"""
    objs = find_objects(data)

    # 页面对象按出现顺序
    pages = []
    for m in re.finditer(rb"(?m)^(\d+)\s+0\s+obj(.*?)endobj", data, re.S):
        if b"/Type" in m.group(2) and re.search(rb"/Type\s*/Page(?![s])", m.group(2)):
            pages.append((int(m.group(1)), m.group(2)))

    out = []
    for _pnum, body in pages:
        # 内容流
        cm = re.search(rb"/Contents\s+(\d+)\s+0\s+R", body)
        content = b""
        if cm:
            _, craw = objs.get(int(cm.group(1)), (b"", b""))
            content = craw or b""
        # 资源字典 -> /XObject 映射
        xmap = {}
        rm = re.search(rb"/Resources\s+(\d+)\s+0\s+R", body)
        if rm:
            rdic = objs.get(int(rm.group(1)), (b"", None))[0]
            xo = re.search(rb"/XObject\s*<<(.*?)>>", rdic, re.S)
            if xo:
                for k, v in re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", xo.group(1)):
                    xmap[k.decode()] = int(v)
        # 内容流里出现的图像名（保持绘制顺序）
        names = re.findall(rb"/(\w+)\s+Do", content)
        if not names:
            names = [k.encode() for k in xmap]
        for nm in names:
            key = nm.decode()
            if key in xmap:
                out.append(extract_jpeg(objs, xmap[key]))
                break
    if not out:
        raise ValueError("没有在 PDF 中找到可用的内嵌图片")
    return out


# ---------------------------------------------------------------- 坐标计算

def fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def matrix(w_px, h_px, mode="fit"):
    """返回 (cm 字符串, 说明文本)"""
    sw, sh = PAGE_W / w_px, PAGE_H / h_px
    if mode == "cover":
        s = max(sw, sh)
        dw, dh = w_px * s, h_px * s
        tx, ty = (PAGE_W - dw) / 2.0, (PAGE_H - dh) / 2.0
        crop_x = max(0.0, -tx) / 72 * 25.4
        crop_y = max(0.0, -ty) / 72 * 25.4
        note = f"铺满（左右裁 {crop_x:.2f}mm / 上下裁 {crop_y:.2f}mm）"
    else:
        s = min(sw, sh)
        dw, dh = w_px * s, h_px * s
        tx, ty = (PAGE_W - dw) / 2.0, (PAGE_H - dh) / 2.0
        note = (f"不裁切（左右白边各 {tx / 72 * 25.4:.2f}mm，"
                f"上下白边各 {ty / 72 * 25.4:.2f}mm），成品 {dw / 72 * 25.4:.1f}×{dh / 72 * 25.4:.1f}mm")
    return f"{fmt(dw)} 0 0 {fmt(dh)} {fmt(tx)} {fmt(ty)}", note


# ---------------------------------------------------------------- 写 PDF

def build(out_path: pathlib.Path, images, mode="fit"):
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    off = {}

    def start(n):
        off[n] = len(out)
        out.extend(f"{n} 0 obj\n".encode("latin-1"))

    def end():
        out.extend(b"\nendobj\n")

    n_img = len(images)

    start(1)
    out.extend(b"<< /Type /Catalog /Pages 2 0 R >>")
    end()

    kids = " ".join(f"{3 + i} 0 R" for i in range(n_img))
    start(2)
    out.extend(f"<< /Type /Pages /Kids [{kids}] /Count {n_img} >>".encode("latin-1"))
    end()

    # 页面
    for i in range(n_img):
        start(3 + i)
        out.extend((
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /ProcSet [/PDF /ImageC] /XObject << /Im{i} {3 + n_img + i} 0 R >> >> "
            f"/Contents {3 + 2 * n_img + i} 0 R >>"
        ).encode("latin-1"))
        end()

    # 图像（原样搬运 JPEG 字节，绝不经过 str）
    notes = []
    for i, (w, h, jpg) in enumerate(images):
        start(3 + n_img + i)
        out.extend((
            f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 "
            f"/Filter /DCTDecode /Length {len(jpg)} >>\nstream\n"
        ).encode("latin-1"))
        out.extend(jpg)
        out.extend(b"\nendstream")
        end()
        _cm, note = matrix(w, h, mode)
        notes.append((i + 1, w, h, note))

    # 内容流
    for i, (w, h, _jpg) in enumerate(images):
        cm, _ = matrix(w, h, mode)
        body = f"q\n{cm} cm\n/Im{i} Do\nQ\n".encode("latin-1")
        start(3 + 2 * n_img + i)
        out.extend(f"<< /Length {len(body)} >>\nstream\n".encode("latin-1"))
        out.extend(body)
        out.extend(b"endstream")
        end()

    # xref（每行恒 20 字节）
    xref = len(out)
    total = 3 + 3 * n_img
    out.extend(f"xref\n0 {total}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for n in range(1, total):
        out.extend(f"{off[n]:010d} 00000 n \n".encode("latin-1"))
    out.extend((
        f"trailer\n<< /Size {total} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode("latin-1"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(out))

    print(f"已生成: {out_path}")
    print(f"  文件大小: {len(out):,} 字节")
    for pno, w, h, note in notes:
        print(f"  第{pno}页: 原图 {w}x{h}px -> {note}")
    return out_path


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src = pathlib.Path(sys.argv[1]).expanduser()
    dst = pathlib.Path(sys.argv[2]).expanduser()
    mode = sys.argv[3].lower() if len(sys.argv) > 3 else "fit"
    if mode not in ("fit", "cover"):
        print("模式只能是 fit 或 cover")
        sys.exit(1)

    data = src.read_bytes()
    images = collect(data)
    print(f"源文件: {src}")
    print(f"找到 {len(images)} 张内嵌图片，模式: {mode}\n")
    build(dst, images, mode)


if __name__ == "__main__":
    main()
