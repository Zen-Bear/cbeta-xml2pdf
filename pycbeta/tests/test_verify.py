import os
import re
import glob
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


class TestGenerateFormalConfig(unittest.TestCase):
    """generate_formal 的配置解析：base 配置 JSON（纯 presets）也要生效（不能回退出厂）。"""

    def test_base_config_preset_applied(self):
        import json
        import tempfile
        from unittest import mock
        from pycbeta.model import Work
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            pre = os.path.join(d, "presets.json")
            with open(pre, "w", encoding="utf-8") as f:
                json.dump({"output": {"inline_brackets": "halfwidth"}}, f)
            seen = {}
            with mock.patch.object(V, "HtmlRenderer") as M:
                M.return_value.render_work.return_value = ["x.html"]
                V.generate_formal("x.xml", Work(id="T", source_file="",
                                                metadata={}, body=[],
                                                notes_by_n={}, apps=[],
                                                simplified=False),
                                  "html", os.path.join(d, "out"),
                                  config_path=pre)
                seen = M.call_args.kwargs
            self.assertEqual(seen.get("inline_brackets"), "halfwidth")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestGenerateFormalBracketFallback(unittest.TestCase):
    """缺 verify.inline_brackets（如 publish 临时预设）→ 回退半角（官方口径）。"""

    def test_missing_key_falls_back_halfwidth(self):
        import json
        import tempfile
        from unittest import mock
        from pycbeta.model import Work
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            pre = os.path.join(d, "presets.json")
            with open(pre, "w", encoding="utf-8") as f:
                json.dump({"output": {"inline_brackets": "fullwidth"}}, f)
            seen = {}
            with mock.patch.object(V, "HtmlRenderer") as M:
                M.return_value.render_work.return_value = ["x.html"]
                V.generate_formal("x.xml", Work(id="T", source_file="",
                                                metadata={}, body=[],
                                                notes_by_n={}, apps=[],
                                                simplified=False),
                                  "html", os.path.join(d, "out"),
                                  config_path=pre)
                seen = M.call_args.kwargs
            self.assertEqual(seen.get("inline_brackets"), "halfwidth")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestStripOfficialNo(unittest.TestCase):
    def test_token_from_work(self):
        from pycbeta.model import E, Text, Work
        w = Work(id="X", source_file="", metadata={}, body=[
            E(tag="head", attrs={}, children=[Text(text="No. 1116-B"),
                                              Text(text=" 序")])],
            notes_by_n={}, apps=[], simplified=False)
        self.assertEqual(_head_no_tokens(w), ["No. 1116-B"])

    def test_docnumber_included(self):
        # 生成侧 strip_head_no 省略 docNumber 整元素 → 官方侧需按其全文对等剥离
        from pycbeta.model import E, Text, Work
        w = Work(id="T", source_file="",
                 metadata={"docNumber": "No. 349 [No. 310(42)]"},
                 body=[E(tag="docNumber",
                         children=[Text(text="No. 349 [No. 310(42)]")])],
                 notes_by_n={}, apps=[], simplified=False)
        self.assertEqual(_head_no_tokens(w), ["No. 349 [No. 310(42)]"])
        out = _strip_official_no("No. 349 [No. 310(42)]\n正文\n",
                                 _head_no_tokens(w))
        self.assertNotIn("No. 349", out)
        self.assertIn("正文", out)

    def test_official_line_start_only(self):
        s = "No. 1116-B序\n正文提No. 1116-B\nNo. 1116-C序\n"
        out = _strip_official_no(s, ["No. 1116-B", "No. 1116-C"])
        self.assertTrue(out.startswith("序\n"))
        self.assertIn("正文提No. 1116-B", out)  # 非行首不动
        self.assertIn("\n序\n", out)  # 多令牌逐个剥
        self.assertEqual(_strip_official_no(s, []), s)

    def test_official_leading_ws_kept(self):
        # 官方 html 提取行常带前导空格：保留空白、剥 token+其后空白（与生成侧同形）
        s = "  No. 1077-A 重刻准提淨業序\nNo. 1077准提淨業卷之一\n"
        out = _strip_official_no(s, ["No. 1077-A"])
        self.assertTrue(out.startswith("  重刻准提淨業序"))
        self.assertIn("No. 1077准提淨業卷之一", out)  # docNumber 不在令牌表，不动

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
        for sub, name in (("txt", "T9999_001.txt"),
                          ("txt", "T9999_002.txt"),
                          ("html", "T9999_001.html")):
            d = os.path.join(flat, sub)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write("x " + name)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_txt_notes_in_txt_dir(self):
        # text-with-notes 落 `txt/`，不混入 html 等其它格式目录
        hits = find_official(self.root, "T99n9999", "txt_notes")
        self.assertEqual(len(hits), 2)
        self.assertTrue(all(f"{os.sep}txt{os.sep}" in f for f in hits))

    def test_scope_applies_to_notes(self):
        hits = find_official(self.root, "T99n9999", "txt_notes", juan={1})
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].endswith("T9999_001.txt"))


class TestVerifyDirExcluded(unittest.TestCase):
    """`*（验证）*/` 不得当基线：正式比对档与基线同 stem，自比对会假绿。"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        flat = os.path.join(self.root, "T9999 Book")
        os.makedirs(os.path.join(flat, "html"), exist_ok=True)
        with open(os.path.join(flat, "html", "T9999_001.html"),
                  "w", encoding="utf-8") as f:
            f.write("official")
        vdir = os.path.join(flat, "T9999 Book（验证）", "html")
        os.makedirs(vdir, exist_ok=True)
        with open(os.path.join(vdir, "T99n9999.html"),
                  "w", encoding="utf-8") as f:
            f.write("formal")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_formal_excluded_when_official_present(self):
        hits = find_official(self.root, "T99n9999", "html")
        self.assertEqual(len(hits), 1)
        self.assertIn("official", open(hits[0], encoding="utf-8").read())

    def test_formal_only_yields_empty(self):
        # 无官方、仅正式档 → 空（不得自命中假绿）
        os.remove(os.path.join(self.root, "T9999 Book", "html",
                               "T9999_001.html"))
        self.assertEqual(find_official(self.root, "T99n9999", "html"), [])


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
        # zip 自带目录层次 → 应平展进 txt/
        fakezip = os.path.join(self.root, "f.zip")
        with zipfile.ZipFile(fakezip, "w") as z:
            z.writestr("text-with-notes/T9999.txt_notes/T9999_001.txt",
                       "body\n\n    [1] 注【大】\n")
        real_http = fetch_mod._http_download

        def fake_zip(url, dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(fakezip, dest)
            return True

        fetch_mod._http_download = fake_zip
        self.addCleanup(setattr, fetch_mod, "_http_download", real_http)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_notes_flat_into_txt_dir_no_zip(self):
        res = _fetch_one("T9999", "txt_notes", "T", "9999", self.dl,
                         self.source_cfg, self.root)
        want = os.path.join(self.flat, "txt", "T9999_001.txt")
        self.assertEqual(res, [want])
        self.assertTrue(os.path.isfile(want))
        # 不带 zip 的目录层次、work 目录不留 zip、不建仓库目录
        self.assertFalse(os.path.exists(
            os.path.join(self.flat, "text-with-notes")))
        self.assertFalse(glob.glob(os.path.join(self.flat, "**", "*.zip"),
                                   recursive=True))
        self.assertFalse(os.path.exists(os.path.join(self.root, "T")))


class TestPdfNoBaseline(unittest.TestCase):
    def test_pdf_skipped(self):
        from pycbeta.verify import verify_one
        r = verify_one("nonexistent.xml", "pdf", "", tempfile.mkdtemp())
        self.assertEqual(r["status"], "no_baseline")
        self.assertIn("PDF", r["detail"])


class TestNormalizeWithLines(unittest.TestCase):
    def test_line_map_aligns(self):
        from pycbeta.verify import normalize_with_lines, normalize
        raw = "第一行\n\n第二行 [01-02]\n第三行"
        norm, line_of, raw_lines = normalize_with_lines(raw)
        self.assertEqual(norm, normalize(raw))
        self.assertEqual(len(norm), len(line_of))
        self.assertEqual(raw_lines[line_of[norm.index("二")]], "第二行 [01-02]")

    def test_cross_line_bracket_fallback(self):
        from pycbeta.verify import normalize_with_lines
        norm, line_of, _ = normalize_with_lines("a〔b\nc〕d")
        self.assertEqual(norm, "ad")
        self.assertEqual(line_of, [])


class TestReportCtxLocation(unittest.TestCase):
    def test_report_marks_span_and_line(self):
        from pycbeta.verify import format_verify_report
        recs = [{
            "xml": "T01n0001.xml", "fmt": "docx", "status": "fail",
            "gen": "T01n0001.docx", "official_kind": "docx",
            "official": "official.docx", "matched": 100,
            "missing": 0, "extra": 1, "total": 1,
            "ctx": [("insert", 1, 2, 1, 1)],
            "ctx_loc": [{"gen_line": 12, "src_line": 12}],
            "src_cmp": "T01n0001_compare_docx_official.txt",
            "gen_cmp": "T01n0001_compare_docx_generated.txt",
            "norm_gen": "甲X乙", "norm_official": "甲乙",
        }]
        s = "\n".join(format_verify_report(recs))
        self.assertIn("【源比较】行号对齐 T01n0001_compare_docx_official.txt", s)
        self.assertIn("【新比较】行号对齐 T01n0001_compare_docx_generated.txt", s)
        self.assertIn("1.（源比较第12行，新比较第12行）", s)
        self.assertIn("【源】甲〖〗乙", s)
        self.assertIn("【新】甲〖X〗乙", s)
        self.assertNotIn("标出差异位置", s)

    def test_report_without_loc_falls_back(self):
        from pycbeta.verify import format_verify_report
        recs = [{
            "xml": "T01n0001.xml", "fmt": "docx", "status": "fail",
            "gen": "T01n0001.docx", "official_kind": "docx",
            "official": "official.docx", "matched": 100,
            "missing": 0, "extra": 1, "total": 1,
            "ctx": [("insert", 1, 2, 1, 1)],
            "norm_gen": "甲X乙", "norm_official": "甲乙",
        }]
        s = "\n".join(format_verify_report(recs))
        self.assertIn("1.\n", s)
        self.assertIn("【源】甲〖〗乙", s)
        self.assertNotIn("标出差异位置", s)

    def test_mark_span(self):
        from pycbeta.verify import _mark_span
        self.assertEqual(_mark_span("甲乙", 1, 1), "甲〖〗乙")
        self.assertEqual(_mark_span("甲X乙", 1, 2), "甲〖X〗乙")
        self.assertEqual(_mark_span("", 0, 0), "〖〗")


class TestVerifyAlwaysComparesNotes(unittest.TestCase):
    """校验恒比注：generate_formal 强制 show_notes=True（忽略 output.show_notes=false）。"""

    def _capture(self, fmt, renderer_name):
        from unittest import mock
        import pycbeta.verify as V
        from pycbeta.model import Work
        captured = {}

        class Fake:
            def __init__(self, **kw):
                captured.update(kw)

            def render_work(self, work, out_dir, filename=""):
                return os.path.join(out_dir, filename or "out")

        w = Work(id="T", source_file="", metadata={}, body=[],
                 notes_by_n={}, apps=[])
        out = tempfile.mkdtemp()
        with mock.patch.object(V, renderer_name, Fake):
            V.generate_formal("T1.xml", w, fmt, out, overrides={"show_notes": False})
        return captured

    def test_docx_notes_forced(self):
        self.assertTrue(self._capture("docx", "DocxRenderer")["show_notes"])

    def test_txt_notes_forced(self):
        self.assertTrue(self._capture("txt", "TxtRenderer")["show_notes"])


class TestVerifyOnlyGenPaths(unittest.TestCase):
    """verify_one(gen_paths=...)：只校验已有产物，跳过 generate_formal。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={}, body=[],
                    notes_by_n={}, apps=[], simplified=False)

    def test_missing_gen_returns_error_without_regenerating(self):
        from unittest import mock
        import pycbeta.verify as V
        with mock.patch.object(V, "P5Parser") as P, \
                mock.patch.object(V, "generate_formal") as G:
            P.return_value.parse.return_value = self._work()
            rec = V.verify_one("x.xml", "txt", "srcdir", "outroot",
                               gen_paths=[])
        self.assertEqual(rec["status"], "error")
        self.assertIn("生成档缺失", rec["detail"])
        G.assert_not_called()
        s = "\n".join(V.format_verify_report([rec]))
        self.assertIn("[FAIL] txt 校验异常", s)

    def test_given_gen_skips_regeneration(self):
        from unittest import mock
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            gen = os.path.join(d, "T.txt")
            with open(gen, "w", encoding="utf-8") as f:
                f.write("正文甲")
            with mock.patch.object(V, "P5Parser") as P, \
                    mock.patch.object(V, "generate_formal") as G, \
                    mock.patch.object(V, "_extract_xml_parts",
                                      return_value=("T", "", "正文甲", [])):
                P.return_value.parse.return_value = self._work()
                rec = V.verify_one("x.xml", "txt", d, os.path.join(d, "v"),
                                   baseline="xml", gen_paths=[gen])
            G.assert_not_called()
            self.assertEqual(rec["gen"], [gen])
            self.assertIn(rec["status"], ("ok", "fail"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
