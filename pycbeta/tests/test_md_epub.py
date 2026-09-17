import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.render_md import MdRenderer
from pycbeta.render_epub import EpubRenderer

CBETA = r"E:\dev\cbeta\cbeta_ebook"


class TestMd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_md_strip_head_no(self):
        from pycbeta.model import E, Text
        head = E(tag="head", attrs={}, children=[Text(text="No. 1116-B"),
                                                 Text(text=" 序")])
        t = MdRenderer(strip_head_no=True)._render_node(head)
        self.assertNotIn("No. 1116", t)
        self.assertIn("序", t)
        t2 = MdRenderer()._render_node(head)
        self.assertIn("No.1116-B", t2)  # md 归一化无空格；默认保留令牌

    def test_md(self):
        fn = MdRenderer(notes="endnote").render_work(self.work, self.tmp)
        text = open(fn, encoding="utf-8").read()
        self.assertIn("# 彌勒", text)
        self.assertIn("[^1]", text)
        self.assertIn("[^1]:", text)
        self.assertIn("## 校注", text)

    def test_md_inline(self):
        fn = MdRenderer(notes="inline").render_work(self.work, self.tmp, "i.md")
        text = open(fn, encoding="utf-8").read()
        self.assertNotIn("[^1]", text)
        self.assertIn("（月氏國", text)


class TestEpub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_epub(self):
        fn = EpubRenderer().render_work(self.work, self.tmp)
        z = zipfile.ZipFile(fn)
        names = z.namelist()
        for p in ("mimetype", "META-INF/container.xml", "OEBPS/content.opf",
                  "OEBPS/nav.xhtml", "OEBPS/toc.ncx"):
            self.assertIn(p, names)
        self.assertEqual(z.read("mimetype").decode(), "application/epub+zip")
        ch = [n for n in names if n.endswith(".xhtml") and "ch" in n]
        self.assertTrue(ch)
        xhtml = z.read(ch[0]).decode("utf-8")
        self.assertIn("<body>", xhtml)
        self.assertIn("彌勒", xhtml)
        # 中间 HTML 目录 _epub_tmp 生成后清理，不留残余
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "_epub_tmp")))


class TestCorrCbetaRender(unittest.TestCase):
    """corr-cbeta：html 开门控 span.corr；md 始终透明（排除）。"""

    def _work(self):
        from pycbeta.model import E, Text, Work
        return Work(id="T", source_file="",
                    metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=[
                        Text(text="甲"),
                        E(tag="corr-cbeta", attrs={"n": "1"},
                          children=[Text(text="弗")]),
                        Text(text="乙")])],
                    notes_by_n={}, apps=[], simplified=False)

    def test_html_on_off(self):
        from pycbeta.render_html import HtmlRenderer
        out = {}
        for flag in (False, True):
            d = tempfile.mkdtemp()
            self.addCleanup(__import__("shutil").rmtree, d, True)
            HtmlRenderer(theme=None, notes="endnote",
                         corr_cbeta=flag).render_work(self._work(), d)
            blob = "".join(
                open(os.path.join(d, f), encoding="utf-8").read()
                for f in os.listdir(d) if f.endswith(".html"))
            out[flag] = blob
        self.assertNotIn('class="corr"', out[False])
        self.assertIn('class="corr"', out[True])
        self.assertIn("弗", out[True])

    def test_md_plain(self):
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        fn = MdRenderer(notes="endnote").render_work(self._work(), d)
        text = open(fn, encoding="utf-8").read()
        self.assertIn("弗", text)
        self.assertNotIn("corr", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
