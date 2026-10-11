# -*- coding: utf-8 -*-
"""仓库写隔离守卫（刻意命名 zzz：在 discover 字母序中最后执行）。

断言：自测试进程启动（`pycbeta/tests/__init__.py` 记录基线指纹，早于任何
用例运行）以来，三个入库文件无任何改动：
`presets/config.user.json`、`pycbeta/data/annotations.txt`、`presets/宋体.css`。

命名以 test_zzz 开头只为在 `discover` 默认字母序里殿后；本断言比较的是
"导入期基线 vs 现在"，与执行位置无关——排在后面的模块（如新增的
test_zzz_* 之后者）不在本守卫覆盖内，新增写仓库文件的测试请自带
tempdir/mock（仓内惯例：`save_config_preset(..., root=tmp)`、
`mock.patch.object(..., "user_presets_dir")`），并把文件加入
`pycbeta/tests/__init__.py: WATCHED_FILES`。

失败时先 `git checkout -- <文件>` 还原再修测试，禁止把脏文件直接提交
（曾有 `maxDiff 0→10` 被测试静默改回、随提交入库的事故）。
"""
import os
import unittest


class TestRepoHygiene(unittest.TestCase):
    def test_watched_files_unchanged(self):
        try:
            from pycbeta.tests import BASELINE, WATCHED_FILES
        except Exception:
            self.skipTest("无进程启动基线（包未经理所导入，如直跑单个测试文件）")
            return
        if not BASELINE:
            self.skipTest("空基线，跳过")
            return
        import hashlib

        def digest(path):
            try:
                with open(path, "rb") as f:
                    return hashlib.sha256(f.read()).hexdigest()
            except OSError:
                return None

        dirty = []
        for p in WATCHED_FILES:
            if digest(p) != BASELINE.get(p):
                dirty.append(os.path.relpath(p, os.getcwd()))
        self.assertEqual(
            dirty, [],
            "测试写脏了入库文件（须改走临时目录/mock，勿直接提交）："
            + "; ".join(dirty)
            + "；先 `git checkout -- <文件>` 还原",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
