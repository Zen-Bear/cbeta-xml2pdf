# GUI 设计（xml2pdf 侧）

> 依据 `E:\dev\cbeta\publish\docs\链路B-设计契约.md`（唯一契约）。本文件仅设计，**不包含代码**；
> 实施阶段产出：`pycbeta/gui/panel.py`、`pycbeta/gui/__main__.py`，依赖 `PySide6>=6.6`。

---

## 1. 目标与分工

- `xml2pdf` 侧交付**可复用 UI 组件** + 独立转换窗；`publish` 侧集成（右栏面板/中栏来源列/合成分流）。
- 纸张/字体/引擎等**单一逻辑归属 `xml2pdf`**（`config.json pages/font_sets/engines`），publish 不重复实现。
- 模块化钩子已就绪：`pycbeta/fetch.py:230 fetch_work`、`pycbeta/verify.py:278 verify_one`、`pycbeta/cli.py:51 render_one`（见 `docs/第三方调用说明.md`）。

## 2. 数据模型 `XmlOptions`（扩展版）

```python
@dataclass
class XmlOptions:
    page: str = "a4"                    # pages 键（a4/a5/letter/book/phone/tablet/monitor）
    font_set: str = "default"           # font_sets 键，可带 :zh-Hans
    engine: str = "docx2pdf"            # docx2pdf[:wps] | html2pdf[:chromium]
    margins: dict = None                # None → pages[page].margins
    formats: list = None                # None → [pdf]；如 ["pdf", "epub"]
    output: dict = None                 # output 覆盖（见表「GUI 可回存参数」）
    font_scale: float = 1.0             # 字号等比缩放（大字版 1.33/1.5；字号不影响逐字校验）
    pagination: dict = None             # 智能分页 {enabled,duplex,juan,juan_first,mulu_level1,pb,tei}
    series_title: dict = None           # 经藏名 {enabled,font,size}
    t2s: bool = False                 # OpenCC t2s 简体输出（正文/注释/元数据；未指定 font_set 时自动套简体字库；校验时官方基线同步转简体）
    verify: dict = None                 # 可选：转换后校验 {enabled:bool, formats:list}
```

### 2.1 config.json 参数分类（GUI 可改并回存）

| 分组 | 参数（config 键） | 控件 | 回存目标 |
|---|---|---|---|
| 页面 | `pages.<page>` | 下拉 | `xml_options.page` |
| | `pages.<page>.margins`（可选） | 数字输入（四边） | `xml_options.margins` |
| | `output.grayscale` | 复选「黑白输出」 | `output.grayscale` |
| | `output.page_border` | 复选「页面边框」 | `output.page_border` |
| | `output.pdf_zoom` | 数字输入「PDF 缩放」 | `output.pdf_zoom` |
| 字体 | `font_sets` | 下拉（组合:语言） | `xml_options.font_set` |
| 引擎 | `engines.docx2pdf.chain` / `html2pdf` | 单选+单体下拉 | `xml_options.engine` |
| 输出格式 | — | 多选 `pdf/epub/docx/html/md` | `xml_options.formats` |
| | `output.font_scale` | 数字输入「字号缩放」（大字版 1.33/1.5） | `output.font_scale` |
| | `output.t2s` | 复选「简体转换」（OpenCC t2s；未指定 font_set 时自动套简体字库；校验时官方基线同步转简体） | `output.t2s` |
| 注释 | `output.show_notes` | 复选「显示注释」 | `output.show_notes` |
| | `output.footnote_per_page` | 复选「脚注每页重新编号」 | `output.footnote_per_page` |
| | `output.inline_brackets` | 下拉 halfwidth/fullwidth | `output.inline_brackets` |
| | `output.suppress_title_notes` | 复选「压制标题注码」 | `output.suppress_title_notes` |
| 排版 | `output.split_juan` | 复选「按卷分文件」 | `output.split_juan` |
| | `output.show_close_juan` | 复选「显示结束卷标题」 | `output.show_close_juan` |
| | `output.suppress_jhead_dup` | 复选「卷名去重」 | `output.suppress_jhead_dup` |
| | `output.ignore_xml_style` / `ignore_xml_space` | 复选（脏数据忽略） | `output.*` |
| | `output.verse_caesura` / `verse_strip_quotes` | 输入/复选（偈颂） | `output.*` |
| 分页 | `output.pagination.*` | 分组复选（智能分页/双面/卷首/序品/pb/尾页） | `pagination.*` |
| 经藏名 | `output.series_title.*` | 复选+字体+字号 | `series_title.*` |
| 校验 | `verify.maxDiff/diffLines/auto_fetch/scope_juan` | 高级页（阈值/自动下载/卷限定） | `verify.*` |

**不适合 GUI 修改**：`source.xml_dir/catalog/download_dir`（路径，走浏览/配置页而非面板）、`downloads.*` URL 模板（固定，改配置文件）。

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
│   ☐ 黑白输出(grayscale)    ☐ 页面边框(page_border)            │
├───────────────────────────────────────────────────────────────┤
│ 字体:  [default ▼]（font_sets 键，含 :zh-Hans 变体）           │
├───────────────────────────────────────────────────────────────┤
│ 输出格式: ☐ pdf ☑ epub ☐ docx ☐ html ☐ md                     │
│ 引擎: (•) docx2pdf  ( ) html2pdf     单体 [自动 ▼]            │
│       ☐ 简体转换（OpenCC t2s；校验时官方基线同步转简体）             │
├───────────────────────────────────────────────────────────────┤
│ 注释: ☑ 显示注释 ☑ 脚注每页重新编号 ☐ 压制标题注码              │
│       inline 括号 [halfwidth ▼]                               │
├───────────────────────────────────────────────────────────────┤
│ 排版: ☐ 按卷分文件 ☐ 显示结束卷 ☑ 卷名去重 ☐ 忽略XML样式/空格    │
│       偈颂分隔 [　　]  ☐ 去偈颂引号                            │
├───────────────────────────────────────────────────────────────┤
│ 分页: ☐ 智能分页 ☐ 双面打印 ☑ 卷首换页 ☐ 首卷换页              │
│       ☑ 序/品 level1 换页 ☐ 按 pb 分页 ☑ 尾页换页             │
├───────────────────────────────────────────────────────────────┤
│ 经藏名: ☑ 打印  字体 [隸書, LiSu ▼]  字号 [9]                 │
├───────────────────────────────────────────────────────────────┤
│ 校验(高级): ☐ 转换后校验  阈值[10]  差异行[5]                  │
│       ☑ 基线缺失自动下载 ☑ 按卷限定官方基线                    │
└───────────────────────────────────────────────────────────────┘
```

接口（同前）：
- `get_options() -> XmlOptions` / `set_options(opts)` / 信号 `optionsChanged(XmlOptions)`
- 每个选项卡控件值变更即写回内存中的 `XmlOptions`，`get_options()` 汇总

> 注（2026-09-06）：上图为初版草图，当前实际为八卡——输出格式 / **样式表** / 页面 / 分页 /
> 排版 / 注释 / 注音 / 校验。样式表卡列两默认 CSS 路径（可打开）；注音卡词表行下有实际路径
> hint + 打开按钮；数据源按钮在面板顶部配置栏（原独立窗按钮已移除，`SourceDialog` 共用）。

### 3.2 `XmlOptionsDialog(QDialog)`
面板的对话框包装：`exec() -> Optional[XmlOptions]`（Accept→选项；Cancel→None），`[确定][取消]`。

## 4. 独立窗 `python -m pycbeta.gui`

### 4.1 输入两种模式

```
┌─ xml2pdf（独立窗） ────────────────────────────────────────────┐
│ 输入来源: (•) 目录/文件  ( ) 佛典編號列表                        │
│ 目录/文件: [cbeta_xml 目录 或 *.xml……]  [浏览]                  │
│ 編號列表:  [T0349, X1116, TX0006, A1057…（逗号/换行分隔）]  │
│            ☐ 自动下载缺失 XML（source.xml_dir）                 │
│            ☐ 同时下载官方基线（html/docx/txt 供校验）           │
│ 输出     [………………]  [浏览]                                    │
│ 设置     [XmlOptionsPanel 嵌入]                                │
│ ┌─ 批量列表 ────────────────────────────────────────────────┐ │
│ │ 经号        经名              来源    状态    进度          │ │
│ │ T0349      彌勒菩薩所問本願經  本地XML  待转换  ████░░ 40% │ │
│ │ X1116      毗尼日用切要香乳記  已下载  待转换  ░░░░░░  0%  │ │
│ └───────────────────────────────────────────────────────────┘ │
│ [开始] [取消]   ██████████░░░░░░░░ 进度条                      │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 佛典編號列表流程（走当前逻辑）

对列表内每个 ID：
1. `fetch.is_work_id(id)` 校验；`parse_work_id` → `(canon, no)`
2. **本地查找**：`fetch.find_local_xml(source.xml_dir, canon, no)`（统一根目录两档：平展优先、仓库次之，排除 `out/`）
   - 未找到且勾选「自动下载缺失 XML」→ `fetch.fetch_work(id, ["xml"], presets, download_dir)` 下载到 `source.download_dir`，再查找
   - 未找到且未勾选 → 行状态标「缺 XML」跳过
3. **（可选）官方基线**：勾选「同时下载官方基线」→ `fetch.ensure_baselines(id, ["html","docx","txt"], presets, download_dir)`（校验用；docx/odt 非 T/X 静默失败）
4. **转换**：`cli.render_one` 或子进程 `[sys.executable, "-m", "pycbeta", "-i", xml, "-f", fmt, "--page", opts.page, "-o", out_dir]`（`t2s=True` 时追加 `--t2s`）
5. **（可选）校验**：`verify.verify_one(xml, fmt, source, out_root)`，行状态显示 `OK/缺N/多N`（简体转换开启时官方基线同步转简体后比对）

批量列表列：`经号 | 经名 | 来源（本地/已下载/官方基线） | 状态 | 进度`；`QThread` + 信号更新；取消中断后续。

### 4.3 目录/文件模式
递归扫描 `**/*.xml`（排除 `out/`）填充批量列表；其余同流程（来源列统一「本地XML」）。

## 5. publish 集成（契约 §3-4，由 publish 侧实施）

### 5.1 配置持久化 `publish/config/app.json`
```json
{
  "default_source": "official",          // official | xml
  "xml2pdf": { "path": "E:/dev/cbeta/xml2pdf",
               "options": { "page": "a4", "font_set": "default", "engine": "docx2pdf",
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
    # 1) 确保 XML：fetch.find_local_xml / fetch_work（source.download_dir，缺失自动下载）
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
3. 冒烟：`python -m pycbeta.gui` 单文件/ID 列表转 pdf/epub；ID 列表含未下载经（如 A1057）验证自动下载；publish 侧 `sys.path += ["E:/dev/cbeta/xml2pdf"]` 引入 `XmlOptionsPanel`
4. publish 侧（契约 `publish/TODO.md:P1 链路B`）：config/collection 字段、bridge、中栏/右栏、[合成] 分流
5. 验收：链路 B 端到端（XML 源 → pdf/epub → 合并）；`default_source`/`work_sources` 逐书覆盖生效；`xml_options` 全量回存后重启一致

## 8. 非目标（契约 §6）

- 不做三藏/朝代目录过滤（沿用 publish 启动时内存生成）
- 不做 X 續藏 bulei.txt 归并逻辑（已纳入 publish 三藏映射）
- `margins` 首版可选透传（None → 继承 page preset）；自定义编辑 UI 列为后续