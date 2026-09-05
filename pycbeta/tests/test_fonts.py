"""P5 豆腐字检测：分区名 / cmap / 收字 / 覆盖判定（仅用仓内补充字形，不依赖系统字体）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.fonts import (
    block_name, font_cmap, collect_work_chars, check_coverage,
    font_check_report, format_font_report, supplement_path,
    FontLocator, read_family_names, search_fonts,
)
from pycbeta.model import E, Gaiji, Text, Work

SUPPLEMENT = supplement_path()
assert SUPPLEMENT, "随仓补充字形缺失：cbeta/fonts/CBETASupplement.ttf"


class FakeGaijiDb:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, code):
        return self._m.get(code)


def _work():
    return Work(
        id="T", source_file="", metadata={"title": "測試經", "author": ""},
        body=[E(tag="p", attrs={}, children=[
            Text(text="無量香𤬪燒"),
            Gaiji(code="CB00096", char="𤬪"),
            Gaiji(code="CB99999", char="中"),
        ])],
        notes_by_n={}, apps=[], simplified=False)


class TestBlock(unittest.TestCase):
    def test_blocks(self):
        self.assertEqual(block_name(0x4E2D), "CJK Unified")
        self.assertEqual(block_name(0x24B2A), "CJK Ext B")
        self.assertEqual(block_name(0x30000), "CJK Ext G")
        self.assertEqual(block_name(0xE000), "PUA")
        self.assertEqual(block_name(0x41), "U+0041")


class TestCmap(unittest.TestCase):
    def test_supplement(self):
        cm = font_cmap(SUPPLEMENT)
        self.assertIn(0x24B2A, cm)
        self.assertNotIn(0x4E2D, cm)

    def test_ttc_union(self):
        # TTC 按全部字重取并集（simsun.ttc 含 SimSun + NSimSun）
        cm = font_cmap(r"C:\Windows\Fonts\simsun.ttc")
        self.assertIn(0x5EB6, cm)
        self.assertTrue(len(cm) > 20000)


class TestListFonts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil
        cls.tmp = tempfile.mkdtemp()
        shutil.copy(SUPPLEMENT, os.path.join(cls.tmp, "CBETASupplement.ttf"))
        cls.loc = FontLocator(extra_dirs=[cls.tmp], scan_system=False)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_read_family_names(self):
        names = read_family_names(SUPPLEMENT)
        self.assertTrue(names)

    def test_search_by_filename(self):
        rows = search_fonts("CBETASupplement", self.loc)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0][0])
        self.assertTrue(rows[0][2].endswith(".ttf"))

    def test_search_no_hit(self):
        self.assertEqual(search_fonts("no-such-font-xyz", self.loc), [])

    def test_search_all(self):
        rows = search_fonts("", self.loc)
        self.assertEqual(len(rows), 1)


class TestCollect(unittest.TestCase):
    def test_collect(self):
        info = collect_work_chars(_work(), FakeGaijiDb({"CB00096": {"unicode": "24B2A"}}))
        # ASCII 跳过；𤬪 正文1 + 缺字解析1 = 2；中 正文（缺字码直通取 char 中）1
        self.assertNotIn("a", info)
        self.assertEqual(info["𤬪"]["count"], 2)
        self.assertIn("gaiji:CB00096", info["𤬪"]["sources"])
        self.assertIn("text", info["𤬪"]["sources"])
        self.assertEqual(info["中"]["count"], 1)
        self.assertIn("測試經", info["測"]["context"])

    def test_chardecl_fallback(self):
        w = _work()
        w.metadata["charDecl"] = {"CB00001": {"unicode": "4E2D"}}
        info = collect_work_chars(w, FakeGaijiDb({}))
        self.assertIn("中", info)


class TestCoverage(unittest.TestCase):
    def test_tofu_and_sup(self):
        info = collect_work_chars(_work(), FakeGaijiDb({"CB00096": {"unicode": "24B2A"}}))
        self.assertIn("𤬪", info)
        rep = font_check_report(_work(),
                                [("Supplement", SUPPLEMENT)],
                                FakeGaijiDb({"CB00096": {"unicode": "24B2A"}}))
        # 中 无覆盖 → tofu；𤬪 仅补充字形 → sup_only
        tofu_chars = [r["char"] for r in rep["tofu"]]
        sup_chars = [r["char"] for r in rep["sup_only"]]
        self.assertIn("中", tofu_chars)
        self.assertIn("𤬪", sup_chars)
        r = [x for x in rep["tofu"] if x["char"] == "中"][0]
        self.assertEqual(r["codepoint"], "U+4E2D")
        self.assertEqual(r["block"], "CJK Unified")
        text = format_font_report(rep, "T")
        self.assertIn("[TOFU] 中 U+4E2D", text)
        self.assertIn("[SUP ] 𤬪 U+24B2A", text)

    def test_missing_file(self):
        rep = font_check_report(_work(), [("Nope", r"E:\nonexistent\x.ttf")],
                                FakeGaijiDb({}))
        self.assertTrue(rep["missing_files"])
        text = format_font_report(rep, "T")
        self.assertIn("[MISS]", text)

    def test_fallback_tier(self):
        # 𤬪 仅 simsunb（系统回退字）覆盖 → FB 档，非 tofu
        rep = font_check_report(
            _work(), [], FakeGaijiDb({"CB00096": {"unicode": "24B2A"}}),
            [("SimSun-ExtB", r"C:\Windows\Fonts\simsunb.ttf")])
        fb_chars = [r["char"] for r in rep["fallback"]]
        self.assertIn("𤬪", fb_chars)
        self.assertEqual(rep["tofu"], [r for r in rep["tofu"] if r["char"] != "𤬪"])
        text = format_font_report(rep, "T")
        self.assertIn("[FB  ]", text)
        self.assertIn("fallback", text)


if __name__ == "__main__":
    unittest.main()
