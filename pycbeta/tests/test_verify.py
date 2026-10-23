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
    _strip_official_no, _NOTE_LINE_RE

NOTE_RE = _NOTE_LINE_RE


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


class TestGenerateFormalHtmlTheme(unittest.TestCase):
    """generate_formal html/epub：与转换同 CSS（基底 + html-epub-user-theme 增量）。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={}, body=[],
                    notes_by_n={}, apps=[], simplified=False)

    def _pre(self, d, user=None):
        import json
        pre = os.path.join(d, "presets.json")
        cfg = {"output": {}, "verify": {}}
        if user:
            cfg["html-epub-user-theme"] = user
        with open(pre, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return pre

    def test_html_receives_base_css(self):
        import tempfile
        from unittest import mock
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            up = os.path.join(d, "u.css")
            with open(up, "w", encoding="utf-8") as f:
                f.write("div.usermark{color:red}")
            with mock.patch.object(V, "HtmlRenderer") as M:
                M.return_value.render_work.return_value = ["x.html"]
                V.generate_formal("x.xml", self._work(), "html",
                                  os.path.join(d, "out"),
                                  config_path=self._pre(d, up))
                base = M.call_args.kwargs.get("base_css")
            self.assertIn("cbetarc", base)       # 官方基底仍在
            self.assertIn("div.usermark{color:red}", base)  # 增量追加在后
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_epub_receives_base_css(self):
        import tempfile
        from unittest import mock
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            up = os.path.join(d, "u.css")
            with open(up, "w", encoding="utf-8") as f:
                f.write("div.usermark{color:red}")
            with mock.patch.object(V, "EpubRenderer") as M:
                M.return_value.render_work.return_value = "x.epub"
                V.generate_formal("x.xml", self._work(), "epub",
                                  os.path.join(d, "out"),
                                  config_path=self._pre(d, up))
                base = M.call_args.kwargs.get("base_css")
            self.assertIn("cbetarc", base)
            self.assertIn("div.usermark{color:red}", base)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_no_user_theme_stays_official(self):
        import tempfile
        from unittest import mock
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            with mock.patch.object(V, "HtmlRenderer") as M:
                M.return_value.render_work.return_value = ["x.html"]
                V.generate_formal("x.xml", self._work(), "html",
                                  os.path.join(d, "out"),
                                  config_path=self._pre(d))
                base = M.call_args.kwargs.get("base_css")
            self.assertIn("cbetarc", base)       # user 空时行为零变化
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

    def test_cross_file_anchor_block_reading_order(self):
        # 跨文件：正文锚点在 ch1，注块却在 ch2（mulu 拆分致背节整体落末章）。
        # 旧逐块逻辑在 ch2 只看 ch2 锚点 → add 块丢失、reg 块垫底；
        # 全局遇序后按 ch1 锚点位置归位（X1077 母佛疑倒实锤）。
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            body1 = ("<p>甲<a id=\"note_anchor_n1\" class=\"noteAnchor\" "
                     "href=\"#nn1\">[1]</a>乙"
                     "<a id='cb_note_anchor1' class='noteAnchor add' "
                     "href='#cb_note_1'>[A1]</a>丙</p>")
            body2 = "<p>丁</p>"
            notes = ("<span class='footnote' id='nn1'>注一</span>"
                     "<div class='footnote' id='cb_note_1'>附加</div>")
            f1 = self._xhtml(d, "ch1.xhtml", body1)
            f2 = self._xhtml(d, "ch2.xhtml", body2, notes)
            out = V._join_epub_ours([f1, f2])
            self.assertNotEqual(out.find("附加"), -1)
            self.assertLess(out.find("注一"), out.find("附加"))
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

    def test_extract_text_epub_reading_order(self):
        # html trial：epub 抽取按全局正文锚点遭遇序归位（锚在前章、块在后章）。
        # 旧逻辑不重排 → 分组序（reg 先）与官方 html 阅读序错位（X1077 实锤）。
        import pycbeta.verify as V
        import zipfile
        d = tempfile.mkdtemp()
        try:
            ep = os.path.join(d, "a.epub")
            ch1 = ("<html><body><p>甲"
                   "<a id='cb_note_anchor1' class='noteAnchor add' href='#cb_note_1'>[A1]</a>"
                   "<a id=\"note_anchor_n1\" class=\"noteAnchor\" href=\"#nn1\">[1]</a>"
                   "乙</p></body></html>")
            ch2 = ("<html><body><p>丙</p><hr><h1>校注</h1>"
                   "<span class='footnote' id='nn1'>注一</span>"
                   "<div class='footnote' id='cb_note_1'>附加</div></body></html>")
            with zipfile.ZipFile(ep, "w") as z:
                z.writestr("OEBPS/ch1.xhtml", ch1)
                z.writestr("OEBPS/ch2.xhtml", ch2)
            out = V.extract_text(ep, strip_jiaozhu=False)
            self.assertLess(out.find("附加"), out.find("注一"))
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

    def test_footnote_spans_anchor_order(self):
        # 顺序校注：分组注块按正文锚点遭遇序重排（官方 html 数字块+A 块 → 交错）
        import pycbeta.verify as V
        raw = ("<p>甲<a id=\"note_anchor_n1\" href=\"#nn1\">[1]</a>乙"
               "<a id='cb_note_anchor1' href='#cb_note_1'>[A1]</a>丙"
               "<a id=\"note_anchor_n2\" href=\"#nn2\">[2]</a>丁</p>"
               "<span class='footnote' id='nn1'>注一</span>"
               "<span class='footnote' id='nn2'>注二</span>"
               "<div class='footnote' id='cb_note_1'>附加</div>")
        body, foot = V._split_html_text(raw)
        self.assertLess(foot.find("注一"), foot.find("附加"))
        self.assertLess(foot.find("附加"), foot.find("注二"))
        self.assertIn("甲", body)

    def test_footnote_spans_no_anchor_stable(self):
        # 无锚条目 stable 垫底；单注原样
        import pycbeta.verify as V
        raw = ("<p>甲<a id=\"note_anchor_n1\" href=\"#nn1\">[1]</a>乙</p>"
               "<span class='footnote' id='nn1'>注一</span>"
               "<div class='footnote'>无名注</div>")
        body, foot = V._split_html_text(raw)
        self.assertLess(foot.find("注一"), foot.find("无名注"))
        one = V._split_html_text("<p>文</p><span class='footnote' id='n1'>注</span>")
        self.assertIn("注", one[1])

    def test_extract_text_html_reading_order(self):
        # 抽取层遇序化：extract_text 对分组 html 按阅读顺序输出注块
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "c.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "<html><body><p>甲"
                    "<a id=\"note_anchor_n1\" href=\"#nn1\">[1]</a>乙"
                    "<a id='cb_note_anchor1' href='#cb_note_1'>[A1]</a>丙"
                    "<a id=\"note_anchor_n2\" href=\"#nn2\">[2]</a>丁</p>"
                    "<span class='footnote' id='nn1'>注一</span>"
                    "<span class='footnote' id='nn2'>注二</span>"
                    "<div class='footnote' id='cb_note_1'>附加</div>"
                    "</body></html>")
            out = V.extract_text(p)
            self.assertLess(out.find("注一"), out.find("附加"))
            self.assertLess(out.find("附加"), out.find("注二"))
            self.assertIn("甲", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_extract_text_html_already_ordered_stable(self):
        # 已遇序的 html（我方形态）重排为幂等：顺序与内容不变
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "c.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "<html><body><p>甲"
                    "<a id=\"note_anchor_n1\" href=\"#nn1\">[1]</a>乙"
                    "<a id='cb_note_anchor1' href='#cb_note_1'>[A1]</a>丙"
                    "<a id=\"note_anchor_n2\" href=\"#nn2\">[2]</a>丁</p>"
                    "<span class='footnote' id='nn1'>注一</span>"
                    "<div class='footnote' id='cb_note_1'>附加</div>"
                    "<span class='footnote' id='nn2'>注二</span>"
                    "</body></html>")
            out = V.extract_text(p)
            self.assertLess(out.find("注一"), out.find("附加"))
            self.assertLess(out.find("附加"), out.find("注二"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestEpubTxtBaseline(unittest.TestCase):
    """epub→html 首选：命中顺序 html/txt_notes/epub；epub 现货仍比。"""

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

    def test_trial_order_html_txt_epub(self):
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
                             ["html", "txt_notes", "epub"])
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
                         ["html", "txt_notes", "epub"])
        self.assertEqual(V.chain_for("docx", {}), ["docx", "html"])
        self.assertEqual(V.chain_for("txt", None), ["txt_notes"])

    def test_chain_override_and_sanitize(self):
        import pycbeta.verify as V
        self.assertEqual(V.chain_for("epub", {"epub": ["html"]}), ["html"])
        self.assertEqual(
            V.chain_for("epub", {"epub": ["zzz", "txt_notes", "txt_notes"]}),
            ["txt_notes"])
        self.assertEqual(V.chain_for("epub", {"epub": []}),
                         ["html", "txt_notes", "epub"])

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
            [("html", ["h"]), ("txt_notes", ["t"]), ("epub", ["e"])])
        # 同路径去重（链序在前者胜）
        self.assertEqual(
            V.resolve_bases("epub", {"txt_notes": ["x"], "html": ["x"]}, None),
            [("html", ["x"])])
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

    def test_longer_token_first_no_residue(self):
        # 令牌互为前缀（No. 1651-1 ⊂ No. 1651-10）：长先剥 + 词边界，
        # 不得把 "No. 1651-10" 剥成 "0"
        s = "No. 1651-10 大周西明寺故大德圓測法師佛舍利塔銘\n"
        out = _strip_official_no(s, ["No. 1651-1", "No. 1651-10"])
        self.assertTrue(out.startswith("大周西明寺"))
        self.assertNotIn("0 ", out)
        self.assertEqual(
            _strip_official_no("No. 1651-1 卷上\n", ["No. 1651-1"]), "卷上\n")

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

    def test_data_label_note_moved(self):
        """科判注（subtype=ke）行 `    [ data-label='科NN'] 内容` 同移文末、保持文件序。"""
        s = ("正文一\n"
             "\n"
             "    [ data-label='科01'] 第一序分初證信序\n"
             "\n"
             "    [0001a01] 已【CB】，巳【卍續】\n"
             "\n"
             "正文二\n")
        body, notes = _extract_txt_parts(s)
        self.assertNotIn("第一序分初證信序", body)
        self.assertIn("[ data-label='科01'] 第一序分初證信序", notes)
        self.assertIn("[0001a01] 已【CB】，巳【卍續】", notes)
        # 文件序（科判注在数字注之前）
        self.assertLess(notes.find("第一序分初證信序"), notes.find("已【CB】"))
        self.assertIn("正文二", body)

    def test_star_dup_line_dropped(self):
        """星号位复注：官方同一注在正文位多渲染一行（同文、4 空格缩进）→ 去重。"""
        s = ("正文\n"
             "    [1] 疑疑礙次同\n"
             "    疑疑礙次同\n"
             "    後文\n")
        body, notes = _extract_txt_parts(s)
        self.assertEqual(notes, "    [1] 疑疑礙次同")
        self.assertNotIn("疑疑礙次同", body)
        self.assertIn("後文", body)

    def test_data_label_inline_marker_stays(self):
        """正文内联科判锚点（非 4 空格注行）不得当注移走（由 normalize 剥标记）。"""
        s = "正文[ data-label='科01']如是我聞：\n\n後文\n"
        body, notes = _extract_txt_parts(s)
        self.assertEqual(notes.strip(), "")
        self.assertIn("如是我聞", body)

    def test_end_to_end_txt_notes_align(self):
        """官方侧（内联科判注 + 星号位重复行）与生成侧（文末注）归一后逐字一致。"""
        from pycbeta.verify import normalize, _norm_official_txt
        official = ("(一)如是我聞：\n"
                    "\n"
                    "    [ data-label='科01'] 第一序分初證信序\n"
                    "    第一序分初證信序\n"
                    "\n"
                    "    [0001a01] 已【CB】，巳【卍續】\n")
        ours = ("(一)如是我聞：\n"
                "\n"
                "[0524k01] 第一序分初證信序\n"
                "[0001a01] 已【CB】，巳【卍續】\n")
        self.assertEqual(normalize(ours),
                         normalize(_norm_official_txt(official)))

    def test_real_file_anchor(self):
        from pycbeta.tests._data import DATA_ROOT
        p = os.path.join(DATA_ROOT, "T0349 彌勒菩薩所問本願經",
                         "T0349.txt", "T0349_001.txt")
        if not os.path.isfile(p):
            self.skipTest("缺少外部测试数据：设 PYCBETA_TEST_DATA")
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


class TestNormalizeDataLabel(unittest.TestCase):
    """官方 txt 科判注标记 `[ data-label='科NN']` 剥离（normalize）。"""

    def test_strip_marker(self):
        from pycbeta.verify import normalize
        self.assertEqual(normalize("[ data-label='科01']如是我聞："),
                         normalize("如是我聞："))
        self.assertEqual(normalize("第一序分初證信序[ data-label='科02']"),
                         normalize("第一序分初證信序"))
        # 无空格变体（防上游格式微差）
        self.assertEqual(normalize("x[data-label='科03']y"), normalize("xy"))

    def test_other_long_brackets_kept(self):
        from pycbeta.verify import normalize
        # 缺字拆字式长括号（两侧同形，须保留参与比对；内部连字符由通规则剥除）
        n = normalize("[泳-永+(瑤-王)]")
        self.assertIn("泳", n)
        self.assertIn("瑤", n)
        self.assertIn("[", n)   # 括号未被 data-label 规则误剥


class TestBodySidecar(unittest.TestCase):
    """旁路「仅正文」比对（差异是否全在注释）：分段 helper + 严格 0 判定。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)

    def _html(self, name, body, notes):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("<html><body><p>" + body + "</p>\n"
                    "<span class='footnote' id='n1'>"
                    "<a href='#note_anchor_1'>[1]</a> " + notes + "</span>\n"
                    "</body></html>")
        return p

    def _docx(self, name, body, notes=None):
        p = os.path.join(self.tmp, name)
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("word/document.xml",
                       "<w:document><w:body><w:p><w:r><w:t>" + body
                       + "</w:t></w:r></w:p></w:body></w:document>")
            if notes is not None:
                z.writestr("word/footnotes.xml",
                           "<w:footnotes><w:footnote><w:p><w:r><w:t>" + notes
                           + "</w:t></w:r></w:p></w:footnote></w:footnotes>")
        return p

    def test_split_txt_ours_tail_notes(self):
        from pycbeta.verify import _split_txt_ours
        body, notes = _split_txt_ours("正文一\n正文二\n\n[1] 注一\n\n[2] 注二")
        self.assertEqual(body, "正文一\n正文二")
        self.assertIn("[1] 注一", notes)
        self.assertIn("[2] 注二", notes)
        # 无注块：原样
        b2, n2 = _split_txt_ours("正文一\n正文二")
        self.assertEqual((b2, n2), ("正文一\n正文二", ""))

    def test_split_md_body(self):
        from pycbeta.verify import _split_md_body
        body, notes = _split_md_body("正文一\n\n## 校注\n\n[^1]: 注一")
        self.assertEqual(body, "正文一\n\n")
        self.assertIn("## 校注", notes)
        self.assertEqual(_split_md_body("无注")[1], "")

    def test_extract_docx_parts(self):
        from pycbeta.verify import _extract_docx_parts, extract_text
        p = self._docx("a.docx", "正文甲", "注甲")
        body, notes = _extract_docx_parts(p)
        self.assertEqual(body.strip(), "正文甲")
        self.assertEqual(notes.strip(), "注甲")
        # 与 extract_text 逐字节一致（正文 + "\n" + 脚注）
        self.assertEqual(extract_text(p), body + "\n" + notes)
        p2 = self._docx("b.docx", "正文乙")
        self.assertIsNone(_extract_docx_parts(p2)[1])
        self.assertEqual(extract_text(p2).strip(), "正文乙")

    def test_body_sidecar_notes_only(self):
        from pycbeta.verify import _body_sidecar
        gen = self._html("gen.html", "正文甲", "注一")
        off = self._html("off.html", "正文甲", "注二")   # 正文同、注释异
        bm, be, notes_only = _body_sidecar([gen], "html", off, "html")
        self.assertEqual((bm, be), (0, 0))
        self.assertTrue(notes_only)

    def test_body_sidecar_body_diff(self):
        from pycbeta.verify import _body_sidecar
        gen = self._html("gen2.html", "正文甲", "注一")
        off = self._html("off2.html", "正文乙", "注一")   # 正文异
        bm, be, notes_only = _body_sidecar([gen], "html", off, "html")
        self.assertGreater(bm + be, 0)
        self.assertFalse(notes_only)

    def test_body_sidecar_unsupported(self):
        from pycbeta.verify import _body_sidecar
        gen = self._html("gen3.html", "正文甲", "注一")
        bm, be, notes_only = _body_sidecar([gen], "html", "x.odt", "odt")
        self.assertIsNone(notes_only)
        self.assertIsNone(bm)
        self.assertIsNone(be)

    def test_cfg_int_keeps_zero(self):
        """配置整数取值：只有缺失才回缺省，0 原样保留（2026-10-15 用户反馈：
        maxDiff 0 被 `or 10` 改成 10）。"""
        from pycbeta.verify import cfg_int
        self.assertEqual(cfg_int(None, 10), 10)
        self.assertEqual(cfg_int("", 10), 10)
        self.assertEqual(cfg_int(0, 10), 0)
        self.assertEqual(cfg_int(5, 10), 5)
        self.assertEqual(cfg_int("3", 10), 3)

    def test_report_max_diff_zero(self):
        """阈值 0 必须生效：缺3/多0 在 max_diff=0 下判 FAIL。"""
        from pycbeta.verify import _format_verify_record
        rec = {"xml": "x.xml", "fmt": "txt", "status": "fail",
               "missing": 3, "extra": 0,
               "trials": [{"kind": "txt_notes", "official": "o.txt",
                           "missing": 3, "extra": 0, "total": 3, "ok": False,
                           "ctx": [], "ctx_loc": []}]}
        txt = "\n".join(_format_verify_record(rec, 5, 0))
        self.assertIn("[FAIL]", txt)
        self.assertIn(">阈值0)", txt)

    def test_report_line_scope(self):
        from pycbeta.verify import _format_verify_record
        rec = {"xml": "x.xml", "fmt": "html", "status": "fail",
               "missing": 5, "extra": 0,
               "trials": [{"kind": "html", "official": "o.html",
                           "missing": 5, "extra": 0, "total": 5, "ok": False,
                           "ctx": [], "ctx_loc": [],
                           "body_missing": 0, "body_extra": 0,
                           "diff_scope": "notes_only"}]}
        txt = "\n".join(_format_verify_record(rec, 5, 10))
        # 并入 [OK]/[FAIL] 行末、`【】` 包裹（2026-10-13）；
        # 文案简化为「【仅仅注释差异】」（2026-10-13 用户反馈）
        self.assertIn("【仅仅注释差异】", txt)
        self.assertNotIn("正文差异 0（差异全部在注释）", txt)
        self.assertNotIn("\n      正文差异", txt)

    def test_report_line_scope_zero_no_suffix(self):
        """缺0/多0：不显示「正文差异 0」（2026-10-13 用户反馈）。"""
        from pycbeta.verify import _format_verify_record
        rec = {"xml": "x.xml", "fmt": "html", "status": "ok",
               "missing": 0, "extra": 0,
               "trials": [{"kind": "html", "official": "o.html",
                           "missing": 0, "extra": 0, "total": 0, "ok": True,
                           "ctx": [], "ctx_loc": [], "diff_scope": "notes_only"}]}
        txt = "\n".join(_format_verify_record(rec, 5, 10))
        self.assertIn("  [OK] (html→html 缺0/多0 ≤阈值10)", txt)
        self.assertNotIn("正文差异", txt)
        self.assertNotIn("仅仅注释差异", txt)

    def test_report_line_scope_unknown(self):
        from pycbeta.verify import _format_verify_record
        rec = {"xml": "x.xml", "fmt": "odt", "status": "fail",
               "missing": 3, "extra": 0,
               "trials": [{"kind": "odt", "official": "o.odt",
                           "missing": 3, "extra": 0, "total": 3, "ok": False,
                           "ctx": [], "ctx_loc": [], "diff_scope": "unknown"}]}
        txt = "\n".join(_format_verify_record(rec, 5, 10))
        self.assertIn("正文无法判定", txt)


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

    def test_strict_juan_no_wrong_volume_fallback(self):
        """真子集：无对应卷文件 → 该种基线缺席（错卷文件不得充数，T0220:523 实锤）。"""
        self.assertEqual(
            find_official(self.root, "T99n9999", "txt_notes",
                          juan={3}, strict_juan=True), [])

    def test_nonstrict_juan_keeps_fallback(self):
        """整本/全覆盖任务（非 strict）：旧回退行为保留（按冊命名对不上时可用）。"""
        hits = find_official(self.root, "T99n9999", "txt_notes", juan={3})
        self.assertEqual(len(hits), 2)

    def test_strict_juan_keeps_matching(self):
        hits = find_official(self.root, "T99n9999", "txt_notes",
                             juan={1}, strict_juan=True)
        self.assertEqual([os.path.basename(f) for f in hits], ["T9999_001.txt"])

    def test_epub_scope_strict(self):
        """epub 纳入卷限定：整部单文件（无 _NNN）不得充子集基线；按卷 epub 可命中。"""
        d = os.path.join(self.root, "T9999 Book", "epub")
        os.makedirs(d, exist_ok=True)
        whole = os.path.join(d, "T9999.epub")
        with open(whole, "w", encoding="utf-8") as f:
            f.write("whole")
        self.assertEqual(
            find_official(self.root, "T99n9999", "epub",
                          juan={1}, strict_juan=True), [])
        self.assertEqual(
            find_official(self.root, "T99n9999", "epub", juan={1}), [whole])
        vol = os.path.join(d, "T9999_002.epub")
        with open(vol, "w", encoding="utf-8") as f:
            f.write("vol2")
        hits = find_official(self.root, "T99n9999", "epub",
                             juan={2}, strict_juan=True)
        self.assertEqual([os.path.basename(f) for f in hits],
                         ["T9999_002.epub"])


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


class TestDiffStats(unittest.TestCase):
    """diff_stats 前后缀裁剪优化：计数/ctx 与全文 difflib 一致（同作品高相似）。"""

    def test_identical(self):
        from pycbeta.verify import diff_stats
        m, mi, ex, ctx = diff_stats("甲" * 5000, "甲" * 5000)
        self.assertEqual((mi, ex, ctx), (0, 0, []))
        self.assertEqual(m, 5000)

    def test_localized_diff_offsets(self):
        # 差异在中段：ctx 索引须为全文绝对位置（+前缀）
        from pycbeta.verify import diff_stats
        ours = "A" * 1000 + "X" + "B" * 1000
        theirs = "A" * 1000 + "Y" + "B" * 1000
        m, mi, ex, ctx = diff_stats(ours, theirs)
        self.assertEqual((mi, ex), (1, 1))
        self.assertEqual(len(ctx), 1)
        tag, i1, i2, j1, j2 = ctx[0]
        self.assertEqual((i1, i2, j1, j2), (1000, 1001, 1000, 1001))

    def test_matches_full_difflib_on_similar(self):
        # 高相似（同作品场景）：裁剪结果 == 全文 difflib
        import difflib
        from pycbeta.verify import diff_stats
        base = ("经文内容重复出现测试。" * 300)
        ours = "首" + base + "甲" * 5 + "尾"
        theirs = "首" + base + "乙" * 5 + "尾"
        sm = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
        matched = sum(b.size for b in sm.get_matching_blocks())
        m, mi, ex, _ = diff_stats(ours, theirs)
        self.assertEqual((m, mi, ex),
                         (matched, len(theirs) - matched, len(ours) - matched))

    def test_prefix_suffix_only(self):
        from pycbeta.verify import diff_stats
        # theirs（官方）末尾多两字 → missing=2（生成档缺失）
        m, mi, ex, ctx = diff_stats("甲乙丙丁", "甲乙丙丁戊己")
        self.assertEqual((mi, ex), (2, 0))
        self.assertEqual(ctx, [("insert", 4, 4, 4, 6)])


class TestTrialPassLine(unittest.TestCase):
    """trial 通过行：0/0 记逐字一致；非 0/0 如实打出缺/多数。

    不再断言“仅含CBETA版本日期/版权等元数据微小差异”（差异性质由片段举证）。"""

    def test_zero(self):
        from pycbeta.verify import trial_pass_line
        s = trial_pass_line("txt_notes", 0, 0, 0, 10)
        self.assertIn("逐字完全一致", s)
        self.assertNotIn("缺", s)

    def test_nonzero_reports_counts(self):
        from pycbeta.verify import trial_pass_line
        s = trial_pass_line("txt_notes", 3, 2, 5, 10)
        self.assertIn("缺3字", s)
        self.assertIn("多2字", s)
        self.assertIn("合计5", s)
        self.assertIn("≤阈值10", s)
        self.assertNotIn("仅含CBETA", s)


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


class TestNormalizeEntities(unittest.TestCase):
    def test_html_entities_unescaped(self):
        # 官方 HTML 经正则剥标签，`&quot;`/`&#39;` 等残留；生成侧为 raw 字符。
        # normalize 须归一，否则 T0001 类巴利引文整段计缺。
        from pycbeta.verify import normalize
        self.assertEqual(normalize('～&quot;Aggo &#39;ham asmi&quot;'),
                         normalize('～"Aggo \'ham asmi"'))
        self.assertEqual(normalize('a&amp;b'), normalize('a&b'))
        self.assertEqual(normalize('a&lt;b&gt;c'), normalize('a<b>c'))

    def test_unknown_entity_kept_and_plain_unchanged(self):
        from pycbeta.verify import normalize
        # 未知实体原样保留（`&not` 是合法遗留实体会变 `¬`，故用无歧义词缀）
        self.assertEqual(normalize('&xyzabc;'), '&xyzabc;')
        self.assertEqual(normalize('甲乙丙'), '甲乙丙')


class TestReportBaselineLabel(unittest.TestCase):
    """报告 `【源】` 行带基线类别（`{fmt}→{kind}`）：避免「epub 【源】…txt」误读
    （T1499 反馈）；下游取 `【源】` 前 disp 的 `→` 左侧为产物格式，兼容。"""

    def test_source_line_carries_baseline_kind(self):
        from pycbeta.verify import format_verify_report
        recs = [{
            "xml": "T24n1499.xml", "fmt": "epub", "status": "fail",
            "gen": "T24n1499.epub", "official_kind": "txt_notes",
            "official": r"E:\x\txt\T1499_001.txt",
            "missing": 0, "extra": 18, "total": 18,
            "norm_gen": "甲", "norm_official": "甲",
            "trials": [
                {"kind": "txt_notes", "official": r"E:\x\txt\T1499_001.txt",
                 "missing": 0, "extra": 18, "total": 18, "ok": False, "ctx": []},
                {"kind": "epub", "official": r"E:\x\epub\T1499.epub",
                 "missing": 1, "extra": 138, "total": 139, "ok": False, "ctx": []},
            ],
        }]
        s = "\n".join(format_verify_report(recs))
        # 每个 trial 的 【源】 行都带自己的基线类别
        self.assertIn("epub→txt_notes 【源】", s)
        self.assertIn("epub→epub 【源】", s)
        # 下游解析：`【源】` 前 disp 取 `→` 左侧 = 产物格式
        src_lines = [ln for ln in s.splitlines() if "【源】" in ln]
        self.assertEqual(len(src_lines), 2)
        for ln in src_lines:
            self.assertEqual(
                ln.split("【源】")[0].strip().split("→")[0].strip(), "epub")


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

    def test_report_full_lines_and_raw_files(self):
        from pycbeta.verify import format_verify_report
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        base = os.path.join(root, "b.html")
        with open(base, "w", encoding="utf-8") as f:
            f.write("<html><body><p>[0036004]锚</p><p>甲乙</p></body></html>")
        sc = os.path.join(root, "s.txt")
        with open(sc, "w", encoding="utf-8") as f:
            f.write("甲乙\n")
        gc = os.path.join(root, "g.txt")
        with open(gc, "w", encoding="utf-8") as f:
            f.write("甲X乙\n")
        dp = os.path.join(root, "g.docx")
        with zipfile.ZipFile(dp, "w") as z:
            z.writestr("word/document.xml",
                       "<w:document><w:body><w:p><w:t>甲X乙</w:t></w:p>"
                       "</w:body></w:document>")
            z.writestr("word/footnotes.xml", "<w:footnotes/>")
        recs = [{
            "xml": "T01n0001.xml", "fmt": "docx", "status": "fail",
            "gen": [dp],
            "trials": [{
                "kind": "html", "official": base, "official_files": [base],
                "missing": 0, "extra": 1, "total": 1, "ok": False,
                "ctx": [("insert", 1, 2, 1, 1)],
                "ctx_loc": [{"gen_line": 1, "src_line": 1}],
                "src_cmp": sc, "gen_cmp": gc,
                "norm_official": "甲乙", "norm_gen": "甲X乙",
            }],
        }]
        s = "\n".join(format_verify_report(recs))
        self.assertIn("【源整行】甲乙", s)
        self.assertIn("【新整行】甲X乙", s)
        self.assertIn("【源文件】b.html:2行（[0036004]后1行）", s)
        self.assertIn("【新文件】正文第1段", s)

    def test_mark_span(self):
        from pycbeta.verify import _mark_span
        self.assertEqual(_mark_span("甲乙", 1, 1), "甲〖〗乙")
        self.assertEqual(_mark_span("甲X乙", 1, 2), "甲〖X〗乙")
        self.assertEqual(_mark_span("", 0, 0), "〖〗")
        # pad>0 且 span 为空：填对端长度的 〓，两行对齐
        self.assertEqual(_mark_span("甲乙", 1, 1, pad=1), "甲〖〓〗乙")
        self.assertEqual(_mark_span("甲乙", 1, 1, pad=3), "甲〖〓〓〓〗乙")
        self.assertEqual(_mark_span("甲X乙", 1, 2, pad=5), "甲〖X〗乙")

    def test_mark_span_caps(self):
        """差异段/补位上限（2026-10-14 用户确认：50 字 / 10 个〓）——
        治报告写入巨量原文（T1579 报告 5.8MB、单行 54 万字符实锤）。"""
        from pycbeta.verify import _mark_span
        # 差异段 >50 字：截断 + `…`
        out = _mark_span("前" + "甲" * 500 + "后", 1, 501)
        self.assertEqual(out, "前〖" + "甲" * 50 + "…〗后")
        # 恰好 50 字：不截断
        out2 = _mark_span("前" + "甲" * 50 + "后", 1, 51)
        self.assertEqual(out2, "前〖" + "甲" * 50 + "〗后")
        # 补位 >10 个：封顶 10 个 + `…`
        self.assertEqual(_mark_span("甲乙", 1, 1, pad=999999),
                         "甲〖" + "〓" * 10 + "…〗乙")
        # 恰好 10 个：不截
        self.assertEqual(_mark_span("甲乙", 1, 1, pad=10),
                         "甲〖" + "〓" * 10 + "〗乙")

    def test_report_line_length_bounded(self):
        """报告行长度有界：巨长差异段不得再写入报告（真值回归）。"""
        from pycbeta.verify import _format_verify_record
        rec = {"xml": "x.xml", "fmt": "txt", "status": "fail",
               "missing": 99999, "extra": 0,
               "trials": [{"kind": "txt_notes", "official": "o.txt",
                           "missing": 99999, "extra": 0, "total": 99999,
                           "ok": False, "ctx": [("replace", 0, 99999, 0, 99999)],
                           "ctx_loc": [], "norm_official": "乙" * 100000,
                           "norm_gen": "甲" * 100000}]}
        lines = _format_verify_record(rec, 5, 10)
        longest = max(len(L) for L in lines)
        self.assertLess(longest, 400, f"报告行最长 {longest} 字符，应远小于原文长度")


class TestDocxStructureGuard(unittest.TestCase):
    """结构护栏：docx 段中段/表中段 → 判结构非法（防文字抽取假绿）。"""

    def test_nested_paragraph_detected(self):
        from pycbeta.verify import _nested_block_hits
        self.assertEqual(len(_nested_block_hits(
            "<w:body><w:p><w:p>x</w:p></w:p></w:body>")), 1)
        self.assertEqual(len(_nested_block_hits(
            "<w:body><w:p><w:r/><w:tbl/></w:p></w:body>")), 1)

    def test_clean_and_table_cell_ok(self):
        from pycbeta.verify import _nested_block_hits
        self.assertEqual(_nested_block_hits("<w:body><w:p>a</w:p><w:p>b</w:p></w:body>"), [])
        # 表格单元格内的 <w:p> 合法（tbl 在 p 外）
        self.assertEqual(_nested_block_hits(
            "<w:body><w:tbl><w:tr><w:tc><w:p>a</w:p></w:tc></w:tr></w:tbl></w:body>"), [])
        # <w:pPr>/<w:pict> 不误判
        self.assertEqual(_nested_block_hits("<w:p><w:pPr><w:pict/></w:pPr></w:p>"), [])

    def test_docx_nested_block_violations_zip(self):
        import zipfile
        from pycbeta.verify import docx_nested_block_violations
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "bad.docx")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("word/document.xml",
                           "<w:body><w:p><w:p>x</w:p></w:p></w:body>")
            hits = docx_nested_block_violations(p)
            self.assertTrue(hits)
            self.assertTrue(hits[0].startswith("word/document.xml:"))
            self.assertEqual(docx_nested_block_violations(
                os.path.join(d, "missing.docx")), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_loose_text_run_detected(self):
        """游离 run（`<w:p>` 外的非空文字 run）判非法（Word 丢弃＝假绿）。"""
        from pycbeta.verify import _loose_run_hits
        self.assertEqual(len(_loose_run_hits(
            "<w:body><w:p><w:r><w:t>正文</w:t></w:r></w:p>"
            "<w:r><w:t>游离</w:t></w:r></w:body>")), 1)
        # 段内 run 正常；空文字游离 run（标题页占位）不报
        self.assertEqual(_loose_run_hits(
            "<w:body><w:p><w:r><w:t>正文</w:t></w:r></w:p></w:body>"), [])
        self.assertEqual(_loose_run_hits(
            "<w:body><w:r><w:t></w:t></w:r></w:body>"), [])
        # 表格单元格内段落里的 run 正常
        self.assertEqual(_loose_run_hits(
            "<w:body><w:tbl><w:tr><w:tc><w:p>"
            "<w:r><w:t>格</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body>"), [])

    def test_docx_loose_run_violations_zip(self):
        import zipfile
        from pycbeta.verify import docx_nested_block_violations
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "loose.docx")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("word/document.xml",
                           "<w:body><w:r><w:t>游离</w:t></w:r></w:body>")
            hits = docx_nested_block_violations(p)
            self.assertTrue(hits)
            self.assertIn("游离文字", hits[0])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_report_prints_struct_issue(self):
        from pycbeta.verify import format_verify_report
        recs = [{"xml": "X.xml", "fmt": "docx", "status": "fail",
                 "gen": "X.docx", "missing": 0, "extra": 0, "total": 0,
                 "ctx": [], "struct_issues": ["word/document.xml: <w:p><w:p>x"]}]
        s = "\n".join(format_verify_report(recs))
        self.assertIn("结构非法", s)
        self.assertIn("段中段/表中段/游离文字 1 处", s)


class TestExtractDocxLineBreaks(unittest.TestCase):
    """docx 抽取保留行内 <w:br/>：同段目录/偈颂分行不连成一行
    （TX01n0001 类 <p cb:type="pre"> 目录每 <lb/> 一行）。"""

    def _mk(self, d, docxml, fnxml=None):
        import zipfile
        p = os.path.join(d, "t.docx")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("word/document.xml",
                       "<w:document><w:body>" + docxml + "</w:body></w:document>")
            if fnxml is not None:
                z.writestr("word/footnotes.xml", fnxml)
        return p

    def test_br_splits_lines(self):
        from pycbeta.verify import extract_text
        d = tempfile.mkdtemp()
        try:
            p = self._mk(d, "<w:p><w:t>甲乙</w:t><w:br/>"
                            "<w:t>丙丁</w:t></w:p>")
            lines = extract_text(p).split("\n")
            self.assertIn("甲乙", lines)
            self.assertIn("丙丁", lines)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_typed_br_and_footnotes(self):
        from pycbeta.verify import extract_text
        d = tempfile.mkdtemp()
        try:
            p = self._mk(d, "<w:p><w:t>正文</w:t></w:p>",
                         "<w:footnotes><w:p><w:t>注一</w:t>"
                         "<w:br w:type=\"textWrapping\"/><w:t>注二</w:t></w:p>"
                         "</w:footnotes>")
            lines = extract_text(p).split("\n")
            self.assertIn("注一", lines)
            self.assertIn("注二", lines)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestDocxStripQuotedGt(unittest.TestCase):
    """剥标签识引号：属性值里的 `>` 不得提前截断标签、留下 `"/>` 残渣
    （2026-10-16：T1585 目录文字自带 `>`，书签名 w:name="㊀問起>" 致校验假差异）。"""

    def test_tag_with_gt_in_quoted_attr(self):
        from pycbeta.verify import _TAG_RE
        xml = '<w:bookmarkStart w:id="1" w:name="㊀問起>"/><w:t>甲</w:t>'
        self.assertEqual(_TAG_RE.sub("", xml), "甲")

    def test_extract_docx_bookmark_gt_name(self):
        from pycbeta.verify import extract_text
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "t.docx")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("word/document.xml",
                           "<w:document><w:body><w:p>"
                           "<w:r><w:t>成唯識論卷第十</w:t></w:r>"
                           '<w:bookmarkStart w:id="1" w:name="㊀問起>"/>'
                           '<w:bookmarkEnd w:id="1"/></w:p></w:body></w:document>')
            text = extract_text(p)
            self.assertIn("成唯識論卷第十", text)
            self.assertNotIn('"/>', text)
        finally:
            shutil.rmtree(d, ignore_errors=True)


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


class TestVerifyOnePhases(unittest.TestCase):
    """阶段回调（progress）：四阶段按序上报、回调异常不外抛；
    docx 路径回归：`for _p in gen_path` 循环不得遮蔽阶段回调名
    （曾致 `'str' object is not callable`）。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={}, body=[],
                    notes_by_n={}, apps=[], simplified=False)

    def _run(self, progress=None):
        """最小 docx 端到端（无基线）：返回 (rec, phases, tmpdir)。"""
        from unittest import mock
        import pycbeta.verify as V
        d = tempfile.mkdtemp(prefix="vphase-")
        gen = os.path.join(d, "T.docx")
        with zipfile.ZipFile(gen, "w") as z:
            z.writestr("word/document.xml",
                       '<?xml version="1.0"?><w:document xmlns:w="x">'
                       '<w:body><w:p><w:r><w:t>正文甲</w:t></w:r></w:p>'
                       '</w:body></w:document>')
        phases = []
        cb = progress if progress is not None else phases.append
        with mock.patch.object(V, "P5Parser") as P, \
                mock.patch.object(V, "generate_formal", return_value=[gen]), \
                mock.patch.object(V, "load_effective_presets",
                                  return_value={"verify": {"auto_fetch": False}}), \
                mock.patch.object(V, "find_official", return_value=[]):
            P.return_value.parse.return_value = self._work()
            rec = V.verify_one("x.xml", "docx", d, os.path.join(d, "v"),
                               progress=cb)
        return rec, phases, d

    def test_docx_path_reports_phases(self):
        rec, phases, d = self._run()
        try:
            self.assertEqual(rec["status"], "no_baseline")
            self.assertIn("生成比对档", phases)
            self.assertIn("抽取归一", phases)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_progress_exception_swallowed(self):
        def boom(_ph):
            raise RuntimeError("cb-fail")
        rec, _phases, d = self._run(progress=boom)
        try:
            self.assertEqual(rec["status"], "no_baseline")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestEpubTrialBodyOnly(unittest.TestCase):
    """epub 基线试算只比**正文段**：官方 epub 导出无尾注/校勘块（note-inline 内联；
    全库官方 epub footnote 块=0），全量比对会把我们的尾注整块记为"多"
    （2026-10-13 T1499 实锤：多 137 字）。注释由 txt_notes 试算覆盖。"""

    @staticmethod
    def _mk_epub(path, body, foot=None):
        import zipfile
        html = ("<html><body><p>" + body + "</p>"
                + (f"<div class='footnote' id='n1'>"
                   f"<a href='#note_anchor_1' id='a1'>[1]</a> {foot}</div>"
                   if foot else "")
                + "</body></html>")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("OEBPS/ch1.xhtml", html)

    def test_epub_trial_excludes_our_notes(self):
        import tempfile
        from unittest import mock
        from pycbeta.model import Work
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        gen = os.path.join(d, "X.epub")
        off = os.path.join(d, "off.epub")
        txt = os.path.join(d, "X_001.txt")
        self._mk_epub(gen, "正文甲", "校勘注乙")   # 我们：有尾注
        self._mk_epub(off, "正文甲")               # 官方：无尾注
        with open(txt, "w", encoding="utf-8") as f:
            f.write("正文甲\n")                    # 官方 txt 无注 → txt 试算失败
        work = Work(id="X", source_file="", metadata={}, body=[],
                    notes_by_n={}, apps=[], simplified=False)

        def _find(source, stem, kind, juan=None, extra_roots=(),
                  strict_juan=False):
            return {"txt_notes": [txt], "epub": [off]}.get(kind, [])

        with mock.patch.object(V, "P5Parser") as P, \
                mock.patch.object(V, "generate_formal", return_value=[gen]), \
                mock.patch.object(V, "load_effective_presets",
                                  return_value={"verify": {"auto_fetch": False}}), \
                mock.patch.object(V, "find_official", side_effect=_find):
            P.return_value.parse.return_value = work
            rec = V.verify_one("x.xml", "epub", d, os.path.join(d, "v"),
                               max_diff=0)
        trials = {t["kind"]: t for t in rec.get("trials", [])}
        self.assertIn("txt_notes", trials)
        self.assertIn("epub", trials)
        # txt 试算：epub→txt 形含注块 → 官方 txt 无注 → 长度差 > 0；
        # 长度门（max_diff=0）直接截断，缺/多为 None（不再跑整篇比对）
        self.assertTrue(trials["txt_notes"].get("truncated"))
        self.assertGreater(trials["txt_notes"].get("length_diff") or 0, 0)
        # epub 试算：只比正文段 → 0/0（尾注不计）
        self.assertEqual((trials["epub"]["missing"], trials["epub"]["extra"]),
                         (0, 0))
        self.assertEqual(rec["status"], "ok")


class TestFormatDuration(unittest.TestCase):
    """耗时格式化 + 报告段首行带耗时（2026-10-14 用户反馈：弹窗与报告都写）。"""

    def test_format_duration(self):
        from pycbeta.verify import format_duration as fd
        self.assertEqual(fd(0), "0.0s")
        self.assertEqual(fd(12.34), "12.3s")
        self.assertEqual(fd(59.99), "1 分 00 秒")     # 四舍五入到分
        self.assertEqual(fd(65), "1 分 05 秒")
        self.assertEqual(fd(3661), "1 小时 01 分")
        self.assertEqual(fd(None), "")
        self.assertEqual(fd("x"), "")
        self.assertEqual(fd(-1), "")

    def test_report_header_has_durations(self):
        from pycbeta.verify import _format_verify_record
        rec = {"xml": "T.xml", "fmt": "txt", "status": "ok", "missing": 0,
               "extra": 0, "render_sec": 3.24, "verify_sec": 65.0,
               "trials": [{"kind": "txt_notes", "official": "o.txt",
                           "missing": 0, "extra": 0, "total": 0, "ok": True,
                           "ctx": [], "ctx_loc": []}]}
        first = _format_verify_record(rec, 5, 10)[0]
        self.assertEqual(first, "=== T.xml　生成 3.2s　校验 1 分 05 秒")

    def test_report_header_without_durations_unchanged(self):
        from pycbeta.verify import _format_verify_record
        rec = {"xml": "T.xml", "fmt": "txt", "status": "ok", "missing": 0,
               "extra": 0,
               "trials": [{"kind": "txt_notes", "official": "o.txt",
                           "missing": 0, "extra": 0, "total": 0, "ok": True,
                           "ctx": [], "ctx_loc": []}]}
        self.assertEqual(_format_verify_record(rec, 5, 10)[0], "=== T.xml")


class TestBaselineCoverage(unittest.TestCase):
    """基线覆盖：卷号区间格式化 + 报告行（2026-10-14 用户反馈）。"""

    def test_format_juan_ranges(self):
        from pycbeta.verify import format_juan_ranges as fj
        self.assertEqual(fj([]), "")
        self.assertEqual(fj(None), "")
        self.assertEqual(fj([3]), "3")
        self.assertEqual(fj([1, 2, 3, 5, 7, 8]), "1-3,5,7-8")
        self.assertEqual(fj([2, 1]), "1-2")

    def _rec(self, cov, ok=True):
        return {"xml": "T.xml", "fmt": "txt",
                "status": "ok" if ok else "fail",
                "missing": 0 if ok else 5, "extra": 0,
                "baseline_coverage": cov,
                "trials": [{"kind": "txt_notes", "official": "o.txt",
                            "missing": 0 if ok else 5, "extra": 0,
                            "total": 0 if ok else 5, "ok": ok,
                            "ctx": [], "ctx_loc": []}]}

    def test_report_line_when_incomplete(self):
        from pycbeta.verify import _format_verify_record
        s = "\n".join(_format_verify_record(self._rec(
            {"txt_notes": {"have": 2, "expect": 100,
                           "missing": [1, 2, 3, 5]}}, ok=False), 5, 10))
        self.assertIn("基线覆盖：txt_notes 2/100 卷（缺 1-3,5）", s)

    def test_no_line_when_complete(self):
        from pycbeta.verify import _format_verify_record
        s = "\n".join(_format_verify_record(self._rec(
            {"txt_notes": {"have": 100, "expect": 100, "missing": []}}),
            5, 10))
        self.assertNotIn("基线覆盖", s)


class TestHeadNoTokenAlwaysStripped(unittest.TestCase):
    """行首 head/No. 令牌：校验恒剥、两侧同剥（2026-10-14 用户确认）——
    与 output.strip_head_no 开关解耦；官方侧 No. 头不再卡住公共前缀
    （T1579 html 10 秒 vs 约 1 小时 的脆弱点即来自此）。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="",
                    metadata={"docNumber": "No. 1579"}, body=[],
                    notes_by_n={}, apps=[], simplified=False)

    def _rec(self, switch_on, ours_text, off_text):
        import json as _json
        from unittest import mock
        import pycbeta.verify as V
        d = tempfile.mkdtemp()
        try:
            gen = os.path.join(d, "T.txt")
            with open(gen, "w", encoding="utf-8") as f:
                f.write(ours_text)
            off = os.path.join(d, "off.txt")
            with open(off, "w", encoding="utf-8") as f:
                f.write(off_text)
            cfgp = os.path.join(d, "cfg.json")
            with open(cfgp, "w", encoding="utf-8") as f:
                _json.dump({"output": {"strip_head_no": switch_on}}, f)
            with mock.patch.object(V, "P5Parser") as P, \
                    mock.patch.object(
                        V, "find_official",
                        side_effect=lambda s, st, k, juan=None, **kw:
                        [off] if k == "txt_notes" else []):
                P.return_value.parse.return_value = self._work()
                return V.verify_one("x.xml", "txt", d, os.path.join(d, "v"),
                                    config_path=cfgp, max_diff=10,
                                    gen_paths=[gen])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_official_token_stripped_when_switch_off(self):
        """开关关、我方产物无令牌、官方有令牌 ⇒ 官方令牌仍被剥 ⇒ 0/0。"""
        rec = self._rec(False, "瑜伽師地論卷第一\n正文甲\n",
                        "No. 1579 瑜伽師地論卷第一\n正文甲\n")
        self.assertEqual((rec.get("missing"), rec.get("extra")), (0, 0))

    def test_both_sides_stripped_when_switch_off(self):
        """开关关、两侧都有令牌 ⇒ 两侧同剥（不会把我方令牌算成"多"）。"""
        rec = self._rec(False, "No. 1579 瑜伽師地論卷第一\n正文甲\n",
                        "No. 1579 瑜伽師地論卷第一\n正文甲\n")
        self.assertEqual((rec.get("missing"), rec.get("extra")), (0, 0))


if __name__ == "__main__":
    unittest.main()
