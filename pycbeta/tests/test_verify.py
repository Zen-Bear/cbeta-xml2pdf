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
    """缺 verify.inline_brackets（如 publish 临时预设）→ 回退半角（官方口径）。
    epub 分支曾漏传该参数（渲染器默认全角），一并守护。"""

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

    def test_epub_branch_passes_brackets(self):
        import json
        import tempfile
        from unittest import mock
        from pycbeta.model import Work
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            pre = os.path.join(d, "presets.json")
            with open(pre, "w", encoding="utf-8") as f:
                json.dump({"output": {"inline_brackets": "fullwidth"},
                           "verify": {"inline_brackets": "halfwidth"}}, f)
            seen = {}
            with mock.patch.object(V, "EpubRenderer") as M:
                M.return_value.render_work.return_value = "x.epub"
                V.generate_formal("x.xml", Work(id="T", source_file="",
                                                metadata={}, body=[],
                                                notes_by_n={}, apps=[],
                                                simplified=False),
                                  "epub", os.path.join(d, "out"),
                                  config_path=pre)
                seen = M.call_args.kwargs
            self.assertEqual(seen.get("inline_brackets"), "halfwidth")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestBaselineRoots(unittest.TestCase):
    """配置基线目录（source.baselines）：2026r2 布局发现 + 首个非空根胜出。"""

    def _tree(self):
        import tempfile
        d = tempfile.mkdtemp()
        cfg = os.path.join(d, "r2")
        src = os.path.join(d, "work")
        # 2026r2 布局：{letter}/{ID}/{ID}_NNN.txt|docx；epub 为 {letter}/{ID}.epub
        os.makedirs(os.path.join(cfg, "T", "T0001"))
        for i in ("001", "002"):
            with open(os.path.join(cfg, "T", "T0001", f"T0001_{i}.txt"),
                      "w", encoding="utf-8") as f:
                f.write(f"cfg-note-{i}\n")
            with open(os.path.join(cfg, "T", "T0001", f"T0001_{i}.docx"),
                      "w", encoding="utf-8") as f:
                f.write("x")
        with open(os.path.join(cfg, "T", "T0001.epub"), "w",
                  encoding="utf-8") as f:
            f.write("x")
        # 旧布局（work 相邻目录）：txt/ 子目录
        os.makedirs(os.path.join(src, "txt"))
        with open(os.path.join(src, "txt", "T0001_001.txt"), "w",
                  encoding="utf-8") as f:
            f.write("src-note-001\n")
        return d, cfg, src

    def test_r2_layouts_found(self):
        import shutil
        import pycbeta.verify as V
        d, cfg, src = self._tree()
        try:
            txt = V.find_official(src, "T0001", "txt_notes",
                                  extra_roots=[cfg])
            self.assertTrue(txt)
            self.assertTrue(all(p.startswith(os.path.abspath(cfg))
                                for p in txt))
            docx = V.find_official(src, "T0001", "docx",
                                   extra_roots=[cfg])
            self.assertTrue(docx)
            self.assertTrue(all(p.startswith(os.path.abspath(cfg))
                                for p in docx))
            epub = V.find_official(src, "T0001", "epub",
                                   extra_roots=[cfg])
            self.assertEqual(len(epub), 1)
            self.assertTrue(epub[0].endswith("T0001.epub"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_configured_first_wins_no_merge(self):
        # 两边都有：只用配置根（不合并，避免同内容重复致注块翻倍）
        import shutil
        import pycbeta.verify as V
        d, cfg, src = self._tree()
        try:
            txt = V.find_official(src, "T0001", "txt_notes",
                                  extra_roots=[cfg])
            self.assertEqual(len(txt), 2)
            self.assertFalse(any(p.startswith(os.path.abspath(src))
                                 for p in txt))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_fallback_to_src(self):
        # 未配置/空串：回退旧行为（只查输入相邻目录）
        import shutil
        import pycbeta.verify as V
        d, cfg, src = self._tree()
        try:
            txt = V.find_official(src, "T0001", "txt_notes")
            self.assertEqual(len(txt), 1)
            self.assertTrue(txt[0].startswith(os.path.abspath(src)))
            txt2 = V.find_official(src, "T0001", "txt_notes",
                                   extra_roots=["", None])
            self.assertEqual(txt2, txt)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_juan_scope_in_root(self):
        import shutil
        import pycbeta.verify as V
        d, cfg, src = self._tree()
        try:
            txt = V.find_official(src, "T0001", "txt_notes",
                                  juan={1}, extra_roots=[cfg])
            self.assertEqual(len(txt), 1)
            self.assertTrue(txt[0].endswith("T0001_001.txt"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestJoinEpubSiddhamFigures(unittest.TestCase):
    """epub→txt 物化：ranja 读音/图注/无解缺字（X1077 类）。
    html/epub 形保持空元素（官方同款），只在 txt 重组形物化为官方 txt 形态。
    """

    def _xhtml(self, d, name, body):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"<html><head><title>t</title></head><body>{body}</body></html>")
        return p

    def test_ranja_materialized(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<span class='ranja' roman='ra\u1e43' code='RJ-CCEB' "
                    "char='X'/>乙</p>")
            f1 = self._xhtml(d, "ch1.xhtml", body)
            out = V._join_epub_ours([f1])
            self.assertIn("ra\u1e43", out)
            self.assertNotIn("ranja", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_empty_gaiji_becomes_square(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<span class=\"gaiji\" data-gid=\"RJ-E046\">"
                    "</span>乙</p>")
            f1 = self._xhtml(d, "ch1.xhtml", body)
            out = V._join_epub_ours([f1])
            self.assertIn("甲\u25a1乙", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_figure_caption_materialized(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<img src=\"data:image/gif;base64,AAA\" "
                    "alt=\"X59p0224_01.gif\" />乙</p>")
            f1 = self._xhtml(d, "ch1.xhtml", body)
            out = V._join_epub_ours([f1])
            self.assertIn("\u3010\u5716\uff1aX59p0224_01.gif\u3011", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_extract_keeps_empty(self):
        # extract（html/epub trial）仍视空元素为空，不受物化影响
        from pycbeta.verify import extract_text
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<span class='ranja' roman='ra\u1e43' code='RJ-CCEB' "
                    "char='X'/><span class=\"gaiji\" data-gid=\"RJ-E046\">"
                    "</span><img src=\"data:image/gif;base64,AAA\" "
                    "alt=\"X.gif\" />乙</p>")
            f1 = self._xhtml(d, "ch1.xhtml", body)
            self.assertEqual(extract_text(f1).replace("\n", ""), "甲乙")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestJoinEpubStarNotes(unittest.TestCase):
    """星号位注块复位（T0625 类）：官方 txt 注块按引用位点重复
    （`[23]` 与 `[*23-1]` 同块并存），html 星号位只留空标记，
    `_join_epub_ours` 按正文顺序复注块；add 注记亦按位交错。"""

    def _xhtml(self, d, name, body, notes=()):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"<html><head><title>t</title></head><body>{body}"
                    f"<hr><h1>校注</h1>{notes}</body></html>")
        return p

    def test_star_dup_positioned_by_body_order(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<a id=\"note_anchor_n1\" class=\"noteAnchor\" "
                    "href=\"#nn1\">[1]</a>乙"
                    "<span class='note-star' data-n='n1'></span>丙"
                    "<a id=\"note_anchor_n2\" class=\"noteAnchor\" "
                    "href=\"#nn2\">[2]</a>丁</p>")
            notes = ("<span class='footnote' id='nn1'>注一</span>"
                     "<span class='footnote' id='nn2'>注二</span>")
            f1 = self._xhtml(d, "ch1.xhtml", body, notes)
            out = V._join_epub_ours([f1])
            i1, i1d, i2 = out.find("注一"), out.find("注一", out.find("注一") + 1), out.find("注二")
            self.assertNotEqual(i1, -1)
            self.assertNotEqual(i1d, -1)
            self.assertLess(i1, i1d)
            self.assertLess(i1d, i2)
            self.assertNotIn("note-star", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_add_notes_interleaved_by_body_order(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<a id=\"note_anchor_n1\" class=\"noteAnchor\" "
                    "href=\"#nn1\">[1]</a>乙"
                    "<a id='cb_note_anchor1' class='noteAnchor add' "
                    "href='#cb_note_1'>[A1]</a>丙"
                    "<span class='note-star' data-n='n1'></span>"
                    "<a id=\"note_anchor_n2\" class=\"noteAnchor\" "
                    "href=\"#nn2\">[2]</a>丁</p>")
            notes = ("<span class='footnote' id='nn1'>注一</span>"
                     "<span class='footnote' id='nn2'>注二</span>"
                     "<div class='footnote' id='cb_note_1'>附加</div>")
            f1 = self._xhtml(d, "ch1.xhtml", body, notes)
            out = V._join_epub_ours([f1])
            self.assertLess(out.find("注一"), out.find("附加"))
            self.assertLess(out.find("附加"), out.find("注二"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_add_only_chapter_interleaved(self):
        # 无星号位但有新增校注的章节同样走按位重组（T1859 [A1] 类）
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<a id=\"note_anchor_n1\" class=\"noteAnchor\" "
                    "href=\"#nn1\">[1]</a>乙"
                    "<a id='cb_note_anchor1' class='noteAnchor add' "
                    "href='#cb_note_1'>[A1]</a>丙"
                    "<a id=\"note_anchor_n2\" class=\"noteAnchor\" "
                    "href=\"#nn2\">[2]</a>丁</p>")
            notes = ("<span class='footnote' id='nn1'>注一</span>"
                     "<span class='footnote' id='nn2'>注二</span>"
                     "<div class='footnote' id='cb_note_1'>附加</div>")
            f1 = self._xhtml(d, "ch1.xhtml", body, notes)
            out = V._join_epub_ours([f1])
            self.assertLess(out.find("注一"), out.find("附加"))
            self.assertLess(out.find("附加"), out.find("注二"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_no_star_byte_identical_to_split(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body = ("<p>甲<a id=\"note_anchor_n1\" class=\"noteAnchor\" "
                    "href=\"#nn1\">[1]</a>乙</p>")
            notes = "<span class='footnote' id='nn1'>注一</span>"
            f1 = self._xhtml(d, "ch1.xhtml", body, notes)
            raw = open(f1, encoding="utf-8").read()
            b, f = V._split_html_text(raw, body_only=True)
            self.assertEqual(V._join_epub_ours([f1]), b + "\n" + f)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestJoinEpubOurs(unittest.TestCase):
    """epub 生成侧正文+注块重组：多卷注记归文末，与官方 txt 同构。"""

    def _xhtml(self, d, name, body, notes=()):
        p = os.path.join(d, name)
        notes_html = "".join(
            f"<div class='footnote' id='n{i}'>{n}</div>" for i, n in enumerate(notes))
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"<html><head><title>t</title></head><body>{body}"
                    f"<hr><h1>校注</h1>{notes_html}</body></html>")
        return p

    def test_multi_file_notes_to_end(self):
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            f1 = self._xhtml(d, "ch1.xhtml", "<p>甲</p>", ["注一"])
            f2 = self._xhtml(d, "ch2.xhtml", "<p>乙</p>", ["注二"])
            out = V._join_epub_ours([f1, f2])
            self.assertLess(out.find("甲"), out.find("乙"))
            self.assertLess(out.find("乙"), out.find("注一"))
            self.assertLess(out.find("注一"), out.find("注二"))
            self.assertNotIn("校注", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_epub_container_skips_nav(self):
        import pycbeta.verify as V
        import zipfile
        d = tempfile.mkdtemp()
        try:
            ep = os.path.join(d, "a.epub")
            with zipfile.ZipFile(ep, "w") as z:
                z.writestr("OEBPS/nav.xhtml",
                           "<html><body>导航卷001</body></html>")
                z.writestr("OEBPS/ch1.xhtml",
                           "<html><body><p>正文</p></body></html>")
            out = V._join_epub_ours([ep])
            self.assertIn("正文", out)
            self.assertNotIn("导航", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_epub_boilerplate_skipped(self):
        # 官方结构 titlepage/front/toc/back 不进比对；无正文页回退全量
        import pycbeta.verify as V
        from pycbeta.verify import extract_text
        import zipfile
        d = tempfile.mkdtemp()
        try:
            ep = os.path.join(d, "off.epub")
            with zipfile.ZipFile(ep, "w") as z:
                z.writestr("OEBPS/titlepage.xhtml",
                           "<html><body>封面</body></html>")
                z.writestr("OEBPS/front.xhtml",
                           "<html><body>說明贊助捐款</body></html>")
                z.writestr("OEBPS/toc.xhtml",
                           "<html><body>目次</body></html>")
                z.writestr("OEBPS/juans/001.xhtml",
                           "<html><body><p>正文甲</p></body></html>")
                z.writestr("OEBPS/back.xhtml",
                           "<html><body>贊助</body></html>")
            t = extract_text(ep)
            self.assertIn("正文甲", t)
            for junk in ("封面", "贊助捐款", "目次", "贊助"):
                self.assertNotIn(junk, t)
            # _join 同口径
            self.assertNotIn("贊助", V._join_epub_ours([ep]))
            # 全是 boilerplate 时回退全量（不空比对）
            ep2 = os.path.join(d, "onlyback.epub")
            with zipfile.ZipFile(ep2, "w") as z:
                z.writestr("OEBPS/back.xhtml",
                           "<html><body>贊助</body></html>")
            self.assertIn("贊助", extract_text(ep2))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_extract_jiaozhu_flag(self):
        # html 校注头：默认剥离（docx/md/txt 比对）；html/epub 比对保留
        from pycbeta.verify import extract_text
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "a.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write("<html><body><p>文</p><hr><h1>校注</h1>"
                        "<span class='footnote'>注</span></body></html>")
            self.assertNotIn("校注", extract_text(p))
            kept = extract_text(p, strip_jiaozhu=False)
            self.assertIn("校注", kept)
            self.assertIn("注", kept)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_split_body_only(self):
        # 文件版只取 body：<title> 头文本不进正文/注记
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "c.xhtml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("<html><head><title>头标题</title></head>"
                        "<body><p>正文</p>"
                        "<span class='footnote' id='n1'>注文</span>"
                        "</body></html>")
            body, foot = V._extract_html_parts(p)
            self.assertIn("正文", body)
            self.assertNotIn("头标题", body + foot)
            self.assertIn("注文", foot)
            # 文本版默认全文（含头），body_only=True 同文件版
            with open(p, encoding="utf-8") as fh:
                raw = fh.read()
            full_body, _ = V._split_html_text(raw)
            self.assertIn("头标题", full_body)
            part_body, _ = V._split_html_text(raw, body_only=True)
            self.assertNotIn("头标题", part_body)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_nested_footnote_kept_whole(self):
        # 注记内嵌套 span（缺字 ruby）：旧非贪婪正则提前截断，
        # 尾部漏回正文；配平后整体归注记
        import pycbeta.verify as V
        raw = ("<p>正文甲</p>"
               "<span class='footnote' id='n1'>"
               "<a href='#a1'>[1]</a> 曜【大】＊"
               "<span class=\"gaiji\"><ruby>？<rt>gai</rt></ruby></span>"
               "尾【聖】＊</span>"
               "<p>正文乙</p>")
        body, foot = V._split_html_text(raw)
        self.assertIn("正文甲", body)
        self.assertIn("正文乙", body)
        self.assertNotIn("【聖】", body)
        self.assertIn("曜【大】＊", foot)
        self.assertIn("尾【聖】＊", foot)

    def test_nested_div_footnote(self):
        import pycbeta.verify as V
        raw = ("<p>前</p>"
               "<div class='footnote' id='c1'>"
               "<p>注首</p><div>内块尾【聖】</div></div>"
               "<p>后</p>")
        body, foot = V._split_html_text(raw)
        self.assertIn("前", body)
        self.assertIn("后", body)
        self.assertNotIn("内块尾", body)
        self.assertIn("注首", foot)
        self.assertIn("内块尾", foot)

    def test_unclosed_footnote_stays_in_body(self):
        # 未闭合与旧行为一致：留正文
        import pycbeta.verify as V
        raw = "<p>文</p><span class='footnote' id='n1'>注无尾"
        body, foot = V._split_html_text(raw)
        self.assertIn("注无尾", body)
        self.assertEqual(foot, "")


class TestEpubTxtBaseline(unittest.TestCase):
    """epub→txt_notes 首选：命中顺序 txt/epub/html；epub 现货仍比。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={}, body=[],
                    notes_by_n={}, apps=[], simplified=False)

    def _mkepub(self, d, name, text="正文甲"):
        import zipfile
        p = os.path.join(d, name)
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("OEBPS/ch1.xhtml",
                       f"<html><body><p>{text}</p></body></html>")
        return p

    def _mktxt(self, d, name, text="正文甲"):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def _run(self, d, by_kind):
        from unittest import mock
        import pycbeta.verify as V
        gen = self._mkepub(d, "T.epub")
        with mock.patch.object(V, "P5Parser") as P, \
                mock.patch.object(
                    V, "find_official",
                    side_effect=lambda s, st, k, juan=None, **kw:
                    by_kind.get(k, [])):
            P.return_value.parse.return_value = self._work()
            return V.verify_one("x.xml", "epub", d, os.path.join(d, "v"),
                                gen_paths=[gen])

    def test_txt_preferred(self):
        import shutil
        d = tempfile.mkdtemp()
        try:
            rec = self._run(d, {"txt_notes": [self._mktxt(d, "t.txt")]})
            self.assertEqual(rec["official_kind"], "txt_notes")
            self.assertEqual(rec["status"], "ok")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_trial_order_txt_epub_html(self):
        # 三 trial 全失败才走完循环：内容各不相同，保证 trials 有 3 条
        import shutil
        d = tempfile.mkdtemp()
        try:
            gen = self._mkepub(d, "T.epub", text="甲" * 30)
            by_kind = {"txt_notes": [self._mktxt(d, "t.txt", text="乙" * 30)],
                       "epub": [self._mkepub(d, "e.epub", text="丙" * 30)],
                       "html": [self._mktxt(d, "h.html", text="丁" * 30)]}
            from unittest import mock
            import pycbeta.verify as V
            with mock.patch.object(V, "P5Parser") as P, \
                    mock.patch.object(
                        V, "find_official",
                        side_effect=lambda s, st, k, juan=None, **kw:
                        by_kind.get(k, [])):
                P.return_value.parse.return_value = self._work()
                rec = V.verify_one("x.xml", "epub", d, os.path.join(d, "v"),
                                   gen_paths=[gen])
            self.assertEqual(rec["status"], "fail")
            self.assertEqual([t["kind"] for t in rec["trials"]],
                             ["txt_notes", "epub", "html"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_epub_only_still_compares(self):
        import shutil
        d = tempfile.mkdtemp()
        try:
            rec = self._run(d, {"epub": [self._mkepub(d, "e.epub")]})
            self.assertIn(rec["status"], ("ok", "fail"))
            self.assertEqual(rec["official_kind"], "epub")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestVerifyBases(unittest.TestCase):
    """基线链配置化：缺键/非法回退默认表；need 跟链首走。"""

    def test_chain_defaults(self):
        import pycbeta.verify as V
        self.assertEqual(V.chain_for("epub", None),
                         ["txt_notes", "epub", "html"])
        self.assertEqual(V.chain_for("docx", {}), ["docx", "html"])
        self.assertEqual(V.chain_for("txt", None), ["txt_notes"])

    def test_chain_override_and_sanitize(self):
        import pycbeta.verify as V
        self.assertEqual(V.chain_for("epub", {"epub": ["html"]}), ["html"])
        self.assertEqual(
            V.chain_for("epub", {"epub": ["zzz", "txt_notes", "txt_notes"]}),
            ["txt_notes"])
        self.assertEqual(V.chain_for("epub", {"epub": []}),
                         ["txt_notes", "epub", "html"])

    def test_need_follows_chain_head(self):
        import pycbeta.verify as V
        self.assertEqual(V.need_for_base("txt_notes"), ["txt_notes"])
        self.assertEqual(V.need_for_base("docx"), ["docx", "html"])
        self.assertEqual(V.need_for_base("zzz"), ["html"])

    def test_resolve_bases_order_and_dedup(self):
        import pycbeta.verify as V
        off = {"txt_notes": ["t"], "epub": ["e"], "html": ["h"]}
        self.assertEqual(
            V.resolve_bases("epub", off, None),
            [("txt_notes", ["t"]), ("epub", ["e"]), ("html", ["h"])])
        # 同路径去重
        self.assertEqual(
            V.resolve_bases("epub", {"txt_notes": ["x"], "html": ["x"]}, None),
            [("txt_notes", ["x"])])
        # 缺现货跳过
        self.assertEqual(V.resolve_bases("epub", {"html": ["h"]}, None),
                         [("html", ["h"])])

    def test_factory_bases_match_defaults(self):
        from pycbeta.theme import load_presets
        import pycbeta.verify as V
        self.assertEqual(load_presets()["verify"]["bases"], V.DEFAULT_BASES)


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

    def test_own_products_excluded(self):
        # 自产渲染物不得当基线：`{id 书名}.ext`（恒带空格）、`{stem}_html/` 目录
        flat = os.path.join(self.root, "T9999 Book")
        with open(os.path.join(flat, "T9999 Title.html"),
                  "w", encoding="utf-8") as f:
            f.write("product")
        htmldir = os.path.join(flat, "T99n9999_html")
        os.makedirs(htmldir, exist_ok=True)
        with open(os.path.join(htmldir, "T9999_001.html"),
                  "w", encoding="utf-8") as f:
            f.write("stray")
        hits = find_official(self.root, "T99n9999", "html")
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].endswith(os.path.join(
            "html", "T9999_001.html")))


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
        self.assertIn("【源】甲〖〓〗乙", s)  # 源空 span 填对端长度的 〓
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
        self.assertIn("【源】甲〖〓〗乙", s)
        self.assertNotIn("标出差异位置", s)

    def test_mark_span(self):
        from pycbeta.verify import _mark_span
        self.assertEqual(_mark_span("甲乙", 1, 1), "甲〖〗乙")
        self.assertEqual(_mark_span("甲X乙", 1, 2), "甲〖X〗乙")
        self.assertEqual(_mark_span("", 0, 0), "〖〗")
        # pad>0 且 span 为空：填对端长度的 〓，两行对齐
        self.assertEqual(_mark_span("甲乙", 1, 1, pad=1), "甲〖〓〗乙")
        self.assertEqual(_mark_span("甲乙", 1, 1, pad=3), "甲〖〓〓〓〗乙")
        self.assertEqual(_mark_span("甲X乙", 1, 2, pad=5), "甲〖X〗乙")


class TestWorkSummary(unittest.TestCase):
    """总结行 `[id] N format: 1[docx=OK], …`：下游速读。"""

    def test_single_ok(self):
        from pycbeta.verify import format_work_summary
        self.assertEqual(format_work_summary("T1", [("docx", "ok", 0, 0)]),
                         "[T1] 1 format: 1[docx=OK(0/0)]")

    def test_multi_mixed(self):
        from pycbeta.verify import format_work_summary
        s = format_work_summary("T45n1859", [
            ("docx", "ok", 0, 0), ("pdf", "covered", None, None, "docx"),
            ("epub", "fail", 48, 97)])
        self.assertEqual(
            s, "[T45n1859] 3 format: 1[docx=OK(0/0)], 2[pdf=1], "
               "3[epub=FAIL(48/97)]")

    def test_other_statuses(self):
        from pycbeta.verify import format_work_summary
        s = format_work_summary("X", [("epub", "no_baseline", None, None),
                                      ("txt", "nogen", None, None),
                                      ("md", "error", None, None)])
        self.assertEqual(s, "[X] 3 format: 1[epub=NO_BASELINE], 2[txt=NOGEN], "
                            "3[md=ERROR]")

    def test_fmt_arrow_stripped(self):
        from pycbeta.verify import format_work_summary
        self.assertEqual(format_work_summary("T", [("pdf→docx", "ok", 0, 0)]),
                         "[T] 1 format: 1[pdf=OK(0/0)]")

    def test_covered_unresolved_falls_back(self):
        # 引用目标不在本行内 → 回退 COVERED，不断格式
        from pycbeta.verify import format_work_summary
        s = format_work_summary("T", [("pdf", "covered", None, None, "docx")])
        self.assertEqual(s, "[T] 1 format: 1[pdf=COVERED]")
        s = format_work_summary("T", [("pdf", "covered", None, None, "html"),
                                      ("docx", "ok", 0, 0)])
        self.assertEqual(s, "[T] 2 format: 1[pdf=COVERED], 2[docx=OK(0/0)]")

    def test_covered_out_of_order_resolves(self):
        # 记录乱序（pdf 在前）仍按 fmt 定位
        from pycbeta.verify import format_work_summary
        s = format_work_summary("T", [("pdf", "covered", None, None, "docx"),
                                      ("docx", "fail", 1, 2)])
        self.assertEqual(s, "[T] 2 format: 1[pdf=2], 2[docx=FAIL(1/2)]")

    def test_ok_none_counts(self):
        from pycbeta.verify import format_work_summary
        self.assertEqual(format_work_summary("T", [("docx", "ok", None, None)]),
                         "[T] 1 format: 1[docx=OK(?/?)]")

    def test_group_summary_covered_ref(self):
        # GUI covered 记录带 cover_by：引用与记录顺序无关
        from pycbeta.verify import format_verify_report
        recs = [
            {"id": "T1", "xml": "a.xml", "fmt": "pdf", "status": "covered",
             "cover_by": "docx", "detail": "已由 docx 校验覆盖（未重复）"},
            {"id": "T1", "xml": "a.xml", "fmt": "docx", "status": "ok",
             "missing": 0, "extra": 0},
        ]
        s = "\n".join(format_verify_report(recs))
        self.assertIn("[T1] 2 format: 1[pdf=2], 2[docx=OK(0/0)]", s)
        self.assertIn("[--]  pdf 已由 docx 校验覆盖", s)

    def test_group_summary_in_report(self):
        from pycbeta.verify import format_verify_report
        recs = [
            {"id": "T1", "xml": "a.xml", "fmt": "docx", "status": "ok",
             "missing": 0, "extra": 0},
            {"id": "T1", "xml": "a.xml", "fmt": "epub", "status": "fail",
             "missing": 2, "extra": 3},
            {"id": "T2", "xml": "b.xml", "fmt": "txt", "status": "no_baseline"},
        ]
        s = "\n".join(format_verify_report(recs))
        self.assertIn("[T1] 2 format: 1[docx=OK(0/0)], 2[epub=FAIL(2/3)]", s)
        # 有 id 的按 id 聚组
        self.assertIn("[T2] 1 format: 1[txt=NO_BASELINE]", s)
        # 原有行保留
        self.assertIn("=== a.xml", s)
        self.assertIn("=== b.xml", s)


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
