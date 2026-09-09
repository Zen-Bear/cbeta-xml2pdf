import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.update_data import update_all, format_report, SOURCES


def _dl(mapping):
    def fake(url, dest):
        if url not in mapping:
            return False
        with open(dest, "wb") as f:
            f.write(mapping[url])
        return True
    return fake


def _urls():
    return {s["url"]: None for s in SOURCES}


class TestUpdateData(unittest.TestCase):
    def setUp(self):
        import shutil
        self.root = tempfile.mkdtemp()
        self._shutil = shutil
        os.makedirs(os.path.join(self.root, "cbeta", "data"))
        os.makedirs(os.path.join(self.root, "cbeta", "fonts"))

    def tearDown(self):
        self._shutil.rmtree(self.root, ignore_errors=True)

    def _seed(self, name, raw):
        from pycbeta.update_data import SOURCES as _S
        dest = os.path.join(self.root, *next(
            s["dest"] for s in _S if s["key"] == name))
        with open(dest, "wb") as f:
            f.write(raw)
        return dest

    def test_unchanged_skips_write(self):
        body = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        dest = self._seed("gaiji", body)
        mtime = os.path.getmtime(dest)
        rep = update_all(root=self.root,
                         download=_dl({SOURCES[0]["url"]: body}))
        self.assertEqual(rep[0]["status"], "unchanged")
        self.assertEqual(os.path.getmtime(dest), mtime)

    def test_json_diff_overwrites(self):
        old = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        new = json.dumps({"CB1": {"uni_char": "x"},
                          "CB2": {"uni_char": "y"}}).encode("utf-8")
        self._seed("gaiji", old)
        rep = update_all(root=self.root,
                         download=_dl({SOURCES[0]["url"]: new}))
        self.assertEqual(rep[0]["status"], "updated")
        self.assertIn("CB2", rep[0]["detail"])
        got = json.load(open(os.path.join(
            self.root, "cbeta", "data", "cbeta_gaiji.json"),
            encoding="utf-8"))
        self.assertIn("CB2", got)

    def test_bad_json_keeps_local(self):
        old = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        dest = self._seed("gaiji", old)
        rep = update_all(root=self.root,
                         download=_dl({SOURCES[0]["url"]: b"{broken"}))
        self.assertEqual(rep[0]["status"], "failed")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), old)

    def test_download_failure(self):
        rep = update_all(root=self.root, download=lambda u, d: False)
        self.assertTrue(rep)
        self.assertTrue(all(r["status"] == "failed" for r in rep))

    def test_ttf_rejects_small_file(self):
        dest = self._seed("supplement-ttf", b"\x00\x01\x00\x00" + b"z" * 10)
        rep = update_all(
            root=self.root,
            download=_dl({[s for s in SOURCES
                            if s["key"] == "supplement-ttf"][0]["url"]:
                          b"not a font"}))
        row = next(r for r in rep if r["key"] == "supplement-ttf")
        self.assertEqual(row["status"], "failed")
        self.assertEqual(os.path.getsize(dest), 14)

    def test_dry_run_writes_nothing(self):
        old = json.dumps({"CB1": {"uni_char": "x"}}).encode("utf-8")
        new = json.dumps({"CB1": {"uni_char": "x"},
                          "CB2": {"uni_char": "y"}}).encode("utf-8")
        dest = self._seed("gaiji", old)
        rep = update_all(root=self.root, dry_run=True,
                         download=_dl({SOURCES[0]["url"]: new}))
        self.assertEqual(rep[0]["status"], "preview")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), old)

    def test_format_report(self):
        lines = format_report([
            {"key": "gaiji", "status": "unchanged", "detail": "1 条"},
            {"key": "x", "status": "failed", "detail": "err"}])
        self.assertEqual(len(lines), 2)
        self.assertIn("gaiji", lines[0])


if __name__ == "__main__":
    unittest.main()
