import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pycbeta.fetch as fetch_mod
from pycbeta.fetch import _fetch_one, _find_work_dir, find_local_xml, work_dir
from pycbeta.verify import find_official


def _touch(path, content="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestTwoTierLayout(unittest.TestCase):
    """统一根目录两档查找：平展优先、仓库次之。"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        # 平展：根下 work id 开头的条目
        _touch(os.path.join(self.root, "T9999 Book", "T99n9999.xml"))
        _touch(os.path.join(self.root, "T9999 Book", "T9999_001.html"))
        # 仓库：github 镜像布局
        _touch(os.path.join(self.root, "T", "T99", "T99n9999.xml"))
        _touch(os.path.join(self.root, "T", "T9999", "html", "T9999_001.html"))
        # out/ 必须排除
        _touch(os.path.join(self.root, "out", "verify", "T9999_001.html"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_xml_flat_first(self):
        hits = find_local_xml(self.root, "T", "9999")
        self.assertEqual(len(hits), 2)
        self.assertTrue(hits[0].replace(os.sep, "/").endswith("T9999 Book/T99n9999.xml"))
        self.assertIn("T/T99/T99n9999.xml", hits[1].replace(os.sep, "/"))

    def test_xml_repo_fallback(self):
        shutil.rmtree(os.path.join(self.root, "T9999 Book"))
        hits = find_local_xml(self.root, "T", "9999")
        self.assertEqual(len(hits), 1)
        self.assertIn("T/T99/T99n9999.xml", hits[0].replace(os.sep, "/"))

    def test_official_flat_first(self):
        hits = find_official(self.root, "T99n9999", "html")
        self.assertEqual(len(hits), 2)
        self.assertTrue(hits[0].replace(os.sep, "/").endswith("T9999 Book/T9999_001.html"))

    def test_out_excluded(self):
        hits = find_official(self.root, "T99n9999", "html")
        self.assertFalse(any(f"{os.sep}out{os.sep}" in f for f in hits))
        xmls = find_local_xml(self.root, "T", "9999")
        self.assertFalse(any(f"{os.sep}out{os.sep}" in f for f in xmls))


class TestFlatLanding(unittest.TestCase):
    """下载一律落平展 work 目录：已有复用；无则建 `{id} {书名}`；文件齐不重复下载。"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.flat = os.path.join(self.root, "T9999 Book")
        os.makedirs(self.flat)
        catalog = os.path.join(self.root, "catalog.txt")
        with open(catalog, "w", encoding="utf-8") as f:
            f.write("T,99,9999,1,1,x,Test Book\n")
        self.source_cfg = {"catalog": catalog}
        self.dl = {"xml": "http://example/{canon}/{canon}{vol}/{file}",
                   "html": "http://example/{id}.html.zip"}
        self.downloaded = []
        real_http = fetch_mod._http_download

        def fake_http(url, dest):
            self.downloaded.append(url)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write("x")
            return True

        fetch_mod._http_download = fake_http
        self.addCleanup(setattr, fetch_mod, "_http_download", real_http)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_work_dir_hit_and_miss(self):
        self.assertEqual(_find_work_dir(self.root, "T9999"), self.flat)
        self.assertIsNone(_find_work_dir(self.root, "T0000"))
        # 更长編號目录不误命中（T9999a）
        os.makedirs(os.path.join(self.root, "T9999a 他经"))
        self.assertEqual(_find_work_dir(self.root, "T9999"), self.flat)

    def test_xml_lands_flat(self):
        res = _fetch_one("T9999", "xml", "T", "9999", self.dl,
                         self.source_cfg, self.root)
        want = os.path.join(self.flat, "T99n9999.xml")
        self.assertEqual(res, [want])
        self.assertTrue(os.path.isfile(want))
        self.assertEqual(self.downloaded, ["http://example/T/T99/T99n9999.xml"])

    def test_xml_creates_work_dir_with_title(self):
        shutil.rmtree(self.flat)
        res = _fetch_one("T9999", "xml", "T", "9999", self.dl,
                         self.source_cfg, self.root)
        self.assertEqual(os.path.basename(os.path.dirname(res[0])),
                         "T9999 Test Book")

    def test_baseline_lands_flat_ignoring_out_decoy(self):
        # work 目录 out/ 下的同名诱饵不计入已落盘
        decoy = os.path.join(self.flat, "out", "verify", "T9999_001.html")
        os.makedirs(os.path.dirname(decoy))
        with open(decoy, "w", encoding="utf-8") as f:
            f.write("x")
        fakezip = os.path.join(self.root, "f.zip")
        with zipfile.ZipFile(fakezip, "w") as z:
            z.writestr("T9999_001.html", "<html></html>")

        real_http = fetch_mod._http_download

        def fake_zip(url, dest):
            self.downloaded.append(url)
            shutil.copy(fakezip, dest)
            return True

        fetch_mod._http_download = fake_zip
        try:
            res = _fetch_one("T9999", "html", "T", "9999", self.dl,
                             self.source_cfg, self.root)
        finally:
            fetch_mod._http_download = real_http
        self.assertEqual(res, [os.path.join(self.flat, "T9999_001.html")])

    def test_nested_txt_notes_found_without_redownload(self):
        # 手工整理的嵌套形态（{work}/text-with-notes/{id}.txt_notes/）
        # 必须被认作已落盘，不重复下载、不搬动
        nested = os.path.join(self.flat, "text-with-notes", "T9999.txt_notes")
        os.makedirs(nested)
        want = os.path.join(nested, "T9999_001.txt")
        with open(want, "w", encoding="utf-8") as f:
            f.write("x")
        dl = dict(self.dl)
        dl["txt_notes"] = "http://example/{id}.txt.zip"
        res = _fetch_one("T9999", "txt_notes", "T", "9999", dl,
                         self.source_cfg, self.root)
        self.assertEqual(res, [want])
        self.assertEqual(self.downloaded, [])

    def test_work_dir_reuses_existing_dir(self):
        # 已有旧名目录（不带动词书名）时复用，不再建新目录
        d = tempfile.mkdtemp()
        old = os.path.join(d, "T9999 旧书名")
        os.makedirs(old)
        self.assertEqual(work_dir(d, "T9999", "新书名"), old)


if __name__ == "__main__":
    unittest.main()
