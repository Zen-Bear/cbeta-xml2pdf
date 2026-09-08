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
from .theme import load_presets, _PRESETS_PATH

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
    仅简体统一流程调用；传统路径不动。"""
    bodies, notes = [], []
    for ln in text.split("\n"):
        if _NOTE_LINE_RE.match(ln):
            notes.append(ln)
        else:
            bodies.append(ln)
    return "\n".join(bodies), "\n".join(notes)


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
        from .theme import (load_run_config, resolve_base_config,
                            default_run_path)
        _run = load_run_config(config_path) if config_path else load_run_config()
        _rdir = os.path.dirname(os.path.abspath(config_path)) if config_path \
            else os.path.dirname(os.path.abspath(default_run_path()))
        presets = load_presets(resolve_base_config(_run, _rdir))
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
    if fmt in ("docx", "md") and _run is not None:
        try:
            from .theme import resolve_pdf_docx_css, Theme as _Theme
            theme = _Theme.from_css(resolve_pdf_docx_css(_run, _rdir), "zh-Hant")
        except (OSError, ValueError):
            theme = None
    p = lambda k, d=None: out_defaults.get(k, d)
    if fmt == "html":
        files = HtmlRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=p("show_notes", True), inline_brackets=p("inline_brackets", "fullwidth"), annotations=_ann).render_work(work, out_dir=outdir)
        return [os.path.join(outdir, f) for f in files]
    if fmt == "docx":
        return [os.path.join(outdir, DocxRenderer(theme=theme, notes="footnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=p("show_notes", True), suppress_jhead_dup=p("suppress_jhead_dup", True), show_close_juan=bool(p("show_close_juan", False)), inline_brackets=p("inline_brackets", "fullwidth"), series_title=p("series_title", {}), annotations=_ann).render_work(work, out_dir=outdir, filename=f"{stem}.docx"))]
    if fmt == "epub":
        return [os.path.join(outdir, EpubRenderer(theme=theme, notes="endnote", ignore_xml_style=bool(p("ignore_xml_style")), ignore_xml_space=bool(p("ignore_xml_space")), show_notes=p("show_notes", True), annotations=_ann).render_work(work, out_dir=outdir, filename=f"{stem}.epub"))]
    if fmt == "md":
        return [os.path.join(outdir, MdRenderer(theme=theme, notes="footnote", show_notes=p("show_notes", True), inline_brackets=p("inline_brackets", "fullwidth"), annotations=_ann).render_work(work, out_dir=outdir, filename=f"{stem}.md"))]
    raise ValueError(f"unknown format {fmt}")

def verify_one(xml_fn: str, fmt: str, source: str, out_root: str, max_diff: int = 10, diff_lines: int = 5, config_path: Optional[str] = None, t2s: bool = False) -> Dict:
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
    if not compare_infos:
        ours_raw = strip_infos(ours_raw)
    ours = normalize(ours_raw, ruby_brackets)
    name = os.path.basename(xml_fn)
    stem = os.path.splitext(name)[0]
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
    base_kind = {"md":"txt","docx":"docx","html":"html","epub":"epub"}.get(fmt,"html")
    bases = []
    if base_kind in official:
        bases.append((base_kind, official[base_kind]))
    # docx 无官方时回退 html 比较（用户要求）
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
        need = {"md": ["txt"], "docx": ["docx", "html"],
                "html": ["html"], "epub": ["epub"]}.get(fmt, ["html"])
        if t2s and "txt_notes" not in need:
            need = ["txt_notes"] + need
        ensure_baselines(work.id, need, presets, source)
        official = _discover()
        bases = []
        if base_kind in official:
            bases.append((base_kind, official[base_kind]))
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
        if t2s and bkind in ("txt", "txt_notes"):
            # 简体：text 族注记块移文末，与生成侧文末注记对齐（传统不动；
            # true-txt 无注记行时为无操作）
            _tb, _tn = _extract_txt_parts(theirs_raw)
            theirs_raw = _tb + "\n" + _tn if _tn.strip() else _tb
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
