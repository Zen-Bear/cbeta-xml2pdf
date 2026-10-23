# -*- coding: utf-8 -*-
"""本程序临时目录的启动清理（硬杀残留；只动超过阈值的旧目录）。"""
import glob
import os
import shutil
import tempfile
import time

#: 只清理本程序创建的临时目录/文件前缀；默认 24 小时，避开并发实例正在用的目录。
PREFIXES = ("xml2pdf-",)


def cleanup_stale_temp_dirs(max_age_hours=24, prefixes=PREFIXES):
    """删除临时根下超过 max_age_hours 的 `xml2pdf-*` 目录。

    返回 (删除数, 失败列表[短说明])。只处理目录；最近修改的不动
    （并发运行的实例会持续写自己的目录）。任何单项失败都不中断其余项。
    """
    root = tempfile.gettempdir()
    try:
        cutoff = time.time() - float(max_age_hours) * 3600
    except (TypeError, ValueError):
        cutoff = time.time() - 24 * 3600
    removed, failed = 0, []
    for prefix in prefixes:
        for path in glob.glob(os.path.join(root, f"{prefix}*")):
            if not os.path.isdir(path):
                continue
            try:
                if os.path.getmtime(path) >= cutoff:
                    continue
                shutil.rmtree(path)
                removed += 1
            except OSError as exc:
                failed.append(f"{os.path.basename(path)}: {exc}")
    return removed, failed
