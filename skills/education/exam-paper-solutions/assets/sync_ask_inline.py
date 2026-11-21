#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 assets/ask-widget.html 内联同步进 solution-template.html（改完组件跑一次）。

模板里必须带一份完整组件，这样「cp 模板」出来的文件即使忘了跑 inject_ask.py 也有提问功能。
代价是两处副本，所以改 ask-widget.html 后**必须**跑本脚本，别手改模板里那一块。

用法：python3 sync_ask_inline.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIDGET = HERE / "ask-widget.html"
TARGETS = [HERE / "solution-template.html"]
BLOCK_RE = re.compile(r"<!-- WBS-ASK-WIDGET.*?<!-- /WBS-ASK-WIDGET -->", re.S)


def main():
    src = WIDGET.read_text(encoding="utf-8").strip()
    # 模板里默认不带 key（生成交付物时由 inject_ask.py 写入）
    src = re.sub(r'("key":")[^"]*(")', r"\1\2", src, count=1)
    rc = 0
    for t in TARGETS:
        if not t.exists():
            print(f"✗ 缺文件：{t}")
            rc = 1
            continue
        text = t.read_text(encoding="utf-8")
        if BLOCK_RE.search(text):
            text = BLOCK_RE.sub(lambda _: src, text, count=1)
            act = "已替换"
        else:
            i = text.lower().rfind("</body>")
            if i < 0:
                print(f"✗ {t.name} 里找不到 </body>")
                rc = 1
                continue
            text = text[:i] + src + "\n" + text[i:]
            act = "已插入"
        t.write_text(text, encoding="utf-8")
        print(f"✓ {t.name} {act}（{len(src)} 字符）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
