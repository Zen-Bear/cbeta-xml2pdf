# -*- coding: utf-8 -*-
"""校验库：供 CLI --verify、test/verify_text.py 及 GUI 复用。"""
import difflib, glob, os, re, sys, zipfile
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
        parts = []
        with zipfile.ZipFile(path) as z:
            for n in _epub_content_names(z):
                txt = z.read(n).decode("utf-8", "replace")
                txt = _body_only(txt)
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
            xml = re.sub(r"</w:p[^>]*>", "\n", xml)
            txt = _TAG_RE.sub("", xml)
            try:
                fn = z.read("word/footnotes.xml").decode("utf-8")
                fn = _EQ_RE.sub(_eq_base, fn)
                fn = _W_RUBY_RE.sub("", fn)
                fn = re.sub(r"</w:p[^>]*>", "\n", fn)
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
    由 normalize 的 r"\[[^\]\[]{1,8}\]" 统一剥离（不依赖 class）。
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


def _join_epub_blob_star(raw: str) -> tuple:
    """含星号位标记/新增校注锚点的章节重组：(body, foot)，
    与 `_split_html_text` 同文本口径，另按正文顺序交错注记
    （官方 txt 注块按引用位点排列：星号位复块如 `[23]` 与 `[*23-1]` 同块并存，
    新增校注如 `[A1]` 按出现位置插入；无星号位、无新增校注时与旧逻辑逐字节一致）。"""
    raw = _prep_html_blob(raw, body_only=True)
    spans = _footnote_spans(raw)
    blocks = [raw[s:e] for s, e in spans]
    parts, prev = [], 0
    for s, e in spans:
        parts.append(raw[prev:s])
        prev = e
    parts.append(raw[prev:])
    body_raw = "".join(parts)
    events = []  # (pos, kind, key)：kind reg=note_anchor_n，add=cb seq，star=note n
    for m in _BODY_ANCHOR_RE.finditer(body_raw):
        if m.group(2) is not None:
            events.append((m.start(), "reg", m.group(2)))
        else:
            events.append((m.start(), "add", m.group(3)))
    for m in _STAR_SPAN_RE.finditer(body_raw):
        nm = _STAR_N_RE.search(m.group(0))
        if nm:
            events.append((m.start(), "star", nm.group(2)))
    events.sort(key=lambda e: e[0])
    foots = []  # (key, text)：key 与事件 key 同口径（reg→n，add→seq）
    for b in blocks:
        im = _FOOT_ID_RE.search(b[:b.find(">") + 1] if ">" in b else b)
        if im:
            key = im.group(3) if im.group(3) is not None else im.group(4)
            kind = "reg" if im.group(3) is not None else "add"
            foots.append((kind, key, _foot_block_text(b)))
        else:
            foots.append((None, None, _foot_block_text(b)))
    # add 注记块（_back_cb）在文档尾集中存放，官方 txt 按正文位置交错：
    # 独立分区、事件驱动发射，不参与常规队列消费（否则前瞻吞掉后续常规块）
    adds = {}
    main = []
    for kind, key, text in foots:
        if kind == "add":
            adds.setdefault(key, text)
        else:
            main.append((kind, key, text))
    by_key = {}
    for kind, key, text in main:
        by_key.setdefault((kind, key), text)
    out = []
    queue = list(main)
    for _, kind, key in events:
        if kind == "star":
            dup = by_key.get(("reg", key))
            if dup is not None:
                out.append(dup)
            continue
        if kind == "add":
            hit = adds.get(key)
            if hit is not None:
                out.append(hit)
            continue
        idx = next((i for i, (k, kk, _) in enumerate(queue)
                    if k == kind and kk == key), None)
        if idx is None:
            continue
        for i in range(idx + 1):
            out.append(queue[i][2])
        del queue[:idx + 1]
    for _, _, text in queue:
        out.append(text)
    body_text = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", body_raw, flags=re.I)
    return _TAG_RE.sub("", body_text), "".join(out)


def _join_epub_ours(gen_paths) -> str:
    """epub 生成侧正文+注块重组：解包内各 xhtml（跳过 nav.xhtml 导航页），
    逐文件 `_extract_html_parts` 拆 body/foot（顺带去 `<hr><h1>校注</h1>` 头，
    官方 txt 侧无此头），正文全接 + 注记全接，与官方 txt“正文+注块”同构。
    含星号位标记（`note-star`）或新增校注锚点（`cb_note_anchor`，
    官方 txt 按正文位置交错、非常规尾聚）的章节走 `_join_epub_blob_star`
    按位重组（含星号位复注块）；其余与旧逻辑逐字节一致。docx/html/md/txt 不走这里。"""
    bodies, foots = [], []
    for p in gen_paths or []:
        try:
            if p.lower().endswith(".epub"):
                with zipfile.ZipFile(p) as z:
                    blobs = [z.read(n).decode("utf-8", "replace")
                             for n in _epub_content_names(z)]
            else:
                blobs = [open(p, encoding="utf-8", errors="replace").read()]
        except Exception:
            # 文件缺失/损坏（含非法 zip）：跳过该文件，不中断整批
            continue
        for raw in blobs:
            # txt 形先物化悉昙读音/图注/无解缺字（官方 txt 裸读音+图注+◇；
            # html/epub 形保持空元素）
            raw = _materialize_figs_gaiji(_materialize_ranja(raw))
            if _STAR_SPAN_RE.search(raw) or "cb_note_anchor" in raw:
                b, f = _join_epub_blob_star(raw)
            else:
                b, f = _split_html_text(raw, body_only=True)
            bodies.append(b)
            if f.strip():
                foots.append(f)
    out = "".join(bodies)
    if foots:
        out += "\n" + "".join(foots)
    return out


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
    键口径与 `_join_epub_blob_star` 一致（reg→n，add→seq）。
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
    ctx 只取前 max_ctx 条非 equal opcode（报告片段数；缺/多计数不受影响）。"""
    sm = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    matched = sum(op.size for op in sm.get_matching_blocks())
    missing = len(theirs) - matched
    extra = len(ours) - matched
    ctx = [(op[0], op[1], op[2], op[3], op[4]) for op in sm.get_opcodes() if op[0] != "equal"][:max_ctx]
    return matched, missing, extra, ctx

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
    for token in tokens:
        text = re.sub(r"(?m)^([ \t\u3000]*)" + re.escape(token) + r"[ \t\u3000]*",
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
        files = HtmlRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=True, inline_brackets=p("inline_brackets", "halfwidth"), annotations=_ann, strip_head_no=_shn, siddham_text=bool(p("siddham_text", False)), title_t2s=bool(_tt(presets)), figure_base=_fig_dirs or None).render_work(work, out_dir=outdir)
        return [os.path.join(outdir, f) for f in files]
    if fmt == "docx":
        return [os.path.join(outdir, DocxRenderer(theme=theme, notes="footnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=True, suppress_jhead_dup=p("suppress_jhead_dup", True), show_close_juan=bool(p("show_close_juan", False)), inline_brackets=p("inline_brackets", "halfwidth"), series_title=p("series_title", {}), annotations=_ann, strip_head_no=_shn, show_body_siddham=bool(p("show_body_siddham", True)), figure_base=_fig_dirs or None).render_work(work, out_dir=outdir, filename=f"{stem}.docx"))]
    if fmt == "epub":
        return [os.path.join(outdir, EpubRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=True, inline_brackets=p("inline_brackets", "halfwidth"), annotations=_ann, strip_head_no=_shn, siddham_text=bool(p("siddham_text", False)), figure_base=_fig_dirs or None).render_work(work, out_dir=outdir, filename=f"{stem}.epub"))]
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
            return {"xml": xml_fn, "fmt": fmt, "status": "ok", "gen": gen_path, "official": bpath_disp, "official_kind": bkind, "matched": m, "missing": mi, "extra": ex, "total": total, "ctx": ctx, "src_cmp": src_cmp, "gen_cmp": gen_cmp, "norm_gen": t_ours, "norm_official": theirs, "trials": trials}
    bkind, bpath, m, mi, ex, ctx, total, src_cmp, gen_cmp, best_theirs, best_loc, best_ours = best
    return {"xml": xml_fn, "fmt": fmt, "status": "fail", "gen": gen_path, "official": bpath, "official_kind": bkind, "matched": m, "missing": mi, "extra": ex, "total": total, "ctx": ctx, "ctx_loc": best_loc, "src_cmp": src_cmp, "gen_cmp": gen_cmp, "norm_gen": best_ours, "norm_official": best_theirs, "trials": trials}


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
