import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.render_md import MdRenderer
from pycbeta.render_epub import EpubRenderer

CBETA = r"E:\dev\cbeta\test"


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
