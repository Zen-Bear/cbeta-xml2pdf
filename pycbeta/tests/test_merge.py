import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta import merge as M

import importlib.util as _ilu
_WRAPPER = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "test", "merge_cbreader.py")
_spec = _ilu.spec_from_file_location("merge_cbreader", _WRAPPER)
merge_cli = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(merge_cli)

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
    def test_per_vol(self):
        # 按册分组：同部跨册分家，不再跨册归一
        self.assertEqual(M._norm_group("TX", "TX07", "TX07n0006"),
                         ("TX", "TX07", "0006"))
        self.assertEqual(M._norm_group("TX", "TX08", "TX08n0006"),
                         ("TX", "TX08", "0006"))
        self.assertEqual(M._norm_group("T", "T01", "T01n0001"),
                         ("T", "T01", "0001"))

    def test_fallback(self):
        self.assertEqual(M._norm_group("T", "T01", "appendix"),
                         ("T", "T01", "appendix"))

    def test_only_match(self):
        m = M._only_match
        self.assertTrue(m("TX07n0006", "TX", "0006", {"TX07n0006", "TX08n0006"}))
        self.assertTrue(m("TXn0006", "TX", "0006", {"TX07n0006"}))
        self.assertTrue(m("TX0006", "TX", "0006", {"TX07n0006"}))
        self.assertTrue(m("", "TX", "0006", {"TX07n0006"}))
        self.assertFalse(m("TX0007", "TX", "0006", {"TX07n0006"}))

    def test_frag_key(self):
        self.assertEqual(
            M._frag_key(os.path.join("X", "TX07n0006_003.xml")),
            ("TX", "TX07", "0006", 3, "TX07n0006"))
        self.assertIsNone(M._frag_key("T12n0349.xml"))  # 整本非碎片
        self.assertIsNone(M._frag_key("foo_001.xml"))  # 无卷号形态按整文件


class TestCollectMerge(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.mkdtemp()
        # 同部跨册：TX07 ×2 + TX08 ×1 → 两组
        _write(self.src, "TX", "TX07", "TX07n0006_001.xml", "甲", "(第1卷-第6卷)")
        _write(self.src, "TX", "TX07", "TX07n0006_002.xml", "乙", "(第1卷-第6卷)",
               chars=CHAR)
        _write(self.src, "TX", "TX08", "TX08n0006_003.xml", "丙", "(第7卷-第15卷)")
        # 同册旧例 + 非碎片整本（不动）
        _write(self.src, "T", "T01", "T01n0001_001.xml", "子", "(全一卷)")
        _write(self.src, "T", "T01", "T01n0001.xml", "整本不动", "(全一卷)")

    def test_collect_groups_per_vol(self):
        groups = M.collect(self.src)
        self.assertIn(("TX", "TX07", "0006"), groups)
        self.assertIn(("TX", "TX08", "0006"), groups)
        self.assertIn(("T", "T01", "0001"), groups)
        # 整本文件未进组
        self.assertEqual(len(groups[("T", "T01", "0001")]), 1)
        got = sorted(groups[("TX", "TX07", "0006")])
        self.assertEqual([(v, s) for v, s, _, _ in got],
                         [("TX07", 1), ("TX07", 2)])

    def test_merge_per_vol(self):
        out = os.path.join(tempfile.mkdtemp(), "TX", "TX07", "TX07n0006.xml")
        groups = M.collect(self.src)
        got = M.merge(sorted(groups[("TX", "TX07", "0006")]), out)
        self.assertEqual(got[0], 2)
        from lxml import etree
        r = etree.parse(out).getroot()
        text = "".join(r.itertext())
        self.assertLess(text.find("甲"), text.find("乙"))
        self.assertNotIn("丙", text)  # 他册不串组
        # charDecl 组内并集（后卷 CB1 补进首卷 header）
        chars = [e for e in r.iter()
                 if e.tag.rsplit("}", 1)[-1] == "char"]
        self.assertEqual(len(chars), 1)
        self.assertEqual(got[1], 2)

    def test_split_paths(self):
        whole, groups = M.split_paths([
            os.path.join(self.src, "T", "T01", "T01n0001.xml"),
            os.path.join(self.src, "TX", "TX07", "TX07n0006_001.xml"),
            os.path.join(self.src, "TX", "TX08", "TX08n0006_003.xml"),
            os.path.join(self.src, "T", "T01", "appendix_001.xml"),
        ])
        self.assertEqual(len(whole), 2)  # 整本 + 无卷号形态
        self.assertEqual(sorted(groups), [("TX", "TX07", "0006"),
                                          ("TX", "TX08", "0006")])

    def test_resolve_prefers_whole(self):
        import unittest.mock as mock
        tmp = tempfile.mkdtemp()
        with mock.patch("pycbeta.fetch.find_local_xml",
                        return_value=["whole.xml"]):
            paths, merged = M.resolve_work_files(self.src, "TX", "0006", tmp)
            self.assertEqual(paths, ["whole.xml"])
            self.assertFalse(merged)

    def test_resolve_merges_frags(self):
        import unittest.mock as mock
        tmp = tempfile.mkdtemp()
        with mock.patch("pycbeta.fetch.find_local_xml", return_value=[]):
            paths, merged = M.resolve_work_files(self.src, "TX", "0006", tmp)
            self.assertTrue(merged)
            self.assertEqual(len(paths), 2)  # 两册两文件
            self.assertTrue(paths[0].endswith("TX07n0006.xml"))
            self.assertTrue(paths[1].endswith("TX08n0006.xml"))
            from lxml import etree
            t0 = "".join(etree.parse(paths[0]).getroot().itertext())
            self.assertIn("甲", t0)
            self.assertNotIn("丙", t0)

    def test_resolve_empty(self):
        import unittest.mock as mock
        with mock.patch("pycbeta.fetch.find_local_xml", return_value=[]):
            self.assertEqual(M.resolve_work_files(self.src, "ZZ", "9999",
                                                  tempfile.mkdtemp()),
                             ([], False))

    def test_main_only_forms(self):
        import io
        from contextlib import redirect_stdout
        for only in ("TX07n0006", "TXn0006", "TX0006"):
            out_root = tempfile.mkdtemp()
            buf = io.StringIO()
            with redirect_stdout(buf):
                merge_cli.main(["--src", self.src, "-o", out_root,
                                "--only", only])
            self.assertTrue(os.path.isfile(
                os.path.join(out_root, "TX", "TX07", "TX07n0006.xml")), only)
            if only == "TX0006":
                # 同 no 全中：两册各一文件
                self.assertTrue(os.path.isfile(
                    os.path.join(out_root, "TX", "TX08", "TX08n0006.xml")))


if __name__ == "__main__":
    unittest.main()
