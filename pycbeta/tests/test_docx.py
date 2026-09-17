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

CBETA = r"E:\dev\cbeta\cbeta_ebook"
TESTDATA = r"E:\dev\cbeta\cbeta_ebook"


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

    def test_info_page_fangsong(self):
        # 【經文資訊】尾页：仿宋 + 行距 1（w:line=240）
        doc = self.z.read("word/document.xml").decode("utf-8")
        self.assertIn("經文資訊", doc)
        self.assertIn("仿宋", doc)
        self.assertIn('w:line="240"', doc)


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


class TestPreNoFirstLine(unittest.TestCase):
    """预排不缩进（CSS pre/text-indent:0）：只掐 w:firstLine，段间距/行距跟 p 不变；
    真 <pre> 与 <p cb:type=pre> 同口径（X60n1116 实证）。"""

    def _para_of(self, e):
        r = DocxRenderer(bookmarks=False)
        out = r._render_e(e)
        return out[out.find("<w:pPr>"):out.find("</w:pPr>")]

    def test_cb_type_pre_no_first_line(self):
        ppr = self._para_of(E(tag="p", attrs={"cb:type": "pre"},
                                children=[Text(text="序文")]))
        self.assertNotIn("firstLine", ppr)
        self.assertIn('w:before="120"', ppr)  # 段间距跟 p 不变
        self.assertIn('w:line="336"', ppr)  # 跟随出厂 p=1.4（2026-09-11 定稿）

    def test_true_pre_same(self):
        ppr = self._para_of(E(tag="pre", attrs={},
                                children=[Text(text="序文")]))
        self.assertNotIn("firstLine", ppr)
        self.assertIn('w:before="120"', ppr)

    def test_plain_p_uses_named_style(self):
        r = DocxRenderer(bookmarks=False)
        out = r._render_e(E(tag="p", attrs={}, children=[Text(text="序文")]))
        self.assertIn('w:val="p"', out)  # 正文走 p 命名样式（缩进在 styles.xml）


class TestStripHeadNo(unittest.TestCase):
    """head/jhead 行首 No. 令牌剥离（默认关，开后余部 lstrip）。"""

    def test_head_default_kept(self):
        r = DocxRenderer(bookmarks=False)
        out = r._render_e(E(tag="head", attrs={},
                            children=[Text(text="No. 1116-B"), Text(text=" 序")]))
        self.assertIn("No. 1116-B", out)

    def test_head_stripped(self):
        r = DocxRenderer(bookmarks=False, strip_head_no=True)
        out = r._render_e(E(tag="head", attrs={},
                            children=[Text(text="No. 1116-B"), Text(text=" 序")]))
        self.assertNotIn("No. 1116", out)
        self.assertIn("序", out)


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

    def test_series_para_has_style(self):
        from pycbeta.model import Work, E, Text
        w = Work(id="T", source_file="", metadata={"title": "t", "series": "X經"},
                 body=[E(tag="p", attrs={}, children=[Text("文")])],
                 notes_by_n={}, apps=[])
        fn = DocxRenderer().render_work(w, self.tmp, "series.docx")
        z = zipfile.ZipFile(fn)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertIn('w:val="series-title"', doc)  # 经藏名挂命名样式，预览可标【经藏名】
        styles = z.read("word/styles.xml").decode("utf-8")
        self.assertIn('w:styleId="series-title"', styles)

    def test_def_run_carries_def_style(self):
        from pycbeta.model import Work, E, Text
        from pycbeta.theme import Theme
        css = (":root { --font-def: 新細明體, PMingLiU; }\n"
               "cb:def { font-size: 0.9em; }\n")
        t = Theme.from_css(css)
        w = Work(id="T", source_file="", metadata={"title": "t"},
                 body=[E(tag="div", attrs={"type": "note"},
                         children=[E(tag="def", attrs={},
                                     children=[Text("释义")])])],
                 notes_by_n={}, apps=[])
        fn = DocxRenderer(theme=t).render_work(w, self.tmp, "def.docx")
        z = zipfile.ZipFile(fn)
        s = z.read("word/document.xml").decode("utf-8")
        # def run 带 def 标签：字号 0.9em（12pt×0.9=10.8pt→round 取 22 半磅=11pt）与 def 字体
        self.assertIn('<w:sz w:val="22"/>', s)
        self.assertIn('w:eastAsia="新細明體"', s)

    def test_def_p_has_def_pstyle(self):
        from pycbeta.model import Work, E, Text
        from pycbeta.theme import Theme
        css = (":root { --font-def: 新細明體, PMingLiU; }\n"
               "cb:def { font-size: 0.9em; }\n")
        t = Theme.from_css(css)
        w = Work(id="T", source_file="", metadata={"title": "t"},
                 body=[E(tag="div", attrs={"type": "note"},
                         children=[E(tag="def", attrs={},
                                     children=[E(tag="p", attrs={"style": "margin-left:1em"},
                                                 children=[Text("释义段")])])])],
                 notes_by_n={}, apps=[])
        fn = DocxRenderer(theme=t).render_work(w, self.tmp, "defp.docx")
        z = zipfile.ZipFile(fn)
        s = z.read("word/document.xml").decode("utf-8")
        # def 内 p 挂 pStyle def（预览标【释义】），run 照旧 0.9em（round 取 22），缩进保留
        self.assertIn('w:val="def"', s)
        self.assertIn('<w:sz w:val="22"/>', s)
        self.assertIn("<w:ind", s)

    def test_div_note_p_has_div_note_pstyle(self):
        from pycbeta.model import Work, E, Text
        from pycbeta.theme import Theme
        css = ("p { font-size: 12pt; }\n"
               "div.div-note { font-weight: bold; }\n")
        t = Theme.from_css(css)
        w = Work(id="T", source_file="", metadata={"title": "t"},
                 body=[E(tag="div", attrs={"type": "note"},
                         children=[E(tag="p", attrs={},
                                     children=[Text("注文")])])],
                 notes_by_n={}, apps=[])
        fn = DocxRenderer(theme=t).render_work(w, self.tmp, "divnote.docx")
        z = zipfile.ZipFile(fn)
        s = z.read("word/document.xml").decode("utf-8")
        styles = z.read("word/styles.xml").decode("utf-8")
        # div-note 内 p 挂 pStyle div-note（预览标【字义】）
        self.assertIn('w:val="div-note"', s)
        # 样式自包含 p 布局+粗体（字号 12pt + w:b）
        self.assertIn('w:styleId="div-note"', styles)
        self.assertIn("<w:b/>", styles)

    def test_tag_base_pt_resolves_em(self):
        from pycbeta.theme import Theme
        t = Theme.from_css(":root {}\n.footnote { font-size: 0.75em; }\n")
        r = DocxRenderer(theme=t)
        # _tag_base_pt 是父级语义（绝对值 only，供自身 em 换算，不复利）
        self.assertEqual(r._tag_base_pt(("footnote",)), 12.0)
        self.assertEqual(r._tag_base_pt(("p",)), 12.0)
        # _resolve_tag_pt 由外向内解算（注音锚：脚注 0.75em→9.0，不回落 12）
        self.assertEqual(r._resolve_tag_pt(("footnote",)), 9.0)
        self.assertEqual(r._resolve_tag_pt(("p",)), 12.0)
        self.assertEqual(r._resolve_tag_pt(("nope",)), 12.0)

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
        self.assertEqual(cfg["zh-Hans"], ["SimSun-ExtB", "SimSun-ExtG",
                                          "CBETA Supplement"])


class TestRanjana(unittest.TestCase):
    """RJ 悉昙：charDecl rjchar 显示 + Ranjana 系字体（官方 docx 同款）。

    无 Ranjana 字体时主题字体直显 rjchar（可读非悉昙体）；PUA 私用字不再落盘。
    """

    def _renderer(self, files, chardecl=None):
        import types
        import unittest.mock as mock
        m1 = mock.patch("pycbeta.fonts.locator")
        m2 = mock.patch("pycbeta.fonts.font_cmap")
        ml = m1.start()
        mc = m2.start()
        self.addCleanup(m1.stop)
        self.addCleanup(m2.stop)
        ml.return_value.path.side_effect = files.get
        mc.side_effect = lambda p: {
            "/rj.ttf": frozenset({ord("屇")}),
            "/song.ttf": frozenset({ord("A"), ord("屇")}),
        }.get(p, frozenset())
        r = DocxRenderer()
        r._work = types.SimpleNamespace(
            metadata={"charDecl": chardecl or {}}, simplified=False)
        return r

    def test_resolve_prefers_rjchar(self):
        r = self._renderer({})
        cd = {"RJ-X": {"rjchar": "屇", "pua": "U+10CCBA"}}
        r._work.metadata["charDecl"] = cd
        self.assertEqual(r._resolve_gaiji("RJ-X", "X"), "屇")
        # 非 RJ 码不受影响（走旧链路回 raw）
        self.assertEqual(r._resolve_gaiji("CB-X", "Y"), "Y")

    def test_font_installed_and_covering(self):
        r = self._renderer({"Ranjana": "/rj.ttf", "SimSun": "/song.ttf"})
        self.assertEqual(r._ranjana_font_for("屇"), "Ranjana")

    def test_font_missing_falls_back(self):
        r = self._renderer({"SimSun": "/song.ttf"})
        self.assertIsNone(r._ranjana_font_for("屇"))

    def test_render_rj_run(self):
        from pycbeta.model import Gaiji
        r = self._renderer({"Ranjana": "/rj.ttf", "SimSun": "/song.ttf"})
        r._work.metadata["charDecl"] = {"RJ-X": {"rjchar": "屇"}}
        out = r._render_node(Gaiji(code="RJ-X", char="X"))
        self.assertIn('w:eastAsia="Ranjana"', out)
        self.assertIn("屇", out)
        # 没装 Ranjana：主题字体 + rjchar 可读文本（非 tofu）
        r2 = self._renderer({"SimSun": "/song.ttf"})
        r2._work.metadata["charDecl"] = {"RJ-X": {"rjchar": "屇"}}
        out2 = r2._render_node(Gaiji(code="RJ-X", char="X"))
        self.assertNotIn("Ranjana", out2)
        self.assertIn("屇", out2)


class TestRenderFallback(unittest.TestCase):
    """render-time 按字回退：主字体缺字形的字拆出用回退字体，保证无 tofu。

    如 標楷體缺 U+43F6 → 该字 SimSun run，其余保留原字体（2026-09-06 用户报 tofu）。
    """

    def _renderer(self, files):
        import unittest.mock as mock
        m1 = mock.patch("pycbeta.fonts.locator")
        m2 = mock.patch("pycbeta.fonts.font_cmap")
        ml = m1.start()
        mc = m2.start()
        self.addCleanup(m1.stop)
        self.addCleanup(m2.stop)
        ml.return_value.path.side_effect = files.get
        mc.side_effect = lambda p: {
            "/kai.ttf": frozenset({0x41, 0x42}),
            "/song.ttf": frozenset({0x41, 0x42, 0x43F6}),
            "/pm.ttf": frozenset({0x41}),
        }.get(p, frozenset())
        return DocxRenderer()

    def test_all_covered_single_run(self):
        r = self._renderer({"Kai": "/kai.ttf", "SimSun": "/song.ttf"})
        out = r._run("AB", "p", fonts="Kai")
        self.assertEqual(out.count("<w:r>"), 1)
        self.assertIn('w:eastAsia="Kai"', out)

    def test_missing_char_splits_fallback(self):
        r = self._renderer({"Kai": "/kai.ttf", "SimSun": "/song.ttf"})
        out = r._run("A䏶B", "p", fonts="Kai")
        self.assertEqual(out.count("<w:r>"), 3)
        self.assertIn('w:eastAsia="Kai"', out)
        self.assertIn('w:eastAsia="SimSun"', out)
        # 回退 run 只换 eastAsia，ascii/hAnsi 不动
        m = [l for l in out.split("<w:r>") if "䏶" in l][0]
        self.assertIn('w:eastAsia="SimSun"', m)

    def test_no_file_means_unverified(self):
        r = self._renderer({})
        out = r._run("A䏶B", "p", fonts="Nope")
        self.assertEqual(out.count("<w:r>"), 1)  # 无法验证，保持原样

    def test_true_tofu_stays(self):
        # 主 chain 全缺 → 不拆（真 tofu，预览警告照报）
        r = self._renderer({"Kai": "/kai.ttf"})
        self.assertIsNone(r._split_covered("䏶", "Kai"))

    def test_fallback_order(self):
        r = self._renderer({"Kai": "/kai.ttf", "SimSun": "/song.ttf",
                            "PMingLiU": "/pm.ttf"})
        self.assertEqual(r._fallback_for("Kai", "䏶"), "SimSun")

    def test_fallback_hant_prefers_ming(self):
        import unittest.mock as mock
        m1 = mock.patch("pycbeta.fonts.locator")
        m2 = mock.patch("pycbeta.fonts.font_cmap")
        ml = m1.start()
        mc = m2.start()
        self.addCleanup(m1.stop)
        self.addCleanup(m2.stop)
        ml.return_value.path.side_effect = {
            "Kai": "/kai.ttf", "SimSun": "/song.ttf",
            "PMingLiU": "/pm.ttf"}.get
        mc.side_effect = lambda p: {
            "/kai.ttf": frozenset({0x41}),
            "/song.ttf": frozenset({0x41, 0x43F6}),
            "/pm.ttf": frozenset({0x41, 0x43F6}),
        }.get(p, frozenset())
        rh = DocxRenderer()  # 默认 zh-Hant
        self.assertEqual(rh._fallback_for("Kai", "䏶"), "PMingLiU")
        rs = DocxRenderer(gaiji_lang="zh-Hans")
        self.assertEqual(rs._fallback_for("Kai", "䏶"), "SimSun")

    def test_config_fallback_keys(self):
        from pycbeta.theme import load_presets
        import os as _os
        cfg = load_presets(_os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "config.json")).get("output", {}).get("docx", {})
        self.assertEqual(cfg["fallbackFonts"]["zh-Hant"][0], "PMingLiU")
        self.assertEqual(cfg["fallbackFonts"]["zh-Hans"][0], "SimSun")
        self.assertEqual(cfg["fallbackFonts"]["zh-Hant"][-1],
                         "Microsoft YaHei")
        self.assertEqual(cfg["siddhamFonts"], ["Ranjana", "Siddam"])

    def test_custom_fallback_chain(self):
        import unittest.mock as mock
        m1 = mock.patch("pycbeta.fonts.locator")
        m2 = mock.patch("pycbeta.fonts.font_cmap")
        ml = m1.start()
        mc = m2.start()
        self.addCleanup(m1.stop)
        self.addCleanup(m2.stop)
        ml.return_value.path.side_effect = {
            "Kai": "/kai.ttf", "OnlyFb": "/only.ttf"}.get
        mc.side_effect = lambda p: {
            "/kai.ttf": frozenset({0x41}),
            "/only.ttf": frozenset({0x41, 0x43F6}),
        }.get(p, frozenset())
        r = DocxRenderer(fallback_fonts={"zh-Hant": ["OnlyFb"]})
        self.assertEqual(r._fallback_for("Kai", "䏶"), "OnlyFb")
        # 空配置回默认值
        r2 = DocxRenderer(fallback_fonts={})
        self.assertIn("SimSun", r2._fallback_chain())

    def test_custom_siddham_list(self):
        import unittest.mock as mock
        m1 = mock.patch("pycbeta.fonts.locator")
        m2 = mock.patch("pycbeta.fonts.font_cmap")
        ml = m1.start()
        mc = m2.start()
        self.addCleanup(m1.stop)
        self.addCleanup(m2.stop)
        ml.return_value.path.side_effect = {"OnlyS": "/s.ttf"}.get
        mc.side_effect = lambda p: frozenset({ord("屇")}) \
            if p == "/s.ttf" else frozenset()
        r = DocxRenderer(siddham_fonts=["OnlyS"])
        self.assertEqual(r._ranjana_font_for("屇"), "OnlyS")

    def test_verse_end_to_end(self):
        import tempfile
        import zipfile
        from pycbeta.model import Work, E, Text
        r = self._renderer({"標楷體": "/kai.ttf", "SimSun": "/song.ttf",
                            "新細明體": "/pm.ttf"})
        w = Work(id="T", source_file="", metadata={"title": "t"},
                 body=[E(tag="lg", attrs={}, children=[
                     E(tag="l", attrs={}, children=[Text(text="AB䏶")])])],
                 notes_by_n={}, apps=[], simplified=False)
        # 主题 verse=標楷體走 _run 路径；缺字拆出 SimSun run
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = r.render_work(w, tmp, "v.docx")
        x = zipfile.ZipFile(fn).read("word/document.xml").decode("utf-8")
        self.assertIn('w:eastAsia="SimSun"', x)
        self.assertIn('w:eastAsia="標楷體"', x)


class TestMarker(unittest.TestCase):
    """注释注码（2026-09-06）：字体 output.notes_marker_font 可配（默认 Times New Roman）；
    字号=正文字号×0.75（12pt 正文下 9pt）——不随标题段放大，随 font_scale 等比放大。"""

    def test_default_font(self):
        r = DocxRenderer()
        self.assertEqual(r.notes_marker_font, "Times New Roman")
        self.assertIn('w:ascii="Times New Roman"', r._marker_rpr())

    def test_custom_font(self):
        import re
        r = DocxRenderer(notes_marker_font="宋体, SimSun")
        self.assertIn('w:ascii="宋体, SimSun"', r._marker_rpr())
        # 空白回退默认
        self.assertEqual(DocxRenderer(notes_marker_font="  ").notes_marker_font,
                         "Times New Roman")

    def test_default_size_9pt(self):
        import re
        sz = re.search(r'<w:sz w:val="(\d+)"', DocxRenderer()._marker_rpr()).group(1)
        self.assertEqual(sz, "18")  # 12pt 正文×0.75=9pt

    def test_size_ignores_paragraph(self):
        import re
        r = DocxRenderer()
        r._tag_stack = ["p"]
        r._div_stack = []
        sz_p = re.search(r'<w:sz w:val="(\d+)"', r._marker_rpr()).group(1)
        r._tag_stack = ["head"]  # 标题段基数大，注码不跟
        sz_head = re.search(r'<w:sz w:val="(\d+)"', r._marker_rpr()).group(1)
        self.assertEqual(sz_p, sz_head)

    def test_size_follows_font_scale(self):
        import re
        from pycbeta.theme import Theme
        th = Theme()
        th.scale_font_sizes(1.5)
        big = re.search(r'<w:sz w:val="(\d+)"',
                        DocxRenderer(theme=th)._marker_rpr()).group(1)
        self.assertEqual(big, "27")  # 9pt×1.5=13.5pt，随大字版等比放大

    def test_render_uses_marker_font(self):
        import zipfile
        from pycbeta.model import Work, Note, NoteRef
        body = [E(tag="p", attrs={}, children=[
            Text(text="文"), NoteRef(notes=[Note(children=[Text(text="注")])])])]
        w = Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                 body=body, notes_by_n={}, apps=[], simplified=False)
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(notes="endnote", notes_marker_font="宋体").render_work(
            w, tmp, "mk.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn('w:ascii="宋体"', xml)

    def test_config_key_and_legacy_fallback(self):
        import os as _os
        from pycbeta.cli import _notes_marker_font
        from pycbeta.theme import load_presets
        cfg = load_presets(_os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "config.json")).get("output", {})
        self.assertEqual(cfg.get("notes_marker_font"), "Times New Roman")
        self.assertEqual(_notes_marker_font({}), None)
        self.assertEqual(_notes_marker_font({"marker_font": "旧"}), "旧")
        self.assertEqual(
            _notes_marker_font({"notes_marker_font": "新", "marker_font": "旧"}), "新")


class TestDocxVertical(unittest.TestCase):
    """纵排：vertical=True 时每节 sectPr 写 textDirection tbRl；默认无。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=[Text(text="hi")])],
                    notes_by_n={}, apps=[], simplified=False)

    def _doc(self, **kw):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(**kw).render_work(self._work(), tmp, "v.docx")
        with zipfile.ZipFile(fn) as z:
            return z.read("word/document.xml").decode("utf-8")

    def test_default_horizontal(self):
        self.assertNotIn("textDirection", self._doc())

    def test_vertical_all_sections(self):
        import re
        xml = self._doc(vertical=True)
        sects = re.findall(r"<w:sectPr>.*?</w:sectPr>", xml, flags=re.S)
        self.assertTrue(sects)
        for s in sects:
            self.assertIn('<w:textDirection w:val="tbRl"/>', s)


class TestVerticalMarkers(unittest.TestCase):
    """纵排注码保持横躺（WPS/LO 忽略 w:fitText，全角化拉长版面，见 TODO 实锤链）。
    本类锁定该决定：纵排文档无 fitText 残留，注码原文完整；防后人重加。"""

    def _work(self):
        from pycbeta.model import Work, Note, NoteRef
        body = [E(tag="p", attrs={}, children=[
            Text(text="文"), NoteRef(notes=[Note(children=[Text(text="注")])])])]
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=body, notes_by_n={}, apps=[], simplified=False)

    def _doc(self, **kw):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(**kw).render_work(self._work(), tmp, "m.docx")
        with zipfile.ZipFile(fn) as z:
            return z.read("word/document.xml").decode("utf-8")

    def test_no_fittext_helper_gone(self):
        r = DocxRenderer(vertical=True)
        self.assertFalse(hasattr(r, "_fit_for_rpr"))
        self.assertFalse(hasattr(r, "_fit_id"))

    def test_vertical_markers_plain(self):
        import re
        xml = self._doc(notes="endnote", vertical=True)
        self.assertNotIn("fitText", xml)
        marks = re.findall(r"<w:t[^>]*>\[(\d+)\]", xml)
        self.assertTrue(len(marks) >= 2)  # 正文注码 + 文末校注区序号都在
        self.assertIn('<w:textDirection w:val="tbRl"/>', xml)  # 纵排本身不受影响
class TestSiddhamReading(unittest.TestCase):
    """悉昙读音（官方 docx 同款）：正文/脚注 `<g>` RJ 均附 `(roman)`。

    官方 html/txt 无读音，故仅 docx 出读音；unicode 转写优先（raṃ），CBETA 式兜底。
    """

    TEI = """<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt>
<title level="m" xml:lang="zh-Hant">測試經</title>
<author>譯者</author>
</titleStmt></fileDesc>
<encodingDesc><charDecl>
<char xml:id="RJ-CCEB">
<charProp><localName>rjchar</localName><value>歾</value></charProp>
<charProp><localName>Romanized form in CBETA transcription</localName><value>ra.m</value></charProp>
<charProp><localName>Romanized form in Unicode transcription</localName><value>raṃ</value></charProp>
<mapping cb:dec="1101035" type="PUA">U+10CCEB</mapping>
</char>
</charDecl></encodingDesc></teiHeader>
<text><body>
<p>淨法界<g ref="#RJ-CCEB">X</g>字<anchor xml:id="nkr_note_1" n="k1"/>觀</p>
</body><back>
<note n="k1" type="mod">注<g ref="#RJ-CCEB">X</g>文</note>
</back></text></TEI>"""

    def _work(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "T9999.xml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.TEI)
        self.addCleanup(__import__("shutil").rmtree, d, True)
        return P5Parser().parse(p)

    def test_chardecl_captures_roman(self):
        w = self._work()
        rec = (w.metadata.get("charDecl") or {}).get("RJ-CCEB") or {}
        self.assertEqual(rec.get("roman"), "raṃ")
        self.assertEqual(rec.get("roman_cbeta"), "ra.m")
        self.assertEqual(rec.get("rjchar"), "歾")

    def test_gaiji_roman_lookup(self):
        import types
        r = DocxRenderer()
        r._work = types.SimpleNamespace(
            metadata={"charDecl": {"RJ-A": {"roman": "raṃ"}}}, simplified=False)
        self.assertEqual(r._gaiji_roman("RJ-A"), "raṃ")
        r._work.metadata["charDecl"] = {"RJ-A": {"roman_cbeta": "ra.m"}}
        self.assertEqual(r._gaiji_roman("RJ-A"), "ra.m")
        r._work.metadata["charDecl"] = {"RJ-A": {"rjchar": "歾"}}
        self.assertEqual(r._gaiji_roman("RJ-A"), "")
        self.assertEqual(r._gaiji_roman("CB-X"), "")

    def test_docx_body_and_footnote_have_reading(self):
        import re as _re
        import zipfile
        import tempfile
        w = self._work()
        fn = DocxRenderer().render_work(w, tempfile.mkdtemp())
        z = zipfile.ZipFile(fn)
        try:
            body = "".join(_re.findall(
                r"<w:t[^>]*>([^<]*)</w:t>",
                z.read("word/document.xml").decode("utf-8")))
            self.assertIn("歾(raṃ)", body)
            names = z.namelist()
            self.assertIn("word/footnotes.xml", names)
            foot = "".join(_re.findall(
                r"<w:t[^>]*>([^<]*)</w:t>",
                z.read("word/footnotes.xml").decode("utf-8")))
            self.assertIn("歾(raṃ)", foot)
        finally:
            z.close()

    def test_sg_parens(self):
        import re as _re
        import zipfile
        import tempfile
        from pycbeta.parser import P5Parser
        from pycbeta.render_docx import DocxRenderer
        tei = self.TEI.replace(
            "<p>淨法界<g ref=\"#RJ-CCEB\">X</g>字<anchor xml:id=\"nkr_note_1\" n=\"k1\"/>觀</p>",
            "<p>唵<cb:yin><cb:zi>㘕</cb:zi><cb:sg>音注</cb:sg></cb:yin>抮</p>")
        d = tempfile.mkdtemp()
        p = os.path.join(d, "T9999.xml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(tei)
        self.addCleanup(__import__("shutil").rmtree, d, True)
        w = P5Parser().parse(p)
        fn = DocxRenderer().render_work(w, tempfile.mkdtemp())
        z = zipfile.ZipFile(fn)
        try:
            txt = "".join(_re.findall(
                r"<w:t[^>]*>([^<]*)</w:t>",
                z.read("word/document.xml").decode("utf-8")))
            self.assertIn("唵㘕(音注)抮", txt)
        finally:
            z.close()

    def test_hide_body_siddham(self):
        import re as _re
        import zipfile
        import tempfile
        from pycbeta.parser import P5Parser
        from pycbeta.render_docx import DocxRenderer
        w = P5Parser().parse(self._work_path())
        fn = DocxRenderer(show_body_siddham=False).render_work(
            w, tempfile.mkdtemp())
        z = zipfile.ZipFile(fn)
        try:
            body = "".join(_re.findall(
                r"<w:t[^>]*>([^<]*)</w:t>",
                z.read("word/document.xml").decode("utf-8")))
            # 正文：字和读音都不显示
            self.assertNotIn("歾", body)
            self.assertNotIn("raṃ", body)
            # 脚注：不受影响，照常出字和读音
            foot = "".join(_re.findall(
                r"<w:t[^>]*>([^<]*)</w:t>",
                z.read("word/footnotes.xml").decode("utf-8")))
            self.assertIn("歾(raṃ)", foot)
        finally:
            z.close()

    def test_reading_uses_latin_font(self):
        import re as _re
        import zipfile
        import tempfile
        from pycbeta.parser import P5Parser
        from pycbeta.render_docx import DocxRenderer
        w = P5Parser().parse(self._work_path())
        fn = DocxRenderer().render_work(w, tempfile.mkdtemp())
        z = zipfile.ZipFile(fn)
        try:
            doc = z.read("word/document.xml").decode("utf-8")
            runs = doc.split("<w:r>")
            hit = [s for s in runs if "(raṃ)" in s]
            self.assertTrue(hit)
            self.assertIn('w:ascii="Calibri"', hit[0])
        finally:
            z.close()

    def test_tt_transliteration_red(self):
        import re as _re
        import zipfile
        import tempfile
        from pycbeta.parser import P5Parser
        from pycbeta.render_docx import DocxRenderer
        tei = self.TEI.replace(
            "<p>淨法界<g ref=\"#RJ-CCEB\">X</g>字<anchor xml:id=\"nkr_note_1\" n=\"k1\"/>觀</p>",
            "<p><cb:tt place=\"inline\">"
            "<cb:t xml:lang=\"sa-x-rj\">a<g ref=\"#RJ-CCEB\">X</g></cb:t>"
            "<cb:t xml:lang=\"zh-Hant\">乙</cb:t></cb:tt>尾</p>")
        d = tempfile.mkdtemp()
        p = os.path.join(d, "T9999.xml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(tei)
        self.addCleanup(__import__("shutil").rmtree, d, True)
        w = P5Parser().parse(p)
        fn = DocxRenderer().render_work(w, tempfile.mkdtemp())
        z = zipfile.ZipFile(fn)
        try:
            doc = z.read("word/document.xml").decode("utf-8")
            self.assertIn('w:val="FF4400"', doc)
            txt = "".join(_re.findall(
                r"<w:t[^>]*>([^<]*)</w:t>", doc))
            # 两行直连无分隔（官方同款），不插全角空格
            self.assertIn("a歾(raṃ)乙", txt)
        finally:
            z.close()

    def _work_path(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "T9999.xml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.TEI)
        self.addCleanup(__import__("shutil").rmtree, d, True)
        return p

    def test_html_md_txt_have_no_reading(self):
        import tempfile
        from pycbeta.render_html import HtmlRenderer
        from pycbeta.render_md import MdRenderer
        from pycbeta.render_txt import TxtRenderer
        w = self._work()
        tmp = tempfile.mkdtemp()
        files = HtmlRenderer().render_work(w, tmp)
        html = ""
        for p in files:
            fp = p if os.path.isabs(p) else os.path.join(tmp, p)
            html += open(fp, encoding="utf-8").read()
        self.assertNotIn("(ra", html)
        md = open(MdRenderer().render_work(w, tmp, "t.md"),
                  encoding="utf-8").read()
        self.assertNotIn("(ra", md)
        txt = open(TxtRenderer().render_work(w, tmp, "t.txt"),
                   encoding="utf-8").read()
        self.assertNotIn("(ra", txt)


class TestInlineBracketSize(unittest.TestCase):
    """内联括号字号与内容一致（不继承外层 head 等标题字号）。"""

    def _renderer(self):
        from pycbeta.model import Work
        r = DocxRenderer()
        r._reset_state(Work(id="T", source_file="",
                            metadata={"title": "t", "author": ""},
                            body=[], notes_by_n={}, apps=[], simplified=False))
        return r

    def _sizes(self, out):
        return re.findall(r'<w:sz w:val="(\d+)"', out)

    def test_place_inline_in_head(self):
        from pycbeta.model import Note, Text
        r = self._renderer()
        r._tag_stack.append("head")  # 模拟 head 上下文（如 X1077 卷首题名）
        try:
            note = Note(tag="note", attrs={}, n="", ntype="", place="inline",
                        children=[Text(text="夾注")])
            out = r._render_inline_note(note)
        finally:
            r._tag_stack.pop()
        sizes = self._sizes(out)
        self.assertTrue(sizes)
        self.assertEqual(len(set(sizes)), 1)  # 括号与内容同字号

    def test_inline_mode_context_free(self):
        r = self._renderer()
        r._tag_stack.append("head")
        try:
            out = r._render_inline_mode("校注")
        finally:
            r._tag_stack.pop()
        # note-inline 0.9em（非 head 字号），左右括号一致
        self.assertEqual(set(self._sizes(out)), {"22"})


class TestBylineRight(unittest.TestCase):
    """署名一律右对齐：cb:type 大小写不敏感映射 + author/translator 样式右对齐。"""

    def _renderer(self):
        from pycbeta.model import Work
        r = DocxRenderer()
        r._reset_state(Work(id="T", source_file="",
                            metadata={"title": "t", "author": ""},
                            body=[], notes_by_n={}, apps=[], simplified=False))
        return r

    def test_mapping_case_insensitive(self):
        r = self._renderer()
        for tp, tag in (("author", "author"), ("Translator", "translator"),
                        ("translator", "translator"), ("TRANSLATOR", "translator"),
                        ("", "byline")):
            e = E(tag="byline", attrs={"cb:type": tp} if tp else {},
                  children=[Text(text="某")])
            self.assertIn(f'w:pStyle w:val="{tag}"', r._render_e(e))

    def test_align_right(self):
        r = self._renderer()
        for tag in ("author", "translator", "byline"):
            self.assertIn('w:jc w:val="right"', r.theme.docx_para(tag))


class TestVerticalUncenter(unittest.TestCase):
    """竖排取消居中：title/head/juan/pin 内联 left；横排零变化；名单外不动。"""

    def _renderer(self, vertical):
        from pycbeta.model import Work
        r = DocxRenderer(vertical=vertical)
        r._reset_state(Work(id="T", source_file="",
                            metadata={"title": "t", "author": ""},
                            body=[], notes_by_n={}, apps=[], simplified=False))
        return r

    def test_vertical_adds_left(self):
        for tag in ("title", "head", "juan", "pin"):
            r = self._renderer(True)
            out = r._para(r._run("文", tag), tag)
            self.assertIn('<w:jc w:val="left"/>', out)
            self.assertIn(f'w:pStyle w:val="{tag}"', out)  # 命名样式保留

    def test_vertical_scope(self):
        r = self._renderer(True)
        for tag in ("p", "figure", "byline", "footnote"):
            out = r._para(r._run("文", tag), tag)
            self.assertNotIn('w:val="left"', out)

    def test_horizontal_unchanged(self):
        r = self._renderer(False)
        out = r._para(r._run("文", "juan"), "juan")
        self.assertNotIn('w:val="left"', out)


class TestDivExtraLineHeight(unittest.TestCase):
    """div 内段落：元素自带行距不被 div 经 body 回退带入的值覆盖。"""

    def _renderer(self):
        from pycbeta.model import Work
        r = DocxRenderer()
        r._reset_state(Work(id="T", source_file="",
                            metadata={"title": "t", "author": ""},
                            body=[], notes_by_n={}, apps=[], simplified=False))
        return r

    def test_own_value_wins(self):
        # div-other 无自身属性，其回退行距不得覆盖 head 自身的 1.0
        r = self._renderer()
        r._div_stack = ["div-other"]
        out = r._para(r._run("文", "head"), "head")
        self.assertIn('w:pStyle w:val="head"', out)
        self.assertNotIn("w:line=", out)

    def test_div_margins_kept(self):
        # div-xu 的边距仍要进来，只去行距
        r = self._renderer()
        r._div_stack = ["div-xu"]
        out = r._para(r._run("文", "head"), "head")
        self.assertIn("w:before=", out)
        self.assertNotIn("w:line=", out)

    def test_no_own_value_uses_body_via_style(self):
        # verse 无自身行距：不再靠 div_extra 内联回退（避免重复），
        # 行距由命名样式 verse（docx_para 的 body 回退）提供
        r = self._renderer()
        r._div_stack = ["div-other"]
        out = r._para(r._run("文", "verse"), "verse")
        self.assertIn('w:pStyle w:val="verse"', out)
        self.assertNotIn("w:line=", out)
        self.assertIn('w:line="336"', r.theme.docx_para("verse"))


class TestNoteCf(unittest.TestCase):
    """cf（confer 参考）：docx 全注型追加 ` (cf. a; b)`（前导空格，对齐官方 docx）。"""

    def _work(self, ntype="mod"):
        from pycbeta.model import App, AppRead, Note, NoteRef, Work
        note = Note(tag="note", attrs={}, n="0006001", ntype=ntype,
                    children=[Text(text="傳抱【CB】")])
        cf1 = Note(tag="note", attrs={}, n="", ntype="cf1", children=[Text(text="A17")])
        cf2 = Note(tag="note", attrs={}, n="", ntype="cf2", children=[Text(text="B42")])
        lem = AppRead(tag="lem", attrs={}, role="lem", children=[cf1, cf2])
        app = App(tag="app", attrs={}, key="beg0006001", lem=lem)
        ref = NoteRef(n="0006001", notes=[note])
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[app, E(tag="p", attrs={}, children=[Text(text="文"), ref])],
                    notes_by_n={"0006001": [note]}, apps=[app], simplified=False)

    def _render(self, notes):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(notes=notes).render_work(self._work(), tmp, "cf.docx")
        z = zipfile.ZipFile(fn)
        try:
            out = {}
            for part in ("word/document.xml", "word/footnotes.xml"):
                try:
                    out[part] = z.read(part).decode("utf-8")
                except KeyError:
                    pass
            return fn, out
        finally:
            z.close()

    def test_footnote_cf(self):
        _fn, out = self._render("footnote")
        self.assertIn(" (cf. A17; B42)", out["word/footnotes.xml"])

    def test_endnote_cf(self):
        _fn, out = self._render("endnote")
        self.assertIn(" (cf. A17; B42)", out["word/document.xml"])

    def test_inline_cf(self):
        _fn, out = self._render("inline")
        self.assertIn(" (cf. A17; B42)", out["word/document.xml"])
        self.assertIn("（", out["word/document.xml"])  # inline 括号

    def test_cf_all_note_types(self):
        for ntype in ("mod", "orig", "add"):
            r = DocxRenderer(notes="endnote")
            w = self._work(ntype)
            r._reset_state(w)
            ref = w.body[1].children[1]
            self.assertIn(" (cf. A17; B42)", r._cf_run(ref.notes[0]))


class TestFootnoteInTitle(unittest.TestCase):
    """标题内 noteref（如 jhead 里的校勘注）：脚注内容只带 body → footnote 继承链，
    不继承标题字号基准/粗体/颜色（曾出 15pt 小三加粗蓝字）。"""

    def _xml(self):
        from pycbeta.model import Note, NoteRef, Work
        note = Note(tag="note", attrs={}, n="0810005", ntype="mod",
                    children=[Text(text="園【大】")])
        jhead = E(tag="jhead", attrs={}, children=[
            Text(text="佛說"), NoteRef(n="0810005", notes=[note]),
            Text(text="園生樹經")])
        body = [E(tag="juan", attrs={"n": "001", "fun": "open"},
                  children=[jhead]),
                E(tag="p", attrs={}, children=[Text(text="正文")])]
        work = Work(id="T", source_file="",
                    metadata={"title": "t", "author": ""},
                    body=body, notes_by_n={"0810005": [note]},
                    apps=[], simplified=False)
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(notes="footnote").render_work(work, tmp, "t.docx")
        z = zipfile.ZipFile(fn)
        try:
            return (z.read("word/document.xml").decode("utf-8"),
                    z.read("word/footnotes.xml").decode("utf-8"))
        finally:
            z.close()

    def test_footnote_runs_are_footnote_sized(self):
        _doc, fns = self._xml()
        # 注文 run：footnote 0.75em 按 body 12pt 解 = 9pt（sz 18），不是标题的 15pt
        self.assertIn('<w:sz w:val="18"/>', fns)
        self.assertNotIn('<w:sz w:val="30"/>', fns)

    def test_footnote_runs_not_bold_or_colored(self):
        _doc, fns = self._xml()
        self.assertNotIn("<w:b/>", fns)
        self.assertNotIn("<w:b ", fns)
        self.assertNotIn("0000ff", fns)


class TestAppStarRemoved(unittest.TestCase):
    """star_removed app（corresp 指向他处注）：不在自身锚点重渲该注（官方只在注原位出注），
    lem 内 cf 仍由对应 add 注追加；普通 corresp app（beg_N 重出）保持渲染。"""

    def _work(self, app_type):
        from pycbeta.model import App, AppRead, Note, NoteRef, Work
        note1 = Note(tag="note", attrs={}, n="0001004", ntype="mod",
                     children=[Text(text="甲【大】＊，乙【聖】＊")])
        note2 = Note(tag="note", attrs={}, n="0001a01", ntype="add",
                     children=[Text(text="甲【CB】，丙【大】")])
        cf = Note(tag="note", attrs={}, n="", ntype="cf1", children=[Text(text="Z99")])
        lem = AppRead(tag="lem", attrs={}, role="lem", children=[cf])
        app = App(tag="app", attrs={"corresp": "#0001004"}, key="beg0001a01",
                  atype=app_type, lem=lem)
        ref1 = NoteRef(n="0001004", notes=[note1])
        ref2 = NoteRef(n="0001a01", notes=[note2])
        body = [ref1, E(tag="p", attrs={}, children=[
            Text(text="甲"), ref2, app, Text(text="乙")])]
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=body, notes_by_n={"0001004": [note1], "0001a01": [note2]},
                    apps=[app], simplified=False)

    def _xml(self, app_type):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(notes="footnote").render_work(
            self._work(app_type), tmp, "x.docx")
        z = zipfile.ZipFile(fn)
        try:
            return (z.read("word/document.xml").decode("utf-8"),
                    z.read("word/footnotes.xml").decode("utf-8"))
        finally:
            z.close()

    def test_star_removed_not_rerendered(self):
        doc, fns = self._xml("star_removed")
        self.assertEqual(doc.count("w:footnoteReference"), 2)
        self.assertEqual(fns.count("Z99"), 1)
        self.assertEqual(fns.count("甲【大】＊，乙【聖】＊"), 1)

    def test_plain_corresp_kept(self):
        doc, fns = self._xml(None)
        self.assertEqual(doc.count("w:footnoteReference"), 3)


class TestSplitLemmaOrig(unittest.TestCase):
    """整体 orig 注 + 拆分 mod(a/b)：docx 只出 a/b（官方口径，小写 a/b = 一個校勘
    條目拆成二組，见 model.suppressed_orig_notes）。孤立 orig（无 base-mod）仍出。"""

    def _work(self, with_mod=True):
        from pycbeta.model import Note, NoteRef, Work
        orig = Note(tag="note", attrs={}, n="0028009", ntype="orig",
                    children=[Text(text="其積又火＝𧂐火又【三】")])
        byn = {"0028009": [orig]}
        kids = [Text(text="燃"), NoteRef(n="0028009", notes=[orig])]
        if with_mod:
            ma = Note(tag="note", attrs={}, n="0028009a", ntype="mod",
                      children=[Text(text="其積【大】")])
            mb = Note(tag="note", attrs={}, n="0028009b", ntype="mod",
                      children=[Text(text="火又【CB】")])
            byn.update({"0028009a": [ma], "0028009b": [mb]})
            kids += [NoteRef(n="0028009a", notes=[ma]),
                     NoteRef(n="0028009b", notes=[mb])]
        kids.append(Text(text="其積，火又不燃"))
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=kids)],
                    notes_by_n=byn, apps=[], simplified=False)

    def _xml(self, with_mod):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(notes="footnote").render_work(
            self._work(with_mod), tmp, "s.docx")
        z = zipfile.ZipFile(fn)
        try:
            return (z.read("word/document.xml").decode("utf-8"),
                    z.read("word/footnotes.xml").decode("utf-8"))
        finally:
            z.close()

    def test_split_orig_suppressed(self):
        doc, fns = self._xml(True)
        self.assertEqual(doc.count("w:footnoteReference"), 2)
        self.assertNotIn("＝", fns)
        self.assertIn("其積【大】", fns)
        self.assertIn("火又【CB】", fns)

    def test_standalone_orig_kept(self):
        doc, fns = self._xml(False)
        self.assertEqual(doc.count("w:footnoteReference"), 1)
        self.assertIn("＝", fns)


class TestSuppressedOrigNotes(unittest.TestCase):
    """model.suppressed_orig_notes：小写 a/b 视为同一条目拆组；大写 A/B 不合并。"""

    def test_lowercase_grouped(self):
        from pycbeta.model import Note, suppressed_orig_notes
        def N(n, t):
            return Note(tag="note", attrs={}, n=n, ntype=t)
        out = suppressed_orig_notes({
            "0028009": [N("0028009", "orig")],
            "0028009a": [N("0028009a", "mod")],
            "0028009b": [N("0028009b", "mod")],
        })
        self.assertEqual(out, {"0028009"})

    def test_uppercase_not_grouped(self):
        from pycbeta.model import Note, suppressed_orig_notes
        def N(n, t):
            return Note(tag="note", attrs={}, n=n, ntype=t)
        self.assertEqual(
            suppressed_orig_notes({"0001A": [N("0001A", "orig")],
                                   "0001a": [N("0001a", "mod")]}),
            set())

    def test_standalone_orig_kept(self):
        from pycbeta.model import Note, suppressed_orig_notes
        n = Note(tag="note", attrs={}, n="0001001", ntype="orig")
        self.assertEqual(suppressed_orig_notes({"0001001": [n]}), set())


class TestAncestorInheritance(unittest.TestCase):
    """run 级逐层继承（外→内，属性各自最近优先，body 兜底）：并列标签同时生效、
    非 div 祖先字号可继承、body 颜色可继承、三段后代选择器生效。"""

    def _rpr(self, css, body, needle):
        import shutil, zipfile, re as _re
        from pycbeta.theme import Theme
        from pycbeta.model import Work
        w = Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                 body=body, notes_by_n={}, apps=[], simplified=False)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        fn = DocxRenderer(theme=Theme.from_css(css)).render_work(w, tmp, "a.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        for m in _re.finditer(r"<w:r>(.*?)</w:r>", xml, _re.S):
            if needle in m.group(1):
                rpr = _re.search(r"<w:rPr>.*?</w:rPr>", m.group(1), _re.S)
                return rpr.group(0) if rpr else ""
        return ""

    def test_parallel_tags_both_apply(self):
        # 偈颂 + 楷体：字号/绿色来自 verse，字体来自 kaiti（CSS 逐属性层叠）
        from pycbeta.model import E, Text
        body = [E(tag="lg", attrs={"rend": "kaiti"},
                  children=[E(tag="l", attrs={}, children=[Text("偈文")])])]
        rpr = self._rpr("", body, "偈文")
        self.assertIn('w:sz w:val="24"', rpr)      # verse 12pt
        self.assertIn("008040", rpr)               # verse 绿
        self.assertIn("標楷體", rpr)                # kaiti 字体

    def test_non_div_ancestor_size_inherited(self):
        # li 字号 → 内层 p run（CSS 继承；此前 item 不在 run 祖先链）
        from pycbeta.theme import Theme
        from pycbeta.model import E, Text
        css = Theme().raw_css + "\nli { font-size: 20pt; }\n"
        body = [E(tag="list", attrs={}, children=[
            E(tag="item", attrs={}, children=[
                E(tag="p", attrs={}, children=[Text("項目文")])])])]
        rpr = self._rpr(css, body, "項目文")
        self.assertIn('w:sz w:val="40"', rpr)      # 20pt

    def test_body_color_propagates(self):
        from pycbeta.model import E, Text
        body = [E(tag="p", attrs={}, children=[Text("正文")])]
        rpr = self._rpr("body { color: #ff0000; font-size: 14pt; }\n", body, "正文")
        self.assertIn('w:sz w:val="28"', rpr)      # 14pt 来自 body
        self.assertIn("ff0000", rpr)

    def test_deep_descendant_applies(self):
        from pycbeta.theme import Theme
        from pycbeta.model import E, Text
        css = (Theme().raw_css
               + "\ndiv.div-xu div.div-other p.head { color: #123456; }\n")
        body = [E(tag="div", attrs={"type": "xu"}, children=[
            E(tag="div", attrs={"type": "other"}, children=[
                E(tag="head", attrs={}, children=[Text("深層標題")])])])]
        rpr = self._rpr(css, body, "深層標題")
        self.assertIn("123456", rpr)

    def test_head_inline_note_not_scaled(self):
        # 标题内正文夹注：0.6em×head20pt=12pt、不继承标题粗体（p.head .doube-line-note）
        from pycbeta.model import E, Note, Text
        note = Note(tag="note", attrs={}, n="", ntype="", place="inline",
                    children=[Text("呪文節略")])
        body = [E(tag="head", attrs={}, children=[Text("標題"), note])]
        rpr = self._rpr("", body, "呪文節略")
        self.assertIn('w:sz w:val="24"', rpr)   # 12pt
        self.assertNotIn("<w:b/>", rpr)         # 不粗
        self.assertIn("800080", rpr)            # 夹注紫
        head = self._rpr("", body, "標題")
        self.assertIn('w:sz w:val="40"', head)  # 标题本体 20pt
        self.assertIn("<w:b/>", head)           # 标题本体加粗

    def test_renderer_page_typography_direct(self):
        # 库直接调用渲染器（带 page_presets）也按纸张：16开 body 10.5pt → 正文 run 10.5pt
        import shutil
        from pycbeta.theme import Theme, PAGE_PRESETS
        from pycbeta.model import E, Text, Work
        w = Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                 body=[E(tag="p", attrs={}, children=[Text("正文")])],
                 notes_by_n={}, apps=[], simplified=False)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        fn = DocxRenderer(theme=Theme(), page="16开",
                          page_presets=PAGE_PRESETS).render_work(w, tmp, "pg.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn('w:sz w:val="21"', xml)   # 10.5pt


class TestLatinFont(unittest.TestCase):
    """西文字体（--font-latin）落到 run 的 w:ascii/hAnsi；eastAsia 仍中文名。

    不加 w:hint="eastAsia"：带附加符号的拉丁字母（ā ī 等 EAW=A 模糊字符）
    会因 hint 被判给 eastAsia 而落中文字体（如 舍衛【大】，～Sāvatthī）。
    """

    def test_run_rfonts(self):
        r = DocxRenderer(latin_font="Calibri")
        out = r._run("Sāvatthī K17n abc", "footnote")
        self.assertIn('w:ascii="Calibri"', out)
        self.assertIn('w:eastAsia="新細明體"', out)
        self.assertIn('w:hAnsi="Calibri"', out)
        self.assertNotIn("w:hint", out)  # 有 hint 时 ā/ī 落中文字体
        out_p = r._run("K17n abc", "p")
        self.assertIn('w:ascii="Calibri"', out_p)
        self.assertIn('w:eastAsia="新細明體"', out_p)
        self.assertNotIn("w:hint", out_p)

    def test_styles_footnote_rfonts(self):
        from pycbeta.model import Work
        w = Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                 body=[], notes_by_n={}, apps=[], simplified=False)
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(latin_font="Calibri").render_work(w, tmp, "f.docx")
        st = zipfile.ZipFile(fn).read("word/styles.xml").decode("utf-8")
        m = re.search(r'<w:style[^>]*w:styleId="footnote".*?</w:style>', st, re.S)
        self.assertIsNotNone(m)
        self.assertIn('w:ascii="Calibri"', m.group(0))
        self.assertIn('w:eastAsia="新細明體"', m.group(0))
        self.assertNotIn("w:hint", m.group(0))


class TestAnnotationPerPage(unittest.TestCase):
    """repeat=page（docx 专属）：按原书页 <pb> 清空已注集合，翻页重注。"""

    def _work(self, pb=True):
        from pycbeta.model import Pb, Work
        kids = [Text(text="般若")]
        if pb:
            kids.append(Pb(n="1"))
        kids.append(Text(text="般若"))
        body = [E(tag="p", attrs={}, children=kids)]
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=body, notes_by_n={}, apps=[], simplified=False)

    def _count(self, work, repeat):
        from pycbeta.annotate import resolve_annotations
        ann = resolve_annotations({"enabled": True, "scheme": "pinyin",
                                   "style": "inline", "repeat": repeat})
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(annotations=ann).render_work(work, tmp, "pp.docx")
        xml = zipfile.ZipFile(fn).read("word/document.xml").decode("utf-8")
        return xml.count("〔bō rě〕")

    def test_pb_repages(self):
        self.assertEqual(self._count(self._work(True), "page"), 2)

    def test_first_single(self):
        self.assertEqual(self._count(self._work(True), "first"), 1)

    def test_no_pb_falls_back_single(self):
        self.assertEqual(self._count(self._work(False), "page"), 1)


class TestCorrCbetaRender(unittest.TestCase):
    """corr-cbeta 渲染门控：默认关透明，开则 docx 红字。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="",
                    metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=[
                        Text(text="甲"),
                        E(tag="corr-cbeta", attrs={"n": "1"},
                          children=[Text(text="弗")]),
                        Text(text="乙")])],
                    notes_by_n={}, apps=[], simplified=False)

    def _doc(self, flag):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(notes="footnote", corr_cbeta=flag).render_work(
            self._work(), tmp, "c.docx")
        z = zipfile.ZipFile(fn)
        try:
            return z.read("word/document.xml").decode("utf-8")
        finally:
            z.close()

    def test_off_transparent(self):
        doc = self._doc(False)
        self.assertIn("弗", doc)
        self.assertNotIn("FF0000", doc)

    def test_on_red(self):
        doc = self._doc(True)
        self.assertIn('<w:color w:val="FF0000"/>', doc)
        self.assertIn("弗", doc)


class TestNoteAnnDedup(unittest.TestCase):
    """repeat=page 下，正文用字先占 seen，脚注不再重复注（注内容延迟到页末渲染）。"""

    def _doc(self):
        from pycbeta.model import Note, NoteRef, Work
        note = Note(tag="note", attrs={}, n="n1", ntype="mod",
                    children=[Text(text="\U00024B2A")])   # 𤬪（Ext B）
        ref = NoteRef(n="n1", notes=[note])
        work = Work(id="T", source_file="",
                    metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=[
                        Text(text="\U00024B2A"), ref])],
                    notes_by_n={"n1": [note]}, apps=[], simplified=False)
        ann = {"table": {"X": {"pinyin": "x", "zhuyin": ""}},
               "scheme": "pinyin", "style": "inline",
               "rare_zones": frozenset({"B"}), "rare_cmap": frozenset(),
               "repeat": "page", "full_text": False,
               "brackets": ["〔", "〕"], "rt_size": "50%",
               "rt_font": "", "ruby_up": "100%"}
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fn = DocxRenderer(notes="footnote", annotations=ann).render_work(
            work, tmp, "n.docx")
        z = zipfile.ZipFile(fn)
        try:
            return (z.read("word/document.xml").decode("utf-8"),
                    z.read("word/footnotes.xml").decode("utf-8"))
        finally:
            z.close()

    def test_body_annotated_footnote_not(self):
        doc, fns = self._doc()
        self.assertIn("dù", doc)          # 正文注
        self.assertNotIn("dù", fns)       # 脚注同页不重复注


if __name__ == "__main__":
    unittest.main(verbosity=2)
