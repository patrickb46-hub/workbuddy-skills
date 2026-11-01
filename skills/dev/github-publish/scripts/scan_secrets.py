#!/usr/bin/env python3
"""
上传前隐私/密钥体检。

用法：
    python3 scan_secrets.py <目录> [--json] [--ignore PATTERN ...]

退出码：
    0  没有高危项（CRIT/HIGH），可以上传
    1  发现高危项，**必须停下**，逐条处理或由用户显式确认
    2  用法错误

设计原则：
    - 宁可误报，不可漏报。误报就在结论里说明，不要静默忽略。
    - 输出里对命中的密钥做脱敏，避免体检报告本身泄露。
"""

import argparse
import json
import os
import re
import sys

MAX_SCAN_BYTES = 1_500_000
BIG_FILE_BYTES = 50 * 1024 * 1024

TEXT_EXT = {
    ".md", ".txt", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".jsonc",
    ".html", ".htm", ".css", ".scss", ".py", ".sh", ".bash", ".zsh", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".xml", ".svg", ".sql", ".java", ".kt", ".go",
    ".rs", ".c", ".h", ".cpp", ".swift", ".rb", ".php", ".env", ".gitignore", ".plist",
}

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}

SENSITIVE_FILES = [
    (r"^\.env(\..*)?$", "环境变量文件"),
    (r".*\.(pem|key|p12|pfx|jks|keystore)$", "私钥/证书"),
    (r"^id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$", "SSH 密钥"),
    (r"^(credentials|secrets?|auth|token)\.(json|ya?ml|txt)$", "凭证文件"),
    (r"^cookies\.json$", "浏览器 cookies"),
    (r"^\.netrc$", "netrc 凭证"),
    (r"^\.npmrc$", "npm 令牌"),
    (r"^\.pypirc$", "PyPI 令牌"),
]

# 目录名命中即提醒（agent 记忆 / 会话记录，通常含大量个人信息）
SENSITIVE_DIRS = {".workbuddy", ".claude", ".codex", ".cursor", ".agents", ".ssh"}

PATTERNS = [
    # (级别, 名称, 正则)
    ("CRIT", "私钥内容", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("CRIT", "GitHub Token", r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    ("CRIT", "OpenAI/DeepSeek 风格 Key", r"\bsk-[A-Za-z0-9_\-]{20,}"),
    ("CRIT", "AWS Access Key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("CRIT", "Slack Token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("CRIT", "Google API Key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("CRIT", "微信/腾讯云 SecretId", r"\bAKID[0-9A-Za-z]{20,}\b"),
    (
        "CRIT",
        "硬编码密码/密钥",
        r"(?i)(api[_-]?key|secret|token|passwd|password|passphrase|授权码)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]",
    ),
    ("HIGH", "macOS 用户绝对路径", r"/Users/[A-Za-z0-9._-]+/"),
    ("HIGH", "Linux 用户绝对路径", r"/home/[A-Za-z0-9._-]+/"),
    ("HIGH", "Windows 用户绝对路径", r"[A-Za-z]:\\\\?Users\\\\?[A-Za-z0-9._-]+\\\\"),
    ("HIGH", "邮箱地址", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("HIGH", "手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ("HIGH", "身份证号", r"(?<!\d)\d{17}[\dXx](?!\d)"),
    ("MED", "内网地址", r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
]

# 这些邮箱是文档占位符，不算泄漏
EMAIL_ALLOW = re.compile(
    r"(?i)(example\.(com|org|net)|@localhost|users\.noreply\.github\.com|"
    r"^you@|^user@|^name@|^your[.-]|^test@|^foo@|^noreply@)"
)


def is_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        return True
    base = os.path.basename(path).lower()
    return base in {".gitignore", ".npmrc", ".netrc", "dockerfile", "makefile", "readme"}


def redact(s, keep=4):
    s = s.strip()
    if len(s) <= keep + 2:
        return s[:2] + "***"
    return s[:keep] + "***" + s[-2:]


def scan_file(path, rel):
    findings = []

    base = os.path.basename(path)
    for pat, label in SENSITIVE_FILES:
        if re.match(pat, base, re.I):
            findings.append(("CRIT", rel, 0, label, "敏感文件名"))
            break

    try:
        size = os.path.getsize(path)
    except OSError:
        return findings
    if size > BIG_FILE_BYTES:
        findings.append(("HIGH", rel, 0, f"超大文件 {size // 1048576}MB", "GitHub 单文件上限 100MB"))

    if size > MAX_SCAN_BYTES or not is_text(path):
        return findings

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return findings

    for lineno, line in enumerate(lines, 1):
        if len(line) > 4000:
            line = line[:4000]
        for level, name, pat in PATTERNS:
            m = re.search(pat, line)
            if not m:
                continue
            hit = m.group(0)
            if name == "邮箱地址" and EMAIL_ALLOW.search(hit):
                continue
            findings.append((level, rel, lineno, name, redact(hit)))
    return findings


def main():
    ap = argparse.ArgumentParser(description="上传前隐私/密钥体检")
    ap.add_argument("root", nargs="?", default=".", help="要扫描的目录")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--ignore", action="append", default=[], help="忽略的路径子串，可多次指定")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"不是目录：{root}", file=sys.stderr)
        return 2

    findings = []
    scanned = 0
    big_dirs = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        rel_dir = os.path.relpath(dirpath, root)
        for d in dirnames:
            if d in SENSITIVE_DIRS:
                big_dirs.append(os.path.join(rel_dir, d) if rel_dir != "." else d)

        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if any(ig in rel for ig in args.ignore):
                continue
            findings.extend(scan_file(full, rel))
            scanned += 1

    crit = [f for f in findings if f[0] == "CRIT"]
    high = [f for f in findings if f[0] == "HIGH"]
    med = [f for f in findings if f[0] == "MED"]

    if args.json:
        print(
            json.dumps(
                {
                    "root": root,
                    "scanned_files": scanned,
                    "sensitive_dirs": big_dirs,
                    "crit": len(crit),
                    "high": len(high),
                    "med": len(med),
                    "findings": [
                        {"level": l, "file": f, "line": n, "kind": k, "snippet": s}
                        for l, f, n, k, s in findings
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if (crit or high) else 0

    print(f"扫描目录：{root}")
    print(f"文件数：{scanned}")
    if big_dirs:
        print("\n⚠️  以下目录通常是 agent 记忆/会话记录，**不要提交**：")
        for d in big_dirs:
            print(f"   - {d}/")

    if not findings:
        print("\n✅ 未发现个人信息或密钥。可以上传。")
        return 0

    order = {"CRIT": 0, "HIGH": 1, "MED": 2}
    findings.sort(key=lambda f: (order[f[0]], f[1], f[2]))

    print("\n发现如下（命中内容已脱敏）：\n")
    for level, f, n, kind, snippet in findings:
        loc = f"{f}:{n}" if n else f
        print(f"  [{level}] {loc}\n         {kind} → {snippet}")

    print(f"\n合计：CRIT {len(crit)} / HIGH {len(high)} / MED {len(med)}")
    if crit or high:
        print("\n❌ 存在高危项，**不得直接上传**。先逐条处理：")
        print("   - 真实密钥 → 立刻吊销并改用环境变量")
        print("   - 绝对路径 / 邮箱 / 姓名 → 改成占位符或相对路径")
        print("   - 确属误报 → 在结论里写明理由，并交由用户确认")
        return 1

    print("\n✅ 只有中低风险项（如内网地址），确认无实质泄露后可上传。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
