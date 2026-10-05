"""EPUB3 renderer: IR -> EPUB package.

Content chapters are produced by the HTML renderer (official-format body),
then packaged as EPUB3 (OPF + nav + NCX). Notes default to endnotes
(the official #back section works inside EPUB readers).
"""

import io
import os
import re
import shutil
import zipfile
import xml.sax.saxutils as sax
from typing import List, Optional

from .model import Work
from .annotate import active as _ann_active
from .render_html import HtmlRenderer, CSS


def _x(s: str) -> str:
    return sax.escape(s)


class EpubRenderer:
    def __init__(self, gaiji_db=None, theme=None, notes="endnote", base_css=None,
                 ignore_xml_style=False, ignore_xml_space=False, show_notes=True,
                 annotations=None, strip_head_no=False, inline_brackets="fullwidth",
                 note_inline_brackets=None, figure_base=None, corr_cbeta=False,
                 siddham_text=False, mulu_break=True, mulu_levels=(1,),
                 mulu_zhang_break=False,
                 pre_dedent=False, pre_dedent_spaces=4):
        # theme=None → 纯基底（官方基底默认）；pdf_docx 主题不再进 epub
        #（render_html 章节与 style.css 同源 base_css）。
        self.theme = theme
        self.notes = notes
        self.gaiji_db = gaiji_db
        self.base_css = base_css
        self.ignore_xml_style = ignore_xml_style
        self.ignore_xml_space = ignore_xml_space
        self.show_notes = show_notes
        # 难字注音（P6）：None 或 {"table", "scheme"}，转发给内部 HtmlRenderer
        self._annotations = _ann_active(annotations)
        self.strip_head_no = strip_head_no  # 去 head/jhead 行首 No. 令牌（转内部 HtmlRenderer）
        self.corr_cbeta = corr_cbeta        # CBETA 校改字标红（转内部 HtmlRenderer）
        self.inline_brackets = inline_brackets
        self.note_inline_brackets = note_inline_brackets or inline_brackets
        self.figure_base = figure_base
        self.siddham_text = siddham_text  # 转内部 HtmlRenderer（有读音悉昙字形+读音，默认关）
        self.mulu_break = mulu_break      # 非「卷」mulu 拆 spine（与 docx mulu_levels 分页同口径）
        self.mulu_levels = mulu_levels    # 触发拆 spine 的 mulu level 集合（转内部 HtmlRenderer）
        self.mulu_zhang_break = bool(mulu_zhang_break)  # 章信号（第X章）也拆 spine
        self.pre_dedent = bool(pre_dedent)          # 预排去缩进（转内部 HtmlRenderer）
        try:
            self.pre_dedent_spaces = max(0, int(pre_dedent_spaces))
        except (TypeError, ValueError):
            self.pre_dedent_spaces = 4
        self.missing_figures = []

    def render_work(self, work: Work, out_dir: str, filename: str = "") -> str:
        tmp = os.path.join(out_dir, "_epub_tmp")
        self.missing_figures = []
        try:
            inner = HtmlRenderer(theme=self.theme, notes=self.notes,
                                 base_css=self.base_css,
                                 ignore_xml_style=self.ignore_xml_style,
                                 ignore_xml_space=self.ignore_xml_space,
                                 show_notes=self.show_notes,
                                 annotations=self._annotations,
                                 strip_head_no=self.strip_head_no,
                                  inline_brackets=self.inline_brackets,
                                  note_inline_brackets=self.note_inline_brackets,
                                  figure_base=self.figure_base,
                                  siddham_text=self.siddham_text,
                                  corr_cbeta=self.corr_cbeta,
                                  mulu_break=self.mulu_break,
                                  mulu_levels=self.mulu_levels,
                                  mulu_zhang_break=self.mulu_zhang_break,
                                  pre_dedent=self.pre_dedent,
                                  pre_dedent_spaces=self.pre_dedent_spaces)
            html_files = inner.render_work(work, tmp)
            self.missing_figures = list(inner.missing_figures)
            md = work.metadata
            title = md.get("title") or work.id
            author = md.get("author") or ""
            lang = "zh-Hans" if getattr(work, "simplified", False) else "zh-Hant"
            chapters = self._build_chapters(tmp, html_files, title)
            chapters, copyright_ch = self._split_copyright(chapters)
            # spine = 正文卷 + 版权页；nav/ncx 目录只留正文卷
            spine = chapters + ([copyright_ch] if copyright_ch else [])
            opf = self._build_opf(work, title, author, spine, lang)
            nav = self._build_nav(title, chapters, lang)
            ncx = self._build_ncx(title, chapters)
            data = self._zip(work.id, spine, opf, nav, ncx, lang)
            os.makedirs(out_dir, exist_ok=True)
            if not filename:
                filename = f"{work.id}.epub"
            fn = os.path.join(out_dir, filename)
            with open(fn, "wb") as f:
                f.write(data)
            return fn
        finally:
            # 中间 HTML 目录随包生成后清理（成功/失败都清，避免污染输出/校验目录）
            shutil.rmtree(tmp, ignore_errors=True)

    _MULU_BREAK_RE = re.compile(
        r'<div class="mulu-break" data-title="([^"]*)"></div>')

    @classmethod
    def _split_mulu_breaks(cls, body: str) -> List[tuple]:
        """按 level-1 非「卷」mulu 断页标记把一卷正文切成 [(标题|None, html)]。
        与 docx `split_sections` 口径一致：首个标记前无可见内容则不切
        （镜像「首个序/品不切」）。无标记 → 原样单段。"""
        parts = []
        cur_title = None
        last = 0
        for m in cls._MULU_BREAK_RE.finditer(body):
            seg = body[last:m.start()]
            if parts or re.sub(r"<[^>]+>", "", seg).strip():
                parts.append((cur_title, seg))
            cur_title = m.group(1) or None
            last = m.end()
        tail = body[last:]
        if parts or re.sub(r"<[^>]+>", "", tail).strip():
            parts.append((cur_title, tail))
        return parts or [(None, body)]

    def _build_chapters(self, tmp: str, html_files: List[str], title: str) -> List[dict]:
        chapters = []
        for fn in html_files:
            html = open(os.path.join(tmp, fn), encoding="utf-8").read()
            body = self._extract_body(html)
            m = re.search(r"_(\d+)\.html$", fn)
            juan = int(m.group(1)) if m else len(chapters) + 1
            for ctitle, seg in self._split_mulu_breaks(body):
                cid = f"ch{len(chapters) + 1}"
                chapters.append({"id": cid, "file": f"{cid}.xhtml",
                                 "title": ctitle or f"{title} 卷{juan:03d}",
                                 "body": seg})
        return chapters

    @staticmethod
    def _split_copyright(chapters: List[dict]):
        """各章末尾的 `#cbeta-copyright` 版权块抽走去重，独立成 spine 末项。

        CSS 分页在阅读器里不可靠，且多卷时版权块会逐章重复；
        独立 spine 项在所有阅读器都另起一页（官方 epub 同款 back.xhtml 做法）。
        返回 (正文章节, 版权章节或 None)；nav/ncx 只用正文章节。"""
        kept = None
        pat = re.compile(r"<div id='cbeta-copyright'>.*?</div>\s*"
                         r"<!-- end of cbeta-copyright -->", re.S)
        for ch in chapters:
            m = pat.search(ch["body"] or "")
            if m:
                if kept is None:
                    kept = m.group(0)
                ch["body"] = ch["body"][:m.start()] + ch["body"][m.end():]
        copyright_ch = None
        if kept:
            copyright_ch = {"id": "copyright", "file": "copyright.xhtml",
                            "title": "經文資訊", "body": kept}
        return chapters, copyright_ch

    @staticmethod
    def _extract_body(html: str) -> str:
        body = re.search(r"<body>(.*)</body>", html, re.S)
        return body.group(1) if body else ""

    def _build_chapter_xhtml(self, ch: dict, title: str, css: str,
                               lang: str = "zh-Hant") -> str:
        # css = 外部样式表文件名（同目录）；用 <link> + manifest 声明，
        # 兼容性优于 <style>@import（部分阅读器忽略未入 manifest 的资源）
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}">\n<head>\n'
            f'<title>{_x(ch["title"])}</title>\n'
            f'<link rel="stylesheet" type="text/css" href="{_x(css)}"/>\n'
            "</head>\n<body>\n"
            f'{ch["body"]}\n'
            "</body>\n</html>"
        )

    def _build_opf(self, work, title, author, chapters, lang="zh-Hant") -> str:
        manifest = "".join(
            f'<item id="{c["id"]}" href="{c["file"]}" media-type="application/xhtml+xml"/>'
            for c in chapters)
        manifest += ('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
                     'properties="nav"/>')
        manifest += ('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
        manifest += ('<item id="style" href="style.css" media-type="text/css"/>')
        spine = "".join(f'<itemref idref="{c["id"]}"/>' for c in chapters)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">\n'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'<dc:identifier id="uid">{_x(work.id)}</dc:identifier>\n'
            f'<dc:title>{_x(title)}</dc:title>\n'
            f'<dc:language>{lang}</dc:language>\n'
            f'<dc:creator>{_x(author)}</dc:creator>\n'
            '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>\n'
            "</metadata>\n"
            f'<manifest>{manifest}</manifest>\n'
            f'<spine toc="ncx">{spine}</spine>\n'
            "</package>"
        )

    def _build_nav(self, title, chapters, lang="zh-Hant") -> str:
        items = "".join(f'<li><a href="{c["file"]}">{_x(c["title"])}</a></li>' for c in chapters)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            f'xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}">\n<head>\n'
            f"<title>{_x(title)}</title>\n</head>\n<body>\n<nav epub:type=\"toc\">\n"
            f"<h1>{_x(title)}</h1>\n<ol>\n{items}\n</ol>\n</nav>\n</body>\n</html>"
        )

    def _build_ncx(self, title, chapters) -> str:
        items = "".join(
            f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{_x(c["title"])}</text></navLabel>'
            f'<content src="{c["file"]}"/></navPoint>'
            for i, c in enumerate(chapters, 1))
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
            f'<head><meta name="dtb:uid" content=""/></head>\n'
            f'<docTitle><text>{_x(title)}</text></docTitle>\n'
            f'<navMap>{items}</navMap>\n</ncx>'
        )

    def _zip(self, work_id, chapters, opf, nav, ncx, lang="zh-Hant") -> bytes:
        css = self.base_css if self.base_css is not None else CSS
        zio = io.BytesIO()
        with zipfile.ZipFile(zio, "w") as z:
            z.writestr("mimetype", "application/epub+zip",
                       compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml",
                       '<?xml version="1.0" encoding="utf-8"?>\n'
                       '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                       '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                       "</rootfiles></container>")
            z.writestr("OEBPS/content.opf", opf)
            z.writestr("OEBPS/nav.xhtml", nav)
            z.writestr("OEBPS/toc.ncx", ncx)
            z.writestr("OEBPS/style.css", css)
            for c in chapters:
                xhtml = self._build_chapter_xhtml(c, c["title"],
                                                  "style.css", lang)
                z.writestr(f"OEBPS/{c['file']}", xhtml)
        return zio.getvalue()
