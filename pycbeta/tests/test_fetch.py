import os
import sys
import io
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.fetch import (resolve_source, fetch_work, catalog_lookup,
                           work_dir, materialize_work, title_t2s,
                           check_ebook_updates, canonical_work_id,
                           parse_work_id, DEFAULT_DOWNLOADS, find_local_xml)


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


class TestDetectBaselineDirs(unittest.TestCase):
    """官方电子书根目录自动检测（数据源面板一键填充用）。"""

    def _root(self):
        import tempfile
        d = tempfile.mkdtemp()
        for name in ("cbeta-text-with-notes", "cbeta_docx_2026r2",
                     "cbeta_epub_2026r2", "other"):
            os.makedirs(os.path.join(d, name))
        return d

    def test_detect_three_kinds(self):
        import shutil
        from pycbeta.fetch import detect_baseline_dirs
        d = self._root()
        try:
            got = detect_baseline_dirs(d)
            self.assertEqual(
                {k: os.path.basename(v) for k, v in got.items()
                 if k in ("txt_notes", "docx", "epub")},
                {"txt_notes": "cbeta-text-with-notes",
                 "docx": "cbeta_docx_2026r2",
                 "epub": "cbeta_epub_2026r2"})
            self.assertTrue(all(os.path.isabs(v) for v in got.values()))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_txt_notes_beats_plain_txt(self):
        import shutil
        from pycbeta.fetch import detect_baseline_dirs
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "txt"))
            os.makedirs(os.path.join(d, "cbeta-text-with-notes"))
            got = detect_baseline_dirs(d)
            self.assertEqual(os.path.basename(got["txt_notes"]),
                             "cbeta-text-with-notes")
            self.assertEqual(os.path.basename(got["txt"]), "txt")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_bad_root_empty(self):
        from pycbeta.fetch import detect_baseline_dirs
        self.assertEqual(detect_baseline_dirs(""), {})
        self.assertEqual(detect_baseline_dirs(os.path.join(
            tempfile.mkdtemp(), "nope")), {})
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "f.txt"), "w") as f:
                f.write("x")
            self.assertEqual(detect_baseline_dirs(d), {})
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


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


class TestLetterSuffixId(unittest.TestCase):
    """字母后缀 work id（TXa001/T0128a/JB005）：catalog 大小写不敏感 + 保留原始大小写，
    规范化 work id 供 URL/目录（CBETA XML 名与电子书端点大小写敏感）。"""

    def _cat(self):
        d = tempfile.mkdtemp()
        cat = os.path.join(d, "mapping.txt")
        with io.open(cat, "w", encoding="utf-8") as f:
            f.write("TX,00,a001,2,1,a001a01,太虛大師全書．編纂說明,釋太虛\n"
                    "T,02,0128a,1,1,0835c13,須摩提女經,支謙\n"
                    "J,15,B005,3,1,0001a01,某經,某\n")
        return cat

    def test_lookup_case_insensitive_keeps_case(self):
        cat = self._cat()
        r = catalog_lookup(cat, "TX", "A001")[0]
        self.assertEqual((r["vol"], r["no"], r["file"]),
                         ("00", "a001", "TX00na001.xml"))
        self.assertEqual(catalog_lookup(cat, "T", "0128A")[0]["file"],
                         "T02n0128a.xml")
        self.assertEqual(catalog_lookup(cat, "J", "b005")[0]["file"],
                         "J15nB005.xml")

    def test_canonical_work_id(self):
        presets = {"source": {"catalog": self._cat()}}
        self.assertEqual(canonical_work_id("txa001", presets), "TXa001")
        self.assertEqual(canonical_work_id("T0128A", presets), "T0128a")
        self.assertEqual(canonical_work_id("JB005", presets), "JB005")
        self.assertEqual(canonical_work_id("ZZ9999", presets), "ZZ9999")

    def test_urls_from_canonical(self):
        presets = {"source": {"catalog": self._cat()}}
        wid = canonical_work_id("TXA001", presets)
        canon, no = parse_work_id(wid)
        rec = catalog_lookup(presets["source"]["catalog"], canon, no)[0]
        self.assertTrue(DEFAULT_DOWNLOADS["xml"].format(
            canon=canon, vol=rec["vol"], file=rec["file"])
            .endswith("/TX/TX00/TX00na001.xml"))
        self.assertTrue(DEFAULT_DOWNLOADS["html"].format(id=wid)
                        .endswith("/html/TXa001.html.zip"))
        self.assertTrue(DEFAULT_DOWNLOADS["epub"].format(canon=canon, id=wid)
                        .endswith("/epub/TX/TXa001.epub"))


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

    def test_root_is_workdir_no_nesting(self):
        # root 本身已是该 work 目录时直接返回，避免基线落到 {work}/{id}/... 嵌套
        d = tempfile.mkdtemp()
        wd = os.path.join(d, "T0349 測試經")
        os.makedirs(wd)
        self.assertEqual(work_dir(wd, "T0349", "測試經", _presets()), wd)
        self.assertFalse(os.path.isdir(os.path.join(wd, "T0349")))

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

    def test_out_root_not_excluded(self):
        # 无目录名排除：工作根自己叫 out（如 cbeta_ebook/out）或子目录叫 out，
        # 其下文件全部正常参与查找
        import shutil
        d = tempfile.mkdtemp()
        try:
            root = os.path.join(d, "out")
            wd = os.path.join(root, "T0349 某經")
            os.makedirs(wd)
            fn = os.path.join(wd, "T12n0349.xml")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("<x/>")
            hits = find_local_xml(root, "T", "0349")
            self.assertEqual(hits, [os.path.abspath(fn)])
            # 子目录 out/ 同样不排除
            other = os.path.join(d, "work")
            os.makedirs(os.path.join(other, "out"))
            fn2 = os.path.join(other, "out", "T12n0349.xml")
            with open(fn2, "w", encoding="utf-8") as f:
                f.write("<x/>")
            self.assertEqual(find_local_xml(other, "T", "0349"),
                             [os.path.abspath(fn2)])
        finally:
            shutil.rmtree(d, ignore_errors=True)


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


class TestCheckUpdates(unittest.TestCase):
    def test_work_id_from_dirname(self):
        from pycbeta.fetch import _work_id_from_dirname
        self.assertEqual(_work_id_from_dirname("T0349 彌勒菩薩"), "T0349")
        self.assertEqual(_work_id_from_dirname("T0001 长阿含经"), "T0001")
        self.assertEqual(_work_id_from_dirname("TX0006 太虛"), "TX0006")
        self.assertEqual(_work_id_from_dirname("out"), "")
        self.assertEqual(_work_id_from_dirname("T"), "")

    def test_format_report(self):
        from pycbeta.fetch import format_update_report
        rep = [{"id": "T1", "status": "updated", "detail": "a"},
               {"id": "T2", "status": "unchanged", "detail": ""},
               {"id": "T3", "status": "failed", "detail": "HTTP 500"}]
        lines = "\n".join(format_update_report(rep))
        self.assertIn("已更新 1", lines)
        self.assertIn("T1", lines)
        self.assertIn("失败 T3", lines)

    def _mk(self, root, wid, title, file):
        d = os.path.join(root, f"{wid} {title}")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, file)
        with open(p, "w", encoding="utf-8") as f:
            f.write("old")
        return d, p

    def test_check_updates(self):
        root = tempfile.mkdtemp()
        self._mk(root, "T0349", "书", "T12n0349.xml")
        self._mk(root, "T0625", "书2", "T15n0625.xml")
        self._mk(root, "T0670", "书3", "T16n0670.xml")
        # catalog 已钉死内置（真实收录 T0349/T0625/T0670），不再经 presets 注入
        presets = {"source": {"cbeta_ebook": root},
                   "downloads": {"xml": "http://x/{file}"}}

        def probe(url, dest):
            if "0349" in dest:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write("new")
                return "changed", "3→3B"
            if "0625" in dest:
                return "unchanged", ""
            return "failed", "HTTP 500"

        rep = {r["id"]: r for r in
               check_ebook_updates(root, presets, probe=probe,
                                   with_baselines=False)}
        self.assertEqual(rep["T0349"]["status"], "updated")
        self.assertEqual(rep["T0625"]["status"], "unchanged")
        self.assertEqual(rep["T0670"]["status"], "failed")

    def test_check_refreshes_present_baselines(self):
        root = tempfile.mkdtemp()
        d, _ = self._mk(root, "T0349", "书", "T12n0349.xml")
        os.makedirs(os.path.join(d, "html"))
        with open(os.path.join(d, "html", "T0349_001.html"), "w",
                   encoding="utf-8") as f:
            f.write("old-html")
        # catalog 已钉死内置（真实收录 T0349），不再经 presets 注入
        presets = {"source": {"cbeta_ebook": root},
                   "downloads": {"xml": "http://x/{file}"}}
        seen = []

        def probe(url, dest):
            return "changed", "1→2"

        def fake_base(work_id, fmt, dl, canon, wdir, force=False):
            seen.append((fmt, force))
            return ["x"] if force else []

        with mock.patch("pycbeta.fetch._fetch_baseline_flat",
                        side_effect=fake_base):
            rep = check_ebook_updates(root, presets, probe=probe)
        self.assertEqual(rep[0]["status"], "updated")
        self.assertIn(("html", True), seen)   # 已有格式强制刷新
        self.assertIn(("txt_notes", False), seen)  # 文本族缺失则补下
        self.assertIn("基线已刷新:html", rep[0]["detail"])

    def test_present_baseline_formats(self):
        from pycbeta.fetch import _present_baseline_formats
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "html"))
        os.makedirs(os.path.join(d, "epub"))
        os.makedirs(os.path.join(d, "txt"))
        for p in (os.path.join(d, "html", "T0349_001.html"),
                  os.path.join(d, "epub", "T0349.epub"),
                  os.path.join(d, "txt", "T0349_001.txt")):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        self.assertEqual(sorted(_present_baseline_formats(d, "T0349")),
                         ["epub", "html", "txt_notes"])

    def test_check_skips_unresolvable_id(self):
        # catalog 钉死内置：T9999 无记录 → skipped（空/缺键同理回内置）
        root = tempfile.mkdtemp()
        self._mk(root, "T9999", "书", "T99n9999.xml")
        rep = check_ebook_updates(
            root, {"source": {"cbeta_ebook": root}},
            probe=lambda u, d: ("unchanged", ""))
        self.assertEqual(rep[0]["status"], "skipped")


class TestResolveCatalog(unittest.TestCase):
    """catalog 钉死内置：相对→仓库根解析；绝对/空→一律回内置。"""

    def test_relative_resolves_to_builtin(self):
        from pycbeta.fetch import resolve_catalog, builtin_catalog
        self.assertEqual(resolve_catalog("cbeta/data/sutra_mapping.txt"),
                         builtin_catalog())

    def test_absolute_and_empty_fall_back_to_builtin(self):
        from pycbeta.fetch import resolve_catalog, builtin_catalog
        self.assertEqual(resolve_catalog("X:\\nope\\mulu.txt"),
                         builtin_catalog())
        self.assertEqual(resolve_catalog(""), builtin_catalog())
        self.assertEqual(resolve_catalog(None), builtin_catalog())


class TestInspectXmlSource(unittest.TestCase):
    def _mk(self, d, edition):
        p = os.path.join(d, "T99n9999.xml")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>'
                    '<editionStmt>')
            if edition is not None:
                f.write(f"<edition>{edition}</edition>")
            f.write("</editionStmt></fileDesc></teiHeader><text><body/></text></TEI>")
        return p

    def test_p5_safe(self):
        from pycbeta.fetch import inspect_xml_source
        d = tempfile.mkdtemp()
        self._mk(d, "XML TEI P5")
        info = inspect_xml_source(d)
        self.assertTrue(info["safe"])
        self.assertEqual(info["edition"], "XML TEI P5")

    def test_p5b_unsafe(self):
        from pycbeta.fetch import inspect_xml_source
        d = tempfile.mkdtemp()
        self._mk(d, "單卷版 XML TEI P5b")
        info = inspect_xml_source(d)
        self.assertFalse(info["safe"])
        self.assertIn("P5b", info["edition"])

    def test_missing_edition_treated_safe(self):
        from pycbeta.fetch import inspect_xml_source
        d = tempfile.mkdtemp()
        self._mk(d, None)
        self.assertTrue(inspect_xml_source(d)["safe"])

    def test_empty_or_missing_dir(self):
        from pycbeta.fetch import inspect_xml_source
        self.assertIsNone(inspect_xml_source("")["safe"])
        self.assertIsNone(inspect_xml_source(r"X:\nope")["safe"])
        self.assertIsNone(inspect_xml_source(tempfile.mkdtemp())["safe"])


if __name__ == "__main__":
    unittest.main()
