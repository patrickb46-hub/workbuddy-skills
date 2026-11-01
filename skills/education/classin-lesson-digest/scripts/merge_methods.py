#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「答题方法 / 通用规律」合并进一个累积的 docx，自动去重。

用法：
    python3 merge_methods.py --items items.json --docx "答题方法汇总.docx"
    python3 merge_methods.py --items items.json --docx out.docx --dry-run
    python3 merge_methods.py --docx out.docx --rebuild        # 按索引重建
    python3 merge_methods.py --docx out.docx --list           # 看看现在有什么

items.json 格式（数组，字段除 title/body 外都可省）：
[
  {"section": "文言文", "title": "翻译先定位实词", "body": "① …\\n② …",
   "source": "2026-10-21 第2节"}
]

去重规则（依次判断，命中即视为同一方法）：
  1) key 归一化后完全相同（技能会为每条方法生成稳定的 key）
  2) 标题归一化后相同，或标题相似度 ≥ 0.80
  3) 标题+正文整体：相同 / 包含（长度 ≤ 0.6）/ 相似度 ≥ 0.85
  4) 同 section 内正文相似度 ≥ 0.70
命中重复但新内容更长（多 20% 以上）→ 用更完整的版本替换；来源会累加
索引文件：与 docx 同名的 .index.json（记录归一化文本，下次快速比对）
"""
import argparse
import datetime as dt
import difflib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

DUP_RATIO = 0.85
DUP_CONTAIN_RATIO = 0.60
MIN_LEN = 8

PUNCT = re.compile(r"[\s\u3000,，.。;；:：!！?？、'\"“”‘’()（）\[\]【】<>《》\-—_/\\|*#·~`]+")


def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = PUNCT.sub("", s)
    return s


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def is_dup(a_norm, b_norm):
    if not a_norm or not b_norm:
        return False
    if a_norm == b_norm:
        return True
    short, long_ = sorted([a_norm, b_norm], key=len)
    if len(short) >= MIN_LEN and short in long_ and len(short) / len(long_) >= DUP_CONTAIN_RATIO:
        return True
    return sim(a_norm, b_norm) >= DUP_RATIO


def find_dup(new, items):
    """返回 (命中的已有条目, 命中原因) 或 (None, "")。"""
    n_title = norm(new.get("title", ""))
    n_body = norm(new.get("body", ""))
    n_all = norm(new.get("title", "") + new.get("body", ""))
    n_key = norm(new.get("key", ""))
    n_sec = norm(new.get("section", ""))
    for ex in items:
        e_title = ex.get("title_norm") or norm(ex.get("title", ""))
        e_all = ex.get("norm") or norm(ex.get("title", "") + ex.get("body", ""))
        e_sec = norm(ex.get("section", ""))
        if n_key and n_key == ex.get("key_norm"):
            return ex, "key"
        if n_title and e_title and (n_title == e_title or sim(n_title, e_title) >= 0.80):
            return ex, "title"
        if is_dup(n_all, e_all):
            return ex, "text"
        if n_sec == e_sec:
            e_body = ex.get("body_norm") or norm(ex.get("body", ""))
            if n_body and e_body and sim(n_body, e_body) >= 0.70:
                return ex, "body"
    return None, ""


# ---------------------------------------------------------------- 索引
def index_path(docx_path):
    p = Path(docx_path)
    return p.with_name(p.stem + ".index.json")


def load_index(docx_path):
    ip = index_path(docx_path)
    if ip.exists():
        try:
            data = json.loads(ip.read_text("utf-8"))
            if isinstance(data, dict) and "items" in data:
                return data
        except Exception:
            pass
    # 没有索引但有 docx → 从 docx 反向解析（按 Heading 2 切条）
    items = []
    if Path(docx_path).exists():
        try:
            from docx import Document
            doc = Document(docx_path)
            section, cur = "通用", None
            for p in doc.paragraphs:
                st = (p.style.name or "")
                if st.startswith("Heading 1"):
                    section = p.text.strip()
                elif st.startswith("Heading 2"):
                    title = re.sub(r"^\d+[.、]\s*", "", p.text.strip())
                    cur = {"section": section, "title": title, "body": "", "sources": []}
                    items.append(cur)
                elif cur is not None and p.text.strip() and not st.startswith("Heading"):
                    if p.text.startswith("来源："):
                        cur["sources"].append(p.text.replace("来源：", "").strip())
                    else:
                        cur["body"] = (cur["body"] + "\n" + p.text.strip()).strip()
        except Exception as e:
            print("[warn] 读旧 docx 失败：%s" % e, file=sys.stderr)
    for it in items:
        it["norm"] = norm(it.get("title", "") + it.get("body", ""))
    return {"docx": str(docx_path), "updated_at": "", "items": items}


def save_index(docx_path, data):
    data["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    index_path(docx_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


# ---------------------------------------------------------------- docx
def _set_font(run, name="宋体", size=None, bold=None, color=None):
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def build_docx(docx_path, items, title="语文答题方法汇总"):
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.4)
    sec.top_margin = sec.bottom_margin = Cm(2.2)

    st = doc.styles["Normal"]
    st.font.name = "宋体"
    st.font.size = Pt(11)
    st.paragraph_format.line_spacing = 1.5
    st.paragraph_format.space_after = Pt(4)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(p.add_run(title), "黑体", 20, True)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(p2.add_run("共 %d 条 · 更新于 %s" %
                         (len(items), dt.date.today().strftime("%Y年%m月%d日"))),
              "宋体", 9, False, (0x8A, 0x90, 0x99))

    sections = []
    for it in items:
        s = it.get("section") or "通用"
        if s not in sections:
            sections.append(s)

    n = 0
    for s in sections:
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(14)
        _set_font(h.add_run(s), "黑体", 14, True)
        h.style = doc.styles["Heading 1"]
        for r in h.runs:
            _set_font(r, "黑体", 14, True, (0x19, 0x1C, 0x1F))

        for it in [x for x in items if (x.get("section") or "通用") == s]:
            n += 1
            hh = doc.add_paragraph()
            hh.style = doc.styles["Heading 2"]
            hh.paragraph_format.space_before = Pt(10)
            _set_font(hh.add_run("%d. %s" % (n, it.get("title") or "未命名")),
                      "黑体", 11.5, True, (0x19, 0x1C, 0x1F))
            for line in str(it.get("body") or "").split("\n"):
                line = line.strip()
                if not line:
                    continue
                para = doc.add_paragraph()
                para.paragraph_format.first_line_indent = Pt(0)
                _set_font(para.add_run(line), "宋体", 10.5)
            srcs = it.get("sources") or ([it["source"]] if it.get("source") else [])
            if srcs:
                sp = doc.add_paragraph()
                _set_font(sp.add_run("来源：" + "、".join(srcs)), "宋体", 8.5,
                          False, (0x9A, 0xA0, 0xA7))

    doc.save(str(docx_path))
    return docx_path


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="答题方法合并 + 去重 → docx")
    ap.add_argument("--items", help="新条目 JSON")
    ap.add_argument("--docx", required=True, help="目标 docx 路径")
    ap.add_argument("--title", default="语文答题方法汇总")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild", action="store_true", help="只按索引重建 docx")
    ap.add_argument("--list", action="store_true", help="列出已有条目")
    args = ap.parse_args()

    docx_path = Path(os.path.expanduser(args.docx))
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_index(docx_path)
    items = data.get("items", [])

    if args.list:
        for i, it in enumerate(items, 1):
            print("%2d. [%s] %s" % (i, it.get("section") or "通用", it.get("title")))
        print("共 %d 条" % len(items))
        return 0

    added, dup, updated = 0, 0, 0
    reasons = {}
    if args.items and not args.rebuild:
        raw = json.loads(Path(os.path.expanduser(args.items)).read_text("utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("items", [])
        for it in raw:
            title = (it.get("title") or "").strip()
            body = (it.get("body") or "").strip()
            if not title and not body:
                continue
            n_new = norm(title + body)
            if len(n_new) < 4:
                continue
            hit, why = find_dup(it, items)
            if hit is None:
                items.append({
                    "section": (it.get("section") or "通用").strip(),
                    "title": title or "要点",
                    "body": body,
                    "key": (it.get("key") or "").strip(),
                    "key_norm": norm(it.get("key", "")),
                    "title_norm": norm(title),
                    "body_norm": norm(body),
                    "sources": [it["source"]] if it.get("source") else [],
                    "norm": n_new,
                })
                added += 1
            else:
                dup += 1
                reasons[why] = reasons.get(why, 0) + 1
                # 新版本更完整 → 覆盖正文
                if len(n_new) > len(hit.get("norm") or "") * 1.2:
                    hit["body"] = body or hit.get("body", "")
                    hit["title"] = title or hit.get("title", "")
                    hit["body_norm"] = norm(hit["body"])
                    hit["title_norm"] = norm(hit["title"])
                    hit["norm"] = n_new
                    updated += 1
                if it.get("source"):
                    srcs = hit.setdefault("sources", [])
                    if it["source"] not in srcs:
                        srcs.append(it["source"])

    print("新增 %d 条 · 重复跳过 %d 条 · 补全 %d 条 · 现有 %d 条"
          % (added, dup, updated, len(items)))
    if reasons:
        print("  去重命中：%s" % "、".join("%s %d" % (k, v) for k, v in reasons.items()))
    if args.dry_run:
        print("（dry-run，未写入）")
        return 0

    build_docx(docx_path, items, args.title)
    save_index(docx_path, {"docx": str(docx_path), "title": args.title, "items": items})
    print("已写入 → %s" % docx_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
