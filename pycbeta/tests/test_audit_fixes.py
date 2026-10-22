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


if __name__ == "__main__":
    unittest.main()
