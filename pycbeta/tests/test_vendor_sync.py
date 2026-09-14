import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta._vendor import cbeta_fetch as cf
from pycbeta import names

_API = ("is_work_id", "parse_work_id", "canonical_work_id", "catalog_lookup",
        "DEFAULT_DOWNLOADS", "REMOTE_URLS", "ALL_FORMATS", "download",
        "unzip_flat", "fetch_if_changed", "probe", "probe_info")


class TestVendorSync(unittest.TestCase):
    """vendor 副本来自 cbeta-fetch（唯一事实源）：sha256/版本对账，防手改漂移。"""

    def test_source_sha256_and_version(self):
        path = os.path.abspath(cf.__file__)
        soft = os.path.join(os.path.dirname(path), "SOURCE.txt")
        self.assertTrue(os.path.isfile(soft), "缺 _vendor/SOURCE.txt")
        rec = {}
        with open(soft, encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.split("=", 1)
                    rec[k.strip()] = v.strip()
        with open(path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(rec.get("sha256"), sha,
                         "vendor 副本被手改；请跑 cbeta-fetch/tools/sync_into.py")
        self.assertEqual(rec.get("version"), cf.__version__)

    def test_public_api(self):
        for name in _API:
            self.assertTrue(hasattr(cf, name), name)

    def test_id_grammar_in_sync_with_names(self):
        # 共享层与 names.py 的 canon/编号语法应一致（防漂移）
        self.assertEqual(cf.CANON, names.CANON)
        self.assertEqual(cf.WORK_PART, names.WORK_PART)


if __name__ == "__main__":
    unittest.main()
