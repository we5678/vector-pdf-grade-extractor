# vector-pdf-grade-extractor

从**文字已被转成矢量路径**的成绩表 PDF 中恢复表格数据，并计算挂科率、体育合格率与班级学分绩点。

> **隐私说明**
> 本仓库只包含代码和说明，不含任何姓名、学号、成绩、课程名单或原始 PDF。
> 默认 `.gitignore` 已排除 `data/`、`work/`、`output/`、`*.pdf`、`*.png`、`*.json`、`*.csv`、`*.npy`。
> 如要提交自己的运行结果，请先确认已彻底脱敏。

## 为什么需要这套流程

这类 PDF 常见于“Excel/WPS 打印成 PDF”或扫描件：

- 用 `pypdf` / `pdfplumber` 提取文本为空，因为文字被转成了矢量轮廓；
- 直接把整页交给 OCR 时，相邻单元格的数字会粘连，小数点容易丢失；
- 中文 OCR 对数字也有系统性误识，例如 `0` 被识别成“刀 / 艺 / 生”。

本项目的核心不是“再调一次 OCR”，而是：

1. 用 PDF 里现成的矢量表格线精确定位每个单元格；
2. 把每个单元格切成独立小图并拼成一张“考卷”，让 OCR 在干净背景下识别；
3. 对全表字符做**连通域分割 + 字形聚类**，同一数字的字形只出现一次；
4. 用一次 OCR 给少量字形簇打标签，再按标签解码整张表；
5. 用第二次 OCR 交叉校验，并人工复核低分/临界分单元格。

因为数字来自字形本身，而不是 OCR 的猜测，0 / 6 / 8 / 9 这类容易混淆的字形可以得到稳定结果。

## 环境

- Windows 10/11（使用系统自带 `Windows.Media.Ocr`，需安装中文 OCR 语言包）
- Python 3.10+
- PowerShell 5.1+

```bash
pip install -r requirements.txt
```

依赖：`pymupdf`、`opencv-python`、`numpy`。

## 目录结构

```
scripts/
  ocr_windows.ps1        Windows OCR 封装（输出词 + 坐标）
  01_extract_grids.py    从矢量线条提取表格网格
  02_render_pages.py     页面渲染为 400 dpi PNG
  03_build_cell_sheets.py 单元格切图拼版，供 OCR 使用
  04_cluster_glyphs.py   字符连通域分割 + 字形聚类
  05_label_clusters.py   用 OCR 结果给字形簇打标签
  06_decode_cells.py     按标签解码整张表
  07_cross_check.py      与 OCR 结果交叉校验
  08_stats.py            挂科率 / 体育合格率 / 学分绩点
  09_export_csv.py       导出 Excel 可读的 CSV
```

## 快速开始

把所有输入 PDF 放进 `data/`（**不要提交到 Git**）。

```bash
# 1. 网格与页面
python scripts/01_extract_grids.py --pdf-dir data --out work/grids.json
python scripts/02_render_pages.py --pdf-dir data --out work/pages --dpi 400

# 2. 单元格拼版 + OCR（用于交叉校验）
python scripts/03_build_cell_sheets.py --pages work/pages --grids work/grids.json --out work/cells
powershell -NoProfile -File scripts/ocr_windows.ps1 `
    -ImagePath work/cells/s1_p1.png -OutPath work/cells/s1_p1_ocr.json
# 对 work/cells 下每一页重复一次；也可写循环。

# 3. 字形聚类 + 给簇打标签
python scripts/04_cluster_glyphs.py --grids work/grids.json --pages work/pages --out-dir work
powershell -NoProfile -File scripts/ocr_windows.ps1 `
    -ImagePath work/cluster_sheet.png -OutPath work/cluster_sheet_ocr.json
python scripts/05_label_clusters.py `
    --ocr-json work/cluster_sheet_ocr.json --sheet work/cluster_sheet.json `
    --glyphs work/glyphs.json --out work/cluster_labels.json

# 4. 解码 + 交叉校验
python scripts/06_decode_cells.py --glyphs work/glyphs.json `
    --labels work/cluster_labels.json --out work/decoded.json
python scripts/07_cross_check.py --decoded work/decoded.json `
    --meta work/cells/meta.json --ocr-dir work/cells --out work/ocr_mismatches.json

# 5. 统计 + 导出
python scripts/08_stats.py --decoded work/decoded.json --out work/stats.json `
    --sport-cols '{"s1": 54, "s2": 28}'
python scripts/09_export_csv.py --decoded work/decoded.json --stats work/stats.json `
    --out-dir output
```

> 参数中的列号 `54 / 28` 是示例：分别对应两个学期“体育”课程所在的列。
> 请按你的表格表头调整；其余列号可用 `--id-col / --credits-col / --gpa-col / --wavg-col / --score-start` 修改。

## 关键步骤说明

### 1. 网格识别

`01_extract_grids.py` 遍历 PDF 的矢量绘图对象：

- 高度 < 1.5pt 且宽度 > 50pt 视为横线；
- 宽度 < 1.5pt 且高度 > 30pt 视为竖线。

输出每个页面的横线 y 坐标与竖线 x 坐标（单位 pt）。

### 2. 表头与续页

第一页通常有一行很高的表头（竖排课程名），后续页不重复表头。
`03` 与 `04` 用第一条横线带的高度判断：

- 第一条带高 > 60pt → 视作表头，跳过；
- 否则从第一行开始就是数据。

如果表格样式不同，调整 `--header-gap`。

### 3. 字形聚类（核心）

`04_cluster_glyphs.py` 对每个单元格做连通域分析：

- 过滤边框碎片、横竖线残留；
- 每个字符缩放到 32×48 的黑白模板；
- 以 `mean(|a-b|) < 0.03` 做贪心聚类。

同一个数字在不同单元格里形状一致，因此几千个字符会收敛到几十个簇。
`cluster_sheet.png` 是每个簇的代表图；OCR 它即可自动得到标签。
`05_label_clusters.py` 将标签写回簇 ID。

小数点通常不会被 OCR 识别，`06` 通过字形尺寸（宽 ≤ 11、高 ≤ 12）自动识别。

### 4. 交叉校验

`07_cross_check.py` 把字形解码结果与单元格拼版的 OCR 结果对比。
重点关注 `ocr_only`：如果 OCR 读到了数字而字形解码为空，说明有字符被漏切。
低分和 60 分附近的单元格建议再人工看一遍。

### 5. 统计口径

`08_stats.py` 的默认规则：

- 两学期都没有成绩/学分的学生**不进入任何分母**；
- 百分制 < 60 记挂科；
- `缺考` / `禁考`（在数据中统一为 `ABSENT`）计入挂科人次，并单独统计；
- 体育合格 = 体育成绩 ≥ 60；`ABSENT` 不算合格；
- 班级平均学分绩点 = 学生“学分绩点”的算术平均；
- 学分加权绩点 = Σ(绩点 × 实获学分) / Σ实获学分。

> 注意：表中的“实获学分”通常不包含挂科课程学分，因此学分加权绩点可能略偏高。
> 如果学校有单独的“修读学分”字段，建议改用修读学分加权。

## 可选：姓名与课程名

仓库不包含任何姓名/课程映射。需要导出可读表格时，自行准备本地 JSON：

```json
// names.json（不要提交）
{"2024000001": "示例姓名"}
```

```json
// courses.json（不要提交）
{"s1": {"8": "高等数学", "15": "大学物理"}}
```

然后：

```bash
python scripts/09_export_csv.py ... --names-json names.json --courses-json courses.json
```

## 已知限制

- 假设同一 PDF 内各页列布局一致、第一页有表头；
- 假设字符是印刷体、同一字号；手写体或字号混乱时聚类阈值需要调整；
- 若单元格内两个数字粘连，连通域会合并，可能被过滤掉；`07` 的 `ocr_only` 可用于发现这类问题；
- Windows OCR 只是“打标签”和“交叉校验”的辅助，最终数字来自字形聚类；
- 不同的表格样式可能需要调整 `--threshold`、`--header-gap`、`--skip-cols`。

## License

未指定许可证。使用前请自行确认输入数据的授权与隐私合规要求。
