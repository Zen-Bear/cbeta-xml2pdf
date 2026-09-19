import glob
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.model import E, Note, NoteRef, Text
from pycbeta.render_docx import DocxRenderer
from pycbeta.render_html import HtmlRenderer
from pycbeta.render_md import MdRenderer
from pycbeta.verify import normalize

CBETA = r"E:\dev\cbeta\cbeta_ebook"


def _body(html):
    """剥 <style>/<script>、官方 head 边框 span、style 属性、标签间空白后比较正文
    （官方 CSS/模板装饰差异不计，如校注说明注释、<span class="border">、lg 内联样式、缩进换行）。"""
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    html = re.sub(r"<html[^>]*>", "<html>", html)  # lang 等文档属性不计入正文比对
    html = re.sub(r'<span class="border">|</span>', "", html)
    html = re.sub(r'\sstyle="[^"]*"', "", html)
    html = re.sub(r">\s+<", "><", html)
    return html.split("<div id='cbeta-copyright'>")[0]


class TestRenderX1116(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "X1116 毗尼日用切要香乳記", "X60n1116.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()
        # inline 括号 halfwidth 对齐 CBETA 官方（官方 html 用半角括号）
        cls.files = HtmlRenderer(inline_brackets="halfwidth").render_work(cls.work, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_files(self):
        self.assertEqual(self.files, ["X1116_001.html", "X1116_002.html"])

    def test_matches_official(self):
        base = os.path.join(CBETA, "X1116 毗尼日用切要香乳記")
        for f in self.files:
            with open(os.path.join(self.tmp, f), encoding="utf-8") as fh:
                mine = fh.read()
            with open(os.path.join(base, f), encoding="utf-8") as fh:
                official = fh.read()
            mine_body = _body(mine)
            off_body = _body(official)
            self.assertEqual(mine_body, off_body, f"body differs from official for {f}")


class TestRenderYP0019(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = os.path.join(CBETA, "YP0019 毘尼日用切要講記")
        xml = os.path.join(base, "YP0019.xml")
        if not os.path.isfile(xml):
            # 官方材料化后输入名为 `YP13n0019.xml`；兼容旧短名
            hits = (sorted(glob.glob(os.path.join(base, "YP*n0019.xml")))
                    or sorted(glob.glob(os.path.join(base, "YP*0019.xml"))))
            if hits:
                xml = hits[0]
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()
        # inline 括号 halfwidth 对齐 CBETA 官方（官方 html 用半角括号）
        cls.files = HtmlRenderer(inline_brackets="halfwidth").render_work(cls.work, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_files(self):
        self.assertEqual(self.files, ["YP0019_001.html", "YP0019_002.html"])

    def test_matches_official(self):
        base = os.path.join(CBETA, "YP0019 毘尼日用切要講記")
        for f in ("YP0019_001.html", "YP0019_002.html"):
            off = os.path.join(base, f)
            if not os.path.isfile(off):
                off = os.path.join(base, "html", f)  # 新基线布局：{work}/html/
            if not os.path.isfile(off):
                self.skipTest(f"官方基线缺失：{f}（外部数据已重材料化）")
            with open(os.path.join(self.tmp, f), encoding="utf-8") as fh:
                mine = fh.read()
            with open(off, encoding="utf-8") as fh:
                official = fh.read()
            mine_body = _body(mine)
            off_body = _body(official)
            self.assertEqual(mine_body, off_body, f"body differs from official for {f}")


class TestStripHeadNoX1116(unittest.TestCase):
    """X60n1116 真例：head 行首 `No. 1116-B` 开剥离、余部去空格（默认保留）。"""

    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "X1116 毗尼日用切要香乳記", "X60n1116.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_default_kept(self):
        files = HtmlRenderer().render_work(self.work, self.tmp)
        text = "".join(open(os.path.join(self.tmp, f), encoding="utf-8").read()
                       for f in files)
        self.assertIn("No. 1116-B", text)

    def test_stripped(self):
        sub = os.path.join(self.tmp, "strip")
        files = HtmlRenderer(strip_head_no=True).render_work(self.work, sub)
        text = "".join(open(os.path.join(sub, f), encoding="utf-8").read()
                       for f in files)
        self.assertNotIn("No. 1116-B", text)
        self.assertIn("序", text)


class TestStripDocNumber(unittest.TestCase):
    """docNumber 编号行（如 No. 349 [No. 310(42)]）：strip_head_no 开启时四文本格式省略。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="",
                    metadata={"docNumber": "No. 349 [No. 310(42)]"},
                    body=[E(tag="docNumber",
                            children=[Text(text="No. 349 [No. 310(42)]")])],
                    notes_by_n={}, apps=[], simplified=False)

    def _html(self, flag):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        files = HtmlRenderer(strip_head_no=flag).render_work(self._work(), d)
        return "".join(open(os.path.join(d, f), encoding="utf-8").read()
                       for f in files)

    def test_html_default_kept(self):
        self.assertIn("No. 349", self._html(False))

    def test_html_stripped(self):
        self.assertNotIn("No. 349", self._html(True))

    def test_md_txt_stripped(self):
        from pycbeta.render_txt import TxtRenderer
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        md = open(MdRenderer(strip_head_no=True).render_work(
            self._work(), d, filename="a.md"), encoding="utf-8").read()
        txt = open(TxtRenderer(strip_head_no=True).render_work(
            self._work(), d, filename="a.txt"), encoding="utf-8").read()
        self.assertNotIn("No. 349", md)
        self.assertNotIn("No. 349", txt)


class TestUnclear(unittest.TestCase):
    """<unclear>（文字无法辨析）渲染为标准虚缺符号 □（U+25A1），四格式一致。"""

    def test_html(self):
        self.assertEqual(HtmlRenderer()._render_misc(E(tag="unclear")), "□")

    def test_docx(self):
        out = DocxRenderer()._render_e(E(tag="unclear"))
        self.assertIn("□", out)
        self.assertIn("<w:t", out)

    def test_md(self):
        self.assertEqual(MdRenderer()._render_e(E(tag="unclear")), "□")

    def test_verify_normalize_unifies(self):
        # 官方基线用 ▆，本管线用 □：归一后两侧一致
        self.assertEqual(normalize("▆□▆"), "□□□")
        self.assertIn("□", normalize("傾向傾向▆▆演培"))


class TestSgParens(unittest.TestCase):
    """<cb:sg> 梵呗注音：html/epub/pdf(html2pdf) 输出官方半角括号 (音…)。"""

    def test_sg(self):
        e = E(tag="sg", attrs={}, children=[Text(text="音")])
        self.assertEqual(HtmlRenderer()._render_e(e), "(音)")

    def test_yin_zi_sg(self):
        e = E(tag="yin", attrs={}, children=[
            E(tag="zi", attrs={}, children=[Text(text="㘕")]),
            E(tag="sg", attrs={}, children=[Text(text="音")])])
        self.assertEqual(HtmlRenderer()._render_e(e), "㘕(音)")


class TestNoteInlineSemantics(unittest.TestCase):
    """正文夹注（place=inline）与校注内联 tag/括号/开关分离。"""

    def _inline_note(self, text="夾注"):
        return Note(tag="note", attrs={}, n="", ntype="", place="inline",
                    children=[Text(text=text)])

    def _ref(self):
        note = Note(tag="note", attrs={}, n="n1", ntype="mod", place="foot",
                    children=[Text(text="校注")])
        return NoteRef(n="n1", notes=[note])

    def test_html_brackets_independent(self):
        r = HtmlRenderer(notes="inline", inline_brackets="halfwidth",
                         note_inline_brackets="fullwidth")
        r._app_by_n = {}
        self.assertIn("（校注）", r._render_noteref(self._ref()))
        self.assertIn("(夾注)", r._render_note(self._inline_note()))

    def test_html_show_notes_off_keeps_inline(self):
        r = HtmlRenderer(show_notes=False)
        self.assertIn("夾注", r._render_note(self._inline_note()))
        self.assertEqual(r._render_noteref(self._ref()), "")

    def test_docx_brackets_independent(self):
        r = DocxRenderer(inline_brackets="halfwidth", note_inline_brackets="fullwidth")
        self.assertIn("（", r._render_inline_mode("校注"))
        self.assertNotIn("(", r._render_inline_mode("校注"))
        self.assertIn("(", r._render_inline_note(self._inline_note()))

    def test_docx_show_notes_off_keeps_inline(self):
        r = DocxRenderer(show_notes=False)
        self.assertIn("夾注", r._render_inline_note(self._inline_note()))

    def test_md_brackets_independent(self):
        r = MdRenderer(notes="inline", inline_brackets="halfwidth",
                       note_inline_brackets="fullwidth")
        self.assertIn("（校注）", r._render_noteref(self._ref()))
        self.assertIn("(夾注)", r._render_inline_note(self._inline_note()))

    def test_square_bracket_note_inline(self):
        r = HtmlRenderer(notes="inline", note_inline_brackets="corner")
        r._app_by_n = {}
        self.assertIn("〔校注〕", r._render_noteref(self._ref()))
        self.assertIn("[", DocxRenderer(note_inline_brackets="square")
                      ._render_inline_mode("校注"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
