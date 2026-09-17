"""CBETA gaiji (missing character) database access."""

import json
import os
from typing import Dict, Optional


class GaijiDb:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "cbeta", "data")
        self._db: Dict[str, dict] = {}
        for fn in ("cbeta_gaiji.json", "cbeta_sanskrit.json"):
            path = os.path.join(data_dir, fn)
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    self._db.update(json.load(f))

    def get(self, code: str) -> Optional[dict]:
        return self._db.get(code)

    def records(self):
        """全库记录（dict 值集合；只读遍历用，如注音回退的规范化字）。"""
        return self._db.values()

    def __contains__(self, code: str) -> bool:
        return code in self._db


def pua(code: str) -> str:
    if code.startswith("SD"):
        return chr(0xFA000 + int(code[-4:], 16))
    if code.startswith("RJ"):
        return chr(0x100000 + int(code[-4:], 16))
    return chr(0xF0000 + int(code[2:]))
