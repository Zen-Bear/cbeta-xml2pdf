import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.render_pdf import PdfRenderer, _draw_page_borders, _add_pdf_bookmarks

CBETA = r"E:\dev\cbeta\cbeta_ebook"


def extract_text(pdf):
    import pymupdf
    doc = pymupdf.open(pdf)
    return len(doc), "".join(p.get_text() for p in doc)


class TestPdfHorizontal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "X1116 毗尼日用切要香乳記", "X60n1116.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_horizontal_a4(self):
        r = PdfRenderer(page="a4")
        html = r.render_work(self.work, self.tmp, "main.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "out.pdf"))
        pages, text = extract_text(pdf)
        self.assertGreater(pages, 50)
        self.assertIn("原夫文", text)
        self.assertIn("校注", text)
        self.assertGreater(len(text), 30000)

    def test_page_size_phone(self):
        import pymupdf
        r = PdfRenderer(page="手机")
        html = r.render_work(self.work, self.tmp, "phone.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "phone.pdf"))
        doc = pymupdf.open(pdf)
        w, h = doc[0].rect.width, doc[0].rect.height
        self.assertLess(w, h)  # portrait
        self.assertAlmostEqual(w, 283.5, delta=10)  # ~100mm

    def test_vertical(self):
        r = PdfRenderer(page="a4", vertical=True)
        html = r.render_work(self.work, self.tmp, "vert.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "vert.pdf"))
        pages, text = extract_text(pdf)
        self.assertGreater(pages, 50)
        self.assertIn("原夫文".replace("", "\n").replace("\n\n", "\n")[0:1], text)
        self.assertGreater(len(text), 30000)

    def test_grayscale_css(self):
        r = PdfRenderer(page="a4", grayscale=True)
        html = r.render_work(self.work, self.tmp, "gray.html")
        with open(html, encoding="utf-8") as f:
            css = f.read()
        self.assertIn("color: #000 !important", css)
        self.assertIn("background-color: #fff !important", css)
        r2 = PdfRenderer(page="a4")
        html2 = r2.render_work(self.work, self.tmp, "color.html")
        with open(html2, encoding="utf-8") as f:
            css2 = f.read()
        self.assertNotIn("!important", css2)

    def test_page_border_drawn(self):
        import pymupdf
        src = os.path.join(self.tmp, "tiny.pdf")
        d = pymupdf.open()
        d.new_page(width=595, height=842)
        d.save(src)
        d.close()
        _draw_page_borders(src)
        doc = pymupdf.open(src)
        self.assertEqual(len(doc), 1)
        drawings = doc[0].get_drawings()
        self.assertEqual(len(drawings), 1)
        rect = drawings[0]["rect"]
        self.assertGreater(rect.width, 500)
        self.assertGreater(rect.height, 700)

    def test_bookmarks_toc(self):
        import pymupdf
        src = os.path.join(self.tmp, "bm.pdf")
        d = pymupdf.open()
        d.new_page(width=595, height=842)
        d.new_page(width=595, height=842)
        d.save(src)
        d.close()
        _add_pdf_bookmarks(src, [(1, "卷一"), (2, "卷二")])
        doc = pymupdf.open(src)
        self.assertEqual(doc.get_toc(), [[1, "卷一", 1], [1, "卷二", 2]])

    def test_split_by_juan(self):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        w = P5Parser().parse(xml)
        r = PdfRenderer(page="a4", split=True)
        htmls = r.render_work(w, self.tmp, "sp.html")
        self.assertEqual(len(htmls), 1)
        pdfs = [os.path.splitext(h)[0] + ".pdf" for h in htmls]
        for h, p in zip(htmls, pdfs):
            r.html_to_pdf(h, p)
        for p in pdfs:
            self.assertTrue(os.path.isfile(p))

    def test_juan_heading_pages(self):
        """目录书签页号：多卷书每卷从新页开始。"""
        r = PdfRenderer(page="a4")
        html = r.render_work(self.work, self.tmp, "jh.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "jh.pdf"))
        import pymupdf
        doc = pymupdf.open(pdf)
        toc = doc.get_toc()
        self.assertEqual(len(toc), 2)
        self.assertEqual(toc[0], [1, "毗尼日用切要香乳記卷上", 1])
        pages = [t[2] for t in toc]
        self.assertEqual(len(set(pages)), 2)  # 两卷不同页


class TestVerticalWrap(unittest.TestCase):
    """竖排 body class 开关（纯字符串，不调引擎/字体）。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[], notes_by_n={}, apps=[], simplified=False)

    def test_vertical_body_class(self):
        r = PdfRenderer(page="a4", vertical=True)
        r._pdf_css = lambda: "BASE"
        out = r._wrap("<p>x</p>", self._work())
        self.assertIn('<body class="vertical-rl">', out)

    def test_horizontal_no_class(self):
        r = PdfRenderer(page="a4", vertical=False)
        r._pdf_css = lambda: "BASE"
        out = r._wrap("<p>x</p>", self._work())
        self.assertIn("<body>", out)
        self.assertNotIn("vertical-rl", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
