import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pycbeta.fetch as fetch_mod
from pycbeta.fetch import _fetch_one
from pycbeta.verify import _extract_txt_parts, find_official, _head_no_tokens, \
    _strip_official_no

NOTE_RE = re.compile(r"(?m)^ {4}\[[^\]\[]{1,12}\]")


class TestStripOfficialNo(unittest.TestCase):
    def test_token_from_work(self):
        from pycbeta.model import E, Text, Work
        w = Work(id="X", source_file="", metadata={}, body=[
            E(tag="head", attrs={}, children=[Text(text="No. 1116-B"),
                                              Text(text=" 序")])],
            notes_by_n={}, apps=[], simplified=False)
        self.assertEqual(_head_no_tokens(w), ["No. 1116-B"])

    def test_official_line_start_only(self):
        s = "No. 1116-B序\n正文提No. 1116-B\nNo. 1116-C序\n"
        out = _strip_official_no(s, ["No. 1116-B", "No. 1116-C"])
        self.assertTrue(out.startswith("序\n"))
        self.assertIn("正文提No. 1116-B", out)  # 非行首不动
        self.assertIn("\n序\n", out)  # 多令牌逐个剥
        self.assertEqual(_strip_official_no(s, []), s)

    def test_strip_no_from_dual_shape(self):
        import json
        import tempfile
        from pycbeta.verify import _strip_no_from
        d = tempfile.mkdtemp()
        pre = os.path.join(d, "presets.json")
        with open(pre, "w", encoding="utf-8") as f:
            json.dump({"output": {"strip_head_no": True}}, f)
        self.assertTrue(_strip_no_from(pre))  # presets 形态直读
        run = os.path.join(d, "run.json")
        with open(run, "w", encoding="utf-8") as f:
            json.dump({"config-json": pre, "html-epub-theme": "",
                       "html-epub-user-theme": "", "pdf-docx-theme": "",
                       "pdf-docx-user-theme": ""}, f)
        self.assertTrue(_strip_no_from(run))  # run 形态走组合单解算
        self.assertFalse(_strip_no_from(os.path.join(d, "nope.json")))


class TestExtractTxtParts(unittest.TestCase):
    SAMPLE = (
        "No. 999\n"
        "書名\n"
        "\n"
        "西晉[15]月氏國三藏譯\n"
        "\n"
        "    [15] 月氏國【大】，〔－〕【宋】\n"
        "\n"
        "[16]輩，五百比丘。\n"
        "\n"
        "    [16] 輩【大】，比丘【宋】\n"
    )

    def test_notes_moved_order_kept(self):
        body, notes = _extract_txt_parts(self.SAMPLE)
        # 注记块移出正文
        self.assertNotIn("[15] 月氏國", body)
        self.assertIn("[15] 月氏國", notes)
        self.assertIn("[16] 輩【大】", notes)
        # 行首 [n] 是正文（标题/署名/偈锚），必须保留在 body
        self.assertIn("[16]輩，五百比丘。", body)
        # 注记内部保序
        self.assertLess(notes.find("[15]"), notes.find("[16]"))
        # 标题与空行保留在 body
        self.assertIn("書名", body)
        self.assertIn("No. 999", body)

    def test_no_notes_passthrough(self):
        s = "正文第一行\n\n正文第二行\n"
        body, notes = _extract_txt_parts(s)
        self.assertEqual(notes.strip(), "")
        self.assertEqual(body, s)

    def test_real_file_anchor(self):
        p = os.path.join(r"E:\dev\cbeta\cbeta_ebook", "T0349 彌勒菩薩所問本願經",
                         "T0349.txt", "T0349_001.txt")
        with open(p, encoding="utf-8") as f:
            s = f.read()
        expect = NOTE_RE.findall(s)
        self.assertGreater(len(expect), 0)
        body, notes = _extract_txt_parts(s)
        # 注记行数一致，正文无残留；行是严格划分（调用方 join 时才多一个 \n）
        self.assertEqual(len(notes.splitlines()), len(expect))
        self.assertFalse(NOTE_RE.search(body))
        self.assertEqual(len(body.split("\n")) + len(notes.split("\n")),
                         len(s.split("\n")))


class TestTxtNotesDiscovery(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        flat = os.path.join(self.root, "T9999 Book")
        for sub, name in (("T9999.txt", "T9999_001.txt"),
                          ("T9999.txt_notes", "T9999_001.txt"),
                          ("T9999.txt_notes", "T9999_002.txt")):
            d = os.path.join(flat, sub)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write("x " + name)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_txt_and_notes_isolated(self):
        # txt 发现不受 .txt_notes 干扰，反之亦然
        hits = find_official(self.root, "T99n9999", "txt_notes")
        self.assertEqual(len(hits), 2)
        self.assertTrue(all("txt_notes" in f for f in hits))
        hits_txt = find_official(self.root, "T99n9999", "txt")
        self.assertTrue(len(hits_txt) >= 1)
        self.assertTrue(all("txt_notes" not in f for f in hits_txt))

    def test_scope_applies_to_notes(self):
        hits = find_official(self.root, "T99n9999", "txt_notes", juan={1})
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].endswith("T9999_001.txt"))


class TestTxtNotesLanding(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.flat = os.path.join(self.root, "T9999 Book")
        os.makedirs(self.flat)
        catalog = os.path.join(self.root, "catalog.txt")
        with open(catalog, "w", encoding="utf-8") as f:
            f.write("T,99,9999,1,1,x,Test\n")
        self.source_cfg = {"catalog": catalog}
        self.dl = {"txt_notes": "http://example/{id}.txt.zip"}
        fakezip = os.path.join(self.root, "f.zip")
        with zipfile.ZipFile(fakezip, "w") as z:
            z.writestr("T9999_001.txt", "body\n\n    [1] 注【大】\n")
        real_http = fetch_mod._http_download

        def fake_zip(url, dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(fakezip, dest)
            return True

        fetch_mod._http_download = fake_zip
        self.addCleanup(setattr, fetch_mod, "_http_download", real_http)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_notes_lands_separate_dir(self):
        res = _fetch_one("T9999", "txt_notes", "T", "9999", self.dl,
                         self.source_cfg, self.root)
        want = os.path.join(self.flat, "T9999.txt_notes", "T9999_001.txt")
        self.assertEqual(res, [want])
        self.assertTrue(os.path.isfile(want))
        # 不污染 txt 目录，不建仓库目录
        self.assertFalse(os.path.exists(os.path.join(self.flat, "T9999.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "T")))


if __name__ == "__main__":
    unittest.main()
