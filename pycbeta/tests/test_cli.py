import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.cli import resolve_output, resolve_engine_vertical_lang


def _args(out):
    return SimpleNamespace(output=out, name_template=None)


def _work(wid="TX0006"):
    return SimpleNamespace(id=wid, metadata={})


def _touch(d, name):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("x")
    return p


class TestResolveOutputCollision(unittest.TestCase):
    def test_single_unchanged_without_used(self):
        # _used=None 时逐字节旧行为（单文件/重跑一致）
        d, n = resolve_output("/s/TX07n0006.xml", "txt", _args("/o"), _work())
        self.assertEqual((d, n), ("/o", "TX0006.txt"))

    def test_group_uniform_with_rename(self):
        import shutil
        d = tempfile.mkdtemp()
        try:
            used = {}
            d1, n1 = resolve_output("/s/TX07n0006.xml", "txt",
                                    _args(d), _work(), used)
            self.assertEqual(n1, "TX0006.txt")
            _touch(d, n1)  # 首文件已落盘
            d2, n2 = resolve_output("/s/TX08n0006.xml", "txt",
                                    _args(d), _work(), used)
            # 全组统一 stem 名；首文件被预改名
            self.assertEqual(n2, "TX08n0006.txt")
            self.assertTrue(os.path.isfile(os.path.join(d, "TX07n0006.txt")))
            self.assertFalse(os.path.isfile(os.path.join(d, "TX0006.txt")))
            d3, n3 = resolve_output("/s/TX09n0006.xml", "txt",
                                    _args(d), _work(), used)
            self.assertEqual(n3, "TX09n0006.txt")
            self.assertEqual(d1, d2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_replay_shared_state(self):
        # render 与 verify 共用同一 state：重放直接得终态名
        used = {}
        r1 = [resolve_output(f"/s/TX0{n}n0006.xml", "txt", _args("/o"),
                             _work(), used)[1] for n in (7, 8, 9)]
        r2 = [resolve_output(f"/s/TX0{n}n0006.xml", "txt", _args("/o"),
                             _work(), used)[1] for n in (7, 8, 9)]
        self.assertEqual(r1, ["TX0006.txt", "TX08n0006.txt", "TX09n0006.txt"])
        self.assertEqual(r2, ["TX07n0006.txt", "TX08n0006.txt", "TX09n0006.txt"])

    def test_rerun_fresh_state_keeps_name(self):
        # 同一输入重跑（新 state）：基名相同不触发回退
        _, n1 = resolve_output("/s/T12n0349.xml", "txt", _args("/o"),
                               _work("T0349"), {})
        _, n2 = resolve_output("/s/T12n0349.xml", "txt", _args("/o"),
                               _work("T0349"), {})
        self.assertEqual((n1, n2), ("T0349.txt", "T0349.txt"))

    def test_explicit_file_untouched(self):
        out = os.path.join(tempfile.mkdtemp(), "mine.txt")
        d, n = resolve_output("/s/TX08n0006.xml", "txt", _args(out),
                              _work(), {})
        self.assertEqual(n, "mine.txt")


class TestProcessFileErrors(unittest.TestCase):
    def test_oserror_continues_and_counts(self):
        # 某格式 OSError（如目标被 Word 占用）不中断其余格式，返回失败计数
        from unittest import mock
        import pycbeta.cli as cli
        args = SimpleNamespace(t2s=False, font_check=False)
        w = SimpleNamespace(id="T1", metadata={})
        with mock.patch.object(cli, "P5Parser") as P, \
                mock.patch.object(cli, "resolve_output", return_value=("d", "n")), \
                mock.patch.object(cli, "render_one") as R:
            P.return_value.parse.return_value = w
            R.side_effect = [PermissionError("denied"), None]
            n = cli.process_file("x.xml", ["docx", "txt"], args, None)
        self.assertEqual(n, 1)
        self.assertEqual(R.call_count, 2)


class TestResolveEngineVerticalLang(unittest.TestCase):
    """engine/vertical/font_lang：显式开关 > 配置 > 默认。"""

    def _args(self, **kw):
        a = SimpleNamespace(engine=None, vertical=False, font_lang=None, t2s=False)
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_defaults(self):
        e, v, lang = resolve_engine_vertical_lang(self._args(), {})
        self.assertIsNone(e)
        self.assertFalse(v)
        self.assertEqual(lang, "zh-Hant")

    def test_from_config(self):
        pres = {"engine": "html2pdf", "font_lang": "zh-Hans",
                "output": {"vertical": True}}
        e, v, lang = resolve_engine_vertical_lang(self._args(), pres)
        self.assertEqual(e, "html2pdf")
        self.assertTrue(v)
        self.assertEqual(lang, "zh-Hans")

    def test_explicit_overrides_config(self):
        pres = {"engine": "html2pdf", "font_lang": "zh-Hans",
                "output": {"vertical": True}}
        a = self._args(engine="docx2pdf", font_lang="zh-Hant")
        e, v, lang = resolve_engine_vertical_lang(a, pres)
        self.assertEqual(e, "docx2pdf")
        self.assertTrue(v)               # vertical 无显式关，配置仍生效
        self.assertEqual(lang, "zh-Hant")

    def test_t2s_forces_simplified_over_config(self):
        e, v, lang = resolve_engine_vertical_lang(
            self._args(t2s=True), {"font_lang": "zh-Hant"})
        self.assertEqual(lang, "zh-Hans")


class TestWorkIdNotHijackedByDir(unittest.TestCase):
    def test_same_named_dir_without_xml_falls_back_to_work_id(self):
        # cwd 下恰好有同名（非 XML）目录时，合法編號不得被判为目录而报
        # 「no XML files under <id>」；应改按編號材料化（此处打桩到材料化即算通过）
        import io
        from contextlib import redirect_stderr
        from unittest import mock
        from pycbeta.cli import main
        d = tempfile.mkdtemp()
        os.mkdir(os.path.join(d, "T0349"))
        cwd = os.getcwd()
        try:
            os.chdir(d)
            err = io.StringIO()
            with mock.patch("pycbeta.fetch.materialize_work",
                            return_value=(["DUMMY.xml"], "x")), \
                    mock.patch("pycbeta.cli.process_file", return_value=0):
                with redirect_stderr(err):
                    rc = main(["-i", "T0349", "-f", "pdf"])
            self.assertEqual(rc, 0)
            self.assertNotIn("no XML files under", err.getvalue())
        finally:
            os.chdir(cwd)


class TestConfigArgAccepted(unittest.TestCase):
    def test_pure_presets_config_not_rejected(self):
        # 纯基础配置 JSON（config.user.json / presets 快照）经 --config 不再报
        # 「旧 --config 全量快照」；配置通过后到 input 才失败
        import io
        import json
        from contextlib import redirect_stderr
        from pycbeta.cli import main
        fd, fn = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"output": {"t2s": True}}, f)
            err = io.StringIO()
            with redirect_stderr(err):
                with self.assertRaises(SystemExit):
                    main(["--config", fn, "-i", "not-a-work", "-f", "pdf"])
            self.assertNotIn("全量快照", err.getvalue())
            self.assertIn("input not found", err.getvalue())
        finally:
            os.remove(fn)


class TestVerifyOnly(unittest.TestCase):
    """--verify-only：跳过渲染，用输出命名规则定位既有生成档；缺失计失败。"""

    def _run(self, d, xml, extra=()):
        import io
        import json
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        from unittest import mock
        from pycbeta.cli import main
        from pycbeta.filename import default_output_name
        cfgp = os.path.join(d, "cfg.json")
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"verify": {"auto_fetch": False}}, f)
        work = SimpleNamespace(id="T0001", metadata={})
        out = io.StringIO()
        with mock.patch("pycbeta.parser.P5Parser") as P, \
                mock.patch("pycbeta.verify.work_juan_numbers",
                           return_value=[]), \
                mock.patch("pycbeta.cli.process_file") as PF:
            P.return_value.parse.return_value = work
            with redirect_stdout(out):
                rc = main(["--config", cfgp, "-i", xml, "-f", "txt",
                           "--verify-only", *extra])
        return rc, out.getvalue(), PF, \
            os.path.join(d, default_output_name("T0001", None, True) + ".txt")

    def test_missing_gen_counts_fail_and_skips_render(self):
        import shutil
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "T01n0001.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            rc, s, PF, _ = self._run(d, xml)
            self.assertIn("gen not found", s)
            self.assertEqual(rc, 1)
            PF.assert_not_called()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_summary_line_lists_formats(self):
        # 总结行 `[stem] N format: 1[txt=NOGEN], …` 紧跟 === 行之后
        import io
        import json
        import shutil
        from contextlib import redirect_stdout
        from unittest import mock
        from pycbeta.cli import main
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "T01n0001.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            cfgp = os.path.join(d, "cfg.json")
            with open(cfgp, "w", encoding="utf-8") as f:
                json.dump({"verify": {"auto_fetch": False}}, f)
            out = io.StringIO()
            with mock.patch("pycbeta.cli.process_file") as PF:
                with redirect_stdout(out):
                    rc = main(["--config", cfgp, "-i", xml, "-f", "txt,docx",
                               "--verify-only"])
            s = out.getvalue()
            self.assertIn("[T01n0001] 2 format: 1[txt=NOGEN], 2[docx=NOGEN]",
                          s)
            self.assertLess(s.index("=== T01n0001.xml"),
                            s.index("[T01n0001] 2 format:"))
            self.assertEqual(rc, 1)
            PF.assert_not_called()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_present_gen_no_baseline_skips_render(self):
        import shutil
        from pycbeta.filename import default_output_name
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "T01n0001.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            gen = os.path.join(
                d, default_output_name("T0001", None, True) + ".txt")
            with open(gen, "w", encoding="utf-8") as f:
                f.write("x")
            rc, s, PF, _ = self._run(d, xml)
            self.assertIn("no baseline", s)
            self.assertEqual(rc, 0)
            PF.assert_not_called()
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestShowNotesFlag(unittest.TestCase):
    """--show-notes/--no-show-notes：显式开关 > config output.show_notes。"""

    def _capture(self, config_show=None, extra=()):
        import io
        import json
        import shutil
        from contextlib import redirect_stdout
        from unittest import mock
        from pycbeta.cli import main
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "T01n0001.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            out_cfg = {}
            if config_show is not None:
                out_cfg["show_notes"] = config_show
            cfgp = os.path.join(d, "cfg.json")
            with open(cfgp, "w", encoding="utf-8") as f:
                json.dump({"output": out_cfg}, f)
            buf = io.StringIO()
            with mock.patch("pycbeta.cli.process_file") as PF:
                with redirect_stdout(buf):
                    main(["--config", cfgp, "-i", xml, "-f", "txt", *extra])
            return PF.call_args.args[2].show_notes
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_no_show_notes_overrides_config_true(self):
        self.assertFalse(self._capture(True, ["--no-show-notes"]))

    def test_show_notes_overrides_config_false(self):
        self.assertTrue(self._capture(False, ["--show-notes"]))

    def test_config_applies_without_flag(self):
        self.assertFalse(self._capture(False))
        self.assertTrue(self._capture(True))

    def test_default_true(self):
        self.assertTrue(self._capture())


class TestResolveVerifyEbook(unittest.TestCase):
    """校验基线下载目录：显式 --cbeta-ebook > presets > src（防 split-brain）。"""

    def test_explicit_wins(self):
        from types import SimpleNamespace
        from pycbeta.cli import resolve_verify_ebook
        args = SimpleNamespace(cbeta_ebook="E")
        self.assertEqual(
            resolve_verify_ebook(args, {"source": {"cbeta_ebook": "P"}}, "S"),
            "E")

    def test_preset_fallback(self):
        from types import SimpleNamespace
        from pycbeta.cli import resolve_verify_ebook
        args = SimpleNamespace(cbeta_ebook="")
        self.assertEqual(
            resolve_verify_ebook(args, {"source": {"cbeta_ebook": "P"}}, "S"),
            "P")

    def test_src_last_resort(self):
        from types import SimpleNamespace
        from pycbeta.cli import resolve_verify_ebook
        args = SimpleNamespace(cbeta_ebook="")
        self.assertEqual(resolve_verify_ebook(args, {}, "S"), "S")
        self.assertEqual(resolve_verify_ebook(args, None, "S"), "S")

    def test_verify_fetch_uses_explicit_ebook(self):
        # 主链：--verify 缺基线时 ensure_baselines 落显式目录（publish 场景）
        import io
        import json
        import shutil
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        from unittest import mock
        from pycbeta.cli import main
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "T01n0001.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            gen = os.path.join(d, "T0001.html")
            with open(gen, "w", encoding="utf-8") as f:
                f.write("x")
            cfgp = os.path.join(d, "cfg.json")
            with open(cfgp, "w", encoding="utf-8") as f:
                json.dump({"verify": {"auto_fetch": True}}, f)
            eb = os.path.join(d, "eb")
            os.makedirs(eb)
            work = SimpleNamespace(id="T0001", metadata={})
            seen = {}
            with mock.patch("pycbeta.parser.P5Parser") as P, \
                    mock.patch("pycbeta.verify.work_juan_numbers",
                               return_value=[]), \
                    mock.patch("pycbeta.cli.process_file", return_value=0), \
                    mock.patch("pycbeta.verify.generate_formal",
                               return_value=[gen]), \
                    mock.patch("pycbeta.verify.find_official",
                               return_value=[]), \
                    mock.patch("pycbeta.fetch.ensure_baselines",
                               side_effect=lambda w, n, p, e:
                               seen.update(wid=w, need=n, ebook=e)):
                P.return_value.parse.return_value = work
                with redirect_stdout(io.StringIO()):
                    main(["--config", cfgp, "-i", xml, "-f", "html",
                          "--verify", "--cbeta-ebook", eb])
            self.assertEqual(seen.get("ebook"), eb)
            self.assertEqual(seen.get("wid"), "T0001")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestCliMultiDocxMerge(unittest.TestCase):
    """CLI 多卷 docx 与 verify_one 同口径：merge_docx 合并（注归文末）再抽取，
    不得逐文件抽取后拼接（注插正文中间致大差异）。"""

    def test_merge_used_for_multi_docx(self):
        import io
        import json
        import shutil
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        from unittest import mock
        from pycbeta.cli import main
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "T01n0001.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            gen = os.path.join(d, "T0001.docx")
            with open(gen, "w", encoding="utf-8") as f:
                f.write("x")
            cfgp = os.path.join(d, "cfg.json")
            with open(cfgp, "w", encoding="utf-8") as f:
                json.dump({"verify": {"auto_fetch": False}}, f)
            vols = [os.path.join(d, f"v{i}.docx") for i in (1, 2, 3)]
            merged = os.path.join(d, "merged.docx")
            work = SimpleNamespace(id="T0001", metadata={"title": "T"})
            seen = {}

            def _find(source, stem, kind, juan=None, **kw):
                return list(vols) if kind == "docx" else []

            def _extract(path, strip_jiaozhu=True):
                if path == merged:
                    seen["extracted_merged"] = True
                    return "OFFICIAL_TEXT"
                return "GEN_TEXT"

            with mock.patch("pycbeta.parser.P5Parser") as P, \
                    mock.patch("pycbeta.verify.work_juan_numbers",
                               return_value=[1, 2, 3]), \
                    mock.patch("pycbeta.cli.process_file", return_value=0), \
                    mock.patch("pycbeta.verify.generate_formal",
                               return_value=[gen]), \
                    mock.patch("pycbeta.verify.find_official",
                               side_effect=_find), \
                    mock.patch("pycbeta.verify.merge_docx",
                               return_value=merged) as M, \
                    mock.patch("pycbeta.verify.extract_text",
                               side_effect=_extract):
                P.return_value.parse.return_value = work
                with redirect_stdout(io.StringIO()):
                    main(["--config", cfgp, "-i", xml, "-f", "docx",
                          "--verify"])
            M.assert_called_once()
            self.assertEqual(list(M.call_args.args[0]), vols)
            self.assertTrue(M.call_args.args[1].endswith(
                "_official_merged_docx.docx"))
            self.assertTrue(seen.get("extracted_merged"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestEpubTxtNeed(unittest.TestCase):
    """-f epub 缺基线时只拉 txt_notes（首选），epub/html 用现货。"""

    def test_fetch_need_is_txt_notes(self):
        import io
        import json
        import shutil
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        from unittest import mock
        from pycbeta.cli import main
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "T01n0001.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            gen = os.path.join(d, "T0001.epub")
            with open(gen, "w", encoding="utf-8") as f:
                f.write("x")
            cfgp = os.path.join(d, "cfg.json")
            with open(cfgp, "w", encoding="utf-8") as f:
                json.dump({"verify": {"auto_fetch": True}}, f)
            work = SimpleNamespace(id="T0001", metadata={})
            seen = {}
            with mock.patch("pycbeta.parser.P5Parser") as P, \
                    mock.patch("pycbeta.verify.work_juan_numbers",
                               return_value=[]), \
                    mock.patch("pycbeta.cli.process_file", return_value=0), \
                    mock.patch("pycbeta.verify.generate_formal",
                               return_value=[gen]), \
                    mock.patch("pycbeta.verify.find_official",
                               return_value=[]), \
                    mock.patch("pycbeta.fetch.ensure_baselines",
                               side_effect=lambda w, n, p, e:
                               seen.update(need=n)):
                P.return_value.parse.return_value = work
                with redirect_stdout(io.StringIO()):
                    main(["--config", cfgp, "-i", xml, "-f", "epub",
                          "--verify"])
            self.assertEqual(seen.get("need"), ["txt_notes"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestVersion(unittest.TestCase):
    def test_version_flag_matches_package(self):
        import io
        from contextlib import redirect_stdout
        from pycbeta import __version__
        from pycbeta.cli import main
        out = io.StringIO()
        with redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, out.getvalue())


class TestFragLines(unittest.TestCase):
    """校验报告片段：18 字窗口（旧行为）+ compare 文件行号 + 整行原文。"""

    def test_full_lines_and_numbers(self):
        from pycbeta.cli import _frag_lines
        out = _frag_lines(2, "replace", 1, 2, 1, 2, "甲乙丙", "甲丁丙",
                          {"gen_line": 5, "src_line": 7},
                          ["n1", "n2", "n3", "n4", "新行完整文本"],
                          ["s1", "s2", "s3", "s4", "s5", "s6", "源行完整文本"])
        text = "\n".join(out)
        self.assertIn("2.（源比较第7行，新比较第5行）", text)
        self.assertIn("【源】甲〖丁〗丙", text)  # 旧窗口行为不变
        self.assertIn("【新】甲〖乙〗丙", text)
        self.assertIn("【源整行】源行完整文本", text)
        self.assertIn("【新整行】新行完整文本", text)

    def test_missing_loc_falls_back(self):
        from pycbeta.cli import _frag_lines
        out = _frag_lines(1, "insert", 1, 1, 1, 4, "甲乙", "甲XYZ乙",
                          {}, ["甲乙"], ["甲XYZ乙"])
        text = "\n".join(out)
        self.assertTrue(text.startswith("      1."))
        self.assertNotIn("比较第", text)
        self.assertIn("（行号不可得）", text)

    def test_out_of_range_line_falls_back(self):
        from pycbeta.cli import _frag_lines
        out = _frag_lines(1, "replace", 0, 1, 0, 1, "甲", "乙",
                          {"gen_line": 99, "src_line": 0}, ["甲"], ["乙"])
        text = "\n".join(out)
        self.assertIn("（行号不可得）", text)

    def test_frag_locs_both_sides(self):
        from pycbeta.verify import _frag_locs
        off = [("base.html", "甲[0036004]行\n又【CB】，及【選集】\n尾行")]
        gen_index = ("text", [], [])
        src, gen = _frag_locs({"gen_line": 2, "src_line": 2},
                              ["甲行", "又【CB】，及【選集】"],
                              ["甲行", "又【CB】，及【選集】"],
                              off, gen_index, "甲行\n又【CB】，及【選集】")
        self.assertIn("base.html:2行", src)
        self.assertIn("生成文本第2行", gen)

    def test_query_runs_and_anchors(self):
        from pycbeta.verify import _query_runs, _nearest_anchor, _locate_hits
        qs = _query_runs("又【CB】，及【選集】")
        self.assertEqual(qs[0], "又【CB】，及【選集】")
        self.assertIn("又，及", qs)
        lines = ["甲[0036004]行", "中间", "目标行"]
        a, d = _nearest_anchor(lines, 2)
        self.assertEqual((a, d), ("[0036004]", 2))
        self.assertEqual(_nearest_anchor(["甲", "乙"], 1), ("", -1))
        hits = _locate_hits([("f.html", "甲[0036004]行\n目标行")], "目标行")
        self.assertEqual(hits, ["f.html:2行（[0036004]后1行）"])
        self.assertEqual(_locate_hits([("f.html", "甲")], "不存在串"), [])

    def test_gen_docx_index(self):
        import zipfile
        from pycbeta.verify import _gen_locate_index, _locate_gen_hits
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        dp = os.path.join(tmp, "a.docx")
        with zipfile.ZipFile(dp, "w") as z:
            z.writestr("word/document.xml",
                       "<w:body><w:p><w:t>第一段</w:t></w:p>"
                       "<w:p><w:t>第二段</w:t></w:p></w:body>")
            z.writestr("word/footnotes.xml",
                       '<w:footnotes><w:footnote w:id="7"><w:p><w:t>注文七</w:t></w:p>'
                       "</w:footnote></w:footnotes>")
        idx = _gen_locate_index("docx", [dp])
        self.assertEqual(idx[0], "docx")
        self.assertEqual(_locate_gen_hits(idx, "第二段"), ["正文第2段"])
        self.assertEqual(_locate_gen_hits(idx, "注文七"), ["脚注7"])
        self.assertEqual(_locate_gen_hits(idx, "没有串"), [])
        self.assertEqual(_gen_locate_index("txt", [])[0], "text")


if __name__ == "__main__":
    unittest.main()
