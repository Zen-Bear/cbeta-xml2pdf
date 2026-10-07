import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta import verify as V


def _write(p, text="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class TestDefaultVerifyRoot(unittest.TestCase):
    def test_appends_name(self):
        self.assertEqual(V.default_verify_root(os.path.join("d", "out")),
                         os.path.join(os.path.abspath(
                             os.path.join("d", "out")), "验证"))

    def test_empty_uses_cwd(self):
        self.assertEqual(V.default_verify_root(""),
                         os.path.join(os.getcwd(), "验证"))


class TestResolveVerifyRoot(unittest.TestCase):
    def test_custom_wins(self):
        r = V.resolve_verify_root(output_arg="/tmp/o", xml_fn="/tmp/x.xml",
                                   custom=" /tmp/c ")
        self.assertEqual(r, os.path.abspath("/tmp/c"))

    def test_dir_output(self):
        d = tempfile.mkdtemp(prefix="vroot-")
        try:
            self.assertEqual(V.resolve_verify_root(output_arg=d, xml_fn=""),
                             os.path.join(os.path.abspath(d), "验证"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_file_output_uses_dirname(self):
        self.assertEqual(
            V.resolve_verify_root(output_arg="/tmp/o/book.docx",
                                   xml_fn="/tmp/x.xml"),
            os.path.join(os.path.abspath("/tmp/o"), "验证"))

    def test_no_output_uses_xml_dir(self):
        self.assertEqual(
            V.resolve_verify_root(xml_fn=os.path.join("s", "x.xml")),
            os.path.join(os.path.abspath("s"), "验证"))


class TestParseVerifyReportName(unittest.TestCase):
    def test_full(self):
        self.assertEqual(V.parse_verify_report_name("T0349 書（验证）"),
                         {"id": "T0349", "title": "書"})

    def test_traditional_suffix(self):
        self.assertEqual(V.parse_verify_report_name("X1077 准提净业（驗證）"),
                         {"id": "X1077", "title": "准提净业"})

    def test_no_title(self):
        self.assertEqual(V.parse_verify_report_name("T1（验证）"),
                         {"id": "T1", "title": ""})

    def test_rejects(self):
        for bad in ("", "T0349", "A（验证）", "报告（验证）",
                    "T0349 書", "random dir", "T0349 書（验证）extra"):
            self.assertIsNone(V.parse_verify_report_name(bad), bad)


class TestFindVerifyReports(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vfind-")
        self.vroot = os.path.join(self.d, "验证")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_missing_root_is_empty(self):
        self.assertEqual(V.find_verify_reports(
            os.path.join(self.d, "nope")), [])

    def test_new_layout_found_legacy_ignored(self):
        hit = os.path.join(self.vroot, "T0349 書（验证）")
        _write(os.path.join(hit, "report.json"), "{}")
        _write(os.path.join(hit, "report.txt"), "t")
        # 旧平铺目录不得收录
        _write(os.path.join(self.d, "X1077 業（验证）", "report.json"), "{}")
        # 名字不像 work id 的跳过
        _write(os.path.join(self.vroot, "A（验证）", "report.json"), "{}")
        got = V.find_verify_reports(self.vroot)
        self.assertEqual(len(got), 1)
        e = got[0]
        self.assertEqual((e["id"], e["title"]), ("T0349", "書"))
        self.assertEqual(e["dir"], os.path.abspath(hit))
        self.assertEqual(e["report_json"], os.path.join(hit, "report.json"))
        self.assertEqual(e["report_txt"], os.path.join(hit, "report.txt"))

    def test_json_fallback_removed(self):
        # 机读结论只认 report.json：旧命名（stem / verify_report）不再发现
        hit = os.path.join(self.vroot, "T0349 書（验证）")
        _write(os.path.join(hit, "T0349_書_校验报告.json"), "{}")
        _write(os.path.join(hit, "T12n0349_verify_report.json"), "{}")
        (got,) = V.find_verify_reports(self.vroot)
        self.assertEqual(got["report_json"], "")

    def test_txt_fallback_still_supported(self):
        # txt 回退保留：stem 命名仍可发现（与 JSON 无关）
        hit = os.path.join(self.vroot, "T0349 書（验证）")
        _write(os.path.join(hit, "T0349_書_校验报告.txt"), "t")
        (got,) = V.find_verify_reports(self.vroot)
        self.assertEqual(got["report_json"], "")
        self.assertTrue(got["report_txt"].endswith("_校验报告.txt"))

    def test_no_reports_still_listed(self):
        hit = os.path.join(self.vroot, "T0001 無（验证）")
        os.makedirs(hit)
        (got,) = V.find_verify_reports(self.vroot)
        self.assertEqual((got["report_json"], got["report_txt"]), ("", ""))

    def test_sorted_by_dir(self):
        for n in ("X0002 乙（验证）", "T0001 甲（验证）"):
            os.makedirs(os.path.join(self.vroot, n))
        dirs = [e["dir"] for e in V.find_verify_reports(self.vroot)]
        self.assertEqual(dirs, sorted(dirs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
