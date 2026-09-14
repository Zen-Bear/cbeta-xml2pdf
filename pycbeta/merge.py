"""CBReader 按卷碎片合册（输入层自动合册 + 手动脚本共用库）。

CBReader 书库布局 `XML/<CANON>/<VOL>/<canon><vol>n<no>_<seq>.xml`
（如 `T/T01/T01n0001_001.xml`），每卷一个独立 TEI；管线要按册整本
（github xml-p5 同款粒度，一册一书）。
合并规则：组内取首卷 teiHeader（charDecl 按 xml:id 并集，缺字不断），
按 (vol, seq) 拼接各卷 `<body>` 子节点（back 恒无，有则警告并丢弃），外包同一 TEI。

管线入口 `fetch.materialize_work` 三源材料化时调用 `merge_groups_to_dir`：
碎片按组合册落 work 目录（`cbeta_ebook/{id} {书名}/`，与下载整文件同处）。
目录模式（用户给目录）仍可落临时目录（`merge_groups_to_dir(groups)` 自建，随进程清）。
下游只见文件路径，零感知。
"""

import os
import re

from lxml import etree

_FRAG_RE = re.compile(r"^(?P<stem>.+?)_(?P<seq>\d+)\.xml$", re.IGNORECASE)
_STEM_RE = re.compile(r"^(?P<canon>[A-Z]+)(?P<vol>\d{2,3})[nN](?P<no>.+)$")
_TEI_NS = "http://www.tei-c.org/ns/1.0"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _norm_group(canon, vol, stem):
    """分组键（按册）：stem 含卷号（TX07n0006）→ (canon, vol, no)；
    无卷号形态回退 (canon, vol, stem) 独立成组（长度不同，永不串组）。

    >>> _norm_group("TX", "TX07", "TX07n0006")
    ('TX', 'TX07', '0006')
    >>> _norm_group("T", "T01", "appendix")
    ('T', 'T01', 'appendix')
    """
    m = _STEM_RE.match(stem)
    if m and m.group("canon").upper() == canon.upper():
        return (canon, vol, m.group("no"))
    return (canon, vol, stem)


def _only_match(only, canon, no, stems):
    """--only 命中：任一碎片 stem（如 TX07n0006）/ 归一 stem（TXn0006）/ 佛典編號（TX0006）。"""
    o = (only or "").upper()
    if not o:
        return True
    if o in {s.upper() for s in stems}:
        return True
    return o in {f"{canon}N{no}".upper(), f"{canon}{no}".upper()}


def _frag_key(path):
    """文件名 → 碎片分组键 (canon, vol, no, seq, stem)；非碎片返回 None。
    vol 取 stem 自带卷号（TX07n0006 → TX07），不依赖目录布局。"""
    m = _FRAG_RE.match(os.path.basename(path))
    if not m:
        return None
    s = _STEM_RE.match(m.group("stem"))
    if not s:
        return None
    return (s.group("canon").upper(), s.group("canon").upper() + s.group("vol"),
            s.group("no"), int(m.group("seq")), m.group("stem"))


def split_paths(paths):
    """walk 结果分区：整文件列表 + 碎片组 {(canon, vol, no): [(vol, seq, path, stem)]}。
    纯文件名判定，不读文件；无卷号形态按整文件走。"""
    whole, groups = [], {}
    for p in paths:
        k = _frag_key(p)
        if k is None:
            whole.append(p)
            continue
        canon, vol, no, seq, stem = k
        groups.setdefault((canon, vol, no), []).append((vol, seq, p, stem))
    return whole, groups


def collect(src):
    """全树收集：{(canon, vol, no): [(vol, seq, path, stem)]}。
    仅收 *_<数字>.xml 碎片（整本文件不动）；供手动脚本全量合册。"""
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


def collect_work_frags(xml_dir, canon, no):
    """某部碎片定向收集（編號流用）：{(canon, vol, no): [...]}，无则 {}。
    整文件优先由调用方先查（find_local_xml），此处只收碎片。"""
    groups = {}
    canon, no = (canon or "").upper(), (no or "").upper()
    for dp, _dn, fns in os.walk(xml_dir):
        for fn in sorted(fns):
            k = _frag_key(os.path.join(dp, fn))
            if k is None:
                continue
            c, vol, n, seq, stem = k
            if c != canon or n.upper() != no:
                continue
            groups.setdefault((c, vol, n), []).append((vol, seq, os.path.join(dp, fn), stem))
    return groups


def _find_child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _m_titles(doc):
    """各碎片 level=m 中文题名（同册内应一致；差异打印提示，取首卷）。"""
    out = []
    for e in doc.getroot().iter():
        if _local(e.tag) == "title" and e.get("level") == "m":
            lang = e.get(_XML_ID.replace("id", "lang")) or e.get("lang") or ""
            if lang.startswith("zh"):
                out.append("".join(e.itertext()).strip())
    return out


def _union_chardecl(header, docs):
    """charDecl 按 xml:id 跨卷并集（首卷 header 为准，后卷补缺；各卷一致时等同首卷）。
    否则首卷无 charDecl 而后卷有（如 TX0006 的 CB16748 在 015 卷），合册丢缺字声明。"""
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


def merge(files, out_path, quiet=False):
    """files: [(vol, seq, path, stem)]；按 (vol, seq) 排序拼接。返回 (卷数, body 子节点数)。
    quiet=True 时压住题名/charDecl 提示（管线内调用；手动脚本默认 False）。"""
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
    if not quiet:
        titles = {_t for d in docs for _t in _m_titles(d)}
        if len(titles) > 1:
            print(f"  提示：各卷题名卷范围各异（{len(titles)} 种），取首卷（元数据噪声，不影响正文）")
    n_char = _union_chardecl(header, docs) if header is not None else 0
    if n_char and not quiet:
        print(f"  charDecl 跨卷并集：后卷补 {n_char} 字")
    if not quiet:
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


def _dest_for(root, canon, vol, stem):
    # 平展：{stem}.xml 直接落 root（work 目录内一部多册各自成文件，同下载布局）
    return os.path.join(root, stem + ".xml")


def _ensure_tmpdir(tmpdir=None):
    """调用方未给目录时自建（atexit 随进程清；目录模式用）。返回 tmpdir。"""
    if tmpdir:
        return tmpdir
    import tempfile
    import atexit
    import shutil
    tmpdir = tempfile.mkdtemp(prefix="xml2pdf-merge-")
    atexit.register(shutil.rmtree, tmpdir, True)
    return tmpdir


def merge_groups_to_dir(groups, dest_root=None, quiet=True):
    """碎片组 → 平展落盘（`{stem}.xml` 直接放 root；按组键排序），返回路径列表。

    dest_root=None 时自建临时目录（随进程清，目录模式用）；材料化时传 work 目录
    （`cbeta_ebook/{id} {书名}/`，与下载整文件/基线同目录）。"""
    dest_root = _ensure_tmpdir(dest_root)
    out = []
    for key in sorted(groups):
        files = sorted(groups[key])
        canon, vol = key[0], key[1]
        stem0 = files[0][3]
        dest = _dest_for(dest_root, canon, vol, stem0)
        merge(files, dest, quiet=quiet)
        out.append(dest)
    return out
