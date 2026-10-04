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
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QHeaderView, QSpinBox,
    QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout,
    QWidget,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "styles")
from pycbeta.annotate import DEFAULT_TABLE as ANN_DEFAULT_TABLE  # 内置注音词表路径
# 样式表卡：默认两 CSS（路径, 说明）
STYLE_FILES = (
    ("pdf_docx.css", "印刷主题（pdf/docx 专用）"),
    ("html_epub_official.css", "电子书基底（html/epub；官方电子书样式）"),
)
FACTORY_NAME = os.path.join("pycbeta", "config.json")
# 默认用户预设（在 presets/ 内，git 忽略）；下拉首项“出厂默认”为空值
USER_PRESET_NAME = "config.user.json"
PRESET_DIRNAME = "presets"
SENTINEL_LABEL = "（出厂默认）"
SLOT_NAME_WIDTH = 220    # “当前配置：<名>”里名字的固定显示宽度（px），超长省略

PAGINATION_KEYS = ["enabled", "duplex", "juan", "juan_first", "mulu_levels", "pb", "tei"]
PAGINATION_LABELS = {
    "enabled": "智能分页", "duplex": "双面打印",
    "juan": "卷首换页", "juan_first": "首卷换页",
    "mulu_levels": "目录换页 level",
    "pb": "按 pb 分页", "tei": "尾页换页",
}
# 各分页选项的补充说明（UI 以灰色括号显示在标签右侧）
PAGINATION_HINTS = {
    "enabled": "（总开关：关则下列分页规则全部失效，保持自然排版）",
    "duplex": "（每卷从单数页开始，Word 自动补空白偶页；双面装订用）",
    "juan": "（每卷开头另起一页；第 1 卷默认与书名同页）",
    "juan_first": "（第 1 卷也另起一页，书名/题署独占一页；需勾选「卷首换页」）",
    "mulu_levels": "（序/品等目录在所选 level 各自另起一页；epub 同步按此拆章节）",
    "pb": "（源 XML 的 <pb> 刻本页边界处换页；默认关）",
    "tei": "（末尾【經文資訊】页另起一页）",
}
# 目录换页 level 下拉：显示名 → 级别元组（开关关闭=不分，故无「关」项）
MULU_LEVEL_ITEMS = [
    ("仅 level-1（默认）", (1,)),
    ("level-1+2", (1, 2)),
    ("level-1+2+3", (1, 2, 3)),
]
FORMATS = ["pdf", "docx", "html", "epub", "md", "txt"]
DOCX_SINGLES = ["msword", "wps", "docbuilder", "libreoffice", "minipdf"]
HTML_SINGLES = ["chromium", "prince", "weasyprint", "cbetapdf"]
INSTALL_HINTS = {
    "msword": "需安装 MS Word",
    "wps": "需安装 WPS Office",
    "docbuilder": "需安装 ONLYOFFICE DocBuilder",
    "libreoffice": "需安装 LibreOffice",
    "minipdf": "从 GitHub Releases 下载 minipdf.exe 放入 engines/",
    "chromium": "需 playwright install chromium",
    "prince": "需安装 Prince",
    "weasyprint": "需 pip install weasyprint",
    "cbetapdf": "从 GitHub Releases 下载 cbetapdf.exe 放入 engines/",
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
# 版本号子目录安装（如 ...\WPS Office\<版本>\office6\wps.exe）：glob 兜底，
# which/PATH 查不到时命中
WPS_ROOTS = [
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


def _progid_registered(progid):
    """COM ProgID 是否在注册表注册（不启动进程）。用于 Office/WPS 自定义安装
    位置的就绪判定——渲染实际走 COM ProgID，与安装目录无关（`C:\\Apps\\...`
    这类自定义路径不必写进代码）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid):
            return True
    except OSError:
        return False


def detect_engines(presets=None, root=None, progid_check=None):
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
    # WPS 就绪：路径命中 或 KWPS COM ProgID 已注册（自定义安装目录也能识别；
    # 渲染链本身走 KWPS.Application，故以注册为准）；仍需 pywin32（has_com）
    _pc = progid_check or _progid_registered
    has_wps_com = False
    if has_com:
        try:
            has_wps_com = bool(_pc("KWPS.Application")) or bool(_pc("wps.Application"))
        except Exception:
            has_wps_com = False
    return {
        "msword": _office_ready(MSWORD_EXES, MSWORD_PATHS, (), has_com,
                                extra_globs=MSWORD_GLOBS),
        "wps": _office_ready(WPS_EXES, (), WPS_DIRS, has_com,
                             extra_globs=wps_globs) or has_wps_com,
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


def set_config_preset_theme(path, value):
    """预设主题键写入：下拉值（如“霞鹜文楷”/“pdf_docx.css”）→ 预设文件
    pdf-docx-user-theme 键；出厂值则删键（该预设回退 run 槽）。其余键原样保留
    （// 注释会丢，json.dump 重写，与保存预设一致）。返回路径。"""
    data = load_config_preset(path)
    if not isinstance(data, dict):
        raise ValueError(f"配置预设顶层非对象：{path}")
    v = (value or "").strip()
    if not v or v == "pdf_docx.css":
        data.pop("pdf-docx-user-theme", None)
    else:
        data["pdf-docx-user-theme"] = \
            v if v.lower().endswith(".css") else v + ".css"
    ap = os.path.abspath(_config_preset_path(path))
    with open(ap, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return ap


def apply_selected_preset_theme(presets, preset_path):
    """运行时快照用：选中预设的主题键叠到底座有效配置上（同键覆盖）。

    显示（_refresh_theme_box）与渲染（子进程快照）同锚定“当前选中预设”，
    否则选预设换主题只亮不生效。无选中/无键 → 原样返回（可测纯函数，
    不碰 Qt/文件写）。"""
    from pycbeta.theme import preset_file_theme_keys
    keys = preset_file_theme_keys(preset_path) if preset_path else {}
    if keys and isinstance(presets, dict):
        presets = copy.deepcopy(presets)
        presets.update(keys)
    return presets


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
    data.pop("theme", None)  # 遗留 theme 键退役；新式 PRESET_THEME_KEYS 键保留，
    # 随快照进子进程（显式开关 > 预设键 > run.json 槽，见 theme.resolve_*）
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


class DataUpdateDialog(QDialog):
    """官方数据更新：先列更新源（remote_sources.json），确认后再跑。
    行源 update_data.source_rows()；更新跑 DataUpdateWorker（含 dry-run 仅检查），
    完后逐行填状态（catalog 钉死内置，更新即生效，无自定义路径提示）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("官方数据更新")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("可从官方更新的数据："))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["数据项", "本地文件", "上次更新", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        try:
            from pycbeta.update_data import load_sources, source_rows
            self._keys = [s["key"] for s in load_sources()]
            rows = source_rows()
        except (OSError, ValueError):
            self._keys, rows = [], []
        self.table.setRowCount(len(rows))
        for i, (name, _url, dest, when) in enumerate(rows):
            for j, text in enumerate((name, dest, when, "待检查")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, j, item)
        layout.addWidget(self.table, 1)
        brow = QHBoxLayout()
        self.dry_box = QCheckBox("仅检查（不写盘）")
        self.dry_box.setToolTip("dry-run：下载比对并预告，不覆盖本地文件")
        self.btn_go = QPushButton("开始更新")
        self.btn_go.setToolTip("后台同步上游，失败项不写盘、不断其他项")
        self.btn_go.clicked.connect(self._on_go)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.reject)
        self.status = QLabel("")
        self.status.setStyleSheet("color: gray")
        self.status.setWordWrap(True)
        brow.addWidget(self.dry_box)
        brow.addWidget(self.btn_go)
        brow.addWidget(self.btn_close)
        brow.addWidget(self.status, 1)
        layout.addLayout(brow)
        self._worker = None

    def _on_go(self):
        self.btn_go.setEnabled(False)
        self.dry_box.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.status.setText("正在从上游同步…")
        self._worker = DataUpdateWorker(
            dry_run=bool(self.dry_box.isChecked()))
        self._worker.finished_report.connect(self._on_finished)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self):
        self.btn_go.setEnabled(True)
        self.dry_box.setEnabled(True)
        self.btn_close.setEnabled(True)

    def _on_finished(self, report):
        from pycbeta.update_data import format_report
        marks = {"unchanged": "一致", "updated": "已更新", "preview": "可更新",
                 "manual": "手动", "failed": "失败"}
        by_key = {r.get("key"): r for r in (report or []) if r.get("key")}
        for i, key in enumerate(self._keys):
            if i >= self.table.rowCount():
                break
            r = by_key.get(key) or {}
            st = marks.get(r.get("status", ""), "?")
            detail = r.get("detail", "")
            item = QTableWidgetItem(f"{st}（{detail}）" if detail else st)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 3, item)
        self.status.setText("；".join(format_report(report or [])) or "无更新项")


def clean_verify_dirs(out_dir, verify_root=None):
    """删除 `out_dir` 下的校验产物（可重生成的中间产物）：
    旧平铺 `*（验证）`/`*（驗證）` + 生效校验根。
    默认根（`{输出}/验证`）整树删；用户自选根只删其下 `*（验证）` 子目录
    （不动自选根本身及无关内容）。

    返回 (删除数, 失败列表[短说明])。目录不存在/空视为 0。
    """
    import glob as _glob
    import shutil as _sh
    from pycbeta.verify import default_verify_root as _dvr
    if not (out_dir or "").strip() and not (verify_root or "").strip():
        return 0, []
    removed, errs = 0, []
    out = (out_dir or "").strip()
    if out:
        for pat in ("*（验证）", "*（驗證）"):
            for d in _glob.glob(os.path.join(out, pat)):
                if not os.path.isdir(d):
                    continue
                try:
                    _sh.rmtree(d)
                    removed += 1
                except OSError as e:
                    errs.append(f"{os.path.basename(d)}: {e}")
    try:
        custom = (verify_root or "").strip()
        default = _dvr(out) if out else ""
        eff = os.path.abspath(custom) if custom else default
    except Exception:
        eff, default, custom = "", "", ""
    if not eff or not os.path.isdir(eff):
        return removed, errs
    is_default = (not custom) or (
        bool(default) and os.path.abspath(eff) == os.path.abspath(default))
    if not is_default:
        # 自选根：只删其下校验子目录
        for pat in ("*（验证）", "*（驗證）"):
            for d in _glob.glob(os.path.join(eff, pat)):
                if not os.path.isdir(d):
                    continue
                try:
                    _sh.rmtree(d)
                    removed += 1
                except OSError as e:
                    errs.append(f"{os.path.basename(d)}: {e}")
        return removed, errs
    try:
        kids = [d for pat in ("*（验证）", "*（驗證）")
                for d in _glob.glob(os.path.join(eff, pat))
                if os.path.isdir(d)]
        _sh.rmtree(eff)
        removed += len(kids) or 1
    except OSError as e:
        errs.append(f"验证: {e}")
    return removed, errs


def _human_size(num_bytes):
    """字节数 → 人读串（B/KB/MB/GB/TB，一位小数；B 取整）。"""
    n = float(max(0, num_bytes or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            break
        n /= 1024
    return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"


def verify_dir_size(out_dir, verify_root=None):
    """校验产物占盘：生效校验根（自选或 {输出}/验证）+ 旧平展 `*（验证）`，
    返回 (bytes, files)。只统计文件大小；不存在/空 → (0, 0)；不抛异常。"""
    import glob as _glob
    from pycbeta.verify import default_verify_root as _dvr
    total, count = 0, 0
    roots = []
    out = (out_dir or "").strip()
    try:
        custom = (verify_root or "").strip()
        eff = os.path.abspath(custom) if custom else (_dvr(out) if out else "")
    except Exception:
        eff = ""
    if eff:
        roots.append(eff)
    if out:
        for pat in ("*（验证）", "*（驗證）"):
            roots += [d for d in _glob.glob(os.path.join(out, pat))
                      if os.path.isdir(d)]
    for r in roots:
        for dp, _dn, fns in os.walk(r):
            for fn in fns:
                try:
                    total += os.path.getsize(os.path.join(dp, fn))
                    count += 1
                except OSError:
                    continue
    return total, count


class XmlOptionsPanel(QWidget):
    """七选项卡面板。get_options/set_options；值变更发 optionsChanged。"""
    optionsChanged = Signal(object)

    def __init__(self, presets=None, parent=None):
        super().__init__(parent)
        self._presets = presets or {}
        self._emitting = False
        self._theme_dirty = False     # 「生效样式」下拉被手动改过（本次运行覆盖，未落盘）
        self._series_extra = {}       # series_title 旧 font/size 键透传保留
        self._paren_hint_labels = []  # 各选项右侧灰色括号说明标签（供测试/样式核对）
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
        self.cfg_box = cfg   # 配置框标题常驻最后动作（_set_cfg_title）
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

    def _radio(self, text, checked=False):
        # 同父单选组：QRadioButton 默认互斥（同 parent 自动 exclusive）
        box = QRadioButton(text)
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
        # 不折行 + 固定单行高：行距数字宽度变化时若随内容折行/收缩，本行（及下方
        # 控件）会上下小幅跳动（字号不跨折行阈值故不跳，行距跳）。文案很短，无需折行。
        self.typo_info.setWordWrap(False)
        self.typo_info.setFixedHeight(self.fontMetrics().lineSpacing())
        form.addRow("", self.typo_info)
        self.grayscale_box = self._check("黑白输出")
        self.border_box = self._check("页面边框")
        _grow = QHBoxLayout()
        _grow.setContentsMargins(0, 0, 0, 0)
        _grow.addWidget(self.grayscale_box)
        _grow.addSpacing(24)
        _grow.addWidget(self.border_box)
        _grow.addStretch(1)
        form.addRow("", _grow)
        # 佛典丛书名（title level="s"）：仅首页左上角一行（无「每页」选项）
        _srow = QHBoxLayout()
        _srow.setContentsMargins(0, 0, 0, 0)
        _srow.addWidget(QLabel("佛典丛书名"))
        self.series_on = self._check("首页打印", checked=True)
        self.series_on.setToolTip(
            "output.series_title.enabled：经藏名（title level=\"s\"）印在首页左上角；"
            "字体/字号走 CSS p.series-title")
        _srow.addWidget(self.series_on)
        _srow.addStretch(1)
        form.addRow("", _srow)
        _shint = self._gray_hint(
            "（经藏名 title level=\"s\" 仅印在首页左上角；字体/字号走 CSS p.series-title）")
        _shint.setContentsMargins(20, 0, 0, 0)
        form.addRow("", _shint)
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
        # 切纸张永远刷新 spin 显示（跟随态显示预设；取消跟随显示本纸 custom，
        # 无 custom 以预设为编辑起点）。否则取消跟随下框里滞留上一张纸的值，
        # 看似当前纸张的值，保存即串写（A5/手机边距串扰即此）。
        if self.margin_follow.isChecked():
            self._fill_margin_spins()
        else:
            self._fill_margin_spins(use_custom=True)
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
            text = "跟随 CSS body"
        else:
            text = (f"纸张绑定：{self.typo_size_spin.value():g}pt／"
                    f"{self.typo_lh_spin.value():g}")
        if text != self.typo_info.text():
            self.typo_info.setText(text)

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
        self.theme_box.setToolTip(
            "生效样式：预设键 > run.json 的 pdf-docx-user-theme 槽 > 出厂默认；"
            "下拉选中即本次转换生效（不落盘），右侧按钮永久保存")
        self.theme_box.currentIndexChanged.connect(self._on_theme_box_changed)
        trow.addWidget(self.theme_box, 1)
        self.theme_default_btn = QPushButton("设为默认")
        self.theme_default_btn.clicked.connect(self._on_theme_default)
        trow.addWidget(self.theme_default_btn)
        self.btn_editor = QPushButton("编辑CSS")
        self.btn_editor.setToolTip("DOCX 所见即所得调样式（左改参/右预览），存预设进 presets/")
        self.btn_editor.clicked.connect(self._open_style_editor)
        trow.addWidget(self.btn_editor)
        self.theme_dir_btn = QPushButton("用户预设目录")
        self.theme_dir_btn.clicked.connect(lambda _v: self._open_local_file(
            self._user_presets_path()))
        trow.addWidget(self.theme_dir_btn)
        form.addRow("生效样式", trow)
        self.theme_status = QLabel()
        self.theme_status.setWordWrap(True)
        self.theme_status.setStyleSheet("color: gray")
        form.addRow("", self.theme_status)
        self._refresh_theme_box()
        self._update_theme_button()
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
        return w

    def _user_presets_path(self):
        from pycbeta.theme import user_presets_dir
        d = user_presets_dir()
        os.makedirs(d, exist_ok=True)
        return d

    def _selected_preset_theme(self):
        """当前选中预设的生效主题 → (value, 来源)；无选中/无键 → ("", "")。
        显示锚定选中预设（而非 run.json 槽），否则换预设不跟走主题。"""
        from pycbeta.theme import preset_file_theme_keys
        path = self._selected_preset()
        if not path:
            return "", ""
        keys = preset_file_theme_keys(path)
        for k in ("pdf-docx-user-theme", "pdf-docx-theme"):
            if keys.get(k):
                stem = os.path.splitext(os.path.basename(path))[0]
                return keys[k], f"预设 {stem}"
        return "", ""

    def _refresh_theme_box(self, keep_value=None):
        from pycbeta.theme import resolve_theme_css
        from pycbeta.gui.css_editor import current_theme_source
        if keep_value is not None:
            cur, src = keep_value, ""
        else:
            cur, src = self._selected_preset_theme()
            if not cur:
                cur, src = current_theme_source()
        self.theme_box.refresh(cur)
        self._theme_dirty = False
        _path, label = resolve_theme_css(cur)
        shown = _path or "内置 pdf_docx.css"
        if len(shown) > 60:
            shown = shown[:25] + "…" + shown[-30:]
        tail = f"（来自{src}）" if src else ""
        self.theme_status.setText(f"当前生效：{label}（{shown}）{tail}")
        if "缺失" in label or "不存在" in label:
            self.theme_status.setStyleSheet("color: red")
        else:
            self.theme_status.setStyleSheet("color: gray")

    def _on_theme_box_changed(self, _index):
        """下拉改选：本次运行即时生效（不落盘），右侧按钮仍用于永久保存。"""
        self._theme_dirty = True
        self.theme_status.setStyleSheet("color: gray")
        self.theme_status.setText("已改选：本次转换即生效；点右侧按钮可永久保存")
        self._changed()

    def theme_override(self):
        """本次运行的主题覆盖值（未改选 → None，沿用预设键/run 槽/出厂）。

        改选后返回归一化 `.css` 值；选中「出厂默认样式」→ ""（清除预设用户主题键，
        回退到标准槽/内置）。供 `_start` 叠进运行快照。"""
        if not self._theme_dirty:
            return None
        v = (self.theme_box.selected_value() or "").strip()
        if not v or v == "pdf_docx.css":
            return ""
        return v if v.lower().endswith(".css") else v + ".css"

    def _update_theme_button(self):
        """样式落盘按钮双文案：命名预设→“预设生效”，出厂项→“设为默认”。

        与 _on_theme_default 的分流目标一致；预设切换/下拉重填后刷新。"""
        if self._selected_preset():
            self.theme_default_btn.setText("预设生效")
            self.theme_default_btn.setToolTip(
                "写入所选预设的 pdf-docx-user-theme 键（永久生效）")
        else:
            self.theme_default_btn.setText("设为默认")
            self.theme_default_btn.setToolTip(
                "写入 run.json 主题槽（永久生效）")

    def _on_theme_default(self):
        """生效样式落盘：选中命名预设 → 写该预设的 pdf-docx-user-theme 键
        （预设自带主题，切换预设即跟走）；出厂默认项 → 写 run.json 主题槽。
        按钮文案由 _update_theme_button 同步（预设生效/设为默认）。"""
        from pycbeta.gui.css_editor import set_user_theme
        value = self.theme_box.selected_value()
        preset = self._selected_preset()
        if preset:
            try:
                set_config_preset_theme(preset, value)
            except (OSError, ValueError) as exc:
                self.theme_status.setText(f"写入预设失败：{exc}")
                self.theme_status.setStyleSheet("color: red")
                return
            self._refresh_theme_box(keep_value=value)
            self._changed()
            return
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
        cur = self.theme_box.selected_value()
        cur_path = self.theme_box.selected_path()
        dirty = self._theme_dirty
        dlg = CssEditorDialog(sample_xml=None, engine_chain=chain, parent=self,
                              initial_theme=cur)
        dlg.exec()
        # 退出只刷新预设列表（编辑器内可能新增/删除预设），**保持当前选择与未落盘改选**：
        # 先按真实默认重锚（首项「（默认）」= 预设键/run 槽/出厂），再把选择重新定位到
        # 原来那一项——否则把用户选的样式直接当默认刷新，会平白多出「（默认）」二字。
        self._refresh_theme_box()
        if cur_path:
            self.theme_box.select_path(cur_path)
        if dirty:
            self._on_theme_box_changed(None)

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

    def _gray_hint(self, text):
        """灰色括号说明标签（纯文本，含 <> 不被当作 HTML）；登记供核对。"""
        label = QLabel(text)
        label.setStyleSheet("color: gray")
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        self._paren_hint_labels.append(label)
        return label

    def _check_row(self, parent, text, hint="", checked=False):
        """复选框 + 灰色括号说明：说明短则同行，长则置于选项下一行（缩进）。

        parent 为 QVBoxLayout；返回复选框（供 get_options/set_options 读写）。"""
        box = self._check(text, checked=checked)
        if not hint:
            parent.addWidget(box)
            return box
        lab = self._gray_hint(hint)
        if len(hint) <= 24:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(box)
            row.addWidget(lab, 1)
            parent.addLayout(row)
        else:
            parent.addWidget(box)
            lab.setContentsMargins(20, 0, 0, 0)
            lab.setMaximumWidth(420)
            parent.addWidget(lab)
        return box

    def _tab_pagination(self):
        w = QWidget()
        grid = QGridLayout(w)
        left = QVBoxLayout()
        left.addWidget(self._hint("分节即分页单元：Word 里每节另起一页"))
        self.pg_boxes = {}
        self.pg_hints = {}
        for key in PAGINATION_KEYS:
            if key == "mulu_levels":
                continue  # 下拉，单独处理
            box = self._check(PAGINATION_LABELS[key])
            self.pg_boxes[key] = box
            hint = PAGINATION_HINTS.get(key, "")
            if hint:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(box)
                lab = self._gray_hint(hint)
                self.pg_hints[key] = lab
                row.addWidget(lab, 1)
                left.addLayout(row)
            else:
                left.addWidget(box)
        # 目录换页 level：开关（默认开）+ 下拉（仅1 / 1+2 / 1+2+3）
        self.mulu_on_box = self._check(
            PAGINATION_LABELS["mulu_levels"], checked=True)
        self.mulu_on_box.toggled.connect(self._on_mulu_on)
        self.mulu_levels_box = QComboBox()
        for _name, _lv in MULU_LEVEL_ITEMS:
            self.mulu_levels_box.addItem(_name, _lv)
        self.mulu_levels_box.setCurrentIndex(0)   # 默认仅 level-1
        self.mulu_levels_box.currentIndexChanged.connect(
            lambda _i: self._changed())
        _lrow = QHBoxLayout()
        _lrow.setContentsMargins(0, 0, 0, 0)
        _lrow.addWidget(self.mulu_on_box)
        _lrow.addWidget(self.mulu_levels_box)
        _llab = self._gray_hint(PAGINATION_HINTS["mulu_levels"])
        self.pg_hints["mulu_levels"] = _llab
        _lrow.addWidget(_llab, 1)
        self._on_mulu_on(self.mulu_on_box.isChecked())
        # 智能合页：level≥2 短节与下节同页（只看前一节累计字数）
        self.pg_smart_box = self._check("短节智能合页", checked=True)
        self.pg_smart_spin = QSpinBox()
        self.pg_smart_spin.setRange(50, 3000)
        self.pg_smart_spin.setSingleStep(50)
        self.pg_smart_spin.setValue(200)
        self.pg_smart_spin.setToolTip("前一节累计正文字数低于此值时，与下一节同页")
        self.pg_smart_spin.valueChanged.connect(lambda _v: self._changed())
        self.pg_smart_box.toggled.connect(self._on_pg_smart)
        _srow = QHBoxLayout()
        _srow.setContentsMargins(0, 0, 0, 0)
        _srow.addWidget(self.pg_smart_box)
        _spin_row = QHBoxLayout()
        _spin_row.setContentsMargins(0, 0, 0, 0)
        _spin_row.setSpacing(2)                 # 「不足」贴紧输入框
        _spin_row.addWidget(QLabel("不足"))
        _spin_row.addWidget(self.pg_smart_spin)
        _spin_row.addWidget(QLabel("字"))
        _srow.addLayout(_spin_row)
        _srow.addStretch(1)
        # 注释独立一行跨两列（与控件同行会被挤到过早折行）
        _smart_hint = self._gray_hint(
            "（默认仅 level-1 时不生效，需选 level-1+2…；"
            "前一节不足 200 字与下节同页，约合 A4 纸 5 行；"
            "仅 DOCX 及 docx2pdf 派生的 PDF）")
        _smart_hint.setContentsMargins(20, 0, 0, 0)
        self._on_pg_smart(self.pg_smart_box.isChecked())
        left.addStretch(1)
        grid.setColumnStretch(0, 1)             # 左列吃富余宽度
        grid.addLayout(left, 0, 0)
        grid.addLayout(_lrow, 1, 0, 1, 2)
        grid.addLayout(_srow, 2, 0, 1, 2)
        grid.addWidget(_smart_hint, 3, 0, 1, 2)
        return w

    def _tab_layout(self):
        w = QWidget()
        grid = QGridLayout(w)
        left = QVBoxLayout()
        self.split_box = self._check_row(
            left, "按卷分文件", "（每卷单独成一个文件；与分页联动）")
        self.close_juan_box = self._check_row(
            left, "显示结束卷标题", "（打印卷末「卷终」等 close 标题；默认关）")
        self.dedup_box = self._check_row(
            left, "卷名去重", "（卷头标题与书名重复时去重；默认开）", checked=True)
        self.strip_no_box = self._check_row(
            left, "去掉标题行首 No.",
            "（如「No. 1116-B 序」→「序」；正文内 No. 不动）")
        self.strip_no_box.setToolTip("去 head/jhead 行首 No. 令牌（如 No. 1116-B 序→序，余部去前导空格；正文内 No. 不动；书签保留原样）")
        self.corr_box = self._check_row(
            left, "CBETA校改字标红",
            "（默认关：CBETA 校改用字标红；与逐字校验无关）")
        self.corr_box.setToolTip(
            "output.corr_cbeta（默认关）：app.lem 原始 wit 含 #wit.cbeta 的正文用字标红——"
            "docx 红 #FF0000、html/epub span.corr；md/txt 不标；与逐字校验无关")
        left.addStretch(1)
        grid.addLayout(left, 0, 0)
        right = QVBoxLayout()
        self.ign_style_box = self._check_row(
            right, "忽略 XML 样式脏数据",
            "（样式脏数据开关默认关；忽略源 XML 的 <p style> 缩进，保留原文）")
        self.ign_space_box = self._check_row(
            right, "忽略 XML 空格脏数据",
            "（空格脏数据开关默认关；忽略源 XML 首尾空白，保留原文）")
        self.caesura_edit = QLineEdit("　　")
        self.caesura_edit.textChanged.connect(lambda _v: self._changed())
        crow = QHBoxLayout()
        crow.setContentsMargins(0, 0, 0, 0)
        crow.addWidget(QLabel("偈颂分隔符"))
        crow.addWidget(self.caesura_edit)
        crow.addWidget(self._gray_hint("（<caesura/> 处分隔，默认两个全角空格）"), 1)
        right.addLayout(crow)
        self.strip_quotes_box = self._check_row(
            right, "去掉偈颂首尾引号", "（去掉偈颂行首尾的「」『』）")
        self.pre_dedent_box = self._check("预排去缩进")
        self.pre_dedent_box.setToolTip(
            "output.pre_dedent（默认关）：预排段每行行首最多去 N 个空白"
            "（半角/全角/制表各计 1）；不足 N 去尽；行中与相对层次保留")
        self.pre_dedent_spin = QSpinBox()
        self.pre_dedent_spin.setRange(1, 10)
        self.pre_dedent_spin.setValue(4)
        self.pre_dedent_spin.setToolTip("每行行首最多去掉的空白个数")
        self.pre_dedent_spin.valueChanged.connect(lambda _v: self._changed())
        self.pre_dedent_box.toggled.connect(self._on_pre_dedent)
        prow = QHBoxLayout()
        prow.setContentsMargins(0, 0, 0, 0)
        prow.addWidget(self.pre_dedent_box)
        prow.addWidget(QLabel("最多去"))
        prow.addWidget(self.pre_dedent_spin)
        prow.addWidget(self._gray_hint(
            "（仅每行行首最多 N 个空白；不足去尽，行中不动）"), 1)
        right.addLayout(prow)
        self._on_pre_dedent(self.pre_dedent_box.isChecked())
        self.title_wrap_box = self._check_row(
            right, "书名超长换行", "（超 1 行在空格/成对破折号处换行；默认开）",
            checked=True)
        self.title_wrap_box.setToolTip(
            "output.title_smart_wrap（默认开）：书名超出版心 1 行时，"
            "在空格（去掉）/成对转折号 --/——（保留在行尾）处换行；"
            "单个 -–—（范围号）不断；仅 DOCX 链")
        right.addStretch(1)
        grid.addLayout(right, 0, 1)
        return w

    def _on_pre_dedent(self, on):
        self.pre_dedent_spin.setEnabled(bool(on))

    def _on_pg_smart(self, on):
        self.pg_smart_spin.setEnabled(bool(on))

    def _on_mulu_on(self, on):
        self.mulu_levels_box.setEnabled(bool(on))

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
        self.siddham_text_box = self._check("悉昙字形+读音文本形（docx 同款）", checked=False)
        self.siddham_text_box.setToolTip(
            "勾选后 html/epub/txt/md 有读音悉昙输出字形(读音)文本（如 誆(raṃ)），与 docx 一致；"
            "默认关闭走官方形态（html 空元素、txt 裸读音）。"
            "开启后偏离官方基线，校验必挂，阅读版专用")
        form.addRow("", self.siddham_text_box)

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
        arow = QHBoxLayout()
        # 三选一（互斥）：无注音 / 难字注音 / 全文注音 —— 单选按钮
        self.ann_none = self._radio("无注音", checked=True)
        self.ann_hard = self._radio("难字注音")
        self.ann_full = self._radio("全文注音")
        self.ann_none.setToolTip("不注音")
        self.ann_hard.setToolTip("只注难字：词表 + 分区/补充字形自动注音")
        self.ann_full.setToolTip("全文逐字注音（含难字注音；词表优先，忽略分区/频率）")
        for b in (self.ann_none, self.ann_hard, self.ann_full):
            arow.addWidget(b)
        arow.addStretch(1)
        form.addRow("", arow)
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
        self.ann_file = QLineEdit(ANN_DEFAULT_TABLE)
        self.ann_file.setReadOnly(True)          # 只能浏览选择，不可手输
        self.ann_file.setToolTip("注音词表（TSV）：只读；点「浏览…」选用其它词表，默认内置表")
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
        self.convert_report_box = self._check("转换报告", checked=True)
        self.convert_report_box.setToolTip(
            "output.convert_report（默认开）：记录渲染期间的特殊处理与对原文的改动"
            "（字体替换/缺字/预排去缩进/标题折行/去标题 No./忽略脏数据/注音待审等），"
            "落 {输出}/验证/{id 书名}（验证）/{id 书名}_转换报告.txt，与校验报告同处")
        _vrow = QHBoxLayout()
        _vrow.setContentsMargins(0, 0, 0, 0)
        _vrow.setSpacing(18)
        _vrow.addWidget(self.verify_on)
        _vrow.addWidget(self.convert_report_box)
        _vrow.addStretch(1)
        form.addRow("", _vrow)
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
        _af_hint = self._gray_hint("（首选基线缺失时自动下载官方文档）")
        _af_hint.setContentsMargins(20, 0, 0, 0)
        form.addRow("", _af_hint)
        form.addRow("", self.scope_box)
        _sj_hint = self._gray_hint("（只用 XML 实际覆盖卷的官方 _NNN 文件）")
        _sj_hint.setContentsMargins(20, 0, 0, 0)
        form.addRow("", _sj_hint)
        self.clean_verify_btn = QPushButton("清理校验产物…")
        self.clean_verify_btn.setToolTip(
            "删除输出目录下的校验中间产物（旧 *（验证）/ 新 验证/ 总目录："
            "正式比对档/compare/报告）；"
            "可重生成，不影响成品")
        self.clean_verify_btn.clicked.connect(self._on_clean_verify)
        form.addRow("", self.clean_verify_btn)
        return w

    def _verify_output_dir(self):
        """校验产物所在输出目录：优先主窗「输出目录」编辑框；取不到返回 ""。"""
        win = self.window()
        edit = getattr(win, "out_edit", None)
        if edit is not None:
            return (edit.text() or "").strip()
        return ""

    def _on_clean_verify(self):
        out_dir = self._verify_output_dir()
        if not out_dir:
            out_dir = QFileDialog.getExistingDirectory(
                self, "选择输出目录（清理其下的校验产物）")
        out_dir = (out_dir or "").strip()
        if not out_dir or not os.path.isdir(out_dir):
            if out_dir:
                QMessageBox.warning(self, "清理校验产物",
                                    f"目录不存在：{out_dir}")
            return
        import glob as _glob
        try:
            _custom = (((self._presets or {}).get("source") or {}).get(
                "verify_root") or "").strip() or None
        except Exception:
            _custom = None
        dirs = []
        for pat in ("*（验证）", "*（驗證）"):
            dirs += [d for d in _glob.glob(os.path.join(out_dir, pat))
                     if os.path.isdir(d)]
        _vroot = os.path.join(out_dir, "验证")
        if os.path.isdir(_vroot):
            for pat in ("*（验证）", "*（驗證）"):
                dirs += [d for d in _glob.glob(os.path.join(_vroot, pat))
                         if os.path.isdir(d)]
        if _custom:
            _ceff = os.path.abspath(_custom)
            if os.path.isdir(_ceff):
                for pat in ("*（验证）", "*（驗證）"):
                    dirs += [d for d in _glob.glob(os.path.join(_ceff, pat))
                             if os.path.isdir(d)]
        if not dirs:
            QMessageBox.information(self, "清理校验产物",
                                    "未发现校验产物目录（*（验证）/验证/）。")
            return
        names = "\n".join("  " + os.path.basename(d) for d in dirs[:12])
        more = f"\n  …（共 {len(dirs)} 个）" if len(dirs) > 12 else ""
        if QMessageBox.question(
                self, "清理校验产物",
                f"将删除以下 {len(dirs)} 个校验产物目录（不可撤销）：\n"
                f"{names}{more}\n\n位置：{out_dir}\n删除后下次校验会重新生成。",
                 QMessageBox.Yes | QMessageBox.No,
                 QMessageBox.No) != QMessageBox.Yes:
            return
        removed, errs = clean_verify_dirs(out_dir, _custom)
        msg = f"已删除 {removed} 个校验产物目录。"
        if errs:
            msg += "\n失败：\n" + "\n".join(errs[:5])
        QMessageBox.information(self, "清理校验产物", msg)

    # ---------- 配置预设（一切按下拉选中项） ----------
    def _set_cfg_title(self, action=None):
        """配置框标题常驻最后动作（不消失）；换预设/还原出厂后复原为“配置”。"""
        self.cfg_box.setTitle("配置" if not action else f"配置（{action}）")

    def _clear_default_if_deleted(self, path):
        """删掉的正是 run.json 默认指向的预设 → 清空槽，避免下次启动悬空警告。"""
        try:
            from pycbeta.theme import (load_run_config, set_run_slot,
                                       default_run_path)
            run = load_run_config()
            slot = (run.get("config-json") or "").strip()
            if not slot:
                return
            rdir = os.path.dirname(os.path.abspath(default_run_path()))
            hit = os.path.abspath(slot if os.path.isabs(slot)
                                  else os.path.join(rdir, slot))
            if os.path.normcase(hit) == os.path.normcase(os.path.abspath(path)):
                set_run_slot("config-json", "")
        except (OSError, ValueError):
            pass

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
        self._set_cfg_title("已保存")
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
        self._set_cfg_title("已设默认")
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
        if hasattr(self, "theme_default_btn"):  # 初始化时样式表卡尚未建
            self._update_theme_button()

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
        self._set_cfg_title()
        self._update_preset_buttons()
        self._refresh_theme_box()  # 预设自带主题键时跟走显示
        self._update_theme_button()  # 落盘目标跟走（预设生效/设为默认）
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
        self._set_cfg_title("已存预设")
        self._changed()

    def _on_preset_delete(self):
        path = self._selected_preset()
        if not path:
            QMessageBox.information(self, "删除预设", "“出厂默认”不是文件，删不掉。")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("删除预设")
        box.setText(f"确定删除预设“{os.path.basename(path)}”吗？")
        ok_btn = box.addButton("确定删除", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(ok_btn)
        box.exec()
        if box.clickedButton() is not ok_btn:
            return
        try:
            delete_config_preset(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self._clear_default_if_deleted(path)
        self._refresh_cfg_presets()
        self.refresh_slot_label()
        self._set_cfg_title("已删除")
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
        box = getattr(self, "theme_box", None)  # 所见即所得：当前样式选择跟进预设
        try:
            sel = box.selected_value() if box is not None else ""
        except Exception:
            sel = ""
        if sel and sel != "pdf_docx.css":
            data["pdf-docx-user-theme"] = \
                sel if sel.lower().endswith(".css") else sel + ".css"
        else:
            data.pop("pdf-docx-user-theme", None)
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
        self._set_cfg_title()
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
                "siddham_text": self.siddham_text_box.isChecked(),
                "inline_brackets": self.brackets_box.currentData(),
                "note_inline_brackets": self.note_brackets_box.currentData(),
                "split_juan": self.split_box.isChecked(),
                "show_close_juan": self.close_juan_box.isChecked(),
                "suppress_jhead_dup": self.dedup_box.isChecked(),
                "strip_head_no": self.strip_no_box.isChecked(),
                "corr_cbeta": self.corr_box.isChecked(),
                "ignore_xml_style": self.ign_style_box.isChecked(),
                "ignore_xml_space": self.ign_space_box.isChecked(),
                "verse_caesura": self.caesura_edit.text(),
                "verse_strip_quotes": self.strip_quotes_box.isChecked(),
                "pre_dedent": self.pre_dedent_box.isChecked(),
                "pre_dedent_spaces": int(self.pre_dedent_spin.value()),
                "title_smart_wrap": self.title_wrap_box.isChecked(),
                "convert_report": self.convert_report_box.isChecked(),
            },
            font_scale=float(self.scale_spin.value()),
            pagination={**{k: b.isChecked() for k, b in self.pg_boxes.items()},
                        "mulu_levels": (
                            list(self.mulu_levels_box.currentData() or ())
                            if self.mulu_on_box.isChecked() else []),
                        "mulu_smart_merge": self.pg_smart_box.isChecked(),
                        "mulu_smart_min_chars": int(
                            self.pg_smart_spin.value())},
            series_title={"enabled": self.series_on.isChecked(),
                          **self._series_extra},
            t2s=self.t2s_box.isChecked(),
            vertical=self.vert_box.isChecked(),
            typo=typo,
            annotations={
                "enabled": self.ann_hard.isChecked() or self.ann_full.isChecked(),
                "full_text": self.ann_full.isChecked(),
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
            _ml = pg.get("mulu_levels")
            if _ml is None:  # 旧键兼容：mulu_level1 bool → [1]/[]
                _ml = [1] if pg.get("mulu_level1", True) else []
            _ml = list(_ml)
            self.mulu_on_box.setChecked(bool(_ml))
            _idx = 0
            for _i, (_n, _lv) in enumerate(MULU_LEVEL_ITEMS):
                if list(_lv) == _ml:
                    _idx = _i
                    break
            self.mulu_levels_box.setCurrentIndex(_idx)
            self._on_mulu_on(self.mulu_on_box.isChecked())
            self.pg_smart_box.setChecked(bool(pg.get("mulu_smart_merge", True)))
            try:
                self.pg_smart_spin.setValue(
                    int(pg.get("mulu_smart_min_chars", 200)))
            except (TypeError, ValueError):
                self.pg_smart_spin.setValue(200)
            self._on_pg_smart(self.pg_smart_box.isChecked())
            o = opts.output or {}
            self.split_box.setChecked(bool(o.get("split_juan", False)))
            self.close_juan_box.setChecked(bool(o.get("show_close_juan", False)))
            self.dedup_box.setChecked(bool(o.get("suppress_jhead_dup", True)))
            self.strip_no_box.setChecked(bool(o.get("strip_head_no", False)))
            self.corr_box.setChecked(bool(o.get("corr_cbeta", False)))
            self.ign_style_box.setChecked(bool(o.get("ignore_xml_style", False)))
            self.ign_space_box.setChecked(bool(o.get("ignore_xml_space", False)))
            self.caesura_edit.setText(str(o.get("verse_caesura", "　　")))
            self.strip_quotes_box.setChecked(bool(o.get("verse_strip_quotes", False)))
            self.pre_dedent_box.setChecked(bool(o.get("pre_dedent", False)))
            try:
                self.pre_dedent_spin.setValue(int(o.get("pre_dedent_spaces", 4)))
            except (TypeError, ValueError):
                self.pre_dedent_spin.setValue(4)
            self.title_wrap_box.setChecked(bool(o.get("title_smart_wrap", True)))
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
            self.siddham_text_box.setChecked(bool(o.get("siddham_text", False)))
            i = self.brackets_box.findData(o.get("inline_brackets", "fullwidth"))
            if i >= 0:
                self.brackets_box.setCurrentIndex(i)
            j = self.note_brackets_box.findData(
                o.get("note_inline_brackets") or o.get("inline_brackets", "fullwidth"))
            if j >= 0:
                self.note_brackets_box.setCurrentIndex(j)
            self._sync_note_brackets_enabled()
            an = opts.annotations or {}
            _full = bool(an.get("full_text", False))
            _en = bool(an.get("enabled", False)) or _full
            self.ann_none.setChecked(not _en)
            self.ann_hard.setChecked(_en and not _full)
            self.ann_full.setChecked(_full)
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
            self.ann_file.setText(str(an.get("file") or ANN_DEFAULT_TABLE))
            vf = opts.verify or {}
            self.verify_on.setChecked(bool(vf.get("enabled", True)))
            self.maxdiff_spin.setValue(int(vf.get("maxDiff", 10) or 10))
            self.difflines_spin.setValue(int(vf.get("diffLines", 5) or 5))
            self.autofetch_box.setChecked(bool(vf.get("auto_fetch", True)))
            self.scope_box.setChecked(bool(vf.get("scope_juan", True)))
            self.convert_report_box.setChecked(
                bool(o.get("convert_report", True)))
        finally:
            self._emitting = False
        self._changed()


SOURCE_LABELS = [
    ("xml_dir", "本地 XML 候选源（只读；角色同远端 URL）"),
    ("cbeta_ebook", "XML及电子书（官方下载保存平展目录）"),
    ("verify_root", "校验目录（为空=跟随输出目录，即 {输出}/验证）"),
]
# catalog 已钉死内置（fetch.resolve_catalog），不再接受自定义：固定为程序内
# cbeta/data/sutra_mapping.txt，随「更新官方数据」刷新，此处不设编辑行。
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


def clear_xml_dir(root=None, preset_path=None):
    """把目标预设的 source.xml_dir 清空并保存（非 P5 源经确认后清除）。

    preset_path 为空时写默认用户预设（presets/config.user.json）。"""
    data = None
    if preset_path and os.path.isfile(preset_path):
        try:
            data = _read_json(preset_path)
        except (OSError, ValueError):
            data = None
    if data is None:
        data, _actual = load_slot("user", root)
    data = apply_source_edits(data, {"source": {"xml_dir": ""}})
    if preset_path:
        os.makedirs(os.path.dirname(os.path.abspath(preset_path)), exist_ok=True)
        with open(preset_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return
    save_current(data, root)


class SourceDialog(QDialog):
    """数据源窗口：查看/编辑输入来源目录与 CBETA 官方下载 URL 模板。

    确定 = 合并进目标预设（默认 `presets/config.user.json`；可指定当前选中预设，
    即本次命中的"未配置"错误来源）；取消 = 丢弃。"""

    def __init__(self, parent=None, preset_path=None, out_dir=None):
        super().__init__(parent)
        self._preset_path = preset_path or ""
        self._init_out_dir = out_dir or ""
        name = os.path.basename(self._preset_path) or USER_PRESET_NAME
        self.setWindowTitle(f"设置（{name}）")
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        if self._preset_path and os.path.isfile(self._preset_path):
            try:
                data = _read_json(self._preset_path)
            except (OSError, ValueError):
                data, _actual = load_slot("user")
        else:
            data, _actual = load_slot("user")
        src = (data.get("source") or {})
        # 路径 edits 均为隐藏数据载体，可见行在各 tab（输入输出/本地官方电子书）；
        # 保存/测试口径不变（path_edits 键齐全）
        self.path_edits = {}
        for key, label in SOURCE_LABELS:
            edit = QLineEdit(str(src.get(key, "")))
            edit.setReadOnly(True)  # 只能浏览选择，不可手输（与注音词表行一致）
            edit.setToolTip("只读；点「浏览…」修改")
            self.path_edits[key] = edit
        self.title_t2s_box = QCheckBox("工作目录书名转简体（t2s）")
        self.title_t2s_box.setChecked(bool(src.get("title_t2s", True)))
        self.src_tabs = QTabWidget()
        # 输入输出 tab（排第一）：XML 及电子书 + 输出目录 + 转简体
        tab_io = QWidget()
        tio = QVBoxLayout(tab_io)
        tio.addWidget(QLabel("XML及电子书"))
        row_eb = QHBoxLayout()
        eb_edit = self.path_edits["cbeta_ebook"]
        eb_browse = QPushButton("浏览…")
        eb_browse.clicked.connect(lambda _v, e=eb_edit: self._browse_dir(e))
        row_eb.addWidget(eb_edit, 1)
        row_eb.addWidget(eb_browse)
        tio.addLayout(row_eb)
        eb_lab = QLabel("官方下载保存平展目录  source.cbeta_ebook")
        eb_lab.setStyleSheet("color: gray")
        tio.addWidget(eb_lab)
        tio.addWidget(QLabel("输出目录"))
        row_out = QHBoxLayout()
        self.io_out_edit = QLineEdit(out_dir or "")
        out_browse = QPushButton("浏览…")
        out_browse.clicked.connect(lambda _v: self._browse_dir(self.io_out_edit))
        out_open = QPushButton("打开目录")
        out_open.clicked.connect(self._open_out_dir)
        row_out.addWidget(self.io_out_edit, 1)
        row_out.addWidget(out_browse)
        row_out.addWidget(out_open)
        tio.addLayout(row_out)
        out_lab = QLabel("source.out_dir（输出成品目录，存入配置）")
        out_lab.setStyleSheet("color: gray")
        tio.addWidget(out_lab)
        tio.addWidget(QLabel("校验目录"))
        row_vroot = QHBoxLayout()
        vr_edit = self.path_edits["verify_root"]
        vr_browse = QPushButton("浏览…")
        vr_browse.clicked.connect(lambda _v, e=vr_edit: self._browse_dir(e))
        vr_clear = QPushButton("清空")
        vr_clear.setToolTip("清空=跟随输出目录（{输出}/验证）")
        vr_clear.clicked.connect(lambda _v, e=vr_edit: e.setText(""))
        row_vroot.addWidget(vr_edit, 1)
        row_vroot.addWidget(vr_browse)
        row_vroot.addWidget(vr_clear)
        tio.addLayout(row_vroot)
        vr_lab = QLabel("source.verify_root（为空=跟随输出目录，即 {输出}/验证）")
        vr_lab.setStyleSheet("color: gray")
        tio.addWidget(vr_lab)
        row_ver = QHBoxLayout()
        self.io_verify_edit = QLineEdit()
        self.io_verify_edit.setReadOnly(True)
        self.io_verify_edit.setToolTip("生效校验根（自选或 {输出}/验证）")
        ver_refresh = QPushButton("刷新")
        ver_refresh.setToolTip("重新统计校验目录占用")
        ver_refresh.clicked.connect(lambda _v: self._refresh_verify_info())
        ver_open = QPushButton("打开目录")
        ver_open.clicked.connect(lambda _v: self._open_verify_dir())
        ver_clean = QPushButton("删除校验产物…")
        ver_clean.setToolTip("删除生效校验根下的校验中间产物（可重生成）")
        ver_clean.clicked.connect(lambda _v: self._on_clean_verify_io())
        row_ver.addWidget(self.io_verify_edit, 1)
        row_ver.addWidget(ver_refresh)
        row_ver.addWidget(ver_open)
        row_ver.addWidget(ver_clean)
        tio.addLayout(row_ver)
        self.io_verify_size = QLabel()
        self.io_verify_size.setStyleSheet("color: gray")
        tio.addWidget(self.io_verify_size)
        self.io_out_edit.textChanged.connect(
            lambda _t: self._refresh_verify_info())
        vr_edit.textChanged.connect(
            lambda _t: self._refresh_verify_info())
        self._refresh_verify_info()
        tio.addWidget(self.title_t2s_box)
        t2s_lab = QLabel(
            "source.title_t2s：工作目录与输出成品文件名中的书名是否转简体"
            "（默认开；只影响新建名字，不改已存在目录/文件，不改文件内容）")
        t2s_lab.setStyleSheet("color: gray")
        t2s_lab.setWordWrap(True)
        tio.addWidget(t2s_lab)
        tio.addStretch(1)
        self.src_tabs.addTab(tab_io, "输入输出")
        # 本地官方电子书 tab（排第二）：本地 XML 候选源置顶 + 三格式官方基线目录；
        # 为空=未配置（该格式回退旧行为：只查输入相邻目录）
        tab_base = QWidget()
        t0 = QVBoxLayout(tab_base)
        _bl = src.get("baselines") if isinstance(src.get("baselines"), dict) else {}
        self.base_edits = {}
        self._syncing_base = False

        def _add_base_row(key, label, initial):
            row = QHBoxLayout()
            edit = QLineEdit(str(initial))
            edit.setReadOnly(True)  # 只能浏览选择，不可手输（与主表一致）
            edit.setToolTip("只读；点「浏览…」修改")
            browse = QPushButton("浏览…")
            browse.clicked.connect(lambda _v, e=edit: self._browse_dir(e))
            clear = QPushButton("清空")
            clear.setToolTip("清空=未配置，该格式回退旧行为")
            clear.clicked.connect(lambda _v, e=edit: e.setText(""))
            row.addWidget(edit, 1)
            row.addWidget(browse)
            row.addWidget(clear)
            t0.addLayout(row)
            lab = QLabel(f"{label}  " +
                         ("source.xml_dir" if key == "xml_dir"
                          else f"source.baselines.{key}"))
            lab.setStyleSheet("color: gray")
            t0.addWidget(lab)
            self.base_edits[key] = edit

        # 本地 XML 候选源置顶
        _add_base_row("xml_dir", "本地XML候选源", src.get("xml_dir", ""))
        _base_info = QLabel(
            "<a href='https://cbeta.org/ebooks'>官方</a>整套电子书，"
            "可用于校验（可选）：")
        _base_info.setTextFormat(Qt.RichText)
        _base_info.setOpenExternalLinks(True)
        t0.addWidget(_base_info)
        # 官方电子书根目录（如 CBETA 2026r2）：一键自动检测子目录对应格式
        rrow = QHBoxLayout()
        self.base_root_edit = QLineEdit(str(src.get("baselines_root", "")))
        self.base_root_edit.setReadOnly(True)
        self.base_root_edit.setToolTip("只读；点「浏览…」修改")
        rbowse = QPushButton("浏览…")
        rbowse.clicked.connect(
            lambda _v: self._browse_dir(self.base_root_edit))
        self.btn_detect_base = QPushButton("自动检测")
        self.btn_detect_base.setToolTip(
            "按子目录名识别格式（text-with-notes/docx/epub…），填入下方各行；"
            "只填能识别的，其余不动")
        self.btn_detect_base.clicked.connect(self._on_detect_baselines)
        rrow.addWidget(self.base_root_edit, 1)
        rrow.addWidget(rbowse)
        rrow.addWidget(self.btn_detect_base)
        t0.addLayout(rrow)
        rlab = QLabel("官方电子书根目录  source.baselines_root（选填，仅用于自动检测）")
        rlab.setStyleSheet("color: gray")
        t0.addWidget(rlab)
        for key, label in (("txt", "TXT 无注释"),
                           ("txt_notes", "TXT 带注释"),
                           ("docx", "DOCX"),
                           ("epub", "EPUB"),
                           ("pdf", "PDF")):
            _add_base_row(key, label, _bl.get(key, ""))
        # xml_dir 与隐藏主表 edit 同键双向同步（保存口径不变）
        _main_xml = self.path_edits.get("xml_dir")

        def _sync_xml_from_tab(text):
            if self._syncing_base:
                return
            self._syncing_base = True
            try:
                if _main_xml is not None and _main_xml.text() != text:
                    _main_xml.setText(text)
            finally:
                self._syncing_base = False

        def _sync_xml_from_main(text):
            if self._syncing_base:
                return
            self._syncing_base = True
            try:
                if self.base_edits["xml_dir"].text() != text:
                    self.base_edits["xml_dir"].setText(text)
            finally:
                self._syncing_base = False

        self.base_edits["xml_dir"].textChanged.connect(_sync_xml_from_tab)
        if _main_xml is not None:
            _main_xml.textChanged.connect(_sync_xml_from_main)
        t0.addStretch(1)
        tab_dl = QWidget()
        t1 = QVBoxLayout(tab_dl)
        t1.addWidget(QLabel("官方下载 URL 模板（{canon}/{vol}/{file}/{id} 为占位符）："))
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
        t1.addWidget(self.dl_table, 1)
        tab_upd = QWidget()
        t2 = QVBoxLayout(tab_upd)
        t2.addWidget(QLabel("官方数据更新源（remote_sources.json，只读；"
                            "点下方「更新官方数据」刷新；单元格可选中后 Ctrl+C 拷贝）："))
        self.upd_table = QTableWidget(0, 4)
        self.upd_table.setHorizontalHeaderLabels(
            ["数据项", "更新 URL", "本地文件", "上次更新"])
        hdr = self.upd_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)   # 更新 URL 放宽
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)   # 本地文件放宽
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 日期缩窄
        # 只读但可选中拷贝：禁编辑触发 + 扩展选择 + Ctrl+C 进剪贴板
        self.upd_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.upd_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.upd_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        copy_sc = QShortcut(QKeySequence.Copy, self.upd_table)
        copy_sc.setContext(Qt.WidgetShortcut)
        copy_sc.activated.connect(
            lambda: self._copy_table_selection(self.upd_table))
        try:
            from pycbeta.update_data import source_rows
            _upd_rows = source_rows()
        except Exception:
            _upd_rows = []
        self.upd_table.setRowCount(len(_upd_rows))
        for i, (name, url, dest, when) in enumerate(_upd_rows):
            for j, text in enumerate((name, url, dest, when)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 全表只读
                if j == 1:
                    item.setToolTip(url)
                self.upd_table.setItem(i, j, item)
        t2.addWidget(self.upd_table, 1)
        self.upd_table.itemDoubleClicked.connect(self._open_upd_url)
        upd_hint = QLabel("双击「更新 URL」列可用浏览器打开链接；"
                          "单元格可选中后 Ctrl+C 拷贝。")
        upd_hint.setStyleSheet("color: gray")
        upd_hint.setWordWrap(True)
        t2.addWidget(upd_hint)
        # 输入输出排第一，本地官方电子书排第二，更新源第三，下载模板第四
        self.src_tabs.insertTab(1, tab_base, "本地官方电子书")
        self.src_tabs.addTab(tab_upd, "官方数据更新源")
        self.src_tabs.addTab(tab_dl, "电子书下载模板")
        layout.addWidget(self.src_tabs, 1)
        urow = QHBoxLayout()
        self.btn_update_data = QPushButton("更新官方数据")
        self.btn_update_data.setToolTip(
            "打开更新对话框：列出可从官方更新的数据，确认后同步 "
            "（先校验再落盘，一致跳过）")
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
        t2.addLayout(urow)
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
        """官方数据更新改走对话框：先列更新源，确认后再跑（执行逻辑在 DataUpdateDialog）。"""
        dlg = DataUpdateDialog(self)
        dlg.exec()
        self._refresh_last_update()

    def _dialog_presets(self):
        """以对话框当前编辑值构造 presets（未保存也能检查更新）。"""
        src = {k: e.text().strip() for k, e in self.path_edits.items()}
        src["title_t2s"] = bool(self.title_t2s_box.isChecked())
        src["baselines"] = {k: self.base_edits[k].text().strip()
                            for k in ("txt", "txt_notes", "docx", "epub",
                                      "pdf")}
        src["baselines_root"] = self.base_root_edit.text().strip()
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

    def _on_detect_baselines(self):
        """官方电子书根目录一键检测：子目录名→格式，填入下方各行。
        只填能识别的（未命中的行不动）；无命中弹提示。"""
        from pycbeta.fetch import detect_baseline_dirs
        root = self.base_root_edit.text().strip()
        got = detect_baseline_dirs(root) if root else {}
        filled = []
        for key in ("txt", "txt_notes", "docx", "epub", "pdf"):
            if got.get(key) and key in self.base_edits:
                self.base_edits[key].setText(got[key])
                filled.append(key)
        if not filled:
            QMessageBox.information(
                self, "自动检测",
                "该目录下未识别出已知格式子目录\n"
                "（text-with-notes/docx/epub/pdf/txt），请检查根目录。")

    def out_dir(self):
        """对话框内输出目录当前值（仅本次运行，不存入预设）。"""
        return self.io_out_edit.text().strip()

    def _open_out_dir(self):
        d = self.io_out_edit.text().strip() or os.path.join(os.getcwd(), "out")
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))

    def _effective_verify_root(self):
        """生效校验根：自选（source.verify_root）优先，否则 {输出}/验证。"""
        try:
            custom = self.path_edits["verify_root"].text().strip()
        except (AttributeError, RuntimeError, KeyError):
            custom = ""
        if custom:
            return os.path.abspath(custom)
        try:
            from pycbeta.verify import default_verify_root
            return default_verify_root(self.io_out_edit.text().strip())
        except Exception:
            return ""

    def _refresh_verify_info(self):
        """校验目录行刷新：生效路径 + 占盘重统（静默失败保底）。"""
        try:
            vroot = self._effective_verify_root()
        except Exception:
            vroot = ""
        try:
            self.io_verify_edit.setText(vroot)
        except (AttributeError, RuntimeError):
            return
        try:
            custom = self.path_edits["verify_root"].text().strip()
            total, count = verify_dir_size(self.io_out_edit.text().strip(),
                                           custom or None)
        except Exception:
            total, count = 0, 0
        try:
            if count:
                self.io_verify_size.setText(
                    f"占用 {_human_size(total)}（{count} 个文件）")
            else:
                self.io_verify_size.setText("（尚无校验产物）")
        except (AttributeError, RuntimeError):
            pass

    def _open_verify_dir(self):
        try:
            d = self.io_verify_edit.text().strip()
        except (AttributeError, RuntimeError):
            return
        if d and os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))

    def _on_clean_verify_io(self):
        """输入输出栏一键删除：带占用确认，删完刷新（只清生效根及旧平展）。"""
        out_dir = self.io_out_edit.text().strip()
        try:
            custom = self.path_edits["verify_root"].text().strip() or None
        except (AttributeError, RuntimeError, KeyError):
            custom = None
        total, count = verify_dir_size(out_dir, custom)
        if not count:
            QMessageBox.information(self, "删除校验产物",
                                    "尚无校验产物，无需删除。")
            return
        if QMessageBox.question(
                self, "删除校验产物",
                f"将删除输出目录下的校验产物（{count} 个文件，"
                f"占用 {_human_size(total)}，不可撤销）：\n  {out_dir}\n\n"
                "删除后下次校验会重新生成。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        removed, errs = clean_verify_dirs(out_dir, custom)
        msg = f"已删除 {removed} 个校验产物目录。"
        if errs:
            msg += "\n失败：\n" + "\n".join(errs[:5])
        QMessageBox.information(self, "删除校验产物", msg)
        self._refresh_verify_info()

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "选择目录", edit.text().strip() or "")
        if d:
            edit.setText(d)

    def _open_upd_url(self, item):
        """官方数据更新源表：双击「更新 URL」列用浏览器打开（仅 http/https）。"""
        try:
            if item is None or item.column() != 1:
                return
            url = (item.text() or "").strip()
            if url.lower().startswith(("http://", "https://")):
                QDesktopServices.openUrl(QUrl(url))
        except (AttributeError, RuntimeError):
            pass

    @staticmethod
    def _copy_table_selection(table):
        """选中单元格 → 剪贴板（制表符分列、换行分行；供只读信息表 Ctrl+C）。"""
        try:
            idxs = table.selectionModel().selectedIndexes()
        except (AttributeError, RuntimeError):
            return
        if not idxs:
            return
        rows = {}
        for ix in idxs:
            rows.setdefault(ix.row(), {})[ix.column()] = ix.data() or ""
        lines = ["\t".join(cols.get(c, "") for c in range(max(cols) + 1))
                 for _, cols in sorted(rows.items())]
        QApplication.clipboard().setText("\n".join(lines))

    def accept(self):
        if self._preset_path and os.path.isfile(self._preset_path):
            try:
                data = _read_json(self._preset_path)
            except (OSError, ValueError):
                data, _actual = load_slot("user")
        else:
            data, _actual = load_slot("user")
        values = {"source": {k: e.text().strip() for k, e in self.path_edits.items()},
                  "downloads": {}}
        values["source"]["title_t2s"] = bool(self.title_t2s_box.isChecked())
        values["source"]["baselines"] = {
            k: self.base_edits[k].text().strip()
            for k in ("txt", "txt_notes", "docx", "epub", "pdf")}
        values["source"]["baselines_root"] = \
            self.base_root_edit.text().strip()
        values["source"]["out_dir"] = self.io_out_edit.text().strip()
        for i in range(self.dl_table.rowCount()):
            k = self.dl_table.item(i, 0).text()
            v = self.dl_table.item(i, 1).text() if self.dl_table.item(i, 1) else ""
            values["downloads"][k] = v.strip()
        xml_dir = values["source"].get("xml_dir", "")
        if not values["source"].get("cbeta_ebook", ""):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("电子书输出目录未配置")
            box.setText("电子书输出目录（source.cbeta_ebook）是必填项，"
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
        merged = apply_source_edits(data, values)
        if self._preset_path:
            try:
                os.makedirs(os.path.dirname(
                    os.path.abspath(self._preset_path)), exist_ok=True)
                with open(self._preset_path, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except OSError as exc:
                QMessageBox.warning(self, "保存失败", str(exc))
                return
        else:
            save_current(merged)
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
