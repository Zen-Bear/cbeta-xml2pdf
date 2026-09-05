import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.cli import scaled_page_presets
from pycbeta.theme import FONT_SETS, Theme, _scale_font_size, combo_latin, resolve_page


class TestScaleHelper(unittest.TestCase):
    def test_pt_em(self):
        self.assertEqual(_scale_font_size("12pt", 1.5), "18pt")
        # em/% 相对单位不乘（随基准自动放大，乘了会双重放大）
        self.assertEqual(_scale_font_size("0.7em", 1.5), "0.7em")
        self.assertEqual(_scale_font_size("0.75em", 1.5), "0.75em")
        self.assertEqual(_scale_font_size("80%", 1.5), "80%")
        self.assertEqual(_scale_font_size("9pt", 4 / 3), "12pt")

    def test_non_numeric_kept(self):
        self.assertIsNone(_scale_font_size("bold", 1.5))
        self.assertIsNone(_scale_font_size(None, 1.5))
        self.assertIsNone(_scale_font_size("", 2.0))


class TestScaleFontSizes(unittest.TestCase):
    def test_tags_scaled(self):
        t = Theme().scale_font_sizes(1.5)
        # 注意：title 取 CSS 合并后的有效值（h1.title 30pt）；
        # note-ref 取用户 CSS 值（现为 0.75em，随资源走，旧 9pt 已作废）
        self.assertEqual(t.tags["p"]["font-size"], "18pt")
        self.assertEqual(t.tags["title"]["font-size"], "45pt")
        self.assertEqual(t.tags["footnote"]["font-size"], "13.5pt")
        self.assertEqual(t.tags["note-ref"]["font-size"], "0.75em")
        self.assertEqual(t.tags["verse"]["font-size"], "18pt")

    def test_font_family_untouched(self):
        t = Theme().scale_font_sizes(1.5)
        self.assertIn("font-family", t.tags["p"])
        self.assertIn("font-family", t.tags["kaiti"])

    def test_raw_css_override_appended(self):
        t = Theme().scale_font_sizes(1.5)
        self.assertIn("p { font-size: 18pt; }", t.raw_css)
        self.assertIn("div.lg { font-size: 18pt; }", t.raw_css)

    def test_noop(self):
        t = Theme()
        before = t.raw_css
        t.scale_font_sizes(1.0)
        self.assertEqual(t.raw_css, before)
        self.assertEqual(t.tags["p"]["font-size"], "12pt")

    def test_invalid(self):
        for bad in (0, -1, "x"):
            with self.assertRaises(ValueError):
                Theme().scale_font_sizes(bad)

    def test_hans_then_scale(self):
        t = Theme()
        t.apply_font_set("default", lang="zh-Hans")
        t.scale_font_sizes(1.5)
        self.assertEqual(t.tags["p"]["font-size"], "18pt")
        self.assertIn("SimSun", t.tags["p"]["font-family"])

    def test_single_source_body_pin(self):
        # P1 回归：body/pin 来自 font_sets，rend 简体可用
        t = Theme()
        self.assertIn("font-family", t.tags["body"])
        self.assertIn("font-family", t.tags["pin"])
        h = Theme()
        h.apply_font_set("default", lang="zh-Hans")
        self.assertIn("KaiTi", h.tags["kaiti"]["font-family"])


class TestLatinFont(unittest.TestCase):
    def test_combo_latin_pair(self):
        self.assertIn("latin", FONT_SETS["default"])
        self.assertEqual(combo_latin(None, "default", "zh-Hant"), "Calibri")
        self.assertEqual(combo_latin(None, "default", "zh-Hans"), "Calibri")

    def test_combo_latin_custom_and_fallback(self):
        sets = {"default": {"latin": ["Times", "SimSun"]}}
        self.assertEqual(combo_latin(sets, "default", "zh-Hant"), "Times")
        self.assertEqual(combo_latin(sets, "default", "zh-Hans"), "SimSun")
        self.assertEqual(combo_latin({}, "default", "zh-Hant"), "Calibri")
        self.assertEqual(combo_latin({"other": {}}, "nope", "zh-Hans"), "Calibri")
        self.assertEqual(combo_latin({"default": {"latin": "Solo"}}, "default", "zh-Hant"), "Solo")

    def test_latin_not_a_tag(self):
        # 组合级 latin 不进入标签体系（无 CSS 规则、无 tags 条目）
        t = Theme()
        self.assertNotIn("latin", t.tags)
        h = Theme()
        h.apply_font_set("default", lang="zh-Hans")
        self.assertNotIn("latin", h.tags)

    def test_resolve_page_default(self):
        # pages 不再自带 latin_font 时回退 Calibri（旧配置自带值仍优先）
        self.assertEqual(resolve_page("a4", {"a4": {"size": [210, 297]}})["latin_font"], "Calibri")
        self.assertEqual(
            resolve_page("a4", {"a4": {"size": [210, 297], "latin_font": "OldStyle"}})["latin_font"],
            "OldStyle")

    def test_docx_renderer_precedence(self):
        # 显式参数 > 页面方案 > Calibri
        from pycbeta.render_docx import DocxRenderer
        pages = {"a4": {"size": [210, 297],
                        "margins": {"top": 25.4, "right": 25.4, "bottom": 25.4, "left": 25.4},
                        "doc_size": 11, "latin_font": "PageFont"}}
        self.assertEqual(DocxRenderer(page_presets=pages).latin_font, "PageFont")
        self.assertEqual(DocxRenderer(page_presets=pages, latin_font="ComboFont").latin_font,
                         "ComboFont")
        self.assertEqual(DocxRenderer().latin_font, "Calibri")


class TestScaledPagePresets(unittest.TestCase):
    def test_doc_size_follows(self):
        pages = {"a4": {"size": [210, 297], "doc_size": 11, "latin_font": "Calibri"}}
        out = scaled_page_presets(pages, 1.5)
        self.assertEqual(out["a4"]["doc_size"], 16.5)
        self.assertEqual(pages["a4"]["doc_size"], 11)  # 不改原配置

    def test_missing_doc_size(self):
        out = scaled_page_presets({"x": {"size": [1, 2]}}, 2.0)
        self.assertNotIn("doc_size", out["x"])


class TestDescendantSelector(unittest.TestCase):
    CSS = ("p.head { color: #0000a0; }\n"
           "div.div-xu p.head { color: #000; }\n"
           "div.div-xu p.head span.note-inline { color: #111; }\n"
           "p.head[data-head-level=\"1\"] { font-size: 16pt; }\n")

    def test_parse_compounds(self):
        t = Theme.from_css(self.CSS)
        self.assertEqual(t.tags["head"]["color"], "#0000a0")
        self.assertEqual(len(t.compounds), 1)
        anc, tgt, props, sel = t.compounds[0]
        self.assertEqual((anc, tgt), ("div-xu", "head"))
        # CSS 未指定字体 → font_sets.default 组合键补上（Hant 第一项）
        self.assertEqual(props, {"color": "#000",
                                 "font-family": "標楷體, KaiTi, serif"})
        # 三段及以上、属性选择器不进 tags 也不进 compounds（HTML 靠原文 CSS）
        self.assertNotIn("span.note-inline", [c[1] for c in t.compounds])

    def test_run_override(self):
        t = Theme.from_css(self.CSS)
        # 序内 head：后代规则覆盖 p.head 蓝色
        rpr = t.docx_run("div-xu", "head", base_pt=14.0)
        self.assertIn('w:val="000000"', rpr)
        self.assertNotIn("0000a0", rpr)
        # 非序 head：保持蓝色
        rpr = t.docx_run("p", "head", base_pt=14.0)
        self.assertIn("0000a0", rpr)

    def test_para_override(self):
        t = Theme.from_css("div.div-xu { margin-top: 1em; }\n"
                           "div.div-xu p.head { margin-top: 3em; }\n")
        ppr = t.docx_para("div-xu", "head")
        self.assertIn('w:before="840"', ppr)  # 3em × 14pt × 20（head 默认字号 14pt）

    def test_css_roundtrip(self):
        t = Theme.from_css(self.CSS)
        css = t.css()
        self.assertIn("div.div-xu p.head", css)

    def test_docx_run_in_xu(self):
        # 端到端：div-xu 栈内的 head run 取后代规则（不用默认 CSS，避免随样式文件改动而 brittle）
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.theme import Theme as _T
        r = DocxRenderer(theme=_T.from_css("div.div-xu p.head { color: #123456; }"))
        r._div_stack = ["div-xu"]
        r._tag_stack = ["head"]
        out = r._run("新譯大乘入楞伽經序", *r._current_tag())
        self.assertIn('w:val="123456"', out)


class TestHex6(unittest.TestCase):
    def test_expand_and_pass(self):
        from pycbeta.theme import _hex6
        self.assertEqual(_hex6("#000"), "000000")
        self.assertEqual(_hex6("#abc"), "aabbcc")
        self.assertEqual(_hex6("#0000a0"), "0000a0")
        self.assertEqual(_hex6("555555"), "555555")

    def test_invalid_skipped(self):
        from pycbeta.theme import _hex6
        self.assertIsNone(_hex6(None))
        self.assertIsNone(_hex6(""))
        self.assertIsNone(_hex6("red"))
        self.assertIsNone(_hex6("#12"))
        self.assertIsNone(_hex6("#gggggg"))


class TestFontSetCompound(unittest.TestCase):
    SETS = {"default": {"div.div-xu p.head": ["HantFont, serif", "HansFont, serif"]}}

    def test_override_and_no_junk(self):
        from pycbeta.theme import Theme
        t = Theme.from_css("div.div-xu p.head { color: #000; }\n")
        t.apply_font_set("default", lang="zh-Hant", font_sets=self.SETS)
        got = [(a, tg, p.get("font-family")) for a, tg, p, _s in t.compounds]
        self.assertIn(("div-xu", "head", "HantFont, serif"), got)
        self.assertNotIn("div.div-xu p.head", t.tags)  # 不写 junk 标签
        self.assertIn("div.div-xu p.head", t.raw_css)  # HTML/PDF 跟随覆盖

    def test_append_when_missing(self):
        from pycbeta.theme import Theme
        t = Theme.from_css("p.head { color: #0000a0; }\n")
        t.apply_font_set("default", lang="zh-Hans", font_sets=self.SETS)
        got = [(a, tg, p.get("font-family")) for a, tg, p, _s in t.compounds]
        self.assertIn(("div-xu", "head", "HansFont, serif"), got)

    def test_invalid_key_skipped(self):
        from pycbeta.theme import Theme
        t = Theme.from_css("p.head { color: #0000a0; }\n")
        n_comp = len(t.compounds)
        t.apply_font_set("default", lang="zh-Hant",
                         font_sets={"default": {"foo bar": "X, serif",
                                                "a b c": "Y, serif"}})
        self.assertEqual(len(t.compounds), n_comp)
        self.assertNotIn("foo bar", t.tags)
        self.assertNotIn("a b c", t.tags)

    def test_docx_run_uses_switched_font(self):
        from pycbeta.theme import Theme
        from pycbeta.render_docx import DocxRenderer
        t = Theme.from_css("div.div-xu p.head { color: #000; }\n")
        t.apply_font_set("default", lang="zh-Hant", font_sets=self.SETS)
        r = DocxRenderer(theme=t)
        r._div_stack = ["div-xu"]
        r._tag_stack = ["head"]
        out = r._run("序", *r._current_tag())
        self.assertIn('w:eastAsia="HantFont"', out)


    def test_css_specified_wins_over_default(self):
        # CSS 文件明确指定字体 → font_sets.default 不覆盖
        from pycbeta.theme import Theme
        t = Theme.from_css("div.div-xu p.head { color: #000; font-family: CustomFont, serif; }\n")
        got = [(a, tg, pr.get("font-family")) for a, tg, pr, _s in t.compounds]
        self.assertIn(("div-xu", "head", "CustomFont, serif"), got)

if __name__ == "__main__":
    unittest.main()
