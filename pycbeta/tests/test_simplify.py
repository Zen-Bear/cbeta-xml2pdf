import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.model import Lb, NoteRef, Text
from pycbeta.parser import P5Parser
from pycbeta.simplify import _Converter, simplify_text, simplify_work
from pycbeta.verify import t2s_baseline

CBETA = r"E:\dev\cbeta\cbeta_ebook"


class TestConvertUnit(unittest.TestCase):
    def setUp(self):
        self.cv = _Converter()

    def test_whole_sentence(self):
        t = Text("彌勒菩薩所問本願經")
        self.cv.convert_unit([t])
        self.assertEqual(t.text, "弥勒菩萨所问本愿经")

    def test_phrase_across_lb(self):
        # 乾坤 被行断打断：整句拼接仍按词表 乾坤，不误转 干坤
        a, b = Text("天乾"), Text("坤地")
        self.cv.convert_unit([a, Lb(n="1"), b])
        self.assertEqual(a.text + b.text, "天乾坤地")

    def test_noteref_break(self):
        # 上标注码是停顿：執著 不与其后文字合并成 执著作
        a, b = Text("執著"), Text("作")
        self.cv.convert_unit([a, NoteRef(n="1"), b])
        self.assertEqual(a.text, "执著")
        self.assertEqual(b.text, "作")

    def test_proper_noun_fix(self):
        # 乾闥婆 读 qián，规范保留 乾（t2s 泛化为 干，修正回写）
        t = Text("乾闥婆")
        self.cv.convert_unit([t])
        self.assertEqual(t.text, "乾闼婆")

    def test_proper_noun_variant_codepoint(self):
        # 异体码点 U+95A5（字形同“闥”U+95E5）经 t2s 转为 U+9600，
        # 术语表须同样覆盖，否则漏网为干+U+9600+婆
        t = Text("乾" + chr(0x95A5) + "婆")
        self.cv.convert_unit([t])
        self.assertEqual([hex(ord(c)) for c in t.text], ["0x4e7e", "0x95fc", "0x5a46"])
        self.assertEqual(t.text, "乾闼婆")

    def test_length_preserved_structure_kept(self):
        # 结构节点不动：Lb/NoteRef 原位保留，line 属性不变
        a, b = Text("第一行", line="5"), Text("第二行", line="6")
        lb = Lb(n="1")
        ref = NoteRef(n="2")
        self.cv.convert_unit([a, lb, ref, b])
        self.assertEqual(a.line, "5")
        self.assertEqual(b.line, "6")
        self.assertEqual(lb.n, "1")
        self.assertEqual(ref.n, "2")

    def test_idempotent(self):
        t = Text("彌勒菩薩所問本願經")
        self.cv.convert_unit([t])
        once = t.text
        self.cv.convert_unit([t])
        self.assertEqual(t.text, once)


class TestPlainTextPipeline(unittest.TestCase):
    """纯文本管线（校验侧转换官方基线用）与 IR 管线一致。"""

    def test_simplify_text(self):
        self.assertEqual(simplify_text("彌勒菩薩所問本願經"), "弥勒菩萨所问本愿经")
        self.assertEqual(simplify_text("乾闥婆"), "乾闼婆")
        self.assertEqual(simplify_text("乾" + chr(0x95A5) + "婆"), "乾闼婆")

    def test_t2s_baseline_same_pipeline(self):
        s = "執著乾闥婆皇后"
        self.assertEqual(t2s_baseline(s), simplify_text(s))

    def test_length_preserved(self):
        s = "般若波羅蜜多心經觀自在菩薩"
        self.assertEqual(len(simplify_text(s)), len(s))


class TestRenderTimeGaiji(unittest.TestCase):
    """渲染时解析的缺字：简体模式同样过 t2s 管线（与官方侧 t2s_baseline 对齐）。"""

    def _work(self, simplified):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={}, body=[],
                    notes_by_n={}, apps={}, simplified=simplified)

    def test_traditional_untouched(self):
        from pycbeta.render_html import HtmlRenderer
        r = HtmlRenderer()
        r._work = self._work(False)
        self.assertEqual(r._resolve_gaiji("CBXXXX", "鬱"), "鬱")

    def test_simplified_converts(self):
        from pycbeta.render_html import HtmlRenderer
        from pycbeta.render_docx import DocxRenderer
        for cls in (HtmlRenderer, DocxRenderer):
            r = cls()
            r._work = self._work(True)
            self.assertEqual(r._resolve_gaiji("CBXXXX", "鬱"), "郁")

    def test_simplify_work_sets_flag(self):
        from pycbeta.parser import P5Parser
        fn = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        w = P5Parser().parse(fn)
        self.assertFalse(w.simplified)
        simplify_work(w)
        self.assertTrue(w.simplified)


class TestSimplifyWork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fn = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        cls.w = P5Parser().parse(fn)

    def test_metadata_and_body(self):
        simplify_work(self.w)
        self.assertIn("弥勒", self.w.metadata.get("title", ""))
        # 正文应出现简体字（源 XML 为繁体）
        self.assertIn("弥勒", self.w.metadata.get("title", ""))
        txt = "".join(n.text for b in self.w.body for n in _all_texts(b))
        self.assertNotIn("彌勒", txt)
        self.assertIn("弥勒", txt)


def _all_texts(node):
    from pycbeta.model import App, E, Text as _T
    out = []
    items = [node]
    if isinstance(node, App):
        items = ([node.lem] if node.lem is not None else []) + list(node.rdgs)
    for it in items:
        if it is None:
            continue
        if isinstance(it, _T):
            out.append(it)
        if isinstance(it, E):
            for c in it.children:
                out.extend(_all_texts(c))
    return out


if __name__ == "__main__":
    unittest.main()