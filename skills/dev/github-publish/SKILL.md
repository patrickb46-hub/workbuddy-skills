---
name: github-publish
description: 把本地项目发布到 GitHub —— 隐私体检、写 .gitignore/LICENSE、本地提交、gh repo create、推送、校验远端。当用户说"上传到 GitHub / 发布到 GitHub / 建个 GitHub 仓库 / 开源这个项目 / push 到 GitHub / 传到 GitHub 上 / 帮我传代码"时使用。内置不可跳过的隐私体检门禁：未过体检不得推送。
agent_created: true
---

# GitHub 发布

## 零、硬性规定（GATE：不可跳过、不可协商）

**推送前必须跑完隐私体检，且 CRIT 与 HIGH 都为 0。**

绝不允许上传（任何项目、任何理由）：

- 真实姓名、网名与实名绑定、学校 / 公司 / 班级、住址、身份证号、学号、手机号、邮箱地址
- 密钥类：API Key、Token、SMTP/IMAP 授权码、私钥、证书、Cookie、`.netrc`
- 含用户名的绝对路径：`/Users/<name>/`、`/home/<name>/`、`C:\Users\<name>\`
- agent 记忆与会话目录：`.workbuddy/`、`.claude/`、`.codex/`、`.agents/`

执行纪律：

1. 命中 CRIT / HIGH 时**立即停下**，把清单原样交给用户，由用户决定每一项怎么处理。不要"顺手改成占位符然后继续推"。
2. **真实密钥没有例外**：哪怕用户说"没事、能推"，也必须先吊销/轮换，再改成环境变量。这条不接受确认。
3. 用户明确说明某项属于可公开信息（例如 GitHub 用户名、公开邮箱）时，才可用 `--ignore` 放行，并在最终结论里写明"第 X 项经用户确认属公开信息"。
4. 体检报告只留在终端输出，不要写进仓库。
5. 已经推到远方才发现泄漏 → 先吊销密钥，再和用户讨论是否改写历史（破坏性操作，须用户明确同意）。

## 一、执行顺序

### 1. 定位项目根

确认要发布的是哪个目录。注意区分：

- 项目根（含 README / 源码入口）
- 工作区根（可能还包着 `.workbuddy/`、构建产物、临时 zip）——**优先发项目根，不要发工作区根**

### 2. 环境体检

```bash
bash <skill>/scripts/preflight.sh <项目根>
```

重点看三项：`gh auth status` 是否已登录、`git config user.email` 是否为空或真实邮箱、有没有 `.DS_Store` / 大文件 / 敏感目录。

### 3. 隐私体检（GATE）

```bash
python3 <skill>/scripts/scan_secrets.py <项目根>
```

- 退出码 0：可继续（若只有 MED 项，逐条判断后说明）
- 退出码 1：**停**。把输出贴给用户，逐条处理完再重跑，直到为 0
- 需要放行白名单项：`--ignore 子串`（可多次），并在结论里说明理由

判据与易漏位置见 `references/privacy-checklist.md`。

### 4. 组装仓库

- 生成 `.gitignore`：至少包含 `.DS_Store`、`node_modules/`、构建产物、`*.zip`、`.workbuddy/`、`.claude/`、`.env*`
- 生成 `LICENSE`：默认 MIT，版权人写 **GitHub 用户名**而不是真实姓名
- 检查 README 里有没有绝对路径、内网地址、截图里的账号信息
- 把不该发布的开发脚本 / 截图挪到 `dev/` 或 `docs/`，或直接排除

### 5. 本地提交

```bash
cd <项目根>
git init                      # 若还没有 .git
git config user.name  "<GitHub 用户名>"
git config user.email "<login>@users.noreply.github.com"   # 不暴露真实邮箱
git add -A
git status                    # ★ 提交前再肉眼过一遍文件清单
git commit -m "<一句话说清这是什么>"
```

`git add -A` 之后**必须**看一次 `git status`，确认没有意外的目录被卷进来。

### 6. 确认可见性（必须问）

公网仓库是单向门。**建仓前一定问用户：public 还是 private？** 不要替用户决定。

### 7. 建仓并推送

```bash
gh repo create <repo-name> --public --source=. --remote=origin --push
# 私有：--private
```

已有远端时改用 `git remote add origin <url>` + `git push -u origin main`。

### 8. 校验远端

```bash
gh repo view --web                                  # 或 gh browse
gh api repos/<login>/<repo>/contents | head         # 确认文件清单
```

确认：文件数对得上、没有意外目录、README 正常渲染。

## 二、收尾必须交代

- 仓库 URL
- 提交摘要（几个文件、什么内容）
- 体检结论：扫了多少文件、命中什么、怎么处理的、哪些是经用户确认的忽略项
- 若做了取舍（比如把工具脚本挪进 `dev/`），说明原因

## 三、常见坑

| 现象 | 原因 / 处理 |
| --- | --- |
| `Author identity unknown` | 没设 `user.name/user.email`，按第 5 步设成 noreply |
| 提交里带出真实邮箱 | 全局 git 配置用了真实邮箱，改成 `<login>@users.noreply.github.com` |
| `gh: HTTP 403` | 缺 `repo` scope，`gh auth refresh -s repo` |
| 仓库建好了但没推上去 | `--source=.` 指向的不是当前目录，或分支名不是 `main` |
| `.workbuddy/` 被提交 | `.gitignore` 漏了，`git rm -r --cached .workbuddy` 后重提交 |
| 文件太大被拒 | GitHub 单文件 100MB 上限，先剔除或改用 Git LFS |
| 已有 `.git` 且 remote 指向别处 | 先 `git remote -v` 看清楚，别把项目推到别人的仓库 |
