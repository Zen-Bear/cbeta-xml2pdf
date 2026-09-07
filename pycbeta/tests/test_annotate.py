"""P6 难字注音：词表装载 / 最长匹配 / 五渲染器标记 / verify 剥除。"""
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.annotate import (
    DEFAULT_TABLE, active, load_table, resolve_annotations, split_annotated,
    parse_rt_size, parse_rare_zones, in_rare_zones, auto_reading, rt_css_rule,
    valid_brackets, split_eq_reading, load_supplement_cmap,
)
from pycbeta.parser import P5Parser
from pycbeta.render_docx import DocxRenderer
from pycbeta.render_epub import EpubRenderer
from pycbeta.render_html import HtmlRenderer
from pycbeta.render_md import MdRenderer
from pycbeta.verify import extract_text, normalize

CBETA = r"E:\dev\cbeta\test"

CUSTOM_TABLE = "彌勒\tmí lè\tㄇㄧˊ ㄌㄜˋ\n菩薩\tpú sà\tㄆㄨˊ ㄙㄚˋ\n月氏國\tyuè shì guó\tㄩㄝˋ ㄕˋ ㄍㄨㄛˊ\n"


class TestLoadTable(unittest.TestCase):
    def test_bundled(self):
        # 内置表用户可自行增删：只断言形状（非空，每行 pinyin/zhuyin 双列）
        table = load_table()
        self.assertTrue(len(table) >= 1)
        for term, r in table.items():
            self.assertTrue(term)
            self.assertIn("pinyin", r)
            self.assertIn("zhuyin", r)

    def test_known_entry(self):
        fn = os.path.join(tempfile.mkdtemp(), "k.txt")
        with open(fn, "w", encoding="utf-8") as f:
            f.write("般若\tbō rě\tㄅㄛ ㄖㄜˇ\n迦葉\tjiā shè\tㄐㄧㄚ ㄕㄜˋ\n")
        table = load_table(fn)
        self.assertEqual(table["般若"]["pinyin"], "bō rě")
        self.assertEqual(table["般若"]["zhuyin"], "ㄅㄛ ㄖㄜˇ")
        self.assertEqual(table["迦葉"]["pinyin"], "jiā shè")

    def test_missing_file(self):
        self.assertEqual(load_table(r"E:\nonexistent\no-such-table.txt"), {})

    def test_comments_and_blanks(self):
        fn = os.path.join(tempfile.mkdtemp(), "t.txt")
        with open(fn, "w", encoding="utf-8") as f:
            f.write("# 注释\n\n般若\tbō rě\n")
        table = load_table(fn)
        self.assertEqual(table, {"般若": {"pinyin": "bō rě", "zhuyin": ""}})


class TestResolve(unittest.TestCase):
    def test_off(self):
        self.assertIsNone(resolve_annotations(None))
        self.assertIsNone(resolve_annotations({}))
        self.assertIsNone(resolve_annotations({"enabled": False}))

    def test_scheme_fallback(self):
        spec = resolve_annotations({"enabled": True, "scheme": "bogus"})
        self.assertEqual(spec["scheme"], "pinyin")
        spec = resolve_annotations({"enabled": True, "scheme": "zhuyin"})
        self.assertEqual(spec["scheme"], "zhuyin")

    def test_docx_style_fallback(self):
        spec = resolve_annotations({"enabled": True})
        self.assertEqual(spec["style"], "inline")
        self.assertEqual(spec["brackets"], ["〔", "〕"])
        spec = resolve_annotations({"enabled": True, "style": "ruby"})
        self.assertEqual(spec["style"], "ruby")
        spec = resolve_annotations({"enabled": True, "style": "bogus"})
        self.assertEqual(spec["style"], "inline")
        spec = resolve_annotations({"enabled": True, "brackets": ["(", ")"]})
        self.assertEqual(spec["brackets"], ["(", ")"])
        for bad in (None, "x", ["("], ["(", ")", "x"], ["ab", "〕"], ["", "〕"]):
            spec = resolve_annotations({"enabled": True, "brackets": bad})
            self.assertEqual(spec["brackets"], ["〔", "〕"])

    def test_old_docx_style_compat(self):
        ann = active({"table": {"般若": {"pinyin": "bō rě", "zhuyin": ""}},
                      "docx_style": "ruby"})
        self.assertEqual(ann["style"], "ruby")
        ann = active({"table": {"般若": {"pinyin": "bō rě", "zhuyin": ""}},
                      "docx_style": "bracket"})
        self.assertEqual(ann["style"], "inline")

    def test_new_keys_carried(self):
        spec = resolve_annotations({"enabled": True, "rt_size": "60%",
                                    "rt_font": "楷体", "rare_zones": ["G", "H"]})
        self.assertEqual(spec["rt_size"], "60%")
        self.assertEqual(spec["rt_font"], "楷体")
        self.assertEqual(spec["rare_zones"], frozenset({"G", "H"}))
        self.assertFalse(spec["full_text"])
        spec = resolve_annotations({"enabled": True, "full_text": True})
        self.assertTrue(spec["full_text"])
        self.assertEqual(spec["ruby_up"], "100%")
        spec = resolve_annotations({"enabled": True, "ruby_up": "14pt"})
        self.assertEqual(spec["ruby_up"], "14pt")
        ann = active({"table": {"a": {"pinyin": "x", "zhuyin": ""}},
                      "rare_zones": "B"})
        self.assertEqual(ann["rare_zones"], frozenset({"B"}))
        self.assertEqual(ann["ruby_up"], "100%")

    def test_field_style(self):
        spec = resolve_annotations({"enabled": True, "style": "field"})
        self.assertEqual(spec["style"], "field")
        spec = resolve_annotations({"enabled": True, "style": "bogus"})
        self.assertEqual(spec["style"], "inline")

    def test_split_eq_reading(self):
        self.assertEqual(split_eq_reading("菩薩", "pú sà"),
                         [("菩", "pú"), ("薩", "sà")])
        self.assertEqual(split_eq_reading("般若", "bō rě"),
                         [("般", "bō"), ("若", "rě")])
        # 音节数对不上 → 整词 single 域兜底
        self.assertEqual(split_eq_reading("觀世音", "guān shì yīn dúde"),
                         [("觀世音", "guān shì yīn dúde")])
        self.assertEqual(split_eq_reading("菩", "pú"), [("菩", "pú")])


class TestRtSize(unittest.TestCase):
    def test_percent(self):
        self.assertAlmostEqual(parse_rt_size("50%", 12.0), 6.0)
        self.assertAlmostEqual(parse_rt_size("60 %", 10.0), 6.0)

    def test_absolute(self):
        self.assertAlmostEqual(parse_rt_size("7pt", 12.0), 7.0)
        self.assertAlmostEqual(parse_rt_size("7", 12.0), 7.0)

    def test_invalid(self):
        self.assertIsNone(parse_rt_size(None, 12.0))
        self.assertIsNone(parse_rt_size("", 12.0))
        self.assertIsNone(parse_rt_size("big", 12.0))
        self.assertIsNone(parse_rt_size("0", 12.0))
        self.assertIsNone(parse_rt_size("};evil{", 12.0))

    def test_css_rule(self):
        ann = {"table": {"a": {"pinyin": "x", "zhuyin": ""}}, "scheme": "pinyin",
               "style": "ruby", "brackets": ["〔", "〕"],
               "rt_size": "60%", "rt_font": "楷体"}
        rule = rt_css_rule(ann)
        self.assertIn("ruby rt", rule)
        self.assertIn("font-size: 60%", rule)
        self.assertIn('font-family: "楷体"', rule)
        ann["style"] = "inline"
        self.assertEqual(rt_css_rule(ann), "")
        ann = dict(ann, style="ruby", rt_size="};evil{", rt_font='a";b')
        rule = rt_css_rule(ann)
        self.assertNotIn("evil", rule)
        self.assertIn('font-family: "ab"', rule)


class TestRare(unittest.TestCase):
    def test_parse_rare_zones(self):
        self.assertEqual(parse_rare_zones(["G", "H"]), frozenset({"G", "H"}))
        self.assertEqual(parse_rare_zones("B"), frozenset({"B"}))
        self.assertEqual(parse_rare_zones("Ext G, cjk ext h"), frozenset({"G", "H"}))
        # All 已取消：视为非法忽略
        self.assertEqual(parse_rare_zones("All"), frozenset())
        self.assertEqual(parse_rare_zones(["b", "ALL", "Z"]), frozenset({"B"}))
        self.assertEqual(parse_rare_zones(""), frozenset())
        self.assertEqual(parse_rare_zones(None), frozenset())
        self.assertEqual(parse_rare_zones(["Z", ""]), frozenset())
        self.assertTrue(in_rare_zones(0x24B2A, frozenset({"B"})))
        self.assertFalse(in_rare_zones(0x4E2D, frozenset({"B"})))
        self.assertTrue(in_rare_zones(0x30000, frozenset({"G"})))
        self.assertFalse(in_rare_zones(0x30000, frozenset({"B"})))

    def test_auto_reading(self):
        self.assertEqual(auto_reading("楞"), "léng")
        self.assertEqual(auto_reading("楞", "zhuyin"), "ㄌㄥˊ")
        self.assertEqual(auto_reading("𤬪"), "dù")
        # 未收录字（TONE 原样返回 / BOPOMOFO 补˙）→ None
        self.assertIsNone(auto_reading("𰀀"))
        self.assertIsNone(auto_reading("𰀀", "zhuyin"))

    def test_auto_reading_no_pypinyin(self):
        import unittest.mock as mock
        from pycbeta import annotate as _a
        _a._READING_CACHE.clear()
        try:
            with mock.patch.dict(sys.modules, {"pypinyin": None}):
                self.assertIsNone(auto_reading("楞"))
        finally:
            _a._READING_CACHE.clear()

    def test_split_rare(self):
        table = {"菩薩": {"pinyin": "pú sà", "zhuyin": "ㄆㄨˊ ㄙㄚˋ"}}
        # 词表优先于自动
        segs = split_annotated("菩薩𤬪", table, rare_zones=frozenset({"B"}))
        self.assertEqual(segs, [("菩薩", "pú sà"), ("𤬪", "dù")])
        # 关闭分区则不注
        self.assertEqual(split_annotated("𤬪", table), [("𤬪", None)])
        # 分区外未知字跳过（𰀀 属 G 区，用 B 分区时不注），已知仍注
        table2 = {"X": {"pinyin": "x", "zhuyin": ""}}
        segs = split_annotated("a𰀀𤬪b", table2, rare_zones=frozenset({"B"}))
        self.assertEqual(segs, [("a𰀀", None), ("𤬪", "dù"), ("b", None)])
        # G 分区则 𰀀 未收录跳过（pypinyin 无此字）
        segs = split_annotated("a𰀀b", table2, rare_zones=frozenset({"G"}))
        self.assertEqual(segs, [("a𰀀b", None)])

    def test_split_full(self):
        # 全文模式：词表优先整词（菩薩整体 pú sà，专音保留），其余逐字，忽略 seen/zones
        table = {"菩薩": {"pinyin": "pú sà", "zhuyin": "ㄆㄨˊ ㄙㄚˋ"}}
        segs = split_annotated("菩薩A1好", table, full=True)
        self.assertEqual(segs, [("菩薩", "pú sà"), ("A1", None), ("好", "hǎo")])
        seen = {"菩薩"}
        segs = split_annotated("菩薩好", table, full=True, seen=seen)
        self.assertEqual(segs, [("菩薩", "pú sà"), ("好", "hǎo")])
        # 空表 + full 照注逐字（active 层要求表非空，split 层不设限）
        segs = split_annotated("楞", {}, full=True)
        self.assertEqual(segs, [("楞", "léng")])


class TestSupplement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pycbeta.fonts import supplement_path
        cls.SUPPLEMENT = supplement_path()
        assert cls.SUPPLEMENT, "随仓补充字形缺失：cbeta/fonts/CBETASupplement.ttf"

    def test_load_cmap(self):
        cmap = load_supplement_cmap(self.SUPPLEMENT)
        self.assertTrue(len(cmap) > 10000)
        self.assertIn(0x24B2A, cmap)   # 𤬪：补充字形覆盖
        self.assertNotIn(0x4E2D, cmap)  # 中：常用字不在补充字形内

    def test_load_missing(self):
        self.assertEqual(load_supplement_cmap(r"E:\nonexistent\x.ttf"), frozenset())
        self.assertEqual(load_supplement_cmap(""), frozenset())
        self.assertEqual(load_supplement_cmap(None), frozenset())

    def test_load_no_fonttools(self):
        import unittest.mock as mock
        with mock.patch.dict(sys.modules, {"fontTools": None, "fontTools.ttLib": None}):
            from pycbeta import annotate as _a
            _a._CMAP_CACHE.clear()
            try:
                self.assertEqual(_a.load_supplement_cmap(self.SUPPLEMENT), frozenset())
            finally:
                _a._CMAP_CACHE.clear()

    def test_split_cmap(self):
        table = {"X": {"pinyin": "x", "zhuyin": ""}}
        # 无阈值，仅 cmap：覆盖字注音，非覆盖字不注
        segs = split_annotated("a楞𤬪b", table, rare_cmap=frozenset({0x24B2A}))
        self.assertEqual(segs, [("a楞", None), ("𤬪", "dù"), ("b", None)])

    def test_resolve_carries_cmap(self):
        spec = resolve_annotations({"enabled": True, "rare_font": self.SUPPLEMENT})
        self.assertTrue(len(spec["rare_cmap"]) > 10000)
        ann = active({"table": {"X": {"pinyin": "x", "zhuyin": ""}},
                      "rare_cmap": frozenset({0x695E})})
        self.assertIn(0x695E, ann["rare_cmap"])

    def test_md_cmap_end_to_end(self):
        from pycbeta.model import Text as _T
        ann = active({"table": {"X": {"pinyin": "x", "zhuyin": ""}},
                      "scheme": "pinyin", "style": "inline",
                      "brackets": ["〔", "〕"], "rare_cmap": frozenset({0x695E})})
        out = MdRenderer(annotations=ann)._render_node(_T("a楞b"))
        self.assertEqual(out, "a楞〔léng〕b")

    def test_enabled_missing_file_off(self):
        spec = resolve_annotations({"enabled": True, "file": r"E:\nonexistent\x.txt"})
        self.assertIsNone(spec)

    def test_active(self):
        self.assertIsNone(active(None))
        self.assertIsNone(active({"table": {}, "scheme": "pinyin"}))
        ann = active({"table": {"般若": {"pinyin": "bō rě", "zhuyin": ""}}, "scheme": "zhuyin"})
        self.assertEqual(ann["scheme"], "zhuyin")


class TestSplit(unittest.TestCase):
    TABLE = {
        "觀世音": {"pinyin": "guān shì yīn", "zhuyin": "ㄍㄨㄢ ㄕˋ ㄧㄣ"},
        "菩薩": {"pinyin": "pú sà", "zhuyin": "ㄆㄨˊ ㄙㄚˋ"},
    }

    def test_longest_first(self):
        # 最长优先：觀世音整体匹配，不拆成 觀+世音
        segs = split_annotated("南無觀世音菩薩", self.TABLE)
        self.assertEqual(segs, [("南無", None), ("觀世音", "guān shì yīn"),
                                ("菩薩", "pú sà")])

    def test_no_match(self):
        self.assertEqual(split_annotated("阿彌陀佛", self.TABLE), [("阿彌陀佛", None)])

    def test_seen_dedup(self):
        table = dict(self.TABLE)
        seen = set()
        segs = split_annotated("觀世音菩薩", table, seen=seen)
        self.assertEqual(segs, [("觀世音", "guān shì yīn"), ("菩薩", "pú sà")])
        # 同集合再次出现 → 去注音保原文；新词仍注
        segs = split_annotated("觀世音如來", table, seen=seen)
        self.assertEqual(segs, [("觀世音", None), ("如來", None)])
        table["如來"] = {"pinyin": "rú lái", "zhuyin": "ㄖㄨˊ ㄌㄞˊ"}
        segs = split_annotated("如來觀世音", table, seen=seen)
        self.assertEqual(segs, [("如來", "rú lái"), ("觀世音", None)])
        # seen=None 不过滤
        segs = split_annotated("觀世音", table)
        self.assertEqual(segs, [("觀世音", "guān shì yīn")])

    def test_empty(self):
        self.assertEqual(split_annotated("般若", {}), [("般若", None)])
        self.assertEqual(split_annotated("", self.TABLE), [])

    def test_scheme_column(self):
        segs = split_annotated("菩薩", self.TABLE, scheme="zhuyin")
        self.assertEqual(segs, [("菩薩", "ㄆㄨˊ ㄙㄚˋ")])

    def test_missing_column_no_annotate(self):
        table = {"般若": {"pinyin": "bō rě", "zhuyin": ""}}
        self.assertEqual(split_annotated("般若", table, scheme="zhuyin"), [("般若", None)])


class TestRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()
        cls.table_fn = os.path.join(cls.tmp, "ann.txt")
        with open(cls.table_fn, "w", encoding="utf-8") as f:
            f.write(CUSTOM_TABLE)
        cls.ann = resolve_annotations({"enabled": True, "scheme": "pinyin",
                                       "file": cls.table_fn})
        cls.ann_ruby = resolve_annotations({"enabled": True, "scheme": "pinyin",
                                            "file": cls.table_fn,
                                            "style": "ruby"})
        assert cls.ann is not None and cls.ann_ruby is not None

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_style_brackets_defaults(self):
        self.assertEqual(self.ann.get("style"), "inline")
        self.assertEqual(self.ann.get("brackets"), ["〔", "〕"])
        self.assertEqual(self.ann_ruby.get("style"), "ruby")

    def test_html_inline(self):
        files = HtmlRenderer(annotations=self.ann).render_work(self.work, self.tmp)
        text = open(os.path.join(self.tmp, files[0]), encoding="utf-8").read()
        self.assertNotIn("<ruby>", text)
        self.assertIn("彌勒〔mí lè〕", text)

    def test_md_custom_brackets(self):
        from pycbeta.annotate import resolve_annotations as _res
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "inline",
                    "brackets": ["(", ")"], "file": self.table_fn})
        fn = MdRenderer(annotations=ann).render_work(self.work, self.tmp, "cb.md")
        text = open(fn, encoding="utf-8").read()
        self.assertIn("彌勒(mí lè)", text)
        self.assertNotIn("彌勒〔", text)

    def test_repeat_first(self):
        from pycbeta.annotate import resolve_annotations as _res
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "inline",
                    "repeat": "first", "file": self.table_fn})
        r = MdRenderer(annotations=ann)
        fn = r.render_work(self.work, self.tmp, "first.md")
        text = open(fn, encoding="utf-8").read()
        # 全文只注首次：括注恰一次，原文多次
        self.assertEqual(text.count("彌勒〔mí lè〕"), 1)
        self.assertGreater(text.count("彌勒"), 3)
        # 渲染器复用不跨文档污染：第二次渲染同样恰一次
        fn2 = r.render_work(self.work, self.tmp, "first2.md")
        text2 = open(fn2, encoding="utf-8").read()
        self.assertEqual(text2.count("彌勒〔mí lè〕"), 1)

    def test_repeat_page_docx(self):
        import re as _re4
        from pycbeta.annotate import resolve_annotations as _res
        from pycbeta.parser import P5Parser as _P
        xml = os.path.join(CBETA, "T0670 楞伽阿跋多羅寶經", "T16n0670.xml")
        work = _P().parse(xml)
        first = _res({"enabled": True, "scheme": "pinyin", "style": "inline",
                      "repeat": "first", "file": self.table_fn})
        page = _res({"enabled": True, "scheme": "pinyin", "style": "inline",
                     "repeat": "page", "file": self.table_fn})
        f1 = DocxRenderer(annotations=first,
                          pagination={"enabled": True}).render_work(work, self.tmp, "p1.docx")
        f2 = DocxRenderer(annotations=page,
                          pagination={"enabled": True}).render_work(work, self.tmp, "p2.docx")
        import zipfile as _z
        x1 = _z.ZipFile(f1).read("word/document.xml").decode("utf-8")
        x2 = _z.ZipFile(f2).read("word/document.xml").decode("utf-8")
        # CUSTOM_TABLE 词在 T0670 正文未必出现：不断言绝对数，只断言 page>=first（分节重置只增不减）
        n1 = len(_re4.findall("〔.*?〕", x1))
        n2 = len(_re4.findall("〔.*?〕", x2))
        self.assertGreaterEqual(n2, n1)

    def test_repeat_validation(self):
        spec = resolve_annotations({"enabled": True, "repeat": "first"})
        self.assertEqual(spec["repeat"], "first")
        spec = resolve_annotations({"enabled": True, "repeat": "page"})
        self.assertEqual(spec["repeat"], "page")
        spec = resolve_annotations({"enabled": True, "repeat": "bogus"})
        self.assertEqual(spec["repeat"], "all")
        spec = resolve_annotations({"enabled": True})
        self.assertEqual(spec["repeat"], "all")

    def test_html_rt_css(self):
        from pycbeta.annotate import resolve_annotations as _res
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "ruby",
                    "rt_size": "60%", "rt_font": "楷体", "file": self.table_fn})
        files = HtmlRenderer(annotations=ann).render_work(self.work, self.tmp)
        text = open(os.path.join(self.tmp, files[0]), encoding="utf-8").read()
        self.assertIn("ruby rt", text)
        self.assertIn("font-size: 60%", text)
        self.assertIn('font-family: "楷体"', text)

    def test_docx_ruby_enriched(self):
        # rubyPr 补完（WPS 拼音指南同款结构）+ rt 独立字号
        from pycbeta.annotate import resolve_annotations as _res
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "ruby",
                    "rt_size": "7pt", "rt_font": "楷体", "file": self.table_fn})
        fn = DocxRenderer(annotations=ann).render_work(self.work, self.tmp, "rt.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        for tag in ("<w:hps ", "<w:hpsRaise ", "<w:hpsBaseText ", '<w:lid w:val="zh-CN"/>'):
            self.assertIn(tag, xml)
        import re
        self.assertRegex(xml, re.compile(r"<w:rt>.*?<w:sz w:val=\"14\"/>", re.S))
        self.assertIn('w:eastAsia="楷体"', xml)

    def test_md_rare_end_to_end(self):
        from pycbeta.annotate import resolve_annotations as _res
        from pycbeta.model import Text as _T
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "inline",
                    "rare_zones": ["B"], "file": self.table_fn})
        out = MdRenderer(annotations=ann)._render_node(_T("a𤬪b"))
        self.assertEqual(out, "a𤬪〔dù〕b")

    def test_md_full_end_to_end(self):
        from pycbeta.annotate import resolve_annotations as _res
        from pycbeta.model import Text as _T
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "inline",
                    "full_text": True, "file": self.table_fn})
        self.assertTrue(ann["full_text"])
        # 词表优先整词（CUSTOM_TABLE 有彌勒），其余逐字
        out = MdRenderer(annotations=ann)._render_node(_T("彌勒好"))
        self.assertEqual(out, "彌勒〔mí lè〕好〔hǎo〕")

    def test_gaiji_annotated(self):
        # 解析后缺字走统一注音管线（<g> 𤬪 这类有 Unicode 的缺字可被自动注音；未知码直通原文）
        from pycbeta.model import Gaiji as _G
        rare = {"table": {"X": {"pinyin": "x", "zhuyin": ""}}, "scheme": "pinyin",
                "style": "inline", "brackets": ["〔", "〕"], "rare_zones": frozenset({"B"})}
        g = _G(code="CB99999", char="𤬪")
        self.assertEqual(MdRenderer(annotations=rare)._render_node(g), "𤬪〔dù〕")
        ruby = dict(rare, style="ruby")
        out = HtmlRenderer(annotations=ruby)._render_gaiji(g)
        self.assertIn("<ruby>𤬪<rt>dù</rt></ruby>", out)
        out = DocxRenderer(annotations=rare)._render_node(g)
        import re as _re
        self.assertIn("𤬪〔dù〕", _re.sub(r"<[^>]+>", "", out))
        self.assertNotIn("<w:ruby>", out)
        # 未启用注音：原文直通
        self.assertEqual(MdRenderer()._render_node(g), "𤬪")

    def test_html_ruby(self):
        files = HtmlRenderer(annotations=self.ann_ruby).render_work(self.work, self.tmp)
        text = open(os.path.join(self.tmp, files[0]), encoding="utf-8").read()
        self.assertIn("<ruby>彌勒<rt>mí lè</rt></ruby>", text)

    def test_html_off_by_default(self):
        files = HtmlRenderer().render_work(self.work, self.tmp)
        text = open(os.path.join(self.tmp, files[0]), encoding="utf-8").read()
        self.assertNotIn("<ruby>", text)
        self.assertNotIn("mí lè", text)

    def test_md_bracket(self):
        fn = MdRenderer(annotations=self.ann).render_work(self.work, self.tmp, "ann.md")
        text = open(fn, encoding="utf-8").read()
        self.assertIn("彌勒〔mí lè〕", text)

    def test_docx_ruby(self):
        fn = DocxRenderer(annotations=self.ann_ruby).render_work(self.work, self.tmp, "ann.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("<w:ruby>", xml)
        self.assertIn("<w:rt>", xml)
        self.assertIn("mí lè", xml)
        self.assertIn("彌勒", xml)

    def test_docx_bracket(self):
        # 后备模式（LibreOffice/WPS 可见）：无 w:ruby，纯文本括注，原文不丢
        fn = DocxRenderer(annotations=self.ann).render_work(self.work, self.tmp, "br.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertNotIn("<w:ruby>", xml)
        self.assertIn("彌勒〔mí lè〕", xml)

    def test_docx_field(self):
        # EQ 域模式（WPS 拼音指南原生模板）：逐字 begin/instr/end，无 w:ruby
        from pycbeta.annotate import resolve_annotations as _res
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "field",
                    "file": self.table_fn})
        fn = DocxRenderer(annotations=ann).render_work(self.work, self.tmp, "fld.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertNotIn("<w:ruby>", xml)
        self.assertIn('<w:fldChar w:fldCharType="begin"/>', xml)
        self.assertIn('<w:fldChar w:fldCharType="end"/>', xml)
        self.assertIn("\\o", xml)
        # 彌勒逐字两域（up/hps 随正文字号，默认宋体）
        import re as _re2
        self.assertRegex(xml, _re2.compile(r"\\up \d+\(mí\),彌"))
        self.assertRegex(xml, _re2.compile(r"\\up \d+\(lè\),勒"))
        self.assertIn("Font:宋体", xml)
        self.assertRegex(xml, _re2.compile(r"hps\d+"))

    def test_field_up_default(self):
        # 默认抬升 100% 正文字号（整字高，不与正文相交）：正文无个位数 up
        from pycbeta.annotate import resolve_annotations as _res
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "field",
                    "file": self.table_fn})
        fn = DocxRenderer(annotations=ann).render_work(self.work, self.tmp, "up.docx")
        with zipfile.ZipFile(fn) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        import re as _re3
        ups = sorted(set(int(v) for v in _re3.findall(r"\\up (\d+)\(", xml)))
        self.assertTrue(ups)
        self.assertGreaterEqual(min(ups), 10)
        # 自定义 ruby_up 生效
        ann2 = _res({"enabled": True, "scheme": "pinyin", "style": "field",
                     "ruby_up": "60%", "file": self.table_fn})
        fn2 = DocxRenderer(annotations=ann2).render_work(self.work, self.tmp, "up2.docx")
        with zipfile.ZipFile(fn2) as z:
            xml2 = z.read("word/document.xml").decode("utf-8")
        ups2 = sorted(set(int(v) for v in _re3.findall(r"\\up (\d+)\(", xml2)))
        self.assertTrue(ups2)
        self.assertLess(max(ups2), min(ups))

    def test_extract_docx_field(self):
        # EQ 域提取：域代码丢弃，原文保留（verify 可比对）
        from pycbeta.annotate import resolve_annotations as _res
        from pycbeta.verify import _eq_base
        import re as _re
        ann = _res({"enabled": True, "scheme": "pinyin", "style": "field",
                    "file": self.table_fn})
        fn = DocxRenderer(annotations=ann).render_work(self.work, self.tmp, "vf.docx")
        text = extract_text(fn)
        self.assertNotIn("mí lè", text)
        self.assertNotIn("jc0", text)
        self.assertIn("彌勒", text)
        # 非注音域代码保持原样（旧行为）
        m = _re.search(r"<w:instrText[^>]*>(.*?)</w:instrText>",
                       "x<w:instrText xml:space=\"preserve\"> PAGE </w:instrText>y")
        from pycbeta.verify import _EQ_RE
        self.assertIn("PAGE", _EQ_RE.sub(_eq_base, m.group(0)))

    def test_epub_ruby(self):
        fn = EpubRenderer(annotations=self.ann).render_work(self.work, self.tmp, "ann.epub")
        self.assertTrue(zipfile.is_zipfile(fn))

    def test_head_byline_suppressed(self):
        # 题署/卷名不注音（byline 含"月氏國"，jhead/书名含"彌勒菩薩"），正文注音保留
        import re
        files = HtmlRenderer(annotations=self.ann_ruby).render_work(self.work, self.tmp)
        html = open(os.path.join(self.tmp, files[0]), encoding="utf-8").read()
        byline = re.search(r"<p class=\"byline\">.*?</p>", html, re.S).group(0)
        self.assertNotIn("<ruby>", byline)
        self.assertIn("<ruby>彌勒", html)  # 正文注音不受压制影响
        files = HtmlRenderer(annotations=self.ann).render_work(self.work, self.tmp)
        html = open(os.path.join(self.tmp, files[0]), encoding="utf-8").read()
        byline = re.search(r"<p class=\"byline\">.*?</p>", html, re.S).group(0)
        self.assertNotIn("月氏國〔", byline)
        self.assertIn("彌勒〔mí lè〕", html)  # 行内模式正文注音保留
        fn = MdRenderer(annotations=self.ann).render_work(self.work, self.tmp, "sup.md")
        md = open(fn, encoding="utf-8").read()
        self.assertNotIn("月氏國〔", md)
        self.assertNotIn("## 彌勒〔", md)
        self.assertIn("彌勒〔mí lè〕", md)  # 正文注音保留


class TestVerifyStrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()
        table_fn = os.path.join(cls.tmp, "ann.txt")
        with open(table_fn, "w", encoding="utf-8") as f:
            f.write(CUSTOM_TABLE)
        cls.ann = resolve_annotations({"enabled": True, "scheme": "pinyin",
                                       "file": table_fn})
        cls.ann_ruby = resolve_annotations({"enabled": True, "scheme": "pinyin",
                                            "file": table_fn,
                                            "style": "ruby"})

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_extract_html_strips_rt(self):
        fn = os.path.join(self.tmp, "a.html")
        with open(fn, "w", encoding="utf-8") as f:
            f.write("<p>學<ruby>般若<rt>bō rě</rt></ruby>波羅蜜</p>")
        self.assertEqual(extract_text(fn).strip(), "學般若波羅蜜")

    def test_extract_docx_strips_rt(self):
        fn = DocxRenderer(annotations=self.ann_ruby).render_work(self.work, self.tmp, "v.docx")
        text = extract_text(fn)
        self.assertNotIn("mí lè", text)
        self.assertIn("彌勒", text)

    def test_extract_docx_bracket_normalizes_clean(self):
        # bracket 模式提取后经 normalize 与无注音一致（verify 可比对）
        fn = DocxRenderer(annotations=self.ann).render_work(self.work, self.tmp, "vb.docx")
        self.assertNotIn("<w:ruby>", zipfile.ZipFile(fn).read("word/document.xml").decode("utf-8"))
        text = normalize(extract_text(fn))
        self.assertNotIn("mí lè", text)
        self.assertIn("彌勒", text)

    def test_normalize_strips_md_bracket(self):
        self.assertEqual(normalize("學彌勒〔mí lè〕菩薩"), "學彌勒菩薩")

    def test_normalize_custom_brackets_gated(self):
        # 自定义括号：仅读音内容被剥，正文/校勘括号保留
        # （用超 8 字读音 ruling out 旧 [...] 短标记规则，确保走门控分支）
        self.assertEqual(normalize("南無[guān shì yīn pú sà]菩薩", ("[", "]")), "南無菩薩")
        self.assertEqual(normalize("A[月氏國三藏法師譯經]B", ("[", "]")), "A[月氏國三藏法師譯經]B")
        self.assertEqual(normalize("A（月氏國）B（bō rě）C", ("（", "）")), "A（月氏國）BC")
        self.assertEqual(normalize("無注音（月氏國）文本", ("（", "）")), "無注音（月氏國）文本")


class TestCliSource(unittest.TestCase):
    """无 --config 时同样读内置 config（与其他 output.* 默认一致），避免开关被静默忽略。"""

    def test_builtin_source_no_config(self):
        from pycbeta.cli import _annotations_source
        spec, base = _annotations_source(None, None)
        self.assertTrue(base.endswith("config.json"))
        self.assertIsInstance(spec, dict)  # 内置顶层 annotations 存在（开关状态不假定，随仓库现状）
        self.assertIn(spec.get("scheme", "pinyin"), ("pinyin", "zhuyin"))
        # 开关语义：关→None，开→可装载（与 resolve_annotations 一致）
        if spec.get("enabled"):
            self.assertIsNotNone(resolve_annotations(spec, base))
        else:
            self.assertIsNone(resolve_annotations(spec, base))

    def test_explicit_config(self):
        from pycbeta.cli import _annotations_source
        spec, base = _annotations_source("some.json", {"annotations": {"enabled": True}})
        self.assertEqual(base, "some.json")
        self.assertTrue(spec.get("enabled"))

    def test_builtin_enabled_resolves(self):
        # 用户场景：直接改内置 config 开 enabled=true，无 --config 也能装载
        from pycbeta.cli import _annotations_source
        spec, base = _annotations_source(None, None)
        spec = dict(spec, enabled=True)
        ann = resolve_annotations(spec, base)
        self.assertIsNotNone(ann)
        self.assertTrue(len(ann["table"]) >= 1)


if __name__ == "__main__":
    unittest.main()
