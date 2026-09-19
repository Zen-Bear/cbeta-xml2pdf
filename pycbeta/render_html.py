"""HTML renderer producing the official CBETA format (cb_note style)."""

import html
import os
import re
from contextlib import contextmanager
from typing import List, Optional

from .gaiji import GaijiDb
from .annotate import active as _ann_active, split_annotated as _split_ann, rt_css_rule as _rt_css, track_seen as _track_seen, page_repeat as _page_repeat
from .model import App, E, Gaiji, Lb, Note, NoteRef, Pb, Text, Work
from .theme import strip_head_no, bracket_pair

# 官方（golden）格式基底 CSS：styles/cbeta_golden.css（html/epub 用）。
# pdf/docx 的默认主题是 styles/pdf_docx.css（theme.py 加载）。base_css 供
# 库调用方自定义基底；CLI 直接用内置文件，不暴露参数。
_CBETA_CSS_PATH = os.path.join(os.path.dirname(__file__), "styles", "cbeta_golden.css")


def _load_cbeta_css() -> str:
    try:
        with open(_CBETA_CSS_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


CSS = _load_cbeta_css()

LINEHEAD_RE = re.compile(
    r"^[A-Z]{1,2}\d{2,3}n(?:\d{4}[a-zA-Z]?|[ABa]\d{3})_p\d+[a-z]\d+$"
)


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def split_juans(body) -> List[tuple]:
    """把 body 按 <milestone unit="juan"/> 切成 [(卷号, ops)]，ops 为
    ('open'/'close'/'node'/'milestone', node) 扁平事件流（跨卷 div 会补 close/open）。
    pdf/docx 按卷输出（split）与目录书签都依赖它。"""
    events = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, E) and n.tag == "div":
                events.append(("open", n))
                walk(n.children)
                events.append(("close", n))
            elif isinstance(n, E) and n.tag == "milestone" and n.attrs.get("unit") == "juan":
                events.append(("milestone", n))
            else:
                events.append(("node", n))

    walk(body)
    juans = []
    cur_no = 0
    cur = []
    open_divs = []

    def meaningful(ops):
        for kind, n in ops:
            if kind != "node":
                return True
            if isinstance(n, Text):
                if n.text.strip():
                    return True
            else:
                return True
        return False

    for kind, n in events:
        if kind == "milestone":
            if cur and meaningful(cur):
                for d in reversed(open_divs):
                    cur.append(("close", d))
                juans.append((cur_no, cur))
            cur = []
            for d in open_divs:
                cur.append(("open", d))
            cur_no = int(n.attrs.get("n")) if n.attrs.get("n") else cur_no + 1
        else:
            if kind == "open":
                open_divs.append(n)
            elif kind == "close":
                if open_divs and open_divs[-1] is n:
                    open_divs.pop()
            cur.append((kind, n))
    if cur and meaningful(cur):
        juans.append((cur_no, cur))
    return juans


class HtmlRenderer:
    def __init__(self, gaiji_db=None, figure_base=None, theme=None, notes="endnote",
                 name_template=None, base_css=None, ignore_xml_style=False,
                 ignore_xml_space=False, show_notes=True, grayscale=False, inline_brackets="fullwidth",
                 note_inline_brackets=None,
                 annotations=None, strip_head_no=False, corr_cbeta=False):
        self.gaiji_db = gaiji_db if gaiji_db is not None else GaijiDb()
        self.theme = theme
        # 图片搜索目录：str | list[str]（{work}/figures → {work}/txt → 仓库 figures）
        fb = [figure_base] if isinstance(figure_base, str) else list(figure_base or [])
        self.figure_dirs = [d for d in fb if d]
        self.missing_figures = []  # 本次渲染缺失的图片 basename（警告用，不中断）
        self.notes = notes  # 'endnote' (official) | 'inline'
        self.name_template = name_template
        self.base_css = base_css if base_css is not None else CSS
        self.ignore_xml_style = ignore_xml_style
        self.ignore_xml_space = ignore_xml_space
        self.show_notes = show_notes
        self.grayscale = grayscale  # 黑白：渲染时追加全局去色 CSS
        self.inline_brackets = inline_brackets  # 正文夹注（place=inline，原文）括号
        self.note_inline_brackets = note_inline_brackets or inline_brackets  # 校注内联括号（缺省回退）
        self.strip_head_no = strip_head_no  # 去 head/jhead 行首 No. 令牌（默认 false 保留）
        self.corr_cbeta = corr_cbeta        # CBETA 校改字标红（corr-cbeta；默认 false）
        # 难字注音（P6）：None 或 {"table", "scheme"}（CLI 已由 resolve_annotations 装载；渲染器内不做 IO）
        self._annotations = _ann_active(annotations)
        self._ann_seen = set()  # repeat first/page 已注词集合（render_work 起始终置零）
        self._work = None
        self._note_seq = 0
        self._old_seq = 0
        self._back_old = []  # orig/mod footnotes (old format), rendered first
        self._back_cb = []   # add footnotes (cb_note format), rendered after
        self._lb = None
        self._div_stack = 0
        self._in_pre = False

    @contextmanager
    def _no_ann(self):
        """标题/题署块内压制注音（P6：仅正文 Text 注音，head/byline/juan/jhead/docNumber 不注）。"""
        save = self._annotations
        self._annotations = None
        try:
            yield
        finally:
            self._annotations = save

    def render_work(self, work: Work, out_dir: str) -> List[str]:
        os.makedirs(out_dir, exist_ok=True)
        self._work = work
        self._ann_seen = set()
        self.missing_figures = []
        self._app_by_n = {}
        for n in self._iter_all(work.body):
            if isinstance(n, App) and n.key:
                self._app_by_n[n.key[3:]] = n
        juans = self._split_juans(work.body)
        written = []
        for juan_no, nodes in juans:
            self._note_seq = 0
            self._old_seq = 0
            self._back_old = []
            self._back_cb = []
            self._div_stack = 0
            self._lb = None
            self._in_pre = False
            # repeat=page：每卷文件已注清零，本卷词首现重注
            if _page_repeat(self._annotations):
                self._ann_seen = set()
            body = self._render_ops(nodes)
            html_out = self._wrap(body, work, juan_no)
            if self.name_template:
                from .filename import apply_template
                fn = apply_template(self.name_template, work, juan=juan_no) + ".html"
            else:
                fn = f"{work.id}_{juan_no:03d}.html"
            with open(os.path.join(out_dir, fn), "w", encoding="utf-8") as f:
                f.write(html_out)
            written.append(fn)
        return written

    def _split_juans(self, body) -> List[tuple]:
        return split_juans(body)

    def _render_ops(self, ops) -> str:
        out = []
        self._div_stack = 0
        for kind, n in ops:
            if kind == "open":
                t = n.attrs.get("type")
                cls = f' class="div-{_esc(t)}"' if t else ""
                out.append(f"<div{cls}>")
                self._div_stack += 1
            elif kind == "close":
                out.append("</div>")
                self._div_stack -= 1
            else:
                out.append(self._render_node(n))
        return "".join(out)

    def _iter_all(self, nodes):
        for n in nodes:
            yield n
            if isinstance(n, App):
                if n.lem is not None:
                    yield from self._iter_all([n.lem])
                yield from self._iter_all(n.rdgs)
            if getattr(n, "children", None):
                yield from self._iter_all(n.children)

    def _wrap(self, body, work, juan_no) -> str:
        md = work.metadata
        title = md.get("title") or work.id
        lang = "zh-Hans" if getattr(work, "simplified", False) else "zh-Hant"
        notes = "" if self.notes == "inline" else ("".join(self._back_old) + "\n\n".join(self._back_cb))
        back = "  <hr><h1>校注</h1>\n" + notes + "\n\n" if notes else "  \n"
        theme_css = self.theme.raw_css if self.theme and self.theme.raw_css else (
            self.theme.css() if self.theme else "")
        theme_block = "\n" + theme_css if theme_css else ""
        gray_rule = ("\n    * { color: #000 !important; background-color: #fff !important; "
                     "border-color: #000 !important; }"
                     "\n    a, a:visited { color: #000 !important; }") if self.grayscale else ""
        inline_rule = ""
        if self.notes == "inline":
            props = (self.theme.tags.get("note-inline") or {}) if self.theme else {}
            if props:
                decls = "; ".join(f"{k}: {v}" for k, v in props.items() if v)
                inline_rule = f"\n    span.note-inline {{ {decls} }}"
            else:
                inline_rule = "\n    span.note-inline { font-size: 0.9em; color: #666; }"
        # 注音 rt 字号字体（P6）：ruby style 时输出 ruby rt 规则（行内模式无 rt 元素则为空）
        ann_rule = _rt_css(self._annotations) if self._annotations is not None else ""
        parts = [
            f'<html lang="{lang}">\n<head>\n',
            '  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />\n',
            f"  <title>{_esc(title)}</title>\n",
            "  <style>\n",
            self.base_css,
            theme_block,
            inline_rule,
            ann_rule,
            gray_rule,
            "  </style>\n",
            "</head>\n<body>\n",
            "<div id='body'>\n  ",
            body,
            "\n</div>\n",
            "<div id='back'>\n",
            back,
            "</div>\n",
            self._copyright(md),
            "</body></html>",
        ]
        return "".join(parts)

    def _copyright(self, md) -> str:
        source = md.get("source") or "CBETA"
        title = md.get("title") or ""
        contributors = md.get("contributors") or ""
        pub = md.get("publication_date") or ""
        pub = pub.split(" ")[0]
        vol = md.get("vol") or ""
        no = md.get("no") or ""
        vol_no = f"第 {_esc(vol)} 冊 No. {_esc(no)} " if vol and no else ""
        r = "<div id='cbeta-copyright'><p>\n"
        r += f"【經文資訊】{_esc(source)} {vol_no}{_esc(title)}<br>\n"
        r += f"【版本記錄】發行日期：{_esc(pub)}，最後更新：{_esc(pub)}<br>\n"
        r += f"【編輯說明】本資料庫由 財團法人佛教電子佛典基金會（CBETA）依「{_esc(source)}」所編輯<br>\n"
        r += f"【原始資料】{_esc(contributors)}<br>\n"
        r += "【其他事項】詳細說明請參閱【<a href='https://www.cbeta.org/copyright' target='_blank'>財團法人佛教電子佛典基金會資料庫版權宣告</a>】\n"
        r += "</p></div><!-- end of cbeta-copyright -->\n"
        return r

    def _render_nodes(self, nodes) -> str:
        out = []
        i = 0
        total = len(nodes)
        while i < total:
            node = nodes[i]
            if isinstance(node, Pb):
                if (i + 1 < total and isinstance(nodes[i + 1], Text)
                        and not nodes[i + 1].text.strip(" \t\n\r")):
                    i += 2
                    continue
                i += 1
                continue
            out.append(self._render_node(node))
            i += 1
        return "".join(out)

    def _first_line(self, node) -> Optional[str]:
        if isinstance(node, Text):
            return node.line
        for c in getattr(node, "children", []):
            ln = self._first_line(c)
            if ln:
                return ln
        return None

    def _line_info(self, node) -> str:
        ln = self._first_line(node) or self._lb or ""
        return f"<span class='lineInfo' line='{_esc(ln)}'></span>"

    def _render_node(self, node) -> str:
        if isinstance(node, Text):
            t = node.text
            if self.ignore_xml_space:
                t = t.strip(" \t\u3000")
            if not self._in_pre:
                t = re.sub(r"[\n\r]", "", t)
                if not t.strip(" \t"):
                    return ""
            if self._annotations is not None:
                return self._ann_text(t)
            return _esc(t)
        if isinstance(node, Lb):
            if node.lbtype != "old":
                self._lb = node.n
            return ""
        if isinstance(node, Pb):
            return ""
        if isinstance(node, E) and node.tag == "milestone":
            return ""
        if isinstance(node, Gaiji):
            return self._render_gaiji(node)
        if isinstance(node, NoteRef):
            return self._render_noteref(node)
        if isinstance(node, Note):
            return self._render_note(node)
        if isinstance(node, App):
            return ""
        if isinstance(node, E):
            return self._render_e(node)
        return ""

    def _resolve_gaiji_raw(self, code: str, raw: str) -> str:
        # 优先级：gaiji_db（CBETA 全局缺字表，与官方 html 一致）→ charDecl（本经 charDecl，兜底）→ raw
        data = self.gaiji_db.get(code) if self.gaiji_db else None
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
        chard = (self._work.metadata.get("charDecl") or {}) if self._work else {}
        rec = chard.get(code)
        if rec:
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

    def _resolve_gaiji(self, code: str, raw: str) -> str:
        char = self._resolve_gaiji_raw(code, raw)
        if getattr(self._work, "simplified", False):
            # 简体模式：渲染时解析的缺字同样过 t2s 管线（与官方侧 t2s_baseline 对齐）
            from .simplify import simplify_text
            return simplify_text(char)
        return char

    def _ann_text(self, t: str) -> str:
        """注音发射（P6）：Text 与解析后缺字共用（词表+生僻字兜底）。"""
        ann = self._annotations
        segs = _split_ann(t, ann["table"], ann["scheme"],
                          ann.get("rare_zones", frozenset()),
                          ann.get("rare_cmap"),
                          _track_seen(ann, self._ann_seen),
                          ann.get("full_text", False))
        if ann.get("style", "inline") == "inline":
            # 右侧行内：纯文本括注（Word 打开 html、旧浏览器等无 ruby 环境可见）
            l, r = ann.get("brackets", ["〔", "〕"])
            return "".join(
                _esc(seg) if reading is None
                else f"{_esc(seg)}{l}{_esc(reading)}{r}"
                for seg, reading in segs)
        return "".join(
            _esc(seg) if reading is None
            else f"<ruby>{_esc(seg)}<rt>{_esc(reading)}</rt></ruby>"
            for seg, reading in segs)

    def _gaiji_roman(self, code: str) -> str:
        """悉昙读音（charDecl Romanized form，Unicode 式优先），无则 ""。"""
        chard = (self._work.metadata.get("charDecl") or {}) if self._work else {}
        rec = chard.get(code) or {}
        return (rec.get("roman") or rec.get("roman_cbeta") or "").strip()

    def _render_gaiji(self, node: Gaiji) -> str:
        raw = node.char or node.code
        roman = self._gaiji_roman(node.code)
        if roman:
            # 悉昙缺字：官方同款 ranja 空元素（读音走 roman 属性 + CSS 显示；
            # 文本抽取为空，与官方 html 一致，不污染逐字校验）
            chard = (self._work.metadata.get("charDecl") or {}) if self._work else {}
            glyph = ((chard.get(node.code) or {}).get("rjchar")
                     or self._resolve_gaiji(node.code, raw))
            return (f"<span class='ranja' roman='{_esc(roman)}' "
                    f"code='{_esc(node.code)}' char='{_esc(glyph)}'/>")
        if raw and ord(raw[0]) >= 0x2A700:
            char = self._resolve_gaiji(node.code, raw)
            if self._annotations is not None:
                inner = self._ann_text(char)
                return f'<span class="gaiji" data-gid="{_esc(node.code)}">{inner}</span>'
            return f'<span class="gaiji" data-gid="{_esc(node.code)}">{_esc(char)}</span>'
        char = self._resolve_gaiji(node.code, raw)
        if self._annotations is not None:
            return self._ann_text(char)
        return _esc(char)

    def _render_e(self, e: E) -> str:
        if e.tag == "app":
            # 正文内联校勘（P5a/P5b）：base 读法只在 <lem>，只渲染 lem；rdg 是异读不进正文
            lem = next((c for c in e.children
                        if isinstance(c, E) and c.tag == "lem"), None)
            return self._render_nodes(lem.children) if lem is not None else ""
        tag = e.tag
        a = e.attrs
        if tag == "div":
            return self._render_div(e)
        if tag == "p":
            return self._render_p(e) + "\n"
        if tag == "head":
            level = self._div_stack
            kids = strip_head_no(e.children)[0] if self.strip_head_no else e.children
            with self._no_ann():
                inner = self._render_nodes(kids)
            return f'<p data-head-level="{level}" class="head">{inner}</p>'
        if tag == "byline":
            with self._no_ann():
                inner = self._render_nodes(e.children)
            return f'<p class="byline">{self._line_info(e)}{inner}</p>\n'
        if tag == "juan":
            with self._no_ann():
                inner = self._render_nodes(e.children)
            return f"<p class='juan'>{inner}</p>"
        if tag == "jhead":
            kids = strip_head_no(e.children)[0] if self.strip_head_no else e.children
            if a.get("type") == "pin":
                # 品名：与其他品名一致，渲染成 head 段落（data-head-level + class=head）
                level = self._div_stack
                with self._no_ann():
                    inner = self._render_nodes(kids)
                return f'<p data-head-level="{level}" class="head">{inner}</p>'
            with self._no_ann():
                return self._render_nodes(kids)
        if tag == "docNumber":
            # 编号行（No. XXXX）：与 head/jhead 同源，strip_head_no 开启时整体省略
            # （docx 恒不显；html/epub/md/txt 官方版保留，故默认保留）
            if self.strip_head_no:
                return ""
            with self._no_ann():
                return self._render_nodes(e.children)
        if tag == "lg":
            return self._render_lg(e)
        if tag == "l":
            return self._render_l(e)
        if tag == "caesura":
            return ""
        if tag == "list":
            cls = ' class="no-marker"' if a.get("rend") == "no-marker" else ""
            return f"<ul{cls}>{self._render_nodes(e.children)}</ul>"
        if tag == "item":
            return f"<li>{self._render_nodes(e.children)}</li>\n"
        if tag == "form":
            return f'<p class="form">{self._render_nodes(e.children)}</p>\n'
        if tag in ("entry", "def", "term", "foreign", "hi", "seg", "quote", "ref", "title",
                   "yin", "zi", "sg", "unclear", "choice", "corr", "corr-cbeta", "sic", "reg",
                   "table", "row", "cell",
                   "figure", "graphic", "anchor", "bibl", "biblScope", "sp", "event", "date", "idno",
                   "space", "pb", "lb", "mulu", "milestone"):
            return self._render_misc(e)
        return self._render_nodes(e.children)

    def _render_div(self, e: E) -> str:
        a = e.attrs
        cls = ""
        t = a.get("type")
        if t:
            cls = f" class=\"div-{_esc(t)}\""
        self._div_stack += 1
        inner = self._render_nodes(e.children)
        self._div_stack -= 1
        return f"<div{cls}>{inner}</div>"

    def _render_p(self, e: E) -> str:
        a = e.attrs
        ptype = a.get("cb:type") or a.get("type")
        style = a.get("style")
        if self.ignore_xml_style:
            style = None
        if ptype == "pre":
            s = f' style="{_esc(style)}"' if style else ""
            prev = self._in_pre
            self._in_pre = True
            inner = self._render_nodes(e.children)
            self._in_pre = prev
            return f'<pre class=""{s}>{self._line_info(e)}{inner}</pre>'
        if ptype:
            cls = f" class=\"{_esc(ptype)}\""
        else:
            from .figures import is_figure_only
            cls = ' class="figure"' if is_figure_only(e) else ' class=""'
        s = f' style="{_esc(style)}"' if style else ""
        return f"<p{cls}{s}>{self._line_info(e)}{self._render_nodes(e.children)}</p>"

    def _render_tt(self, e: E) -> str:
        """对照块：转写行（sa-x-rj）包 transliteration span（官方朱砂色）；
        文本与泛型扁平渲染一致，不影响逐字校验。"""
        out = []
        for c in e.children:
            if isinstance(c, E) and c.tag == "t" and \
                    (c.attrs.get("xml:lang") or "").startswith("sa"):
                out.append("<span class='transliteration'>"
                           + self._render_nodes(c.children) + "</span>")
            else:
                out.append(self._render_node(c))
        return "".join(out)

    def _render_lg(self, e: E) -> str:
        a = e.attrs
        t = a.get("type")
        style = (a.get("style") or "").replace("text-indent:-1em", "").replace("text-indent:-2em", "").rstrip(";")
        indent = ""
        m = __import__("re").search(r"text-indent:([^;]*)", a.get("style") or "")
        if m:
            indent = m.group(1).strip()
        cls = f"lg {t}" if t else "lg"
        s = f' style="{_esc(style)}"' if style else ""
        rows = self._render_lg_rows(e.children, indent)
        return f'<div class="{cls}"{s}>{rows}</div>'

    def _render_lg_rows(self, children, indent: str) -> str:
        out = []
        first = True
        for c in children:
            if isinstance(c, E) and c.tag == "l":
                cells = self._split_l_cells(c)
                first_style = f" style='text-indent:{indent}'" if first and indent else ""
                first = False
                cell_html = "".join(f"<div class='lg-cell'{first_style if i == 0 else ''}>{part}</div>"
                                    for i, part in enumerate(cells))
                out.append(f'<div class="lg-row">{cell_html}</div>')
            else:
                out.append(self._render_node(c))
        return "".join(out)

    def _split_l_cells(self, l: E) -> List[str]:
        parts = []
        buf = []
        for c in l.children:
            if isinstance(c, E) and c.tag == "caesura":
                parts.append(self._render_nodes(buf))
                buf = []
            else:
                buf.append(c)
        if buf or not parts:
            parts.append(self._render_nodes(buf))
        return parts

    def _render_l(self, e: E) -> str:
        return ""

    def _render_note(self, note: Note) -> str:
        # 正文夹注（<note place="inline">）属原文，不受「注释总开关」控制
        if note.place in ("inline", "inline2", "interlinear"):
            inner = self._render_nodes(note.children)
            lb, rb = bracket_pair(self.inline_brackets)
            if note.place == "interlinear":
                return f'<span class="interlinear-note">{lb}{inner}{rb}</span>'
            return f"<span class='doube-line-note'>{lb}{inner}{rb}</span>"
        return ""

    def _render_noteref(self, ref: NoteRef) -> str:
        if not self.show_notes:
            return ""
        notes = ref.notes
        if not notes:
            return ""
        note = self._pick_note(notes)
        content = self._render_nodes(note.children).strip()
        if self.notes == "inline":
            app = self._app_by_n.get(note.n or "")
            if app is not None and app.lem is not None:
                cfs = [c for c in app.lem.children
                       if isinstance(c, Note) and (c.ntype or "").startswith("cf")]
                if cfs:
                    refs = "; ".join(self._render_cf(app, c) for c in cfs)
                    content += f"(cf. {refs})"
            lb, rb = bracket_pair(self.note_inline_brackets)
            return f"<span class='note-inline'>{lb}{content}{rb}</span>"
        if note.ntype == "add":
            self._note_seq += 1
            seq = self._note_seq
            app = self._app_by_n.get(note.n or "")
            if app is not None and app.lem is not None:
                cfs = [c for c in app.lem.children
                       if isinstance(c, Note) and (c.ntype or "").startswith("cf")]
                if cfs:
                    refs = "; ".join(self._render_cf(app, c) for c in cfs)
                    content += f"(cf. {refs})"
            self._back_cb.append(
                f"<div class='footnote' id='cb_note_{seq}'>\n"
                f"  [<a href='#cb_note_anchor{seq}'>A{seq}</a>] {content}\n"
                f"</div>"
            )
            return f"<a id='cb_note_anchor{seq}' class='noteAnchor add' href='#cb_note_{seq}'>[A{seq}]</a>"
        n = note.n or ""
        self._old_seq += 1
        seq = self._old_seq
        self._back_old.append(
            f"<span class='footnote' id='n{_esc(n)}'><a href='#note_anchor_{_esc(n)}'>[{_esc(n)}]</a> {content}</span>\n"
        )
        return f'<a id="note_anchor_{_esc(n)}" class="noteAnchor" href="#n{_esc(n)}">[{seq}]</a>'

    @staticmethod
    def _render_cf(app: Optional[App], note: Note) -> str:
        s = "".join(t.text for t in note.children if isinstance(t, Text))
        provider = app.lem.attrs.get("cb:provider") if app and app.lem else None
        if LINEHEAD_RE.match(s) and not provider:
            return f"<span class='cbeta-linehead'>{_esc(s)}</span>"
        return _esc(s)

    @staticmethod
    def _pick_note(notes: List[Note]) -> Note:
        for t in ("mod", "orig", "add", "equivalent", "rest"):
            for n in notes:
                if n.ntype == t:
                    return n
        return notes[0]

    def _render_misc(self, e: E) -> str:
        tag = e.tag
        if tag == "unclear":
            return "□"  # 文字无法辨析：标准虚缺符号 U+25A1
        if tag == "anchor":
            if e.attrs.get("type") == "circle":
                return "◎"
            return ""
        if tag == "space":
            try:
                q = int(e.attrs.get("quantity") or 1)
            except ValueError:
                q = 1
            return "　" * q
        if tag == "mulu":
            return ""
        if tag == "graphic":
            return self._render_graphic(e)
        if tag == "figure":
            return self._render_nodes(e.children)
        if tag in ("table", "row", "cell"):
            return self._render_table(e)
        if tag == "sic":
            return ""
        if tag == "sg":
            # 梵呗注音（<cb:sg>）：官方半角括号，如 (音𫬠)
            return "(" + self._render_nodes(e.children) + ")"
        if tag == "tt":
            return self._render_tt(e)
        if tag == "choice":
            return self._render_nodes(e.children)
        if tag == "corr":
            return self._render_nodes(e.children)
        if tag == "corr-cbeta":
            # CBETA 校改字（parser 包出；默认关＝透明）：开则 span.corr 红字
            inner = self._render_nodes(e.children)
            if not self.corr_cbeta:
                return inner
            return f'<span class="corr">{inner}</span>'
        if tag == "reg":
            return self._render_nodes(e.children)
        return self._render_nodes(e.children)

    def _render_graphic(self, e: E) -> str:
        from .figures import find_figure, graphic_basename
        url = e.attrs.get("url") or ""
        base = graphic_basename(url)
        if base:
            path = find_figure(base, self.figure_dirs)
            if path:
                import base64
                data = base64.b64encode(open(path, "rb").read()).decode("ascii")
                mime = path.rsplit(".", 1)[-1].lower() or "png"
                return f'<img src="data:image/{_esc(mime)};base64,{data}" />'
            if base not in self.missing_figures:
                self.missing_figures.append(base)
        return f"<span imgsrc='{_esc(os.path.basename(url))}' class='graphic'></span>"

    def _render_table(self, e: E) -> str:
        if e.tag == "table":
            style = e.attrs.get("style")
            s = f' style="{_esc(style)}"' if style else ""
            return f'<div class="bip-table"{s}>{self._render_nodes(e.children)}</div>'
        if e.tag == "row":
            return f"<div class='bip-table-row'>{self._render_nodes(e.children)}</div>"
        extra = ""
        if e.attrs.get("rows"):
            extra += f' rowspan="{_esc(e.attrs["rows"])}"'
        if e.attrs.get("cols"):
            extra += f' colspan="{_esc(e.attrs["cols"])}"'
        return f'<div class="bip-table-cell"{extra}>{self._render_nodes(e.children)}</div>'
