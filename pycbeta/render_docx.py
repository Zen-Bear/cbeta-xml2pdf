"""DOCX renderer: IR -> OOXML document with real Word footnotes.

Footnote pattern: footnotes.xml part + w:footnoteReference superscript runs
(same as official CBETA docx; 参考实现已归档 backup/20260902）。
Styling comes from the shared Theme (semantic tags -> OOXML props).
"""

import io
import os
import re
import zipfile
from contextlib import contextmanager
from typing import List, Optional

from .model import App, E, Gaiji, Lb, Note, NoteRef, Pb, Text, Work
from .gaiji import GaijiDb
from .theme import Theme, resolve_page, _hex6, strip_head_no, bracket_pair
from .render_html import split_juans
from .filename import apply_template
from .annotate import active as _ann_active, split_annotated as _split_ann, parse_rt_size as _parse_rt_size, split_eq_reading as _split_eq, track_seen as _track_seen, page_repeat as _page_repeat

_REND_TAGS = ("kaiti", "heiti", "mingti", "fangsong")


def split_sections(body, rules: dict) -> list:
    """按分页规则把 body 切成 [(卷号, ops)]（跨 div 补 close/open，同 split_juans）。

    rules: {juan, juan_first, mulu_level1, pb}。
    - milestone（卷边界）：juan 规则触发；首个卷边界默认不切（紧跟书名），juan_first=true 时也切
    - 卷头 juan（fun=open）：恒为断点（无开关），卷头/译者/首品同节；后续品仍由 mulu_level1 切分
    - <cb:mulu level="1"> 非"卷"型且有目录文字（序/品/其他）：mulu_level1 触发分页；
      但首个序/品紧跟书名题署块时不切（与 juan_first 无关，恒生效）
    - <cb:pb>：pb 规则（默认关）
    - 首个分页单元（节内尚无可见内容）不切；mulu/pb 节点归入新节（mulu 保留 pending 书签）；
      题署块（docNumber/title/byline/juan 卷头）不计为可见内容，故首个序/品贴书名时与标题页同节"""
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

    def mulu_text(n) -> str:
        parts = []
        for c in n.children:
            if isinstance(c, Text):
                parts.append(c.text)
            elif getattr(c, "children", None):
                parts.append(mulu_text(c))
        return "".join(parts)

    def is_break(kind, n) -> bool:
        if kind == "milestone":
            return bool(rules.get("juan", True))
        if not isinstance(n, E):
            return False
        if n.tag == "juan" and n.attrs.get("fun") == "open":
            return True  # 卷头开启新节：卷头/译者/首品同节（后续品仍由 mulu_level1 切分）
        if n.tag == "mulu" and rules.get("mulu_level1", True) and mulu_text(n).strip():
            return n.attrs.get("level") == "1" and n.attrs.get("type") != "卷"
        if n.tag == "pb" and rules.get("pb", False):
            return True
        return False

    def meaningful(ops) -> bool:
        """节内是否已有内容：lb/pb/space/anchor 渲染为空不计；
        题署块（docNumber/title/byline/juan 卷头，含 jhead/书名/卷次）不计，
        首个序/品贴书名时不切；
        level=1 非"卷"型有文字的 mulu 计为已有分页单元（首个单元保护：空节首 mulu 不切）。"""
        for kind, n in ops:
            if kind != "node":
                continue
            if isinstance(n, Text):
                if n.text.strip():
                    return True
            elif isinstance(n, (Lb, Pb)):
                continue
            elif isinstance(n, E):
                if n.tag in ("space", "milestone", "anchor",
                             "docNumber", "title", "byline",
                             "juan"):  # 卷头（含 jhead/书名/卷次）亦属题署块
                    continue
                if n.tag == "mulu":
                    if (n.attrs.get("level") == "1" and n.attrs.get("type") != "卷"
                            and mulu_text(n).strip()):
                        return True
                    continue
                return True
        return False

    walk(body)
    sections = []
    cur_no = None
    cur = []
    open_divs = []
    juan_first = bool(rules.get("juan_first", False))

    for kind, n in events:
        if is_break(kind, n):
            is_milestone = kind == "milestone"
            force = is_milestone and juan_first
            has_content = bool(cur and meaningful(cur))
            if has_content or force:
                for d in reversed(open_divs):
                    cur.append(("close", d))
                if meaningful(cur) or force:
                    sections.append((cur_no, cur))
                cur = []
                for d in open_divs:
                    cur.append(("open", d))
                if is_milestone:
                    cur_no = int(n.attrs.get("n")) if n.attrs.get("n") else (cur_no or 0) + 1
                else:
                    # mulu/pb 节点归入新节（mulu 保留 pending 书签，pb 渲染为空）
                    cur.append((kind, n))
            elif is_milestone:
                cur_no = int(n.attrs.get("n")) if n.attrs.get("n") else (cur_no or 0) + 1
            else:
                cur.append((kind, n))
        else:
            if kind == "open":
                open_divs.append(n)
            elif kind == "close":
                if open_divs and open_divs[-1] is n:
                    open_divs.pop()
            cur.append((kind, n))
    if cur and meaningful(cur):
        sections.append((cur_no, cur))
    return sections

# 段落级命名样式（styles.xml 里定义，段落用 <w:pStyle> 引用而非内联 pPr）
_STYLED_PARAS = ("title", "head", "juan", "pin", "p", "verse", "footnote", "byline",
                 "author", "translator", "series-title", "def", "div-note")

# 缺字回退链默认值（config output.docx.fallbackFonts 可覆盖；与预览 PREVIEW_FALLBACKS 对应。
# 按渲染语言分栏（gaiji_lang）：繁体优先明体、简体优先宋体；SimSunExtB 管 Ext-B 及以后；
# CBETA Supplement 管 Ext C-G 与私用区；微软雅黑垫底（系统必带、覆盖广，最后兜底）；
# 原字体文件缺失时不验证、保持原样。）
DEFAULT_FALLBACK_FONTS = {
    "zh-Hant": ("PMingLiU", "SimSun", "SimSunExtB", "CBETA Supplement",
                "Microsoft YaHei"),
    "zh-Hans": ("SimSun", "SimSunExtB", "PMingLiU", "CBETA Supplement",
                "Microsoft YaHei"),
}
# 悉昙字体默认值（config output.docx.siddhamFonts 可覆盖；RJ 码按覆盖选用，
# 官方 docx 同款 eastAsia="Ranjana"；语言无关，单列即可）
DEFAULT_SIDDHAM_FONTS = ("Ranjana", "Siddam")
_EASTASIA_RE = re.compile(r'w:eastAsia="([^"]+)"')


def _x(s: str) -> str:
    from xml.sax.saxutils import escape
    return escape(s)


_COLOR_RE = re.compile(r'<w:color[^>]*/>')


def _strip_color(xml: str) -> str:
    """全局黑白：去掉所有 <w:color …/> 颜色属性（含程序与 CSS 定义的一切颜色）。"""
    return _COLOR_RE.sub("", xml)


class DocxRenderer:
    def __init__(self, gaiji_db=None, theme=None, page="a4", notes="footnote",
                 page_presets=None, ignore_xml_style=False, ignore_xml_space=False,
                 verse_caesura="　　", verse_strip_quotes=False,
                 grayscale=False, page_border=False,
                 bookmarks=True, split=False, show_close_juan=False,
                 suppress_jhead_dup=True,
                 inline_brackets="fullwidth", note_inline_brackets=None,
                   footnote_per_page=True, show_notes=True,
                   suppress_title_notes=False, footnote_separator=None, strip_head_no=False,
                   show_body_siddham=True,
                   series_title=None, pagination=None, latin_font: Optional[str] = None,
                   annotations=None, gaiji_fonts=None, gaiji_lang: str = "zh-Hant",
                   fallback_fonts=None, siddham_fonts=None,
                   vertical: bool = False, notes_marker_font: Optional[str] = None):
        self.gaiji_db = gaiji_db if gaiji_db is not None else GaijiDb()
        self.theme = theme if theme is not None else Theme()
        self.ignore_xml_style = ignore_xml_style  # 忽略 <p style> 的 margin-left 脏数据
        self.ignore_xml_space = ignore_xml_space  # 忽略文本首尾多余空格（含全角）
        self.verse_caesura = verse_caesura        # 偈颂 caesura 分隔符（默认两个全角空格）
        self.strip_verse_quotes = verse_strip_quotes  # 去掉偈颂首尾「『 』」（同时忽略悬挂）
        self.grayscale = grayscale                # 全局黑白：忽略所有颜色（含 CSS 定义）
        self.page_border = page_border            # 每页四周加框
        self.bookmarks = bookmarks                # 每卷加书签（默认卷号）
        self.show_close_juan = show_close_juan    # 显示结束卷标题（fun="close"，默认隐藏）
        self.suppress_jhead_dup = suppress_jhead_dup  # 仅 jhead 去重（默认 true，head 保留书名）
        self.inline_brackets = inline_brackets    # 正文夹注（place=inline，原文）括号：halfwidth="()" / fullwidth="（）"
        self.note_inline_brackets = note_inline_brackets or inline_brackets  # 校注内联括号（缺省回退 inline_brackets）
        self.footnote_per_page = footnote_per_page  # 脚注每页重新编号（默认 true）
        self.footnote_separator = footnote_separator  # 脚注分隔线 {thicknessPt,lengthPercent,spaceTwips}
        self.show_notes = show_notes                # 关闭注释（默认 true 显示）
        self.show_body_siddham = show_body_siddham  # 正文悉昙字和读音（默认 true 显示；false 则正文不显示，脚注不受影响）
        self.suppress_title_notes = suppress_title_notes  # 压制卷名/品名校勘注码（默认 false 保留）
        self.strip_head_no = strip_head_no  # 去 head/jhead 行首 No. 令牌（默认 false 保留）
        self.series_title = series_title or {}         # 经藏名（title level="s"）首页左上角配置 {enabled,font,size}
        self.pagination = pagination or {}             # 智能分页 {enabled,duplex,juan,juan_first,mulu_level1,pb,tei}
        self.vertical = vertical                      # 纵排：每节 sectPr 写 textDirection tbRl（上→下、右→左）
        # 缺字字体链（P5）：{zh-Hant:[...], zh-Hans:[...]}，>0xFFFF 缺字取本机已装首个；
        # 懒解析（首个超大缺字才扫系统字体，平时零开销）；缺省 ["CBETA Supplement"]（旧行为）
        self.gaiji_fonts = gaiji_fonts or {}
        self.gaiji_lang = gaiji_lang or "zh-Hant"
        self._gaiji_font_resolved = None  # None=未解析；解析后为字体名字符串
        # 按字回退链（output.docx.fallbackFonts，{zh-Hant:[...],zh-Hans:[...]}；
        # 空走默认值；语言 key 缺失回繁体栏）
        self.fallback_fonts = fallback_fonts or {}
        # 悉昙字体（output.docx.siddhamFonts，单列；空走默认值 ["Ranjana","Siddam"]）
        self.siddham_fonts = list(siddham_fonts) if siddham_fonts else None
        self._fb_cmap = {}                # 按字回退：家族名 -> cmap|None（无文件），进程内复用
        self.notes_marker_font = ((notes_marker_font or "").strip()
                                or "Times New Roman")  # 注释注码字体（[N]/脚注编号上标，output.notes_marker_font 可配）
        # 难字注音（P6）：None 或 {"table", "scheme"}（CLI 已由 resolve_annotations 装载；渲染器内不做 IO）
        self._annotations = _ann_active(annotations)
        self._ann_seen = set()  # repeat first/page 已注词集合（_reset_state 起始终置零）
        self._suppress_note_ref = False             # 标题渲染时的临时压制开关
        self._in_note = False                     # 脚注/尾注内容渲染中（悉昙开关只作用正文）
        self._pending_mulu = None                 # 待附到下一 head/jhead 的 mulu 书签 {level,text}
        self.split = split                        # 按卷输出多个文档
        self._body_para_count = 0                 # 正文已渲染段落数（决定 juan 是否换页）
        cfg = resolve_page(page, page_presets)
        w_mm, h_mm = cfg["size"]
        self.page_w = int(w_mm * 56.6929)   # 1mm = 56.6929 twips
        self.page_h = int(h_mm * 56.6929)
        self.page_margins = {k: int(v * 56.6929) for k, v in cfg["margins"].items()}
        # 文档兜底字号：跟主题 base（body 单源；未知回 11，保持旧 pages 默认行为）
        self.doc_size = self.theme.base_pt(fallback=11)
        # 西文字体优先级：显式参数（font_sets 组合 latin）> 页面方案 latin_font > "Calibri"
        self.latin_font = latin_font or cfg["latin_font"]
        self.notes = notes  # 'footnote' | 'endnote' | 'inline'
        self._work = None
        self._fn_seq = 0
        self._fns: List[str] = []
        self._en_notes: List[str] = []
        self._tag_stack: List[str] = []
        self._div_stack: List[str] = []
        self._list_stack: List[int] = []
        self._in_pre = False

    @contextmanager
    def _no_ann(self):
        """标题/题署块内压制注音（P6：仅正文 Text 注音，head/byline/juan/jhead/title-m 不注）。"""
        save = self._annotations
        self._annotations = None
        try:
            yield
        finally:
            self._annotations = save

    def _list_numid(self, a) -> int:
        style = self.theme.tags.get("list", {}).get("list-style-type")
        if style is None:
            style = "none" if (a.get("rend") or "").find("no-marker") >= 0 else "disc"
        return {"none": 2, "disc": 1, "bullet": 1, "circle": 1, "decimal": 3}.get(style, 2)

    def _tag_base_pt(self, tags) -> float:
        """段落级标签的 pt 字号，作为 em 换算基准（默认主题 base，旧 12.0）。
        只认绝对 pt（em 由调用方按上下文解，这里保持父级语义，避免复利）。"""
        for t in reversed(tags):
            fs = (self.theme.tags.get(t) or {}).get("font-size")
            m = re.match(r"([\d.]+)pt", fs or "")
            if m:
                return float(m.group(1))
        return self.theme.base_pt()

    def _resolve_tag_pt(self, tags) -> float:
        """标签栈由外向内解算 pt（绝对替换，em 按已解基准乘；基准主题 base）。
        注音等相对尺寸的锚：脚注 0.75em→9.0，不回落 12。"""
        from pycbeta.theme import _abs_pt
        cur = self.theme.base_pt()
        for t in (tags or ()):
            pt = _abs_pt((self.theme.tags.get(t) or {}).get("font-size"), cur)
            if pt is not None:
                cur = pt
        return cur

    def _run_rpr(self, tags, props) -> str:
        """run 属性（含 <w:rPr> 包裹）：_run 与 _run_annotated 共用，保证注音 run 样式一致。"""
        tags = tags or (self._current_tag(),)
        rpr = self.theme.docx_run(*tags, base_pt=self._tag_base_pt(tags))
        if props.get("bold"):
            rpr += "<w:b/>"
        if props.get("sz"):
            rpr += f'<w:sz w:val="{props["sz"]}"/><w:szCs w:val="{props["sz"]}"/>'
        if props.get("vert"):
            rpr += f'<w:vertAlign w:val="{props["vert"]}"/>'
        fonts = props.get("fonts")
        if fonts:
            # 显式字体优先：去掉主题带来的 rFonts 再追加（同一 rPr 内重复 w:rFonts 时 Word 取首个，不去会失效）
            rpr = re.sub(r"<w:rFonts[^>]*/>", "", rpr)
            rpr += f'<w:rFonts w:ascii="{fonts}" w:eastAsia="{fonts}" w:hint="eastAsia"/>'
        if rpr:
            rpr = f"<w:rPr>{rpr}</w:rPr>"
        return rpr

    def _run(self, text: str, *tags: str, **props) -> str:
        tags = tags or (self._current_tag(),)
        rpr = self._run_rpr(tags, props)
        if self._in_pre:
            # 换行拆成多个 <w:t> run，中间用 <w:r><w:br/></w:r>（不能裸 <w:br/>，否则 WPS 忽略）
            runs = [self._fb_emit(p, rpr) for p in text.split("\n")]
            return "<w:r><w:br/></w:r>".join(runs)
        return self._fb_emit(text.replace("\n", ""), rpr)

    def _fb_emit(self, text: str, rpr: str) -> str:
        """单文本 run 发射（含按字回退）：主字体缺字形的字拆出，用回退字体另起 run。

        无缺字/无法验证（字体文件缺失）时输出与旧路径字节一致，保证零回归。
        """
        m = _EASTASIA_RE.search(rpr)
        chunks = self._split_covered(text, m.group(1)) if m else None
        if not chunks:
            return (f"<w:r>{rpr}<w:t xml:space=\"preserve\">"
                    f"{_x(text)}</w:t></w:r>")
        out = []
        for chunk, fb in chunks:
            rr = rpr if not fb else re.sub(
                f'w:eastAsia="[^"]+"', f'w:eastAsia="{fb}"', rpr, count=1)
            out.append(f"<w:r>{rr}<w:t xml:space=\"preserve\">"
                       f"{_x(chunk)}</w:t></w:r>")
        return "".join(out)

    def _fallback_cmap(self, family):
        """主字体文件 cmap（无文件返回 None=无法验证，保持原样）；随 renderer 缓存。"""
        if family in self._fb_cmap:
            return self._fb_cmap[family]
        cmap = None
        try:
            from .fonts import locator as _loc, font_cmap as _fc
            path = _loc().path(family)
            if path:
                cmap = _fc(path)
        except Exception:  # noqa: BLE001 —— 查不到不断渲染
            cmap = None
        self._fb_cmap[family] = cmap
        return cmap

    def _fallback_chain(self):
        """本语言回退链（配置优先，缺省默认值；key 缺失回繁体栏）。"""
        chain = (self.fallback_fonts or {}).get(self.gaiji_lang)
        if not chain:
            chain = (self.fallback_fonts or {}).get("zh-Hant")
        return chain or DEFAULT_FALLBACK_FONTS.get(
            self.gaiji_lang) or DEFAULT_FALLBACK_FONTS["zh-Hant"]

    def _fallback_for(self, family, ch):
        """某字在主字体缺字形时的回退字体（本语言链内首个覆盖者）；
        无则 None（真 tofu）。"""
        for fb in self._fallback_chain():
            if fb == family:
                continue
            cmap = self._fallback_cmap(fb)
            if cmap is not None and ord(ch) in cmap:
                return fb
        return None

    def _split_covered(self, text, family):
        """文本按主字体覆盖切分 → None（全覆盖/无法验证）或 [(chunk, fb|None)]。"""
        cmap = self._fallback_cmap(family)
        if cmap is None:
            return None
        chunks, buf, cur = [], [], None
        started = False
        for ch in text:
            fb = None if ord(ch) in cmap else self._fallback_for(family, ch)
            if not started:
                cur, started = fb, True
            if fb != cur:
                chunks.append(("".join(buf), cur))
                buf, cur = [], fb
            buf.append(ch)
        if buf:
            chunks.append(("".join(buf), cur))
        if len(chunks) == 1 and chunks[0][1] is None:
            return None
        return chunks

    def _rt_rpr(self, tags, props, hps: int, rt_font: str) -> str:
        """注音 rt run 属性：字号=注音字号（hps 半磅），字体=rt_font 或正文字体；
        先去掉主题带来的段落字号/字体再追加，避免 w:sz/w:rFonts 重复。"""
        rpr = self.theme.docx_run(*tags, base_pt=self._tag_base_pt(tags))
        rpr = re.sub(r"<w:sz[^>]*/>", "", rpr)
        rpr = re.sub(r"<w:szCs[^>]*/>", "", rpr)
        rpr = re.sub(r"<w:rFonts[^>]*/>", "", rpr)
        if props.get("bold"):
            rpr += "<w:b/>"
        if props.get("vert"):
            rpr += f"<w:vertAlign w:val=\"{props['vert']}\"/>"
        rpr += f"<w:sz w:val=\"{hps}\"/><w:szCs w:val=\"{hps}\"/>"
        font = (rt_font or props.get("fonts") or "").replace('"', "")
        if font:
            rpr += f"<w:rFonts w:ascii=\"{font}\" w:eastAsia=\"{font}\" w:hint=\"eastAsia\"/>"
        if rpr:
            rpr = f"<w:rPr>{rpr}</w:rPr>"
        return rpr

    def _plain_run(self, seg: str, rpr: str) -> str:
        """普通文本 run（注音未匹配片段共用；含按字回退）。"""
        return self._fb_emit(seg.replace(chr(10), ""), rpr)

    def _eq_field(self, base: str, reading: str, hps: int, up: int, font: str) -> str:
        """单个 EQ 拼音指南域（WPS 原生模板字节级复刻）：
        ``{ EQ \\* jc0 \\* "Font:F" \\* hpsN \\o \\ad(\\s \\up U(RD),BASE) }``。
        begin 裸 run（WPS 原生即无 rPr），instr/end 带 rFonts+lang（WPS 原生同款）。"""
        from xml.sax.saxutils import escape as _esc_q
        font_s = _esc_q(font.replace('"', ""), {'"': "&quot;"})
        rd_s = _esc_q(reading, {'"': "&quot;"})
        base_s = _esc_q(base, {'"': "&quot;"})
        fld_rpr = ('<w:rPr><w:rFonts w:hint="eastAsia"/>'
                   '<w:lang w:val="en-US" w:eastAsia="zh-CN"/></w:rPr>')
        code = (f" EQ \\* jc0 \\* &quot;Font:{font_s}&quot; \\* hps{hps} "
                f"\\o \\ad(\\s \\up {up}({rd_s}),{base_s})")
        return (f"<w:r><w:fldChar w:fldCharType=\"begin\"/></w:r>"
                f"<w:r>{fld_rpr}<w:instrText xml:space=\"preserve\">{code}</w:instrText></w:r>"
                f"<w:r>{fld_rpr}<w:fldChar w:fldCharType=\"end\"/></w:r>")

    def _run_annotated(self, text: str, *tags: str, **props) -> str:
        """难字注音 run：匹配片段注音，未匹配走 _run。
        style=ruby（上方）：包 <w:ruby>（rt 拼音/注音 + rubyBase 原文，仅 Word 可见，
        LibreOffice/WPS 整段丢弃）；=inline（右侧）：纯文本括注 X〔注音〕（所有阅读器可见）。
        <pre> 内（_in_pre）不支持 ruby（换行会撕裂注音结构），回退 _run 全文。"""
        if self._in_pre:
            return self._run(text, *tags, **props)
        tags = tags or (self._current_tag(),)
        ann = self._annotations
        segs = _split_ann(text, ann["table"], ann["scheme"],
                          ann.get("rare_zones", frozenset()),
                          ann.get("rare_cmap"),
                          _track_seen(ann, self._ann_seen),
                          ann.get("full_text", False))
        if len(segs) == 1 and segs[0][1] is None:
            return self._run(text, *tags, **props)
        rpr = self._run_rpr(tags, props)
        if ann.get("style", "inline") == "inline":
            # 右侧行内：单 run 纯文本括注（verify 侧 normalize 剥除读音括注，比对无影响）
            l, r = ann.get("brackets", ["〔", "〕"])
            out = []
            for seg, reading in segs:
                if not seg:
                    continue
                seg = seg.replace(chr(10), "")
                if reading is None:
                    out.append(self._fb_emit(seg, rpr))
                else:
                    out.append(self._fb_emit(f"{seg}{l}{reading}{r}", rpr))
            return "".join(out)
        if ann.get("style", "inline") == "field":
            # 上方 EQ 域（WPS/Word 可见）：逐字拼音指南域；读音按音节分配，整词兜底
            base_pt = self._resolve_tag_pt(tags)
            rt_pt = _parse_rt_size(ann.get("rt_size"), base_pt) or base_pt * 0.5
            hps = max(1, int(round(rt_pt * 2)))
            # 抬升量 up：默认 100% 正文字号（一个整字高，构造上不与正文相交；
            # WPS 原生例为 60%，但新細明體等字框高时 60% 会相交，可配 ruby_up 微调）
            up = _parse_rt_size(ann.get("ruby_up", "100%"), base_pt) or base_pt
            up = max(1, int(round(up)))
            font = (ann.get("rt_font") or "").strip() if isinstance(ann.get("rt_font"), str) else ""
            font = font or "宋体"  # WPS 拼音指南默认字体
            out = []
            for seg, reading in segs:
                if not seg:
                    continue
                if reading is None:
                    out.append(self._plain_run(seg, rpr))
                else:
                    out.append("".join(
                        self._eq_field(b, r, hps, up, font)
                        for b, r in _split_eq(seg, reading)))
            return "".join(out)
        # 上方 ruby：rubyPr 补完（hps/hpsRaise/hpsBaseText/lid，Word 拼音指南完整结构；
        # 旧版仅 rubyAlign 会被严格 Reader 忽略；WPS 另见 field 模式）
        base_pt = self._resolve_tag_pt(tags)
        rt_pt = _parse_rt_size(ann.get("rt_size"), base_pt) or base_pt * 0.5
        rt_font = (ann.get("rt_font") or "").strip() if isinstance(ann.get("rt_font"), str) else ""
        hps = max(1, int(round(rt_pt * 2)))
        hps_base = max(1, int(round(base_pt * 2)))
        ruby_pr = (f"<w:rubyPr><w:rubyAlign w:val=\"center\"/><w:hps w:val=\"{hps}\"/>"
                   f"<w:hpsRaise w:val=\"{hps_base}\"/><w:hpsBaseText w:val=\"{hps_base}\"/>"
                   f"<w:lid w:val=\"zh-CN\"/></w:rubyPr>")
        rt_rpr = self._rt_rpr(tags, props, hps, rt_font)
        out = []
        for seg, reading in segs:
            if not seg:
                continue
            if reading is None:
                out.append(self._fb_emit(seg.replace(chr(10), ""), rpr))
            else:
                out.append(
                    f"<w:ruby>{ruby_pr}"
                    f"<w:rt><w:r>{rt_rpr}<w:t xml:space=\"preserve\">"
                    f"{_x(reading)}</w:t></w:r></w:rt>"
                    f"<w:rubyBase>{self._fb_emit(seg, rpr)}</w:rubyBase></w:ruby>")
        return "".join(out)

    def _marker_rpr(self) -> str:
        """注码 run 属性：字号=正文字号×note-ref 比例（CSS 默认 0.75em，12pt 正文下=9pt）
        + note-ref 颜色 + 上标。不随所在段落放大（序标题注码不再跟标题字号）；
        随 font_scale 等比放大（主题 scale_font_sizes 已放大 pt 值与 em 比例，此处直接用）。
        注：纵排注码保持横躺（WPS/LO 忽略 w:fitText，全角化又拉长版面，见 TODO 实锤链）。"""
        base = self._tag_base_pt(("p",))  # 锚定正文，不取当前段落
        fs = (self.theme.tags.get("note-ref") or {}).get("font-size") or ""
        m = re.match(r"([\d.]+)pt", fs)
        if m:
            sz = int(float(m.group(1)) * 2)
        else:
            m = re.match(r"([\d.]+)em", fs)
            if m:
                sz = int(float(m.group(1)) * base * 2)
            else:
                sz = int(base * 2)
        color = _hex6((self.theme.tags.get("note-ref") or {}).get("color"))
        rpr = f'<w:color w:val="{color}"/>' if color else ""
        font = _x(self.notes_marker_font)
        return (f"<w:rPr><w:sz w:val=\"{sz}\"/><w:szCs w:val=\"{sz}\"/>{rpr}"
                '<w:vertAlign w:val="superscript"/>'
                f'<w:rFonts w:ascii="{font}"/></w:rPr>')

    def _fn_ref(self, fid: int) -> str:
        return f'<w:r>{self._marker_rpr()}<w:footnoteReference w:id="{fid}"/></w:r>'

    def _fn_entry(self, fid: int, content: str) -> str:
        # 脚注段落用命名样式 footnote + 内联 spacing 兜底（WPS 可能忽略样式级脚注间距）
        ppr = f'<w:pStyle w:val="footnote"/>' + self.theme.docx_para("footnote")
        ref = ('<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:footnoteRef/></w:r>'
               '<w:r><w:t xml:space="preserve"> </w:t></w:r>')
        return (
            f'<w:footnote w:id="{fid}"><w:p><w:pPr>{ppr}</w:pPr>{ref}{content}</w:p></w:footnote>'
        )

    def _series_size_pt(self, st) -> int:
        """经藏名字号（半磅）：主题 p.series-title font-size 优先（pt 绝对值；
        em 按正文字号折算）；无规则时回退 config 旧 size 键，再回退 9pt。"""
        fs = (st.get("font-size") or "").strip()
        m = re.match(r"([\d.]+)pt", fs)
        if m:
            return int(float(m.group(1)) * 2)
        m = re.match(r"([\d.]+)em", fs)
        if m:
            return int(float(m.group(1)) * self._tag_base_pt(("p",)) * 2)
        try:
            return int(float(self.series_title.get("size", 9)) * 2)
        except (TypeError, ValueError):
            return 18

    def _para(self, runs: str, *tags: str, indent: float = 0, hang=None,
              page_break: bool = False, count: bool = True, no_first_line: bool = False) -> str:
        tags = tuple(t for t in tags if t)
        # div 祖先上下文并入：多数调用点只传本标签（如 juan/table/pin），在此统一补上，
        # 否则 div 属性（如 div-xu 边距）到不了命名样式段落；已含 div 的调用去重后合并幂等
        # （段落标签仍在末尾）。模板段落（注释节/书名/经藏名）在 body 渲染完成后调用，
        # 此时 div 栈为空，不受影响；脚注内容另由 _footnote_content 清栈隔离。
        tags = tuple(dict.fromkeys(tuple(self._div_stack) + tags))
        para = tags[-1] if tags else "p"
        # div-note 内 p/form 挂 div-note 样式（预览标【字义】；def 结尾标【释义】不动）：
        # 样式在 styles.xml 内联拷贝 p 布局+粗体，视觉与原来（p 样式+粗体 run）一致。
        if "div-note" in tags and para in ("p", "form"):
            para = "div-note"
        if count:
            self._body_para_count += 1
        pb = "<w:pageBreakBefore/>" if page_break else ""
        # div 祖先的段落属性（margin 等）内联追加：命名样式只含本标签属性，
        # 不含 div 上下文；内联值覆盖样式值（与 theme.docx_para 的 div 优先语义一致）。
        # 目前仅 div-xu 携带段落属性，其它 div-* 经此路径输出为空串，无影响。
        div_tags = [t for t in tags if t.startswith("div-")]
        div_extra = self.theme.docx_para(*div_tags) if div_tags else ""
        # 偈颂首句悬挂（lg 的 margin-left + text-indent:-N em 特征）：内联 w:ind 覆盖命名样式
        if hang:
            font_pt = self._tag_base_pt(tags)
            left = int(hang[0] * font_pt * 20)
            fl = int(hang[1] * font_pt * 20)
            ind = f'<w:ind w:left="{left}" w:firstLine="{fl}"/>'
            if para in _STYLED_PARAS:
                p = f"<w:p><w:pPr><w:pStyle w:val=\"{para}\"/>{pb}{ind}{div_extra}</w:pPr>{runs}</w:p>"
                return self._with_bookmark(p)
        # 核心标签走命名段落样式（styles.xml）；footnote 额外内联 spacing 兜底
        if para in _STYLED_PARAS and indent == 0:
            ppr = f'<w:pStyle w:val="{para}"/>'
            if page_break:
                ppr += pb
            if para == "footnote":
                ppr += self.theme.docx_para("footnote")
            ppr += div_extra
            p = f"<w:p><w:pPr>{ppr}</w:pPr>{runs}</w:p>"
            return self._with_bookmark(p)
        ppr = self.theme.docx_para(*tags, indent_em=indent, no_first_line=no_first_line)
        # 内联路径也挂命名样式（直接属性照旧覆盖样式，视觉不变；
        # Word 样式窗格/预览标签可识别，如 def>p 的“释义”）
        sty = f'<w:pStyle w:val="{para}"/>' if para in _STYLED_PARAS else ""
        ppr = f"<w:pPr>{sty}{ppr}</w:pPr>" if (sty or ppr) else ""
        p = f"<w:p>{ppr}{runs}</w:p>"
        return self._with_bookmark(p)

    def _with_bookmark(self, para_xml: str) -> str:
        """目录书签：milestone（卷边界）之后的下一个段落用「卷N」书签包裹。书签置于段内避免 pageBreakBefore 产生空白书签页。"""
        if not self.bookmarks or self._pending_juan is None:
            return para_xml
        name = f"卷{self._pending_juan}"
        self._pending_juan = None
        bid = self._bm_id
        self._bm_id += 1
        start = f'<w:bookmarkStart w:id="{bid}" w:name="{name}"/>'
        end = f'<w:bookmarkEnd w:id="{bid}"/>'
        # 置于段内：</w:pPr> 之后、</w:p> 之前，避免 pageBreakBefore 导致书签在上一页空白
        if "</w:pPr>" in para_xml:
            para_xml = para_xml.replace("</w:pPr>", f"</w:pPr>{start}", 1)
            para_xml = para_xml.replace("</w:p>", f"{end}</w:p>", 1)
        elif "<w:p>" in para_xml:
            para_xml = para_xml.replace("<w:p>", f"<w:p>{start}", 1)
            para_xml = para_xml.replace("</w:p>", f"{end}</w:p>", 1)
        else:
            para_xml = f"{start}{para_xml}{end}"
        return para_xml

    def render_work(self, work: Work, out_dir: str, filename: str = "") -> str:
        """默认返回单个文档路径；split=True 时返回按卷切分的路径列表。
        pagination.enabled 时按分页单元渲染，每个单元一个分节
        （duplex=true → oddPage 单数页开始，Word 自动补空白偶页）。"""
        os.makedirs(out_dir, exist_ok=True)
        if self.split:
            return self._render_split(work, out_dir, filename)
        self._reset_state(work)
        if self.pagination.get("enabled"):
            sections = []
            last_juan = object()
            for juan_no, ops in split_sections(work.body, self.pagination):
                if juan_no != last_juan:
                    self._pending_juan = str(juan_no) if juan_no else None
                    last_juan = juan_no
                # repeat=page：每分页单元已注清零，本单元词首现重注
                if _page_repeat(self._annotations):
                    self._ann_seen = set()
                sections.append(self._render_ops(ops))
            body = sections
        else:
            body = self._render_body(work.body)
        title = work.metadata.get("title") or work.id
        author = work.metadata.get("author") or ""
        doc = self._build_docx(title, author, body)
        if not filename:
            filename = f"{work.id}.docx"
        fn = os.path.join(out_dir, filename)
        with open(fn, "wb") as f:
            f.write(doc)
        return fn

    def _reset_state(self, work: Work) -> None:
        self._work = work
        self._ann_seen = set()
        self._fn_seq = 0
        self._fns = []
        self._en_notes = []
        self._tag_stack = []
        self._div_stack = []
        self._body_para_count = 0
        self._pending_juan = None     # 待加书签的卷号（milestone 之后的下一个段落）
        self._bm_id = 0               # 书签递增 id

    def _render_split(self, work: Work, out_dir: str, filename: str = "") -> List[str]:
        """按卷输出：每卷一个独立文档（书名页 + 本卷正文 + teiHeader 尾页）。"""
        title = work.metadata.get("title") or work.id
        author = work.metadata.get("author") or ""
        files = []
        for juan_no, ops in split_juans(work.body):
            self._reset_state(work)
            body = self._render_ops(ops)
            doc = self._build_docx(title, author, body)
            if filename:
                stem = os.path.splitext(filename)[0]
                fn = f"{stem}_卷{juan_no}.docx"
            else:
                fn = f"{work.id}_卷{juan_no}.docx"
            path = os.path.join(out_dir, fn)
            with open(path, "wb") as f:
                f.write(doc)
            files.append(path)
        return files

    def _render_ops(self, ops) -> str:
        """按卷切分后的扁平 ops 渲染（div open/close 事件转 _div_stack）。"""
        out = []
        for kind, n in ops:
            if kind == "open":
                t = n.attrs.get("type")
                if t:
                    self._div_stack.append(f"div-{t}")
            elif kind == "close":
                t = n.attrs.get("type")
                if t and self._div_stack:
                    self._div_stack.pop()
            else:
                out.append(self._render_node(n))
        return "".join(out)

    def _resolve_gaiji_raw(self, code: str, raw: str) -> str:
        # 优先级：RJ 悉昙用 charDecl rjchar（常规汉字；官方行为，配 Ranjana 系字体显示，
        # 不用 PUA 私用字——无字体覆盖，必 tofu）→ gaiji_db（CBETA 全局缺字表，与官方 html 一致）
        # → charDecl（本经 charDecl，兜底）→ raw
        if code.startswith("RJ"):
            chard0 = (self._work.metadata.get("charDecl") or {}) if self._work else {}
            rj = (chard0.get(code) or {}).get("rjchar")
            if rj:
                return rj
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

    def _gaiji_roman(self, code: str) -> str:
        """悉昙读音（charDecl Romanized form，Unicode 式优先）。
        官方 docx 正文/脚注均附读音（如 歾(raṃ)）；html/md/txt 官方无，故仅 docx 用。
        无记录返回 ""。"""
        chard = (self._work.metadata.get("charDecl") or {}) if self._work else {}
        rec = chard.get(code) or {}
        return (rec.get("roman") or rec.get("roman_cbeta") or "").strip()

    def _ranjana_font_for(self, ch):
        """RJ 悉昙字形：首个已装且覆盖该字者（配置 output.docx.siddhamFonts，
        缺省 ["Ranjana","Siddam"]）；无则 None。

        有则 run 指定该字体（官方 docx 同款 eastAsia="Ranjana"）；无则回退主题字体——
        rjchar 本身是常规汉字，依然可读，只是非悉昙体（用户实证：没装显示歾，装了显示种子字）。
        """
        if not ch:
            return None
        for fam in (self.siddham_fonts if self.siddham_fonts is not None
                    else DEFAULT_SIDDHAM_FONTS):
            cmap = self._fallback_cmap(fam)
            if cmap is not None and ord(ch[0]) in cmap:
                return fam
        return None

    def _gaiji_font(self) -> str:
        """超大缺字（>0xFFFF）字体：按 gaiji_lang 取链，首个本机已装者；
        全缺/无配置回退首项（缺省 CBETA Supplement，旧行为）。结果缓存，零缺字时零开销。"""
        if self._gaiji_font_resolved is None:
            chain = (self.gaiji_fonts or {}).get(self.gaiji_lang) or ["CBETA Supplement"]
            pick = chain[0] if chain else "CBETA Supplement"
            try:
                from .fonts import locator as _loc
                loc = _loc()
                for name in chain:
                    if name and loc.path(name):
                        pick = name
                        break
            except Exception:
                pass
            self._gaiji_font_resolved = pick
        return self._gaiji_font_resolved

    def _render_body(self, body) -> str:
        return "".join(self._render_node(n) for n in body)

    def _current_tag(self) -> tuple:
        para = self._tag_stack[-1] if self._tag_stack else "p"
        return tuple(self._div_stack) + (para,)

    def _render_node(self, n) -> str:
        if isinstance(n, Text):
            text = n.text.strip(" \t　") if self.ignore_xml_space else n.text
            if self._annotations is not None:
                return self._run_annotated(text, *self._current_tag())
            return self._run(text, *self._current_tag())
        if isinstance(n, Lb) or isinstance(n, Pb):
            return ""
        if isinstance(n, Gaiji):
            roman = self._gaiji_roman(n.code)
            if roman and not getattr(self, "_in_note", False) \
                    and not self.show_body_siddham:
                return ""  # 正文隐藏悉昙字（含读音）；脚注/尾注不受影响
            char = self._resolve_gaiji(n.code, n.char or n.code)
            fonts = None
            if n.code.startswith("RJ"):
                # 悉昙文：已装且覆盖则指定 Ranjana 系字体（官方同款），否则主题字体直显 rjchar
                fonts = self._ranjana_font_for(char)
            if fonts is None and char and ord(char[0]) > 0xFFFF:
                fonts = self._gaiji_font()
            kw = {"fonts": fonts} if fonts else {}
            if self._annotations is not None:
                # 读音走纯文本通道（拉丁不过注音），避免进 ruby
                out = self._run_annotated(char, *self._current_tag(), **kw)
                if roman:
                    out += self._run(f"({roman})", *self._current_tag(),
                                     fonts=self.latin_font)
                return out
            if roman:
                return (self._run(char, *self._current_tag(), **kw)
                        + self._run(f"({roman})", *self._current_tag(),
                                    fonts=self.latin_font))
            return self._run(char, *self._current_tag(), **kw)
        if isinstance(n, NoteRef):
            return self._render_noteref(n)
        if isinstance(n, App):
            return self._render_app(n)
        if isinstance(n, Note):
            return self._render_inline_note(n)
        if isinstance(n, E):
            return self._render_e(n)
        return ""

    def _rend_tag(self, a) -> Optional[str]:
        for r in (a.get("rend") or "").split():
            if r in _REND_TAGS:
                return r
        return None

    def _render_children(self, el, *tags: str) -> str:
        tags = tuple(t for t in tags if t)
        if tags:
            self._tag_stack.extend(tags)
        out = "".join(self._render_node(c) for c in el.children)
        if tags:
            del self._tag_stack[-len(tags):]
        return out

    def _render_inline_mode(self, content: str) -> str:
        """注释方式=inline：校注用主题 note-inline 样式（括号走 note_inline_brackets）。"""
        tags = self._current_tag() + ("note-inline",)
        lb, rb = bracket_pair(getattr(self, "note_inline_brackets", "fullwidth"))
        return (self._run(lb, *tags) + content + self._run(rb, *tags))

    def _footnote_content(self, note) -> str:
        """脚注内容在正文 div 上下文之外渲染（不继承正文 div 的粗体/颜色）。"""
        prev = self._div_stack
        self._div_stack = []
        prev_note = getattr(self, "_in_note", False)
        self._in_note = True
        try:
            return self._render_children(note, "footnote")
        finally:
            self._div_stack = prev
            self._in_note = prev_note

    def _render_noteref(self, ref: NoteRef) -> str:
        if not self.show_notes or self._suppress_note_ref:
            return ""
        notes = ref.notes
        if not notes:
            return ""
        note = self._pick_note(notes)
        content = self._footnote_content(note)
        if self.notes == "inline":
            return self._render_inline_mode(content)
        self._fn_seq += 1
        seq = self._fn_seq
        if self.notes == "endnote":
            self._en_notes.append((seq, content))
            return f'<w:r>{self._marker_rpr()}<w:t>[{seq}]</w:t></w:r>'
        self._fns.append(self._fn_entry(seq, content))
        return self._fn_ref(seq)

    def _render_app(self, app: App) -> str:
        if not self.show_notes or self._suppress_note_ref:
            return ""
        if app.attrs.get("corresp"):
            n = app.attrs["corresp"].lstrip("#")
            notes = (self._work.notes_by_n or {}).get(n) if self._work else None
            if notes:
                note = self._pick_note(notes)
                content = self._footnote_content(note)
                if self.notes == "inline":
                    return self._render_inline_mode(content)
                self._fn_seq += 1
                seq = self._fn_seq
                if self.notes == "endnote":
                    self._en_notes.append((seq, content))
                    return f'<w:r>{self._marker_rpr()}<w:t>[{seq}]</w:t></w:r>'
                self._fns.append(self._fn_entry(seq, content))
                return self._fn_ref(seq)
        return ""

    def _render_inline_note(self, note: Note) -> str:
        # 正文夹注（<note place="inline">）属原文，不受「注释总开关」控制
        if note.place in ("inline", "inline2", "interlinear"):
            # 夹注样式跟随主题 doube-line-note / interlinear-note（对齐 HTML 的紫色夹注）
            nt = "interlinear-note" if note.place == "interlinear" else "doube-line-note"
            tags = self._current_tag() + (nt,)
            lb, rb = bracket_pair(getattr(self, "inline_brackets", "fullwidth"))
            return (self._run(lb, *tags) + self._render_children(note, nt)
                    + self._run(rb, *tags))
        return ""

    def _pick_note(self, notes):
        for t in ("mod", "orig", "add", "equivalent", "rest"):
            for n in notes:
                if n.ntype == t:
                    return n
        return notes[0]

    def _render_e(self, e: E) -> str:
        if e.tag == "app":
            # 正文内联校勘（P5a/P5b）：base 读法只在 <lem>，只渲染 lem；rdg 是异读不进正文
            lem = next((c for c in e.children
                        if isinstance(c, E) and c.tag == "lem"), None)
            return self._render_children(lem) if lem is not None else ""
        tag = e.tag
        a = e.attrs
        if tag == "milestone" and a.get("unit") == "juan":
            self._pending_juan = a.get("n") or "?"
            return ""
        if tag == "p":
            ptype = a.get("cb:type") or a.get("type")
            if ptype == "pre":
                prev = self._in_pre
                self._in_pre = True
                runs = self._render_children(e, "p")
                self._in_pre = prev
                # 预排不缩进（CSS pre/text-indent:0；只掐首行，段间距/行距跟 p 不变）
                return self._para(runs, "p", "pre", no_first_line=True)
            # p/@type 映射到主题标签（dharani 等），对齐 HTML 的 class="dharani"
            ptag = ptype if ptype in self.theme.tags else None
            style = a.get("style") or ""
            indent = 0
            if not self.ignore_xml_style:
                m = re.search(r"margin-left:\s*([\d.]+)em", style)
                if m:
                    indent = float(m.group(1))
            tags = self._current_tag() + ((ptag,) if ptag else ())
            return self._para(self._render_children(e, "p", ptag, self._rend_tag(a)),
                              *tags, indent=indent)
        if tag == "pre":
            prev = self._in_pre
            self._in_pre = True
            runs = self._render_children(e, "p", "pre")
            self._in_pre = prev
            return self._para(runs, "p", "pre", no_first_line=True)
        if tag == "head":
            # 仅 jhead 去重，head 保留书名；若有 pending mulu（紧随的 cb:mulu），则以 mulu 的 level/text 作隐形书签（段内避免空白页）
            nodes = e.children
            if self.strip_head_no:
                nodes, _ = strip_head_no(nodes)
            is_pin = bool(re.search(r"品第[一二三四五六七八九十百千]", self._render_text(e)))
            para_tag = "pin" if is_pin else "head"
            with self._no_ann():
                runs = self._render_tagged_clean(nodes, para_tag, self._rend_tag(a))
            p = self._para(runs, para_tag)
            if self.bookmarks and self._pending_mulu is not None:
                lvl = self._pending_mulu["level"]
                name = self._pending_mulu["text"]
                bid = self._bm_id; self._bm_id += 1
                start = f'<w:bookmarkStart w:id="{bid}" w:name="{name}"/>'
                end = f'<w:bookmarkEnd w:id="{bid}"/>'
                if "</w:pPr>" in p:
                    p = p.replace("</w:pPr>", f"</w:pPr>{start}", 1)
                    p = p.replace("</w:p>", f"{end}</w:p>", 1)
                elif "<w:p>" in p:
                    p = p.replace("<w:p>", f"<w:p>{start}", 1)
                    p = p.replace("</w:p>", f"{end}</w:p>", 1)
                else:
                    p = f"{start}{p}{end}"
                # 大纲级别按 mulu level
                outline = f'<w:outlineLvl w:val="{lvl-1}"/>'
                if "<w:pPr>" in p:
                    p = p.replace("<w:pPr>", f"<w:pPr>{outline}", 1)
                else:
                    p = p.replace("<w:p>", f"<w:p><w:pPr>{outline}</w:pPr>", 1)
                self._pending_mulu = None
            return p
        if tag == "byline":
            # 作者/译者独立样式：byline cb:type="author" -> author，cb:type="Translator" -> translator
            bt = a.get("cb:type") or ""
            btag = "translator" if bt == "Translator" else ("author" if bt == "author" else "byline")
            with self._no_ann():
                runs = self._render_children(e, btag, self._rend_tag(a))
            return self._para(runs, btag)
        if tag == "juan":
            if a.get("fun") == "close":
                self._pending_juan = None   # 结束卷标题不加书签
                if self.show_close_juan:
                    # 直接渲染 jhead（避免 _render_juan_title(juan) 包裹 jhead 产生嵌套空段+空白书签）
                    out = []
                    for c in e.children:
                        if isinstance(c, E) and c.tag == "jhead":
                            out.append(self._render_juan_title(c, page_break=False))
                    return "".join(out) if out else ""
                return ""                   # 默认不显示结束卷标题
            # open 卷：容器，各子元素独立渲染（卷名/译者/品名分行，整体非正文，压制注音）
            with self._no_ann():
                return "".join(self._render_node(c) for c in e.children)
        if tag == "jhead":
            if a.get("type") == "pin":
                nodes = self._children_no_dup_title(e) if self.suppress_jhead_dup else e.children
                if self.strip_head_no:
                    nodes, _ = strip_head_no(nodes)
                with self._no_ann():
                    runs = self._render_tagged_clean(nodes, "pin", self._rend_tag(a))
                p = self._para(runs, "pin")
            else:
                p = self._render_juan_title(e)
            if p and self.bookmarks and self._pending_mulu is not None:
                lvl = self._pending_mulu["level"]
                name = self._pending_mulu["text"]
                bid = self._bm_id; self._bm_id += 1
                start = f'<w:bookmarkStart w:id="{bid}" w:name="{name}"/>'
                end = f'<w:bookmarkEnd w:id="{bid}"/>'
                if "</w:pPr>" in p:
                    p = p.replace("</w:pPr>", f"</w:pPr>{start}", 1)
                    p = p.replace("</w:p>", f"{end}</w:p>", 1)
                elif "<w:p>" in p:
                    p = p.replace("<w:p>", f"<w:p>{start}", 1)
                    p = p.replace("</w:p>", f"{end}</w:p>", 1)
                else:
                    p = f"{start}{p}{end}"
                outline = f'<w:outlineLvl w:val="{lvl-1}"/>'
                if "<w:pPr>" in p:
                    p = p.replace("<w:pPr>", f"<w:pPr>{outline}", 1)
                else:
                    p = p.replace("<w:p>", f"<w:p><w:pPr>{outline}</w:pPr>", 1)
                self._pending_mulu = None
            return p
        if tag == "mulu":
            txt = self._render_text(e).strip()
            if not txt:
                return ""   # 空目录标记（如 <cb:mulu n="1" type="卷">）不输出
            try:
                lvl = int(a.get("level") or "1")
            except ValueError:
                lvl = 1
            lvl = max(1, min(9, lvl))
            # 隐形书签：不落可见段，仅暂存待附到紧随的 head/jhead（跨 lb/pb 保留）
            self._pending_mulu = {"level": lvl, "text": txt}
            return ""
        if tag == "title":
            if a.get("level") == "m":
                # 书名（title m）：多卷（jhead 含"卷N"≠书名）打印书名一次；
                # 单卷（jhead 全文==书名）由 suppress_jhead_dup 将相同 jhead 压成空段，
                # mulu 书签保留其上，恰只显示一个书名；count=False 避免首卷 jhead 误加分页
                with self._no_ann():
                    runs = self._render_tagged_clean(e.children, "title")
                return self._para(runs, "title", count=False)
            return self._render_children(e)
        if tag == "docNumber":
            return ""  # 恒不显
        if tag == "tt":
            return self._render_tt(e)
        if tag == "t":
            return self._render_children(e)
        if tag == "lg":
            return self._render_lg(e)
        if tag == "l":
            return self._render_children(e)
        if tag == "list":
            self._list_stack.append(self._list_numid(a))
            out = "".join(self._render_node(c) for c in e.children)
            self._list_stack.pop()
            return out
        if tag == "item":
            level = max(len(self._list_stack) - 1, 0)
            numid = self._list_stack[-1] if self._list_stack else 0
            ppr = self.theme.docx_para("item")
            if numid:
                ppr = (f'<w:numPr><w:ilvl w:val="{level}"/>'
                       f'<w:numId w:val="{numid}"/></w:numPr>') + ppr
            ppr = f"<w:pPr>{ppr}</w:pPr>" if ppr else ""
            return f"<w:p>{ppr}{self._render_children(e, 'item')}</w:p>"
        if tag == "div":
            dtype = a.get("type")
            if dtype:
                self._div_stack.append(f"div-{dtype}")
                out = self._render_children(e)
                self._div_stack.pop()
                return out
            return self._render_children(e)
        if tag in ("table", "row", "cell"):
            return self._render_table(e)
        if tag == "unclear":
            return self._run("□", *self._current_tag())  # 虚缺符号 U+25A1（文字无法辨析）
        if tag == "form":
            return self._para(self._render_children(e, "form", self._rend_tag(a)), "form")
        if tag == "def":
            # 释义（cb:def）：run 带 def 标签（def 字号/字体生效）；
            # def 内 p 见 _render_def_p（run/段落同时带 def，p 上下文保留）。
            self._tag_stack.append("def")
            try:
                out = []
                for c in e.children:
                    if isinstance(c, E) and c.tag == "p":
                        out.append(self._render_def_p(c))
                    else:
                        out.append(self._render_node(c))
                return "".join(out)
            finally:
                self._tag_stack.pop()
        if tag == "sg":
            # 梵呗注音（<cb:sg>）：官方半角括号，如 (音𫬠)；yin/zi 不动
            return (self._run("(", *self._current_tag())
                    + self._render_children(e)
                    + self._run(")", *self._current_tag()))
        return self._render_children(e)

    def _render_def_p(self, p):
        """def 内的 p 段落：run 带 def（def 字号/字体生效），段落标签以
        "def" 结尾挂 pStyle（预览标【释义】）；p 的缩进/边距照旧内联，
        视觉不变（直接属性覆盖样式）。"""
        a = p.attrs
        ptype = a.get("cb:type") or a.get("type")
        ptag = ptype if ptype in self.theme.tags else None
        style = a.get("style") or ""
        indent = 0
        if not self.ignore_xml_style:
            m = re.search(r"margin-left:\s*([\d.]+)em", style)
            if m:
                indent = float(m.group(1))
        tags = tuple(dict.fromkeys(tuple(self._div_stack) + ("p", "def")
                                   + ((ptag,) if ptag else ())))
        runs = self._render_children(p, "p", *((ptag,) if ptag else ()),
                                     self._rend_tag(a), "def")
        return self._para(runs, *tags, indent=indent)

    def _body_has_title_m(self) -> bool:
        """body 树中是否含 <title level="m"> 节点（含则书名由正文渲染，避免 title_para 重复）。"""
        def scan(nodes):
            for n in nodes:
                if isinstance(n, E) and n.tag == "title" and n.attrs.get("level") == "m":
                    return True
                if getattr(n, "children", None) and scan(n.children):
                    return True
            return False
        return scan(self._work.body) if self._work else False

    def _children_no_dup_title(self, e):
        """过滤掉与书名相同的 <title> 子元素（品名/卷名里重复的书名，脏数据）。"""
        title = (self._work.metadata or {}).get("title") if self._work else None
        if not title:
            return e.children
        out = []
        for c in e.children:
            if isinstance(c, E) and c.tag == "title" and self._render_text(c).strip() == title.strip():
                continue
            out.append(c)
        return out

    def _render_tagged_clean(self, nodes, *tags: str) -> str:
        """渲染标题（品名/卷名）：suppress_title_notes 开启时压制校勘注码。"""
        prev = self._suppress_note_ref
        if self.suppress_title_notes:
            self._suppress_note_ref = True
        try:
            return self._render_tagged(nodes, *tags)
        finally:
            self._suppress_note_ref = prev

    def _render_juan_title(self, e, page_break: bool = True) -> str:
        """卷名段落（juan 样式）：书名==卷名则整段跳过（受 suppress_jhead_dup 控制，
        不落空段、不附书签，书名已由 title m 打印）；open 卷非首内容换页。"""
        title = (self._work.metadata or {}).get("title") if self._work else None
        txt = self._render_text(e).strip()
        if self.suppress_jhead_dup and title and txt and txt == title.strip():
            # 单卷去重：jhead 与书名相同，整段丢弃；mulu/卷书签一并清除，
            # 避免孤立书签（书签必须附着在真实段落上）
            self._pending_mulu = None
            self._pending_juan = None
            return ""
        nodes = self._children_no_dup_title(e) if self.suppress_jhead_dup else e.children
        if self.strip_head_no:
            nodes, _ = strip_head_no(nodes)
        with self._no_ann():
            runs = self._render_tagged_clean(nodes, "juan", self._rend_tag(e.attrs))
        return self._para(runs, "juan",
                          page_break=page_break and self._body_para_count > 0)

    def _render_text(self, e) -> str:
        """Concatenate descendant text (for title/heading labels)."""
        parts = []
        for n in e.children:
            if isinstance(n, Text):
                parts.append(n.text)
            elif getattr(n, "children", None):
                parts.append(self._render_text(n))
        return "".join(parts)

    def _render_tt(self, e: E) -> str:
        ts = [c for c in e.children if isinstance(c, E) and c.tag == "t"]
        if e.attrs.get("type") == "app":
            main = [t for t in ts if (t.attrs.get("place") or "") != "foot"]
            return self._render_nodes(main) if main else ""

        def _row(t):
            # 转写行（sa-x-rj）：主题 transliteration 标签（官方朱砂色）
            if (t.attrs.get("xml:lang") or "").startswith("sa"):
                return self._render_tagged(t.children, "transliteration")
            return self._render_nodes(t.children)

        if len(ts) >= 2 and e.attrs.get("type") not in ("app", "single-line"):
            # 官方 docx 两行直连无分隔（如 歾(raṃ)㘕）；不插全角空格
            #（裸 U+3000 run 无 rPr 时部分 Word 回退缺字形显示方框）
            return _row(ts[0]) + _row(ts[1])
        return "".join(_row(c) if isinstance(c, E) and c.tag == "t"
                       else self._render_node(c) for c in e.children)

    def _render_nodes(self, nodes) -> str:
        return "".join(self._render_node(n) for n in nodes)

    def _render_tagged(self, nodes, *tags: str) -> str:
        tags = tuple(t for t in tags if t)
        if tags:
            self._tag_stack.extend(tags)
        out = "".join(self._render_node(n) for n in nodes)
        if tags:
            del self._tag_stack[-len(tags):]
        return out

    @staticmethod
    def _strip_quote_text(nodes, leading=False, trailing=False):
        """去掉偈颂首/尾的「『 』」：改第一个/最后一个 Text 节点内容。"""
        def find(nodes, last):
            seq = nodes if not last else reversed(nodes)
            for n in seq:
                if isinstance(n, Text):
                    return n
                if getattr(n, "children", None):
                    r = find(n.children, last)
                    if r:
                        return r
            return None

        if leading:
            t = find(nodes, False)
            if t:
                t.text = t.text.lstrip("「『")
        if trailing:
            t = find(nodes, True)
            if t:
                t.text = t.text.rstrip("』」")

    @staticmethod
    def _leading_quotes(e) -> int:
        """首行前导引号「『 数量（决定悬挂深度）。"""
        for c in e.children:
            if isinstance(c, Text):
                return len(re.match(r"[「『]*", c.text).group(0))
            if isinstance(c, E):
                n = DocxRenderer._leading_quotes(c)
                if n:
                    return n
        return 0

    def _render_lg(self, e: E) -> str:
        rend = self._rend_tag(e.attrs)
        # 偈颂首句引号悬挂：按首行前导引号「『 数量自动悬挂（每引号 1em），
        # 不依赖 XML text-indent（数据常有 0em 漏标）；块缩进用主题 css 的 verse margin-left
        hang = None
        l_els = [c for c in e.children if isinstance(c, E) and c.tag == "l"]
        if l_els and not self.strip_verse_quotes:
            q = self._leading_quotes(l_els[0])
            if q:
                ml = (self.theme.tags.get("verse") or {}).get("margin-left")
                m = re.match(r"([\d.]+)em", ml or "")
                left = float(m.group(1)) if m else 2.0
                hang = (left, -float(q))
        if self.strip_verse_quotes:
            hang = None  # 去掉引号后不再悬挂
        lines = []
        pending: list = []
        # 建立 l 在 l_els 中的索引以正确处理首尾引号悬挂
        l_index = {id(c): i for i, c in enumerate(l_els)}
        for c in e.children:
            if isinstance(c, E) and c.tag == "l":
                idx = l_index.get(id(c), 0)
                children = list(c.children)
                if self.strip_verse_quotes:
                    if idx == 0:
                        self._strip_quote_text(children, leading=True)
                    if idx == len(l_els) - 1:
                        self._strip_quote_text(children, trailing=True)
                parts = []
                buf = []
                for cc in children:
                    if isinstance(cc, E) and cc.tag == "caesura":
                        parts.append(self._render_tagged(buf, "verse", rend))
                        buf = []
                    else:
                        buf.append(cc)
                if buf or not parts:
                    parts.append(self._render_tagged(buf, "verse", rend))
                sep = self._run(self.verse_caesura, "verse")
                ln = sep.join(parts)
                if pending:
                    pending_runs = "".join(self._render_node(p) for p in pending)
                    ln = pending_runs + ln
                    pending = []
                lines.append(ln)
            elif isinstance(c, (NoteRef, App)):
                pending.append(c)
            elif isinstance(c, Text) and c.text.strip():
                pending.append(c)
            elif isinstance(c, E):
                # Lb/Pb 等在 lg 层直接忽略（_render_node 返回 ""），其它 E 如 anchor 已转为 NoteRef/App
                r = self._render_node(c)
                if r:
                    pending.append(c)
        if pending and lines:
            pending_runs = "".join(self._render_node(p) for p in pending)
            lines[-1] = lines[-1] + pending_runs
            pending = []
        elif pending:
            lines.append("".join(self._render_node(p) for p in pending))
        if not lines:
            return ""
        # 每个 <l> 一行（<w:r><w:br/></w:r> 换行，必须包进 run）；整个 lg 一个段落
        runs = "".join(f"{ln}<w:r><w:br/></w:r>" for ln in lines[:-1]) + lines[-1]
        return self._para(runs, "verse", hang=hang)

    def _render_table(self, e: E) -> str:
        if e.tag == "table":
            return f"<w:tbl>{self._render_nodes(e.children)}</w:tbl>"
        if e.tag == "row":
            return f"<w:tr>{self._render_nodes(e.children)}</w:tr>"
        # 单元格段落走主题（避免回退 Normal 1.5 倍行距）
        return f"<w:tc>{self._para(self._render_children(e, 'p'), 'p')}</w:tc>"

    def _footnote_separator_para(self) -> str:
        """脚注分隔线 pPr：底边框线（粗细/长短/与首行脚注间距，来自
        config.json output.docx.footnoteSeparator；缺省 0.5pt / 30% / 20 twips）。"""
        cfg = self.footnote_separator or {}
        thick = float(cfg.get("thicknessPt") or 0.5)
        length = float(cfg.get("lengthPercent") or 30)
        space = int(cfg.get("spaceTwips") or 20)
        sz = max(2, int(round(thick * 8)))          # w:sz 单位 = 1/8 pt
        text_width = self.page_w - self.page_margins["left"] - self.page_margins["right"]
        right_ind = int(text_width * (100 - length) / 100)   # 线长=栏宽的 length%
        return (f'<w:pBdr><w:bottom w:val="single" w:sz="{sz}" w:space="1" '
                f'w:color="auto"/></w:pBdr>'
                f'<w:spacing w:before="0" w:after="{space}"/>'
                f'<w:ind w:left="0" w:right="{right_ind}"/>')

    def _tei_info_page(self, title: str, author: str) -> str:
        """teiHeader 信息单独尾页，与 HTML 版权块一致：从【經文資訊】开始。"""
        md = (self._work.metadata or {}) if self._work else {}
        src = md.get("source") or "CBETA"
        vol = md.get("vol") or ""
        no = md.get("no") or ""
        pub = (md.get("publication_date") or "").split(" ")[0]
        contrib = md.get("contributors") or ""
        info = [f"【經文資訊】{src}" + (f" 第 {vol} 冊 No. {no}" if vol and no else "")
                + (f"　{title}" if title else "")]
        if pub:
            info.append(f"【版本記錄】發行日期：{pub}，最後更新：{pub}")
        info.append(f"【編輯說明】本資料庫由 財團法人佛教電子佛典基金會（CBETA）依「{src}」所編輯")
        if contrib:
            info.append(f"【原始資料】{contrib}")
        parts = []
        for i, line in enumerate(info):
            ppr = '<w:pageBreakBefore/>' if i == 0 else ""
            parts.append(f'<w:p><w:pPr>{ppr}<w:spacing w:after="120"/></w:pPr>'
                         f'{self._run(line, "p")}</w:p>')
        return "".join(parts)

    def _build_docx(self, title: str, author: str, body: str) -> bytes:
        fns = "".join(self._fns)
        en_section = ""
        if self.notes == "endnote" and self._en_notes:
            items = []
            for seq, content in self._en_notes:
                items.append(self._para(
                    self._run(f"[{seq}] ", "footnote") + content,
                    "footnote"))
            en_section = self._para(self._run("注释", "head"), "head") + "".join(items)
        title_para = ""
        # 书名（teiHeader title m）作首段打印，与官方 docx 首行一致：
        # body 已含 <title level="m"> 节点（如卷内书名）时由正文渲染，避免重复
        if title and not self._body_has_title_m():
            title_para = self._para(self._run(title, "title"), "title", count=False)
        tei_page = self._tei_info_page(title, author)
        pw, ph = self.page_w, self.page_h
        m = self.page_margins
        fnpr = ('<w:footnotePr><w:numRestart w:val="eachPage"/></w:footnotePr>'
                if self.footnote_per_page else "")
        border = ""
        if self.page_border:
            # 页面四周加框：0.75pt 单线，距纸边 24pt（与 PDF 版一致的边框）
            b = '<w:pgBorders w:offsetFrom="page">' \
                f'<w:top w:val="single" w:sz="6" w:space="24" w:color="000000"/>' \
                f'<w:left w:val="single" w:sz="6" w:space="24" w:color="000000"/>' \
                f'<w:bottom w:val="single" w:sz="6" w:space="24" w:color="000000"/>' \
                f'<w:right w:val="single" w:sz="6" w:space="24" w:color="000000"/></w:pgBorders>'
            border = b

        # 经藏名（title level="s"）仅首页顶部一行：正文首段左上角（隶体/黑体，可配置）
        # 字体/字号走主题 p.series-title；config 内旧 font/size 键仅作回退兼容
        series_para = ""
        if self.series_title.get("enabled", True):
            series = ((self._work.metadata.get("series") or "") if self._work else "").strip()
            if series:
                st = self.theme.tags.get("series-title") or {}
                ff = (st.get("font-family") or "").split(",")[0].strip().strip('"').strip("'")
                if not ff:
                    ff = self.series_title.get("font") or "宋体, SimSun"
                    ff = [n.strip().strip('"').strip("'") for n in ff.split(",")][0]
                size = self._series_size_pt(st)
                _srpr = (
                    f'<w:rPr><w:rFonts w:ascii="{self.latin_font}" w:eastAsia="{ff}" w:hAnsi="{self.latin_font}"/>'
                    f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>')
                series_para = (
                    f'<w:p><w:pPr><w:pStyle w:val="series-title"/>'
                    f'<w:jc w:val="left"/></w:pPr>'
                    f'{self._fb_emit(series, _srpr)}</w:p>'
                )
        header_xml = ""  # 保留扩展点：如需页眉可在此生成 header1.xml

        def sect_inner(typ: str = "") -> str:
            t = f'<w:type w:val="{typ}"/>' if typ else ""
            hr = '<w:headerReference w:type="first" r:id="rId4"/>' if header_xml else ""
            tp = '<w:titlePg/>' if header_xml else ""
            td = '<w:textDirection w:val="tbRl"/>' if self.vertical else ""
            # sectPr 子元素顺序：headerReference → footnotePr → type → pgSz → pgMar → pgBorders → titlePg → textDirection
            return (f"{hr}{fnpr}{t}<w:pgSz w:w=\"{pw}\" w:h=\"{ph}\"/>"
                    f'<w:pgMar w:top="{m["top"]}" w:right="{m["right"]}" '
                    f'w:bottom="{m["bottom"]}" w:left="{m["left"]}"/>{border}{tp}{td}')

        def sect(typ: str = "") -> str:
            # 文档末节：sectPr 作 w:body 最后孩子（唯一合法的裸位置）
            return f"<w:sectPr>{sect_inner(typ)}</w:sectPr>"

        def section_break(typ: str = "") -> str:
            # 节间分隔：sectPr 必须装进段落 pPr；裸挂 w:body 会被 Word 忽略
            # （曾导致分页全不生效：切分正确但第二个序不换页）。
            # 终止空段零间距 + 2pt 空 run，几乎不占版心；节尾裸 run/表格等结尾一律适用。
            return (f'<w:p><w:pPr><w:spacing w:after="0" w:before="0"/>'
                    f"<w:sectPr>{sect_inner(typ)}</w:sectPr></w:pPr>"
                    f'<w:r><w:rPr><w:sz w:val="2"/><w:szCs w:val="2"/></w:rPr></w:r></w:p>')

        if isinstance(body, list):
            # 分页模式：每个分页单元一节；duplex → oddPage（单数页开始，Word 自动补空白偶页）
            duplex = bool(self.pagination.get("duplex", False))
            t = "oddPage" if duplex else ""
            inner = series_para + title_para
            if body:
                for sec in body[:-1]:
                    inner += sec + section_break(t)
                if self.pagination.get("tei", True):
                    inner += body[-1] + section_break(t) + en_section + tei_page + sect("")
                else:
                    inner += body[-1] + en_section + tei_page + sect(t)
            else:
                inner += en_section + tei_page + sect("")
        else:
            inner = f"{series_para}{title_para}{body}{en_section}{tei_page}{sect('')}"
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{inner}'
            "</w:body></w:document>"
        )
        sep_para = self._footnote_separator_para()
        footnotes = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr>{sep_para}</w:pPr></w:p></w:footnote>'
            '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
            f"{fns}"
            "</w:footnotes>"
        )
        if self.grayscale:
            # 全局黑白：把 document/footnotes/styles 里所有 w:color 一律去掉
            document = _strip_color(document)
            footnotes = _strip_color(footnotes)
        def _style(tag: str) -> str:
            # div-note 样式内联拷贝 p 布局+粗体（自包含，渲染时按 live 主题计算，
            # 不腐烂；免 basedOn 链兼容风险；预览回落无需跟链）。
            base = ("p", "div-note") if tag == "div-note" else (tag,)
            ppr = self.theme.docx_para(*base)
            if self.bookmarks and tag == "juan":
                # 大纲级别 1 → Word 导航窗格可见卷目录
                ppr += '<w:outlineLvl w:val="0"/>'
            elif self.bookmarks and tag == "pin":
                # 品名 = 第二级目录（挂在卷之下）
                ppr += '<w:outlineLvl w:val="1"/>'
            rpr = self.theme.docx_run(*base)
            ppr_x = f"<w:pPr>{ppr}</w:pPr>" if ppr else ""
            rpr_x = f"<w:rPr>{rpr}</w:rPr>" if rpr else ""
            return (f'<w:style w:type="paragraph" w:styleId="{tag}">'
                    f'<w:name w:val="{tag}"/><w:basedOn w:val="Normal"/>'
                    f"{ppr_x}{rpr_x}</w:style>")

        styled = "".join(_style(tag) for tag in _STYLED_PARAS)
        styles = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="'
            f'{self.latin_font}" w:eastAsia="{self._body_font()}" w:hAnsi="{self.latin_font}"/>'
            f'<w:sz w:val="{int(self.doc_size * 2)}"/></w:rPr></w:rPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
            f'<w:pPr>{self._normal_spacing()}</w:pPr></w:style>'
            f"{styled}"
            "</w:styles>"
        )
        if self.grayscale:
            styles = _strip_color(styles)
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
            + ('<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>' if header_xml else "")
            + "</Types>"
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        )
        doc_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            + ('<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>' if header_xml else "")
            + "</Relationships>"
        )
        numbering = self._build_numbering()
        zio = io.BytesIO()
        with zipfile.ZipFile(zio, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", rels)
            z.writestr("word/document.xml", document)
            z.writestr("word/footnotes.xml", footnotes)
            z.writestr("word/styles.xml", styles)
            z.writestr("word/numbering.xml", numbering)
            z.writestr("word/_rels/document.xml.rels", doc_rels)
            if header_xml:
                z.writestr("word/header1.xml", header_xml)
        return zio.getvalue()

    def _body_font(self) -> str:
        for key in ("body", "p"):
            ff = (self.theme.tags.get(key) or {}).get("font-family")
            if not ff:
                continue
            names = [n.strip().strip('"').strip("'") for n in ff.split(",")]
            names = [n for n in names if n]
            if names:
                return names[0]
        return "微軟正黑體"

    def _normal_spacing(self) -> str:
        """Normal 样式的兜底行距：跟随主题 body 的 line-height（CSS 层叠语义），
        未设回退 p，再未设则 1.5 倍。2026-09-06 前跟 p（正文恒单倍），与 PDF 打架。"""
        lh = (self.theme.tags.get("body") or {}).get("line-height")
        if lh is None:
            lh = (self.theme.tags.get("p") or {}).get("line-height")
        m = re.match(r"([\d.]+)", lh or "")
        if m:
            return f'<w:spacing w:line="{int(float(m.group(1)) * 240)}" w:lineRule="auto"/>'
        return '<w:spacing w:line="360" w:lineRule="auto"/>'

    def _list_indent_base(self) -> int:
        """编号基准缩进：跟随主题 list 的 margin-left（em，按 12pt 基准）。"""
        ml = (self.theme.tags.get("list") or {}).get("margin-left")
        m = re.match(r"([\d.]+)em", ml or "")
        if m:
            return int(float(m.group(1)) * 12 * 20)
        return 420

    def _build_numbering(self) -> str:
        base = self._list_indent_base()
        lvls = ""
        for ilvl in range(9):
            indent = base + ilvl * 360
            lvls += (
                f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/>'
                '<w:numFmt w:val="bullet"/><w:lvlText w:val="•"/>'
                f'<w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{indent}" w:hanging="210"/></w:pPr></w:lvl>'
            )
        none_lvls = ""
        for ilvl in range(9):
            indent = base + ilvl * 360
            none_lvls += (
                f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/>'
                '<w:numFmt w:val="bullet"/><w:lvlText w:val=" "/>'
                f'<w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{indent}" w:hanging="210"/></w:pPr></w:lvl>'
            )
        dec_lvls = ""
        for ilvl in range(9):
            indent = base + ilvl * 360
            dec_lvls += (
                f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/>'
                '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
                f'<w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{indent}" w:hanging="210"/></w:pPr></w:lvl>'
            )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:abstractNum w:abstractNumId="0">{lvls}</w:abstractNum>'
            f'<w:abstractNum w:abstractNumId="1">{none_lvls}</w:abstractNum>'
            f'<w:abstractNum w:abstractNumId="2">{dec_lvls}</w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
            '<w:num w:numId="3"><w:abstractNumId w:val="2"/></w:num>'
            "</w:numbering>"
        )
