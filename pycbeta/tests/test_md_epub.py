import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.render_md import MdRenderer
from pycbeta.render_epub import EpubRenderer

CBETA = r"E:\dev\cbeta\cbeta_ebook"


class TestMd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_md_strip_head_no(self):
        from pycbeta.model import E, Text
        head = E(tag="head", attrs={}, children=[Text(text="No. 1116-B"),
                                                 Text(text=" 序")])
        t = MdRenderer(strip_head_no=True)._render_node(head)
        self.assertNotIn("No. 1116", t)
        self.assertIn("序", t)
        t2 = MdRenderer()._render_node(head)
        self.assertIn("No.1116-B", t2)  # md 归一化无空格；默认保留令牌

    def test_md_docnumber_own_line(self):
        from pycbeta.model import E, Text
        body = [E(tag="docNumber", attrs={}, children=[Text(text="No. 349")]),
                E(tag="juan", attrs={}, children=[
                    E(tag="jhead", attrs={}, children=[Text(text="某經")])])]
        from pycbeta.model import Work
        w = Work(id="T", source_file="", metadata={}, body=body,
                 notes_by_n={}, apps=[], simplified=False)
        text = open(MdRenderer().render_work(w, self.tmp, "n.md"),
                    encoding="utf-8").read()
        self.assertTrue(text.startswith("No.349\n\n## 某經"))

    def test_md(self):
        fn = MdRenderer(notes="endnote").render_work(self.work, self.tmp)
        text = open(fn, encoding="utf-8").read()
        # 卷首不对齐官方 txt：无 `# 书名/作者` 头，直接从 No. 行开始
        self.assertTrue(text.startswith("No."))
        self.assertNotIn("\n# ", text)  # 无一级标题（卷首 `## ` 不计）
        self.assertIn("[^1]", text)
        self.assertIn("[^1]:", text)
        self.assertIn("## 校注", text)

    def test_md_inline(self):
        fn = MdRenderer(notes="inline").render_work(self.work, self.tmp, "i.md")
        text = open(fn, encoding="utf-8").read()
        self.assertNotIn("[^1]", text)
        self.assertIn("（月氏國", text)


class TestEpub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_epub(self):
        fn = EpubRenderer().render_work(self.work, self.tmp)
        z = zipfile.ZipFile(fn)
        names = z.namelist()
        for p in ("mimetype", "META-INF/container.xml", "OEBPS/content.opf",
                  "OEBPS/nav.xhtml", "OEBPS/toc.ncx"):
            self.assertIn(p, names)
        self.assertEqual(z.read("mimetype").decode(), "application/epub+zip")
        ch = [n for n in names if n.endswith(".xhtml") and "ch" in n]
        self.assertTrue(ch)
        xhtml = z.read(ch[0]).decode("utf-8")
        self.assertIn("<body>", xhtml)
        self.assertIn("彌勒", xhtml)
        # 中间 HTML 目录 _epub_tmp 生成后清理，不留残余
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "_epub_tmp")))


class TestEpubMuluSplit(unittest.TestCase):
    """epub 与 docx 同口径分页：level-1 非「卷」mulu 拆 spine 章节（nav 同步），
    标记不残留成品。"""

    def _work(self):
        from pycbeta.model import E, Text, Work
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=[Text("卷首")]),
                          E(tag="mulu", attrs={"level": "1", "type": "其他"},
                            children=[Text("節甲")]),
                          E(tag="p", attrs={}, children=[Text("甲文")]),
                          E(tag="mulu", attrs={"level": "1", "type": "其他"},
                            children=[Text("節乙")]),
                          E(tag="p", attrs={}, children=[Text("乙文")])],
                    notes_by_n={}, apps=[], simplified=False)

    def test_split_spine_by_mulu(self):
        import re
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        fn = EpubRenderer().render_work(self._work(), d)
        z = zipfile.ZipFile(fn)
        ch = sorted(n for n in z.namelist()
                    if n.endswith(".xhtml") and n.startswith("OEBPS/ch"))
        self.assertEqual(len(ch), 3)
        nav = z.read("OEBPS/nav.xhtml").decode("utf-8")
        titles = re.findall(r"<li><a [^>]*>([^<]*)</a>", nav)
        self.assertIn("節甲", titles)
        self.assertIn("節乙", titles)
        blob = "".join(z.read(n).decode("utf-8") for n in ch)
        self.assertNotIn("mulu-break", blob)  # 标记不残留


class TestCorrCbetaRender(unittest.TestCase):
    """corr-cbeta：html 开门控 span.corr；md 始终透明（排除）。"""

    def _work(self):
        from pycbeta.model import E, Text, Work
        return Work(id="T", source_file="",
                    metadata={"title": "t", "author": ""},
                    body=[E(tag="p", attrs={}, children=[
                        Text(text="甲"),
                        E(tag="corr-cbeta", attrs={"n": "1"},
                          children=[Text(text="弗")]),
                        Text(text="乙")])],
                    notes_by_n={}, apps=[], simplified=False)

    def test_html_on_off(self):
        from pycbeta.render_html import HtmlRenderer
        out = {}
        for flag in (False, True):
            d = tempfile.mkdtemp()
            self.addCleanup(__import__("shutil").rmtree, d, True)
            HtmlRenderer(theme=None, notes="endnote",
                         corr_cbeta=flag).render_work(self._work(), d)
            blob = "".join(
                open(os.path.join(d, f), encoding="utf-8").read()
                for f in os.listdir(d) if f.endswith(".html"))
            out[flag] = blob
        self.assertNotIn('class="corr"', out[False])
        self.assertIn('class="corr"', out[True])
        self.assertIn("弗", out[True])

    def test_md_plain(self):
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        fn = MdRenderer(notes="endnote").render_work(self._work(), d)
        text = open(fn, encoding="utf-8").read()
        self.assertIn("弗", text)
        self.assertNotIn("corr", text)


class TestEpubSongCss(unittest.TestCase):
    """epub 字体落实：派生基底 epub_print.css 含繁简正文实规则；成品注入生效。"""

    def _text(self):
        import io
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with io.open(os.path.join(root, "styles", "epub_print.css"),
                      encoding="utf-8") as f:
            return f.read()

    def test_both_lang_rules(self):
        css = self._text()
        self.assertIn('html[lang="zh-Hant"] body', css)
        self.assertIn("PMingLiU", css)  # 繁体明体栈
        self.assertIn('html[lang="zh-Hans"] body', css)
        self.assertIn("SimSun", css)  # 简体宋体栈

    def test_electronic_structure_rules(self):
        # 派生自 pdf_docx 会丢 golden 的电子书结构规则，此处守护三条修复：
        css = self._text()
        self.assertIn("span.footnote { display: block }", css)  # 尾注逐条分行
        self.assertIn("text-indent: 0!important", css)  # 经文资讯首行不缩进
        # 卷名字体：写死字面值（不用 var，阅读器不支持自定义属性），
        # 选择器带 html[lang] 压过 `html[lang] p` 正文规则
        self.assertIn('html[lang="zh-Hant"] p.juan', css)
        self.assertIn('html[lang="zh-Hans"] p.juan', css)
        self.assertIn("標楷體", css)
        self.assertIn("楷体", css)

    def test_copyright_page_break(self):
        # 经文资讯尾页另页（仅 epub_print 定制；官方不另页）
        css = self._text()
        self.assertIn("#cbeta-copyright", css)
        self.assertIn("break-before: page", css)
        self.assertIn("page-break-before: always", css)

    def test_resolve_returns_song_not_golden(self):
        from pycbeta.theme import resolve_html_base_css
        got = resolve_html_base_css({}, None,
                                    std="pycbeta/styles/epub_print.css")
        self.assertIn("SimSun", got)
        self.assertIn("派生：pdf_docx.css 全文止", got)

    def test_epub_embeds_song_rules(self):
        import shutil
        from pycbeta.parser import P5Parser
        from pycbeta.render_epub import EpubRenderer
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        work = P5Parser().parse(xml)
        d = tempfile.mkdtemp()
        try:
            fn = EpubRenderer(base_css=self._text()).render_work(work, d)
            z = zipfile.ZipFile(fn)
            style = z.read("OEBPS/style.css").decode("utf-8")
            self.assertIn("SimSun", style)
            # 样式表须在 manifest 声明、章节用 <link> 引用（否则阅读器不加载）
            opf = z.read("OEBPS/content.opf").decode("utf-8")
            self.assertIn('href="style.css"', opf)
            ch = [n for n in z.namelist() if "/ch" in n and n.endswith(".xhtml")]
            head = z.read(ch[0]).decode("utf-8")
            self.assertIn('href="style.css"', head)
            self.assertIn('lang="zh-Hant"', head)  # 繁体走明体分支
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestEpubCopyrightPage(unittest.TestCase):
    """版权块独立成页：各章抽走去重，spine 末项 copyright.xhtml（必另起一页）。"""

    def test_copyright_split_spine(self):
        import shutil
        from pycbeta.parser import P5Parser
        from pycbeta.render_epub import EpubRenderer
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        work = P5Parser().parse(xml)
        d = tempfile.mkdtemp()
        try:
            fn = EpubRenderer().render_work(work, d)
            z = zipfile.ZipFile(fn)
            self.assertIn("OEBPS/copyright.xhtml", z.namelist())
            opf = z.read("OEBPS/content.opf").decode("utf-8")
            self.assertLess(opf.find('idref="ch1"'), opf.find('idref="copyright"'))
            nav = z.read("OEBPS/nav.xhtml").decode("utf-8")
            self.assertNotIn("copyright", nav)  # 目录只留正文卷
            ch1 = z.read("OEBPS/ch1.xhtml").decode("utf-8")
            self.assertNotIn("cbeta-copyright", ch1)
            cp = z.read("OEBPS/copyright.xhtml").decode("utf-8")
            self.assertIn("cbeta-copyright", cp)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_copyright_dedup_multi_chapter(self):
        from pycbeta.render_epub import EpubRenderer
        div = ("<div id='cbeta-copyright'><p>版</p></div>"
               "<!-- end of cbeta-copyright -->")
        chs = [{"id": "ch1", "file": "ch1.xhtml", "title": "t1",
                "body": "A" + div},
               {"id": "ch2", "file": "ch2.xhtml", "title": "t2",
                "body": "B" + div}]
        rest, cp = EpubRenderer._split_copyright(chs)
        self.assertNotIn("cbeta-copyright", rest[0]["body"])
        self.assertNotIn("cbeta-copyright", rest[1]["body"])
        self.assertEqual(cp["file"], "copyright.xhtml")
        self.assertIn("cbeta-copyright", cp["body"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
