import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.fetch import resolve_source, fetch_work


class TestResolveSource(unittest.TestCase):
    def test_empty_raises_with_guidance(self):
        for presets in (None, {}, {"source": {}},
                        {"source": {"xml_dir": "", "download_dir": ""}}):
            with self.assertRaises(ValueError) as ctx:
                resolve_source(presets)
            self.assertIn("config.user.json", str(ctx.exception))

    def test_download_missing_raises(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_source({"source": {"xml_dir": "X:\\corpus"}})
        self.assertIn("download_dir", str(ctx.exception))

    def test_explicit_args_win(self):
        xml, dl = resolve_source({"source": {"xml_dir": "X:\\a", "download_dir": "X:\\b"}},
                                 xml_dir="Y:\\a")
        self.assertEqual((xml, dl), ("Y:\\a", "X:\\b"))

    def test_ok(self):
        self.assertEqual(resolve_source({"source": {"xml_dir": "X:\\a",
                                                    "download_dir": "X:\\b"}}),
                         ("X:\\a", "X:\\b"))

    def test_fetch_work_no_cwd_drop(self):
        # download_dir 空时直接报错，不再 os.path.join("", …) 落盘到 cwd
        with self.assertRaises(ValueError):
            fetch_work("T0349", ["xml"], {"source": {"xml_dir": "X:\\a"}})

    def test_fetch_only_needs_download_dir(self):
        # 纯下载不要求 xml_dir（need_xml=False）
        xml, dl = resolve_source({"source": {"download_dir": "X:\\b"}},
                                 need_xml=False)
        self.assertEqual((xml, dl), ("", "X:\\b"))
        with self.assertRaises(ValueError):
            resolve_source({"source": {"download_dir": "X:\\b"}})


if __name__ == "__main__":
    unittest.main()
