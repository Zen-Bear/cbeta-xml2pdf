# -*- coding: utf-8 -*-
"""审核批 1（快修）回归：变量环、run.json 槽替换、配置 dest、catalog 文件名、
产物收编前缀、CLI 主题编码、字体扫描韧性。对应 docs/TODO.md 高危六/七、
中危五/六、低危三/七。"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock


class TestThemeVarSubst(unittest.TestCase):
    def test_cycle_terminates(self):
        from pycbeta.theme import _subst_vars
        out = _subst_vars("var(--x)", {"--x": "var(--y)", "--y": "var(--x)"})
        self.assertIsInstance(out, str)

    def test_chain_resolves(self):
        from pycbeta.theme import _subst_vars
        self.assertEqual(_subst_vars("var(--a)", {"--a": "12pt"}), "12pt")


class TestRunJsonSlotReplace(unittest.TestCase):
    def test_backslash_value_roundtrips(self):
        from pycbeta.theme import _replace_json_string_slot
        text = '{\n  "config-json": "presets/a.json"\n}'
        new = _replace_json_string_slot(text, "config-json",
                                        r"E:\dev\cbeta\my n.json")
        self.assertEqual(json.loads(new)["config-json"],
                         r"E:\dev\cbeta\my n.json")


class TestRemoteDestGuard(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "cbeta", "data"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, text):
        fn = os.path.join(self.root, "cbeta", "data", "remote_sources.json")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(text)

    def test_dotdot_rejected(self):
        from pycbeta.update_data import load_sources
        self._write('{"a": {"url": "u", "dest": "../evil.txt", "kind": "text"}}')
        with self.assertRaises(ValueError):
            load_sources(self.root)

    def test_drive_rejected(self):
        from pycbeta.update_data import load_sources
        self._write('{"a": {"url": "u", "dest": "C:/evil.txt", "kind": "text"}}')
        with self.assertRaises(ValueError):
            load_sources(self.root)


class TestCatalogDest(unittest.TestCase):
    def test_rejects_bad_names(self):
        from pycbeta.fetch import _catalog_dest
        for bad in ("../x.xml", "a/b.xml", "a\\b.xml", "..", "", "C:x.xml"):
            with self.assertRaises(ValueError):
                _catalog_dest("w", bad)

    def test_accepts_plain_name(self):
        from pycbeta.fetch import _catalog_dest
        self.assertTrue(_catalog_dest("w", "T0349_001.xml")
                        .endswith("T0349_001.xml"))


class TestProducedPathsWithin(unittest.TestCase):
    def test_outside_filtered(self):
        from pycbeta.gui.__main__ import parse_produced_paths
        d, other = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            inside = os.path.join(d, "T0672.docx")
            outside = os.path.join(other, "someone.docx")
            for p in (inside, outside):
                open(p, "w").close()
            log = f"x -> {inside}\ny -> {outside}\n"
            self.assertEqual(parse_produced_paths(log, within=d), [inside])
        finally:
            shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(other, ignore_errors=True)

    def test_default_behaviour_kept(self):
        from pycbeta.gui.__main__ import parse_produced_paths
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "a.docx")
            open(p, "w").close()
            self.assertEqual(parse_produced_paths(f"-> {p}\n"), [p])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestLoadThemeEncoding(unittest.TestCase):
    def test_gbk_json_raises(self):
        from pycbeta.cli import load_theme
        d = tempfile.mkdtemp()
        try:
            fn = os.path.join(d, "t.json")
            with open(fn, "wb") as f:
                f.write('{"tags": {"p": {"color": "红"}}}'.encode("gbk"))
            with self.assertRaises(ValueError):
                load_theme(fn)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestFontScanResilience(unittest.TestCase):
    def test_unreadable_font_skipped(self):
        from pycbeta import fonts as F
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "bad.ttf"), "wb") as f:
                f.write(b"\x00\x01\x00\x00")
            with mock.patch.object(F, "read_family_names",
                                   side_effect=OSError("locked")):
                loc = F.FontLocator(extra_dirs=[d], scan_system=False)
            self.assertIsInstance(loc, F.FontLocator)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestHtmlAttrEscaping(unittest.TestCase):
    def test_attr_and_text_helpers(self):
        from pycbeta.render_html import _attr, _esc
        self.assertEqual(_attr('a"b<c>d&e\'f'),
                         "a&quot;b&lt;c&gt;d&amp;e&#x27;f")
        self.assertNotIn("&quot;", _esc('a"b'))

    def test_lg_class_and_indent_escaped(self):
        from pycbeta.model import E
        from pycbeta.render_html import HtmlRenderer
        e = E(tag="lg", attrs={"type": 'x" onmouseover="alert(1)',
                               "style": "text-indent:1em' onx='y"})
        out = HtmlRenderer()._render_lg(e)
        self.assertNotIn('onmouseover="alert(1)"', out)
        self.assertIn("&quot;", out)

    def test_p_style_escaped(self):
        from pycbeta.model import E, Text
        from pycbeta.render_html import HtmlRenderer
        e = E(tag="p", attrs={"style": 'color:red" onmouseover="alert(1)'},
              children=[Text("x")])
        out = HtmlRenderer()._render_e(e)
        self.assertNotIn('onmouseover="alert(1)"', out)
        self.assertIn("&quot;", out)


class TestThemeFontEscaping(unittest.TestCase):
    def test_docx_run_font_escaped(self):
        from pycbeta.theme import Theme
        css = 'body { font-family: x"/><w:color w:val="FF0000; }'
        out = Theme.from_css(css).docx_run("body")
        self.assertNotIn("<w:color", out)
        self.assertIn("&quot;", out)


class TestDocxAttrEscaping(unittest.TestCase):
    def test_attr_helper(self):
        from pycbeta.render_docx import _attr
        self.assertEqual(_attr('a"b<c>&d'), "a&quot;b&lt;c&gt;&amp;d")


class TestAtomicWrite(unittest.TestCase):
    def test_write_overwrite_and_no_temp_residue(self):
        from pycbeta.atomic import write_text
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "sub", "a.json")
            write_text(p, '{"a": 1}\n')
            self.assertEqual(open(p, encoding="utf-8").read(), '{"a": 1}\n')
            write_text(p, '{"a": 2}\n')
            self.assertEqual(json.loads(open(p, encoding="utf-8").read())["a"], 2)
            self.assertEqual(
                [n for n in os.listdir(os.path.dirname(p))
                 if n.startswith(".tmp-")], [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_failure_cleans_temp(self):
        from pycbeta.atomic import write_text
        d = tempfile.mkdtemp()
        try:
            with mock.patch("pycbeta.atomic.os.replace",
                            side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    write_text(os.path.join(d, "a.json"), "x")
            self.assertEqual(os.listdir(d), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestPdfBackendFallback(unittest.TestCase):
    def test_raising_backend_falls_through(self):
        from pycbeta import render_pdf as R
        d = tempfile.mkdtemp()
        try:
            docx = os.path.join(d, "a.docx")
            with open(docx, "wb") as f:
                f.write(b"x")
            pdf = os.path.join(d, "a.pdf")

            def bad(_docx, _pdf):
                raise RuntimeError("boom")

            def good(_docx, pdf_fn):
                with open(pdf_fn, "wb") as f:
                    f.write(b"%PDF-1.4")
                return pdf_fn

            with mock.patch.dict(R._DOCX_BACKENDS,
                                 {"bad": bad, "good": good}):
                out = R.docx_to_pdf(docx, pdf, chain=["bad", "good"])
            self.assertEqual(os.path.abspath(out), os.path.abspath(pdf))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestTimeoutGuard(unittest.TestCase):
    def test_values(self):
        from pycbeta.render_pdf import _timeout_seconds
        self.assertEqual(_timeout_seconds({"timeoutSeconds": "abc"}), 120)
        self.assertEqual(_timeout_seconds({"timeoutSeconds": -5}), 1)
        self.assertEqual(_timeout_seconds({"timeoutSeconds": 99999}), 3600)
        self.assertEqual(_timeout_seconds({}), 120)


@unittest.skipUnless(os.name == "nt", "Windows 进程树")
class TestKillProcessTree(unittest.TestCase):
    def test_child_killed(self):
        import subprocess as sp
        import sys as _sys
        from pycbeta.gui.__main__ import _kill_process_tree
        p = sp.Popen([_sys.executable, "-c",
                      "import time; time.sleep(30)"])
        try:
            _kill_process_tree(p)
            self.assertIsNotNone(p.wait(timeout=10))
        finally:
            try:
                p.kill()
            except Exception:
                pass


class TestEntitySafety(unittest.TestCase):
    def test_external_entity_not_expanded(self):
        from pycbeta.parser import P5Parser
        d = tempfile.mkdtemp()
        try:
            secret = os.path.join(d, "secret.txt")
            with open(secret, "w", encoding="utf-8") as f:
                f.write("TOPSECRET")
            xml = os.path.join(d, "x.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0"?>\n'
                        '<!DOCTYPE TEI [<!ENTITY xxe SYSTEM "file:///'
                        + secret.replace("\\", "/") + '">]>\n'
                        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
                        '<p>&xxe;</p></body></text></TEI>')
            w = P5Parser().parse(xml)
            text = "".join(getattr(n, "text", "") or "" for n in w.body)
            self.assertNotIn("TOPSECRET", text)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestOfficialArtifactExclusion(unittest.TestCase):
    def test_compare_files_not_treated_as_baseline(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "txt"))
            for name, body in (("x_001.txt", "正文"),
                               ("x_compare_html_official.txt", "自产")):
                with open(os.path.join(d, "txt", name), "w",
                          encoding="utf-8") as f:
                    f.write(body)
            found = [os.path.basename(p)
                     for p in V.find_official(d, "x", "txt_notes")]
            self.assertIn("x_001.txt", found)
            self.assertNotIn("x_compare_html_official.txt", found)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestNormalizeAndCfgInt(unittest.TestCase):
    def test_bom_stripped(self):
        from pycbeta.verify import normalize
        self.assertEqual(normalize("\ufeff甲 乙"), "甲乙")

    def test_cfg_int_invalid_falls_back(self):
        from pycbeta.verify import cfg_int
        self.assertEqual(cfg_int("abc", 10), 10)
        self.assertEqual(cfg_int(None, 5), 5)
        self.assertEqual(cfg_int(0, 10), 0)


class TestBaselineReadDegrade(unittest.TestCase):
    def test_corrupt_baseline_does_not_abort_or_pass(self):
        from unittest import mock
        import pycbeta.verify as V
        from pycbeta.model import Work
        d = tempfile.mkdtemp(prefix="vdegrade-")
        try:
            os.makedirs(os.path.join(d, "txt"))
            base = os.path.join(d, "txt", "x_001.txt")
            with open(base, "w", encoding="utf-8") as f:
                f.write("正文甲")
            gen = os.path.join(d, "gen_x.txt")
            with open(gen, "w", encoding="utf-8") as f:
                f.write("正文甲")
            work = Work(id="x", source_file="", metadata={}, body=[],
                        notes_by_n={}, apps=[], simplified=False)
            real = V.extract_text

            def flaky(path, **kw):
                if os.path.abspath(path) == os.path.abspath(base):
                    raise OSError("corrupt baseline")
                return real(path, **kw)

            with mock.patch.object(V, "P5Parser") as P, \
                    mock.patch.object(V, "generate_formal",
                                      return_value=[gen]), \
                    mock.patch.object(V, "extract_text", side_effect=flaky):
                P.return_value.parse.return_value = work
                rec = V.verify_one("x.xml", "txt", d, os.path.join(d, "v"),
                                   gen_paths=[gen])
            # 不抛穿，且绝不因「空基线」误判通过
            self.assertEqual(rec["status"], "fail")
            errs = [t.get("error") for t in rec.get("trials") or []
                    if t.get("error")]
            self.assertTrue(errs)
            self.assertIn("corrupt baseline", errs[0])
            self.assertIn("读取失败", "\n".join(V.format_verify_report([rec])))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestThemeNumericGuard(unittest.TestCase):
    def test_bad_values_do_not_crash(self):
        from pycbeta.theme import Theme, _abs_pt, apply_page_typography
        self.assertIsNone(_abs_pt("1.2.3pt", 12))
        self.assertEqual(_abs_pt(".5em", 12), 6.0)
        th = Theme()
        apply_page_typography(th, "x", {"x": {
            "body_font_size": "1.2.3pt", "body_line_height": "1.2.3"}})
        self.assertEqual(th.tags.get("body", {}).get("font-size"), "12pt")


class TestRenderNumericGuard(unittest.TestCase):
    def test_malformed_milestone_and_quantity(self):
        from pycbeta.model import E, Text
        from pycbeta.render_html import HtmlRenderer, split_juans
        from pycbeta.render_docx import split_sections
        body = [E(tag="milestone", attrs={"unit": "juan", "n": "卷一"}),
                E(tag="p", children=[Text("甲")])]
        self.assertTrue(split_juans(body))
        self.assertTrue(split_sections(body, {}))
        out = HtmlRenderer()._render_e(
            E(tag="space", attrs={"quantity": "999999"}))
        self.assertLessEqual(len(out), 100)


if __name__ == "__main__":
    unittest.main()
