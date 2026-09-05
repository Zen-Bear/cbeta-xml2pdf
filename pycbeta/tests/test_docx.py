import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.model import App, E, Text
from pycbeta.render_docx import DocxRenderer, split_sections

CBETA = r"E:\dev\cbeta\test"
TESTDATA = r"E:\dev\cbeta\test"


def _ops_text(ops):
    """收集 ops（含 open/close/div 标记）中全部 Text 文本，用于断言节归属。"""
    out = []

    def walk(items):
        for it in items:
            n = it[1] if isinstance(it, tuple) else it
            if n is None:
                continue
            if isinstance(n, Text):
                out.append(n.text)
            elif isinstance(n, App):
                if n.lem is not None:
                    walk([n.lem])
                walk(n.rdgs)
            elif isinstance(n, E):
                walk(n.children)

    walk([o[1] for o in ops])
    return "".join(out)


class TestDocxPagination(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _render(self, xml, cfg):
        work = P5Parser().parse(xml)
        fn = DocxRenderer(pagination=cfg).render_work(work, self.tmp, "pg.docx")
        z = zipfile.ZipFile(fn)
        doc = z.read("word/document.xml").decode("utf-8")
        z.close()
        return doc, work

    def test_single_volume_no_extra_sections(self):
        # T0349 单卷：无 mulu level1，首卷不分页 → 正文节 + tei 节
        doc, _ = self._render(os.path.join(TESTDATA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml"),
                              {"enabled": True, "juan": True, "mulu_level1": True})
        self.assertEqual(doc.count("<w:sectPr"), 2)

    def test_juan_first_title_page(self):
        # juan_first=true → 书名独占一页：空标题节 + 正文节 + tei 节
        doc, _ = self._render(os.path.join(TESTDATA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml"),
                              {"enabled": True, "juan": True, "juan_first": True})
        self.assertEqual(doc.count("<w:sectPr"), 3)

    def test_duplex_odd_page(self):
        # duplex → 每个分页单元 oddPage 分节；T0625 4卷 → 4 个 oddPage
        doc, _ = self._render(os.path.join(TESTDATA, "T0625 大樹緊那羅王所問經", "T15n0625.xml"),
                              {"enabled": True, "juan": True, "duplex": True})
        self.assertEqual(doc.count("<w:sectPr"), 5)          # 4 卷 + tei
        self.assertEqual(doc.count('<w:type w:val="oddPage"/>'), 4)

    def test_mulu_level1_sections(self):
        # T0672：序 + 品 level=1 各分节；卷书签仍每卷一个
        doc, _ = self._render(os.path.join(TESTDATA, "T0672 大乘入楞伽經", "T16n0672.xml"),
                              {"enabled": True, "juan": True, "mulu_level1": True})
        self.assertGreater(doc.count("<w:sectPr"), 10)
        for n in ("卷1", "卷2", "卷7"):
            self.assertIn(f'w:name="{n}"', doc)

    def test_split_sections_first_unit_no_split(self):
        # 首个分页单元不切：X1116 序A 与 juan 1 同节（含标题页前置内容）
        work = P5Parser().parse(os.path.join(TESTDATA, "X1116 毗尼日用切要香乳記", "X60n1116.xml"))
        secs = split_sections(work.body, {"juan": True, "mulu_level1": True})
        self.assertGreater(len(secs), 3)                     # 序A/B/C + 凡例… 分节
        self.assertEqual(secs[0][0], 1)                      # 首节属于卷 1

    def test_first_mulu_after_title_no_split(self):
        # 首个序紧跟书名题署块时不切（docNumber/title/byline 不计为可见内容，与 juan_first 无关）；
        # 第二个序起照常切分
        work = P5Parser().parse(os.path.join(TESTDATA, "T0670 楞伽阿跋多羅寶經", "T16n0670.xml"))
        secs = split_sections(work.body, {"juan": True, "mulu_level1": True})
        self.assertEqual(len(secs), 6)                       # 原 7 节：题署块+蔣之奇序合并为首节
        sec0 = _ops_text(secs[0][1])
        self.assertIn("No. 670", sec0)                       # 题署块在首节
        self.assertIn("蔣之奇序", sec0)                      # 首个序与标题页同节
        self.assertIn("蘇軾序", _ops_text(secs[1][1]))       # 第二个序独立成节

    def test_juan_head_mulu_same_section(self):
        # 卷头 juan E（含 jhead/书名/卷次）不计为可见内容：其后紧跟的首个品 mulu 不切分
        # （T1672 卷四/卷六：孤儿卷头并入品节，17 节→15 节；与 juan_first 无关）
        work = P5Parser().parse(os.path.join(TESTDATA, "T0672 大乘入楞伽經", "T16n0672.xml"))
        secs = split_sections(work.body, {"juan": True, "mulu_level1": True})
        self.assertEqual(len(secs), 15)
        # 含“卷第六”卷头 E 的节，同节必含一级品 mulu（旧行为会将其切走）
        found = False
        for _, ops in secs:
            nodes = [n for _, n in ops]
            has_juan6 = any(isinstance(n, E) and n.tag == "juan"
                            and "卷第六" in _ops_text([(None, n)]) for n in nodes)
            has_pin_mulu = any(isinstance(n, E) and n.tag == "mulu"
                               and n.attrs.get("level") == "1"
                               and n.attrs.get("type") == "品" for n in nodes)
            if has_juan6 and has_pin_mulu:
                found = True
        self.assertTrue(found, "卷六卷头与品 mulu 应在同一节")

    def test_juan_break_pin_same_section(self):
        # 卷头 juan（fun=open）为断点：卷头开启新节，其后紧跟的首个品 mulu 不切分
        # （T0670：卷头/译者/一切佛語心品同节；与 milestone/juan_first 正交）
        work = P5Parser().parse(os.path.join(TESTDATA, "T0670 楞伽阿跋多羅寶經", "T16n0670.xml"))
        secs = split_sections(work.body, {"juan": True, "mulu_level1": True})
        self.assertEqual(len(secs), 6)
        # 含卷头 juan E 的节，同节必含一级品 mulu（旧行为品名被切到下一节）
        found = False
        for _, ops in secs:
            nodes = [n for _, n in ops]
            has_juan = any(isinstance(n, E) and n.tag == "juan"
                           and n.attrs.get("fun") == "open" for n in nodes)
            has_pin_mulu = any(isinstance(n, E) and n.tag == "mulu"
                               and n.attrs.get("level") == "1"
                               and n.attrs.get("type") == "品" for n in nodes)
            if has_juan and has_pin_mulu:
                found = True
        self.assertTrue(found, "卷头与品 mulu 应在同一节")

    def test_juan_byline_mulu_chain_no_split(self):
        # 题署链 docNumber→卷头→译者 byline→品名：节内零计数节点，首个品 mulu 不切分
        # （byline 不看 cb:type，Translator/author/other 一视同仁）
        def E2(tag, kids=(), attrs=None):
            return E(tag=tag, attrs=dict(attrs or {}), children=list(kids))
        body = [
            E2("docNumber", [Text(text="No. 999")]),
            E2("juan", [E2("jhead", [Text(text="某經卷第一")])],
               {"n": "001", "fun": "open"}),
            E2("byline", [Text(text="譯者某甲")], {"cb:type": "Translator"}),
            E2("div", [E2("mulu", [Text(text="某品")], {"level": "1", "type": "品"}),
                       E2("head", [Text(text="品正文")])], {"type": "pin"}),
        ]
        secs = split_sections(body, {"juan": True, "mulu_level1": True})
        self.assertEqual(len(secs), 1)
        alltext = "".join(_ops_text(ops) for _, ops in secs)
        for s in ("No. 999", "卷第一", "譯者某甲", "某品"):
            self.assertIn(s, alltext)

    def test_section_breaks_inside_paragraph_props(self):
        # 节间 sectPr 必须装进段落 pPr：裸挂 w:body 会被 Word 忽略
        # （曾导致切分正确但第二个序不换页；仅文末最后一个允许裸位置）
        doc, _ = self._render(os.path.join(TESTDATA, "T0670 楞伽阿跋多羅寶經", "T16n0670.xml"),
                              {"enabled": True, "juan": True, "mulu_level1": True})
        import xml.etree.ElementTree as ET
        ET.fromstring(doc.encode("utf-8"))               # 输出必须良构
        total = doc.count("<w:sectPr")
        self.assertGreater(total, 1)
        stripped = re.sub(r"<w:pPr>.*?</w:pPr>", "", doc, flags=re.S)
        self.assertEqual(stripped.count("<w:sectPr"), 1)     # 仅剩文末合法裸 sectPr

    def test_second_xu_breaks_before_sushi(self):
        # T0670 第二个序（蘇軾序）节前必须有 pPr 内节分隔
        doc, _ = self._render(os.path.join(TESTDATA, "T0670 楞伽阿跋多羅寶經", "T16n0670.xml"),
                              {"enabled": True, "juan": True, "mulu_level1": True})
        i = doc.find("蘇軾序")
        self.assertGreater(i, 0)
        head = doc[max(0, i - 1500):i]
        self.assertRegex(head, r"</w:sectPr></w:pPr>")


class TestDocx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()
        cls.doc = DocxRenderer().render_work(cls.work, cls.tmp)
        cls.z = zipfile.ZipFile(cls.doc)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_parts(self):
        names = self.z.namelist()
        for p in ("[Content_Types].xml", "word/document.xml", "word/footnotes.xml",
                  "word/styles.xml", "word/_rels/document.xml.rels"):
            self.assertIn(p, names)

    def test_footnotes(self):
        doc = self.z.read("word/document.xml").decode("utf-8")
        fn = self.z.read("word/footnotes.xml").decode("utf-8")
        refs = doc.count("footnoteReference")
        entries = fn.count("<w:footnote w:id=")  # real footnotes (separators use w:type first)
        self.assertEqual(refs, entries)
        self.assertEqual(refs, 53)
        self.assertIn("月氏國", fn)

    def test_body(self):
        doc = self.z.read("word/document.xml").decode("utf-8")
        self.assertIn("彌勒", doc)


class TestDivXuSpacing(unittest.TestCase):
    """div 祖先的段落属性必须透过命名样式快车道：div-xu 的 margin 进内联 w:spacing。"""

    def _renderer(self):
        from pycbeta.theme import Theme
        th = Theme(raw_css="div.div-xu { margin-top: 1em; margin-bottom: 2em; }")
        return DocxRenderer(theme=th, bookmarks=False)

    def test_xu_paragraph_gets_spacing(self):
        r = self._renderer()
        out = r._para(r._run("x", "p"), "div-xu", "p", count=False)
        self.assertIn('w:before="240"', out)
        self.assertIn('w:after="480"', out)

    def test_plain_paragraph_untouched(self):
        r = self._renderer()
        out = r._para(r._run("x", "p"), "p", count=False)
        self.assertNotIn("w:before", out)
        self.assertNotIn("w:after", out)

    def test_div_context_merged_for_bare_tags(self):
        # 调用点只传本标签时（如 head/juan/table），div 祖先上下文由 _para 统一并入
        r = self._renderer()
        r._div_stack.append("div-xu")
        try:
            out = r._para(r._run("x", "head"), "head", count=False)
        finally:
            r._div_stack.pop()
        self.assertIn('w:before="240"', out)
        self.assertIn('w:after="480"', out)


class TestDocxOptions(unittest.TestCase):
    """presets.json output 段的 grayscale / page_border 参数。"""

    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_grayscale_strips_all_colors(self):
        fn = DocxRenderer(grayscale=True).render_work(self.work, self.tmp, "gray.docx")
        z = zipfile.ZipFile(fn)
        for part in ("word/document.xml", "word/styles.xml", "word/footnotes.xml"):
            xml = z.read(part).decode("utf-8")
            self.assertNotIn("<w:color", xml, part)
        # 对照组：默认输出带颜色（head/juan 蓝色等）
        fn2 = DocxRenderer().render_work(self.work, self.tmp, "color.docx")
        z2 = zipfile.ZipFile(fn2)
        self.assertIn("<w:color", z2.read("word/document.xml").decode("utf-8"))

    def test_page_border(self):
        fn = DocxRenderer(page_border=True).render_work(self.work, self.tmp, "border.docx")
        z = zipfile.ZipFile(fn)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertIn('<w:pgBorders w:offsetFrom="page">', doc)
        for side in ("top", "left", "bottom", "right"):
            self.assertIn(f'<w:{side} w:val="single" w:sz="6" w:space="24" w:color="000000"/>', doc)
        # 对照组：默认无边框
        fn2 = DocxRenderer().render_work(self.work, self.tmp, "noborder.docx")
        z2 = zipfile.ZipFile(fn2)
        self.assertNotIn("<w:pgBorders", z2.read("word/document.xml").decode("utf-8"))


class TestDocxBookmarksSplit(unittest.TestCase):
    """目录书签（默认卷号）与按卷输出。"""

    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0672 大乘入楞伽經", "T16n0672.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_bookmarks_by_juan(self):
        fn = DocxRenderer().render_work(self.work, self.tmp, "bm.docx")
        z = zipfile.ZipFile(fn)
        doc = z.read("word/document.xml").decode("utf-8")
        # 7 个卷书签（milestone）+ 14 个品名 mulu 隐形书签
        self.assertEqual(doc.count("<w:bookmarkStart"), 21)
        for n in ("卷1", "卷2", "卷7"):
            self.assertIn(f'w:name="{n}"', doc)
        styles = z.read("word/styles.xml").decode("utf-8")
        self.assertIn("outlineLvl", styles)  # Word 导航窗格可见卷目录

    def test_bookmarks_off(self):
        fn = DocxRenderer(bookmarks=False).render_work(self.work, self.tmp, "nobm.docx")
        z = zipfile.ZipFile(fn)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertNotIn("<w:bookmarkStart", doc)
        styles = z.read("word/styles.xml").decode("utf-8")
        self.assertNotIn("outlineLvl", styles)

    def test_split(self):
        files = DocxRenderer(split=True).render_work(self.work, self.tmp, "sp.docx")
        self.assertEqual(len(files), 7)
        for f in files:
            self.assertTrue(os.path.isfile(f))
        # 每卷文件含对应卷标题
        z = zipfile.ZipFile(files[1])
        self.assertIn("卷第二", z.read("word/document.xml").decode("utf-8"))


class TestGaijiFonts(unittest.TestCase):
    """缺字字体链（output.docx.gaijiFonts）：>0xFFFF 缺字取本机已装首个，懒解析。"""

    def test_default_keeps_supplement(self):
        import unittest.mock as mock
        with mock.patch("pycbeta.fonts.locator") as ml:
            ml.return_value.path.return_value = None
            r = DocxRenderer()
            self.assertEqual(r._gaiji_font(), "CBETA Supplement")
            # 缓存：第二次不再扫
            r._gaiji_font()
            self.assertEqual(ml.return_value.path.call_count, 1)

    def test_chain_picks_installed(self):
        import unittest.mock as mock
        with mock.patch("pycbeta.fonts.locator") as ml:
            ml.return_value.path.side_effect = lambda n: "/x.ttf" if n == "SimSunExtB" else None
            r = DocxRenderer(gaiji_fonts={"zh-Hans": ["NoSuchFontXYZ", "SimSunExtB"]},
                             gaiji_lang="zh-Hans")
            self.assertEqual(r._gaiji_font(), "SimSunExtB")

    def test_lang_selects_chain(self):
        import unittest.mock as mock
        with mock.patch("pycbeta.fonts.locator") as ml:
            ml.return_value.path.return_value = "/x.ttf"
            r = DocxRenderer(gaiji_fonts={"zh-Hant": ["A"], "zh-Hans": ["B"]},
                             gaiji_lang="zh-Hans")
            self.assertEqual(r._gaiji_font(), "B")
            ml.return_value.path.assert_called_with("B")

    def test_render_uses_chain_font(self):
        import unittest.mock as mock
        from pycbeta.model import Gaiji
        with mock.patch("pycbeta.fonts.locator") as ml:
            ml.return_value.path.side_effect = lambda n: "/x.ttf" if n == "TestChainFont" else None
            r = DocxRenderer(gaiji_fonts={"zh-Hans": ["TestChainFont"]},
                             gaiji_lang="zh-Hans")
            out = r._render_node(Gaiji(code="CB99999", char=chr(0x30000)))
            self.assertIn('w:eastAsia="TestChainFont"', out)
            # 显式字体唯一（主题字体被替换，不重复）
            self.assertEqual(out.count("<w:rFonts"), 1)

    def test_builtin_config_chains(self):
        from pycbeta.theme import load_presets
        import os as _os
        cfg = load_presets(_os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "config.json")).get("output", {}).get("docx", {}).get("gaijiFonts")
        self.assertEqual(cfg["zh-Hant"], ["CBETA Supplement"])
        self.assertEqual(cfg["zh-Hans"], ["SimSunExtB", "CBETA Supplement"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
