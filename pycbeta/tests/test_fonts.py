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


def _mini_name_table(records):
    """records: [(platform, lang, nameId, text)] → name 表字节（仅单测造字用）。"""
    import struct
    blobs, recs = [], []
    head = 6 + 12 * len(records)
    off = head
    for plat, lang, nid, text in records:
        raw = text.encode("utf-16-be") if plat in (0, 3) else text.encode("latin-1")
        recs.append(struct.pack(">6H", plat, 1, lang, nid, len(raw), off - head))
        blobs.append(raw)
        off += len(raw)
    return struct.pack(">HHH", 0, len(recs), head) + b"".join(recs) + b"".join(blobs)


def _mini_ttf(path, records):
    """最小 TTF（仅 name 表，供地域归一测试；不依赖系统字体）。"""
    import struct
    name_tab = _mini_name_table(records)
    header = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    entry = struct.pack(">4sIII", b"name", 0, 12 + 16, len(name_tab))
    with open(path, "wb") as f:
        f.write(header + entry + name_tab)


def _mini_ttc(path, faces_records):
    """最小 TTC（多字重同文件，供串字重测试；表偏移为绝对偏移，与真实文件一致）。"""
    import struct
    name_tabs = [_mini_name_table(r) for r in faces_records]
    n = len(name_tabs)
    base = 12 + 4 * n
    bodies, entries = [], []
    off = base
    for name_tab in name_tabs:
        entries.append((off, name_tab))
        off += 12 + 16 + len(name_tab)
    out = [struct.pack(">4sII", b"ttcf", 0x00010000, n)]
    for body_off, _tab in entries:
        out.append(struct.pack(">I", body_off))
    with open(path, "wb") as f:
        f.write(b"".join(out))
        for body_off, name_tab in entries:
            f.write(struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
                    + struct.pack(">4sIII", b"name", 0, body_off + 12 + 16,
                                  len(name_tab))
                    + name_tab)


class TestPreferredFamilyLocale(unittest.TestCase):
    """preferred_family 地域归一（自造字体，不依赖系统字体装了什么）。

    背景：霞鹜文楷 TC 的 0x404 名用鶩 U+9DA9、0x804 名用鹜 U+9E5C；
    OOXML 精确匹配要求写 GDI 可见的那个，否则 Word/WPS 回退宋体。
    """

    TRAD = "A鶩B"  # U+9DA9
    SIMP = "A鹜B"  # U+9E5C
    LAT = "ALatB"

    def _loc(self, tmp):
        import pycbeta.fonts as F
        _mini_ttf(os.path.join(tmp, "t.ttf"), [
            (3, 0x404, 1, self.TRAD),
            (3, 0x409, 1, self.LAT),
            (3, 0x804, 1, self.SIMP),
        ])
        return F.FontLocator(extra_dirs=[tmp], scan_system=False)

    def _use(self, loc):
        import pycbeta.fonts as F
        old = F._locator
        F._locator = loc
        self.addCleanup(setattr, F, "_locator", old)
        old_env = os.environ.get("PYCBETA_UI_LANG")
        self.addCleanup(lambda: (os.environ.pop("PYCBETA_UI_LANG", None)
                                 if old_env is None
                                 else os.environ.update(
                                     PYCBETA_UI_LANG=old_env)))

    def test_trad_input_simplified_system(self):
        import shutil
        import pycbeta.fonts as F
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self._use(self._loc(tmp))
        os.environ["PYCBETA_UI_LANG"] = "0x804"
        self.assertEqual(F.preferred_family(self.TRAD), self.SIMP)

    def test_trad_input_trad_system_keeps(self):
        import shutil
        import pycbeta.fonts as F
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self._use(self._loc(tmp))
        os.environ["PYCBETA_UI_LANG"] = "0x404"
        self.assertEqual(F.preferred_family(self.TRAD), self.TRAD)

    def test_ascii_input_keeps(self):
        import shutil
        import pycbeta.fonts as F
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self._use(self._loc(tmp))
        os.environ["PYCBETA_UI_LANG"] = "0x804"
        self.assertEqual(F.preferred_family(self.LAT), self.LAT)

    def test_missing_font_keeps(self):
        import pycbeta.fonts as F
        self._use(F.FontLocator(extra_dirs=[], scan_system=False))
        os.environ["PYCBETA_UI_LANG"] = "0x804"
        self.assertEqual(F.preferred_family("NoSuchFontXYZ"), "NoSuchFontXYZ")

    def test_ttc_same_face(self):
        """多字重：PMingLiU 字重不出 MingLiU（同字重取英文名）。"""
        import shutil
        import pycbeta.fonts as F
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        _mini_ttc(os.path.join(tmp, "m.ttc"), [
            [(3, 0x409, 1, "MingLiU"), (3, 0x404, 1, "細明體")],
            [(3, 0x409, 1, "PMingLiU"), (3, 0x404, 1, "新細明體")],
        ])
        self._use(F.FontLocator(extra_dirs=[tmp], scan_system=False))
        os.environ["PYCBETA_UI_LANG"] = "0x409"
        self.assertEqual(F.preferred_family("新細明體"), "PMingLiU")


if __name__ == "__main__":
    unittest.main()
