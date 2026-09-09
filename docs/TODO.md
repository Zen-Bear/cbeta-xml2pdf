# TODO

- **铁律（2026-09-06 用户确认）：改 `pycbeta/styles/pdf_docx.css` 前必须先经用户确认（出值才动手），plan 模式只展示不动。**
- **死命令（2026-09-07 用户确认）：任何新 XML 元素（cb:* 等）必须入左栏 `EDITABLE_ROWS` + `TAG_SELECTOR` 映射 + CSS 变量/规则，验收 = 左栏可见可调。**
- [x] **已完成 render-time 按字回退**（2026-09-06 用户报 標楷體 U+43F6 预览/Word 双 tofu）：`RENDER_FALLBACKS=(SimSun,PMingLiU,微软雅黑)`，`_fb_emit` 按 cmap 查覆盖、缺字拆 run（只换 eastAsia）；无文件不断言保持原样；真全缺（如悉昙 PUA）保持 tofu + 预览点名。T0672 对账文本一致；单测 TestRenderFallback 6 项；全量 302 OK，verify 8/0
  - 追补（2026-09-06）：回退链分繁简（Hant 首选 PMingLiU，Hans 首选 SimSun；跟 gaiji_lang；含 SimSunExtB/CBETA Supplement）；`output.docx.gaijiFonts` 未动（删的只是顶层 font_sets）；`linkActivated` 改 flag 跟踪消 RuntimeWarning；Ranjana.ttf/Siddam.ttf 实测 0/58 样本 PUA（纯装饰 CJK，不接线）
  - RJ 悉昙接线（2026-09-06）：官方 docx 实锤 `eastAsia="Ranjana"` + rjchar 常规字（不用 PUA）；parser 收 `rjchar`，`_resolve_gaiji` RJ 优先，`_ranjana_font_for` 按覆盖选字体（Ranjana→Siddam），无则主题字体直显（可读）；sample plane-16 PUA 清零，101 Ranjana run；单测 TestRanjana 5 项；全量 308 OK，verify 8/0
  - 回退链/siddhamFonts 进 config（2026-09-06）：`output.docx.fallbackFonts{zh-Hant,zh-Hans}`（替代硬编码，微软雅黑垫底）+ `output.docx.siddhamFonts`（缺省 ["Ranjana","Siddam"]）；`cbeta/fonts/README.md` 补悉昙节；单测 311 OK，verify 8/0

- [ ] **P1 高** GUI 链路 B（设计文档已完成：`docs/GUI设计.md`（选项卡面板 + 佛典編號列表输入/自动下载）；可复用模块调用见 `docs/第三方调用说明.md` §6.1）
  - 目录清理执行（2026-09-04）：git 首提交 3168e76（安全网，.gitignore 覆盖 out*/__pycache__/用户槽）→ 缺字库搬家 ruby-cbeta→cbeta/data（gaiji.py 改道，三处文档引用同步；data 与原逐字节一致；names.py 出处注释保留）→ 删 ruby-cbeta 整目录/engines僵尸config/out产物/test/out*/__pycache__/空pycbeta/fonts → docs 三 txt 转 md（无交叉引用）→ 清 tmp 调试残留；验证：缺字冒烟（33893 条，𤬪正常解析）+ 单测 217 OK + T0349 端到端；第二提交 3eb588b；1.75GB 两 zip 用户已移走冷盘（从未入库，工作区干净，无需提交）
  - 落地 panel（2026-09-04）：`pycbeta/gui/panel.py`（XmlOptions 七卡：输出格式/页面/分页/排版/注释/注音/校验；字体并入输出格式卡t2s在上字体在下自动切zh-Hans；纸张下拉`名（宽×高mm）`+定宽220；分页含佛典丛书名右列+双列说明小字；排版双列；引擎组仅pdf启用；注音卡常用六项括号预设下拉；校验文案基线→官方文档；边距四输入；保存/还原出厂三槽 `config.user/last.json`；临时 presets 写入器）+ `__main__.py` 独立窗（目录/編號列表/自动下载/批量表/QThread/取消）+ requirements PySide6；单测 test_gui 23 项（含引擎单引擎 5 项+布局 3 项+产物路径 2 项）；单引擎按管线动态填项+可用性探测（COM+主程序双条件，修 pywin32 误报）+安装提示（缺失红字），配置框置顶；文件列显示产物名链接（UserRole 存全路径，单击打开）；单引擎探测修 pywin32 误报（COM+主程序双条件）并支持版本号目录 glob（C:\Apps\WPS Office\12.1.0.21915 实证 wps 已安装）；编号列表大小写不敏感（fetch 层归一化大写，CLI 同样受益）；窗口标题 CBETA XML 格式转换 v1.0；官方基线改名官方电子书；输出行加打开目录按钮；数据源窗口（source 三路径 + downloads 八模板可视编辑，走三槽保存，apply_source_edits 纯函数可测）；catalog 备份到 cbeta/data/sutra_mapping.txt（默认仍指 publish 原件）；输入来源双向自动切换（同行 HBox 左对齐相邻）；复选框同行相邻；标题带 GUI 日期（gui/*.py 最新 mtime）；输出框默认 cwd/out；文件列多产物菜单选择打开（_on_file/_open_cell 分离）；pdf 默认 footnote（中间 docx 53 真脚注，修 render_one pdf 分支 endnote 默认）；页面边距上下/左右两列；排版两脏数据开关归第二列；全量 200 OK；独立窗 offscreen 实例化通过
  - 待废弃 `output.pdf_zoom`（2026-09-04 用户确认）：GUI 不暴露；config 保留；后续版本移除
  - 适配 cbeta/ 目录重组（2026-09-04）：`CBETA 補充字型/`→`cbeta/fonts/`，9 处引用改道（fonts.supplement_path/render_pdf._font_data_uri 改走共用函数/双测试改 supplement_path()/config 注释/两份设计文档）；补 test_fonts 缺失的 model 导入；全量 200 OK + verify 16/0
  - `pycbeta/gui/panel.py`：`XmlOptions`（page/font_set/engine/margins/formats + output/pagination/series_title/verify 覆盖） + `XmlOptionsPanel(QWidget)`（页面/字体/输出格式/注释/排版/分页/经藏名/校验 八选项卡，get_options/set_options）+ `XmlOptionsDialog(QDialog)`（exec→XmlOptions|None）
  - `pycbeta/gui/__main__.py`：`python -m pycbeta.gui` 独立窗（输入=目录/文件 或 佛典編號列表；find_local_xml→fetch_work 下载 XML→可选 ensure_baselines 下载官方基线→批量转换；QThread 进度/取消；sys.path 无侵入）
  - `requirements.txt` 追加 `PySide6>=6.6`
  - publish 侧（契约 `publish/docs/链路B-设计契约.md`，`publish/TODO.md:P1`）：config/app.json `default_source`+`xml2pdf.options`、collection `work_sources/xml_options`、`src/books/xml2pdf_bridge.py batch_convert`、中栏来源列/右栏三单选/[合成]按源分流
  - 验收：独立窗目录/ID 列表转换（含未下载经自动下载 XML+基线）；publish `sys.path+=["E:/dev/cbeta/xml2pdf"]` 引入 `XmlOptionsPanel`；`xml_options` 全量回存重启一致；端到端 XML→pdf/epub→合并

- [x] **已完成 P2** LibreOffice（2026-09-04 复检：`soffice.com --version` 26.2.5.2 ✓；2026-09-05 用户升级至 26.8.0.3，复测 `--engine docx2pdf:libreoffice` 实转 T0672 出 2.05MB PDF ✓，见 `test/out_lo/`（用户指正后改测 `--notes footnote` 脚注版，已覆盖同目录））
  - 现状：`C:\Apps\LibreOffice` 26.2.5.2（非默认 Program Files），`pycbeta/config.json:110` 与 `engines/config.json:20` `engines.paths.libreoffice` 指向其 `soffice.com`；`pycbeta/render_pdf.py:20 _find_soffice` 优先读该路径
  - 用户手工安装后：验证 `soffice.com --version`、`_find_soffice()`、`python -m pycbeta -i <xml> -f docx --engine libreoffice` 出 PDF
  - 若改安装路径：同步更新两处 config 的 `engines.paths.libreoffice`
  - 注意：安装前 `taskkill /F /IM soffice.bin`（`render_pdf.py:89 --headless` 常驻会锁安装目录）
  - 安装文档：`docs/安装说明.md`（2026-09-04：Python 库分组表/八引擎安装验证表/字体安装/CLI 全参数/GUI 使用/校验测试/常见问题）；README 同步（安装节指向新文档、CLI 表补齐 verify/font-check/list-fonts 等缺行）

- [ ] **P12 中** 本地单卷跨目录版本 XML（2026-09-09 用户立项，只调研未动手）
  - 现状实锤：CBReader 按**冊**分目录（`XML/<CANON>/<VOL>/`），一部跨多册时按卷碎片散落多目录
    （如 TX0006 般若波羅蜜多心經幽贊：`TX07/TX07n0006_001~_006` + `TX08/TX08n0006_007~` +
    `TX09/…`，seq 卷号全局连续；`TX07 - TX09` 即此）；每碎片是完整 TEI（含 teiHeader，
    juan milestone 跨卷连续：卷1 → 卷7，2026-09-09 实测）。
  - 缺口两处：① `test/merge_cbreader.py` 分组键是 `(canon, vol, stem)`（stem 含 vol，
    如 `TX07n0006` vs `TX08n0006`）——只合**同目录**按卷碎片，跨册同部产出多个文件；
    ② 管线下游（`BatchWorker._resolve` / CLI）把每个文件当一部渲染（书名/书签/分页全散）。
    `find_local_xml` 本身返回列表，能发现碎片，不是瓶颈。
  - 方案（推荐 A）：增强 `merge_cbreader.py` 做跨册合并——分组键改 `(canon, no)`（stem 去 vol
    部分归一化），seq 全局排序，teiHeader 取首卷，落盘单文件；不动主链（parser/Work/书签/
    分页/verify 全不受影响）。B（管线原生多文件感知：find 后归组、顺序 parse 拼接 Work）
    改动面大（输出命名/书签/分页/verify 全要动），不采用。
  - 动手前必验：各卷 teiHeader 是否一致（卷次信息有无分歧）；`nkr_note*`/`beg/end` 锚点编号
    跨卷是否唯一（若卷内自循环，合并后 backfill 冲突，需重编号）；witness/charDecl 跨卷。
  - 验收：TX0006 跨 TX07-TX?? 合出一部（卷数连续），书签/分页不断；与已合单文件版文本一致；
    全量回归 + verify 8/0。
- [x] **已完成** 单元测试数据路径迁移（`CBETA` 常量 → `E:\dev\cbeta\test`；`TestRenderYP0012` → `TestRenderYP0019`；`_body` 归一化剥 `<style>`/border span/style 属性/标签空白）
- [x] **已完成** `parser.py:221` charDecl `xml:id` 命名空间缺陷修复（`{NS_XML}id`）；并调整 `_resolve_gaiji` 优先级为 **gaiji_db → charDecl → raw**（官方 html 与 gaiji_db 一致，charDecl composition 非真实字符，仅作兜底）
- [x] **P8 低** 官方数据更新（2026-09-09 落实：上游 cbeta_gaiji 8/12 新增 CB35027-CB35032
  ［IDS composition + PUA U+F88D3-D8，管线照 uni_char or composition 走］；cbeta_gaiji.json
  31653→31659 整体覆盖，sanskrit 一致未动；CBETASupplement.ttf 与上游同字节（10150460）
  未动；sutra_mapping.txt 与 publish 原件一致未动；全量 383 OK，verify 8/0）
  - `--update-data` 官方数据更新入口（2026-09-09）：`pycbeta/update_data.py`（4 项直链：
    cbeta_gaiji.json / cbeta_sanskrit.json 取 cbeta_gaiji 仓 master，
    CBETASupplement.ttf 取 cbeta-fonts 仓 main，sutra_mapping 取 heavenchou/cbwork-bin
    sutralist 直链——URL 来源 publish/mulu/REMOTE_SOURCES.md §1；只同步本仓 4 文件，
    不搬 publish 的 remote_manager 整套）；下临时文件→先校验（JSON 非空对象/TTF 头+体积/
    文本非空）再落盘，一致跳过；`--dry-run` 预演；CLI 独立分组短路；GUI 配置栏"更新官方数据"
    按钮（后台线程跑，跑完弹报告）；单测全离线（mock 下载）
- [x] **P7 中** 竖排 docx（2026-09-05 用户点档3）：`DocxRenderer(vertical=True)` 每节 `sectPr` 写 `<w:textDirection w:val="tbRl"/>`（上→下、右→左；schema 顺序 titlePg 后，节间/文末两路径共用 `sect_inner`）；CLI `--vertical -f docx` 透传（docx2pdf 中间件同传；pdf 管线仍强制 html2pdf）；T0672 实证 16/16 分节；单测 TestDocxVertical 2 项；全量 223 OK。局限：纵排专用 @字体未切（后续）；纵排注码保持横躺（WPS/LO 忽略 w:fitText，全角化拉长版面的弯路已实锤退役，见下；T0672 注码注文无损）；ruby/注音竖排观感待 Word 目检
  - fitText 退役实锤链（2026-09-05）：用户 WPS 盲猜"某些字转 90 度"→ 代码考古确认 `_fit_for_rpr` 用 `w:fitText` + `w:vertAlign=rotate`（原生只管 CJK 横排压缩，不支旋转）→ 真 WPS 目检三连击：注码保持横躺 ✓ / 注文无缺字 ✓ / fitText 渲染层零生效（360° 全角残留、两行一列、版面拉长）→ 全角化拉长否决（版面崩坏）→ fitText 全仓退役（render_docx 删除 `_fit_id/_fit_for_rpr` 及注码/文末区两调用点；TestVerticalMarkers 改锁"无 fitText 残留 + 注码原文完整"，防后人重加；T0672 重渲 fitText:0/tbRl:16/[1] 注码完整；全量 226 OK）
- [x] **已完成** 注释注码字体可配+大字版字号修复（2026-09-06 用户报：注码 Times New Roman 能否配置；--font-scale 1.5 下正文注码 27pt/序 31.5pt 巨大）
  - `output.notes_marker_font`（默认 "Times New Roman"，如 "宋体, SimSun"；旧键 `marker_font` 回退；`DocxRenderer(notes_marker_font)`，CLI 由 output 透传 docx/pdf 两分支；verify/run_tests/第三方旧 args 走 getattr 默认）
  - 注码默认 0.75em（12pt 正文下 9pt，与 pdf 管线现行值对齐；`pdf_docx.css` 1em→0.75em，`render_pdf.py:517` 硬覆盖删除统一走 theme）
  - 根因：`_scale_font_size` 把 em/% 也乘（相对单位随基准自动放大）+ 注码锚定所在段落 → 1.5 下 1em×18pt 双重放大出 27pt/31.5pt；现 em/% 原样返回（只放 pt），注码锚定正文 `p` 不随标题段；T0672 实证 1.0 注码 18（9pt）/1.5 注码 27（13.5pt 单比）；单测 TestMarker 7 项 + test_theme 同步；verify docx 8/0；全量待跑
- [ ] **P3 低** 双轨校验 — XML 文本基线（异构 `lxml itertext`）作为渲染基线的辅轨
  - 背景：`IR` 自比对（两侧同走 `pycbeta/parser.py:40 P5Parser`）会掩盖 `lb/ed`、`charDecl`、`wit` 等解析缺陷
  - 方案：`html/txt/docx` 渲染基线保持主轨（`pycbeta/verify.py:248 verify_one` 现行）；新增 `verify --baseline xml` 辅轨：官方侧 `lxml.etree.itertext(official.xml)` 直抽，生成侧 `work_text(Work)` 线性化，两侧经 `normalize:18` 后 `diff_stats` 对比
  - 涉及：`pycbeta/verify.py:189 find_official` 新增 `kind="xml"` 分支、`work_text` 辅助、`base_kind` 映射 `all→xml`
  - 验收：`T15n0625`/`X60n1116`/`T12n0349` 在 `baseline_root=E:\dev\cbeta\publish\cbeta_xml` 检出时 `0/0`
- [x] **已完成 P1 GUI 样式编辑器**（2026-09-06 用户点档：DOCX 所见即所得调 `pdf_docx.css` 字体参数）
  - `pycbeta/gui/css_editor.py`：`CssEditorDialog`（样式表卡按钮弹窗，publish 可复用）+ `python -m pycbeta.gui.css_editor --sample` 独立运行；左标签分组四件套+源码页（tinycss2 红字不覆盖）/右 QTextDocument 模拟预览（回读 `DocxRenderer` run 真值：字号/字体/颜色/加粗/上标，ruby/EQ 展小字灰，注文尾注归并；分页以 Word 为准）/底导出样张 DOCX+PDF（跟主窗口引擎链）+ `user.css` 落盘自动生效+恢复出厂；样张默认 `css-presets/sample.xml`（用户已定稿）
  - 附带修批量桥：`--font-set` 默认省略（保 `user.css` 字体不被 `apply_font_set` 踩；显式组合/t2s 照旧覆盖）；`build_render_cmd` 纯函数可测；单测 TestStyleEditor 8 项；全量待跑
  - 追加强化（2026-09-06）：编辑器行按书顺序（文件不动）+ 未知规则原文透传；经藏名抽离到 CSS
    （`p.series-title`，config 仅留开关、旧键回退，GUI 分页卡改跳转）；字体三组下拉（中文
    buckets/西文三/字库目录+打开/刷新）；颜色两组（CSS 现有色标来源/自定义）
  - 改名 css_editor（2026-09-06）：`editor.py`→`css_editor.py`、`StyleEditorDialog`→
    `CssEditorDialog`（引用全改，无外部依赖）；控件预填出厂值+touched 输出；左栏滚动；
    字体中文优先显示+纯英文非精选过滤（`pmingliu` 别名补入 `fonts._ZH_ALIASES`）
  - 预设库双目录（2026-09-06）：内置 `pycbeta/styles/presets/`（入库+示例 large-print+
    README，删不掉）+ 用户 `css-presets/`（不入库）；编辑器顶部预设行切换/另存/删除；
    切换只装载，保存用户CSS即应用为当前；`list/save/delete/strip_prefix` 纯函数可测
  - 统一大迁移（2026-09-06）：font_sets 迁 CSS `:root` 双栏变量 + `config.theme` 默认槽 +
    编辑器双栏/下拉复用 + `user.css` 概念删除（详见本条）：T0672 繁字节一致、简仅经藏名
    隸書→隶书一处；用户槽朝华标题B搬入 `css-presets/我的样式.css` 并设默认；`--font-set`
    用到即报错；publish 桥需同日跟进（跨仓）
  - [x] **已修 html/epub 主题污染（2026-09-08 用户立案，当日落实）**：`8d534a4` 之前不带
    `--theme` 时 html/epub 纯 golden（`theme=None`），原始设计决策（`docs/设计报告-代码评审.md`
    Q7/§8）亦如此；`8d534a4` 后默认主题漏进 html/epub（选择器真实碰撞）。修复：html/epub
    传 `theme=None` + 基底（默认 golden），旧 `--theme` 删除（用了报错指新开关）；epub 三处
    同修（默认 `Theme()`/章节转发/`style.css` 走基底）；`verify.py` 同步。决策按 A 落地
    （永远纯 golden，`html-epub-user-theme` 占位警告+忽略）；publish 尚未接入，无依赖。
  - [x] **已落实 run.json 组合单（2026-09-08 用户立项并定稿）**：`--config`/`--theme` 合并成一个
    `--config`（run.json 5 槽：config-json/html-epub-theme/html-epub-user-theme/pdf-docx-theme/
    pdf-docx-user-theme）；`config.user.json` 不再是默认（仅面板存档/显式引用）；不带 `--config`
    自动读仓库根 `run.json`；旧 `--theme` 与旧全量快照硬切换（报错指新格式）；`config.last.json`
    轮转废弃；出厂 `theme` 键删除；有效配置 = 出厂 ← base 文件按鍵深合并（整包替换退役）；
        新开关 `--pdf-docx-theme`/`--pdf-docx-user-theme`/`--html-epub-theme`（逐槽覆盖）。
    全量 362+ OK，verify 8/0
  - set_run_slot 文本级手术（2026-09-08）：run.json 带 `//` 注释，裸 `json.dump` 重写会丢注释
    （且读失败会误判损坏进 .bad）；改逐行替换目标槽（注释/顺序/其余键原样保留）+ 注释模板新建；
    `current_theme_value` 读路径同修；    全量 376 OK
  - 内置预设退役（2026-09-08）：`large-print.css` 搬 `css-presets/` 当用户预设、
    `我的样式.css` 改名 `my.css`（run.json 槽同步改名，文本级手术保注释）；
    下拉去内置组（只剩出厂默认+用户预设，tooltip 标路径）；`styles/presets/` 只剩 README；
    相关单测改 mock/同形文件；全量 377 OK，verify 8/0
  - 面板纸张默认持久化（2026-09-08）：`options_from_presets` 读 `default_page` 但
    `_presets_merged` 从不写回去——选 A5 保存再开仍回 a4；补写 `data["default_page"]`；
    用户 `config.user.json` 已置 a5（CLI/面板初值三端一致）；全量 377 OK，verify 8/0
  - [x] **已落实 配置栏四按钮+默认纸张（2026-09-08 用户立项）**：面板配置栏"保存到配置"改名
    "保存用户配置"（写 `config.user.json` 不变）；新增"载入用户配置"（读回面板，文件缺失置灰）；
    新增"设为默认"（run.json `config-json` 槽指向 `config.user.json`）；"还原出厂"保留。
    出厂 `config.json` 加顶层 `"default_page": "a4"`；CLI `--page` 默认改 None →
    `显式 > 有效配置 default_page > a4`；GUI `options_from_presets` 跟随该键（非法值
    `resolve_page` 本来就警告回 a4）。config.user.json 保留（面板存档/显式引用），仅不再是默认。
  - 后缀归一+边距持久化+格式入库验证（2026-09-08）：`set_user_theme` 补 `.css`（下拉 stem
    时有时无）；边距改 `custom_margins` 键（出厂全有 margins，无法区分自定义）：保存写/重勾删、
    载入恢复、`resolve_page` 三级、`write_temp_presets` 同步；取消跟随填预设值作基线，跟随中
    切纸张刷新显示；搭售修 `t2s` 移出 `if margins`；格式栏（formats/engine/font_lang）上轮已
    入库，本次只验证；    全量 381 OK，verify 8/0
  - 字号单源 body（2026-09-08 用户立项并定 A）：`body{font-size:12pt}` 为唯一源，`p` 删字号走继承；
    `pages.doc_size` 键删除（9 纸张），doc 默认跟 `Theme.base_pt`（p→body 绝对值，未知回 11）；
    `docx_run` 半磅 `int`→`round` + 支持 `%`，`docx_para` font_pt 同样解 em，`_tag_base_pt` 默认走
    base；其余保持 pt（精确直观），em 只留天生相对处；编辑器字号显示回退 body 值（只显示不写回）；
    附带 0.9em 由 21 变 22（注音小字 10.5→11pt，唯一视觉变化，需目检）；全量 382 OK，verify 8/0
  - 标签锚定+目录可开（2026-09-08）：当前配置恒显示运行组合链（run.json → base 文件/出厂默认），
    保存/载入/设默认/还原只换后缀不再翻转；"打开用户预设目录"无响应是 `_open_local_file` 用
    `isfile` 误杀目录，改 `exists`；全量 382 OK
  - 字体栈统一同字体双名（2026-09-07）：出厂各 `--font-*` 一律"中文名, 英文名"（除 body 唯一
    多段链：中英双名+mac 兜底+Times New Roman 拉丁）；删通用族尾段（PDF 端 `_pdf_css` 已追加
    sans-serif）；繁 body 补回 PMingLiU、head 改 微軟正黑體/Microsoft JhengHei、
    div-xu-head 改 標楷體/DFKaiShu 与 楷体/KaiTi；注释同步
  - 字体下拉可编辑可搜（2026-09-07）：去"常用栈"分组；中文/字库单名自动补同字体英文别名
    （data="名, 别名"、显示短名），英文单名不补；`editable+NoInsert` 打字过滤；lost-focus
    匹配选项自动选中（写 data）、不匹配警告+复原旧选中项；框恒只显示一个名字（临时项首段
    短名）；删空白占位（空=清显示不写）；触发信号 currentTextChanged→currentIndexChanged
    （手输不实时写源码）；粗细改三态按钮（默认灰=未覆盖/加粗/常规，点击轮换）
  - 启动载用户槽 theme（2026-09-07）：`current_theme_value` 解析到 css-presets/ 用户文件即
    `_load_preset_path`（源码页=其覆盖块、保存按钮亮）；内置默认不载入（保持灰归另存）
  - 颜色按钮去文字（2026-09-07）：26×26 纯色块，右键清除/tooltip 保留，列头收窄
  - def 元素入左栏（2026-09-07，新元素死命令首例）：`TAG_SELECTOR["cb:def"]="def"` +
    `FONT_VAR_TAGS` 加 def；`render_docx._render_e` def 分支（run 带 def 标签，def 内 p 继承）；    `pdf_docx.css` `--font-def` 双栏 + `cb:def{font-size:0.9em}`（无颜色）；左栏"释义"行 +
    tooltip 双向查找（`_row_cb_tip` 各行 tooltip 标 cb 标签）；全量 345 OK、verify 8/0
  - 字义/释义正文化（2026-09-07）：`div.div-note` 去灰改加粗、`cb:def` 改 1em（恒等于正文；
    OOXML run 无继承，必须显式）；div-note 内 p/form 挂 pStyle div-note（样式内联拷贝 p
    布局+粗体，视觉不变；预览标【字义】，def 优先标【释义】）；内联路径（缩进段）一律挂
    命名样式（直接属性覆盖，视觉不变）；无 sz run 回落命名样式→文档默认（form 唵者预览
    11pt 与 Word 一致，不再掉 Qt 默认小字）；设为默认等全按钮取消 autoDefault（回车不
    误触）；左栏 480；状态条声明图片不显示；字号 400ms 防抖（输入"12"只刷一次）；
    全量 354 OK、verify 8/0
- [ ] **P9 中** GUI 界面三语切换（简/繁/英，2026-09-06 用户立项；与输出经文 t2s/font_sets 无关，是界面本身语言）
  - 背景：界面中文串全硬编码（panel 约数百处、`__main__` 状态栏/按钮），无 `QTranslator` 机制
  - 方案：先抽字符串资源（`pycbeta/gui/i18n/*.ts`，Qt Linguist 流程：`pylupdate6` 抽取→翻译→`lrelease` 编译→`QTranslator.load/install`），面板顶部或设置加语言下拉（简/繁/英，存用户槽，重启生效；或动态 `retranslateUi` 热切）
  - 验收：三语切换无硬编码残留（`rg` 查中文串只剩 ts 源）；offscreen 实例化通过；单测不断言具体中文文案（现有 `tabText` 名单用例需同步为 key 断言或跟随默认语言）
- [ ] **P10 低** GUI 深色模式（2026-09-06 用户立项）
  - 背景：现为 Qt 默认浅色；Qt6 可部分跟随系统深色，未显式适配（红字提示/灰字 hint 在深色下可能看不清）
  - 方案：跟随系统 `Qt::ColorScheme` + 手动开关（三态：跟随/浅色/深色，存用户槽）；先只保证现有样式表（红/灰提示色）在深色下可读，不过度定制 QSS
  - 验收：深/浅/跟随三档目检（配置栏/七卡/批量表/状态栏无看不清文字）

- [x] **已完成 P4** `docx` 段合并到 `output`（死配置修复：顶层 `docx` 删段 → `output.docx.footnoteSeparator`；零代码改动，实测自定义 2.0pt 生效；单测 58 + verify 24 0 失败）
  - 落点：`config.json` 顶层 `docx` 段删除，`output.docx.footnoteSeparator` 生效（与 `cli.py:346`、`run_tests.py:79,98` 读取位置对齐）；`render_docx.py:894` 注释同步；`功能清单.md:86` 键路径同步
  - 实测：默认 0.5pt→`w:sz=4`，`--config` 自定义 2.0pt→`w:sz=16`（此前顶层键全仓无读取，改值无效果）

- [x] **已完成 P1** 字体定义单一来源化（`font_sets` ↔ `pdf_docx.css` 合并，大字版前置已落地）
  - 背景：`pycbeta/styles/pdf_docx.css` 15 处 font-family 与 `pycbeta/config.json font_sets["default"]` 繁体值逐字重复，改字体需两处同步
  - 差异点（非纯重复）：`body`（CSS 独有，PDF 全页兜底 微軟正黑體；DOCX `docDefaults` 用 `p` 字体 新細明體 → 现状 PDF 兜底与 DOCX 兜底不一致）；`p.pin`（CSS 独有，`font_sets` 无 pin；`theme.py` 已有 `TAG_SELECTOR["pin"]`）；`span.note-inline`（CSS 无字体→PDF 继承 body 微軟正黑體，DOCX 用 `font_sets.note-inline` 新細明體 → 现状不一致）；`series`（`font_sets` 有，CSS 无，实际由 `output.series_title.font` 驱动，本次保留不动）
  - 锁定改动：不新增独立 `rend_fonts` 节；`kaiti/heiti/fangsong/mingti` 继续留在 `font_sets`（`--font-set :zh-Hans` 同时切换行内 rend 简体字体）；`config.json font_sets["default"]` 增 `body`/`pin`（繁简两版，`pin` 繁简沿用正文对）；`pdf_docx.css` 删除 15 处重复 `font-family`（保留字号/颜色/边距/缩进等非字体属性，`body` 保留 `line-height`）；`pycbeta/theme.py` 默认 `Theme()` 自动应用 `font_sets["default"]` 繁体字体，`TAG_SELECTOR` 增 `"body": "body"`，序列化时不给 `sans-serif` 等通用字体族加引号；`pycbeta/render_docx.py:1089 _body_font()` 改为优先读 `body`、回退读 `p`（顺带统一 PDF/DOCX 文档级默认字体）；`--font-set zh-Hans` 同时覆盖 `body`/`pin`；回滚风险：`note-inline` PDF 微变（微軟正黑體→新細明體）
  - 验收：单测 47 + verify 24 0 失败 + pdf/docx 冒烟观感对比（`--font-scale` 未开启时与现状一致）

- [x] **已完成 P2** 大字版（`output.font_scale` + `--font-scale`，`Theme.scale_font_sizes` 等比缩放 tags 与 raw_css，`doc_size` 跟随；字号不影响逐字校验；单测 11 + 回归 24 0 失败）
  - 落点：`pycbeta/config.json output.font_scale: 1.0`；`pycbeta/theme.py scale_font_sizes`（tags + raw_css 追加覆盖，只调一次）；`pycbeta/cli.py --font-scale`（显式优先于 config，`doc_size` 跟随，`--verify` 时回 1.0）；`output.series_title.size` 保持独立配置
  - 实测：`--font-scale 1.5` docx `w:sz` 24→36、60→90、18→27（精确 1.5 倍）；html 含覆盖规则；单测 58 OK；verify 24 0 失败

- [x] **已完成 P5** 豆腐字检验（`--font-check` + 缺字字体链；单测 test_fonts + 全量 191 OK；verify 繁体/t2s 16/0）
  - 背景：`fonts/` 目录为空，未随包字库；BMP 缺字（㮈 U+3B88 等）PMingLiU/SimSun 覆盖 ✓，但 Ext B 缺字（𤬪 U+24B2A、𭈫 U+2D22B）仅 `simsunb.ttf` 覆盖，`pycbeta/render_docx.py:438` 对 >0xFFFF 硬编码字体 `"CBETA Supplement"` 未安装→依赖 Word 回退；楷体栈（標楷體 DFKai-SB）覆盖为 0（偈颂/书名 BMP 缺字靠回退）
  - 改动：`--font-check` 静态覆盖率扫描（`fontTools` cmap × font_sets 字体栈，报 字/标签/所缺字体/gaiji 码）；docx >0xFFFF gaiji 字体链补 `SimSunExtB`（`render_docx.py:438` 一行）
  - 验收：T0349 等含 gaiji 经书 `0 豆腐`
  - 落地（2026-09-04）：`--font-check`（`pycbeta/fonts.py`: `block_name/font_cmap/collect_work_chars/check_coverage/font_check_report/format_font_report` + `FontLocator.path` + `supplement_path`；`cli.py`: `_stack_font_files/_run_font_check`，theme=None 时自建默认 Theme；fontTools 入 requirements core）。四档结论：OK / SUP（仅补充字形，需安装）/ FB（仅系统回退字 SimSun-ExtB/ExtG，Word 常自动用，跨机有风险；渲染结果优先于 SUP 显示）/ TOFU（字/码位/分区/次数/上下文/出处 `<g:CB号>`）；缺失字族标 MISS；gbk 控台降级 + 输出目录落盘 `font-check-<id>.txt`。T0625 实测 1166 字 0 豆腐（6 回退字全为 `<g>` 缺字）；单测 `test_fonts.py` 8 项；全量 164 OK；verify 繁体/t2s 16/0（检测不改渲染）

- [x] **P6 中** 难字注音（外部词表 + 五格式，2026-09-03 完成）
  - 方案：`pycbeta/config.json` 顶层 `annotations {enabled:false, scheme:pinyin|zhuyin, file:""}`（默认关，config-only 无 CLI 开关）；词表为外部 TSV（`词语<TAB>拼音<TAB>注音`，空=file 用内置 `pycbeta/data/annotations.txt` 20 词，`#` 注释），最长优先、finditer 非重叠；渲染前不改 IR（渲染时处理）；verify 默认关闭互斥——开启也可比对（extract 剥 `<rt>/<rp>/w:rt`，md〔〕由 normalize 剥除）
  - 涉及：新增 `pycbeta/annotate.py`（`load_table/resolve_annotations/active/split_annotated`，渲染器内不做 IO，CLI `main()` 装载后经 `render_one` 传入）；`render_html.py` 包 `<ruby>X<rt>注音</rt></ruby>`；`render_pdf.py` 转发（chromium 原生 ruby）；`render_epub.py` 转发内部 HtmlRenderer；`render_docx.py` `_run_rpr` 抽取复用 + `_run_annotated` 包 `w:ruby`（`rubyAlign=center`，rt/rubyBase 同 rPr；`<pre>` 内回退无注音）；`render_md.py` 括注 `X〔注音〕`（不用（），避与校勘 inline 括号混淆）；三渲染器 `_no_ann()` 在 head/byline/juan/jhead/docNumber/title-m 标题块压制（仅正文 Text 注音，metadata 书名天然免疫）；`verify.py` `_RUBY_RE/_W_RUBY_RE` + normalize〔〕上限 20→40（官方基线仅〔－〕类短标记）
  - 测试：`pycbeta/tests/test_annotate.py` 21 项（装载/规整/最长优先/缺列不注/四格式标记/标题压制/提取剥除）；html/ruby 156→152（标题 4 处被压）、md 165→161；CLI 开/关冒烟；`--verify` 注音开启 2/2 通过
  - 修复（2026-09-04）：无 `--config` 时曾静默忽略内置开关（`main()` 只从显式 presets 读 annotations，与其他 output.* 默认读内置 config 不一致）；现 `_annotations_source` 无 config 时读内置 `pycbeta/config.json`，生效时打印 `annotations: <scheme>, N terms, style=<...>`；回归 `TestCliSource` 3 项
  - 实证（2026-09-04）：用户报"注音把词清除"（願入楞伽城→願入城）——验尸 `test/out_t2s/T0672.docx` 含 1015 个 `w:ruby`（楞伽 57 处全在），文件侧正确，系 LibreOffice/WPS 不渲染 `w:ruby` 整段丢弃（Word/浏览器正常）；楞伽行另有笔误（注音抄成比丘的）已改正 `léng qié/ㄌㄥˊ ㄑㄧㄝˊ`
  - 位置可配（2026-09-04）：`annotations.style`: `ruby`=汉字上方（html/epub `<ruby>`、docx `w:ruby`，仅浏览器/Word 可见）/`inline`=汉字右侧行内（各格式统一括注，默认 inline）；`annotations.brackets` 一对单字（默认〔〕，如 `["(",")"]`）；md 恒行内；旧键 `docx_style` 由 `active()` 兼容；verify 全链路跟随：`generate_formal` 透传注音（验实际产出），`normalize(text, ruby_brackets)` 自定义括号门控剥除（仅读音字符集，正文/校勘括号保留；`[]` 与校勘短标记规则冲突避免使用）；CLI `--verify` 独立分支同步传参 + `vlog` gbk 降级（此前梵文 ṅ 可致崩溃）。单测 131 OK；verify 繁体 16/0、简体 16/0（注音开启）；`() `自定义括号 docx 逐字一致；CLI `--verify` T0672 与 md-vs-html 差距经开/关对照证实为既有（与注音无关）
  - 上方即 ruby（2026-09-04）：WPS 拼音指南落盘同样是标准 `w:ruby`（CT_Ruby），差别在 `rubyPr` 完备性——旧版仅 `rubyAlign` 会被 WPS/LO 忽略；现补完 `hps/hpsRaise/hpsBaseText/lid`（WPS 同款结构，Word 兼容）+ rt 独立字号字体；LO 的 DOCX ruby 导入本身有限制，LO 下仍建议 inline
  - 注音字号字体（2026-09-04）：`annotations.rt_size`（默认 "50%"，相对段落字号；可写 "7pt"）+ `rt_font`（默认空=继承；如 "楷体"）；html 注入 `ruby rt{...}` CSS 规则（仅 ruby style），docx 写 `w:rt` 字号字体 + `w:hps`；行内括注为纯文本无字号
  - 生僻字自动（2026-09-04）：`annotations.rare_zones`（默认空=关闭；如 ["G","H"]，原码位阈值 rare_from 已删，见"分区选择"）——分区内汉字按字取音（pypinyin TONE/BOPOMOFO，未收录跳过；缺 pypinyin 静默跳过，requirements 记为可选）；词表优先（最长匹配先行，全文模式除外）；多音字取最常用读音（佛教专音如迦葉 shè 务必进词表覆盖）；解析后缺字（`<g>` 解出 Unicode 的，如 T0625 𤬪→𤬪〔dù〕）同样参与（此前"图片字不注"收窄为"未解析 PUA/图片不注"）；verify 透明（读音字符集门控）
  - 注音频率（2026-09-04）：`annotations.repeat`: `all`=每次都注（默认）/`first`=全文只注首次/`page`=每分页单元首次（docx 按智能分页分节重置，html/epub 按卷文件重置，md 无分页等同 first）；`split_annotated` 经 `seen` 集合去重（`repeat_mode/track_seen/page_repeat`），标题压制天然不占首次（压制路径不进 split）；渲染器复用跨文档清零（`render_work`/`_reset_state` 重置）。T0672 实测 78 处楞伽只注首次；单测 168 OK；verify 繁体/t2s 16/0（去重后剥除仍一致）
  - EQ 域上方注音（2026-09-04）：用户取证 WPS 12.1 拼音指南落盘为传统 EQ 域 `{ EQ \* jc0 \* "Font:宋体" \* hps12 \o \ad(\s \up 11(pú),菩) }`（逐字 begin/instr/end），根本不用 `w:ruby`——此前 WPS/LO 看不见的原因；新增 `style: field`（docx 发 EQ 域，逐字、读音按音节分配，up 取正文字号×0.6 复刻 WPS 比例，字体取 rt_font 否则宋体；html 回退 ruby，md 回退行内）；`ruby_up` 可配抬升量（默认 "100%" 正文字号——60% 在新細明體下与正文相交，已改默认，用户 WPS 已见字，ruby_up=100% 合适（已确认））；verify 提取侧 `_eq_base` 还原原文（仅注音签名，非注音域代码保持旧行为）。单测 155 OK；verify 繁体 16/0、简体 16/0；用户 WPS 12.1 实测可见（已确认）
  - 缺字字体链（2026-09-04）：`output.docx.gaijiFonts {zh-Hant:[补充字形], zh-Hans:[SimSunExtB,补充字形]}` 可配；`DocxRenderer(gaiji_fonts/gaiji_lang)` 首个超大缺字时懒解析首个已装（平时零开销，全缺回退首项）；连带修 `_run_rpr` 显式 fonts 被主题字体淹没（同 rPr 双 w:rFonts 时 Word 取首个，旧代码缺字字体恒失效）；单测 TestGaijiFonts 5 项；全量 191 OK
  - 补充字形注音（2026-09-04）：`annotations.rare_font`（TTF/OTF 路径，空=关闭）——`CBETASupplement.ttf` cmap 共 13943 字（13920 Lo），覆盖字自动注音，与分区选择为"或"关系（`load_supplement_cmap` 按路径缓存，fontTools 缺失静默空集）；T0625 `<g>𤬪`→`𤬪〔dù〕` 实证；单测 TestSupplement 6 项
  - 分区选择（2026-09-04）：`rare_from` 码位阈值删除，换 `annotations.rare_zones`（`[]`=关闭；`["G","H"]`、全扩展九区数组；兼容 `Ext G` 前缀写法）；分区表硬编码 A–I（I 在数值上位于 F、G 之间，故不用阈值）；读音进程级常驻缓存；`rare_zones` 的 `"All"` 歧义已删，改独立 `annotations.full_text`（true=词表优先整词注音、其余逐字，忽略 zones/repeat；专音以词表为准；T0349 实证标题干净）。单测 170 OK；verify 繁体/t2s 16/0
  - div-xu 颜色链路（2026-09-04）：用户改色不生效——默认链路实测正常（html 有 div.div-xu 规则+class；docx 115 处 w:color 555）；根因为 `TAG_SELECTOR` 缺 div-* 项，`theme.css()` 重序列化丢弃 div 规则（`--theme xxx.json` 路径 html/pdf 必现），已补 `TAG_SELECTOR.setdefault(div-*)`（font_sets 无 div 标签，不误注字体）
  - 署名规则合并+注音字号（2026-09-04）：`p.author`/`p.translator` 完全相同的两段规则合并为逗号分组 + 译者空覆盖块（后定义优先，实测 tags 完全一致）；note-ref 用户自改 `1em` 已验证生效（`tags[note-ref]==1em`，旧 9pt 断言同步更新）；`--list-fonts [关键词]` 查本机字体 GDI 名（`FontLocator.scan_system` 可关，`search_fonts` 供 CLI/GUI 复用；test_fonts 4 项）；单测 186 OK
  - 序字体进 font_sets（2026-09-04）：`font_sets.default` 加后代组合键 `"div.div-xu p.head": [標楷體…(繁), 楷体…(简)]`，与 CSS 文件互抄；`apply_font_set` 显式切换恒覆盖，`__init__` 默认仅 CSS 未指定时填充（`_set_compound_font` 共用，非法键跳过不写 junk）；docx 走 compounds，HTML/PDF 走 raw_css 追加规则（层叠覆盖）；T0672 繁→標楷體、`:zh-Hans`→楷体实证。单测 182 OK
  - 后代选择器（2026-09-04）：T0672 序标题 `<head>` 在 div-xu 内，命中 p.head 蓝色覆盖 div 黑色（与浏览器优先级一致）；引擎新增两段 `A B` 后代支持（`_parse_css_tags` 收 compounds，`_props`/`docx_para` 凭完整标签栈匹配，`css()` 原样回写，`scale_font_sizes` 跟随；三段+/属性选择器忽略）；pdf_docx.css 加 `div.div-xu p.head` 规则（用户自改为 #408080 + 標楷體，实证 run 同时生效）；连带修 3 位简写色 `#000` 写出非法 `w:val="000"`（`_hex6` 展开，docx_run/_marker_rpr 共用）；仓内源文件颜色统一 6 位（golden `#00f`→`#0000ff`，xu/w/note 灰系展开，注释内一并统一；用户自定义 CSS 仍由 `_hex6` 兜底）。单测 177 OK
  - 验收：五格式注音均可见；单测 120 OK；verify 繁体 16/0、简体 16/0 保持
