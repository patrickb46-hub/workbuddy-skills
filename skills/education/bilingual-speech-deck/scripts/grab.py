#!/usr/bin/env python3
"""Fetch article pages, list inline image URLs (resolved to absolute)."""
import re, sys, os, subprocess, urllib.parse, json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
OUT = os.path.dirname(os.path.abspath(__file__)) + "/pages"
os.makedirs(OUT, exist_ok=True)


def fetch(url):
    name = re.sub(r'[^a-zA-Z0-9]+', '_', url)[-90:] + ".html"
    path = os.path.join(OUT, name)
    subprocess.run(["curl", "-sSLk", "--max-time", "30", "-A", UA,
                    "-H", "Accept-Language: zh-CN,zh;q=0.9",
                    "--compressed", url, "-o", path], check=False)
    if not os.path.exists(path):
        return None
    return path


def imgs(path, url):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            t = raw.decode(enc)
            break
        except Exception:
            t = raw.decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r'<img[^>]+>', t, re.I):
        tag = m.group(0)
        s = re.search(r'(?:data-src|data-original|data-lazy|src)\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        if not s:
            continue
        src = s.group(1).strip()
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = urllib.parse.urljoin(url, src)
        elif not src.startswith("http"):
            src = urllib.parse.urljoin(url, src)
        if not re.search(r'\.(jpg|jpeg|png|webp)', src, re.I):
            continue
        w = re.search(r'(?:width|data-width)\s*=\s*["\']?(\d+)', tag, re.I)
        out.append((src, int(w.group(1)) if w else 0))
    # dedupe preserve order
    seen, res = set(), []
    for s, w in out:
        if s in seen:
            continue
        seen.add(s)
        res.append((s, w))
    return res


if __name__ == "__main__":
    for url in sys.argv[1:]:
        p = fetch(url)
        print("=" * 80)
        print("URL:", url)
        if not p:
            print("  FAILED")
            continue
        for s, w in imgs(p, url):
            print(f"  w={w:<5} {s}")
