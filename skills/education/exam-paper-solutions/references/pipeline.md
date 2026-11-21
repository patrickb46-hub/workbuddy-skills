# 读图、几何图复检、渲染自检、收尾（细节版）

## 一、读图流程

```bash
IMG_PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python   # 必须用它，才有 Pillow
IMG_TOOL=$HOME/.workbuddy/skills/exam-paper-solutions/tools/imgtool.py
```

| 需求 | 命令 |
|---|---|
| 一步预处理（转码＋整页副本＋尺寸建议） | `$IMG_PY $IMG_TOOL prep "$GROUP_DIR" -o /tmp/prep --human` → 读 `read_paths` |
| 先用 OCR 导航（打出每行文字的纵坐标） | `$IMG_PY $SK/tools/ocr.py JPG/a.jpg` |
| 直接问「第 3 题在哪」，给 crop 参数 | `$IMG_PY $SK/tools/ocr.py JPG/a.jpg --find 第3题` |
| 定位文字行（给出可直接用的 crop 参数） | `$IMG_PY $IMG_TOOL lines a.jpg -o /tmp/l.jpg --human` |
| 横向也要定位 | `$IMG_PY $IMG_TOOL grid a.jpg -o /tmp/g.jpg` |
| 全宽长条放大 | `crop … --rel 0,0.26,1.0,0.32 --to-width 2000` |
| 小区域放大 | `crop … --rel 0.62,0.32,0.95,0.48 --scale 2.5` |
| 长页一次全读 | `strip a.jpg --n 5 --max 1800` |
| HEIC → JPG | `convert "$GROUP_DIR/HEIC"`（自动写同级 `JPG/`） |
| 图形复检 | `figcheck 全解.html --src JPG/a.jpg --map "1=x,y,w,h"` |
| 清临时区 | `clean --workspaces` |

三条铁律：**① 整页通读用 2000px，别从 1500 试起；② 先 `lines`/`grid` 定位再 `crop`，不许凭感觉猜比例；③ 原图只读，重复转换加 `--force` 否则堆 `-2` 副本。**

省 token 的读图习惯：

- 一次 `prep` 拿到整页副本后，**先整页读一遍**把握题量与分区，再只对"图形／公式／密集小字"做局部放大。
- 同一区域不要读第二遍：读完立刻把要点写进 `.mk` 规格，后面靠规格不靠图。
- 题干纯文字、无图的题，不必再看图。

## 二、渲染自检（已工具化）

```bash
$IMG_PY ~/.workbuddy/skills/exam-paper-solutions/tools/shoot.py "$GROUP_DIR/xxx全解.html" -o /tmp/shots
```

输出：页面尺寸、每屏墨量、空白带、右侧贴边，并且**只保留首屏、末屏、有问题的屏**的切片。
读 1–3 张就够；报告里出现"空白竖带／右侧贴边／几乎空白"时再去读对应切片。

底层细节（要手工截图时才看）：

- Chrome 路径 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，参数 `--headless=new --no-sandbox --hide-scrollbars --window-size=1000,14000`。
- **绝不加 `--user-data-dir`**（必被 kill，退出码 137）；窗口高度上限约 16384，超过静默不出图。
- `CVDisplayLink…` 日志是无害噪音；Chrome 偶发不退出，图已生成直接 `ls`。
- 纸面背景 `#f2f2ef`（242），判断"有没有内容"的灰度阈值必须低于 242。
- 右下角折叠按钮是 `position:fixed`，贴窗口底部，算内容高度时要排除。

## 三、写长文件（防截断）

`build.py` 直接写文件，没有截断问题。手写路径下：`Write` 写头部＋首块＋`<!--SPLIT-->`＋`</body></html>`，之后每次 `Edit` 把 `<!--SPLIT-->` 换成「新内容＋`<!--SPLIT-->`」，最后一次删标记。每次 150–250 行。

## 四、收尾清理

```bash
rm -rf "$GROUP_DIR/HEIC"                                  # ① 删原图副本
mv ~/Downloads/IMG_41xx.HEIC ~/.Trash/                    # ② 只删第 0 步记下的那批
$IMG_PY $IMG_TOOL clean --workspaces                      # ③ 清 imgtool 临时区
rm -rf /tmp/shots /tmp/wbs-shots                          # ④ 清截图临时区
```

动手前三条硬核对：① 两份 HTML 都在且非空；② `JPG/` 与源图张数一一对应；③ Downloads 里只动记录过的那批。用户说"原图留着"就跳过 ①②。

## 五、常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 打印时答案整块消失 | 用了 `<details>` | 换 checkbox 折叠 |
| 「全部展开解答」只开一道题 | 某个 `.fd` 缺 `fd-sol` 类 | `check.py` 会直接点名第几题 |
| 点一个折叠块，别的题跟着开 | id 重复 | `check.py` 报 id 重复 |
| 搜索搜不到题号 | 题号没写在 `.qhd.q` 里 | 改结构 |
| 页面比窗口高、最后几屏空白 | 折叠没默认收起 / 内容过长 | 确认 `checked` 没被写死；必要时按题分两份 |
| 图上文字被切断 | SVG `viewBox` 太小 | 加 padding，重新 `figcheck` |
