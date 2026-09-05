"""IR data model for CBETA XML P5."""

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
