import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta import report as R


class TestReportBasics(unittest.TestCase):
    """转换报告收集器：no-op / 编号 / 内容单行化 / sticky / key 去重 / 计数。"""

    def setUp(self):
        R.report.reset()

    def tearDown(self):
        R.report.reset()

    def test_noop_when_inactive(self):
        R.report.add("字体", "x", line=1)
        R.report.count("其它", "□", line=1)
        self.assertFalse(R.report.active())
        self.assertEqual(R.report.entries(), [])
        self.assertIn("未发现", R.report.format_text())

    def test_add_numbering_and_blank(self):
        R.report.begin("T1", "a.xml")
        R.report.set_fmt("docx")
        R.report.set_context(line=10)
        R.report.add("字体替换", "'A' 归一为 'B'", content="内容1")
        R.report.add("缺字字形", "CB1→字", line=12)
        e = R.report.entries()
        self.assertEqual(e[0]["line"], 10)          # 无 line 用 context
        self.assertEqual(e[0]["fmt"], "docx")
        txt = R.report.format_text(fmt="docx")
        self.assertTrue(txt.startswith("# 转换报告 T1 [docx]"))
        self.assertIn("1. [字体替换] [docx] XML 行 10：'A' 归一为 'B'", txt)
        self.assertIn("   （内容：内容1）", txt)
        self.assertIn("2. [缺字字形] [docx] XML 行 12：CB1→字", txt)
        self.assertIn("\n\n", txt)                  # 条间空行

    def test_key_dedupe(self):
        R.report.begin("T")
        R.report.set_fmt("docx")
        R.report.add("字体", "m", line=1, key=("c", "x", 1))
        R.report.add("字体", "m", line=1, key=("c", "x", 1))
        self.assertEqual(len(R.report.entries()), 1)

    def test_key_scoped_per_fmt(self):
        # 同名事件各格式各记（key 按格式隔离），合并视图再合成 fmt 标签
        R.report.begin("T")
        R.report.set_fmt("docx")
        R.report.add("注释", "m", key=("k",))
        R.report.set_fmt("html")
        R.report.add("注释", "m", key=("k",))
        e = R.report.entries()
        self.assertEqual(len(e), 2)
        self.assertEqual({x["fmt"] for x in e}, {"docx", "html"})
        self.assertIn("[docx|html]", R.report.format_text())

    def test_set_fmt_resets_context(self):
        # 换格式清行号上下文：避免上一格式的末行串到本格式
        R.report.begin("T")
        R.report.set_fmt("docx")
        R.report.set_context(line=99)
        R.report.add("c", "m")
        R.report.set_fmt("html")
        R.report.add("c2", "m2")
        e = R.report.entries()
        self.assertEqual(e[0]["line"], 99)
        self.assertIsNone(e[1]["line"])

    def test_sticky_seeded_in_per_fmt(self):
        R.report.add("主题兜底", "缺预设→出厂", sticky=True)   # begin 前登记
        R.report.begin("T")
        R.report.set_fmt("docx")
        R.report.add("内容改动", "改", line=5)
        d = R.report.format_text(fmt="docx")
        self.assertIn("[配置] XML 行 —：缺预设→出厂", d)
        m = R.report.format_text()
        self.assertTrue(m.startswith("# 转换报告 T [merged]"))
        self.assertIn("[配置]", m)

    def test_count_cap_and_lines(self):
        R.report.begin("T")
        R.report.set_fmt("docx")
        for i in range(1, 8):
            R.report.count("其它显示调整", "□", line=100 + i)
        txt = R.report.format_text(fmt="docx")
        self.assertIn("汇总：□×7（XML 行 101、102、103、104、105…）", txt)

    def test_count_merged_sum(self):
        R.report.begin("T")
        R.report.set_fmt("docx")
        R.report.count("其它显示调整", "□", line=1, n=2)
        R.report.set_fmt("pdf")
        R.report.count("其它显示调整", "□", line=2, n=3)
        m = R.report.format_text()
        self.assertIn("汇总：□×5", m)

    def test_content_single_line_truncate(self):
        R.report.begin("T")
        R.report.set_fmt("docx")
        R.report.add("c", "m", line=1, content="a\nb\tc" + "x" * 200)
        c = R.report.entries()[0]["content"]
        self.assertNotIn("\n", c)
        self.assertNotIn("\t", c)
        self.assertTrue(c.endswith("…"))

    def test_reset(self):
        R.report.begin("T")
        R.report.add("c", "m", line=1)
        R.report.reset()
        self.assertFalse(R.report.active())
        self.assertEqual(R.report.entries(), [])


class TestMergeConvertReports(unittest.TestCase):
    """per-fmt 报告合并：条目去重合并 fmt、计数求和并集行号、坏文件跳过。"""

    def setUp(self):
        R.report.reset()

    def tearDown(self):
        R.report.reset()

    def _write(self, d, name, text):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def _two_fmt(self):
        R.report.begin("T1")
        R.report.set_fmt("docx")
        R.report.add("字体替换", "'A' 归一为 'B'", line=10, content="c")
        R.report.count("其它显示调整", "□", line=11)
        dtext = R.report.format_text(fmt="docx")
        R.report.begin("T1")
        R.report.set_fmt("pdf")
        R.report.add("字体替换", "'A' 归一为 'B'", line=10, content="c")
        R.report.count("其它显示调整", "□", line=11)
        ptext = R.report.format_text(fmt="pdf")
        return dtext, ptext

    def test_merge_dedupe_and_sum(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        dtext, ptext = self._two_fmt()
        p1 = self._write(d, "a.txt", dtext)
        p2 = self._write(d, "b.txt", ptext)
        merged = R.merge_convert_reports([p1, p2])
        self.assertTrue(merged.startswith("# 转换报告 T1 [merged]"))
        self.assertIn("[docx|pdf]", merged)
        self.assertEqual(merged.count("1. [字体替换]"), 1)   # 去重
        self.assertIn("汇总：□×2", merged)

    def test_merge_skips_bad_file(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p = self._write(d, "x.txt",
                        "# 转换报告 T [docx]\n"
                        "1. [c] [docx] XML 行 1：m\n")
        out = R.merge_convert_reports([os.path.join(d, "missing.txt"), p])
        self.assertIn("XML 行 1：m", out)

    def test_merge_empty(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p = self._write(d, "e.txt",
                        "# 转换报告 T [docx]\n本文件未发现需记录的特殊处理。\n")
        self.assertEqual(R.merge_convert_reports([p]), "")


class TestFontEvents(unittest.TestCase):
    """字体类埋点：GDI 归一、按字回退、真 tofu。"""

    def setUp(self):
        R.report.reset()

    def tearDown(self):
        R.report.reset()

    def test_gaiji_note_canon(self):
        import io
        from contextlib import redirect_stdout
        from pycbeta import fonts
        R.report.begin("T")
        R.report.set_fmt("docx")
        with redirect_stdout(io.StringIO()):
            fonts._note_canon("FooFace", "BarFace")
        cats = [e["cat"] for e in R.report.entries()]
        self.assertIn("字体替换", cats)

    def test_fallback_and_tofu(self):
        from pycbeta.render_docx import DocxRenderer
        r = DocxRenderer(bookmarks=False)
        R.report.begin("T")
        R.report.set_fmt("docx")
        r._fb_cmap = {"Main": {ord("甲")}, "FB": {ord("乙")}}
        r.fallback_fonts = {"zh-Hant": ["FB"]}
        r.gaiji_lang = "zh-Hant"
        r._split_covered("甲乙丙", "Main")
        cats = {e["cat"] for e in R.report.entries()}
        self.assertIn("字体替换", cats)   # 乙 → 回退 FB
        self.assertIn("字体缺失", cats)   # 丙 无覆盖 → tofu


class TestStickyEvents(unittest.TestCase):
    """配置级兜底（sticky）：begin 前登记，begin 后进入每个 work。"""

    def setUp(self):
        R.report.reset()

    def tearDown(self):
        R.report.reset()

    def test_theme_fallback_sticky(self):
        import io
        from contextlib import redirect_stdout
        from pycbeta.theme import resolve_theme_css
        with redirect_stdout(io.StringIO()):
            resolve_theme_css("no-such-preset-xyz-12345")
        R.report.begin("T")
        R.report.set_fmt("docx")
        self.assertIn("主题兜底", [e["cat"] for e in R.report.entries()])

    def test_page_fallback_sticky(self):
        from pycbeta.theme import resolve_page
        resolve_page("NoSuchPageXYZ", {})
        R.report.begin("T")
        R.report.set_fmt("docx")
        self.assertIn("页面兜底", [e["cat"] for e in R.report.entries()])


class TestReviewEvents(unittest.TestCase):
    """注音待审按 work 首次登记（同一字跨 work 各记一次，work 内去重）。"""

    def setUp(self):
        R.report.reset()

    def tearDown(self):
        from pycbeta import annotate as A
        A.clear_reviewed()
        R.report.reset()

    def test_review_per_work(self):
        from pycbeta import annotate as A
        A.clear_reviewed()
        c = "\U0002BB20"                       # pypinyin 未收录（Ext-C）
        R.report.begin("T1")
        R.report.set_fmt("docx")
        A.auto_reading(c)
        A.auto_reading(c)                      # 同 work 去重
        cats = [e["cat"] for e in R.report.entries()]
        self.assertEqual(cats.count("注音待审"), 1)
        R.report.begin("T2")                   # 第二个 work：同字再现应再记
        R.report.set_fmt("docx")
        A.auto_reading(c)
        cats2 = [e["cat"] for e in R.report.entries()]
        self.assertEqual(cats2.count("注音待审"), 1)

    def test_full_text_no_review(self):
        from pycbeta import annotate as A
        A.clear_reviewed()
        c = "\U0002BB20"
        R.report.begin("T1")
        R.report.set_fmt("docx")
        A.auto_reading(c, review=False)        # 全文模式不登记
        self.assertNotIn("注音待审", [e["cat"] for e in R.report.entries()])


class TestContentEvents(unittest.TestCase):
    """内容改动类埋点冒烟：pre 去缩进、标题折行、去标题 No.、忽略脏数据、
    卷名去重、偈颂去引号、sic 丢弃。"""

    def setUp(self):
        R.report.reset()

    def tearDown(self):
        R.report.reset()

    @staticmethod
    def _work(body, title="t"):
        from pycbeta.model import Work
        return Work(id="T", source_file="",
                    metadata={"title": title, "author": ""}, body=body,
                    notes_by_n={}, apps=[], simplified=False)

    def _docx_cats(self, body, title="t", **kw):
        import tempfile
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.model import E, Text
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        R.report.begin("T")
        R.report.set_fmt("docx")
        DocxRenderer(bookmarks=False, **kw).render_work(
            self._work(body, title), d, "x.docx")
        return {e["cat"] for e in R.report.entries()}

    def test_pre_dedent(self):
        from pycbeta.model import E, Text
        body = [E(tag="p", attrs={"cb:type": "pre"},
                  children=[Text("\u3000\u3000\u3000\u3000緒　言\n\u3000\u3000學　史")])]
        self.assertIn("预排去缩进", self._docx_cats(body, pre_dedent=True))

    def test_title_wrap(self):
        from pycbeta.model import E, Text
        long = "太虛大師全書．第一編　佛法總學(第1卷-第26卷)"
        body = [E(tag="p", attrs={}, children=[Text("正文")])]
        self.assertIn("标题折行", self._docx_cats(body, title=long))

    def test_strip_head_no(self):
        from pycbeta.model import E, Text
        body = [E(tag="head", children=[Text("No. 1116-B 序")])]
        self.assertIn("去标题行首", self._docx_cats(body, strip_head_no=True))

    def test_ignore_xml_style(self):
        from pycbeta.model import E, Text
        body = [E(tag="p", attrs={"style": "margin-left:2em"},
                  children=[Text("正文")])]
        self.assertIn("忽略脏数据", self._docx_cats(body, ignore_xml_style=True))

    def test_juan_dedup(self):
        from pycbeta.model import E, Text
        body = [E(tag="juan", attrs={"fun": "open"},
                  children=[E(tag="jhead", children=[Text("T書")])])]
        self.assertIn("卷名去重", self._docx_cats(body, title="T書"))

    def test_verse_quote(self):
        from pycbeta.model import E, Text
        body = [E(tag="lg", children=[
            E(tag="l", children=[Text("「春眠不覺曉」")])])]
        self.assertIn("偈颂去引号",
                      self._docx_cats(body, verse_strip_quotes=True))

    def test_misc_count(self):
        import tempfile
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.model import E, Text
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        R.report.begin("T")
        R.report.set_fmt("docx")
        body = [E(tag="p", children=[Text("甲"), E(tag="unclear")])]
        DocxRenderer(bookmarks=False).render_work(self._work(body), d, "x.docx")
        self.assertIn("汇总：虚缺符 □×1", R.report.format_text(fmt="docx"))

    def test_notes_summary(self):
        from pycbeta.model import E, Text
        cats = self._docx_cats([E(tag="p", children=[Text("甲")])],
                               show_notes=False)
        self.assertIn("注释", cats)

    def test_sic_dropped_html(self):
        import tempfile
        from pycbeta.render_html import HtmlRenderer
        from pycbeta.model import E, Text
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        body = [E(tag="p", children=[Text("甲"), E(tag="sic", children=[Text("乙")])])]
        R.report.begin("T")
        R.report.set_fmt("html")
        HtmlRenderer().render_work(self._work(body), d)
        self.assertIn("内容丢弃", {e["cat"] for e in R.report.entries()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
