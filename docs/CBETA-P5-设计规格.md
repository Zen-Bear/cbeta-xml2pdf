# CBETA XML P5 → 多格式转换工具 · 设计规格书

| 项 | 内容 |
|---|---|
| 版本 | v0.1（草案） |
| 日期 | 2026-08-13 |
| 状态 | 决策已定，待实现 |
| 源格式 | CBETA XML P5（官方发布版） |
| 目标 | Python 重写，IR 架构 |

---

## 1. 已确认决策（Decision Record）

| # | 决策 | 理由 |
|---|---|---|
| D1 | **源格式 = CBETA XML P5**（cbeta-org/xml-p5），不用 P5a | p5a 是内部工作库（标注"不建議大眾使用"），p5 是正式发布版；官方 HTML 参照就是 P5 结构生成的 |
| D2 | **重写为 Python**，不以 Ruby 为基底修改 | ruby-cbeta 是 P5a 取向，P5 校勘结构（锚点/back/wit 引用）需重写解析层；且 docx/epub/繁转简 在 Python 生态成熟 |
| D3 | **IR 架构**：XML 解析一次 → 语义模型（IR）→ 多渲染器 | 支持 6 种输出 + 脚注/尾注 + 竖排 + 简体，全部解耦 |
| D4 | **PDF 引擎可插拔**，不用 Prince（商业授权是硬门槛） | 横排主用 **WeasyPrint**（免费、纯 Python、页面/书签/字体齐全），竖排用 **Chromium headless**（免费、vertical-rl），两者共用同一"PDF-ready HTML+CSS"中间产物 |
| D5 | 脚注支持"脚注 / 尾注"双模式，引擎不支持脚注时优雅降级为尾注 | 官方 docx=真脚注、pdf/html=尾注 已有参照；降级路径保证任何引擎可行 |
| D6 | 输出格式：**HTML（官方格式）、PDF（横排+竖排）、EPUB、DOCX**；**不做 TXT/ODT**（仅作参照） | 用户要求 |
| D7 | 简体转换 = 文本层后处理（OpenCC） | 与 IR 解耦 |
| D8 | 缺字以"最终字形 + CB 码"双层进 IR；字形优先取 `<g>` 内容 + 档头 charDecl，外部 JSON（cbeta_gaiji.json 等）兜底 | P5 自带字形，渲染自足 |

## 2. 系统架构

```
cbeta-org/xml-p5（CBETA XML P5）
          │  lxml 解析（忽略命名空间，按本地名）
          ▼
   IR（语义模型）◄──── 一次性解析，含校勘归一化
          │
          ├─ HTML 渲染器  →  官方格式（cb_note_anchor / #back / gaiji span）
          ├─ EPUB 渲染器  →  EPUB3（XHTML + OPF/NCX）
          ├─ DOCX 渲染器  →  OOXML 直出（真脚注 footnotes.xml）
          ├─ PDF 渲染器   →  PDF-ready HTML+CSS → 可插拔引擎
          │       ├─ 横排：WeasyPrint（@page 页大小/书签/字体/脚注→尾注或 float:footnote）
          │       └─ 竖排：Chromium headless（writing-mode:vertical-rl）
          └─ 文本后处理：繁→简（OpenCC）
```

关键约束：
- **渲染器只读 IR**，不得反向解析 XML/HTML 结构；
- **PDF 引擎差异只在"PDF-ready HTML"层收敛**，IR 与各渲染器不感知引擎。

## 3. 输入：CBETA XML P5

### 3.1 数据来源与文件结构

- 来源：https://github.com/cbeta-org/xml-p5（官方 TEI P5，定期从内部 P5a 生成发布）
- 目录：`<canon>/<vol>/<vol>n<work>.xml`
  - canon（藏经 ID）：1~2 码，如 `T`、`X`、`GA`、`GB`、`ZS`、`ZW`
  - vol（册号）：3~5 码，如 `T01`、`A091`、`ZS01`、`GA001`
  - work（经号）：
    - 4 码数字：`T0001`
    - 4 码+字母（**大小写有区分**）：`T0128a`（CBETA 给）、`T0150A`（大正藏给）
    - 大写字母+3 码：`JA041`；小写字母+3 码（非正文）：`ZWa072`

### 3.2 多册 / 跨册特例

| 类型 | 作品 | 说明 |
|---|---|---|
| 跨 4 册 | L1557 | L130~L133，卷 17/34/51 分跨两册 |
| 跨 3 册 | T0220（大般若经） | T05~T07，T05/T06 各 1 档、T07 拆 13 档（a~o）；卷号/章节也跨册 |
| 跨 3 册 | P1612、P1615 | P179~P181、P181~P183 |
| 跨 2 册 | A1267、A1501、C1163、JB271、JB277、K1257、L1490、L1638、P1519、P1611、P1617、U1418、X0240、X0367、X0714、X0822、X1568、X1571、YP0011 | 完整清单见官方 work-multi-vol.md |

**合并规则**：同一 work 的多册/多档 XML 在解析时合并为一个 work；`<milestone unit="juan">` 划分卷；T0220 输出时去掉档尾 a/b/c… 后缀（统一为 T0220）。

### 3.3 TEI 总体结构（已实证 T12n0349-p5）

```
<TEI xml:id="T12n0349">
  <teiHeader>
    <fileDesc>
      <titleStmt> title×5 / author / respStmt </titleStmt>
      <editionStmt> edition / respStmt[id=resp1] / respStmt[id=resp2] </editionStmt>
      <extent>1卷</extent>
      <publicationStmt> idno[type=CBETA]>(canon/vol/no) / distributor / availability / date </publicationStmt>
      <sourceDesc><bibl/></sourceDesc>
    </fileDesc>
    <encodingDesc>
      <projectDesc> p[lang=en/zh-Hant] </projectDesc>
      <editorialDecl><punctuation resp="#resp1"/></editorialDecl>
      <tagsDecl>
        <namespace name="http://www.tei-c.org/ns/">
          <tagUsage gi="rdg"><listWit> witness[id=wit.cbeta]… </listWit></tagUsage>
        </namespace>
      </tagsDecl>
    </encodingDesc>
    <profileDesc><langUsage> language[ident=zh-Hant/en] </langUsage></profileDesc>
    <revisionDesc> change[when] </revisionDesc>
  </teiHeader>
  <text>
    <body> …正文… </body>
    <back> …校勘区… </back>
  </text>
</TEI>
```

要点：
- `<witness>` 表位于 `encodingDesc > tagsDecl > namespace > tagUsage[gi=rdg] > listWit`；
- `<respStmt xml:id="respN">` 可出现在 titleStmt / editionStmt；`#respN` 是全档引用；
- `<charDecl>` **可选**（有缺字映射时出现，如 X60n1116）；
- `<publicationStmt><date>` 是 P5 生成/发布日期（如 2025-01-30）；
- 命名空间：TEI + cb（`cb:div`、`cb:t`…）。**解析时忽略命名空间、按本地名处理**，P5a/P5 同策略。

### 3.4 body 正文元素（P5 实际形态）

- 分页分行：`<pb n="0001a" ed="T"/>`、`<lb n="0001a01" ed="T"/>`（P5a 可能无 ed；双版本 lb 并存 `ed="X"`+`ed="R150"`；`lb/@type="honorific|old"`）
- 分卷：`<milestone unit="juan" n="1"/>`（注意：**前一个 lb 属于新卷**，官方已证实）
- 卷首尾：`<juan n="001" fun="open|close"><jhead><title>…</title></jhead></juan>`
- 章节：`<div type="xu|jing|pin|fen|…">`（命名空间剥除后统一为 `div`）、`<head>`、`<mulu type="卷|經|…" level="1" n="…" label="…"/>`
- 段落/偈颂：`<p>`（`type="dharani|head1..6|pre"`、`rend`、`style`）、`<lg type="regular" subtype="v5|note1…">`、`<l>`、`<caesura/>`
- **校勘锚点（P5 特有）**：
  - `<anchor xml:id="nkr_note_orig_0164001" n="0164001"/>`（orig 校勘注所在位置）
  - `<anchor xml:id="beg<key>" n="…"/>` 与 `<anchor xml:id="end<key>"/>`（校勘用字区间起止）
  - `<anchor type="circle"/>`（原书 ◎ 记号）、`<anchor xml:id="fx…"/>`
- 夹注：`<note place="inline|inline2|interlinear">`（仍内联在 body）
- 缺字：`<g ref="#CB02494">䟦</g>`（**P5 自带字形**；SD/RJ 同）
- 双语对照：`<tt>`、`<t xml:lang="sa-Sidd|zh-Hant|san-tr|pi">`、`<yin><zi/><sg/></yin>`
- 其他：`<byline>`、`<docNumber>`、`<graphic url>`/`<figure>`、`<table cols><row><cell rows/cols>`、`<list rend><item>`、`<foreign>`、`<term>`、`<seg rend>`、`<hi rend>`、`<space quantity>`、`<unclear cert>`、`<choice><corr/><sic/></choice>`、`<reg>`、`<sg>`、`<quote>`、`<ref>`、`<bibl>`、`<biblScope>`

### 3.5 back 校勘区（P5 特有）

```
<back>
  <div><head>CBETA 校注</head>            ← 校注区标题（可含）
    <app from="#beg0162b0601" to="#end0162b0601">
      <lem wit="#wit.cbeta" resp="#resp3">已</lem>
      <rdg wit="#wit.orig">巳</rdg>
    </app>
    <note n="0001005" resp="#resp2" type="orig" place="foot text">韞＝溫【宋】【元】</note>
    <note n="0001005" resp="#resp1" type="mod">…</note>
    <note place="foot" type="equivalent">…</note>
    <note place="foot" type="rest">…</note>
  </div>
</back>
```

- note/app 的 `resp`、`wit` 均为**引用**（`#respN` / `#wit.*`）；
- `<app from="#begX" to="#endX">` 用锚点对定位 body 位置。

## 4. IR 数据模型

### 4.1 元数据 Metadata（对齐官方 `*.yaml`）

```
Work:
  id: "T0349"            # 去除册号，T12n0349 → T0349；T0220 特例
  canon: "T"
  vol: "12"              # normalize：T12 / GA009 / ZS01
  title: "彌勒菩薩所問本願經"
  author: "西晉 竺法護譯"
  source: "大正新脩大藏經"
  volume_extent: "1卷"
  publisher: "中華電子佛典協會（CBETA）"
  contributors: "…"
  punctuation: "AI 標點"     # 来自 editorialDecl>punctuation
  publication_date: "2025-01-30"
  revision: [ {when, who, what} ]   # revisionDesc
  license: "…"
```

### 4.2 语义树（节点）

```
Document
 ├─ Metadata
 └─ Body（有序节点流）
     ├─ Block 节点：Div(type/level), P(type/rend/style), Head, Byline,
     │            Lg(type/subtype/rend), List, Table, Figure, DocNumber,
     │            JuanMarker(n, fun, jhead), Milestone(n=juan)
     ├─ Inline 节点：Text(run, line=lb, char_idx), Lb(n, ed), Caesura,
     │            G(Gaiji), Tt(dual-line), Yin(zi+sg), Hi, Seg, Space,
     │            Foreign, Term, Unclear, Choice(corr/sic/reg)
     └─ 校勘一等对象：Note, App  （见 4.3）
```

- `Text` run 携带所属 `lb` 与字符序号（HTML 官方格式的 `lineInfo` / `w` 需要）；
- `Div` 记录嵌套层级（`data-head-level`）。

### 4.3 一等对象：Note / App / Gaiji

```
Note:
  n          # 校勘编号（页内/行内流水，特例：0、-n10、a/b 拆分）
  type       # orig | mod | add | equivalent | rest | star | authorial | cf1..cf6 | inline
  place      # foot | text | foot text | inline | inline2 | interlinear
  subtype    # biao | jie | ke | shift | 規範字詞（可选）
  resp       # 已解析为人名/机构（如 "CBETA.maha"）
  note_key   # 修订考据库链接（可选）
  text       # 校注文本（含 <space>、<g> 已展开）
  position   # 关联的正文锚点位置（锚点回填后）

App:
  key        # from/to 锚点 key（begX/endX）
  type       # star | star_removed | hide | 缺省
  lem: { text, wit:[版本], resp }
  rdg: [ { text, wit:[版本], resp, type: correctionRemark|variantRemark|cbetaRemark } ]
  position   # 正文位置（锚点区间回填）

Gaiji:
  cb_code    # CB02494 / SD-DA42 / RJ-CCBA
  char       # 最终字形（优先 <g> 内容，次 charDecl，最后外部 JSON）
  data       # 原始记录（composition/unicode/normal…，供弹窗等）
  pua        # 派生 PUA（需要时计算）
```

Note 与 App 的**归属版本**（witness 解析后的【大】【宋】…）是 DOCX/多版本输出的关键。

## 5. P5 解析规则（核心实现规格）

### 5.1 解析流程（每档 XML）

```
① 预扫描 teiHeader
   ├─ 元数据（title/author/extent/date/revision/punctuation）
   ├─ wit 表： 收集 <listWit><witness xml:id="wit.orig">【卍續】</witness>
   │            → { "#wit.orig": "【卍續】", "#wit1": "【嘉興-CB】", … }
   ├─ resp 表：收集 <respStmt xml:id="resp1"> 的 name → { "#resp1": "AI", … }
   └─ charDecl（可选）：缺字映射 → { "#CB02494": {…} }
② 遍历 <text/body>，按本地名分发构建 IR 节点
   ├─ 遇 <anchor xml:id="nkr_note_<type>_<key>" n="N"> → 校勘注锚点（type∈{orig,mod,add,…}）
   │    同一校勘的 orig/mod 锚点相邻且 n 相同 → 按 n 去重，一个校勘只挂一个 NoteRef
   ├─ 遇 <anchor xml:id="begX"> / "endX"      → 记录区间 X 起止
   ├─ 遇 <g ref="#CB…">content</g>            → Gaiji{cb_code, char=content}
   └─ 其余元素按 5.6 映射表
③ 遍历 <text/back>
   ├─ <note … target="#nkr_note_<type>_<key>"> → 按 target 精确回填；无 target 时按 n 归组
   ├─ <app from="#begX" to="#endX"> → 按区间 X 回填
   └─ wit/resp 引用 → 用①的表就地解析
④ 生成 IR（校勘已归位，正文与校勘合一）
```

### 5.2 锚点回填算法（已按实证数据校准）

- **nkr_note_<type>_<key>**：P5 对同一条校勘可能生成**多个锚点**（`nkr_note_orig_N`、`nkr_note_mod_N`…），在 body 中**相邻、n 相同**（实证：T0349 为 orig→mod→beg 顺序相邻）。back 中 note 用 `target="#nkr_note_<type>_<key>"` **精确引用**；
- **去重规则**：一个校勘（同一 n）在 body 只挂一个 `NoteRef`，其 `notes` 携带该 n 的全部注释（orig+mod+add…），渲染器自选。官方 HTML 佐证：T0349 的 96 条注释 → 官方 HTML 只输出 48 个 `noteAnchor`（= 48 个校勘组）；
- **beg/end 区间**：`begX`/`endX` 锚点之间的正文片段即 app 的 lem 用字区间 → app 在此处回填（`App` 节点内联），正文区间文本保留；
- **注意**：body 正文被锚点切成多个 tail 片段，回填后需合并回同一 Text run；`lb` 出现在 lem/rdg 内部时（跨行校勘）需保留行号归属。

### 5.3 wit / resp 引用解析

- `wit="#wit.orig #wit2"` → `【卍續】【…】`（拆空格，逐项查表；查不到保留原文并告警）；
- `resp="#resp3"` → 查 respStmt 表；
- `punctuation resp="#resp1"` → 确定标点类型（AI/原書/CBETA/DILA）。

### 5.4 缺字解析

- 优先级：`<g>` 元素内容（P5 自带） > charDecl 映射 > 外部 `cbeta_gaiji.json` / `cbeta_sanskrit.json`；
- 编码范围（官方）：CB00001~CB34547（十进制）、RJ-C943~RJ-E06F、SD-A440~SD-E5E3；
- PUA 派生（需要时）：CB → `0xF0000+十进制`；SD → `0xFA000+末4位hex`；RJ → `0x100000+末4位hex`；
- `cb:behaviour="no-norm"`（term/text 上）→ 禁用通用字正规化。

### 5.5 边界用例（必须回归）

| 用例 | 规则 |
|---|---|
| T0220 大般若经 | T05/T06/T07 多档合并为一个 work；输出统一为 `T0220`，去档尾 a~o |
| L1557 / GA0037 / X0714 卷跨册 | 卷 17/34/51 / 卷 2 / 卷 3 按官方清单拼接跨册 HTML/docx |
| `<milestone unit="juan">` 前的 lb | **属于新卷**（T01n0001 卷 2 从 11a02 起） |
| 卷号不连续/非 1 起始 | 以 milestone/@n 为准（X03n0208 从第 10 卷起） |
| T16n0657 双行夹注跨偈行 | lb 需移到 note 结束前（ruby 硬编码的处理需对照复刻） |
| lb 双版本 | `ed="X"`+`ed="R150"` 并存，只取主版本（如 X），R 版可作次行号 |
| note 位置特例 | 夹在 l 间、list/item 间、直接 body/div 下、div/note/p |
| 空 mulu | 目录中忽略 |
| 小经编号 note | `n="0030001-n10"` 含后缀，需去重编号 |

### 5.6 元素 → IR 映射表（摘要，完整表随实现细化）

| P5 元素 | IR 节点 | 关键属性 → IR 字段 |
|---|---|---|
| `div`（含 cb:div） | Div | type/rend/style → level 由嵌套深度 |
| `head` | Head | 文本；`data-head-level` 用 Div 深度 |
| `p` | P | type(cb:type)/rend/style |
| `lg` / `l` | Lg / L | type/subtype/rend/style/cb:place |
| `lb` | Lb | n/ed/type(honorific,old) |
| `pb` | Pb | n/ed（渲染通常忽略） |
| `milestone` | Milestone | unit=juan, n → 分卷 |
| `juan` / `jhead` | JuanMarker | n/fun, jhead 文本 |
| `note` | Note | n/type/place/subtype/resp/note_key/text |
| `anchor` | Anchor 或归并到 Text | nkr_note_orig/beg/end/circle/fx |
| `app`/`lem`/`rdg` | App | from/to/type; wit/resp 解析后 |
| `g` | Gaiji | ref→cb_code, content→char |
| `tt`/`t` | Tt | type/rend/place; t/xml:lang |
| `yin`/`zi`/`sg` | Yin | zi 文本 + sg 声调（括号包裹） |
| `table`/`row`/`cell` | Table/Row/Cell | cols/rows/cols/rend/style |
| `list`/`item` | List/Item | rend, item/n/xml:id |
| `graphic`/`figure` | Graphic | url |
| `byline` | Byline | cb:type(Author/Translator…) |
| `docNumber` | DocNumber | 文本 "No. 1" |
| `mulu` | Mulu | type/level/n/label（TOC） |
| `choice`/`corr`/`sic`/`reg` | Choice | corr 取正文，sic 备注，reg 为通用字 |
| `foreign`/`term`/`hi`/`seg`/`space`/`unclear`/`quote`/`ref` | Inline | rend/style/lang |
| 文本节点 | Text | 归属 lb + 字符序号 |
| `<back>` | 不建节点 | 只在预扫描/回填时使用 |

## 6. 渲染器目标

### 6.1 HTML（官方格式，golden target = `./cbeta/*.html`）

- 结构：`#body` + `#back`（尾注区）+ `#cbeta-copyright`；
- 脚注引用：`<a id='cb_note_anchorN' class='noteAnchor {type}' href='#cb_note_N'>[A序]</a>`；
- 尾注：`<div class='footnote' id='cb_note_N'>[<a href='#cb_note_anchorN'>A序</a>] 内容</div>`；
- 缺字：`<span class="gaiji" data-gid="CB01140">字形</span>`；
- 行号：`<span class='lineInfo' line='0163a09'></span>`；head 带 `data-head-level`；div 类名 `div-{type}`；
- 按卷输出多文件（`X1116_001.html`）。

### 6.2 PDF

- **中间产物**：IR → "PDF-ready HTML+CSS"（CSS 含 `@page` 预设、主题、`@font-face` CBETASupplement）；
- **横排**：WeasyPrint。页面大小（手机/平板/显示器预设）、自定义字体/样式；脚注优先 CSS `float:footnote`（WeasyPrint 不支持则降级尾注）；
- **竖排**：Chromium headless + `writing-mode:vertical-rl`，需带竖排度量的 CJK 字库；**先做 POC**（标点竖排、双行夹注、行首行号）；
- 书签/目录：WeasyPrint `bookmark-level` 生成。

### 6.3 EPUB（EPUB3）

- XHTML（复用 HTML 渲染器的正文部分）+ OPF + NCX/NAV + 包为 zip；
- 注释用 `<aside>`/弹窗或尾注，缺字用 CSS 字体嵌入。

### 6.4 DOCX（OOXML 直出）

- `word/document.xml` + `word/footnotes.xml`（**真脚注**，参照官方 docx：53 footnotes）；
- 缺字 run 标 `w:eastAsia="CBETA Supplement"`（参照官方 fontTable 用法）；
- 双行对照(tt)/偈颂(lg) 用表格或段落缩进呈现；
- 按卷输出（`T0349_001.docx`）。

### 6.5 繁转简（可选后处理）

- OpenCC 词表，作用于 Text 节点（渲染前），输出简体 HTML/PDF/EPUB/DOCX。

## 7. 验证与测试策略

| 层 | 方法 |
|---|---|
| 解析正确性 | 用 `./cbeta` 真实 P5 样本跑通 IR，断言锚点回填/引用解析/witness 表正确 |
| HTML 回归 | 与官方 HTML（X1116_001.html 等）做**字节级/规范化 diff** |
| DOCX 回归 | 与官方 docx 比对：脚注数、段落数、字体引用（结构断言） |
| 多册/边界 | T0220、L1557 等特例的专门用例集 |
| 缺字 | 遍历 CB/RJ/SD 三类，验证字形与 PUA |
| 性能 | 大藏经全量转档时间基准（解析层单遍） |

## 8. 风险与待验证项

| 风险 | 等级 | 处置 |
|---|---|---|
| WeasyPrint 无真脚注 | 中 | 降级尾注（R1 允许）；或 paged.js（Chromium 上跑） |
| Chromium 竖排排版细节 | 高 | **优先做竖排 POC**（标点竖排/双行夹注/行首行号 4 项验收） |
| P5 锚点回填复杂（跨行校勘、lem 内 div） | 中 | 解析层单元测试 + 官方 HTML 对照 |
| charDecl / witness 位置差异 | 低 | 解析器按结构定位（已验证 tagsDecl>listWit） |
| CBETA 规范演进（如 dharani 改标 p/@type） | 低 | 解析器容忍未知类型，未知元素默认透传文本 |

## 9. 附录：资产清单

### 9.1 可复用数据（语言无关，直接使用）

| 资产 | 位置 |
|---|---|
| 缺字库 | `ruby-cbeta/lib/data/cbeta_gaiji.json`（4MB）、`cbeta_sanskrit.json` |
| 藏经元数据 | `canons.csv`、`categories.json` |
| Unicode 版本表 | `unicode-1.1.json`（供手机/桌面字形判断） |
| 官方参照输出 | `cbeta/` 各目录（HTML/PDF/EPUB/DOCX/ODT/TXT + `*.yaml`） |
| 缺字字体 | `cbeta/fonts/CBETASupplement.ttf`（+ 网络 woff2） |
| 官方规范 | `cbeta/cbeta-documentation/`（60 元素 + 结构 + 跨册 + global attributes） |

**P5 源数据完整性**：`cbeta/` 下全部 14 部经论均已具备 P5 XML（含 T0452、T0670、T0672），均确认含 `<back>`/`<witness>`/`nkr_note_orig` 锚点，结构完整，可作解析层与 golden 回归的测试集。

### 9.2 技术栈（Python）

| 用途 | 库 |
|---|---|
| XML 解析 | lxml（XPath/DOM/RelaxNG） |
| PDF 横排 | WeasyPrint（@page/书签/字体） |
| PDF 竖排 | Chromium headless（Playwright） |
| EPUB | 标准库 zipfile + 自写 XHTML/OPF |
| DOCX | OOXML 直出（zipfile + XML 模板） |
| 繁转简 | OpenCC |
| 测试 | pytest + 自写 golden diff |

### 9.3 Ruby 中可参考实现（只读参考，不依赖）

- `cbeta.rb`：ID/册号/行首正则、normalize_vol、juan_across_vol、PUA 计算；
- `p5a_to_html.rb` 等：元素语义与 HTML 呈现细节（注意是 P5a 结构，校勘层需按 P5 重写）；
- 官方 HTML `./cbeta` 才是 HTML 渲染器的最终基准。

## 10. 实现状态

## 11. CLI（2026-08 重构）

```
python -m pycbeta -i <xml|目录> -f <format> [-o <输出>] [选项]

共享参数（所有格式）: -i/--input  -o/--output  -f/--format{html,pdf,docx,md,epub,all}
                     --theme  --name-template
注释（所有格式）   : --notes{footnote,endnote,inline}
页面（pdf/docx）   : --page{a4,a5,letter,phone,tablet,monitor,book}
PDF 专属           : --vertical  --engine{chromium,docx2pdf,prince,weasyprint}
```

`-f` 支持逗号组合（`html,pdf,docx`）或 `all`（全部 5 种）；**一次解析 IR，内存内多次渲染**（不持久化）。

**输出文件名模板（`--name-template`）**：
- 占位符：`[id]`（作品 ID）`[书名]` `[作者]` `[vol]`（册号）`[juan]`（卷号，按卷输出补零 001）
- 例：`--name-template "[id] [书名]（[作者]）"` → `T0349 彌勒菩薩所問本願經（西晉 竺法護譯）.docx`
- 缺省：`{id}_{juan}.html` / `{id}.{ext}`

**Windows 文件名安全化**（`filename.py`）：
1. 非法字符 → **全角映射**（`:`→`：`、`\`→`＼`、`/`→`／`、`*`→`＊`、`?`→`？`、`"`→`＂`、`<`→`＜`、`>`→`＞`、`|`→`｜`）
2. 无全角对应（控制字符等）→ 删除 + **警告到 stderr**
3. 尾随点/空格清理；保留名（CON/PRN/…）加前缀 `_`；超长截断
4. 结果为空 → 退回占位（警告）

**日志**：不加 `--log` 参数——进度走 stdout、警告走 stderr，用户重定向 `> log 2>&1` 即可。

**注释三种方式（`--notes`）**：
- `footnote` 页底脚注（docx=OOXML 默认；pdf=docx2pdf/Prince 引擎；epub=EPUB3 aside，待实现）
- `endnote` 文末尾注（html=官方 `#back` 默认；pdf 默认）
- `inline` **括号夹注**（所有格式支持，正文内 `（内容）`）
- 缺省按格式：docx=footnote，html/pdf/epub=endnote

输出规则：
- 单文件输入、无 `-o`：源目录生成**同名文件+扩展名**（html 生成 `<同名>_html/` 目录）
- `-o` 以格式扩展名结尾：视为输出文件；`-o` 为目录：视为输出目录，文件名 = 作品 id + 扩展名
- 目录输入：`os.walk` 逐文件处理

`--page` 同时作用于 docx（`w:pgSz` twips）与 pdf（`@page`）；docx 支持脚注/尾注双模式（OOXML 脚注 or 文末「注释」节）。

### M1：P5 解析层 + IR（已完成）

```
pycbeta/
  model.py      IR 数据模型（Text/Lb/Pb/Gaiji/E/Note/NoteRef/App/AppRead/Work）
  names.py      canon/vol/work ID 规则、normalize_vol、work_id 派生
  gaiji.py      GaijiDb（JSON 缺字库加载）、PUA 计算
  parser.py     P5Parser：两阶段解析 + 锚点回填 + wit/resp 解析 + 去重
  __main__.py   CLI：python -m pycbeta <xml> [out-dir]
  tests/        16 项 unittest，全绿
```

### M2：HTML 渲染器（对齐官方格式，已完成）

```
  render_html.py  HtmlRenderer：IR → 官方 cb_note 格式 HTML
```

**验证结果（golden 对照）**：
- **X1116（主 golden）**：body + back 与官方 HTML **逐字节一致**，仅版权块「發行日期」依赖 yaml（XML 无此字段）；
- **YP0012**：001/002/004 逐字节一致；003/005 差异仅为「官方首 div 单引号怪癖」+「缺图档无法内联 base64」；其余卷仅版权日期差异；
- 13 部作品全部解析+渲染无报错，**分卷文件数与官方完全一致**（T0672=7、YP0012=9、T1525=9、X1116=2…）。

**已实现的关键规则**（均为逐字节 diff 校准）：
- 分卷：`<milestone unit="juan">`，支持 **div 跨卷**（闭开 div）；文件名 `{id}_{卷号:03d}.html`
- 元素渲染：p（class/style/lineInfo）、head（data-head-level）、byline、juan、pre（保留换行/全角空格）、lg（lg-row/lg-cell + caesura 分格 + text-indent 移到首格）、list/li、table（bip-table div）、dharani、form、docNumber、doube-line-note
- 注释：**add→cb_note 新格式**（`[A序]` + `#back` div），**orig/mod→旧格式**（`note_anchor`+`#n`）；back 顺序=旧格式在前、cb_note 在后；A 序号**分卷重新编号**；add 注内容追加 lem 的 cf 引用（`(cf. ...)`，有 `cb:provider` 时不包 linehead span）
- 缺字：span 判定 `ord(char)>=0x2A700`；显示字形按 `charDecl > 外部 DB（unicode→norm_unicode→big5→composition→pua）> 原文`
- 行号：仅取主版本 lb（`ed==canon`，忽略 R 副版）；Text 保留全角空格、非 pre 去换行

**已知差异**（需外部数据或接受）：
- 版权块「發行日期/最後更新」来自 yaml，XML 只有 publication_date
- `<graphic>` 内联 base64 需 figure 图档目录（`figure_base` 可配置）
- 官方生成器对「body 首 div」偶用单引号（生成器自身不一致）

### M3：PDF（已完成，Chromium 引擎）

```
  render_pdf.py  PdfRenderer（IR → PDF-ready HTML + @page/字体/endnotes）+ Chromium 转换
```

**引擎决策**：**PDF 引擎可插拔**（`--engine` 或环境变量 `CBETA_PDF_ENGINE`）：
- **chromium（默认）**：Playwright 无头 Chromium，横排+竖排均可，免费
- **docx2pdf**：IR → DOCX（真脚注）→ LibreOffice/Word → PDF；**免费拿到页底脚注**（OOXML 脚注被 Office 渲染器放页底）；需装 LibreOffice 或 Word；仅横排
- **prince**：装好后直接切；Prince 原生支持页底脚注/PDF 书签/竖排，待后续测试
- **weasyprint**：需 Windows GTK/Pango；不支持竖排/脚注，仅横排备选

同一份 PDF-ready HTML+CSS 喂给 HTML 类引擎；docx2pdf 走 DOCX 中转。

**PDF 库脚注调研（2026-08，四个候选均不满足脚注需求）**：

| 库 | 工作流 | 原生脚注 | 竖排 | 许可 | 结论 |
|---|---|---|---|---|---|
| WeasyPrint | HTML/CSS | ❌ 无 `float:footnote` | ❌ | BSD | 最好的纯 Python HTML/CSS（@page/书签强），但 Windows 缺 GTK、无脚注/竖排 |
| pdfkit | HTML/CSS | ❌（旧 WebKit 无 CSS 脚注） | ❌ | MIT | 用旧 WebKit，不如现代 Chromium，且有 CJK 生僻字问题 |
| fpdf2 | 程序化 | ❌ 无内建（需手动页底排脚注） | ❌ | MIT | 轻量；程序化=重写排版，无自动排版引擎 |
| borb | 程序化 | ❌ 无 | ❌ | **AGPL**（闭源商用受限） | 排除 |

结论：页底脚注只有两条路——**Prince（付费，HTML/CSS 原生）**或 **docx2pdf（免费，OOXML 真脚注→Office）**；现有引擎栈（chromium+docx2pdf+prince）已覆盖脚注/竖排/书签，四个候选库均非升级项。

**验证结果**：
- 横排 A4：X1116 生成 95 页 PDF，全文 78,734 字提取完整（含正文/尾注/校注）
- 页面尺寸：phone（100×178mm）/ tablet / monitor / a4 / a5 预设均生效
- 竖排 POC：`writing-mode: vertical-rl` 渲染成功（122 页，文字逐字竖排提取），**判定可行**

**发现并修复的 Chromium 打印 bug**：字体栈中含 `cbetarc`（经 @font-face 嵌入 CBETASupplement）时，多页打印会**丢弃全部 CJK 文字**（屏幕/单页正常，≥2 页即丢）。修复：默认字体栈不含 cbetarc；gaiji 已解析为系统字体可覆盖字形。cbetarc 嵌入作为 opt-in（带此已知问题注释）。

**页底脚注（R1 双模式补齐）**：自由引擎（Chromium/WeasyPrint）无 CSS `float:footnote`，接入 **paged.js**（跑在 Chromium 里，实现 CSS Paged Media 脚注）实现真页底脚注：
- CLI `--footnotes`：正文 `[N]` 上标调用 + 页底脚注区（自定义编号，规避 paged.js 计数器 bug）
- 未加 `--footnotes` 时保持文末尾注（默认）
- 已验证：T0349 8 页，脚注在页底渲染（页底区域墨迹确认）；文本提取对部分脚注字形受限（Chromium ToUnicode 子集问题，视觉正常）

**竖排待补**（非阻塞）：
- 行首行号（页边竖排行号）未实现
- 双行对照 tt 竖排：13 部样本均无 `<tt>`，需含悉漢对照的作品验证

后续里程碑：
- M4：DOCX（真脚注已完成，EPUB 待做）
- M5：繁转简、主题、页面配置

### M4：DOCX（真脚注，进行中）

```
  render_docx.py  DocxRenderer（IR → OOXML，真页底脚注）
```

**脚注机制**（参照官方 docx 结构，参考实现已归档 backup/20260902）：`word/footnotes.xml` part + `w:footnoteReference` 上标引用 + `FootnoteText` 样式。

**已验证（T0349，官方 docx 53 条脚注）**：
- **53 条脚注对齐官方**：48 个唯一校勘 + 5 条 `corresp` 星号重复校勘（`<app corresp="#N">` 重复出现处也发脚注）
- OOXML 结构合法：文本全部在 `<w:r><w:t>` run 内；python-docx 打开成功（54 段 + footnotes part）
- **偈颂（lg）**：对齐官方——每行 `w:br` 换行、两栏用 4 全角空格分隔（非表格）
- **缺字字体**：天城/扩展区缺字（ord>0xFFFF）run 用 `CBETA Supplement` 字体（`w:rFonts w:eastAsia`），对齐官方 docx
- **tt 双行对照**：t 行内拼接（无含 tt 样本验证）

待完善：EPUB、tt 竖排、简体、主题。

CLI：`python -m pycbeta <xml> out --docx`

### M5：主题系统 + 官方默认样式

```
  theme.py             Theme（语义标签 → CSS-like 属性 → 各格式样式）
  styles/pdf_docx.css  PDF/DOCX 默认主题（正式文件，默认使用）
  styles/cbeta_golden.css  HTML/EPUB 官方（golden）基底
```

**核心思想**（用户提出）：`title/head/juan/p/verse/footnote...` 等语义标签共享一套风格定义，用户改一处，HTML/PDF/DOCX 同时生效。

**语义 type 全部暴露为 CSS 钩子**（来自 P5 规范 `cb:type`）：
- `cb:div type` → `.div-orig`（原文粗体）、`.div-commentary`、`.div-xu`…（22 种）
- `p` → `p.dharani` / `p.form` / `p[data-head-level=N]`（6 级缩进）
- `byline` → `p.byline`；`note type` → `a.noteAnchor.add/.mod/.orig/.star`
- `lg` → `div.lg.regular/.note1`；`mulu` → `.mulu`

**`styles/pdf_docx.css`（PDF/DOCX 默认主题）**：Theme 默认加载它（raw_css 供 HTML/PDF 直接用，tinycss2 解析成 tags 供 DOCX）；用户 `--theme` 按标签覆盖。HTML/EPUB 默认不加载主题（只用 cbeta_golden.css 基底，保持官方逐字节一致）。

**DOCX 语义继承**：div 类型进入标签上下文栈（`div-orig` 内段落自动继承粗体），`docx_run()/docx_para()` 多标签合并。

用法：`python -m pycbeta <xml> out --docx|--pdf [--theme theme.css|json]`

**两种主题输入**（用户选一）：
1. **JSON**（`{"tags": {...}}`）——显式标签映射
2. **CSS**（推荐）——用户直接写 CSS，`tinycss2` 解析：
   - HTML/PDF：**用户 CSS 原样使用**（零转换，所见即所得）
   - DOCX：解析选择器→语义标签，可转换属性（font-size/font-weight/color/font-family/text-align/text-indent/line-height/margin-left）→ OOXML rPr/pPr；`em` 换算用该标签字号上下文；不可转换属性忽略

验证：pdf_docx.css 默认生效；DOCX 53 脚注 + div-orig 继承 + python-docx 可开；PDF 8 页完整；22 测试全绿。
