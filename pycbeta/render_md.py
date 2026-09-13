"""Markdown renderer: IR -> Markdown text.

Notes: inline -> （…）; footnote/endnote -> Markdown footnotes [^n].
"""

import os
import re
from contextlib import contextmanager
from typing import List, Optional

from .model import App, E, Gaiji, Lb, Note, NoteRef, Pb, Text, Work, \
    suppressed_orig_notes
from .annotate import active as _ann_active, split_annotated as _split_ann, track_seen as _track_seen
from .gaiji import GaijiDb
from .theme import Theme, strip_head_no, bracket_pair


class MdRenderer:
    def __init__(self, gaiji_db=None, theme=None, notes="endnote", show_notes=True, inline_brackets="fullwidth",
                 note_inline_brackets=None,
                 annotations=None, strip_head_no=False, show_dharani_transliteration=False):
        self.gaiji_db = gaiji_db if gaiji_db is not None else GaijiDb()
        self.theme = theme if theme is not None else Theme()
        self.notes = notes  # 'footnote' | 'endnote' | 'inline'
        self.show_notes = show_notes
        self.inline_brackets = inline_brackets  # 正文夹注（place=inline，原文）括号
        self.note_inline_brackets = note_inline_brackets or inline_brackets  # 校注内联括号（缺省回退）
        self.strip_head_no = strip_head_no  # 去 head/jhead 行首 No. 令牌（默认 false 保留）
        self.show_dharani_transliteration = show_dharani_transliteration  # 逐字咒文表（无 place="inline"）转写（默认 false 去掉，官方 txt 一致）
        # 难字注音（P6）：None 或 {"table", "scheme"}；md 无 ruby，用〔注音〕括注
        # （不用（），避免与校勘记 inline 括号混淆；verify 侧 normalize 已剥除〔〕）
        self._annotations = _ann_active(annotations)
        self._ann_seen = set()  # repeat first/page 已注词集合（render_work 起始终置零；md 单文件，page 等同 first）
        self._work = None
        self._fn_seq = 0
        self._fn_notes: List[str] = []
        self._div_depth = 0
        self._drop_sa = False  # 逐字咒文表 `<cb:tt>`（无 place="inline"）内：转写默认不显示

    @contextmanager
    def _no_ann(self):
        """标题/题署块内压制注音（P6：仅正文 Text 注音，head/byline/juan/jhead/docNumber 不注）。"""
        save = self._annotations
        self._annotations = None
        try:
            yield
        finally:
            self._annotations = save

    def render_work(self, work: Work, out_dir: str, filename: str = "") -> str:
        self._work = work
        self._ann_seen = set()
        self._fn_seq = 0
        self._fn_notes = []
        self._app_by_n = {}
        for n in self._iter_all(work.body):
            if isinstance(n, App) and n.key:
                self._app_by_n[n.key[3:]] = n
        self._orig_suppressed = suppressed_orig_notes(work.notes_by_n)
        md = work.metadata
        title = md.get("title") or work.id
        author = md.get("author") or ""
        body = self._render_body(work.body)
        fns = "\n\n".join(f"[^{i}]: {c}" for i, c in enumerate(self._fn_notes, 1))
        text = f"# {title}\n\n{author}\n\n{body}"
        if fns:
            text += "\n\n## 校注\n\n" + fns
        text = text.rstrip() + "\n"
        os.makedirs(out_dir, exist_ok=True)
        if not filename:
            filename = f"{work.id}.md"
        fn = os.path.join(out_dir, filename)
        with open(fn, "w", encoding="utf-8") as f:
            f.write(text)
        return fn

    def _iter_all(self, nodes):
        for n in nodes:
            yield n
            if isinstance(n, App):
                if n.lem is not None:
                    yield from self._iter_all([n.lem])
                yield from self._iter_all(n.rdgs)
            if getattr(n, "children", None):
                yield from self._iter_all(n.children)

    def _resolve_gaiji_raw(self, code, raw):
        # 优先级：gaiji_db（CBETA 全局缺字表，与官方 html 一致）→ charDecl（本经 charDecl，兜底）→ raw
        data = self.gaiji_db.get(code) if self.gaiji_db else None
        if data:
            for k in ("unicode", "norm_unicode"):
                v = data.get(k)
                if v:
                    try:
                        return chr(int(v, 16))
                    except ValueError:
                        pass
            for k in ("norm_big5_char", "norm_uni_char", "uni_char", "composition"):
                v = data.get(k)
                if v:
                    return v
            m = re.match(r"U\+([0-9A-Fa-f]+)", data.get("pua") or "")
            if m:
                return chr(int(m.group(1), 16))
        chard = (self._work.metadata.get("charDecl") or {}) if self._work else {}
        rec = chard.get(code)
        if rec:
            if rec.get("unicode"):
                try:
                    return chr(int(rec["unicode"], 16))
                except ValueError:
                    pass
            if rec.get("normal"):
                return rec["normal"]
            if rec.get("composition"):
                return rec["composition"]
        return raw

    def _resolve_gaiji(self, code, raw):
        char = self._resolve_gaiji_raw(code, raw)
        if getattr(self._work, "simplified", False):
            # 简体模式：渲染时解析的缺字同样过 t2s 管线（与官方侧 t2s_baseline 对齐）
            from .simplify import simplify_text
            return simplify_text(char)
        return char

    def _gaiji_roman(self, code: str) -> str:
        """悉昙读音（charDecl Romanized form，Unicode 式优先），无则 ""。"""
        chard = (self._work.metadata.get("charDecl") or {}) if self._work else {}
        rec = chard.get(code) or {}
        return (rec.get("roman") or rec.get("roman_cbeta") or "").strip()

    def _render_body(self, body) -> str:
        return "".join(self._render_node(n) for n in body)

    def _ann_text(self, t: str) -> str:
        """注音发射（P6）：Text 与解析后缺字共用；md 无上方注音，恒为右侧行内括注。"""
        ann = self._annotations
        l, r = ann.get("brackets", ["〔", "〕"])
        return "".join(
            seg if reading is None else f"{seg}{l}{reading}{r}"
            for seg, reading in _split_ann(t, ann["table"], ann["scheme"],
                                           ann.get("rare_zones", frozenset()),
                                           ann.get("rare_cmap"),
                                           _track_seen(ann, self._ann_seen),
                                           ann.get("full_text", False)))

    def _render_node(self, n) -> str:
        if isinstance(n, Text):
            # 版面断行 <lb/> 已置为 ""，需将换行/缩进等空白归一化为无，避免 md 断句
            t = re.sub(r"[\s　]+", "", n.text)
            if self._annotations is not None:
                return self._ann_text(t)
            return t
        if isinstance(n, Lb) or isinstance(n, Pb):
            return ""
        if isinstance(n, Gaiji):
            roman = self._gaiji_roman(n.code)
            if roman:
                if self._drop_sa and not self.show_dharani_transliteration:
                    return ""  # 逐字咒文表转写不显示（官方 txt 同款）
                # 悉昙缺字：官方 txt 系裸读音（如 raṃ），md 同口径，无字形无括号
                return roman
            char = self._resolve_gaiji(n.code, n.char or n.code)
            if self._annotations is not None:
                return self._ann_text(char)
            return char
        if isinstance(n, NoteRef):
            return self._render_noteref(n)
        if isinstance(n, App):
            return self._render_app(n)
        if isinstance(n, Note):
            return self._render_inline_note(n)
        if isinstance(n, E):
            return self._render_e(n)
        return ""

    def _render_children(self, el, kids=None) -> str:
        return "".join(self._render_node(c) for c in (kids if kids is not None else el.children))

    def _render_note_content(self, note) -> str:
        """注内容在正文逐字咒文表上下文之外渲染（注内悉昙照常出读音/占位）。"""
        prev = getattr(self, "_drop_sa", False)
        self._drop_sa = False
        try:
            return self._render_children(note)
        finally:
            self._drop_sa = prev

    def _cf_suffix(self, note, app=None) -> str:
        """cf（confer 参考）：官方 text-with-notes 只为 add 型注追加 `(cf. a; b)`，
        多个以 `; ` 连接（html/txt 同规则；mod/orig 不加）。"""
        if note.ntype != "add":
            return ""
        if app is None:
            app = self._app_by_n.get(note.n or "")
        if app is None or app.lem is None:
            return ""
        cfs = [c for c in app.lem.children
               if isinstance(c, Note) and (c.ntype or "").startswith("cf")]
        if not cfs:
            return ""
        refs = "; ".join("".join(t.text for t in c.children
                                 if isinstance(t, Text)) for c in cfs)
        return f"(cf. {refs})"

    def _render_noteref(self, ref: NoteRef) -> str:
        if not self.show_notes:
            return ""
        notes = ref.notes
        if not notes:
            return ""
        note = self._pick_note(notes)
        if note.ntype == "orig" and (note.n or "") in self._orig_suppressed:
            return ""
        content = self._render_note_content(note) + self._cf_suffix(note)
        if self.notes == "inline":
            lb, rb = bracket_pair(self.note_inline_brackets)
            return f"{lb}{content}{rb}"
        self._fn_seq += 1
        self._fn_notes.append(content)
        return f"[^{self._fn_seq}]"

    def _render_app(self, app: App) -> str:
        if not self.show_notes:
            return ""
        # star_removed（去校勘星）：读法已由 corresp 指向的注在其位置渲染，避免重复
        if app.atype == "star_removed":
            return ""
        if app.attrs.get("corresp"):
            n = app.attrs["corresp"].lstrip("#")
            notes = (self._work.notes_by_n or {}).get(n) if self._work else None
            if notes:
                note = self._pick_note(notes)
                if note.ntype == "orig" and (note.n or "") in self._orig_suppressed:
                    return ""
                content = self._render_note_content(note) + self._cf_suffix(note, app=app)
                if self.notes == "inline":
                    lb, rb = bracket_pair(self.note_inline_brackets)
                    return f"{lb}{content}{rb}"
                self._fn_seq += 1
                self._fn_notes.append(content)
                return f"[^{self._fn_seq}]"
        return ""

    def _render_inline_note(self, note: Note) -> str:
        if note.place in ("inline", "inline2", "interlinear"):
            lb, rb = bracket_pair(self.inline_brackets)
            return f"{lb}{self._render_note_content(note)}{rb}"
        return ""

    def _pick_note(self, notes):
        for t in ("mod", "orig", "add", "equivalent", "rest"):
            for n in notes:
                if n.ntype == t:
                    return n
        return notes[0]

    def _render_e(self, e: E) -> str:
        if e.tag == "app":
            # 正文内联校勘（P5a/P5b）：base 读法只在 <lem>，只渲染 lem；rdg 是异读不进正文
            lem = next((c for c in e.children
                        if isinstance(c, E) and c.tag == "lem"), None)
            return self._render_children(lem) if lem is not None else ""
        tag = e.tag
        if tag == "p":
            return self._render_children(e).strip() + "\n\n"
        if tag == "tt":
            # 逐字咒文表（无 place="inline"）内转写默认不显示
            prev = self._drop_sa
            self._drop_sa = (e.attrs.get("place") or "") != "inline"
            try:
                return self._render_children(e)
            finally:
                self._drop_sa = prev
        if tag == "head":
            level = min(self._div_depth + 1, 6)
            kids = strip_head_no(e.children)[0] if self.strip_head_no else None
            with self._no_ann():
                inner = self._render_children(e, kids).strip()
            return f"{'#' * level} {inner}\n\n"
        if tag == "byline":
            with self._no_ann():
                inner = self._render_children(e).strip()
            return inner + "\n\n"
        if tag == "mulu":
            return ""
        if tag == "unclear":
            return "□"  # 虚缺符号 U+25A1（文字无法辨析）
        if tag == "juan":
            with self._no_ann():
                inner = self._render_children(e).strip()
            return f"## {inner}\n\n"
        if tag in ("jhead", "docNumber"):
            kids = None
            if tag == "jhead" and self.strip_head_no:
                kids = strip_head_no(e.children)[0]
            with self._no_ann():
                return self._render_children(e, kids)
        if tag == "lg":
            return self._render_lg(e)
        if tag == "l":
            return self._render_children(e)
        if tag == "list":
            return "".join(self._render_node(c) for c in e.children)
        if tag == "item":
            return f"- {self._render_children(e).strip()}\n"
        if tag == "div":
            self._div_depth += 1
            out = self._render_children(e)
            self._div_depth -= 1
            return out
        if tag == "table":
            return self._render_table(e)
        if tag == "graphic":
            return self._figure_mark(e)
        if tag == "figure":
            out = []
            for c in e.children:
                if isinstance(c, E) and c.tag == "graphic":
                    out.append(self._figure_mark(c))
                else:
                    out.append(self._render_node(c))
            return "".join(out)
        if tag == "sg":
            # 梵呗注音（<cb:sg>）：官方半角括号，如 (音𫬠)
            return "(" + self._render_children(e) + ")"
        return self._render_children(e)

    def _render_lg(self, e: E) -> str:
        lines = []
        pending: list = []
        for c in e.children:
            if isinstance(c, E) and c.tag == "l":
                parts = []
                buf = []
                for cc in c.children:
                    if isinstance(cc, E) and cc.tag == "caesura":
                        parts.append("".join(self._render_node(x) for x in buf))
                        buf = []
                    else:
                        buf.append(cc)
                if buf or not parts:
                    parts.append("".join(self._render_node(x) for x in buf))
                ln = "　　".join(parts)
                if pending:
                    ln = "".join(self._render_node(p) for p in pending) + ln
                    pending = []
                lines.append(ln)
            elif isinstance(c, (NoteRef, App)):
                pending.append(c)
            elif isinstance(c, Text) and c.text.strip():
                pending.append(c)
            elif isinstance(c, E):
                r = self._render_node(c)
                if r:
                    pending.append(c)
        if pending and lines:
            lines[-1] = lines[-1] + "".join(self._render_node(p) for p in pending)
            pending = []
        elif pending:
            lines.append("".join(self._render_node(p) for p in pending))
        return "\n".join("　　" + ln for ln in lines) + "\n\n" if lines else ""

    def _figure_mark(self, e) -> str:
        """图注标记（官方 txt 同款，md 比对官方 txt）：【圖：<文件名>】；无 url 落空。"""
        url = (e.attrs.get("url") or "").replace("\\", "/")
        base = url.split("/")[-1] if url else ""
        return f"【圖：{base}】" if base else ""

    def _render_table(self, e: E) -> str:
        rows = []
        for r in e.children:
            if isinstance(r, E) and r.tag == "row":
                cells = [self._render_children(c).strip()
                         for c in r.children if isinstance(c, E) and c.tag == "cell"]
                rows.append(cells)
        if not rows:
            return ""
        head = rows[0]
        out = ["| " + " | ".join(head) + " |",
               "|" + "|".join(["---"] * len(head)) + "|"]
        for r in rows[1:]:
            out.append("| " + " | ".join(r) + " |")
        return "\n".join(out) + "\n\n"
