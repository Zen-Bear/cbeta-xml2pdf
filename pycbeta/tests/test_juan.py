# -*- coding: utf-8 -*-
"""卷范围（juan）纯函数层测试：语法/标签/后缀/IR 过滤。"""
import unittest

from pycbeta import juan as J
from pycbeta.model import App, E, Note, NoteRef, Text, Work


def _ms(n):
    return E(tag="milestone", attrs={"unit": "juan", "n": str(n)})


def _note(n, text="注"):
    return Note(tag="note", attrs={}, n=str(n), ntype="orig",
                children=[Text(text=text)])


def _work(body, notes=None, apps=None):
    return Work(id="T0001", source_file="", metadata={"title": "t", "author": ""},
                body=body, notes_by_n=notes or {}, apps=apps or [],
                simplified=False)


def _all_texts(nodes):
    out = []
    for n in nodes:
        if isinstance(n, Text):
            out.append(n.text)
        elif getattr(n, "children", None):
            out += _all_texts(n.children)
    return out


class TestParseJuanSpec(unittest.TestCase):
    def test_single(self):
        self.assertEqual(J.parse_juan_spec("34"), [(34, 34)])

    def test_range(self):
        self.assertEqual(J.parse_juan_spec("34-100"), [(34, 100)])

    def test_multi_segments(self):
        self.assertEqual(J.parse_juan_spec("34-36,40,42-45"),
                         [(34, 36), (40, 40), (42, 45)])

    def test_tilde_forms(self):
        self.assertEqual(J.parse_juan_spec("34~36"), [(34, 36)])
        self.assertEqual(J.parse_juan_spec("34～36"), [(34, 36)])
        self.assertEqual(J.parse_juan_spec("34 - 36"), [(34, 36)])

    def test_plus_separator(self):
        self.assertEqual(J.parse_juan_spec("34-36+40"), [(34, 36), (40, 40)])

    def test_merge_overlap_and_adjacent(self):
        self.assertEqual(J.parse_juan_spec("34,35,36"), [(34, 36)])
        self.assertEqual(J.parse_juan_spec("34-36,35-40"), [(34, 40)])
        self.assertEqual(J.parse_juan_spec("40,34-36,42-45,41"),
                         [(34, 36), (40, 45)])

    def test_errors(self):
        for bad in ("", "  ", "abc", "34-", "-34", "100-34", "0", "34-10000",
                    "3.5", "卷1"):
            with self.assertRaises(ValueError, msg=bad):
                J.parse_juan_spec(bad)

    def test_juan_set(self):
        self.assertEqual(J.juan_set([(34, 36), (40, 40)]),
                         {34, 35, 36, 40})


class TestLabelAndSplit(unittest.TestCase):
    def test_label(self):
        self.assertEqual(J.format_juan_label([(34, 36), (40, 40)]), "34-36、40")
        self.assertEqual(J.format_juan_label([(34, 34)]), "34")
        self.assertEqual(J.format_juan_label([(34, 100)]), "34-100")

    def test_split_id_juan(self):
        self.assertEqual(J.split_id_juan("T25n1509:34-100"),
                         ("T25n1509", "34-100"))
        self.assertEqual(J.split_id_juan("T25n1509：34-100"),
                         ("T25n1509", "34-100"))
        self.assertEqual(J.split_id_juan("T0349"), ("T0349", None))
        self.assertEqual(J.split_id_juan("T0349:"), ("T0349", None))
        self.assertEqual(J.split_id_juan(""), ("", None))

    def test_split_id_juan_nnn(self):
        # 官方分卷后缀形态：`T0001_001` ≡ `T0001:1`（1-3 位归一；`:` 优先）
        self.assertEqual(J.split_id_juan("T0001_001"), ("T0001", "1"))
        self.assertEqual(J.split_id_juan("T0001_1"), ("T0001", "1"))
        self.assertEqual(J.split_id_juan("T0001_01"), ("T0001", "1"))
        self.assertEqual(J.split_id_juan("T25n1509_034"), ("T25n1509", "34"))
        self.assertEqual(J.split_id_juan("T0001_000"), ("T0001", "0"))
        self.assertEqual(J.split_id_juan("T0001_0001"), ("T0001_0001", None))
        self.assertEqual(J.split_id_juan("T0001_"), ("T0001_", None))
        self.assertEqual(J.split_id_juan("T0001:1_002"), ("T0001", "1_002"))
        with self.assertRaises(ValueError):
            J.parse_juan_spec(J.split_id_juan("T0001_000")[1])
        with self.assertRaises(ValueError):
            J.parse_juan_spec(J.split_id_juan("T0001:1_002")[1])


class TestResolveSuffix(unittest.TestCase):
    def test_default_template(self):
        s, fb = J.resolve_juan_suffix("", "34-36、40")
        self.assertEqual(s, "（卷34-36、40）")
        self.assertTrue(fb)

    def test_custom_template(self):
        s, fb = J.resolve_juan_suffix("【{label}】", "34")
        self.assertEqual(s, "【34】")
        self.assertFalse(fb)

    def test_bad_template_falls_back(self):
        s, fb = J.resolve_juan_suffix("（卷）", "34")
        self.assertEqual(s, "（卷34）")
        self.assertTrue(fb)


class TestFilterWorkJuan(unittest.TestCase):
    def _sample(self):
        n1, n2 = _note("1"), _note("2")
        a1 = App(tag="app", attrs={}, children=[], key="app.1")
        a2 = App(tag="app", attrs={}, children=[], key="app.2")
        div1 = E(tag="div", attrs={}, children=[
            Text("j1a"), NoteRef(n="1", notes=[n1]), a1])
        body = [Text("head0"), _ms(1), div1, _ms(2),
                Text("j2"), NoteRef(n="2", notes=[n2]),
                _ms(3), E(tag="div", attrs={}, children=[Text("j3"), a2])]
        w = _work(body, notes={"1": [n1], "2": [n2]}, apps=[a1, a2])
        return w, n1, n2

    def test_filter_middle(self):
        w, _n1, n2 = self._sample()
        res = J.filter_work_juan(w, J.parse_juan_spec("2-3"))
        self.assertEqual(res["status"], "filtered")
        self.assertEqual(res["kept"], {2, 3})
        self.assertEqual(res["all"], {1, 2, 3})
        self.assertEqual(res["label"], "2-3")
        # 前置内容（juan 0）与 j1 全掉；j2/j3 保留
        texts = _all_texts(w.body)
        self.assertEqual(texts, ["j2", "j3"])
        ms = [int(n.attrs["n"]) for n in w.body
              if isinstance(n, E) and n.tag == "milestone"]
        self.assertEqual(ms, [2, 3])
        # 注/app 裁剪：n1 与 a1 被裁；n2 保留（NoteRef 在 j2）
        self.assertEqual(set(w.notes_by_n), {"2"})
        self.assertEqual([a.key for a in w.apps], ["app.2"])
        self.assertIn(n2, w.notes_by_n["2"])

    def test_filter_first_keeps_juan0(self):
        w, _n1, _n2 = self._sample()
        res = J.filter_work_juan(w, J.parse_juan_spec("1"))
        self.assertEqual(res["status"], "filtered")
        self.assertEqual(res["kept"], {1})
        texts = _all_texts(w.body)
        self.assertIn("head0", texts)       # 首 milestone 前内容随最小卷保留
        self.assertIn("j1a", texts)
        self.assertNotIn("j2", texts)
        self.assertEqual(set(w.notes_by_n), {"1"})
        self.assertEqual([a.key for a in w.apps], ["app.1"])

    def test_full_is_noop(self):
        w, _n1, _n2 = self._sample()
        before = w.body
        res = J.filter_work_juan(w, J.parse_juan_spec("1-3"))
        self.assertEqual(res["status"], "full")
        self.assertIs(w.body, before)
        self.assertEqual(set(w.notes_by_n), {"1", "2"})

    def test_empty_intersection(self):
        w, _n1, _n2 = self._sample()
        before = w.body
        res = J.filter_work_juan(w, J.parse_juan_spec("9"))
        self.assertEqual(res["status"], "empty")
        self.assertIs(w.body, before)

    def test_no_milestone(self):
        w = _work([Text("a"), Text("b")])
        before = w.body
        res = J.filter_work_juan(w, J.parse_juan_spec("1"))
        self.assertEqual(res["status"], "no_milestone")
        self.assertIs(w.body, before)

    def test_nested_div_span(self):
        n1 = _note("1")
        div = E(tag="div", attrs={}, children=[
            Text("a"), _ms(1), Text("b"), _ms(2), Text("c"),
            NoteRef(n="1", notes=[n1])])
        w = _work([div], notes={"1": [n1]})
        res = J.filter_work_juan(w, J.parse_juan_spec("2"))
        self.assertEqual(res["status"], "filtered")
        (d,) = w.body
        self.assertIsInstance(d, E)
        self.assertEqual(d.tag, "div")
        texts = [n.text for n in d.children if isinstance(n, Text)]
        self.assertEqual(texts, ["c"])
        ms = [int(n.attrs["n"]) for n in d.children
              if isinstance(n, E) and n.tag == "milestone"]
        self.assertEqual(ms, [2])
        self.assertEqual(set(w.notes_by_n), {"1"})

    def test_milestone_without_n_counts_sequentially(self):
        body = [E(tag="milestone", attrs={"unit": "juan"}),
                Text("one"),
                E(tag="milestone", attrs={"unit": "juan"}),
                Text("two")]
        w = _work(body)
        res = J.filter_work_juan(w, J.parse_juan_spec("2"))
        self.assertEqual(res["status"], "filtered")
        texts = [n.text for n in w.body if isinstance(n, Text)]
        self.assertEqual(texts, ["two"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
