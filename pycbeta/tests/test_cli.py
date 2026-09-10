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


class TestResolveOutputCollision(unittest.TestCase):
    def test_single_unchanged_without_used(self):
        # _used=None 时逐字节旧行为（单文件/重跑一致）
        d, n = resolve_output("/s/TX07n0006.xml", "txt", _args("/o"), _work())
        self.assertEqual((d, n), ("/o", "TX0006.txt"))

    def test_multi_source_fallback_to_stem(self):
        used = set()
        d1, n1 = resolve_output("/s/TX07n0006.xml", "txt", _args("/o"), _work(), used)
        d2, n2 = resolve_output("/s/TX08n0006.xml", "txt", _args("/o"), _work(), used)
        d3, n3 = resolve_output("/s/TX09n0006.xml", "txt", _args("/o"), _work(), used)
        self.assertEqual(n1, "TX0006.txt")
        self.assertEqual(n2, "TX08n0006.txt")
        self.assertEqual(n3, "TX09n0006.txt")
        self.assertEqual(d1, d2)

    def test_rerun_same_file_keeps_name(self):
        # 同一输入重跑：基名相同不触发回退（不因旧产物改名）
        used = set()
        _, n1 = resolve_output("/s/T12n0349.xml", "txt", _args("/o"), _work("T0349"), used)
        used.clear()  # 新一轮运行
        _, n2 = resolve_output("/s/T12n0349.xml", "txt", _args("/o"), _work("T0349"), used)
        self.assertEqual((n1, n2), ("T0349.txt", "T0349.txt"))

    def test_still_colliding_gets_suffix(self):
        used = set()
        a = ("", "TX0006.txt")
        used.add((os.path.normcase(os.path.abspath("/o")), "tx0006.txt"))
        used.add((os.path.normcase(os.path.abspath("/o")), "tx08n0006.txt"))
        _, n = resolve_output("/s/TX08n0006.xml", "txt", _args("/o"), _work(), used)
        self.assertEqual(n, "TX08n0006_2.txt")
        self.assertEqual(a[1], "TX0006.txt")


if __name__ == "__main__":
    unittest.main()
