import importlib.util
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_MERGE_PATH = os.path.join(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "test", "merge_cbreader.py")
_spec = importlib.util.spec_from_file_location("merge_cbreader", _MERGE_PATH)
merge_cbreader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(merge_cbreader)

FRAG = """<?xml version="1.0" encoding="utf-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:id="{stem}">
  <teiHeader>
    <fileDesc><titleStmt>
      <title level="m" xml:lang="zh-Hant">全書．第六編{rng}</title>
      <author>譯者甲</author>
    </titleStmt></fileDesc>
    <encodingDesc><charDecl>{chars}</charDecl></encodingDesc>
  </teiHeader>
  <text><body><p>{text}</p></body></text>
</TEI>"""

CHAR = ('<char xml:id="CB1"><charProp><localName>normalized form</localName>'
        '<value>解</value></charProp></char>')


def _write(d, canon, vol, fn, text, rng, chars=""):
    vd = os.path.join(d, canon, vol)
    os.makedirs(vd, exist_ok=True)
    stem = fn[:-8]  # 去 _NNN.xml
    with open(os.path.join(vd, fn), "w", encoding="utf-8") as f:
        f.write(FRAG.format(stem=stem, rng=rng, chars=chars, text=text))
    return os.path.join(vd, fn)


class TestNormGroup(unittest.TestCase):
    def test_cross_vol(self):
        self.assertEqual(merge_cbreader._norm_group("TX", "TX07", "TX07n0006"),
                         ("TX", "0006"))
        self.assertEqual(merge_cbreader._norm_group("T", "T01", "T01n0001"),
                         ("T", "0001"))

    def test_fallback(self):
        self.assertEqual(merge_cbreader._norm_group("T", "T01", "appendix"),
                         ("T", "T01/appendix"))

    def test_only_match(self):
        m = merge_cbreader._only_match
        self.assertTrue(m("TX07n0006", "TX", "0006", {"TX07n0006", "TX08n0006"}))
        self.assertTrue(m("TXn0006", "TX", "0006", {"TX07n0006"}))
        self.assertTrue(m("TX0006", "TX", "0006", {"TX07n0006"}))
        self.assertTrue(m("", "TX", "0006", {"TX07n0006"}))
        self.assertFalse(m("TX0007", "TX", "0006", {"TX07n0006"}))


class TestCollectMerge(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.mkdtemp()
        # 跨册：TX07 ×2 + TX08 ×1，seq 全局连续
        _write(self.src, "TX", "TX07", "TX07n0006_001.xml", "甲", "(第1卷-第6卷)")
        _write(self.src, "TX", "TX07", "TX07n0006_002.xml", "乙", "(第1卷-第6卷)",
               chars=CHAR)
        _write(self.src, "TX", "TX08", "TX08n0006_003.xml", "丙", "(第7卷-第15卷)")
        # 同卷旧例 + 非碎片整本（不动）
        _write(self.src, "T", "T01", "T01n0001_001.xml", "子", "(全一卷)")
        _write(self.src, "T", "T01", "T01n0001.xml", "整本不动", "(全一卷)")

    def test_collect_groups(self):
        groups = merge_cbreader.collect(self.src)
        self.assertIn(("TX", "0006"), groups)
        self.assertIn(("T", "0001"), groups)
        # 整本文件未进组
        self.assertEqual(len(groups[("T", "0001")]), 1)
        got = sorted(groups[("TX", "0006")])
        self.assertEqual([(v, s) for v, s, _, _ in got],
                         [("TX07", 1), ("TX07", 2), ("TX08", 3)])

    def test_merge_cross_vol(self):
        out = os.path.join(tempfile.mkdtemp(), "TX", "TX07", "TX07n0006.xml")
        groups = merge_cbreader.collect(self.src)
        got = merge_cbreader.merge(sorted(groups[("TX", "0006")]), out)
        self.assertEqual(got[0], 3)
        from lxml import etree
        r = etree.parse(out).getroot()
        text = "".join(r.itertext())
        # (vol, seq) 顺序拼接
        self.assertLess(text.find("甲"), text.find("乙"))
        self.assertLess(text.find("乙"), text.find("丙"))
        # charDecl 跨卷并集（后卷 CB1 补进首卷 header）
        chars = [e for e in r.iter()
                 if e.tag.rsplit("}", 1)[-1] == "char"]
        self.assertEqual(len(chars), 1)
        # 卷数 milestone 感知外：body 三段俱全
        self.assertEqual(got[1], 3)

    def test_merge_single_vol_unchanged_path(self):
        import io
        from contextlib import redirect_stdout
        out_root = tempfile.mkdtemp()
        buf = io.StringIO()
        with redirect_stdout(buf):
            merge_cbreader.main(["--src", self.src, "-o", out_root,
                                 "--only", "T01n0001"])
        self.assertTrue(os.path.isfile(
            os.path.join(out_root, "T", "T01", "T01n0001.xml")))

    def test_main_cross_vol_only_forms(self):
        import io
        from contextlib import redirect_stdout
        for only in ("TX07n0006", "TXn0006", "TX0006"):
            out_root = tempfile.mkdtemp()
            buf = io.StringIO()
            with redirect_stdout(buf):
                merge_cbreader.main(["--src", self.src, "-o", out_root,
                                     "--only", only])
            self.assertTrue(os.path.isfile(
                os.path.join(out_root, "TX", "TX07", "TX07n0006.xml")), only)
            self.assertIn("跨册", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
