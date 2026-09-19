# pycbeta — CBETA XML P5 多格式转换器

CBETA XML P5 → **HTML / PDF / DOCX / EPUB / Markdown**

单一解析器（IR 中间表示）+ 多渲染器，样式由共享主题驱动，
DOCX/PDF 输出支持字体方案、打印模式、书签、黑白输出等出版级选项。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium   # PDF 默认引擎
```

完整说明（PDF 各引擎安装、字体安装、GUI 使用、常见问题）见 `docs/安装说明.md`。
图形界面：`python -m pycbeta.gui`（七选项卡 + 独立转换窗，PySide6）。

## 快速上手

```bash
# 全格式
python -m pycbeta -i 经文.xml -f all

# 指定格式与输出
python -m pycbeta -i 经文.xml -f docx,pdf -o outdir

# 简体字体方案
python -m pycbeta -i 经文.xml -f docx --font-set zh-Hans

# 简体输出（OpenCC t2s 文本转换；未指定 --font-set 时自动套简体字库）
python -m pycbeta -i 经文.xml -f docx --t2s

# 打印模式（每卷从单数页开始）+ 页边框
python -m pycbeta -i 经文.xml -f docx,pdf --presets-file my.json
```

## 命令行参数

| 参数 | 说明 |
|---|---|
| `-i` / `-o` / `-f` | 输入、输出、格式（docx,pdf,html,epub,md,all）|
| `--theme` | 自定义主题 CSS/JSON（替换 pdf_docx.css）|
| `--font-set 组合:语言` | 字体方案，如 `zh-Hans` 一键简体字库（只换字库，不转文字） |
| `--t2s` / `--no-t2s` | 简体输出（OpenCC t2s 正文/注释/元数据；未指定 `--font-set` 时自动套 `default:zh-Hans` 字体；校验时官方文档同步转简体后比对）|
| `--font-scale 1.5` | 字号等比缩放（重排式大字，老人版推荐 1.33/1.5；字号不影响逐字校验）|
| `--config` | 自定义全局配置 JSON（别名 --presets-file）|
| `--page` | 页面方案名（a4/a5/book…或 config.json 的 pages；pdf/docx 适用）|
| `--notes` | footnote / endnote / inline（默认 docx=footnote，其余=endnote）|
| `--engine 管线[:单体]` | PDF 输出选择，见下节 |
| `--engine-tag` | PDF 文件名追加实际引擎名（如 `X60n1116_wps.pdf`）|
| `--vertical` | 竖排 PDF（走 HTML 管线）|
| `--xml-dir` / `--cbeta-ebook` | 本地 XML 候选源（只读，建议指向本地 cbeta-org/xml-p5 全仓库副本） / 电子书输出目录（可写，平展一部一目录，XML+官方电子书同目录）|
| `--name-template` | 输出文件名模板（`[id]`/`[书名]`/`[作者]`/`[vol]`/`[juan]`）；缺省 `{佛典編號 书名}.{ext}`（书名跟随 `source.title_t2s` 转简）|
| `--list-fonts [关键词]` | 列出本机字体（家族名\|路径），仅列表不渲染 |
| `--verify` | 生成后逐字校验（对比官方文档；`--verify-max-diff` 阈值默认 10，`--verify-diff-lines` 默认 5）|
| `--font-check` | 豆腐字检测（逐字覆盖率报告，不中断渲染）|

## PDF 输出：管线与引擎

`-f pdf` 时由 `--engine` 选择转换路径：

| 写法 | 管线 | 行为 |
|---|---|---|
| （默认，不传）| **DOCX→PDF** | 先渲染 DOCX，再按后端链转 PDF；带经文资讯尾页 |
| `--engine docx2pdf` | DOCX→PDF | 同默认 |
| `--engine docx2pdf:wps` | DOCX→PDF | 强制单一后端 wps |
| `--engine html2pdf` | HTML→PDF | 按 html2pdf.chain 引擎链 |
| `--engine html2pdf:prince` | HTML→PDF | 强制 prince |
| `--engine chromium/prince/weasyprint/cbetapdf…` | HTML→PDF | 指定单一引擎 |

- DOCX 后端链（config.json `engines.docx2pdf.chain`）：msword → wps → docbuilder → libreoffice → minipdf，按序尝试
- HTML 引擎链（`engines.html2pdf.chain`）：chromium → cbetapdf
- `--vertical` 竖排自动走 HTML 管线（DOCX 渲染器尚未实现竖排）

### 各后端说明

| 后端 | 说明 |
|---|---|
| msword / word | MS Word COM 导出（保真度最高，需 Office + pywin32）|
| wps | WPS Office COM 导出（需 WPS + pywin32）|
| libreoffice | soffice 命令行（自定义路径在 engines.paths 配置）|
| minipdf / docbuilder | 外部引擎（engines.external 注册，未安装自动跳过）|

## 配置文件

- **`pycbeta/config.json`** — 全局配置：字体方案（font_sets）、页面方案（pages）、
  输出处理（output）、转换引擎与后端链（engines）、DOCX 字体映射/行高（docx）。
  支持 `//` 注释；复制后用 `--config` 指定。
- **`pycbeta/styles/pdf_docx.css`** — PDF/DOCX 默认主题（各语义标签的观感）。
- **`pycbeta/styles/html_epub_official.css`** — HTML/EPUB 官方格式基底（逐字节对齐官方）。

想改样式直接编辑对应文件；`--theme` 用于整体替换主题层。
详见 `docs/设计报告-代码评审.md` §8。

## PDF 转换方案

| 管线 | 路径 | 说明 |
|---|---|---|
| docx2pdf（**默认**）| XML → DOCX → PDF | Word/WPS/LibreOffice 后端链自动探测 |
| html2pdf (chromium) | XML → HTML → PDF | headless Chromium |
| html2pdf (prince) | XML → HTML → PDF | 原生脚注/奇偶页分节 |
| html2pdf (weasyprint) | XML → HTML → PDF | Windows 需 GTK/Pango |

`docx2pdf` 复用 DOCX 渲染管线，PDF 与 DOCX 观感一致、带经文资讯尾页；
Word/WPS 走 COM 导出（需 pywin32），LibreOffice 走命令行。

### 新增转换引擎

**方式一：外部命令行引擎（零代码）**

任何能通过命令行把输入转成 PDF 的程序，在 `config.json` 的
`engines.external` 注册即可，两条管线（docx2pdf / html2pdf）通用：

```json
"engines": {
  "external": {
    "myconverter": {
      "executable": "C:/tools/myconv.exe",       // 绝对路径或相对项目根
      "arguments": "convert \"{input}\" -o \"{output}\"",
      "timeoutSeconds": 120
    }
  },
  "docx2pdf": { "chain": ["msword", "wps", "myconverter"] },  // 加入后端链
  ...
}
```

然后把引擎名传给 `--engine myconverter`（HTML 管线）或写入
`engines.docx2pdf.chain`（DOCX 管线）。参数模板支持 `{input}`/`{output}` 占位符。

**方式三：内置 Python 引擎（需改代码）**

- docx2pdf：写 `_pdf_via_xxx(docx_fn, pdf_fn)` 函数，注册进
  `render_pdf._DOCX_BACKENDS["xxx"]`；
- html2pdf：写 `_xxx_to_pdf(html_fn, pdf_fn)` 方法，加入
  `render_pdf.html_to_pdf` 的分派（内置三引擎 chromium/prince/weasyprint 在此）。

## 测试

```bash
# 单元测试
python -m unittest discover pycbeta.tests

# 端到端转换测试（test/*.xml -> test/out/<格式>/）
python test\run_tests.py                 # 全部 XML 全格式
python test\run_tests.py -f docx,pdf     # 指定格式
python test\run_tests.py --pages a4,a5,book  # 多页面方案各出一版
python test\run_tests.py --pdf-engine docx2pdf
```

## 目录结构

```
pycbeta/
  parser.py        P5 XML -> IR
  model.py         IR 数据模型
  render_html.py   IR -> 官方格式 HTML（分卷）
  render_pdf.py    IR -> PDF-ready HTML -> Chromium/Prince/WeasyPrint；DOCX->PDF
  render_docx.py   IR -> OOXML（真页底脚注、命名样式、按卷分节）
  render_epub.py   IR -> EPUB3
  render_md.py     IR -> Markdown
  theme.py         主题：语义标签 -> 各格式样式；config.json 加载
  config.json      全局配置（字体/页面/输出/引擎链）
  styles/          html_epub_official.css / pdf_docx.css / epub_print.css
docs/              设计报告与规格
test/              run_tests.py 端到端测试 + 样例 XML
```

## 渊源

CBETA 佛典編號/册号规则（`pycbeta/names.py`）移植自
[RayCHOU/ruby-cbeta](https://github.com/RayCHOU/ruby-cbeta) 的 `cbeta.rb`
（Copyright (c) 2016 Dharma Drum Institute of Liberal Arts, MIT License），
其余为独立重写；与上游无 fork 关系、无共享历史。本仓代码同样采用 MIT License（见根 `LICENSE`）。
