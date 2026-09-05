"""CBETA ID rules (canon / vol / work / linehead), ported from ruby-cbeta cbeta.rb."""

import re

CANON = r"(?:CC|DA|GA|GB|LC|TX|YP|ZS|ZW|[A-Z])"
SORT_ORDER = ["T", "X", "A", "K", "S", "F", "C", "D", "U", "P", "J", "L", "G", "M", "N",
              "ZS", "I", "ZW", "B", "GA", "GB", "Y", "LC", "TX", "YP", "CC"]
VOL3 = ["A", "CC", "C", "G", "GA", "GB", "L", "M", "P", "U"]
WORK_PART = r"(?:\d{4}[a-zA-Z]?|[ABa]\d{3})"
BASENAME = re.compile(rf"\A{CANON}\d{{2,3}}n{WORK_PART}\Z")
CANON_ID = re.compile(rf"\A{CANON}\Z")
WORK_ID = re.compile(rf"\A{CANON}{WORK_PART}\Z")


def get_canon_id_from_work_id(work: str) -> Optional[str]:
    m = re.match(rf"^({CANON})", work)
    return m.group(1) if m else None


def get_canon_from_vol(vol: str) -> Optional[str]:
    m = re.match(rf"^({CANON})", vol)
    return m.group(1) if m else None


def normalize_vol(vol: str) -> str:
    m = re.match(rf"^({CANON})(.*)$", vol)
    if not m:
        raise ValueError(f"unknown vol format: {vol}")
    canon, num = m.group(1), m.group(2)
    length = 3 if canon in VOL3 else 2
    return canon + num.rjust(length, "0")


def get_work_id_from_basename(fn: str) -> str:
    m = re.match(rf"^({CANON})\d{{2,3}}n(.*)$", fn)
    r = (m.group(1) + m.group(2)) if m else fn
    if r.startswith("T0220"):
        r = "T0220"
    return r


def get_linehead(file_basename: str, lb: str) -> Optional[str]:
    if file_basename is None:
        return None
    r = re.match(r"^(T\d\dn0220)", file_basename)
    base = r.group(1) if r else file_basename
    base += "_" if re.search(r"\d$", base) else ""
    return base + "p" + lb


def get_sort_order_from_canon_id(canon: str) -> Optional[str]:
    try:
        i = SORT_ORDER.index(canon)
    except ValueError:
        return None
    return chr(ord("A") + i)
