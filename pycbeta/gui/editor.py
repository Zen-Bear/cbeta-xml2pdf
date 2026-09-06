"""DOCX 所见即所得样式编辑器（P1 GUI）。

三层出口（与 panel/__main__ 同构）：
- ``StyleEditorDialog`` —— 纯对话框，``(sample_xml=None, engine_chain=None, parent=None)``，
  当前 GUI 样式表卡弹窗 + publish 侧同样 import 即用；
- ``main()`` —— ``python -m pycbeta.gui.editor [--sample 样张.xml]`` 独立运行；
- 导出：样张 DOCX/PDF（PDF 经主窗口引擎链），CSS 落仓库根 ``user.css``（GUI 自动生效）。

预览原理（模拟显示，非 Word 真排版）：左改参 → 覆盖 CSS 块 → 工作 CSS
（出厂 ``pdf_docx.css`` 原文 + 覆盖块）→ ``Theme.from_css`` → ``DocxRenderer``
重渲样张 → 回读 ``document.xml``（+``footnotes.xml``）runs → ``QTextDocument``
只读显示。字体四参数（字体/字号/粗细/颜色）读的是渲染器刚写出的真值；
分页/页边距/行尾换行以 Word 为准（顶部常驻提示）。
"""
import os
import re
import sys
import tempfile
import zipfile

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QDialog,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FACTORY_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "styles", "pdf_docx.css")
USER_CSS_NAME = "user.css"

# 临时样张候选（glob，按序取首个命中者；精简样本到了替换此处即可）
SAMPLE_CANDIDATES = (
    r"E:\dev\cbeta\test\T0349*\T12n0349.xml",
    r"E:\dev\cbeta\test\T1144*\T20n1144.xml",
)

# 左侧可调行：(覆盖块选择器, 显示名)
EDITABLE_ROWS = (
    ("h1.title", "书名"),
    ("p.head", "标题"),
    ("p.juan", "卷名"),
    ("p.pin", "品名"),
    ("p", "正文"),
    ("div.lg", "偈颂"),
    ("span.note-inline", "行内夹注"),
    (".footnote", "脚注文字"),
    ("sup.note-ref", "注释序号"),
    ("p.byline", "题署"),
    ("p.author", "作者"),
    ("p.translator", "译者"),
    ("[rend~=kaiti]", "楷体"),
    ("[rend~=heiti]", "黑体"),
    ("[rend~=fangsong]", "仿宋"),
    ("[rend~=mingti]", "明体"),
    ("div.div-xu p.head", "序标题"),
)

WEIGHT_ITEMS = [("（跟随）", ""), ("加粗", "bold"), ("正常", "normal")]


def user_css_path(root=None):
    """用户 CSS 路径（仓库根 user.css；git 忽略，不入库）。"""
    return os.path.join(root or REPO_ROOT, USER_CSS_NAME)


def save_user_css_text(text, root=None):
    """用户 CSS 落盘（纯函数，可单测）；返回路径。"""
    path = user_css_path(root)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def clear_user_css(root=None):
    """删除用户 CSS（不存在也算成功）；返回是否删过文件。"""
    path = user_css_path(root)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def factory_css_text():
    with open(os.path.abspath(FACTORY_CSS), encoding="utf-8") as f:
        return f.read()


def default_sample():
    import glob
    for cand in SAMPLE_CANDIDATES:
        hits = sorted(glob.glob(cand))
        if hits:
            return hits[0]
    return ""


def build_override_block(values):
    """{selector: {font-family, font-size, font-weight, color}} → 覆盖块文本。

    只含字体四属性；空值跳过，无值行不输出（EDITABLE_ROWS 顺序）。
    """
    out = ["/* 可视化编辑器生成：只覆盖字体四属性，后定义优先 */"]
    order = [sel for sel, _label in EDITABLE_ROWS]
    for sel in order + [s for s in values if s not in order]:
        props = values.get(sel) or {}
        decls = []
        if props.get("font-family"):
            decls.append(f"font-family: {props['font-family']}")
        if props.get("font-size"):
            decls.append(f"font-size: {props['font-size']}")
        if props.get("font-weight"):
            decls.append(f"font-weight: {props['font-weight']}")
        if props.get("color"):
            decls.append(f"color: {props['color']}")
        if decls:
            out.append(f"{sel} {{ {'; '.join(decls)}; }}")
    return "\n".join(out) + "\n"


def parse_override_block(text):
    """覆盖块文本 → ({selector: props}, 错误信息|None)。

    用 Theme._parse_css_tags 复用选择器映射（含后代组合）；tinycss2 错误 token
    报红，不抛异常。只取字体四属性。
    """
    from pycbeta.theme import Theme, TAG_SELECTOR
    import tinycss2
    try:
        errors = [t for t in tinycss2.parse_stylesheet(
            text or "", skip_comments=True, skip_whitespace=True)
            if t.type == "error"]
    except Exception as exc:  # noqa: BLE001 —— 非法输入只红字
        return {}, str(exc)
    err = None
    if errors:
        err = "; ".join(str(getattr(e, "message", e)) for e in errors[:3])
    values = {}
    try:
        tags, compounds = Theme._parse_css_tags(text or "")
    except Exception as exc:  # 防御：解析器内部异常也只红字
        return {}, str(exc)
    keep = ("font-family", "font-size", "font-weight", "color")
    for tag, props in tags.items():
        sel = (TAG_SELECTOR.get(tag) or "").split(",")[0].strip()
        if sel:
            got = {k: v for k, v in props.items() if k in keep}
            if got:
                values.setdefault(sel, {}).update(got)
    for _anc, _tgt, cprops, selector in compounds:
        got = {k: v for k, v in cprops.items() if k in keep}
        if got:
            values.setdefault(selector, {}).update(got)
    return values, err


# ---------------- DOCX 回读 → 预览规格（纯函数，可单测） ----------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(tag):
    return f"{{{_W_NS}}}{tag}"


def _a(el, name):
    """OOXML 属性取值（w: 命名空间限定，如 w:val/w:id）。"""
    return el.get(f"{{{_W_NS}}}{name}") if el is not None else None


def _run_text(run):
    return "".join(t.text or "" for t in run.iter(_w("t")))


def _rpr(run):
    rpr = run.find(_w("rPr"))
    return rpr if rpr is not None else None


def _sz_pt(rpr):
    if rpr is None:
        return None
    sz = rpr.find(_w("sz"))
    val = _a(sz, "val")
    if sz is None or not val:
        return None
    try:
        return float(val) / 2.0
    except (TypeError, ValueError):
        return None


def _color(rpr):
    if rpr is None:
        return ""
    c = rpr.find(_w("color"))
    val = _a(c, "val")
    return f"#{val}" if val else ""


def _font(rpr):
    if rpr is None:
        return ""
    f = rpr.find(_w("rFonts"))
    if f is None:
        return ""
    return _a(f, "eastAsia") or _a(f, "ascii") or ""


def _flags(rpr):
    bold = rpr is not None and rpr.find(_w("b")) is not None
    sup = False
    if rpr is not None:
        va = rpr.find(_w("vertAlign"))
        sup = _a(va, "val") in ("superscript", "super")
    return bold, sup


_EQ_RE = re.compile(r"\\up\s+\d+\(([^)]+)\),([^)]*)\)")


def _eq_reading(instr):
    m = _EQ_RE.search(instr or "")
    return m.group(1).strip() if m else ""


def _para_runs(p, fn_id_to_num):
    """段落 → [run规格]；ruby/EQ 展开为 原文+灰小字〔读音〕；脚注引用取编号。"""
    runs = []
    for run in p.findall(_w("r")):
        rpr = _rpr(run)
        bold, sup = _flags(rpr)
        base = {"text": "", "size": _sz_pt(rpr), "font": _font(rpr),
                "bold": bold, "color": _color(rpr), "super": sup, "dim": False}
        if run.find(_w("footnoteReference")) is not None:
            fid = _a(run.find(_w("footnoteReference")), "id")
            num = fn_id_to_num.get(fid, "?")
            runs.append(dict(base, text=f"[{num}]", super=True))
            continue
        instr = run.find(_w("instrText"))
        if instr is not None:
            rd = _eq_reading(instr.text or "")
            base_text = ""
            tail = (instr.tail or "")
            m = re.search(r",([^)]*)\)", instr.text or "")
            if m:
                base_text = m.group(1)
            runs.append(dict(base, text=base_text or tail.strip()))
            if rd:
                runs.append(dict(base, text=f"〔{rd}〕", size=None,
                                 super=True, dim=True))
            continue
        t = _run_text(run)
        if t:
            runs.append(dict(base, text=t))
    for ruby in p.findall(_w("ruby")):
        rt = ruby.find(f"{_w('rt')}")
        reading = "".join(x.text or "" for x in rt.iter(_w("t"))) if rt is not None else ""
        rb = ruby.find(f"{_w('rubyBase')}")
        base_text = "".join(x.text or "" for x in rb.iter(_w("t"))) if rb is not None else ""
        rpr = None
        if rb is not None:
            first = rb.find(_w("r"))
            rpr = _rpr(first) if first is not None else None
        bold, _sup = _flags(rpr)
        runs.append({"text": base_text, "size": _sz_pt(rpr), "font": _font(rpr),
                     "bold": bold, "color": _color(rpr), "super": False, "dim": False})
        if reading:
            runs.append({"text": f"〔{reading}〕", "size": None, "font": "",
                         "bold": False, "color": "", "super": True, "dim": True})
    return [r for r in runs if r["text"]]


_PSTYLE_ALIGN = {"title": "center", "head": "center", "juan": "center",
                 "pin": "center", "byline": "right", "author": "right",
                 "translator": "right"}


def docx_spec(docx_path):
    """DOCX → 预览规格 ``{"paras": [{style, align, runs}], "footnotes": [{num, runs}]}``。

    正文段落取 w:p（含 pStyle 对齐）；脚注取 footnotes.xml（跳过分隔符 0/1），
    统一归并 —— 预览尾注陈列，页底位置以 Word 为准。
    """
    from lxml import etree
    spec = {"paras": [], "footnotes": []}
    with zipfile.ZipFile(docx_path) as z:
        names = z.namelist()
        doc = etree.fromstring(z.read("word/document.xml"))
        fn_root = (etree.fromstring(z.read("word/footnotes.xml"))
                   if "word/footnotes.xml" in names else None)
    fn_id_to_num, fn_bodies = {}, {}
    if fn_root is not None:
        num = 0
        for fn in fn_root.findall(_w("footnote")):
            fid = _a(fn, "id")
            if fid in ("0", "1"):
                continue
            num += 1
            fn_id_to_num[fid] = num
            runs = []
            for p in fn.findall(_w("p")):
                runs.extend(_para_runs(p, {}))
            fn_bodies[num] = runs
    for p in doc.iter(_w("p")):
        style = ""
        ppr = p.find(_w("pPr"))
        if ppr is not None:
            ps = ppr.find(_w("pStyle"))
            if ps is not None:
                style = _a(ps, "val") or ""
        align = _PSTYLE_ALIGN.get(style, "")
        if not align and ppr is not None:
            jc = ppr.find(_w("jc"))
            if jc is not None:
                align = {"center": "center", "right": "right",
                         "both": "justify"}.get(_a(jc, "val") or "", "")
        runs = _para_runs(p, fn_id_to_num)
        if runs:
            spec["paras"].append({"style": style, "align": align, "runs": runs})
    for num in sorted(fn_bodies):
        if fn_bodies[num]:
            spec["footnotes"].append({"num": num, "runs": fn_bodies[num]})
    return spec


# ---------------- 后台重渲线程 ----------------

class _RenderThread(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, xml_path, css_text, out_dir, parent=None):
        super().__init__(parent)
        self._xml = xml_path
        self._css = css_text
        self._out = out_dir

    def run(self):
        try:
            from pycbeta.parser import P5Parser
            from pycbeta.render_docx import DocxRenderer
            from pycbeta.theme import Theme
            work = P5Parser().parse(self._xml)
            theme = Theme.from_css(self._css)
            fn = DocxRenderer(theme=theme, notes="footnote",
                              bookmarks=False).render_work(
                work, self._out, filename="preview.docx")
            self.done.emit(fn if isinstance(fn, str) else fn[0])
        except Exception as exc:  # noqa: BLE001 —— 错误进状态行，不崩界面
            self.failed.emit(str(exc))


# ---------------- 对话框 ----------------

class StyleEditorDialog(QDialog):
    """所见即所得样式编辑器：左调参 / 右预览 / 底导出。"""

    def __init__(self, sample_xml=None, engine_chain=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("样式编辑器（DOCX 所见即所得）")
        self.resize(1180, 760)
        self._engine_chain = engine_chain
        self._tmp = tempfile.mkdtemp(prefix="style-editor-")
        self._work = None            # 当前解析后 Work（样张缓存）
        self._work_src = ("", 0)     # (path, mtime)
        self._last_docx = ""         # 最近一次重渲产物（导出用）
        self._last_good_css = ""     # 最近一次可预览的工作 CSS
        self._need_refresh = False   # 渲染中又有改动时补一轮
        self._thread = None
        self._rows = {}              # selector -> 控件组
        self._build(sample_xml or default_sample())

    # ----- 构造 -----
    def _build(self, sample):
        layout = QVBoxLayout(self)
        # 样张行
        srow = QHBoxLayout()
        srow.addWidget(QLabel("样张"))
        self.sample_edit = QLineEdit(sample)
        self.sample_edit.setPlaceholderText("XML 样张路径")
        self.sample_edit.editingFinished.connect(self._on_sample_changed)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_sample)
        srow.addWidget(self.sample_edit, 1)
        srow.addWidget(browse)
        layout.addLayout(srow)
        # 左右分栏
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._left_panel())
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        tip = QLabel("预览为模拟显示（字体四参数为真值），分页/页边距以 Word 为准")
        tip.setStyleSheet("color: gray")
        rl.addWidget(tip)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        rl.addWidget(self.preview, 1)
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color: gray")
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        # 底栏
        brow = QHBoxLayout()
        self.btn_docx = QPushButton("保存DOCX")
        self.btn_pdf = QPushButton("导出PDF")
        self.btn_css = QPushButton("保存用户CSS")
        self.btn_reset = QPushButton("恢复出厂")
        self.btn_close = QPushButton("关闭")
        self.btn_docx.clicked.connect(self._export_docx)
        self.btn_pdf.clicked.connect(self._export_pdf)
        self.btn_css.clicked.connect(self._save_user_css)
        self.btn_reset.clicked.connect(self._reset_factory)
        self.btn_close.clicked.connect(self.reject)
        for b in (self.btn_docx, self.btn_pdf, self.btn_css, self.btn_reset,
                  self.btn_close):
            brow.addWidget(b)
        brow.addStretch(1)
        layout.addLayout(brow)
        # 防抖重渲
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.refresh_preview)
        # 初始值：出厂 CSS + 空覆盖块
        self._factory_css = factory_css_text()
        self._source_edit.setPlainText("/* 在此追加/覆盖规则；解析失败时本框红字且预览保持上次 */\n")
        self._sync_controls_from_block()
        self.refresh_preview()

    def _left_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        # 控件页
        cw = QWidget()
        form = QFormLayout(cw)
        for sel, label in EDITABLE_ROWS:
            row = QHBoxLayout()
            font_edit = QLineEdit()
            font_edit.setPlaceholderText("字体，如 朝华标题B, ZhaohuaMinB")
            font_edit.setMinimumWidth(170)
            size_edit = QLineEdit()
            size_edit.setPlaceholderText("如 20pt / 0.75em")
            size_edit.setFixedWidth(110)
            weight = QComboBox()
            for label, data in WEIGHT_ITEMS:
                weight.addItem(label, data)
            weight.setFixedWidth(80)
            color_btn = QPushButton("颜色")
            color_btn.setFixedWidth(64)
            color_btn.clicked.connect(
                lambda _v, s=sel: self._pick_color(s))
            color_btn.setToolTip("点击取色；右键清除")
            color_btn.setContextMenuPolicy(Qt.CustomContextMenu)
            color_btn.customContextMenuRequested.connect(
                lambda _p, s=sel: self._clear_color(s))
            row.addWidget(font_edit, 1)
            row.addWidget(size_edit)
            row.addWidget(weight)
            row.addWidget(color_btn)
            form.addRow(label, row)
            self._rows[sel] = {"font": font_edit, "size": size_edit,
                               "weight": weight, "color": color_btn,
                               "color_value": ""}
            font_edit.textChanged.connect(lambda _v: self._on_control_changed())
            size_edit.textChanged.connect(lambda _v: self._on_control_changed())
            weight.currentIndexChanged.connect(lambda _i: self._on_control_changed())
        tabs.addTab(cw, "控件")
        # 源码页
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(4, 4, 4, 4)
        self._source_edit = QPlainTextEdit()
        self._source_edit.textChanged.connect(self._on_source_changed)
        sl.addWidget(self._source_edit, 1)
        self._source_err = QLabel()
        self._source_err.setStyleSheet("color: red")
        self._source_err.setWordWrap(True)
        sl.addWidget(self._source_err)
        tabs.addTab(sw, "源码")
        layout.addWidget(tabs, 1)
        return w

    # ----- 工作 CSS -----
    def work_css(self):
        """工作 CSS = 出厂原文 + 覆盖块（源码页文本）。"""
        return self._factory_css + "\n" + self._source_edit.toPlainText()

    def _on_control_changed(self):
        values = {}
        for sel, ctrls in self._rows.items():
            props = {}
            if ctrls["font"].text().strip():
                props["font-family"] = ctrls["font"].text().strip()
            if ctrls["size"].text().strip():
                props["font-size"] = ctrls["size"].text().strip()
            if ctrls["weight"].currentData():
                props["font-weight"] = ctrls["weight"].currentData()
            if ctrls["color_value"]:
                props["color"] = ctrls["color_value"]
            if props:
                values[sel] = props
        block = build_override_block(values)
        with QSignalBlocker(self._source_edit):
            self._source_edit.setPlainText(block)
        self._source_err.setText("")
        self._schedule()

    def _on_source_changed(self):
        values, err = parse_override_block(self._source_edit.toPlainText())
        if err:
            self._source_err.setText(f"CSS 解析失败（预览保持上次）：{err}")
            return
        self._source_err.setText("")
        self._sync_controls_from_block(values)
        self._schedule()

    def _sync_controls_from_block(self, values=None):
        if values is None:
            values, _err = parse_override_block(self._source_edit.toPlainText())
        for sel, ctrls in self._rows.items():
            props = (values or {}).get(sel, {})
            with QSignalBlocker(ctrls["font"]):
                ctrls["font"].setText(props.get("font-family", ""))
            with QSignalBlocker(ctrls["size"]):
                ctrls["size"].setText(props.get("font-size", ""))
            with QSignalBlocker(ctrls["weight"]):
                i = ctrls["weight"].findData(props.get("font-weight", ""))
                ctrls["weight"].setCurrentIndex(i if i >= 0 else 0)
            ctrls["color_value"] = props.get("color", "")
            self._paint_color_button(sel)

    def _paint_color_button(self, sel):
        btn = self._rows[sel]["color"]
        val = self._rows[sel]["color_value"]
        btn.setStyleSheet(f"background-color: {val}" if val else "")

    def _pick_color(self, sel):
        c = QColorDialog.getColor(QColor(self._rows[sel]["color_value"] or "#000000"),
                                 self, f"{sel} 颜色")
        if c.isValid():
            self._rows[sel]["color_value"] = c.name()
            self._paint_color_button(sel)
            self._on_control_changed()

    def _clear_color(self, sel):
        self._rows[sel]["color_value"] = ""
        self._paint_color_button(sel)
        self._on_control_changed()

    # ----- 样张 -----
    def _browse_sample(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择预览样张 XML", "",
                                              "XML (*.xml);;所有文件 (*)")
        if path:
            self.sample_edit.setText(path)
            self._on_sample_changed()

    def _on_sample_changed(self):
        self._work = None
        self.refresh_preview()

    def _load_work(self):
        from pycbeta.parser import P5Parser
        path = self.sample_edit.text().strip()
        if not path or not os.path.isfile(path):
            return None
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        if self._work is None or self._work_src != (path, mtime):
            try:
                self._work = P5Parser().parse(path)
            except Exception as exc:  # noqa: BLE001
                self.status.setText(f"样张解析失败：{exc}")
                return None
            self._work_src = (path, mtime)
        return self._work

    # ----- 预览 -----
    def _schedule(self):
        self._timer.start()

    def refresh_preview(self):
        work = self._load_work()
        if work is None:
            if not self.sample_edit.text().strip():
                self.status.setText("请先选择预览样张 XML")
            return
        values, err = parse_override_block(self._source_edit.toPlainText())
        if err:
            return  # 源码非法：保持上次预览（红字已在源码页）
        css = self.work_css()
        self._last_good_css = css
        self.status.setText("正在预览…")
        if self._thread is not None and self._thread.isRunning():
            self._need_refresh = True  # 本轮结束后补一轮
            return
        self._need_refresh = False
        self._thread = _RenderThread(self.sample_edit.text().strip(), css, self._tmp,
                                     self)
        self._thread.done.connect(self._on_rendered)
        self._thread.failed.connect(self._on_render_failed)
        self._thread.start()

    def _render_inline(self, css):
        """同步重渲（单测/导出前保底用；界面走线程）。返回 docx 路径。"""
        import tempfile as _tf
        from pycbeta.parser import P5Parser
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.theme import Theme
        work = P5Parser().parse(self.sample_edit.text().strip())
        theme = Theme.from_css(css)
        out = _tf.mkdtemp(prefix="style-editor-")
        fn = DocxRenderer(theme=theme, notes="footnote",
                          bookmarks=False).render_work(work, out, "preview.docx")
        return fn if isinstance(fn, str) else fn[0]

    def _on_rendered(self, docx_path):
        import datetime
        try:
            spec = docx_spec(docx_path)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"预览解析失败：{exc}")
            return
        self._last_docx = docx_path
        self._show_spec(spec)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.status.setText(f"预览已更新 {now}")
        if self._need_refresh:
            self._need_refresh = False
            QTimer.singleShot(0, self.refresh_preview)

    def _on_render_failed(self, msg):
        self.status.setText(f"重渲失败：{msg}")
        if self._need_refresh:
            self._need_refresh = False
            QTimer.singleShot(0, self.refresh_preview)

    def _show_spec(self, spec):
        from PySide6.QtGui import QTextBlockFormat
        doc = self.preview.document()
        doc.clear()
        cur = QTextCursor(doc)
        for para in spec["paras"]:
            fmt = QTextBlockFormat()
            if para["align"] == "center":
                fmt.setAlignment(Qt.AlignCenter)
            elif para["align"] == "right":
                fmt.setAlignment(Qt.AlignRight)
            elif para["align"] == "justify":
                fmt.setAlignment(Qt.AlignJustify)
            cur.setBlockFormat(fmt)
            for r in para["runs"]:
                cf = QTextCharFormat()
                if r["size"]:
                    cf.setFontPointSize(r["size"])
                if r["font"]:
                    cf.setFontFamilies([r["font"]])
                if r["bold"]:
                    cf.setFontWeight(QFont.Bold)
                if r["color"]:
                    cf.setForeground(QColor(r["color"]))
                if r["super"]:
                    cf.setVerticalAlignment(
                        QTextCharFormat.VerticalAlignment.AlignSuperScript)
                if r["dim"]:
                    cf.setFontPointSize((r["size"] or 10.5) * 0.7)
                    cf.setForeground(QColor("#888888"))
                cur.insertText(r["text"], cf)
            cur.insertBlock()
        if spec["footnotes"]:
            cur.insertText("────────────────")
            cur.insertBlock()
            cf = QTextCharFormat()
            cf.setFontWeight(QFont.Bold)
            cur.insertText("校注（预览统一作尾注显示，页底脚注以 Word 为准）", cf)
            cur.insertBlock()
            for fn in spec["footnotes"]:
                for r in fn["runs"]:
                    cf = QTextCharFormat()
                    if r["size"]:
                        cf.setFontPointSize(r["size"])
                    if r["font"]:
                        cf.setFontFamilies([r["font"]])
                    if r["bold"]:
                        cf.setFontWeight(QFont.Bold)
                    if r["color"]:
                        cf.setForeground(QColor(r["color"]))
                    if r["super"]:
                        cf.setVerticalAlignment(
                            QTextCharFormat.VerticalAlignment.AlignSuperScript)
                    cur.insertText(r["text"], cf)
                cur.insertBlock()

    # ----- 导出 -----
    def _export_docx(self):
        import shutil
        path, _ = QFileDialog.getSaveFileName(self, "保存样张 DOCX", "preview.docx",
                                              "Word (*.docx)")
        if not path:
            return
        src = self._last_docx
        if not src or not os.path.isfile(src):
            try:
                src = self._render_inline(self._last_good_css or self.work_css())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "导出失败", str(exc))
                return
        try:
            shutil.copyfile(src, path)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.status.setText(f"DOCX 已保存：{path}")

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出样张 PDF", "preview.pdf",
                                              "PDF (*.pdf)")
        if not path:
            return
        from pycbeta.render_pdf import docx_to_pdf
        src = self._last_docx
        if not src or not os.path.isfile(src):
            try:
                src = self._render_inline(self._last_good_css or self.work_css())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "导出失败", str(exc))
                return
        self.status.setText("正在转 PDF…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            docx_to_pdf(src, path, chain=self._engine_chain)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.status.setText(f"PDF 已导出：{path}")

    def _save_user_css(self):
        try:
            path = save_user_css_text(self._last_good_css or self.work_css())
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "已保存",
                                f"用户 CSS 已存 {path}\n主窗口批量渲染自动生效（--theme）。")

    def _reset_factory(self):
        path = user_css_path()
        if os.path.isfile(path):
            if QMessageBox.question(
                    self, "恢复出厂",
                    f"删除用户 CSS（{path}）并回到出厂样式？",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                clear_user_css()
            except OSError as exc:
                QMessageBox.warning(self, "恢复失败", str(exc))
                return
        self._source_edit.setPlainText(
            "/* 在此追加/覆盖规则；解析失败时本框红字且预览保持上次 */\n")
        self._sync_controls_from_block({})
        self.refresh_preview()

    def closeEvent(self, event):
        try:
            if self._thread is not None and self._thread.isRunning():
                self._thread.wait(2000)
        finally:
            super().closeEvent(event)


def main(argv=None):
    """独立运行：python -m pycbeta.gui.editor [--sample 样张.xml]。"""
    import argparse
    ap = argparse.ArgumentParser(description="DOCX 所见即所得样式编辑器")
    ap.add_argument("--sample", default="", help="预览样张 XML 路径")
    args = ap.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv or [])
    dlg = StyleEditorDialog(sample_xml=args.sample or None)
    dlg.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
