"""IR data model for CBETA XML P5."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Node:
    pass


@dataclass
class Text(Node):
    text: str = ""
    line: Optional[str] = None


@dataclass
class Lb(Node):
    n: str = ""
    ed: Optional[str] = None
    lbtype: Optional[str] = None


@dataclass
class Pb(Node):
    n: Optional[str] = None
    ed: Optional[str] = None


@dataclass
class Gaiji(Node):
    code: str = ""
    char: Optional[str] = None


@dataclass
class E(Node):
    tag: str = ""
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List[Node] = field(default_factory=list)


@dataclass
class Note(E):
    n: Optional[str] = None
    ntype: Optional[str] = None
    place: Optional[str] = None
    subtype: Optional[str] = None
    resp: Optional[str] = None
    note_key: Optional[str] = None


@dataclass
class NoteRef(Node):
    n: Optional[str] = None
    notes: List[Note] = field(default_factory=list)


@dataclass
class App(E):
    key: Optional[str] = None
    atype: Optional[str] = None
    lem: Optional["AppRead"] = None
    rdgs: List["AppRead"] = field(default_factory=list)


@dataclass
class AppRead(E):
    role: str = ""
    wit: List[str] = field(default_factory=list)
    resp: Optional[str] = None
    rtype: Optional[str] = None


@dataclass
class Work:
    id: str
    source_file: str
    metadata: Dict[str, object]
    body: List[Node]
    notes_by_n: Dict[str, List[Note]]
    apps: List[App]
    simplified: bool = False  # simplify_work 置位后，渲染时解析的缺字同样过 t2s 管线


def _base_n(n: str) -> str:
    """校勘编号去掉尾部小写 a/b 后缀（CBETA：小写 a、b 是一个校勘条目拆成二组；
    大写 A、B 是内文两处相同编号，不参与合并）。"""
    return re.sub(r"[a-z]+$", "", n or "")


def suppressed_orig_notes(notes_by_n) -> set:
    """docx/txt/md 口径：整体 `type="orig"` 注若其 base n 存在 `type="mod"`（拆分成
    a/b 的现代形式），则不单独出注（官方 docx/txt 只出拆分后的 mod；html/epub 不调用）。"""
    mod_bases = set()
    for n, notes in (notes_by_n or {}).items():
        if n and any(nt.ntype == "mod" for nt in notes):
            mod_bases.add(n)
            mod_bases.add(_base_n(n))
    out = set()
    for n, notes in (notes_by_n or {}).items():
        if not n:
            continue
        if any(nt.ntype == "mod" for nt in notes):
            continue
        if not any(nt.ntype == "orig" for nt in notes):
            continue
        if _base_n(n) in mod_bases:
            out.add(n)
    return out
