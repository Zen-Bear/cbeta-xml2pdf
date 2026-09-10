import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.cli import resolve_output


def _args(out):
    return SimpleNamespace(output=out, name_template=None)


def _work(wid="TX0006"):
    return SimpleNamespace(id=wid, metadata={})


def _touch(d, name):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("x")
    return p


class TestResolveOutputCollision(unittest.TestCase):
    def test_single_unchanged_without_used(self):
        # _used=None 时逐字节旧行为（单文件/重跑一致）
        d, n = resolve_output("/s/TX07n0006.xml", "txt", _args("/o"), _work())
        self.assertEqual((d, n), ("/o", "TX0006.txt"))

    def test_group_uniform_with_rename(self):
        import shutil
        d = tempfile.mkdtemp()
        try:
            used = {}
            d1, n1 = resolve_output("/s/TX07n0006.xml", "txt",
                                    _args(d), _work(), used)
            self.assertEqual(n1, "TX0006.txt")
            _touch(d, n1)  # 首文件已落盘
            d2, n2 = resolve_output("/s/TX08n0006.xml", "txt",
                                    _args(d), _work(), used)
            # 全组统一 stem 名；首文件被预改名
            self.assertEqual(n2, "TX08n0006.txt")
            self.assertTrue(os.path.isfile(os.path.join(d, "TX07n0006.txt")))
            self.assertFalse(os.path.isfile(os.path.join(d, "TX0006.txt")))
            d3, n3 = resolve_output("/s/TX09n0006.xml", "txt",
                                    _args(d), _work(), used)
            self.assertEqual(n3, "TX09n0006.txt")
            self.assertEqual(d1, d2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_replay_shared_state(self):
        # render 与 verify 共用同一 state：重放直接得终态名
        used = {}
        r1 = [resolve_output(f"/s/TX0{n}n0006.xml", "txt", _args("/o"),
                             _work(), used)[1] for n in (7, 8, 9)]
        r2 = [resolve_output(f"/s/TX0{n}n0006.xml", "txt", _args("/o"),
                             _work(), used)[1] for n in (7, 8, 9)]
        self.assertEqual(r1, ["TX0006.txt", "TX08n0006.txt", "TX09n0006.txt"])
        self.assertEqual(r2, ["TX07n0006.txt", "TX08n0006.txt", "TX09n0006.txt"])

    def test_rerun_fresh_state_keeps_name(self):
        # 同一输入重跑（新 state）：基名相同不触发回退
        _, n1 = resolve_output("/s/T12n0349.xml", "txt", _args("/o"),
                               _work("T0349"), {})
        _, n2 = resolve_output("/s/T12n0349.xml", "txt", _args("/o"),
                               _work("T0349"), {})
        self.assertEqual((n1, n2), ("T0349.txt", "T0349.txt"))

    def test_explicit_file_untouched(self):
        out = os.path.join(tempfile.mkdtemp(), "mine.txt")
        d, n = resolve_output("/s/TX08n0006.xml", "txt", _args(out),
                              _work(), {})
        self.assertEqual(n, "mine.txt")


if __name__ == "__main__":
    unittest.main()
