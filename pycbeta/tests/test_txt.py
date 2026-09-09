import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.model import E, Gaiji, Note, NoteRef, Text, Work
from pycbeta.render_txt import TxtRenderer
from pycbeta.verify import _extract_xml_parts, _strip_txt_head, _norm_official_txt, \
    _strip_md_marks


def _work(body, notes_by_n=None, title="測試經", author="譯者"):
    return Work(id="T9999", source_file="", metadata={"title": title, "author": author},
                body=body, notes_by_n=notes_by_n or {}, apps=[], simplified=False)


def _note(text, ntype="mod", place="foot"):
    return Note(tag="note", attrs={}, n="n1", ntype=ntype, place=place,
                children=[Text(text=text)])


class TestTxtRenderer(unittest.TestCase):
    def test_bare_no_markers(self):
        body = [
            E(tag="head", attrs={}, children=[Text(text="序品")]),
            E(tag="p", attrs={}, children=[Text(text="正文")]),
            E(tag="juan", attrs={}, children=[Text(text="卷上")]),
            E(tag="item", attrs={}, children=[Text(text="條目")]),
            E(tag="table", attrs={}, children=[
                E(tag="row", attrs={}, children=[
                    E(tag="cell", attrs={}, children=[Text(text="甲")]),
                    E(tag="cell", attrs={}, children=[Text(text="乙")])])]),
            E(tag="unclear", attrs={}, children=[]),
        ]
        out = TxtRenderer().render_work(_work(body), tempfile.mkdtemp(), "t.txt")
        with open(out, encoding="utf-8") as f:
            t = f.read()
        self.assertIn("序品", t)
        self.assertNotIn("#", t)
        self.assertNotIn("[^", t)
        self.assertNotIn("|", t)
        self.assertNotIn("- 條目", t)
        self.assertIn("甲\t乙", t)
        self.assertIn("□", t)

    def test_footnotes_collected_no_marker(self):
        ref = NoteRef(n="n1", notes=[_note("甲本作乙", "orig"), _note("乙本作甲", "mod")])
        body = [E(tag="p", attrs={}, children=[Text(text="正文"), ref])]
        r = TxtRenderer()
        out = r.render_work(_work(body, {"n1": ref.notes}), tempfile.mkdtemp(), "t.txt")
        with open(out, encoding="utf-8") as f:
            t = f.read()
        # mod 优先单选，文末集中，正文无 [^n] 标记
        self.assertNotIn("[^", t)
        self.assertIn("乙本作甲", t)
        self.assertNotIn("甲本作乙", t)
        self.assertLess(t.find("正文"), t.find("乙本作甲"))

    def test_inline_brackets(self):
        ref = NoteRef(n="n1", notes=[_note("小注", "mod")])
        body = [E(tag="p", attrs={}, children=[Text(text="正文"), ref])]
        t = TxtRenderer(notes="inline", inline_brackets="halfwidth")._render_node(
            E(tag="p", attrs={}, children=[Text(text="正文"), ref]))
        self.assertIn("(小注)", t)
        t2 = TxtRenderer(notes="inline")._render_node(
            E(tag="p", attrs={}, children=[Text(text="正文"), ref]))
        self.assertIn("（小注）", t2)

    def test_gaiji_char_passthrough(self):
        body = [E(tag="p", attrs={}, children=[Gaiji(code="CB00096", char="𤬪")])]
        t = TxtRenderer()._render_node(body[0])
        self.assertIn("𤬪", t)


TEI_HEAD = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt>
<title level="s">大正藏</title>
<title level="m" xml:lang="en">Roman Title</title>
<title level="m" xml:lang="zh-Hant">繁體正題</title>
<author>譯者甲</author>
</titleStmt></fileDesc>
<encodingDesc><charDecl>
<char xml:id="CB9"><charProp><localName>normalized form</localName><value>解</value></charProp>
<mapping type="unicode">U+89E3</mapping></char>
</charDecl></encodingDesc></teiHeader>
{text}
</TEI>"""

TEI_BODY = """<text><body>
<p>正文一<anchor xml:id="nkr_note_1" n="k1"/>正文二<unclear/>正文三<g ref="#CB9"/></p>
<p>行內<note place="inline">小注</note>尾</p>
</body><back>
<note n="k1" type="orig">原本作甲</note>
<note n="k1" type="mod">改本作乙</note>
<note n="k9" type="mod">無人引用</note>
</back></text>"""


def _write_tei(text=TEI_BODY, head_titles=None):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "T9999.xml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(TEI_HEAD.format(text=text))
    return p


class TestExtractXmlParts(unittest.TestCase):
    def test_title_author_rules(self):
        title, author, body, foots = _extract_xml_parts(_write_tei("<text><body><p>文</p></body></text>"))
        # level=m 中文优先（跳过 level=s 与英文 m）
        self.assertEqual(title, "繁體正題")
        self.assertEqual(author, "譯者甲")
        self.assertIn("文", body)
        self.assertEqual(foots, [])

    def test_back_pool_pick_and_order(self):
        title, author, body, foots = _extract_xml_parts(_write_tei())
        # mod 优先单选；k9 无 anchor 引用不进注块
        self.assertEqual(foots, ["改本作乙"])
        self.assertNotIn("原本作甲", "".join(foots))
        self.assertNotIn("無人引用", "".join(foots))
        # 正文无注残留；unclear→□；g 经 charDecl unicode 解析
        self.assertIn("正文一正文二□正文三解", body)
        # 行内注默认全角括号
        self.assertIn("行內（小注）尾", body)

    def test_inline_halfwidth(self):
        title, author, body, foots = _extract_xml_parts(_write_tei(), "halfwidth")
        self.assertIn("行內(小注)尾", body)

    def test_anchor_dedup(self):
        text = ("<text><body><p>甲<anchor xml:id=\"nkr_note_1\" n=\"k1\"/>"
                "乙<anchor xml:id=\"nkr_note_2\" n=\"k1\"/></p></body><back>"
                "<note n=\"k1\" type=\"mod\">注一</note></back></text>")
        title, author, body, foots = _extract_xml_parts(_write_tei(text))
        self.assertEqual(foots, ["注一"])

    def test_app_dropped(self):
        text = ("<text><body><p>甲<anchor xml:id=\"beg1\"/>乙<anchor xml:id=\"end1\"/></p>"
                "</body><back><app from=\"#beg1\"><lem>異文</lem>"
                "<rdg wit=\"#A\">別本</rdg></app></back></text>")
        title, author, body, foots = _extract_xml_parts(_write_tei(text))
        # back 内无 corresp 的 app 整棵丢弃（lem/rdg 不进正文）
        self.assertEqual(body, "甲乙")
        self.assertEqual(foots, [])

    def test_body_app_without_anchor_mirrors_render(self):
        # body 内无 from/corresp 的 app：渲染侧泛型默认分支直吐 lem+rdg 子文本，
        # 抽取侧镜像收子文本（TX0006 碎片形态；有锚 app 仍整棵丢）
        text = ("<text><body><p>室可以居<app><lem>几儿</lem>"
                "<rdg>可以</rdg></app>儱</p>"
                "<p>乙<app from=\"#b1\" corresp=\"k9\">异文</app>丙</p></body>"
                "<back></back></text>")
        title, author, body, foots = _extract_xml_parts(_write_tei(text))
        self.assertIn("室可以居几儿可以儱", body)
        self.assertNotIn("异文", body)
        self.assertEqual(foots, [])


class TestAuxEntry(unittest.TestCase):
    def test_baseline_xml_rejects_other_fmt(self):
        import unittest.mock as mock
        from pycbeta.verify import verify_one
        sample = os.path.join(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "css-presets", "sample.xml")
        d = tempfile.mkdtemp()
        gen = os.path.join(d, "s.md")
        with open(gen, "w", encoding="utf-8") as f:
            f.write("x")
        with mock.patch("pycbeta.verify.generate_formal", return_value=[gen]):
            with self.assertRaises(ValueError):
                verify_one(sample, "md", d, d, baseline="xml")

    def test_no_txt_no_html_fallback(self):
        # txt 不回退：官方只有 html 时直接 no_baseline（不拿 html 凑数）
        import unittest.mock as mock
        from pycbeta.verify import verify_one
        sample = os.path.join(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "css-presets", "sample.xml")
        d = tempfile.mkdtemp()
        gen = os.path.join(d, "s.txt")
        with open(gen, "w", encoding="utf-8") as f:
            f.write("x")
        fake_html = os.path.join(d, "SAMPLE_001.html")
        with open(fake_html, "w", encoding="utf-8") as f:
            f.write("<p>x</p>")
        def _find(source, stem, kind, juan=None):
            return [fake_html] if kind == "html" else []
        with mock.patch("pycbeta.verify.generate_formal", return_value=[gen]), \
                mock.patch("pycbeta.verify.find_official", side_effect=_find), \
                mock.patch("pycbeta.fetch.ensure_baselines", return_value={}):
            r = verify_one(sample, "txt", d, d, t2s=False)
            self.assertEqual(r["status"], "no_baseline")
            self.assertIsNone(r["official"])


class TestOfficialTxtAlign(unittest.TestCase):
    HEAD = ("#----\n#【經文資訊】大正新脩大藏經\n#【版本記錄】2024\n#----\n\n"
            "No. 349 [No. 310(42)]\n後經\n\n西晉[15]月氏國譯\n\n聞如是\n\n"
            "    [15] 月氏國【大】\n")

    def test_strip_head(self):
        self.assertTrue(_strip_txt_head(self.HEAD).startswith("No. 349"))
        self.assertNotIn("經文資訊", _strip_txt_head(self.HEAD))
        # 无版头原样；文中 # 行不动
        self.assertEqual(_strip_txt_head("No. 1\n正文\n# 注释\n"), "No. 1\n正文\n# 注释\n")
        self.assertEqual(_strip_txt_head("正文\n"), "正文\n")

    def test_norm_moves_notes(self):
        out = _norm_official_txt(self.HEAD)
        # 注行挪文末：正文区无注残留，注在尾部
        body, _ = out.split("聞如是")
        self.assertNotIn("[15] 月氏國", body)
        self.assertTrue(out.rstrip().endswith("月氏國【大】"))
        # 无注记行为无操作（除版头外）
        self.assertEqual(_norm_official_txt("No. 1\n正文\n"), "No. 1\n正文\n")

    def test_strip_md_marks(self):
        s = "# 題\n\n文[^16]字\n\n## 校注\n\n[^16]: 輩【大】\n"
        self.assertEqual(_strip_md_marks(s), "# 題\n\n文[^16]字\n\n輩【大】\n")
        # 正文 [^n] 引用不动（归 normalize 通规则）
        self.assertIn("[^16]", _strip_md_marks(s))
        # 无标记原样
        self.assertEqual(_strip_md_marks("正文\n"), "正文\n")


if __name__ == "__main__":
    unittest.main()
