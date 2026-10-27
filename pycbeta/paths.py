# -*- coding: utf-8 -*-
"""运行期路径：绿色版默认数据目录一律放在 exe 旁。"""
import os
import sys


def app_root():
    """冻结包 = exe 所在目录；源码运行 = 仓库根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_cbeta_ebook(create=False):
    """默认电子书工作目录：`<app_root>/cbeta_ebook`；create=True 时自动建。"""
    path = os.path.join(app_root(), "cbeta_ebook")
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def resolve_cbeta_ebook(presets=None, explicit=None, create=True):
    """显式值 > presets source.cbeta_ebook > exe 旁默认目录（自动创建）。"""
    cfg = (presets.get("source") or {}) if isinstance(presets, dict) else {}
    val = (explicit or cfg.get("cbeta_ebook") or "").strip()
    return val or default_cbeta_ebook(create=create)
