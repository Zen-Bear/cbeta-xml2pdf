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


if __name__ == "__main__":
    unittest.main()
