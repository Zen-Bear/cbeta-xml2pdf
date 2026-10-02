import os
import json
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.theme import Theme, _scale_font_size, _scale_font_dict, strip_head_no, \
    resolve_font_vars, resolve_page, resolve_theme_css, _abs_pt


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


class TestScaleFontDict(unittest.TestCase):
    def test_pt_scaled_in_place(self):
        d = {"font-size": "12pt", "font-family": "X"}
        _scale_font_dict(d, 1.5)
        self.assertEqual(d, {"font-size": "18pt", "font-family": "X"})

    def test_relative_and_missing_untouched(self):
        for fs in ("0.75em", "80%", "bold", None):
            d = {"font-family": "X"}
            if fs is not None:
                d["font-size"] = fs
            _scale_font_dict(d, 1.5)
            self.assertEqual(d.get("font-size"), fs)


class TestStripHeadNo(unittest.TestCase):
    def _t(self, text, line=None):
        from pycbeta.model import Text
        return Text(text, line=line) if line else Text(text)

    def test_token_and_lstrip(self):
        from pycbeta.model import Lb
        out, tok = strip_head_no([self._t("No. 1116-B"), Lb(n="x"), self._t(" 序")])
        self.assertEqual(tok, "No. 1116-B")
        self.assertEqual([(type(n).__name__, getattr(n, "text", None)) for n in out],
                         [("Lb", None), ("Text", "序")])

    def test_empty_remainder_dropped(self):
        out, tok = strip_head_no([self._t("No. 349")])
        self.assertEqual(tok, "No. 349")
        self.assertEqual(out, [])

    def test_no_match_untouched(self):
        kids = [self._t("序"), self._t("No. 1116-A经云")]
        out, tok = strip_head_no(kids)
        self.assertEqual(tok, "")
        self.assertIs(out[0], kids[0])  # 非变异：原节点原样返回
        self.assertIs(out[1], kids[1])

    def test_input_not_mutated(self):
        from pycbeta.model import Lb
        kids = [self._t("No. 1116-B"), Lb(n="x"), self._t(" 序")]
        strip_head_no(kids)
        self.assertEqual([n.text for n in kids if hasattr(n, "text")],
                         ["No. 1116-B", " 序"])


class TestScaleFontSizes(unittest.TestCase):
    def test_tags_scaled(self):
        t = Theme().scale_font_sizes(1.5)
        # 注意：title 取 CSS 合并后的有效值（h1.title 26pt）；
        # p 无 font-size（跟随 body，单源），body 缩放带动正文
        self.assertEqual(t.tags["body"]["font-size"], "18pt")
        self.assertIsNone((t.tags.get("p") or {}).get("font-size"))
        self.assertEqual(t.tags["title"]["font-size"], "39pt")
        # footnote 出厂已是 0.75em：字符串不动，有效值随放大的 base 走
        self.assertEqual(t.tags["footnote"]["font-size"], "0.75em")
        self.assertIn('w:val="27"', t.docx_run("footnote"))
        self.assertEqual(t.tags["note-ref"]["font-size"], "0.75em")
        self.assertIsNone((t.tags.get("verse") or {}).get("font-size"))  # 跟随 body
        self.assertEqual(t.tags["verse"]["color"], "#008040")

    def test_font_family_untouched(self):
        t = Theme().scale_font_sizes(1.5)
        self.assertIn("font-family", t.tags["p"])
        self.assertIn("font-family", t.tags["kaiti"])

    def test_raw_css_override_appended(self):
        t = Theme().scale_font_sizes(1.5)
        self.assertIn("body { font-size: 18pt; }", t.raw_css)
        self.assertIn("h1.title { font-size: 39pt; }", t.raw_css)

    def test_noop(self):
        t = Theme()
        before = t.raw_css
        t.scale_font_sizes(1.0)
        self.assertEqual(t.raw_css, before)
        self.assertEqual(t.tags["body"]["font-size"], "12pt")

    def test_invalid(self):
        for bad in (0, -1, "x"):
            with self.assertRaises(ValueError):
                Theme().scale_font_sizes(bad)

    def test_hans_then_scale(self):
        t = Theme(lang="zh-Hans")
        t.scale_font_sizes(1.5)
        self.assertEqual(t.tags["body"]["font-size"], "18pt")
        self.assertIn("SimSun", t.tags["p"]["font-family"])

    def test_compounds_scaled(self):
        # 第二循环覆盖：出厂 div.div-xu p.head 20pt → 30pt
        t = Theme().scale_font_sizes(1.5)
        hits = [c for c in t.compounds
                if c[0] == "div-xu" and c[1] == "head"]
        self.assertTrue(hits, "出厂应有 div-xu/head compound")
        self.assertEqual(hits[0][2]["font-size"], "30pt")

    def test_single_source_body_pin(self):
        # 字体来自 CSS :root 变量（繁简双栏），非 font_sets
        t = Theme()
        self.assertIn("新細明體", t.tags["body"]["font-family"])
        self.assertIn("新細明體", t.tags["pin"]["font-family"])
        h = Theme(lang="zh-Hans")
        self.assertIn("宋体", h.tags["p"]["font-family"])
        self.assertIn("KaiTi", h.tags["kaiti"]["font-family"])


class TestPreFontSize(unittest.TestCase):
    """预排段字号写死小四 12pt，不跟随 body（纸张预设调正文时目录不变）。"""

    def test_pre_font_size_12pt(self):
        from pycbeta.theme import Theme
        t = Theme()
        self.assertEqual(t.tags["pre"]["font-size"], "12pt")
        self.assertIn('w:sz w:val="24"', t.docx_run("p", "pre"))

    def test_pre_decoupled_from_page_typography(self):
        from pycbeta.theme import Theme, apply_page_typography
        t = Theme()
        apply_page_typography(t, "a4", {"a4": {"body_font_size": "14pt"}})
        self.assertEqual(t.tags["body"]["font-size"], "14pt")
        self.assertEqual(t.tags["pre"]["font-size"], "12pt")   # 不跟随
        self.assertIn('w:sz w:val="24"', t.docx_run("p", "pre"))


class TestFontVars(unittest.TestCase):
    CSS = (":root { --font-p: HantP; --font-title: HantT; }\n"
           'html[lang="zh-Hans"] { --font-p: HansP; }\n'
           "p { font-size: 12pt; }\n"
           "h1.title { font-family: var(--font-title); font-size: 30pt; }\n")

    def test_collect_both_columns(self):
        hant, hans = resolve_font_vars(self.CSS)
        self.assertEqual(hant["--font-p"], "HantP")
        self.assertEqual(hans["--font-p"], "HansP")
        self.assertNotIn("--font-title", hans)  # 未覆盖栏继承 :root

    def test_hans_falls_back_to_hant(self):
        t = Theme.from_css(self.CSS, lang="zh-Hans")
        self.assertEqual(t.tags["p"]["font-family"], "HansP")
        self.assertEqual(t.tags["title"]["font-family"], "HantT")

    def test_var_substitution_in_rules(self):
        t = Theme.from_css(self.CSS)
        self.assertEqual(t.tags["title"]["font-family"], "HantT")
        # 字面量仍优先于变量填充
        t2 = Theme.from_css("p { font-family: Literal; }\n" + self.CSS)
        self.assertEqual(t2.tags["p"]["font-family"], "Literal")

    def test_var_fallback_value(self):
        t = Theme.from_css(":root { }\np { font-family: var(--nope, FB); }\n")
        self.assertEqual(t.tags["p"]["font-family"], "FB")

    def test_def_selector_mapping(self):
        from pycbeta.theme import _SELECTOR_TAGS, FONT_VAR_TAGS
        self.assertEqual(_SELECTOR_TAGS["cb:def"], "def")
        self.assertIn("def", FONT_VAR_TAGS)
        t = Theme.from_css(
            ":root { --font-def: 新細明體, PMingLiU; }\n"
            "cb:def { font-size: 0.9em; }\n")
        self.assertEqual(t.tags["def"]["font-family"],
                         "新細明體, PMingLiU")
        self.assertEqual(t.tags["def"]["font-size"], "0.9em")


class TestLatinFont(unittest.TestCase):
    def test_latin_var_pair(self):
        t = Theme()
        self.assertEqual(t.font_var("latin", "?"), "Calibri")
        h = Theme(lang="zh-Hans")
        self.assertEqual(h.font_var("latin", "?"), "Calibri")
        self.assertEqual(Theme().font_var("nope", "D"), "D")

    def test_latin_not_a_tag(self):
        # --font-latin 不进入标签体系（无 CSS 规则、无 tags 条目）
        t = Theme()
        self.assertNotIn("latin", t.tags)

    def test_resolve_page_default(self):
        # pages 不再自带 latin_font 时回退 Calibri（旧配置自带值仍优先）
        self.assertEqual(resolve_page("a4", {"a4": {"size": [210, 297]}})["latin_font"], "Calibri")
        self.assertEqual(
            resolve_page("a4", {"a4": {"size": [210, 297], "latin_font": "OldStyle"}})["latin_font"],
            "OldStyle")

    def test_resolve_page_custom_margins(self):
        # custom_margins（用户改的）> margins（预设自带）> 25.4 默认
        m = resolve_page("a4", {"a4": {"margins": {"top": 25.4, "right": 25.4,
                                                   "bottom": 25.4, "left": 25.4},
                                       "custom_margins": {"top": 20.0}}})["margins"]
        self.assertEqual(m["top"], 20.0)
        self.assertEqual(m["right"], 25.4)
        m2 = resolve_page("a4", {"a4": {}})["margins"]
        self.assertEqual(m2["top"], 25.4)

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


class TestBasePtSingleSource(unittest.TestCase):
    def test_abs_pt(self):
        self.assertEqual(_abs_pt("12pt", 12.0), 12.0)
        self.assertEqual(_abs_pt("1.5em", 12.0), 18.0)
        self.assertEqual(_abs_pt("75%", 12.0), 9.0)
        self.assertIsNone(_abs_pt("abc", 12.0))
        self.assertIsNone(_abs_pt("", 12.0))

    def test_base_pt_single_source(self):
        from pycbeta.theme import Theme
        # body 单源：p 无字号走 body；都无回 12.0；doc 默认回 11
        t = Theme.from_css("body { font-size: 14pt; }\np { color: #000; }\n")
        self.assertEqual(t.base_pt(), 14.0)
        t2 = Theme.from_css("p { font-size: 12pt; }\n")
        self.assertEqual(t2.base_pt(), 12.0)
        t3 = Theme.from_css("p { color: #000; }\n")
        self.assertEqual(t3.base_pt(), 12.0)          # 无 body/p 字号 → 默认 fallback 12
        self.assertEqual(t3.base_pt(fallback=11), 11.0)
        # doc 默认跟 base（未知回 11，保持旧 pages 默认行为）
        from pycbeta.render_docx import DocxRenderer
        self.assertEqual(DocxRenderer(theme=t).doc_size, 14.0)
        self.assertEqual(DocxRenderer(theme=t3).doc_size, 11.0)

    def test_apply_page_typography(self):
        from pycbeta.theme import Theme, apply_page_typography
        pages = {"16开": {"body_font_size": "10.5pt", "body_line_height": 1.5},
                 "MyPage": {"body_font_size": "11pt"},
                 "a4": {}}
        t = Theme.from_css("body { font-size: 12pt; line-height: 1.4; }\n")
        apply_page_typography(t, "16开", pages)
        self.assertEqual(t.tags["body"]["font-size"], "10.5pt")
        self.assertEqual(t.tags["body"]["line-height"], "1.5")
        self.assertEqual(t.base_pt(), 10.5)
        # 大小写不敏感（拉丁名）
        t2 = Theme.from_css("body { font-size: 12pt; line-height: 1.4; }\n")
        apply_page_typography(t2, "MYPAGE", pages)
        self.assertEqual(t2.tags["body"]["font-size"], "11pt")
        self.assertEqual(t2.tags["body"]["line-height"], "1.4")  # 未写不动
        # 无键不动
        t3 = Theme.from_css("body { font-size: 12pt; line-height: 1.4; }\n")
        apply_page_typography(t3, "a4", pages)
        self.assertEqual(t3.tags["body"]["font-size"], "12pt")
        # 非法值忽略并保留原值
        t4 = Theme.from_css("body { font-size: 12pt; line-height: 1.4; }\n")
        apply_page_typography(t4, "x", {"x": {"body_font_size": "abc",
                                              "body_line_height": "??"}})
        self.assertEqual(t4.tags["body"]["font-size"], "12pt")
        self.assertEqual(t4.tags["body"]["line-height"], "1.4")

    def test_docx_follows_page_typography(self):
        from pycbeta.theme import Theme
        from pycbeta.render_docx import DocxRenderer
        t = Theme.from_css("body { font-size: 12pt; }\np { color: #000; }\n")
        from pycbeta.theme import apply_page_typography
        apply_page_typography(t, "16开", {"16开": {"body_font_size": "10.5pt",
                                                  "body_line_height": 1.5}})
        r = DocxRenderer(theme=t)
        self.assertEqual(r.doc_size, 10.5)  # 文档默认跟纸张
        self.assertIn('w:val="21"/>', t.docx_run("p"))  # 正文 10.5pt

    def test_explicit_p_beats_page(self):
        from pycbeta.theme import Theme, apply_page_typography
        # p 亲笔写过字号 → 纸张只改 body，不动 p（CSS 语义：p 规则胜继承）
        t = Theme.from_css("body { font-size: 12pt; }\n"
                           "p { font-size: 14pt; }\n")
        self.assertIn(("p", "font-size"), t._explicit)
        self.assertNotIn(("p", "font-size"), Theme()._explicit)  # DEFAULT 不算
        apply_page_typography(t, "16开", {"16开": {"body_font_size": "10.5pt",
                                                  "body_line_height": 1.5}})
        self.assertEqual(t.tags["body"]["font-size"], "10.5pt")
        self.assertEqual(t.tags["p"]["font-size"], "14pt")
        # 行距同理：没写过才跟
        self.assertEqual(t.tags["p"].get("line-height"), "1.5")

    def test_name_case_insensitive(self):
        from pycbeta.theme import resolve_page
        pages = {"tablet9": {"size": [121, 194],
                             "margins": {"top": 10, "right": 10,
                                         "bottom": 10, "left": 10}}}
        # 大小写通吃，且用用户边距而非回退默认
        for name in ("tablet9", "Tablet9", "TABLET9"):
            cfg = resolve_page(name, pages)
            self.assertEqual(cfg["size"], [121, 194])
            self.assertEqual(cfg["margins"]["top"], 10)
        # 内置键同样大小写不敏感
        self.assertEqual(resolve_page("A4", {})["size"], [210, 297])


class TestDescendantSelector(unittest.TestCase):
    CSS = ("p.head { color: #0000a0; }\n"
           "div.div-xu p.head { color: #000; }\n"
           "div.div-xu p.head span.note-inline { color: #111; }\n"
           "p.head[data-head-level=\"1\"] { font-size: 16pt; }\n")

    def test_parse_compounds(self):
        t = Theme.from_css(self.CSS)
        self.assertEqual(t.tags["head"]["color"], "#0000a0")
        # 两段 + 三段后代各一条（三段现支持：CSS 后代语义，祖先按序）
        self.assertEqual(len(t.compounds), 2)
        two = [c for c in t.compounds if c[0] == "div-xu" and c[1] == "head"]
        self.assertEqual(len(two), 1)
        self.assertEqual(two[0][2], {"color": "#000"})
        deep = [c for c in t.compounds if c[1] == "note-inline"]
        self.assertEqual(len(deep), 1)
        self.assertEqual(deep[0][0], ("div-xu", "head"))
        self.assertEqual(deep[0][2], {"color": "#111"})
        # 属性选择器不进 compounds（HTML 靠原文 CSS）
        self.assertNotIn('p.head[data-head-level="1"]',
                         [c[3] for c in t.compounds])

    def test_deep_descendant_applies(self):
        t = Theme.from_css(self.CSS)
        rpr = t.docx_run("div-xu", "head", "note-inline", base_pt=14.0)
        self.assertIn("111111", rpr)

    def test_deep_descendant_requires_ancestors(self):
        t = Theme.from_css(self.CSS)
        # 缺 div-xu 祖先 → 三段规则不生效（层叠到 head 的 #000 或 p.head 蓝）
        rpr = t.docx_run("head", "note-inline", base_pt=14.0)
        self.assertNotIn("111111", rpr)

    def test_head_inline_note_rule(self):
        from pycbeta.theme import Theme
        t = Theme()   # 出厂 pdf_docx.css
        hits = [c for c in t.compounds
                if c[0] == "head" and c[1] == "doube-line-note"]
        self.assertTrue(hits, "出厂应有 p.head .doube-line-note 规则")
        self.assertEqual(hits[0][2].get("font-size"), "0.6em")
        self.assertEqual(hits[0][2].get("font-weight"), "normal")
        rpr = t.docx_run("head", "doube-line-note", base_pt=20.0)
        self.assertIn('w:sz w:val="24"', rpr)   # 0.6em × 20pt = 12pt
        self.assertNotIn("<w:b/>", rpr)         # 不继承标题粗体

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
        self.assertIn('w:before="720"', ppr)  # 3em × 12pt × 20（head 无字号 → 跟随 body 12pt）

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


class TestFontVarCompound(unittest.TestCase):
    def test_compound_filled_from_vars(self):
        from pycbeta.theme import Theme
        t = Theme.from_css(":root { --font-div-xu-head: VFont, serif; }\n"
                           "div.div-xu p.head { color: #000; }\n")
        got = [(a, tg, p.get("font-family")) for a, tg, p, _s in t.compounds]
        self.assertIn(("div-xu", "head", "VFont, serif"), got)

    def test_compound_hans_column(self):
        from pycbeta.theme import Theme
        t = Theme.from_css(":root { --font-div-xu-head: HantF; }\n"
                           'html[lang="zh-Hans"] { --font-div-xu-head: HansF; }\n',
                           lang="zh-Hans")
        got = [(a, tg, p.get("font-family")) for a, tg, p, _s in t.compounds]
        self.assertIn(("div-xu", "head", "HansF"), got)

    def test_css_specified_wins_over_default(self):
        # CSS 文件明确指定字体 → 变量填充不覆盖
        from pycbeta.theme import Theme
        t = Theme.from_css("div.div-xu p.head { color: #000; font-family: CustomFont, serif; }\n")
        got = [(a, tg, pr.get("font-family")) for a, tg, pr, _s in t.compounds]
        self.assertIn(("div-xu", "head", "CustomFont, serif"), got)

    def test_docx_run_uses_var_font(self):
        from pycbeta.theme import Theme
        from pycbeta.render_docx import DocxRenderer
        t = Theme.from_css(":root { --font-div-xu-head: VFont, serif; }\n"
                           "div.div-xu p.head { color: #000; }\n")
        r = DocxRenderer(theme=t)
        r._div_stack = ["div-xu"]
        r._tag_stack = ["head"]
        out = r._run("序", *r._current_tag())
        self.assertIn('w:eastAsia="VFont"', out)


class TestResolveThemeCss(unittest.TestCase):
    def test_empty_and_factory(self):
        from pycbeta.theme import resolve_theme_css
        self.assertEqual(resolve_theme_css("")[0], None)
        self.assertEqual(resolve_theme_css("pdf_docx.css")[0], None)
        self.assertEqual(resolve_theme_css(None)[0], None)

    def test_builtin_preset_by_name(self):
        import os
        import shutil
        import tempfile
        import pycbeta.theme as _theme
        from pycbeta.theme import list_presets, resolve_theme_css
        root = tempfile.mkdtemp()
        try:
            # 内置组退役后查找仍认旧名（向后兼容）：mock 内置目录
            bdir = os.path.join(root, "b")
            os.makedirs(bdir)
            with open(os.path.join(bdir, "old.css"), "w",
                      encoding="utf-8") as f:
                f.write("/* x */\n")
            import unittest.mock as mock
            nodir = os.path.join(root, "nodir")  # 不创建：用户目录缺席
            with mock.patch.object(_theme, "BUILTIN_PRESETS_DIR", bdir), \
                    mock.patch.object(_theme, "user_presets_dir",
                                      lambda root=None: nodir):
                found = [n for k, n, _p in list_presets()
                         if k == "builtin"]
                self.assertIn("old", found)
                path, label = resolve_theme_css("old")
                self.assertTrue(path and os.path.isfile(path))
                self.assertIn("内置", label)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_missing_falls_back_with_warning(self):
        import io
        from contextlib import redirect_stdout
        from pycbeta.theme import resolve_theme_css
        buf = io.StringIO()
        with redirect_stdout(buf):
            path, label = resolve_theme_css("no-such-preset-xyz")
        self.assertIsNone(path)
        self.assertIn("内置", label)
        self.assertIn("no-such-preset-xyz", buf.getvalue())


class TestRunConfig(unittest.TestCase):
    """run.json 组合单：缺省/补键/非法/旧格式/槽解析。"""

    def test_missing_file_gives_defaults_silently(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        from pycbeta.theme import load_run_config, DEFAULT_RUN_CONFIG
        root = tempfile.mkdtemp()
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                run = load_run_config(None, root)  # 默认路径不存在 → 静默缺省
            self.assertEqual({k: run[k] for k in DEFAULT_RUN_CONFIG},
                             DEFAULT_RUN_CONFIG)
            self.assertEqual(buf.getvalue(), "")
            # 显式指定的缺失文件 → OSError（CLI 转 ap.error）
            with self.assertRaises(OSError):
                load_run_config(os.path.join(root, "nope.json"))
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_missing_keys_filled(self):
        import json
        import tempfile
        from pycbeta.theme import load_run_config, DEFAULT_RUN_CONFIG
        fd, fn = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pdf-docx-user-theme": "mine"}, f)
            run = load_run_config(fn)
            self.assertEqual(run["pdf-docx-user-theme"], "mine")
            self.assertEqual(run["pdf-docx-theme"],
                             DEFAULT_RUN_CONFIG["pdf-docx-theme"])
        finally:
            os.remove(fn)

    def test_bad_json_raises(self):
        import tempfile
        from pycbeta.theme import load_run_config
        fd, fn = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("{not json")
            with self.assertRaises(ValueError):
                load_run_config(fn)
        finally:
            os.remove(fn)

    def test_legacy_snapshot_rejected(self):
        import json
        import tempfile
        from pycbeta.theme import load_run_config
        fd, fn = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"output": {}, "theme": "x"}, f)
            with self.assertRaises(ValueError) as ctx:
                load_run_config(fn)
            self.assertIn("run.json", str(ctx.exception))
        finally:
            os.remove(fn)

    def test_base_config_factory_and_relative(self):
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout
        from pycbeta.theme import (load_run_config, resolve_base_config,
                                   _PRESETS_PATH)
        self.assertEqual(resolve_base_config({}, None), _PRESETS_PATH)
        root = tempfile.mkdtemp()
        try:
            cfg = os.path.join(root, "mine.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"output": {}}, f)
            run = load_run_config(None, root)  # 无文件 → 缺省
            run["config-json"] = "mine.json"
            self.assertEqual(resolve_base_config(run, root), cfg)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run["config-json"] = "nope.json"
                self.assertEqual(resolve_base_config(run, root),
                                 _PRESETS_PATH)
            self.assertIn("不存在", buf.getvalue())
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_config_arg_run_mode(self):
        import json
        import tempfile
        from pycbeta.theme import resolve_config_arg
        fd, fn = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pdf-docx-user-theme": "mine.css",
                           "config-json": "config.json"}, f)
            run, rdir = resolve_config_arg(fn)
            self.assertEqual(run["pdf-docx-user-theme"], "mine.css")
            self.assertEqual(rdir, os.path.dirname(os.path.abspath(fn)))
        finally:
            os.remove(fn)

    def test_resolve_config_arg_base_mode(self):
        import json
        import tempfile
        from pycbeta.theme import (resolve_config_arg, resolve_effective_config,
                                   DEFAULT_RUN_CONFIG)
        fd, fn = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"output": {"t2s": True}, "default_page": "a5"}, f)
            run, rdir = resolve_config_arg(fn)
            self.assertEqual(os.path.abspath(run["config-json"]),
                             os.path.abspath(fn))
            for k in DEFAULT_RUN_CONFIG:
                if k != "config-json":
                    self.assertEqual(run[k], DEFAULT_RUN_CONFIG[k])
            eff = resolve_effective_config(run, rdir)
            self.assertTrue(eff["output"]["t2s"])
            self.assertEqual(eff["default_page"], "a5")
        finally:
            os.remove(fn)

    def test_resolve_config_arg_default_and_bad(self):
        import tempfile
        from pycbeta.theme import resolve_config_arg, DEFAULT_RUN_CONFIG
        root = tempfile.mkdtemp()
        try:
            run, rdir = resolve_config_arg(None, root)  # 无 run.json → 全缺省
            self.assertEqual({k: run[k] for k in DEFAULT_RUN_CONFIG},
                             DEFAULT_RUN_CONFIG)
            self.assertEqual(rdir, os.path.abspath(root))
            bad = os.path.join(root, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("[1, 2]")
            with self.assertRaises(ValueError):
                resolve_config_arg(bad)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_html_user_theme_appends(self):
        import tempfile
        from pycbeta.theme import resolve_html_base_css
        d = tempfile.mkdtemp()
        try:
            up = os.path.join(d, "u.css")
            with open(up, "w", encoding="utf-8") as f:
                f.write("div.lg-cell{display:block}")
            css = resolve_html_base_css({}, None, user=up)
            self.assertIn("cbetarc", css)  # 官方基底仍在
            self.assertIn("div.lg-cell{display:block}", css)  # 增量追加在后
            css2 = resolve_html_base_css({}, None)
            self.assertIn("cbetarc", css2)
            self.assertNotIn("lg-cell{display:block}", css2)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_html_base_defaults_official(self):
        from pycbeta.theme import resolve_html_base_css
        css = resolve_html_base_css({}, None)
        self.assertIn("cbetarc", css)
        self.assertNotIn("--font-body", css)
        # 标题内正文夹注不跟标题放大/加粗（与 pdf_docx.css 同口径）
        self.assertIn(".head .doube-line-note", css)

    def test_placeholder_noop(self):
        import io
        from contextlib import redirect_stdout
        from pycbeta.theme import check_run_placeholders
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertIsNone(
                check_run_placeholders({"html-epub-user-theme": "x.css"}))
        self.assertEqual(buf.getvalue(), "")

    def test_set_run_slot(self):
        import shutil
        import tempfile
        from pycbeta.theme import (set_run_slot, load_run_config,
                                   DEFAULT_RUN_CONFIG)
        root = tempfile.mkdtemp()
        try:
            p = set_run_slot("pdf-docx-user-theme", "mine", root)
            self.assertTrue(p.endswith("run.json"))
            d = load_run_config(p)  # 模板带注释，走 loader 解析
            self.assertEqual(d["pdf-docx-user-theme"], "mine")
            self.assertEqual(d["pdf-docx-theme"],
                             DEFAULT_RUN_CONFIG["pdf-docx-theme"])
            with self.assertRaises(ValueError):
                set_run_slot("nope", "x", root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_set_slot_preserves_comments(self):
        import shutil
        import tempfile
        from pycbeta.theme import set_run_slot, load_run_config
        root = tempfile.mkdtemp()
        try:
            fn = os.path.join(root, "run.json")
            with open(fn, "w", encoding="utf-8") as f:
                f.write('{\n  // 我的注释\n  "config-json": "a.json",\n'
                        '  "pdf-docx-user-theme": "old"\n}\n')
            set_run_slot("pdf-docx-user-theme", "new", root)
            text = open(fn, encoding="utf-8").read()
            self.assertIn("// 我的注释", text)  # 注释保留
            self.assertIn('"config-json": "a.json"', text)  # 其余键原样
            self.assertEqual(load_run_config(fn)["pdf-docx-user-theme"],
                             "new")
            # 缺键插入
            set_run_slot("pdf-docx-theme", "std.css", root)
            text2 = open(fn, encoding="utf-8").read()
            self.assertIn("// 我的注释", text2)
            self.assertEqual(load_run_config(fn)["pdf-docx-theme"],
                             "std.css")
            # 配置栏写 config-json 槽：theme 行逐字节不动（槽隔离）
            set_run_slot("config-json", "other.json", root)
            text3 = open(fn, encoding="utf-8").read()
            for line in text2.splitlines():
                if "pdf-docx-user-theme" in line or "pdf-docx-theme" in line:
                    self.assertIn(line, text3.splitlines())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_set_slot_bad_file(self):
        import shutil
        import tempfile
        from pycbeta.theme import set_run_slot, load_run_config
        root = tempfile.mkdtemp()
        try:
            fn = os.path.join(root, "run.json")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("{broken")
            set_run_slot("pdf-docx-user-theme", "mine", root)
            self.assertTrue(os.path.isfile(fn + ".bad"))
            text = open(fn, encoding="utf-8").read()
            self.assertIn("//", text)  # 按注释模板重建
            self.assertEqual(load_run_config(fn)["pdf-docx-user-theme"],
                             "mine")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_deep_merge(self):
        from pycbeta.theme import deep_merge
        base = {"output": {"t2s": False, "pagination": {"enabled": True}},
                "pages": {"a4": {}}}
        over = {"output": {"pagination": {"enabled": False}}}
        got = deep_merge(base, over)
        self.assertFalse(got["output"]["pagination"]["enabled"])
        self.assertFalse(got["output"]["t2s"])  # 未覆盖键保留
        self.assertIn("pages", got)
        self.assertEqual(base["output"]["pagination"]["enabled"], True)  # 不污染

    def test_effective_config_and_legacy_theme_warn(self):
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout
        from pycbeta.theme import resolve_effective_config
        root = tempfile.mkdtemp()
        try:
            cfg = os.path.join(root, "mine.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"output": {"t2s": True}, "theme": "x"}, f)
            run = {"config-json": "mine.json"}
            buf = io.StringIO()
            with redirect_stdout(buf):
                got = resolve_effective_config(run, root)
            # 按鍵合并：用户 t2s 生效，出厂其他键保留；遗留 theme 键警告
            self.assertTrue(got["output"]["t2s"])
            self.assertIn("pages", got)
            self.assertIn("theme", buf.getvalue())
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_absolute_and_relative_path(self):
        import os
        import tempfile
        from pycbeta.theme import resolve_theme_css
        tmp = tempfile.mkdtemp()
        try:
            fn = os.path.join(tmp, "mine.css")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("p { font-size: 1pt; }\n")
            path, label = resolve_theme_css(fn)
            self.assertEqual(path, fn)
            self.assertEqual(label, "路径指定")
            sub = os.path.join(tmp, "sub")
            os.makedirs(sub)
            path2, _l2 = resolve_theme_css("mine.css", base_dir=tmp)
            self.assertEqual(path2, fn)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

class TestLineHeightInherit(unittest.TestCase):
    """行距 CSS 层叠：无本标签行距时继承 body（与浏览器/PDF 一致，DOCX 不再全员单倍）。"""

    def test_inherit_body(self):
        from pycbeta.theme import Theme
        t = Theme.from_css("body { line-height: 1.8; }\n"
                           "p.head { color: #000; }\n"
                           "p { line-height: 1; }\n")
        self.assertIn('w:line="432"', t.docx_para("head"))
        self.assertIn('w:line="240"', t.docx_para("p"))
        self.assertIn('w:line="432"', t.docx_para("juan"))

    def test_body_rhythm_uniform(self):
        # 2026-09-06：正文 p 显式行距，head 上下边距，div-xu 随正文节奏
        # 2026-09-11：出厂值调整为 p=1.4、head 上边距 0.5em（用户定稿）
        from pycbeta.theme import Theme
        t = Theme()
        self.assertIn('w:line="336"', t.docx_para("p"))
        self.assertIn('w:before="200"', t.docx_para("head"))  # 0.5em@20pt
        self.assertIn('w:after="200"', t.docx_para("head"))  # 0.5em@20pt
        self.assertIn('w:before="120"', t.docx_para("div-xu"))  # 0.5em@12pt
        self.assertIn('w:after="240"', t.docx_para("div-xu"))  # 1.0em@12pt（2026-09-12 定稿）

    def test_explicit_wins(self):
        from pycbeta.theme import Theme
        t = Theme.from_css("body { line-height: 1.8; }\n"
                           "p.pin { line-height: 2; }\n")
        self.assertIn('w:line="480"', t.docx_para("pin"))

    def test_normal_spacing_follows_body(self):
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.theme import Theme
        r = DocxRenderer(theme=Theme.from_css("body { line-height: 1.8; }\n"))
        self.assertIn('w:line="432"', r._normal_spacing())


class TestResolveNotes(unittest.TestCase):
    def test_default_footnote(self):
        from pycbeta.theme import resolve_notes
        self.assertEqual(resolve_notes(None), "footnote")
        self.assertEqual(resolve_notes({}), "footnote")
        self.assertEqual(resolve_notes({"output": {}}), "footnote")

    def test_config_value(self):
        from pycbeta.theme import resolve_notes
        self.assertEqual(
            resolve_notes({"output": {"notes": "endnote"}}), "endnote")
        self.assertEqual(
            resolve_notes({"output": {"notes": "INLINE"}}), "inline")

    def test_invalid_config_falls_back(self):
        from pycbeta.theme import resolve_notes
        self.assertEqual(
            resolve_notes({"output": {"notes": "bogus"}}), "footnote")
        self.assertEqual(
            resolve_notes({"output": {"notes": ""}}), "footnote")

    def test_explicit_wins(self):
        from pycbeta.theme import resolve_notes
        self.assertEqual(
            resolve_notes({"output": {"notes": "endnote"}}, explicit="inline"),
            "inline")
        # 非法 explicit 忽略，取 config
        self.assertEqual(
            resolve_notes({"output": {"notes": "endnote"}}, explicit="x"),
            "endnote")


class TestBracketPair(unittest.TestCase):
    def test_pairs(self):
        from pycbeta.theme import bracket_pair
        self.assertEqual(bracket_pair("halfwidth"), ("(", ")"))
        self.assertEqual(bracket_pair("fullwidth"), ("（", "）"))
        self.assertEqual(bracket_pair("corner"), ("〔", "〕"))
        self.assertEqual(bracket_pair("square"), ("[", "]"))

    def test_fallback_fullwidth(self):
        from pycbeta.theme import bracket_pair
        self.assertEqual(bracket_pair(None), ("（", "）"))
        self.assertEqual(bracket_pair(""), ("（", "）"))
        self.assertEqual(bracket_pair("bogus"), ("（", "）"))


class TestLoadEffectivePresets(unittest.TestCase):
    def test_run_json_resolved(self):
        from pycbeta.theme import load_effective_presets
        d = tempfile.mkdtemp()
        cfg = os.path.join(d, "presets.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"source": {"cbeta_ebook": r"E:\ebook"},
                       "output": {"notes": "endnote"}}, f)
        run = os.path.join(d, "run.json")
        with open(run, "w", encoding="utf-8") as f:
            json.dump({"config-json": cfg, "html-epub-theme": "html_epub_official.css",
                       "html-epub-user-theme": "", "pdf-docx-theme": "pdf_docx.css",
                       "pdf-docx-user-theme": ""}, f)
        p = load_effective_presets(run)
        self.assertEqual(p.get("source", {}).get("cbeta_ebook"), r"E:\ebook")
        self.assertEqual((p.get("output") or {}).get("notes"), "endnote")

    def test_plain_presets_passthrough(self):
        from pycbeta.theme import load_effective_presets
        d = tempfile.mkdtemp()
        cfg = os.path.join(d, "p.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"output": {"notes": "inline"}}, f)
        p = load_effective_presets(cfg)
        self.assertEqual((p.get("output") or {}).get("notes"), "inline")
        self.assertEqual(load_effective_presets(None).get("output", {}).get("notes"),
                         "footnote")


class TestVerticalUncenter(unittest.TestCase):
    def test_constant(self):
        from pycbeta.theme import VERTICAL_UNCENTER
        self.assertEqual(tuple(VERTICAL_UNCENTER), ("title", "head", "juan", "pin"))

    def test_factory_css_has_override(self):
        from pycbeta.theme import Theme
        t = Theme()  # 出厂 pdf_docx.css
        raw = t.raw_css or ""
        self.assertIn("body.vertical-rl p.juan", raw)
        self.assertIn("body.vertical-rl h1.title", raw)
        self.assertIn("body.vertical-rl p.head", raw)
        self.assertIn("body.vertical-rl p.pin", raw)


class TestRequiredThemeTags(unittest.TestCase):
    """pdf_docx.css 是默认值唯一来源（DEFAULT_THEME 已移除）：必需元素缺失即失败并
    提示往 CSS 补上。"""

    def test_factory_css_complete(self):
        import pycbeta.theme as _t
        missing = _t.missing_required_theme(_t.Theme())
        self.assertEqual(
            missing, [],
            "pdf_docx.css 缺少必要主题元素/属性（请补上）：\n  - "
            + "\n  - ".join(missing))

    def test_missing_elements_reported(self):
        # 只剩 body（+ 变量字体）→ title 等整体缺失，文案含选择器
        import pycbeta.theme as _t
        t = _t.Theme.from_css("body { font-size: 12pt; line-height: 1.4; }\n")
        missing = _t.missing_required_theme(t)
        self.assertTrue(any("title" in m and "h1.title" in m for m in missing),
                        f"应报出 title（选择器 h1.title），实际：{missing}")

    def test_missing_prop_reported_with_selector(self):
        # 删掉 p 的 text-indent 声明 → p 元素在（字体变量创建）但缺属性
        import pycbeta.theme as _t
        css = _t.Theme().raw_css.replace("text-indent: 2em;", "")
        missing = _t.missing_required_theme(_t.Theme.from_css(css))
        self.assertTrue(any("元素 p" in m and "text-indent" in m for m in missing),
                        f"应报出 p 缺 text-indent，实际：{missing}")

    def test_default_theme_removed(self):
        # 防回归：默认值不得再写回 Python（否则"DEFAULT 兜底"问题复现）
        import pycbeta.theme as _t
        self.assertFalse(hasattr(_t, "DEFAULT_THEME"))

    def test_p_follows_body_single_source(self):
        import pycbeta.theme as _t
        t = _t.Theme()
        self.assertIsNone((t.tags.get("p") or {}).get("font-size"))
        self.assertEqual(t.tags["body"]["font-size"], "12pt")
        # p 不写 w:sz，靠 docDefaults 继承 body
        self.assertNotIn("w:sz", t.docx_run("p"))

    def test_body_size_propagates_to_p(self):
        from pycbeta.theme import Theme
        from pycbeta.render_docx import DocxRenderer
        t = Theme.from_css("body { font-size: 14pt; }\n")
        self.assertNotIn("w:sz", t.docx_run("p"))     # p 无显式字号
        self.assertEqual(DocxRenderer(theme=t).doc_size, 14.0)


class TestEnsurePageTypography(unittest.TestCase):
    """纸张排版入口 ensure_page_typography：库直接调用渲染器也按纸张生效，
    且 CLI（先 apply 再 font_scale）不会被二次应用重置。"""

    def test_renderer_applies_when_not_applied(self):
        from pycbeta.theme import Theme, PAGE_PRESETS
        from pycbeta.render_docx import DocxRenderer
        r = DocxRenderer(theme=Theme(), page="16开", page_presets=PAGE_PRESETS)
        self.assertEqual(r.theme.tags["body"]["font-size"], "10.5pt")
        self.assertEqual(r.doc_size, 10.5)

    def test_idempotent_after_scale(self):
        from pycbeta.theme import Theme, apply_page_typography, PAGE_PRESETS
        from pycbeta.render_docx import DocxRenderer
        t = Theme()
        apply_page_typography(t, "16开", PAGE_PRESETS)   # CLI 顺序：先定基准
        t.scale_font_sizes(1.5)
        DocxRenderer(theme=t, page="16开", page_presets=PAGE_PRESETS)  # 应跳过
        self.assertEqual(t.tags["body"]["font-size"], "15.75pt")

    def test_no_presets_noop(self):
        # page_presets=None（验证/默认）不应用纸张键，保持 CSS body
        from pycbeta.theme import Theme
        from pycbeta.render_docx import DocxRenderer
        r = DocxRenderer(theme=Theme(), page="16开")
        self.assertEqual(r.theme.tags["body"]["font-size"], "12pt")

    def test_fallbacks_constant(self):
        from pycbeta.theme import FALLBACKS
        self.assertEqual(FALLBACKS["base_pt"], 12.0)
        self.assertEqual(FALLBACKS["doc_size_pt"], 11)
        self.assertEqual(FALLBACKS["line_height"], 1.5)
        self.assertEqual(FALLBACKS["verse_hang_em"], 2.0)
        self.assertTrue(FALLBACKS["body_font"])


class TestPresetThemeKeys(unittest.TestCase):
    """预设主题键：显式开关 > 预设键 > run.json 槽 > 内置（pdf/docx + html/epub）。"""
    def _root(self):
        import shutil
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        css = os.path.join(root, "mark.css")
        with open(css, "w", encoding="utf-8") as f:
            f.write("p.presetmark{color:#123456}")
        return root, css

    def _run(self, root, preset_data):
        base = os.path.join(root, "p.json")
        with open(base, "w", encoding="utf-8") as f:
            json.dump(preset_data, f, ensure_ascii=False)
        return {"config-json": base}, root

    def test_preset_file_theme_keys(self):
        import shutil
        from pycbeta.theme import preset_file_theme_keys
        root = tempfile.mkdtemp()
        try:
            p = os.path.join(root, "a.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"pdf-docx-user-theme": "x.css",
                           "html-epub-theme": "",
                           "pdf-docx-theme": 123,
                           "output": {}}, f)
            self.assertEqual(preset_file_theme_keys(p),
                             {"pdf-docx-user-theme": "x.css"})
            self.assertEqual(
                preset_file_theme_keys(os.path.join(root, "nope.json")), {})
            bad = os.path.join(root, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{oops")
            self.assertEqual(preset_file_theme_keys(bad), {})
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_docx_run_eastasia_canonicalized(self):
        import unittest.mock as mock
        from pycbeta.theme import Theme
        t = Theme.from_css(':root { --font-p: FooTC, FooEN; }\n'
                           'p { font-family: var(--font-p); }\n')
        with mock.patch("pycbeta.theme.preferred_family",
                        side_effect=lambda x: "CANON-" + x) as m:
            out = t.docx_run("p")
        m.assert_called_with("FooTC")
        self.assertIn('w:eastAsia="CANON-FooTC"', out)
        self.assertIn('w:ascii="FooTC"', out)  # 西文槽不动，只归一 eastAsia

    def test_pdf_user_preset_beats_run_slot(self):
        from pycbeta.theme import resolve_pdf_docx_css
        root, css = self._root()
        run, rdir = self._run(root, {"pdf-docx-user-theme": css})
        run["pdf-docx-user-theme"] = "nonexistent-slot.css"
        got = resolve_pdf_docx_css(run, rdir)
        self.assertIn("#123456", got)  # 预设键胜（run 槽文件不存在也会回内置）

    def test_pdf_explicit_beats_preset(self):
        from pycbeta.theme import resolve_pdf_docx_css
        root, css = self._root()
        run, rdir = self._run(root, {"pdf-docx-user-theme": css})
        got = resolve_pdf_docx_css(run, rdir, user="")
        self.assertNotIn("#123456", got)

    def test_pdf_preset_empty_and_nonstring_fall_through(self):
        from pycbeta.theme import resolve_pdf_docx_css, preset_theme_value
        root, _css = self._root()
        run, rdir = self._run(root, {"pdf-docx-user-theme": ""})
        self.assertEqual(preset_theme_value(run, rdir, "pdf-docx-user-theme"), "")
        run2, _r2 = self._run(root, {"pdf-docx-user-theme": 123})
        self.assertEqual(preset_theme_value(run2, rdir, "pdf-docx-user-theme"), "")
        self.assertEqual(preset_theme_value(run, rdir, "no-such-key"), "")
        css = resolve_pdf_docx_css(run, rdir)
        self.assertNotIn("presetmark", css)

    def test_pdf_std_preset_full_replace(self):
        from pycbeta.theme import resolve_pdf_docx_css
        root, _css = self._root()
        std = os.path.join(root, "std.css")
        with open(std, "w", encoding="utf-8") as f:
            f.write("p.onlystd{color:red}")
        run, rdir = self._run(root, {"pdf-docx-theme": std})
        got = resolve_pdf_docx_css(run, rdir)
        self.assertIn("onlystd", got)
        self.assertNotIn("--font-body", got)  # 整套替换，出厂全文不在
    def test_html_user_preset_appends(self):
        from pycbeta.theme import resolve_html_base_css
        root, css = self._root()
        run, rdir = self._run(root, {"html-epub-user-theme": css})
        got = resolve_html_base_css(run, rdir)
        self.assertIn("cbetarc", got)  # 官方基底仍在
        self.assertIn("#123456", got)  # 预设增量追加在后
        got2 = resolve_html_base_css(run, rdir, user="")
        self.assertNotIn("#123456", got2)  # 显式空胜预设

    def test_std_preset_override_warns(self):
        import io
        from contextlib import redirect_stdout
        from pycbeta.theme import resolve_pdf_docx_css, resolve_html_base_css
        root, _css = self._root()
        std = os.path.join(root, "std.css")
        with open(std, "w", encoding="utf-8") as f:
            f.write("p.onlystd{color:red}")
        run, rdir = self._run(root, {"pdf-docx-theme": std})
        buf = io.StringIO()
        with redirect_stdout(buf):
            resolve_pdf_docx_css(run, rdir)
        self.assertIn("整套替换", buf.getvalue())
        run2, _r2 = self._run(root, {"pdf-docx-user-theme": "my.css"})
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            resolve_pdf_docx_css(run2, rdir)
        self.assertNotIn("整套替换", buf2.getvalue())  # 增量键不警告
        hstd = os.path.join(root, "hstd.css")
        with open(hstd, "w", encoding="utf-8") as f:
            f.write("p.h{color:red}")
        run3, _r3 = self._run(root, {"html-epub-theme": hstd})
        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            resolve_html_base_css(run3, rdir)
        self.assertIn("官方基底", buf3.getvalue())


if __name__ == "__main__":
    unittest.main()
