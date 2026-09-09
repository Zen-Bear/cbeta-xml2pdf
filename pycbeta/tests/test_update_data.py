import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.update_data import update_all, format_report, load_sources


GAIJI_URL = "http://example/gaiji.json"
TTF_URL = "http://example/supp.ttf"


def _dl(mapping):
    def fake(url, dest):
        if url not in mapping:
            return False
        with open(dest, "wb") as f:
            f.write(mapping[url])
        return True
    return fake


def _sources():
    return [
        {"key": "gaiji", "kind": "json-dict", "url": GAIJI_URL,
         "dest": ("cbeta", "data", "cbeta_gaiji.json"), "note": ""},
        {"key": "supplement-ttf", "kind": "ttf", "url": TTF_URL,
         "dest": ("cbeta", "fonts", "CBETASupplement.ttf"), "note": ""},
        {"key": "siddham-fonts", "kind": "manual",
         "url": "http://example/dl", "dest": (), "note": "手动下载"},
    ]


class TestUpdateData(unittest.TestCase):
    def setUp(self):
        import shutil
        self.root = tempfile.mkdtemp()
        self._shutil = shutil
        os.makedirs(os.path.join(self.root, "cbeta", "data"))
        os.makedirs(os.path.join(self.root, "cbeta", "fonts"))

    def tearDown(self):
        self._shutil.rmtree(self.root, ignore_errors=True)

    def _seed(self, key, raw):
        dest = os.path.join(
            self.root, "cbeta", "data" if key == "gaiji" else "fonts",
            "cbeta_gaiji.json" if key == "gaiji" else "CBETASupplement.ttf")
        with open(dest, "wb") as f:
            f.write(raw)
        return dest

    def _run(self, **kw):
        kw.setdefault("sources", _sources())
        # 默认探针失败 → 走旧全量下载路（离线；探针路径另测）
        kw.setdefault("probe", lambda u, e, l, d: ("failed", None, None))
        return update_all(root=self.root, **kw)

    def test_unchanged_skips_write(self):
        body = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        dest = self._seed("gaiji", body)
        mtime = os.path.getmtime(dest)
        rep = self._run(download=_dl({GAIJI_URL: body}))
        self.assertEqual(rep[0]["status"], "unchanged")
        self.assertEqual(os.path.getmtime(dest), mtime)

    def test_json_diff_overwrites(self):
        old = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        new = json.dumps({"CB1": {"uni_char": "x"},
                          "CB2": {"uni_char": "y"}}).encode("utf-8")
        self._seed("gaiji", old)
        rep = self._run(download=_dl({GAIJI_URL: new}))
        self.assertEqual(rep[0]["status"], "updated")
        self.assertIn("CB2", rep[0]["detail"])
        got = json.load(open(os.path.join(
            self.root, "cbeta", "data", "cbeta_gaiji.json"),
            encoding="utf-8"))
        self.assertIn("CB2", got)

    def test_bad_json_keeps_local(self):
        old = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        dest = self._seed("gaiji", old)
        rep = self._run(download=_dl({GAIJI_URL: b"{broken"}))
        self.assertEqual(rep[0]["status"], "failed")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), old)

    def test_download_failure(self):
        rep = self._run(download=lambda u, d: False)
        auto = [r for r in rep if r["key"] != "siddham-fonts"]
        self.assertTrue(auto)
        self.assertTrue(all(r["status"] == "failed" for r in auto))

    def test_ttf_rejects_small_file(self):
        dest = self._seed("supplement-ttf", b"\x00\x01\x00\x00" + b"z" * 10)
        rep = self._run(download=_dl({TTF_URL: b"not a font"}))
        row = next(r for r in rep if r["key"] == "supplement-ttf")
        self.assertEqual(row["status"], "failed")
        self.assertEqual(os.path.getsize(dest), 14)

    def test_dry_run_writes_nothing(self):
        old = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        new = json.dumps({"CB1": {"uni_char": "x"},
                          "CB2": {"uni_char": "y"}}).encode("utf-8")
        dest = self._seed("gaiji", old)
        rep = self._run(dry_run=True, download=_dl({GAIJI_URL: new}))
        self.assertEqual(rep[0]["status"], "preview")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), old)

    def test_manual_only_shows(self):
        rep = self._run(download=lambda u, d: False)
        row = next(r for r in rep if r["key"] == "siddham-fonts")
        self.assertEqual(row["status"], "manual")
        self.assertIn("http://example/dl", row["detail"])

    def test_format_report(self):
        lines = format_report([
            {"key": "gaiji", "status": "unchanged", "detail": "1 条"},
            {"key": "x", "status": "failed", "detail": "err"}])
        self.assertEqual(len(lines), 2)
        self.assertIn("gaiji", lines[0])

    def test_probe_not_modified_skips_download(self):
        import unittest.mock as mock
        body = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        dest = self._seed("gaiji", body)
        mtime = os.path.getmtime(dest)
        dl = mock.Mock(return_value=True)
        rep = update_all(
            root=self.root, download=dl,
            sources=_sources(),
            probe=lambda u, e, l, d: ("not-modified", "E1", "LM1"))
        self.assertEqual(rep[0]["status"], "unchanged")
        self.assertIn("免下载", rep[0]["detail"])
        dl.assert_not_called()
        self.assertEqual(os.path.getmtime(dest), mtime)

    def test_probe_downloaded_validates_and_writes_sidecar(self):
        import json as _json
        new = _json.dumps({"CB1": {"uni_char": "x"},
                           "CB2": {"uni_char": "y"}}).encode("utf-8")

        def fake_probe(url, etag, lm, dest):
            with open(dest, "wb") as f:
                f.write(new)
            return ("downloaded", "E9", "LM9")

        rep = update_all(root=self.root, sources=_sources(),
                         probe=fake_probe,
                         download=lambda u, d: self.fail("should not fallback"))
        self.assertEqual(rep[0]["status"], "updated")
        sidecar = _json.load(open(os.path.join(
            self.root, "cbeta", "data", ".last-update.json"),
            encoding="utf-8"))
        self.assertEqual(sidecar["gaiji"]["etag"], "E9")
        self.assertIn("at", sidecar["gaiji"])
        # dry-run 不写 sidecar
        import shutil
        root2 = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root2, "cbeta", "data"))
            update_all(root=root2, dry_run=True, sources=_sources(),
                       probe=fake_probe, download=lambda u, d: True)
            self.assertFalse(os.path.isfile(os.path.join(
                root2, "cbeta", "data", ".last-update.json")))
        finally:
            shutil.rmtree(root2, ignore_errors=True)

    def test_last_update_summary(self):
        import json as _json
        from pycbeta.update_data import last_update_summary
        self.assertEqual(last_update_summary(self.root), "")
        fn = os.path.join(self.root, "cbeta", "data", ".last-update.json")
        with open(fn, "w", encoding="utf-8") as f:
            _json.dump({"gaiji": {"at": "2026-09-09T10:00:00",
                                  "detail": "x"}}, f)
        s = last_update_summary(self.root)
        self.assertIn("2026-09-09", s)
        self.assertIn("gaiji", s)

    def test_summary_falls_back_to_git_dates(self):
        import unittest.mock as mock
        import tempfile
        import shutil
        from pycbeta.update_data import last_update_summary
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "cbeta", "data"))
            rows = [{"key": "gaiji", "kind": "json-dict", "url": "u",
                     "dest": ("cbeta", "data", "cbeta_gaiji.json")},
                    {"key": "siddham-fonts", "kind": "manual", "url": "u",
                     "dest": (), "note": ""}]
            with mock.patch("pycbeta.update_data._git_file_date",
                            return_value="2026-09-08") as m:
                s = last_update_summary(root, sources=rows)
                self.assertIn("2026-09-08", s)
                self.assertIn("gaiji", s)
                self.assertNotIn("siddham", s)
                called = [c.args[1] for c in m.call_args_list]
                self.assertTrue(any("cbeta_gaiji.json" in str(c)
                                    for c in called))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_git_file_date_no_git(self):
        import unittest.mock as mock
        from pycbeta.update_data import _git_file_date
        with mock.patch("subprocess.run",
                        side_effect=FileNotFoundError("no git")):
            self.assertEqual(_git_file_date("/nonexistent", "x"), "")


class TestLoadSources(unittest.TestCase):
    def setUp(self):
        import shutil
        self.root = tempfile.mkdtemp()
        self._shutil = shutil
        os.makedirs(os.path.join(self.root, "cbeta", "data"))

    def tearDown(self):
        self._shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, text):
        fn = os.path.join(self.root, "cbeta", "data", "remote_sources.json")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(text)
        return fn

    def test_missing_file_raises_loudly(self):
        with self.assertRaises(OSError):
            load_sources(self.root)

    def test_bad_json_raises(self):
        self._write("{broken")
        with self.assertRaises(ValueError):
            load_sources(self.root)

    def test_unknown_kind_raises(self):
        self._write('{"a": {"url": "u", "dest": "d", "kind": "zzz"}}')
        with self.assertRaises(ValueError):
            load_sources(self.root)

    def test_loads_and_manual(self):
        self._write('{'
                    '"g": {"url": "http://example/g.json",'
                    ' "dest": "cbeta/data/g.json", "kind": "json-dict"},'
                    '"m": {"url": "http://example/dl", "dest": "",'
                    ' "kind": "manual", "note": "手下"}}')
        rows = load_sources(self.root)
        by_key = {r["key"]: r for r in rows}
        self.assertEqual(by_key["g"]["dest"], ("cbeta", "data", "g.json"))
        self.assertEqual(by_key["m"]["dest"], ())
        self.assertEqual(by_key["m"]["note"], "手下")

    def test_real_file_loads(self):
        rows = load_sources()
        keys = [r["key"] for r in rows]
        self.assertIn("gaiji", keys)
        self.assertIn("siddham-fonts", keys)
        man = next(r for r in rows if r["key"] == "siddham-fonts")
        self.assertEqual(man["kind"], "manual")


if __name__ == "__main__":
    unittest.main()
