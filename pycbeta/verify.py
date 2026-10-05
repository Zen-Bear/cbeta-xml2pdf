# -*- coding: utf-8 -*-
"""校验库：供 CLI --verify、test/verify_text.py 及 GUI 复用。"""
import difflib, glob, hashlib, json, os, re, sys, zipfile
from typing import List, Dict, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from .parser import P5Parser
from .model import E, Text, Lb, Pb
from .render_html import HtmlRenderer
from .render_docx import DocxRenderer
from .render_epub import EpubRenderer
from .render_md import MdRenderer
from .render_txt import TxtRenderer
from .theme import load_presets, load_effective_presets, _PRESETS_PATH, strip_head_no

def normalize(text: str, ruby_brackets=None) -> str:
    # 官方基线 unclear 用 ▆，本管线渲染用 □（U+25A1）：两侧归一到 □ 再比较
    text = text.replace("▆", "□")
    # 悉昙/缺字占位：官方 txt 用 ◇（U+25C7），生成侧用私用区字（PUA）；统一为 □
    text = text.replace("◇", "□")
    text = re.sub(r"[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]",
                  "□", text)
    text = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", text)
    text = re.sub(r"\[[^\]\[]{1,8}\]", "", text)
    # 【】见证标记剥除（【CB】/【大】等，官方与生成侧同源）；含「圖」的不剥
    #（官方 txt 图注如 【圖：X59p0224_01.gif】，须保留参与比对）
    text = re.sub(r"\u3010(?![^\u3011]*\u5716)[^\u3011]{1,20}\u3011", "", text)
    # 〔〕上限 40（原 20）：官方基线内仅 〔－〕类短标记，注音括注 〔bō rě〕等多音节可超 20 字
    text = re.sub(r"\u3014[^\u3015]{1,40}\u3015", "", text)
    if ruby_brackets:
        # 自定义右侧注音括号（如（）/[]）：仅剥除读音字符内容（拼音字母+声调符号/注音符号+空格），
        # 正文与校勘记括号（内含汉字）不受影响；官方侧无注音，此规则为无操作
        l, r = ruby_brackets
        if len(l) == 1 and len(r) == 1 and (l, r) != ("〔", "〕"):
            # 读音字符集：ASCII 字母+空格、拉丁扩展（含拼音声调 ū ǖ ê）、
            # 修饰声调符 ˊˇˋ˙、注音符号区；汉字不在其中，故正文/校勘括号得以保留
            _reading = "A-Za-z\\u00c0-\\u024f\\u1e00-\\u1eff\\u02c7\\u02ca\\u02cb\\u02d9\\u3100-\\u312f "
            text = re.sub(re.escape(l) + "([" + _reading + "]{1,40})" + re.escape(r), "", text)
    text = re.sub(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", "", text)
    text = re.sub(r"CBETA[^\n]*", "", text)
    text = re.sub(r"\[\^\d+\]", "", text)
    text = re.sub(r"[#>*`\-]{1,3}", "", text)
    text = re.sub(r"◎", "", text)
    text = re.sub(r"\(cf\.[^)]*\)", "", text)
    return re.sub(r"[\s\u3000]+", "", text)


def normalize_with_lines(text: str, ruby_brackets=None):
    """normalize 的逐行版：返回 (norm, line_of, raw_lines)。

    line_of[i] = norm[i] 对应的原始行号（0-based，行号即可与 *_compare_*.txt 对齐）。
    逐行归一与整体归一的罕见不一致（括号跨行等）时返回空 line_of（调用方退回无行号显示）。
    """
    norm_all = normalize(text, ruby_brackets)
    raw_lines = (text or "").split("\n")
    parts, line_of = [], []
    for li, ln in enumerate(raw_lines):
        n = normalize(ln, ruby_brackets)
        parts.append(n)
        line_of.extend([li] * len(n))
    norm = "".join(parts)
    if norm != norm_all:
        return norm_all, [], raw_lines
    return norm, line_of, raw_lines


def ctx_locations(ctx, ours_line, theirs_line) -> list:
    """ctx（diff opcodes）→ 每条差异的原始行定位（1-based；行不可得为 None）。"""
    out = []
    for _tag, i1, _i2, j1, _j2 in ctx or []:
        o_li = ours_line[min(i1, len(ours_line) - 1)] if ours_line else None
        t_li = theirs_line[min(j1, len(theirs_line) - 1)] if theirs_line else None
        out.append({"gen_line": (o_li + 1) if o_li is not None else None,
                    "src_line": (t_li + 1) if t_li is not None else None})
    return out


def _mark_span(text: str, a: int, b: int, before: int = 18, after: int = 18,
               pad: int = 0) -> str:
    """归一文本差异段标记：前文…〖差异〗…后文（差异为空时显示空括号）。
    pad>0 且 span 为空时填 `〓`×pad（对端 span 长度），使源/新两行位置对齐；
    pad=0 保持旧行为。"""
    a = max(0, min(a, len(text)))
    b = max(a, min(b, len(text)))
    pre = text[max(0, a - before):a]
    mid = text[a:b]
    post = text[b:b + after]
    if not mid and pad > 0:
        return f"{pre}〖{'〓' * pad}〗{post}"
    return f"{pre}〖{mid}〗{post}"


_ANCHOR_RE = re.compile(r"\[([A-Za-z0-9]{1,12})\]")


def _query_runs(query):
    """display 行 → 查询串列（由长到短）：原样/去标记/最长 CJK 节。
    归一/展示层剥掉的标记（【】/[...]）在原文里可能还在，原样先试。"""
    out = []
    q = (query or "").strip()
    if q:
        out.append(q)
    bare = re.sub(r"【[^】]*】", "", q)
    bare = re.sub(r"\[[^\]\[]{1,12}\]", "", bare).strip()
    if bare and bare != q:
        out.append(bare)
    runs = re.findall(r"[\u4e00-\u9fff]{2,}", bare)
    out.extend(sorted(set(runs), key=len, reverse=True)[:3])
    return [s for s in out if s]


def _nearest_anchor(lines, idx, span=15):
    """行表 idx 往前找最近的 [n]/[Ax] 锚点 → (锚, 相距行数)；无则 ("", -1)。"""
    for i in range(idx, max(-1, idx - span), -1):
        m = _ANCHOR_RE.search(lines[i])
        if m:
            return m.group(0), idx - i
    return "", -1


def _locate_hits(files_texts, query, max_hits=3):
    """[(文件名, 原文)] 里找查询行 → ["文件:行（锚后n行）", ...]。
    原文取定位用形态（含 [n] 锚点）；行号是该文件抽取文本的行号。"""
    hits = []
    for q in _query_runs(query):
        for fname, raw in files_texts:
            if q not in raw:
                continue
            lines = raw.split("\n")
            for li, ln in enumerate(lines):
                if q in ln:
                    a, d = _nearest_anchor(lines, li)
                    tail = f"（{a}后{d}行）" if a else ""
                    hits.append(f"{fname}:{li + 1}行{tail}")
                    if len(hits) >= max_hits:
                        return hits
        if hits:
            break
    return hits


def _official_locate_texts(bkind, bpath, fmt, strip_jiaozhu, prep=None):
    """trial 基线文件 → [(文件名, 定位用原文)]（重抽取，ms 级；含 [n] 锚点）。
    保留换行结构与锚点标记；行号为本文件抽取文本行号。
    prep 为可选后处理（toks/t2s/txtnorm 对齐比对侧文字）。"""
    files = bpath if isinstance(bpath, list) else [bpath]
    out = []
    for p in files:
        try:
            label = os.path.basename(p) if isinstance(p, str) else str(p)
            if bkind == "html" and fmt == "docx":
                b, f = _extract_html_parts(p)
                t = b + "\n" + f
            else:
                t = extract_text(p, strip_jiaozhu=strip_jiaozhu)
            out.append((label, prep(t, bkind) if prep else t))
        except Exception:
            continue
    return out


def _gen_locate_index(fmt, gen_paths):
    """生成档定位索引：docx → ("docx", 正文段落[], [(w:id, 注文)])；
    其余 → ("text", 全文行表)。段落按 </w:p> 切分，与 Word 段落序号一致；
    脚注按 footnotes.xml 顺序（w:id 即 Word 脚注号）。"""
    if fmt == "docx" and gen_paths:
        try:
            with zipfile.ZipFile(gen_paths[0]) as z:
                doc = z.read("word/document.xml").decode("utf-8", "replace")
                try:
                    fn = z.read("word/footnotes.xml").decode("utf-8", "replace")
                except KeyError:
                    fn = ""
            paras = [re.sub(r"<[^>]+>", "", p) for p in doc.split("</w:p>")]
            foots = []
            for m in re.finditer(r'<w:footnote w:id="(\d+)"(.*?)</w:footnote>',
                                 fn, re.S):
                wid, body = m.group(1), m.group(2)
                foots.append((wid, re.sub(r"<[^>]+>", "", body)))
            return ("docx", paras, foots)
        except Exception:
            pass
    return ("text", [], [])


def _locate_gen_hits(gen_index, query, o_nsrc="", max_hits=3):
    """生成侧定位：docx 按段落/脚注找；其余按生成原文行表找。"""
    hits = []
    queries = _query_runs(query)
    kind = gen_index[0] if gen_index else "text"
    if kind == "docx":
        _, paras, foots = gen_index
        for q in queries:
            for pi, p in enumerate(paras):
                if q and q in p:
                    hits.append(f"正文第{pi + 1}段")
                    if len(hits) >= max_hits:
                        return hits
            for wid, body in foots:
                if q and q in body:
                    hits.append(f"脚注{wid}")
                    if len(hits) >= max_hits:
                        return hits
            if hits:
                break
        return hits
    lines = (o_nsrc or "").split("\n")
    for q in queries:
        for li, ln in enumerate(lines):
            if q and q in ln:
                hits.append(f"生成文本第{li + 1}行")
                if len(hits) >= max_hits:
                    return hits
        if hits:
            break
    return hits


def _frag_locs(loc, o_rawln, t_rawln, off_texts, gen_index, o_nsrc):
    """片段双侧原始文件定位 → (src_loc, gen_loc)（分号分隔多命中；空侧返回 ""）。
    以 compare 整行为查询串，分别在官方基线文件文本（含 [n] 锚点）与生成档索引中找。"""
    sl = loc.get("src_line")
    gl = loc.get("gen_line")
    t_full = t_rawln[sl - 1] if sl and 0 < sl <= len(t_rawln) else ""
    o_full = o_rawln[gl - 1] if gl and 0 < gl <= len(o_rawln) else ""
    src_loc = "; ".join(_locate_hits(off_texts, t_full)) if t_full.strip() else ""
    gen_loc = "; ".join(_locate_gen_hits(gen_index, o_full, o_nsrc)) \
        if o_full.strip() else ""
    return src_loc, gen_loc


def format_work_summary(work_id, items) -> str:
    """单经书校验总结行（下游速读哪个格式过/不过及程度）：
    `[T45n1859] 3 format: 1[docx=OK(0/0)], 2[pdf=1], 3[epub=FAIL(48/97)]`。
    items = [(fmt, status, missing, extra)] 或 [(fmt, status, missing, extra, ref)]，
    按处理顺序；status ∈ ok/fail/covered/no_baseline/nogen/error/…（大小写不敏感）。
    - ok→`OK(mi/ex)`，fail→`FAIL(mi/ex)`（缺数/多 None 记 `?`）；
    - covered + ref 可解（ref 格式在本行内）→ `N[pdf=M]`（M 为 ref 的序号，
      即"结果看第 M 条"）；解不了回退 `COVERED`；
    - 其余状态大写原文（no_baseline→NO_BASELINE 等）。
    行首 `[id]` 刻意避开下游 `[OK]/[FAIL]/[--]` 行首解析；纯报告层，不影响主程序。"""
    order = []
    for it in items:
        f = (it[0] or "?").split("→")[0].strip() or "?"
        if f not in order:
            order.append(f)
    parts = []
    for i, it in enumerate(items, 1):
        fmt, status = it[0], it[1]
        mi = it[2] if len(it) > 2 else None
        ex = it[3] if len(it) > 3 else None
        ref = it[4] if len(it) > 4 else None
        f = (fmt or "?").split("→")[0].strip() or "?"
        st = (status or "").strip().lower()
        if st == "ok":
            mi_s = mi if mi is not None else "?"
            ex_s = ex if ex is not None else "?"
            parts.append(f"{i}[{f}=OK({mi_s}/{ex_s})]")
        elif st == "fail":
            mi_s = mi if mi is not None else "?"
            ex_s = ex if ex is not None else "?"
            parts.append(f"{i}[{f}=FAIL({mi_s}/{ex_s})]")
        elif st == "covered":
            r = (ref or "").split("→")[0].strip()
            if r and r in order:
                parts.append(f"{i}[{f}={order.index(r) + 1}]")
            else:
                parts.append(f"{i}[{f}=COVERED]")
        elif st in ("no_baseline", "nogen", "error"):
            parts.append(f"{i}[{f}={st.upper()}]")
        else:
            parts.append(f"{i}[{f}={st.upper() or '?'}]")
    return f"[{work_id}] {len(items)} format: " + ", ".join(parts)


def _display_text(raw: str) -> str:
    """*_compare_*.txt 落盘文本：剥 [..]/页码令牌、压缩 3+ 空行；
    报告行号即以此文本为准（normalize 后内容与 raw 同）。"""
    txt = re.sub(r"\[[^\]\[]{1,8}\]", "", raw)
    txt = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", txt)
    return re.sub(r"\n{3,}", "\n\n", txt).strip() + "\n"

_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.S | re.I)

def _ann_brackets_from(presets):
    """annotations 自定义右侧括号（verify 剥除用）：未启用/默认〔〕→None（走默认规则）。"""
    try:
        from .annotate import valid_brackets
        spec = (presets or {}).get("annotations") or {}
        if not spec.get("enabled"):
            return None
        b = valid_brackets(spec.get("brackets"))
        return (b[0], b[1]) if (b[0], b[1]) != ("〔", "〕") else None
    except Exception:
        return None# 注音剥除（P6）：html/epub 的 <rt>/<rp>、docx 的 <w:rt> 内容在提取时丢弃，
# 开启注音不影响回归基线比对（md 的〔〕括注由 normalize 剥除，见 normalize）
_RUBY_RE = re.compile(r"<r[tp][^>]*>.*?</r[tp]>", re.S | re.I)
_W_RUBY_RE = re.compile(r"<w:rt>.*?</w:rt>", re.S)
_EQ_RE = re.compile(r"<w:instrText[^>]*>(.*?)</w:instrText>", re.S)

def _eq_base(m):
    """EQ 拼音指南域还原原文：仅处理注音签名（\\ad + \\up），其余域代码保持原样（旧行为）。
    ``\\ad(\\s \\up N(RD),BASE)`` → BASE；解析失败 → ""（丢代码，避免开关文本泄漏进比对）。"""
    code = m.group(1)
    if "\\ad" not in code or "\\up" not in code:
        return m.group(0)
    tail = code.rsplit(",", 1)[-1].strip()
    if tail.endswith(")"):
        tail = tail[:-1].strip()
    if tail and len(tail) <= 20 and "\\" not in tail:
        return tail
    return ""

# epub 导航/封面/前后言 boilerplate（官方结构 titlepage/front/toc/back/nav；
# 我方 nav）：抽取比对时跳过。命中为空时回退全量，避免空比对。
_EPUB_SKIP_BASENAMES = frozenset({
    "nav.xhtml", "toc.xhtml", "titlepage.xhtml", "front.xhtml",
    "back.xhtml", "cover.xhtml",
})


def _epub_content_names(z) -> list:
    """epub 内正文 xhtml 名单（跳过 boilerplate；为空回退全量）。"""
    names = [n for n in z.namelist()
             if n.lower().endswith((".xhtml", ".html"))
             and os.path.basename(n).lower() not in _EPUB_SKIP_BASENAMES]
    if not names:
        names = [n for n in z.namelist()
                 if n.lower().endswith((".xhtml", ".html"))]
    return names


def _body_only(raw: str) -> str:
    """只取 <body> 内容（去掉 <title>/nav 头文本）；无 body 标签原样返回。"""
    m = re.search(r"<body[^>]*>(.*)</body>", raw, flags=re.S | re.I)
    return m.group(1) if m else raw


def extract_text(path: str, strip_jiaozhu: bool = True) -> str:
    """抽取可比对文本。html 分支默认剥离 `<hr><h1>校注</h1>` 标题
    （docx/md/txt 比对：生成侧无此标题，官方侧须同步剥离）；
    fmt 为 html/epub 时传 False 保留（生成侧 html/epub 有此标题，需对齐）。
    epub 分支从不处理该标题（章节内联，无独立标题块可剥；txt trial
    用 `_join_epub_ours` 另行处理）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub":
        with zipfile.ZipFile(path) as z:
            raws = [_body_only(z.read(n).decode("utf-8", "replace"))
                    for n in _epub_content_names(z)]
        raws = _reorder_epub_footnotes(raws)
        parts = []
        for txt in raws:
            txt = _STYLE_RE.sub("", txt)
            txt = _RUBY_RE.sub("", txt)
            txt = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", txt, flags=re.I)
            parts.append(_TAG_RE.sub("", txt))
        return "".join(parts)
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
            xml = _EQ_RE.sub(_eq_base, xml)
            xml = _W_RUBY_RE.sub("", xml)
            # 行内 <w:br/>（同段目录/偈颂/预排的分行）保留为换行，避免剥标签后
            # 多行连成一行；与 html 侧「一行一条」口径一致（官方/生成同规）
            xml = re.sub(r"</w:p[^>]*>", "\n", xml)
            xml = re.sub(r"<w:br[^>]*>", "\n", xml)
            txt = _TAG_RE.sub("", xml)
            try:
                fn = z.read("word/footnotes.xml").decode("utf-8")
                fn = _EQ_RE.sub(_eq_base, fn)
                fn = _W_RUBY_RE.sub("", fn)
                fn = re.sub(r"</w:p[^>]*>", "\n", fn)
                fn = re.sub(r"<w:br[^>]*>", "\n", fn)
                txt += "\n" + _TAG_RE.sub("", fn)
            except KeyError:
                pass
            return txt
    if ext == ".odt":
        with zipfile.ZipFile(path) as z:
            return _TAG_RE.sub("", z.read("content.xml").decode("utf-8"))
    if ext in (".html", ".xhtml", ".htm"):
        raw = open(path, encoding="utf-8", errors="replace").read()
        raw = _body_only(raw)
        raw = _reorder_html_footnotes(raw)  # 顺序校注：注块按阅读顺序（双侧同规）
        raw = _STYLE_RE.sub("", raw)
        raw = _RUBY_RE.sub("", raw)
        if strip_jiaozhu:
            raw = re.sub(r"<hr[^>]*>\s*<h1[^>]*>\s*校注\s*</h1>", "", raw, flags=re.I | re.S)
            raw = re.sub(r"<h1[^>]*>\s*校注\s*</h1>", "", raw, flags=re.I)
        raw = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", raw, flags=re.I)
        return _TAG_RE.sub("", raw)
    return open(path, encoding="utf-8", errors="replace").read()


def t2s_baseline(text: str) -> str:
    """官方基线转简体：与生成侧 simplify 同一管线（OpenCC t2s + 专名修正）。

    简体校验时调用：官方基线恒为繁体，经此转换后再与简体生成档比对。
    作用于 extract 后的纯文本，因此 html/txt/docx/epub/odt 各模式统一适用，
    无需分模式处理（txt 无需剥标签同样走此路径，结果一致）。"""
    from .simplify import simplify_text
    return simplify_text(text)


def _extract_html_parts(path: str):
    """抽取 html 为 (正文, 脚注) 两段，用于多卷合并时将脚注统一放文末（与 docx 合并对齐）。
    同时剥离尾注上方的 <hr><h1>校注</h1> 标题（与 docx 校注区标题对齐）。
    脚注判定以 class='footnote' 为准（div/span 均处理），正文中的校注锚点 [A1]/[0164001] 等
    由 normalize 的方括号规则 [..] 统一剥离（不依赖 class）。
    只取 <body> 内容（<title> 等头文本非正文，官方/生成不对称，见 _body_only）；
    无 body 标签回退全文。"""
    raw = open(path, encoding="utf-8", errors="replace").read()
    return _split_html_text(raw, body_only=True)


def _foot_block_text(block_raw: str) -> str:
    """单个 footnote 块转文本（与 `_split_html_text` 注记侧逐字节一致，
    唯行首 ASCII 空白剥除：新增校注 `[A1]` 与常规注块同列行首；
    html 成品仍保留官方缩进，此处只影响 txt 重组形，比对归一本就无视空白）。"""
    t = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", block_raw, flags=re.I)
    return _TAG_RE.sub("", t).lstrip(" \n\r\t") + "\n"


# 悉昙空位标记（HtmlRenderer 输出；官方 html 同款：读音走 roman 属性，
# 文本抽取为空，html/epub 比对不受影响；txt 重组形按官方 txt 物化为裸读音）
_RANJA_RE = re.compile(r"<span\b[^>]*\bclass=(['\"])ranja\1[^>]*>", re.I)
_ROMAN_RE = re.compile(r"\broman=(['\"])([^'\"]*)\1", re.I)


def _materialize_ranja(raw: str) -> str:
    """epub→txt 专用：ranja 空标记物化为裸读音（如 `raṃ`）。
    官方 txt 悉昙缺字即裸读音（`raṃ【CB】，◇【卍續】`），而官方 html/epub
    为空元素——故只在 txt 重组管线物化，extract/html 侧保持为空。"""
    def _rep(m):
        rm = _ROMAN_RE.search(m.group(0))
        return rm.group(2) if rm else ""
    return _RANJA_RE.sub(_rep, raw)


# 内嵌图（HtmlRenderer：找得到嵌 base64 + alt 留文件名；找不到留 imgsrc span）
# 与无解 PUA 空位标记（官方 txt 作图注/◇，官方 html/epub 为空元素）
_FIG_IMG_RE = re.compile(r"<img\b[^>]*\balt=(['\"])([^'\"]+)\1[^>]*>", re.I)
_FIG_SPAN_RE = re.compile(
    r"<span\b[^>]*\bimgsrc=(['\"])([^'\"]+)\1[^>]*>\s*</span\s*>", re.I)
_EMPTY_GAIJI_RE = re.compile(
    r"<span\b[^>]*\bclass=(['\"])gaiji\1[^>]*(?:/>\s*|>\s*</span\s*>)", re.I)


def _materialize_figs_gaiji(raw: str) -> str:
    """epub→txt 专用：内嵌图物化官方 txt 图注（`【圖：x.gif】`），
    无解 PUA 空位标记物化为 `□`（官方 txt 作 `◇`，归一同值）。
    均只在 txt 重组管线物化；extract/html/epub 侧保持空元素/无文本，
    与官方 html/epub 一致。"""
    raw = _FIG_IMG_RE.sub(lambda m: "【圖：" + m.group(2) + "】", raw)
    raw = _FIG_SPAN_RE.sub(lambda m: "【圖：" + m.group(2) + "】", raw)
    return _EMPTY_GAIJI_RE.sub("□", raw)


# 星号位空标记（HtmlRenderer._render_star_app 输出；文本抽取为空，
# html 比对不受影响；本模块按位复注块用）
_STAR_SPAN_RE = re.compile(
    r"<span\b[^>]*\bclass=(['\"])note-star\1[^>]*>", re.I)
_STAR_N_RE = re.compile(r"\bdata-n=(['\"])([^'\"]+)\1", re.I)
# 正文常规注记锚点：mod/orig 用 note_anchor_{n}，add 用 cb_note_anchor{seq}
_BODY_ANCHOR_RE = re.compile(
    r"<a\b[^>]*\bid=(['\"])(?:note_anchor_([^'\"]+)|cb_note_anchor(\d+))\1[^>]*>",
    re.I)
_FOOT_ID_RE = re.compile(r"\bid=(['\"])(n([^'\"]+)|cb_note_(\d+))\1", re.I)


def _epub_blobs(gen_paths):
    """逐个产出 epub/文件内的正文 xhtml 原始字符串（跳过 nav 等 boilerplate）。
    文件缺失/损坏（含非法 zip）跳过，不中断整批。"""
    for p in gen_paths or []:
        try:
            if p.lower().endswith(".epub"):
                with zipfile.ZipFile(p) as z:
                    for n in _epub_content_names(z):
                        yield z.read(n).decode("utf-8", "replace")
            else:
                yield open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue


def _epub_blob_parts(raw: str, bi: int):
    """单个 xhtml（已预处理）拆成 (body_raw, events, blocks)。

    body_raw：去注块后的正文（保留标签，供锚点扫描）。
    events：`[(bi, pos, kind, key)]`，kind=reg/add/star（正文锚点与星号位）。
    blocks：`[(bi, pos, kind, key, text)]`，kind=reg/add（None 为无 id 注块），
            text 为 `_foot_block_text` 结果，均按文档序。"""
    spans = _footnote_spans(raw)
    parts, prev = [], 0
    for s, e in spans:
        parts.append(raw[prev:s])
        prev = e
    parts.append(raw[prev:])
    body_raw = "".join(parts)
    events = []  # kind reg=note_anchor_n，add=cb seq，star=note n
    for m in _BODY_ANCHOR_RE.finditer(body_raw):
        if m.group(2) is not None:
            events.append((bi, m.start(), "reg", m.group(2)))
        else:
            events.append((bi, m.start(), "add", m.group(3)))
    for m in _STAR_SPAN_RE.finditer(body_raw):
        nm = _STAR_N_RE.search(m.group(0))
        if nm:
            events.append((bi, m.start(), "star", nm.group(2)))
    blocks = []
    for s, e in spans:
        b = raw[s:e]
        im = _FOOT_ID_RE.search(b[:b.find(">") + 1] if ">" in b else b)
        text = _foot_block_text(b)
        if im is None:
            blocks.append((bi, s, None, None, text))
        elif im.group(4) is not None:  # cb_note_N → add
            blocks.append((bi, s, "add", im.group(4), text))
        else:                          # nXXX → reg
            blocks.append((bi, s, "reg", im.group(3), text))
    return body_raw, events, blocks


def _reorder_epub_footnotes(raws) -> list:
    """epub 各章 html（已取 body）中的脚注块按**全局**正文锚点遭遇序重排。

    1 卷 html 经 mulu 拆多章（spine）后，背节整体落该卷末章，而锚点分散在
    前各章；官方 html 按**卷**（单文件）重排（`_reorder_html_footnotes`），
    故此处须跨章取全局锚点序。逐章：拆出注块与分隔文本，注块按匹配到的
    全局锚点位置重排（`add` 键按文档序 FIFO 消费，兼容各卷重号），无锚块
    垫底；分隔文本原位保留。无注块（<2 块）的章原样返回，零回归。"""
    events = {}  # key -> [(bi, pos), ...]（全局文档序）
    for bi, raw in enumerate(raws):
        spans = _footnote_spans(raw)
        parts, prev = [], 0
        for s, e in spans:
            parts.append(raw[prev:s])
            prev = e
        parts.append(raw[prev:])
        for m in _BODY_ANCHOR_RE.finditer("".join(parts)):
            key = ("reg", m.group(2)) if m.group(2) is not None \
                else ("add", m.group(3))
            events.setdefault(key, []).append((bi, m.start()))
    ptr = {}
    out = []
    for raw in raws:
        spans = _footnote_spans(raw)
        if len(spans) < 2:
            out.append(raw)
            continue
        segs, blocks, prev = [], [], 0
        for s, e in spans:
            segs.append(raw[prev:s])
            blocks.append(raw[s:e])
            prev = e
        segs.append(raw[prev:])
        keyed = []
        for i, b in enumerate(blocks):
            im = _FOOT_ID_RE.search(b[:b.find(">") + 1] if ">" in b else b)
            pos = None
            if im is not None:
                key = ("reg", im.group(3)) if im.group(3) is not None \
                    else ("add", im.group(4))
                lst = events.get(key)
                p = ptr.get(key, 0)
                if lst and p < len(lst):
                    pos = lst[p]
                    ptr[key] = p + 1
            keyed.append((pos if pos is not None else (len(raws), len(raw)), i, b))
        keyed.sort(key=lambda t: (t[0], t[1]))
        new_blocks = [b for _p, _i, b in keyed]
        out.append(segs[0] + "".join(
            new_blocks[k] + segs[k + 1] for k in range(len(new_blocks))))
    return out


def _join_epub_ours(gen_paths) -> str:
    """epub 生成侧正文+注块重组（**全局**阅读序）。

    解包内各 xhtml（跳过 nav 等 boilerplate），逐文件预处理后汇成全局正文与
    注块池，按全局正文锚点遭遇序交错注块（官方 txt“正文+注块”即阅读序）；
    星号位标记（note-star）按位复注块。单文件输出与旧逐块逻辑逐字节一致；
    跨文件/跨章（mulu 拆分致锚点与注块分处不同章节）亦归位到阅读序。
    docx/html/md/txt 不走这里。"""
    bodies = []
    events = []          # (bi, pos, kind, key)
    reg_queue = []       # [bi, pos, key, text]（key=None 为无 id 注块）
    add_pool = {}        # seq -> [text, ...]（文档序 FIFO）
    for bi, raw in enumerate(_epub_blobs(gen_paths)):
        # txt 形先物化悉昙读音/图注/无解缺字（官方 txt 裸读音+图注+◇；
        # html/epub 形保持空元素）
        raw = _materialize_figs_gaiji(_materialize_ranja(raw))
        raw = _prep_html_blob(raw, body_only=True)
        body_raw, ev, blocks = _epub_blob_parts(raw, bi)
        bodies.append(body_raw)
        events.extend(ev)
        for _b, pos, kind, key, text in blocks:
            if kind == "add":
                add_pool.setdefault(key, []).append(text)
            else:
                reg_queue.append([bi, pos, key, text])
    events.sort(key=lambda e: (e[0], e[1]))
    reg_first = {}
    for _bi, _pos, key, text in reg_queue:
        if key is not None:
            reg_first.setdefault(key, text)
    queue = list(reg_queue)
    out = []
    for _bi, _pos, kind, key in events:
        if kind == "star":
            dup = reg_first.get(key)
            if dup is not None:
                out.append(dup)
            continue
        if kind == "add":
            pool = add_pool.get(key)
            if pool:
                out.append(pool.pop(0))
            continue
        idx = next((i for i in range(len(queue)) if queue[i][2] == key), None)
        if idx is None:
            continue
        for i in range(idx + 1):
            out.append(queue[i][3])
        del queue[:idx + 1]
    for item in queue:
        out.append(item[3])
    body_text = "".join(
        _TAG_RE.sub("", re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", b,
                               flags=re.I)) for b in bodies)
    foot_text = "".join(out)
    if not foot_text.strip():
        return body_text
    return body_text + "\n" + foot_text


_TAG_OPEN_RE = re.compile(r"<(div|span)\b[^>]*>", re.I)
_TAG_CLOSE_RE = re.compile(r"</(div|span)\s*>", re.I)
_FOOT_OPEN_RE = re.compile(r"<(div|span)\b[^>]*\bclass='footnote'[^>]*>", re.I)


def _prep_html_blob(raw: str, body_only: bool = False) -> str:
    """html 文本预处理（`_split_html_text` 与星号位重组共用；逐字节一致）：
    body_only 时先取 `<body>` 内容，再去 style/ruby 与校注头。"""
    if body_only:
        m = re.search(r"<body[^>]*>(.*)</body>", raw, flags=re.S | re.I)
        if m:
            raw = m.group(1)
    raw = _STYLE_RE.sub("", raw)
    raw = _RUBY_RE.sub("", raw)
    raw = re.sub(r"<hr[^>]*>\s*<h1[^>]*>\s*校注\s*</h1>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<h1[^>]*>\s*校注\s*</h1>", "", raw, flags=re.I)
    return raw


def _split_html_text(raw: str, body_only: bool = False):
    """html 文本版 _extract_html_parts（输入已是字符串；文件版见该函数）：
    拆 (正文, 脚注)，去校注头。body_only=True 时先取 <body> 内容
    （去掉 <title>/nav 头文本；epub 重组专用，官方 txt 侧无此文本）。
    注记块按栈配平匹配（可含嵌套 div/span，如缺字 ruby），非嵌套输入下
    与旧非贪婪正则逐字节一致；未闭合的不收录（留正文）。
    注块按正文锚点遭遇序重排（顺序校注：官方 html 尾注数字块+A 块分组，
    与遭遇序产品对齐；单注/无锚输入原样返回，零回归）。"""
    raw = _prep_html_blob(raw, body_only=body_only)
    spans = _footnote_spans(raw)
    ordered = _reorder_footnote_spans(raw, spans)
    foot_text = ""
    for s, e in ordered:  # 注块按阅读顺序串联
        t = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", raw[s:e], flags=re.I)
        foot_text += _TAG_RE.sub("", t) + "\n"
    parts, prev = [], 0
    for s, e in spans:  # 正文按原始位置剔除注块（顺序无关）
        parts.append(raw[prev:s])
        prev = e
    parts.append(raw[prev:])
    body_raw = "".join(parts)
    body_raw = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", body_raw, flags=re.I)
    return _TAG_RE.sub("", body_raw), foot_text


def _footnote_spans(raw: str):
    """顶层 footnote div/span 块的 (start, end) 区间（栈配平，可含嵌套 div/span，
    如注记内的缺字 `<span class="gaiji">`；旧非贪婪正则会在内层闭标签提前截断，
    把注记尾部（含 `【聖】` 等）漏回正文）。
    未闭合的不收录（与旧行为一致，留正文）；自闭合不入栈；注释内标签不特殊处理
    （与旧一致）。"""
    events = []
    for m in _TAG_OPEN_RE.finditer(raw):
        if m.group(0).rstrip().endswith("/>"):
            continue
        tag = m.group(1).lower()
        events.append((m.start(), "open", tag,
                       bool(_FOOT_OPEN_RE.match(m.group(0))), m.end()))
    for m in _TAG_CLOSE_RE.finditer(raw):
        events.append((m.start(), "close", m.group(1).lower(), False, m.end()))
    events.sort(key=lambda e: e[0])
    spans = []
    stack = []
    for _pos, kind, tag, is_foot, end in events:
        if kind == "open":
            stack.append([tag, _pos, end, is_foot])
            continue
        while stack and stack[-1][0] != tag:
            stack.pop()
        if not stack:
            continue
        _otag, opos, _oend, ofoot = stack.pop()
        if ofoot and not any(s[3] for s in stack):
            spans.append((opos, end))
    return spans


def _reorder_footnote_spans(raw: str, spans: list) -> list:
    """注块 (start, end) 按正文锚点遭遇序重排（顺序校注）。

    官方 html 尾注按数字注块 + A 注块分组，与遭遇序产品不对齐；
    按正文锚点（`note_anchor_{n}`/`cb_note_anchor{seq}`）出现顺序重排注块，
    键口径与 `_join_epub_ours` 一致（reg→n，add→seq）。
    无锚条目 stable 垫底；少于 2 块或正文无锚时原样返回。"""
    if len(spans) < 2:
        return spans
    parts, prev = [], 0
    for s, e in spans:
        parts.append(raw[prev:s])
        prev = e
    parts.append(raw[prev:])
    body = "".join(parts)
    order = []
    for m in _BODY_ANCHOR_RE.finditer(body):
        if m.group(2) is not None:
            order.append(("reg", m.group(2)))
        else:
            order.append(("add", m.group(3)))
    if not order:
        return spans
    pos = {k: i for i, k in enumerate(order)}

    def key_of(span):
        s, e = span
        head = raw[s:s + 400]  # id 在开标签内
        im = _FOOT_ID_RE.search(head)
        if not im:
            return (len(order), s)
        k = ("reg", im.group(3)) if im.group(3) is not None \
            else ("add", im.group(4))
        return (pos.get(k, len(order)), s)

    return sorted(spans, key=key_of)


def _reorder_html_footnotes(raw: str) -> str:
    """html 注块物理重排为阅读顺序（抽取用；双侧同规，产品文件不动）。

    仅当注块连续（间隔纯空白）时就地重排（CBETA html 均如此）；
    否则原样返回（交由 `_split_html_text` 的 body/foot 拆分侧处理）。
    """
    spans = _footnote_spans(raw)
    if len(spans) < 2:
        return raw
    ordered = _reorder_footnote_spans(raw, spans)
    if ordered == spans:
        return raw
    for i in range(len(spans) - 1):
        if raw[spans[i][1]:spans[i + 1][0]].strip():
            return raw
    blocks = {sp: raw[sp[0]:sp[1]] for sp in spans}
    sep = raw[spans[0][1]:spans[1][0]]
    rebuilt = sep.join(blocks[sp] for sp in ordered)
    return raw[:spans[0][0]] + rebuilt + raw[spans[-1][1]:]


# 结构护栏：<w:p> 内层再开 <w:p>（或 <w:tbl> 落段内）为非法 OOXML，
# Word/WPS 会丢弃嵌套段落/表 → 文字在 raw XML 里（文本抽取假绿）但成品丢内容。
_WP_BLK_RE = re.compile(r"<w:p\b[^>]*?(/?)>|<w:tbl\b[^>]*?(/?)>|</w:p>|</w:tbl>")


def _nested_block_hits(xml: str, limit: int = 5) -> list:
    """document.xml/footnotes.xml 中非法嵌套块 → 上下文片段（最多 limit 条）。"""
    out = []
    p_depth = 0
    for m in _WP_BLK_RE.finditer(xml):
        tok = m.group(0)
        if tok.startswith("</w:p"):
            p_depth = max(0, p_depth - 1)
        elif tok.startswith("</w:tbl"):
            continue
        elif tok.startswith("<w:p"):
            if p_depth >= 1:
                out.append(_nested_ctx(xml, m.start()))
                if len(out) >= limit:
                    return out
            if not tok.endswith("/>"):
                p_depth += 1
        elif tok.startswith("<w:tbl") and p_depth >= 1:
            out.append(_nested_ctx(xml, m.start()))
            if len(out) >= limit:
                return out
    return out


def _nested_ctx(xml: str, i: int, before: int = 60, after: int = 90) -> str:
    """违规点上下文（压缩空白；含邻近文字，便于定位）。"""
    return re.sub(r"\s+", " ", xml[max(0, i - before):i + after]).strip()


def docx_nested_block_violations(path: str, limit: int = 5) -> list:
    """docx 非法嵌套块（段中段/表中段）→ 定位片段列表。
    扫描 word/document.xml + word/footnotes.xml；表格单元格内的 <w:p> 合法
    （tbl 在 p 外），不误报。文件缺失/损坏 → []。"""
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            for name in ("word/document.xml", "word/footnotes.xml"):
                try:
                    xml = z.read(name).decode("utf-8", "replace")
                except KeyError:
                    continue
                hits = _nested_block_hits(xml, limit - len(out))
                out.extend(f"{name}: {h}" for h in hits)
                if len(out) >= limit:
                    break
    except (OSError, zipfile.BadZipFile):
        return []
    return out[:limit]


_INFO_MARKS = ("【版本記錄】", "【編輯說明】", "【原始資料】", "【版權宣告】", "【製作說明】", "【其他事項】")

def strip_infos(text: str) -> str:
    """剥离全部【經文資訊】信息块（每块独立：本块起至其最后一个信息标记的行尾，
    不超过下一个【經文資訊】），保留其后可能存在的校注/脚注内容。"""
    out = []
    while True:
        idx = text.find("【經文資訊】")
        if idx == -1:
            out.append(text)
            break
        out.append(text[:idx])
        seg = text[idx:]
        nxt = seg.find("【經文資訊】", 1)
        limit = nxt if nxt != -1 else len(seg)
        pos = 0
        end = limit
        while True:
            best = limit
            for mk in _INFO_MARKS:
                p = seg.find(mk, pos)
                if p != -1 and p < best:
                    best = p
            if best >= limit:
                break
            nl = seg.find("\n", best)
            end = nl if nl != -1 and nl < limit else limit
            pos = best + 1
        text = seg[end:]
    return "".join(out)

def strip_docx_head(text: str, title: str, docnumber: str = "", series: str = "") -> str:
    """元素级整行剥离（绝不子串替换，保护 "No. 1116-A" 等正文内容）：
    - docNumber 元素全文整行（官方 docx 渲染为独立段落行）
    - 整行==书名的卷首标题行（官方多卷每卷开头重复书名）
    - 整行==经藏名的首页行（title level="s"）"""
    if docnumber:
        text = re.sub(r'(?m)^[ \t]*' + re.escape(docnumber) + r'[ \t]*$', '', text)
    if title:
        text = re.sub(r'(?m)^[ \t]*' + re.escape(title) + r'[ \t]*$', '', text)
    if series:
        text = re.sub(r'(?m)^[ \t]*' + re.escape(series) + r'[ \t]*$', '', text)
    return text

def merge_docx(paths: List[str], out_path: str) -> str:
    """将多卷官方 docx 合并为单个 docx：body 依次拼接、footnotes 统一放文末，
    抽取 TXT 时脚注全部位于页尾，与生成单文件 docx 对齐。"""
    z0 = zipfile.ZipFile(paths[0])
    doc0 = z0.read("word/document.xml").decode("utf-8")

    def _body_children(xml: str) -> str:
        i = xml.find("<w:body>")
        j = xml.rfind("</w:body>")
        seg = xml[i + len("<w:body>"):j] if i != -1 and j != -1 else ""
        return re.sub(r"<w:sectPr>.*?</w:sectPr>\s*$", "", seg, flags=re.S)

    segs = []
    foots = []
    for p in paths:
        z = zipfile.ZipFile(p)
        d = z.read("word/document.xml").decode("utf-8")
        segs.append(_body_children(d))
        try:
            fn = z.read("word/footnotes.xml").decode("utf-8")
            foots.extend(re.findall(r"<w:footnote[ >].*?</w:footnote>", fn, flags=re.S))
        except KeyError:
            pass
    sect = re.search(r"<w:sectPr>.*?</w:sectPr>", doc0, flags=re.S)
    head = doc0[:doc0.find("<w:body>")]
    merged_doc = head + "<w:body>" + "".join(segs) + (sect.group(0) if sect else "") + "</w:body></w:document>"
    merged_fn = ""
    try:
        fn0 = z0.read("word/footnotes.xml").decode("utf-8")
        open_tag = fn0[:fn0.find(">") + 1]
        merged_fn = open_tag + "".join(foots) + "</w:footnotes>"
    except KeyError:
        pass
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zo:
        for n in z0.namelist():
            if n == "word/document.xml":
                zo.writestr(n, merged_doc)
            elif n == "word/footnotes.xml":
                if merged_fn:
                    zo.writestr(n, merged_fn)
            else:
                zo.writestr(n, z0.read(n))
    return out_path

def diff_stats(ours: str, theirs: str, max_ctx: int = 5):
    """ours=生成档文本, theirs=官方文本。
    missing=生成档缺失（官方有而生成档无），extra=生成档多出（生成档有而官方无）。
    ctx 只取前 max_ctx 条非 equal opcode（报告片段数；缺/多计数不受影响）。

    性能：先裁最长公共前缀 P / 公共后缀 S（O(n) 扫描），仅对中段做
    `SequenceMatcher`，matched = P + S + 中段 matched；返回的 ctx 索引整体 +P。
    同作品真实比对（高相似、差异局部）下与全文结果**逐对相同**（291 对实证），
    耗时约 1/16；差异集中在两端时近乎零成本。串全等时中段空、ctx=[]。
    注：对“几乎无关”的两串（非校验场景），difflib 的分块启发式偶有 ±3 字出入；
    校验恒为同作品（stem 匹配）比对，不触发。"""
    n = min(len(ours), len(theirs))
    p = 0
    while p < n and ours[p] == theirs[p]:
        p += 1
    s = 0
    while s < n - p and ours[len(ours) - 1 - s] == theirs[len(theirs) - 1 - s]:
        s += 1
    mid_o = ours[p:len(ours) - s]
    mid_t = theirs[p:len(theirs) - s]
    sm = difflib.SequenceMatcher(None, mid_o, mid_t, autojunk=False)
    matched = p + s + sum(op.size for op in sm.get_matching_blocks())
    missing = len(theirs) - matched
    extra = len(ours) - matched
    ctx = [(op[0], op[1] + p, op[2] + p, op[3] + p, op[4] + p)
           for op in sm.get_opcodes() if op[0] != "equal"][:max_ctx]
    return matched, missing, extra, ctx


def trial_pass_line(bkind: str, mi: int, ex: int, total: int, max_diff: int) -> str:
    """trial 通过行（阈值内）：0/0 记逐字完全一致；非 0/0 如实打出缺/多数。

    不再断言“仅含CBETA版本日期/版权等元数据微小差异”——差异性质由随后
    的差异片段自行举证（调用方在 total>0 时照常附片段）。"""
    if total > 0:
        return (f"      → {bkind} 通过: 缺{mi}字(生成档缺失) / 多{ex}字"
                f"(生成档多出)，合计{total} ≤阈值{max_diff}")
    return f"      → {bkind} 通过: 逐字完全一致"

def work_juan_numbers(work) -> set:
    """work.body 中 <milestone unit="juan" n="…"> 的卷号集合
    （用于把官方基线限定到 XML 实际覆盖的卷数，如 TX07n0006 → {1..6}）。"""
    out = set()

    def walk(nodes):
        for n in nodes:
            if isinstance(n, E) and n.tag == "milestone" and n.attrs.get("unit") == "juan":
                try:
                    out.add(int(n.attrs.get("n")))
                except (TypeError, ValueError):
                    pass
            elif getattr(n, "children", None):
                walk(n.children)

    walk(getattr(work, "body", []))
    return out


_NOTE_LINE_RE = re.compile(r"^ {4}\[[^\]\[]{1,12}\]")


def _extract_txt_parts(text: str):
    """官方 txt/txt_notes 分段为 (正文, 注记)：把段后注记块（`^    [...]` 行）移至文末，
    镜像 _extract_html_parts（html 以 class='footnote' 判定，此处以 4 格缩进判定）。

    全库验证结论：4 格缩进非 `[` 行零出现；行首 `[n]`（标题/署名/偈锚）全是正文，
    必须靠缩进区分；注记括号形态为纯数字/`A\\d+`/`\\d+[a-z]`/`＊N-M`；注记恒单行。
    我方 md/html/docx 生成侧注记都在文末，移位后两边同构（正文+注记）再比对。
    经 `_norm_official_txt` 繁简通用调用；无注记行为无操作。"""
    bodies, notes = [], []
    for ln in text.split("\n"):
        if _NOTE_LINE_RE.match(ln):
            notes.append(ln)
        else:
            bodies.append(ln)
    return "\n".join(bodies), "\n".join(notes)


_TXT_HEAD_RE = re.compile(r"\A(#.*\n|[ \t]*\n)+")


def _strip_txt_head(text: str) -> str:
    """官方 txt/txt_notes 版头剥离：文件开头连续 `#` 注释行（CBETA 导出出版块，
    经 strip_infos 后只剩 `#---/#` 残留，同样在此剥离）+ 空行。
    生成侧无此块；文中的 `#` 行不动（`\\A` 只锚定开头块）；CBETA 正文永不以 `#` 开头。"""
    return _TXT_HEAD_RE.sub("", text)


def _norm_official_txt(text: str) -> str:
    """官方 txt/txt_notes 侧对齐（繁简通用）：版头剥离 + 注记块识别挪文末，
    与生成侧正文+注块同构；无注记行为无操作。渲染侧零触碰。
    （注：`No.` 行不搬移——生成侧 docNumber 本就在体首，双方同序。）
    """
    text = _strip_txt_head(text)
    tb, tn = _extract_txt_parts(text)
    return tb + "\n" + tn if tn.strip() else tb


_MD_FN_RE = re.compile(r"\[\^\d+\]: ")


def _strip_md_marks(text: str) -> str:
    """生成侧 md 标记剥离（md 种专用）：`## 校注` 块头 + `[^n]: ` 定义标记。
    官方侧无此标记体系；正文 `[^n]` 引用由 normalize 通规则处理。此处只动精确字面，安全退化。"""
    text = text.replace("\n\n## 校注\n\n", "\n\n", 1)
    return _MD_FN_RE.sub("", text)


#: 各格式校验基线链（首选→回退；官方有变改配置 verify.bases 即可，不改代码）
DEFAULT_BASES = {
    "md": ["txt_notes", "html"],
    "docx": ["docx", "html"],
    "html": ["html"],
    "txt": ["txt_notes"],
    "epub": ["txt_notes", "epub", "html"],
}
#: 首选基线缺失时按需下载的格式（跟链首走）
NEED_BY_KIND = {
    "txt_notes": ["txt_notes"],
    "docx": ["docx", "html"],
    "html": ["html"],
    "epub": ["epub"],
}
_KNOWN_BASE_KINDS = frozenset(("html", "txt_notes", "docx", "epub", "odt"))


def chain_for(fmt, chains=None):
    """fmt 的基线链：配置 verify.bases[fmt]（缺键/空/非法回退默认表），
    非法 kind 丢弃、保序去重，恒非空。"""
    c = chains.get(fmt) if isinstance(chains, dict) else None
    if isinstance(c, list) and c:
        seen, out = set(), []
        for k in c:
            if isinstance(k, str) and k in _KNOWN_BASE_KINDS and k not in seen:
                seen.add(k)
                out.append(k)
        if out:
            return out
    return list(DEFAULT_BASES.get(fmt, ["html"]))


def resolve_bases(fmt, official, chains=None):
    """基线 trial 链：链序 ∩ 本地现货，保序；同路径去重。返回 [(kind, paths)]。"""
    chain = chain_for(fmt, chains)
    seen_paths, out = [], []
    for k in chain:
        v = (official or {}).get(k)
        if v and all(p != v for p in seen_paths):
            seen_paths.append(v)
            out.append((k, v))
    return out


def need_for_base(base_kind):
    """首选基线缺失时按需下载的格式（跟链首走）。"""
    return list(NEED_BY_KIND.get(base_kind, ["html"]))


def _head_no_tokens(work) -> list:
    """work 全部 head/jhead 行首 No. 令牌 + docNumber 整行文本（去重保序；
    `output.strip_head_no` 官方侧对等剥离用）。
    生成侧 strip_head_no 开启时 head/jhead 剥令牌、docNumber 整元素省略，
    故官方侧需按同表对等剥离。同输入必同值；无命中返回 []。"""
    out = []
    t_doc = (work.metadata.get("docNumber") or "").strip() if hasattr(work, "metadata") else ""
    if t_doc:
        out.append(t_doc)
    stack = list(getattr(work, "body", []) or [])
    while stack:
        n = stack.pop(0)
        if isinstance(n, E) and n.tag in ("head", "jhead"):
            _, token = strip_head_no(n.children)
            if token and token not in out:
                out.append(token)
        stack[0:0] = list(getattr(n, "children", []) or [])
    return out


def _strip_official_no(text: str, tokens) -> str:
    """官方侧对等剥离：行首精确令牌逐个移除（与生成侧逐 head/jhead 剥离同构）。
    允许行首横向空白并保留（官方 html 提取行常带前导空格）；连带 token 后的
    横向空白一起吃掉，使官方侧余部与生成侧形状一致。空表时原样返回。"""
    if not tokens:
        return text
    # 长 token 先剥（`No. 1651-10` 先于 `No. 1651-1`，否则短 token 会吃掉
    # 长 token 前缀只剩 `0`）；词边界 `(?![0-9A-Za-z-])` 防部分匹配
    for token in sorted(tokens, key=len, reverse=True):
        text = re.sub(
            r"(?m)^([ \t\u3000]*)" + re.escape(token)
            + r"(?![0-9A-Za-z\-])[ \t\u3000]*",
            r"\1", text)
    return text


def _strip_no_from(config_path=None) -> bool:
    """strip_head_no 开关读取（--config 双形态兼容，生成/官方双侧同源）。
    presets 文件直读 output 槽；run.json 走组合单解算；任一为 true 即 true，全缺省 false。"""
    try:
        p = load_presets(config_path) if config_path else load_presets()
        if (p.get("output") or {}).get("strip_head_no", False):
            return True
    except Exception:
        pass
    try:
        from .theme import load_run_config, resolve_effective_config, default_run_path
        run = load_run_config(config_path) if config_path else load_run_config()
        rdir = os.path.dirname(os.path.abspath(config_path)) if config_path \
            else os.path.dirname(os.path.abspath(default_run_path()))
        if (resolve_effective_config(run, rdir).get("output") or {}).get("strip_head_no", False):
            return True
    except Exception:
        pass
    return False


_XML_INLINE_NOTE_PLACES = ("inline", "inline2", "interlinear")
_XML_NOTE_ORDER = ("mod", "orig", "add", "equivalent", "rest")
_XML_DROP_TAGS = ("app", "anchor", "mulu")
_WS_RE = re.compile(r"[\s　]+")


def _extract_xml_parts(path: str, inline_brackets: str = "fullwidth",
                       show_dharani_transliteration: bool = False):
    """P3 辅轨：官方 XML 直抽为 (title, author, body, foots)。

    异构实现（lxml 直读，不走 P5Parser；规则镜像 parser/render_txt 的可观测行为，
    共享的只有缺字数据 GaijiDb 与版头选取语义）：
    - 仅走 text/body；back 只作注池（与 parser _collect_back 对应）；
    - 文本节点空白归一（`[\\s　]+`→""，与 Text→txt 同规则；tail 同收；注释/PI 跳过节点留 tail）；
    - body 内 <note>：行内 place 才保留子文本，其余整棵丢弃（镜像 _render_inline_note）；
    - <app>/<anchor>/<mulu> 整棵丢弃（生成侧恒空：back-app 无 corresp 即 ""；anchor 转 NoteRef/空 E）；
      例外：body 内无 from/corresp 的 app 收子文本（parser 不进 _parse_app，渲染泛型分支直吐 lem/rdg）；
    - <unclear>→□；<g> 经 GaijiDb+charDecl 解析（与 _resolve_gaiji_raw 同优先级）；
    - 其余元素默认收子文本（镜像 _render_e 默认分支）；
    - 注块顺序镜像生成侧：body anchor 文档序（nkr_note_ 去重 + beg 位 app-corresp），
      back 注按 n= 分组、mod>orig>add>equivalent>rest 单选（镜像 _pick_note）。
    - 版头 title/author 选取与 _parse_header 同规则（level=m 中文优先；author 直取）。
    """
    from lxml import etree

    def ln(e):
        return etree.QName(e).localname if isinstance(e.tag, str) else ""

    tree = etree.parse(path)
    root = tree.getroot()

    def find_first(el, name):
        for c in el.iter():
            if ln(c) == name:
                return c
        return None

    header = find_first(root, "teiHeader")
    title, author = "", ""
    chard = {}
    if header is not None:
        ts = None
        for c in header.iter():
            if ln(c) == "titleStmt":
                ts = c
                break
        if ts is not None:
            titles = [c for c in ts if ln(c) == "title"]

            def _lang(t):
                return t.get("{http://www.w3.org/XML/1998/namespace}lang") or t.get("lang") or ""

            for t in titles:
                if t.get("level") == "m" and _lang(t).startswith("zh"):
                    title = "".join(t.itertext()).strip()
                    break
            if not title:
                for t in titles:
                    if t.get("level") == "m":
                        title = "".join(t.itertext()).strip()
                        break
            if not title and titles:
                title = "".join(titles[0].itertext()).strip()
            au = next((c for c in ts if ln(c) == "author"), None)
            if au is not None:
                author = "".join(au.itertext()).strip()
        cd = find_first(header, "charDecl")
        if cd is not None:
            for ch in cd.iter():
                if ln(ch) != "char":
                    continue
                cid = (ch.get("{http://www.w3.org/XML/1998/namespace}id")
                       or ch.get("id") or "").lstrip("#")
                if not cid:
                    continue
                rec = {}
                for cp in ch.iter():
                    if ln(cp) != "charProp":
                        continue
                    name_el = next((x for x in cp if ln(x) == "localName"), None)
                    val_el = next((x for x in cp if ln(x) == "value"), None)
                    name = (name_el.text or "") if name_el is not None else ""
                    val = (val_el.text or "") if val_el is not None else ""
                    if name == "composition":
                        rec["composition"] = val
                    elif name == "normalized form":
                        rec["normal"] = val
                    elif name == "Romanized form in Unicode transcription":
                        rec["roman"] = val
                    elif name == "Romanized form in CBETA transcription":
                        rec["roman_cbeta"] = val
                for mp in ch.iter():
                    if ln(mp) != "mapping":
                        continue
                    t = mp.get("type")
                    if t == "unicode":
                        rec["unicode"] = (mp.text or "").replace("U+", "")
                    elif t == "PUA":
                        rec["pua"] = mp.text or ""
                chard[cid] = rec

    try:
        from .gaiji import GaijiDb
        _gdb = GaijiDb()
    except Exception:
        _gdb = None

    def resolve_gaiji(code, raw):
        rec = chard.get(code) or {}
        if rec.get("roman") or rec.get("roman_cbeta"):
            # 悉昙缺字：官方 txt 裸读音（如 raṃ），与 TxtRenderer 同规则
            return (rec.get("roman") or rec.get("roman_cbeta")).strip()
        if code.startswith("RJ"):
            # 无法表示的悉昙字：官方 text-with-notes 占位 ◇，与 TxtRenderer 同规则
            return "\u25c7"
        data = _gdb.get(code) if _gdb else None
        if data:
            for k in ("unicode", "norm_unicode"):
                v = data.get(k)
                if v:
                    try:
                        return chr(int(v, 16))
                    except ValueError:
                        pass
            for k in ("norm_big5_char", "norm_uni_char", "uni_char", "composition"):
                v = data.get(k)
                if v:
                    return v
            m = re.match(r"U\+([0-9A-Fa-f]+)", data.get("pua") or "")
            if m:
                return chr(int(m.group(1), 16))
        rec = chard.get(code) or {}
        if rec.get("unicode"):
            try:
                return chr(int(rec["unicode"], 16))
            except ValueError:
                pass
        if rec.get("normal"):
            return rec["normal"]
        if rec.get("composition"):
            return rec["composition"]
        return raw

    def chunks(el, out, in_dharani=False):
        """子树文本走查（镜像 _render_node 可观测行为），结果 append 到 out。"""
        if el.text:
            out.append(_WS_RE.sub("", el.text))
        for child in el:
            if not isinstance(child.tag, str):
                # 注释/PI：跳过节点，tail 照收（与 parser _traverse 一致）
                if child.tail:
                    out.append(_WS_RE.sub("", child.tail))
                continue
            t = ln(child)
            if t == "note":
                if child.get("place") in _XML_INLINE_NOTE_PLACES:
                    lb, rb = ("(", ")") if inline_brackets == "halfwidth" else ("（", "）")
                    out.append(lb)
                    chunks(child, out, in_dharani)
                    out.append(rb)
                # 非行内注整棵丢弃（body 内注生成侧恒 ""；back 注走注池）
            elif t == "tt" and (child.get("place") or "") != "inline" \
                    and not show_dharani_transliteration:
                # 逐字咒文表（无 place="inline"）内转写默认不显示（镜像 render_txt/md）
                chunks(child, out, in_dharani=True)
            elif t == "app":
                # 正文内联校勘（P5a/P5b，如 CBReader 書庫）：base 读法只在 <lem>，
                # 渲染侧只出 lem（见 render_*.py _render_e），此处镜像只收 lem 子文本；
                # rdg 是异读不进正文。back 内的 app 不走此分支（anchor 序另处理）。
                lem = next((c for c in child
                            if isinstance(c.tag, str) and ln(c) == "lem"), None)
                if lem is not None:
                    chunks(lem, out, in_dharani)
            elif t in _XML_DROP_TAGS:
                pass
            elif t == "graphic":
                # 图注标记（官方 txt 同款），与 TxtRenderer._figure_mark 同规则
                url = (child.get("url") or "").replace("\\", "/")
                base = url.split("/")[-1] if url else ""
                if base:
                    out.append(f"【圖：{base}】")
            elif t == "figure":
                for c in child:
                    if isinstance(c.tag, str) and ln(c) == "graphic":
                        url = (c.get("url") or "").replace("\\", "/")
                        base = url.split("/")[-1] if url else ""
                        if base:
                            out.append(f"【圖：{base}】")
                    else:
                        chunks(c, out, in_dharani)
                    if c.tail:
                        out.append(_WS_RE.sub("", c.tail))
            elif t == "sg":
                # 梵呗注音（<cb:sg>）：官方半角括号（与 render_txt 同规则）
                out.append("(")
                chunks(child, out, in_dharani)
                out.append(")")
            elif t == "unclear":
                out.append("□")
            elif t == "g":
                code = (child.get("ref") or "").lstrip("#")
                raw = _WS_RE.sub("", "".join(child.itertext())) or code
                if in_dharani and not show_dharani_transliteration \
                        and code.startswith("RJ"):
                    pass  # 逐字咒文表悉昙整行不显示（与 TxtRenderer 同规则）
                else:
                    out.append(resolve_gaiji(code, raw))
            else:
                chunks(child, out, in_dharani)
            if child.tail:
                out.append(_WS_RE.sub("", child.tail))

    text_el = find_first(root, "text")
    body = back = None
    if text_el is not None:
        for c in text_el:
            if not isinstance(c.tag, str):
                continue
            if ln(c) == "body" and body is None:
                body = c
            elif ln(c) == "back" and back is None:
                back = c

    # back 注池：{n: [note]}（与 _collect_back 对应）
    pool = {}
    if back is not None:
        for e in back.iter():
            if isinstance(e.tag, str) and ln(e) == "note":
                pool.setdefault(e.get("n"), []).append(e)
    # back app 表：{from-id: corresp-n}（与 _parse_app key 对应）
    apps = {}
    if back is not None:
        for e in back.iter():
            if isinstance(e.tag, str) and ln(e) == "app":
                frm = (e.get("from") or "").lstrip("#")
                if frm:
                    apps[frm] = (e.get("corresp") or "").lstrip("#") or None

    def pick(n):
        cands = pool.get(n) or []
        for want in _XML_NOTE_ORDER:
            for e in cands:
                if e.get("type") == want:
                    return e
        return None

    def note_text(e):
        out = []
        chunks(e, out)
        return "".join(out)

    body_chunks, foots = [], []
    seen_n = set()
    if body is not None:
        pre = []
        chunks(body, pre)  # 占位：正文走查另行处理 anchor 顺序，见下
        # anchor 顺序注块（镜像 NoteRef/_render_app 落子顺序）
        for e in body.iter():
            if not isinstance(e.tag, str):
                continue
            if ln(e) != "anchor":
                continue
            aid = (e.get("{http://www.w3.org/XML/1998/namespace}id")
                   or e.get("id") or "")
            if aid.startswith("nkr_note_"):
                n = e.get("n")
                if n and n not in seen_n:
                    seen_n.add(n)
                    hit = pick(n)
                    if hit is not None:
                        foots.append(note_text(hit))
            elif aid.startswith("beg"):
                cn = apps.get(aid)
                if cn:
                    hit = pick(cn)
                    if hit is not None:
                        foots.append(note_text(hit))
        # 正文：anchor 本身无文本贡献（NoteRef 落 ""；App 无 corresp 落 ""），
        # 故 chunks(body) 已是正文（anchor 子文本恒空，drop 与否无差）
        body_chunks = pre
    return title, author, "".join(body_chunks), foots


def find_official(source: str, stem: str, kind: str, juan: Optional[set] = None,
                  extra_roots=()) -> List[str]:
    """官方基线发现：短名回退/`_NNN` 优先/卷范围限定；统一根目录下平展优先、仓库次之。

    多根：`extra_roots`（配置的各格式基线目录，如 2026r2）在前、`source`（输入
    相邻目录，旧行为）在后，逐根独立跑发现流程，**首个非空根胜出**（跨根不合并，
    避免同内容重复文件导致注块翻倍假挂；缺键/空串=未配置，直走旧行为）。

    说明：不按目录名排除任何路径（曾排除 `out/`，但工作根本身就可能叫 out，
    误杀整库且用户无从得知；现彻底去掉该隐藏限制）。
    唯一例外：`*（验证）*/`（校验产物目录，正式比对档与基线同 stem，
    不排除会自比对假绿）。"""
    for root in ([r for r in (extra_roots or []) if r] + [source]):
        found = _find_official_in(root, stem, kind, juan)
        if found:
            return found
    return []


def _find_official_in(source: str, stem: str, kind: str,
                      juan: Optional[set] = None) -> List[str]:
    """单根发现（原 find_official 本体；多根时逐根调用）。"""
    short = ""
    m = re.match(r"^([A-Z]+)\d+n(.+)$", stem)
    if m:
        short = m.group(1) + m.group(2)
        stems = [stem, short]
    else:
        stems = [stem]
    pats = []
    for s in stems:
        if kind == "txt_notes":
            # 官方 text-with-notes：新布局 `{work}/txt/{s}_NNN.txt`；
            # 兼容旧布局 `{s}.txt_notes/` 与平铺 `{s}.txt`；
            # 2026r2 集中库布局 `{letter}/{s}/{s}_NNN.txt`（无 txt/ 中间层）。
            pats += [os.path.join(source, "**", "txt", f"{s}_*.txt"),
                     os.path.join(source, "**", "txt", f"{s}.txt"),
                     os.path.join(source, "**", s, f"{s}_*.txt"),
                     os.path.join(source, "**", f"{s}.txt_notes", "*.txt"),
                     os.path.join(source, "**", f"{s}.txt_notes")]
        else:
            pats.append(os.path.join(source, "**", f"{s}*.{kind}"))
    out, seen = [], set()
    # 自产文件排除（与基线同名会误命中）：
    # 1) *（验证）*/ —— 校验正式比对档；
    # 2) 文件名含空格 —— 我方渲染产物 `{id 书名}.ext` 恒带空格，官方文件名恒无空格；
    # 3) `{stem}_html/`、`{short}_html/` 目录 —— HtmlRenderer 默认输出目录。
    html_dirs = {f"{s}_html" for s in (stems or []) if s}
    for pat in pats:
        for f in sorted(glob.glob(pat, recursive=True)):
            af = os.path.abspath(f)
            if "（验证）" in af or "（驗證）" in af:
                # 校验产物目录（CLI/GUI 的 `{id 书名}（验证）/`）不得当基线：
                # 正式比对档与基线同 stem，自比对会假绿
                continue
            if " " in os.path.basename(af):
                continue
            parts = af.split(os.sep)
            if any(p in html_dirs for p in parts):
                continue
            if af not in seen and os.path.isfile(af) and os.path.getsize(af) > 0:
                seen.add(af)
                out.append(af)
    # 两档排序（统一根目录下）：平展优先——顶层条目名以 work id（短名，如 YP0021）
    # 或 stem 开头的命中排前面，如 `YP0021 異部宗輪論語體釋\\YP0021.html`；
    # 仓库布局（如 `T\\T0349\\html\\T0349_001.html`，下载落盘即此布局）次之。
    # 后续后缀优先/卷过滤只做筛选，保持此相对顺序。
    prefixes = tuple(p for p in (short, stem) if p)
    src_abs = os.path.abspath(source)

    def _is_flat(f: str) -> bool:
        rel = os.path.relpath(os.path.abspath(f), src_abs)
        return rel.split(os.sep)[0].startswith(prefixes)
    out = [f for f in out if _is_flat(f)] + [f for f in out if not _is_flat(f)]
    # CBETA 官方 dump 命名带 _NNN 后缀（如 T0349_001.docx）；本管线生成档不带后缀
    # （如 T0349.docx）。两者并存时只取带后缀的官方文件，避免把生成档误当基线。
    suffixed = [f for f in out if re.search(r"_\d+(\.\w+)?$", f)]
    if suffixed and any(f not in suffixed for f in out):
        out = suffixed
    # 卷范围限定：XML 实际覆盖的卷号 → 官方 _NNN 文件（如 TX07n0006 卷1-6 → TX0006_001..006.html，
    # 而非整编 49 文件）。txt_notes 文件同为 {id}_NNN.txt 命名，一并过滤。过滤后为空
    # （官方按冊分卷等命名不对应）则回退不过滤。
    if juan and kind in ("html", "docx", "txt_notes"):
        scoped = []
        for f in out:
            m = re.search(r"_(\d+)\.\w+$", os.path.basename(f))
            if m and int(m.group(1)) in juan:
                scoped.append(f)
        if scoped:
            out = scoped
    return out

def _epub_mulu_levels(pg):
    """epub 拆 spine 用的 mulu level 集合（与 CLI 同口径）。"""
    pg = pg or {}
    if pg.get("enabled", True) is False:
        return ()
    from .render_docx import _mulu_levels
    return tuple(sorted(_mulu_levels(pg)))


def _epub_zhang_break(pg):
    """epub 章信号拆 spine：R2 开关（默认开）且 R1 开（与 CLI 同口径）。"""
    pg = pg or {}
    if pg.get("enabled", True) is False:
        return False
    if not _epub_mulu_levels(pg):
        return False
    return bool(pg.get("mulu_zhang_break", True))


def generate_formal(xml_fn: str, work, fmt: str, outdir: str, config_path: Optional[str] = None, overrides: Optional[dict] = None) -> List[str]:
    """正式管线生成，返回生成档路径列表（html 按卷多个文件，其余单元素）。"""
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(xml_fn))[0]
    presets = {}
    _run = None
    _rdir = None
    try:
        from .theme import (resolve_config_arg,
                            resolve_effective_config)
        # 宽容分流：run.json 或基础配置 JSON（纯 presets）都认；与 CLI 同口径
        _run, _rdir = resolve_config_arg(config_path)
        presets = resolve_effective_config(_run, _rdir)
        out_defaults = {**(presets.get("output") or {}), **(presets.get("verify") or {})}
    except Exception:
        try:
            presets = load_presets()
            out_defaults = {**(presets.get("output") or {}), **(presets.get("verify") or {})}
        except Exception:
            from .theme import OUTPUT_PRESETS as _DO, VERIFY_PRESETS as _DV
            out_defaults = {**dict(_DO), **dict(_DV)}
    if overrides:
        out_defaults = {**out_defaults, **overrides}
    if "inline_brackets" not in ((presets or {}).get("verify") or {}) and \
            not (overrides and "inline_brackets" in overrides):
        # verify 缺键强制半角：output.* 的全角不透入校验管线（官方基线恒半角）；
        # 显式 verify.inline_brackets 照走（有键不碰）
        out_defaults["inline_brackets"] = "halfwidth"
    # 注音透传（P6）：开启后校验实际产出（提取/归一侧剥除注音，比对无影响）
    try:
        from .annotate import resolve_annotations
        _ann = resolve_annotations((presets or {}).get("annotations"), config_path or _PRESETS_PATH)
    except Exception:
        _ann = None
    theme = None
    # 主题跟随 run.json 的 pdf-docx 槽（与主程序一致；字体系与提取文本无关，
    # lang 恒繁体）；html/epub 恒纯基底，不吃主题
    if fmt in ("docx", "md", "txt") and _run is not None:
        try:
            from .theme import resolve_pdf_docx_css, Theme as _Theme
            theme = _Theme.from_css(resolve_pdf_docx_css(_run, _rdir), "zh-Hant")
        except (OSError, ValueError):
            theme = None
    p = lambda k, d=None: out_defaults.get(k, d)
    _shn = _strip_no_from(config_path)
    # 图片搜索目录（与生产一致；文本比对不受图片影响，仅保证生成档一致）
    try:
        from .figures import work_figure_dirs
        _ebook = ((presets or {}).get("source") or {}).get("cbeta_ebook")
        _fig_dirs = work_figure_dirs(_ebook, work.id, xml_fn)
    except Exception:
        _fig_dirs = []
    # 校验恒比注：忽略 output.show_notes（转换时取消「显示注释」不改变校验内容；
    # 官方基线含注，若生成档不带注会误报大量差异）
    # 括号口径缺省半角：官方基线恒半角括号；配置缺 verify.inline_brackets
    # （如 publish 临时预设）时向官方对齐，不回退全角
    if fmt == "html":
        from .fetch import title_t2s as _tt
        files = HtmlRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=True, inline_brackets=p("inline_brackets", "halfwidth"), annotations=_ann, strip_head_no=_shn, siddham_text=bool(p("siddham_text", False)), title_t2s=bool(_tt(presets)), pre_dedent=bool(p("pre_dedent", False)), pre_dedent_spaces=p("pre_dedent_spaces", 4), figure_base=_fig_dirs or None).render_work(work, out_dir=outdir)
        return [os.path.join(outdir, f) for f in files]
    if fmt == "docx":
        return [os.path.join(outdir, DocxRenderer(theme=theme, notes="footnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=True, suppress_jhead_dup=p("suppress_jhead_dup", True), show_close_juan=bool(p("show_close_juan", False)), inline_brackets=p("inline_brackets", "halfwidth"), note_inline_brackets=p("note_inline_brackets", None), series_title=p("series_title", {}), pagination=p("pagination", {}), verse_caesura=p("verse_caesura", "　　"), verse_strip_quotes=bool(p("verse_strip_quotes", False)), footnote_per_page=p("footnote_per_page", True), vertical=bool(p("vertical", False)), annotations=_ann, strip_head_no=_shn, show_body_siddham=bool(p("show_body_siddham", True)), pre_dedent=bool(p("pre_dedent", False)), pre_dedent_spaces=p("pre_dedent_spaces", 4), title_smart_wrap=bool(p("title_smart_wrap", True)), figure_base=_fig_dirs or None).render_work(work, out_dir=outdir, filename=f"{stem}.docx"))]
    if fmt == "epub":
        return [os.path.join(outdir, EpubRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=True, inline_brackets=p("inline_brackets", "halfwidth"), annotations=_ann, strip_head_no=_shn, siddham_text=bool(p("siddham_text", False)), pre_dedent=bool(p("pre_dedent", False)),            pre_dedent_spaces=p("pre_dedent_spaces", 4), mulu_levels=_epub_mulu_levels(p("pagination", {})), mulu_zhang_break=_epub_zhang_break(p("pagination", {})), figure_base=_fig_dirs or None).render_work(work, out_dir=outdir, filename=f"{stem}.epub"))]
    if fmt == "md":
        return [os.path.join(outdir, MdRenderer(theme=theme, notes="footnote", show_notes=True, inline_brackets=p("inline_brackets", "halfwidth"), annotations=_ann, strip_head_no=_shn, show_dharani_transliteration=bool(p("show_dharani_transliteration", False)), siddham_text=bool(p("siddham_text", False))).render_work(work, out_dir=outdir, filename=f"{stem}.md"))]
    if fmt == "txt":
        return [os.path.join(outdir, TxtRenderer(theme=theme, notes="footnote", show_notes=True, inline_brackets=p("inline_brackets", "halfwidth"), annotations=_ann, strip_head_no=_shn, show_dharani_transliteration=bool(p("show_dharani_transliteration", False)), siddham_text=bool(p("siddham_text", False))).render_work(work, out_dir=outdir, filename=f"{stem}.txt"))]
    raise ValueError(f"unknown format {fmt}")

def verify_one(xml_fn: str, fmt: str, source: str, out_root: str, max_diff: int = 10, diff_lines: int = 5, config_path: Optional[str] = None, t2s: bool = False, baseline: str = "render", gen_paths: Optional[List[str]] = None, baseline_roots: Optional[dict] = None) -> Dict:
    if fmt == "pdf":
        # 官方无 PDF 基线：PDF 由 docx（docx2pdf）或 html（html2pdf）派生，正文已由该格式校验覆盖
        return {"xml": xml_fn, "fmt": fmt, "status": "no_baseline", "gen": [],
                "detail": "PDF 无官方基线（正文由 docx/html 校验覆盖）"}
    work = P5Parser().parse(xml_fn)
    # 繁体剥离键：官方基线恒为繁体，官方侧 strip_docx_head 必须用繁体键
    t_title = (work.metadata.get("title") or "").strip()
    t_docnumber = (work.metadata.get("docNumber") or "").strip()
    t_series = (work.metadata.get("series") or "").strip()
    if t2s:
        from .simplify import simplify_work
        simplify_work(work)
    outdir = os.path.join(out_root, fmt)
    if gen_paths is not None:
        # 只校验已有产物（--verify-only）：跳过 generate_formal，不重写正式输出
        gen_path = [p for p in gen_paths if os.path.isfile(p)]
        if not gen_path:
            return {"xml": xml_fn, "fmt": fmt, "status": "error",
                    "detail": "生成档缺失（--verify-only 未找到可比对文件）", "gen": []}
    else:
        gen_path = generate_formal(xml_fn, work, fmt, outdir, config_path=config_path)
    # 结构护栏：docx（含 pdf→docx 委托产物）不得含段中段/表中段（否则 Word 丢内容）
    struct_issues = []
    if fmt == "docx":
        for _p in gen_path:
            struct_issues += docx_nested_block_violations(_p)
            if len(struct_issues) >= 5:
                break
        struct_issues = struct_issues[:5]
    ours_raw = "".join(extract_text(p, strip_jiaozhu=(fmt not in ("html", "epub")))
                       for p in gen_path)
    try:
        cfg = (load_effective_presets(config_path).get("verify") or {})
    except Exception:
        cfg = {}
    try:
        _presets_full = load_effective_presets(config_path)
    except Exception:
        _presets_full = {}
    ruby_brackets = _ann_brackets_from(_presets_full)
    compare_infos = bool((cfg or {}).get("compareInfos", False))
    docnumber = (work.metadata.get("docNumber") or "").strip()
    series = (work.metadata.get("series") or "").strip()
    if fmt == "docx":
        title = (work.metadata.get("title") or "").strip()
        ours_raw = strip_docx_head(ours_raw, title, docnumber, series)
    if fmt == "md":
        # md 标记官方侧没有：`## 校注` 块头 + `[^n]: ` 定义标记（引用由 normalize 通规则剥）
        ours_raw = _strip_md_marks(ours_raw)
    if not compare_infos:
        ours_raw = strip_infos(ours_raw)
    ours_disp = _display_text(ours_raw)
    ours, ours_line, _ours_lines = normalize_with_lines(ours_disp, ruby_brackets)
    if fmt == "epub":
        # txt trial 专用形（官方 txt“正文+注块”同构）；其余 trial 沿用原交错形
        _txt_raw = _join_epub_ours(gen_path)
        if not compare_infos:
            _txt_raw = strip_infos(_txt_raw)
        ours_txt_disp = _display_text(_txt_raw)
        ours_txt, ours_txt_line, _ = normalize_with_lines(ours_txt_disp,
                                                          ruby_brackets)
    else:
        ours_txt, ours_txt_line, ours_txt_disp = ours, ours_line, ours_disp
    # strip_head_no 联动：生成侧已剥 head/jhead 行首 No. 令牌；官方侧求同一令牌表对等剥离
    _strip_no = _strip_no_from(config_path)
    strip_tokens = _head_no_tokens(work) if _strip_no else []
    name = os.path.basename(xml_fn)
    stem = os.path.splitext(name)[0]
    if baseline == "xml":
        # P3 辅轨：IR→TXT（生成侧 TxtRenderer）vs 官方 XML→TXT（输入 XML 本身
        # 经 _extract_xml_parts 直抽；baseline_root 方案作废——cbeta_xml 为空目录，
        # 输入 XML 即官方下载件，直用可避版本偏斜且零新配置）。仅 fmt=txt。
        if fmt != "txt":
            raise ValueError("--baseline xml 仅支持 fmt=txt（IR→TXT vs 官方XML→TXT）")
        # inline 括号口径与 generate_formal 一致（output←verify 合并；run 优先，出厂兜底）
        try:
            from .theme import load_run_config, default_run_path, resolve_effective_config
            _run = load_run_config(config_path) if config_path else load_run_config()
            _rdir = os.path.dirname(os.path.abspath(config_path)) if config_path \
                else os.path.dirname(os.path.abspath(default_run_path()))
            _ib_defaults = {**(resolve_effective_config(_run, _rdir).get("output") or {})}
        except Exception:
            try:
                _ib_defaults = dict(load_effective_presets(config_path).get("output") or {})
            except Exception:
                _ib_defaults = {}
        try:
            _v = load_effective_presets(config_path).get("verify")
            _ib_defaults.update(_v or {})
        except Exception:
            pass
        title_x, author_x, body_x, foots_x = _extract_xml_parts(
            xml_fn, _ib_defaults.get("inline_brackets", "fullwidth"),
            bool(_ib_defaults.get("show_dharani_transliteration", False)))
        # 生成侧（TxtRenderer）卷首已去书名/作者名，官方侧同口径直接从正文开始
        theirs_raw = body_x.lstrip("\n")
        if foots_x:
            theirs_raw += "\n\n" + "\n\n".join(foots_x)
        if not compare_infos:
            theirs_raw = strip_infos(theirs_raw)
        if strip_tokens:
            theirs_raw = _strip_official_no(theirs_raw, strip_tokens)
        if t2s:
            theirs_raw = t2s_baseline(theirs_raw)
        theirs_disp = _display_text(theirs_raw)
        theirs, theirs_line, _theirs_lines = normalize_with_lines(theirs_disp, ruby_brackets)
        try:
            os.makedirs(outdir, exist_ok=True)
            src_cmp = os.path.join(outdir, f"{stem}_compare_xml_official.txt")
            gen_cmp = os.path.join(outdir, f"{stem}_compare_txt_generated.txt")
            with open(src_cmp, "w", encoding="utf-8") as f:
                f.write(theirs_disp)
            with open(gen_cmp, "w", encoding="utf-8") as f:
                f.write(ours_disp)
        except Exception:
            src_cmp = gen_cmp = ""
        m, mi, ex, ctx = diff_stats(ours, theirs, diff_lines)
        total = mi + ex
        status = "ok" if total <= max_diff else "fail"
        return {"xml": xml_fn, "fmt": fmt, "status": status, "gen": gen_path,
                "official": xml_fn, "official_kind": "xml", "matched": m,
                "missing": mi, "extra": ex, "total": total, "ctx": ctx,
                "ctx_loc": ctx_locations(ctx, ours_line, theirs_line),
                "src_cmp": src_cmp, "gen_cmp": gen_cmp,
                "norm_gen": ours, "norm_official": theirs}
    scope_juan = bool((cfg or {}).get("scope_juan", True))
    _juan = work_juan_numbers(work) if scope_juan else None

    def _discover():
        out = {}
        # 配置基线目录优先（数据源面板「校验基线」tab：source.baselines 或显式传入；
        # 缺键/空=未配置，直走旧行为）；首个非空根胜出
        _bl = baseline_roots
        if _bl is None:
            try:
                _bl = ((_presets_full.get("source") or {}).get("baselines")
                       or {})
            except Exception:
                _bl = {}
        if not isinstance(_bl, dict):
            _bl = {}
        for k in ("html", "txt_notes", "docx", "epub", "odt"):
            _extra = [(_bl.get(k) or "").strip()] if (_bl.get(k) or "").strip() else []
            found = find_official(source, stem, k,
                                  juan=_juan if k in ("html", "docx", "txt_notes") else None,
                                  extra_roots=_extra)
            if found:
                out[k] = found
        return out

    _chains = (cfg or {}).get("bases")
    chain = chain_for(fmt, _chains)
    base_kind = chain[0]

    def _bases(official):
        return resolve_bases(fmt, official, _chains)

    official = _discover()
    if base_kind not in official and bool((cfg or {}).get("auto_fetch", True)):
        # 首选基线缺失：按需下载（docx/odt 非 T/X 等 404 静默跳过）
        from .fetch import ensure_baselines
        presets = load_effective_presets(config_path)
        need = need_for_base(base_kind)
        # 材料化模型：基线落 cbeta_ebook work 目录（缺省回退 source）
        ebook = ((presets.get("source") or {}).get("cbeta_ebook") or "").strip() \
            or source
        ensure_baselines(work.id, need, presets, ebook)
        official = _discover()
    bases = _bases(official)
    if not bases:
        return {"xml": xml_fn, "fmt": fmt, "status": "no_baseline", "gen": gen_path, "official": None}
    best = None
    trials = []
    for bkind, bpath in bases:
        if isinstance(bpath, list) and bkind == "docx" and len(bpath) > 1:
            title = t_title
            if bkind == "docx":
                # 多卷官方 docx 先合并为单个 docx，再抽取 TXT：脚注统一在文末
                merged_docx = os.path.join(outdir, f"{stem}_official_merged_{bkind}.docx")
                merged_docx = merge_docx(bpath, merged_docx)
                merged_raw = extract_text(merged_docx)
                merged_raw = strip_docx_head(merged_raw, title, t_docnumber, t_series)
                if not compare_infos:
                    merged_raw = strip_infos(merged_raw)
                theirs_raw = merged_raw
            else:
                parts = []
                for p in bpath:
                    txt = extract_text(p)
                    if not compare_infos:
                        txt = strip_infos(txt)
                    parts.append(txt)
                theirs_raw = "".join(parts)
            bpath_disp = f"{bpath[0]} (+{len(bpath)-1})"
        elif isinstance(bpath, list) and len(bpath) > 1:
            # 多卷官方 html：docx 回退时脚注统一放文末以对齐 docx；html 自身比较保持原样
            if bkind == "html" and fmt == "docx":
                bodies, foots = [], []
                for p in bpath:
                    b, f = _extract_html_parts(p)
                    title = t_title
                    b = strip_docx_head(b, title, t_docnumber, t_series)
                    f = strip_docx_head(f, title, t_docnumber, t_series)
                    if not compare_infos:
                        b = strip_infos(b)
                        f = strip_infos(f)
                    bodies.append(b)
                    foots.append(f)
                theirs_raw = "".join(bodies) + "\n" + "".join(foots)
            else:
                parts = []
                for p in bpath:
                    txt = extract_text(p, strip_jiaozhu=(fmt not in ("html", "epub")))
                    if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                        title = t_title
                        txt = strip_docx_head(txt, title, t_docnumber, t_series)
                    if not compare_infos:
                        txt = strip_infos(txt)
                    parts.append(txt)
                theirs_raw = "".join(parts)
            bpath_disp = f"{bpath[0]} (+{len(bpath)-1})"
        elif isinstance(bpath, list):
            # 单文件：docx 亦过滤 title/docNumber（与多卷首卷一致）；docx 回退 html 同理
            theirs_raw = extract_text(bpath[0], strip_jiaozhu=(fmt not in ("html", "epub")))
            if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                title = t_title
                theirs_raw = strip_docx_head(theirs_raw, title, t_docnumber, t_series)
            if not compare_infos:
                theirs_raw = strip_infos(theirs_raw)
            bpath_disp = bpath[0]
        else:
            theirs_raw = extract_text(bpath, strip_jiaozhu=(fmt not in ("html", "epub")))
            if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                title = t_title
                theirs_raw = strip_docx_head(theirs_raw, title, t_docnumber, t_series)
            if not compare_infos:
                theirs_raw = strip_infos(theirs_raw)
            bpath_disp = bpath
        if bkind == "txt_notes":
            # text 族官方侧对齐（繁简通用）：版头剥离 + 注记块识别挪文末，
            # 与生成侧正文+注块同构；无注记行为无操作
            theirs_raw = _norm_official_txt(theirs_raw)
        if strip_tokens:
            theirs_raw = _strip_official_no(theirs_raw, strip_tokens)
        if t2s:
            # 简体校验：官方基线（繁体）经同一 t2s 管线转简体后再比对；
            # 作用于剥离后的纯文本，落盘 _compare 文件与比对输入一致
            theirs_raw = t2s_baseline(theirs_raw)
        theirs_disp = _display_text(theirs_raw)
        theirs, theirs_line, _theirs_lines = normalize_with_lines(theirs_disp, ruby_brackets)
        if bkind == "txt_notes" and fmt == "epub":
            # epub→txt trial：生成侧用重组形（正文全接+注块全接）；
            # 其余 trial 沿用原交错形（官方同形）
            t_ours, t_line, t_disp = ours_txt, ours_txt_line, ours_txt_disp
        else:
            t_ours, t_line, t_disp = ours, ours_line, ours_disp
        try:
            os.makedirs(outdir, exist_ok=True)
            src_cmp = os.path.join(outdir, f"{stem}_compare_{bkind}_official.txt")
            gen_cmp = os.path.join(outdir, f"{stem}_compare_{fmt}_{bkind}_generated.txt")
            with open(src_cmp, "w", encoding="utf-8") as f:
                f.write(theirs_disp)
            with open(gen_cmp, "w", encoding="utf-8") as f:
                f.write(t_disp)
        except Exception:
            src_cmp = gen_cmp = ""
        m, mi, ex, ctx = diff_stats(t_ours, theirs, diff_lines)
        total = mi + ex
        trials.append({"kind": bkind, "official": bpath_disp, "missing": mi,
                       "extra": ex, "total": total, "ok": total <= max_diff,
                       "official_files": list(bpath) if isinstance(bpath, list)
                       else ([bpath] if isinstance(bpath, str) else []),
                       "ctx": ctx, "norm_official": theirs,
                       "norm_gen": t_ours,
                       "ctx_loc": ctx_locations(ctx, t_line, theirs_line),
                       "src_cmp": src_cmp, "gen_cmp": gen_cmp})
        cur = (bkind, bpath_disp, m, mi, ex, ctx, total, src_cmp, gen_cmp, theirs,
               ctx_locations(ctx, t_line, theirs_line), t_ours)
        if best is None or total < best[6]:
            best = cur
        if total <= max_diff:
            st = "fail" if struct_issues else "ok"
            return {"xml": xml_fn, "fmt": fmt, "status": st, "gen": gen_path, "official": bpath_disp, "official_kind": bkind, "matched": m, "missing": mi, "extra": ex, "total": total, "ctx": ctx, "src_cmp": src_cmp, "gen_cmp": gen_cmp, "norm_gen": t_ours, "norm_official": theirs, "trials": trials, "struct_issues": struct_issues}
    bkind, bpath, m, mi, ex, ctx, total, src_cmp, gen_cmp, best_theirs, best_loc, best_ours = best
    return {"xml": xml_fn, "fmt": fmt, "status": "fail", "gen": gen_path, "official": bpath, "official_kind": bkind, "matched": m, "missing": mi, "extra": ex, "total": total, "ctx": ctx, "ctx_loc": best_loc, "src_cmp": src_cmp, "gen_cmp": gen_cmp, "norm_gen": best_ours, "norm_official": best_theirs, "trials": trials, "struct_issues": struct_issues}


def format_verify_report(records, diff_lines: int = 5, max_diff: int = 10):
    """verify_one 记录列表 → 验证总报告行（对齐 report.txt 风格，含前 N 条差异片段）。

    记录须为 verify_one 返回 dict；每个 XML 一段，逐条列出**每个尝试过的基线**
    （`trials`）并标 [OK]/[FAIL]，失败项列前 diff_lines 条【源】【新】差异。
    无 `trials` 的记录（如 P3 辅轨 baseline=xml）退化为单条，标签 `{fmt}→{kind}`。
    同一 work 的多条记录（多格式）先聚组，每组段首加总结行
    `[id] N format: 1[docx=OK], …`（下游速读；行首避开 `[OK]/[FAIL]/[--]` 解析）。
    """
    groups, order = {}, []
    for r in records or []:
        key = r.get("id") or os.path.basename(r.get("xml") or "") or "?"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    lines = []
    for key in order:
        recs = groups[key]
        lines.append(format_work_summary(
            key, [((rec.get("fmt") or ""), rec.get("status"),
                    rec.get("missing"), rec.get("extra"),
                    rec.get("cover_by"))
                   for rec in recs]))
        for r in recs:
            lines.extend(_format_verify_record(r, diff_lines, max_diff))
    return lines


def _format_verify_record(r, diff_lines: int = 5, max_diff: int = 10):
    """单条记录 → 报告行（原 format_verify_report 循环体）。"""
    lines = []
    name = os.path.basename(r.get("xml") or r.get("id") or "")
    fmt = r.get("fmt", "")
    st = r.get("status")
    lines.append(f"=== {name}")
    _struct = r.get("struct_issues") or []
    if _struct:
        lines.append(f"  [FAIL] {fmt} 结构非法（段中段/表中段 {len(_struct)} 处，"
                     "Word/WPS 会丢弃；文字抽取假绿）：")
        for s in _struct[:5]:
            lines.append(f"         {s}")
    if st == "no_baseline":
        detail = r.get("detail")
        lines.append(f"  [--]  {fmt} no baseline"
                     + (f"（{detail}）" if detail else ""))
        return lines
    if st == "covered":
        lines.append(f"  [--]  {fmt} {r.get('detail') or '已覆盖'}")
        return lines
    if st == "error":
        lines.append(f"  [FAIL] {fmt} 校验异常: {r.get('detail', '')}")
        return lines
    ours = r.get("norm_gen") or ""
    gen = r.get("gen")
    if isinstance(gen, list):
        gen = gen[0] if gen else ""
    trials = r.get("trials")
    if not trials:
        trials = [{"kind": r.get("official_kind") or "?",
                   "official": r.get("official"),
                   "missing": r.get("missing"), "extra": r.get("extra"),
                   "total": r.get("total"), "ok": st == "ok",
                   "ctx": r.get("ctx"), "ctx_loc": r.get("ctx_loc"),
                   "src_cmp": r.get("src_cmp"), "gen_cmp": r.get("gen_cmp"),
                   "norm_official": r.get("norm_official")}]
    for t in trials:
        ok = bool(t.get("ok"))
        mark = "[OK]" if ok else "[FAIL]"
        op = "≤" if ok else ">"
        lines.append(f"  {mark} ({fmt}→{t.get('kind')} 缺{t.get('missing')}/"
                     f"多{t.get('extra')} {op}阈值{max_diff})")
        if t.get("official"):
            lines.append(f"  {fmt} 【源】{t['official']}")
            if t.get("src_cmp"):
                lines.append("       【源比较】行号对齐 " + t["src_cmp"])
        if gen:
            lines.append(f"  {fmt} 【新】{gen}")
            if t.get("gen_cmp"):
                lines.append("       【新比较】行号对齐 " + t["gen_cmp"])
        # 有差异就列前 diff_lines 条（含绿灯但非 缺0/多0 的情况）
        if not ok or (t.get("missing") or 0) + (t.get("extra") or 0) > 0:
            theirs = t.get("norm_official") or ""
            # 各 trial 的生成侧文本可能不同（如 epub→txt 用重组形），
            # 用 trial 自带的 norm_gen（缺失回退整记录级）
            t_ours = t.get("norm_gen") or ours
            locs = t.get("ctx_loc") or []
            # compare 文件整行 + 原始文件定位（CLI 报告同口径；读不到回退）
            try:
                _t_rawln = open(t["src_cmp"], encoding="utf-8").read().split("\n") \
                    if t.get("src_cmp") else []
            except (OSError, ValueError):
                _t_rawln = []
            try:
                _o_rawln = open(t["gen_cmp"], encoding="utf-8").read().split("\n") \
                    if t.get("gen_cmp") else []
            except (OSError, ValueError):
                _o_rawln = []
            _off_texts = _official_locate_texts(
                t.get("kind"), t.get("official_files") or [], fmt,
                (fmt not in ("html", "epub")))
            _gen_index = _gen_locate_index(
                fmt, r.get("gen") if isinstance(r.get("gen"), list)
                else ([r.get("gen")] if r.get("gen") else []))
            src_loc = gen_loc = ""
            for idx, (_tag, i1, i2, j1, j2) in enumerate(
                    (t.get("ctx") or [])[:diff_lines], 1):
                loc = locs[idx - 1] if idx - 1 < len(locs) else {}
                parts = []
                if loc.get("src_line"):
                    parts.append(f"源比较第{loc['src_line']}行")
                if loc.get("gen_line"):
                    parts.append(f"新比较第{loc['gen_line']}行")
                where = f"（{'，'.join(parts)}）" if parts else ""
                lines.append(f"      {idx}.{where}")
                lines.append(f"         【源】{_mark_span(theirs, j1, j2, pad=i2 - i1)}")
                lines.append(f"         【新】{_mark_span(t_ours, i1, i2, pad=j2 - j1)}")
                sl = loc.get("src_line")
                gl = loc.get("gen_line")
                lines.append("         【源整行】" + (
                    _t_rawln[sl - 1] if sl and 0 < sl <= len(_t_rawln)
                    else "（行号不可得）"))
                lines.append("         【新整行】" + (
                    _o_rawln[gl - 1] if gl and 0 < gl <= len(_o_rawln)
                    else "（行号不可得）"))
                src_loc, gen_loc = _frag_locs(
                    loc, _o_rawln, _t_rawln, _off_texts, _gen_index,
                    "\n".join(_o_rawln))
                if src_loc:
                    lines.append(f"         【源文件】{src_loc}")
            if gen_loc:
                lines.append(f"         【新文件】{gen_loc}")
    return lines


# ---------------- 校验指纹 verify-fp-1 ----------------
# 用途：publish 在跑 --verify 之前廉价预判“上次 pass 结论是否仍然有效”，
# 以跳过重复校验。只读（stat/读文件/读配置/glob），禁 parse/渲染/下载/
# 写文件/控制台输出；任一无法证明的情形返回 None（调用方一律重验）。
# 本机有效：mtime、本机路径解析参与定位，不保证跨机器可比。
_FP_VERSION = "verify-fp-1"
_FP_FORMATS = ("html", "docx", "epub", "md", "txt", "pdf")
# 影响比对文本的源码模块：任一变化必须使旧指纹失效；改此表本身须 bump 版本。
# 刻意排除：fonts/gaiji/figures（只影响字形与图片，不影响抽取文本）、
# filename/names（只影响命名）、fetch/merge/cli（输入内容已直接哈希；cli 只做编排）。
_FP_IMPL_MODULES = ("verify", "render_docx", "render_html", "render_epub",
                    "render_md", "render_txt", "render_pdf", "theme",
                    "annotate", "simplify", "parser", "model")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str):
    """文件内容 sha256（读失败返回 None）。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, ValueError):
        return None


def _file_identity(path: str):
    """文件身份 {name, size, mtime_ns, sha256}；缺失/不可读/非文件 → None。
    mtime_ns 仅记录不哈希（合册临时文件每次 mtime 都新；同字节重写不应失效）。"""
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        return None
    if not os.path.isfile(path):
        return None
    digest = _sha256_file(path)
    if digest is None:
        return None
    return {"name": os.path.basename(path), "size": st.st_size,
            "mtime_ns": st.st_mtime_ns, "sha256": digest}


def _impl_digest(modules=None, pkg_dir=None) -> str:
    """实现摘要：包版本 + 指定模块源码内容哈希（缺失记 missing 标记，保证确定性）。"""
    import pycbeta
    pkg = pkg_dir or os.path.dirname(os.path.abspath(pycbeta.__file__))
    h = hashlib.sha256()
    h.update(("verify-fp-impl-1|" + pycbeta.__version__).encode("utf-8"))
    for m in (modules if modules is not None else _FP_IMPL_MODULES):
        h.update(("|" + m + "|").encode("utf-8"))
        data = None
        try:
            with open(os.path.join(pkg, m + ".py"), "rb") as f:
                data = f.read()
        except (OSError, ValueError):
            data = None
        h.update(data if data is not None else b"<missing>")
    return "sha256:" + h.hexdigest()


def _canon_jsonable(v):
    """配置值规范形（确定性；未知类型走 repr，集合排序）。"""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_canon_jsonable(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted((_canon_jsonable(x) for x in v), key=repr)
    if isinstance(v, dict):
        return {str(k): _canon_jsonable(v[k]) for k in sorted(v, key=repr)}
    return repr(v)


def _canon_annotations(presets, config_path):
    """注音配置规范形：与 resolve_annotations 同源，表内容整体哈希（无路径）。"""
    try:
        from .annotate import resolve_annotations
        spec = (presets.get("annotations")
                if isinstance(presets, dict) else None)
        ann = resolve_annotations(spec, config_path or _PRESETS_PATH)
    except Exception:
        return None
    if not ann:
        return None
    try:
        table_digest = _sha256_bytes(json.dumps(
            _canon_jsonable(ann.get("table") or {}),
            sort_keys=True, ensure_ascii=True).encode("utf-8"))
    except Exception:
        return None
    return {
        "scheme": ann.get("scheme"),
        "brackets": list(ann.get("brackets") or []),
        "repeat": ann.get("repeat"),
        "zones": sorted(ann.get("rare_zones") or []),
        "full_text": bool(ann.get("full_text", False)),
        "table_sha256": table_digest,
        "rare": _canon_jsonable(ann.get("rare_cmap")),
    }


def _theme_css_digest(config_path=None):
    """与 generate_formal 同口径的主题 CSS 内容摘要（无路径）。
    解析失败 → 出厂等价摘要；连出厂都不可读 → "unavailable"。"""
    text = None
    try:
        from .theme import resolve_config_arg, resolve_pdf_docx_css
        _run, _rdir = resolve_config_arg(config_path)
        text = resolve_pdf_docx_css(_run, _rdir)
    except Exception:
        text = None
    if not isinstance(text, str) or not text:
        try:
            from .theme import Theme as _Theme
            text = _Theme().raw_css or ""
        except Exception:
            return "unavailable"
    return "sha256:" + _sha256_bytes(text.encode("utf-8"))


def canonical_verify_config(config_path=None, _presets=None):
    """生效校验配置的规范形（JSON 可序列化；失败返回 None）。
    只收 generate_formal 实际消费的影响文本键 + verify 链配置；
    show_notes（formal 强制 True）、notes 模式（按格式写死）、
    corr_cbeta/footnote_separator/font_scale 等 formal 未消费项一律剔除；
    临时路径/输出目录等位置信息一律不收（只哈希内容）。
    本函数自身静默（内部打印一律重定向吞掉）。"""
    import io as _io
    from contextlib import redirect_stdout as _redir
    buf = _io.StringIO()
    try:
        with _redir(buf):
            return _canonical_verify_config_inner(config_path, _presets)
    except Exception:
        return None


def _canonical_verify_config_inner(config_path=None, _presets=None):
    if _presets is not None:
        presets = _presets
    else:
        try:
            presets = load_effective_presets(config_path)
        except Exception:
            return None
    if not isinstance(presets, dict):
        return None
    out = presets.get("output") or {}
    ver = presets.get("verify") or {}
    # inline_brackets 回退规则与 generate_formal 同构（verify 缺键强制半角）
    ib = ver.get("inline_brackets") if "inline_brackets" in ver else "halfwidth"
    try:
        from .fetch import title_t2s as _tt
        t2s_flag = bool(_tt(presets))
    except Exception:
        t2s_flag = False
    try:
        shn = bool(_strip_no_from(config_path))
    except Exception:
        shn = False
    return {
        "ignore_xml_style": bool(out.get("ignore_xml_style", False)),
        "ignore_xml_space": bool(out.get("ignore_xml_space", False)),
        "suppress_jhead_dup": bool(out.get("suppress_jhead_dup", True)),
        "show_close_juan": bool(out.get("show_close_juan", False)),
        "inline_brackets": ib,
        "note_inline_brackets": out.get("note_inline_brackets"),
        "series_title": _canon_jsonable(out.get("series_title") or {}),
        "pagination": _canon_jsonable(out.get("pagination") or {}),
        "verse_caesura": out.get("verse_caesura", "　　"),
        "verse_strip_quotes": bool(out.get("verse_strip_quotes", False)),
        "footnote_per_page": bool(out.get("footnote_per_page", True)),
        "vertical": bool(out.get("vertical", False)),
        "show_body_siddham": bool(out.get("show_body_siddham", True)),
        "siddham_text": bool(out.get("siddham_text", False)),
        "show_dharani_transliteration": bool(
            out.get("show_dharani_transliteration", False)),
        "pre_dedent": bool(out.get("pre_dedent", False)),
        "pre_dedent_spaces": _canon_jsonable(out.get("pre_dedent_spaces", 4)),
        "title_smart_wrap": bool(out.get("title_smart_wrap", True)),
        "strip_head_no": shn,
        "title_t2s": t2s_flag,
        "scope_juan": bool(ver.get("scope_juan", True)),
        "bases": _canon_jsonable(ver.get("bases")),
        "annotations": _canon_annotations(presets, config_path),
        "theme_css": _theme_css_digest(config_path),
        "pages": _canon_jsonable(presets.get("pages") or {}),
    }


def _locate_xml_nosideeffects(work_id, presets):
    """只读定位本地 XML（不下载、不物化、不写文件）：source.cbeta_ebook /
    source.xml_dir 内 find_local_xml；找不到 → []。"""
    try:
        from .fetch import parse_work_id, find_local_xml
        canon, no = parse_work_id(work_id or "")
    except Exception:
        return []
    src = (presets.get("source") or {}) if isinstance(presets, dict) else {}
    roots = []
    for k in ("cbeta_ebook", "xml_dir"):
        v = (src.get(k) or "").strip() if isinstance(src.get(k), str) else ""
        if v and os.path.isdir(v):
            roots.append(v)
    out, seen = [], set()
    for r in roots:
        try:
            found = find_local_xml(r, canon, no)
        except Exception:
            continue
        for p in found:
            if p not in seen and os.path.isfile(p):
                seen.add(p)
                out.append(p)
    return out


def verify_fingerprint(work_id, fmt, *, xml_files=None, config_path=None,
                       max_diff=10, diff_lines=5, t2s=None,
                       engine=None, vertical=None, baseline_roots=None,
                       baseline="render", _ctx=None):
    """校验指纹（Phase 1）：判断“上次 pass 结论是否仍然有效”的廉价预检。
    返回 "verify-fp-1:sha256:…" 或 None（不能证明 → 调用方一律重验）。
    无副作用：不 parse、不渲染、不下载、不写文件、不打印（内部输出一律重定向吞掉）。
    本机有效，不保证跨机器可比。t2s/engine/vertical 为 None 时取有效配置值；
    baseline_roots 为 None 时取配置 source.baselines。
    `_ctx`（内部用）：预计算的 {presets,canon,official,impl}，供 build_report_json
    一次发现多格式复用，避免每格式重扫基线目录。"""
    if (fmt or "") not in _FP_FORMATS:
        return None
    import io as _io
    from contextlib import redirect_stdout as _redir
    buf = _io.StringIO()
    try:
        with _redir(buf):
            return _verify_fingerprint_inner(
                work_id, fmt, xml_files, config_path, max_diff, diff_lines,
                t2s, engine, vertical, baseline_roots, baseline, _ctx)
    except Exception:
        return None


_FP_KINDS = ("html", "txt_notes", "docx", "epub", "odt")


def _fp_roots_cfg(presets, baseline_roots):
    """指纹/报告的基线根配置：显式 baseline_roots 优先，否则 presets source.baselines。"""
    if baseline_roots is None:
        _bl = ((presets.get("source") or {}).get("baselines") or {})
        return _bl if isinstance(_bl, dict) else {}
    return baseline_roots if isinstance(baseline_roots, dict) else {}


def _official_superset(source, stem, roots_cfg):
    """基线超集发现（juan=None，不过滤；只增不减方向安全）→ {kind: [paths]}。
    只读；单种失败跳过。build_report_json 与 verify_fingerprint 共用（扫一次复用）。"""
    out = {}
    for kind in _FP_KINDS:
        v = roots_cfg.get(kind, "") if isinstance(roots_cfg, dict) else ""
        extra = [v.strip()] if isinstance(v, str) and v.strip() else []
        try:
            found = find_official(source, stem, kind, juan=None,
                                  extra_roots=extra)
        except Exception:
            found = []
        if found:
            out[kind] = found
    return out


def _verify_fingerprint_inner(work_id, fmt, xml_files, config_path,
                              max_diff, diff_lines, t2s, engine, vertical,
                              baseline_roots, baseline, _ctx=None):
    _ctx = _ctx or {}
    if "presets" in _ctx:
        presets = _ctx["presets"]
    else:
        try:
            presets = load_effective_presets(config_path)
        except Exception:
            return None
    if not isinstance(presets, dict):
        return None
    out = presets.get("output") or {}
    if t2s is None:
        t2s = bool(out.get("t2s", False))
    if engine is None:
        engine = (presets.get("engine") or "").strip() or None
    if vertical is None:
        vertical = bool(out.get("vertical", False))
    # pdf 覆盖关系（与 CLI 同口径）：结论随源格式，覆盖映射进载荷
    from .render_pdf import pdf_source_fmt
    coverage = {}
    eff = fmt
    if fmt == "pdf":
        src = pdf_source_fmt(engine, bool(vertical))
        coverage = {"pdf": src}
        eff = src
    # XML 输入（调用方显式优先；否则只读定位，找不到 → None）
    if xml_files is None:
        xml_files = _locate_xml_nosideeffects(work_id, presets)
    if not xml_files:
        return None
    xmlrecs = []
    for f in xml_files:
        ident = _file_identity(f)
        if ident is None:
            return None
        xmlrecs.append(ident)
    stem = os.path.splitext(os.path.basename(xml_files[0]))[0]
    source = os.path.dirname(os.path.abspath(xml_files[0]))
    if "canon" in _ctx:
        canon = _ctx["canon"]
    else:
        canon = canonical_verify_config(config_path, _presets=presets)
    if canon is None:
        return None
    # 基线超集（juan=None，不过滤；只增不减方向安全）+ 首选缺失即 None
    if "official" in _ctx:
        official = _ctx["official"]
    else:
        roots_cfg = _fp_roots_cfg(presets, baseline_roots)
        official = _official_superset(source, stem, roots_cfg)
    ver = presets.get("verify") or {}
    chains_cfg = ver.get("bases")
    chain = chain_for(eff, chains_cfg)
    if not chain or not official.get(chain[0]):
        return None  # 首选基线缺失：实际跑会下载，本次不能证明
    bases = resolve_bases(eff, official, chains_cfg)
    if not bases:
        return None
    blrecs = {}
    for kind, paths in bases:
        ids = []
        for p in paths:
            ident = _file_identity(p)
            if ident is None:
                return None
            ids.append(ident)
        blrecs[kind] = ids
    impl = _ctx.get("impl") if "impl" in _ctx else _impl_digest()
    payload = {
        "fp_version": _FP_VERSION,
        "work": work_id,
        "requested": [fmt],
        "coverage": coverage,
        "xml": xmlrecs,
        "config_digest": _sha256_bytes(json.dumps(
            canon, sort_keys=True, ensure_ascii=True).encode("utf-8")),
        "baselines": blrecs,
        "thresholds": {"max_diff": int(max_diff), "diff_lines": int(diff_lines)},
        "t2s": bool(t2s),
        "engine": engine,
        "vertical": bool(vertical),
        "baseline": baseline,
        "impl": impl,
    }
    return "verify-fp-1:sha256:" + _sha256_bytes(json.dumps(
        payload, sort_keys=True, ensure_ascii=True).encode("utf-8"))


_VERDICTS = ("pass", "fail", "undetermined", "error")
_VERDICT_SEVERITY = {"pass": 0, "undetermined": 1, "error": 2, "fail": 3}


def _record_counts(r):
    """单条记录的 (missing, extra)：顶层缺失回退首个 trial；都没有 → (None, None)。"""
    mi, ex = r.get("missing"), r.get("extra")
    if mi is None or ex is None:
        for t in (r.get("trials") or []):
            if not isinstance(t, dict):
                continue
            if mi is None:
                mi = t.get("missing")
            if ex is None:
                ex = t.get("extra")
            if mi is not None and ex is not None:
                break
    return mi, ex


def _counts_reason(mi, ex):
    parts = []
    if mi is not None:
        parts.append(f"missing {mi}")
    if ex is not None:
        parts.append(f"extra {ex}")
    return ", ".join(parts)


def verdict_for(record):
    """单条 verify_one 记录 → (verdict, reason)。
    verdict ∈ pass/fail/undetermined/error（指纹提案 §2 口径，与 report.txt
    的 [OK]/[FAIL]/[--] 块一致：struct_issues 非空恒为 fail）；
    reason 为机读短码（no_baseline / covered:docx / gen_not_found /
    missing m, extra e / struct_illegal n / detail 原文），pass 时为 None。
    大小写不敏感；未知状态 → error（不得伪装 pass/fail）。"""
    r = record if isinstance(record, dict) else {}
    st = str(r.get("status") or "").strip().lower()
    struct = r.get("struct_issues") or []
    n_struct = len(struct) if isinstance(struct, list) else 1
    mi, ex = _record_counts(r)
    if n_struct:
        extra = _counts_reason(mi, ex)
        reason = f"struct_illegal {n_struct}" + (f"; {extra}" if extra else "")
        return ("fail", reason)
    if st == "ok":
        return ("pass", None)
    if st == "fail":
        return ("fail", _counts_reason(mi, ex) or "diff_over_threshold")
    if st == "no_baseline":
        return ("undetermined", "no_baseline")
    if st == "covered":
        return ("undetermined", f"covered:{r.get('cover_by') or '?'}")
    if st == "nogen":
        return ("undetermined", "gen_not_found")
    if st == "error":
        return ("error", str(r.get("detail") or "verify_error"))
    return ("error", f"unknown_status:{st or 'missing'}")


def _public_file_identity(path):
    """report.json inputs 用公开标识（提案 §4.2：仅 name/size/mtime_ns，不含 sha）。"""
    ident = _file_identity(path)
    if ident is None:
        return None
    return {"name": ident["name"], "size": ident["size"],
            "mtime_ns": ident["mtime_ns"]}


def build_report_json(work_id, records, *, xml_files=None, config_path=None,
                      requested_formats=None, max_diff=10, diff_lines=5,
                      t2s=None, engine=None, vertical=None,
                      baseline_roots=None, baseline="render",
                      report_name="report.txt"):
    """verify_one 记录列表 → report.json 载荷 dict（指纹提案 §4 口径）。
    纯装配：只读文件哈希，不写文件、不打印（内部输出重定向吞掉）；
    算不出的字段记 None，绝不抛异常（极端失败回退最小骨架）。"""
    import io as _io
    from contextlib import redirect_stdout as _redir
    buf = _io.StringIO()
    try:
        with _redir(buf):
            return _build_report_json_inner(
                work_id, records, xml_files, config_path,
                requested_formats, max_diff, diff_lines,
                t2s, engine, vertical, baseline_roots, baseline,
                report_name)
    except Exception:
        return {"schema": 1, "work": work_id, "fmts": {},
                "error": "build_failed"}


def _build_report_json_inner(work_id, records, xml_files, config_path,
                             requested_formats, max_diff, diff_lines,
                             t2s, engine, vertical, baseline_roots, baseline,
                             report_name):
    import pycbeta as _pkg
    recs = [r for r in (records or []) if isinstance(r, dict)]
    groups = {}
    for r in recs:
        fmt = str(r.get("fmt") or "").strip() or "?"
        groups.setdefault(fmt, []).append(r)
    if requested_formats is None:
        wanted = sorted(groups)
    else:
        wanted = [str(f).strip() or "?" for f in requested_formats]
        for f in wanted:
            groups.setdefault(f, [])
    try:
        presets = load_effective_presets(config_path)
    except Exception:
        presets = {}
    if not isinstance(presets, dict):
        presets = {}
    canon = canonical_verify_config(config_path, _presets=presets)
    config_digest = ("sha256:" + _sha256_bytes(json.dumps(
        canon, sort_keys=True, ensure_ascii=True).encode("utf-8"))) \
        if canon is not None else None
    # XML 输入：显式优先，否则从记录反推（只读，不定位下载）
    if xml_files is None:
        seen = set()
        xml_files = []
        for r in recs:
            p = r.get("xml")
            if isinstance(p, str) and p and p not in seen:
                seen.add(p)
                xml_files.append(p)
    xmlrecs = []
    for f in xml_files or []:
        ident = _public_file_identity(f)
        if ident is not None:
            xmlrecs.append(ident)
    # 基线超集（与 verify_fingerprint 同口径：juan=None；只增不减方向安全）
    official = {}
    blrecs = {}
    if xml_files:
        source = os.path.dirname(os.path.abspath(xml_files[0]))
        stem = os.path.splitext(os.path.basename(xml_files[0]))[0]
        roots_cfg = _fp_roots_cfg(presets, baseline_roots)
        official = _official_superset(source, stem, roots_cfg)
        for kind, found in official.items():
            ids = []
            for p in found:
                ident = _public_file_identity(p)
                if ident is not None:
                    ids.append(ident)
            if ids:
                blrecs[kind] = ids
    # pdf 覆盖关系（与 CLI/指纹同口径）
    coverage = {}
    if "pdf" in wanted:
        try:
            from .render_pdf import pdf_source_fmt as _psf
            _e, _v = engine, vertical
            if _e is None or _v is None:
                out = presets.get("output") or {}
                if _e is None:
                    _e = (presets.get("engine") or "").strip() or None
                if _v is None:
                    _v = bool(out.get("vertical", False))
            coverage = {"pdf": _psf(_e, bool(_v))}
        except Exception:
            coverage = {}
    # 预计算一次，供每个格式的指纹复用（避免 (1+N) 次基线目录重扫）
    try:
        impl_digest = _impl_digest()
    except Exception:
        impl_digest = "unavailable"
    _ctx = {"presets": presets, "canon": canon, "official": official,
            "impl": impl_digest}
    fmts = {}
    for fmt in wanted:
        grp = groups.get(fmt, [])
        best = "pass"
        reasons = []
        tot_mi = tot_ex = 0
        has_mi = has_ex = False
        gens = set()
        for r in grp:
            v, reason = verdict_for(r)
            if _VERDICT_SEVERITY[v] > _VERDICT_SEVERITY[best]:
                best = v
            if reason and reason not in reasons:
                reasons.append(reason)
            mi, ex = _record_counts(r)
            if isinstance(mi, int):
                tot_mi += mi
                has_mi = True
            if isinstance(ex, int):
                tot_ex += ex
                has_ex = True
            g = r.get("gen")
            if isinstance(g, (list, tuple)):
                for p in g:
                    if p:
                        gens.add(str(p))
            elif g:
                gens.add(str(g))
        try:
            fp = verify_fingerprint(
                work_id, fmt, xml_files=xml_files, config_path=config_path,
                max_diff=max_diff, diff_lines=diff_lines, t2s=t2s,
                engine=engine, vertical=vertical,
                baseline_roots=baseline_roots, baseline=baseline, _ctx=_ctx)
        except Exception:
            fp = None
        if not grp:
            best = "undetermined"
            reasons = ["no_record"]
        fmts[fmt] = {
            "verdict": best,
            "fingerprint": fp,
            "missing": tot_mi if has_mi else None,
            "extra": tot_ex if has_ex else None,
            "reason": "; ".join(reasons) if reasons else None,
            "formal_outputs": sorted(gens),
            "report": report_name,
        }
    try:
        from datetime import datetime as _dt
        created = _dt.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        created = ""
    return {
        "schema": 1,
        "fingerprint_version": _FP_VERSION,
        "tool": {"name": "pycbeta", "version": _pkg.__version__},
        "verify_impl": {"module": "pycbeta.verify", "digest": impl_digest,
                        "algorithm": "verify-1"},
        "work": work_id,
        "requested_formats": list(wanted),
        "thresholds": {"max_diff": int(max_diff), "diff_lines": int(diff_lines)},
        "inputs": {"xml_files": xmlrecs, "config_digest": config_digest,
                   "baselines": blrecs, "coverage": coverage},
        "fmts": fmts,
        "created_at": created,
    }


_VERIFY_ROOT_NAME = "验证"
_VERIFY_DIR_SUFFIXES = ("（验证）", "（驗證）")
_WORK_ID_RE = re.compile(r"^[A-Za-z]+\d+[A-Za-z]*$")


def default_verify_root(out_dir):
    """校验总目录唯一规则：`{输出}/验证`（out 为空 → 当前目录下 验证）。"""
    base = os.path.abspath(out_dir) if out_dir else os.getcwd()
    return os.path.join(base, _VERIFY_ROOT_NAME)


def resolve_verify_root(output_arg=None, xml_fn="", custom=""):
    """校验根目录决议（CLI/GUI 共用唯一入口）：
    custom（--verify-root）非空 → 其绝对路径；
    否则 default_verify_root(输出基)：输出参数是目录用其本身、是文件用其目录、
    无输出用 xml 所在目录。只做路径计算，不建目录、不碰文件。"""
    if (custom or "").strip():
        return os.path.abspath((custom or "").strip())
    base = ""
    if output_arg:
        _o = os.path.abspath(output_arg)
        base = _o if (os.path.isdir(_o) or not os.path.splitext(_o)[1]) \
            else os.path.dirname(_o)
    elif xml_fn:
        base = os.path.dirname(os.path.abspath(xml_fn))
    return default_verify_root(base)


def parse_verify_report_name(name):
    """`{id 书名}（验证）` → {"id", "title"}（兼容 （驗證） 后缀）。
    后缀不对 / id 不像 work id / 空 → None。title 缺失记 ""。"""
    s = (name or "").strip()
    core = None
    for suf in _VERIFY_DIR_SUFFIXES:
        if s.endswith(suf):
            core = s[:-len(suf)].strip()
            break
    if not core:
        return None
    parts = core.split(None, 1)
    if not parts or not _WORK_ID_RE.match(parts[0]):
        return None
    return {"id": parts[0], "title": parts[1].strip() if len(parts) > 1 else ""}


def find_verify_reports(verify_root):
    """新布局发现：只扫 `{verify_root}/*（验证）/` 直接子目录（不递归、不认旧平铺）。
    每目录配对报告：report.json 优先，否则 `*_verify_report.json` /
    `*_校验报告.json` 首个；txt 同理（report.txt / `*_verify_report.txt` /
    `*_校验报告.txt`）；无报告文件的仍收录（字段记 ""）。
    返回 [{"id","title","dir","report_json","report_txt"}]，按 dir 排序；
    根不存在 → []。只读，不抛异常。"""
    out = []
    try:
        if not verify_root or not os.path.isdir(verify_root):
            return []
        import glob as _glob
        for pat in ("*（验证）", "*（驗證）"):
            for d in sorted(_glob.glob(os.path.join(verify_root, pat))):
                if not os.path.isdir(d):
                    continue
                parsed = parse_verify_report_name(os.path.basename(d))
                if parsed is None:
                    continue
                rj = os.path.join(d, "report.json")
                if not os.path.isfile(rj):
                    cands = []
                    for pat in ("*_verify_report.json", "*_校验报告.json"):
                        cands += _glob.glob(os.path.join(d, pat))
                    cands = sorted(cands)
                    rj = cands[0] if cands else ""
                rt = os.path.join(d, "report.txt")
                if not os.path.isfile(rt):
                    cands = []
                    for pat in ("*_verify_report.txt", "*_校验报告.txt"):
                        cands += _glob.glob(os.path.join(d, pat))
                    cands = sorted(cands)
                    rt = cands[0] if cands else ""
                out.append({"id": parsed["id"], "title": parsed["title"],
                            "dir": os.path.abspath(d),
                            "report_json": rj, "report_txt": rt})
    except Exception:
        return out
    out.sort(key=lambda e: e["dir"])
    return out
