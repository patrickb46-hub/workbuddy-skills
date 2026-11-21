#!/usr/bin/env python3
"""git 传输不可达时，用 GitHub Data API 完成推送。

适用场景：`git push` 卡在 `CONNECT tunnel failed` / `Empty reply from server`，
但 `gh api` 仍能正常访问（说明 api.github.com 通、github.com 主站不通）。

做法：把工作目录的当前状态作为**全量快照**提交——远端有而本地没有的文件会被删除。

用法：
    python3 api_push.py --repo owner/name --dir /path/to/project
    python3 api_push.py --repo owner/name --dir . -m "更新说明"
    python3 api_push.py --repo owner/name --dir . --dry-run   # 只列文件不提交

前置：gh auth login 已登录且含 repo scope。
"""
import argparse
import base64
import json
import os
import pathlib
import subprocess
import sys

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".DS_Store"}


def gh(args, stdin=None, method=None):
    """调用 gh api，失败时抛异常。"""
    cmd = ["gh", "api"] + (["-X", method] if method else []) + args
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(args[:2])} 失败：\n{r.stderr.strip()[:500]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def try_gh(args):
    """调用 gh api，失败返回 None（用于探测）。"""
    try:
        return gh(args)
    except RuntimeError:
        return None


def collect(root: pathlib.Path):
    """收集要提交的文件，跳过 .git 等目录。"""
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description="用 GitHub Data API 推送（全量快照）")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--dir", required=True, help="项目根目录")
    ap.add_argument("--branch", default="main", help="目标分支（默认 main）")
    ap.add_argument("-m", "--message", default="sync via GitHub API", help="提交信息")
    ap.add_argument("--dry-run", action="store_true", help="只列文件，不提交")
    args = ap.parse_args()

    root = pathlib.Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"目录不存在：{root}")

    files = collect(root)
    if not files:
        sys.exit("没有可提交的文件")
    sizes = sum(f.stat().st_size for f in files)
    print(f"项目：{root}\n文件：{len(files)} 个，共 {sizes / 1024 / 1024:.2f} MB\n")

    if args.dry_run:
        for f in files:
            print(f"  {f.relative_to(root)}")
        return

    repo = args.repo
    ref = f"refs/heads/{args.branch}"

    # ---- 1. 探测分支是否已存在 ----
    head = try_gh([f"repos/{repo}/git/ref/heads/{args.branch}"])
    if head and head.get("object", {}).get("sha"):
        head_sha = head["object"]["sha"]
        print(f"[1/4] 分支已存在，HEAD = {head_sha[:12]}")
    else:
        print("[1/4] 空仓库 → 先用 Contents API 建立初始提交")
        # 空仓库不允许直接创建 blob（会 409 "Git Repository is empty"）
        seed = files[0]
        gh([f"repos/{repo}/contents/{seed.relative_to(root).as_posix()}", "--input", "-"],
           stdin=json.dumps({
               "message": "init",
               "content": base64.b64encode(seed.read_bytes()).decode(),
               "branch": args.branch,
           }),
           method="PUT")
        head_sha = gh([f"repos/{repo}/git/ref/heads/{args.branch}"])["object"]["sha"]
        print(f"      初始提交 {head_sha[:12]}")

    # ---- 2. 上传 blob ----
    print(f"[2/4] 上传 {len(files)} 个 blob …")
    tree, failed = [], []
    for i, p in enumerate(files, 1):
        rel = p.relative_to(root).as_posix()
        try:
            sha = gh([f"repos/{repo}/git/blobs", "--input", "-"],
                     stdin=json.dumps({
                         "content": base64.b64encode(p.read_bytes()).decode(),
                         "encoding": "base64",
                     }))["sha"]
        except RuntimeError as e:
            failed.append((rel, str(e)[:120]))
            continue
        mode = "100755" if os.access(p, os.X_OK) else "100644"
        tree.append({"path": rel, "mode": mode, "type": "blob", "sha": sha})
        if i % 20 == 0 or i == len(files):
            print(f"      {i}/{len(files)}")

    if failed:
        print(f"\n⚠️  {len(failed)} 个文件上传失败：")
        for rel, err in failed:
            print(f"   {rel} — {err}")
        if not tree:
            sys.exit("全部失败，中止")

    # ---- 3. 建树 + 提交 ----
    print("[3/4] 创建 tree 与 commit …")
    tree_sha = gh([f"repos/{repo}/git/trees", "--input", "-"],
                  stdin=json.dumps({"tree": tree}))["sha"]
    commit_sha = gh([f"repos/{repo}/git/commits", "--input", "-"],
                    stdin=json.dumps({
                        "message": args.message,
                        "tree": tree_sha,
                        "parents": [head_sha],
                    }))["sha"]
    print(f"      tree={tree_sha[:12]}  commit={commit_sha[:12]}")

    # ---- 4. 推进分支 ----
    print("[4/4] 推进分支 …")
    gh([f"repos/{repo}/git/refs/heads/{args.branch}", "--input", "-"],
       stdin=json.dumps({"sha": commit_sha, "force": True}), method="PATCH")

    print(f"\n完成：https://github.com/{repo}")
    print(f"本地 commit 与远端 hash 会不同（远端由 API 生成）。")
    print(f"网络恢复后用 git fetch origin && git reset --hard origin/{args.branch} 对齐。")


if __name__ == "__main__":
    main()
