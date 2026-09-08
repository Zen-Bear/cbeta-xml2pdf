import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.cli import scaled_page_presets
from pycbeta.theme import Theme, _scale_font_size, resolve_font_vars, resolve_page, \
    resolve_theme_css


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
        t = Theme(lang="zh-Hans")
        t.scale_font_sizes(1.5)
        self.assertEqual(t.tags["p"]["font-size"], "18pt")
        self.assertIn("SimSun", t.tags["p"]["font-family"])

    def test_single_source_body_pin(self):
        # 字体来自 CSS :root 变量（繁简双栏），非 font_sets
        t = Theme()
        self.assertIn("新細明體", t.tags["body"]["font-family"])
        self.assertIn("新細明體", t.tags["pin"]["font-family"])
        h = Theme(lang="zh-Hans")
        self.assertIn("宋体", h.tags["p"]["font-family"])
        self.assertIn("KaiTi", h.tags["kaiti"]["font-family"])


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
        self.assertEqual(len(t.compounds), 1)
        anc, tgt, props, sel = t.compounds[0]
        self.assertEqual((anc, tgt), ("div-xu", "head"))
        # 片段无 :root 变量 → 不填充字体（变量填充只认同文件 :root 双栏）
        self.assertEqual(props, {"color": "#000"})
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
        from pycbeta.theme import resolve_theme_css
        path, label = resolve_theme_css("large-print")
        self.assertTrue(path and os.path.isfile(path))
        self.assertIn("内置", label)
        path2, _l2 = resolve_theme_css("large-print.css")
        self.assertEqual(path, path2)

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

    def test_html_base_defaults_golden(self):
        from pycbeta.theme import resolve_html_base_css
        css = resolve_html_base_css({}, None)
        self.assertIn("cbetarc", css)
        self.assertNotIn("--font-body", css)

    def test_placeholder_warns(self):
        import io
        from contextlib import redirect_stdout
        from pycbeta.theme import check_run_placeholders
        buf = io.StringIO()
        with redirect_stdout(buf):
            check_run_placeholders({"html-epub-user-theme": "x.css"})
        self.assertIn("尚未接线", buf.getvalue())
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            check_run_placeholders({})
        self.assertEqual(buf2.getvalue(), "")

    def test_set_run_slot(self):
        import json
        import shutil
        import tempfile
        from pycbeta.theme import set_run_slot, DEFAULT_RUN_CONFIG
        root = tempfile.mkdtemp()
        try:
            p = set_run_slot("pdf-docx-user-theme", "mine", root)
            self.assertTrue(p.endswith("run.json"))
            d = json.load(open(p, encoding="utf-8"))
            self.assertEqual(d["pdf-docx-user-theme"], "mine")
            self.assertEqual(d["pdf-docx-theme"],
                             DEFAULT_RUN_CONFIG["pdf-docx-theme"])
            with self.assertRaises(ValueError):
                set_run_slot("nope", "x", root)
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
        # 2026-09-06：正文 p 显式 1.5，head 上下边距，div-xu 随正文节奏
        from pycbeta.theme import Theme
        t = Theme()
        self.assertIn('w:line="360"', t.docx_para("p"))
        self.assertIn('w:before="400"', t.docx_para("head"))  # 1em@20pt
        self.assertIn('w:after="200"', t.docx_para("head"))  # 0.5em@20pt
        self.assertIn('w:before="120"', t.docx_para("div-xu"))  # 0.5em@12pt
        self.assertIn('w:after="72"', t.docx_para("div-xu"))  # 0.3em@12pt

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


if __name__ == "__main__":
    unittest.main()
