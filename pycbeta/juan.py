# -*- coding: utf-8 -*-
"""按卷范围（juan）选取子集：`T25n1509:34-100` 子集渲染与校验的纯函数层。

语法（CLI `--juan` / `-i ID:范围` / GUI 编号后缀 `:` 共用）：
  `34` / `34-100` / `34-36,40,42-45`
  - `,` 与 `+` 都作段分隔（GUI 列表内 `,` 是任务分隔符，用 `+`）；
  - `-`/`~`/`～` 三认一（归一为 `-`）；
  - 闭区间、`lo<=hi`（`100-34` 报错不下调）；去重合并（重叠/相邻）。

过滤在 IR 层按 `<milestone unit="juan">` 重放 body：div 壳浅拷贝、
milestone 保留（分页/分文件/书签机制照常）；`juan 0`（首 milestone 前内容）
仅在所选含全书最小卷时保留；无 milestone → `no_milestone`（调用方警告忽略）；
选择覆盖全部卷 → `full`（不动，字节一致、不加后缀）。
"""
import re
from dataclasses import replace
from typing import List, Optional, Set, Tuple

from .model import App, E, NoteRef, Work

__all__ = ["parse_juan_spec", "juan_set", "format_juan_label",
           "split_id_juan", "resolve_juan_suffix", "filter_work_juan",
           "normalize_segments", "DEFAULT_SUFFIX_TEMPLATE"]

#: 卷号上限（防 `1-99999999` 类输入炸内存）
_MAX_JUAN = 9999

#: 后缀模板默认值（`output.juan_suffix_template`；含 `{label}` 才生效）
DEFAULT_SUFFIX_TEMPLATE = "（卷{label}）"


def parse_juan_spec(spec) -> List[Tuple[int, int]]:
    """解析卷范围 → 归一去重的 [(lo, hi)]（闭区间，按 lo 升序）。

    非法输入抛 ValueError（含起止颠倒、非数字、空、超上限）。
    """
    s = (spec or "").strip()
    if not s:
        raise ValueError("卷范围为空")
    segs: List[List[int]] = []
    for part in re.split(r"[,，+]", s):
        part = part.strip().replace("～", "-").replace("~", "-")
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)|(\d+)", part)
        if not m:
            raise ValueError(
                f"卷范围非法: {part!r}（示例 34 / 34-100 / 34-36,40）")
        if m.group(3) is not None:
            lo = hi = int(m.group(3))
        else:
            lo, hi = int(m.group(1)), int(m.group(2))
        if lo < 1 or hi < 1:
            raise ValueError(f"卷号从 1 起: {part!r}")
        if lo > _MAX_JUAN or hi > _MAX_JUAN:
            raise ValueError(f"卷号超出上限 {_MAX_JUAN}: {part!r}")
        if lo > hi:
            raise ValueError(f"卷范围起止颠倒: {part!r}（应为 34-100）")
        segs.append([lo, hi])
    if not segs:
        raise ValueError("卷范围为空")
    segs.sort()
    out = [segs[0]]
    for lo, hi in segs[1:]:
        if lo <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [(lo, hi) for lo, hi in out]


def juan_set(segs) -> Set[int]:
    """段列表 → 卷号集合。"""
    return {n for lo, hi in (segs or []) for n in range(lo, hi + 1)}


def format_juan_label(segs) -> str:
    """段列表 → 显示标签：`34` / `34-100` / `34-36、40`（段间全角顿号）。"""
    parts = []
    for lo, hi in (segs or []):
        parts.append(str(lo) if lo == hi else f"{lo}-{hi}")
    return "、".join(parts)


def normalize_segments(segs) -> Optional[List[Tuple[int, int]]]:
    """段列表归一（排序、合并重叠/相邻）→ [(lo, hi)]。

    `[]`/None → None（无卷范围）；非法（非二元、非整数、`lo<1`、`lo>hi`）抛
    `ValueError`（与 `parse_juan_spec` 同口径；供指纹/报告等已解析入参复用，
    调用方据此判"不能证明"或报错）。
    """
    out: List[List[int]] = []
    for it in (segs or []):
        try:
            lo, hi = int(it[0]), int(it[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise ValueError(f"卷范围非法: {it!r}（应为 (lo, hi)）")
        if lo < 1 or hi < 1:
            raise ValueError(f"卷号从 1 起: {it!r}")
        if lo > hi:
            raise ValueError(f"卷范围起止颠倒: {it!r}")
        out.append([lo, hi])
    if not out:
        return None
    out.sort()
    merged = [out[0]]
    for lo, hi in out[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(lo, hi) for lo, hi in merged]


def split_id_juan(text) -> Tuple[str, Optional[str]]:
    """`T25n1509:34-100` → ("T25n1509", "34-100")；
    `T0001_001` → ("T0001", "1")；无分隔符 → (原文, None)。

    `:` 与全角 `：` 都认，优先于 `_NNN`（`T0001:1_002` 走冒号分支，spec
    `1_002` 交给下游报错）；spec 为空串视为无（返回 None）。
    `_NNN` 认 1–3 位数字（官方分卷后缀形态；`_001`/`_01`/`_1` 归一为整数串；
    `_0`/`_000` 返回 "0" 交给 `parse_juan_spec` 报"卷号从 1 起"；4 位以上不认）。
    head 合法性由调用方判定（本函数不校验：非法 head 后续走"非法編號"/文件
    不存在原有报错路径）。
    """
    s = (text or "").strip()
    m = re.match(r"^([^:：]+)[:：](.*)$", s)
    if m:
        spec = m.group(2).strip()
        return m.group(1).strip(), (spec or None)
    m2 = re.match(r"^(.+)_(\d{1,3})$", s)
    if m2:
        return m2.group(1), str(int(m2.group(2)))
    return s, None


def resolve_juan_suffix(template, label) -> Tuple[str, bool]:
    """后缀渲染 → (后缀, 是否回退默认)。

    `output.juan_suffix_template` 为空/不含 `{label}` → 回退默认 `（卷{label}）`
    并置回退位（调用方据此警告）。
    """
    tpl = (template or "").strip()
    if tpl and "{label}" in tpl:
        try:
            return tpl.format(label=label), False
        except (KeyError, IndexError, ValueError):
            pass
    return DEFAULT_SUFFIX_TEMPLATE.format(label=label), True


def _milestone_juans(body) -> List[int]:
    """body 中全部卷 milestone 卷号（文档序，缺失 n 按前值 +1）。"""
    out: List[int] = []
    cur = 0

    def walk(nodes):
        nonlocal cur
        for n in nodes:
            if isinstance(n, E) and n.tag == "milestone" \
                    and n.attrs.get("unit") == "juan":
                try:
                    cur = int(n.attrs.get("n"))
                except (TypeError, ValueError):
                    cur += 1
                out.append(cur)
            elif getattr(n, "children", None):
                walk(n.children)

    walk(body)
    return out


def _walk_filter(nodes, selected: Set[int], keep0: bool, state: dict) -> list:
    """重放 body：milestone 置位并保留命中者；div 等容器浅拷贝；
    叶子按当前卷保留；juan 0 段按 keep0 保留。"""
    out = []
    for n in nodes:
        if isinstance(n, E) and n.tag == "milestone" \
                and n.attrs.get("unit") == "juan":
            try:
                state["cur"] = int(n.attrs.get("n"))
            except (TypeError, ValueError):
                state["cur"] = state["cur"] + 1
            if state["cur"] in selected:
                out.append(n)
            continue
        if isinstance(n, E) and getattr(n, "children", None):
            kids = _walk_filter(n.children, selected, keep0, state)
            if kids:
                out.append(replace(n, children=kids))
            continue
        if state["cur"] in selected or (state["cur"] == 0 and keep0):
            out.append(n)
    return out


def _collect_refs(nodes, note_ns: Set[str], app_keys: Set[str]) -> None:
    for n in nodes:
        if isinstance(n, NoteRef):
            if n.n:
                note_ns.add(str(n.n))
        elif isinstance(n, App):
            if n.key:
                app_keys.add(n.key)
        if getattr(n, "children", None):
            _collect_refs(n.children, note_ns, app_keys)


def filter_work_juan(work: Work, segs) -> dict:
    """按卷范围过滤 Work（原地）。返回：

    `{"status": "filtered"|"full"|"no_milestone"|"empty",
      "kept": set, "all": set, "label": str}`

    - `full`：选择覆盖全部卷 → 不动（字节一致；调用方不加后缀）；
    - `filtered`：body 重放 + 裁剪 `notes_by_n`（按保留 NoteRef）与 `apps`；
    - `no_milestone`：无卷 milestone → 不动（调用方警告忽略）；
    - `empty`：与全书卷号无交集 → 不动（调用方报错）。
    """
    selected = juan_set(segs)
    all_juans = set(_milestone_juans(getattr(work, "body", [])))
    res = {"status": "no_milestone", "kept": set(), "all": all_juans,
           "label": format_juan_label(segs)}
    if not all_juans:
        return res
    if not (selected & all_juans):
        res["status"] = "empty"
        return res
    if all_juans <= selected:
        res["status"] = "full"
        res["kept"] = set(all_juans)
        return res
    keep0 = min(all_juans) in selected
    state = {"cur": 0}
    new_body = _walk_filter(getattr(work, "body", []), selected, keep0, state)
    if not new_body:
        res["status"] = "empty"
        return res
    note_ns: Set[str] = set()
    app_keys: Set[str] = set()
    _collect_refs(new_body, note_ns, app_keys)
    work.body = new_body
    work.notes_by_n = {k: v for k, v in (work.notes_by_n or {}).items()
                       if str(k) in note_ns}
    work.apps = [a for a in (work.apps or []) if a.key in app_keys]
    res["status"] = "filtered"
    res["kept"] = selected & all_juans
    return res
