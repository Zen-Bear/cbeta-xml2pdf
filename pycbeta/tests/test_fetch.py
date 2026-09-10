import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.fetch import (resolve_source, fetch_work, catalog_lookup,
                           work_dir, materialize_work, title_t2s)


def _presets(xml_dir="", cbeta_ebook="", **extra):
    src = {"xml_dir": xml_dir, "cbeta_ebook": cbeta_ebook}
    src.update(extra)
    return {"source": src}


class TestResolveSource(unittest.TestCase):
    def test_ebook_required_with_guidance(self):
        for presets in (None, {}, {"source": {}},
                        {"source": {"xml_dir": "", "cbeta_ebook": ""}}):
            with self.assertRaises(ValueError) as ctx:
                resolve_source(presets)
            self.assertIn("config.user.json", str(ctx.exception))
            self.assertIn("cbeta_ebook", str(ctx.exception))

    def test_xml_dir_optional(self):
        self.assertEqual(resolve_source(_presets(cbeta_ebook="X:\\ebook")),
                         ("", "X:\\ebook"))

    def test_same_dir_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_source(_presets(xml_dir="X:\\same", cbeta_ebook="X:\\same"))
        self.assertIn("不能相同", str(ctx.exception))

    def test_explicit_args_win(self):
        xml, eb = resolve_source(
            _presets(xml_dir="X:\\a", cbeta_ebook="X:\\b"), xml_dir="Y:\\a")
        self.assertEqual((xml, eb), ("Y:\\a", "X:\\b"))


class TestCatalog(unittest.TestCase):
    def test_title_returned(self):
        import io
        d = tempfile.mkdtemp()
        cat = os.path.join(d, "mapping.txt")
        with io.open(cat, "w", encoding="utf-8") as f:
            f.write("T,12,0349,1,1,0186c03,彌勒菩薩所問本願經,譯者\n"
                    "TX,07,0006,6,1,b001a01,太虛大師全書．第六編,釋太虛\n")
        got = catalog_lookup(cat, "T", "0349")
        self.assertEqual(got[0]["title"], "彌勒菩薩所問本願經")
        self.assertEqual(got[0]["file"], "T12n0349.xml")


class TestWorkDir(unittest.TestCase):
    def test_create_with_t2s_title(self):
        d = tempfile.mkdtemp()
        with mock.patch("pycbeta.simplify.simplify_text",
                        side_effect=lambda s: s.replace("彌", "弥")):
            p = work_dir(d, "T0349", "彌勒菩薩經", _presets(), create=True)
        self.assertTrue(os.path.isdir(p))
        self.assertEqual(os.path.basename(p), "T0349 弥勒菩薩經")

    def test_reuse_existing(self):
        d = tempfile.mkdtemp()
        old = os.path.join(d, "T0349 旧书名")
        os.makedirs(old)
        self.assertEqual(work_dir(d, "T0349", "新书名", _presets()), old)

    def test_not_confuse_longer_id(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "T0349a 他经"))
        self.assertIsNone(work_dir(d, "T0349", "本经", _presets()))

    def test_title_t2s_flag(self):
        d = tempfile.mkdtemp()
        with mock.patch("pycbeta.simplify.simplify_text",
                        side_effect=lambda s: s.replace("彌", "弥")):
            p = work_dir(d, "T0349", "彌勒經",
                         _presets(title_t2s=False), create=True)
        self.assertEqual(os.path.basename(p), "T0349 彌勒經")
        self.assertTrue(title_t2s(_presets(title_t2s=True)))
        self.assertFalse(title_t2s(_presets(title_t2s=False)))


class TestMaterialize(unittest.TestCase):
    def _src_frag(self, root, canon, vol, stem, seq, text):
        vd = os.path.join(root, canon, vol)
        os.makedirs(vd, exist_ok=True)
        p = os.path.join(vd, f"{stem}_{seq}.xml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f'<?xml version="1.0" encoding="utf-8"?>'
                    f'<TEI xmlns="http://www.tei-c.org/ns/1.0">'
                    f'<teiHeader><fileDesc><titleStmt>'
                    f'<title level="m" xml:lang="zh-Hant">題</title>'
                    f'</titleStmt></fileDesc></teiHeader>'
                    f'<text><body><p>{text}</p></body></text></TEI>')
        return p

    def test_xml_dir_copy(self):
        x = tempfile.mkdtemp()
        e = tempfile.mkdtemp()
        whole = os.path.join(x, "T0349 書", "T12n0349.xml")
        os.makedirs(os.path.dirname(whole))
        with open(whole, "w", encoding="utf-8") as f:
            f.write("<TEI/>")
        with mock.patch("pycbeta.fetch._http_download", return_value=False):
            paths, label = materialize_work(
                "T0349", _presets(xml_dir=x, cbeta_ebook=e))
        self.assertEqual(label, "xml_copy")
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].startswith(e))
        # 第二次：已材料化，直接命中
        paths2, label2 = materialize_work(
            "T0349", _presets(xml_dir=x, cbeta_ebook=e))
        self.assertEqual(label2, "xml_copy")  # 有源仍走源（mtime 不新则不拷）
        self.assertEqual(paths, paths2)

    def test_xml_dir_frag_merge(self):
        x = tempfile.mkdtemp()
        e = tempfile.mkdtemp()
        self._src_frag(x, "TX", "TX07", "TX07n0006", "001", "甲")
        self._src_frag(x, "TX", "TX07", "TX07n0006", "002", "乙")
        self._src_frag(x, "TX", "TX08", "TX08n0006", "003", "丙")
        paths, label = materialize_work(
            "TX0006", _presets(xml_dir=x, cbeta_ebook=e))
        self.assertEqual(label, "xml_merge")
        self.assertEqual(len(paths), 2)  # 两册两文件
        names = sorted(os.path.basename(p) for p in paths)
        self.assertEqual(names, ["TX07n0006.xml", "TX08n0006.xml"])

    def test_refresh_newer_source(self):
        x = tempfile.mkdtemp()
        e = tempfile.mkdtemp()
        whole = os.path.join(x, "T0349 書", "T12n0349.xml")
        os.makedirs(os.path.dirname(whole))
        with open(whole, "w", encoding="utf-8") as f:
            f.write("v1")
        paths, _ = materialize_work("T0349", _presets(xml_dir=x, cbeta_ebook=e))
        with open(paths[0], encoding="utf-8") as f:
            self.assertEqual(f.read(), "v1")
        # 源更新且 mtime 变新 → 重拷
        import time
        time.sleep(0.01)
        with open(whole, "w", encoding="utf-8") as f:
            f.write("v2")
        os.utime(whole, None)
        paths2, _ = materialize_work("T0349", _presets(xml_dir=x, cbeta_ebook=e))
        with open(paths2[0], encoding="utf-8") as f:
            self.assertEqual(f.read(), "v2")

    def test_download_source(self):
        e = tempfile.mkdtemp()

        def fake_fetch(wid, fmts, presets, cbeta_ebook):
            d = os.path.join(cbeta_ebook, "T0349 書")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "T12n0349.xml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("<TEI/>")
            return {"xml": [p]}

        with mock.patch("pycbeta.fetch.fetch_work", side_effect=fake_fetch):
            paths, label = materialize_work(
                "T0349", _presets(cbeta_ebook=e))
        self.assertEqual(label, "downloaded")
        self.assertEqual(len(paths), 1)

    def test_no_source(self):
        e = tempfile.mkdtemp()
        with mock.patch("pycbeta.fetch._http_download", return_value=False):
            paths, label = materialize_work(
                "T0349", _presets(cbeta_ebook=e))
        self.assertEqual((paths, label), ([], ""))


class TestFetchWork(unittest.TestCase):
    def test_ebook_required(self):
        with self.assertRaises(ValueError):
            fetch_work("T0349", ["xml"], _presets(xml_dir="X:\\a"))

    def test_fetch_only_needs_ebook(self):
        with mock.patch("pycbeta.fetch.catalog_lookup", return_value=[]):
            res = fetch_work("T0349", ["xml"], _presets(cbeta_ebook="X:\\b"))
        self.assertEqual(res, {"xml": []})


if __name__ == "__main__":
    unittest.main()
