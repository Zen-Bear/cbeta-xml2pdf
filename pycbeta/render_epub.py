"""EPUB3 renderer: IR -> EPUB package.

Content chapters are produced by the HTML renderer (official-format body),
then packaged as EPUB3 (OPF + nav + NCX). Notes default to endnotes
(the official #back section works inside EPUB readers).
"""

import io
import os
import re
import zipfile
import xml.sax.saxutils as sax
from typing import List, Optional

from .model import Work
from .annotate import active as _ann_active
from .render_html import HtmlRenderer, CSS
from .theme import Theme


def _x(s: str) -> str:
    return sax.escape(s)


class EpubRenderer:
    def __init__(self, gaiji_db=None, theme=None, notes="endnote", base_css=None,
                 ignore_xml_style=False, ignore_xml_space=False, show_notes=True,
                 annotations=None):
        self.theme = theme if theme is not None else Theme()
        self.notes = notes
        self.gaiji_db = gaiji_db
        self.base_css = base_css
        self.ignore_xml_style = ignore_xml_style
        self.ignore_xml_space = ignore_xml_space
        self.show_notes = show_notes
        # 难字注音（P6）：None 或 {"table", "scheme"}，转发给内部 HtmlRenderer
        self._annotations = _ann_active(annotations)

    def render_work(self, work: Work, out_dir: str, filename: str = "") -> str:
        tmp = os.path.join(out_dir, "_epub_tmp")
        html_files = HtmlRenderer(theme=self.theme, notes=self.notes,
                                  base_css=self.base_css,
                                  ignore_xml_style=self.ignore_xml_style,
                                  ignore_xml_space=self.ignore_xml_space,
                                  show_notes=self.show_notes,
                                  annotations=self._annotations) \
            .render_work(work, tmp)
        md = work.metadata
        title = md.get("title") or work.id
        author = md.get("author") or ""
        lang = "zh-Hans" if getattr(work, "simplified", False) else "zh-Hant"
        chapters = self._build_chapters(tmp, html_files, title)
        opf = self._build_opf(work, title, author, chapters, lang)
        nav = self._build_nav(title, chapters, lang)
        ncx = self._build_ncx(title, chapters)
        data = self._zip(work.id, chapters, opf, nav, ncx, lang)
        os.makedirs(out_dir, exist_ok=True)
        if not filename:
            filename = f"{work.id}.epub"
        fn = os.path.join(out_dir, filename)
        with open(fn, "wb") as f:
            f.write(data)
        return fn

    def _build_chapters(self, tmp: str, html_files: List[str], title: str) -> List[dict]:
        chapters = []
        for fn in html_files:
            html = open(os.path.join(tmp, fn), encoding="utf-8").read()
            body = self._extract_body(html)
            m = re.search(r"_(\d+)\.html$", fn)
            juan = int(m.group(1)) if m else len(chapters) + 1
            cid = f"ch{len(chapters) + 1}"
            chapters.append({"id": cid, "file": f"{cid}.xhtml",
                             "title": f"{title} 卷{juan:03d}", "body": body})
        return chapters

    @staticmethod
    def _extract_body(html: str) -> str:
        body = re.search(r"<body>(.*)</body>", html, re.S)
        return body.group(1) if body else ""

    def _build_chapter_xhtml(self, ch: dict, title: str, css: str,
                               lang: str = "zh-Hant") -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}">\n<head>\n'
            f'<title>{_x(ch["title"])}</title>\n'
            f'<style>{css}</style>\n'
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
        css = self.theme.raw_css or self.theme.css()
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
                                                  '@import url("style.css");',
                                                  lang)
                z.writestr(f"OEBPS/{c['file']}", xhtml)
        return zio.getvalue()
