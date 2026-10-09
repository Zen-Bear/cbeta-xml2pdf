# GUI 设计（xml2pdf 侧）

> 依据外部下游项目（publish）的「链路B-设计契约」（唯一契约）。本文件仅设计，**不包含代码**；
> 实施阶段产出：`pycbeta/gui/panel.py`、`pycbeta/gui/__main__.py`，依赖 `PySide6>=6.6`。

---

## 1. 目标与分工

- `xml2pdf` 侧交付**可复用 UI 组件** + 独立转换窗；`publish` 侧集成（右栏面板/中栏来源列/合成分流）。
- 纸张/字体/引擎等**单一逻辑归属 `xml2pdf`**（出厂 `presets/config.factory.json` 的 `pages/font_lang/engines`），publish 不重复实现。
- 模块化钩子已就绪：`pycbeta/fetch.py:230 fetch_work`、`pycbeta/verify.py:278 verify_one`、`pycbeta/cli.py:51 render_one`（见 `docs/第三方调用说明.md`）。

## 2. 数据模型 `XmlOptions`（扩展版）

```python
@dataclass
class XmlOptions:
    page: str = "a4"                    # pages 键（a4/a5/信纸/手机/平板8寸/9寸/11寸/32开/16开；大小写不敏感）
    font_lang: str = "zh-Hant"         # 字库语言（CSS :root 双栏；t2s 自动切简）
    engine: str = "docx2pdf"            # docx2pdf[:wps] | html2pdf[:chromium]
    margins: dict = None                # None → pages[page].margins
    formats: list = None                # None → [pdf]；如 ["pdf", "epub"]
    output: dict = None                 # output 覆盖（见表「GUI 可回存参数」）
    font_scale: float = 1.0             # 字号等比缩放（大字版 1.33/1.5；字号不影响逐字校验）
    pagination: dict = None             # 智能分页 {enabled,duplex,juan,juan_first,mulu_levels,mulu_zhang_break,mulu_smart_merge,mulu_smart_max_frac,pb,tei}
    series_title: dict = None           # 经藏名 {enabled,font,size}
    t2s: bool = False                 # OpenCC t2s 简体输出（正文/注释/元数据；未指定 --font-lang 时自动用简体字库；校验时官方文档同步转简体）
    verify: dict = None                 # 可选：转换后校验 {enabled:bool, formats:list}
```

### 2.1 出厂配置参数分类（`presets/config.factory.json`；GUI 可改并回存到用户预设）

| 分组 | 参数（config 键） | 控件 | 回存目标 |
|---|---|---|---|
| 页面 | `pages.<page>` | 下拉 | `xml_options.page` |
| | `pages.<page>.margins`（可选） | 数字输入（四边） | `xml_options.margins` |
| | `output.grayscale` | 复选「黑白输出」 | `output.grayscale` |
| | `output.page_border` | 复选「页面边框」 | `output.page_border` |
| | `output.page_border_style` | 下拉「样式：单线/双线（古籍）」（未勾选禁用） | `output.page_border_style` |
| | `output.page_border_width_pt` | 数字输入「内框宽度」（0.25–3 pt；未勾选禁用） | `output.page_border_width_pt` |
| | `output.page_border_color` | 按钮「内框颜色」（调色板，存 `#RRGGBB`；未勾选禁用） | `output.page_border_color` |
| | `output.pdf_zoom` | 数字输入「PDF 缩放」 | `output.pdf_zoom` |
| 字体 | CSS :root 双栏变量 | 字库两态（繁/简） | `xml_options.font_lang` |
| 引擎 | `engines.docx2pdf.chain` / `html2pdf` | 单选+单体下拉 | `xml_options.engine` |
| 输出格式 | — | 多选 `pdf/epub/docx/html/md` | `xml_options.formats` |
| | `output.font_scale` | 数字输入「字号缩放」（大字版 1.33/1.5） | `output.font_scale` |
| | `output.t2s` | 复选「简体转换」（OpenCC t2s；未指定 --font-lang 时自动用简体字库；校验时官方文档同步转简体） | `output.t2s` |
| 注释 | `output.notes` | 下拉「注释方式」页底脚注/文末尾注/括号内联（纯三值，出厂 footnote） | `output.notes` |
| | `output.show_notes` | 复选「显示注释」 | `output.show_notes` |
| | `output.footnote_per_page` | 复选「脚注每页重新编号」 | `output.footnote_per_page` |
| | `output.inline_brackets` | 下拉「正文夹注」全角/半角（`<note place="inline">` 原文夹注） | `output.inline_brackets` |
| | `output.note_inline_brackets` | 下拉「校注内联括号」〔〕/[]/全角（）/半角()（`corner`/`square`/`fullwidth`/`halfwidth`，默认 fullwidth；〔〕[] 优先，与正文夹注区分；**注释方式≠括号内联时置灰**） | `output.note_inline_brackets` |
| | `output.suppress_title_notes` | 复选「压制标题注码」 | `output.suppress_title_notes` |
| 排版 | `output.split_juan` | 复选（各选项右侧附**灰色括号说明**，短同行、长置下一行）：按卷分文件/显示结束卷标题/卷名去重/去掉标题行首 No./CBETA校改字标红/忽略 XML 样式·空格脏数据/偈颂分隔符/去掉偈颂首尾引号 | `output.split_juan` |
| | `output.show_close_juan` | 复选「显示结束卷标题」 | `output.show_close_juan` |
| | `output.suppress_jhead_dup` | 复选「卷名去重」 | `output.suppress_jhead_dup` |
| | `output.strip_head_no` | 复选「去掉标题行首 No.」 | `output.strip_head_no` |
| | `output.corr_cbeta` | 复选「CBETA校改字标红」（默认关） | `output.corr_cbeta` |
| | `output.ignore_xml_style` / `ignore_xml_space` | 复选（脏数据忽略） | `output.*` |
| | `output.verse_caesura` / `verse_strip_quotes` | 输入/复选（偈颂） | `output.*` |
| 分页 | `output.pagination.*` | 分组复选（各选项右侧**灰色括号说明**）：智能分页=总开关（关则下列全失效）；双面打印=每卷单数页起；卷首换页=每卷开头另起一页（第 1 卷默认与书名同页）；首卷换页=第 1 卷也另起一页、书名独占首页（需勾选卷首换页）；目录换页 level=开关（默认开）+下拉（仅 level-1（默认）/level-1+2/level-1+2+3/level-1+2+3+4），选中 level 的目录各自另起一页（epub 同步按此拆章节）；章独立成页=开关（默认开）mulu 形如「第X章」时无视 level 独立成页、章恒不参与合页（epub 同步拆章）；空标题并入下节=开关（默认关）本节只有标题、无正文时与下一节同页（同卷内；复用"空则不切"机制）；短节智能合页=level≥2 的短节（前一节**估算**占页不足所选比例，默认 1/3；按当前纸张/边距/字号/行距估算）与下一节同页（仅 DOCX 及 docx2pdf 派生的 PDF，可关；下拉含 level≥2 才生效）；按 pb 分页=按 `<pb>` 刻本页边界；尾页换页=末尾【經文資訊】另起一页 | `pagination.*`（`mulu_levels`/`mulu_zhang_break`/`mulu_heading_merge`/`mulu_smart_merge`/`mulu_smart_max_frac`；旧键 `mulu_level1` 兼容） |
| 经藏名 | `output.series_title.*` | 复选+字体+字号 | `series_title.*` |
| 校验 | `verify.enabled/maxDiff/diffLines/auto_fetch/scope_juan` + `output.convert_report` | 高级页（转换后校验开关**默认开** + **转换报告开关默认开**/阈值/报告差异行数/自动下载/卷限定 + 「清理校验产物…」按钮） | `verify.*` / `output.convert_report` |
| 注音 | `annotations.enabled` / `full_text` | 三选一**单选按钮**「无注音 / 难字注音 / 全文注音」（全文含难字；`QRadioButton` 同组互斥）+ 方案/位置/括号/频率/词表（词表**只读**，浏览选择，默认内置表）；`rare_zones`/`rare_font` 走 config | `annotations.*` |

**不适合 GUI 修改**：`source.xml_dir/cbeta_ebook`（路径，数据源窗口只读框走浏览；`catalog` 钉死内置）、`downloads.*` URL 模板（数据源窗口 tab1 可改，存当前选中预设）、`source.title_t2s`（数据源窗口复选）。

### 2.2 回存语义
- 面板 `set_options()` 以 `load_presets()` 的 `output/pagination/series_title` 为默认值回填，未勾选项不写入（保持继承）。
- publish 侧持久化整个 `XmlOptions` → `collection.xml_options`；独立窗「保存配置」可写用户配置文件（JSON，路径可选）。

## 3. 可复用组件 `pycbeta/gui/panel.py`

### 3.1 `XmlOptionsPanel(QWidget)`（选项卡分组）

```
┌─ XmlOptionsPanel ─────────────────────────────────────────────┐
│ [页面] [字体] [输出格式] [注释] [排版] [分页] [经藏名] [校验]  │
├───────────────────────────────────────────────────────────────┤
│ 页面:                                                         │
│   纸张 [a4 ▼]    边距 [使用页面预设 □]  上[ ] 下[ ] 左[ ] 右[ ] │
│   ☐ 黑白输出(grayscale)  ☐ 页面边框(page_border)  样式[单线 ▼] 内框宽度[0.75 pt] 内框颜色[#333333]（未勾选禁用） │
│   佛典丛书名 ☑ 首页打印  （经藏名 title level="s" 仅首页左上角；字体/字号走 CSS） │
├───────────────────────────────────────────────────────────────┤
│ 字体:  [default ▼]（CSS :root 双栏变量，繁/简两态）           │
├───────────────────────────────────────────────────────────────┤
│ 输出格式: ☐ pdf ☑ epub ☐ docx ☐ html ☐ md                     │
│ 引擎: (•) docx2pdf  ( ) html2pdf     单体 [自动 ▼]            │
│       ☐ 简体转换（OpenCC t2s；校验时官方文档同步转简体）             │
├───────────────────────────────────────────────────────────────┤
│ 注释: 正文夹注 [全角（） ▼]                                    │
│       ☑ 正文显示悉昙字和读音                                  │
│       ──────────────────────────────                          │
│       注释总开关 ☑ 显示注释                                    │
│       ☑ 脚注每页重新编号 ☐ 压制标题注码                        │
│       注释方式 [页底脚注 ▼] 校注内联括号 [全角（） ▼]（非括号内联时置灰） │
├───────────────────────────────────────────────────────────────┤
│ 排版: ☐ 按卷分文件（每卷单独成文件）                          │
│       ☐ 显示结束卷标题（打印卷末 close 标题；默认关）         │
│       ☑ 卷名去重（卷头与书名重复时去重；默认开）              │
│       ☐ 去掉标题行首 No.（如 No. 1116-B 序→序）               │
│       ☐ CBETA校改字标红（默认关；与逐字校验无关）             │
│       ☐ 忽略 XML 样式脏数据（默认关；保留原文）               │
│       ☐ 忽略 XML 空格脏数据（默认关；保留原文）               │
│       偈颂分隔 [　　]（<caesura/> 处分隔，默认两个全角空格）  │
│       ☐ 去掉偈颂首尾引号（去掉「」『』）                      │
│       ☐ 预排去缩进 [最多去 4]（每行行首最多 N 空白；默认关）  │
│       ☑ 书名超长换行（超行在空格/成对破折号处换行；默认开）  │
├───────────────────────────────────────────────────────────────┤
│ 分页: ☐ 智能分页（总开关）                                    │
│       ☐ 双面打印（每卷单数页起）                              │
│       ☑ 卷首换页（每卷开头另起一页）                          │
│       ☐ 首卷换页（第1卷也另起一页，书名独占首页）             │
│       ☑ 目录换页 level [仅 level-1（默认）▼]（序/品各自另起一页）│
│       ☑ 章独立成页（第X章无视 level 独立成页；恒不参与合页）   │
│       ☐ 空标题并入下节（本节只有标题、无正文时与下节同页）     │
│       ☑ 短节智能合页 不足[1/3 页]（level≥2 短节与下节同页；估算）│
│       ☐ 按 pb 分页（按刻本页边界；默认关）                    │
│       ☑ 尾页换页（【經文資訊】另起一页）                       │
├───────────────────────────────────────────────────────────────┤
│ 校验(高级): ☑ 转换后校验 ☑ 转换报告  阈值[10]  报告差异行[5]    │
│       ☑ 官方文档缺失自动下载（首选基线缺失时自动下载）         │
│       ☑ 按卷限定官方文档（只用实际覆盖卷的官方 _NNN 基线）      │
│       [清理校验产物…]                                          │
└───────────────────────────────────────────────────────────────┘
```

接口（同前）：
- `get_options() -> XmlOptions` / `set_options(opts)` / 信号 `optionsChanged(XmlOptions)`
- 每个选项卡控件值变更即写回内存中的 `XmlOptions`，`get_options()` 汇总

> 注（2026-09-06）：上图为初版草图，当前实际为八卡——输出格式 / **样式表** / 页面 / 分页 /
> 排版 / 注释 / 注音 / 校验。样式表卡 = CSS 下拉（当前默认第一+（默认）标记）+ 设为默认
> + 打开用户目录 + 两默认 CSS 路径（可打开）+ **「html/epub 增量」行**（2026-10-07：
> `CssComboBox` 出厂三件套参数化，默认"无（官方原样）"；下拉选 css 后"设为默认"写
> run.json `html-epub-user-theme` 槽；追加在官方基底之后，层叠后胜；`set_user_theme`
> 加 `slot` 参数）；输出格式卡有"模式"组
> （竖排直书 + 简体转换 + 字库繁简两态同行，竖排在左；GUI 经 `--vertical`/`--font-lang` 进子进程；
> 复选框长说明收进 tooltip）；注音卡词表行下有实际路径
> hint + 打开按钮；注释卡注码相关项、引擎组（单引擎+自动）说明同样收进 tooltip；
> 面板顶部槽标签显示“当前配置：<预设名>”（“当前配置”为链接、点击打开 run.json；
> 名字固定宽度、超长省略号，tooltip 全名）；数据源按钮在主窗口输入来源
> 同行最右（`SourceDialog` 共用）。
>
> CSS 编辑器（2026-09-06，`pycbeta/gui/css_editor.py`）：`CssEditorDialog`（样式表卡“打开 CSS 编辑器”按钮弹窗；
> publish 侧同样 import 即用）+ `python -m pycbeta.gui.css_editor --sample X.xml` 独立运行。
> 左调参（标签分组字体双栏繁简 + 字号粗细颜色 + 源码页，控件预填有效默认值、只输出碰过的项，左栏可滚动，预览繁简可切）/ 右 QTextDocument 模拟预览（读 `DocxRenderer`
> 刚写出的 run 真值；注文尾注归并；分页以 Word 为准）/ 底导出样张 DOCX+PDF（PDF 跟主窗口
> 引擎链）+ 恢复出厂（装载出厂缓冲）。
>
> 编辑器行按书本排版顺序（经藏名→书名→序→作者译者→卷品→标题→正文→偈颂→夹注→注码注文→
> 注锚→行内字体）；`pdf_docx.css` 文件本身不动。控件不认识的规则（标题 level 属性选择器、
> 注记偈行等）原文透传，改控件不丢失。字体下拉可编辑可搜（editable+NoInsert 打字过滤；
> 中文/字库单名自动补同字体英文别名 data="名, 别名"、框只显示一个名字；lost-focus 匹配选项
> 自动选中、不匹配警告+复原；跨字体/未装栈载入走临时项不堆积；无空白占位）；粗细三态按钮
> （默认灰=未覆盖/加粗/常规，点击轮换）；颜色 26×26 纯色块（无文字，右键清除）；左栏行
> tooltip 标 cb 标签（双向查找）；启动自动载入 run.json 默认主题（保存亮）。
>
> 预设库（单目录 `presets/`，入库随包分发）：样式 `*.css` + 配置 `*.json` 混放（按扩展名区分）
> + 样张 `sample.xml`；内置 `pycbeta/styles/presets/`（删不掉）。编辑器顶部预设行切换只装载（切换/另存/删除用户预设）；
> "设为默认"写 run.json 的 `pdf-docx-user-theme`（面板样式表卡同动作）；`恢复出厂`只装载出厂缓冲（不删预设、不改默认）。
> 面板配置框预设下拉：一切以选中项为准——`presets/*.json`（首项“（出厂默认）”=空；
> 出厂文件 `presets/config.factory.json` 不是可选预设，`list_config_presets` 排除）。
> 选中即载入；**保存**=覆盖选中（出厂默认项置灰，出厂只读）；**另存…**=新建；
> **删除**=删选中（删除前确认；删的正是默认指向的预设则自动清空槽，避免悬空警告）；
> **设为默认**=run.json 的 `config-json` 槽指选中（出厂默认=清空槽）；
> 保存/设默认等成功后配置框标题常驻最后动作（如“配置（已保存）”，换预设/还原出厂后复原）。
> **还原出厂**=面板回 `presets/config.factory.json` 值（不写盘）。默认用户预设 =
> `presets/config.user.json`（v0.5 起入库标准预设，机器路径已清洗；run.json 默认指向）。出厂文件 GUI 永不写；
> 要改出厂默认需手动编辑该文件（2026-10-08 由 `pycbeta/config.json` 改名，带注释）。
> 运行组合单见 `run.json`（5 槽；`config-json` 可指 `presets/*.json`）。
>
> 备忘（2026-09-06）：预览技术选型 QTextEdit vs QWebEngineView，以后再议——
> QTextEdit 胜在毫秒刷新/逐 run 可编程（注文归并/缺字点名）/单测友好/零依赖，
> 劣在无真分页竖排；WebEngine 胜在像素级真效果（@page/vertical-rl/printToPdf 即成品），
> 劣在秒级刷新/内存大/DOCX 链路作废（只认 HTML，ruby/EQ 注音特性看不见）/单测打包成本高。
> 结论：调字体字号颜色保持 QTextEdit；HTML 竖排精品预览若立项再上 WebEngine（P11 预留）。

### 3.2 `XmlOptionsDialog(QDialog)`
面板的对话框包装：`exec() -> Optional[XmlOptions]`（Accept→选项；Cancel→None），`[确定][取消]`。

### 3.3 `SourceDialog` / `DataUpdateDialog`（数据源窗口）
- `SourceDialog`：路径行 `xml_dir` + `cbeta_ebook`（均只读+浏览；后者清空确定时弹必填警告）；`catalog` 钉死内置（tab2 的佛典目录映射表行即其位置与更新状态）。
- 表格改两 tab：tab1「电子书下载模板」（`downloads.*`，键列只读，值可改，确定存当前选中预设）；tab2「官方数据更新源」（`remote_sources.json` 全表只读：数据项/更新 URL/本地文件/上次更新）。
- 「更新官方数据」按钮开 `DataUpdateDialog`：更新源列表 + 「开始更新」（后台线程，`dry-run` 仅检查）+ 逐行状态；「更新XML」按钮逻辑不动。

## 4. 独立窗 `python -m pycbeta.gui`

### 4.1 输入两种模式

```
┌─ xml2pdf（独立窗） ────────────────────────────────────────────┐
│ 输入来源: (•) 目录/文件  ( ) 佛典編號列表 [?]                [◂] │
│ 目录/文件: [XML 目录 / 单个 .xml]  [目录…]                   │
│ 編號列表:  [T0349, X1116, T0001:1-2（逗号/空格分隔；卷用 ID:范围）] [文件…] │
│            ☐ 自动下载缺失 XML（官方源）                         │
│            ☐ 同时下载官方电子书（html/docx/txt_notes 供校验）   │
│ 输出     [………………]  [浏览]                                    │
│ 设置     [XmlOptionsPanel 嵌入]                                │
│ ┌─ 批量列表 ────────────────────────────────────────────────┐ │
│ │ 经号        经名              来源    状态    进度          │ │
│ │ T0349      彌勒菩薩所問本願經  本地XML  转换中  ████░░ 40% │ │
│ │ X1116      毗尼日用切要香乳記  已下载  待转换  ░░░░░░  0%  │ │
│ └───────────────────────────────────────────────────────────┘ │
│ [转换] [取消]   ██████████░░░░░░░░ 进度条                      │
└──────────────────────────────────────────────────────────────┘
```

独立窗启动参数（publish 一键送校验用）：`--ids-file/--out/--preset/--formats/--verify/--verify-root/--autostart`（`--verify-root` 只本次运行覆写校验根，见第三方调用说明 §6.3）。

输入帮助（C 方案）：输入来源行「佛典編號列表」右「？」按钮弹输入说明对话框（三形态 + 卷语法，文本 `gui.__main__.input_help_text()`，publish 可复用；`_input_help_dialog` 构造与展示分离可测）；对话框用 QLabel wordWrap（QMessageBox 按词边界换行、CJK 长行不断行）+ 最小宽 520 + 文本可选中；编号框 tooltip 为同内容精简版（显式换行）；「文件…」tooltip 注明列表 token 可带 `:范围` 后缀；CLI `-i` help 同步一句卷后缀说明。

### 4.2 佛典編號列表流程（走当前逻辑）

对列表内每个 ID：
0. **token 语法**：`T0349` / 长编号 `T25n1509`（按册号消歧）/ 卷范围 `T0349:2-3`、`T25n1509:34-100`（`:`/`：`；多段用 `+`，因 `,` 是列表分隔符）/ 官方分卷后缀 `T0349_002` ≡ `T0349:2`（1–3 位，`:` 优先）；token 间用空白/`，`/`;`/`；`/`、`分隔，`#` 后为注释，大写归一；非法编号标「非法編號」红字，非法卷范围标「非法卷范围」红字（`parse_work_ids_file`，`.txt` 列表同规则）
1. `fetch.is_work_id(id)` 校验（长编号先归一短编号+册号）；`parse_work_id` → `(canon, no)`
2. **三源材料化**：`fetch.materialize_work(id, presets, xml_dir, cbeta_ebook)`
   - `cbeta_ebook/{id} {书名}/` 已有 → 直接用（来源标「本地XML」）
   - `xml_dir`（只读候选源；**建议指向本地下载的 cbeta-org/xml-p5 全仓库副本（发布版 P5）**，勿指 CBReader）有 → 拷贝/碎片按组合册落 work 目录（来源标「本地拷贝/合册合成」）
    - **xml_dir 版本抽检**：`fetch.inspect_xml_source(xml_dir)` 抽样读 `<edition>`；非「XML TEI P5」（P5a/P5b）→ GUI 弹窗「仍使用 / 清除该路径 / 取消」（默认高亮清除；「清除」写回当前选中预设 `source.xml_dir=""`），转换首次也兜底检一次；CLI 打印警告后继续
   - 勾选「自动下载缺失 XML」且前两源无 → `fetch.fetch_work(id, ["xml"], presets, cbeta_ebook)`（来源标「已下载」）
       - 全无 → 行状态标「缺 XML」跳过
   - **列表预填**（转换开始前）：`materialize_work(..., dry_run=True)` 只预测来源标签（不拷贝/不合册/不下载），配合 catalog 经名，把每行「经名/来源」在「待转换」阶段先填好（后面的书不再等到轮到它才显示）；实际转换时用准确值覆盖，解析失败则清空来源。每轮开始还把光标/视图复位到第一行的「文件」列
3. **（可选）官方电子书**：勾选「同时下载官方电子书」→ `fetch.ensure_baselines(id, ["html","docx","txt"], presets, cbeta_ebook)`（落 work 目录；docx/odt 非 T/X 静默失败）
4. **转换**：`cli.render_one` 或子进程 `[sys.executable, "-m", "pycbeta", "-i", xml, "-f", fmt, "--page", opts.page, "-o", out_dir]`（`t2s=True` 时追加 `--t2s`；子进程 stdout 强制 `PYTHONIOENCODING=utf-8`，中文产物名方可回读）。**默认产物名 = `{佛典編號 书名}`**（`filename.default_output_name`，书名跟随 `source.title_t2s` 转简；`--name-template` 显式覆盖，html 仍 renderer 内部命名）。**卷范围（编号后缀）**：编号 token 支持 `T0349:2-3` / `T25n1509:34-100`（多段用 `+`，因 `,` 是列表分隔符；长编号按册号消歧）——`_make_id_job` 拆 `wid/vol/juan`（非法范围标「非法卷范围」红字）；命令追加 `--juan`；`_juan_plan` 按解析出的实际卷数决定是否加 `（卷…）` 后缀（全覆盖=不加，与 CLI 一致）；输出名/校验目录/报告目录同名加后缀（`output.juan_suffix_template` 可改）
5. **（可选）校验**：`verify.verify_one(xml, fmt, source, out_root)`，进度条把校验计入总单元；行状态显示 `完成｜校验 OK/失败N/无对照N` 并按结果着色（通过绿 `#2e7d32` / 失败红 `#c62828` / 无对照灰）；某行确认有 XML 待转换后状态列先由「待转换」转 `转换中…`（解析/下载阶段仍显示「待转换」），进入校验再示 `校验中（fmt）…`；**校验产物独立成 `{输出}/{id 书名}（验证）/` 子目录**（内部保持 `{fmt}/` 结构：重生成文件 + 各格式 `*_compare_*.txt` + `report.txt`；渲染输出仍在输出根），文件列依次为「渲染产物 + **验证总报告 `{id 书名}（验证）/{stem}_verify_report.txt`（排最后）**」，均可单击打开（各格式 `*_compare_*.txt` 仍落盘但**不列文件列**）；总报告由 `verify.format_verify_report(records, diff_lines, max_diff)` 生成，**逐条列出每个尝试过的对照**：`[OK]|[FAIL] ({fmt}→{对照kind} 缺X/多Y ≤|>阈值N)` + `【源】/【新】` + 前 N 条【源】【新】差异（N=`verify.diffLines` 默认 5，绿灯但非 缺0/多0 也列）；全部结束弹 `VerifySummaryDialog` 汇总（通过/失败/无对照计数 + 逐项明细 + 「打开报告目录」，失败不强制弹窗）。信号：`row_verify(int, level)`、`verify_result(dict)`（简体转换开启时官方文档同步转简体后比对）。**PDF 走源格式校验**：`docx2pdf`→按 docx、`html2pdf`→按 html；源格式已选中则标灰色「已覆盖」不重复，未选中则委托该类校验（显示 `pdf→docx`/`pdf→html`）

> 校验卡「清理校验产物…」：确认后删除**输出目录**下全部 `{id 书名}（验证）/`（及 `（驗證）/`）子目录——可重生成的中间产物，成品不受影响；完成后提示删除数量。清理逻辑 `panel.clean_verify_dirs(out_dir)`（纯函数，可单测）。

> **转换报告**（`output.convert_report`，默认开；`--no-convert-report` 关）：记录渲染期间一切特殊处理与对原文的改动，落 `{输出}/{id 书名}（验证）/{id 书名}_转换报告.txt`（与校验报告同处；各格式中间件落 `（验证）/{fmt}/{id 书名}_转换报告_{fmt}.txt`，GUI 行末合并为一份并只列合并件）。条目含**物理 XML 行号**与内容摘要，连续序号、条间空行；覆盖：字体替换（GDI 归一/按字回退）、字体缺失/无法验证、缺字字形、悉昙字体、预排去缩进/空行、标题折行、去标题行首 No.、忽略脏数据（style/空格）、卷名去重、偈颂去引号、内容丢弃（cb:tt/sic/docNumber）、注音待审、简繁转换、注释/悉昙/校改开关、图缺失、其它显示调整（□/space/◎ 计数）、输出改名/净化、主题/页面兜底。收集器 `pycbeta/report.py`（渲染器零 IO，仅 CLI/GUI 落盘）；开关与查看方式同校验报告（文件列单击打开），**转换报告排在文件列最后**。

批量列表列：`经号 | 经名 | 来源（本地/已下载/官方电子书） | 状态 | 文件`；`QThread` + 信号更新；取消中断后续。进度条按 **(job × 格式 × 实际 XML 数)** 计单位——一个编号可能材料化出多个 XML（如 TX0001→TX01n0001/TX02n0001），解析出 `xmls` 后动态校正总数（空 job 扣预算），避免跑完第一个 XML 就冲到 100% 后干等。

### 4.3 目录/文件模式
`目录…` 选目录：递归扫描 `**/*.xml`（排除 `out/`）填充批量列表；`文件…` 选单个 `.xml`（单文件转换）或 ID 列表 `.txt`（如 `test/mini-test.txt`，逐行取 `is_work_id` 命中的 token，去重保序 → 生成「佛典編號列表」批量，走材料化/自动下载）；其余同流程（来源列统一「本地XML」）。解析：`gui.__main__.parse_work_ids_file`。

## 5. publish 集成（契约 §3-4，由 publish 侧实施）

### 5.1 配置持久化 `publish/config/app.json`
```json
{
  "default_source": "official",          // official | xml
  "xml2pdf": { "path": "D:/xml2pdf",
               "options": { "page": "a4", "font_lang": "zh-Hant", "engine": "docx2pdf",
                            "output": {"grayscale": false, "show_notes": true},
                            "pagination": {"enabled": false, "duplex": false},
                            "series_title": {"enabled": true} } }
}
```
集合 JSON 新增：`source`（继承全局）、`work_sources: {经号: official|xml}`、`xml_options: {…XmlOptions 全量…}`；
兼容旧 JSON（缺字段 → `official`，`xml_options` 缺字段 → 继承 `app.json xml2pdf.options`）。

### 5.2 publish 右栏（来源设置）
```
来源: (•)跟随集合  ( )官方  ( )本地XML   [设置…]
```
- 三单选写 `collection.source`；`[设置…]` → `exec XmlOptionsDialog` → 存 `collection.xml_options`
- 单选 `跟随集合` 时显示继承后的实际值（灰显来源名）

### 5.3 publish 中栏（丛书列表）
`QTreeWidget` → `QTableWidget`，列：`经号 | 经名 | 来源[官方|XML▼]`
- 第 3 列为下拉：缺省显示继承集合级；改值写 `work_sources[经号]`
- 批量：多选行 → 右键/按钮「设为官方」「设为XML」

### 5.4 合成分流（数据流）
```
[合成] → 读 work_ids + work_sources
  ├─ source=="xml"     → xml2pdf_bridge.batch_convert(works_xml, XmlOptions, progress_cb)
  │                      （内部 cache_manager.ensure_xml → subprocess pycbeta 转换）
  └─ source=="official" → official_ebook_source.download_ebook → cbeta_ebooks
→ ebook_merger 单一格式合并（支持分册）
```

### 5.5 桥接口 `publish/src/books/xml2pdf_bridge.py`
```python
def batch_convert(work_ids: list[str], out_dir: Path,
                  opts: XmlOptions, progress_cb) -> dict[str, Path]:
    # 1) 确保 XML：fetch.materialize_work（cbeta_ebook → xml_dir → 下载）
    # 2) 每部：subprocess [sys.executable, "-m", "pycbeta", "-i", xml, "-f", fmt,
    #                     "--page", opts.page, "-o", out_dir]
    # 3) progress_cb(done, total, work_id)
```

## 6. 文件布局（实施产出）

```
pycbeta/
  gui/
    __init__.py        # 空
    panel.py           # XmlOptions / XmlOptionsPanel(选项卡) / XmlOptionsDialog
    __main__.py        # python -m pycbeta.gui 独立窗（目录/文件 或 佛典編號列表）
requirements.txt       # 追加 PySide6>=6.6（publish 侧已含）
```

## 7. 实施顺序（后续 build）

1. `pycbeta/gui/panel.py`：`XmlOptions`（含 output/pagination/series_title/verify 覆盖）+ 选项卡 Panel + Dialog（复用 `load_presets()`）
2. `pycbeta/gui/__main__.py`：独立窗（目录/文件 + 佛典編號列表两种输入；find_local_xml → fetch_work 下载 XML → 可选 ensure_baselines → 批量转换 + 进度/取消）
3. 冒烟：`python -m pycbeta.gui` 单文件/ID 列表转 pdf/epub；ID 列表含未下载经（如 A1057）验证自动下载；publish 侧 `sys.path += ["<xml2pdf 仓库路径>"]` 引入 `XmlOptionsPanel`
4. publish 侧（契约 `publish/TODO.md:P1 链路B`）：config/collection 字段、bridge、中栏/右栏、[合成] 分流
5. 验收：链路 B 端到端（XML 源 → pdf/epub → 合并）；`default_source`/`work_sources` 逐书覆盖生效；`xml_options` 全量回存后重启一致

## 8. 非目标（契约 §6）

- 不做三藏/朝代目录过滤（沿用 publish 启动时内存生成）
- 不做 X 續藏 bulei.txt 归并逻辑（已纳入 publish 三藏映射）
- `margins` 首版可选透传（None → 继承 page preset）；自定义编辑 UI 列为后续