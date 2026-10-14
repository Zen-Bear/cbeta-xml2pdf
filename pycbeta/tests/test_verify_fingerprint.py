import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

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
        self.assertTrue(a.startswith(V._FP_VERSION + ":sha256:"))

    def test_mtime_change_does_not_invalidate(self):
        """同字节重写（仅 mtime 变）不改指纹：载荷不含 mtime_ns（2026-10-14 修正）。"""
        a = self.fp()
        st = os.stat(self.base)
        os.utime(self.base, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
        self.assertNotEqual(os.stat(self.base).st_mtime_ns, st.st_mtime_ns)
        self.assertEqual(a, self.fp())

    def test_fp_identity_excludes_mtime(self):
        self.assertEqual(sorted(V._fp_file_identity(self.base)),
                         ["name", "sha256", "size"])

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


class TestDirectLookup(unittest.TestCase):
    """集中库布局直接定位（2026-10-14 提速）：与通配符同集合、同顺序；非该布局回退通配符。"""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vdir-")
        # 集中库布局：{root}/{canon}/{work_id}/{work_id}_{NNN}.{ext}；单文件 {root}/{canon}/{id}.{ext}
        for n in (1, 2, 3):
            _write(os.path.join(self.d, "T", "T0001", f"T0001_{n:03d}.html"), "x")
        _write(os.path.join(self.d, "T", "T0001", "T0001_001.docx"), "x")
        _write(os.path.join(self.d, "T", "T0001.epub"), "x")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _both(self, kind, **kw):
        a = V._find_official_in(self.d, "T01n0001", kind, **kw)
        with mock.patch.object(V, "_direct_official", return_value=[]):
            b = V._find_official_in(self.d, "T01n0001", kind, **kw)
        return a, b

    def test_library_layout_equivalent(self):
        for kind in ("html", "docx", "epub"):
            a, b = self._both(kind)
            self.assertTrue(a, kind)              # 直接定位命中
            self.assertEqual(a, b, kind)          # 与通配符同集合、同顺序

    def test_juan_filter_equivalent(self):
        a, b = self._both("html", juan={2})
        self.assertEqual([os.path.basename(x) for x in a], ["T0001_002.html"])
        self.assertEqual(a, b)

    def test_unknown_layout_falls_back(self):
        flat = tempfile.mkdtemp(prefix="vflat-")
        try:
            _write(os.path.join(flat, "T01n0001.html"), "x")
            a = V._find_official_in(flat, "T01n0001", "html")
            self.assertEqual([os.path.basename(x) for x in a], ["T01n0001.html"])
        finally:
            shutil.rmtree(flat, ignore_errors=True)


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
        # created_at 为生成时刻（跨秒会不同），非本次断言对象：剔除后再比
        j1.pop("created_at", None)
        j2.pop("created_at", None)
        self.assertEqual(j1, j2)
        self.assertTrue(j1["fmts"]["html"]["fingerprint"].startswith(
            V._FP_VERSION + ":sha256:"))


class TestJuanParam(FingerprintFixture):
    """`verify_fingerprint(juan=)`（P11）：None 逐字回归；归一等价/互异；
    非法 → None；基线卷限定（**真子集严格语义**：无对应卷文件 → 不能证明）。"""

    def _add_vol_baselines(self):
        for n in ("001", "002", "003", "004"):
            _write(os.path.join(self.d, f"T0001_{n}.html"), "<html/>")

    def test_none_matches_legacy(self):
        self.assertEqual(self.fp(), self.fp(juan=None))

    def test_empty_list_is_none(self):
        self.assertEqual(self.fp(), self.fp(juan=[]))

    def test_normalization_equivalent(self):
        self._add_vol_baselines()
        a = self.fp(juan=[(2, 2), (1, 1)])
        b = self.fp(juan=[(1, 1), (2, 2)])
        self.assertIsNotNone(a)
        self.assertEqual(a, b)

    def test_none_vs_subset_and_subsets_differ(self):
        self._add_vol_baselines()
        whole = self.fp()
        s1 = self.fp(juan=[(1, 2)])
        s2 = self.fp(juan=[(3, 4)])
        self.assertNotEqual(whole, s1)
        self.assertNotEqual(s1, s2)

    def test_subset_without_volume_baseline_is_none(self):
        """真子集无对应卷基线 → 不能证明（None），整部单文件不充数。"""
        self.assertIsNone(self.fp(juan=[(1, 2)]))

    def test_invalid_returns_none(self):
        for bad in ([(0, 1)], [(2, 1)], [("a", 1)], "2-3", [(1,)]):
            self.assertIsNone(self.fp(juan=bad), msg=repr(bad))

    def test_baseline_scoped(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        for n in ("001", "002"):
            _write(os.path.join(d, f"T0001_{n}.html"), "<html/>")
        scoped = V._official_superset(d, "T0001", {}, juan=[(1, 1)])
        self.assertEqual(
            [os.path.basename(p) for p in scoped.get("html", [])],
            ["T0001_001.html"])
        whole = V._official_superset(d, "T0001", {})
        self.assertEqual(
            sorted(os.path.basename(p) for p in whole.get("html", [])),
            ["T0001_001.html", "T0001_002.html"])

    def test_baseline_scoped_strict_absence(self):
        """真子集无对应卷 → 该种缺席（不回落全量；与 verify_one 严格语义一致）。"""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        _write(os.path.join(d, "T0001_001.html"), "<html/>")
        scoped = V._official_superset(d, "T0001", {}, juan=[(2, 2)])
        self.assertEqual(scoped.get("html", []), [])


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
