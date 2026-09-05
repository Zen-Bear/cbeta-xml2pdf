"""XML 转换选项面板（P1 GUI 链路 B 可复用组件）。

七选项卡：输出格式 / 页面 / 分页 / 排版 / 注释 / 注音 / 校验。
控件值 ↔ XmlOptions ↔ config presets 三向同步；dict 型选项经临时 presets 进子进程桥。

三槽配置（仓库根目录）：出厂 pycbeta/config.json（只读，GUI 永不写）、
当前 config.user.json、 上一次 config.last.json。保存时轮换，永不超过三份。
"""
import copy
import json
import os
import tempfile

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FACTORY_NAME = os.path.join("pycbeta", "config.json")
USER_NAME = "config.user.json"
LAST_NAME = "config.last.json"

PAGINATION_KEYS = ["enabled", "duplex", "juan", "juan_first", "mulu_level1", "pb", "tei"]
PAGINATION_LABELS = {
    "enabled": "智能分页", "duplex": "双面打印", "juan": "卷首换页",
    "juan_first": "首卷换页", "mulu_level1": "序/品 level1 换页",
    "pb": "按 pb 分页", "tei": "尾页换页",
}
FORMATS = ["pdf", "docx", "html", "md", "epub"]
DOCX_SINGLES = ["msword", "wps", "docbuilder", "libreoffice", "minipdf"]
HTML_SINGLES = ["chromium", "prince", "weasyprint", "cbetapdf"]
INSTALL_HINTS = {
    "msword": "需安装 MS Word",
    "wps": "需安装 WPS Office",
    "docbuilder": "需安装 ONLYOFFICE DocBuilder",
    "libreoffice": "需安装 LibreOffice",
    "minipdf": "随包 engines/minipdf.exe",
    "chromium": "需 playwright install chromium",
    "prince": "需安装 Prince",
    "weasyprint": "需 pip install weasyprint",
    "cbetapdf": "随包 engines/cbetapdf.exe",
}


MSWORD_EXES = ["winword", "winword.exe"]
MSWORD_PATHS = [
    r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    r"C:\Program Files\Microsoft Office\root\Office15\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\root\Office15\WINWORD.EXE",
]
WPS_EXES = ["wps", "wps.exe", "wpp.exe", "et.exe"]
WPS_DIRS = [
    r"C:\Program Files\Kingsoft\WPS Office",
    r"C:\Program Files (x86)\Kingsoft\WPS Office",
]
# 版本号子目录安装（如 C:\Apps\WPS Office\12.1.0.21915\office6\wps.exe，
# 与 C:\Apps\LibreOffice 同一习惯）：glob 兜底，which/PATH 查不到时命中
WPS_ROOTS = [
    r"C:\Apps\WPS Office",
    r"C:\Program Files\Kingsoft\WPS Office",
    r"C:\Program Files (x86)\Kingsoft\WPS Office",
]
WPS_GLOBS = [rf"{r}\*\office6\{exe}" for r in WPS_ROOTS
             for exe in ("wps.exe", "et.exe", "wpp.exe")]
MSWORD_GLOBS = [
    r"C:\Program Files\Microsoft Office\root\Office*\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\root\Office*\WINWORD.EXE",
]


def _office_ready(exe_names, extra_files=(), extra_dirs=(), has_com=True,
                  which=None, isfile=None, isdir=None, glob=None,
                  extra_globs=()):
    """Office 系就绪判定（单测可注入 which/isfile/isdir/glob）：
    pywin32 COM 环境 + 主程序存在（PATH / 固定路径 / 版本号目录 glob）两者缺一不可。
    只查 pywin32 会把'装了 pywin32 但没装 Word'误判为已安装（此前 bug）。"""
    import shutil as _sh
    which = which or _sh.which
    isfile = isfile or os.path.isfile
    isdir = isdir or os.path.isdir
    if glob is None:
        import glob as _g
        glob = _g.glob
    if not has_com:
        return False
    try:
        for n in exe_names:
            if which(n):
                return True
    except Exception:
        pass
    try:
        for p in extra_files:
            if p and isfile(p):
                return True
        for d in extra_dirs:
            if d and isdir(d):
                return True
        for pat in extra_globs:
            if glob(pat):
                return True
    except Exception:
        pass
    return False


def detect_engines(presets=None, root=None):
    """单引擎可用性探测（只读：不启动进程/浏览器）。
    返回 {单引擎名: bool}。presets 为空时读内置 config（取 engines.paths/external）。"""
    import shutil
    if presets is None:
        try:
            from pycbeta.theme import load_presets
            presets = load_presets()
        except Exception:
            presets = {}
    eng = (presets or {}).get("engines") or {}
    paths = eng.get("paths") or {}
    external = eng.get("external") or {}
    root = root or REPO_ROOT

    def _exe_exists(p):
        if not p:
            return False
        if os.path.isabs(p) and os.path.isfile(p):
            return True
        return os.path.isfile(os.path.join(root, p))

    try:
        import win32com.client  # noqa: F401
        has_com = True
    except Exception:
        has_com = False
    try:
        import playwright  # noqa: F401
        has_chromium = True
    except Exception:
        has_chromium = False
    try:
        import weasyprint  # noqa: F401
        has_weasy = True
    except Exception:
        has_weasy = False
    lo = paths.get("libreoffice") or ""
    has_lo = _exe_exists(lo) or bool(shutil.which("soffice") or shutil.which("soffice.exe")
                                     or shutil.which("soffice.com"))
    has_docbuilder = _exe_exists(paths.get("docbuilder") or "") or bool(shutil.which("docbuilder"))
    has_prince = bool(shutil.which("prince") or shutil.which("prince.exe"))
    mini_exe = (external.get("minipdf") or {}).get("executable") or "engines/minipdf.exe"
    cbeta_exe = (external.get("cbetapdf") or {}).get("executable") or "engines/cbetapdf.exe"
    local_wps = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Kingsoft", "WPS Office")
    wps_globs = list(WPS_GLOBS)
    if local_wps:
        wps_globs += [local_wps + "\\*\\office6\\" + exe
                      for exe in ("wps.exe", "et.exe", "wpp.exe")]
    return {
        "msword": _office_ready(MSWORD_EXES, MSWORD_PATHS, (), has_com,
                                extra_globs=MSWORD_GLOBS),
        "wps": _office_ready(WPS_EXES, (), WPS_DIRS, has_com,
                             extra_globs=wps_globs),
        "docbuilder": has_docbuilder, "libreoffice": has_lo,
        "minipdf": _exe_exists(mini_exe) or bool(shutil.which("minipdf")),
        "chromium": has_chromium,
        "prince": has_prince, "weasyprint": has_weasy,
        "cbetapdf": _exe_exists(cbeta_exe),
    }
BRACKET_PRESETS = {
    "〔〕": ["〔", "〕"],
    "（）": ["（", "）"],
    "[]": ["[", "]"],
}
STYLE_ITEMS = [("汉字上方 ruby", "ruby"), ("汉字右侧行内", "inline"), ("汉字上方 WPS 域", "field")]
REPEAT_ITEMS = [("每次都注", "all"), ("全文只注首次", "first"), ("每单元只注首次", "page")]
SCHEME_ITEMS = [("拼音", "pinyin"), ("注音符号", "zhuyin")]
BRACKET_NAMES = list(BRACKET_PRESETS.keys())
SERIES_FONTS = ["隸書, LiSu", "楷體, KaiTi", "宋体, SimSun", "黑體, SimHei",
                "新細明體, PMingLiU", "微軟正黑體"]


def slot_paths(root=None):
    """三槽路径 (出厂, 当前, 上一次)。root 默认为仓库根（单测可覆写）。"""
    root = root or REPO_ROOT
    return (os.path.join(root, FACTORY_NAME),
            os.path.join(root, USER_NAME),
            os.path.join(root, LAST_NAME))


def _read_json(path):
    # 出厂 config.json 含 // 注释，走 load_presets 去注释解析；
    # 用户槽文件为本模块纯 JSON 写出，同样兼容。
    from pycbeta.theme import load_presets
    return load_presets(path)


def load_slot(which="user", root=None):
    """读槽：which ∈ user/last/factory。user 缺失回退 factory。
    返回 (data, actual)，actual 为实际来源槽名。"""
    factory, user, last = slot_paths(root)
    if which == "factory":
        return _read_json(factory), "factory"
    if which == "last":
        return _read_json(last), "last"
    if os.path.isfile(user):
        return _read_json(user), "user"
    return _read_json(factory), "factory"


def save_current(data, root=None):
    """保存当前：上一次 ← 当前文件（若存在），当前 ← data。返回实际来源链。"""
    _factory, user, last = slot_paths(root)
    if os.path.isfile(user):
        with open(user, encoding="utf-8") as f:
            prev = f.read()
        with open(last, "w", encoding="utf-8") as f:
            f.write(prev)
        rotated = True
    else:
        rotated = False
    with open(user, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"rotated": rotated}


def reset_factory(root=None):
    """还原出厂：上一次 ← 当前文件（若存在），当前 ← 出厂拷贝。返回出厂数据。"""
    factory, user, last = slot_paths(root)
    if os.path.isfile(user):
        with open(user, encoding="utf-8") as f:
            prev = f.read()
        with open(last, "w", encoding="utf-8") as f:
            f.write(prev)
    with open(factory, encoding="utf-8") as f:
        text = f.read()
    with open(user, "w", encoding="utf-8") as f:
        f.write(text)
    return _read_json(factory)


@dataclass
class XmlOptions:
    """面板数据模型（字段含义见 docs/GUI设计.md §2）。"""
    page: str = "a4"
    font_set: str = "default"
    engine: str = "docx2pdf"
    margins: Optional[dict] = None          # None=跟随页面预设；否则 {top,right,bottom,left} mm
    formats: List[str] = field(default_factory=lambda: ["pdf"])
    output: dict = field(default_factory=dict)
    font_scale: float = 1.0
    pagination: dict = field(default_factory=dict)
    series_title: dict = field(default_factory=dict)
    t2s: bool = False
    annotations: dict = field(default_factory=dict)
    verify: dict = field(default_factory=dict)


def options_from_presets(presets):
    """presets → XmlOptions（面板 set_options 用；缺键取设计默认值）。"""
    out = (presets.get("output") or {})
    pages = (presets.get("pages") or {})
    return XmlOptions(
        page="a4" if "a4" in pages else (next(iter(pages), "a4")),
        font_set="default",
        engine="docx2pdf",
        margins=None,
        formats=["pdf"],
        output={k: copy.deepcopy(v) for k, v in out.items()
                if k not in ("pagination", "series_title")},
        font_scale=float(out.get("font_scale", 1.0) or 1.0),
        pagination=copy.deepcopy(out.get("pagination") or {}),
        series_title=copy.deepcopy(out.get("series_title") or {}),
        t2s=bool(out.get("t2s", False)),
        annotations=copy.deepcopy(presets.get("annotations") or {}),
        verify=copy.deepcopy(presets.get("verify") or {}),
    )


def write_temp_presets(base, opts, path=None):
    """XmlOptions → 临时 presets JSON（子进程桥 --config 用）。
    以 base（当前槽）为底，合并 output/pagination/series_title/annotations/verify
    与页面边距；调用方用后删除。返回路径。"""
    data = copy.deepcopy(base)
    data.setdefault("output", {}).update(copy.deepcopy(opts.output or {}))
    if opts.pagination:
        data["output"]["pagination"] = copy.deepcopy(opts.pagination)
    if opts.series_title:
        data["output"]["series_title"] = copy.deepcopy(opts.series_title)
    if opts.annotations:
        data["annotations"] = copy.deepcopy(opts.annotations)
    if opts.verify:
        data.setdefault("verify", {}).update(copy.deepcopy(opts.verify))
    if opts.margins:
        data.setdefault("pages", {}).setdefault(opts.page, {})["margins"] = \
            copy.deepcopy(opts.margins)
    data["output"]["t2s"] = bool(opts.t2s)
    data["output"]["font_scale"] = float(opts.font_scale or 1.0)
    if path is None:
        fd, path = tempfile.mkstemp(prefix="xml2pdf-gui-", suffix=".json")
        os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


class XmlOptionsPanel(QWidget):
    """七选项卡面板。get_options/set_options；值变更发 optionsChanged。"""
    optionsChanged = Signal(object)

    def __init__(self, presets=None, parent=None):
        super().__init__(parent)
        self._presets = presets or {}
        self._emitting = False
        self._font_dirty = False      # 字体下拉被手动碰过（t2s 自动切换豁免）
        self._font_auto = False       # 当前字体为 t2s 自动切入
        self._font_before_auto = "default"
        self._emitting = True
        try:
            self._build()
        finally:
            self._emitting = False
        if presets:
            self.set_options(options_from_presets(presets))

    # ---------- 构造 ----------
    def _build(self):
        layout = QVBoxLayout(self)
        cfg = QGroupBox("配置")
        bar = QHBoxLayout(cfg)
        self.slot_label = QLabel("当前：出厂默认")
        self.btn_save = QPushButton("保存到配置")
        self.btn_reset = QPushButton("还原出厂")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_reset.clicked.connect(self._on_reset)
        bar.addWidget(self.slot_label)
        bar.addStretch(1)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_reset)
        layout.addWidget(cfg)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._tab_formats(), "输出格式")
        self.tabs.addTab(self._tab_page(), "页面")
        self.tabs.addTab(self._tab_pagination(), "分页")
        self.tabs.addTab(self._tab_layout(), "排版")
        self.tabs.addTab(self._tab_notes(), "注释")
        self.tabs.addTab(self._tab_ann(), "注音")
        self.tabs.addTab(self._tab_verify(), "校验")

    def _combo(self, items, cur=None):
        box = QComboBox()
        for label, value in items:
            box.addItem(label, value)
        if cur is not None:
            i = box.findData(cur)
            if i >= 0:
                box.setCurrentIndex(i)
        box.currentIndexChanged.connect(lambda _i: self._changed())
        return box

    def _check(self, text, checked=False):
        box = QCheckBox(text)
        box.setChecked(checked)
        box.toggled.connect(lambda _v: self._changed())
        return box

    def _changed(self):
        if not self._emitting:
            self.optionsChanged.emit(self.get_options())

    # ---------- 各卡 ----------
    def _tab_page(self):
        w = QWidget()
        form = QFormLayout(w)
        pages = self._presets.get("pages") or {"a4": {}}
        self.page_box = QComboBox()
        for name, cfg in pages.items():
            size = (cfg or {}).get("size") or []
            if len(size) == 2:
                label = f"{name}（{size[0]}×{size[1]}mm）"
            else:
                label = name
            self.page_box.addItem(label, name)
        self.page_box.setFixedWidth(220)
        self.page_box.currentIndexChanged.connect(lambda _i: self._changed())
        form.addRow("纸张", self.page_box)
        self.margin_follow = QCheckBox("边距跟随页面预设")
        self.margin_follow.setChecked(True)
        self.margin_follow.toggled.connect(self._on_margin_follow)
        form.addRow("", self.margin_follow)
        self.margin_spins = {}
        grid = QGridLayout()
        for col, keys in enumerate((((("top", "上"), ("bottom", "下"))),
                                    ((("left", "左"), ("right", "右"))))):
            box = QVBoxLayout()
            for key, label in keys:
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 100.0)
                spin.setValue(25.4)
                spin.setSuffix(" mm")
                spin.setEnabled(False)
                spin.valueChanged.connect(lambda _v: self._changed())
                self.margin_spins[key] = spin
                cell = QHBoxLayout()
                cell.addWidget(QLabel(label))
                cell.addWidget(spin, 1)
                box.addLayout(cell)
            grid.addLayout(box, 0, col)
        form.addRow("边距", grid)
        self.grayscale_box = self._check("黑白输出")
        self.border_box = self._check("页面边框")
        form.addRow("", self.grayscale_box)
        form.addRow("", self.border_box)
        return w

    def _on_margin_follow(self, follow):
        for spin in self.margin_spins.values():
            spin.setEnabled(not follow)
        self._changed()

    def _font_items(self):
        sets = self._presets.get("font_sets") or {"default": {}}
        items = []
        for combo in sets.keys():
            items.append((combo, combo))
            items.append((f"{combo}:zh-Hans", f"{combo}:zh-Hans"))
        return items

    def _on_font_manual(self, _i):
        self._font_dirty = True
        self._font_auto = False
        self._changed()

    def _on_t2s(self, checked):
        if checked and not self._font_dirty and not self._font_auto:
            cur = self.font_box.currentData()
            base = (cur or "default").split(":")[0]
            self._font_before_auto = cur or "default"
            target = f"{base}:zh-Hans"
            i = self.font_box.findData(target)
            if i < 0:
                self.font_box.addItem(target, target)
                i = self.font_box.findData(target)
            self._emitting = True
            try:
                self.font_box.setCurrentIndex(i)
            finally:
                self._emitting = False
            self._font_auto = True
        if not checked and self._font_auto:
            i = self.font_box.findData(self._font_before_auto)
            self._emitting = True
            try:
                if i >= 0:
                    self.font_box.setCurrentIndex(i)
            finally:
                self._emitting = False
            self._font_auto = False
        self._changed()

    def _tab_formats(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        self.format_boxes = {}
        row = QHBoxLayout()
        row.addWidget(QLabel("格式"))
        for fmt in FORMATS:
            box = self._check(fmt, checked=(fmt == "pdf"))
            self.format_boxes[fmt] = box
            row.addWidget(box)
        row.addStretch(1)
        layout.addLayout(row)
        # 字体区（原字体卡并入）：简体转换在上，字体下拉在下
        frow = QHBoxLayout()
        self.t2s_box = self._check("简体转换（OpenCC t2s；自动套简体字库）")
        self.t2s_box.toggled.connect(self._on_t2s)
        frow.addWidget(self.t2s_box)
        frow.addWidget(QLabel("字体"))
        self.font_box = QComboBox()
        for label, value in self._font_items():
            self.font_box.addItem(label, value)
        self.font_box.currentIndexChanged.connect(self._on_font_manual)
        frow.addWidget(self.font_box, 1)
        layout.addLayout(frow)
        self.engine_group = QGroupBox("引擎（仅 PDF 需要）")
        el = QHBoxLayout(self.engine_group)
        from PySide6.QtWidgets import QRadioButton
        self.engine_docx = QRadioButton("docx2pdf")
        self.engine_html = QRadioButton("html2pdf")
        self.engine_docx.setChecked(True)
        self.engine_docx.toggled.connect(self._on_pipe_changed)
        self.engine_html.toggled.connect(self._on_pipe_changed)
        self.single_box = QComboBox()
        self.single_box.currentIndexChanged.connect(self._on_single_changed)
        el.addWidget(self.engine_docx)
        el.addWidget(self.engine_html)
        el.addWidget(QLabel("单引擎"))
        el.addWidget(self.single_box)
        el.addStretch(1)
        layout.addWidget(self.engine_group)
        self.engine_hint = self._hint("自动=按链顺序首个成功者；单引擎=只用该引擎，失败即报错")
        layout.addWidget(self.engine_hint)
        self._status = detect_engines(self._presets)
        self._refresh_singles()
        fl = QHBoxLayout()
        fl.addWidget(QLabel("字号缩放"))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.5, 3.0)
        self.scale_spin.setSingleStep(0.05)
        self.scale_spin.setValue(1.0)
        self.scale_spin.valueChanged.connect(lambda _v: self._changed())
        fl.addWidget(self.scale_spin)
        fl.addWidget(QLabel("（大字版 1.33/1.5）"))
        fl.addStretch(1)
        layout.addLayout(fl)
        layout.addStretch(1)
        self.format_boxes["pdf"].toggled.connect(self._on_pdf_toggled)
        self._on_pdf_toggled(self.format_boxes["pdf"].isChecked())
        return w

    def _pipe(self):
        return "html2pdf" if self.engine_html.isChecked() else "docx2pdf"

    def _refresh_singles(self, keep=""):
        """按管线重填单引擎下拉：首项恒为自动，其余带可用性后缀。keep 命中则恢复选中。"""
        names = HTML_SINGLES if self._pipe() == "html2pdf" else DOCX_SINGLES
        prev, self._emitting = self._emitting, True
        try:
            self.single_box.clear()
            self.single_box.addItem("自动（按链顺序）", "")
            for name in names:
                ok = self._status.get(name, False)
                label = f"{name}（已安装）" if ok else f"{name}（未安装，{INSTALL_HINTS[name]}）"
                self.single_box.addItem(label, name)
            i = self.single_box.findData(keep) if keep else 0
            self.single_box.setCurrentIndex(i if i >= 0 else 0)
        finally:
            self._emitting = prev
        self._update_engine_hint()

    def _update_engine_hint(self):
        single = self.single_box.currentData() or ""
        if not single:
            self.engine_hint.setStyleSheet("color: gray")
            self.engine_hint.setText("自动=按链顺序首个成功者；单引擎=只用该引擎，失败即报错")
        elif self._status.get(single, False):
            self.engine_hint.setStyleSheet("color: gray")
            self.engine_hint.setText(f"单引擎 {single} 已就绪")
        else:
            self.engine_hint.setStyleSheet("color: red")
            self.engine_hint.setText(f"单引擎 {single} 未安装：{INSTALL_HINTS.get(single, '')}")

    def _on_pipe_changed(self, _v):
        self._refresh_singles()
        self._changed()

    def _on_single_changed(self, _i):
        self._update_engine_hint()
        self._changed()

    def _on_pdf_toggled(self, checked):
        self.engine_group.setEnabled(checked)
        self._changed()

    def _hint(self, text):
        label = QLabel(text)
        label.setStyleSheet("color: gray")
        label.setWordWrap(True)
        return label

    def _tab_pagination(self):
        w = QWidget()
        grid = QGridLayout(w)
        left = QVBoxLayout()
        left.addWidget(self._hint("分节即分页单元：Word 里每节另起一页"))
        self.pg_boxes = {}
        for key in PAGINATION_KEYS:
            box = self._check(PAGINATION_LABELS[key])
            self.pg_boxes[key] = box
            left.addWidget(box)
        left.addStretch(1)
        grid.addLayout(left, 0, 0)
        right = QVBoxLayout()
        group = QGroupBox("佛典丛书名")
        form = QFormLayout(group)
        self.series_on = self._check("首页打印", checked=True)
        form.addRow("", self.series_on)
        self.series_font = QComboBox()
        self.series_font.setEditable(True)
        self.series_font.addItems(SERIES_FONTS)
        self.series_font.currentIndexChanged.connect(lambda _i: self._changed())
        self.series_font.editTextChanged.connect(lambda _v: self._changed())
        form.addRow("字体", self.series_font)
        self.series_size = QSpinBox()
        self.series_size.setRange(6, 72)
        self.series_size.setValue(9)
        self.series_size.valueChanged.connect(lambda _v: self._changed())
        form.addRow("字号", self.series_size)
        right.addWidget(group)
        right.addWidget(self._hint("印在首页左上角"))
        right.addStretch(1)
        grid.addLayout(right, 0, 1)
        return w

    def _tab_layout(self):
        w = QWidget()
        grid = QGridLayout(w)
        left = QVBoxLayout()
        left.addWidget(self._hint("卷名去重默认开启；按卷分文件与分页联动"))
        self.split_box = self._check("按卷分文件")
        self.close_juan_box = self._check("显示结束卷标题")
        self.dedup_box = self._check("卷名去重", checked=True)
        for b in (self.split_box, self.close_juan_box, self.dedup_box):
            left.addWidget(b)
        left.addStretch(1)
        grid.addLayout(left, 0, 0)
        right = QVBoxLayout()
        right.addWidget(self._hint("脏数据开关默认关闭（保留原文）；偈颂分隔符填两个全角空格，引号指「『 』"))
        self.ign_style_box = self._check("忽略 XML 样式脏数据")
        self.ign_space_box = self._check("忽略 XML 空格脏数据")
        self.strip_quotes_box = self._check("去掉偈颂首尾引号")
        right.addWidget(self.ign_style_box)
        right.addWidget(self.ign_space_box)
        self.caesura_edit = QLineEdit("　　")
        self.caesura_edit.textChanged.connect(lambda _v: self._changed())
        form = QFormLayout()
        form.addRow("偈颂分隔符", self.caesura_edit)
        right.addLayout(form)
        right.addWidget(self.strip_quotes_box)
        right.addStretch(1)
        grid.addLayout(right, 0, 1)
        return w

    def _tab_notes(self):
        w = QWidget()
        form = QFormLayout(w)
        self.notes_on = self._check("显示注释", checked=True)
        self.per_page_box = self._check("脚注每页重新编号", checked=True)
        self.title_notes_box = self._check("压制卷名/品名校勘注码")
        form.addRow("", self.notes_on)
        form.addRow("", self.per_page_box)
        form.addRow("", self.title_notes_box)
        self.brackets_box = self._combo([("全角（）", "fullwidth"), ("半角()", "halfwidth")],
                                        "fullwidth")
        form.addRow("inline 括号", self.brackets_box)
        return w

    def _tab_ann(self):
        w = QWidget()
        form = QFormLayout(w)
        self.ann_on = self._check("开启难字注音")
        form.addRow("", self.ann_on)
        self.ann_scheme = self._combo(SCHEME_ITEMS, "pinyin")
        form.addRow("方案", self.ann_scheme)
        self.ann_style = self._combo(STYLE_ITEMS, "inline")
        form.addRow("位置", self.ann_style)
        self.ann_brackets = self._combo([(k, k) for k in BRACKET_NAMES], "〔〕")
        form.addRow("括号", self.ann_brackets)
        self.ann_repeat = self._combo(REPEAT_ITEMS, "all")
        form.addRow("频率", self.ann_repeat)
        row = QHBoxLayout()
        self.ann_file = QLineEdit()
        self.ann_file.setPlaceholderText("空=内置词表")
        self.ann_file.textChanged.connect(lambda _v: self._changed())
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_ann_file)
        row.addWidget(self.ann_file)
        row.addWidget(browse)
        form.addRow("词表", row)
        return w

    def _browse_ann_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择注音词表", "", "TSV (*.txt *.tsv);;所有文件 (*)")
        if path:
            self.ann_file.setText(path)

    def _tab_verify(self):
        w = QWidget()
        form = QFormLayout(w)
        self.verify_on = self._check("转换后校验（对比官方文档）")
        form.addRow("", self.verify_on)
        self.maxdiff_spin = QSpinBox()
        self.maxdiff_spin.setRange(0, 1000)
        self.maxdiff_spin.setValue(10)
        self.maxdiff_spin.valueChanged.connect(lambda _v: self._changed())
        form.addRow("阈值 maxDiff", self.maxdiff_spin)
        self.difflines_spin = QSpinBox()
        self.difflines_spin.setRange(0, 50)
        self.difflines_spin.setValue(5)
        self.difflines_spin.valueChanged.connect(lambda _v: self._changed())
        form.addRow("差异行数", self.difflines_spin)
        self.autofetch_box = self._check("官方文档缺失自动下载", checked=True)
        self.scope_box = self._check("按卷限定官方文档", checked=True)
        form.addRow("", self.autofetch_box)
        form.addRow("", self.scope_box)
        return w

    # ---------- 三槽 ----------
    def _on_save(self):
        cur, _actual = load_slot("user")
        save_current(self._presets_merged(cur))
        self.slot_label.setText("当前：用户配置（已保存）")
        self._changed()

    def _presets_merged(self, cur):
        """当前槽为底 + 面板值合并 → 可存 presets。"""
        data = copy.deepcopy(cur)
        opts = self.get_options()
        data.setdefault("output", {}).update(copy.deepcopy(opts.output or {}))
        if opts.pagination:
            data["output"]["pagination"] = copy.deepcopy(opts.pagination)
        if opts.series_title:
            data["output"]["series_title"] = copy.deepcopy(opts.series_title)
        if opts.annotations:
            data["annotations"] = copy.deepcopy(opts.annotations)
        if opts.verify:
            data.setdefault("verify", {}).update(copy.deepcopy(opts.verify))
        if opts.margins:
            data.setdefault("pages", {}).setdefault(opts.page, {})["margins"] = \
                copy.deepcopy(opts.margins)
        data["output"]["t2s"] = bool(opts.t2s)
        data["output"]["font_scale"] = float(opts.font_scale or 1.0)
        return data

    def _on_reset(self):
        reset_factory()
        self.set_options(options_from_presets(load_slot("user")[0]))
        self.slot_label.setText("当前：出厂默认（已还原）")
        self._changed()

    def mark_slot(self, actual):
        self.slot_label.setText(f"当前：{'用户配置' if actual == 'user' else '出厂默认'}")

    # ---------- 读写 ----------
    def get_options(self):
        follow = self.margin_follow.isChecked()
        margins = None
        if not follow:
            margins = {k: float(sp.value()) for k, sp in self.margin_spins.items()}
        pipe = "docx2pdf" if self.engine_docx.isChecked() else "html2pdf"
        single = self.single_box.currentData() or ""
        engine = f"{pipe}:{single}" if single else pipe
        return XmlOptions(
            page=self.page_box.currentData() or self.page_box.currentText(),
            font_set=self.font_box.currentData() or "default",
            engine=engine,
            margins=margins,
            formats=[f for f, b in self.format_boxes.items() if b.isChecked()] or ["pdf"],
            output={
                "grayscale": self.grayscale_box.isChecked(),
                "page_border": self.border_box.isChecked(),
                "show_notes": self.notes_on.isChecked(),
                "footnote_per_page": self.per_page_box.isChecked(),
                "suppress_title_notes": self.title_notes_box.isChecked(),
                "inline_brackets": self.brackets_box.currentData(),
                "split_juan": self.split_box.isChecked(),
                "show_close_juan": self.close_juan_box.isChecked(),
                "suppress_jhead_dup": self.dedup_box.isChecked(),
                "ignore_xml_style": self.ign_style_box.isChecked(),
                "ignore_xml_space": self.ign_space_box.isChecked(),
                "verse_caesura": self.caesura_edit.text(),
                "verse_strip_quotes": self.strip_quotes_box.isChecked(),
            },
            font_scale=float(self.scale_spin.value()),
            pagination={k: b.isChecked() for k, b in self.pg_boxes.items()},
            series_title={"enabled": self.series_on.isChecked(),
                          "font": self.series_font.currentText(),
                          "size": int(self.series_size.value())},
            t2s=self.t2s_box.isChecked(),
            annotations={
                "enabled": self.ann_on.isChecked(),
                "scheme": self.ann_scheme.currentData(),
                "style": self.ann_style.currentData(),
                "brackets": list(BRACKET_PRESETS[self.ann_brackets.currentText()]),
                "repeat": self.ann_repeat.currentData(),
                "file": self.ann_file.text().strip(),
            },
            verify={
                "enabled": self.verify_on.isChecked(),
                "maxDiff": int(self.maxdiff_spin.value()),
                "diffLines": int(self.difflines_spin.value()),
                "auto_fetch": self.autofetch_box.isChecked(),
                "scope_juan": self.scope_box.isChecked(),
            },
        )

    def set_options(self, opts):
        self._emitting = True
        try:
            i = self.page_box.findData(opts.page)
            if i < 0:
                i = self.page_box.findText(opts.page)
            if i >= 0:
                self.page_box.setCurrentIndex(i)
            self.margin_follow.setChecked(opts.margins is None)
            if opts.margins:
                for k, sp in self.margin_spins.items():
                    if k in opts.margins:
                        sp.setValue(float(opts.margins[k]))
            self._on_margin_follow(opts.margins is None)
            self.grayscale_box.setChecked(bool(opts.output.get("grayscale", False)))
            self.border_box.setChecked(bool(opts.output.get("page_border", False)))
            i = self.font_box.findData(opts.font_set)
            if i < 0:
                self.font_box.addItem(opts.font_set, opts.font_set)
                i = self.font_box.findData(opts.font_set)
            self.font_box.setCurrentIndex(i)
            self._font_dirty = False
            self._font_auto = False
            self.t2s_box.setChecked(bool(opts.t2s))
            for f, b in self.format_boxes.items():
                b.setChecked(f in (opts.formats or ["pdf"]))
            pipe, _, single = (opts.engine or "docx2pdf").partition(":")
            (self.engine_docx if pipe != "html2pdf" else self.engine_html).setChecked(True)
            self._refresh_singles(keep=single)
            self._on_pdf_toggled("pdf" in (opts.formats or ["pdf"]))
            self.scale_spin.setValue(float(opts.font_scale or 1.0))
            pg = opts.pagination or {}
            for k, b in self.pg_boxes.items():
                b.setChecked(bool(pg.get(k, False)))
            o = opts.output or {}
            self.split_box.setChecked(bool(o.get("split_juan", False)))
            self.close_juan_box.setChecked(bool(o.get("show_close_juan", False)))
            self.dedup_box.setChecked(bool(o.get("suppress_jhead_dup", True)))
            self.ign_style_box.setChecked(bool(o.get("ignore_xml_style", False)))
            self.ign_space_box.setChecked(bool(o.get("ignore_xml_space", False)))
            self.caesura_edit.setText(str(o.get("verse_caesura", "　　")))
            self.strip_quotes_box.setChecked(bool(o.get("verse_strip_quotes", False)))
            st = opts.series_title or {}
            self.series_on.setChecked(bool(st.get("enabled", True)))
            if st.get("font"):
                self.series_font.setCurrentText(str(st["font"]))
            self.series_size.setValue(int(st.get("size", 9) or 9))
            self.notes_on.setChecked(bool(o.get("show_notes", True)))
            self.per_page_box.setChecked(bool(o.get("footnote_per_page", True)))
            self.title_notes_box.setChecked(bool(o.get("suppress_title_notes", False)))
            i = self.brackets_box.findData(o.get("inline_brackets", "fullwidth"))
            if i >= 0:
                self.brackets_box.setCurrentIndex(i)
            an = opts.annotations or {}
            self.ann_on.setChecked(bool(an.get("enabled", False)))
            for box, key, default in ((self.ann_scheme, "scheme", "pinyin"),
                                      (self.ann_style, "style", "inline"),
                                      (self.ann_repeat, "repeat", "all")):
                j = box.findData(an.get(key, default))
                if j >= 0:
                    box.setCurrentIndex(j)
            pair = tuple(an.get("brackets") or ["〔", "〕"])
            for name, pv in BRACKET_PRESETS.items():
                if tuple(pv) == pair:
                    self.ann_brackets.setCurrentText(name)
                    break
            self.ann_file.setText(str(an.get("file", "")))
            vf = opts.verify or {}
            self.verify_on.setChecked(bool(vf.get("enabled", False)))
            self.maxdiff_spin.setValue(int(vf.get("maxDiff", 10) or 10))
            self.difflines_spin.setValue(int(vf.get("diffLines", 5) or 5))
            self.autofetch_box.setChecked(bool(vf.get("auto_fetch", True)))
            self.scope_box.setChecked(bool(vf.get("scope_juan", True)))
        finally:
            self._emitting = False
        self._changed()


SOURCE_LABELS = [
    ("xml_dir", "本地 XML 目录（优先查找）"),
    ("download_dir", "官方下载落盘目录（缺失时下载到这）"),
    ("catalog", "佛典目录 catalog（sutra_mapping.txt）"),
]
DOWNLOAD_KEYS = ["xml", "xml_repo", "html", "docx", "epub", "txt", "txt_notes", "odt"]


def apply_source_edits(base, values):
    """纯函数：base presets + values{source:{...}, downloads:{...}} → 合并副本。
    只覆盖所给键（空字符串视为清空，不写 None）。"""
    data = copy.deepcopy(base)
    for k, v in (values.get("source") or {}).items():
        if v is not None:
            data.setdefault("source", {})[k] = v
    for k, v in (values.get("downloads") or {}).items():
        if v is not None:
            data.setdefault("downloads", {})[k] = v
    return data


class SourceDialog(QDialog):
    """数据源窗口：查看/编辑输入来源目录与 CBETA 官方下载 URL 模板。
    确定 = 合并进当前槽并保存（走三槽轮换）；取消 = 丢弃。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据源（source / downloads）")
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        data, _actual = load_slot("user")
        src = (data.get("source") or {})
        form = QFormLayout()
        self.path_edits = {}
        for key, label in SOURCE_LABELS:
            row = QHBoxLayout()
            edit = QLineEdit(str(src.get(key, "")))
            browse = QPushButton("浏览…")
            if key == "catalog":
                browse.clicked.connect(lambda _v, e=edit: self._browse_file(e))
            else:
                browse.clicked.connect(lambda _v, e=edit: self._browse_dir(e))
            row.addWidget(edit, 1)
            row.addWidget(browse)
            form.addRow(f"{label}\nsource.{key}", row)
            self.path_edits[key] = edit
        layout.addLayout(form)
        layout.addWidget(QLabel("官方下载 URL 模板（{canon}/{vol}/{file}/{id} 为占位符）："))
        self.dl_table = QTableWidget(0, 2)
        self.dl_table.setHorizontalHeaderLabels(["格式", "URL 模板"])
        self.dl_table.horizontalHeader().setStretchLastSection(True)
        dl = (data.get("downloads") or {})
        keys = [k for k in DOWNLOAD_KEYS if k in dl] + \
            [k for k in dl.keys() if k not in DOWNLOAD_KEYS]
        self.dl_table.setRowCount(len(keys))
        for i, k in enumerate(keys):
            key_item = QTableWidgetItem(k)
            key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)  # 键列只读
            self.dl_table.setItem(i, 0, key_item)
            self.dl_table.setItem(i, 1, QTableWidgetItem(str(dl[k])))
        layout.addWidget(self.dl_table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "选择目录", edit.text().strip() or "")
        if d:
            edit.setText(d)

    def _browse_file(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "选择 catalog 文件",
                                              edit.text().strip() or "", "文本 (*.txt);;所有文件 (*)")
        if path:
            edit.setText(path)

    def accept(self):
        data, _actual = load_slot("user")
        values = {"source": {k: e.text().strip() for k, e in self.path_edits.items()},
                  "downloads": {}}
        for i in range(self.dl_table.rowCount()):
            k = self.dl_table.item(i, 0).text()
            v = self.dl_table.item(i, 1).text() if self.dl_table.item(i, 1) else ""
            values["downloads"][k] = v.strip()
        save_current(apply_source_edits(data, values))
        super().accept()


class XmlOptionsDialog(QDialog):
    """面板的对话框包装：Accept→选项，Cancel→None。"""

    def __init__(self, presets=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("XML 转换选项")
        layout = QVBoxLayout(self)
        self.panel = XmlOptionsPanel(presets)
        layout.addWidget(self.panel)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_options(self):
        return self.panel.get_options() if self.result() == QDialog.Accepted else None
