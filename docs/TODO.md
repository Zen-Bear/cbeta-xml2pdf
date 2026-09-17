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

- [x] **已完成 P12** 本地单卷跨目录版本 XML（2026-09-09 立项，2026-09-10 落地 A 方案）
  - 预检实锤（TX0006：TX07 001-006 + TX08 007-015 + TX09 016-049，seq 全局连续；juan milestone 1-49 连续；每碎片完整 TEI 无 back）：题名仅卷范围各异（取首卷，元数据噪声）；锚点零冲突（重复 id 仅各卷根 xml:id + witness）；charDecl 仅 015 卷 1 字（CB16748，恰被同卷唯一 `<g>` 引用）；body 内 foot 注 4（渲染/抽取双双丢弃，既有语义）+ 无锚 app 8（渲染直吐 lem/rdg，抽取侧镜像漏收——本次修齐）
  - 落点：`test/merge_cbreader.py` 分组键改 `(canon,no)`（无卷号 stem 回退旧键，长度不同永不串组；排序 `(vol,seq)`）；`merge()` 加 charDecl 按 id 跨卷并集 + 题名差异提示 + back 实质内容警告（body-only 语义不变）；跨册落首卷目录沿首卷 stem（`TX/TX07/TX07n0006.xml`，work id TX0006 不变，零管线改动）；`--only` 三形态（碎片 stem/归一 stem/佛典編號）；单测 `pycbeta/tests/test_merge.py` 7 项
  - 抽取侧附带修正（aux-only，零渲染影响）：`_extract_xml_parts` body 内无 from/corresp 的 app 收子文本（镜像渲染泛型默认分支；有锚 app 仍丢，残留已知）；单测 `test_body_app_without_anchor_mirrors_render`
  - 验收：TX0006 实合 49 碎片→1 部（199 body 节点）；合部 body/注块与碎片拼接逐字相等（509548 字）；辅轨 `--baseline xml` 0/0；docx 冒烟 826KB/4642 段/outline 俱全；单测 28 OK（merge/txt/verify）；全量回归按用户指示跳过（改动面：一次性合部脚本 + aux 抽取镜像，渲染/解析零触碰）
  - 备选 B（管线原生多文件感知）改动面大未采用；旧同目录合部语义保持原样（T01n0001 路径不变，单测锁死）
  - 自动合册入管线（2026-09-10 用户立项：xml_dir 直指 CBReader 书库免下载出书）：`pycbeta/merge.py` 库化（分组改按册 `(canon,vol,no)`；`resolve_work_files` 整文件优先否则碎片合册；`split_paths` 目录分区；合成落 tmpdir 随跑随清；`test/merge_cbreader.py` 瘦身薄 wrapper）；CLI 編號流 + 目录 walk + GUI ID/目录双模式接线（下游只见路径零感知；GUI 行标签“合册合成”）；多源同部输出触发式回退输入基名（`resolve_output _used`，单文件逐字节不变；html 命名 renderer 内置残留已知；GUI 批量同撞既有，另立项）；验收 TX0006 书库直出 3 txt + 逐册辅轨 0/0 + 逐册官方对照（TX07 0/0；TX08/TX09 差源 variance + 体注既有语义，非合部丢字，见下）；单册保真（组内拼接逐字相等）；全量 473 OK；门禁 html 双 OK（txt/md 残留已知类）；全量 verify 超时系环境慢（子集正常落盘），非失败
  - 统一命名（2026-09-10）：同轮多源同名全组改输入基名（首个亦回溯改名，`TX07n0006/TX08n0006/TX09n0006`，册数可见；`filename.dedupe_run_outputs`，render/verify 共用 state 重放得终态；GUI worker 显式 `-o` 同规则）；单文件/重跑逐字节不变；全量 483 OK
  - fetch 纯下载不要求 xml_dir（`need_xml=False`；download 空仍报错，堵 cwd 落盘保留）
  - 材料化模型重构（2026-09-10 用户定稿）：`download_dir` 改名 **`cbeta_ebook`**（唯一可写工作根；平展 `{id} {书名}/`，书名取 catalog 经 `source.title_t2s` 转简+净化）；`xml_dir` 定位为**只读候选源**（角色同远端 URL，两者相同即报错）；`fetch.materialize_work` 三源解析（cbeta_ebook → xml_dir 拷贝/碎片按册合册 → 官方下载，mtime 刷新）；`work_dir/_find_work_dir`（`{id}*` 复用，排除 T0349a 类误命中）；基线按需落 work 目录；**删除 git sparse clone 兜底与 `downloads.xml_repo`**；`merge_groups_to_tmpdir`→`merge_groups_to_dir`（平展 `{stem}.xml`），删 `merge.resolve_work_files`；CLI `--download-dir`→`--cbeta-ebook`、編號流改用 run.json 有效配置（原误用出厂 `load_presets`，材料化看不到用户槽）；GUI 三源接线+来源标签、数据源窗口 `title_t2s` 复选；verify 基线自动下载落 cbeta_ebook；`config.user.json`/测试语料迁 `<repo>/cbeta_ebook`；全量 493 OK
  - Phase 2 更新检查（2026-09-10）：`fetch.check_ebook_updates`（遍历 cbeta_ebook work 目录，逐 XML 条件下载 `If-Modified-Since`（304 免下载）+ 字节比对，不改项不落盘；无 sidecar，按日期/体积判定；**只走远程源，不涉本地 CBReader 候选源**）+ `format_update_report`（已更新/无变化/失败/跳过 + 需重新生成 ID 段）；**XML 有更新的 work，本地已有基线一并强制刷新**（`with_baselines`，仅已存在格式，GUI 复选「同时更新已有基线」默认开）；GUI 数据源窗口「检查电子书更新」按钮（`EbookUpdateWorker` 后台线程 + `EbookUpdateDialog` 弹窗，**一键拷贝已更新 ID** 到剪贴板）；字节详情去掉 `B` 后缀；单测 `TestCheckUpdates` 6 项 + GUI 2 项 + `_fetch_baseline_flat force` 1 项
- [x] **已完成** 单元测试数据路径迁移（`CBETA` 常量 → `E:\dev\cbeta\test`；`TestRenderYP0012` → `TestRenderYP0019`；`_body` 归一化剥 `<style>`/border span/style 属性/标签空白）
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
  - [ ] **待办** 门禁外 6 红后续（2026-09-10 取证，详见校验说明书 §5“门禁外已知红”；无一回归，门禁口径不变）：
    1. 渲染 body-placed foot 注（parser 收编 + 六渲染器出注 + aux 镜像 + 全门禁回归；收 TX08 类注 + T01 stub，T01 25k 本体仍红——输入就没有）；
    2. T01 `_cbreader` 重合（9/5 旧版 charDecl 4/应 70，卫生；与 17k 缺失无关）；
    3. 辅轨 `No.` 令牌镜像剥离（5 行；`strip_head_no=true` 时 aux 16 缺转 0）
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
- [ ] **P9 中（已归档，不做）** GUI 界面三语切换（2026-09-06 立项，2026-09-10 用户决议归档；与输出经文 t2s/font_sets 无关，是界面本身语言）
  - 背景：界面中文串全硬编码（panel 约数百处、`__main__` 状态栏/按钮），无 `QTranslator` 机制
  - 方案（存档）：先抽字符串资源（`pycbeta/gui/i18n/*.ts`，Qt Linguist 流程：`pylupdate6` 抽取→翻译→`lrelease` 编译→`QTranslator.load/install`），面板顶部或设置加语言下拉（简/繁/英，存用户槽，重启生效；或动态 `retranslateUi` 热切）
  - 验收（存档）：三语切换无硬编码残留（`rg` 查中文串只剩 ts 源）；offscreen 实例化通过；单测不断言具体中文文案（现有 `tabText` 名单用例需同步为 key 断言或跟随默认语言）
- [ ] **P10 低（已归档，不做）** GUI 深色模式（2026-09-06 立项；2026-09-10 落地一次后用户撤回，整体 revert，归档）
  - 背景：现为 Qt 默认浅色；Qt6 可部分跟随系统深色，未显式适配（红字提示/灰字 hint 在深色下可能看不清）
  - 方案（存档）：跟随系统 `Qt::ColorScheme` + 手动开关（三态：跟随/浅色/深色，存用户槽）；先只保证现有样式表（红/灰提示色）在深色下可读，不过度定制 QSS
  - 验收（存档）：深/浅/跟随三档目检（配置栏/七卡/批量表/状态栏无看不清文字）
  - 备注：曾落地 `dark.py` 三态+用户槽+recolor（含 Fusion 试错、调色板定案、外观下拉搬家），`63ec9b3`/`cebd6c9`，后经 `dd87a28` 整体 revert；重做时直接看这三提交

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

- [ ] **最低优先级（最后）** `html-epub-user-theme` 接线（2026-09-09 决议：意义不大，暂不做）
  - 现状：`EMPTY_RUN` 占位 `""`（`theme.py:418`），非空警告+忽略（564-567）；无 CLI 开关、无 GUI 控件；html/epub 默认纯 golden
  - 将来要做时的探明设计（三步）：`resolve_html_base_css` 加 `user` 形参（显式开关 > 槽 > 纯基底，`_resolve_run_file` 缺文件警告+回退），用户文件追加到 golden 之后——`render_html._wrap` 与 epub `style.css` 同吃一份 `base_css`，渲染侧零改动；CLI 加 `--html-epub-user-theme`（与 pdf 侧对称）；单测锁追加顺序/回退/显式优先；golden 选择器与 pdf 出厂同体系（`.head`/`div.lg`/`p.form`…），增量可复用习惯；verify 走文本不受影响

- [x] **strip_head_no 去标题行首 No. 令牌**（2026-09-10 用户立项：X60n1116 `<head>No. 1116-B…序`）
  - 落点：`theme.strip_head_no` helper（非变异，跳空节点，余部 lstrip 吃版式空格，正文 No. 不动）+ 六渲染器（docx/html/md/txt 直改，epub/pdf 继承 html；docx jhead 先 strip 再 dedup）+ `config output.strip_head_no=false` + CLI `--strip-head-no` + GUI 排版卡复选（默认不勾）+ verify 三入口联动（生成透传 + 官方行首精确令牌表对等剥离；`--config` 双形态收敛 `_strip_no_from`，旧静默回出厂坑已填）
  - 验收：X60n1116 `-f txt` 开剥离 0/496（missing=0 四令牌 A/B/C/D 全对齐；残留 = 题署行版式差 + body-app 双变体展开，属已知局限类，非 strip 问题）；默认关全量 454/458（4 失败系用户未提交 CSS 改动 `h1.title 30→26pt`，非本件；stash 干净树对照通过）
  - 附带：`docNumber` 独立元素（如 `No. 1116`）两边保留不动；书签/目录文本不同步
  - 导航窗格跟随可见段落（OOXML 同一段落无法分离；mulu 书签名保留 No.）——2026-09-10 用户确认接受现状，不动
- [x] **插图机制（2026-09-11 用户立项：`<figure><graphic url="../figures/X/X59p0224_01.gif">`，缺图报错？自动下载？）**
  - 远端已核验：`cbeta-git/CBR2X-figures`（`master`，布局 `{canon}/{basename}`，如 `X/X59p0224_01.gif` 6.4KB 确有其文件）；模板 `https://raw.githubusercontent.com/cbeta-git/CBR2X-figures/master/{canon}/{file}` 进出厂 `config.json downloads.figures` + `panel.DOWNLOAD_KEYS`（数据源 URL 表/重置自动兼容）
  - 新模块 `pycbeta/figures.py`（纯函数）：`split_graphic_url/download_url/find_figure/search_dirs/work_figure_dirs/graphic_urls_in_text/gif+png size/looks_like_image`
  - `fetch.ensure_figures`（`{work}/figures` 已有 → `{work}/txt` 基线 bonus 拷贝 → 远端下载；404/失败记缺失不抛错）+ `materialize_work` 四出口与 `ensure_baselines` 自动触发（含图才跑）
  - 渲染：`HtmlRenderer.figure_base` 升级 str|list + `missing_figures`（占位 span 不变）；`EpubRenderer` 透传；`DocxRenderer` 新增 `_render_graphic`（手拼 OOXML `word/media`+rels+`w:drawing`，尺寸读 GIF 头按版心等比 clamp，缺图 `【圖：…】`）；pdf 两管线自动继承；CLI `render_one/process_file` 经 `figures.work_figure_dirs` 接线 + 缺图行打印（GUI 经子进程同口径进状态栏）；`verify.generate_formal` 同路径传入（文本比对不受图片影响）
  - 验收：新 `test_figures.py` 17 项（含 docx 包内 media/rels/drawing + 三部件 lxml 良构断言——曾抓到漏 `</a:xfrm>` 致 Word 打不开）；X59 实测 html 4 张 base64 零占位、docx 4 media 良构、raw 下载 6557B 与基线一致；缺图策略=警告+占位不中断（用户确认）
  - 追修（2026-09-11 用户反馈 X1077 docx/pdf 无图）：根因是 `<figure>` 在 CBETA 里常**内联于 `<p>`**，而 `_render_graphic` 恒包 `<w:p>` → 非法嵌套，WPS 静默丢弃段内图片（最小顶层用例正常，故对照实验才暴露）。修法：`_in_para` 上下文（`_render_para_children` + `_render_tagged` 内统一标记，覆盖 p/pre/head/byline/pin/form/def/verse/cell/脚注/夹注），段内只出 run 级 drawing，块级才包段。实测 X59 pdf（WPS）94 页 4 图；另发现卷名/mulu 区 8 处既有 `title` 嵌套（文字完整，与图片无关，未动）
  - 追修2（2026-09-11）：折叠按钮改绿底白字（各态 stylesheet 同色 + `ButtonText` 调色板设白，箭头靠方向区分；像素级单测锁定）；图片 100% 上限（审计确认只缩小不放大 + `jpeg_size` SOF 解析 + 1x1 原生/2000px 等比压单测锁定）
- [ ] **CBETA 校改字标红 `corr`（2026-09-12 用户点档：先记录不修改）**
  - 现象/取证：官方**同一颗字**在 docx 用字符样式 `corr` 红 `FF0000`（`<w:rStyle w:val="corr"/>`，T0001_001.docx 全文 12 处；styles.xml `corr` → color FF0000）；官方 **epub** 用 `<span class='corr'>` + `cbeta.css` 的 `.corr{color:red}`；官方 **html 不标红**（全库扫描 0 处 `corr`/`cbeta` span）；txt 无颜色
  - 判定规则：正文所采用的读法 `app/lem` 的 `@wit` 含 **`#wit.cbeta`**（IR 解析为 `app.lem.wit` 含 `【CB】`/`【CB-…】`）→ 该校改字标红；lem 为 `#wit.orig`（如 `['【大】']`）不标。例：`0005009` lem `['【CB】','【宮-CB】']` → 官方红；`0006002` lem `['【大】']` → 不红。T01 lem 含 `【CB` 213 处，juan1 与官方 12 处量级吻合
  - 我方现状：判定信息已具备（`app.lem.wit`），但正文夹在 `<anchor beg.../>…<anchor end.../>` 之间，parser 丢弃 `end` 锚点且不记区间 → IR 无法定位校改字；三渲染器均无 `corr`，golden 只有未用的 `.cbeta`、无 `.corr`
  - 拟定实施（范围待定，未做）：parser `_traverse` 维护 corr 区间栈（`beg` 且 lem 含 `#wit.cbeta` 开，匹配 `end` 闭），包合成 IR 节点 `E(tag="corr", children=[…])`（App 一并包入、正文渲染为空无害；建议按**原始 `#wit.cbeta` id** 判，不依赖 label）；docx → 红字（官方字符样式或主题色内联）；epub → `span.corr` + golden `.corr{color:red}`；html/md/txt → 只渲染子节点不产生 span（与官方 html/txt 一致、保 golden 对照）；死命令三件套：`TAG_SELECTOR["corr"]="span.corr"` + `EDITABLE_ROWS ("span.corr","CBETA校改")` + CSS 规则
  - 待用户定：实现范围（docx+epub 对齐官方 / 六格式全标红(html 偏离官方) / 暂不做）与判定键（原始 `wit.cbeta` id（推荐）/ 解析后 `【CB` label）
- [ ] **元素覆盖扫描（2026-09-10 三项并查，决议：都不加行，只记录）**
  - test XML 19 文件 body 普查：左栏缺失但可见 = `l`（13/4819）/`caesura`（11/4747）/`cb:t/tt`（T01/X59n1077）/`list/item`（3 文件）/正文内 `title`（6/126）/`hi/seg[border]/note[hide]`/`space`（4/430）/`yin/zi/sg+entry/term`（X59/X60）/`figure/graphic`（3/74）/`g`（12/947）+`app/lem/rdg`/`div@type=orig/commentary/jing/pin/fen/w/other`（other 1808，左栏仅 xu/note）；`rend` 四行 19 文件零命中无样张；结构性无需调 = lb(70125)/pb/milestone/cb:juan/jhead/docNumber/mulu(2087)/anchor(9837)
  - schema（cbeta-p5.rnc）对照：唯一值得加的是 `table/row/cell`（走 bip-table，左栏无行）——本次不加；`list` 低优先级；其余透传/功能性不值得单列；header 无行系正确忽略
- [ ] **字体扫描（2026-09-10，决议：只记录不动链）**
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
  - 保留（防误删）：`p.form`/`p.figure` 的 `text-indent:0`（压 p 的 2em）、`cb:def` 的 `font-weight:normal`（压 div-note 加粗）、**`p.series-title` 的 `text-align:left`（压 p 的 justify；曾被我误列为可省，已更正）**、脚注 `line-height:1`、`li{text-indent:0}`、`pre{text-indent:0}`（REQUIRED 要求）
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
  - 新仓库 `E:\dev\cbeta\cbeta-fetch`（`cbeta_fetch.py` 单文件、纯标准库）：`is_work_id`/`parse_work_id`（canon 大写、no 原样）/`canonical_work_id`/`catalog_lookup`/`DEFAULT_DOWNLOADS`（含新 `pdf`）/`REMOTE_URLS`（元数据单源）/`download`（原子·可 `unzip`）/`unzip_flat`/`fetch_if_changed`/`probe`；`pyproject.toml`（发行名 `cbeta-fetch`）、README/API/CHANGELOG/LICENSE、`tools/sync_into.py`、`docs/对接单-publish.md`
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
  - 已把激活预设缺的 source 块回填（现 `resolve_source` → `('', 'E:\dev\cbeta\cbeta_ebook')`）
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
