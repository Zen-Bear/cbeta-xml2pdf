import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.filename import dedupe_run_outputs


class TestDedupeRunOutputs(unittest.TestCase):
    def test_single_uses_default(self):
        st = {}
        n, rn = dedupe_run_outputs(st, "/o", "TX0006.txt", "TX07n0006")
        self.assertEqual((n, rn), ("TX0006.txt", []))

    def test_group_uniform_stem_names(self):
        st = {}
        n1, r1 = dedupe_run_outputs(st, "/o", "TX0006.txt", "TX07n0006")
        n2, r2 = dedupe_run_outputs(st, "/o", "TX0006.txt", "TX08n0006")
        n3, r3 = dedupe_run_outputs(st, "/o", "TX0006.txt", "TX09n0006")
        self.assertEqual(n1, "TX0006.txt")
        self.assertEqual(r1, [])
        self.assertEqual(n2, "TX08n0006.txt")
        # 首文件预改名（调用方执行，缺失忽略）
        self.assertEqual(len(r2), 1)
        self.assertTrue(r2[0][0].endswith("TX0006.txt"))
        self.assertTrue(r2[0][1].endswith("TX07n0006.txt"))
        self.assertEqual(n3, "TX09n0006.txt")
        self.assertEqual(r3, [])

    def test_replay_yields_final_names(self):
        # 同一 state 重放（verify 阶段）：直接得终态名，不再改名
        st = {}
        dedupe_run_outputs(st, "/o", "TX0006.txt", "TX07n0006")
        dedupe_run_outputs(st, "/o", "TX0006.txt", "TX08n0006")
        n1, r1 = dedupe_run_outputs(st, "/o", "TX0006.txt", "TX07n0006")
        n2, r2 = dedupe_run_outputs(st, "/o", "TX0006.txt", "TX08n0006")
        self.assertEqual((n1, n2), ("TX07n0006.txt", "TX08n0006.txt"))
        self.assertEqual((r1, r2), ([], []))

    def test_different_works_untouched(self):
        st = {}
        n1, _ = dedupe_run_outputs(st, "/o", "T0349.txt", "T12n0349")
        n2, _ = dedupe_run_outputs(st, "/o", "T0625.txt", "T15n0625")
        self.assertEqual((n1, n2), ("T0349.txt", "T0625.txt"))

    def test_same_file_repeat_idempotent(self):
        st = {}
        n1, r1 = dedupe_run_outputs(st, "/o", "T0349.txt", "T12n0349")
        n2, r2 = dedupe_run_outputs(st, "/o", "T0349.txt", "T12n0349")
        self.assertEqual((n1, r1), ("T0349.txt", []))
        self.assertEqual((n2, r2), ("T0349.txt", []))

    def test_foreign_occupancy_gets_suffix(self):
        import os as _os
        taken_key = (_os.path.normcase(_os.path.abspath("/o")), "b.txt")
        st = {"_taken": {taken_key}, "_groups": {}}
        n1, _ = dedupe_run_outputs(st, "/o", "X.txt", "A")
        n2, r2 = dedupe_run_outputs(st, "/o", "X.txt", "B")
        self.assertEqual(n1, "X.txt")
        # B.txt 被外部占用 → B_2；A 照常转 stem 名
        self.assertEqual(n2, "B_2.txt")
        self.assertEqual(len(r2), 1)


class TestDefaultOutputName(unittest.TestCase):
    def test_id_and_title(self):
        from pycbeta.filename import default_output_name
        self.assertEqual(default_output_name("T0349", "彌勒菩薩所問本願經", False),
                         "T0349 彌勒菩薩所問本願經")

    def test_no_title_falls_back_to_id(self):
        from pycbeta.filename import default_output_name
        self.assertEqual(default_output_name("T0349", "", True), "T0349")

    def test_t2s_follows_switch(self):
        import unittest.mock as mock
        from pycbeta.filename import default_output_name
        with mock.patch("pycbeta.simplify.simplify_text",
                        return_value="弥勒菩萨所问本愿经"):
            got = default_output_name("T0349", "彌勒菩薩所問本願經", True)
        self.assertEqual(got, "T0349 弥勒菩萨所问本愿经")

    def test_sanitized(self):
        from pycbeta.filename import default_output_name
        self.assertEqual(default_output_name("T1", "a/b:c", False), "T1 a／b：c")


if __name__ == "__main__":
    unittest.main()
