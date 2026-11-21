#!/usr/bin/env python3
"""给已发布的稿件发置顶评论（用 cookies.json，走网页接口）。

用法：
    python3 post_comment.py BV1xxxxxxx --file comment.txt [--pin]
    python3 post_comment.py BV1xxxxxxx -m "文字"
"""
import argparse, json, os, ssl, sys, urllib.parse, urllib.request

CK = os.path.expanduser(os.environ.get("BILI_SECRET_DIR", "~/.workbuddy/secrets/bili") + "/cookies.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def sess():
    ck = json.load(open(CK))
    cookie = "; ".join(f"{k}={v}" for k, v in ck.items())
    return cookie, ck.get("bili_jct", "")


def get(url, cookie):
    req = urllib.request.Request(url, headers={
        "Cookie": cookie, "User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def post(url, data, cookie):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Cookie": cookie, "User-Agent": UA, "Referer": "https://www.bilibili.com/",
        "Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bvid")
    ap.add_argument("-m", "--message", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--pin", action="store_true", help="尝试置顶（需 UP 主权限）")
    a = ap.parse_args()

    msg = a.message or (open(a.file, encoding="utf-8").read().strip() if a.file else "")
    if not msg:
        sys.exit("没有评论内容")

    cookie, csrf = sess()
    info = get(f"https://api.bilibili.com/x/web-interface/view?bvid={a.bvid}", cookie)
    if info.get("code") != 0:
        sys.exit(f"取稿件失败：{info}")
    aid = info["data"]["aid"]
    print(f"{a.bvid} → aid={aid}  《{info['data']['title']}》")

    r = post("https://api.bilibili.com/x/v2/reply/add",
             {"oid": aid, "type": 1, "message": msg, "plat": 1, "csrf": csrf}, cookie)
    print("发评论：", r.get("code"), r.get("message"))
    if r.get("code") != 0:
        sys.exit(1)
    rpid = r["data"]["rpid"]
    print("rpid =", rpid)
    if a.pin:
        p = post("https://api.bilibili.com/x/v2/reply/pin", {"oid": aid, "type": 1, "rpid": rpid, "csrf": csrf}, cookie)
        print("置顶：", p.get("code"), p.get("message"))


if __name__ == "__main__":
    main()
