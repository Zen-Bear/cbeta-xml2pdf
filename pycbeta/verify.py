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
from .theme import load_presets, _PRESETS_PATH, strip_head_no

def normalize(text: str, ruby_brackets=None) -> str:
    # 官方基线 unclear 用 ▆，本管线渲染用 □（U+25A1）：两侧归一到 □ 再比较
    text = text.replace("▆", "□")
    text = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", text)
    text = re.sub(r"\[[^\]\[]{1,8}\]", "", text)
    text = re.sub(r"\u3010[^\u3011]{1,20}\u3011", "", text)
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

def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub":
        parts = []
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith((".xhtml", ".html")):
                    txt = z.read(n).decode("utf-8", "replace")
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
        raw = _STYLE_RE.sub("", raw)
        raw = _RUBY_RE.sub("", raw)
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
    由 normalize 的 r\"\\[[^\\]\\[]{1,8}\\]\" 统一剥离（不依赖 class）。"""
    raw = open(path, encoding="utf-8", errors="replace").read()
    raw = _STYLE_RE.sub("", raw)
    raw = _RUBY_RE.sub("", raw)
    raw = re.sub(r"<hr[^>]*>\s*<h1[^>]*>\s*校注\s*</h1>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<h1[^>]*>\s*校注\s*</h1>", "", raw, flags=re.I)
    footnotes = re.findall(r"<(?:div|span) class='footnote'[^>]*>.*?</(?:div|span)>", raw, flags=re.S | re.I)
    foot_text = ""
    for fn in footnotes:
        t = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", fn, flags=re.I)
        foot_text += _TAG_RE.sub("", t) + "\n"
    body_raw = re.sub(r"<(?:div|span) class='footnote'[^>]*>.*?</(?:div|span)>", "", raw, flags=re.S | re.I)
    body_raw = re.sub(r"</(p|div|h[1-6]|li|tr)[^>]*>", "\n", body_raw, flags=re.I)
    body_text = _TAG_RE.sub("", body_raw)
    return body_text, foot_text

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

def diff_stats(ours: str, theirs: str):
    """ours=生成档文本, theirs=官方文本。
    missing=生成档缺失（官方有而生成档无），extra=生成档多出（生成档有而官方无）。"""
    sm = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    matched = sum(op.size for op in sm.get_matching_blocks())
    missing = len(theirs) - matched
    extra = len(ours) - matched
    ctx = [(op[0], op[1], op[2], op[3], op[4]) for op in sm.get_opcodes() if op[0] != "equal"][:5]
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


def _head_no_tokens(work) -> list:
    """work 全部 head/jhead 的行首 No. 令牌（去重保序；`output.strip_head_no` 官方侧对等剥离用）。
    同输入必同值（与生成侧同一 helper 同一规则）；无命中返回 []。"""
    out = []
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
    全串转义 + 行首锚定（非行首的正文 No. 不动）；空表时原样返回。"""
    if not tokens:
        return text
    for token in tokens:
        text = re.sub(r"(?m)^" + re.escape(token), "", text)
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


def _extract_xml_parts(path: str, inline_brackets: str = "fullwidth"):
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

    def chunks(el, out):
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
                    chunks(child, out)
                    out.append(rb)
                # 非行内注整棵丢弃（body 内注生成侧恒 ""；back 注走注池）
            elif t == "app" and not child.get("from") and not child.get("corresp"):
                # body 内无锚 app（lem/rdg 直挂正文，如 TX0006 碎片）：parser 不进
                # _parse_app（仅 back 的进），渲染侧泛型默认分支直吐子文本，此处镜像
                # 收子文本。有 from/corresp 的仍整棵丢（渲染侧行内恒空；其注池归并只走
                # anchor 序，未覆盖——残留已知局限）。
                chunks(child, out)
            elif t in _XML_DROP_TAGS:
                pass
            elif t == "unclear":
                out.append("□")
            elif t == "g":
                code = (child.get("ref") or "").lstrip("#")
                raw = _WS_RE.sub("", "".join(child.itertext())) or code
                out.append(resolve_gaiji(code, raw))
            else:
                chunks(child, out)
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


def find_official(source: str, stem: str, kind: str, juan: Optional[set] = None) -> List[str]:
    """官方基线发现：短名回退/`_NNN` 优先/`out/` 排除/卷范围限定；统一根目录下平展优先、仓库次之。"""
    short = ""
    m = re.match(r"^([A-Z]+)\d+n(.+)$", stem)
    if m:
        short = m.group(1) + m.group(2)
        stems = [stem, short]
    else:
        stems = [stem]
    pats = []
    for s in stems:
        if kind == "txt":
            pats += [os.path.join(source, "**", f"{s}.txt", "*.txt"), os.path.join(source, "**", f"{s}.txt")]
        elif kind == "txt_notes":
            # 与 txt 同形但目录隔离（{s}.txt_notes/），两者内容不同不可混用
            pats += [os.path.join(source, "**", f"{s}.txt_notes", "*.txt"),
                     os.path.join(source, "**", f"{s}.txt_notes")]
        else:
            pats.append(os.path.join(source, "**", f"{s}*.{kind}"))
    out, seen = [], set()
    for pat in pats:
        for f in sorted(glob.glob(pat, recursive=True)):
            af = os.path.abspath(f)
            if "out" + os.sep in af:
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
        from .theme import (load_run_config, default_run_path,
                            resolve_effective_config)
        _run = load_run_config(config_path) if config_path else load_run_config()
        _rdir = os.path.dirname(os.path.abspath(config_path)) if config_path \
            else os.path.dirname(os.path.abspath(default_run_path()))
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
    if fmt == "html":
        files = HtmlRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=p("show_notes", True), inline_brackets=p("inline_brackets", "fullwidth"), annotations=_ann, strip_head_no=_shn).render_work(work, out_dir=outdir)
        return [os.path.join(outdir, f) for f in files]
    if fmt == "docx":
        return [os.path.join(outdir, DocxRenderer(theme=theme, notes="footnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=p("show_notes", True), suppress_jhead_dup=p("suppress_jhead_dup", True), show_close_juan=bool(p("show_close_juan", False)), inline_brackets=p("inline_brackets", "fullwidth"), series_title=p("series_title", {}), annotations=_ann, strip_head_no=_shn).render_work(work, out_dir=outdir, filename=f"{stem}.docx"))]
    if fmt == "epub":
        return [os.path.join(outdir, EpubRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=p("show_notes", True), annotations=_ann, strip_head_no=_shn).render_work(work, out_dir=outdir, filename=f"{stem}.epub"))]
    if fmt == "md":
        return [os.path.join(outdir, MdRenderer(theme=theme, notes="footnote", show_notes=p("show_notes", True), inline_brackets=p("inline_brackets", "fullwidth"), annotations=_ann, strip_head_no=_shn).render_work(work, out_dir=outdir, filename=f"{stem}.md"))]
    if fmt == "txt":
        return [os.path.join(outdir, TxtRenderer(theme=theme, notes="footnote", show_notes=p("show_notes", True), inline_brackets=p("inline_brackets", "fullwidth"), annotations=_ann, strip_head_no=_shn).render_work(work, out_dir=outdir, filename=f"{stem}.txt"))]
    raise ValueError(f"unknown format {fmt}")

def verify_one(xml_fn: str, fmt: str, source: str, out_root: str, max_diff: int = 10, diff_lines: int = 5, config_path: Optional[str] = None, t2s: bool = False, baseline: str = "render") -> Dict:
    work = P5Parser().parse(xml_fn)
    # 繁体剥离键：官方基线恒为繁体，官方侧 strip_docx_head 必须用繁体键
    t_title = (work.metadata.get("title") or "").strip()
    t_docnumber = (work.metadata.get("docNumber") or "").strip()
    t_series = (work.metadata.get("series") or "").strip()
    if t2s:
        from .simplify import simplify_work
        simplify_work(work)
    outdir = os.path.join(out_root, fmt)
    gen_path = generate_formal(xml_fn, work, fmt, outdir, config_path=config_path)
    ours_raw = "".join(extract_text(p) for p in gen_path)
    try:
        cfg = load_presets(config_path).get("verify") if config_path else load_presets().get("verify")
    except Exception:
        cfg = {}
    try:
        _presets_full = load_presets(config_path) if config_path else load_presets()
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
    ours = normalize(ours_raw, ruby_brackets)
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
                _ib_defaults = dict(load_presets(config_path).get("output")
                                    if config_path else load_presets().get("output") or {})
            except Exception:
                _ib_defaults = {}
        try:
            _v = load_presets(config_path).get("verify") if config_path \
                else load_presets().get("verify")
            _ib_defaults.update(_v or {})
        except Exception:
            pass
        title_x, author_x, body_x, foots_x = _extract_xml_parts(
            xml_fn, _ib_defaults.get("inline_brackets", "fullwidth"))
        if not title_x:
            title_x = work.id  # 与生成侧 `md.get("title") or work.id` 对齐
        theirs_raw = f"{title_x}\n\n{author_x}\n\n{body_x}"
        if foots_x:
            theirs_raw += "\n\n" + "\n\n".join(foots_x)
        if not compare_infos:
            theirs_raw = strip_infos(theirs_raw)
        if strip_tokens:
            theirs_raw = _strip_official_no(theirs_raw, strip_tokens)
        if t2s:
            theirs_raw = t2s_baseline(theirs_raw)
        theirs = normalize(theirs_raw, ruby_brackets)
        try:
            os.makedirs(outdir, exist_ok=True)
            src_cmp = os.path.join(outdir, f"{stem}_compare_xml_official.txt")
            gen_cmp = os.path.join(outdir, f"{stem}_compare_txt_generated.txt")
            theirs_disp = re.sub(r"\[[^\]\[]{1,8}\]", "", theirs_raw)
            ours_disp = re.sub(r"\[[^\]\[]{1,8}\]", "", ours_raw)
            theirs_disp = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", theirs_disp)
            ours_disp = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", ours_disp)
            theirs_disp = re.sub(r"\n{3,}", "\n\n", theirs_disp).strip() + "\n"
            ours_disp = re.sub(r"\n{3,}", "\n\n", ours_disp).strip() + "\n"
            with open(src_cmp, "w", encoding="utf-8") as f:
                f.write(theirs_disp)
            with open(gen_cmp, "w", encoding="utf-8") as f:
                f.write(ours_disp)
        except Exception:
            src_cmp = gen_cmp = ""
        m, mi, ex, ctx = diff_stats(ours, theirs)
        total = mi + ex
        status = "ok" if total <= max_diff else "fail"
        return {"xml": xml_fn, "fmt": fmt, "status": status, "gen": gen_path,
                "official": xml_fn, "official_kind": "xml", "matched": m,
                "missing": mi, "extra": ex, "total": total, "ctx": ctx,
                "src_cmp": src_cmp, "gen_cmp": gen_cmp}
    scope_juan = bool((cfg or {}).get("scope_juan", True))
    _juan = work_juan_numbers(work) if scope_juan else None

    def _discover():
        out = {}
        for k in ("html", "txt", "txt_notes", "docx", "epub", "odt"):
            found = find_official(source, stem, k, juan=_juan if k in ("html", "docx", "txt_notes") else None)
            if found:
                out[k] = found
        return out

    official = _discover()
    base_kind = {"md":"txt","docx":"docx","html":"html","epub":"epub","txt":"txt"}.get(fmt,"html")
    bases = []
    if base_kind in official:
        bases.append((base_kind, official[base_kind]))
    # docx 无官方时回退 html 比较（用户要求）；txt 不回退——无官方 txt 直接 no_baseline
    if fmt != "txt":
        fb = official.get("html")
        if fb and all(p != fb for _,p in bases):
            bases.append(("html", fb))
    if t2s and "txt_notes" in official and all(p != official["txt_notes"] for _, p in bases):
        # 简体统一：txt_notes 优先（传统不动；缺失时落回现有顺序）
        bases.insert(0, ("txt_notes", official["txt_notes"]))
    if not bases and bool((cfg or {}).get("auto_fetch", True)):
        # 基线缺失：按需调用 fetch 下载（docx/odt 非 T/X 等 404 静默跳过）
        from .fetch import ensure_baselines
        presets = load_presets(config_path) if config_path else load_presets()
        need = {"md": ["txt"], "docx": ["docx", "html"], "txt": ["txt"],
                "html": ["html"], "epub": ["epub"]}.get(fmt, ["html"])
        if t2s and "txt_notes" not in need:
            need = ["txt_notes"] + need
        # 材料化模型：基线落 cbeta_ebook work 目录（缺省回退 source）
        ebook = ((presets.get("source") or {}).get("cbeta_ebook") or "").strip() \
            or source
        ensure_baselines(work.id, need, presets, ebook)
        official = _discover()
        bases = []
        if base_kind in official:
            bases.append((base_kind, official[base_kind]))
        if fmt != "txt":
            fb = official.get("html")
            if fb and all(p != fb for _,p in bases):
                bases.append(("html", fb))
        if t2s and "txt_notes" in official and all(p != official["txt_notes"] for _, p in bases):
            bases.insert(0, ("txt_notes", official["txt_notes"]))
    if not bases:
        return {"xml": xml_fn, "fmt": fmt, "status": "no_baseline", "gen": gen_path, "official": None}
    best = None
    for bkind, bpath in bases:
        if isinstance(bpath, list) and bkind in ("docx", "txt") and len(bpath) > 1:
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
                    txt = extract_text(p)
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
            theirs_raw = extract_text(bpath[0])
            if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                title = t_title
                theirs_raw = strip_docx_head(theirs_raw, title, t_docnumber, t_series)
            if not compare_infos:
                theirs_raw = strip_infos(theirs_raw)
            bpath_disp = bpath[0]
        else:
            theirs_raw = extract_text(bpath)
            if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                title = t_title
                theirs_raw = strip_docx_head(theirs_raw, title, t_docnumber, t_series)
            if not compare_infos:
                theirs_raw = strip_infos(theirs_raw)
            bpath_disp = bpath
        if bkind in ("txt", "txt_notes"):
            # text 族官方侧对齐（繁简通用）：版头剥离 + 注记块识别挪文末，
            # 与生成侧正文+注块同构；无注记行为无操作
            theirs_raw = _norm_official_txt(theirs_raw)
        if strip_tokens:
            theirs_raw = _strip_official_no(theirs_raw, strip_tokens)
        if t2s:
            # 简体校验：官方基线（繁体）经同一 t2s 管线转简体后再比对；
            # 作用于剥离后的纯文本，落盘 _compare 文件与比对输入一致
            theirs_raw = t2s_baseline(theirs_raw)
        theirs = normalize(theirs_raw, ruby_brackets)
        try:
            os.makedirs(outdir, exist_ok=True)
            src_cmp = os.path.join(outdir, f"{stem}_compare_{bkind}_official.txt")
            gen_cmp = os.path.join(outdir, f"{stem}_compare_{fmt}_generated.txt")
            theirs_disp = re.sub(r"\[[^\]\[]{1,8}\]", "", theirs_raw)
            ours_disp = re.sub(r"\[[^\]\[]{1,8}\]", "", ours_raw)
            theirs_disp = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", theirs_disp)
            ours_disp = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", ours_disp)
            # 比较文件可读性：压缩多余空行（html 抽取每段落加换行导致大量空白行）
            theirs_disp = re.sub(r"\n{3,}", "\n\n", theirs_disp).strip() + "\n"
            ours_disp = re.sub(r"\n{3,}", "\n\n", ours_disp).strip() + "\n"
            with open(src_cmp, "w", encoding="utf-8") as f:
                f.write(theirs_disp)
            with open(gen_cmp, "w", encoding="utf-8") as f:
                f.write(ours_disp)
        except Exception:
            src_cmp = gen_cmp = ""
        m, mi, ex, ctx = diff_stats(ours, theirs)
        total = mi + ex
        cur = (bkind, bpath_disp, m, mi, ex, ctx, total, src_cmp, gen_cmp)
        if best is None or total < best[6]:
            best = cur
        if total <= max_diff:
            return {"xml": xml_fn, "fmt": fmt, "status": "ok", "gen": gen_path, "official": bpath_disp, "official_kind": bkind, "matched": m, "missing": mi, "extra": ex, "total": total, "ctx": ctx, "src_cmp": src_cmp, "gen_cmp": gen_cmp}
    bkind, bpath, m, mi, ex, ctx, total, src_cmp, gen_cmp = best
    return {"xml": xml_fn, "fmt": fmt, "status": "fail", "gen": gen_path, "official": bpath, "official_kind": bkind, "matched": m, "missing": mi, "extra": ex, "total": total, "ctx": ctx, "src_cmp": src_cmp, "gen_cmp": gen_cmp}
