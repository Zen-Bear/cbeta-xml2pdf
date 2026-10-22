# -*- coding: utf-8 -*-
"""原子文本写盘：同目录临时文件 → `os.replace`（Windows 同卷可覆盖替换）。

GUI 配置/预设与 run.json 等「写入后立刻会被下一次读取」的小文件统一走这里，
避免写一半崩溃/断电留下半截 JSON/CSS。
"""
import os
import tempfile


def write_text(path: str, text: str, encoding: str = "utf-8") -> str:
    """原子写入 `path`：先写同目录临时文件，成功后替换；失败清理临时文件。

    - 自动创建父目录；
    - 沿用平台默认换行转换（与旧 `open(path, "w")` 行为一致）；
    - 返回目标绝对路径。"""
    target = os.path.abspath(path)
    parent = os.path.dirname(target) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return target
