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


class FingerprintFixture(unittest.TestCase):
    """tmp 自包含夹具：work xml + html 基线 + 最小 presets（无网络/无仓库数据）。"""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vfp-")
        self.xml = _write(os.path.join(self.d, "T01n0001.xml"),
                          "<TEI><text><body><p>甲乙丙</p></body></text></TEI>")
        self.base = _write(os.path.join(self.d, "T01n0001.html"),
                           "<html><body><p>甲乙丙</p></body></html>")
        self.cfg = os.path.join(self.d, "cfg.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"output": {}, "verify": {}}, f)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def fp(self, **kw):
        kw.setdefault("xml_files", [self.xml])
        kw.setdefault("config_path", self.cfg)
        return V.verify_fingerprint("T0001", "html", **kw)


class TestDeterminism(FingerprintFixture):
    def test_same_inputs_same_fp(self):
        a = self.fp()
        b = self.fp()
        self.assertIsNotNone(a)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("verify-fp-1:sha256:"))

    def test_xml_change_invalidates(self):
        a = self.fp()
        with open(self.xml, "a", encoding="utf-8") as f:
            f.write("<p>丁</p>")
        self.assertNotEqual(a, self.fp())

    def test_config_change_invalidates(self):
        a = self.fp()
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"output": {"verse_caesura": "XXX"},
                       "verify": {}}, f)
        self.assertNotEqual(a, self.fp())

    def test_threshold_change_invalidates(self):
        self.assertNotEqual(self.fp(), self.fp(max_diff=5))

    def test_baseline_change_invalidates(self):
        a = self.fp()
        with open(self.base, "a", encoding="utf-8") as f:
            f.write("more")
        self.assertNotEqual(a, self.fp())

    def test_baseline_removed_is_none(self):
        os.remove(self.base)
        self.assertIsNone(self.fp())

    def test_t2s_tracked(self):
        self.assertNotEqual(self.fp(t2s=False), self.fp(t2s=True))

    def test_pdf_differs_and_records_coverage(self):
        # pdf 默认被 docx 覆盖：需 docx 基线在场才可证明
        docx = os.path.join(self.d, "T01n0001.docx")
        with open(docx, "w", encoding="utf-8") as f:
            f.write("docx")
        a = self.fp()
        b = V.verify_fingerprint("T0001", "pdf", xml_files=[self.xml],
                                 config_path=self.cfg)
        self.assertIsNotNone(b)
        self.assertNotEqual(a, b)

    def test_preferred_baseline_missing_is_none(self):
        # 首选基线缺失：实际跑会触发下载（副作用），本次不能证明 → None
        # （夹具仅 html；docx 首选 docx 缺席）
        self.assertIsNone(V.verify_fingerprint(
            "T0001", "docx", xml_files=[self.xml], config_path=self.cfg))


class TestPresetsParam(FingerprintFixture):
    """`verify_fingerprint(presets=)`：同一 effective 配置下三种调用逐字一致；
    `presets=None` 保持现状；裸预设（含主题键）走出厂深合并（分类器回归）。

    P2、下游 presets 入参提案 §3/§6 验收。"""

    def _setup_configs(self):
        st = os.path.join(self.d, "st.json")
        with open(st, "w", encoding="utf-8") as f:
            json.dump({"output": {"strip_head_no": False},
                        "verify": {"scope_juan": True},
                        "pdf-docx-user-theme": "large-print.css"}, f)
        run = os.path.join(self.d, "run.json")
        with open(run, "w", encoding="utf-8") as f:
            json.dump({"config-json": st,
                       "html-epub-theme": "html_epub_official.css",
                       "html-epub-user-theme": "",
                       "pdf-docx-theme": "pdf_docx.css",
                       "pdf-docx-user-theme": ""}, f)
        return st, run

    def test_three_forms_identical(self):
        from pycbeta.theme import load_effective_presets
        st, run = self._setup_configs()
        eff = load_effective_presets(run)
        kw = dict(xml_files=[self.xml])
        a = V.verify_fingerprint("T0001", "html", config_path=st, **kw)
        b = V.verify_fingerprint("T0001", "html", config_path=run, **kw)
        c = V.verify_fingerprint("T0001", "html", presets=eff, **kw)
        self.assertIsNotNone(a)
        self.assertEqual(a, b)
        self.assertEqual(b, c)

    def test_presets_none_keeps_config_path_behavior(self):
        st, run = self._setup_configs()
        kw = dict(xml_files=[self.xml])
        a = V.verify_fingerprint("T0001", "html", config_path=run, **kw)
        b = V.verify_fingerprint(
            "T0001", "html", config_path=run, presets=None, **kw)
        self.assertIsNotNone(a)
        self.assertEqual(a, b)

    def test_classifier_deep_merges_theme_keyed_preset(self):
        from pycbeta.theme import (load_effective_presets, load_presets,
                                    deep_merge)
        st, run = self._setup_configs()
        self.assertEqual(load_effective_presets(st),
                         deep_merge(load_presets(), load_presets(st)))
        self.assertEqual(load_effective_presets(st),
                         load_effective_presets(run))

    def test_build_report_json_presets_passthrough(self):
        from pycbeta.theme import load_effective_presets
        st, run = self._setup_configs()
        eff = load_effective_presets(run)
        rec = {"fmt": "html", "xml": self.xml, "status": "ok", "missing": 0,
               "extra": 0, "gen": [self.base]}
        kw = dict(xml_files=[self.xml], config_path=run,
                  requested_formats=["html"])
        j1 = V.build_report_json("T0001", [rec], **kw)
        j2 = V.build_report_json("T0001", [rec], presets=eff, **kw)
        self.assertEqual(j1, j2)
        self.assertTrue(j1["fmts"]["html"]["fingerprint"].startswith(
            "verify-fp-1:sha256:"))


class TestNoneCases(FingerprintFixture):
    def test_unknown_fmt(self):
        self.assertIsNone(V.verify_fingerprint(
            "T0001", "bogus", xml_files=[self.xml], config_path=self.cfg))

    def test_missing_xml(self):
        self.assertIsNone(V.verify_fingerprint(
            "T0001", "html", xml_files=[os.path.join(self.d, "no.xml")],
            config_path=self.cfg))

    def test_empty_xml_list(self):
        self.assertIsNone(V.verify_fingerprint(
            "T0001", "html", xml_files=[], config_path=self.cfg))

    def test_no_locate_no_download(self):
        # xml_files=None 且无本地源 → None（绝不下载/物化）
        self.assertIsNone(V.verify_fingerprint(
            "ZZ9999", "html", config_path=self.cfg))


class TestNoSideEffects(FingerprintFixture):
    def test_dir_snapshot_unchanged_and_quiet(self):
        import io
        from contextlib import redirect_stdout
        before = {}
        for dp, _, fns in os.walk(self.d):
            for fn in fns:
                p = os.path.join(dp, fn)
                st = os.stat(p)
                with open(p, "rb") as f:
                    before[p] = (st.st_size, st.st_mtime_ns, f.read())
        buf = io.StringIO()
        with redirect_stdout(buf):
            fp = self.fp()
        self.assertIsNotNone(fp)
        self.assertEqual(buf.getvalue(), "")
        after = {}
        for dp, _, fns in os.walk(self.d):
            for fn in fns:
                p = os.path.join(dp, fn)
                st = os.stat(p)
                with open(p, "rb") as f:
                    after[p] = (st.st_size, st.st_mtime_ns, f.read())
        self.assertEqual(before, after)


class TestImplDigest(unittest.TestCase):
    def test_stable_and_sensitive(self):
        d = tempfile.mkdtemp(prefix="vfpimpl-")
        try:
            a = os.path.join(d, "a.py")
            b = os.path.join(d, "b.py")
            with open(a, "w", encoding="utf-8") as f:
                f.write("x = 1\n")
            with open(b, "w", encoding="utf-8") as f:
                f.write("y = 2\n")
            d1 = V._impl_digest(modules=["a", "b"], pkg_dir=d)
            self.assertEqual(d1, V._impl_digest(modules=["a", "b"], pkg_dir=d))
            with open(b, "w", encoding="utf-8") as f:
                f.write("y = 3\n")
            self.assertNotEqual(
                d1, V._impl_digest(modules=["a", "b"], pkg_dir=d))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_real_digest_stable(self):
        self.assertEqual(V._impl_digest(), V._impl_digest())


class TestCanonicalConfig(unittest.TestCase):
    def test_show_notes_excluded(self):
        a = V.canonical_verify_config(_presets={"output": {"show_notes": True},
                                                "verify": {}})
        b = V.canonical_verify_config(_presets={"output": {"show_notes": False},
                                                "verify": {}})
        self.assertIsNotNone(a)
        self.assertEqual(
            V._sha256_bytes(__import__("json").dumps(
                a, sort_keys=True, ensure_ascii=True).encode("utf-8")),
            V._sha256_bytes(__import__("json").dumps(
                b, sort_keys=True, ensure_ascii=True).encode("utf-8")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
