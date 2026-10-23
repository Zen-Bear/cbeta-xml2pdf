# TODO

- **铁律（2026-09-06 用户确认）：改 `pycbeta/styles/pdf_docx.css` 前必须先经用户确认（出值才动手），plan 模式只展示不动。**
- **死命令（2026-09-07 用户确认）：任何新 XML 元素（cb:* 等）必须入左栏 `EDITABLE_ROWS` + `TAG_SELECTOR` 映射 + CSS 变量/规则，验收 = 左栏可见可调。**
- **语言规范（2026-10-14 用户确认；已写入项目根 `AGENTS.md`，每次对话自动加载）：不自造缩写、不自造代称（如「甲方案／乙方案」）；术语写全称并沿用项目文档既有称法；引用原话保持原样；**尽量简单明了**（先给结论，短句/列表/表格优先）；发现前文有自造缩写或笔误时主动更正。**
- **当前优先级（2026-10-06 审计；2026-10-06 更新：X1077 用户实测全绿；publish 仓 P0–P4 已全完成，无遗留）**：
  - P0 收尾（已提交 `6ba95c5`/`c59ec8d`）：xml2pdf GUI（转换中/预填经名来源/光标落文件列）+ 外部引擎 URL + TODO 审计；publish 封面演示待提交。
  - P1：按卷范围 juan **已落地（2026-10-07，见文末「已完成 按卷范围」）**；外部引擎分发已改走上游 URL（安装文档已写明，不传 Release）。
  - P2：html/epub 用户 CSS **已落地（2026-10-07，见下「已完成 html/epub 使用 CSS（用户增量）」）**。门禁外红灯已全消（2026-10-06：T0001/X1077 六格式全绿）；校验报告「差异是否全在注释」已落地（Q3，`diff_scope`）；Q1（html 回退 txt）降为可选/低。
  - P3/关闭：body-placed foot 注渲染（2026-10-21 全库 229 XML 实测 body 内 `place="foot"` 0 处、TX0006 6 碎片亦 0 ⇒ 暂不立项，除非另有 CBReader 书库源）；T01 `_cbreader` 重合（数据卫生，低）；元素/字体扫描（已记录，无代码改动）；html2pdf 分页（决议不做）；`verify_one`/`build_report_json` 行级共享（收益小，暂不）。
- [x] **已完成 render-time 按字回退**（2026-09-06 用户报 標楷體 U+43F6 预览/Word 双 tofu）：`RENDER_FALLBACKS=(SimSun,PMingLiU,微软雅黑)`，`_fb_emit` 按 cmap 查覆盖、缺字拆 run（只换 eastAsia）；无文件不断言保持原样；真全缺（如悉昙 PUA）保持 tofu + 预览点名。T0672 对账文本一致；单测 TestRenderFallback 6 项；全量 302 OK，verify 8/0
  - 追补（2026-09-06）：回退链分繁简（Hant 首选 PMingLiU，Hans 首选 SimSun；跟 gaiji_lang；含 SimSunExtB/CBETA Supplement）；`output.docx.gaijiFonts` 未动（删的只是顶层 font_sets）；`linkActivated` 改 flag 跟踪消 RuntimeWarning；Ranjana.ttf/Siddam.ttf 实测 0/58 样本 PUA（纯装饰 CJK，不接线）
  - RJ 悉昙接线（2026-09-06）：官方 docx 实锤 `eastAsia="Ranjana"` + rjchar 常规字（不用 PUA）；parser 收 `rjchar`，`_resolve_gaiji` RJ 优先，`_ranjana_font_for` 按覆盖选字体（Ranjana→Siddam），无则主题字体直显（可读）；sample plane-16 PUA 清零，101 Ranjana run；单测 TestRanjana 5 项；全量 308 OK，verify 8/0
  - 回退链/siddhamFonts 进 config（2026-09-06）：`output.docx.fallbackFonts{zh-Hant,zh-Hans}`（替代硬编码，微软雅黑垫底）+ `output.docx.siddhamFonts`（缺省 ["Ranjana","Siddam"]）；`cbeta/fonts/README.md` 补悉昙节；单测 311 OK，verify 8/0

- [x] **已完成 P1** GUI 链路 B（2026-09-17 用户销项：设计文档 `docs/GUI设计.md`、可复用模块边界 `docs/第三方调用说明.md` §6.1、publish 链路B 契约均落地；面板/独立窗/一键送校验已上线。小项 `output.pdf_zoom` 复核后保留，见下条）
  - 目录清理执行（2026-09-04）：git 首提交 3168e76（安全网，.gitignore 覆盖 out*/__pycache__/用户槽）→ 缺字库搬家 ruby-cbeta→cbeta/data（gaiji.py 改道，三处文档引用同步；data 与原逐字节一致；names.py 出处注释保留）→ 删 ruby-cbeta 整目录/engines僵尸config/out产物/test/out*/__pycache__/空pycbeta/fonts → docs 三 txt 转 md（无交叉引用）→ 清 tmp 调试残留；验证：缺字冒烟（33893 条，𤬪正常解析）+ 单测 217 OK + T0349 端到端；第二提交 3eb588b；1.75GB 两 zip 用户已移走冷盘（从未入库，工作区干净，无需提交）
  - 落地 panel（2026-09-04）：`pycbeta/gui/panel.py`（XmlOptions 七卡：输出格式/页面/分页/排版/注释/注音/校验；字体并入输出格式卡t2s在上字体在下自动切zh-Hans；纸张下拉`名（宽×高mm）`+定宽220；分页含佛典丛书名右列+双列说明小字；排版双列；引擎组仅pdf启用；注音卡常用六项括号预设下拉；校验文案基线→官方文档；边距四输入；保存/还原出厂三槽 `config.user/last.json`；临时 presets 写入器）+ `__main__.py` 独立窗（目录/編號列表/自动下载/批量表/QThread/取消）+ requirements PySide6；单测 test_gui 23 项（含引擎单引擎 5 项+布局 3 项+产物路径 2 项）；单引擎按管线动态填项+可用性探测（COM+主程序双条件，修 pywin32 误报）+安装提示（缺失红字），配置框置顶；文件列显示产物名链接（UserRole 存全路径，单击打开）；单引擎探测修 pywin32 误报（COM+主程序双条件）并支持版本号目录 glob（D:\WPS Office\12.1.0.21915 实证 wps 已安装）；编号列表大小写不敏感（fetch 层归一化大写，CLI 同样受益）；窗口标题 CBETA XML 格式转换 v1.0；官方基线改名官方电子书；输出行加打开目录按钮；数据源窗口（source 三路径 + downloads 八模板可视编辑，走三槽保存，apply_source_edits 纯函数可测）；catalog 备份到 cbeta/data/sutra_mapping.txt（默认仍指 publish 原件）；输入来源双向自动切换（同行 HBox 左对齐相邻）；复选框同行相邻；标题带 GUI 日期（gui/*.py 最新 mtime）；输出框默认 cwd/out；文件列多产物菜单选择打开（_on_file/_open_cell 分离）；pdf 默认 footnote（中间 docx 53 真脚注，修 render_one pdf 分支 endnote 默认）；页面边距上下/左右两列；排版两脏数据开关归第二列；全量 200 OK；独立窗 offscreen 实例化通过
  - `output.pdf_zoom` 保留（2026-10-20 复核：`render_pdf.py:795` 在用，HTML→PDF 整页缩放；GUI 未暴露）；`docs/GUI设计.md:43` 的「PDF 缩放」输入行是陈旧描述，不改功能
  - 适配 cbeta/ 目录重组（2026-09-04）：`CBETA 補充字型/`→`cbeta/fonts/`，9 处引用改道（fonts.supplement_path/render_pdf._font_data_uri 改走共用函数/双测试改 supplement_path()/config 注释/两份设计文档）；补 test_fonts 缺失的 model 导入；全量 200 OK + verify 16/0
  - `pycbeta/gui/panel.py`：`XmlOptions`（page/font_set/engine/margins/formats + output/pagination/series_title/verify 覆盖） + `XmlOptionsPanel(QWidget)`（页面/字体/输出格式/注释/排版/分页/经藏名/校验 八选项卡，get_options/set_options）+ `XmlOptionsDialog(QDialog)`（exec→XmlOptions|None）
  - `pycbeta/gui/__main__.py`：`python -m pycbeta.gui` 独立窗（输入=目录/文件 或 佛典編號列表；find_local_xml→fetch_work 下载 XML→可选 ensure_baselines 下载官方基线→批量转换；QThread 进度/取消；sys.path 无侵入）
  - `requirements.txt` 追加 `PySide6>=6.6`
  - publish 侧（契约 `publish/docs/链路B-设计契约.md`，`publish/TODO.md:P1`）：config/app.json `default_source`+`xml2pdf.options`、collection `work_sources/xml_options`、`src/books/xml2pdf_bridge.py batch_convert`、中栏来源列/右栏三单选/[合成]按源分流
  - 验收：独立窗目录/ID 列表转换（含未下载经自动下载 XML+基线）；publish `sys.path+=["D:/xml2pdf"]` 引入 `XmlOptionsPanel`；`xml_options` 全量回存重启一致；端到端 XML→pdf/epub→合并

- [x] **已完成 P2** LibreOffice（2026-09-04 复检：`soffice.com --version` 26.2.5.2 ✓；2026-09-05 用户升级至 26.8.0.3，复测 `--engine docx2pdf:libreoffice` 实转 T0672 出 2.05MB PDF ✓，见 `test/out_lo/`（用户指正后改测 `--notes footnote` 脚注版，已覆盖同目录））
  - 现状：`D:\LibreOffice` 26.2.5.2（非默认 Program Files），`pycbeta/config.json:110` 与 `engines/config.json:20` `engines.paths.libreoffice` 指向其 `soffice.com`；`pycbeta/render_pdf.py:20 _find_soffice` 优先读该路径
  - 用户手工安装后：验证 `soffice.com --version`、`_find_soffice()`、`python -m pycbeta -i <xml> -f docx --engine libreoffice` 出 PDF
  - 若改安装路径：同步更新两处 config 的 `engines.paths.libreoffice`
  - 注意：安装前 `taskkill /F /IM soffice.bin`（`render_pdf.py:89 --headless` 常驻会锁安装目录）
  - 安装文档：`docs/安装说明.md`（2026-09-04：Python 库分组表/八引擎安装验证表/字体安装/CLI 全参数/GUI 使用/校验测试/常见问题）；README 同步（安装节指向新文档、CLI 表补齐 verify/font-check/list-fonts 等缺行）

- [x] **已完成 P12** 本地单卷跨目录版本 XML（2026-09-09 立项，2026-09-10 落地 A 方案）
  - 预检实锤（TX0006：TX07 001-006 + TX08 007-015 + TX09 016-049，seq 全局连续；juan milestone 1-49 连续；每碎片完整 TEI 无 back）：题名仅卷范围各异（取首卷，元数据噪声）；锚点零冲突（重复 id 仅各卷根 xml:id + witness）；charDecl 仅 015 卷 1 字（CB16748，恰被同卷唯一 `<g>` 引用）；body 内 foot 注 4（渲染/抽取双双丢弃，既有语义；2026-10-21 复核：本机 `cbeta_xml` 全库 229 XML 与 TX0006 6 碎片 body 内 `place="foot"` 均为 0，此 4 处未复现）+ 无锚 app 8（渲染直吐 lem/rdg，抽取侧镜像漏收——本次修齐）
  - 落点：`test/merge_cbreader.py` 分组键改 `(canon,no)`（无卷号 stem 回退旧键，长度不同永不串组；排序 `(vol,seq)`）；`merge()` 加 charDecl 按 id 跨卷并集 + 题名差异提示 + back 实质内容警告（body-only 语义不变）；跨册落首卷目录沿首卷 stem（`TX/TX07/TX07n0006.xml`，work id TX0006 不变，零管线改动）；`--only` 三形态（碎片 stem/归一 stem/佛典編號）；单测 `pycbeta/tests/test_merge.py` 7 项
  - 抽取侧附带修正（aux-only，零渲染影响）：`_extract_xml_parts` body 内无 from/corresp 的 app 收子文本（镜像渲染泛型默认分支；有锚 app 仍丢，残留已知）；单测 `test_body_app_without_anchor_mirrors_render`
  - 验收：TX0006 实合 49 碎片→1 部（199 body 节点）；合部 body/注块与碎片拼接逐字相等（509548 字）；辅轨 `--baseline xml` 0/0；docx 冒烟 826KB/4642 段/outline 俱全；单测 28 OK（merge/txt/verify）；全量回归按用户指示跳过（改动面：一次性合部脚本 + aux 抽取镜像，渲染/解析零触碰）
  - 备选 B（管线原生多文件感知）改动面大未采用；旧同目录合部语义保持原样（T01n0001 路径不变，单测锁死）
  - 自动合册入管线（2026-09-10 用户立项：xml_dir 直指 CBReader 书库免下载出书）：`pycbeta/merge.py` 库化（分组改按册 `(canon,vol,no)`；`resolve_work_files` 整文件优先否则碎片合册；`split_paths` 目录分区；合成落 tmpdir 随跑随清；`test/merge_cbreader.py` 瘦身薄 wrapper）；CLI 編號流 + 目录 walk + GUI ID/目录双模式接线（下游只见路径零感知；GUI 行标签“合册合成”）；多源同部输出触发式回退输入基名（`resolve_output _used`，单文件逐字节不变；html 命名 renderer 内置残留已知；GUI 批量同撞既有，另立项）；验收 TX0006 书库直出 3 txt + 逐册辅轨 0/0 + 逐册官方对照（TX07 0/0；TX08/TX09 差源 variance + 体注既有语义，非合部丢字，见下）；单册保真（组内拼接逐字相等）；全量 473 OK；门禁 html 双 OK（txt/md 残留已知类）；全量 verify 超时系环境慢（子集正常落盘），非失败
  - 统一命名（2026-09-10）：同轮多源同名全组改输入基名（首个亦回溯改名，`TX07n0006/TX08n0006/TX09n0006`，册数可见；`filename.dedupe_run_outputs`，render/verify 共用 state 重放得终态；GUI worker 显式 `-o` 同规则）；单文件/重跑逐字节不变；全量 483 OK
  - fetch 纯下载不要求 xml_dir（`need_xml=False`；download 空仍报错，堵 cwd 落盘保留）
  - 材料化模型重构（2026-09-10 用户定稿）：`download_dir` 改名 **`cbeta_ebook`**（唯一可写工作根；平展 `{id} {书名}/`，书名取 catalog 经 `source.title_t2s` 转简+净化）；`xml_dir` 定位为**只读候选源**（角色同远端 URL，两者相同即报错）；`fetch.materialize_work` 三源解析（cbeta_ebook → xml_dir 拷贝/碎片按册合册 → 官方下载，mtime 刷新）；`work_dir/_find_work_dir`（`{id}*` 复用，排除 T0349a 类误命中）；基线按需落 work 目录；**删除 git sparse clone 兜底与 `downloads.xml_repo`**；`merge_groups_to_tmpdir`→`merge_groups_to_dir`（平展 `{stem}.xml`），删 `merge.resolve_work_files`；CLI `--download-dir`→`--cbeta-ebook`、編號流改用 run.json 有效配置（原误用出厂 `load_presets`，材料化看不到用户槽）；GUI 三源接线+来源标签、数据源窗口 `title_t2s` 复选；verify 基线自动下载落 cbeta_ebook；`config.user.json`/测试语料迁 `<repo>/cbeta_ebook`；全量 493 OK
  - Phase 2 更新检查（2026-09-10）：`fetch.check_ebook_updates`（遍历 cbeta_ebook work 目录，逐 XML 条件下载 `If-Modified-Since`（304 免下载）+ 字节比对，不改项不落盘；无 sidecar，按日期/体积判定；**只走远程源，不涉本地 CBReader 候选源**）+ `format_update_report`（已更新/无变化/失败/跳过 + 需重新生成 ID 段）；**XML 有更新的 work，本地已有基线一并强制刷新**（`with_baselines`，仅已存在格式，GUI 复选「同时更新已有基线」默认开）；GUI 数据源窗口「检查电子书更新」按钮（`EbookUpdateWorker` 后台线程 + `EbookUpdateDialog` 弹窗，**一键拷贝已更新 ID** 到剪贴板）；字节详情去掉 `B` 后缀；单测 `TestCheckUpdates` 6 项 + GUI 2 项 + `_fetch_baseline_flat force` 1 项
- [x] **已完成** 单元测试数据路径迁移（`CBETA` 常量 → `D:\CBETA\test`；`TestRenderYP0012` → `TestRenderYP0019`；`_body` 归一化剥 `<style>`/border span/style 属性/标签空白）
- [x] **已完成** `parser.py:221` charDecl `xml:id` 命名空间缺陷修复（`{NS_XML}id`）；并调整 `_resolve_gaiji` 优先级为 **gaiji_db → charDecl → raw**（官方 html 与 gaiji_db 一致，charDecl composition 非真实字符，仅作兜底）
- [x] **P8 低** 官方数据更新（2026-09-09 落实：上游 cbeta_gaiji 8/12 新增 CB35027-CB35032
  ［IDS composition + PUA U+F88D3-D8，管线照 uni_char or composition 走］；cbeta_gaiji.json
  31653→31659 整体覆盖，sanskrit 一致未动；CBETASupplement.ttf 与上游同字节（10150460）
  未动；sutra_mapping.txt 与 publish 原件一致未动；全量 383 OK，verify 8/0）
  - `--update-data` 官方数据更新入口（2026-09-09）：`pycbeta/update_data.py`（4 项直链：    cbeta_gaiji.json / cbeta_sanskrit.json 取 cbeta_gaiji 仓 master，
    CBETASupplement.ttf 取 cbeta-fonts 仓 main，sutra_mapping 取 heavenchou/cbwork-bin
    sutralist 直链——URL 来源 publish/mulu/REMOTE_SOURCES.md §1；只同步本仓 4 文件，
    不搬 publish 的 remote_manager 整套）；下临时文件→先校验（JSON 非空对象/TTF 头+体积/
    文本非空）再落盘，一致跳过；`--dry-run` 预演；CLI 独立分组短路；GUI 数据源窗口
    "更新官方数据"按钮（后台线程跑，跑完弹报告，期间锁 Ok/Cancel）；单测全离线（mock 下载）
  - URL 表外置（2026-09-09）：`cbeta/data/remote_sources.json` 入库（改 URL 不改代码；
    悉昙/蘭札只有下载页 https://cbeta.org/downloads 无直链，记 manual 项仅展示）；
    缺失/非法大声报错；`fetch.DEFAULT_DOWNLOADS` 保持不动（数据源窗口 URL 早已配置化）
  - 更新记录+预检+重置（2026-09-09）：成功覆盖写 `.last-update.json` sidecar 入库
    （dry-run/未变不写），数据源窗口灰字显示（无记录回退 git 入库日期）；ETag/
    Last-Modified 探针（304 免下载，失败回退全量路）；数据源窗口"重置 URL"进按钮组
    Reset 位（只填表，点确定才保存）
- [x] **P7 中** 竖排 docx（2026-09-05 用户点档3）：`DocxRenderer(vertical=True)` 每节 `sectPr` 写 `<w:textDirection w:val="tbRl"/>`（上→下、右→左；schema 顺序 titlePg 后，节间/文末两路径共用 `sect_inner`）；CLI `--vertical -f docx` 透传（docx2pdf 中间件同传；pdf 管线仍强制 html2pdf）；T0672 实证 16/16 分节；单测 TestDocxVertical 2 项；全量 223 OK。局限：纵排专用 @字体未切（后续）；纵排注码保持横躺（WPS/LO 忽略 w:fitText，全角化拉长版面的弯路已实锤退役，见下；T0672 注码注文无损）；ruby/注音竖排观感待 Word 目检
  - fitText 退役实锤链（2026-09-05）：用户 WPS 盲猜"某些字转 90 度"→ 代码考古确认 `_fit_for_rpr` 用 `w:fitText` + `w:vertAlign=rotate`（原生只管 CJK 横排压缩，不支旋转）→ 真 WPS 目检三连击：注码保持横躺 ✓ / 注文无缺字 ✓ / fitText 渲染层零生效（360° 全角残留、两行一列、版面拉长）→ 全角化拉长否决（版面崩坏）→ fitText 全仓退役（render_docx 删除 `_fit_id/_fit_for_rpr` 及注码/文末区两调用点；TestVerticalMarkers 改锁"无 fitText 残留 + 注码原文完整"，防后人重加；T0672 重渲 fitText:0/tbRl:16/[1] 注码完整；全量 226 OK）
- [x] **已完成** 注释注码字体可配+大字版字号修复（2026-09-06 用户报：注码 Times New Roman 能否配置；--font-scale 1.5 下正文注码 27pt/序 31.5pt 巨大）
  - `output.notes_marker_font`（默认 "Times New Roman"，如 "宋体, SimSun"；旧键 `marker_font` 回退；`DocxRenderer(notes_marker_font)`，CLI 由 output 透传 docx/pdf 两分支；verify/run_tests/第三方旧 args 走 getattr 默认）
  - 注码默认 0.75em（12pt 正文下 9pt，与 pdf 管线现行值对齐；`pdf_docx.css` 1em→0.75em，`render_pdf.py:517` 硬覆盖删除统一走 theme）
  - 根因：`_scale_font_size` 把 em/% 也乘（相对单位随基准自动放大）+ 注码锚定所在段落 → 1.5 下 1em×18pt 双重放大出 27pt/31.5pt；现 em/% 原样返回（只放 pt），注码锚定正文 `p` 不随标题段；T0672 实证 1.0 注码 18（9pt）/1.5 注码 27（13.5pt 单比）；单测 TestMarker 7 项 + test_theme 同步；verify docx 8/0；全量待跑
- [x] **已完成 P3** 双轨校验 — TxtRenderer 第六格式 + XML 直抽辅轨（2026-09-09）
  - 路线变更：原文 `work_text()` helper 作废——txt render 是正式管线（可测可用），辅轨即 `verify_one(fmt="txt", baseline="xml")`；`baseline_root=cbeta_xml` 作废（该目录为空）——官方侧直接用输入 XML 本身直抽（版本零偏斜、零新配置）
  - 落点：`pycbeta/render_txt.py`（TxtRenderer：裸文本，题署去标记、注文末集中无 `[^n]`、表 TAB 化；`notes/show_notes/inline_brackets/annotations` 与 md 对齐）；CLI `-f txt`（`_ALL_FORMATS` 六项，`all` 含 txt）+ GUI 格式栏（默认不勾）；`verify.py:generate_formal` txt 分支 + 主轨 `txt→txt` 映射（cli/verify_text/verify_one 三处）；`verify.py:_extract_xml_parts`（lxml 异构直抽：只走 text/body、back 作注池、anchor 文档序、mod>orig 单选、app/mulu 整棵丢、unclear→□、g 经 GaijiDb+charDecl、行内注括号口径与 generate_formal 同源）；`verify_one(baseline="xml")`（仅 fmt=txt，其余 ValueError；落盘 `*_compare_xml_official.txt`）；`test/verify_text.py --baseline xml`（委托 verify_one，报告 `report_xml.txt`）
  - 验收：T15n0625/X60n1116/T12n0349 辅轨 0/0（含 t2s）；单测 `test_txt.py` 10 项；全量 429 OK；主轨 docx/html 8/0 不变
  - 主轨 txt/md 对齐 A 落地（2026-09-10）：官方 txt 侧 `_norm_official_txt`（版头 `#` 块剥离 + `    [n]` 注记块识别挪文末，繁简通用，三比对入口同构；`No.` 行不搬——生成侧 docNumber 本就在体首；`relocate` 试过方向反了已 revert）+ 生成侧 md 标记剥离 `_strip_md_marks`（`## 校注` + `[^n]: `，官方无此体系）；T0349 主轨 txt 624→15；md 经此与 txt 逐字同分（T0672 1012→12，证两者除标记外同一文本）；全集 11 部有官方 txt 者 txt 12~21、missing 全 0，md 与 txt 同分；无官方 txt 者回退 html（先天红，门禁外）；残留=注全变体vs单选每注几个字 + 题署/No. 顺序噪声，门禁仍只看 docx/html+辅轨；单测 +3（432 OK）
  - txt 不回退（2026-09-10）：无官方 txt 直接 `no_baseline`（三入口 `fmt != "txt"` 门控各两处；t2s 的 `txt_notes` 优先保留，仍是 txt 族；`auto_fetch` 先下载、仍无才报）；单测 `test_no_txt_no_html_fallback` 锁死；全量 433 OK
  - 已知局限（非 bug）：主轨 txt-vs-官方txt 与 md 同类红（官方 txt 把全部注变体行内化 + 版头 boilerplate，生成侧注文末集中——语义差异，非丢字；md 同理既有）；`_extract_xml_parts` 与 parser 共享缺字数据（GaijiDb）与版头选取语义，盲区仅限缺字解析本身
  - [x] **已消**（2026-10-06：T0001 六格式实测全绿，X1077 全绿，门禁外已无红）
    - **T0001（T01n0001 長阿含經）根因**：官方对「被 mod(a/b) 拆分取代的 orig 注（`nkr_note_orig_*`）」的处理 = **正文锚点压制 + 尾注块保留（孤注）**；我方 html 此前正文多出锚点（全 22 卷唯一差异 `0028009`），致比对错位 12/12。修复：`render_html._render_noteref` 接 `model.suppressed_orig_notes`——`_orig_suppressed` 命中时**尾注块照常入 `_back_old`**（孤注），正文锚点返回空、不占标记号；`inline` 分支直接压制。单测 `TestSplitOrigSuppressedHtml`。
    - **格式核对**：`txt`/`md`/`docx` 官方基线**不含**该 orig 注（实测 `T0001_004.txt` 无 `其積又火`）→ 全压制；`epub` 亦**整条不出**（官方 epub 为全内联注、无尾注区；`EpubRenderer(suppress_orphan_orig=True)` 转内部 `HtmlRenderer`，2026-10-06 补：epub 的 `txt_notes` trial 由「多12」转 0/0）；仅 `html` 保留孤注（与官方 html 一致）。
    - 附带：`normalize` 加 `html.unescape`（官方 html 正则剥标签后 `&quot;`/`&#39;` 实体残留，生成侧 raw 字符；T0001 html 104→12 大头）。
    - 仍留（非红灯）：渲染 body-placed foot 注（2026-10-21 实测全库 0 处，暂不立项）、T01 `_cbreader` charDecl 重合（卫生）；辅轨 `No.` 镜像已随 X1077 全绿作废。
  - 校验设计决议（2026-10-06 用户点档）：
    - [x] **Q3 已提升并落地**：校验报告告知「差异是否全部在注释」。显式分段（html/epub `_extract_html_parts`/`_extract_epub_parts`；docx `_extract_docx_parts`；官方 txt `_extract_txt_parts`；我方 txt `_split_txt_ours`；md `_split_md_body`）+ 正文段**严格 0** 判定；`verify_one` trial/记录加 `body_missing/body_extra/diff_scope`；报告 trial 行下加 `正文差异 …` 行（行首不用 `[OK]/[FAIL]/[--]`，避免下游块标记误读）；`report.json` 加 `fmts.<fmt>.diff_scope`（多记录聚合 body>unknown>notes_only）。单测 `TestBodySidecar`（8）+ `test_report_json.TestBuildReportJson.test_diff_scope_aggregate`；全量 1126 OK。文档：`校验说明书.md` §5 + `校验report.json说明.md` §3。
    - [ ] **（可选/低）Q1** html 校验失败回退 txt 基线：现决议**不回退**（设计使然，非漏写）——`verify.bases.html=["html"]`、`resolve_bases` 只试链内；实质结构对不上（html 侧校注 inline 保留 `strip_jiaozhu=False`，txt 基线经 `_norm_official_txt` 注挪文末，直接比必红），且会掩盖 html 特有问题（见 `校验说明书.md` §4.2d 排查要点）。仅作可选增强，默认不开。
- [x] **已完成** GUI 转换后校验反馈修复（2026-09-10 用户点档：结果/进度/汇总）
  - 根因：`BatchWorker._verify_one` 仅 `log.emit`（接 statusBar 瞬时消息，被后续覆盖）；行状态不含校验；`total_units` 不含校验；无汇总/日志窗
  - 落点：`pycbeta/gui/__main__.py` — 新增信号 `row_verify(int,level)`/`verify_result(dict)`；`_verify_one` 返回记录 dict（status/missing/extra/total/official_kind/official/gen_cmp/src_cmp，异常 `status=error`）；`run()` 校验前状态列 `校验中（fmt）…`、校验单元计入总进度、逐行 `_row_outcome` 综合「渲染+校验」终态、**校验报告追加到文件列产物列表末尾**（`*_compare_*.txt`，与 docx/txt 同列可点击打开）；`_on_verify_level` 状态列着色（通过 `#2e7d32`/失败 `#c62828`/无基线灰）；`VerifySummaryDialog`（通过/失败/无基线计数 + 逐项明细 + 打开报告目录，报告落 `out/{fmt}/`；无结果不弹、失败不强制弹）；`_start` 重置结果并接线
  - 验收：`TestVerifyFeedback` 5 项（含 `run()` 报告入文件列）；offscreen 集成冒烟（T0349 txt）`verify_results` 完整、状态列 `完成｜校验 失败1` 红色；全量 506 OK
- [x] **已完成** GUI 验证总报告 + xml_dir 版本抽检 + P5b 内联校勘 lem-only（2026-09-10）
  - 背景：新版 XML `單卷版 XML TEI P5b`（CBReader 书库）把校勘内联 `body <app n><lem>已</lem><rdg>巳</rdg></app>`；泛型渲染 lem+rdg 双吐 → 「已巳又語」（发布版 P5 把 base 放正文、app 放 back，故从未触发）。放弃 CBReader 作数据源后仍保留 `xml_dir`（改指本地 `cbeta-org/xml-p5` 全仓库）
  - A 修复：`render_docx/html/md/txt` 的 `_render_e` 内联 `app` 只渲 `<lem>`（无 lem 落空），`verify._extract_xml_parts` 镜像；`test_txt.TestInlineAppLem` 4 项 + 辅轨/四格式校验
  - B 抽检：`fetch.inspect_xml_source(xml_dir, sample=5)`（读文件头 `<edition>`；非「XML TEI P5」→ `safe=False`）；GUI `SourceDialog.accept` 与转换首启兜底弹窗「仍使用/清除该路径/取消」（清除写回用户槽），`panel.xml_dir_warning`/`clear_xml_dir`；CLI `--xml-dir` 非 P5 打印警告后继续；`test_fetch.TestInspectXmlSource` + `test_gui` 3 项
  - C 报告：`verify_one` 返回补 `norm_gen/norm_official`；新增 `format_verify_report(records, diff_lines, max_diff)`；GUI `run()` 每行跨 xml 累积产物、行末写 `{stem}_verify_report.txt` 并**排文件列最后**（`*_compare_*.txt` 仍在前）；`_verify_one` 保留整条返回 dict；`test_gui.TestVerifyFeedback.test_format_verify_report` + `run()` 报告断言
  - 迁移：存量 P5b（现仅 `X59n1077.xml`）需跑数据源窗口「更新XML」或删 work XML 重材料化，验收 `edition` 回 `XML TEI P5`
  - 未做（另议）：P5a/P5b 真兼容（`<choice>` 对齐 + body `type=add` 校勘注转脚注 + `@rend=hide`），当前仅正文 base 正确、校勘注仍缺
  - 2026-10-21 语料实测：229 XML 全为 `XML TEI P5`（0 P5a/P5b）；`choice` 11 处、`rend="hide"` 409 处均在 back（`choice` 父 `t`/`l`；`hide` 全是 `note type="add"`，由 anchor/app 引用），不进正文渲染；`app type="add"` 0 处 ⇒ 主库无样本，暂不立项；仅真正使用 P5a/P5b 源时再做
- [x] **已完成** 报告/文件列/数据源文案/输出命名四项（2026-09-10 用户点档）
  - 报告：`verify_one` 增 `trials`（每个尝试过的基线：kind/missing/extra/total/ok/ctx/norm_official）；`format_verify_report` 标签改 `({fmt}→{基线kind} 缺X/多Y ≤|>阈值N)` 并逐条列出所有尝试基线（标 [OK]/[FAIL]，失败列前 N 条差异）
  - 文件列：验证产物 `*_compare_*.txt` **不列**（仍落盘），只列渲染产物 + `{stem}_verify_report.txt`（排最后）
  - 数据源窗口：「检查电子书更新」→「**更新XML**」；「同时更新已有基线」→「**同时更新电子书**」（去“基线”术语）；状态文案同步
  - 输出命名：默认由 `{id}` 改为 `{id} 书名}`（与下载电子书 work 目录同款），`filename.default_output_name` 跟随 `source.title_t2s` 转简；CLI `resolve_output` + GUI `_out_name_for` 同规则；`--name-template` 仍显式覆盖；html 仍走 renderer 内部命名
  - 验收：`test_cli`/`TestSourceDialog`/`TestVerifyFeedback`/`TestDefaultOutputName` 更新；全量 523 OK；CLI 实测 `-i T12n0349.xml -f txt -o` 出 `T0349 弥勒菩萨所问本愿经.txt`；GUI 冒烟文件列 = [产物, 报告]（无比较文件）
  - 附带修：GUI 子进程 stdout 强制 `PYTHONIOENCODING=utf-8`（中文产物名经 gbk 编码后 `parse_produced_paths` 认不出，致产物不列文件列）
- [x] **已完成** docx 悉昙读音（2026-09-11 用户点档：官方 docx 正文/注释均附 `(raṃ)`）
  - 落点：`parser._parse_chardecl` 增收 `roman`（Unicode 转写）/`roman_cbeta`；`render_docx._render_node` 的 `Gaiji` 分支在字形后拼 `({roman})`（读音走 `latin_font`、纯文本通道不进 ruby、t2s 只转简字形）；`output.show_body_siddham=false` 则正文不显示悉昙字和读音（脚注不受影响，`_footnote_content` 进出挂 `_in_note` 豁免；GUI 注释卡复选「正文显示悉昙字和读音」默认勾，落 `output` 可持久化；CLI 主链/docx2pdf 中间档/校验 `generate_formal` 三处透传）；仅 RJ/有 roman 记录的 `<g>` 触发，普通缺字不动；html 出官方同款 `<span class='ranja' roman code char/>` 空元素 + CSS 显示（文本零影响），md/txt 出官方同款裸读音（`raṃ`，P3 辅轨同步镜像）；html/md/txt 不出括号读音
  - 转写行：主题新增 `transliteration` 标签（`pdf_docx.css`/`cbeta_golden.css` 默认朱砂 `#FF4400`，CSS 编辑器「转写」行可调；docx/html `cb:tt` 的 `sa-x-rj` 行包裹）
  - `<cb:sg>`：四渲染器统一半角括号（如 `(音𫬠)`，官方三端一致）
  - 验收：`test_docx.TestSiddhamReading` 8 项 + `test_txt.TestSgAndSiddhamTxt` 3 项；X59 实测生成侧 `(ra` 0→**36**（与官方 36 对齐），主轨 `docx→docx` **缺12/多0**→`sg` 修后 **0/0 通过**；txt 主轨残差系注音表/尾注结构差（官方无注音 `南na…`、无校注尾注），与本次无关
  - 附带修：`_render_tt` 两行间不再插全角空格（官方直连如 `歾(raṃ)㘕`；裸 U+3000 run 无 `w:rPr` 在部分 Word 回退缺字形显示方框）
- [x] **已完成** 图注对齐 + `【】`收窄 + 〔〕注音剥离确认（2026-09-11 用户点档：官方 txt 有 `【圖：X59p0224_01.gif】` 而我方缺，报告却缺0）
  - 根因有二且互相掩护：`normalize` 的 `【】`≤20 字剥除把官方图注也剥了（两侧都没了）；我方 txt/md 根本不吐图（`figure`/`graphic` 无分支，泛型剩空）
  - 落点：`normalize` 改 `【(?![^】]*圖)[^】]{1,20}】`（见证标记照剥，含圖保留）；txt/md `figure`/`graphic` 出 `【圖：<basename>】`（md 比官方 txt，口径一致；docx/html 保持丢弃，官方亦无文字）；P3 辅轨 `chunks()` 同镜像
  - 〔〕：实测我方注音 `涅槃〔niè pán〕` 等 5 处经 `normalize` 全剥（5→0），比对输入干净；用户配置默认括号走既有规则，无需改。残留 display 文件（`*_compare_*.txt` 原样落盘）属展示用途
  - 验收：`test_txt.TestFigureMark` 4 项（txt/md/aux 标记、见证照剥图注保留、注音剥除）；X59 实测我方 txt 4 标记齐（官方 2+2+0），txt 缺0/多579 不变（注音表/尾注结构差，既有）
- [x] **已完成** txt/md 逐字咒文表转写参数（2026-09-11 用户点档：官方 txt 无 `南na無mo…`）
  - 现象：官方 txt 的逐字咒文表（`南無颯哆喃`）不显示梵文罗马字母，我方 txt 显示 `南na無mo颯sa…`
  - 规则（实证）：`<cb:tt>` **无 `place="inline"`**（逐字咒文表，全库 26 个）官方丢转写；`place="inline"`（68 个）与散文读音保留。非“dharani 段落”一刀切（首版误用导致缺32）
  - 落点：`output.show_dharani_transliteration`（默认 false）；txt/md `_render_e` 的 `tt` 分支按 `place` 置 `_drop_sa`，Gaiji 读音在该上下文丢弃；`verify._extract_xml_parts` 的 `chunks` 同镜像；CLI/`generate_formal` 透传
  - 验收：`test_txt.TestDharaniTransliteration` 4 项；X59 txt `缺0/多457`（579→457，余为注音表/尾注结构差）；docx `0/0` 不变
- [x] **已完成** 基线只用 text-with-notes + 基线平展进格式目录 + 删 zip + 更新XML补 txt_notes（2026-09-11 用户点档）
  - 背景：官方 plain `text` 实测 X1077/T0349 校注均 0 行，对比较无意义；`text-with-notes` 才有校注（X1077 135 条）。旧比较拿 plain text 当 baseline → X59「多457」
  - 弃 plain txt：`fetch` `ALL_FORMATS`/`DEFAULT_DOWNLOADS`/`_BASELINE_FORMATS`/`_ZIP_FORMATS` 去 `txt`；gui `DOWNLOAD_KEYS`、config.json downloads 去 `txt`；`find_official` 去 `kind="txt"`。**渲染格式 `-f txt` 保留**（只删官方下载 kind）
  - 基线选择：txt/md `base_kind="txt_notes"`（`verify.py`/`cli.py --verify`/`test/verify_text.py` 三入口），自动下载 `need` 用 `txt_notes`；txt 不回退、md 保留 html 兜底
  - 新布局：work 根放 XML；基线进格式同名子目录**平展**（`html/ docx/ epub/ odt/ txt/`＝text-with-notes），`_unzip_flat` 忽略 zip 内目录层次，解压后删 zip；新增 `_fmt_dir/_fmt_ext/_collect_fmt`，弃 `_txt_subdir/_collect_txt_flat`；`_fetch_baseline_flat` 重写；`find_official` txt_notes 走 `**/txt/{s}_*.txt`（兼容旧 `{s}.txt_notes/`）
  - 更新XML：`check_ebook_updates` 的 `with_baselines` 除刷新已有格式外，**缺失 `txt_notes` 自动补下**
  - normalize：官方悉昙占位 `◇`(U+25C7) 与私用区字（PUA）统一为 `□`（text-with-notes 用 ◇，生成侧用 PUA）
  - 验收：`test_layout`（落盘 `html/`、zip 平展进 `txt/`、缓存不重下）、`test_verify`（txt_notes 落 `txt/`）、`test_fetch`（present/补下）更新，全量 548 OK；X59 端到端重材料化后布局正确、无 zip；docx `0/0`；txt→txt_notes `缺0/多76`（注文交错位置 vs 集中，先天语义差）
- [x] **已完成** txt 正文尾注标记 + 悉昙 `◇` 占位（2026-09-11 用户点档：正文无标记与文末尾注对不上）
  - 根因：`TxtRenderer._render_noteref` 内容进 `_fn_notes` 后 `return ""`，正文无任何标记（md 早有 `[^n]`）；且 PUA 悉昙字官方用 `◇` 而我们吐私用字
  - 落点：`render_txt.py` 加 `_fn_seq`；正文 NoteRef/App 处返回 `[n]`，文末注块改逐条 `[n] 内容`（一一对应）；`show_notes=false` 时标记与注释全无（`_render_noteref` 短路，不动）；RJ 悉昙无 roman → `◇`，逐字咒文表内整行不显示（有/无 roman 都丢）；`verify._extract_xml_parts` 镜像 `sg` 括号与 RJ roman/`◇`/咒文表丢弃
  - 比较不变：`normalize` 两侧都剥 `[n]`/`[A**]` 标记、`◇`/PUA 都归一 `□`；主轨 txt→txt_notes 仍 `缺69/多9`（较改前 55/9 变动系去掉正文伪 PUA、注块对齐波动，门禁外）；docx/html 不受影响
  - 验收：`test_txt.TestTxtRenderer` 改/加（`[1]`↔`[1] 内容` 对应、show_notes=false 全无、RJ 无 roman→`◇`）；全量 550 OK
  - 已知残留（门禁外，另议）：aux P3 仍 `缺85`——`No.` 令牌镜像（待办3）+ 注块选取/顺序差（我方 136 条 vs 官方 252 行）
- [x] **已完成** 逐字咒文表内 NoteRef 注内容丢读音修复（2026-09-11 用户点档：注释 21–38 成 `【CB】【卍續】`）
  - 根因：`TxtRenderer._render_noteref`/`_render_app` 在当前上下文渲染注内容；逐字咒文表 `<cb:tt>` 内 `_drop_sa=True` 连带把注内悉昙 `<g>` 也丢了 → `na【CB】ba【卍續】` 变 `【CB】【卍續】`。md 同病
  - 落点：txt/md 新增 `_render_note_content(note)`（渲染注内容时临时置 `_drop_sa=False`，结束恢复），`_render_noteref`/`_render_app`/`_render_inline_note` 统一走它
  - 收获：X59 主轨 txt `缺69/多9` → **`缺0/多9`（≤阈值，通过）**；docx `0/0`；P3 aux `缺85` → `缺16`（余为 `No.` 令牌镜像 + 个别注序，门禁外）
  - 验收：`test_txt.TestTxtRenderer.test_note_inside_tt_keeps_reading`；全量 551 OK
- [x] **已完成** 注释方式可配（footnote/endnote/inline）+ GUI 三值下拉 + CLI/SDK 取 config（2026-09-11 用户点档）
  - 关键事实：三值中 footnote/endnote 仅 docx（及 docx2pdf→pdf）有别（页底 vs 文末）；html/epub/md/txt 代码只判 `inline`，footnote≡endnote，故单一值不损现状
  - `config.json output` 增正式键 `"notes": "footnote"`；`theme.resolve_notes(presets, fmt=None, explicit=None)`（explicit>output.notes（非空合法）>默认 footnote）供 SDK
  - CLI：`--notes` 显式 > `config output.notes`（main 里回填 args.notes）> 按格式默认；help 同步
  - GUI：注释卡顶部「注释方式」纯三值下拉（页底脚注/文末尾注/括号内联，无“跟随”），get/set roundtrip；子进程经 snapshot `output.notes` 生效（`build_render_cmd` 无需改）
  - 校验 `generate_formal` 注释模式保持固定（html/epub=endnote、docx=footnote、md/txt=footnote），不读 `output.notes`（否则官方对照口径变）
  - 验收：`test_theme.TestResolveNotes` 4 项 + `test_gui.TestNotesTab.test_notes_mode_default_and_roundtrip`；CLI 实测 `--notes inline` 出内联括号、无 `[n]`
  - 布局微调（2026-09-11）：「显示注释」行加标签「注释总开关」；「注释方式」下拉收窄（maxWidth 110）并与 inline 括号同行、居其左（HBox）；`inline_brackets` 注释明确为「inline 夹注 + 注释方式=inline 的全部注释」括号、六格式、与注音括号独立
- [x] **已完成** 正文夹注 vs 校注内联：tag 分离确认 + 括号拆分 + show_notes 语义修正（2026-09-11 用户点档 A/B/C）
  - 结论：原文夹注 `<note place="inline|inline2|interlinear">` 的 docx/html tag（`doube-line-note`/`interlinear-note`）本就与校注内联（`note-inline`）不同；唯一共用为括号键，另 `show_notes` 门控 docx/html 与 txt/md 不一致
  - B：新增 `output.note_inline_brackets`（默认 fullwidth）专管校注内联；`output.inline_brackets` 专管正文夹注；`note_inline_brackets` 缺省回退 `inline_brackets`（旧调用/官方对照不变）；四渲染器 + epub/pdf 透传；CLI `args.note_inline_brackets = out_defaults.get(...) or args.inline_brackets`
  - A：正文夹注属原文，**不受 `show_notes` 控制** → 去掉 `render_docx._render_inline_note` / `render_html._render_note` 的 `if not show_notes: return ""`；txt/md 本就无门控，四格式统一
  - C：CSS 编辑器行名区分——`doube-line-note`→「正文夹注·双行」、`interlinear-note`→「正文夹注·单行」、`note-inline`→「校注内联」；GUI 注释卡「inline 括号」拆为「正文夹注」（与注释方式同行）+「校注内联括号」
  - 验收：`test_render.TestNoteInlineSemantics` 5 项 + `test_txt` 2 项
  - 追加（2026-09-11）：校注内联括号增 `corner〔〕`/`square[]`（GUI 优先排前，`theme.bracket_pair` 统一映射，未知回退全角）；GUI 转换失败不再只留泛化「失败」——`_render_one` 记 `_last_render_err`（子进程输出末行），`_row_outcome(..., render_errors)` 写入状态列，`✗ {fmt} 生成失败：…` 同步状态栏；`test_gui` 2 项 + `test_theme.TestBracketPair` + `test_render` 1 项
- [x] **已完成** 校验产物独立子目录 + 绿灯非 0/0 也列差异 + CLI 渲染失败友好化（2026-09-11 用户点档）
  - 布局：校验产物（重生成 + compare + report）落 `{输出}/{id 书名}（验证）/`（内部保持 `{fmt}/` 结构；渲染输出仍在输出根）；仅勾选「转换后校验」时启用
  - GUI：`BatchWorker._verify_dir(out_dir, wid, title)`（`default_output_name` + `（验证）`）；`_verify_one` 的 `out_root` 与验证总报告均改该目录；`test_gui.TestVerifyFeedback.test_verify_dir_naming` + `test_run_appends_verify_report_to_files` 更新
  - CLI：`--verify` 的 `verify_root`（镜像输出根）+ `verify_dir`，合并官方文件与 `report.txt` 落该目录（每经书一份），移除旧 `src/out/verify` 全局报告
  - 报告：`format_verify_report` 差异行条件由「失败」放宽为「失败 或 缺/多≠0」，绿灯也列前 `diff_lines` 条【源】【新】
  - CLI 失败：`process_file` 捕获 `OSError` → stderr `{id}: {fmt} 生成失败：{e}`、**继续其余格式**、返回失败计数；`main` 末 `return 1 if render_failed else 0`
  - GUI 解析：`_render_one` stdout/stderr 分流，`_last_error_line` 优先 traceback 异常行 / 关键词行（避免被缓冲的正常 stdout 行顶掉）
  - 验收：`test_cli.TestProcessFileErrors` + `test_gui` 4 项；CLI 实测锁 docx 后 `-f docx,txt` 出 `X1077: docx 生成失败：[Errno 13]...`、txt 仍生成、`EXIT=1`；`--verify` 实测出 `{id 书名}（验证）/report.txt`
- [x] **已完成** 注释卡布局/提示打磨 + 校验汇总弹窗分级配色（2026-09-11 用户点档）
  - 对齐：「注释方式」提升为 form 行标签，其 combo 与「校注内联括号」combo 左对齐；「正文夹注」仍在注释方式行右侧
  - 置灰：`_sync_note_brackets_enabled()`——注释方式≠括号内联时「校注内联括号」禁用；`notes_mode` 变更联动 + `set_options` 回填后同步
  - tooltip：注释方式/正文夹注/校注内联三条精简为 2 行（显式 `\n`，规避 CJK 单行超宽不折行）；正文夹注补「属原文、不受显示注释总开关控制」
  - 校验汇总弹窗：汇总计数与逐项明细分级配色——0/0 通过绿 `#2e7d32`、通过但缺/多≠0 蓝 `#1565c0`（标签「通过(有差)」）、失败/异常红 `#c62828`、无对照灰；明细由 `QPlainTextEdit` 改 `QTextEdit`(HTML)
  - 验收：`test_gui.TestNotesTab` 2 项 + `test_verify_summary_dialog` 扩展
- [x] **已完成** PDF 校验跳过 + EPUB 临时目录清理 + 汇总弹窗有差改蓝（2026-09-11 用户点档）
  - PDF：官方无 PDF 基线，`verify_one(fmt="pdf")` 直接返回 `status="no_baseline"`（`detail` 说明正文由 docx/html 覆盖）；CLI `--verify` 同步跳过（原来会把二进制 PDF 当文本读、且会走到 `generate_formal` 抛 `unknown format` 标异常）；报告 `[--] pdf no baseline`
  - `_epub_tmp`：`render_epub.render_work` 加 `try/finally` + `shutil.rmtree(tmp, ignore_errors=True)`，中间 HTML 目录生成后即清（成功/失败都清），不再污染输出根与校验目录
  - 汇总弹窗「通过(有差)」色由橙 `#ef6c00` 改蓝 `#1565c0`
  - 验收：`test_verify.TestPdfNoBaseline` + `test_md_epub.test_epub` 断言无 `_epub_tmp` 残余
- [x] **已完成** PDF 校验委托管线源格式 + 「已覆盖」态（2026-09-11 用户点档：A + 灰提示 + 保留中间件）
  - `render_pdf.pdf_source_fmt(engine, vertical)`：docx2pdf→docx / html2pdf→html（与 render_one pdf 分支判定一致）
  - GUI `_verify_one`：pdf 且源格式未选中 → 委托 `verify_one(源格式)`，显示 `pdf→docx|html`；源格式已选中 → `status="covered"`（灰「已覆盖」，不重复）
  - CLI `--verify`：pdf 未选中源格式 → 用渲染留下的中间件（`{id 书名}.docx` / `{id 书名}*.html`）按源格式比对，列 `pdf→docx`；已选中 → `[--] pdf 已覆盖（已由 docx 校验）`
  - `VerifySummaryDialog`：新增 `covered` 灰态与「已覆盖 N」计数，不计入「无对照」；`format_verify_report` 增 covered 行
  - 中间件保留现状（不清理）：`{id 书名}.docx` / `{id 书名}.html` 留在输出根
  - 验收：`test_gui.TestVerifyFeedback` 3 项（委托/已覆盖/报告 covered）+ 对话框 covered 项；CLI 实测 `-f pdf --verify` 出 `pdf→docx`、`-f pdf,docx --verify` 出 `[--] pdf 已覆盖`
- [x] **已完成** epub 基线落错目录修复 + 注释卡分组重排（2026-09-11 用户点档）
  - 根因：GUI 校验把 `tmpcfg`（run.json）传给 `verify_one`，而 `verify_one` 用 `load_presets(config_path)` 直读 → run.json 无 `source` → `ebook` 回退 `source`（=work 目录）→ `work_dir(workdir,…)` 嵌套建 `{work}/{id}/epub/`
  - 修：`theme.load_effective_presets(path)`（run.json 含 RUN_KEYS → `load_run_config`+`resolve_effective_config` 解算；否则 presets 直读）；`verify_one` 的 cfg/annotations/inline_brackets/auto_fetch 取值全部改用它（顺带修好 run.json 下 annotations/verify 配置不被读取）
  - 防呆：`fetch.work_dir` 若 `root` 本身即该 work 目录（basename 的 work id 匹配）直接返回，杜绝 `{work}/{id}` 嵌套
  - 手工迁移已落错的一份：`X1077 准提净业\X1077\epub\X1077.epub` → `X1077 准提净业\epub\X1077.epub`
  - 注释卡重排（与「注释总开关」解耦）：`正文夹注`（第1行）→ `正文显示悉昙字和读音`（第2行）→ `注释总开关`（第3行）→ 脚注每页/压制标题 → 注释方式 → 校注内联括号；三 combo 用 `label+_wrap(combo)` 左对齐
  - 验收：`test_fetch.TestWorkDir.test_root_is_workdir_no_nesting` + `test_theme.TestLoadEffectivePresets` 2 项 + `test_gui.TestNotesTab.test_notes_on_label_and_row` 重写
- [x] **已完成** html 校验两处修复：官方 head No. 空白锚定 + `<cb:sg>` 括号（2026-09-11 用户点档）
  - issue1：`verify._strip_official_no` 原 `^token` 无空白锚定，官方 html 提取行前导空格（`"  No. 1077-A …"`）→ head 令牌剥不掉。改 `^([ \t\u3000]*)token[ \t\u3000]*` 替换为 `\1`（保留前导空白、连带 token 后空白），与生成侧 `strip_head_no` 同形；CLI 校验同源修复
  - issue2：`render_html._render_e` 的 `_render_misc` 标签清单缺 `"sg"`，`<cb:sg>音<g>𫬠</g></cb:sg>` 落到默认分支丢括号（`㘕音𫬠`）。清单加 `"sg"` → `㘕(音𫬠)`，与 docx/txt/md 及官方半角一致；epub/pdf(html2pdf) 复用同渲染器一并修好
  - 验收：`test_verify.TestStripOfficialNo.test_official_leading_ws_kept` + `test_render.TestSgParens` 2 项；实测 `verify_one('html', config_path='run.json')` 官方 compare 不含 `No. 1077-A`、生成 compare 含 `(音`
- [x] **已完成** GUI 目录/文件：支持选 ID 列表文件批量（2026-09-11 用户点档）
  - 新增 `文件…` 按钮（`QFileDialog.getOpenFileName`，过滤 `*.xml *.txt`）；`目录…` 保留目录选择
  - `gui.__main__.parse_work_ids_file(path)`：逐行取 `is_work_id` 命中的 token（去重保序），兼容 `test/mini-test.txt`（`T0349 彌勒…`）、逗号/分号/顿号、行首序号、`#` 注释；utf-8 失败回退 gbk
  - `_collect_jobs`：输入为 `.xml` → 单文件；为其他文件 → 按 ID 列表生成 `kind="id"` 批量（材料化/自动下载）；`path_edit` placeholder/按钮 tooltip 更新
  - 验收：`test_gui.TestParseWorkIdsFile` 2 项
- [x] **已完成** div 内标题行距被盖住（2026-09-11 用户点档：head 设 1.0 仍出 1.4）
  - 根因：`_para` 的 `div_extra`（本意只带 div 边距）含 `docx_para(div)` 经 body 回退带入的 `w:line=336`，以内联 pPr 覆盖命名样式（实证：壇法段落 `pStyle=head` + 内联 336）
  - 修法：段落标签自身有 line-height 时，从 div_extra 只摘 `w:line`/`w:lineRule`（留 before/after；全文件无 div-* 写行距，去掉的恒为回退值）；无自身值（verse 等）继续拿回退，零回归
  - 另答疑：CSS 删键≠继承 body——`DEFAULT_THEME` 先打底（`p: 1.8`，`theme.py:120`），删键只是不覆盖；继承分支只对无默认值的标签生效；`apply_page_typography` 另有"p 没亲笔写过跟页 body 走"的页级跟随（有 body_line_height 的纸才触发，verify 路径不调）。结论：行距保持显式写法
    - **2026-09-13 更新**：`DEFAULT_THEME` 已删除（方案 B，见文末），上述"删键不覆盖"已不成立——CSS 现在是唯一定义处，删键即回退继承/出厂缺失由完整性测试报错。
  - 验收：`test_docx.TestDivExtraLineHeight` 3 项；X59 实证壇法段落只剩样式引用、无内联 line；出厂值契约测试同步新值（p 1.5→1.4、head 上边距 1em→0.5em）后全量 629 green
  - 后续（2026-09-12 用户调参）：`div.div-xu` margin-bottom 0.3em→1em；`test_body_rhythm_uniform` 的 `w:after` 断言 72→240 同步，全量回绿
- [x] **已完成** 注释补 cf（confer 参考）+ 西文字体（--font-latin）进 run rFonts（2026-09-12 用户点档）
  - cf 取证：官方三格式不同——html/txt 只为 add 型注追加 `(cf. a; b)`（无前导空格），docx 为全注型追加 ` (cf. a; b)`（前导空格）；我们此前 docx/txt/md 全缺
  - docx：`_reset_state` 建 `_app_by_n`（+ `_iter_all`）；`_cf_run` 追加 ` (cf. a; b)`（`; ` 连接；inline 模式随 note-inline 标签，否则 footnote）；`_render_noteref`/`_render_app` 接入
  - txt/md：`_cf_suffix` 仅 add 型注追加 `(cf. a; b)`（对齐官方 text-with-notes；mod/orig 不加）
  - 西文：`theme.docx_run(..., latin=)`——`w:ascii/hAnsi` 走 latin（`--font-latin`，cli 已解析），`w:eastAsia` 仍首个中文名；`render_docx` 三处（`_run_rpr`/`_rt_rpr`/`_style`）传 `self.latin_font`；修掉「脚注样式西文字体=使用中文字体」
  - 追修（2026-09-12 用户反馈 `舍衛【大】，～Sāvatthī` 的 ā/ī 未转西文）：`w:hint="eastAsia"` 会把 **East Asian Width=A 的拉丁字母**（ā U+0101/ī U+012B 等带附加符号者）判给 eastAsia 中文字体；已去掉 hint（`docx_run` 不再输出），按 Unicode script 走 hAnsi=西文字体，CJK 全角标点（EAW=W/F）仍走 eastAsia。显式字体 run（gaiji/读音 `ascii=eastAsia`）与 WPS EQ 域 rPr 的 hint 无视觉影响，未动
  - 校验无影响：`normalize` 已剥 `\(cf\.[^)]*\)`，cf 增减不改缺/多
  - 验收：`test_docx.TestNoteCf` 4 + `TestLatinFont` 2 + `test_txt.TestNoteCfTxtMd` 3；T01 真实数据内存断言 `0006001`（两 cf ` (cf. 楊郁文…; K17n0647_p0820a22)`）、`0001b0201`（` (cf. Q17_p0302a30)`）；X59 docx 实测 3 处 cf + footnote 样式 ascii=Calibri；全量 638 green
- [x] **已完成** EQ 域继承上下文样式 + docx 注音按原书页重注（2026-09-12 用户点档）
  - Q3 根因：`_eq_field` 的 begin/instr/end 只带最小 rPr（rFonts+lang），WPS/Word 用域 run 格式渲染域结果 → 夹注内「般若」（X59 `第九手持般若經卷`）等注音掉成正文样式；修法 `_eq_field(..., base_rpr)` 注入 `_run_rpr(tags)`（去 `<w:rPr>` 壳）+ 原 `w:lang`，`Font:`/`hps` 不动。`ruby`/`inline` 模式本就带 tags，无需改
  - Q2：`repeat=page` docx 专属改为**按原书页 `<pb>` 重置已注集合**（`_render_node` Pb 分支 `_page_repeat → _ann_seen=set()`），翻页重注；html/epub（每卷文件）、md/txt（整篇）维持现状；无 `<pb>` 回退到智能分页单元/按卷（split）。GUI 第三项改「每页只注首次」+ tooltip；`config.json annotations.repeat` 注释同步
  - Q1：段前/段后**保持磅**（`w:before`，与 PDF/HTML 的 em 语义一致），不改行；官方 styles.xml 虽用 `beforeLines`，但官方 document.xml 也用磅，且行换算受 line-height 影响会偏离
  - 验收：`test_annotate.TestRender.test_docx_field_inherits_context_style` + `test_docx.TestAnnotationPerPage` 3 项；全量 642 green
- [x] **已完成** 竖排取消居中（title/head/juan/pin），横排居中（2026-09-11 用户点档；byline 已另做）
  - 机制：CSS 文件即事实来源——`pdf_docx.css` 加 `body.vertical-rl h1.title/p.head/p.juan/p.pin {text-align:left}` 块（横排无该 class 恒惰性；整套替换主题需自带）；`theme.VERTICAL_UNCENTER` 名单 docx/pdf 共用；docx `_para` 三分支内联 `<w:jc left/>` 覆盖（竖排 left 即顶部）；pdf `_wrap` 竖排加 body class
  - 探针实证（Chromium）：vertical-rl 下 `left`==`start`==顶部（y=1），`center` 居中，`end` 落底——无需 fallback
  - 未动：`TAG_SELECTOR`/compounds 解析、`cbeta_golden.css`、styles.xml、横排输出（字节零变化断言）；X59 竖排实测 46 处 left（含既有 series-title 1 处）
  - 验收：`test_theme/test_docx/test_pdf` 各 1 组（名单/CSS 块/body class/开关联动）
- [x] **已完成** byline 署名统一右对齐（2026-09-11 用户点档；竖排 A 搁置）
  - 查明：html 恒 `class="byline"`（右，对官方）；docx 只认大写 `"Translator"`，X59 小写 `translator` 落 `"byline"`（右）纯属碰巧，T0349 大写则走 `translator`（中）——跨格式本来就不一致
  - 改法：docx 映射大小写不敏感 + `pdf_docx.css` 的 `p.author, p.translator` center→right（与官方 golden `.byline` 右对齐看齐；译者特有覆盖示例注释同步）；X59/T0349 实测均落 `translator` 右对齐
  - 验收：`test_docx.TestBylineRight` 2 项（大小写映射 + `jc=right`）
- [x] **已完成** 文件按钮移编号列表行 + figures 进数据源 + docx 内联括号字号（2026-09-11 用户点档）
  - 布局：`目录…` 留目录/文件行、`文件…` 移编号列表行最右；`ids_edit` placeholder 改为“逗号/空格分隔；或用「文件…」选 ID 列表 .txt”；`path_edit` placeholder 回到“XML 目录 / 单个 .xml”
  - 数据源：`SourceDialog` URL 表显示用出厂 `downloads` 打底合并（用户文件缺 `figures` 等键也可见、可改、可存）；新增 `test_figures_url_visible_with_factory_default`
  - docx 内联括号：根因 `_current_tag()` 只取栈顶——`_render_inline_note` 括号按 `(head,doube)` 解 16pt、内容按 `(doube,)` 解 9.6pt（X59 卷首实测 32 vs 19）。修法：先压注记标签再取 tags（括号与内容同解算）；`_render_inline_mode` 括号只带 `note-inline`（去外层）。验收 `test_docx.TestInlineBracketSize` 2 项；html/md/txt 无字号概念不受影响
- [x] **已完成** 独立窗设置区折叠：配置 ▾/▸ 总开关（2026-09-11 用户点档）
  - `MainWindow` 在输入区与设置区之间加 `QToolButton` 开关，`toggled → panel.setVisible` + 箭头 `▾/▸` 同步，默认展开
  - 收起 `XmlOptionsPanel` 整体（tab 区 +「配置」分组），批量列表因纵向 stretch 自动放大；不碰任何数据逻辑，不持久化
  - 验收：`test_gui.TestMainWindowUx.test_cfg_toggle_collapses_panel`
- [x] **已完成** 图片段对中+无首行缩进；折叠按钮 redesign（2026-09-11 用户点档）
  - figure-only `<p>`（忽略空白/Lb/Pb/anchor/milestone 后全为 figure/graphic）走新 `figure` 主题标签：`p.figure {text-align:center; text-indent:0; margin 0.5em}`（`pdf_docx.css`，超出官方——官方 docx 用 default 样式无居中）；`TAG_SELECTOR`/`_STYLED_PARAS`/样式编辑器「图片」行三件套；图文混排段保持原样
  - html figure-only 出 `class="figure"` + golden `p.figure{text-align:center}`（X1116 无图，golden 测试不受影响；校验纯文本比对不受影响）
  - 折叠按钮：删独立整行，改为输入来源行最右扁平无文字小箭头（22px，hover 才显底，tooltip），逻辑/属性名不变
  - 验收：`test_figures.TestFigureOnly` + `TestFigureParagraphCentered` 4 项（docx `figure` 样式/`jc center`/无 `firstLine`、混排保持 `p`、html class）；`test_cfg_toggle` 加无文字/扁平断言
- [x] **已完成** 校验汇总弹窗显示生成目标文件名（2026-09-11 用户点档）
  - `BatchWorker.run` 取本格式实际产物 `paths[0]` 的 basename 作 `gen_name` 传入 `_verify_one`（pdf 委托时即 pdf 产物名）
  - `VerifySummaryDialog._line`：`[{tag}] {gen_name}{cnt}`，无 `gen_name` 回退「{id} {fmt}」；例 `[通过] TX0006 太虚大师全书…docx 缺0/多0`
  - 验收：`test_verify_summary_dialog` 增 gen_name 断言
  - 顺带：`TestRenderYP0019` 输入 XML 兼容官方名（`YP13n0019.xml`）且官方 html 基线随新布局在 `{work}/html/`、缺失则 skip（外部数据重材料化，非代码回归）
- [x] **已完成** 还原出厂确认 + 校验参数持久化默认开 + 报告差异行数改名（2026-09-11 用户点档）
  - 还原出厂：`panel._on_reset` 执行前弹警告确认（「当前配置会被还原为出厂配置」，确定/取消；取消不动作）
  - 校验持久化：出厂 `config.json` verify 块补 `enabled: true`（默认打开）；`set_options` 缺键默认亦 True；`get_options`/`_presets_merged` 本就 roundtrip 开关/阈值/差异行数/自动下载/卷限定
  - 改名：校验卡「差异行数」→「**报告差异行数**」
  - 验收：`TestConfigBar` 新增 2 项（默认开+开关/阈值持久化回读；还原确认/取消）；注意本机 `config.user.json` 若仍 `enabled:false` 以用户文件为准（出厂默认只影响新配置）
  - 防呆（2026-09-11）：`config.user.json` 的 `source` 曾被清空致批量报“未配置”；已恢复 `cbeta_ebook`（`xml_dir` 保持空，等本地 P5 仓库）；`SourceDialog.accept` 在 `cbeta_ebook` 为空时弹确认（确定保存/取消），避免再次误清空
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
  - 纸张绑字号 GUI（2026-09-09）：页面栏"正文"行（字号/行距框 + 跟随 CSS 复选 + 灰字说明），
    取消跟随填出厂 CSS 基线，切纸张/改值说明同步；保存写条目、重勾删键、临时快照同步；
    全量 414 OK，verify 8/0
  - 跟随显示刷新（2026-09-09）：重勾"跟随"不刷显示（disabled 框留旧自定义值，看着像还在用它，
    点两次才对）→ `_fill_margin_spins` 统一显示刷新；附带修同根静默 bug：跟随批量时 base 的
    僵尸 `custom_margins` 进临时快照，CLI 按它渲染而界面显示跟随——`write_temp_presets` 跟随时
    主动剥离；全量 410 OK
  - 取消跟随恢复自定义（2026-09-09）：取消勾选一律填 plain 预设，当场覆盖框里的已存自定义，
    再也回不去 → 取消时优先恢复已存 custom（没有才拿预设作起点）；附带保存后同步内存预设
    （否则刚存的值取消勾选时读不到）；全量 416 OK，verify 8/0
  - 字号单源 body（2026-09-08 用户立项并定 A）：`body{font-size:12pt}` 为唯一源，`p` 删字号走继承；
    `pages.doc_size` 键删除（9 纸张），doc 默认跟 `Theme.base_pt`（p→body 绝对值，未知回 11）；
    `docx_run` 半磅 `int`→`round` + 支持 `%`，`docx_para` font_pt 同样解 em，`_tag_base_pt` 默认走
    base；其余保持 pt（精确直观），em 只留天生相对处；编辑器字号显示回退 body 值（只显示不写回）；
    附带 0.9em 由 21 变 22（注音小字 10.5→11pt，唯一视觉变化，需目检）；全量 382 OK，verify 8/0
  - 纸张绑字号亲笔优先（2026-09-09）：`Theme._explicit` 记录 CSS 解析来源（DEFAULT 不算）；
    `apply_page_typography` 置 body 的同时，p 没亲笔写过才跟（否则 DOCX 里 DEFAULT p=12pt
    盖住 body 覆盖）；用户 CSS `p:14pt` + 16开 → p 保持 14（CSS 语义）；全量 408 OK
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
  - 小重构（2026-09-09，语义零变更）："只缩基准"字面做会改变大字版语义（标题绝对字号不动），故走保持语义路线——抽 `_scale_font_dict` helper 消 tags/compounds 双循环重复；补单测锁此前无覆盖的 compounds 循环（div-xu/head 20pt→30pt）+ helper 直测；全量 419 OK

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

- [x] **已完成** html/epub 使用 CSS（用户增量）（2026-09-17 用户要求列出；2026-10-07 落地，取代 2026-09-08 纯 golden 决议）
  - 落地：`verify.generate_formal` html/epub 分支传 `base_css`（与转换同 CSS；文本提取不受 CSS 影响）；GUI 样式表卡加「html/epub 增量」行（`CssComboBox` 出厂三件套参数化 + `set_user_theme(slot=)` + `run.json html-epub-user-theme` 槽保存）；其余 4 点此前已就绪（resolver user 层 + 去占位警告 + CLI help + 测试）。实测 T0670 html 产物含用户 CSS。单测 `test_verify.TestGenerateFormalHtmlTheme`（3）+ `test_theme`（2）+ `test_gui.TestHtmlThemeRow`（3）
  - 现状：html/epub 基底 = `theme.resolve_html_base_css(run, run_dir, std=args.html_epub_theme, user=args.html_epub_user_theme)`（`cli.py:663`）→ `HtmlRenderer/EpubRenderer(base_css=…)`；`render_html._wrap` 里 `<style>` 顺序 = `base_css` → `theme.raw_css`（html/epub theme=None，无）→ inline_rule → ann_rule → gray_rule
  - 槽分工（run.json）：`html-epub-theme`＝整套替换基底（默认 `cbeta_golden.css`，一般不动）；`html-epub-user-theme`＝**增量**，追加基底之后（层叠后胜）——当前仅占位警告（`theme.py` `check_run_placeholders`）
  - 目标：把 `html-epub-user-theme` 接成 html/epub 的用户 CSS 层，与 pdf/docx 的 `pdf-docx-user-theme` 对称；md/txt 无 CSS 不涉
  - 改动清单（实现时）：
    1. `theme.resolve_html_base_css`：`user` 非空 → `resolve_theme_css(user, run_dir)`（名走 presets/ 用户库或路径；缺文件警告回退）；命中 → 返回 `base + "\n" + 用户全文`（同 `theme_file_text` 层叠）；删除"尚未接线"警告
    2. `theme.check_run_placeholders`：移除 `html-epub-user-theme` 占位警告；`_RUN_TEMPLATE` 注释同步
    3. `cli`：`--html-epub-user-theme` 帮助去掉"占位"（接线已就绪，`cli.py:663` 已传 `user=`）
    4. `verify.generate_formal`：html/epub 分支目前**没传 `base_css`**（恒 golden，与转换不一致）→ 按 `p("html-epub-theme")`/`p("html-epub-user-theme")` 解析（复用 `resolve_html_base_css`）后传入，保证与转换同 CSS
    5. GUI 样式表卡：加「html/epub 增量」`CssComboBox`（列 presets/*.css）+「设为默认」写 run.json `html-epub-user-theme` 槽（把 `css_editor.set_user_theme` 的槽名参数化）；`html-epub-theme` 基底不加控件（golden）
    6. CSS 编辑器：不新建/不扩到 html（左栏行选择器面向 pdf_docx，golden 类名不同）；后续如需“html/epub 模式”（HtmlRenderer 预览）另立
  - 边界：用户层在 golden **之后**，golden 内 `!important` 会压过用户（如 `*` 灰阶仅 grayscale 时输出）；pdf 的 html2pdf 管线走 `PdfRenderer._pdf_css`（=theme），**不读** `html_base`，不在本方案内
  - 测试：`test_theme`（追加顺序/显式开关优先/缺文件回退）、`test_cli`（`--html-epub-user-theme` 生效）、`test_verify`（同槽）、`test_gui`（下拉+设为默认写槽）；user 空时行为零变化
  - 文档：`主题与样式.md`（html/epub 层叠 = 基底 + 用户层）、`安装说明`（CLI 行去"占位"）、`GUI设计`（样式表卡新行）、`第三方调用说明`（公开行为）
- [x] **已完成** 承接下游两处改动 + 修 `--verify` 編號输入的基线源目录（2026-09-17）
  - 下游 `7518865`：独立窗 `--formats`（预填格式勾选，全不匹配回退 pdf）；补 `TestLaunchArgs` 用例
  - 下游 `2a10d12`：CLI `--verify` 用已收集/材料化的 `xmls`（不再把編號当 XML 路径）；
    补修：基线源目录 `src` 仍按输入算（編號时是 `cwd/T0001`，查不到官方基线）→
    改为 文件=其目录 / 目录=该目录 / 編號=已材料化 XML 的 work 目录；实测
    `-i T0349 --verify` 能定位 `{work}/txt/…` 基线（报告正常产出）
  - 文档：`安装说明`（--verify 说明、启动参数加 --formats）、`第三方调用说明` §6.3
    （--formats + CLI --verify 支持目录/編號）
- [x] **已完成** 承接下游 `37a864a`（CLI --verify 改用 generate_formal）+ 修其 base 配置回退（2026-09-17）
  - 下游 `37a864a`：CLI `--verify` 比对档改由 `verify.generate_formal` 生成（`verify` 段覆盖
    `output` 段，inline_brackets/suppress_jhead_dup/show_close_juan 生效），与独立窗一致；
    比对档落 `{验证}/{fmt}/`，不再复用渲染产物
  - 补修：`generate_formal` 原用 `load_run_config(config_path)`——`--config` 传**基础配置 JSON**
    （纯 presets，如 config.user.json）会抛「旧全量快照」并**回退出厂配置**（比对档失真）。
    改用 `theme.resolve_config_arg`（run.json / 纯 presets 宽容分流，与 CLI 同口径）
  - 测试：`test_verify.TestGenerateFormalConfig`（base 配置的 `output.inline_brackets` 确实生效）
  - 文档：`安装说明 --verify`、`第三方调用说明 §6.3`；全量 745 OK（skipped=1）
  - （同时收到上游 `25eccb8`：同名非XML目录不再劫持編號——逻辑正确，无需另改）

- [x] **strip_head_no 去标题行首 No. 令牌**（2026-09-10 用户立项：X60n1116 `<head>No. 1116-B…序`）
  - 落点：`theme.strip_head_no` helper（非变异，跳空节点，余部 lstrip 吃版式空格，正文 No. 不动）+ 六渲染器（docx/html/md/txt 直改，epub/pdf 继承 html；docx jhead 先 strip 再 dedup）+ `config output.strip_head_no=false` + CLI `--strip-head-no` + GUI 排版卡复选（默认不勾）+ verify 三入口联动（生成透传 + 官方行首精确令牌表对等剥离；`--config` 双形态收敛 `_strip_no_from`，旧静默回出厂坑已填）
  - 验收：X60n1116 `-f txt` 开剥离 0/496（missing=0 四令牌 A/B/C/D 全对齐；残留 = 题署行版式差 + body-app 双变体展开，属已知局限类，非 strip 问题）；默认关全量 454/458（4 失败系用户未提交 CSS 改动 `h1.title 30→26pt`，非本件；stash 干净树对照通过）
  - 附带：`docNumber` 独立元素（如 `No. 1116`）两边保留不动；书签/目录文本不同步
  - 导航窗格跟随可见段落（OOXML 同一段落无法分离；mulu 书签名保留 No.）——2026-09-10 用户确认接受现状，不动
- [x] **docNumber 编号行随 strip_head_no 省略**（2026-09-18 用户反馈 T0349 html/epub 仍显 `No. 349 [No. 310(42)]`）
  - 原只剥 head/jhead 令牌，docNumber 独立元素「两边保留不动」；现改为开关开启时 html/epub/md/txt 省略整元素（docx 本恒不显）
  - verify 对等：`_head_no_tokens` 增 docNumber 全文（生成侧省略 → 官方侧按同表行首剥离）；默认关仍与官方电子书一致（保留）
- [x] **插图机制（2026-09-11 用户立项：`<figure><graphic url="../figures/X/X59p0224_01.gif">`，缺图报错？自动下载？）**
  - 远端已核验：`cbeta-git/CBR2X-figures`（`master`，布局 `{canon}/{basename}`，如 `X/X59p0224_01.gif` 6.4KB 确有其文件）；模板 `https://raw.githubusercontent.com/cbeta-git/CBR2X-figures/master/{canon}/{file}` 进出厂 `config.json downloads.figures` + `panel.DOWNLOAD_KEYS`（数据源 URL 表/重置自动兼容）
  - 新模块 `pycbeta/figures.py`（纯函数）：`split_graphic_url/download_url/find_figure/search_dirs/work_figure_dirs/graphic_urls_in_text/gif+png size/looks_like_image`
  - `fetch.ensure_figures`（`{work}/figures` 已有 → `{work}/txt` 基线 bonus 拷贝 → 远端下载；404/失败记缺失不抛错）+ `materialize_work` 四出口与 `ensure_baselines` 自动触发（含图才跑）
  - 渲染：`HtmlRenderer.figure_base` 升级 str|list + `missing_figures`（占位 span 不变）；`EpubRenderer` 透传；`DocxRenderer` 新增 `_render_graphic`（手拼 OOXML `word/media`+rels+`w:drawing`，尺寸读 GIF 头按版心等比 clamp，缺图 `【圖：…】`）；pdf 两管线自动继承；CLI `render_one/process_file` 经 `figures.work_figure_dirs` 接线 + 缺图行打印（GUI 经子进程同口径进状态栏）；`verify.generate_formal` 同路径传入（文本比对不受图片影响）
  - 验收：新 `test_figures.py` 17 项（含 docx 包内 media/rels/drawing + 三部件 lxml 良构断言——曾抓到漏 `</a:xfrm>` 致 Word 打不开）；X59 实测 html 4 张 base64 零占位、docx 4 media 良构、raw 下载 6557B 与基线一致；缺图策略=警告+占位不中断（用户确认）
  - 追修（2026-09-11 用户反馈 X1077 docx/pdf 无图）：根因是 `<figure>` 在 CBETA 里常**内联于 `<p>`**，而 `_render_graphic` 恒包 `<w:p>` → 非法嵌套，WPS 静默丢弃段内图片（最小顶层用例正常，故对照实验才暴露）。修法：`_in_para` 上下文（`_render_para_children` + `_render_tagged` 内统一标记，覆盖 p/pre/head/byline/pin/form/def/verse/cell/脚注/夹注），段内只出 run 级 drawing，块级才包段。实测 X59 pdf（WPS）94 页 4 图；另发现卷名/mulu 区 8 处既有 `title` 嵌套（文字完整，与图片无关，未动）
  - 追修2（2026-09-11）：折叠按钮改绿底白字（各态 stylesheet 同色 + `ButtonText` 调色板设白，箭头靠方向区分；像素级单测锁定）；图片 100% 上限（审计确认只缩小不放大 + `jpeg_size` SOF 解析 + 1x1 原生/2000px 等比压单测锁定）
- [x] **已完成**（2026-09-17，以 `corr-cbeta` 落地，默认关）~~CBETA 校改字标红 `corr`（2026-09-12 用户点档：先记录不修改）~~
  - 实现见本文件「CBETA 校改字标红 `corr-cbeta`」条：parser beg/end 区间包 `E(tag="corr-cbeta")`、
    按**原始** `#wit.cbeta` 判定（非 `【CB】` label）；docx 红 `#FF0000`、html/epub `span.corr`、
    pdf 随管线；**md/txt 不标**；IR tag 取 `corr-cbeta` 以避开 TEI `<corr>`；默认关（`output.corr_cbeta`）
  - 现象/取证：官方**同一颗字**在 docx 用字符样式 `corr` 红 `FF0000`（`<w:rStyle w:val="corr"/>`，T0001_001.docx 全文 12 处；styles.xml `corr` → color FF0000）；官方 **epub** 用 `<span class='corr'>` + `cbeta.css` 的 `.corr{color:red}`；官方 **html 不标红**（全库扫描 0 处 `corr`/`cbeta` span）；txt 无颜色
  - 判定规则：正文所采用的读法 `app/lem` 的 `@wit` 含 **`#wit.cbeta`**（IR 解析为 `app.lem.wit` 含 `【CB】`/`【CB-…】`）→ 该校改字标红；lem 为 `#wit.orig`（如 `['【大】']`）不标。例：`0005009` lem `['【CB】','【宮-CB】']` → 官方红；`0006002` lem `['【大】']` → 不红。T01 lem 含 `【CB` 213 处，juan1 与官方 12 处量级吻合
  - 我方现状：判定信息已具备（`app.lem.wit`），但正文夹在 `<anchor beg.../>…<anchor end.../>` 之间，parser 丢弃 `end` 锚点且不记区间 → IR 无法定位校改字；三渲染器均无 `corr`，golden 只有未用的 `.cbeta`、无 `.corr`
  - 原拟定实施（落地前记录；实际见 `corr-cbeta` 已完成条）：parser `_traverse` 维护 corr 区间栈（`beg` 且 lem 含 `#wit.cbeta` 开，匹配 `end` 闭），包合成 IR 节点 `E(tag="corr", children=[…])`（App 一并包入、正文渲染为空无害；建议按**原始 `#wit.cbeta` id** 判，不依赖 label）；docx → 红字（官方字符样式或主题色内联）；epub → `span.corr` + golden `.corr{color:red}`；html/md/txt → 只渲染子节点不产生 span（与官方 html/txt 一致、保 golden 对照）；死命令三件套：`TAG_SELECTOR["corr"]="span.corr"` + `EDITABLE_ROWS ("span.corr","CBETA校改")` + CSS 规则
- [x] **已记录（无代码改动）** 元素覆盖扫描（2026-09-10 三项并查，决议：都不加行，只记录）
  - test XML 19 文件 body 普查：左栏缺失但可见 = `l`（13/4819）/`caesura`（11/4747）/`cb:t/tt`（T01/X59n1077）/`list/item`（3 文件）/正文内 `title`（6/126）/`hi/seg[border]/note[hide]`/`space`（4/430）/`yin/zi/sg+entry/term`（X59/X60）/`figure/graphic`（3/74）/`g`（12/947）+`app/lem/rdg`/`div@type=orig/commentary/jing/pin/fen/w/other`（other 1808，左栏仅 xu/note）；`rend` 四行 19 文件零命中无样张；结构性无需调 = lb(70125)/pb/milestone/cb:juan/jhead/docNumber/mulu(2087)/anchor(9837)
  - schema（cbeta-p5.rnc）对照：唯一值得加的是 `table/row/cell`（走 bip-table，左栏无行）——本次不加；`list` 低优先级；其余透传/功能性不值得单列；header 无行系正确忽略
- [x] **已记录（无代码改动）** 字体扫描（2026-09-10，决议：只记录不动链）
  - 真非系统：`cbetarc`（golden 网络字体，离线失效）/`CBETA Supplement`（随仓，缺则回退失效）/`Ranjana`/`Siddam`（随仓）/`Songti TC`（macOS）/`朝华标题B/ZhaohuaMinB`（my.css 用户预设，**免费商用**（用户提供知乎链接，本机随 WPS 已装），非系统自带，他机需自装）；回退链已有覆盖
  - 本机缺但属系统字（本机简体 Win 环境）：`新細明體/PMingLiU`/`標楷體/DFKaiShu`/`隸書/LiSu`——繁体首选链本机悬空，靠 Word 自身回退；根治须手动装字（语言包/繁体机拷贝），不动 CSS（铁律）
  - 系统自带已装：Calibri/Times/Arial/宋体/SimSun/黑体/楷体/仿宋/微軟正黑體/YaHei/ExtB/ExtG（简体链全绿）
  - 落盘（2026-09-10）：`docs/安装说明.md` §3 后追加 §3.1 清单 + §3.2 三档指引（纯文档，零代码）
- [x] **已完成** 验证报告差异定位：`〖…〗` 精确标记 + 源/生成档行号（2026-09-13 用户点档：缺0/多69 怎么理解、差异难定位）
  - 口径答疑：`缺=官方有而生成档缺失`（`missing`）/ `多=生成档有而官方没有`（`extra`）；`缺0/多69` 即生成档多出 69 字、无缺失
  - 旧显示只给变更点前后 10/40 字窗口、不标变更段、无位置信息；新：`_mark_span` 用 opcode 实际区间 `i1:i2/j1:j2` 标出 `〖…〗`（插入/删除侧空括号），上下文前后各 18 字
  - 行号：`normalize_with_lines` 逐行归一 + 字符→行号映射（跨行括号等罕见不一致回退空映射），`_display_text` 统一 compare 落盘文本与映射基准（剥 `[..]`/页码令牌 + 压缩空行），故行号即 `*_compare_*.txt` 的 TXT 行号；报告每条差异先出 `N.（源比较第X行，新比较第Y行）`，源/新路径下各带 `【源比较】/【新比较】行号对齐 <cmp 文件名>`（2026-09-13 用户点档：行号非 DOCX 行、去末行提示）
  - 双入口同步：`format_verify_report`（GUI 报告/GUI 汇总）与 CLI `--verify` 片段（CLI 无落盘行号，仅 `〖〗` 标记）
  - 验收：`test_verify.TestNormalizeWithLines` 2 + `TestReportCtxLocation` 3；全量 647 OK（skipped=1）
- [x] **已完成** 修复 docx/md/txt 校勘注重复：`star_removed` app 不在自身锚点重渲 corresp 注（2026-09-13 用户点档）
  - 现象：`nkr_note_add_0021b2101` + `beg0021b2101` 同处出现两条注——add 注 `琉璃【CB】【麗-CB】，瑠璃【大】，流離【聖】 (cf. …)` 与 `琉璃【大】＊，流離【聖】＊ (cf. …)`（后者为 `corresp="#0021019"` 的 `star_removed` app 重渲了别处注 0021019）
  - 取证（官方 T0001_003.docx）：正文 `[FN89]琉璃城水精門，水精城[FN90]琉璃門` 仅两条；FN89=`琉璃【大】＊，流離【聖】＊`（注 0021019 原位）、FN90=add 注 + cf；`star_removed` app 只贡献 cf 给对应 add 注，不在自身锚点出注（T0001_012 FN73/FN74 同构）
  - 修法：`_render_app` 首判 `app.atype == "star_removed"` → 返回 `""`；docx/txt/md 三渲染器同改（html/epub 本就忽略 App 节点，无重复）
  - 保留：普通 `corresp` app（`beg_N` 重出机制）照旧渲染；cf 仍由 `_cf_run(note)` 从 `_app_by_n[n]` 取 star_removed 的 lem 追加
  - 验收：`test_docx.TestAppStarRemoved` 2 + `test_txt.TestAppStarRemoved` 2；T01 实渲 `水精城[FN509]琉璃門` 仅一条 add 注（含 cf），FN508 为注原位；全量 651 OK（skipped=1）
- [x] **已完成** 拆分校勘：整体 orig 注被 mod(a/b) 取代，docx/txt/md 不再单出（2026-09-13 用户点档：`0028009` 我们 2 条、官方 1 条）
  - 现象：`nkr_note_orig_0028009`（整体）+ `nkr_note_mod_0028009a/b`（拆分）同处；我们按精确 n 各自生成 NoteRef，`_pick_note` 只在同 n 内 mod>orig，故整体 orig 未被取代、`其積` 处多出一条脚注
  - 官方依据：`https://archive2.cbeta.org/en/format/jk_help.php`「小寫的 a、b，是指 CBETA 將一個校勘條目拆成二組」（大寫 A、B 為內文兩處相同編號，不合併）
  - 取证：官方 `T0001_004.docx` 正文 `燃[FN120]其積，[FN121]火又`（仅 mod a/b）、官方 txt `[9a]/[9b]`；官方 html `T0001_004.html` 仍列 `n0028009`+`a`+`b`（三條）；孤立 orig（`0001001` 此序）官方 docx FN1 仍出
  - 修法：`model.suppressed_orig_notes(notes_by_n)`（base=去尾部小写 a/b；该 n 无 mod 且 base 有 mod → 抑制）；`render_docx/txt/md` 缓存 `_orig_suppressed`，`_render_noteref` 与 `_render_app` corresp 分支对 orig 命中即返回空；html/epub/pdf（html 管线）不调用，保持官方 html 全列
  - 验证：`test_docx.TestSplitLemmaOrig` 2 + `TestSuppressedOrigNotes` 3、`test_txt.TestSplitLemmaOrig` 4（txt/md 抑制、html 保留）；T01 实渲 `燃[FN696]其積，[FN697]火又`（orig 不再单出）、FN1 `此序依宋元明…` 仍在；全量 660 OK（skipped=1）
- [x] **已完成** docx2pdf 用 WPS/Word 转 PDF 不再干扰已打开实例（2026-09-13 用户点档：窗口偶尔被激活 + 弹「是否保存修改」）
  - 根因：`render_pdf._com_convert` 原用 `Dispatch` —— WPS/Word 已开时会**附着用户实例**；`app.Visible=False` 会隐藏/激活用户窗口，`app.Quit()` 会退出用户实例（对未保存文档按默认走 → 弹「是否保存修改」），`d.Close(False)` 语义不如显式 `Close(0)`
  - 修法：检测已运行（`GetActiveObject`）→ 安全附着（不动 Visible、不 Quit、`Open(ReadOnly/AddToRecentFiles=False)`、`Close(0)`、`DisplayAlerts=0`/`ScreenUpdating=False`/`Options.SaveInterval=0` 用后恢复）；未运行 → `DispatchEx` 独立隐藏实例 + `Quit(0)`；失败逐级回退（`DispatchEx`→`Open` 参数退化→`ExportAsFixedFormat`→`SaveAs`）
  - 加固：始终从**临时副本**转换（`_prep_open_path`）——WPS/Word 对同一路径 `Documents.Open` 会返回既有 Document，安全附着会误关用户同名文档；转换后删副本
  - 验证：`test_pdf.TestComConvert` 7 项（独立实例隐藏/Quit(0)/只读/Close(0)；附着不改 Visible/不 Quit/设置恢复；DispatchEx 失败回退；SaveAs 回退；失败清理；临时副本不碰原文件、用后即删）；真实 WPS 实测：无实例 → 独立转出 721KB PDF；预置可见实例 → `GetActiveObject` 命中、安全附着转出 PDF 且用户文档仍在（Count 保持 1）、不退出；全量 667 OK（skipped=1）
- [x] **已完成** 校验恒比注：`generate_formal` 忽略 `output.show_notes`（2026-09-13 用户点档）
  - 现象：转换时取消「显示注释」，校验重生成档也去注，而官方基线含注 → 误报大量「缺」
  - 修法：`verify.generate_formal` 五个格式构造器一律 `show_notes=True`（仅校验用；生产 CLI/GUI 仍按开关）
  - 验证：`test_verify.TestVerifyAlwaysComparesNotes` 2 项（docx/txt 用 `overrides={"show_notes": False}` 仍传 True）；全量 669 OK（skipped=1）
  - 附：偈颂（`<lg>`）字体已在样式编辑器「偈颂」行（`div.lg`，docx 主题 tag `verse`）可调，实测 `div.lg` CSS → run rFonts/字号生效
- [x] **已完成** 方案 B：删除 `DEFAULT_THEME`，`pdf_docx.css` 成为默认值唯一定义处（2026-09-13 用户立项）
  - 根因：`Theme.__init__` 先铺 Python `DEFAULT_THEME` 再叠 CSS → 删 CSS 键不生效（露出旧默认）、body 改字号传不到 p/verse；`DEFAULT_THEME` 多数值还与 CSS 重复且更旧（title 24 vs 26、head 14 vs 20、juan 16 vs 20、pin 14 vs 16、note-ref 0.7em vs 0.75em）
  - 实施：`theme.py` 删 `DEFAULT_THEME` 与 div-* `setdefault`/`div-orig bold`（CSS 已有）；`Theme.__init__` 直接从 CSS 解析起（`tags=merged`）；`TRANSLATABLE` 增 `list-style-type`（此前 DOCX 列表样式只来自 DEFAULT，CSS 未解析）
  - 契约：新增 `theme.REQUIRED_THEME_TAGS`（元素→关键属性；`p` 刻意不含 font-size）+ `missing_required_theme(theme)`；`test_theme.TestRequiredThemeTags` 5 项（出厂齐全/缺 div.lg 报出选择器/防 DEFAULT_THEME 复现/p 跟随 body/body 字号传播）
  - 语义结果：`p` 不再写 `w:sz`，DOCX 靠 `docDefaults=body` 继承；删 CSS 键两端一致；`font_scale` 由 body 缩放带动 p（视觉等价）
  - 测试更新：`test_theme` 缩放/`test_gui` 工厂合并/`test_annotate` 正文 12pt 断言改 docDefaults；其余不变
  - 文档：`主题与样式.md` 字号单源节补「DEFAULT_THEME 已移除 + 完整性守护」；`pdf_docx.css` 头部/各行注释由「Python 兜底·勿删」改为「唯一定义处」
  - 验证：全量 674 OK（skipped=1）；出厂 CSS 下 T01/X59 docx 改前后对照——去除 `w:sz/w:szCs` 后**逐部件字节一致**，仅少 T01 20497 / X59 4504 处 `w:sz val=24`（正文 12pt 改由 `docDefaults`（=body）继承，视觉等价、单源达成）
- [x] **已完成** DOCX run 祖先继承补全：从"仅 div+栈顶"改为"body→div→整栈逐层、属性各自最近优先"（2026-09-13 用户点档）
  - 现象（旧）：并列标签只取栈顶（`<lg rend="kaiti">` 楷体生效但偈颂绿丢）、非 div 祖先字号传不进（`li{font-size}` 内层 p 不跟）、`body{color}` 进不了 run、三段后代选择器 DOCX 忽略
  - 修法：`render_docx._current_tag` 返回 `("body",)+div_stack+全部 tag_stack`（外→内），`docx_run` 逐 tag `update` 即"逐属性最近优先、逐层往外、body 兜底"；`theme._parse_css_tags` 支持三段+后代选择器（祖先按序存 tuple），`_apply_compounds` 按序匹配
  - 影响：纯"增加"——T01 20765 / X59 4589 处 run 补回 `w:sz=24`（=body，视觉等价）；X59 548/T01 15 处内联夹注补回 `rFonts`（继承 body 字体）；X59 27 处无 rPr 的注文补回正文 12pt+字体（此前掉 Word 默认 11pt）；文本零变化、无属性被移除
  - 测试：`test_docx.TestAncestorInheritance` 4（并列标签双生效/li 字号下传/body 颜色下传/三段选择器）+ `test_theme.TestDescendantSelector` 扩展 2；全量 680 OK（skipped=1）
- [x] **已完成** 标题内正文夹注不跟标题放大/加粗（2026-09-13 用户点档；方案 C）
  - 现象：`<head>…<note place="inline">呪文節略</note></head>` 因逐层继承 → `.doube-line-note{0.8em}` 相对 head 20pt = **16pt（三号）+ 继承标题粗体**（CSS/官方 html 口径如此；官方 docx 更是整段继承标题 26pt 加粗）
  - 修法（两段后代，仅标题内）：`pdf_docx.css` 与 `cbeta_golden.css` 各加 `p.head .doube-line-note, p.head .interlinear-note { font-size: 0.6em; font-weight: normal; }`（golden 标注「超出官方」）；0.6em×20pt=12pt、去粗，括号同 content
  - HTML/PDF 浏览器原生生效；DOCX 经 `theme.compounds`（head 祖先 + 夹注目标）生效
  - 验证：X1077 实渲 `（呪文節略）` 由 sz=32/b 变 sz=24/无 b、紫 800080，标题本体仍 20pt 加粗；`test_docx.TestAncestorInheritance.test_head_inline_note_not_scaled` + `test_theme.TestDescendantSelector.test_head_inline_note_rule` + golden 断言；全量 682 OK（skipped=1）
- [x] **已完成** pdf_docx.css 去冗余（单源化）：删与被 body 重复/等价继承的声明（2026-09-13 用户点档）
  - 删：`p.author/translator/byline`、`div.lg`(verse) 的 `font-size:12pt`（跟 body）；`p` 的 `line-height:1.4`（跟 body；且修「纸张 body_line_height 被 p 钉死」）；`p.form`/`cb:def` 的 `font-size:1em`（等价继承）
  - 保留（防误删）：`p.form`/`p.figure` 的 `text-indent:0`（压 p 的 2em）、`cb:def` 的 `font-weight:normal`（压 div-note 加粗）、**`p.series-title` 的 `text-align:left`（压 p 的 justify；曾被我误列为可省，已更正）**、脚注 `line-height:1`、`li{text-indent:0}`、`pre{text-indent:0;text-align:left}`（REQUIRED 要求；`text-align:left` 见 2026-09-30 预排段修复）
  - 连带：`REQUIRED_THEME_TAGS` 放宽（author/translator/byline/verse→()、p→("text-indent",)）；`render_docx._para` 的 div 行距剥离条件改为「元素自带行距或所有 div 祖先未写行距」→ 去掉 docx_para 经 body 回退带进 div_extra 的重复 `w:line`（含空 `<w:spacing/>` 清理）
  - 语义：纸张 `body_font_size/line_height` 现能下传到 p/署名/偈颂；默认页输出视觉等价
  - 验证：T01/X59 对照——文本零变化、rPr 仅少 `w:sz=24`（T01 1017、X59 5，改为 docDefaults 继承）、行距由内联重复移到命名样式（同值 336）；test_theme 缩放/工厂合并、test_docx TestDivExtraLineHeight、TestRequiredThemeTags 更新；全量 683 OK（skipped=1）
- [x] **已完成** 兜底值（保命值）清点成文档：`docs/兜底值清单.md`（2026-09-13 用户点档）
  - 区分「主题默认值（CSS 唯一来源）」vs「代码兜底值（CSS/配置缺失才启用）」；按 8 类登记（排版/页面/字体缺字注音/注释括号/PDF 引擎/图片/元数据/运行槽默认），逐条给值+位置+触发条件
  - 重点：em 基准 12pt（`theme.py:943`）、docDefaults 11pt（`render_docx.py:241`，与 12 不一致属历史）、Normal 行距 1.5（`:1805`）、页面回退 a4/25.4mm/Calibri（`theme.py:864-871`）、字体回退链/悉昙/注码/注音默认等
  - 第 1/2 类硬性不可配置；第 3 类多可由 `config.json` 覆盖；`主题与样式.md` 加指针；纯文档零代码
- [x] **已完成** 纸张排版进渲染器构造 + 保命值收敛常量（2026-09-13 用户点档）
  - 1) `theme.ensure_page_typography(theme, page, presets)`：`DocxRenderer`/`PdfRenderer` 构造时调用；同一 theme 已按 (page,presets) 应用过则跳过。CLI 仍在 `font_scale` **之前** `apply_page_typography`（缩放基于纸张基准），故构造时命中标记直接跳过、不会被重置；库直接调用渲染器只要传 `page_presets` 也按纸张生效，`page_presets=None`（verify/默认）不动
  - `PdfRenderer._pdf_css`：在 theme_css 之后补 `body { font-size/line-height }`（取自 theme.tags body），使 html2pdf 也随纸张字号/行距（此前 raw_css 不反映 tags 变更，纸张对 html2pdf 无效）
  - 2) 排版类保命值集中到 `theme.FALLBACKS`（base_pt 12.0 / doc_size_pt 11 / line_height 1.5 / verse_hang_em 2.0 / body_font 微軟正黑體），`render_docx` 与 `base_pt` 默认参统一引用，值不变、只做可读性统一
  - 测试：`test_theme.TestEnsurePageTypography` 4（直接生效/缩放后跳过/无 presets 不动/常量值）+ `test_docx` 直调按纸张 1 + `test_pdf.TestPdfPageTypography` 2；全量 690 OK（skipped=1）
  - 文档：`兜底值清单.md`（第 1 节指向 FALLBACKS）、`主题与样式.md`（纸张 vs CSS 改述：库直调也生效）、`第三方调用说明.md`（DocxRenderer 行）
- [x] **已完成** 字母后缀 work id 大小写支持（`TXa001`/`T0128a`/`JB005` 等）（2026-09-13 用户点档）
  - 根因：全链路把 id 归一为大写（`parse_work_id` `.upper()`），而 catalog 与 CBETA 端点对字母后缀**大小写敏感**且各 canon 不一致（`TX,00,a001`、`T,02,0128a`、`J,15,B005`；T 同一经 A/a 并存）→ `catalog_lookup` 查不到、XML 下不了、ebook URL 404
  - 修法：`catalog_lookup` canon/no **大小写不敏感**匹配、返回值用 catalog 原大小写（新增 `no` 字段，`file` 按原大小写拼）；新增 `canonical_work_id()`（canon 大写 + no 原样，catalog 未命中原样返回），`materialize_work`/`fetch_work`/`ensure_baselines`/`ensure_figures`/`check_ebook_updates` 内部统一调用；`merge.collect_work_frags` 比对改 `n.upper() != no`
  - 实测（`curl -I`）：`TXa001` → XML `.../TX/TX00/TX00na001.xml`、html `.../html/TXa001.html.zip`、epub `.../epub/TX/TXa001.epub` 均 200；全大写 `TXA001` 自动纠为 `TXa001`；`T0128a` 同理（`T0128A` 纠为 `T0128a`）。TX 无 docx/odt（与大小写无关，CBETA 未提供）
  - 测试：`test_fetch.TestLetterSuffixId` 3（不敏感命中保原大小写 / canonical / URL 拼装）；全量 693 OK（skipped=1）
  - 文档：`第三方调用说明.md` §2.3/2.3b
- [x] **已完成** 抽出共享下载/元数据层 `cbeta-fetch`（纯标准库）并 vendor 进 xml2pdf（2026-09-13 用户立项：与 publish 共享下载，A 方案）
  - 新仓库 `D:\cbeta-fetch`（`cbeta_fetch.py` 单文件、纯标准库）：`is_work_id`/`parse_work_id`（canon 大写、no 原样）/`canonical_work_id`/`catalog_lookup`/`DEFAULT_DOWNLOADS`（含新 `pdf`）/`REMOTE_URLS`（元数据单源）/`download`（原子·可 `unzip`）/`unzip_flat`/`fetch_if_changed`/`probe`；`pyproject.toml`（发行名 `cbeta-fetch`）、README/API/CHANGELOG/LICENSE、`tools/sync_into.py`、`docs/对接单-publish.md`
  - xml2pdf：新增 `pycbeta/_vendor/{cbeta_fetch.py,SOURCE.txt,__init__.py}`；`fetch.py` 四函数 + `_http_download`/`_unzip_flat`/`_download_if_changed` 全委托共享（保存签名/行为；`DEFAULT_DOWNLOADS` = 共享表 + 专有 `figures`）；`update_data.py` 的 `_conditional_probe` 委托 `fetch_if_changed`；`remote_sources.json` 省略 url、改 `"source"` 引用 `REMOTE_URLS`（URL 单源）
  - 测试：cbeta-fetch 13 项（file:// 离线下载/解压/大小写/catalog）；xml2pdf 新增 `test_vendor_sync` 3（sha256/version/API/id 语法对账）；全量 696 OK（skipped=1）
  - 分发：publish 单发 GitHub 自包含（vendored 副本 + sha256 校验）；publish 侧改动见 `cbeta-fetch/docs/对接单-publish.md`（含 `src→cbeta_publish` 具名包、去 requests、官方电子书/remote_manager 迁移）
- [x] **已完成** cbeta-fetch v0.1.1：`probe_info`（HEAD 探针带 `size`），publish 对接落地（2026-09-14）
  - 共享层：新增 `probe_info(url, *, etag, last_modified, timeout) -> {status, etag, last_modified, size}`（`size` 取 `Content-Length`，缺失 `None`）；`probe` 保持三元组、改为其薄封装（向后兼容）；cbeta-fetch 提交 `50de57e`，测试 15 OK
  - xml2pdf：vendor 同步 v0.1.1（`SOURCE.txt` `commit=50de57e…`、`sha=04b322d6…`），`test_vendor_sync._API` 补 `probe_info`；全量 696 OK（skipped=1）。**xml2pdf 不用 size**（其变更检测是 GET 字节比对，强于 size；size 仅用于 publish 的「HEAD 存在性/大小即跳过」）
  - publish：已按对接单完成——`cbeta_publish` 具名包、`_vendor` 同步同一 commit、`official_ebook_source` 用 `cf.probe_info`、`remote_manager`/`remote_sources`/`catalog/work_id` 走 `_vendor`、`requirements.txt` 去 `requests`、`tests/test_vendor_sync.py` 守 sha256+`probe_info`；对接单已标记「已实施」
- [x] **已完成** 数据源窗口按当前选中预设写入 + “电子书工作根”改名“电子书输出目录”（2026-09-16）
  - 根因：用户在数据源窗口配置的 `source.cbeta_ebook` 只写 `presets/config.user.json`，
    而运行走的激活预设（run.json 指向的 `Publish A5 繁体….json`）没有该键 →
    `resolve_source` 抛“未配置”。修：`SourceDialog(preset_path=…)` 读写目标预设文件
    （默认用户预设）；主窗 `_edit_source`/`clear_xml_dir` 透传当前选中；标题显示文件名
  - 改名：`电子书工作根`→`电子书输出目录`（SOURCE_LABELS/CLI/fetch/panel 弹窗/config.json/README/docs）
  - 已把激活预设缺的 source 块回填（现 `resolve_source` → `('', 'D:\CBETA\cbeta_ebook')`）
- [x] **已完成** 修 jhead 内校勘注的 docx 脚注变小三加粗（2026-09-16）
  - 根因：`_footnote_content` 只清 `_div_stack`、没清 `_tag_stack`，注文带着外层
    juan/jhead 标签 → footnote 的 0.75em 按标题 20pt 解成 15pt（小三）+ 粗体/蓝色泄漏
  - 修：`render_docx._footnote_content` 同时保存/清空 `_tag_stack`（继承链只剩 body→footnote，
    注文 9pt 无加粗）；`TestFootnoteInTitle` 2 项（字号 sz18/无加粗无色）；全量 719 OK
- [x] **已完成** 配置框标题常驻最后动作 + “缺 XML”细分诊断（2026-09-16）
  - 标题：`_set_cfg_title(action)` 写 `QGroupBox` 标题（配置/配置（已保存/已存预设/已删除/
    已设默认））；换预设（`_on_preset_chosen`）/还原出厂后复原；去掉 1.5 秒闪现 label
  - “缺 XML”：`_resolve` 无结果时区分——未勾选自动下载 / `catalog 未收录`（查 catalog，
    不触网）/ `下载失败`（`_missing_xml_reason`）；修     `fetch` 局部导入导致的 NameError
    （`__main__` 里 `from pycbeta import fetch` 只在 `run()` 内）
- [x] **已完成** 彻底去掉 `out` 目录名隐藏排除（2026-09-16，用户定）
  - 背景：`find_local_xml`/`find_official`/目录扫描曾把绝对路径含 `out/` 的文件全部排除；
    工作根自己叫 `out`（如 `cbeta_ebook/out`）时下载成功也找不到 → “缺 XML（下载失败）”
    （根目录因本地早有 XML 从不下载，掩盖了该 bug）。该写法自首版提交 `3168e76` 即有，
    原意是跳过输出目录，但用户出错无从得知
  - 修：三处 + `inspect_xml_source` 的子目录剪枝，**全部删除**，无任何目录名排除；
    相关用例同步（`test_out_excluded`→`test_out_files_included`，
    `test_baseline_lands_flat_ignoring_out_decoy` 去诱饵改名；`test_fetch`/`test_layout`
    的 out 根用例改为断言全部收录）
  - 另：标签 `电子书输出目录（…）`→`XML及电子书（官方下载保存平展目录）`（SOURCE_LABELS）
- [x] **已完成** 独立窗 `--preset` 认 publish 传的文件名（2026-09-17）
  - 背景：上游 `7258b65` 给 `python -m pycbeta.gui` 加了 `--ids-file/--out/--preset/`
    `--verify/--autostart` 预填；publish `_send_coll_to_verify` 用其一键送校验
    （写 `*_ids.txt` → detached 子进程 → 跑完用导入入库）
  - 缺口：publish 传的是**带 `.json` 的文件名**（如 `my.json`），上游匹配器只认
    stem/绝对路径 → 预设被静默忽略。修：`_apply_launch_args` 归一化去 `.json` 后缀，
    stem/文件名/绝对路径三种都认；`--preset` help 同步
  - `TestLaunchArgs` 4 项（预填/三种写法/缺失保持/空参数零作用）；文档 `第三方调用说明 §6.3` +
    `安装说明 §5`；全量 728 OK
- [x] **已完成** CBETA 校改字标红 `corr-cbeta`（2026-09-17 用户点档；排除 md/txt，默认关）
  - 判定：`app.lem` **原始** `wit` 含 `#wit.cbeta`（按原始 id，不依赖 `【CB】` label）；实测
    19 文件 661 处校改全部 beg/end 同父、0 跨父 → parser `_traverse` 末尾按兄弟列表包区间
  - parser：`_handle` beg/end 放私有 `_CorrMark`；`_wrap_corr` 把中间节点包成
    `E(tag="corr-cbeta", attrs={n})`（App 留区间外，注码不变红）；标记不进 IR
  - 渲染（开关 `output.corr_cbeta`，默认 false）：docx `_render_e` 经主题 tag 红 `#FF0000`；
    html `_render_misc` 出 `span.corr`；epub/ pdf 继承 HtmlRenderer；**md/txt 透明（排除）**
  - 主题/死命令：`TAG_SELECTOR["corr-cbeta"]="span.corr"`、`REQUIRED_THEME_TAGS=("color",)`、
    `EDITABLE_ROWS ("span.corr","CBETA校改")`；`pdf_docx.css span.corr{color:#FF0000}`、
    `cbeta_golden.css .corr{color:red}`（超出官方 html）
  - 配置：`config.json output.corr_cbeta`；GUI 排版卡「CBETA校改字标红」；无 CLI 开关
  - 测试：`test_parser`（合成+ T0452 4 处）、`test_docx`/`test_md_epub`/`test_txt` 开关与排除、
    `test_gui` 选项+左栏行；全量 736 OK（skipped=1）
- [x] **已完成** 批量表只读可拷贝 + 【經文資訊】尾页 CSS（2026-09-17）
  - 批量表五列禁止编辑触发（`NoEditTriggers` + `SelectItems`/`ExtendedSelection`），保留选中与
    Ctrl+C 拷贝；「来源」＝XML 取得方式（本地XML/本地拷贝/合册合成/已下载）
  - 经文资讯尾页：`p.info{font-family:仿宋;line-height:1}`（pdf_docx.css）+ golden
    `#cbeta-copyright p`；docx 尾页改走 tag `info`、pdf 尾页 `<p class="info">`；
    `TAG_SELECTOR["info"]="p.info"` + `REQUIRED_THEME_TAGS["info"]=("font-family","line-height")`
  - 测试：`test_docx.test_info_page_fangsong`（仿宋+w:line=240）、
    `test_gui.test_table_readonly_copyable`
  - 追修（2026-09-17）：`_para` 内联路径（非命名样式段落）**丢弃 `page_break`**，`info`
    尾页因此不另起页（docx 无 `pageBreakBefore`；pdf 走 docx2pdf 同病）→ 内联路径补
    `<w:pageBreakBefore/>`（pStyle 之后、spacing 之前，schema 顺序）；`test_info_page_break_before`
- [x] **已完成** 注音卡三选一 + 生僻字自动注音两处修复（2026-09-17）
  - GUI 注音卡：「无注音 / 难字注音 / 全文注音」互斥三选一（全文含难字）；
    `annotations.enabled`/`full_text` 读写；词表栏**只读**、浏览选择、默认内置表路径
  - Bug1：pypinyin 未收录的补字形（如 𭣛 U+2D8DB）无注音 → `auto_reading` 增加
    gaiji 规范化字回退（`norm_big5_char`/`norm_uni_char`/`norm_unicode`，如 𭣛→變→biàn）
  - Bug2：`repeat=page` 的 seen 去重被**脚注抢先渲染**消费（脚注在注码处先渲，正文再出现
    即无注音）→ docx 脚注/尾注内容**延迟到页末（<pb> 或分节末）渲染**，正文先占 seen；
    自动生僻字恢复参与去重（每页只注首次）
  - 已知语义：`rare_zones` 仅覆盖 CJK 扩展 A–I；基本区难字（如 癅 U+7645）不在其列，
    需入词表（单字行）才注
  - 测试：`test_annotate`（规范化回退、去重含自动）、`test_docx.TestNoteAnnDedup`
    （正文注/脚注不重）、`test_gui`（三选一互斥+回读、词表只读+默认路径）；真机 T0032 实证

- [x] **决议不做（仅记录）** html2pdf 管线分页未对齐 docx（2026-09-28 用户确认「写进 todo，不做」）：`render_pdf.py` 目前只在 `juan` 边界 `break-before: page`，无 `mulu_level1`；如需 HTML 管线 PDF（及 html 成品）也按 level-1 非「卷」mulu 分页，应复用 `render_docx.split_sections` 同口径插断页。（epub 已对齐：`EpubRenderer` 按 mulu 拆 spine 章节，见 `render_epub._split_mulu_breaks`。）

- [x] **已完成** 预排段（`<pre>`/`<p cb:type="pre">`）不两端对齐（2026-09-30 CC0003 实锤）
  - 现象：CC0003「卷第三十五科目」等预排大纲（全角空格手工对位 + 点线 + 页码）在 docx 里长行被**拉伸**（字距撑开、缩进错位），短行正常；官方 PDF 同页为「换行但左对齐、无拉伸」
  - 根因：`pdf_docx.css` 的 `p{text-align:justify}` 透传给预排段（`pre` 只设 `text-indent:0`）；HTML 侧是 `<pre>` 元素不受 `p` 规则影响，DOCX 侧是 `w:p` 会继承 → `w:jc="both"` 对换行后的行两端对齐，把全角空格/点线拉伸
  - 修法：`pdf_docx.css`/`epub_print.css` 的 `pre{text-indent:0;text-align:left}`；**并**在 `render_docx._para` 加 `align` 参数，预排两处调用传 `align="left"` —— 因 `theme.docx_para` 是「靠前标签优先」（`reversed(tags)`），`("p","pre")` 里 p 的 justify 会压过 pre 的 left，仅改 CSS 在 DOCX 不生效
  - 验证：真实 CC0003 重渲→WPS 转 PDF，第 9 页与官方 PDF 第 7 页逐行一致；`test_docx.TestPreNoFirstLine.test_pre_left_aligned_not_justified`；全量 913 OK（9 环境 error 与基线一致）

- [x] **已完成** 图片随纸张等比缩放（A4 基准）+ 双向适配正文区（2026-09-30 X1077 实锤）
  - 现象：X1077 图（368×680px）在 A5 上占页过大、独占一页、正文被挤走；而绝对尺寸与官方 A4 docx/pdf **逐值一致**（368px@96dpi / 276×510pt），差异纯来自纸张（官方 A4）
  - 修法：`render_docx._fit_image_px`——① 先按 `min(page_w/11906, page_h/16838, 1)` 随纸张等比缩小（A4/license 更大页为 1，输出与旧版一致）；② 再宽、高双向适配正文区防溢出；全程只缩不放
  - 验证：X1077 A5 重渲 docx 259×479px、PDF 194.3×359.3pt（占页宽 46%，与官方一致）；单测 `test_figures.test_page_scaled_and_content_fit`；全量 920 OK（9 环境 error 与基线一致）

- [x] **已完成** 按卷范围选取某部经的某卷/几卷（2026-10-01 用户立项；2026-10-07 落地）
  - 落地：① `pycbeta/juan.py`（`parse_juan_spec`/`juan_set`/`format_juan_label`/`split_id_juan`/`resolve_juan_suffix`/`filter_work_juan`）+ `test_juan.py` 20 项；② CLI `--juan`/`-i ID:范围`（互斥；`resolve_output`/html/转换报告/校验目录加后缀）+ 长编号 `T25n1509` 消歧（`fetch.parse_long_work_id`，vol 感知 `find_local_xml`/`_catalog_title`/`materialize_work`/`fetch_work`）；③ `verify.verify_one(juan=)`、`ensure_baselines(juan=)`、`fetch_baseline_juan`（html `…/html/{ID}_{NNN}.html`、txt_notes `…/text-with-notes/{ID}_{NNN}.txt.zip` 实测端点；docx 无单卷 404 → 整包 fallback）、GUI `_make_id_job`/`_juan_plan`/`--juan`/`_verify_dir` 后缀；`output.juan_suffix_template`（config.json 注记 + 兜底值清单）。文档：README/安装说明/GUI设计/校验说明书 §4.4/主题与样式/兜底值清单/功能清单/第三方调用说明。实测：T0670 全范围 no-op 字节一致；`--juan 1 --verify` 单卷基线自动下载 + `0/0` 通过；GUI/CLI 单测补 10+ 项
  - 原分阶段（2026-10-06 优化）：① `pycbeta/juan.py` 纯函数 + `test_juan.py`（可独立验收）；② CLI `--juan`/`-i ID:spec` + 渲染/命名（X1077 e2e）；③ GUI/校验接线 + 单卷基线下载（URL 形态 build 时实测）
  - 目标：支持 `T25n1509:34-100`（大智度論 34–100 卷）这类子集，渲染六格式并按卷子集校验
  - 卷范围语法（`--juan` 与 GUI 编号后缀 `:` 共用）：`34` / `34-100` / `34-36,40,42-45`；`-`/`~`/`～` 三认一（归一为 `-`）；多段用 `,`（CLI）/`+`（GUI 列表内，因 `,` 是任务分隔符）；闭区间、`lo<=hi`（`100-34` 报错不下调）；去重合并
  - 长编号：`T25n1509`/`X59n1077` 现被 `is_work_id` 拒（只认短编号）；新增我方层解析 `T25n1509→(T,25,1509)`（catalog 已命中 vol 25，`T25n1509.xml`），vol 感知 `find_local_xml` + 下载/基线复用 catalog rec；不动 vendored `cbeta_fetch.py`
  - 过滤（核心）：新 `pycbeta/juan.py`（纯函数）——`parse_juan_spec`/`split_id_juan`/`juan_spec_label`/`filter_work_juan`；在 IR 层按 `<milestone unit="juan">` 重放 body（div 壳浅拷贝、milestone 保留，保证分页/分文件/书签），裁剪 `notes_by_n`（按保留 NoteRef 引用）与 `apps`；`juan 0`（首 milestone 前）仅含全书最小卷时保留；无 milestone → 警告忽略；全覆盖 → no-op 不加后缀（字节一致）
  - 命名：默认后缀 `（卷34-36、40）`（段间 `、`，非 `+`）；配置键 `output.juan_suffix_template` 默认 `"（卷{label}）"`，含 `{label}` 才生效（否则回退默认+警告），空值回退默认；显式 `-o` 文件路径尊重用户不加；html 目录同后缀（防与整本互覆盖）；校验目录同后缀
  - 接入点：CLI `-i ID:spec` 拆分 + `--juan` flag（冲突报错）+ `process_file`/校验循环双 parse 点过滤；`verify.verify_one` 加 `juan=` 形参；GUI `_collect_jobs`/`parse_work_ids_file` 剥后缀验 ID、`build_render_cmd --juan`、`_verify_one` 透传、`_verify_dir` 后缀
  - 校验语义：`work_juan_numbers(过滤后)` → `find_official` 的 `_NNN` 过滤自动限定子集基线（`verify.py:1497`）；整包单文件基线（无 `_NNN`）保持红灯（预期，文档写明）；`--baseline xml`（P3 辅轨，直读 XML）不支持子集 → 直接报错
  - 单卷基线下载：新增 `fetch_baseline_juan(work_id, kind, juans, …)`，仅 `auto_fetch` 且子集模式、缺卷时补下；URL 形态（build 时实测 canon 层/位数）：txt 含注 `…/text-with-notes/{ID}_{NNN}.txt.zip`、html `…/html/{ID}_{NNN}.html`、docx `…/docx/{canon}/{ID}_{NNN}.docx`；素文本 `…/text/`（不含注）**不接线**（校验链无素文本 trial，全格式 `show_notes=True` 恒比注）；epub/odt 无单卷形态，整包 fallback
  - 测试：新 `test_juan.py`（spec 正误例、合成 Work 过滤、注/app 裁剪、前置内容、空交集报错、label/模板）；X1077 e2e（`--juan 2-3` 带后缀 + 全范围 no-op 字节一致）；GUI job 解析；单卷下载 mock；全量回归
  - 文档：README/安装说明（CLI 参数）、`GUI设计`（编号后缀：`ID:范围`、多段 `+`、`--juan`）、`校验说明书`（子集语义/整包基线必红/P3 不支持/单卷下载）、`主题与样式`+`兜底值清单`（`output.juan_suffix_template`）
   - 非目标：品名选择（如“初序品”，另议）、XML 预过滤（先全量 parse，正确性优先）、按卷下载 XML（整包一次）
   - 追修（2026-10-11 用户报 T0220:479 卷定位不了）：根因非过滤逻辑（T07 的 479 本就能出），而是多文件分册经（T05/T06/T07）不含所选卷的文件被当**失败**计——CLI 退出码恒 1、GUI 行红字、`empty` 分支倾泻全卷列表（如 200 个卷号刷屏），产物被红字淹没。修法：`juan.scan_file_juans`（正则快扫，不全量解析；无数字 n/不可读→None 按命中）+ `partition_juan_xmls` 预分区（与 `filter_work_juan` 空/非空判定等价）；CLI 編號/目录分支预跳过（info 一行，>8 收敛总数；全不命中 `ap.error`；单文件分支保持严格）；GUI run 循环同口径预跳过（不起子进程、进度照累加，全不命中行红字保留）；`empty` 消息改紧凑区间。实测 `T0220:479` 只出 T07 卷479、EXIT 0；`:601` 大声报错 EXIT 2；单文件 strict 不变

- [x] **已完成** 外部引擎改走上游下载（2026-10-01 用户立项；2026-10-06 用户决议**不上传附件**，安装文档给 URL）
  - 仓库已公开：https://github.com/Zen-Bear/cbeta-xml2pdf（Public、GPL-3.0、分支 `main`、tag `v0.1`）
  - `engines/*.exe`（`cbetapdf.exe` ~90MB、`minipdf.exe` ~10MB）体积大，已从 git 历史移除（`git-filter-repo`）、`.gitignore` 忽略，**不随包、不传 Release**
  - `minipdf.exe` = MiniPdf.Cli v0.38.5，上游直链（已验证与本机逐字节一致）：
    https://github.com/mini-software/MiniPdf/releases/download/v0.38.5/minipdf-win-x64.zip
    （解压即得，放入 `engines/`）；`cbetapdf.exe`（自研 v1.0.0）暂无公开下载，文档标注为可选
  - 落点：`docs/安装说明.md` §2 拆行写明两引擎去向 + `engines/README.md` + GUI `INSTALL_HINTS` + `README.md` §后端说明同步

- [x] **已完成** 开校验时基线目录被重复递归扫描（2026-10-05 立项并落地）
  - 实测（优化前）：`find_official` 对已配置基线根（如 `E:\CBETA\2026r2\cbeta-text-with-notes`）递归 `**` 扫描 **~1.35s/次**；`verify_fingerprint` **~1.85s/次**。`build_report_json` 自己扫一遍 5 种基线，又对每个请求格式各调一次 `verify_fingerprint` → **(1+N) 次大目录扫描**（N=6 时 ~13s）。
  - 修法：抽 `_official_superset`/`_fp_roots_cfg`；`build_report_json` 只扫一次 `official`，连同 `presets`/`canon`/`impl` 经内部 `_ctx` 传给每个 `verify_fingerprint`（`_verify_fingerprint_inner` 检测到就跳过重扫/重算）。实测 3 格式 `build_report_json` 由 ~7s 降到 ~2.6s；指纹与独立调用逐字一致。
  - 单测：`test_report_json.TestBuildReportJson.test_discovery_reused_across_formats`（计数 `find_official` ≤5 次 = 5 kind × 1，而非 (1+N)×5）。
  - 未做：`verify_one` 与 `build_report_json` 的"行级共享"（两者仍各扫一次）；收益较小，暂不。

- [x] **决议放弃（仅记录）** 方向2：publish 官方缓存 → xml2pdf 校验复用（2026-10-07 用户立项；2026-10-07 用户决议放弃）
  - 放弃理由：publish 已配本地库 `official_library=E:\CBETA\2026r2`（pdf/epub/docx/txt_notes 全免下载）+ `default_source=xml`（官方源少用）→ publish 缓存基本为空，复用面窄；2026r2 无 html 目录，缺口仅 html（低频、一次性小下载）
  - 已补（2026-10-21）：GUI 补 html 行完成（`panel.py` 4 处 + `fetch.py` hints；防手改 `source.baselines.html` 被 GUI 保存覆盖丢键）
  - 实现：`panel.py` 显示行／`_dialog_presets`／自动检测／保存四处加 `html`；`fetch.py:107-114` 的 `BASELINE_DIR_HINTS` 加 `("html", ("html","htm"))`；文档：`GUI设计.md`／`校验说明书.md`／`第三方调用说明.md` 的基线格式清单同步
  - 配置：`source.baselines.html = E:\dev\cbeta\cbeta_ebook\html`（GUI 配）
  - 依据：`extra_roots` 优先、单根胜出（`find_official`，`verify.py:1654-1676`；CLI 经 `cli.py:1312/1339` 传入 `extra_roots`）；publish 缓存 `{fmt}/{work}/` 平展文件递归可命中（vendor 平展解压 `_vendor/cbeta_fetch.py:192-200`），`_is_flat` 排序正常
  - 只配 html：`txt_notes/docx/epub` 继续 2026r2 全量库，不动；同格式不双配；同字节基线指纹身份相同（`_fp_file_identity` 只含 name/size/sha256，不含 mtime），为 P2 铺路
  - 测试：`test_gui`（html 行键列表、预设、检测、保存）＋ `test_fetch.test_detect_html`（html/htm）；全量 1352 OK（skipped=122）
  - 验证：T1711 端到端冒烟通过（`source.baselines.html` 指 `E:\dev\cbeta\cbeta_ebook\html`，命中 `T1711_001.html`、`ok 缺0/多0`）；T0001 不在本机 html 库，未跑；显示/预设/检测/保存由上述单测覆盖
  - 非目标：txt（xml2pdf 无纯 txt 基线，publish txt 只能自下，互不干扰）

- [x] **决议放弃（仅记录）** 方向3：`sync-fmt-root` 把 work 基线镜像成格式优先布局（2026-10-07 用户立项；2026-10-07 用户决议放弃）
  - 放弃理由：同方向2（本地库已覆盖 pdf/epub/docx/txt_notes + `default_source=xml`，publish 对官方 html 需求低频）；方向3 另有持续成本（新函数+CLI+测试+文档、双份磁盘、`--force` 新鲜度语义、canonical drift）；与方向2 同时做会被 `extra_root` 遮蔽、边际收益重叠
  - 原方案（存档）：独立同步命令 + 镜像根复用空的 `E:\dev\cbeta\cbeta_ebook`（publish `official_ebooks_dir` 已指它，零配置变化）+ 第一版只 CLI/命令行传目录 + 单命令自动补下缺失源基线 + 默认只补缺失/`--force` 全刷
  - 落点：`fetch.sync_fmt_root(work_ids, fmt_root, kinds, presets, force=False)` + `pycbeta.fetch` CLI 加 `--sync-fmt-root DIR`（复用其 `-f/--cbeta-ebook/load_presets`；默认关闭零行为变化；主 CLI 以后再挂）
  - 流程：`fetch_work` 先补下缺失源基线（404 静默跳过）→ 镜像；收集复用 `_collect_fmt`（`fetch.py:315-324`）
  - 映射（publish `local_path` 口径，publish `official_ebook_source.py:58-69`；注意源/目标目录名不对称）：`{wdir}/{fmtdir}/{id}_NNN.ext` → `{fmt_root}/{fmt}/{CanonicalWork}/{id}_NNN.ext`，其中 txt_notes 源目录是 `txt/`、目标是 `txt_notes/`；epub 单文件 → `{fmt_root}/epub/{CanonicalWork}.epub`；odt 同理；`copy2` 保 mtime（publish 无水位判过期走 mtime 比较，`official_state.py:145-148`，镜像通常不误报）；只补缺失，`--force` 全刷；不镜像 xml/figures/pdf（publish 不消费：无 XML 下载逻辑、成品内嵌、无 pdf 基线）
  - `CanonicalWork` 用 `canonical_work_id`（同源 cbeta-fetch，`fetch.py:198` vs publish `catalog/work_id.py:24-25`）；混合大小写 id（TXa001/T0128a 等）双边对照测试防 drift；运行时两侧 catalog 不一致会静默 miss（测试覆盖）
  - 缺口注明：纯 txt 无镜像（xml2pdf 基线无纯 txt，plain text 已弃用 `fetch.py:5-6`）
  - 测试：新 `test_fetch_fmt_mirror.py`（布局/补缺/force/epub/命名）；T0001 实测后按 publish `local_path` 形态逐 kind 断言；全量回归
  - 文档：`docs/第三方调用说明.md` 加"格式优先镜像根"契约节（布局/目录名不对称/canonical 对齐/txt 缺口）+ `docs/功能清单.md` 加一行

- [x] **上游已落地，待下游 P10 实施** P2：校验结论跨边复用（2026-10-07 用户立项；下游审核意见见提案 §9，上游复核见 §9.6/§9.8）
  - **文档**：`docs/上游-P2校验结论跨边复用提案.md`（§1-8 原案；§9 下游审核意见；§9.6 上游复核）；`docs/上游-指纹presets入参提案.md`（含 §5 上游复核实测）
  - **决策（§9.1）**：阈值两边统一 `max_diff=0`/`diff_lines=5`（旧记录按 0 重跑一次）；配置形态改为上游加 `verify_fingerprint(presets=<effective dict>)` 入参（不再用 run 包装）；只从上游 `report.json` 导入（逐源 + 验收档；`formal_outputs`/`inputs.xml_files` 仅非空校验）
  - **验收档（§9.3，publish 侧）**：strict（`0/0`）自动入库；notes（≤10 且 `diff_scope=="notes_only"`）自动入库；其余人工且不记库（fail+notes_only 也接受，依赖 fail 时照写 `diff_scope`）
  - **多源（§9.4/§9.6/§9.7）**：已定「输入集」模型——publish `entries[work][fmt].sets = [{fingerprint, inputs:[源基名…], …}]`，新鲜＝某 set 的 `inputs` 恰为当前全部源且指纹命中；GUI 聚合报告天然满足，CLI 单源等价、CLI 多源不导入（managed 当场记录）；**上游无需改 GUI**。注意指纹 `xml` 有序，publish 重算须按报告 `inputs.xml_files` 同序映射
  - **上游待办（§9.5 + §9.6 + §9.8，2026-10-07 已全部落地）**：① `verify_fingerprint(presets=)` 入参（含 `_strip_no_from`/`_theme_css_digest`/`_canon_annotations` 改 presets 派生，见 presets 提案 §5）；② 预设 `verify.maxDiff` 改 0、`diff_lines=5`（tracked A5 两项 + 本地 config.user.json；factory 不动）；③ CLI 文档注明 `--verify-max-diff 0`（`docs/安装说明.md`）；④ `校验report.json说明.md` 补 fail 时也输出 `diff_scope`（已办）；⑤ 多源口径已定（publish 输入集模型，§9.7，上游无需改 GUI）；⑥ **分类器修复**（`theme.py` `_is_run_config`：含主题键的裸预设被误判 run.json → 预设各段被丢弃；附带修好 CLI `--config 裸预设`）
  - 验证：单测 `test_verify_fingerprint.TestPresetsParam`（三形态等价 + 缺省回归 + 分类器 + `build_report_json` 透传）+ `test_theme` 分类器回归；全量回归；publish 复用命中跳过（`regen_all` 时仍重生成不校验，见 §9.2）
  - 收益：整轮渲染+校验（分钟级/部）→ 指纹预检（秒级，`verify.py:2402-2408`）
  - 风险/前提：首选基线缺失指纹为 None（`verify.py:2507`）；预设文本键不一致永不命中（静默）；跨机器不主张；方向2/3 已放弃（本地库+自制源下收益低），不影响本项

- [x] **已完成** 校验 `report.json` 命名统一（2026-10-07 用户立项并落地）
  - GUI 原写 `{id}_{书名}_校验报告.json`（`gui/__main__.py:395`）→ 统一为 `report.json`（与 CLI 同名；每 `（验证）/` 目录一书一档，无冲突）；txt 仍 `{id}_{书名}_校验报告.txt`
  - 删除 `find_verify_reports` 的 JSON 回退（`verify.py:2838-2877`）——机读结论只认 `report.json`；txt 回退保留（当前 stem 命名靠它，`report.txt` / `*_verify_report.txt` / `*_校验报告.txt`）
  - 文档：`校验report.json说明.md` §1/§4；单测 `test_verify_dirs` 两例改「JSON 回退已删 / txt 回退仍在」

- [x] **已完成（下游 publish 请求）** GUI 独立窗加 `--verify-root`（2026-10-07 请求并落地）
  - 与 CLI 同名同语义：显式 `--verify-root` ＞ 预设 `source.verify_root` ＞ `{输出}/验证`；只影响校验产物落点，不写回预设
  - 落地 3 处：`gui/__main__.py` argparse 加 `--verify-root`；`_apply_launch_args` 记 `win._verify_root_override`；`_start` 并入 worker `paths`；`BatchWorker.run()` 经新纯函数 `_pick_verify_root(override, presets)` 取生效值（`_verify_dir` 已接受 `verify_root` 形参）
  - 单测 `test_gui.TestVerifyRootOverride` 4 项（优先级/预填/缺省不设/worker paths）；`test_gui` 285 OK
  - 提案全文（背景/现状/最小改动/优先级/验收/publish 影响）：`docs/上游-GUI校验根参数提案.md`；publish 侧对应 `docs/上游-GUI校验根参数提案.md`（其 P7 可收尾：`_open_xml2pdf_window` 追加 `--verify-root <丛书校验目录>/验证`）

- [x] **已完成（下游 P11 请求，2026-10-08 复核并落地）** 卷维度指纹：`verify_fingerprint(juan=)` + report 自描述
  - 背景（correctness）：子集与整本同 XML/同超集基线 → 指纹逐字相同，跨边复用会把「子集 pass」当「整本 pass」；publish 有「子集恒验」绕行（不阻塞）
  - 提案与复核：`docs/上游-指纹juan入参提案.md`（§8：Q1–Q5 答复 + 实现清单）
  - 落地：`juan.normalize_segments`（排序合并；空→None；非法 ValueError）；`verify_fingerprint(juan=)`（非 None 才入 payload，None 逐字回归；`_official_superset` 卷限定 html/docx/txt_notes）；`build_report_json(..., juan=)` 顶层 `juan{segments,label}|None` 恒输出 + 透传每 fmt；CLI 校验流（`_juan_status=="filtered"` 才传）、GUI（`_juan_plan` full/无 milestone → None 并传 `_v_json`，顺带修无 milestone 仍加后缀的既有小 bug）
  - 测试：`test_verify_fingerprint.TestJuanParam`（6：None/空回归、归一等价、None vs 子集互异、非法→None、基线卷限定）+ `test_report_json`（2：自描述+透传、默认 None）+ `test_cli.TestVerifyReportJuan`（2：子集/全覆盖）+ `test_gui` `_juan_plan` 更新
  - 文档：`校验report.json说明.md` §3/§4、`校验说明书.md` §4.4；`schema` 保持 1

- [x] **已完成（用户立项，2026-10-08）** 出厂配置改名 `config.json` → `presets/config.factory.json`（与 user 对称；撤"出厂覆盖层"）
  - 经过：先做了"出厂覆盖层 + GUI 存为出厂"，用户复审后决议**简化**——不引入独立覆盖文件，直接把出厂文件改名进 `presets/`（与 `presets/config.user.json` 对称），GUI 出厂项仍只读
  - 落地：`git mv pycbeta/config.json presets/config.factory.json`（注释保留）；`theme._PRESETS_PATH` 指新路径、`resolve_base_config` 哨兵名 `config.factory.json`（旧名 `config.json` 兼容认）、`DEFAULT_RUN_CONFIG`/`_RUN_TEMPLATE` 注释同步；撤 `factory_override_path`/`load_factory_presets`/`save_factory_override` 与 `panel` 双模式（「保存」回"覆盖选中、出厂项置灰"）；`panel.FACTORY_NAME`/`slot_paths`/`reset_factory`/`load_slot("factory")` 走新路径；`list_config_presets` 排除出厂文件（GUI/publish 预设下拉不出现）；`.gitignore` 去掉 `presets/backup/`
  - 测试：`test_theme.TestFactoryPath`（路径/哨兵名）+ `test_gui`（slot_paths/出厂项保存置灰/`list_config_presets` 排除）+ `test_annotate`/`test_docx` 三处改指 `_PRESETS_PATH`；全量回归
  - 文档：README/安装说明/主题与样式/GUI设计/第三方调用说明（§3.1b 改写）/功能清单/校验说明书 全部改指新名

- [x] **已完成（用户立项，2026-10-09）** 页面边框粗细颜色 + 古籍双框（宽/色键都是内框；单线=内框，双线外框=内框×3全黑）
  - 模型：`output.page_border_width_pt`（默认 0.75）+ `page_border_color`（默认 `#333333`）+ `page_border_style`（single/double，默认 single），开关 `page_border` 不动；归一 `theme.page_border_spec`（显式>预设>默认，非法静默回退）；双线间距恒 3pt（`DOUBLE_GAP_PT`，无键）
  - 落地：`render_docx`（单线内框规格；双线 `thickThinMediumGap` Word 原生近似，单边单色取外框黑）+ `render_pdf._draw_page_borders`（精确绘制）+ CLI `--page-border-width/color/style`（显式>config）+ GUI 页面卡样式下拉/内框宽数字/内框色按钮（未勾选禁用，roundtrip）；verify 不读，指纹白名单不收（边框不影响文本，与 `font_scale` 同例）
  - 外观变更：单线默认色由黑变深灰（单线=内框的推论）；迁移注记见主题与样式/功能清单（显式设 `#000000` 回旧观）
  - 测试：`test_theme.TestPageBorderSpec` + `test_docx`（默认/内框规格/双线）+ `test_pdf.TestPageBorderDraw`（免数据，drawing 断言）+ `test_gui.TestPageBorderPanel`（roundtrip/禁用联动）
  - 附带：独立窗输入帮助 C 方案（编号框卷示例+tooltip+「？」按钮`_input_help_dialog` QLabel 换行；「？」在输入来源行佛典編號列表右；`TestInputHelp` 4 项）
  - 追修（2026-10-09 用户报双线外框左/上线细）：根因非生成端（XML 四边逐字相同）而是渲染器镜像约定——`thickThinMediumGap` 粗细方向标准未定义，LO 实测不按边镜像（上/左翻转；`double` 对称正常、`thinThick` 呈镜像反转，反证成立），WPS 同症（用户所见），Word 按边镜像才正确
  - 追修2（用户：双线还是细 + 给六步手工法）：等粗 `double` 两线皆细不像古籍。改混合式——外框 `pgBorders single`（宽=内框×3 黑，全后端通用）＋ 内框 header DrawingML 锚定矩形（`behindDoc` 衬底，`header2.xml`/rId5 全节引用，每页重复；`w:document` 根补 `xmlns:r`，休眠扩展点潜 bug）；合成 12 页 LO 实测每页外 2.25 黑/内 0.75 `#333`（像素色值 0/51/255 对齐），版式无扰动；`TestFrameHeaderXml` 免数据 3 项

- [x] **已完成（用户点档）** 注释/校验两卡布局收紧
  - 注释卡：校注内联括号并入注释方式下拉右边同行（下拉+标签同置灰 `_sync_note_brackets_enabled`）；注释总开关上方加横线（QFrame HLine/Sunken），与正文夹注组视觉分开
  - 校验卡：两条灰字说明并入复选框同行（不折行，卡高度省两行）；scope 说明重写为用法（只用输入 XML 实际覆盖卷的官方 _NNN 基线；--juan 子集必备）+ `scope_box` tooltip 完整用法（与 `verify.py:1884` 对过）
  - 测试：`test_notes_on_label_and_row` 按新布局重写（无独立表单行、同行含下拉+标签、末行断言）；全量 `test_gui` 298 OK；`GUI设计.md` 示意图同步

- [x] **已完成** 设置窗口校验目录区收编 + 批量表状态提示（2026-10-11 用户点档）
  - 校验目录：生效值与配置合一（字段空/清空时灰字 placeholder「跟随输出：<生效路径>」实时随输出刷新）；原"生效值"标签改「空间占用」、原行末占用灰字 label 删除（占用文本改入该只读框，格式 `5 B（1 个文件）`/`（尚无校验产物）`）；刷新/打开目录/删除校验产物按钮保留；`_open_verify_dir` 改读 `_effective_verify_root()`（原读只读框文本，占用入框后会坏）
  - 批量表：状态格 tooltip 全文定宽折行+「Ctrl+C 可拷贝」（`_status_tip` 纯函数）；补批量表 Ctrl+C 快捷键（`SourceDialog._copy_table_selection` 复用；此前注释写了但未实现）
  - 测试：`TestSourceDialog.test_io_verify_row_follows_out_dir`/`test_verify_rows_labels_and_follow_hint` 重写 + `TestMainWindowUx` 3 项；全量 `test_gui` 308 OK

- [x] **已完成** GUI 字库选择（繁体）不生效修复（2026-10-11 用户报：宋体.css 繁体正文設細明體，字库选繁体仍出宋体）
  - 根因：`build_render_cmd` 仅"简体且非 t2s"传 `--font-lang`；`write_temp_presets` 快照不带 `font_lang`（与 `_presets_merged` 不一致）→ 子进程 `resolve_engine_vertical_lang` 回退 base（config.user.json `font_lang=zh-Hans`）→ `Theme.from_css(zh-Hans)` 走 `html[lang="zh-Hans"]` 栏（`--font-p: 宋体`）
  - 修法：快照携带 `font_lang`（`data["font_lang"] = opts.font_lang or base or "zh-Hant"`，与保存路径同口径；t2s 优先级不变）；只读模拟实证 zh-Hant→`細明體, MingLiU`、zh-Hans→`宋体, SimSun`
  - 测试：`TestTempPresets.test_temp_presets_carries_font_lang`（含 `resolve_engine_vertical_lang` 串联）；`GUI设计.md` §4.2 步 4 注记

- [x] **已查明** T1579 epub/txt 校验慢 vs docx/html 快的原因（2026-10-14 用户报 epub/txt 校验很久；UI 实测 html 10 秒 0/0）
  - 四格式对照（T30n1579，100 卷）：docx 基线 100/100，归一化逐字一致，`docx→docx 缺0/多0`，秒级；html 真 pair（验证-dir 重生档）只差官方 24 字头 `No.1579[cf.Nos.1580-1584]`，`strip_head_no`（配置里开着）整行剥掉 ⇒ 0/0，10 秒；epub 真差异仅 **缺111/多33**（官方 epub 丢 `𥮄𥭳𥝖` 等缺字；头部令牌 24 字已由"恒剥"去掉，修复前为 缺135/多33）却跑 70 分钟+；txt 基线残 **2/100 卷**（113 万 vs 2.6 万）68 秒
  - 机制（三次对照一致）：`diff_stats`（`SequenceMatcher`+`autojunk=False`）耗时是**文本长度的函数、不是差异的函数**（≈n^2.6：30 万字/差6字 71.4s、30 万字/差60字 152s、60 万字/差12字 443s、100 万字/差144字 70 分钟+）。0/0 ⇒ 前后缀裁剪吃光 ⇒ 秒级；prefix=0（25 字官头错位）⇒ trim 失效 ⇒ 百万字整体进 difflib
  - 脆弱性：html 的 10 秒**完全依赖 `strip_head_no` 开着**——关掉复刻则 middle=98 万（生产档 pair 实测 hang 7 分钟+才被超时杀掉）。哪天关掉该开关，html 校验从 10 秒变约 1 小时。docx 不脆弱（对称剥头是无条件逻辑）。→ **2026-10-14 已修**：校验侧行首令牌恒剥、两侧同剥，与开关解耦（见下「已完成 校验行首令牌恒剥」）
  - **小结（2026-10-14 收口）**：T1579 的"epub/txt 校验很久"是**两个原因叠加**——① **含注 txt 基线残卷**（只有 2/100 卷）：第一个试算必然失败 ⇒ 校验链继续往下试；② **往下试到的那次 epub 试算本身慢**（两侧各约 95 万字、差异散布在全文、前后缀裁剪只吃掉 0.7% ⇒ 差不同 65.5 分钟；规律是"耗时只与文本长度有关，与差异多少无关"）。三处修复各治一病：**基线按卷补缺**（治①，顺带消除"错位比对"与"假的多 96 万"）、**行首令牌恒剥**（治"官方头导致裁剪失效"，html 由约 1 小时变 5.3 秒）、**报告差异段封顶**（治报告膨胀 5.8 MB → 29 KB，与耗时无关）。
  - 修复后实测（T1579）：txt `缺0/多0` **5.4 秒**、epub `缺0/多0` **9.1 秒**（第一个试算即通过，后面的 epub/html 试算不再跑）、html 约 10 秒、docx 秒级 ✓。
- [x] **已完成** 校验汇总弹窗：行末「打开报告」链接 + 生成/校验耗时（2026-10-14 用户反馈）
  - 链接：**非「通过且缺0/多0」**的行（出错、失败、通过但有差、无对照、已覆盖）行末给链接，文字「打开报告」，点击用**系统默认程序**打开该行报告文件
  - 打开方式（2026-10-14 用户实测修正）：明细控件 `QTextEdit` → `QTextBrowser`；**不能只靠 `setOpenExternalLinks(True)`**——本地 `file:` 链接仍会在控件内导航（表现为"在弹窗里打开了报告"）⇒ 改为 `setOpenLinks(False)` + `anchorClicked` → `QDesktopServices.openUrl(url)`，点击即交给系统默认程序
  - 「打开报告目录」按钮保留（与行末链接并存）
  - 耗时（简单版）：每行行末显示「生成 3.2s　校验 1 分 05 秒」——生成=该格式渲染子进程墙钟；校验=`verify_one` 全程（含重生成比对档）；`verify.format_duration` 统一格式化（`<60s` 用 `12.3s`，否则 `1 分 05 秒`／`1 小时 01 分`）；同时并入报告段首行 `=== <源文件>　生成 …　校验 …`
  - 报告路径健壮化：原先靠"写完报告后给记录补 `report` 键"，改为**循环前算好报告路径、创建记录时即写入**（事后补键保留为兜底）——避免时序问题导致弹窗不出现链接
  - 记录键：`render_sec`／`verify_sec`／`report`（GUI 写；`verify_one` 本身不产这三个键）
  - 测试：`TestFormatDuration` 3 项（格式化含四舍五入/非法值、段首行带/不带耗时）、`test_run_appends_verify_report_to_files` 扩展（记录带 `report` 与两个耗时键、报告段首行含耗时）、`test_verify_summary_dialog` 扩展（耗时显示）
  - 备注：若运行的是已发布的 EXE（v0.9 打包版）或改动前启动的 GUI 进程，这些改动都不会出现，需要重新打包/重启
- [x] **已完成** 基线按卷核对与补缺（2026-10-14 用户立项："先解决下载卷的问题"，分段/分卷搁置）
  - 问题：按需下载只在"该种基线**一份都没有**"时触发（`ensure_baselines` 见任意文件即跳过）⇒ 历史按卷校验留下的残卷（T1579 txt 仅 `_035`/`_093`）被当全量 ⇒ 全量校验"我们 100 卷 vs 官方 2 卷"，首条差异即"源＝卷第三十五、新＝卷第一"（用户报"TXT 是否比较错卷"实锤），数字无意义（缺0/多96万）且慢 ✗
  - 落点：`pycbeta/fetch.py` 新增 `baseline_volumes`（文件名 `…_{NNN}.ext` → 卷号集合）+ `complete_baselines`（期望卷＝XML 卷号集合，缺卷调 `fetch_baseline_juan` 补齐；`docx` 按用户确认 **(a) 整部重下**；`epub`/`odt` 与无按卷命名者跳过；整体缺失不产条目）；接线 `pycbeta/verify.py` 的 `verify_one`（全量任务 `_juan and not _strict_juan` ⇒ 核对后补缺再比；受 `auto_fetch` 开关控制）与 `pycbeta/cli.py` 校验循环同口径
  - 报告与机读：报告段首行下加 `基线覆盖：txt_notes 2/100 卷（缺 1-34,36-92,94-100）`（`format_juan_ranges` 压缩区间；完整/未核对不显示）；`report.json` 加 `fmts.<fmt>.baseline_coverage = {have, expect, missing}`（多记录聚合：have 最小、expect 最大、missing 并集）；GUI 汇总弹窗行末同步 `基线 <kind> N/M 卷（缺 …）`
  - 边界：卷号↔文件名不保证 100% 一一对应（个别作品编号不同）⇒ 补下尽力而为、404 静默；永远 best-effort，补不齐如实显示缺口，绝不静默当全量
  - 测试：`TestCompleteBaselines` 5 项（解析/补缺只下缺卷/下载失败如实报告/整体缺失无条目/epub 跳过）、`TestBaselineCoverage` 3 项（区间格式化、缺卷报告行、完整不显示）、`test_report_json` 键集与聚合 2 项、GUI 弹窗断言 1 处
  - 备注：分段比对／按卷比对按用户指示**搁置**（TODO 保留条目，暂不动工）
- [x] **已完成** 校验行首令牌恒剥、两侧同剥（2026-10-14 用户确认；与 `output.strip_head_no` 开关解耦）
  - 背景：官方基线恒带 `No. …` 头；开关关掉时官方侧不剥 ⇒ 该头卡住公共前缀（prefix=0）⇒ 整部百万字进逐字比对（html 从约 10 秒变约 1 小时，T1579 实锤）
  - 落点：`verify_one` 令牌表改无条件（`_head_no_tokens(work)`），对我方 `ours_raw` 与 epub 两个专用形（`_txt_raw`/`_body_raw`）同时剥离；`_body_sidecar` 两侧同剥；CLI 校验循环（`_theirs_norm.toks` 无条件 + `ours_raw_all`/`_t_raw`/`_e_raw` 剥离）；`test/verify_text.py` 同口径；`_strip_no_from` 保留作兼容
  - 文档：`校验说明书.md` §7.2 改写、`第三方调用说明.md` `verify_one` 行、`README.md` 与 `config.factory.json` 注记
  - 测试：`TestHeadNoTokenAlwaysStripped` 2 项（开关关掉时官方令牌仍剥 ⇒ 0/0；两侧都有令牌 ⇒ 两侧同剥）
  - 端到端实测（2026-10-14）：把 `strip_head_no` 置 **false** 跑 T1579 html 校验（修复前该场景 7 分钟未完被超时杀掉、按外推约 1 小时）⇒ **`ok 缺0/多0`、5.3 秒** ✓
  - 代价（已告知用户）：该元数据行写错不再被校验发现
  - 遗留（未改）：指纹入参 `canonical_verify_config` 仍含 `strip_head_no` ⇒ 开关切换会改指纹而结论不变（建议后续去掉，会一次性改变既有指纹；不单独做，随下次因其他改动导致的指纹整体失效顺带）
  - 诊断踩坑备忘：初测误拿 `out/` 生产档当生成侧（生产档与验证重生档内容差很多——「校验恒比注」设计使然，校验永远按 canonical 设置重生）；真 pair 是 `（验证）` 目录文件。死掉的假设：`\r`（`normalize` 全剥空白）、官方 epub 内联注（全库仅 4 个 22 字）、有界下界（30 万字场景 66.2s≈全量，无收益，已砍）
- [x] **已完成** 校验正文差异早停（长度门；2026-10-14 定稿，2026-10-20 方案简化；2026-10-23 实施）
  - 现状变化（2026-10-14）：它主要针对"长度悬殊"（残卷/错卷）那一类——该类已被"基线按卷核对与补缺"从源头治掉（残卷自动补全）⇒ 紧迫性下降；仍保留待做，等实际再遇到"长度差很大但基线齐全"的比对时再启用 ✓
  - 背景：门专治「长度差 > 阈值」：T1579 txt 残卷（历史场景）秒判；T1579 epub trial 同样秒判（70 分钟+ → <1s）；html 已 0/0 无需救。只剩「等长＋差异≤阈值＋文本巨大」是门哑的场景（如补完基线后差异很小的百万字对）。
  - 口径（2026-10-20 简化，以本版为准）：不新增配置键、CLI 开关、GUI 输入框；阈值直接用现有 `maxDiff`，严格大于才截断。判定对象 = trial 实际要比的两串（`t_ours`/`theirs`），不是正文段旁路。依据：`diff_stats` 的「缺+多」≥ 两串长度差（`verify.py:1035-1038`），长度差 > `maxDiff` ⇒ 本 trial 必然 fail ⇒ 门只可能截断必然失败的 trial，pass 路径永远全量精确、永不受影响。
  - 门：O(1) 长度门——`|Δ长度| > maxDiff` 即判停（约 3 行）。有界下界版已砍（无收益 ＋ ~40 行复刻代码与误停风险）。
  - 截断规则：整条 trial 先过长度门——超线 ⇒ 本 trial 直接 fail-截断，跳过 `diff_stats` 与正文旁路；未超 ⇒ 走今天的全量精确（注释差异照常全列）。停止只停当前 trial，不停基线链（一个基线截断照样试下一个）。已知取舍：正文缺 N 字、注释多 N 字（总长度差 0）时门不触发，仍走全量比对——罕见，只影响速度不影响结论。
  - 截断显示：`长度差 X > 阈值（未全量比对）`，**不给缺/多拆分、不列差异片段**（长度门不找差异位置，无片段可列）；`【源】/【新】/【源比较】/【新比较】`行照常（GUI 侧 compare 文件已先写；CLI 侧全部 trial 都截断时无 compare 文件，报告只给长度差）。`report.json` 不加新字段：沿用现有「fail + 缺/多=None」形态（`_record_counts`/`build_report_json` 已按 None 处理），`diff_scope` 不变。
  - 定位边界（已向用户说明）：截断报告只能说「差很多、别等了」，说不出哪里差；首字符就不同的对连「首差异锚点」都无价值，故本次不加锚点。真定位（前 N 差异块 + 行号）要靠分段比对。
  - 落点（2026-10-20 简化，约 30~40 行）：① `verify.py:2261` 前 3 行（算长度差，超线记截断 trial 并 `continue`；compare 文件已在 `:2250-2259` 写好）；② `cli.py:1500` 前同样 3 行；③ 全截断兜底：`verify.py:2290` 前返回 `missing/extra/total=None` 的 fail 记录，`cli.py:1566` 的 `if best is None: continue` 改为输出 fail 记录（否则整个格式被静默跳过）；④ `verify.py:2463` 加截断显示分支。不碰 `_body_sidecar`（3 返回值与 3 处测试不变）、`best` 15 元组、`diff_stats`、xml 基线路径、指纹载荷；另有 `test/verify_text.py:239-366` 同款比对循环（开发脚本，实施时一并同步）
  - 实施结果（2026-10-23）：`verify.py` 新增 `length_gate`（差严格大于 `maxDiff` 即截断）；门在 compare 文件写完后、`diff_stats` 前；截断 trial 记 `missing/extra/total=None`、`length_diff`；截断时用正文串 O(n) 判等补回 `diff_scope`（正文全对 → `notes_only`，正文不同 → `body`，计数为空；报告附 `【仅仅注释差异】`/`【正文差异（未全量比对）】`）；全截断兜底返回 fail（优先 `notes_only`，再取最小长度差）。`cli.py` 同门同旁路（全截断不再静默跳过，详情行附「（基线 …）」）；`test/verify_text.py` 同步。新增 11 项单测（8 项 verify 门/报告/集成 + 1 项 CLI 全截断 + 2 项截断仅注释/正文差异）；既有 `TestEpubTrialBodyOnly`（max_diff=0 下 txt_notes 试算改为断言截断）与 `test_cli` 的 `→ epub 失败:` 改为接受 `截断`。
  - 现场实测（T1509 epub，2026-10-23）：html 链差 860 字秒判截断；正文旁路确认这 860 字**全在注释（正文 0/0）**，截断行保留 `【仅仅注释差异】`；txt_notes 链归一后 0/0 通过；整次 `verify_one` **8.5–10.3 秒**（两次实测，此前抓栈确认卡在 `difflib.find_longest_match`，外推数小时）。第三条 epub 链因已通过不再执行。
  - 关窗兜底：`gui/__main__.py` 的 `closeEvent` 等待 10 秒仍不退出时给「强制退出 / 继续等待」，不再永远挡门。
  - 未覆盖：等长（长度差 ≤ maxDiff）且差异散布的超长对仍走整篇 `SequenceMatcher`（T1579 epub 65.5 分钟先例）；需分段/按卷比对（仍搁置）。
  - 影响：改 `verify.py` ⇒ `_impl_digest` 变（`_FP_IMPL_MODULES` 含 `verify`）⇒ 全部已存校验指纹一次性失效，需接受（与方案无关）。
  - 验收：构造用例——复制一个官方基线文件、截掉一半，断言秒级 fail、缺/多为空、报告有「未全量比对」；正常作品（如 T1579 html）仍 `缺0/多0`；T1499 txt（`缺0/多18` 注释差异、正文长度差小）仍出精确数 + `【仅仅注释差异】`；单测（截断/不截断/链 fallback/全截断兜底）＋ 全量回归；文档（`校验说明书.md` + `校验report.json说明.md` 各一行：fail 记录的缺/多可为空）同步。原 T1579 残卷场景已被「按卷核对与补缺」消除（该项已完成，见上），不再作为验收。
  - 注：原「html 10 秒依赖 `strip_head_no`」的注记已过时（行首令牌现恒剥，见上条「校验行首令牌恒剥、两侧同剥」），本次一并删除。
- [ ] **搁置（2026-10-14 用户指示）** 大文本分段比对（适用范围：等长或长度差小、差异不大、但文本百万字的对）
  - 搁置理由：它针对的是"等长 + 差异散布 + 超长文本"那一类慢试算（T1579 epub 试算 65.5 分钟）；现在第一个试算就通过（`缺0/多0`），那类试算不再被触发 ⇒ 暂不启动，等将来真有作品走到第二个试算再做 ✓
  - 整对实证（2026-10-14）：T1579 epub 完整对（95.5 万字）——现行口径（autojunk=False）**缺135/多33，耗时 65.5 分钟**；分段比对 **缺135/多33，约 2 秒** ⇒ **数字完全相同、快约 2000 倍**
  - 同日撤回三条错误结论（都是原型代码 bug，不是分段比对本身的问题）：①「分段比对会翻转判定」——行级 insert/delete 的缺/多记账写反；②「epub 对数字少约 15%」——同一 bug 且原始文本与归一化文本混用；③「分段比对 5 倍虚增」——实验切片取的不是对应内容（两侧行数 33,328 与 28,411，对应关系渐变）
  - 干净对照：4 组按内容锚定的真实窗口（最大 7.7 万字）＋ 8 种合成修改（散点替换、删行、拆行、并行、移行、倒序、整段删）数字全部一致
  - 已知弱点：两侧「行对应关系」崩坏时行级对齐会虚增 ⇒ 实现时加兜底「行级相等率过低则退回一次性全文比对」
  - 待办：全库回放验收（目前只是样本）；比对输入现在是无换行长串，分段比对要在带换行的显示文本上切段、逐行归一，会牵动 compare 文件的行号体系
  - 附带收益：截断报告可升级为「前 5 差异块 + 行号 + 上下文」（真定位）；也是「补完基线后差异很小的百万字对」的唯一提速路
- [ ] **搁置（2026-10-14 用户指示）** 按卷比较（逐卷比对；2026-10-14 讨论立项）
  - 搁置理由同"大文本分段比对"：目前没有作品被触发到"等长 + 差异散布"的慢试算 ⇒ 暂不启动 ✓
  - 原理：比对耗时约与文本长度的 2.6 次方成正比 ⇒ 切成每卷一比，"各卷平方之和"远小于"整篇平方"。实测参照：T1579 epub 整篇 95.5 万字一次性比对 65.5 分钟；分段比对同数字约 2 秒（按卷是分段比对更粗的粒度，量级相同）
  - 底座已具备：项目已有按卷过滤（`filter_work_juan`、`verify_one(juan=…)`、基线按卷限定 `strict_juan`）；缺口是"整篇比对改为逐卷比对 + 汇总"，外加 txt/md/docx 的按卷重整
  - 切卷前提：html 两侧都天然逐卷；epub 两侧也逐卷——官方 `.epub` 容器内是 `OEBPS/juans/NNN.xhtml`（2026-10-20 实测 T1579 100 卷、TX0001 34 卷、T0001 22 卷，均含正文）；我方 epub 按来源卷生成章（一卷可拆多章，`juan` 只在缺标题时回退写入标题，`render_epub.py:137-142`）⇒ 需先补「章→卷」映射；txt/md/docx 是单文件 ⇒ 需要"按卷重整"（正文按卷切开、注释按锚点分配到各卷）
  - 注释必须一起分卷：否则第 1 卷的官方注被算成"我们缺"、最后一卷把全部注算成"我们多"，比整篇一次性比对更糟。归属规则 = 注锚点所在卷；解析器已跟踪当前卷（跨卷星号那次改动加的）
  - 附带收益：① 消除"我们注集中文末、官方注随卷"造成的先天残差；② 报告可逐卷（如"第 5 卷：正文 0 差异、注释 缺3/多2"）；③ 残缺基线直接列出缺哪几卷，而不是百万字的"多"；④ 天然配合"停止线只判正文、注释继续比"
  - 代价：单文件格式（txt/md/docx）要新增按卷重整；数字会变（分卷 + 注释重新归属）⇒ 需全库回放验收；报告与 `report.json` 结构改为"逐卷 + 汇总"
  - 与分段比对的关系：按卷是分段比对的粗粒度形态，但完全复用现有逐字比对（不动 `diff_stats`）；分段比对粒度更细（行级）且不需要解决"我们这侧切卷"。两者择一或组合，等分段比对的整对数据与全库回放后再定
  - **讨论结论（2026-10-14）**：
    - **分段比对**：粒度细、能给出"前 N 个差异行块 + 行号 + 上下文"（真定位），且不需要解决"我们这侧切卷"；但动算法（行级对齐 + 块内逐字 + 接入 compare 文件行号体系），实现风险中等偏高。
    - **对齐失败会虚增**（分段比对的核心风险，已讨论确认）：两侧"行对应关系"崩坏时（换行/分段方式差异大、大块内容搬移、拿错基线），行级对齐只能配上零星相同行 ⇒ 大块"替换"块内两侧内容其实不对应 ⇒ 两侧的字各计一次，缺+多最大可达文本长度的 2 倍。实证：误切实验里整篇比对 23,847/25,644，分段法给出 118,442/120,239（约 5 倍）。**但不是常态**：T1579 epub 实测 76% 的行逐字相同，分段法与整篇数字完全一致。
    - **防护四条**：① 兜底——行级相等率过低则退回整篇一次性比对；② 只在"对齐可信"的区间分段，对齐失败的大区间不硬比；③ 用语义边界（卷/章）切而不是用行边界切；④ 反向校验——"缺+多"接近文本长度 2 倍时标记可疑，不直接出结论。
    - **按卷比对**：同类风险（跨卷的字配不上 ⇒ 该卷内容两侧各计一次），但卷边界由内容决定、两侧卷基本一一对应 ⇒ 触发概率低得多，且影响被限制在单卷；另有独特收益（残缺基线友好、消除"注集中文末 vs 注随卷"残差）。
    - **合理终点（组合形态）**：先按语义边界（卷/章）切，再在范围内按行分段——兼得"规模可控 + 定位精确"，且把分段比对的对齐风险限制在单卷之内。代价是两套都要做，需分批推进。
    - 待办不变：分段比对的全库回放验收（目前只有整对 1 例 + 窗口 4 组 + 合成 8 种的样本）。
- [x] **已完成** 补全残缺官方基线（2026-10-14 落地为"按卷核对与补缺"，见上「已完成 基线按卷核对与补缺」）
  - 适用范围（首次跑会自动补缺卷，下载时间计入弹窗"校验"耗时；补完第二次即为秒级）：T1579 `txt/` 仅 2/100 卷；另有 T0220 3/600、T0279 2/80、T0310 2/120、T0374 2/40、T0397 1/60、T1542 1/18
  - 实测（T1579 txt）：首次 校验 1 分 36 秒（其中主要是补下 98 卷）→ 第二次 **`缺0/多0`、校验 5.4 秒** ✓；也彻底证实此前"缺0/多96万"只是残卷造成的假差异
- [ ] **搁置（2026-10-14 用户指示）** 指纹回退口径对齐（下游《上游审核-指纹首选缺失与回退》审核后定稿，暂不动工）
  - 问题：非 T/X 藏经（如 K 部的 K0016、K1482）的 docx/pdf 上，首选 docx 缺失，且官方 docx 只对 T、X 提供（非 T/X 藏经没有；2026-10-20 实测 `cbeta_docx_2026r2` 仅 T/X 两目录）⇒ 真校验下载 404 后回退 html 给出结论 ✓，但指纹侧硬性要求首选在场、直接缺席返回未定义 ⇒ 每轮都重验、复用永远不中 ✗
  - 方案（定稿）：`fetch.py` 新增规则单一来源（如"官方仅 T、X 提供"的种与藏经判定；未知种恒为可提供），指纹侧仅放宽"规则判定必然不可下载"的情形（按 `resolve_bases` 的回退结果证明，与真跑同口径）；载荷带规则版本常量，将来规则修订时旧记录一次性失效重验；临时 404 等仍返回未定义（将来可能成功，本次不能证明）
  - **暂不做的原因**：改动约 80 行，中等偏小，但收获几乎为零——不提速（省的不过约一次基线发现，修后提速只有约 46 毫秒）、不让结论更对；唯一的收获是非 T/X 藏经的两格式在二轮重制时跳过几次校验，而**指纹载荷一改就会让全部现存记录一次性失效**（下一次全库跑会整体重验，成本高）⇒ 等真在《藏要》第二辑这种大批次上被"未复用"反复拖慢时再做
- [x] **已完成** 校验指纹提速与语义修正（2026-10-14 下游《上游审核-指纹慢根因》审核后落地）
  - 根因（下游实测 + 本仓审核确认）：`source.baselines` 指向大库根后，`_find_official_in` 的 5 组递归通配符每次调用都扫全库（txt_notes 27,049 文件 ≈ 1.4 秒；docx ≈ 0.33 秒）⇒ 单次 `verify_fingerprint` ≈ 1.8 秒 × 87 次 ≈ 177 秒
  - 修法一（发现提速）：新增 `_direct_official`——按集中库布局 `{根}/{canon}/{work_id}/{work_id}_{NNN}.{ext}`（多卷：html/txt_notes/docx）或 `{根}/{canon}/{work_id}.{ext}`（单文件：epub/odt）直接定位，未命中回退通配符；实测单次发现 **1738 ms → 45.9 ms**（T1579 + 三个库根，含基线哈希），**结果集合与顺序完全一致（指纹逐字相同）**；工作目录型根不受影响（T1579 自带基线：新旧均 3~5 ms、结果一致）
  - 修法二（协议语义）：指纹载荷的文件身份改用 `_fp_file_identity`（`{name,size,sha256}`，**不含 `mtime_ns`**）⇒ 同字节重写（或基线重下后 mtime 变化）不再让指纹失效；`_FP_VERSION` `verify-fp-1` → **`verify-fp-2`**，并修正返回串此前**硬编码** `verify-fp-1`（版本升级此前不会体现在串上）
  - 文档：`校验report.json说明.md` §4（新增 `_ctx` 复用说明、载荷不含 mtime、发现提速说明）、`上游-P2校验结论跨边复用提案.md`（mtime 措辞修订）
  - 测试：`TestDirectLookup` 3 项（库布局与通配符同集合同顺序、卷过滤一致、非库布局回退）、`TestDeterminism` 新增 2 项（仅 mtime 变不改指纹、载荷身份不含 mtime）
  - 未做（下游侧，已在文档注明）：publish 按「部 × 格式」逐次调用时复用 `_ctx`（可再省约 2/3 重复扫描）
- [x] **已完成** 校验阈值 0 被改成 10（2026-10-15 用户反馈）
  - 根因：取值处写 `int(v.get("maxDiff", 10) or 10)`——0 是假值，被 `or` 吞掉换成 10。输入框允许 0（范围 0–1000）、保存路径保留 0，只有"读出来用"的 4 处篡改：调 `verify_one` 的实际阈值（最致命）、写报告阈值、`build_report_json` 阈值、设置对话框回显（回显 10 且此时点保存会把 0 写回成 10）
  - 修法：新增 `verify.cfg_int(value, default)`（只有缺失才回缺省，0 与空串分别保留与回缺省），替换上述 4 处共 8 个 `or 缺省`；`verify_one`／指纹／CLI／`test/verify_text.py` 本来就对 0 正确，不动
  - 测试：`cfg_int` 取值、`max_diff=0` 下缺3判 FAIL、输入框 0 往返（保存与回显都是 0）
  - 说明：修完后配 `maxDiff: 0` 会看到更多 fail（以前被放过的 1–10 字差异现在报出）——这是修 bug，不是变严
- [x] **已完成** 方框字（`seg`/`hi` 的 `rend="border"`）渲染（2026-10-15 用户点档：TX12n0007 发现新 tag）
  - 现象：`<seg rend="border">釋</seg>`（科判字）/ `<hi rend="border">題前概說</hi>`（标题字）——原书里的「方框字」。语料：`seg[border]` 350 处／8 部（全 TX）；`hi[border]` 44 处／22 部（全 YP，多在 `<head>`）；`seg`/`hi` 的 rend 另有 `bold`（1993 处）与 `kaiti`（10 处），本次不做（见下）
  - 官方口径：官方 epub `cbeta.css` 即 `span.border { border: 1px black solid }`、正文出 `<span class="border">`；官方 html 也出该 class（规则在网站样式、文件里没有）。官方 docx 无 TX/YP（无从对照）
  - 修法：`render_html._render_misc`（seg/hi 且 rend 含 border → `span.border`；html/epub/pdf-html2pdf 同一管线）＋ `render_docx._render_e`（同判定 → run 打 `border` 标签）；`theme.TRANSLATABLE` 加 `border`、新增 `_border_ooxml`（CSS 简写 → `w:bdr`，1px=0.75pt、solid→single、缺色 auto）、`TAG_SELECTOR["border"]="span.border"`、`REQUIRED_THEME_TAGS["border"]=("border",)`；`pdf_docx.css`／`html_epub_official.css` 各加 `span.border { border: 1px black solid; }`，`epub_print.css` 按派生约定同步
  - 死命令三件套：`TAG_SELECTOR` ＋ 左栏行 `("span.border","方框字")`（`css_editor.EDITABLE_ROWS`，`ROW_TIPS` 注明边框线只在源码页调）＋ CSS 规则
  - 附带（用户点档）：`div.div-commentary` 补进 `html_epub_official.css`（`font-weight: normal`，外观零变化，与 `pdf_docx.css:220` 同口径）；`pdf_docx.css` 原已有该条、不动
  - 测试：`test_theme.TestBorderTag` 4 项、`test_docx.TestBorderRender` 3 项、`test_md_epub.TestBorderRender` 3 项、`test_gui.test_border_editable_row`；`test_render._body` 的归一化已剥 border span，不用动
  - 文档：`主题与样式.md` 新增「方框字」节、`兜底值清单.md` 登记 `border_pt`（0.75）
  - 影响：`render_html`/`render_docx`/`theme` 都在 `_FP_IMPL_MODULES` ⇒ **全部已存校验指纹一次性失效**（下轮全库重验；与 v0.91/v0.92 同例）
  - 已知小差异：官方 epub 不框 YP 的 `<head>` 方框（官方 html 框），我方 html/epub 同管线会框；docx2pdf 引擎对方框的显示待实测（html2pdf 不受影响）
- [x] **已完成** 左栏 UI 加 `div.div-orig`（原文）与 `div.div-commentary`（注释）两行（2026-10-18 落地；2026-10-15 用户指示）
  - 落地：`css_editor.EDITABLE_ROWS` 加 `("div.div-orig","原文")`／`("div.div-commentary","注释")`（排在「正文」行之后）＋ `ROW_TIPS` 两条（原文段官方 golden 与我方 docx 均加粗；解释段官方无特殊样式、缩进来自 XML 的 margin-left）；`TAG_SELECTOR` 早已由 `theme.py` 的 `_DIV_TYPES` 自动登记，CSS 规则早在 `pdf_docx.css:219/220`
  - 两行无字体变量（同「字义」行）：字体双栏置灰，可调字号/粗细/颜色；出厂粗细不算覆盖（按钮显示「默认」）
  - 测试：`test_gui.test_div_orig_commentary_editable_rows`（行与提示存在）＋ `test_gui.test_div_orig_commentary_rows_in_dialog`（行可建、字体栏置灰、粗细默认态、标签文本）
  - 注意：左栏只面向 pdf_docx 主题，html 基底规则不在其可编辑范围（`docs/TODO.md:394`）
- [ ] **搁置** `seg`/`hi` 的 `rend="bold"`（1993 处 / 9 部：YP 7 + TX 2）与 `rend="kaiti"`（10 处 / 2 部：`hi` 6 + `p` 4）的 html/epub 类映射（2026-10-15 扫描发现；2026-10-20 语料复核）
  - 官方 epub 实测：`seg @rend="bold"` → `<span class="bold">`（TX0001 21 处）、`p @rend="kaiti"` → `<span class="kaiti">`（CC0003 4 处）；`hi @rend="bold"`（1968 处，7 部 YP）与 `hi @rend="kaiti"`（YPa001 6 处）官方不出 span（YP0023.epub 的 span.bold=0，偈颂行落 `span.lg-row`）。基底已有 `.bold`，`.kaiti` 官方值 `DFKai-SB, BiauKai` 基底缺；我方现为纯文字。官方 html 本地无库，未核。
  - 暂不做：按官方口径只需做 `seg`/`p` 共 29 处，收益小；`hi` 1968 处官方 epub 不出 span，若跟随会偏离官方形态，是否做需另定。等有实际需求再定范围。
- [x] **已完成** docx `<table>` 完整支持（2026-10-16 用户立项；B28n0157 实报「没能支持 `<table cols="5"><row><cell>…`」）
  - 修前：`_render_table` 只出 `<w:tbl>/<w:tr>/<w:tc>` 裸骨架——无 `tblPr`/`tblGrid`，`cols`/`rows` 合并丢失；`cell` 全部子节点塞进一个 `_para`，`cell` 内 `<p>` 造成段中段（Word/WPS 丢弃嵌套段落）。B0157 实测 37 处、TX0016 15 处
  - 修法（`render_docx.py`）：`_render_table` 重写为 `_render_docx_table`（tblPr/tblGrid/网格模拟/列宽）+ `_docx_cell`/`_render_cell_body`/`_est_text_tw`/`_cell_para_fix`；`cell` 内块级子照 `_render_item` 模式拆兄弟段落（至少保一空段）；`cols`/`rows` → `gridSpan`/`vMerge`，续行补 `<w:vMerge/>` 空占位格（保留同跨度 `gridSpan`，与官方 X0448 同形）；`_cell_depth` 标记让格内 `p` 段落内联覆写 `ind firstLine=0` + `jc left`
  - 官方口径（X0448/X0560/X0575 共 199 表实查）：框线外围四边 `outset sz=6 space=0 color=auto`（无内部格线）、`tblW 0 auto`、`tblCellMar 15dxa×4`、`tblLook 04A0`、不写 `tblInd`；`tcPr` 顺序 `tcW→gridSpan→vMerge→vAlign(center)→hideMark`；`rend` 含 `no-border` → 四边显式 `none`（官方用 `tblStyle=no-bordertable`，视觉等同、免动 styles.xml）
  - docx 专属（自定风格，明确偏离官方；用户已确认）：表格 `jc=center` 居中；列宽按内容估算写 `gridCol`（全角 1em/半角 0.5em × 段字号 + 格边距；gridSpan 格不参与；空列保底 2 字；总宽封顶版心、超则按比例缩）。html/epub/pdf 仍左对齐（官方口径）不动
  - 实测：B0157/TX0016 段中段 37/15 → **0**，新旧产物归一化后文字逐字一致（249,539/154,449 字）；X0448 160 表全出 `tblPr`+`tblGrid`，结构护栏 0，1872 个非空格按文档序命中，首表合并序列与官方 docx 完全相同
  - 测试：`test_docx.TestTableDocx` 8 项（结构/框线开关/gridSpan+vMerge 占位/格内块级子不段中段/空格至少一空段/列宽封顶/表外段落不受 `_cell_depth` 影响/脏数据超出 `cols` 不丢字）；全量 1320 OK
  - 影响：`render_docx` 在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效（下轮全库重验，同 v0.91/v0.92 例）
- [x] **已完成** docx 表格：全网格单线框线 + `tblLayout fixed` + 智能列宽（2026-10-16 用户四项确认：只改 docx／智能少行+按需铺满+fixed／最小列宽 4 字／不进左栏 CSS；线粗 sz=6）
  - 框线：外围 `outset` → **全网格细单线** `single sz=6`（四边 + `insideH/insideV`，0.75pt ≈ 官方 epub 的 1px 全格线）；`rend` 含 no-border → 六边显式 `none`。加 `tblLayout w:type="fixed"`（不加则 Word 自动调整会改列宽，实测窄表被 Word 又缩）
  - 列宽：`_fit_col_widths` 重写——内容放得下按内容收窄；超版心取**最小的"每列最多 T 行"目标**（二分 T，表最矮、折行最少）并用满版心，每列保底 **4 字**（2026-10-16 用户由 2 字改 4 字）；列数多到 4 字×列数 > 版心（X0448 有 25 张 8–12 列表）时，保底降到"均分"再走同一算法（内容感知，不再一律等宽）；富余按"减一行代价最小"回填。（先试过"短列保整行"，实测反而更高——长文本列（識語 60 字）决定行高，保短列只会挤长列，故改"最小 T"）
  - 估算修正：`_est_text_tw` → `_est_cell_tw`：① 多段按**最长段**（原整格求和虚高）；② **注音读音不计宽**（`w:instrText` EQ 域代码、`w:rt` ruby 读音剔除）。修前带注音时 B0157 書名格被算成 74 字（实际约 7 字）
  - 实测（CLI 配置含注音）：B0157 两表 gridSum 7650/8924、TX0016 8940、X0448 160 表 5160–9015（均 ≤ 版心 9027）；163 表全部全网格单线 + `fixed`；4 字保底仅 25 张宽表（8–12 列）几何上放不下，走"均分保底"分支
  - 视觉（Word→PDF 目检）：B0157 書名表（p245）列分隔清楚、`卷數` 表头与 `八十卷` 均单行（4 字保底后）；九品差別圖（p134）成 3 列真网格（原无内线、列挤在一起）
  - 回归：B0157/TX0016 段中段 37/15→0、文字与旧产物逐字一致（249,539/154,449 字）；X0448 护栏 0、1872 格文字全命中；全量 1323 OK
  - 测试：`TestTableDocx` 11 项（`test_structure_official_borders_center` → `test_structure_borders_center_fixed`；新增 4 字保底+铺满、多段取最长段、注音读音不计宽）
  - 影响：`render_docx` 在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效（下轮全库重验）
- [x] **已完成** docx 表格框线与整体对齐改由 CSS 控制（2026-10-16 用户定：`table { border: 1px solid; }`、`border: none` 支持、居中也走 CSS、左栏不加行）
  - 机制：`theme.TAG_SELECTOR` 加 `"table": "table"`、`REQUIRED_THEME_TAGS["table"]=("border","text-align")`；`_border_ooxml` 拆出共用解析 `_border_spec`（返回 (线型, sz, 色)），新增六边版 `_tbl_borders_ooxml`；`Theme` 加 `docx_table_borders()` / `docx_table_jc()`；`render_docx._render_docx_table` 框线与 `jc` 改为读主题
  - CSS：`pdf_docx.css` 加 `table { border: 1px solid; text-align: center; }`（**仅 DOCX 读**——html2pdf 管线标记是 `div.bip-table`、没有 `table` 元素 → 对 HTML/PDF 空转）
  - 映射：`1px solid` → 六边 `single sz=6 color=auto`（＝现状）；`none`/`0` → 六边 `none`（整表不画线）；`text-align: center/left/right`（start/end 归一）→ `w:jc`；认不出/无规则 → 回落内置默认 `single sz=6` + center（`FALLBACKS["table_jc"]`，已登记 `兜底值清单.md`）
  - `rend="no-border"` 的表仍强制六边 `none`（按表覆盖）；单元格段落仍强制左对齐（表格 `text-align` 不漏进格内）；列宽 / `tblCellMar` / `tblLook` 仍硬编码
  - 左栏**未加"表格"行**（表格 2026-09-14 就在左栏外）；调框线/对齐在 CSS 编辑器源码页改那一条
  - 实测：B0157/TX0016/X0448 重渲染结果与改前一致（163 表全网格单线 + fixed；护栏 0；文字逐字一致 249,539/154,449；X0448 1872 格全命中）
  - 测试：`test_theme.TestTableTag` 5 项 + `test_docx` 3 项（CSS 改粗细/线型/颜色/对齐、`none`、无规则回落）；全量 1331 OK
  - 影响：`theme` / `render_docx` 在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹再次整体失效（下轮全库重验）
- [x] **已完成** epub 校验基线链顺序改为 `html → txt_notes → epub`（2026-10-16 用户指示）
  - 定义处：`verify.DEFAULT_BASES["epub"]`（`pycbeta/verify.py:1261`）+ `presets/config.factory.json` 的 `verify.bases.epub` 同步改（`test_verify.test_factory_bases_match_defaults` 守护两者一致）
  - 机制不变：`chain_for`（链序即 trial 序）/`resolve_bases`（∩ 本地现货、按链序去重）/`need_for_base`（缺基线自动下载**跟链首**）→ 现在 epub 链首是 `html`，`-f epub` 缺基线时自动下载改为官方 html（per-vol `{id}_{NNN}.html`）
  - 效果：epub 校验先比官方 html（快），不中再比 text-with-notes，最后才拆官方 epub（含导航/捐款 boilerplate）
  - 手工脚本 `test/verify_text.py` 的私有链（原硬编码 `epub→epub` + html 兜底）改为调用 `verify.chain_for/resolve_bases/need_for_base`，与 CLI 同源
  - 测试：`test_verify`（trial 序 `html/txt_notes/epub`、链默认/空值回退、resolve 序与去重）、`test_cli`（`-f epub` 缺基线拉 `html`）、`test_gui`（基线链行显示 `html, txt_notes, epub`）；全量 1331 OK
  - 文档：`校验说明书.md`（§1 说明、§2 链表、§3 bases 默认、§5 epub 试算改"第三试算"）、`第三方调用说明.md`
  - 注意：首次对某作品做 epub 校验时，若本地没有官方 html，会按 `auto_fetch` 自动下载（落 `cbeta_ebook`）
- [x] **已完成** `<p cb:type="headN">` 当标题渲染（2026-10-16 用户报 B0157「head3 渲染成正文」）
  - 根因：`p cb:type="head3"` 是「带 cb:type 的 p」而非 `<head>`；三渲染器只接了 `pre`/`dharani`/`figure` 等，**没接 headN** → html 出 `<p class="head3">`（CSS 无 `.head3` 规则）、docx 出普通 `p`、md 普通段落 ⇒ 都按正文渲染。官方口径（实测）：官方 html `<p data-head-level="3" class="head">`；官方 docx `<w:pStyle w:val="3"/>`＝Word 内置 heading 3（styles.xml styleId `3`，outlineLvl 2；X0448_001 里 pStyle 1/2/3 各 3/2/15 处）
  - 修法：`render_html._render_p` headN → `<p data-head-level="N" class="head">`（官方同形；`.head` 与 `p.head[data-head-level=N]` 规则生效）；`render_docx` p 分支 headN → 命名样式 `head` + 段落 `outlineLvl="N-1"`；`render_md` headN → `#`×N；txt 不变
  - 连带修复：`<cb:mulu>` 书签/大纲机制此前只认 `head`/`jhead`，headN 段不接 ⇒ 书签越过它挂到后面的 head 或丢失。抽出 `_attach_mulu`/`_with_outline` 复用（顺带修正 `outlineLvl` 插入位置：原插在 `<w:pPr>` 开头即 pStyle 之前，不合 CT_PPr 顺序；改追加在 pPr 末尾＝jc 之后）
  - 实测：B0157 html `<p data-head-level="3" class="head">佛學書目表</p>`、docx `<w:pStyle w:val="head"/><w:outlineLvl w:val="2"/>`、md `### 佛學書目表`（head4 ×2 → `####`）；Word→PDF 目检 p245「佛學書目表」成标题（加粗蓝字居中 20pt）；文字零回归（B0157/TX0016 逐字一致 249,539/154,449；X0448 护栏 0、1872 格全命中）；md 的 `#` 由 `normalize` 剥净不影响校验
  - 测试：`test_render.TestHeadLevelFromCbType` 3 项、`test_docx.TestHeadCbTypeDocx` 4 项、`test_md_epub.TestMd.test_md_head_cb_type`；全量 1339 OK
  - 文档：`主题与样式.md`（标题分级节）、`CBETA-P5-设计规格.md`（元素渲染行）
  - 影响：`render_html`/`render_docx`/`render_md` 均在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效（下轮全库重验）
- [x] **已完成** `<cb:mulu>` 书签**队列化**（合并落地，不再覆盖丢弃）（2026-10-16 用户报 B0157「道德經發隱」书签丢失）
  - 根因：`<cb:mulu level="1">道德經發隱</cb:mulu>` 后面是**卷首标题图**（纯图片段，不作落点）→ pending 悬空；紧接着 `<cb:mulu level="2">敘</cb:mulu>` 把 pending **覆盖**（原实现无条件覆盖）→ 书签/大纲凭空消失。连带：卷13 jhead「道德經發隱」又被「本文」mulu 降成 L1 → 该卷在 Word 导航里整卷条目挂到上一卷（陰符經發隱）下
  - 修法（`render_docx.py`）：`_pending_mulu`（单条 dict）→ `_pending_mulus` **队列**；落地时队列里**每条各挂一个隐形书签**（名字＝各自 mulu 文字），`outlineLvl` 取**更高级别**（`min(level)-1`）；落地点不变（head/jhead/headN，图片段仍不作落点）；新增 `_flush_pending_mulus`（文档结束/分卷结束/jhead 去重丢段时记「mulu 未落地」报告，不静默丢）；`_reset_state` 同时清队列（跨 work 不残留）
  - 实测 B0157：书签 390 → **403**（403 = 24 卷书签 + 379 条 mulu 书签；XML 侧 374 条纯文本 mulu + 5 条含内联标记的全部落地，此前 13 条被静默丢）；导航修正——`L0 道德經發隱敘`（卷13：两个书签合并、级别取 L0）→ `L1 道德經發隱（本文）`，卷14 同理，不再挂到陰符經發隱 下
  - 已知取舍（用户 2026-10-16 确认接受）：落点在「…敘」`head`（图片页之后）⇒ **卷首标题图仍归上一个条目**
  - 回归：B0157/TX0016 文字逐字一致（249,539/154,449 字）；X0448 护栏 0、1872 格全命中；全量 1341 OK
  - 测试：`test_docx.TestHeadCbTypeDocx` +2（两条 mulu 合并落地/级别取高者；mulu 未落地记报告）
  - 文档：`主题与样式.md`（标题分级节补 mulu 队列口径）
- [x] **决议不做（仅记录）** docx 卷首标题图（纯图片段）不作导航条目（2026-10-16 用户确认）
  - 现状：mulu 落点不含图片段 ⇒ 卷首图归上一个条目；若把图片段作落点，会得到**空标签 L0**（Word 导航显示段落文字，图片段无文字），层级会修正（后续条目挂它下）但多一条空行，且卷10/11/12 等会多出空 L0
  - 决议：接受现状（卷首图仍归上一个条目），不再追"图片段作落点"；原计划"先做小测试档在 Word/WPS 目检空标签 L0"随之撤销
- [x] **已完成** 校验报告 `"/>` 怪字符（T31n1585；2026-10-16 用户报；生成侧 + 校验侧两侧修复）
  - 根因（两层）：① 生成侧 `_attach_mulu` 把 `<cb:mulu>` 文字原样写进书签属性 `w:name="…"`（T1585 有 7 条目录文字自带 ASCII `>`：`㊀問起> `×5、`2 廣釋> `、`1 解頌> `；裸 `>` 在属性值里合法，但同一路径下 `&`/`<`/`"` 会产出非法 document.xml——本次一并转义）；② 校验侧 `_TAG_RE = <[^>]+>` 在属性值内的 `>` 处提前截断，残留 `"/>` 进比对文本（normalize 去 `>` 后报告显示 `"/`），与对端 `〓` 补位凑成假差异（报告 2 处、`缺0/多14`、FAIL）
  - 修法：`render_docx.py` 新增 `_attr()`（`escape(s, {'"': "&quot;"})`），用于书签名两处（`_with_bookmark` 卷名书签、`_attach_mulu` mulu 书签）——转义后 Word 显示与导航不变；`verify.py` 的 `_TAG_RE` 改引号感知 `<(?:'[^']*'|"[^"]*"|[^>"'])+>`
  - 影响面实测：229 部语料目录文字含 `>` 仅 T1585（7 处）、含 `&`/`<`/`"` 为 0；新剥标签式对 227 个生成 docx + 2276 个 epub 章节等价（只有 T31n1585 结果变化＝假差异消失）；`verify_one` 端到端重跑 T1585 docx：`缺0/多0` OK（修复前 `缺0/多14`），新生成档 7 个书签名全部转义、document.xml 可解析、抽取无残渣
  - 测试：`test_docx.TestBookmarkNameEscaping` 2 项（`_attr` 四类字符、mulu 书签转义 + 部件可解析）；`test_verify.TestDocxStripQuotedGt` 2 项（引号内 `>` 整段剥除、最小 docx `extract_text` 无残渣）；全量 1345 OK
  - 影响：`render_docx` 与 `verify` 均在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效（与 v0.93 后全库重验合并一次）
- [x] **已完成** docx 卷题落层错乱（T31n1585「卷第三」进第三层；2026-10-16 用户报）
  - 根因：空的「卷」标记 `<cb:mulu n="003" type="卷">` 被整条**跳过**；卷题段（jhead）的 `outlineLvl` 由**上一卷科判队列**的 `min(level)-1` 决定——T1585 各卷内容里没有 head 落点，整卷科判（level 3–6）都攒到**下一卷 jhead**才落地（如卷 3 前有 `二、隨標廣釋` level=3 → 卷第三 outlineLvl=2＝第三层；卷 2 附近队列最低 level=1 才显「正常」）。队列化修（上一条）之前是单条覆盖，由队列**最后一条**定级（卷 3 会落到第 6 层）——两种口径都是错的，根因同一处
  - 修法（`render_docx.py` mulu 分支 + `_attach_mulu`/`_flush_pending_mulus`）：空「卷」标记以 `{"level": 1, "text": ""}` 入队＝**只参与级别计算、不挂书签**；未落地的空标记不记「mulu 未落地」（本身无书签可丢）；其它空标记（`type != "卷"`）照旧跳过
  - 实测（`outlineLvl`）：T1585 卷 1–10 + 后序**全为 0**（修前：卷1 无、卷2=0、卷3=2、卷4 无、卷5/6=5、卷7 无、卷8=3、卷9=4、卷10=1）；T0682（卷标记**带文字**「上/中/下」）与 T0099 层级不变；B0157 书签总数 403 不变、卷题仍 L0；X0767（空 juan、无 jhead 特例）无异常；全档无空名书签
  - 测试：`test_docx.TestHeadCbTypeDocx` +4（卷标记保卷题顶层/卷标记单独入队无书签/空非卷型仍忽略/未落地不报告）；全量 1349 OK
  - 文档：`主题与样式.md`（标题分级节补空「卷」标记口径）
  - 影响：`render_docx` 在 `_FP_IMPL_MODULES` ⇒ 指纹失效同上一条，合并一次
- [x] **已完成 v0.95 发版**（2026-10-21 打包，2026-10-22 发布）
  - 提交 `ba2e4e9`（版本号 0.94 → 0.95）＋ 标签 `v0.95` ＋ GitHub Release（附件 `CBETA-XML2PDF-v0.95-win64.zip`，约 140MB）
  - 打包：staging 目录 `%TEMP%\opencode\rel095\`（`presets/` 快照 ＋ `relnotes.md` ＋ `zipit.py`）；`CBETA-XML2PDF.spec` 的 presets 路径指向 `rel095/presets`（该 spec 被 `.gitignore` 排除，不入库）
  - 内置 `presets/config.user.json` 取仓库内清洗版（不含本机路径；v0.94 误带本机基线路径，本次修正）
  - 冒烟：打包产物离屏启动 15 秒存活正常
  - 影响：版本号参与校验指纹 `_impl_digest` ⇒ 已存校验指纹一次性失效（下轮全库重验）
- [x] **已完成 上游 cbeta-fetch 升级到 v0.2.0 并同步**（2026-10-21）
  - 上游 2026-10-21 18:40 发布 v0.2.0（commit `817d2070d5b502a860a4fe531607572d68a3dfe7`）：TLS 按主机预选（cbdata 只清 `VERIFY_X509_STRICT`）、分块流式下载 ＋ `Content-Length` 完整性校验、原子解压（同名 basename 整单失败）
  - xml2pdf：`pycbeta/_vendor/cbeta_fetch.py` 与 `pycbeta/_vendor/SOURCE.txt` 同步为 0.2.0（sha256 `353a6004984815e5afe2923fc59432ef9f7a7d8b043ad8d10bb294976fd5a2c7`，与上游工作区、publish 副本三份一致）
  - 本仓 `fetch.py:273` 的「unverified SSL」注释已随本次订正（当时写的是 0.1.2 回退口径「已知待改项」；2026-10-22 复核发现该「待改项」已被 0.2.0 做掉，注释已再订正为与 0.2.0 一致口径——TLS 按主机预选＋流式＋长度校验都在共享层，未提交）
  - 影响：`_vendor` 不在 `_FP_IMPL_MODULES` ⇒ 不触发校验指纹失效
- [x] **已完成 全库代码审核（2026-10-21）**
  - 范围：`pycbeta/` 全包（30 个模块）＋ `test/` ＋ 根级脚本。方法：危险模式全量扫描（`eval`/`exec`/`subprocess`/zip/XML 解析/临时文件/宽 `except`/线程/路径拼接/文件编码）＋ 精读网络与写盘路径（`_vendor/cbeta_fetch.py`、`fetch.py`、`verify.py`（抽取与指纹段）、`update_data.py`、`figures.py`、`annotate.py`、`theme.py`（配置与预设段）、`gui/panel.py`、`gui/__main__.py`、`render_pdf.py`、`render_docx.py`（转义段）、`parser.py`、`merge.py`）＋ 两处可复现实验（属性注入、截断响应）
  - 当时未逐行读完：`render_docx.py`、`verify.py`、`theme.py`、`cli.py`、`gui/css_editor.py`（按风险点抽样；于 2026-10-22 第二轮全部补成逐行读完，见下）
  - 结论：3 项高危（HTML/EPUB 属性引号未转义、cbdata 证书失败回退不校验上下文、流式下载无长度校验）＋ 4 项中危（配置与预设写盘非原子、取消转换留半成品产物、LibreOffice 转换无超时、lxml 默认解析器未禁实体）＋ 低危（GUI 宽 `except` 吞异常、过期注释、重复语句）
  - 收敛：后两项高危已由上游 v0.2.0（commit `817d207`）修掉并同步两仓（见下两条「已完成」）；余下高危一项、中危四项待做
  - 第二轮（2026-10-22）全文补审＋逐条核对后：新增待做高危五项、中危六项、低危五批；旧条目的行号/数量按实码订正（见下与各条目内 2026-10-22 标注）
- [x] **已完成 全库代码审核第二轮：全文补审＋核对各条目（2026-10-22）**
  - 范围与方法：第一轮只抽样的五个文件逐行读完——`render_docx.py`（3004 行）、`verify.py`（3328 行）、`theme.py`（1554 行）、`cli.py`（1679 行）、`gui/css_editor.py`（2797 行）；并补 `gui/panel.py`（3262 行）、`gui/__main__.py`（1488 行）、`update_data.py`、`render_pdf.py`（861 行）全文；第一轮已精读的 `render_html.py`、`render_epub.py`、`parser.py`、`filename.py`、`figures.py`、`names.py` 本轮通读核对；另补读 `fetch.py`（994 行）、`annotate.py`（593）、`fonts.py`（667）、`juan.py`（315）、`merge.py`（263）、`report.py`（362）、`render_md.py`（439）、`render_txt.py`（426）、`simplify.py`（136）、`model.py`（122）、`gaiji.py`（35）——至此 `pycbeta/` 生产模块全部全文读过。方法：五个后台只读审核分片负责，重大条目逐条由本会话亲手抽核或复现
  - 复现（本会话亲手跑）：三条新增「高」全部实测——① theme 字体名注入走真实入口 `Theme.docx_run`，输出 `<w:rFonts w:ascii="x"/><w:color w:val="FF0000" …/>`（属性被闭合并可夹带任意 rPr 子元素）；② `_subst_vars` 变量环 8 秒不收敛（顺带实测：该循环持有的全局锁会连解释器退出阶段一起拖死）；③ run.json 替换模板产物为非法 JSON（`Invalid \escape`）
  - 核对订正的旧记录：高危一属性上下文 5 处 ⇒ 实为 15 处（且 `:710` 完全未转义）；`render_docx.py` `_attr` 行号 `:488` ⇒ `:481-488`；`render_epub.py` `sax.escape` 现有用途全在文本节点（非现成漏洞，属未来属位扩展的口径约束）；`gui/panel.py` 宽 `except` 17 ⇒ 22、`gui/__main__.py`「20 余处」⇒ 28；`render_pdf.py` 子进程调用点补第 4 处 `:833`（prince）；宽 `except` 全包实数 186 处；`parser.py:90-91` 重复语句仍在
  - 干净面（记录在案免复查）：`filename.sanitize`（非法字符全角化＋保留名＋200 字上限）与 `figures.split_graphic_url`（只取末段）确保作品 ID→文件名、图片名无路径穿越通道；`theme.py` 全量正则无灾难性回溯；`render_pdf.py` DocBuilder 拼接只有两个文件路径（Windows 文件名禁 `"`，现口径免疫）；`verify.py` 指纹为纯计算、zip 成员名从不参与文件系统路径；生产代码无 `eval`/`exec`/`shell=True`/`os.system`/`pickle`/`yaml.load`；「远程配置包」之外无外部输入直接驱动路径的通道；`juan.py` 卷号有 `_MAX_JUAN` 上限、milestone 解析带守护；`report.py` 纯内存收集不落盘；`gaiji.py:30 pua()` 全仓无调用点（死代码）
  - 产物：新增待做高危四~八、中危五~十一、低危二~七；中危一写盘点清单补全、中危二补取消残留清单、中危三补 prince／COM／逐后端降级
- [x] **已完成 全库代码审核第三轮：核心解析与未审区域（2026-10-22）**
  - 范围：`parser.py` 全文（532 行，此前只读片段——IR 构建、校勘区间 `_wrap_corr`、跨卷星号抑制 `_scan_primary_vols`、`_backfill` 逐行核对）；根级 `CBETA-XML2PDF.spec`、`requirements.txt`、`run.json`、`.gitignore`；`test/run_tests.py`、`test/merge_cbreader.py`、`test/verify_text.py` 全文；测试基座 `pycbeta/tests/_data.py`、`test_zzz_repo_hygiene.py`；并核对 122 条跳过用例的构成
  - 结果：无新增高/中危。解析层与文档口径一致（milestone 数值有守护、校勘区间未配对宁漏不误、星号抑制按注主锚卷号、注释回填只作用于 body 的 NoteRef）；未发现新的路径、注入或资源面
  - 观察（不立项）：`parser._scan_primary_vols` 用正则扫原文，若注释/CDATA 内出现 `<milestone>`/`nkr_note_` 字样会误判卷界（只影响跨卷星号抑制）；`test/verify_text.py` 的比对循环与 CLI 同款（开发脚本，实施长度门时需同步，已并入长度门条目）；`test/run_tests.py:168/223` 的 `total` 从未累加（汇总恒显示 0 项，已并入低危七）
  - 跳过用例构成：122 条全部为环境/语料门控（`requires_data` 无外部 CBETA 电子书库、缺 `pywin32`、认不到可选样式表、单文件直跑无基线、`test_zzz_repo_hygiene` 空基线），非失败、非屏蔽缺陷
  - 打包配置：`.spec` 的 presets 源指向 `%TEMP%\opencode\rel095\presets`（本机发版 staging），发版前必须手改；`.spec` 被 `.gitignore` 排除，与 v0.95 发版记录一致
- [x] **已完成 审核批 1（快修）实施（2026-10-22）**
  - 修复：高危六（`theme._subst_vars` 环/上限）、高危七（`theme._replace_json_string_slot` 改用函数替换）、中危六（`gui/__main__.parse_produced_paths` 前缀校验，调用点传 `out_dir`）、中危五第一批（`update_data.load_sources` 拒 `..`/盘符；`fetch._catalog_dest` 只收纯文件名，两落盘点改用）、低危三第一批（`cli._print_safe` 替换 3 处＋`load_theme` 编码提示）、低危七第一批（`fonts._scan` 逐文件容错；`test/run_tests.py` 计数）
  - 新增测试：`pycbeta/tests/test_audit_fixes.py`（11 项，覆盖上述全部修法）
  - 回归：全量 `python -m unittest discover -s pycbeta/tests -q -t .` = **1363 OK（skipped=122）**
  - 指纹：改 `theme` 在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效（攒批做完统一重验，不单独 bump 版本号）
  - 未做（留后续批次）：中危五剩余 `os.replace` 逐项边界、低危三剩余 html 定位 glob、低危七剩余 `annotate.rt_css_rule`（记录不立项）
- [x] **已完成 审核批 2（转义统一）实施（2026-10-22）**
  - 修复：高危一（`render_html` 新增 `_attr`，属性位全部切换，补漏 `:699/:702` 的 `lg` 类名与 `:710` 缩进）；高危四（`render_docx` 图片名 `_attr`）；高危五（`theme` 新增 `_xml_attr`，`docx_run` 字体名转义）；低危五第一批（`render_docx` 字体名全部 `_attr`、`:725` 改函数替换消除 bad escape、`footnoteSeparator` 数值兜底＋钳制）
  - 新增测试：`test_audit_fixes.py` 追加 5 项（HTML helper／`lg` 类名＋缩进／`p` 的 style／theme `docx_run`／docx `_attr`），合计 16 项
  - 回归：全量 `python -m unittest discover -s pycbeta/tests -q -t .` = **1368 OK（skipped=122）**
  - 指纹：改 `render_html`/`render_docx`/`theme` 均在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效（与批 1 合并，攒批统一重验）
  - 说明：`render_epub` 未改（`sax.escape` 现用途全在文本节点）；高危四在 Windows 上属端到端不可达（文件名禁 `"`），按硬化修复
  - 未做（留后续批次）：低危五剩余 `_strip_quote_text` 原地改树与分页/估高二次方开销
- [x] **已完成 审核批 3（事务与取消）实施（2026-10-22）**
  - 修复：中危一（新增 `pycbeta/atomic.py`；`gui/panel.py` 5 处、`gui/css_editor.py` 2 处、`theme.set_run_slot` 全部改原子写；soffice 产物改 `os.replace`）；中危二第一批（`_kill_process_tree` 以 `taskkill /T /F` 终止桥进程及子孙；`MainWindow.closeEvent` 转换中先取消并等待，未收尾则阻止关窗）；中危三第一批（soffice 600 秒、prince 300 秒超时；后端循环逐 `except` 降级；`timeoutSeconds` 兜底与钳制）
  - 新增测试：`test_audit_fixes.py` 追加 5 项（原子写往返/失败清理、后端降级、超时兜底、进程树终止），合计 21 项
  - 回归：全量 `python -m unittest discover -s pycbeta/tests -q -t .` = **1373 OK（skipped=122）**
  - 指纹：改 `theme`/`render_pdf` ⇒ 已存校验指纹整体失效（与批 1/2 合并，攒批统一重验）
  - 未做（留后续批次）：产物类原子写（docx/html/epub/md/txt/pdf/compare/merged）、取消检查点与残留临时目录清理、取消行终态文案、COM 判活看门狗
  - 备注：工作区 `pycbeta/_vendor` 已被另一会话同步到上游 **v0.2.1**（`d28fc5d`，解压原子性与同名策略），非本批改动、未提交
- [x] **已完成 审核批 4（校验健壮性）实施（2026-10-22）**
  - 修复：中危四（`parser.py`/`verify.py` 两处 `etree.parse` 改 `resolve_entities=False`）；中危七（试算循环 `_xt` 兜底、epub/docx 合并兜底、7 处解码 `errors="replace"`；并加「读取失败的 trial 不判 OK、不参与 best、全部不可读返回 fail」守卫）；中危八（按 `_compare_`/`_official_merged_` 文件名排除自产产物；`isfile`/`getsize` 竞态兜底）；低危四（BOM 剥离、`merge_docx` 全部 `with`、自动取基线 try、`cfg_int` 兜底）
  - 新增测试 5 项（实体不展开、产物排除、BOM+cfg_int、损坏基线降级），合计 26 项
  - 回归：全量 **1378 OK（skipped=122）**
  - 指纹：改 `parser`/`verify` ⇒ 校验指纹整体失效
  - 备注：实现中发现并堵住「空基线 + 短文本 ⇒ extra ≤ 阈值误判 OK」的假绿路径
- [x] **已完成 审核批 5（数值与主题）实施（2026-10-22）**
  - 修复：中危九（theme 11 处数值正则收紧为 `\d*\.?\d+`，坏值走既有告警分支，`.5em` 仍解析）；低危二（`render_docx.py`/`render_html.py` 三处 milestone `int()` 加守护；`<space quantity>` 钳制 1–100）
  - 新增测试 2 项（主题坏值、渲染数值守护），合计 28 项
  - 回归：全量 **1380 OK（skipped=122）**
  - 指纹：改 `theme`/`render_docx`/`render_html` ⇒ 校验指纹整体失效
- [x] **已完成 审核批 6（GUI 体验）实施（2026-10-22）**
  - 修复：高危八（`DataUpdateDialog`/`SourceDialog` 增加 `closeEvent`，更新运行中阻止关窗并用状态行提示；`css_editor.closeEvent` 的 `wait` 超时改为阻止关闭）；中危十第一批（校验目录统计 300ms 防抖；清理确认框明示默认根整树删除；读自定义校验根失败中止清理）；中危十一（四个渲染器缺省产物名过 `filename.sanitize`）
  - 新增测试：`test_audit_fixes.py` 追加 3 项（缺省产物名、closeEvent 守卫、防抖接线）；`test_gui` 的「校验行跟随输出」用例改为等待防抖（`QTest.qWait(400)`）
  - 回归：全量 **1383 OK（skipped=122）**
  - 指纹：改 `render_docx`/`render_md`/`render_txt`/`render_epub` ⇒ 校验指纹整体失效；GUI 件不触
  - 过程记录：关窗守卫最初用模态 `QMessageBox`，导致 offscreen 测试用 Mock worker（`isRunning()` 为真值）关窗时卡死；已改为非模态状态行提示
  - 未做（留后续）：`clean_verify_dirs` 后台化、`css_editor` 导出后台化
- [x] **已完成 审核零碎收尾（2026-10-22）**
  - 修复：低危三（html 定位按 `work.id` 前缀筛选）、低危五（`_strip_quote_text` 渲染后还原、智能合页估高增量、分页串 join）、低危六（删预设清路径、临时目录归 `self._tmp` 并关窗清理、`save_current` 捕获、`Path.as_uri()`、`pdf_zoom` 双端钳制、两处读取改 `with`）、低危七（`rt_css_rule` 过滤补 `<`/`>`/换行）、中危二部分（取消时跳过校验、取消行终态「已取消」）
  - 新增测试 3 项（引号还原/复用一致、`rt_css_rule` 过滤、取消行文案），合计 34 项
  - 回归：全量 **1386 OK（skipped=122）**
  - 指纹：改 `render_docx`/`render_pdf`/`annotate`/`render_html`/`render_epub` ⇒ 指纹整体失效（`cli`/GUI 不触）
  - 未做：中危二硬杀临时目录清理（需与并发实例区分）、中危三 COM 看门狗、中危十后台化两项、产物原子写
- [x] **已完成 审核批 7（校验长度门）实施（2026-10-23）**
  - 修复：`verify.py` 长度门 + 全截断兜底 + 报告分支；`cli.py` 同门与全截断输出；`test/verify_text.py` 同步；`gui/__main__.py` 关窗超时「强制退出」
  - 现场：T1509 epub 由数小时（栈确认 `difflib.find_longest_match`）降至 **8.5–10.3 秒**（两次实测），结果 `[epub=OK(0/0)]`（html 链 860 字差截断，txt_notes 链 0/0）
  - 回归：**1397 OK（skipped=122）**；新增 11 项单测（8 项 verify 门/报告/集成 + 1 项 CLI 全截断 + 2 项截断仅注释/正文差异）
  - 特别验证：截断时补正文旁路（O(n) 判等），正文全对仅注释差异仍标 `notes_only`/`【仅仅注释差异】`；T1509 html 链 860 字差即属此类
  - 指纹：改 `verify.py` ⇒ 校验指纹整体失效（`cli` 不触）
  - 剩余：等长超长对仍需分段/按卷比对（搁置）
- [x] **已完成 高危一** HTML/EPUB 属性引号未转义（可复现；2026-10-22 修复）
  - 位置（2026-10-22 补全清单，此前只列 5 处）：`render_html.py:52-53`（`_esc`＝`html.escape(s, quote=False)`，不转义 `"`）。属性上下文：`:255`、`:366`、`:527-528`、`:535`/`:538`/`:539`、`:630`、`:647`、`:663`、`:667`、`:700`、`:702`（`lg` 的 `cls`，补漏）、`:710`（`lg` 的 `text-indent`，补漏且原为完全未转义）、`:796`、`:802`、`:840`、`:893`、`:941-942`、`:945`、`:950`、`:956`/`:958`；`render_epub.py:22`（`sax.escape` 同样不转义引号；现用途全在文本节点，无属性位）
  - 实证：构造 `style='color:red" onmouseover="alert(1)'` 渲染出 `<p class="" style="color:red" onmouseover="alert(1)">`（属性被撑破）；`type='x" class="evil'` 出重复 `class` 属性
  - 现状数据：`cbeta_xml` 全库 229 个官方 XML 中含 `&quot;` 的 0 个（含 `style="…"` 属性的 177 个）⇒ 当前语料不触发，属硬化缺口而非正在发生的漏洞
  - 修复（2026-10-22）：`render_html` 新增 `_attr()`（`html.escape(quote=True)`），上述属性位全部切换；`_esc` 仅保留文本节点；单测 `test_audit_fixes.TestHtmlAttrEscaping`（helper、`lg` 类名/缩进、`p` 的 style）
  - 代价：改 `render_html`/`render_epub` 在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效（攒批统一重验）
- [x] **已完成 高危二** cbdata 证书失败回退不校验上下文（上游 v0.2.0 已修，2026-10-21 同步两仓）
  - 原问题：`_vendor/cbeta_fetch.py` 的 `_open()` 捕获证书错误后改用不校验上下文重试一次 ⇒ cbdata 官方电子书与 scope-selector JSON 下载可被中间人替换
  - 上游修法（commit `817d207`）：改为按主机预选上下文——`_context_for(url)`（`:145-156`）对 cbdata 主机用 `ssl.create_default_context()` 且只清 `VERIFY_X509_STRICT`（缺 Subject Key Identifier 即可通过），证书链与主机名照常校验；其余主机维持默认上下文；不做异常驱动的降级；`getattr(ssl, "VERIFY_X509_STRICT", 0)` 兼容 Python 3.12 及更早
  - 本仓复核：`_vendor/cbeta_fetch.py:145-168` 落点正确（无 `ssl._create_unverified_context()` 残留）；两仓 vendor 与 `SOURCE.txt` 均为 0.2.0 / `817d207` / sha256 `353a6004…`
  - 影响：改 vendor 不触及 `_FP_IMPL_MODULES` ⇒ 不影响校验指纹
- [x] **已完成 高危三** 流式下载无完整性校验（上游 v0.2.0 已修，2026-10-21 同步两仓）
  - 原问题：`download`/`fetch_if_changed` 的 `shutil.copyfileobj` 后直接 `os.replace`，未比对 `Content-Length` ⇒ 截断响应被当作完整文件落盘（实证：声明 100、实发 10，`copyfileobj` 不抛异常；旧写法 `r.read()` 会抛 `IncompleteRead`）
  - 上游修法（commit `817d207`）：`_copy_stream()` 边写边计字节（`:192-201`），`_check_length()` 比对 `Content-Length`，不符抛 `IOError`（`:204-208`），三处写盘点均调用（`:229-230`、`:240-241`、`:311-312`）⇒ 短读按失败重试
  - 影响：改 vendor 不触及 `_FP_IMPL_MODULES` ⇒ 不影响校验指纹
- [x] **已完成 高危四** DOCX 图片名属性注入（2026-10-22 修复）
  - 位置：`render_docx.py:1820`（`nm = _x(base)`，`_x` 在 `:476-478` 只转义 `&<>`）写进 `wp:docPr @name` 与 `pic:cNvPr @name`（同一 f-string 组）；`base` 来自 XML `<graphic url>` 的 basename
  - 触发：XML 写 `url="x&quot;y.gif"` ⇒ 属性值解码出 `"` ⇒ document.xml 属性提前闭合 ⇒ 非法 OOXML，Word 打不开、回读校验直接失败。与 v0.94 修书签名（`_attr` `:481-488`）同族；注意 Windows 文件名禁 `"`/`<`/`>`，该图片文件在本机不可能存在 ⇒ 端到端不可达，属硬化缺口（代码路径仍按属性位修）
  - 现状数据：官方 229 XML 不含 `&quot;` ⇒ 语料不触发
  - 修复（2026-10-22）：`nm` 改走 `_attr`；单测 `test_audit_fixes.TestDocxAttrEscaping`
  - 代价：改 `render_docx` 在 `_FP_IMPL_MODULES` ⇒ 校验指纹整体失效
- [x] **已完成 高危五** 预设 CSS 字体名直拼进 OOXML rPr（已实测复现；2026-10-22 修复）
  - 位置：`theme.py:1448-1449`（`docx_run` 内 `f'<w:rFonts w:ascii="{latin_name}" w:eastAsia="{east}" w:hAnsi="{latin_name}"/>'` 无任何 XML 转义；`:1436-1440` 的 `strip('"')`/`strip("'")` 只剥首尾，值中部引号原样保留）
  - 实证（2026-10-22 本会话复跑）：CSS `body { font-family: x"/><w:color w:val="FF0000; }` ⇒ `docx_run("body")` 输出 `<w:rFonts w:ascii="x"/><w:color w:val="FF0000" …/>`，属性被闭合、可夹带任意 rPr 子元素
  - 触发：复制/下载他人预设 CSS（presets 可流通，属预期内任意文本）⇒ DOCX 损坏或被夹带格式定义
  - 修复（2026-10-22）：新增 `theme._xml_attr`（`& < > "`），`docx_run` 的 `w:ascii`/`w:eastAsia`/`w:hAnsi` 全部过转义；单测 `test_audit_fixes.TestThemeFontEscaping`
  - 代价：改 `theme` ⇒ 校验指纹整体失效
- [x] **已完成 高危六** `var()` 变量环使 CSS 解析永久挂死（已实测复现；2026-10-22 修复）
  - 位置：`theme.py:610-621`（`_subst_vars`：`while prev != out: out = _VAR_RE.sub(rep, out)`，无迭代上限、无环检测）
  - 实证（2026-10-22 本会话复跑）：CSS `:root{--x:var(--y);--y:var(--x)}` ⇒ `_subst_vars` 8 秒不收敛；CLI/GUI 预览线程都会被冻住 ⇒ 一次坏 CSS 冻结全流程
  - 修复（2026-10-22）：`_subst_vars` 增加已访问值集合与 32 次上限，环/超长链在有限次内停止代入；单测 `test_audit_fixes.TestThemeVarSubst`（环收敛＋正常链）
  - 代价：改 `theme` ⇒ 校验指纹整体失效（已接受；攒批统一重验）
- [x] **已完成 高危七** run.json 文本替换模板把反斜杠减半（已实测复现；2026-10-22 修复）
  - 位置：`theme.py:998-1001`（`rep = r"\1" + json.dumps(value, …)` 后 `pat.subn(rep, …)`——替换模板按正则转义规则处理，`json.dumps` 产出的 `\\` 减半成单个 `\` 落盘）
  - 实证（2026-10-22 本会话复跑）：`_replace_json_string_slot(… "E:\\dev\\cbeta\\my n.json" …)` 写出 `"E:\dev\cbeta\my n.json"`，属非法 JSON，重读报 `Invalid \escape`
  - 触发：GUI「设为默认」在预设跨盘符时走 `slot = 路径` 兜底（`gui/panel.py:2038-2039`）喂绝对路径——Windows 常态即可命中；run.json 损坏由 `theme.py:1031` `.bad` 改名兜底但槽位丢失
  - 修复（2026-10-22）：`pat.subn` 改用函数替换（`lambda`/`_repl`），绕开模板转义层；单测 `test_audit_fixes.TestRunJsonSlotReplace`
  - 代价：改 `theme` ⇒ 校验指纹整体失效（已接受）
- [x] **已完成 高危八** 更新对话框线程生命周期：运行中关窗 qFatal 崩溃（2026-10-22 修复）
  - 位置：`gui/panel.py`（`DataUpdateWorker` / `EbookUpdateWorker` 由对话框持有但无 `closeEvent` 兜底，“关闭”按钮置灰拦不住标题栏 X）；`gui/css_editor.py`（`closeEvent wait(2000)` 超时后仍放行）
  - 触发：点「开始更新」或「更新XML」后在收尾前按 X 关窗 ⇒ `QThread destroyed while running` qFatal，整个进程崩溃；样张重渲超 2 秒时同样崩
  - 修复（2026-10-22）：`DataUpdateDialog` 与 `SourceDialog` 增加 `closeEvent`——更新运行中阻止关窗并在状态行提示（**不用模态框**，避免测试/脚本卡死）；`css_editor.closeEvent` 的 `wait(2000)` 超时改为阻止关闭并提示
  - 代价：不触及 `_FP_IMPL_MODULES` ⇒ 不影响校验指纹
  - 验收：单测 `test_audit_fixes.TestGuiLifecycleGuards`（三处 closeEvent 存在）；手工复演 X 关窗
- [x] **已完成 中危一** 配置与预设写盘非原子（2026-10-22 修复；产物类剩余）
  - 位置（2026-10-22 补全清单；无 `os.replace` 的直写点）：`gui/panel.py` `open(path, "w")` 共 8 处——`:278-280`（`save_current` 写 `presets/config.user.json`）、`:329-331`（`save_config_preset`）、`:357-359`（`set_config_preset_theme`）、`:415-418`/`:431-435`/`:531-534`（`mkstemp` 临时件、调用方删，可接受）、`:2556-2558`（`clear_xml_dir` 写预设）、`:3230-3232`（`SourceDialog.accept` 有预设分支）；间接经 `save_current`：`:2560`/`:3237`。`gui/css_editor.py:259-260`、`:1896-1897`。`theme.py:1021-1046`（run.json 直写，`:1031` 失败时 `.bad` 改名）。产物类同样非原子：`verify.py:2072-2077`/`:2251-2259`（compare 文本对）、`:1003-1013`（merged docx）、`render_docx.py:1238`/`:1308`、`render_epub.py:103`、`render_md.py:75`、`render_txt.py:81`、`merge.py:228`（合册 XML）、`render_pdf.py:604`/`:635`（HTML 交付物）、`render_pdf.py:281-283`（先 `os.remove` 后 `os.rename`，崩溃窗口丢旧文件）
  - 影响：写一半崩溃或磁盘满 ⇒ 半截 JSON/CSS/产物；GUI 配置损坏起不来；验证产物残卷可能被下轮当输入误读
  - 修复（2026-10-22）：新增 `pycbeta/atomic.py`（同目录临时文件＋`os.replace`），上述配置/预设/run.json 写盘点全部改用；`render_pdf.py:281-283` 改 `os.replace`；单测 `test_audit_fixes.TestAtomicWrite`（内容往返、覆盖、失败清理临时文件）
  - 剩余：各格式产物文件与 verify 比对文件的原子写（docx/html/epub/md/txt/pdf/compare/merged），归后续批次（与中危二一并）
  - 代价：改 `verify`/`theme` ⇒ 校验指纹整体失效（`theme` 本批已改）
- [ ] **待做 中危二** 取消转换留下半成品产物
  - 位置：`gui/__main__.py:274-280`（`cancel()` → `self._proc.terminate()`，Windows 为硬杀）；`Popen` 无 `timeout`（`:767-770`，引擎挂死则该行永久卡住只能手动取消）；无 `closeEvent`（全文件检索 0 命中）——转换中直接关窗 ⇒ worker 线程与桥子进程孤儿化继续写盘
  - 硬杀后残留清单（2026-10-22 补）：输出目录 `cli.py:339`（pdf 目标名）、`:399`（html 中转）、`:412`/`:415`（html 目标）、`:355-356`/`:404-406`（引擎标签改名）、`:366-367`/`:371`（docx 副本）；临时目录 `cli.py:346`（`xml2pdf-pdfdocx-`，硬杀后 finally 不执行）；验证子产物 `cli.py:1517-1520`/`:1619-1620`/`:1640-1642`；GUI 行内落盘点取消后仍执行：`gui/__main__.py:477-478`（合并转换报告）、`:504-505`（行验证报告）、`:540-543`（report.json）；`verify_one`（`:439-455`）与 `_resolve`（`:620-672`）无取消检查点；取消行终态记「失败：…」而非「已取消」（`:551-553`）
  - 影响：正在写的 docx/html/epub 留在输出目录，且看起来是完整文件；外部引擎与 COM 进程成孤儿
  - 已修部分（2026-10-22）：新增 `_kill_process_tree`（Windows `taskkill /T /F`，失败回退 `terminate`）替换硬杀；`MainWindow.closeEvent` 转换中先取消并 `wait(10000)`，未收尾则阻止关窗；取消时跳过校验（`if ok and verify_on and not self._cancel`）；取消行终态改「已取消」；单测 `test_audit_fixes.TestKillProcessTree`/`TestRowOutcomeCancel`
  - 剩余：`Popen` 超时（故意不做固定上限，长书合法耗时长）、硬杀后的临时目录清理（需与并发实例区分，待设计）、产物原子写（归中危一剩余）
- [ ] **待做 中危三** PDF 外部转换超时与降级缺口
  - 位置（2026-10-22 补全）：`render_pdf.py:276-277`（soffice 无 `timeout`）、`:833`（prince 无 `timeout`，原记录漏列）、`:361`（docbuilder 180 秒）、`:331`（外部引擎 120 秒，但 `:330` `int(cfg.get("timeoutSeconds"))` 无兜底，配置坏值直接 ValueError 抛穿）；COM 区 `:50`/`:126-229`（`_COM_LOCK` 持锁期间无看门狗，Word/WPS 弹出模态即全进程冻结）；`:401-411`（`docx_to_pdf` 后端循环无逐后端 `try`，soffice `check=True` 的 `CalledProcessError` 与外部引擎超时越过「逐后端降级」设计直接中断全链）
  - 影响：soffice/prince 挂起时该行任务永久卡住；单个后端抛错则整链中断而非降级到下一个后端
  - 已修部分（2026-10-22）：soffice 加 600 秒超时、prince 加 300 秒超时；后端循环逐 `except` 记 errors 继续；`timeoutSeconds` 走 `_timeout_seconds`（坏值回 120、钳制 1–3600）；soffice 产物改 `os.replace`；单测 `test_audit_fixes.TestPdfBackendFallback`/`TestTimeoutGuard`
  - 剩余：COM 区判活看门狗（Word/WPS 模态）
- [x] **已完成 中危四** lxml 默认解析器未禁实体（2026-10-22 修复）
  - 位置：`parser.py:62`（`etree.parse(xml_fn)`，默认 `resolve_entities=True`）、`verify.py:1399`（官方基线直读同口径）；对照 `merge.py:194` 已用 `resolve_entities=False`（2026-10-22 复核：生产代码 `etree.parse` 调用点全查就这三处，范围与此条一致）
  - 影响：异常或恶意 XML 可触发实体膨胀（billion laughs）耗尽内存；实体内容可能进入产物
  - 修复（2026-10-22）：两处改用 `etree.XMLParser(resolve_entities=False)`
  - 代价：改 `parser`/`verify` 在 `_FP_IMPL_MODULES` ⇒ 已存校验指纹整体失效
  - 验收：单测 `test_audit_fixes.TestEntitySafety`（外部实体不展开、不读本地文件）
- [ ] **待做 中危五** remote_sources.json 的 `dest` 不拒 `..` ⇒ 配置可驱动写仓外任意文件
  - 位置：`update_data.py:51`（`dest` 按 `/` 拆段仅滤空段，`..`/盘符/绝对路径成分原样通过）、`:199`（`os.path.join(base, *src["dest"])`）、`:249`（`os.replace(tmp, dest)` 直落盘）
  - 触发：分发出去的「配置包」被替换为含 `dest: "../../xx"` 的 remote_sources.json ⇒ 更新内容（ttf／文本／JSON）覆盖仓库外任意同名文件
  - 另：`:202-258` 循环体内 `os.replace` 无逐项异常边界，单项被占用（字体验证程序/资源管理器锁定）时异常冒泡中断全部剩余更新项
  - 同类（2026-10-22 补读）：`fetch.py:437`/`:899` 把 catalog 记录的 `rec["file"]` 直接 `os.path.join(wdir, …)`——`cbeta/data/sutra_mapping.txt` 同属仓内数据文件，若被替换同样可写出 work 目录；修法一并校验文件名不含分隔符与 `..`
  - 已修部分（2026-10-22）：`load_sources` 解析时拒绝 `..`/盘符成分；新增 `fetch._catalog_dest` 只接受纯文件名（两个落盘点均改用）；单测 `test_audit_fixes.TestRemoteDestGuard`/`TestCatalogDest`
  - 剩余：`:202-258` 的 `os.replace` 逐项异常边界（单项被锁不中断其余更新项）
  - 代价：不触及 `_FP_IMPL_MODULES` ⇒ 不影响校验指纹
  - 验收：恶意 `dest` 单测拒绝并报错；正规 8 源照常更新
- [x] **已完成 中危六** GUI 产物收编只凭「行尾 `→`＋文件存在」（2026-10-22 修复）
  - 位置：`gui/__main__.py:51-60`（`parse_produced_paths` 正则＋`os.path.isfile` 即收编）、消费点 `:781`、文件列 `:546-550`、单击打开 `:1343-1362`
  - 触发：渲染核心或第三方引擎在 stdout/stderr 打印任意 `xxx -> 已存在路径` ⇒ 该文件被当作本轮产物展示，用户单击即用系统默认程序打开别的文件
  - 修复（2026-10-22）：`parse_produced_paths(log, within=…)` 增加前缀校验（normcase 后必须位于本轮输出目录之下），调用点传 `out_dir`；未传 `within` 时保持旧行为（既有调用/单测不变）；单测 `test_audit_fixes.TestProducedPathsWithin`
  - 代价：不触及 `_FP_IMPL_MODULES` ⇒ 不影响校验指纹
- [x] **已完成 中危七** 校验抽取单点失败不降级（损坏基线抛穿整轮；2026-10-22 修复）
  - 位置：`verify.py:2158`/`2171`/`2179`/`2190`/`2203`/`2214`/`2222`（基线试算循环内 `_extract_epub_parts(_p)[0]`、`extract_text` 等无逐文件 `try` ⇒ 单个损坏官方件抛穿，链上后续回退基线不再试算）；`:362`/`371`/`418`/`974`/`986`/`989`/`998`（docx/odt 抽取严格 UTF-8 解码无 `errors="replace"`）
  - 修复（2026-10-22）：试算循环加 `_xt` 兜底（读失败记 `error`、返回空文本、继续下一基线）；epub/docx 合并调用同样兜住；7 处 `.decode("utf-8")` 统一 `errors="replace"`；**避免空基线假绿**——带 `error` 的 trial 不判 OK、不参与 best，全部基线不可读时返回 `status=fail` 且缺/多/总为 None（报告显示「读取失败」）
  - 触发：官方基线本地损坏/移动中断 ⇒ 该卷得到失败报告而非中断
  - 代价：改 `verify` ⇒ 校验指纹整体失效
  - 验收：单测 `test_audit_fixes.TestBaselineReadDegrade`（损坏基线不抛穿、不误判通过、报告含「读取失败」）
- [x] **已完成 中危八** 自产验证产物防误采仅目录名一道防线（2026-10-22 修复）
  - 位置：`verify.py:1776-1784`（`"（验证）" in af` 子串是唯一针对自产产物的防线）
  - 触发：库调用方把 `out_root` 指到 `source` 树内不带该子串的目录 ⇒ 上一轮 `*_compare_*`/`*_official_merged_docx` 留在发现范围；`txt_notes` 全局模式 `**/txt/{s}_*.txt` 恰可与输出目录段名 `txt` 命中 ⇒ 拿自产 compare 当基线「自比对假绿」
  - 修复（2026-10-22）：发现时按文件名排除 `_compare_`、`_official_merged_`（不再依赖目录命名）；`isfile`/`getsize` 包 `OSError` 跳过
  - 代价：改 `verify` ⇒ 校验指纹整体失效
  - 验收：单测 `test_audit_fixes.TestOfficialArtifactExclusion`
- [x] **已完成 中危九** 主题数值解析崩溃面（2026-10-22 修复）
  - 位置：`theme.py:1126-1131`/`1139-1147`（`^([\d.]+)…` 过正则即裸 `float()`，无兜底；`body_font_size: "1.2.3pt"` 崩 `apply_page_typography`）、`:1518-1521`（行高 `1.2.3` 先存进 tags，延迟崩于 `docx_para`）
  - 触发：纸张预设 JSON 手工写成非数值 ⇒ 渲染入口直接 ValueError 中断
  - 修复（2026-10-22）：theme 内 11 处数值正则由 `[\d.]+` 收紧为 `\d*\.?\d+`（保留 `.5em` 写法，拒绝 `1.2.3`）；坏值走既有 else/report 分支，不再进 `float()`
  - 代价：改 `theme` ⇒ 校验指纹整体失效
  - 验收：单测 `test_audit_fixes.TestThemeNumericGuard`（坏值不崩、`.5em` 仍解析）
- [ ] **待做 中危十** GUI 删除与统计的卡顿/冻结面
  - 位置：`panel.py`（`_refresh_verify_info` 每个 `textChanged` 同步全树 `os.walk` 统计校验目录大小）；`panel.py`（清理确认框只列 `*（验证）` 类目录名，`clean_verify_dirs` 对默认根是整树 `rmtree` 且在 GUI 线程执行）；`css_editor.py:2715`/`2688-2691`（导出 PDF／DOCX 兜底渲染在 GUI 线程同步起外部引擎，界面冻结数十秒无进度无取消）
  - 另：`panel.py:1949-1952` 读 `source.verify_root` 失败被静默当 None ⇒ 清理范围旁路扩大到默认根整树
  - 已修部分（2026-10-22）：输入变化改 300ms 防抖（`_schedule_verify_info`），刷新按钮仍即时；清理确认框在默认根时明示「将整树删除 {输出}/验证」；读自定义校验根失败改为警告并中止清理
  - 剩余：`clean_verify_dirs` 挪后台线程；`css_editor` 导出（PDF/DOCX）挪后台线程
  - 代价：不触及 `_FP_IMPL_MODULES` ⇒ 不影响校验指纹
  - 验收：单测（防抖方法存在、既有行跟随用例改等待防抖后通过）；大产物目录手测
- [x] **已完成 中危十一** 各渲染器缺省产物名未净化（2026-10-22 修复）
  - 位置：`render_docx.py`（`f"{work.id}.docx"` 与分卷 `f"{work.id}_卷{n}.docx"`）、`render_md.py:73`、`render_txt.py:79`、`render_epub.py:101`（同形 `f"{work.id}.<ext>"`）
  - 触发：CLI/GUI 主路径传 `out_name`（已过 `filename.sanitize`）；库调用/第三方按 `render_work(w, out_dir)` 缺省调用时 `Work.id` 来自 XML `xml:id` 原样 ⇒ 畸形 `xml:id="../../x"` 可写出输出目录外
  - 修复（2026-10-22）：四个渲染器缺省分支统一 `filename.sanitize(...)`（非法字符全角化）
  - 代价：改四个渲染器 ⇒ 校验指纹整体失效
  - 验收：单测 `test_audit_fixes.TestDefaultOutputNames`（`../evil` 产物仍落 `out_dir`）
- [ ] **待做 低危一** 宽 `except Exception` 全包 186 处（2026-10-22 实数）⇒ 失败无痕；建议至少写进转换报告或日志
  - 分布：`verify.py` 46、`gui/__main__.py` 28、`render_pdf.py` 27（其中 COM 区约 21 处属「逐语句不倒下」设计配套，可豁免）、`gui/panel.py` 22（2026-10-22 订正，原记 17）、`cli.py` 15、`gui/css_editor.py` 15、`fonts.py` 12、`annotate.py` 7、`update_data.py`/`fetch.py`/`filename.py` 各 3、`render_docx.py` 2、`theme.py`/`figures.py`/`report.py` 各 1；全包无裸 `except:`
  - 典型吞错实例：`cli.py:1241`（校验比对写盘失败静默置空，报告定位信息缺失）、`verify.py:1853`（配置解析失败静默回工厂默认）、`panel.py:1951`（清理读自选根失败静默回默认根）、`theme.py:592`（字体变量解析失败静默空表，DOCX 字体全回退无提示）、`css_editor.py:948`（解析失败把空表缓存为永久结果，后续字体判断失真）
- [x] **已完成 低危二** 畸形 XML 数值守护（同源一族；2026-10-22 修复）
  - 位置：`render_docx.py:336`/`344`、`render_html.py:110`（`int(n.attrs.get("n"))` 无 `try`——milestone `n` 非数字即 ValueError 中断整笔）；`render_html.py:869-874`（`<space quantity>` 无上限，畸形大值撑爆内存；官方值 1-3）
  - 修复（2026-10-22）：三处 `int()` 加 `try` 回退 `(cur_no or 0)+1`（与 `parser` 同口径）；`<space quantity>` 钳制到 1–100
  - 代价：改 `render_docx`/`render_html` ⇒ 校验指纹整体失效
  - 验收：单测 `test_audit_fixes.TestRenderNumericGuard`（坏 milestone 不崩、空格长度 ≤100）
- [x] **已完成 低危三** CLI 输出编码零碎（2026-10-22 修复）
  - 位置：`cli.py:142`/`270`/`1621`（裸 `print` 无 `UnicodeEncodeError` 回退）；`load_theme` 严格 UTF-8 无捕获；`:1234-1247`（`--verify-only` 下 html 产物定位用全目录 `glob("*.html")` 取首项）
  - 修复（2026-10-22）：`_print_safe`（编码失败回退 GBK replace）替换相关 print；`load_theme` 捕获 `UnicodeDecodeError` 并抛带提示的 `ValueError`；html 定位优先按 `work.id` 前缀筛选，无命中再回退全目录
  - 代价：不触及 `_FP_IMPL_MODULES` ⇒ 不影响校验指纹
  - 验收：单测 `test_audit_fixes.TestLoadThemeEncoding`；GBK 管道冒烟
- [x] **已完成 低危四** verify.py 健壮性零碎（2026-10-22 修复）
  - `:55`：BOM（`\ufeff`）已并入归一化剥离字符类
  - `:973`/`985`：`merge_docx` 全部 `zipfile.ZipFile` 改 `with`（含输出 zip），句柄不再滞留
  - `:1785`：`find_official` 的 `isfile`/`getsize` 竞态已包 `OSError` 跳过
  - `:2129-2142`：自动取基线整块加 `try/except`，失败按现有基线继续（不再整卷记为错误）
  - `:2324-2332`：`cfg_int` 对非数值串回缺省（`0` 仍原样保留）
  - `:420`-`:1012` 整件驻留内存：仅记录，暂不立项
  - 单测：`test_audit_fixes.TestNormalizeAndCfgInt`、`TestOfficialArtifactExclusion`（竞态路径）
  - 代价：改 `verify` ⇒ 校验指纹整体失效（已接受）
- [ ] **待做 低危五** render_docx 配置域与性能零碎（一批）
  - `:948-951`：`notes_marker_font` 用文本转义（`_x`）写 `w:rFonts` 属性位（配置域，值含 `"` 即损坏）；`:694`/`725`/`816`/`2761`/`2866`：字体名原样拼属性，`:725` 还先进 `re.sub` 替换串（值含 `\` 即「bad escape」崩）——均为本机配置/主题来源，默认链不触发
  - `:2671-2673`：`footnoteSeparator` 数值无 `try`（对照 `_series_size_pt` `:975-978` 有兜底）
  - `:2299-2309`：`_strip_quote_text` 原地改树 ⇒ 同一 Work 对象复用渲染（同进程二次渲染/多格式循环）输出不可复现
  - `:2814`/`:385`：分页模式每轮全量拷贝累计字符串＋智能合页每轮全量估高（数千节时秒级到数十秒）
  - 已修部分（2026-10-22）：字体名全部改走 `_attr`（含 `:725` 改用函数替换，顺带消除 bad escape）；`footnoteSeparator` 数值加 `try`＋范围钳制；`_strip_quote_text` 改为渲染后还原（跨首尾调用按节点去重，不把改动留在 IR）；智能合页估高改增量、分页串改列表 join；单测 `test_audit_fixes.TestDocxAttrEscaping`/`TestVerseQuoteRestore`
  - 代价：改 `render_docx` ⇒ 校验指纹整体失效（已接受）
- [x] **已完成 低危六** GUI 与 PDF 链路零碎（2026-10-22 修复）
  - 删除预设后 `_preset_path` 清空（下次保存走「另存」，不再复活刚删文件）
  - `css_editor` 的兜底导出临时目录改到 `self._tmp` 下，关窗统一 `rmtree`（不再累积）
  - `SourceDialog.accept` 无预设分支的 `save_current` 补 `OSError` 捕获
  - `render_pdf` 的 `page.goto` 改用 `Path.as_uri()`；`pdf_zoom` 在 CLI 与渲染入口双重钳制 0.1–2
  - 句柄零碎（`render_html.py:951`、`render_epub.py:136`）：读取改 `with`
  - 代价：`render_pdf` 触指纹；GUI 件不触；验收：单测 `test_audit_fixes.TestPdf*`/`TestDefaultOutputNames`
- [x] **已完成 低危七** 小模块零碎（2026-10-22 修复）
  - `annotate.py:95-111`（`rt_css_rule`）：过滤补剥 `<`/`>`/换行，`</style>` 无法逃逸；单测 `test_audit_fixes.TestRtCssFilter`
  - `fonts.py:223-229`（`_scan`）：逐文件 `try/except` 跳过坏字体（单测 `TestFontScanResilience`）
  - `test/run_tests.py:168/223`：`total` 计数补齐
  - 另记（不立项）：`merge.py` 的 `tree.write` 合册 XML 非原子已并入中危一；`gaiji.py:30 pua()` 无调用点（若第三方调用，畸形编号 `int()` 会 ValueError）
  - 代价：改 `annotate` 触指纹（本轮已改）；`fonts` 不在 `_FP_IMPL_MODULES` 不触
- [ ] **待做 测试稳定性** 全量 discover 偶发原生崩溃：2026-10-21 第一次 `python -m unittest discover -s pycbeta/tests -q -t .` 以 `0xC0000005`（Windows 访问冲突）退出且无失败摘要，重跑即 1352 OK（skipped=122）；27 个测试模块单独跑全部 OK ⇒ 属跨模块交互/解释器退出期问题，非某个用例失败。定位方向：offscreen 的 PySide6 与 native 库（WeasyPrint / PyMuPDF）退出顺序；未复现前不改代码
- [x] **已完成 文档（publish 侧）** 上游提案文档与 publish `TODO.md` 同步到 v0.2.0 现状
  - `publish/docs/上游-cbeta-fetch-TLS与分块下载.md` 已加「实施结果（2026-10-21）」：上游 commit `817d207`、版本 `0.2.0`、两仓 vendor 同步记录、解压原子性与同名策略留第二批
  - publish `TODO.md` 第四批：TLS、分块流式两条已勾选；解压原子性与同名冲突仍为未做（第二批）
  - 遗留：该文档 §3 与 §5、§6 的「现状」描述仍以 `0.1.2` 为准（保留作对照），实施口径以 `0.2.0` 为准
