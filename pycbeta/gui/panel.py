"""XML 转换选项面板（P1 GUI 链路 B 可复用组件）。

八选项卡：输出格式 / 样式表 / 页面 / 分页 / 排版 / 注释 / 注音 / 校验。
控件值 ↔ XmlOptions ↔ config presets 三向同步；dict 型选项经临时 presets 进子进程桥。

配置预设统一放仓库根 `presets/*.json`（随仓库发布）：下拉选中即载入，
保存=覆盖选中、另存为=新建、删除=删选中、设为默认=run.json 的 config-json 槽指选中。
出厂只读 `pycbeta/config.json`；默认用户预设 `presets/config.user.json`（git 忽略）。
"""
import copy
import json
import os
import tempfile

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout,
    QWidget,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "styles")
# 样式表卡：默认两 CSS（路径, 说明）
STYLE_FILES = (
    ("pdf_docx.css", "印刷主题（pdf/docx 专用）"),
    ("cbeta_golden.css", "电子书基底（html/epub；官方电子书样式）"),
)
FACTORY_NAME = os.path.join("pycbeta", "config.json")
# 默认用户预设（在 presets/ 内，git 忽略）；下拉首项“出厂默认”为空值
USER_PRESET_NAME = "config.user.json"
PRESET_DIRNAME = "presets"
SENTINEL_LABEL = "（出厂默认）"
SLOT_NAME_WIDTH = 220    # “当前配置：<名>”里名字的固定显示宽度（px），超长省略

PAGINATION_KEYS = ["enabled", "duplex", "juan", "juan_first", "mulu_level1", "pb", "tei"]
PAGINATION_LABELS = {
    "enabled": "智能分页", "duplex": "双面打印", "juan": "卷首换页",
    "juan_first": "首卷换页", "mulu_level1": "序/品 level1 换页",
    "pb": "按 pb 分页", "tei": "尾页换页",
}
FORMATS = ["pdf", "docx", "html", "epub", "md", "txt"]
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
REPEAT_ITEMS = [("每次都注", "all"), ("全文只注首次", "first"), ("每页只注首次", "page")]
SCHEME_ITEMS = [("拼音", "pinyin"), ("注音符号", "zhuyin")]
BRACKET_NAMES = list(BRACKET_PRESETS.keys())


def slot_paths(root=None):
    """(出厂, 默认用户预设) 路径。默认用户预设 = `presets/config.user.json`。"""
    root = root or REPO_ROOT
    return (os.path.join(root, FACTORY_NAME),
            os.path.join(root, PRESET_DIRNAME, USER_PRESET_NAME))


def _read_json(path):
    # 出厂 config.json 含 // 注释，走 load_presets 去注释解析；
    # 用户预设文件为本模块纯 JSON 写出，同样兼容。
    from pycbeta.theme import load_presets
    return load_presets(path)


def load_slot(which="user", root=None):
    """读默认用户预设（which='user'）或出厂（which='factory'）。
    用户预设缺失回退出厂。返回 (data, actual)，actual ∈ {"user","factory"}。"""
    factory, user = slot_paths(root)
    if which == "factory":
        return _read_json(factory), "factory"
    if os.path.isfile(user):
        return _read_json(user), "user"
    return _read_json(factory), "factory"


def save_current(data, root=None):
    """把 data 写入默认用户预设 `presets/config.user.json`（无轮换）。"""
    _factory, user = slot_paths(root)
    os.makedirs(os.path.dirname(user), exist_ok=True)
    with open(user, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"rotated": False}


def reset_factory(root=None):
    """读出厂配置（只读，不写盘）。返回出厂数据。"""
    factory, _user = slot_paths(root)
    return _read_json(factory)


def config_presets_dir(root=None):
    """配置预设目录（仓库根 presets/；随仓库发布；*.json 快照）。
    与样式预设 *.css 混放，按扩展名区分。"""
    from pycbeta.theme import user_presets_dir
    return user_presets_dir(root)


def list_config_presets(root=None):
    """命名配置快照 → [(stem, path)]（仅 presets/*.json，按名排序）。"""
    d = os.path.abspath(config_presets_dir(root))
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.lower().endswith(".json"):
            out.append((os.path.splitext(fn)[0], os.path.join(d, fn)))
    return out


def _config_preset_path(name_or_path, root=None):
    d = os.path.abspath(config_presets_dir(root))
    cand = (name_or_path if os.path.isabs(name_or_path or "")
            else os.path.join(d, name_or_path or ""))
    if not cand.lower().endswith(".json"):
        cand += ".json"
    return cand


def save_config_preset(name, data, root=None):
    """快照另存进 presets/<stem>.json；同名覆盖；返回路径。空名抛 ValueError。"""
    from pycbeta.theme import safe_preset_stem
    stem = safe_preset_stem(name)
    if not stem:
        raise ValueError("预设名为空")
    d = os.path.abspath(config_presets_dir(root))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, stem + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def load_config_preset(name_or_path, root=None):
    """读命名快照 → dict（经 _read_json，容忍 // 注释）；缺失抛 ValueError。"""
    path = _config_preset_path(name_or_path, root)
    if not os.path.isfile(path):
        raise ValueError(f"配置预设不存在：{name_or_path}")
    return _read_json(path)


def delete_config_preset(name_or_path, root=None):
    """删除 presets/ 内 .json 快照；目录外/不存在抛 ValueError。"""
    d = os.path.abspath(config_presets_dir(root))
    ap = os.path.abspath(_config_preset_path(name_or_path, root))
    if not ap.lower().endswith(".json") or not os.path.isfile(ap):
        raise ValueError(f"配置预设不存在：{name_or_path}")
    if not (ap == d or ap.startswith(d + os.sep)):
        raise ValueError(f"不在预设目录内：{name_or_path}")
    os.remove(ap)
    return True


def load_run_and_presets(root=None):
    """(run, 有效配置)：run.json 缺失 → 缺省 run；非法 → 缺省 run（打印，不崩界面）。
    有效配置 = 出厂 ← base 文件按鍵合并（与 CLI 一致；面板显示/批量快照共用）。"""
    from pycbeta.theme import (load_run_config, resolve_effective_config,
                               default_run_path, DEFAULT_RUN_CONFIG)
    try:
        run = load_run_config(None, root)
    except ValueError as exc:
        print(f"run.json 非法，用缺省：{exc}")
        run = dict(DEFAULT_RUN_CONFIG)
    try:
        rdir = os.path.dirname(os.path.abspath(default_run_path(root)))
        presets = resolve_effective_config(run, rdir)
    except Exception:
        presets = {}
    return run, presets


def write_temp_run(run, snapshot_path, path=None):
    """临时 run.json（GUI 批量桥用）：复用当前 run 槽，config-json 指快照文件。
    调用方用后删除。返回路径。"""
    import tempfile
    from pycbeta.theme import RUN_KEYS
    data = {k: (run or {}).get(k, "") for k in RUN_KEYS}
    data["config-json"] = snapshot_path
    if path is None:
        fd, path = tempfile.mkstemp(prefix="xml2pdf-gui-run-", suffix=".json")
        os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def write_temp_preset(data, path=None):
    """任意预设 dict → 临时 JSON（一次性改动，不改已有预设/不落 presets/）。

    供第三方（publish）把 `XmlOptionsDialog.get_preset(base)` 的结果直接喂
    `--config`；`--config` 兼容「基础配置 JSON」与「run.json 组合单」两种形态。
    调用方用后删除。返回路径。
    """
    import tempfile
    if path is None:
        fd, path = tempfile.mkstemp(prefix="xml2pdf-preset-", suffix=".json")
        os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data if isinstance(data, dict) else {}, f,
                  ensure_ascii=False, indent=2)
    return path


@dataclass
class XmlOptions:
    """面板数据模型（字段含义见 docs/GUI设计.md §2）。"""
    page: str = "a4"
    font_lang: str = "zh-Hant"        # 字库语言（CSS :root 双栏；t2s 自动切简体）
    engine: str = "docx2pdf"
    margins: Optional[dict] = None          # None=跟随页面预设；否则 {top,right,bottom,left} mm
    typo: Optional[dict] = None             # None=跟随 CSS body；否则 {"font-size","line-height"}
    formats: List[str] = field(default_factory=lambda: ["pdf"])
    output: dict = field(default_factory=dict)
    font_scale: float = 1.0
    pagination: dict = field(default_factory=dict)
    series_title: dict = field(default_factory=dict)
    t2s: bool = False
    vertical: bool = False            # 竖排直书（CLI --vertical；pdf 切 html2pdf 管线）
    annotations: dict = field(default_factory=dict)
    verify: dict = field(default_factory=dict)


def options_from_presets(presets):
    """presets → XmlOptions（面板 set_options 用；缺键取设计默认值）。"""
    out = (presets.get("output") or {})
    pages = (presets.get("pages") or {})
    dflt = presets.get("default_page") or "a4"
    page = dflt if dflt in pages else ("a4" if "a4" in pages
                                       else next(iter(pages), "a4"))
    cm = (pages.get(page) or {}).get("custom_margins")
    pg = pages.get(page) or {}
    _fs = (pg.get("body_font_size") or "").strip() \
        if isinstance(pg.get("body_font_size"), str) else ""
    _lh = str(pg.get("body_line_height") or "").strip()
    typo = {"font-size": _fs, "line-height": _lh}
    typo = {k: v for k, v in typo.items() if v} or None
    return XmlOptions(
        page=page,
        font_lang=presets.get("font_lang") or "zh-Hant",
        engine=presets.get("engine") or "docx2pdf",
        margins=dict(cm) if isinstance(cm, dict) else None,
        typo=typo,
        formats=list(presets.get("formats") or ["pdf"]),
        output={k: copy.deepcopy(v) for k, v in out.items()
                if k not in ("pagination", "series_title")},
        font_scale=float(out.get("font_scale", 1.0) or 1.0),
        pagination=copy.deepcopy(out.get("pagination") or {}),
        series_title=copy.deepcopy(out.get("series_title") or {}),
        t2s=bool(out.get("t2s", False)),
        vertical=bool(out.get("vertical", False)),
        annotations=copy.deepcopy(presets.get("annotations") or {}),
        verify=copy.deepcopy(presets.get("verify") or {}),
    )


def write_temp_presets(base, opts, path=None):
    """XmlOptions → 临时 presets JSON（子进程桥 --config 用）。
    以 base（当前槽）为底，合并 output/pagination/series_title/annotations/verify
    与页面边距；调用方用后删除。返回路径。"""
    data = copy.deepcopy(base)
    data.pop("theme", None)  # 遗留 theme 键退役（主题唯一来源是 run.json 槽）
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
        data.setdefault("pages", {}).setdefault(opts.page, {})[
            "custom_margins"] = copy.deepcopy(opts.margins)
    else:
        # 跟随：删 base 带来的僵尸 custom_margins，否则 CLI 按它渲染，
        # 界面却显示"跟随"——所见非所得
        _pg = (data.get("pages") or {}).get(opts.page)
        if isinstance(_pg, dict):
            _pg.pop("custom_margins", None)
    _tpg = data.setdefault("pages", {}).setdefault(opts.page, {})
    if opts.typo:
        _tpg["body_font_size"] = opts.typo.get("font-size", "")
        _tpg["body_line_height"] = opts.typo.get("line-height", "")
    else:
        _tpg.pop("body_font_size", None)
        _tpg.pop("body_line_height", None)
    data["output"]["t2s"] = bool(opts.t2s)
    data["output"]["vertical"] = bool(opts.vertical)
    data["output"]["font_scale"] = float(opts.font_scale or 1.0)
    if path is None:
        fd, path = tempfile.mkstemp(prefix="xml2pdf-gui-", suffix=".json")
        os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


class DataUpdateWorker(QThread):
    """官方数据更新后台线程：缺字库/字型/目录直链同步（失败不抛，进报告）。"""
    finished_report = Signal(list)

    def __init__(self, dry_run=False, parent=None):
        super().__init__(parent)
        self._dry_run = dry_run

    def run(self):
        from pycbeta.update_data import update_all
        try:
            rep = update_all(dry_run=self._dry_run)
        except Exception as exc:  # noqa: BLE001 —— 网络全挂也不崩界面
            rep = [{"key": "all", "status": "failed", "detail": str(exc)}]
        self.finished_report.emit(rep)


class EbookUpdateWorker(QThread):
    """电子书远程更新检查后台线程：逐 work 条件下载 XML（不改项不落盘）。"""
    finished_report = Signal(list)

    def __init__(self, presets, with_baselines=True, parent=None):
        super().__init__(parent)
        self._presets = presets
        self._with_baselines = with_baselines

    def run(self):
        from pycbeta.fetch import check_ebook_updates
        try:
            ebook = ((self._presets.get("source") or {})
                     .get("cbeta_ebook") or "").strip()
            rep = check_ebook_updates(ebook, self._presets,
                                      with_baselines=self._with_baselines)
        except Exception as exc:  # noqa: BLE001
            rep = [{"id": "all", "status": "failed", "detail": str(exc)}]
        self.finished_report.emit(rep)


class EbookUpdateDialog(QDialog):
    """更新检查结果：状态摘要 + 明细；一键拷贝「已更新 ID」（供重新生成电子书）。"""

    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("电子书更新检查")
        self.resize(560, 420)
        from pycbeta.fetch import format_update_report
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText("\n".join(format_update_report(report or [])))
        layout.addWidget(self.text, 1)
        self._updated = [r["id"] for r in (report or [])
                         if r.get("status") == "updated"]
        row = QHBoxLayout()
        self.btn_copy = QPushButton("拷贝已更新 ID")
        self.btn_copy.setToolTip("将需重新生成的佛典編號复制到剪贴板（换行分隔）")
        self.btn_copy.setEnabled(bool(self._updated))
        self.btn_copy.clicked.connect(self._on_copy)
        row.addWidget(self.btn_copy)
        self.copy_status = QLabel("")
        self.copy_status.setStyleSheet("color: gray")
        row.addWidget(self.copy_status, 1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _on_copy(self):
        QApplication.clipboard().setText("\n".join(self._updated))
        self.copy_status.setText(f"已复制 {len(self._updated)} 个編號")


class XmlOptionsPanel(QWidget):
    """七选项卡面板。get_options/set_options；值变更发 optionsChanged。"""
    optionsChanged = Signal(object)

    def __init__(self, presets=None, parent=None):
        super().__init__(parent)
        self._presets = presets or {}
        self._emitting = False
        self._series_extra = {}       # series_title 旧 font/size 键透传保留
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
        self.cfg_preset_box = QComboBox()
        self.cfg_preset_box.setToolTip(
            "配置预设（presets/*.json + 出厂默认）：选中即载入面板")
        self.cfg_preset_box.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cfg_preset_box.setMinimumContentsLength(8)
        self.cfg_preset_box.setMaximumWidth(170)   # 收窄；下拉弹层按最长项放宽
        self.cfg_preset_box.currentIndexChanged.connect(self._on_preset_chosen)
        self.btn_preset_save = QPushButton("另存…")
        self.btn_preset_save.setToolTip("面板当前值另存进 presets/（命名快照，同名覆盖）")
        self.btn_preset_del = QPushButton("删除")
        self.btn_preset_del.setToolTip("删除当前选中的预设文件（出厂默认项不可删）")
        self.btn_save = QPushButton("保存")
        self.btn_save.setToolTip("面板当前值覆盖当前选中预设（出厂默认项置灰，请用另存…）")
        self.btn_set_default = QPushButton("设为默认")
        self.btn_set_default.setToolTip(
            "run.json 的 config-json 槽指向当前选中项（出厂默认=清空槽）")
        self.btn_reset = QPushButton("还原出厂")
        self._refresh_cfg_presets()
        self.btn_preset_save.clicked.connect(self._on_preset_save_as)
        self.btn_preset_del.clicked.connect(self._on_preset_delete)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_set_default.clicked.connect(self._on_set_default)
        self.btn_reset.clicked.connect(self._on_reset)
        bar.addWidget(self.slot_label)
        bar.addStretch(1)
        bar.addWidget(self.cfg_preset_box)
        bar.addWidget(self.btn_preset_save)
        bar.addWidget(self.btn_preset_del)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_set_default)
        bar.addWidget(self.btn_reset)
        layout.addWidget(cfg)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._tab_formats(), "输出格式")
        self.tabs.addTab(self._tab_styles(), "样式表")
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
            self.page_box.currentIndexChanged.connect(self._on_page_changed)
        form.addRow("纸张", self.page_box)
        self.margin_follow = QCheckBox("边距跟随页面预设")
        self.margin_follow.setChecked(True)
        self.margin_follow.toggled.connect(
            lambda v: self._on_margin_follow(v, fill=True))
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
        trow = QHBoxLayout()
        trow.addWidget(QLabel("字号"))
        self.typo_size_spin = QDoubleSpinBox()
        self.typo_size_spin.setRange(6.0, 72.0)
        self.typo_size_spin.setSingleStep(0.5)
        self.typo_size_spin.setDecimals(1)
        self.typo_size_spin.setSuffix(" pt")
        self.typo_size_spin.setEnabled(False)
        self.typo_size_spin.valueChanged.connect(
            lambda _v: (self._refresh_typo_display(), self._changed()))
        trow.addWidget(self.typo_size_spin)
        trow.addWidget(QLabel("行距"))
        self.typo_lh_spin = QDoubleSpinBox()
        self.typo_lh_spin.setRange(0.5, 3.0)
        self.typo_lh_spin.setSingleStep(0.05)
        self.typo_lh_spin.setDecimals(2)
        self.typo_lh_spin.setEnabled(False)
        self.typo_lh_spin.valueChanged.connect(
            lambda _v: (self._refresh_typo_display(), self._changed()))
        trow.addWidget(self.typo_lh_spin)
        self.typo_follow = QCheckBox("跟随 CSS body")
        self.typo_follow.setChecked(True)
        self.typo_follow.setToolTip("勾选则该纸张用 CSS body 字号行距；取消后可改，存入纸张条目")
        self.typo_follow.toggled.connect(
            lambda v: self._on_typo_follow(v, fill=True))
        trow.addWidget(self.typo_follow)
        trow.addStretch(1)
        form.addRow("正文", trow)
        self.typo_info = QLabel("")
        self.typo_info.setStyleSheet("color: gray")
        self.typo_info.setWordWrap(True)
        form.addRow("", self.typo_info)
        self.grayscale_box = self._check("黑白输出")
        self.border_box = self._check("页面边框")
        form.addRow("", self.grayscale_box)
        form.addRow("", self.border_box)
        return w

    def _preset_margins(self):
        """当前纸张预设边距（plain margins，忽略 custom_margins）。
        取消跟随填基线 / 跟随显示刷新同源；渲染侧 resolve_page 另走 custom 优先，
        两边各取所需（显示刷新的 bug 根因：之前复用 resolve_page 拿到 custom）。"""
        pages = self._presets.get("pages") or {}
        page = self.page_box.currentData() or self.page_box.currentText()
        entry = pages.get(page) or {}
        if not entry:
            low = (page or "").lower()
            for k, v in pages.items():
                if isinstance(k, str) and k.lower() == low \
                        and isinstance(v, dict):
                    entry = v
                    break
        m = entry.get("margins") or {}
        return {k: float(m.get(k, 25.4))
                for k in ("top", "right", "bottom", "left")}

    def _fill_margin_spins(self, use_custom=False):
        """spin 显示刷新。use_custom=False（默认）：plain 预设（跟随显示）；
        True：已存 custom 优先、否则预设（取消勾选恢复上次自定义）。"""
        from PySide6.QtCore import QSignalBlocker
        if use_custom:
            from pycbeta.theme import resolve_page
            page = self.page_box.currentData() or self.page_box.currentText()
            base = resolve_page(page, self._presets.get("pages"))["margins"]
        else:
            base = self._preset_margins()
        for k, sp in self.margin_spins.items():
            with QSignalBlocker(sp):
                sp.setValue(float(base.get(k, 25.4)))

    def _on_margin_follow(self, follow, fill=False):
        for spin in self.margin_spins.values():
            spin.setEnabled(not follow)
        if follow:
            # 重勾跟随：显示刷回预设（否则 disabled 框里留着旧自定义值，
            # 看着像还在用它——上报 bug 的"点两次才刷新"就是缺这一下）
            self._fill_margin_spins()
        elif fill:
            # 取消勾选：恢复已存自定义，没有才拿预设作起点（不能拿预设覆盖自定义）
            self._fill_margin_spins(use_custom=True)
        self._changed()

    def _on_page_changed(self, _i):
        # 跟随中切纸张：spin 显示刷新为新预设（disabled 仅展示）
        if self.margin_follow.isChecked():
            self._fill_margin_spins()
        self._refresh_typo_display()
        self._changed()

    def _css_body_typo(self):
        """出厂 CSS body 字号行距（取消跟随时填入基线）。"""
        from pycbeta.gui.css_editor import (body_font_size, body_line_height,
                                            factory_css_text)
        try:
            css = factory_css_text()
        except OSError:
            return "12pt", "1.5"
        import re
        m = re.match(r"^\s*([\d.]+)\s*pt\s*$", body_font_size(css) or "")
        size = float(m.group(1)) if m else 12.0
        lh = body_line_height(css) or "1.5"
        try:
            lh_v = float(lh)
        except (TypeError, ValueError):
            lh_v = 1.5
        return size, lh_v

    def _refresh_typo_display(self):
        """正文行显示：跟随 CSS body，或纸张绑定的当前框值（只显示，不写配置）。"""
        if self.typo_follow.isChecked():
            self.typo_info.setText("跟随 CSS body")
        else:
            self.typo_info.setText(
                f"纸张绑定：{self.typo_size_spin.value():g}pt／"
                f"{self.typo_lh_spin.value():g}")

    def _on_typo_follow(self, follow, fill=False):
        self.typo_size_spin.setEnabled(not follow)
        self.typo_lh_spin.setEnabled(not follow)
        if not follow and fill:
            from PySide6.QtCore import QSignalBlocker
            # 基线：本纸已有键用键值，否则出厂 CSS body
            pg = (self._presets.get("pages") or {}).get(
                self.page_box.currentData() or self.page_box.currentText()) or {}
            size, lh = self._css_body_typo()
            import re
            m = re.match(r"^\s*([\d.]+)\s*pt\s*$",
                         (pg.get("body_font_size") or ""))
            if m:
                size = float(m.group(1))
            try:
                lh = float(pg.get("body_line_height", lh))
            except (TypeError, ValueError):
                pass
            with QSignalBlocker(self.typo_size_spin):
                self.typo_size_spin.setValue(size)
            with QSignalBlocker(self.typo_lh_spin):
                self.typo_lh_spin.setValue(lh)
        self._refresh_typo_display()
        self._changed()

    def _on_t2s(self, checked):
        # 简体转换强制简体字库（下拉锁定为简体）；取消后解锁回繁体
        self._emitting = True
        try:
            if checked:
                i = self.lang_box.findData("zh-Hans")
                if i >= 0:
                    self.lang_box.setCurrentIndex(i)
                self.lang_box.setEnabled(False)
            else:
                self.lang_box.setEnabled(True)
        finally:
            self._emitting = False
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
        # 模式组（竖排在左，简体转换+字体下拉同行，共框）
        self.mode_group = QGroupBox("模式")
        gel = QHBoxLayout(self.mode_group)
        self.vert_box = self._check("竖排直书")
        self.vert_box.setToolTip("上→下、右→左；竖排时注音与注释序号保持横躺"
                                 "（WPS/LO 不渲染纵中横）")
        self.t2s_box = self._check("简体转换")
        self.t2s_box.setToolTip("OpenCC t2s 简繁转换；勾选后自动套简体字库")
        self.t2s_box.toggled.connect(self._on_t2s)
        gel.addWidget(self.vert_box)
        gel.addWidget(self.t2s_box)
        gel.addWidget(QLabel("字库"))
        self.lang_box = QComboBox()
        self.lang_box.addItem("繁体", "zh-Hant")
        self.lang_box.addItem("简体", "zh-Hans")
        self.lang_box.currentIndexChanged.connect(lambda _i: self._changed())
        self.lang_box.setToolTip("CSS :root 双栏变量切换；简体转换勾选后锁定为简体")
        gel.addWidget(self.lang_box, 1)
        gel.addStretch(1)
        layout.addWidget(self.mode_group)
        self.engine_group = QGroupBox("引擎（仅 PDF 需要）")
        el = QHBoxLayout(self.engine_group)
        from PySide6.QtWidgets import QRadioButton
        self.engine_docx = QRadioButton("docx2pdf")
        self.engine_html = QRadioButton("html2pdf")
        self.engine_docx.setChecked(True)
        self.engine_docx.setToolTip("DOCX→PDF（保真度高，默认；竖排时走 HTML 管线）")
        self.engine_html.setToolTip("HTML→PDF（Chromium 打印；竖排必选）")
        self.engine_docx.toggled.connect(self._on_pipe_changed)
        self.engine_html.toggled.connect(self._on_pipe_changed)
        self.single_box = QComboBox()
        self.single_box.setToolTip("自动=按链顺序首个成功者；单引擎=只用该引擎，失败即报错")
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

    def _tab_styles(self):
        w = QWidget()
        form = QFormLayout(w)
        from pycbeta.gui.css_editor import CssComboBox, set_user_theme
        trow = QHBoxLayout()
        self.theme_box = CssComboBox()
        self.theme_box.setToolTip("默认样式（run.json 的 pdf-docx-user-theme 槽；出厂默认第一）")
        trow.addWidget(self.theme_box, 1)
        self.theme_default_btn = QPushButton("设为默认")
        self.theme_default_btn.setToolTip("选中项写入 run.json 主题槽（永久生效）")
        self.theme_default_btn.clicked.connect(self._on_theme_default)
        trow.addWidget(self.theme_default_btn)
        self.theme_dir_btn = QPushButton("打开用户预设目录")
        self.theme_dir_btn.clicked.connect(lambda _v: self._open_local_file(
            self._user_presets_path()))
        trow.addWidget(self.theme_dir_btn)
        form.addRow("默认样式", trow)
        self.theme_status = QLabel()
        self.theme_status.setWordWrap(True)
        self.theme_status.setStyleSheet("color: gray")
        form.addRow("", self.theme_status)
        self._refresh_theme_box()
        self.style_rows = {}
        for name, desc in STYLE_FILES:
            path = os.path.abspath(os.path.join(_STYLES_DIR, name))
            row = QHBoxLayout()
            edit = QLineEdit(path)
            edit.setReadOnly(True)
            open_btn = QPushButton("打开")
            if os.path.isfile(path):
                open_btn.clicked.connect(
                    lambda _v, p=path: self._open_local_file(p))
            else:
                open_btn.setEnabled(False)
                edit.setStyleSheet("color: red")
                edit.setText(f"{path}（文件不存在）")
            row.addWidget(edit, 1)
            row.addWidget(open_btn)
            form.addRow(f"{name}\n{desc}", row)
            self.style_rows[name] = (edit, open_btn)
        self.btn_editor = QPushButton("打开 CSS 编辑器…")
        self.btn_editor.setToolTip("DOCX 所见即所得调样式（左改参/右预览），存预设进 presets/")
        self.btn_editor.clicked.connect(self._open_style_editor)
        form.addRow("", self.btn_editor)
        return w

    def _user_presets_path(self):
        from pycbeta.theme import user_presets_dir
        d = user_presets_dir()
        os.makedirs(d, exist_ok=True)
        return d

    def _refresh_theme_box(self, keep_value=None):
        from pycbeta.theme import resolve_theme_css
        from pycbeta.gui.css_editor import current_theme_value
        cur = keep_value if keep_value is not None else current_theme_value()
        self.theme_box.refresh(cur)
        _path, label = resolve_theme_css(cur)
        shown = _path or "内置 pdf_docx.css"
        if len(shown) > 60:
            shown = shown[:25] + "…" + shown[-30:]
        self.theme_status.setText(f"当前默认：{label}（{shown}）")
        if "缺失" in label or "不存在" in label:
            self.theme_status.setStyleSheet("color: red")
        else:
            self.theme_status.setStyleSheet("color: gray")

    def _on_theme_default(self):
        from pycbeta.gui.css_editor import set_user_theme
        value = self.theme_box.selected_value()
        try:
            set_user_theme(value)
        except OSError as exc:
            self.theme_status.setText(f"写入失败：{exc}")
            self.theme_status.setStyleSheet("color: red")
            return
        self._refresh_theme_box(keep_value=value)
        self._changed()

    def _open_style_editor(self):
        from pycbeta.gui.css_editor import CssEditorDialog
        single = self.single_box.currentData() or ""
        chain = [single] if single else None
        dlg = CssEditorDialog(sample_xml=None, engine_chain=chain, parent=self)
        dlg.exec()
        self._refresh_theme_box()  # 编辑器内可能改了默认

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
        auto_tip = "自动=按链顺序首个成功者；单引擎=只用该引擎，失败即报错"
        if not single:
            self.engine_hint.setStyleSheet("color: gray")
            self.engine_hint.setText("自动：按链顺序尝试")
            self.engine_hint.setToolTip(auto_tip)
        elif self._status.get(single, False):
            self.engine_hint.setStyleSheet("color: gray")
            self.engine_hint.setText(f"单引擎 {single} 已就绪")
            self.engine_hint.setToolTip(auto_tip)
        else:
            self.engine_hint.setStyleSheet("color: red")
            self.engine_hint.setText(f"单引擎 {single} 未安装")
            self.engine_hint.setToolTip(f"单引擎 {single} 未安装："
                                        f"{INSTALL_HINTS.get(single, '')}")

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
        self.series_css_btn = QPushButton("去 CSS 编辑器调样式…")
        self.series_css_btn.setToolTip("经藏名字体/字号走 CSS p.series-title（此处仅留开关）")
        self.series_css_btn.clicked.connect(self._open_style_editor)
        form.addRow("样式", self.series_css_btn)
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
        self.strip_no_box = self._check("去掉标题行首 No.")
        self.strip_no_box.setToolTip("去 head/jhead 行首 No. 令牌（如 No. 1116-B 序→序，余部去前导空格；正文内 No. 不动；书签保留原样）")
        for b in (self.split_box, self.close_juan_box, self.dedup_box,
                  self.strip_no_box):
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

        def _wrap(widget):
            h = QHBoxLayout()
            h.addWidget(widget)
            h.addStretch(1)
            return h

        # 正文设置（与「注释总开关」无关，排在前面）
        self.brackets_box = self._combo([("全角（）", "fullwidth"), ("半角()", "halfwidth")],
                                        "fullwidth")
        self.brackets_box.setToolTip(
            "正文夹注（<note place=\"inline\">，属原文）：括号形态\n"
            "与校注内联、注音括号独立；不受「显示注释」总开关控制")
        form.addRow("正文夹注", _wrap(self.brackets_box))
        self.siddham_box = self._check("正文显示悉昙字和读音", checked=True)
        self.siddham_box.setToolTip(
            "勾选后正文显示悉昙字和读音（如 种子字(raṃ)）；"
            "未安装悉昙字体Ranjana时显示替代字形（如歾）。"
            "不勾选则正文不显示，脚注不受影响")
        form.addRow("", self.siddham_box)

        # 注释总开关及其从属项
        self.notes_on = self._check("显示注释", checked=True)
        form.addRow("注释总开关", self.notes_on)
        self.per_page_box = self._check("脚注每页重新编号", checked=True)
        self.per_page_box.setToolTip("勾选后注释序号每页从 [1] 重排；不勾选则全文连续编号")
        self.title_notes_box = self._check("压制卷名/品名校勘注码")
        self.title_notes_box.setToolTip("勾选后卷名/品名标题后的上标注释序号隐藏，正文注码不受影响")
        form.addRow("", self.per_page_box)
        form.addRow("", self.title_notes_box)
        self.notes_mode = self._combo(
            [("页底脚注", "footnote"), ("文末尾注", "endnote"), ("括号内联", "inline")],
            "footnote")
        self.notes_mode.setToolTip(
            "注释方式：页底脚注（docx/pdf）/ 文末尾注 / 括号内联\n"
            "html/epub/md/txt 只区分“是否括号内联”；校验固定用脚注/尾注，不受此影响")
        self.notes_mode.setMaximumWidth(110)
        form.addRow("注释方式", _wrap(self.notes_mode))
        self.note_brackets_box = self._combo(
            [("〔〕", "corner"), ("[]", "square"),
             ("全角（）", "fullwidth"), ("半角()", "halfwidth")], "fullwidth")
        self.note_brackets_box.setToolTip(
            "注释方式=“括号内联”时校注的括号（默认全角）\n"
            "〔〕/[] 用于与正文夹注（）区分")
        form.addRow("校注内联括号", _wrap(self.note_brackets_box))
        self.notes_mode.currentIndexChanged.connect(
            lambda _i: self._sync_note_brackets_enabled())
        self._sync_note_brackets_enabled()
        return w

    def _sync_note_brackets_enabled(self):
        """仅注释方式=括号内联时「校注内联括号」可编辑。"""
        self.note_brackets_box.setEnabled(
            self.notes_mode.currentData() == "inline")

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
        self.ann_repeat.setToolTip(
            "注音频率。每页只注首次：docx 按原书页（<pb>）翻页重注；"
            "html/epub 按卷文件；md/txt 整篇（无分页）")
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
        orow = QHBoxLayout()
        self.ann_hint = QLabel()
        self.ann_hint.setWordWrap(True)
        self.ann_hint.setStyleSheet("color: gray")
        self.ann_open = QPushButton("打开")
        self.ann_open.clicked.connect(self._on_open_ann_table)
        orow.addWidget(self.ann_hint, 1)
        orow.addWidget(self.ann_open)
        form.addRow("", orow)
        self.ann_file.textChanged.connect(lambda _v: self._refresh_ann_hint())
        self._refresh_ann_hint()
        return w

    def _ann_table_path(self):
        """当前词表实际路径：空=内置表；否则按 annotate 规则解析（缺失→None）。"""
        from pycbeta.annotate import _resolve_table_path
        return _resolve_table_path(self.ann_file.text().strip() or None, None)

    def _refresh_ann_hint(self):
        path = self._ann_table_path()
        if path:
            self.ann_hint.setStyleSheet("color: gray")
            self.ann_hint.setText(f"实际使用：{path}")
            self.ann_open.setEnabled(True)
        else:
            self.ann_hint.setStyleSheet("color: red")
            self.ann_hint.setText("词表文件不存在，将静默关闭注音")
            self.ann_open.setEnabled(False)

    def _on_open_ann_table(self):
        self._open_local_file(self._ann_table_path())

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
        form.addRow("报告差异行数", self.difflines_spin)
        self.autofetch_box = self._check("官方文档缺失自动下载", checked=True)
        self.scope_box = self._check("按卷限定官方文档", checked=True)
        form.addRow("", self.autofetch_box)
        form.addRow("", self.scope_box)
        return w

    # ---------- 配置预设（一切按下拉选中项） ----------
    def _on_save(self):
        """保存＝把面板当前值覆盖写入**当前选中预设**（出厂默认项置灰）。"""
        path = self._selected_preset()
        if not path:
            return
        try:
            base = load_config_preset(path)
        except (OSError, ValueError):
            base = {}
        data = self._presets_merged(base if isinstance(base, dict) else {})
        self._presets = data
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            path2 = save_config_preset(stem, data)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._refresh_cfg_presets(select=path2)
        self.refresh_slot_label()
        self._changed()

    def _on_set_default(self):
        """run.json 的 config-json 槽指向当前选中项（出厂默认项=清空槽）。"""
        from pycbeta.theme import set_run_slot
        path = self._selected_preset()
        if path:
            try:
                slot = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
            except ValueError:
                slot = path
        else:
            slot = ""
        try:
            set_run_slot("config-json", slot)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "设为默认失败", str(exc))
            return
        self.refresh_slot_label()
        self._changed()

    def _refresh_cfg_presets(self, select=None):
        """预设下拉：首项“出厂默认”（空值）+ presets/*.json；
        select 为 path；未指定则跟随 run.json 当前 config-json 槽。"""
        box = self.cfg_preset_box
        if select is None:
            select = self._run_default_preset_path()
        box.blockSignals(True)
        try:
            box.clear()
            box.addItem(SENTINEL_LABEL, "")
            for stem, path in list_config_presets():
                box.addItem(stem, path)
            idx = box.findData(select) if select else -1
            box.setCurrentIndex(idx if idx >= 0 else 0)
            fm = box.fontMetrics()
            longest = max((fm.horizontalAdvance(box.itemText(i))
                           for i in range(box.count())), default=0)
            box.view().setMinimumWidth(longest + 48)  # 下拉弹层按最长项放宽
        finally:
            box.blockSignals(False)
        self._update_preset_buttons()

    def _run_default_preset_path(self):
        """run.json 的 config-json 槽解析出的文件路径（未指向预设时 None）。"""
        try:
            from pycbeta.theme import (load_run_config, resolve_base_config,
                                       default_run_path, _PRESETS_PATH)
            run = load_run_config()
            hit = resolve_base_config(
                run, os.path.dirname(os.path.abspath(default_run_path())))
            if hit and os.path.abspath(hit) != os.path.abspath(_PRESETS_PATH):
                return hit
        except (OSError, ValueError):
            pass
        return None

    def _selected_preset(self):
        """下拉当前选中 → 预设文件路径（出厂默认项返回 ""）。"""
        return self.cfg_preset_box.currentData() or ""

    def _update_preset_buttons(self):
        has = bool(self._selected_preset())
        self.btn_save.setEnabled(has)
        self.btn_preset_del.setEnabled(has)

    def _on_preset_chosen(self, _index):
        path = self._selected_preset()
        try:
            data = load_config_preset(path) if path else load_slot("factory")[0]
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "载入预设失败", str(exc))
            return
        self.set_options(options_from_presets(data))
        self.refresh_slot_label()
        self._update_preset_buttons()
        self._changed()

    def _on_preset_save_as(self):
        name, ok = QInputDialog.getText(
            self, "另存为配置预设", "预设名（存进 presets/）：")
        if not ok:
            return
        path = self._selected_preset()
        try:
            base = load_config_preset(path) if path else load_slot("factory")[0]
        except (OSError, ValueError):
            base = {}
        if not isinstance(base, dict):
            base = {}
        try:
            path2 = save_config_preset(name, self._presets_merged(base))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "另存失败", str(exc))
            return
        self._refresh_cfg_presets(select=path2)
        self.refresh_slot_label()
        self._changed()

    def _on_preset_delete(self):
        path = self._selected_preset()
        if not path:
            QMessageBox.information(self, "删除预设", "“出厂默认”不是文件，删不掉。")
            return
        try:
            delete_config_preset(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self._refresh_cfg_presets()
        self.refresh_slot_label()
        self._changed()

    def merged_preset(self, base=None):
        """公开：`base`（基础配置 dict，可 None）+ 面板当前值 → 可保存的预设 dict。

        供外部（如 publish）保存预设；语义同内部 `_presets_merged`，
        但不暴露私有名。"""
        return self._presets_merged(base if isinstance(base, dict) else {})

    def _presets_merged(self, cur):
        """当前槽为底 + 面板值合并 → 可存 presets（含所选纸张作默认纸张；
        格式/引擎/字库顶层直存，保证保存→载入 roundtrip）。"""
        data = copy.deepcopy(cur)
        opts = self.get_options()
        data["default_page"] = opts.page
        data["formats"] = list(opts.formats or ["pdf"])
        data["engine"] = opts.engine or "docx2pdf"
        data["font_lang"] = opts.font_lang or "zh-Hant"
        _pg = data.setdefault("pages", {}).setdefault(opts.page, {})
        if opts.margins:
            _pg["custom_margins"] = copy.deepcopy(opts.margins)
        else:
            _pg.pop("custom_margins", None)  # 重勾跟随后真还原，不留僵尸
        if opts.typo:
            _pg["body_font_size"] = opts.typo.get("font-size", "")
            _pg["body_line_height"] = opts.typo.get("line-height", "")
        else:
            _pg.pop("body_font_size", None)  # 重勾跟随后真还原
            _pg.pop("body_line_height", None)
        data.setdefault("output", {}).update(copy.deepcopy(opts.output or {}))
        if opts.pagination:
            data["output"]["pagination"] = copy.deepcopy(opts.pagination)
        if opts.series_title:
            data["output"]["series_title"] = copy.deepcopy(opts.series_title)
        if opts.annotations:
            data["annotations"] = copy.deepcopy(opts.annotations)
        if opts.verify:
            data.setdefault("verify", {}).update(copy.deepcopy(opts.verify))
        data["output"]["t2s"] = bool(opts.t2s)
        data["output"]["vertical"] = bool(opts.vertical)
        data["output"]["font_scale"] = float(opts.font_scale or 1.0)
        return data

    def _on_reset(self):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("还原出厂")
        box.setText("当前配置会被还原为出厂配置。")
        ok_btn = box.addButton("确定", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(ok_btn)
        box.exec()
        if box.clickedButton() is not ok_btn:
            return
        self.set_options(options_from_presets(reset_factory()))
        self.refresh_slot_label()
        self._refresh_cfg_presets()
        self._changed()

    def _open_local_file(self, path):
        """用系统默认程序打开本地文件/目录（样式表/词表/预设目录）；供各卡的"打开"按钮。"""
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    def mark_slot(self, _actual=None):
        self.refresh_slot_label()

    def refresh_slot_label(self):
        """当前配置：`当前配置：<预设名>`。

        “当前配置”是链接（指 run.json，点击打开）；名字固定宽度、超长省略号，
        tooltip 显示全名。
        """
        from pycbeta.theme import (default_run_path, load_run_config,
                                   resolve_base_config, _PRESETS_PATH)
        run_path = default_run_path()
        name = "出厂默认"
        try:
            run = load_run_config()
            hit = resolve_base_config(
                run, os.path.dirname(os.path.abspath(run_path)))
            if hit and os.path.abspath(hit) != os.path.abspath(_PRESETS_PATH):
                name = os.path.basename(hit)
        except (OSError, ValueError):
            name = "出厂默认"
        url = QUrl.fromLocalFile(os.path.abspath(run_path)).toString()
        short = self.slot_label.fontMetrics().elidedText(
            name, Qt.ElideRight, SLOT_NAME_WIDTH)
        self.slot_label.setTextFormat(Qt.RichText)
        self.slot_label.setOpenExternalLinks(True)
        self.slot_label.setToolTip(name)
        self.slot_label.setText(f'<a href="{url}">当前配置</a>：{short}')

    # ---------- 读写 ----------
    def get_options(self):
        follow = self.margin_follow.isChecked()
        margins = None
        if not follow:
            margins = {k: float(sp.value()) for k, sp in self.margin_spins.items()}
        pipe = "docx2pdf" if self.engine_docx.isChecked() else "html2pdf"
        single = self.single_box.currentData() or ""
        engine = f"{pipe}:{single}" if single else pipe
        typo = None
        if not self.typo_follow.isChecked():
            typo = {"font-size": f"{self.typo_size_spin.value():g}pt",
                    "line-height": f"{self.typo_lh_spin.value():g}"}
        return XmlOptions(
            page=self.page_box.currentData() or self.page_box.currentText(),
            font_lang=self.lang_box.currentData() or "zh-Hant",
            engine=engine,
            margins=margins,
            formats=[f for f, b in self.format_boxes.items() if b.isChecked()] or ["pdf"],
            output={
                "grayscale": self.grayscale_box.isChecked(),
                "page_border": self.border_box.isChecked(),
                "show_notes": self.notes_on.isChecked(),
                "notes": self.notes_mode.currentData() or "footnote",
                "footnote_per_page": self.per_page_box.isChecked(),
                "suppress_title_notes": self.title_notes_box.isChecked(),
                "show_body_siddham": self.siddham_box.isChecked(),
                "inline_brackets": self.brackets_box.currentData(),
                "note_inline_brackets": self.note_brackets_box.currentData(),
                "split_juan": self.split_box.isChecked(),
                "show_close_juan": self.close_juan_box.isChecked(),
                "suppress_jhead_dup": self.dedup_box.isChecked(),
                "strip_head_no": self.strip_no_box.isChecked(),
                "ignore_xml_style": self.ign_style_box.isChecked(),
                "ignore_xml_space": self.ign_space_box.isChecked(),
                "verse_caesura": self.caesura_edit.text(),
                "verse_strip_quotes": self.strip_quotes_box.isChecked(),
            },
            font_scale=float(self.scale_spin.value()),
            pagination={k: b.isChecked() for k, b in self.pg_boxes.items()},
            series_title={"enabled": self.series_on.isChecked(),
                          **self._series_extra},
            t2s=self.t2s_box.isChecked(),
            vertical=self.vert_box.isChecked(),
            typo=typo,
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
            self._on_margin_follow(opts.margins is None, fill=False)
            if opts.margins is None:
                self._on_page_changed(-1)  # 跟随时显示刷新为预设值
            self.typo_follow.setChecked(opts.typo is None)
            if opts.typo:
                import re as _re
                m = _re.match(r"^\s*([\d.]+)\s*pt\s*$",
                              opts.typo.get("font-size", ""))
                if m:
                    self.typo_size_spin.setValue(float(m.group(1)))
                try:
                    self.typo_lh_spin.setValue(
                        float(opts.typo.get("line-height", 1.5)))
                except (TypeError, ValueError):
                    pass
            self._on_typo_follow(opts.typo is None, fill=False)
            self._refresh_typo_display()
            self.grayscale_box.setChecked(bool(opts.output.get("grayscale", False)))
            self.border_box.setChecked(bool(opts.output.get("page_border", False)))
            i = self.lang_box.findData(opts.font_lang or "zh-Hant")
            self.lang_box.setCurrentIndex(i if i >= 0 else 0)
            self.t2s_box.setChecked(bool(opts.t2s))
            self._on_t2s(bool(opts.t2s))
            self.vert_box.setChecked(bool(opts.vertical))
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
            self.strip_no_box.setChecked(bool(o.get("strip_head_no", False)))
            self.ign_style_box.setChecked(bool(o.get("ignore_xml_style", False)))
            self.ign_space_box.setChecked(bool(o.get("ignore_xml_space", False)))
            self.caesura_edit.setText(str(o.get("verse_caesura", "　　")))
            self.strip_quotes_box.setChecked(bool(o.get("verse_strip_quotes", False)))
            st = opts.series_title or {}
            self.series_on.setChecked(bool(st.get("enabled", True)))
            # 旧 font/size 键只透传保留（样式走 CSS），不展示
            self._series_extra = {k: copy.deepcopy(v) for k, v in st.items()
                                  if k != "enabled"}
            self.notes_on.setChecked(bool(o.get("show_notes", True)))
            i = self.notes_mode.findData(o.get("notes", "footnote"))
            self.notes_mode.setCurrentIndex(i if i >= 0 else 0)
            self.per_page_box.setChecked(bool(o.get("footnote_per_page", True)))
            self.title_notes_box.setChecked(bool(o.get("suppress_title_notes", False)))
            self.siddham_box.setChecked(bool(o.get("show_body_siddham", True)))
            i = self.brackets_box.findData(o.get("inline_brackets", "fullwidth"))
            if i >= 0:
                self.brackets_box.setCurrentIndex(i)
            j = self.note_brackets_box.findData(
                o.get("note_inline_brackets") or o.get("inline_brackets", "fullwidth"))
            if j >= 0:
                self.note_brackets_box.setCurrentIndex(j)
            self._sync_note_brackets_enabled()
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
            self.verify_on.setChecked(bool(vf.get("enabled", True)))
            self.maxdiff_spin.setValue(int(vf.get("maxDiff", 10) or 10))
            self.difflines_spin.setValue(int(vf.get("diffLines", 5) or 5))
            self.autofetch_box.setChecked(bool(vf.get("auto_fetch", True)))
            self.scope_box.setChecked(bool(vf.get("scope_juan", True)))
        finally:
            self._emitting = False
        self._changed()


SOURCE_LABELS = [
    ("xml_dir", "本地 XML 候选源（只读；角色同远端 URL）"),
    ("cbeta_ebook", "电子书工作根（唯一可写，平展一部一目录）"),
    ("catalog", "佛典目录 catalog（sutra_mapping.txt）"),
]
DOWNLOAD_KEYS = ["xml", "html", "docx", "epub", "txt_notes", "odt", "figures"]


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


def xml_dir_warning(parent, xml_dir, edition=""):
    """非发布版 P5 的 XML 候选源告警。返回 'use' / 'clear' / None（取消）。"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("XML 源版本告警")
    box.setText(f"检测到非发布版 P5 的 XML 源：\n{xml_dir}\n编辑版本：{edition or '未知'}")
    box.setInformativeText(
        "P5a/P5b 与发布版 P5 的校勘编码不同，可能导致正文重复、校勘注丢失、校验失败。")
    use_btn = box.addButton("仍使用（不保证正确）", QMessageBox.AcceptRole)
    clear_btn = box.addButton("清除该路径", QMessageBox.DestructiveRole)
    box.addButton("取消", QMessageBox.RejectRole)
    box.setDefaultButton(clear_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is use_btn:
        return "use"
    if clicked is clear_btn:
        return "clear"
    return None


def clear_xml_dir(root=None):
    """把用户槽 source.xml_dir 清空并保存（非 P5 源经确认后清除）。"""
    data, _actual = load_slot("user", root)
    save_current(apply_source_edits(data, {"source": {"xml_dir": ""}}), root)


class SourceDialog(QDialog):
    """数据源窗口：查看/编辑输入来源目录与 CBETA 官方下载 URL 模板。
    确定 = 合并进默认用户预设（presets/config.user.json）；取消 = 丢弃。"""

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
        self.title_t2s_box = QCheckBox("工作目录书名转简体（t2s）")
        self.title_t2s_box.setToolTip(
            "source.title_t2s：电子书工作目录名 `{id} {书名}` 的书名是否转简体（默认开）")
        self.title_t2s_box.setChecked(bool(src.get("title_t2s", True)))
        layout.addWidget(self.title_t2s_box)
        layout.addWidget(QLabel("官方下载 URL 模板（{canon}/{vol}/{file}/{id} 为占位符）："))
        self.dl_table = QTableWidget(0, 2)
        self.dl_table.setHorizontalHeaderLabels(["格式", "URL 模板"])
        self.dl_table.horizontalHeader().setStretchLastSection(True)
        # 出厂默认值打底：用户文件缺键（如新增的 figures）也显示出厂值，可直接改
        try:
            from pycbeta.theme import load_presets
            _factory_dl = load_presets().get("downloads") or {}
        except (OSError, ValueError):
            _factory_dl = {}
        dl = {**_factory_dl, **(data.get("downloads") or {})}
        keys = [k for k in DOWNLOAD_KEYS if k in dl] + \
            [k for k in dl.keys() if k not in DOWNLOAD_KEYS]
        self.dl_table.setRowCount(len(keys))
        for i, k in enumerate(keys):
            key_item = QTableWidgetItem(k)
            key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)  # 键列只读
            self.dl_table.setItem(i, 0, key_item)
            self.dl_table.setItem(i, 1, QTableWidgetItem(str(dl[k])))
        layout.addWidget(self.dl_table, 1)
        urow = QHBoxLayout()
        self.btn_update_data = QPushButton("更新官方数据")
        self.btn_update_data.setToolTip(
            "缺字库/补充字型/目录从上游直链同步（先校验再落盘，一致跳过）")
        self.btn_update_data.clicked.connect(self._on_update_data)
        self.btn_check_update = QPushButton("更新XML")
        self.btn_check_update.setToolTip(
            "逐 work 目录比对远程 XML（If-Modified-Since/字节；不改项不落盘），"
            "列出需重新生成电子书的 ID（可一键拷贝）")
        self.btn_check_update.clicked.connect(self._on_check_ebook_updates)
        self.ebook_base_box = QCheckBox("同时更新电子书")
        self.ebook_base_box.setChecked(True)
        self.ebook_base_box.setToolTip(
            "XML 有更新的 work，其本地已有的官方电子书（html/docx/txt 等）一并刷新；"
            "只为已存在格式重下，不新增格式")
        self.update_status = QLabel("")
        self.update_status.setStyleSheet("color: gray")
        self.update_status.setWordWrap(True)
        urow.addWidget(self.btn_update_data)
        urow.addWidget(self.btn_check_update)
        urow.addWidget(self.ebook_base_box)
        urow.addWidget(self.update_status, 1)
        layout.addLayout(urow)
        self._refresh_last_update()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.btn_reset_urls = QPushButton("重置 URL")
        self.btn_reset_urls.setToolTip("URL 模板恢复出厂值（只填表，点确定才保存）")
        self.btn_reset_urls.clicked.connect(self._on_reset_urls)
        buttons.addButton(self.btn_reset_urls, QDialogButtonBox.ResetRole)
        layout.addWidget(buttons)
        self._buttons_box = buttons
        self._update_worker = None
        self._ebook_worker = None

    def _refresh_last_update(self):
        from pycbeta.update_data import last_update_summary
        self.update_status.setText(last_update_summary())

    def _on_reset_urls(self):
        """URL 模板恢复出厂值（只填表，不保存；点确定才写入用户配置）。"""
        from pycbeta.theme import load_presets
        try:
            factory_dl = load_presets().get("downloads") or {}
        except (OSError, ValueError):
            factory_dl = {}
        keys = [k for k in DOWNLOAD_KEYS if k in factory_dl] + \
            [k for k in factory_dl.keys() if k not in DOWNLOAD_KEYS]
        self.dl_table.setRowCount(len(keys))
        for i, k in enumerate(keys):
            key_item = QTableWidgetItem(k)
            key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
            self.dl_table.setItem(i, 0, key_item)
            self.dl_table.setItem(i, 1, QTableWidgetItem(
                str(factory_dl[k])))
        self.update_status.setText("已重置为出厂（点确定保存）")

    def _on_update_data(self):
        """官方数据更新（后台线程跑；跑完弹报告；期间锁住更新/重置/确定/取消）。"""
        self.btn_update_data.setEnabled(False)
        self.btn_reset_urls.setEnabled(False)
        self._buttons_box.setEnabled(False)
        self.update_status.setText("正在从上游同步…")
        self._update_worker = DataUpdateWorker()
        self._update_worker.finished_report.connect(self._on_update_finished)
        self._update_worker.finished.connect(self._on_update_done)
        self._update_worker.start()

    def _on_update_done(self):
        self.btn_update_data.setEnabled(True)
        self.btn_reset_urls.setEnabled(True)
        self._buttons_box.setEnabled(True)
        self._refresh_last_update()

    def _on_update_finished(self, report):
        from pycbeta.update_data import format_report
        QMessageBox.information(
            self, "官方数据更新",
            "\n".join(format_report(report or [])) or "无更新项")

    def _dialog_presets(self):
        """以对话框当前编辑值构造 presets（未保存也能检查更新）。"""
        src = {k: e.text().strip() for k, e in self.path_edits.items()}
        src["title_t2s"] = bool(self.title_t2s_box.isChecked())
        dl = {}
        for i in range(self.dl_table.rowCount()):
            k = self.dl_table.item(i, 0).text()
            v = self.dl_table.item(i, 1)
            dl[k] = v.text().strip() if v else ""
        return {"source": src, "downloads": dl}

    def _on_check_ebook_updates(self):
        """电子书远程更新检查（后台线程跑；跑完弹结果窗）。"""
        self.btn_check_update.setEnabled(False)
        self.btn_update_data.setEnabled(False)
        self.btn_reset_urls.setEnabled(False)
        self.ebook_base_box.setEnabled(False)
        self._buttons_box.setEnabled(False)
        self.update_status.setText("正在更新XML…")
        self._ebook_worker = EbookUpdateWorker(
            self._dialog_presets(),
            with_baselines=bool(self.ebook_base_box.isChecked()))
        self._ebook_worker.finished_report.connect(self._on_check_finished)
        self._ebook_worker.finished.connect(self._on_check_done)
        self._ebook_worker.start()

    def _on_check_done(self):
        self.btn_check_update.setEnabled(True)
        self.btn_update_data.setEnabled(True)
        self.btn_reset_urls.setEnabled(True)
        self.ebook_base_box.setEnabled(True)
        self._buttons_box.setEnabled(True)
        self.update_status.setText("XML更新完成")

    def _on_check_finished(self, report):
        dlg = EbookUpdateDialog(report or [], self)
        dlg.exec()

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
        values["source"]["title_t2s"] = bool(self.title_t2s_box.isChecked())
        for i in range(self.dl_table.rowCount()):
            k = self.dl_table.item(i, 0).text()
            v = self.dl_table.item(i, 1).text() if self.dl_table.item(i, 1) else ""
            values["downloads"][k] = v.strip()
        xml_dir = values["source"].get("xml_dir", "")
        if not values["source"].get("cbeta_ebook", ""):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("电子书工作根未配置")
            box.setText("电子书工作根（source.cbeta_ebook）是必填项，"
                        "清空后将无法按編號转换。")
            ok_btn = box.addButton("确定保存", QMessageBox.AcceptRole)
            box.addButton("取消", QMessageBox.RejectRole)
            box.setDefaultButton(ok_btn)
            box.exec()
            if box.clickedButton() is not ok_btn:
                return
        if xml_dir:
            from pycbeta.fetch import inspect_xml_source
            info = inspect_xml_source(xml_dir)
            if info.get("safe") is False:
                choice = xml_dir_warning(self, xml_dir, info.get("edition"))
                if choice is None:
                    return  # 取消保存
                if choice == "clear":
                    values["source"]["xml_dir"] = ""
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

    def get_preset(self, base=None):
        """`exec()` 后：Accepted → 合并后的预设 dict（供保存/另存）；否则 None。"""
        if self.result() != QDialog.Accepted:
            return None
        return self.panel.merged_preset(base)
