# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""verify_text.py 的公共逻辑：规范化、提取、比对。"""
import difflib, glob, os, re, zipfile
from pycbeta.names import get_work_id_from_basename

_LINEHEAD_RE = re.compile(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+")

_LINEHEAD_RE = re.compile(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+")
_NOTE_MARK_RE = re.compile(r"\[[^\]\[]{1,8}\]")
_LABEL_RE = re.compile(r"\u3010[^\u3011]{1,20}\u3011")
_BRACKET_RE = re.compile(r"\u3014[^\u3015]{1,20}\u3015")
_WS_RE = re.compile(r"[\s\u3000]+")
_TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(xml_text):
    xml_text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", xml_text, flags=re.S)
    return _TAG_RE.sub("", xml_text)


def normalize(text):
    text = _LINEHEAD_RE.sub("", text)
    text = _NOTE_MARK_RE.sub("", text)
    text = _LABEL_RE.sub("", text)
    text = _BRACKET_RE.sub("", text)
    return _WS_RE.sub("", text)


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub":
        parts = []
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith((".xhtml", ".html")):
                    parts.append(strip_tags(z.read(n).decode("utf-8", "replace")))
        return "".join(parts)
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            return strip_tags(z.read("word/document.xml").decode("utf-8"))
    if ext in (".html", ".xhtml", ".htm"):
        return strip_tags(open(path, encoding="utf-8", errors="replace").read())
    if ext == ".odt":
        with zipfile.ZipFile(path) as z:
            return strip_tags(z.read("content.xml").decode("utf-8"))
    return open(path, encoding="utf-8", errors="replace").read()


def diff_stats(a, b):
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    matched = sum(op.size for op in sm.get_matching_blocks())
    missing = len(a) - matched
    extra = len(b) - matched
    ctx = [(op[0], op[1], op[2], op[3], op[4])
           for op in sm.get_opcodes() if op[0] != "equal"][:5]
    return matched, missing, extra, ctx


def find_official(source, stem, kind):
    short = get_work_id_from_basename(stem)
    stems = list(dict.fromkeys([stem, short]))
    pats = []
    for s in stems:
        if kind == "txt":
            pats += [os.path.join(source, f"{s}.txt", "*.txt"),
                     os.path.join(source, f"{s}.txt")]
            continue
        pats.append(os.path.join(source, f"{s}*.{kind}"))
    out = []
    seen = set()
    for pat in pats:
        for f in sorted(glob.glob(pat)):
            af = os.path.abspath(f)
            if af not in seen and os.path.isfile(af) and os.path.getsize(af) > 0:
                seen.add(af)
                out.append(af)
    return out
