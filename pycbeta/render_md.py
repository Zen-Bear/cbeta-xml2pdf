"""Markdown renderer: IR -> Markdown text.

Notes: inline -> （…）; footnote/endnote -> Markdown footnotes [^n].
"""

import os
import re
from contextlib import contextmanager
from typing import List, Optional

from .model import App, E, Gaiji, Lb, Note, NoteRef, Pb, Text, Work
from .annotate import active as _ann_active, split_annotated as _split_ann, track_seen as _track_seen
from .gaiji import GaijiDb
from .theme import Theme


class MdRenderer:
    def __init__(self, gaiji_db=None, theme=None, notes="endnote", show_notes=True, inline_brackets="fullwidth",
                 annotations=None):
        self.gaiji_db = gaiji_db if gaiji_db is not None else GaijiDb()
        self.theme = theme if theme is not None else Theme()
        self.notes = notes  # 'footnote' | 'endnote' | 'inline'
        self.show_notes = show_notes
        self.inline_brackets = inline_brackets  # halfwidth="()" / fullwidth="（）"（默认全角）
        # 难字注音（P6）：None 或 {"table", "scheme"}；md 无 ruby，用〔注音〕括注
        # （不用（），避免与校勘记 inline 括号混淆；verify 侧 normalize 已剥除〔〕）
        self._annotations = _ann_active(annotations)
        self._ann_seen = set()  # repeat first/page 已注词集合（render_work 起始终置零；md 单文件，page 等同 first）
        self._work = None
        self._fn_seq = 0
        self._fn_notes: List[str] = []
        self._div_depth = 0

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

    def _render_children(self, el) -> str:
        return "".join(self._render_node(c) for c in el.children)

    def _render_noteref(self, ref: NoteRef) -> str:
        if not self.show_notes:
            return ""
        notes = ref.notes
        if not notes:
            return ""
        note = self._pick_note(notes)
        content = self._render_children(note)
        if self.notes == "inline":
            lb, rb = ("(", ")") if self.inline_brackets == "halfwidth" else ("（", "）")
            return f"{lb}{content}{rb}"
        self._fn_seq += 1
        self._fn_notes.append(content)
        return f"[^{self._fn_seq}]"

    def _render_app(self, app: App) -> str:
        if not self.show_notes:
            return ""
        if app.attrs.get("corresp"):
            n = app.attrs["corresp"].lstrip("#")
            notes = (self._work.notes_by_n or {}).get(n) if self._work else None
            if notes:
                note = self._pick_note(notes)
                content = self._render_children(note)
                if self.notes == "inline":
                    lb, rb = ("(", ")") if self.inline_brackets == "halfwidth" else ("（", "）")
                    return f"{lb}{content}{rb}"
                self._fn_seq += 1
                self._fn_notes.append(content)
                return f"[^{self._fn_seq}]"
        return ""

    def _render_inline_note(self, note: Note) -> str:
        if note.place in ("inline", "inline2", "interlinear"):
            lb, rb = ("(", ")") if self.inline_brackets == "halfwidth" else ("（", "）")
            return f"{lb}{self._render_children(note)}{rb}"
        return ""

    def _pick_note(self, notes):
        for t in ("mod", "orig", "add", "equivalent", "rest"):
            for n in notes:
                if n.ntype == t:
                    return n
        return notes[0]

    def _render_e(self, e: E) -> str:
        tag = e.tag
        if tag == "p":
            return self._render_children(e).strip() + "\n\n"
        if tag == "head":
            level = min(self._div_depth + 1, 6)
            with self._no_ann():
                inner = self._render_children(e).strip()
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
            with self._no_ann():
                return self._render_children(e)
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
