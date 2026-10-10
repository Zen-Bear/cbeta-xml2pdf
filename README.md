# CBETA XML P5 多格式转换器（非官方项目）

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

CBETA XML P5 → **HTML / PDF / DOCX / EPUB / Markdown / TXT**

单一解析器（IR 中间表示）+ 多渲染器，样式由共享主题驱动，
DOCX/PDF 输出支持字体方案、打印模式、书签、黑白输出等出版级选项。

## 安装（绿色版，推荐）

1. 到 [Releases](https://github.com/Zen-Bear/cbeta-xml2pdf/releases) 下载 `CBETA-XML2PDF-v0.5-win64.zip`（约 130MB，PySide6 所致）。
2. 解压到**可写目录**（如 `D:\CBETA-XML2PDF`）；`CBETA-XML2PDF.exe` 与 `_internal/` 需在一起，不可拆分。
3. 双击 `CBETA-XML2PDF.exe` 即开图形界面（免装 Python）。

- **PDF 引擎自备**：绿色版不带引擎。WPS / Word / LibreOffice 三选一安装，或 minipdf /
  cbetapdf 丢进 exe 旁新建的 `engines/`；GUI 引擎下拉红字即未安装（见「PDF 引擎安装」）。
  出厂与标准预设均未填引擎路径：LibreOffice 非默认路径（如 `C:\Apps\...` 且不在 PATH）
  会报未安装——需**另存**一个自用预设后手填 `engines.paths.libreoffice`（GUI 不直接改此键），或把路径加进 PATH。
- **命令行**：同一 exe 也兼 CLI：`CBETA-XML2PDF.exe -i <編號/目录/xml> -f <格式>`（`--help` 可查）。
- **配置（首次必做）**：出厂＋标准预设已内置（`config.user.json` v0.5 起入库，机器路径已清洗），
  但**电子书输出目录 `source.cbeta_ebook` 必填**——在「数据源」窗口设一次（清空时弹必填警告）；
  不设则任何转换都报「未配置」。本地 XML 候选源 / 官方基线库 / 输出目录可选（输出缺省 `cwd/out`），
  详见「数据源与官方书库」。无 `run.json` 时按全出厂跑；GUI「保存」写 exe 旁 `presets/`（便携场景正常）。
- **已知局限**：解压到 Program Files 等只读位置时，保存预设弹"保存失败"警告（`panel._on_save`
  已接住，不崩溃）；要持久化配置请解压到可写目录。

## GUI 快速上手

双击 `CBETA-XML2PDF.exe`，或源码环境 `python -m pycbeta.gui`——**不带参数即启动**。
首次转换前需在「数据源」窗口设一次**电子书输出目录**（`source.cbeta_ebook`，**必填**；
空则每行报「未配置」）；其余路径可选。

1. 输入：填「佛典编号列表」（如 `T0349, X1116`，可带卷范围 `T0349:2-3`）或选「目录/文件」。
2. 勾选输出格式、页面等（默认即可；各卡 tooltip 有说明）。
3. 点「转换」；勾选「转换后校验」则转换后逐字对比官方文档。

- 八选项卡：输出格式 / 样式表 / 页面 / 分页 / 排版 / 注释 / 注音 / 校验
  （输出格式首位，内含字体区；分页含佛典丛书名；注音为常用六项；
  排版卡含 `CBETA校改字标红`＝`output.corr_cbeta`，默认关，**配置项无 CLI 开关**）。
- 顶部"配置"框（一切以下拉选中项为准）：预设下拉（首项`（出厂默认）` + `presets/*.json`，
  选中即载入；默认用户预设 `presets/config.user.json`）、`保存`（覆盖选中，出厂默认项置灰）、
  `另存…`（新建到 `presets/`）、`删除`（删选中，出厂默认项不可删；删除前弹确认，
  若删的正是默认指向的预设则自动清空槽）、`设为默认`
  （run.json 的 `config-json` 槽指向选中项，出厂默认=清空槽；命令行/GUI 默认用它）、
  `还原出厂`（面板回 `presets/config.factory.json` 值，不写盘）。保存/设默认等成功后配置框
  标题常驻最后动作（如“配置（已保存）”，换预设/还原出厂后复原）。出厂文件 GUI 永不写。
- 独立窗：目录/文件 或 佛典編號列表两种输入，☐自动下载缺失 XML / ☐同时下载官方电子书；
  批量表五列（经号/经名/来源/状态/文件）**只读、可选中拷贝**；「来源」＝该部 XML 的取得方式
  （`本地XML`＝工作根已有 / `本地拷贝`＝从本地候选源拷入 / `合册合成`＝碎片按册合并 /
  `已下载`＝从官方下载）；文件列单击打开产物（勾选「转换后校验」时末尾附验证总报告 `{stem}_verify_report.txt`）；开始/取消 + 总进度。数据源窗口「更新XML」可把已下载 work 的 XML（及可选已有电子书）刷新到最新。
- 数据源窗口：路径输入框一律只读（只能点「浏览…」修改；电子书库清空确定时弹必填警告）；
  佛典目录钉死程序内 `cbeta/data/sutra_mapping.txt`（出厂 `presets/config.factory.json` 为仓库相对路径；
  旧预设里的绝对路径会被忽略），随「更新官方数据」刷新。
  「更新官方数据」先弹对话框列出更新源（缺字库/梵字库/补充字型/佛典目录映射表/手动项），
  确认后同步（含仅检查模式）。
- publish 侧集成见 `docs/第三方调用说明.md` §6.1。

### 启动参数（可选，供 publish 一键调用）

```bash
python -m pycbeta.gui [--ids-file ID列表.txt] [--out 输出目录] [--preset 预设] [--formats 格式] [--verify] [--verify-root 校验根] [--autostart]
```
`--ids-file`（填入输入来源并切到“目录/文件”，`.txt` 按行取編號）、`--out`（输出目录预填）、
`--preset`（stem / `*.json` 文件名 / 绝对路径都认，选中即载入面板；不存在则保持原选中）、
`--formats`（逗号分隔，如 `pdf,epub`，预填格式勾选；全不匹配时回退 pdf）、
`--verify`（勾选转换后校验）、`--verify-root`（校验根显式覆盖，只本次运行；优先级
`显式 ＞ 预设 source.verify_root ＞ {输出}/验证`，只影响校验产物落点）、
`--autostart`（窗现即开始批量）。Qt 自带参数透传；无参数时与裸启动完全一致。

## 安装（源码）

> 环境：Windows + Python 3.13/3.14（开发机为 3.14）。下述命令均在仓库根目录执行。

```bash
pip install -r requirements.txt
```

| 包 | 用途 | 缺失后果 |
|---|---|---|
| `lxml` | XML 解析（核心） | 不可运行 |
| `tinycss2` | 主题 CSS 解析（核心） | 不可运行 |
| `fontTools` | 字体 cmap（`--font-check`、补充字形注音） | 检测跳过、自动注音降级 |
| `playwright` + `playwright install chromium` | HTML→PDF 备用引擎（最后手段） | Word 系全缺时才用 |
| `PySide6` | GUI 独立窗/面板 | `python -m pycbeta.gui` 不可运行 |
| `pypinyin`（可选） | 生僻字自动注音 | 缺字跳过，手动词表不受影响 |
| `pymupdf`（可选，仅开发） | PDF 冒烟测试 | 测试跳过 |
| `pywin32`（可选） | Word/WPS COM 导出 PDF | 这两个后端自动跳过 |
| `weasyprint`（可选） | HTML→PDF 备选引擎，另需 GTK/Pango 运行时 | 该引擎不可用 |

## 命令行快速上手

```bash
# 全格式
python -m pycbeta -i 经文.xml -f all

# 指定格式与输出
python -m pycbeta -i 经文.xml -f docx,pdf -o outdir

# 简体字体方案（只换字库，不转文字）
python -m pycbeta -i 经文.xml -f docx --font-lang zh-Hans

# 简体输出（OpenCC t2s 文本转换；未指定 --font-lang 时自动套简体字库）
python -m pycbeta -i 经文.xml -f docx --t2s

# 打印模式（每卷从单数页开始）+ 页边框
python -m pycbeta -i 经文.xml -f docx,pdf --config my.json
```

## PDF 引擎安装（默认 Word 系；装一个即可出 PDF）

默认管线 `docx2pdf`（MS Word / WPS / LibreOffice 系优先）：`msword → wps → docbuilder → libreoffice → minipdf`；
`html2pdf: chromium → cbetapdf` 是最后手段（Word 系全不可用才走）。按链顺序首个成功者出 PDF；`--engine 管线:单体` 可强制单个。

```bash
playwright install chromium   # 备用引擎（最后手段；默认走 Word 系）
```

| 引擎 | 安装 | 验证 |
|---|---|---|
| chromium（最后手段） | `playwright install chromium` | `--engine html2pdf:chromium -f pdf …`（Word 系全缺时） |
| MS Word（msword） | 安装 Office + `pip install pywin32` | `--engine docx2pdf:msword …` |
| WPS（wps） | 安装 WPS Office + `pip install pywin32` | `--engine docx2pdf:wps …` |
| LibreOffice | 安装后把路径填 `engines.paths.libreoffice`（如 `D:\LibreOffice\program\soffice.com`）；安装前先 `taskkill /F /IM soffice.bin`（常驻进程锁目录）。实测 **26.8.0**：`--engine docx2pdf:libreoffice` 转 T0672 脚注版 PDF 效果良好（每页底脚注/分隔线/注码对应均正常） | `soffice.com --version`；`--engine docx2pdf:libreoffice …` |
| ONLYOFFICE DocBuilder | 安装后填 `engines.paths.docbuilder` | `--engine docx2pdf:docbuilder …` |
| minipdf | 本仓库不再随包携带，请从上游下载 `minipdf-win-x64.zip`（MiniPdf.Cli v0.38.5，已验证与本机版本逐字节一致）：https://github.com/mini-software/MiniPdf/releases/download/v0.38.5/minipdf-win-x64.zip ；解压得到 `minipdf.exe` 后放入仓库根 `engines/` 目录；未放则链尾自动跳过（上游主页：https://github.com/mini-software/MiniPdf） | 链尾兜底 |
| cbetapdf | 暂无公开下载（html2pdf 备选链成员，没办法才用）。如已持有该文件，放入仓库根 `engines/` 即可被识别；未放则自动跳过 | html2pdf 备选 |
| prince（最后手段） | 安装 Prince 并进 PATH | `--engine html2pdf:prince …`（Word 系全缺时） |
| weasyprint（最后手段） | `pip install weasyprint` + GTK/Pango 运行时 | `--engine html2pdf:weasyprint …`（Word 系全缺时） |

GUI 里输出格式卡的"单引擎"下拉会自动探测本机已装项（未安装标红并提示去哪装）；
`--engine-tag` 可把实际使用的引擎名追加进 PDF 文件名（如 `X60n1116_wps.pdf`）。

**WPS/Word 已打开时（2026-09-13）**：`docx2pdf:msword|wps` 先用 `DispatchEx` 新建独立
实例（隐藏、只读、`Quit(0)`）；若检测到用户已开着该程序则安全附着——不动窗口、不退出
用户实例、`Documents.Open(ReadOnly)` + `Close(0)`、`DisplayAlerts=0` 用后恢复，并从临时
副本转换。不会再弹「是否保存修改」或关掉用户在编辑的文档。（临时副本避免与用户已打开
的同名文件撞同一 Document 对象。）

自定义外部引擎：配置文件 `engines.external` 注册 `{executable, arguments, timeoutSeconds}`，
`{input}`/`{output}` 为占位符，加入对应 `chain` 即可（见「新增转换引擎」完整示例）。

## 字体安装（可选，但影响豆腐字）

- **本仓自带 CBETA 字库**：`cbeta/fonts/`——`CBETASupplement.ttf`（缺字补充）、`Ranjana.ttf` / `Siddam.ttf`（悉昙）；
  右键「安装」即可用；或到 CBETA 官方下载页取最新版本：https://cbeta.org/downloads
- 正文/标题走系统字库；缺字（`>0xFFFF`）按 `output.docx.gaijiFonts` 链取本机已装首个
  （繁：补充字形；简：SimSunExtB → 补充字形）。生僻字建议装 SimSun-ExtB（一般随系统自带）。
- 查本机有什么名可填：`python -m pycbeta --list-fonts "kaiti"`（中英文关键词都认，
  第一列即 CSS `--font-*` 变量/`--font-lang` 对应的 GDI 名）；查缺字：渲染加 `--font-check`。

### 字体清单（CSS/配置实际引用，2026-09-10 扫描）

| 用途 | 字体（中/英双名任一即可） | 系统自带？ | 缺了会怎样 |
|---|---|---|---|
| 简体正文/署名 | 宋体, SimSun | 简体 Win 自带 | 链首，缺则整链漂移 |
| 简体标题/偈颂 | 楷体, KaiTi | 简体 Win 自带 | 同上 |
| 简繁黑体 | 黑体/黑體, SimHei；繁 head 微軟正黑體, Microsoft JhengHei | Win 自带（JhengHei 需繁体语言包） | 标题变宋体风格 |
| 经藏名 | 仿宋, FangSong | Win 自带 | 掉到宋体 |
| 繁体正文/署名 | 新細明體, PMingLiU | **繁体 Win 自带；简体 Win 默认无** | 本机掉到 SimSun（简体字形）；他机繁体 Win 正常 |
| 繁体标题/偈颂 | 標楷體, DFKaiShu（真名 DFKai-SB） | 同上 | 本机掉到楷体/宋体 |
| 西文/数字 | Calibri, Arial, Times New Roman | Win/Office 自带 | 几乎不缺 |
| 注码 | Times New Roman（`output.notes_marker_font` 可改） | Win 自带 | 同上 |
| Ext-B/G 缺字 | SimSun-ExtB/ExtG | Win10+ 自带 | B 区以上缺字报 FB/TOFU |
| 缺字补充 | CBETA Supplement | **随仓 `cbeta/fonts/`**，双击安装 | 不装则 `>0xFFFF` 缺字无回退 |
| 悉昙 | Ranjana, Siddam | **随仓**，自装（CBETA 官方：[cbeta.org/downloads](https://cbeta.org/downloads)） | 不装则 rjchar 用主题字体直显（可读非梵形） |
| HTML 基底 | cbetarc（网络字体） | 非系统，需联网 | 离线 HTML 置换，PDF/DOCX 不走它 |
| 用户预设 | 朝华标题B, ZhaohuaMinB（`my.css`） | 第三方**免费商用**（用户提供，见下），非系统自带，他机需自装 | 他机标题回退黑体/宋体 |

### 缺字怎么办（三档）

1. **随仓三件**：`cbeta/fonts/CBETASupplement.ttf`、`Ranjana.ttf`、`Siddam.ttf`——右键安装即可；
   装完 `python -m pycbeta --list-fonts "Ranjana"` 应能列出。
2. **系统字本机缺**（常见于简体 Win 跑繁体：PMingLiU/標楷體/隸書）：系统设置加装“繁体中文语言包/附带字体”，
   或从繁体机拷 `mingliu.ttc/kaiu.ttf/simli.ttf` 安装。**不可随包分发**（微软授权），只能各机自装。
3. **第三方字**（如朝华标题B）：免费商用（https://zhuanlan.zhihu.com/p/2016459140264916053），
   常随 WPS 附带；分发样张给他人前，先确认对方已装，否则标题回退。

## 命令行参数

```
-i INPUT           XML 文件/目录/佛典編號（短编号 T0349 / 长编号 T25n1509 按册号消歧）；
                     存在文件按文件、存在目录按目录（目录内无 XML 且名恰为合法編號时按編號，
                     防同名目录劫持）；缺 XML 自动从官方下载；`-i ID:范围` 见 --juan
-o OUTPUT          输出文件或目录（默认源目录同名）
-f FORMAT          html,pdf,docx,md,epub,txt（逗号）或 all（含 txt）
--pdf-docx-theme  pdf/docx 标准 CSS（整套替换出厂 pdf_docx.css 全文）
--pdf-docx-user-theme pdf/docx 增量 CSS（名走 presets/ 双目录或路径，追加）
--html-epub-theme html/epub 基底 CSS（默认官方 html_epub_official.css，纯基底）；
                    epub 要印刷外观并落实正文字体传 `pycbeta/styles/epub_print.css`
                    （golden 电子书结构 + pdf_docx 印刷外观 + 正文字体：繁体明体 /
                    `--t2s` 简体宋体，卷名楷体；经文资讯尾页另页；整套替换）
--html-epub-user-theme html/epub 增量 CSS（已接线：名走 presets/ 双目录或路径，纯文本追加在官方基底之后，层叠后胜；GUI 样式表卡「html/epub 增量」行可设默认；缺文件警告回退基底）
--font-lang        字库：zh-Hant 繁体（默认）/ zh-Hans 简体（CSS :root 双栏变量切换；t2s 自动切简）
--t2s / --no-t2s   OpenCC 简体输出（默认联动简体字库；校验时官方文档同步转简体）
--font-scale 1.5   字号等比缩放（大字版 1.33/1.5；不影响校验）
                   仅 pdf/docx；html/epub 由阅读器原生缩放，不适用
--config           run.json 组合单（别名 --presets-file；5 槽见 docs/主题与样式.md），
                   或基础配置 JSON（config.user.json / presets 快照，当作 config-json 槽）；
                   缺省仓库根 run.json
--page             页面方案（缺省有效配置 default_page，出厂 a4；a4/a5/信纸/手机/平板8寸/平板9寸/平板11寸/32开/16开，键大小写不敏感）
--notes            footnote/endnote/inline（缺省取 config output.notes，出厂 footnote；footnote=页底脚注（docx/pdf），endnote=文末尾注，inline=括号内联；html/epub/md/txt 仅区分 inline 与否）
--strip-head-no    去 head/jhead 行首 No. 令牌（如 No. 1116-B 序→序），并省略 docNumber 编号行
                   （如 T0349 顶部 `No. 349 [No. 310(42)]`）；默认关，可配 output.strip_head_no；
                   docx 恒不显 docNumber，html/epub/md/txt 默认保留（同官方电子书），开此开关才省略
--show-notes / --no-show-notes  显示/关闭校勘注、脚注、尾注（显式 > config output.show_notes；默认显示；
                   仅关校勘/脚注/尾注，不关正文夹注；不影响 --verify——校验恒比注）
--engine 管线[:单体]  PDF 路径，见「PDF 引擎安装」；--vertical 竖排走 HTML 管线
--engine-tag       PDF 文件名追加实际引擎名
--xml-dir / --cbeta-ebook  本地 XML 候选源（只读，建议指向本地 cbeta-org/xml-p5 全仓库副本＝发布版 P5；非 P5 会在 GUI/CLI 告警）/ 电子书输出目录（唯一可写；平展一部一目录，XML+官方电子书同目录；不得与 xml_dir 相同。默认 config source.*；校验基线自动下载亦落此处，显式值优先于 preset）
                    P5a 源可用（管线不认版本照常转换），但校勘编码与发布版不同，正文可能重复/校勘注可能丢失，
                    校验对官方基线差异会偏大；P5/P5a 勿混放同一候选源目录（混放整批判非 P5）。
--name-template    输出文件名模板（[id][书名][作者][vol][juan]）；
                   缺省输出名 = `{佛典編號 书名}`（书名跟随 source.title_t2s 转简，如 `T0349 弥勒菩萨所问本愿经.docx`）
                   html 同形（单卷无后缀，多卷加 `_001` 起编号，如 `…_001.html`）。
--juan 范围        按卷范围选取子集（也可写 `-i ID:范围`，两者互斥）：
                   语法 `34` / `34-100` / `34-36,40,42-45`（`-`/`~`/`～` 三认一，`+` 同 `,`）；
                   官方分卷后缀形态亦可：`-i T0001_001` ≡ `-i T0001:1`（1–3 位归一，`:` 优先，
                   4 位以上/`_0` 按非法范围报错）；
                   选择覆盖全部卷时不裁剪、不加后缀（字节一致）；子集时输出名/校验目录加
                   `（卷34-36、40）` 后缀（`output.juan_suffix_template` 可改；显式 -o 文件路径不加）；
                   长编号如 `T25n1509` 按册号消歧（短编号同 canon+编号跨册重复时无法区分）。
                   校验：官方基线自动限定所选卷；html/txt_notes 缺哪卷下哪卷（单卷端点），
                   docx 无单卷端点整包下载；整包单文件基线（无 `_NNN`）保持红灯（预期）。
--verify [--verify-max-diff N] [--verify-diff-lines N]
                    生成后逐字校验（对比官方文档；阈值 缺+多≤N，出厂默认 10/5，校验预设已统一 0）；
                    `-i` 支持 单个 XML / 目录 / 佛典編號（目录/編號用已收集/材料化的 XML 逐个校验）；
                    比对档由正式管线 `generate_formal` 另生成（`verify` 段覆盖 `output` 段，与独立窗一致），
                    不改动实际产物。
                    跨边复用（下游 P2）要求两边阈值一致：`--verify-max-diff` **不读预设**，
                    若用预设 `verify.maxDiff`（如校验预设已统一 0）须显式传 `--verify-max-diff 0`
--verify-only      只校验已有产物：跳过渲染，用输出命名规则（`resolve_output`，未渲染故走默认名；
                    dedup 改名过的旧产物可能定位不到）定位既有生成档比对；
                    缺失产物报 `gen not found` 并计失败（退出码非零）；报告仍落 `{输出}（验证）/`
--font-check       豆腐字检测（逐字覆盖率报告 TOFU/SUP/FB/MISS，不中断渲染）
--list-fonts [关键词]  列出本机字体（家族名|路径），仅列表不渲染
```

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

- DOCX 后端链（默认管线，config.json `engines.docx2pdf.chain`）：msword → wps → docbuilder → libreoffice → minipdf，按序尝试
- HTML 引擎链（最后手段，`engines.html2pdf.chain`）：chromium → cbetapdf（Word 系全不可用才走）
- `--vertical` 竖排自动走 HTML 管线（DOCX 渲染器尚未实现竖排）

### 各后端说明

| 后端 | 说明 |
|---|---|
| msword / word | MS Word COM 导出（保真度最高，需 Office + pywin32）|
| wps | WPS Office COM 导出（需 WPS + pywin32）|
| libreoffice | soffice 命令行（自定义路径在 engines.paths 配置）|
| minipdf / docbuilder | 外部引擎（engines.external 注册，未安装自动跳过）；`minipdf.exe` 从上游下载（见「PDF 引擎安装」）放入 `engines/`；`cbetapdf.exe` 暂无公开下载（可选），有文件放 `engines/` 即可 |
| chromium / prince / weasyprint | HTML 管线引擎（最后手段）；prince 原生脚注/奇偶页分节；weasyprint Windows 需 GTK/Pango |

`docx2pdf` 复用 DOCX 渲染管线，PDF 与 DOCX 观感一致、带经文资讯尾页；
Word/WPS 走 COM 导出（需 pywin32），LibreOffice 走命令行。

> **已知（不改）**：源 XML 标题的全角空格（U+3000，如「緒　言」「第一章　釋尊略史」）经 DOCX→PDF（WPS/Word 系）导出后，PDF 里被编码为**定位间隙、无空格字形**，导致 **PDF 的拷贝/检索**把标题拆成两行。显示正常，逐字校验不受影响（折叠空白），DOCX/HTML/EPUB/TXT 拷贝正常。本管线保持与官方版式一致，不替换该空格。详见 `docs/功能清单.md` §7。

## 新增转换引擎

**方式一：外部命令行引擎（零代码）**

任何能通过命令行把输入转成 PDF 的程序，在配置文件的
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

**方式二：内置 Python 引擎（需改代码）**

- docx2pdf：写 `_pdf_via_xxx(docx_fn, pdf_fn)` 函数，注册进
  `render_pdf._DOCX_BACKENDS["xxx"]`；
- html2pdf：写 `_xxx_to_pdf(html_fn, pdf_fn)` 方法，加入
  `render_pdf.html_to_pdf` 的分派（内置三引擎 chromium/prince/weasyprint 在此）。

## 配置文件

- **`presets/config.factory.json`** — 出厂配置（2026-10-08 由 `pycbeta/config.json` 改名，
  与默认用户预设 `presets/config.user.json` 对称）：字库语言（font_lang）、页面方案（pages）、
  输出处理（output，含 docx 脚注分隔/字体回退/悉昙字体）、注音（annotations）、校验（verify）、
  转换引擎与后端链（engines）。支持 `//` 注释；复制后用 `--config` 指定。
- **`presets/config.user.json`** — 默认用户预设（v0.5 起入库标准预设；机器路径已清洗，
  他机开箱即用；`run.json` 默认指向；GUI「保存」写它）。`verify.maxDiff` 为 0（P2 跨边口径）。
- **`pycbeta/styles/pdf_docx.css`** — PDF/DOCX 默认主题（各语义标签的观感）。
- **`pycbeta/styles/html_epub_official.css`** — HTML/EPUB 官方格式基底（逐字节对齐官方）。
- **`presets/`** — 用户预设：配置 `*.json`（可自带主题键）+ 样式 `*.css` + 样张。

想改样式直接编辑对应文件；`--pdf-docx-theme`（整套替换）/`--pdf-docx-user-theme`（增量追加）用于主题层。
详见 `docs/主题与样式.md`。

## 数据源与官方书库（可选，推荐）

- **电子书输出目录**（`source.cbeta_ebook`，**必填**）：唯一可写工作根；XML 与官方电子书平展落
  `{id} {书名}/`。GUI 数据源窗口设一次。
- **本地 XML 候选源**（`source.xml_dir`，可选）：本地 `cbeta-org/xml-p5` 全仓库副本（发布版 P5），
  只读；有则免下载 XML。
- **官方书库**（`source.baselines.*` / `baselines_root`，可选，**做逐字校验强烈推荐**）：
  CBETA 官方整批发布，如 **2026r2**（含 `html` / `docx` / `epub` / `text-with-notes` 等格式），
  从官方下载页获取：https://cbeta.org/downloads
  - **好处**：① 逐字校验的官方基线来源（不配则每次现下，慢且依赖网络）；② 本地一份可离线、
    批量校验快；③ 各格式齐，校验覆盖面全。
  - **配置**：数据源窗口「本地官方电子书」tab 指定各格式目录（按目录名自动检测
    `text-with-notes`/`docx`/`epub` 等）；或手改 `source.baselines_root` 指向书库根（如 `E:\CBETA\2026r2`）。

## 校验与测试

```bash
# 单元测试（外部数据用例需指向 CBETA 电子书库，缺失则自动跳过）
#   开发机可把路径写 pycbeta/tests/.data_root（已 gitignore），或设环境变量：
set PYCBETA_TEST_DATA=D:\CBETA\cbeta_ebook
python -m unittest discover -t . -s pycbeta.tests

# 端到端转换测试（test/*.xml -> test/out/<格式>/）
python test\run_tests.py                 # 全部 XML 全格式
python test\run_tests.py -f docx,pdf     # 指定格式
python test\run_tests.py --pages a4,a5   # 多页面方案各出一版（默认 a4,a5,phone,tablet）
python test\run_tests.py --pdf-engine docx2pdf

# 逐字校验回归（对比官方文档）
python test/verify_text.py --source D:\CBETA\cbeta_ebook -f html,docx --max-diff 10        # 繁体回归
python test/verify_text.py --source D:\CBETA\cbeta_ebook -f html,docx --max-diff 10 --t2s  # 简体回归
python test/verify_text.py --source D:\CBETA\cbeta_ebook -f txt --baseline xml             # P3 辅轨：IR→TXT vs 输入XML直抽（查解析层丢字）
```

## 常见问题

- **控台中文乱码**：Windows gbk 控台打不出 ExtB/G 生僻字与拼音声调，程序内已降级显示；
  完整内容看落盘文件（`font-check-<id>.txt`、verify `report.txt` 均为 UTF-8）。
- **首次运行慢**：冷盘 + Defender 扫描 + Python 预热，第二次即正常；与功能开关无关。
- **LibreOffice 升级/改路径**：同步改 `engines.paths.libreoffice`，安装前先杀常驻 `soffice.bin`。
- **WPS 看不见 w:ruby 上方注音**：WPS 只认自家 EQ 域，注音 `style` 改 `field`
  （`ruby_up` 默认 100% 正文字号防相交）；LibreOffice 下用 `inline`。
- **`--font-lang zh-Hans` 只换字库不转文字**，转文字用 `--t2s`。

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
  theme.py         主题：语义标签 -> 各格式样式；出厂配置加载
  presets/config.factory.json  出厂全局配置（字体/页面/输出/引擎链；只读）
  styles/          html_epub_official.css / pdf_docx.css / epub_print.css
docs/              设计报告与规格
test/              run_tests.py 端到端测试 + 样例 XML
```

## 渊源

CBETA 佛典編號/册号规则（`pycbeta/names.py`）移植自
[RayCHOU/ruby-cbeta](https://github.com/RayCHOU/ruby-cbeta) 的 `cbeta.rb`
（Copyright (c) 2016 Dharma Drum Institute of Liberal Arts, MIT License），
其余为独立重写；与上游无 fork 关系、无共享历史。本仓代码采用 **GNU GPL v3**（见根 `LICENSE`）。

> 注：`cbeta/fonts/` 下的 `CBETASupplement.ttf`、`Ranjana.ttf`、`Siddam.ttf`
> 均由 CBETA 官方提供（下载页 [cbeta.org/downloads](https://cbeta.org/downloads)）；字体按各自原始授权分发，
> 不受本仓 GPL 变更影响（`CBETASupplement.ttf` 注明供非营利/研究使用）。
