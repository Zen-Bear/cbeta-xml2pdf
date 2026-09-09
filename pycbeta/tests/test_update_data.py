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
