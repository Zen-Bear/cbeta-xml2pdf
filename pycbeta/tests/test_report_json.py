import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta import verify as V


def _write(p, text="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class JsonFixture(unittest.TestCase):
    """tmp 自包含夹具：work xml + html 基线 + 最小 cfg（无网络/无仓库数据）。"""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vrj-")
        # 生成档放独立输出根（生产布局：源目录与输出根分离，避免
        # find_official 递归把生成档误当基线）
        self.o = tempfile.mkdtemp(prefix="vrjout-")
        self.xml = _write(os.path.join(self.d, "T01n0001.xml"),
                          "<TEI><text><body><p>甲乙丙</p></body></text></TEI>")
        self.base = _write(os.path.join(self.d, "T01n0001.html"),
                           "<html><body><p>甲乙丙</p></body></html>")
        self.gen = _write(os.path.join(self.o, "html",
                                       "T01n0001.html"), "<html>甲乙丙</html>")
        self.cfg = os.path.join(self.d, "cfg.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"output": {}, "verify": {}}, f)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        shutil.rmtree(self.o, ignore_errors=True)

    def rec(self, **kw):
        r = {"xml": self.xml, "fmt": "html", "status": "ok",
             "gen": [self.gen], "official": self.base,
             "official_kind": "html", "missing": 0, "extra": 0,
             "total": 0, "trials": []}
        r.update(kw)
        return r

    def build(self, records, **kw):
        kw.setdefault("xml_files", [self.xml])
        kw.setdefault("config_path", self.cfg)
        return V.build_report_json("T0001", records, **kw)


class TestVerdictFor(unittest.TestCase):
    def test_ok_is_pass(self):
        self.assertEqual(V.verdict_for({"status": "ok"}), ("pass", None))

    def test_ok_case_insensitive(self):
        self.assertEqual(V.verdict_for({"status": "OK"}), ("pass", None))

    def test_fail_counts(self):
        v, reason = V.verdict_for({"status": "fail", "missing": 3,
                                   "extra": 1})
        self.assertEqual(v, "fail")
        self.assertIn("3", reason)
        self.assertIn("1", reason)

    def test_fail_fallback_trial_counts(self):
        v, reason = V.verdict_for({"status": "fail", "trials": [
            {"kind": "html", "missing": 2, "extra": 0}]})
        self.assertEqual(v, "fail")
        self.assertIn("2", reason)

    def test_struct_on_ok_is_fail(self):
        v, reason = V.verdict_for({"status": "ok", "missing": 0,
                                   "extra": 0,
                                   "struct_issues": ["word/document.xml: x"]})
        self.assertEqual(v, "fail")
        self.assertIn("struct_illegal", reason)

    def test_no_baseline(self):
        self.assertEqual(V.verdict_for({"status": "no_baseline"}),
                         ("undetermined", "no_baseline"))

    def test_covered_keeps_source(self):
        self.assertEqual(V.verdict_for({"status": "covered",
                                        "cover_by": "docx"}),
                         ("undetermined", "covered:docx"))

    def test_nogen_is_gen_not_found(self):
        self.assertEqual(V.verdict_for({"status": "nogen"}),
                         ("undetermined", "gen_not_found"))

    def test_error_keeps_detail(self):
        v, reason = V.verdict_for({"status": "error", "detail": "渲染失败"})
        self.assertEqual(v, "error")
        self.assertEqual(reason, "渲染失败")

    def test_unknown_is_error(self):
        v, reason = V.verdict_for({"status": "bogus"})
        self.assertEqual(v, "error")
        self.assertIn("bogus", reason)

    def test_missing_status_is_error(self):
        v, _ = V.verdict_for({})
        self.assertEqual(v, "error")


class TestBuildReportJson(JsonFixture):
    def test_top_keys(self):
        j = self.build([self.rec()])
        self.assertEqual(
            sorted(j), ["created_at", "fingerprint_version", "fmts",
                        "inputs", "juan", "requested_formats", "schema",
                        "thresholds", "tool", "verify_impl", "work"])
        self.assertEqual(j["schema"], 1)
        self.assertEqual(j["fingerprint_version"], "verify-fp-1")
        self.assertEqual(j["work"], "T0001")
        self.assertEqual(j["requested_formats"], ["html"])
        self.assertEqual(j["thresholds"], {"max_diff": 10, "diff_lines": 5})
        self.assertEqual(j["tool"]["name"], "pycbeta")
        self.assertTrue(j["tool"]["version"])
        self.assertEqual(j["verify_impl"]["module"], "pycbeta.verify")
        self.assertTrue(j["verify_impl"]["digest"].startswith("sha256:"))
        datetime.fromisoformat(j["created_at"])  # 可解析即过
        self.assertEqual(
            sorted(j["inputs"]),
            ["baselines", "config_digest", "coverage", "xml_files"])

    def test_juan_self_described_and_passthrough(self):
        j = self.build([self.rec()], juan=[(2, 3)])
        self.assertEqual(j["juan"], {"segments": [[2, 3]], "label": "2-3"})
        self.assertEqual(
            j["fmts"]["html"]["fingerprint"],
            V.verify_fingerprint("T0001", "html", xml_files=[self.xml],
                                 config_path=self.cfg, juan=[(2, 3)]))

    def test_juan_none_by_default(self):
        self.assertIsNone(self.build([self.rec()])["juan"])
        self.assertIsNone(self.build([self.rec()], juan=[])["juan"])

    def test_fmt_entry_keys(self):
        j = self.build([self.rec()])
        self.assertEqual(
            sorted(j["fmts"]["html"]),
            ["diff_scope", "extra", "fingerprint", "formal_outputs", "missing",
             "reason", "report", "verdict"])

    def test_diff_scope_aggregate(self):
        # 旁路正文比对结论：body > unknown > notes_only；无记录 → None
        def rec(scope, **kw):
            r = self.rec(**kw)
            if scope is not None:
                r["diff_scope"] = scope
            return r
        self.assertIsNone(self.build([self.rec()])["fmts"]["html"]["diff_scope"])
        self.assertEqual(self.build([rec("notes_only")])["fmts"]["html"]["diff_scope"],
                         "notes_only")
        self.assertEqual(self.build([rec("notes_only"), rec("unknown")])
                         ["fmts"]["html"]["diff_scope"], "unknown")
        self.assertEqual(self.build([rec("notes_only"), rec("body")])
                         ["fmts"]["html"]["diff_scope"], "body")

    def test_pass_record(self):
        j = self.build([self.rec()])
        e = j["fmts"]["html"]
        self.assertEqual(e["verdict"], "pass")
        self.assertIsNone(e["reason"])
        self.assertEqual((e["missing"], e["extra"]), (0, 0))
        self.assertEqual(e["formal_outputs"], [self.gen])
        self.assertEqual(e["report"], "report.txt")

    def test_fingerprint_consistent(self):
        j = self.build([self.rec()])
        self.assertEqual(j["fmts"]["html"]["fingerprint"],
                         V.verify_fingerprint("T0001", "html",
                                              xml_files=[self.xml],
                                              config_path=self.cfg))

    def test_discovery_reused_across_formats(self):
        # build_report_json 只做一次基线发现（5 种 kind），而非每格式各一次；
        # 多格式时避免 (1+N) 次基线目录重扫。
        calls = []
        orig = V.find_official
        V.find_official = lambda *a, **k: (calls.append(a) or orig(*a, **k))
        try:
            j = self.build(
                [self.rec(fmt="html"),
                 self.rec(fmt="docx", status="no_baseline")],
                requested_formats=["html", "docx"])
        finally:
            V.find_official = orig
        self.assertEqual(j["fmts"]["html"]["verdict"], "pass")
        self.assertLessEqual(len(calls), 5)   # 5 kind × 1 次；不是 (1+2)×5
        # 复用后指纹仍与独立调用一致
        self.assertEqual(j["fmts"]["html"]["fingerprint"],
                         V.verify_fingerprint("T0001", "html",
                                              xml_files=[self.xml],
                                              config_path=self.cfg))

    def test_config_digest_consistent(self):
        j = self.build([self.rec()])
        canon = V.canonical_verify_config(self.cfg)
        expect = "sha256:" + V._sha256_bytes(json.dumps(
            canon, sort_keys=True, ensure_ascii=True).encode("utf-8"))
        self.assertEqual(j["inputs"]["config_digest"], expect)

    def test_inputs_xml_and_baseline(self):
        j = self.build([self.rec()])
        self.assertEqual(
            [x["name"] for x in j["inputs"]["xml_files"]], ["T01n0001.xml"])
        self.assertEqual(
            sorted(j["inputs"]["xml_files"][0]), ["mtime_ns", "name", "size"])
        self.assertEqual(
            [b["name"] for b in j["inputs"]["baselines"]["html"]],
            ["T01n0001.html"])

    def test_fail_record(self):
        j = self.build([self.rec(status="fail", missing=7, extra=2,
                                  total=9)])
        e = j["fmts"]["html"]
        self.assertEqual(e["verdict"], "fail")
        self.assertEqual((e["missing"], e["extra"]), (7, 2))
        self.assertIn("7", e["reason"])

    def test_combine_worst_wins_and_sums(self):
        j = self.build([self.rec(),
                        self.rec(status="fail", missing=4, extra=1,
                                 total=5)])
        e = j["fmts"]["html"]
        self.assertEqual(e["verdict"], "fail")
        self.assertEqual((e["missing"], e["extra"]), (4, 1))

    def test_error_beats_undetermined(self):
        j = self.build([self.rec(status="no_baseline", gen=[],
                                  missing=None, extra=None),
                        self.rec(status="error", detail="占用",
                                 missing=None, extra=None)])
        e = j["fmts"]["html"]
        self.assertEqual(e["verdict"], "error")
        self.assertIn("占用", e["reason"])
        self.assertIn("no_baseline", e["reason"])

    def test_no_baseline_fingerprint_none(self):
        os.remove(self.base)
        j = self.build([self.rec(status="no_baseline", gen=[])])
        e = j["fmts"]["html"]
        self.assertEqual(e["verdict"], "undetermined")
        self.assertEqual(e["reason"], "no_baseline")
        self.assertIsNone(e["fingerprint"])

    def test_no_record_requested(self):
        j = self.build([], requested_formats=["html"])
        e = j["fmts"]["html"]
        self.assertEqual(e["verdict"], "undetermined")
        self.assertEqual(e["reason"], "no_record")

    def test_xml_derived_from_records(self):
        j = V.build_report_json("T0001", [self.rec()],
                                config_path=self.cfg)
        self.assertEqual(
            [x["name"] for x in j["inputs"]["xml_files"]], ["T01n0001.xml"])

    def test_pdf_coverage(self):
        j = self.build([self.rec(fmt="pdf", status="no_baseline", gen=[])],
                       requested_formats=["pdf"])
        self.assertIn("pdf", j["inputs"]["coverage"])
        self.assertEqual(j["fmts"]["pdf"]["verdict"], "undetermined")

    def test_json_roundtrip_sorted(self):
        j = self.build([self.rec()])
        s = json.dumps(j, sort_keys=True, ensure_ascii=True)
        self.assertEqual(json.loads(s)["fmts"]["html"]["verdict"], "pass")

    def test_quiet_and_no_side_effects(self):
        before = {}
        for dp, _, fns in os.walk(self.d):
            for fn in fns:
                p = os.path.join(dp, fn)
                st = os.stat(p)
                with open(p, "rb") as f:
                    before[p] = (st.st_size, st.st_mtime_ns, f.read())
        buf = io.StringIO()
        with redirect_stdout(buf):
            j = self.build([self.rec()])
        self.assertEqual(j["fmts"]["html"]["verdict"], "pass")
        self.assertEqual(buf.getvalue(), "")
        after = {}
        for dp, _, fns in os.walk(self.d):
            for fn in fns:
                p = os.path.join(dp, fn)
                st = os.stat(p)
                with open(p, "rb") as f:
                    after[p] = (st.st_size, st.st_mtime_ns, f.read())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
