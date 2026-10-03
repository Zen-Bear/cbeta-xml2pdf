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


def _report_note(cat, msg, key=None):
    """转换报告：文件名净化（仅 CLI 子进程内激活；GUI worker 侧 no-op）。"""
    try:
        from .report import report
        report.add(cat, msg, key=key)
    except Exception:  # noqa: BLE001 —— 报告失败不影响命名
        pass


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
        _report_note("输出净化", f"文件名删除非法字符：{''.join(warned)!r}",
                     key=("fn_illegal", name))
    s = "".join(out).rstrip(". ").strip()
    stem = s.split(".")[0].upper()
    if stem in _RESERVED:
        s = "_" + s
        print(f"警告: 文件名 {stem} 为保留名，已加前缀 _", file=sys.stderr)
        _report_note("输出净化", f"文件名 {stem} 为保留名，已加前缀 _",
                     key=("fn_reserved", stem))
    if not s:
        print("警告: 文件名经处理后为空，退回使用 [id]", file=sys.stderr)
        _report_note("输出净化", "文件名经处理后为空，退回 UNKNOWN",
                     key=("fn_empty", name))
        return "UNKNOWN"
    if len(s) > _MAX_LEN:
        print(f"警告: 文件名过长，已截断到 {_MAX_LEN} 字符", file=sys.stderr)
        _report_note("输出净化", f"文件名过长，截断到 {_MAX_LEN} 字符",
                     key=("fn_trunc", name))
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


def default_output_name(work_id: str, title: str, title_t2s: bool = True) -> str:
    """默认产物基名：`{workid 书名}`（与下载电子书 work 目录同款）。

    `title_t2s=True` 时书名经 OpenCC 转简（`source.title_t2s`；失败原样）；
    无书名回退 `{workid}`；最后做 Windows 净化。
    """
    title = (title or "").strip()
    if title and title_t2s:
        try:
            from .simplify import simplify_text
            title = simplify_text(title)
        except Exception:
            pass
    return sanitize(f"{work_id} {title}".strip() if title else (work_id or "UNKNOWN"))


def _claim(taken, emitted, out_dir, name):
    """认领一名：已登记（同轮重放/同文件重复）原样返回，不 churn taken；
    否则占用（仍撞则 _2 后缀），返回最终名。"""
    import os as _os
    if (out_dir, name) in emitted:
        return name
    ndir = _os.path.normcase(_os.path.abspath(out_dir))
    cand = name
    if (ndir, cand.lower()) in taken:
        base, ext = _os.path.splitext(name)
        i = 2
        while (ndir, f"{base}_{i}{ext}".lower()) in taken:
            i += 1
        cand = f"{base}_{i}{ext}"
    taken.add((ndir, cand.lower()))
    emitted.append((out_dir, cand))
    return cand


def dedupe_run_outputs(state, out_dir, default_name, src_stem):
    """多源同名统一回退：一次运行内多输入同名时，全组改用输入基名。

    state: 调用方持有 dict（一次运行共用；CLI 主循环 / GUI worker 各持一份；
    render 与 verify 两阶段共用同一对象，重放即得终态名）。
    返回 (final_name, renames)，renames 为需预执行的 [(old_abs, new_abs)]
    （首文件已落盘输出改名；调用方执行，缺失忽略）。
    单文件/重跑/同文件重复：与旧逻辑逐字节一致。
    """
    import os as _os
    base_d, ext = _os.path.splitext(default_name)
    stem = _os.path.splitext(_os.path.basename(src_stem or ""))[0] or base_d
    taken = state.setdefault("_taken", set())
    groups = state.setdefault("_groups", {})
    key = (_os.path.normcase(_os.path.abspath(out_dir)), default_name.lower())
    g = groups.setdefault(key, {"first": stem, "converted": False,
                                "emitted": []})
    if stem == g["first"] and not g["converted"]:
        # 首源（转换前）：legacy 名，幂等
        final = _claim(taken, g["emitted"], out_dir, default_name)
        return final, []
    # 多源组（或其重放）：统一 stem 命名
    renames = []
    if not g["converted"]:
        first = g["first"]
        conv = []
        for (d, n) in g["emitted"]:
            nn = _claim(taken, conv, d, first + _os.path.splitext(n)[1])
            if nn != n:
                renames.append((_os.path.join(d, n), _os.path.join(d, nn)))
        g["emitted"] = conv
        g["converted"] = True
    final = _claim(taken, g["emitted"], out_dir, stem + ext)
    return final, renames
