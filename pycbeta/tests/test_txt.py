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

    def test_footnote_markers_match_endnotes(self):
        ref = NoteRef(n="n1", notes=[_note("甲本作乙", "orig"), _note("乙本作甲", "mod")])
        body = [E(tag="p", attrs={}, children=[Text(text="正文"), ref])]
        r = TxtRenderer()
        out = r.render_work(_work(body, {"n1": ref.notes}), tempfile.mkdtemp(), "t.txt")
        with open(out, encoding="utf-8") as f:
            t = f.read()
        # mod 优先单选；正文 [1] ↔ 文末 [1] 内容一一对应
        self.assertIn("正文[1]", t)
        self.assertIn("[1] 乙本作甲", t)
        self.assertNotIn("甲本作乙", t)
        self.assertLess(t.find("正文[1]"), t.find("[1] 乙本作甲"))

    def test_show_notes_off_no_marker_no_note(self):
        ref = NoteRef(n="n1", notes=[_note("小注", "mod")])
        body = [E(tag="p", attrs={}, children=[Text(text="正文"), ref])]
        out = TxtRenderer(show_notes=False).render_work(
            _work(body, {"n1": ref.notes}), tempfile.mkdtemp(), "t.txt")
        with open(out, encoding="utf-8") as f:
            t = f.read()
        self.assertNotIn("[1]", t)
        self.assertNotIn("小注", t)

    def test_rj_no_roman_uses_diamond(self):
        # 无法表示的悉昙字（无 roman）→ 官方同款占位 ◇；有声读声
        work = _work([E(tag="p", attrs={}, children=[
            Gaiji(code="RJ-E046", char="X"), Gaiji(code="RJ-CCEB", char="Y")])])
        work.metadata["charDecl"] = {"RJ-E046": {"rjchar": "誆"},
                                     "RJ-CCEB": {"roman": "raṃ"}}
        r = TxtRenderer()
        r._work = work
        t = r._render_node(work.body[0])
        self.assertIn("\u25c7", t)
        self.assertIn("raṃ", t)

    def test_note_inside_tt_keeps_reading(self):
        # 逐字咒文表内的 NoteRef：注内容不受 _drop_sa 影响，读数照常
        note = Note(tag="note", attrs={}, n="n1", ntype="add", place="foot",
                    children=[Gaiji(code="RJ-CCEB", char="Y"),
                              Text(text="【CB】，"),
                              Gaiji(code="RJ-E046", char="X"),
                              Text(text="【卍續】")])
        tt = E(tag="tt", attrs={}, children=[
            E(tag="t", attrs={"xml:lang": "zh-Hant"}, children=[Text(text="南")]),
            E(tag="t", attrs={"xml:lang": "sa-x-rj"},
              children=[NoteRef(n="n1", notes=[note])])])
        work = _work([E(tag="p", attrs={"cb:type": "dharani"}, children=[tt])],
                     {"n1": [note]})
        work.metadata["charDecl"] = {"RJ-CCEB": {"roman": "raṃ"},
                                     "RJ-E046": {"rjchar": "誆"}}
        out = TxtRenderer().render_work(work, tempfile.mkdtemp(), "t.txt")
        with open(out, encoding="utf-8") as f:
            t = f.read()
        self.assertIn("[1]", t)                      # 正文标记
        self.assertIn("[1] raṃ【CB】，\u25c7【卍續】", t)  # 注内读数/占位都在
        self.assertNotIn("[1] 【CB】【卍續】", t)

    def test_inline_brackets(self):
        ref = NoteRef(n="n1", notes=[_note("小注", "mod")])
        body = [E(tag="p", attrs={}, children=[Text(text="正文"), ref])]
        t = TxtRenderer(notes="inline", inline_brackets="halfwidth")._render_node(
            E(tag="p", attrs={}, children=[Text(text="正文"), ref]))
        self.assertIn("(小注)", t)
        t2 = TxtRenderer(notes="inline")._render_node(
            E(tag="p", attrs={}, children=[Text(text="正文"), ref]))
        self.assertIn("（小注）", t2)

    def test_note_inline_brackets_independent(self):
        # 校注内联用 note_inline_brackets，正文夹注用 inline_brackets，两者独立
        ref = NoteRef(n="n1", notes=[_note("校注", "mod")])
        t = TxtRenderer(notes="inline", inline_brackets="halfwidth",
                        note_inline_brackets="fullwidth")._render_node(
            E(tag="p", attrs={}, children=[Text(text="正文"), ref]))
        self.assertIn("（校注）", t)
        n = Note(tag="note", attrs={}, n="", ntype="", place="inline",
                 children=[Text(text="夾注")])
        t2 = TxtRenderer(inline_brackets="halfwidth",
                         note_inline_brackets="fullwidth")._render_node(n)
        self.assertEqual(t2, "(夾注)")

    def test_show_notes_off_keeps_inline_note(self):
        # 正文夹注（place=inline）属原文，不受注释总开关控制；校注仍隐藏
        n = Note(tag="note", attrs={}, n="", ntype="", place="inline",
                 children=[Text(text="夾注")])
        self.assertIn("夾注", TxtRenderer(show_notes=False)._render_node(n))
        ref = NoteRef(n="n1", notes=[_note("校注", "mod")])
        out = TxtRenderer(show_notes=False)._render_node(
            E(tag="p", attrs={}, children=[Text(text="正文"), ref]))
        self.assertEqual(out.strip(), "正文")
        self.assertNotIn("校注", out)

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

    def test_body_app_without_anchor_lem_only(self):
        # body 内联 app（P5a/P5b）：base 读法只在 lem，主/辅轨只出 lem；
        # rdg 是异读不进正文；无 lem 的 app 落 ""（有锚 app 仍整棵丢）
        text = ("<text><body><p>室可以居<app><lem>几儿</lem>"
                "<rdg>可以</rdg></app>儱</p>"
                "<p>乙<app from=\"#b1\" corresp=\"k9\">异文</app>丙</p></body>"
                "<back></back></text>")
        title, author, body, foots = _extract_xml_parts(_write_tei(text))
        self.assertIn("室可以居几儿儱", body)
        self.assertNotIn("可以儱", body)
        self.assertNotIn("异文", body)
        self.assertEqual(foots, [])


class TestInlineAppLem(unittest.TestCase):
    """正文内联校勘（P5a/P5b）：只出 <lem> base 读法，rdg 变体不进正文。"""

    BODY = ("<text><body>"
            "<p>速疾。<note n=\"n1\" type=\"add\">已【CB】，巳【卍續】</note>"
            "<app n=\"n1\"><lem wit=\"【CB】\">已</lem>"
            "<rdg wit=\"【卍續】\">巳</rdg></app>又語一僧</p>"
            "</body></text>")

    def test_aux_lem_only(self):
        _, _, body, _ = _extract_xml_parts(_write_tei(self.BODY))
        self.assertIn("速疾。已又語一僧", body)
        self.assertNotIn("巳", body)
        self.assertNotIn("【CB】", body)

    def test_txt_md_lem_only(self):
        from pycbeta.parser import P5Parser
        from pycbeta.render_md import MdRenderer
        work = P5Parser().parse(_write_tei(self.BODY))
        tmp = tempfile.mkdtemp()
        t = open(TxtRenderer().render_work(work, tmp, "t.txt"), encoding="utf-8").read()
        m = open(MdRenderer().render_work(work, tmp, "t.md"), encoding="utf-8").read()
        for s in (t, m):
            self.assertIn("速疾。已又語一僧", s)
            self.assertNotIn("巳", s)

    def test_html_lem_only(self):
        from pycbeta.parser import P5Parser
        from pycbeta.render_html import HtmlRenderer
        work = P5Parser().parse(_write_tei(self.BODY))
        tmp = tempfile.mkdtemp()
        files = HtmlRenderer().render_work(work, tmp)
        html = ""
        for p in files:
            fp = p if os.path.isabs(p) else os.path.join(tmp, p)
            html += open(fp, encoding="utf-8").read()
        self.assertIn("已", html)
        self.assertNotIn("巳", html)

    def test_docx_lem_only(self):
        import re as _re
        import zipfile
        from pycbeta.parser import P5Parser
        from pycbeta.render_docx import DocxRenderer
        work = P5Parser().parse(_write_tei(self.BODY))
        fn = DocxRenderer().render_work(work, tempfile.mkdtemp())
        z = zipfile.ZipFile(fn)
        doc = z.read("word/document.xml").decode("utf-8")
        z.close()
        txt = "".join(_re.findall(r"<w:t[^>]*>([^<]*)</w:t>", doc))
        self.assertIn("已", txt)
        self.assertNotIn("巳", txt)


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


class TestStripHeadNo(unittest.TestCase):
    def test_txt_head(self):
        body = [E(tag="head", attrs={}, children=[Text(text="No. 1116-B"),
                                                  Text(text=" 序")])]
        t = TxtRenderer(strip_head_no=True)._render_node(body[0])
        self.assertNotIn("No. 1116", t)
        self.assertIn("序", t)
        t2 = TxtRenderer()._render_node(body[0])
        self.assertIn("No.1116-B", t2)  # txt 归一化无空格；默认保留令牌


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


class TestSgAndSiddhamTxt(unittest.TestCase):
    """<cb:sg> 半角括号 + 悉昙裸读音（官方 txt 同款）。"""

    TEI = """<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt>
<title level="m" xml:lang="zh-Hant">測試經</title>
<author>譯者</author>
</titleStmt></fileDesc>
<encodingDesc><charDecl>
<char xml:id="RJ-CCEB">
<charProp><localName>rjchar</localName><value>歾</value></charProp>
<charProp><localName>Romanized form in Unicode transcription</localName><value>raṃ</value></charProp>
<mapping cb:dec="1101035" type="PUA">U+10CCEB</mapping>
</char>
</charDecl></encodingDesc></teiHeader>
<text><body>
<p>唵<cb:yin><cb:zi>㘕</cb:zi><cb:sg>音注</cb:sg></cb:yin>抮</p>
<p>淨法界<g ref="#RJ-CCEB">X</g>字</p>
</body></text></TEI>"""

    def _work(self):
        from pycbeta.parser import P5Parser
        d = tempfile.mkdtemp()
        p = os.path.join(d, "T9999.xml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.TEI)
        self.addCleanup(__import__("shutil").rmtree, d, True)
        return P5Parser().parse(p), p

    def test_sg_parens(self):
        from pycbeta.render_md import MdRenderer
        work, _ = self._work()
        tmp = tempfile.mkdtemp()
        t = open(TxtRenderer().render_work(work, tmp, "t.txt"),
                 encoding="utf-8").read()
        m = open(MdRenderer().render_work(work, tmp, "t.md"),
                 encoding="utf-8").read()
        for s in (t, m):
            self.assertIn("唵㘕(音注)抮", s)

    def test_bare_reading(self):
        from pycbeta.render_md import MdRenderer
        work, _ = self._work()
        tmp = tempfile.mkdtemp()
        t = open(TxtRenderer().render_work(work, tmp, "t.txt"),
                 encoding="utf-8").read()
        m = open(MdRenderer().render_work(work, tmp, "t.md"),
                 encoding="utf-8").read()
        for s in (t, m):
            self.assertIn("淨法界raṃ字", s)
            self.assertNotIn("歾", s)

    def test_aux_bare_reading(self):
        _, xml = self._work()
        _, _, body, _ = _extract_xml_parts(xml)
        self.assertIn("淨法界raṃ字", body)
        self.assertNotIn("歾", body)


class TestFigureMark(unittest.TestCase):
    """图注：txt/md 出官方同款【圖：<文件名>】；docx/html 不出文字；aux 镜像。"""

    BODY = ("<text><body>"
            "<p>文前</p>"
            "<figure><graphic url=\"../figures/X/X59p01.gif\"/></figure>"
            "<p>文後</p>"
            "</body></text>")

    def test_txt_md_mark(self):
        from pycbeta.parser import P5Parser
        from pycbeta.render_md import MdRenderer
        work = P5Parser().parse(_write_tei(self.BODY))
        tmp = tempfile.mkdtemp()
        t = open(TxtRenderer().render_work(work, tmp, "t.txt"),
                 encoding="utf-8").read()
        m = open(MdRenderer().render_work(work, tmp, "t.md"),
                 encoding="utf-8").read()
        for s in (t, m):
            self.assertIn("【圖：X59p01.gif】", s)
            self.assertLess(s.find("文前"), s.find("【圖"))
            self.assertLess(s.find("【圖"), s.find("文後"))

    def test_aux_mark(self):
        _, _, body, _ = _extract_xml_parts(_write_tei(self.BODY))
        self.assertIn("【圖：X59p01.gif】", body)

    def test_normalize_keeps_figure_drops_witness(self):
        from pycbeta.verify import normalize
        s = normalize("甲【CB】乙【圖：X59p0224_01.gif】丙")
        self.assertNotIn("【CB】", s)
        self.assertIn("【圖：X59p0224_01.gif】", s)

    def test_normalize_strips_own_annotations(self):
        # 我方注音〔〕（注音表/自动注音所加）参与比对前剥除
        from pycbeta.verify import normalize
        s = normalize("涅槃〔niè pán〕入三昧")
        self.assertNotIn("〔", s)
        self.assertIn("涅槃入三昧", s)


class TestDharaniTransliteration(unittest.TestCase):
    """逐字咒文表（无 place="inline"）转写默认不显示；place="inline" 与散文照常。"""

    TEI = """<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt>
<title level="m" xml:lang="zh-Hant">測試經</title>
<author>譯者</author>
</titleStmt></fileDesc>
<encodingDesc><charDecl>
<char xml:id="RJ-CCEB">
<charProp><localName>rjchar</localName><value>歾</value></charProp>
<charProp><localName>Romanized form in Unicode transcription</localName><value>raṃ</value></charProp>
<mapping cb:dec="1101035" type="PUA">U+10CCEB</mapping>
</char>
</charDecl></encodingDesc></teiHeader>
<text><body>
<p cb:type="dharani"><cb:tt><cb:t xml:lang="zh-Hant">南</cb:t><cb:t xml:lang="sa-x-rj"><g ref="#RJ-CCEB">X</g></cb:t></cb:tt></p>
<p cb:type="dharani"><cb:tt place="inline"><cb:t xml:lang="zh-Hant">唵</cb:t><cb:t xml:lang="sa-x-rj"><g ref="#RJ-CCEB">X</g></cb:t></cb:tt></p>
<p>散文<g ref="#RJ-CCEB">X</g>末</p>
</body></text></TEI>"""

    def _work(self):
        from pycbeta.parser import P5Parser
        d = tempfile.mkdtemp()
        p = os.path.join(d, "T9999.xml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.TEI)
        self.addCleanup(__import__("shutil").rmtree, d, True)
        return P5Parser().parse(p), p

    def test_txt_drops_plain_keeps_inline(self):
        work, _ = self._work()
        t = open(TxtRenderer().render_work(work, tempfile.mkdtemp(), "t.txt"),
                 encoding="utf-8").read()
        self.assertIn("南", t)             # 逐字表中文行保留
        self.assertNotIn("南raṃ", t)       # 逐字表转写丢弃
        self.assertIn("唵raṃ", t)          # place=inline 转写保留
        self.assertIn("散文raṃ末", t)      # 散文缺字读音保留

    def test_txt_shows_when_enabled(self):
        work, _ = self._work()
        t = open(TxtRenderer(show_dharani_transliteration=True).render_work(
            work, tempfile.mkdtemp(), "t.txt"), encoding="utf-8").read()
        self.assertIn("南raṃ", t)

    def test_md_matches_txt(self):
        from pycbeta.render_md import MdRenderer
        work, _ = self._work()
        m = open(MdRenderer().render_work(work, tempfile.mkdtemp(), "t.md"),
                 encoding="utf-8").read()
        self.assertIn("南", m)
        self.assertNotIn("南raṃ", m)
        self.assertIn("唵raṃ", m)

    def test_aux_matches_txt(self):
        _, xml = self._work()
        _, _, body, _ = _extract_xml_parts(xml)
        self.assertIn("南", body)
        self.assertNotIn("南raṃ", body)
        self.assertIn("唵raṃ", body)
        _, _, body2, _ = _extract_xml_parts(
            xml, show_dharani_transliteration=True)
        self.assertIn("南raṃ", body2)


if __name__ == "__main__":
    unittest.main()
