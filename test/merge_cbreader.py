"""CBReader 按卷碎片合并为整本 P5 XML（本地一次性工具）。

CBReader 书库布局 `XML/<CANON>/<VOL>/<canon><vol>n<no>_<seq>.xml`
（如 `T/T01/T01n0001_001.xml`…`_022.xml`），每卷一个独立 TEI；
本管线要整本（github xml-p5 同款）。
合并规则：取首卷 teiHeader（charDecl 按 xml:id 跨卷并集，缺字不断），
按 (vol, seq) 拼接各卷 `<body>` 子节点（back 恒无，有则警告并丢弃），外包同一 TEI；
落盘：同 stem 单卷沿旧例 `<out>/<CANON>/<VOL>/<stem>.xml`；
跨册（同 (canon, no) 多 stem，如 TX0006 跨 TX07-TX09）落首卷目录、
沿首卷 stem（如 `TX/TX07/TX07n0006.xml`，work id 照旧 TX0006，零管线改动；
题名卷范围取首卷，属元数据噪声，打印提示）。
输出比输入新则跳过（除非 --force）。

用例：
  python test/merge_cbreader.py --only T01n0001 -o E:\\dev\\cbeta\\test\\_cbreader
  python test/merge_cbreader.py --only TX0006 -o E:\\dev\\cbeta\\test\\_cbreader
  python test/merge_cbreader.py --canon T -o E:\\dev\\cbeta\\test\\_cbreader
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree

SRC = r"E:\CBETA\CBReader2X\Bookcase\CBETA\XML"

_FRAG_RE = re.compile(r"^(?P<stem>.+?)_(?P<seq>\d+)\.xml$", re.IGNORECASE)
_STEM_RE = re.compile(r"^(?P<canon>[A-Z]+)(?P<vol>\d{2,3})[nN](?P<no>.+)$")
_TEI_NS = "http://www.tei-c.org/ns/1.0"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _norm_group(canon, vol, stem):
    """分组键：stem 含卷号（TX07n0006）→ (canon, no) 跨册归一；
    无卷号形态回退旧键 (canon, vol, stem) 独立成组（长度不同，永不串组）。

    >>> _norm_group("TX", "TX07", "TX07n0006")
    ('TX', '0006')
    >>> _norm_group("T", "T01", "appendix")
    ('T', 'T01/appendix')
    """
    m = _STEM_RE.match(stem)
    if m and m.group("canon").upper() == canon.upper():
        return (canon, m.group("no"))
    return (canon, vol + "/" + stem)


def _only_match(only, canon, no, stems):
    """--only 命中：任一碎片 stem（如 TX07n0006）/ 归一 stem（TXn0006）/ 佛典編號（TX0006）。"""
    o = (only or "").upper()
    if not o:
        return True
    if o in {s.upper() for s in stems}:
        return True
    return o in {f"{canon}N{no}".upper(), f"{canon}{no}".upper()}


def collect(src):
    """{(canon, no): [(vol, seq, path, stem)]}，仅收 *_<数字>.xml 碎片（整本文件不动）。"""
    groups = {}
    for canon in sorted(os.listdir(src)):
        cdir = os.path.join(src, canon)
        if not os.path.isdir(cdir):
            continue
        for vol in sorted(os.listdir(cdir)):
            vdir = os.path.join(cdir, vol)
            if not os.path.isdir(vdir):
                continue
            for fn in sorted(os.listdir(vdir)):
                m = _FRAG_RE.match(fn)
                if not m:
                    continue
                stem = m.group("stem")
                groups.setdefault(_norm_group(canon, vol, stem), []).append(
                    (vol, int(m.group("seq")), os.path.join(vdir, fn), stem))
    return groups


def _find_child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _m_titles(doc):
    """各碎片 level=m 中文题名（跨册时卷范围各异，取首卷，差异打印提示）。"""
    out = []
    for e in doc.getroot().iter():
        if _local(e.tag) == "title" and e.get("level") == "m":
            lang = e.get(_XML_ID.replace("id", "lang")) or e.get("lang") or ""
            if lang.startswith("zh"):
                out.append("".join(e.itertext()).strip())
    return out


def _union_chardecl(header, docs):
    """charDecl 按 xml:id 跨卷并集（首卷 header 为准，后卷补缺；各卷一致时等同首卷）。
    否则首卷无 charDecl 而后卷有（如 TX0006 的 CB16748 在 015 卷），合部丢缺字声明。"""
    target = None
    enc = _find_child(header, "encodingDesc")
    if enc is not None:
        target = _find_child(enc, "charDecl")
    seen = set()
    if target is not None:
        for ch in target.iter():
            if _local(ch.tag) == "char":
                cid = ch.get(_XML_ID) or ch.get("id")
                if cid:
                    seen.add(cid)
    added = 0
    for doc in docs:
        for cd in (e for e in doc.getroot().iter() if _local(e.tag) == "charDecl"):
            for ch in list(cd):
                if _local(ch.tag) != "char":
                    continue
                cid = ch.get(_XML_ID) or ch.get("id")
                if cid and cid not in seen:
                    if target is None:
                        if enc is None:
                            enc = etree.SubElement(header, f"{{{_TEI_NS}}}encodingDesc")
                        target = etree.SubElement(enc, f"{{{_TEI_NS}}}charDecl")
                    target.append(ch)
                    seen.add(cid)
                    added += 1
    return added


def _warn_backs(files, docs):
    """碎片若有 text/back 实质内容，合并会丢弃——打印警告（现行 body-only 语义不变）。"""
    hit = []
    for (_, _, p, _), doc in zip(files, docs):
        for e in doc.getroot().iter():
            if _local(e.tag) == "back" and len(e):
                hit.append(p)
                break
    if hit:
        print(f"  警告：{len(hit)} 碎片含 <back> 实质内容，合并丢弃（body-only）："
              f"{os.path.basename(hit[0])} 等")
    return hit


def merge(files, out_path):
    """files: [(vol, seq, path, stem)]；按 (vol, seq) 排序拼接。返回 (卷数, body 子节点数)。"""
    files = sorted(files)
    if os.path.isfile(out_path) and os.path.getmtime(out_path) >= max(
            os.path.getmtime(p) for _, _, p, _ in files):
        return None  # 最新，跳过
    docs = []
    for _, _, p, _ in files:
        docs.append(etree.parse(p, etree.XMLParser(remove_blank_text=False,
                                                   resolve_entities=False)))
    first = docs[0].getroot()
    nsmap = dict(first.nsmap)
    tei = etree.Element(f"{{{_TEI_NS}}}TEI", nsmap=nsmap or None)
    for attr, val in first.attrib.items():
        tei.set(attr, val)
    header = first.find(f"{{{_TEI_NS}}}teiHeader")
    if header is not None:
        tei.append(header)
    titles = {_t for d in docs for _t in _m_titles(d)}
    if len(titles) > 1:
        print(f"  提示：各卷题名卷范围各异（{len(titles)} 种），取首卷（元数据噪声，不影响正文）")
    n_char = _union_chardecl(header, docs) if header is not None else 0
    if n_char:
        print(f"  charDecl 跨卷并集：后卷补 {n_char} 字")
    _warn_backs(files, docs)
    text = etree.SubElement(tei, f"{{{_TEI_NS}}}text")
    body = etree.SubElement(text, f"{{{_TEI_NS}}}body")
    count = 0
    for doc in docs:
        b = doc.getroot().find(f"{{{_TEI_NS}}}text/{{{_TEI_NS}}}body")
        if b is None:  # 容错：根下直找 body（忽略命名空间写法差异）
            b = next((e for e in doc.getroot().iter()
                      if _local(e.tag) == "body"), None)
        if b is None:
            raise ValueError(f"no <body>: {doc.docinfo.URL}")
        for child in b:
            body.append(child)
            count += 1
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tree = etree.ElementTree(tei)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return len(files), count


def main(argv=None):
    ap = argparse.ArgumentParser(description="合并 CBReader 按卷碎片为整本")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("-o", "--out", required=True, help="落盘根目录")
    ap.add_argument("--canon", default="", help="只合某部（如 T），空=全部")
    ap.add_argument("--only", default="", help="只合某本（碎片 stem 如 T01n0001 / 归一 TXn0006 / 佛典編號如 TX0006）")
    ap.add_argument("--force", action="store_true", help="输出已最新也重写")
    args = ap.parse_args(argv)
    n_work, n_skip = 0, 0
    for (canon, no), files in sorted(collect(args.src).items()):
        if args.canon and canon.upper() != args.canon.upper():
            continue
        files = sorted(files)
        stems = {s for _, _, _, s in files}
        if not _only_match(args.only, canon, no, stems):
            continue
        if len(stems) == 1:
            # 同 stem（旧行为原样）：<out>/<CANON>/<VOL>/<stem>.xml
            vol0, _, _, stem0 = files[0]
            out = os.path.join(args.out, canon, vol0, f"{stem0}.xml")
            label = stem0
        else:
            # 跨册：落首卷目录、沿首卷 stem（work id 不变，零管线改动）
            vol0, _, _, stem0 = files[0]
            out = os.path.join(args.out, canon, vol0, f"{stem0}.xml")
            label = f"{canon}n{no}（跨册：{len(stems)} stem→{stem0}，{len(files)} 碎片）"
        if not args.force and os.path.isfile(out) and os.path.getmtime(out) >= max(
                os.path.getmtime(p) for _, _, p, _ in files):
            n_skip += 1
            continue
        got = merge(files, out)
        if got is None:
            n_skip += 1
            continue
        n_work += 1
        print(f"{label}: {got[0]} 卷 → {out}（body 子节点 {got[1]}）")
    print(f"done: 合并 {n_work} 本，跳过 {n_skip} 本（已最新）。")


if __name__ == "__main__":
    main()
