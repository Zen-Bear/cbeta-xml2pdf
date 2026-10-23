# -*- coding: utf-8 -*-
"""原子文本写盘：同目录临时文件 → `os.replace`（Windows 同卷可覆盖替换）。

GUI 配置/预设与 run.json 等「写入后立刻会被下一次读取」的小文件统一走这里，
避免写一半崩溃/断电留下半截 JSON/CSS。
"""
import os
import tempfile
from contextlib import contextmanager


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


def write_bytes(path: str, data: bytes) -> str:
    """原子写入二进制文件（docx/epub 等）：同目录临时文件 → `os.replace`。"""
    target = os.path.abspath(path)
    parent = os.path.dirname(target) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return target


@contextmanager
def atomic_path(path: str):
    """yield 同目录临时路径；正常退出 `os.replace` 到目标，异常清理临时文件。

    供外部引擎/PDF 转换等「只能按路径写」的场景使用；临时文件与目标同目录，
    保证同卷替换。目标被占用时 `os.replace` 失败，旧文件保持完整。"""
    target = os.path.abspath(path)
    parent = os.path.dirname(target) or "."
    os.makedirs(parent, exist_ok=True)
    suffix = os.path.splitext(target)[1] or ".part"
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=suffix, dir=parent)
    os.close(fd)
    try:
        yield tmp
        os.replace(tmp, target)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
