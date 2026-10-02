import glob
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.model import App, E, Note, NoteRef, Text, Work
from pycbeta.render_docx import DocxRenderer
from pycbeta.render_html import HtmlRenderer
from pycbeta.render_md import MdRenderer
from pycbeta.verify import normalize

from pycbeta.tests._data import DATA_ROOT as CBETA
from pycbeta.tests._data import requires_data


def _body(html):
    """剥 <style>/<script>、官方 head 边框 span、style 属性、标签间空白后比较正文
    （官方 CSS/模板装饰差异不计，如校注说明注释、<span class="border">、lg 内联样式、缩进换行）。"""
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    html = re.sub(r"<html[^>]*>", "<html>", html)  # lang 等文档属性不计入正文比对
    html = re.sub(r'<span class="border">|</span>', "", html)
    html = re.sub(r'\sstyle="[^"]*"', "", html)
    html = re.sub(r">\s+<", "><", html)
    return html.split("<div id='cbeta-copyright'>")[0]


@requires_data
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
        # 默认名与其他格式统一 `{id 书名}`（多卷加 `_NNN`，书名跟 title_t2s）
        self.assertEqual(self.files, ["X1116 毗尼日用切要香乳记_001.html",
                                      "X1116 毗尼日用切要香乳记_002.html"])

    def test_matches_official(self):
        base = os.path.join(CBETA, "X1116 毗尼日用切要香乳記")
        official = ["X1116_001.html", "X1116_002.html"]
        self.assertEqual(len(self.files), len(official))
        for f, of in zip(self.files, official):
            with open(os.path.join(self.tmp, f), encoding="utf-8") as fh:
                mine = fh.read()
            with open(os.path.join(base, of), encoding="utf-8") as fh:
                official = fh.read()
            mine_body = _body(mine)
            off_body = _body(official)
            self.assertEqual(mine_body, off_body, f"body differs from official for {f}")


@requires_data
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
        self.assertEqual(self.files, ["YP0019 毘尼日用切要讲记_001.html",
                                      "YP0019 毘尼日用切要讲记_002.html"])

    def test_matches_official(self):
        base = os.path.join(CBETA, "YP0019 毘尼日用切要講記")
        official = ["YP0019_001.html", "YP0019_002.html"]
        self.assertEqual(len(self.files), len(official))
        for f, of in zip(self.files, official):
            off = os.path.join(base, of)
            if not os.path.isfile(off):
                off = os.path.join(base, "html", of)  # 新基线布局：{work}/html/
            if not os.path.isfile(off):
                self.skipTest(f"官方基线缺失：{of}（外部数据已重材料化）")
            with open(os.path.join(self.tmp, f), encoding="utf-8") as fh:
                mine = fh.read()
            with open(off, encoding="utf-8") as fh:
                official = fh.read()
            mine_body = _body(mine)
            off_body = _body(official)
            self.assertEqual(mine_body, off_body, f"body differs from official for {f}")


class TestHtmlSingleNoSuffix(unittest.TestCase):
    """单卷 html 默认名与其他格式同形（无 `_NNN` 后缀）；多卷加后缀。"""

    def test_single(self):
        from pycbeta.model import E, Text, Work
        w = Work(id="T0349", source_file="",
                 metadata={"title": "彌勒菩薩所問本願經"}, body=[
                     E(tag="p", attrs={}, children=[Text(text="文")])],
                 notes_by_n={}, apps=[], simplified=False)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        files = HtmlRenderer().render_work(w, d)
        self.assertEqual(files, ["T0349 弥勒菩萨所问本愿经.html"])

    def test_title_t2s_off_keeps_hant(self):
        from pycbeta.model import E, Text, Work
        w = Work(id="T0349", source_file="",
                 metadata={"title": "彌勒菩薩所問本願經"}, body=[
                     E(tag="p", attrs={}, children=[Text(text="文")])],
                 notes_by_n={}, apps=[], simplified=False)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        files = HtmlRenderer(title_t2s=False).render_work(w, d)
        self.assertEqual(files, ["T0349 彌勒菩薩所問本願經.html"])


@requires_data
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


class TestStarAppHtml(unittest.TestCase):
    """星号位校勘（有 corresp 的 App）：html 正文官方无标记，
    只留空位标记供 `_join_epub_ours` 按位复注块（文本抽取为空）。"""

    def _app(self, atype=None, corresp="#n1"):
        attrs = {}
        if corresp is not None:
            attrs["corresp"] = corresp
        return App(tag="app", attrs=attrs, children=[], key="beg_1",
                   atype=atype, lem=None, rdgs=[])

    def _work(self):
        note = Note(tag="note", attrs={}, n="n1", ntype="mod", place="foot",
                    children=[Text(text="校注")])
        return Work(id="T", source_file="", metadata={}, body=[],
                    notes_by_n={"n1": [note]}, apps=[], simplified=False)

    def test_star_app_emits_empty_span(self):
        r = HtmlRenderer()
        r._work = self._work()
        out = r._render_star_app(self._app())
        self.assertIn("note-star", out)
        self.assertIn("data-n='n1'", out)
        from pycbeta.verify import extract_text
        import tempfile, os
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "a.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"<html><body><p>甲{out}乙</p></body></html>")
            self.assertEqual(extract_text(p).replace("\n", ""), "甲乙")
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_regular_app_and_removed_silent(self):
        r = HtmlRenderer()
        r._work = self._work()
        self.assertEqual(r._render_star_app(self._app(corresp=None)), "")
        self.assertEqual(
            r._render_star_app(self._app(atype="star_removed")), "")
        r2 = HtmlRenderer(show_notes=False)
        r2._work = self._work()
        self.assertEqual(r2._render_star_app(self._app()), "")

    def test_inline_mode_renders_content(self):
        r = HtmlRenderer(notes="inline", inline_brackets="halfwidth")
        r._work = self._work()
        self.assertIn("(校注)", r._render_star_app(self._app()))


class TestSiddhamBlockTt(unittest.TestCase):
    """块级对照表（无 place）：悉昙消音但注记锚点保留（X1077 陀罗尼类）；
    行内对照表与注内容不受影响。"""

    def _tt(self, place=None):
        from pycbeta.model import Gaiji, NoteRef
        attrs = {}
        if place is not None:
            attrs["place"] = place
        note = Note(tag="note", attrs={}, n="n1", ntype="add", place="foot",
                    children=[Gaiji(code="RJ-CCEB", char="X")])
        sa = E(tag="t", attrs={"xml:lang": "sa-x-rj"},
               children=[NoteRef(n="n1", notes=[note]),
                         Gaiji(code="RJ-CCEB", char="X")])
        zh = E(tag="t", attrs={"xml:lang": "zh-Hant"},
               children=[Text(text="南")])
        return E(tag="tt", attrs=attrs, children=[zh, sa]), note

    def _renderer(self):
        r = HtmlRenderer()
        r._work = Work(id="T", source_file="", metadata={
            "charDecl": {"RJ-CCEB": {"roman": "raṃ"}}}, body=[],
            notes_by_n={}, apps=[], simplified=False)
        r._app_by_n = {}
        r._ann_seen = set()
        return r

    def test_block_tt_drops_siddham_keeps_ref(self):
        tt, _ = self._tt()
        out = self._renderer()._render_tt(tt)
        self.assertIn("南", out)
        self.assertIn("[A1]", out)
        self.assertNotIn("ranja", out)

    def test_inline_tt_keeps_ranja(self):
        tt, _ = self._tt(place="inline")
        out = self._renderer()._render_tt(tt)
        self.assertIn("ranja", out)
        self.assertIn("transliteration", out)

    def test_unresolvable_pua_empty_span(self):
        # 无解 PUA（gaiji_db/charDecl 均无映射）：空 span，文本抽取为空
        from pycbeta.model import Gaiji
        r = self._renderer()
        out = r._render_gaiji(
            Gaiji(code="RJ-TEST-NONE", char=chr(0x10E046)))
        self.assertIn("data-gid", out)
        self.assertNotIn(chr(0x10E046), out)
        self.assertTrue(out.endswith("</span>"))


class TestSiddhamTextFlag(unittest.TestCase):
    """output.siddham_text（默认关）：有读音悉昙按 docx 形输出字形(读音)。"""

    def _work(self):
        from pycbeta.model import Gaiji
        return Work(id="T", source_file="", metadata={
            "charDecl": {"RJ-CCEB": {"roman": "raṃ", "rjchar": "誆"}}},
            body=[Gaiji(code="RJ-CCEB", char="X")],
            notes_by_n={}, apps=[], simplified=False)

    def _plain(self, html):
        return re.sub(r"<[^>]+>", "", html)

    def test_html_default_empty(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        files = HtmlRenderer().render_work(self._work(), d)
        html = "".join(open(os.path.join(d, f), encoding="utf-8").read()
                       for f in files)
        self.assertIn("ranja", html)
        self.assertNotIn("raṃ", self._plain(html))

    def test_html_flag_text(self):
        r = HtmlRenderer(siddham_text=True)
        r._work = self._work()
        from pycbeta.model import Gaiji
        out = r._render_gaiji(Gaiji(code="RJ-CCEB", char="X"))
        self.assertNotIn("ranja", out)
        self.assertIn("誆(raṃ)", self._plain(out))

    def test_txt_md_flag(self):
        import tempfile
        from pycbeta.render_txt import TxtRenderer
        from pycbeta.render_md import MdRenderer
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        t = open(TxtRenderer().render_work(self._work(), d, "a.txt"),
                 encoding="utf-8").read()
        self.assertIn("raṃ", t)
        self.assertNotIn("誆(raṃ)", t)
        t2 = open(TxtRenderer(siddham_text=True).render_work(
            self._work(), d, "b.txt"), encoding="utf-8").read()
        self.assertIn("誆(raṃ)", t2)
        m = open(MdRenderer(siddham_text=True).render_work(
            self._work(), d, "c.md"), encoding="utf-8").read()
        self.assertIn("誆(raṃ)", m)


class TestAddFootnoteIndent(unittest.TestCase):
    """新增校注（add）注块：html 成品保留官方两格缩进（X1116 与官方逐字节一致）；
    txt 重组形（`_join_epub_ours`）行首无缩进，与常规注块同列。"""

    def test_add_footnote_keeps_official_indent(self):
        note = Note(tag="note", attrs={}, n="n9", ntype="add", place="foot",
                    children=[Text(text="新增")])
        r = HtmlRenderer()
        r._app_by_n = {}
        r._work = Work(id="T", source_file="", metadata={}, body=[],
                       notes_by_n={"n9": [note]}, apps=[], simplified=False)
        out = r._render_noteref(NoteRef(n="n9", notes=[note]))
        self.assertIn("[A1]", out)
        self.assertEqual(len(r._back_cb), 1)
        self.assertIn("\n  [<a", r._back_cb[0])

    def test_join_strips_footnote_indent(self):
        from pycbeta.verify import _foot_block_text
        out = _foot_block_text("<div class='footnote' id='cb_note_1'>\n"
                               "  [A1] 新增\n</div>")
        self.assertTrue(out.startswith("[A1] 新增"))
        self.assertNotIn("  [A1]", out)


class TestMuluBreakMarker(unittest.TestCase):
    """html/epub 断页标记：level-1 非「卷」mulu → `<div class="mulu-break" data-title>`；
    默认关（html/pdf 产品与官方同形），epub 开。"""

    def _work(self):
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=[Text("前文")]),
                          E(tag="mulu", attrs={"level": "1", "type": "其他"},
                            children=[Text("附錄一")]),
                          E(tag="p", attrs={}, children=[Text("後文")]),
                          E(tag="mulu", attrs={"level": "1", "type": "卷"},
                            children=[Text("不切")])],
                    notes_by_n={}, apps=[], simplified=False)

    def _render(self, **kw):
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        files = HtmlRenderer(**kw).render_work(self._work(), d)
        return "".join(open(os.path.join(d, f), encoding="utf-8").read()
                       for f in files)

    def test_marker_off_by_default(self):
        self.assertNotIn("mulu-break", self._render())

    def test_marker_on(self):
        blob = self._render(mulu_break=True)
        self.assertIn('<div class="mulu-break" data-title="附錄一"></div>', blob)
        self.assertEqual(blob.count("mulu-break"), 1)  # 「卷」型不标记


class TestPreDedent(unittest.TestCase):
    """预排去缩进：每行行首最多去 N 个空白，不足去尽；开关默认关。"""

    def _work(self):
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={"cb:type": "pre"},
                            children=[Text("　　　　緒　言\n"
                                           "　　　　　第一章　　傳\n"
                                           "　　無縮排行")])],
                    notes_by_n={}, apps=[], simplified=False)

    def _docx_text(self, **kw):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        fn = DocxRenderer(**kw).render_work(self._work(), d, "x.docx")
        import zipfile
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))

    def test_off_by_default(self):
        # 默认关：预排原样保留行首缩进
        self.assertIn("　　　　緒　言", self._docx_text())

    def test_on_strips_four(self):
        out = self._docx_text(pre_dedent=True, pre_dedent_spaces=4)
        self.assertIn("緒　言　第一章", out)   # 4 个全去；5 个去 4 留 1
        self.assertIn("傳無縮排行", out)       # 承接上行；2 个不足去尽
        self.assertNotIn("　　　　緒　言", out)

    def test_helper_edge(self):
        def ded(text):
            return DocxRenderer(pre_dedent=True,
                                pre_dedent_spaces=4)._pre_dedent_text(text)
        self.assertEqual(ded("　　　　abc"), "abc")
        self.assertEqual(ded("   \u3000abc"), "abc")   # 混合空白共 4 个
        self.assertEqual(ded("  ab"), "ab")            # 不足去尽
        self.assertEqual(ded("a  b"), "a  b")          # 行中不动
        self.assertEqual(ded("　　a\n　　　　　b"), "a\n　b")  # 多行各自去

    def test_html_pre_dedent(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        files = HtmlRenderer(pre_dedent=True).render_work(self._work(), d)
        blob = "".join(open(os.path.join(d, f), encoding="utf-8").read()
                       for f in files)
        self.assertIn("緒　言", blob)
        self.assertNotIn("　　　　緒　言", blob)
        self.assertIn("　第一章", blob)        # 5 去 4 留 1

    def test_html_lone_newline_kept_off_line_start(self):
        # 非行首孤立换行保留（X1116 凡例　官方同形）
        w = Work(id="T", source_file="",
                 metadata={"title": "t", "author": ""},
                 body=[E(tag="p", attrs={"cb:type": "pre"},
                         children=[Text("香乳記"), Text("\n"),
                                   Text("宗鏡")])],
                 notes_by_n={}, apps=[], simplified=False)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        files = HtmlRenderer().render_work(w, d)
        blob = "".join(open(os.path.join(d, f), encoding="utf-8").read()
                       for f in files)
        self.assertIn("香乳記\n宗鏡", blob)

    def test_html_pre_blank_tail_dropped(self):
        # pre 内纯换行残留（空元素独占行）丢弃：行间不增多空行
        w = Work(id="T", source_file="",
                 metadata={"title": "t", "author": ""},
                 body=[E(tag="p", attrs={"cb:type": "pre"},
                         children=[Text("一七\n"), Text("\n"),
                                   Text("第三章")])],
                 notes_by_n={}, apps=[], simplified=False)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        files = HtmlRenderer().render_work(w, d)
        blob = "".join(open(os.path.join(d, f), encoding="utf-8").read()
                       for f in files)
        self.assertIn("一七\n第三章", blob)
        self.assertNotIn("\n\n", blob.split("<pre", 1)[1].split("</pre>")[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
