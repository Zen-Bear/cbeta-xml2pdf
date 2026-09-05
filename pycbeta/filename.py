"""Output filename: template tokens + Windows-safe sanitization.

Template tokens (replaced with work metadata):
  [id]     work id (e.g. T0349)
  [书名]   title
  [作者]   author
  [vol]    册号
  [juan]   卷号（per-juan output; empty otherwise）

Sanitization (Windows):
  1) map illegal chars to full-width forms (keep readability)
  2) if a char has no full-width form -> delete + warn (stderr)
  3) strip trailing dots/spaces; reserved names; length cap
  4) if result is empty -> fall back to [id]
"""

import re
import sys

_ILLEGAL_FULLWIDTH = {
    ":": "：", "\\": "＼", "/": "／", "*": "＊", "?": "？",
    '"': "＂", "<": "＜", ">": "＞", "|": "｜",
}
_ILLEGAL_SET = set(_ILLEGAL_FULLWIDTH)
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_MAX_LEN = 200


def sanitize(name: str) -> str:
    """Return a Windows-safe filename; warn (stderr) about deleted chars."""
    warned = []
    out = []
    for ch in name:
        if ch in _ILLEGAL_FULLWIDTH:
            out.append(_ILLEGAL_FULLWIDTH[ch])
        elif ch in _ILLEGAL_SET or ord(ch) < 32:
            warned.append(ch)
        else:
            out.append(ch)
    if warned:
        print(f"警告: 文件名含无全角对应之非法字符，已删除: {''.join(map(repr, warned))}",
              file=sys.stderr)
    s = "".join(out).rstrip(". ").strip()
    stem = s.split(".")[0].upper()
    if stem in _RESERVED:
        s = "_" + s
        print(f"警告: 文件名 {stem} 为保留名，已加前缀 _", file=sys.stderr)
    if not s:
        print("警告: 文件名经处理后为空，退回使用 [id]", file=sys.stderr)
        return "UNKNOWN"
    if len(s) > _MAX_LEN:
        print(f"警告: 文件名过长，已截断到 {_MAX_LEN} 字符", file=sys.stderr)
        s = s[:_MAX_LEN].rstrip(". ")
    return s


def apply_template(template: str, work, juan=None) -> str:
    """Replace [id]/[书名]/[作者]/[vol]/[juan] tokens and sanitize."""
    md = work.metadata
    values = {
        "[id]": work.id,
        "[书名]": md.get("title") or work.id,
        "[作者]": md.get("author") or "",
        "[vol]": str(md.get("vol") or ""),
        "[juan]": f"{int(juan):03d}" if juan else "",
    }
    name = template
    for token, val in values.items():
        name = name.replace(token, val)
    return sanitize(name)
