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


class TestDefaultOutputNames(unittest.TestCase):
    def test_unsafe_work_id_stays_in_out_dir(self):
        from pycbeta.model import Work
        from pycbeta.render_md import MdRenderer
        from pycbeta.render_txt import TxtRenderer
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.render_epub import EpubRenderer
        d = tempfile.mkdtemp()
        try:
            w = Work(id="../evil", source_file="", metadata={}, body=[],
                     notes_by_n={}, apps=[], simplified=False)
            for renderer in (MdRenderer(), TxtRenderer(), DocxRenderer(),
                             EpubRenderer()):
                p = renderer.render_work(w, d)
                self.assertEqual(os.path.dirname(os.path.abspath(p)),
                                 os.path.abspath(d), type(renderer).__name__)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestGuiLifecycleGuards(unittest.TestCase):
    def test_close_event_guards_defined(self):
        from pycbeta.gui.panel import DataUpdateDialog, SourceDialog
        from pycbeta.gui.css_editor import CssEditorDialog
        for cls in (DataUpdateDialog, SourceDialog, CssEditorDialog):
            self.assertIn("closeEvent", cls.__dict__, cls.__name__)

    def test_verify_info_debounce_wired(self):
        from pycbeta.gui.panel import SourceDialog
        self.assertTrue(hasattr(SourceDialog, "_schedule_verify_info"))


class TestVerseQuoteRestore(unittest.TestCase):
    def test_ir_restored_and_second_render_identical(self):
        from pycbeta.model import Work, E, Text
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.verify import extract_text
        d1, d2 = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            w = Work(id="T1", source_file="", metadata={"title": "t"}, body=[
                E(tag="lg", children=[
                    E(tag="l", children=[Text("「甲」")])])],
                notes_by_n={}, apps=[])
            r = DocxRenderer(verse_strip_quotes=True)
            p1 = r.render_work(w, d1, "a.docx")
            node = w.body[0].children[0].children[0]
            self.assertEqual(node.text, "「甲」")   # 渲染后 IR 已还原
            p2 = r.render_work(w, d2, "a.docx")
            self.assertEqual(extract_text(p1), extract_text(p2))
            self.assertNotIn("「甲」", extract_text(p1))  # 渲染期确实剥离
        finally:
            shutil.rmtree(d1, ignore_errors=True)
            shutil.rmtree(d2, ignore_errors=True)


class TestRtCssFilter(unittest.TestCase):
    def test_style_breakout_chars_removed(self):
        from pycbeta.annotate import rt_css_rule
        out = rt_css_rule({"style": "ruby",
                           "rt_font": "</style><script>x</script>"})
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)


class TestRowOutcomeCancel(unittest.TestCase):
    def test_cancelled_row_text(self):
        from pycbeta.gui.__main__ import _row_outcome
        self.assertEqual(_row_outcome(False, [], False, ["x"],
                                      cancelled=True)[0], "已取消")
        self.assertEqual(_row_outcome(False, [], False, ["x"])[0], "失败：x")


class TestLengthGate(unittest.TestCase):
    def test_strictly_greater_only(self):
        from pycbeta.verify import length_gate
        self.assertEqual(length_gate("甲" * 10, "甲" * 20, 10), (False, 10))
        self.assertEqual(length_gate("甲" * 10, "甲" * 21, 10), (True, 11))
        self.assertEqual(length_gate("甲" * 10, "甲" * 10, 10), (False, 0))
        self.assertEqual(length_gate("甲" * 10, "甲" * 11, 0), (True, 1))

    def test_bad_threshold_falls_back(self):
        from pycbeta.verify import length_gate
        self.assertEqual(length_gate("甲" * 10, "甲" * 21, None), (True, 11))


class TestLengthGateReport(unittest.TestCase):
    def _record(self, trials):
        return {"xml": "T1509.xml", "fmt": "epub", "status": "fail",
                "gen": "T1509.epub", "official": "T1509_001.html",
                "official_kind": "html", "missing": None, "extra": None,
                "total": None, "trials": trials, "struct_issues": []}

    def test_truncated_line_has_no_counts(self):
        from pycbeta.verify import _format_verify_record
        rec = self._record([{
            "kind": "html", "official": "T1509_001.html (+99)",
            "missing": None, "extra": None, "total": None, "ok": False,
            "truncated": True, "length_diff": 860, "ctx": [],
            "src_cmp": "", "gen_cmp": ""}])
        txt = "\n".join(_format_verify_record(rec, 5, 10))
        self.assertIn("长度差860", txt)
        self.assertIn("未全量比对", txt)
        self.assertNotIn("缺None", txt)

    def test_all_truncated_summary(self):
        from pycbeta.verify import (format_work_summary,
                                    _format_verify_record)
        rec = self._record([
            {"kind": "html", "official": "h", "missing": None, "extra": None,
             "total": None, "ok": False, "truncated": True,
             "length_diff": 860},
            {"kind": "txt_notes", "official": "t", "missing": None,
             "extra": None, "total": None, "ok": False, "truncated": True,
             "length_diff": 28000}])
        txt = "\n".join(_format_verify_record(rec, 5, 10))
        self.assertEqual(txt.count("未全量比对"), 2)
        self.assertIn("FAIL(?/?)",
                      format_work_summary("T1509",
                                          [("epub", "fail", None, None)]))


class TestVerifyOneLengthGate(unittest.TestCase):
    """verify_one 集成：截断不调用 diff_stats、链回退、全截断兜底。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={}, body=[],
                    notes_by_n={}, apps=[], simplified=False)

    def _run(self, gen_text, bases, max_diff=10, diff_stats=None):
        import pycbeta.verify as V
        d = tempfile.mkdtemp(prefix="vlen-")
        try:
            gen = os.path.join(d, "T.md")
            with open(gen, "w", encoding="utf-8") as f:
                f.write(gen_text)
            paths = {}
            for kind, text, ext in bases:
                p = os.path.join(d, f"base_{kind}.{ext}")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                paths[kind] = [p]
            patches = [
                mock.patch.object(V, "P5Parser"),
                mock.patch.object(V, "load_effective_presets",
                                  return_value={"verify": {"auto_fetch": False}}),
                mock.patch.object(V, "find_official",
                                  side_effect=lambda src, stem, kind, **kw:
                                  paths.get(kind, [])),
            ]
            if diff_stats is not None:
                patches.append(mock.patch.object(V, "diff_stats",
                                                 side_effect=diff_stats))
            with patches[0], patches[1], patches[2]:
                if diff_stats is not None:
                    with patches[3]:
                        rec = self._call(V, d, gen, max_diff)
                else:
                    rec = self._call(V, d, gen, max_diff)
            return rec
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def _call(self, V, d, gen, max_diff):
        V.P5Parser.return_value.parse.return_value = self._work()
        return V.verify_one("x.xml", "md", d, os.path.join(d, "v"),
                            max_diff=max_diff, gen_paths=[gen])

    def test_truncated_skips_sequence_matcher(self):
        rec = self._run("甲" * 100,
                        [("txt_notes", "甲" * 200, "txt")],
                        diff_stats=AssertionError("diff_stats 不应被调用"))
        self.assertEqual(rec["status"], "fail")
        self.assertIsNone(rec["missing"])
        self.assertIsNone(rec["extra"])
        self.assertIsNone(rec["total"])
        self.assertTrue(rec["truncated"])
        self.assertEqual(rec["length_diff"], 100)

    def test_equal_threshold_still_compares(self):
        rec = self._run("甲" * 100,
                        [("txt_notes", "甲" * 110, "txt")], max_diff=10)
        self.assertEqual(rec["status"], "ok")
        self.assertFalse(rec["trials"][0].get("truncated"))
        self.assertEqual(rec["total"], 10)

    def test_chain_falls_back_after_truncation(self):
        rec = self._run("甲" * 100,
                        [("txt_notes", "甲" * 200, "txt"),
                         ("html", "甲" * 100, "html")])
        self.assertEqual(rec["status"], "ok")
        self.assertTrue(rec["trials"][0].get("truncated"))
        self.assertTrue(rec["trials"][1].get("ok"))

    def test_all_truncated_returns_fail_with_none_counts(self):
        rec = self._run("甲" * 100,
                        [("txt_notes", "甲" * 200, "txt"),
                         ("html", "甲" * 300, "html")],
                        diff_stats=AssertionError("diff_stats 不应被调用"))
        self.assertEqual(rec["status"], "fail")
        self.assertIsNone(rec["missing"])
        self.assertIsNone(rec["extra"])
        self.assertIsNone(rec["total"])
        self.assertTrue(rec["truncated"])
        self.assertEqual(rec["length_diff"], 100)
        self.assertEqual(len(rec["trials"]), 2)


    def test_truncated_notes_only_keeps_scope(self):
        gen = "甲" * 100 + "\n\n## 校注\n\n[^1]: " + "注" * 50
        base = "<html><body><p>" + "甲" * 100 + "</p></body></html>"
        rec = self._run(gen, [("html", base, "html")],
                        diff_stats=AssertionError("diff_stats 不应被调用"))
        self.assertEqual(rec["status"], "fail")
        self.assertEqual(rec["diff_scope"], "notes_only")
        self.assertEqual((rec["body_missing"], rec["body_extra"]), (0, 0))
        self.assertIsNone(rec["missing"])
        from pycbeta.verify import format_verify_report
        txt = "\n".join(format_verify_report([rec], 5, 10))
        self.assertIn("【仅仅注释差异】", txt)

    def test_truncated_body_diff_marks_body(self):
        gen = "乙" * 100 + "\n\n## 校注\n\n[^1]: " + "注" * 50
        base = "<html><body><p>" + "甲" * 100 + "</p></body></html>"
        rec = self._run(gen, [("html", base, "html")],
                        diff_stats=AssertionError("diff_stats 不应被调用"))
        self.assertEqual(rec["status"], "fail")
        self.assertEqual(rec["diff_scope"], "body")
        self.assertIsNone(rec["body_missing"])
        from pycbeta.verify import format_verify_report
        txt = "\n".join(format_verify_report([rec], 5, 10))
        self.assertIn("【正文差异（未全量比对）】", txt)


class TestUpdateDataReplaceBoundary(unittest.TestCase):
    def test_locked_item_does_not_abort_rest(self):
        from pycbeta import update_data as U
        d = tempfile.mkdtemp(prefix="upd-")
        try:
            sources = [
                {"key": "a", "kind": "text", "url": "u-a",
                 "dest": ["data", "a.txt"]},
                {"key": "b", "kind": "text", "url": "u-b",
                 "dest": ["data", "b.txt"]},
            ]

            def dl(_url, dest):
                with open(dest, "wb") as f:
                    f.write(b"abc\n")
                return True

            real_replace = os.replace
            calls = {"n": 0}

            def fake_replace(src, dst):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError("locked")
                return real_replace(src, dst)

            with mock.patch.object(U.os, "replace",
                                   side_effect=fake_replace):
                report = U.update_all(
                    root=d, sources=sources, download=dl,
                    probe=lambda *a, **k: ("failed", None, None))
            by = {r["key"]: r for r in report}
            self.assertEqual(by["a"]["status"], "failed")
            self.assertIn("写入失败", by["a"]["detail"])
            self.assertEqual(by["b"]["status"], "updated")
            self.assertFalse(os.path.isfile(
                os.path.join(d, "data", "a.txt")))
            self.assertTrue(os.path.isfile(
                os.path.join(d, "data", "b.txt")))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestVerifyConfigWarning(unittest.TestCase):
    def test_config_read_failure_warns(self):
        import contextlib
        import io
        from pycbeta.model import Work
        import pycbeta.verify as V
        d = tempfile.mkdtemp(prefix="vcfg-")
        try:
            gen = os.path.join(d, "T.txt")
            with open(gen, "w", encoding="utf-8") as f:
                f.write("甲")
            work = Work(id="T", source_file="", metadata={}, body=[],
                        notes_by_n={}, apps=[], simplified=False)
            err = io.StringIO()
            with mock.patch.object(V, "P5Parser") as P, \
                    mock.patch.object(V, "generate_formal",
                                      return_value=[gen]), \
                    mock.patch.object(V, "find_official",
                                      return_value=[]), \
                    mock.patch.object(V, "load_effective_presets",
                                      side_effect=RuntimeError("bad cfg")):
                P.return_value.parse.return_value = work
                with contextlib.redirect_stderr(err):
                    V.verify_one("x.xml", "txt", d, os.path.join(d, "v"),
                                 gen_paths=[gen])
            self.assertIn("读取校验配置失败", err.getvalue())
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestThemeFontVarWarning(unittest.TestCase):
    def test_parse_failure_warns(self):
        import contextlib
        import io
        try:
            import tinycss2  # noqa: F401
        except ImportError:
            self.skipTest("tinycss2 未安装")
        from pycbeta.theme import resolve_font_vars
        err = io.StringIO()
        with mock.patch("tinycss2.parse_stylesheet",
                        side_effect=RuntimeError("bad css")), \
                contextlib.redirect_stderr(err):
            out = resolve_font_vars(":root{}")
        self.assertEqual(out, ({}, {}))
        self.assertIn("字体变量解析失败", err.getvalue())


class TestQtAliasCache(unittest.TestCase):
    def test_failure_not_cached(self):
        import pycbeta.gui.css_editor as CE
        from pycbeta.gui.css_editor import (clear_qt_alias_cache,
                                            qt_aliases)
        clear_qt_alias_cache()
        with mock.patch("pycbeta.fonts.locator",
                        side_effect=RuntimeError("no fonts")):
            self.assertEqual(qt_aliases(), {})
        self.assertIsNone(CE._qt_alias_cache)


class TestStaleTempCleanup(unittest.TestCase):
    def test_old_removed_new_kept(self):
        import time
        from pycbeta.tempdirs import cleanup_stale_temp_dirs
        root = tempfile.gettempdir()
        old = tempfile.mkdtemp(prefix="xml2pdf-test-", dir=root)
        new = tempfile.mkdtemp(prefix="xml2pdf-test-", dir=root)
        try:
            past = time.time() - 7200
            os.utime(old, (past, past))
            removed, failed = cleanup_stale_temp_dirs(
                max_age_hours=1, prefixes=("xml2pdf-test-",))
            self.assertGreaterEqual(removed, 1)
            self.assertFalse(os.path.isdir(old))
            self.assertTrue(os.path.isdir(new))
            self.assertEqual(failed, [])
        finally:
            shutil.rmtree(old, ignore_errors=True)
            shutil.rmtree(new, ignore_errors=True)


class TestComConvertIsolation(unittest.TestCase):
    def test_success_replaces_atomically(self):
        import glob
        from pycbeta import render_pdf as R
        d = tempfile.mkdtemp(prefix="comiso-")
        try:
            pdf = os.path.join(d, "o.pdf")

            class FakeProc:
                pid = 12345
                returncode = 0

                def __init__(self, cmd):
                    self.cmd = cmd

                def communicate(self, timeout=None):
                    i = self.cmd.index("--pdf")
                    with open(self.cmd[i + 1], "wb") as f:
                        f.write(b"%PDF-1.4 test")
                    return (b"", b"")

            with mock.patch.object(
                    R.subprocess, "Popen",
                    side_effect=lambda cmd, **kw: FakeProc(cmd)):
                out = R._com_convert_isolated(
                    "in.docx", pdf, ("Word.Application",), timeout=1)
            self.assertEqual(out, os.path.abspath(pdf))
            self.assertTrue(os.path.isfile(pdf))
            self.assertFalse(glob.glob(os.path.join(d, "xml2pdf-com-*")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_timeout_kills_tree_and_raises(self):
        import glob
        from pycbeta import render_pdf as R
        d = tempfile.mkdtemp(prefix="comiso-")
        try:
            pdf = os.path.join(d, "o.pdf")

            class HangProc:
                pid = 23456
                returncode = None

                def communicate(self, timeout=None):
                    raise R.subprocess.TimeoutExpired(cmd="x", timeout=1)

            killed = []
            with mock.patch.object(R.subprocess, "Popen",
                                   return_value=HangProc()), \
                    mock.patch.object(
                        R, "_kill_process_tree",
                        side_effect=lambda p: killed.append(p)):
                with self.assertRaises(RuntimeError):
                    R._com_convert_isolated(
                        "in.docx", pdf, ("Word.Application",), timeout=1)
            self.assertEqual(len(killed), 1)
            self.assertFalse(os.path.isfile(pdf))
            self.assertFalse(glob.glob(os.path.join(d, "xml2pdf-com-*")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_word_backend_uses_isolation(self):
        from pycbeta import render_pdf as R
        with mock.patch.object(R, "_com_convert_isolated",
                               return_value="x.pdf") as iso:
            self.assertEqual(R._pdf_via_word("a.docx", "b.pdf"), "x.pdf")
        iso.assert_called_once_with("a.docx", "b.pdf", R._COM_WORD)

    def test_helper_exit_codes(self):
        from pycbeta import com_helper
        args = ["--docx", "a", "--pdf", "b",
                "--progids", "Word.Application"]
        with mock.patch("pycbeta.render_pdf._com_convert",
                        return_value="b"):
            self.assertEqual(com_helper.main(args), 0)
        with mock.patch("pycbeta.render_pdf._com_convert",
                        return_value=None):
            self.assertEqual(com_helper.main(args), 2)

    def test_kill_pid_only_office(self):
        import types
        from pycbeta import render_pdf as R
        if os.name != "nt":
            self.skipTest("Windows only")
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[0] == "tasklist":
                return types.SimpleNamespace(
                    stdout='"WINWORD.EXE","1234","Console","1","1,000 K"')
            return types.SimpleNamespace(stdout="")

        with mock.patch.object(R.subprocess, "run", side_effect=fake_run):
            R._kill_pid_if_office(1234)
        self.assertTrue(any(c[0] == "taskkill" for c in calls))
        calls.clear()
        with mock.patch.object(
                R.subprocess, "run",
                side_effect=lambda cmd, **kw: types.SimpleNamespace(
                    stdout='"notepad.exe","1234","Console","1","1,000 K"')):
            R._kill_pid_if_office(1234)
        self.assertFalse(any(c[0] == "taskkill" for c in calls))


if __name__ == "__main__":
    unittest.main()
