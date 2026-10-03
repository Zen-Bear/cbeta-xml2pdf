# -*- coding: utf-8 -*-
"""转换报告收集器（A2）：记录渲染期间一切改动/替换/忽略/隐藏/兜底，
供 CLI/GUI 落盘为 `{验证}/{id 书名}_转换报告.txt`。

设计要点：
- 进程级单例（仿 annotate._REVIEW）；渲染器零 IO 只记内存，落盘由 CLI/GUI 负责。
- 未 begin 时非 sticky 的 add/count 一律 no-op（校验/字体检查不污染报告）。
- sticky：配置级事件（theme 兜底等）在 begin 之前登记，begin 时播种进本 work；
  无 fmt 的 sticky 条目在 per-fmt 切片中按「配置」出现，merge 时去重合并。
- 行号：物理 XML 行（parser.sourceline）；无可依时显示「—」。

文本语法（受控，供 merge 解析）：
    头    `# 转换报告 {id} [{fmt}]`
    条目  `1. [类别] [fmt] XML 行 {line}：{msg}` + 可选 `   （内容：{content}）`
    计数  `2. [类别] [fmt] 汇总：{item}×{n}（XML 行 l1、l2…）`
"""
import re

_MAX_LEN = 120          # 内容单行化后的截断长度
_LINE_CAP = 5           # 计数条目最多列出的行号数

_FMT_STICKY = "配置"
_EMPTY_HINT = "本文件未发现需记录的特殊处理。"


def _one_line(s, limit=_MAX_LEN) -> str:
    """内容单行化：换行/制表转空格、折叠空白、strip、截断。"""
    if s is None:
        return ""
    s = re.sub(r"[\r\n\t]+", " ", str(s))
    s = re.sub(r"  +", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def _fmt_label(fmt):
    return fmt if fmt else _FMT_STICKY


class _Report:
    def __init__(self):
        self._active = False
        self._work_id = ""
        self._xml = ""
        self._fmt = None
        self._entries = []          # [{cat,msg,line,content,fmt,key}]
        self._counts = {}           # (cat,item,fmt) -> {"n":int,"lines":[...]}
        self._seen = set()          # 本 work 去重键
        self._sticky = []           # 配置级条目（跨 work；begin 播种）
        self._sticky_keys = set()
        self._ctx_line = None

    # ---------------- 生命周期 ----------------
    def active(self) -> bool:
        return self._active

    def begin(self, work_id, xml_fn=""):
        self._active = True
        self._work_id = work_id or ""
        self._xml = xml_fn or ""
        self._fmt = None
        self._entries = [dict(e) for e in self._sticky]
        self._counts = {}
        self._seen = set()
        self._ctx_line = None

    def end(self):
        """结束本 work（保留 sticky；供跨 work 复用）：去激活 + 清 per-work 状态。"""
        self._active = False
        self._work_id = ""
        self._xml = ""
        self._fmt = None
        self._entries = []
        self._counts = {}
        self._seen = set()
        self._ctx_line = None

    def set_fmt(self, fmt):
        self._fmt = fmt
        self._ctx_line = None   # 行号上下文按格式隔离，避免跨格式串行号

    def set_context(self, line=None, content=None):
        self._ctx_line = line

    def reset(self):
        """全清（含 sticky；单测/新进程隔离用）。"""
        self.__init__()

    # ---------------- 收集 ----------------
    def add(self, category, message, *, line=None, content=None, detail=None,
            key=None, sticky=False):
        if not sticky and not self._active:
            return  # 未激活：零开销（避免逐字调用时做无用的字符串归一）
        cat = _one_line(category, 0) or "其它"
        msg = _one_line(message)
        body = content
        if detail:
            body = f"{content} ｜ {detail}" if content else detail
        body = _one_line(body, 200)
        if sticky:
            skey = key if key is not None else (cat, msg)
            if skey not in self._sticky_keys:
                self._sticky_keys.add(skey)
                self._sticky.append({"cat": cat, "msg": msg, "line": line,
                                     "content": body, "fmt": None, "key": key})
        if not self._active:
            return
        if key is not None:
            dk = (self._fmt, key)   # 去重按格式隔离：同事件各格式各记，merge 再合并
            if dk in self._seen:
                return
            self._seen.add(dk)
        self._entries.append({"cat": cat, "msg": msg,
                              "line": line if line is not None else self._ctx_line,
                              "content": body, "fmt": None if sticky else self._fmt,
                              "key": key})

    def count(self, category, item, line=None, n=1):
        if not self._active:
            return
        cat = _one_line(category, 0) or "其它"
        item = _one_line(item, 0)
        rec = self._counts.setdefault((cat, item, self._fmt),
                                      {"n": 0, "lines": []})
        rec["n"] += int(n)
        ln = line if line is not None else self._ctx_line
        if ln is not None and ln not in rec["lines"]:
            rec["lines"].append(ln)

    def entries(self):
        return [dict(e) for e in self._entries]

    # ---------------- 输出 ----------------
    @staticmethod
    def _entry_line(n, e):
        line = e.get("line")
        ln = "—" if line is None else line
        out = [f"{n}. [{e['cat']}] [{_fmt_label(e.get('fmt'))}] "
               f"XML 行 {ln}：{e['msg']}"]
        if e.get("content"):
            out.append(f"   （内容：{e['content']}）")
        return out

    @staticmethod
    def _count_line(n, cat, item, fmt, rec):
        lines = rec.get("lines") or []
        shown = "、".join(str(x) for x in lines[:_LINE_CAP])
        if len(lines) > _LINE_CAP:
            shown += "…"
        tail = f"（XML 行 {shown}）" if shown else ""
        return [f"{n}. [{cat}] [{_fmt_label(fmt)}] 汇总：{item}×{rec['n']}{tail}"]

    def format_text(self, fmt=None):
        """fmt=None → 合并视图（跨格式去重/计数求和）；否则 per-fmt 切片。"""
        header_id = self._work_id or "?"
        if fmt is None:
            entries = _merge_entries(self._entries)
            counts = _merge_counts(self._counts)
            label = "merged"
        else:
            entries = [e for e in self._entries
                       if e.get("fmt") in (None, fmt)]
            counts = [(cat, item, fmt, rec)
                      for (cat, item, f), rec in self._counts.items()
                      if f == fmt]
            label = fmt
        lines = [f"# 转换报告 {header_id} [{label}]"]
        if not entries and not counts:
            lines.append("本文件未发现需记录的特殊处理。")
            return "\n".join(lines) + "\n"
        n = 0
        for e in entries:
            n += 1
            lines.extend(self._entry_line(n, e))
            lines.append("")
        for cat, item, f, rec in counts:
            n += 1
            lines.extend(self._count_line(n, cat, item, f, rec))
            lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines) + "\n"


def _merge_entries(entries):
    """按 (cat,line,msg) 去重，合并 fmt 标签（保持首见序）。"""
    order = []
    seen = {}
    for e in entries:
        k = (e.get("cat"), e.get("line"), e.get("msg"))
        if k not in seen:
            seen[k] = {"cat": e["cat"], "msg": e["msg"], "line": e.get("line"),
                       "content": e.get("content"),
                       "fmts": [_fmt_label(e.get("fmt"))]}
            order.append(k)
        else:
            f = _fmt_label(e.get("fmt"))
            if f not in seen[k]["fmts"]:
                seen[k]["fmts"].append(f)
            if not seen[k]["content"] and e.get("content"):
                seen[k]["content"] = e["content"]
    out = []
    for k in order:
        d = seen[k]
        out.append({"cat": d["cat"], "msg": d["msg"], "line": d["line"],
                    "content": d["content"],
                    "fmt": "|".join(d["fmts"])})
    return out


def _merge_counts(counts):
    """合并视图的计数：按 (cat,item) 求和，行号并集，fmt 合并。"""
    agg = {}
    order = []
    for (cat, item, f), rec in counts.items():
        k = (cat, item)
        if k not in agg:
            agg[k] = {"n": 0, "lines": [], "fmts": []}
            order.append(k)
        agg[k]["n"] += rec["n"]
        for ln in rec["lines"]:
            if ln not in agg[k]["lines"]:
                agg[k]["lines"].append(ln)
        lbl = _fmt_label(f)
        if lbl not in agg[k]["fmts"]:
            agg[k]["fmts"].append(lbl)
    return [(cat, item, "|".join(agg[(cat, item)]["fmts"]),
             {"n": agg[(cat, item)]["n"], "lines": agg[(cat, item)]["lines"]})
            for (cat, item) in order]


# ---------------- 合并 per-fmt 文件 ----------------
_HDR_RE = re.compile(r"^#\s*转换报告\s+(?P<id>.*?)\s*\[(?P<fmt>[^\]]*)\]\s*$")
_ENTRY_RE = re.compile(
    r"^\d+\.\s*\[(?P<cat>[^\]]+)\]\s*\[(?P<fmt>[^\]]*)\]\s*"
    r"XML 行\s*(?P<line>.+?)：(?P<msg>.*)$")
_CONTENT_RE = re.compile(r"^\s+（内容：(?P<content>.*)）\s*$")
_COUNT_RE = re.compile(
    r"^\d+\.\s*\[(?P<cat>[^\]]+)\]\s*\[(?P<fmt>[^\]]*)\]\s*"
    r"汇总：(?P<item>.+?)×\d+(?:（XML 行\s*(?P<lines>[^）]*)）)?\s*$")


def _parse_report_file(path):
    """-> (work_id, entries, counts, unknowns) 或 None（读失败）。"""
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return None
    wid = ""
    entries, counts = [], []
    pending = None   # 最近一条条目（等其内容行）
    unknowns = []
    for raw in text.splitlines():
        if not raw.strip() or raw.strip() == _EMPTY_HINT:
            continue
        m = _HDR_RE.match(raw)
        if m:
            wid = wid or m.group("id")
            continue
        m = _ENTRY_RE.match(raw)
        if m:
            pending = {"cat": m.group("cat"), "fmt": m.group("fmt"),
                       "line": None if m.group("line") == "—" else m.group("line"),
                       "msg": m.group("msg"), "content": ""}
            entries.append(pending)
            continue
        m = _CONTENT_RE.match(raw)
        if m and entries:
            (pending if pending else entries[-1])["content"] = m.group("content")
            continue
        m = _COUNT_RE.match(raw)
        if m:
            lines = []
            if m.group("lines"):
                lines = [x.strip() for x in m.group("lines").rstrip("…").split("、")
                         if x.strip()]
            # 计数 n 由内容重数不可靠（合并后×n 已求和）：从原文本抽回
            nm = re.search(r"×(\d+)", raw)
            counts.append({"cat": m.group("cat"), "item": m.group("item"),
                           "fmt": m.group("fmt"), "n": int(nm.group(1)) if nm else 0,
                           "lines": lines})
            pending = None
            continue
        unknowns.append(raw)
    return wid, entries, counts, unknowns


def merge_convert_reports(paths, extra=None):
    """合并多份 per-fmt 报告：条目按 (cat,line,msg) 去重合并 fmt 标签，
    计数按 (cat,item) 求和并合并行号/fmt；坏文件跳过。
    extra=[(类别, 说明)] 追加为条目（GUI worker 侧改名等进程内事件）。返回文本或 ""。"""
    wid = ""
    grouped, order, unknown_lines = {}, [], []
    seen = {}
    for p in paths or []:
        parsed = _parse_report_file(p)
        if parsed is None:
            continue
        rid, entries, counts, unknowns = parsed
        wid = wid or rid
        unknown_lines.extend(unknowns)
        for e in entries:
            k = (e["cat"], e["line"], e["msg"])
            if k not in seen:
                seen[k] = {"cat": e["cat"], "msg": e["msg"], "line": e["line"],
                           "content": e["content"], "fmts": [e["fmt"]]}
                order.append(("e", k))
            else:
                if e["fmt"] not in seen[k]["fmts"]:
                    seen[k]["fmts"].append(e["fmt"])
                if not seen[k]["content"] and e["content"]:
                    seen[k]["content"] = e["content"]
        for c in counts:
            k = (c["cat"], c["item"])
            if k not in grouped:
                grouped[k] = {"n": 0, "lines": [], "fmts": []}
                order.append(("c", k))
            g = grouped[k]
            g["n"] += c["n"]
            for ln in c["lines"]:
                if ln not in g["lines"]:
                    g["lines"].append(ln)
            if c["fmt"] not in g["fmts"]:
                g["fmts"].append(c["fmt"])
    if not order and not unknown_lines and not extra:
        return ""
    lines = [f"# 转换报告 {wid or '?'} [merged]"]
    n = 0
    for kind, k in order:
        n += 1
        if kind == "e":
            d = seen[k]
            ln = "—" if d["line"] is None else d["line"]
            lines.append(f"{n}. [{d['cat']}] [{'|'.join(d['fmts'])}] "
                         f"XML 行 {ln}：{d['msg']}")
            if d["content"]:
                lines.append(f"   （内容：{d['content']}）")
        else:
            g = grouped[k]
            shown = "、".join(str(x) for x in g["lines"][:_LINE_CAP])
            if len(g["lines"]) > _LINE_CAP:
                shown += "…"
            tail = f"（XML 行 {shown}）" if shown else ""
            lines.append(f"{n}. [{k[0]}] [{'|'.join(g['fmts'])}] "
                         f"汇总：{k[1]}×{g['n']}{tail}")
        lines.append("")
    for raw in unknown_lines:
        n += 1
        lines.append(f"{n}. [其它] [merged] {raw}")
        lines.append("")
    for cat, msg in (extra or []):
        n += 1
        lines.append(f"{n}. [{cat}] [merged] {_one_line(msg)}")
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


# 进程级单例
report = _Report()
