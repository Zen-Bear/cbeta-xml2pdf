# -*- coding: utf-8 -*-
"""测试用外部数据根（CBETA 电子书库）解析。

优先级：
1. 环境变量 `PYCBETA_TEST_DATA`（显式设置，含空串则视为“无数据”）；
2. 同目录本地文件 `.data_root`（**不入库**，供本机开发保留数据路径）；
3. 空 → 依赖外部数据的用例自动 skip。

仓库不携带任何开发者机器路径。
"""
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_LOCAL = os.path.join(_HERE, ".data_root")


def _resolve():
    env = os.environ.get("PYCBETA_TEST_DATA")
    if env is not None:
        return env.strip()
    try:
        with open(_LOCAL, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


DATA_ROOT = _resolve()

requires_data = unittest.skipUnless(
    bool(DATA_ROOT) and os.path.isdir(DATA_ROOT),
    "缺少外部测试数据：设环境变量 PYCBETA_TEST_DATA（或 pycbeta/tests/.data_root）"
    "指向 CBETA 电子书库目录")
