import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.model import App, Gaiji, Note, NoteRef, Text
from pycbeta.parser import P5Parser

from pycbeta.tests._data import DATA_ROOT as CBETA
from pycbeta.tests._data import requires_data


def iter_nodes(nodes):
    for n in nodes:
        yield n
        if isinstance(n, App):
            if n.lem is not None:
                yield from iter_nodes([n.lem])
            yield from iter_nodes(n.rdgs)
        if getattr(n, "children", None):
            yield from iter_nodes(n.children)


def all_of(work, cls):
    return [n for n in iter_nodes(work.body) if isinstance(n, cls)]


class TestCharDeclRjchar(unittest.TestCase):
    """charDecl 收录 rjchar（悉昙显示用字；范本用 sample.xml 内联 XML 避免路径依赖）。"""

    def test_rjchar_captured(self):
        xml = ("<TEI xmlns='http://www.tei-c.org/ns/1.0'>"
               "<teiHeader><encodingDesc><charDecl>"
               "<char xml:id='RJ-T'><charProp><localName>rjchar</localName>"
               "<value>屇</value></charProp>"
               "<mapping type='PUA'>U+10CCBA</mapping></char>"
               "</charDecl></encodingDesc></teiHeader>"
               "<text><body><p>文</p></body></text></TEI>")
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                         encoding="utf-8") as f:
            f.write(xml)
            fn = f.name
        try:
            w = P5Parser().parse(fn)
        finally:
            os.remove(fn)
        self.assertEqual((w.metadata.get("charDecl") or {}).get("RJ-T"),
                         {"rjchar": "屇", "pua": "U+10CCBA"})


@requires_data
class TestT0349(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fn = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.w = P5Parser().parse(fn)

    def test_work_id(self):
        self.assertEqual(self.w.id, "T0349")

    def test_metadata(self):
        md = self.w.metadata
        self.assertIn("彌勒", md.get("title", ""))
        self.assertIn("竺法護", md.get("author", ""))
        self.assertEqual(md.get("publication_date"), "2025-01-30 01:37:50 +0800")

    def test_notes(self):
        notes = self.w.notes_by_n
        self.assertEqual(sum(len(v) for v in notes.values()), 96)
        orig = [n for grp in notes.values() for n in grp if n.ntype == "orig"]
        mod = [n for grp in notes.values() for n in grp if n.ntype == "mod"]
        self.assertEqual(len(orig), 48)
        self.assertEqual(len(mod), 48)

    def test_resp_resolved(self):
        notes = [n for grp in self.w.notes_by_n.values() for n in grp]
        taisho = [n for n in notes if n.ntype == "orig"]
        self.assertNotIn("#resp", taisho[0].resp or "")
        self.assertEqual(taisho[0].resp, "Taisho")

    def test_apps_wit_resolved(self):
        apps = self.w.apps
        self.assertTrue(len(apps) > 0)
        resolved = [a for a in apps if a.lem and any("【" in w for w in a.lem.wit)]
        self.assertTrue(len(resolved) > 0)
        self.assertNotIn("#wit", resolved[0].lem.wit[0])

    def test_backfill(self):
        refs = all_of(self.w, NoteRef)
        self.assertTrue(len(refs) > 0)
        self.assertTrue(all(r.notes for r in refs if r.n in self.w.notes_by_n))

    def test_body_text(self):
        text = "".join(n.text for n in all_of(self.w, Text))
        self.assertIn("彌勒", text)
        self.assertTrue(len(text) > 1000)


@requires_data
class TestX1116(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fn = os.path.join(CBETA, "X1116 毗尼日用切要香乳記", "X60n1116.xml")
        cls.w = P5Parser().parse(fn)

    def test_work_id(self):
        self.assertEqual(self.w.id, "X1116")

    def test_witness(self):
        self.assertTrue(any(a.lem and any("【" in w for w in a.lem.wit) for a in self.w.apps))

    def test_notes(self):
        total = sum(len(v) for v in self.w.notes_by_n.values())
        self.assertTrue(total >= 90)

    def test_gaiji(self):
        gaijis = all_of(self.w, Gaiji)
        self.assertTrue(len(gaijis) > 0)
        self.assertTrue(all(g.char for g in gaijis), "P5 <g> should carry char content")


@requires_data
class TestT0452(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fn = os.path.join(CBETA, "T0452 佛說觀彌勒菩薩上生兜率天經", "T14n0452.xml")
        cls.w = P5Parser().parse(fn)

    def test_work_id(self):
        self.assertEqual(self.w.id, "T0452")

    def test_corr_cbeta_ranges(self):
        # 4 处 CBETA 校改（弗/梨/掁/頗）→ corr-cbeta 节点；orig 读法不包
        corr = [n for n in iter_nodes(self.w.body)
                if getattr(n, "tag", "") == "corr-cbeta"]
        self.assertEqual(len(corr), 4)
        marked = "".join(
            getattr(c, "text", "") or "" for x in corr for c in x.children)
        self.assertEqual(marked, "弗梨掁頗")


class TestCorrCbetaParse(unittest.TestCase):
    """合成：lem 原始 wit 含 #wit.cbeta → 包 corr-cbeta；orig 不包。"""

    XML = ("<TEI xmlns='http://www.tei-c.org/ns/1.0'>"
           "<teiHeader><fileDesc><titleStmt><title>t</title>"
           "</titleStmt></fileDesc></teiHeader>"
           "<text><body><p>甲"
           "<anchor xml:id='beg0001' n='0001'/>弗<anchor xml:id='end0001'/>乙"
           "<anchor xml:id='beg0002' n='0002'/>佛<anchor xml:id='end0002'/>丙"
           "</p></body><back>"
           "<app from='#beg0001' to='#end0001'>"
           "<lem wit='#wit.cbeta'>弗</lem><rdg wit='#wit.orig'>佛</rdg></app>"
           "<app from='#beg0002' to='#end0002'>"
           "<lem wit='#wit.orig'>佛</lem><rdg wit='#wit.cbeta'>弗</rdg></app>"
           "</back></text></TEI>")

    def _parse(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                         encoding="utf-8") as f:
            f.write(self.XML)
            fn = f.name
        try:
            return P5Parser().parse(fn)
        finally:
            os.remove(fn)

    def test_only_cbeta_lem_wrapped(self):
        w = self._parse()
        corr = [n for n in iter_nodes(w.body)
                if getattr(n, "tag", "") == "corr-cbeta"]
        self.assertEqual(len(corr), 1)
        self.assertEqual("".join(getattr(c, "text", "") or ""
                                 for c in corr[0].children), "弗")
        # 未改字的正文「佛」仍在，且不在 corr 内
        body_text = "".join(getattr(n, "text", "") or ""
                            for n in iter_nodes(w.body)
                            if isinstance(n, Text))
        self.assertIn("佛", body_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
