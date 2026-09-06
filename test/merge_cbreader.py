"""CBReader 按卷碎片合并为整本 P5 XML（本地一次性工具）。

CBReader 书库布局 `XML/<CANON>/<VOL>/<canon><vol>n<no>_<seq>.xml`
（如 `T/T01/T01n0001_001.xml`…`_022.xml`），每卷一个独立 TEI；
本管线要整本（`{canon}{vol}n{no}.xml`，github xml-p5 同款）。
合并规则：取首卷 teiHeader，按序号拼接各卷 `<body>` 子节点，外包同一 TEI；
落盘 `<out>/<CANON>/<VOL>/<stem>.xml`（VOL 自带部名，如 T01；find_local_xml 仓库布局可直接命中）。
输出比输入新则跳过（除非 --force）。

用例：
  python test/merge_cbreader.py --only T01n0001 -o E:\\dev\\cbeta\\test\\_cbreader
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
_TEI_NS = "http://www.tei-c.org/ns/1.0"


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def collect(src):
    """{stem: [(seq, path)]}，仅收 *_<数字>.xml 碎片（整本文件不动）。"""
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
                groups.setdefault((canon, vol, m.group("stem")), []).append(
                    (int(m.group("seq")), os.path.join(vdir, fn)))
    return groups


def merge(files, out_path):
    """files: [(seq, path)] 有序；返回 (卷数, body 子节点数)。"""
    files = sorted(files)
    if os.path.isfile(out_path) and os.path.getmtime(out_path) >= max(
            os.path.getmtime(p) for _, p in files):
        return None  # 最新，跳过
    docs = []
    for _, p in files:
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
    ap.add_argument("--only", default="", help="只合某本（如 T01n0001）")
    ap.add_argument("--force", action="store_true", help="输出已最新也重写")
    args = ap.parse_args(argv)
    n_work, n_skip = 0, 0
    for (canon, vol, stem), files in sorted(collect(args.src).items()):
        if args.canon and canon.upper() != args.canon.upper():
            continue
        if args.only and stem.upper() != args.only.upper():
            continue
        out = os.path.join(args.out, canon, vol, f"{stem}.xml")
        if not args.force and os.path.isfile(out) and os.path.getmtime(out) >= max(
                os.path.getmtime(p) for _, p in files):
            n_skip += 1
            continue
        got = merge(files, out)
        if got is None:
            n_skip += 1
            continue
        n_work += 1
        print(f"{stem}: {got[0]} 卷 → {out}（body 子节点 {got[1]}）")
    print(f"done: 合并 {n_work} 本，跳过 {n_skip} 本（已最新）。")


if __name__ == "__main__":
    main()
