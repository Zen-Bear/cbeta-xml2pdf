# -*- coding: utf-8 -*-
"""测试包初始化：记录仓库受保护文件的基线指纹（供写隔离守卫用）。

背景：`presets/config.user.json` 自 v0.5 起入库为标准预设；另有
`pycbeta/data/annotations.txt`、`presets/宋体.css` 两个入库数据文件。
测试必须 hermetic——任何用例都不许写脏这三个文件（曾出现跑完回归
`maxDiff 0→10` 被静默改回的事故；见 `test_zzz_repo_hygiene.py`）。

本模块在测试进程首次 `import pycbeta.tests...` 时执行（早于任何用例运行，
unittest 先全量 load 再 run），只读三个小文件取 sha256，失败静默（`None`
即跳过守卫不断链）。直跑单个测试文件（`python pycbeta/tests/test_x.py`，
包未被导入）时无基线，守卫自动跳过并明示。
"""
import hashlib as _hashlib
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_os.path.dirname(_HERE))

#: 写隔离保护清单（入库文件；测试只读，改写即事故）
WATCHED_FILES = (
    _os.path.join(_REPO, "presets", "config.user.json"),
    _os.path.join(_REPO, "pycbeta", "data", "annotations.txt"),
    _os.path.join(_REPO, "presets", "宋体.css"),
)


def _digest(path):
    try:
        with open(path, "rb") as f:
            return _hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


#: 进程启动基线 {abspath: sha256|None}（缺失记 None；导入期只读，永不抛异常）
BASELINE = {p: _digest(p) for p in WATCHED_FILES}
