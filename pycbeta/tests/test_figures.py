import os
import re
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta import figures as F
from pycbeta.model import E, Text, Work
from pycbeta.render_html import HtmlRenderer
from pycbeta.render_docx import DocxRenderer
from pycbeta.render_epub import EpubRenderer

# 最小合法 1x1 GIF（避免依赖外部数据）
GIF_1PX = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
           b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
           b"\x00\x02\x02D\x01\x00;")


def _work(body):
    return Work(id="T9999", source_file="", metadata={"title": "測試經", "author": "譯者"},
                body=body, notes_by_n={}, apps=[], simplified=False)


def _fig_e(url="../figures/X/t.gif"):
    return E(tag="figure", attrs={}, children=[
        E(tag="graphic", attrs={"url": url}, children=[])])


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class TestSplitGraphicUrl(unittest.TestCase):
    def test_full(self):
        self.assertEqual(F.split_graphic_url("../figures/X/X59p0224_01.gif"),
                         ("X", "X59p0224_01.gif"))

    def test_bare(self):
        self.assertEqual(F.split_graphic_url("a.gif"), (None, "a.gif"))

    def test_empty(self):
        self.assertEqual(F.split_graphic_url(""), (None, ""))
        self.assertEqual(F.graphic_basename("../figures/X/X59p0224_01.gif"),
                         "X59p0224_01.gif")

    def test_download_url(self):
        self.assertEqual(
            F.download_url("X", "X59p0224_01.gif",
                           "https://raw.githubusercontent.com/cbeta-git/CBR2X-figures/master/{canon}/{file}"),
            "https://raw.githubusercontent.com/cbeta-git/CBR2X-figures/master/X/X59p0224_01.gif")


class TestFindFigure(unittest.TestCase):
    def test_order_and_missing(self):
        d = tempfile.mkdtemp()
        a = os.path.join(d, "figures")
        b = os.path.join(d, "txt")
        os.makedirs(a)
        os.makedirs(b)
        _write(os.path.join(a, "x.gif"), GIF_1PX)
        _write(os.path.join(b, "x.gif"), GIF_1PX)
        # figures/ 优先于 txt/
        self.assertEqual(F.find_figure("x.gif", [a, b]),
                         os.path.join(a, "x.gif"))
        self.assertEqual(F.find_figure("x.gif", [b, a]),
                         os.path.join(b, "x.gif"))
        self.assertIsNone(F.find_figure("nope.gif", [a, b]))
        self.assertIsNone(F.find_figure("", [a]))

    def test_search_dirs(self):
        d = tempfile.mkdtemp()
        wd = os.path.join(d, "T9999 測試經")
        os.makedirs(os.path.join(wd, "figures"))
        os.makedirs(os.path.join(wd, "txt"))
        dirs = F.search_dirs(work_dir=wd)
        self.assertEqual(dirs, [os.path.join(wd, "figures"), os.path.join(wd, "txt")])
        # 不存在的目录不收
        self.assertEqual(F.search_dirs(work_dir=os.path.join(d, "nope")), [])

    def test_work_figure_dirs(self):
        d = tempfile.mkdtemp()
        wd = os.path.join(d, "T9999 測試經")
        os.makedirs(os.path.join(wd, "txt"))
        xml = os.path.join(wd, "T9999.xml")
        open(xml, "w").close()
        dirs = F.work_figure_dirs(d, "T9999", xml)
        self.assertIn(os.path.join(wd, "txt"), dirs)


class TestImageProbe(unittest.TestCase):
    def test_gif_size(self):
        d = tempfile.mkdtemp()
        p = _write(os.path.join(d, "t.gif"), GIF_1PX)
        self.assertEqual(F.gif_size(p), (1, 1))
        self.assertEqual(F.image_size(p), (1, 1))

    def test_not_image(self):
        d = tempfile.mkdtemp()
        p = _write(os.path.join(d, "x.html"), b"<html>404</html>")
        self.assertIsNone(F.gif_size(p))
        self.assertIsNone(F.image_size(p))
        self.assertFalse(F.looks_like_image(p))
        g = _write(os.path.join(d, "t.gif"), GIF_1PX)
        self.assertTrue(F.looks_like_image(g))

    def test_jpeg_size(self):
        # 最小 JPEG 头：SOI + SOF0(48x32) + EOI
        data = (b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x20\x00\x30"
                b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xd9")
        d = tempfile.mkdtemp()
        p = _write(os.path.join(d, "t.jpg"), data)
        self.assertEqual(F.jpeg_size(p), (48, 32))
        self.assertEqual(F.image_size(p), (48, 32))
        self.assertIsNone(F.jpeg_size(os.path.join(d, "nope.jpg")))

    def test_urls_in_text(self):
        s = '<p>a<graphic url="../figures/X/a.gif"/>b<graphic url="c.gif"/></p>'
        self.assertEqual(F.graphic_urls_in_text(s),
                         ["../figures/X/a.gif", "c.gif"])


class TestHtmlGraphic(unittest.TestCase):
    def test_embedded(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "t.gif"), GIF_1PX)
        r = HtmlRenderer(figure_base=[d])
        out = r._render_e(_fig_e())
        self.assertIn('<img src="data:image/gif;base64,', out)
        self.assertEqual(r.missing_figures, [])

    def test_missing_placeholder(self):
        r = HtmlRenderer(figure_base=[tempfile.mkdtemp()])
        out = r._render_e(_fig_e("../figures/X/m.gif"))
        self.assertIn("class='graphic'", out)
        self.assertEqual(r.missing_figures, ["m.gif"])


class TestEpubGraphic(unittest.TestCase):
    def test_missing_recorded(self):
        r = EpubRenderer(figure_base=[tempfile.mkdtemp()])
        fn = r.render_work(_work([_fig_e("../figures/X/m.gif")]), tempfile.mkdtemp(),
                           "m.epub")
        self.assertTrue(os.path.isfile(fn))
        self.assertEqual(r.missing_figures, ["m.gif"])


class TestFigureOnly(unittest.TestCase):
    def test_is_figure_only(self):
        p = E(tag="p", attrs={}, children=[
            _fig_e(), Text(text="  \n"),
            E(tag="lb", attrs={}, children=[])])
        self.assertTrue(F.is_figure_only(p))
        q = E(tag="p", attrs={}, children=[Text(text="文"), _fig_e()])
        self.assertFalse(F.is_figure_only(q))
        self.assertFalse(F.is_figure_only(E(tag="p", attrs={}, children=[])))

    def test_style_registered(self):
        from pycbeta.theme import TAG_SELECTOR
        from pycbeta.render_docx import _STYLED_PARAS
        from pycbeta.gui.css_editor import EDITABLE_ROWS
        self.assertEqual(TAG_SELECTOR.get("figure"), "p.figure")
        self.assertIn("figure", _STYLED_PARAS)
        self.assertIn(("p.figure", "图片"), EDITABLE_ROWS)


class TestFigureParagraphCentered(unittest.TestCase):
    def test_docx_centered_no_indent(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "t.gif"), GIF_1PX)
        r = DocxRenderer(figure_base=[d])
        p = E(tag="p", attrs={}, children=[_fig_e()])
        fn = r.render_work(_work([p]), d, "f.docx")
        z = zipfile.ZipFile(fn)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertIn('w:pStyle w:val="figure"', doc)
        styles = z.read("word/styles.xml").decode("utf-8")
        m = re.search(r'<w:style[^>]*w:styleId="figure".*?</w:style>', styles, re.S)
        self.assertIsNotNone(m)
        self.assertIn('w:jc w:val="center"', m.group(0))
        self.assertNotIn("w:firstLine", m.group(0))
        z.close()

    def test_docx_mixed_keeps_p(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "t.gif"), GIF_1PX)
        r = DocxRenderer(figure_base=[d])
        p = E(tag="p", attrs={}, children=[Text(text="文"), _fig_e()])
        fn = r.render_work(_work([p]), d, "m.docx")
        doc = zipfile.ZipFile(fn).read("word/document.xml").decode("utf-8")
        self.assertIn('w:pStyle w:val="p"', doc)
        self.assertNotIn('w:pStyle w:val="figure"', doc)

    def test_html_figure_class(self):
        r = HtmlRenderer()
        p = E(tag="p", attrs={}, children=[_fig_e()])
        out = r._render_e(p)
        self.assertIn('<p class="figure">', out)
        q = E(tag="p", attrs={}, children=[Text(text="文"), _fig_e()])
        self.assertIn('<p class="">', r._render_e(q))


class TestDocxGraphic(unittest.TestCase):
    def _renderer(self, d):
        r = DocxRenderer(figure_base=[d])
        r._reset_state(_work([]))
        return r

    def test_embedded_package(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "t.gif"), GIF_1PX)
        r = self._renderer(d)
        body = r._render_e(_fig_e())
        self.assertIn("<w:drawing", body)
        self.assertIn('r:embed="rIdImg1"', body)
        doc = r._build_docx("t", "a", body)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(doc)
            fn = f.name
        try:
            z = zipfile.ZipFile(fn)
            names = z.namelist()
            self.assertIn("word/media/image1.gif", names)
            rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
            self.assertIn('Target="media/image1.gif"', rels)
            self.assertIn('Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"',
                          rels)
            document = z.read("word/document.xml").decode("utf-8")
            self.assertIn("<w:drawing", document)
            ct = z.read("[Content_Types].xml").decode("utf-8")
            self.assertIn('Extension="gif"', ct)
            # OOXML 必须良构（曾漏 </a:xfrm> 导致 Word 打不开）
            from lxml import etree
            for part in ("word/document.xml",
                         "word/_rels/document.xml.rels",
                         "[Content_Types].xml"):
                etree.fromstring(z.read(part))
            z.close()
        finally:
            os.remove(fn)
        self.assertEqual(r.missing_figures, [])

    def test_missing_fallback(self):
        r = self._renderer(tempfile.mkdtemp())
        out = r._render_e(_fig_e("../figures/X/m.gif"))
        self.assertIn("【圖：m.gif】", out)
        self.assertNotIn("<w:drawing", out)
        self.assertEqual(r.missing_figures, ["m.gif"])

    def test_native_size_no_upscale(self):
        # 1x1 小图：extent 即原生 1px（9525 EMU），不拉伸
        import re
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "t.gif"), GIF_1PX)
        r = self._renderer(d)
        out = r._render_e(_fig_e())
        m = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"', out)
        self.assertIsNotNone(m)
        self.assertEqual((int(m.group(1)), int(m.group(2))), (9525, 9525))

    def test_wide_shrinks_keep_ratio(self):
        # 超宽图：压到版心宽、等比（只缩小不放大）
        import re
        import struct
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "w.gif"),
               b"GIF89a" + struct.pack("<HH", 2000, 1000) + b"\x00" * 20)
        r = self._renderer(d)
        out = r._render_e(_fig_e("../figures/X/w.gif"))
        m = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"', out)
        self.assertIsNotNone(m)
        max_px = (r.page_w - r.page_margins["left"] - r.page_margins["right"]) // 15
        self.assertEqual(int(m.group(1)), max_px * 9525)
        self.assertEqual(int(m.group(2)), (1000 * max_px // 2000) * 9525)

    def test_inline_no_nested_para(self):
        # 段内 <figure> 只出 run 级 drawing，不嵌套 <w:p>（WPS 会丢弃嵌套段落图片）
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "t.gif"), GIF_1PX)
        r = self._renderer(d)
        p = E(tag="p", attrs={}, children=[Text(text="文"), _fig_e(), Text(text="字")])
        out = r._render_e(p)
        self.assertEqual(out.count("<w:p>"), 1)
        self.assertEqual(out.count("</w:p>"), 1)
        self.assertEqual(out.count("<w:drawing"), 1)
        self.assertEqual(out.count("</w:drawing>"), 1)


class TestEnsureFigures(unittest.TestCase):
    def test_txt_bonus_and_download(self):
        from pycbeta import fetch as fetch_mod
        root = tempfile.mkdtemp()
        wd = os.path.join(root, "T9999 測試經")
        os.makedirs(os.path.join(wd, "txt"))
        _write(os.path.join(wd, "txt", "a.gif"), GIF_1PX)

        def fake_download(url, dest, timeout=90):
            _write(dest, GIF_1PX)
            return True

        with mock.patch.object(fetch_mod, "_http_download", side_effect=fake_download):
            ok, missing = fetch_mod.ensure_figures(
                "T9999", ["../figures/T/a.gif", "../figures/T/b.gif"],
                {}, root, wdir=wd)
        self.assertEqual(missing, [])
        self.assertTrue(os.path.isfile(os.path.join(wd, "figures", "a.gif")))
        self.assertTrue(os.path.isfile(os.path.join(wd, "figures", "b.gif")))
        self.assertEqual(len(ok), 2)

    def test_download_404_missing(self):
        from pycbeta import fetch as fetch_mod
        root = tempfile.mkdtemp()
        wd = os.path.join(root, "T9999 測試經")
        os.makedirs(wd)
        with mock.patch.object(fetch_mod, "_http_download", return_value=False):
            ok, missing = fetch_mod.ensure_figures(
                "T9999", ["../figures/T/b.gif"], {}, root, wdir=wd)
        self.assertEqual(ok, [])
        self.assertEqual(missing, ["b.gif"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
