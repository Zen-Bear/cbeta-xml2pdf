"""CBETA XML P5 parser: XML -> IR (Work)."""

import re
from typing import Dict, List, Optional

from lxml import etree

from .model import App, AppRead, E, Gaiji, Lb, Note, NoteRef, Pb, Text, Work
from .names import get_work_id_from_basename

NS_TEI = "http://www.tei-c.org/ns/1.0"
NS_CB = "http://www.cbeta.org/ns/1.0"
NS_XML = "http://www.w3.org/XML/1998/namespace"

WIT_RE = re.compile(r"^#(.*)$")
NEWLINE_RE = re.compile(r"[\n\r]")


def _localname(tag) -> str:
    if isinstance(tag, str):
        return etree.QName(tag).localname
    return ""


def _attr_key(key: str) -> str:
    if key.startswith("{"):
        uri, local = key[1:].split("}", 1)
        if uri == NS_XML:
            return "xml:" + local
        if uri == NS_CB:
            return "cb:" + local
        return local
    return key


def _norm_text(s: str) -> str:
    return s.replace("\r", "")


class P5Parser:
    def __init__(self, gaiji_db=None):
        self.gaiji_db = gaiji_db

    def parse(self, xml_fn: str) -> Work:
        self.xml_fn = xml_fn
        tree = etree.parse(xml_fn)
        root = tree.getroot()
        self.root = root
        self._strip_ns(root)

        self._wit: Dict[str, str] = {}
        self._resp: Dict[str, str] = {}
        self._notes: Dict[str, List[Note]] = {}
        self._apps: List[App] = []
        self._apps_by_key: Dict[str, App] = {}
        self._current_lb: Optional[str] = None
        self._seen_ref_n = set()

        header = root.find("teiHeader")
        self.metadata = self._parse_header(header) if header is not None else {}
        xml_id = self._get(root, "xml:id", "id") or ""
        self._canon = self._canon_from(xml_id or self._basename(xml_fn))
        body = root.find("text/body")
        back = root.find("text/back")
        self._collect_back(back)
        self.body = self._traverse(body) if body is not None else []
        self._backfill()
        self.metadata["docNumber"] = self._find_docnumber(self.body)

        work_id = get_work_id_from_basename(xml_id or self._basename(xml_fn))
        work_id = get_work_id_from_basename(xml_id or self._basename(xml_fn))
        return Work(id=work_id, source_file=xml_fn, metadata=self.metadata,
                    body=self.body, notes_by_n=self._notes, apps=self._apps)

    @staticmethod
    def _find_docnumber(nodes) -> Optional[str]:
        """body 中第一个 <docNumber> 元素的全文文本（校验剥离用）。"""
        for n in nodes:
            if isinstance(n, E) and n.tag == "docNumber":
                return "".join(getattr(c, "text", "") or "" for c in n.children if isinstance(c, Text)).strip()
            if getattr(n, "children", None):
                r = P5Parser._find_docnumber(n.children)
                if r is not None:
                    return r
        return None

    @staticmethod
    def _basename(path: str) -> str:
        return path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1][:-4]

    @staticmethod
    def _canon_from(fn: str) -> Optional[str]:
        from .names import get_canon_id_from_work_id
        return get_canon_id_from_work_id(fn)

    @staticmethod
    def _strip_ns(el):
        for e in el.iter():
            if isinstance(e.tag, str):
                e.tag = etree.QName(e).localname

    @staticmethod
    def _attrs(el) -> Dict[str, str]:
        return {_attr_key(k): v for k, v in el.attrib.items()}

    def _get(self, el, *names) -> Optional[str]:
        attrs = self._attrs(el)
        for n in names:
            if n in attrs:
                return attrs[n]
        return None

    def _parse_header(self, teiHeader) -> Dict[str, object]:
        md: Dict[str, object] = {}
        xml_id = self._get(self.root, "xml:id", "id")
        md["id"] = get_work_id_from_basename(xml_id or "") if xml_id else None
        md["charDecl"] = self._parse_chardecl(teiHeader)

        for w in teiHeader.iter("witness"):
            wid = self._get(w, "xml:id", "id")
            if wid:
                self._wit["#" + wid] = "".join(w.itertext()).strip()
        for rs in teiHeader.iter("respStmt"):
            rid = self._get(rs, "xml:id", "id")
            if rid:
                name = rs.find("name")
                self._resp["#" + rid] = "".join(name.itertext()).strip() if name is not None else ""

        def text_of(tag):
            el = teiHeader.find(tag)
            return "".join(el.itertext()).strip() if el is not None else None

        title = None
        series = None
        ts = teiHeader.find("fileDesc/titleStmt")
        if ts is not None:
            titles = ts.findall("title")
            def _lang(t):
                return t.get("{%s}lang" % NS_XML) or t.get("lang") or ""
            for t in titles:
                if t.get("level") == "m" and _lang(t).startswith("zh"):
                    title = "".join(t.itertext()).strip()
                    break
            if title is None:
                for t in titles:
                    if t.get("level") == "m":
                        title = "".join(t.itertext()).strip()
                        break
            if title is None and titles:
                title = "".join(titles[0].itertext()).strip()
            for t in titles:
                if t.get("level") == "s" and _lang(t).startswith("zh"):
                    series = "".join(t.itertext()).strip()
                    break
            if series is None:
                for t in titles:
                    if t.get("level") == "s":
                        series = "".join(t.itertext()).strip()
                        break
        md["title"] = title
        md["series"] = series

        author = teiHeader.find("fileDesc/titleStmt/author")
        md["author"] = "".join(author.itertext()).strip() if author is not None else None
        md["extent"] = text_of("fileDesc/extent")

        idno = teiHeader.find("fileDesc/publicationStmt/idno")
        if idno is not None:
            canon = idno.findtext("idno[@type='canon']")
            vol = idno.findtext("idno[@type='vol']")
            no = idno.findtext("idno[@type='no']")
            md["canon"] = (canon or "").strip()
            md["vol"] = (vol or "").strip()
            md["no"] = (no or "").strip()

        pb = teiHeader.find("fileDesc/publicationStmt")
        pub_date = None
        publisher = None
        if pb is not None:
            d = pb.find("date")
            pub_date = "".join(d.itertext()).strip() if d is not None else None
            dist = pb.find("distributor/name")
            publisher = "".join(dist.itertext()).strip() if dist is not None else None
        md["publication_date"] = pub_date
        md["publisher"] = publisher

        src = teiHeader.find("fileDesc/sourceDesc")
        md["source"] = "".join(src.itertext()).strip() if src is not None else None

        pd = teiHeader.find("encodingDesc/projectDesc")
        contributors = None
        if pd is not None:
            for p in pd.findall("p"):
                if (self._get(p, "xml:lang", "lang") or "").startswith("zh"):
                    contributors = "".join(p.itertext()).strip()
        md["contributors"] = contributors

        punct = teiHeader.find("encodingDesc/editorialDecl/punctuation")
        if punct is not None:
            md["punctuation"] = "".join(punct.itertext()).strip()
            md["punctuation_resp"] = self._resolve(punct.get("resp"))

        rev = []
        for ch in teiHeader.iter("change"):
            when = ch.get("when")
            who = " ".join(n.text or "" for n in ch.findall("name")).strip()
            what = "".join(ch.itertext()).strip()
            rev.append({"when": when, "who": who, "what": what})
        md["revision"] = rev
        return md

    @staticmethod
    def _parse_chardecl(teiHeader) -> Dict[str, dict]:
        out = {}
        cd = teiHeader.find("encodingDesc/charDecl")
        if cd is None:
            cd = teiHeader.find("charDecl")
        if cd is None:
            return out
        for ch in cd.iter("char"):
            # xml:id 为命名空间属性（_strip_ns 只剥标签命名空间），须显式取 NS_XML
            cid = ch.get("{%s}id" % NS_XML) or ch.get("xml:id") or ch.get("id") or ""
            cid = cid.lstrip("#")
            if not cid:
                continue
            rec: Dict[str, str] = {}
            for cp in ch.iter("charProp"):
                ln = cp.findtext("localName") or ""
                val = cp.findtext("value")
                if ln == "composition":
                    rec["composition"] = val or ""
                elif ln == "rjchar":
                    # 悉昙字显示用字（常规汉字，如 RJ-CCBA→屇；官方 docx 用它+Ranjana 字体，不用 PUA）
                    rec["rjchar"] = val or ""
                elif ln == "Romanized form in Unicode transcription":
                    # 悉昙读音（官方 docx 正文/注释均附，如 RJ-CCEB→raṃ）；docx 渲染用
                    rec["roman"] = val or ""
                elif ln == "Romanized form in CBETA transcription":
                    rec["roman_cbeta"] = val or ""
                elif ln == "normalized form":
                    rec["normal"] = val or ""
            for m in ch.iter("mapping"):
                t = m.get("type")
                if t == "unicode":
                    rec["unicode"] = (m.text or "").replace("U+", "")
                elif t == "PUA":
                    rec["pua"] = m.text or ""
            out[cid] = rec
        return out

    def _resolve(self, ref: Optional[str]) -> Optional[str]:
        if not ref:
            return None
        if WIT_RE.match(ref):
            return self._resp.get(ref, ref)
        return ref

    def _collect_back(self, back):
        if back is None:
            return
        for el in back.iter():
            if not isinstance(el.tag, str):
                continue
            if el.tag == "note":
                note = self._parse_note(el)
                self._notes.setdefault(note.n, []).append(note)
            elif el.tag == "app":
                app = self._parse_app(el)
                self._apps.append(app)
                if app.key:
                    self._apps_by_key[app.key] = app

    def _parse_note(self, el) -> Note:
        n = el.get("n")
        resp = self._resolve(el.get("resp"))
        note = Note(
            tag="note",
            attrs=self._attrs(el),
            n=n,
            ntype=el.get("type"),
            place=el.get("place"),
            subtype=el.get("subtype"),
            resp=resp,
            note_key=self._get(el, "note_key", "cb:note_key"),
        )
        note.children = self._traverse(el)
        return note

    def _parse_app(self, el) -> App:
        frm = el.get("from") or ""
        key = frm.lstrip("#") or None
        app = App(tag="app", attrs=self._attrs(el), key=key, atype=el.get("type"))
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child.tag == "lem":
                app.lem = self._parse_app_read(child, "lem")
            elif child.tag == "rdg":
                app.rdgs.append(self._parse_app_read(child, "rdg"))
        return app

    def _parse_app_read(self, el, role: str) -> AppRead:
        wit_refs = (el.get("wit") or "").split()
        wit = [self._wit.get(ref, ref) for ref in wit_refs]
        r = AppRead(
            tag=role,
            attrs=self._attrs(el),
            role=role,
            wit=wit,
            resp=self._resolve(el.get("resp")),
            rtype=el.get("type"),
        )
        r.children = self._traverse(el)
        return r

    def _traverse(self, el) -> List[object]:
        nodes: List[object] = []
        t = _norm_text(el.text or "")
        if t:
            nodes.append(Text(t, line=self._current_lb))
        for child in el:
            if not isinstance(child.tag, str):
                # <!-- --> 等注释节点：本身跳过，但其 tail 为逗号后的正文（_handle 不会处理）
                if child.tail:
                    t2 = _norm_text(child.tail)
                    if t2:
                        nodes.append(Text(t2, line=self._current_lb))
                continue
            nodes.extend(self._handle(child))
        return nodes

    def _handle(self, el) -> List[object]:
        tag = el.tag
        out: List[object] = []
        if tag == "lb":
            ed = el.get("ed")
            lb = Lb(n=el.get("n") or "", ed=ed, lbtype=el.get("type"))
            out.append(lb)
            if lb.lbtype != "old" and (not ed or ed == self._canon):
                self._current_lb = lb.n
        elif tag == "pb":
            out.append(Pb(n=el.get("n"), ed=el.get("ed")))
        elif tag == "g":
            code = (el.get("ref") or "").lstrip("#")
            char = "".join(el.itertext()).strip() or None
            if not char and self.gaiji_db is not None:
                data = self.gaiji_db.get(code)
                if data:
                    char = data.get("uni_char") or data.get("composition")
            out.append(Gaiji(code=code, char=char))
        elif tag == "anchor":
            aid = self._get(el, "xml:id", "id")
            if aid and aid.startswith("nkr_note_"):
                n = el.get("n")
                if n and n not in self._seen_ref_n:
                    self._seen_ref_n.add(n)
                    out.append(NoteRef(n=n))
            elif aid and aid.startswith("beg"):
                app = self._apps_by_key.get(aid)
                if app is not None:
                    out.append(app)
            elif aid and aid.startswith("end"):
                pass
            elif el.get("type") == "circle":
                out.append(E(tag="anchor", attrs=self._attrs(el)))
        elif tag == "note":
            out.append(self._parse_note(el))
        else:
            out.append(E(tag=tag, attrs=self._attrs(el), children=self._traverse(el)))
        tail = _norm_text(el.tail or "")
        if tail:
            out.append(Text(tail, line=self._current_lb))
        return out

    def _backfill(self):
        for node in self._iter_nodes(self.body):
            if isinstance(node, NoteRef):
                node.notes = self._notes.get(node.n, [])

    @staticmethod
    def _iter_nodes(nodes):
        for node in nodes:
            yield node
            if isinstance(node, App):
                if node.lem is not None:
                    yield from P5Parser._iter_nodes([node.lem])
                yield from P5Parser._iter_nodes(node.rdgs)
            if getattr(node, "children", None):
                yield from P5Parser._iter_nodes(node.children)
