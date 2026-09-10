"""GUI 外观三态（P10 深色模式）：跟随系统 / 浅色 / 深色。

- 存用户槽：config.user.json 顶层 `gui_theme`（面板存档惯例；面板保存合并时原样保留）。
- 生效：QApplication.styleHints().setColorScheme（Qt6.5+，本仓 PySide6>=6.6）。
- 提示色：hint/error 经本模块 helper 取值（浅色沿用 legacy gray/red，深色换可读色）；
  运行切换由 recolor_widgets() 全局归一（认 legacy 精确串 + 已换肤值，双向幂等）。
- QToolTip 已是深底白字、色块按钮是用户数据、#cc6600 行标超出本次范围，不管。
"""

MODES = ("follow", "light", "dark")
MODE_LABELS = {"follow": "跟随系统", "light": "浅色", "dark": "深色"}
_SLOT_KEY = "gui_theme"

_HINT_LIGHT = "color: gray"
_ERROR_LIGHT = "color: red"
_HINT_DARK = "color: #B0B0B0"
_ERROR_DARK = "color: #FF7B72"


def get_mode(root=None) -> str:
    """用户槽外观模式；缺失/非法回 follow。只读文件，不碰 QApplication。"""
    try:
        from pycbeta.gui.panel import load_slot
        data, _actual = load_slot("user", root)
        mode = (data or {}).get(_SLOT_KEY, "follow")
        return mode if mode in MODES else "follow"
    except Exception:
        return "follow"


def set_mode(mode, root=None) -> str:
    """写用户槽（其余键原样保留；空槽从 {} 起，不依赖出厂文件存在）；返回落盘值。"""
    from pycbeta.gui.panel import load_slot, save_current
    mode = mode if mode in MODES else "follow"
    try:
        cur, _actual = load_slot("user", root)
    except Exception:
        cur = {}
    data = dict(cur or {})
    data[_SLOT_KEY] = mode
    save_current(data, root)
    return mode


def _app():
    try:
        from PySide6.QtWidgets import QApplication
        return QApplication.instance()
    except Exception:
        return None


# apply_mode 记录的显式意图（None=跟随，走系统探测；light/dark=直接生效，
# 不依赖各平台 styleHints 是否反射——offscreen 等环境 setColorScheme 常驻 Unknown）。
_FORCED = {"mode": None}

# 深色板是否已应用（避免重复 repolish；回切判定不读已污染的 palette）。
_APPLIED = {"dark": False}


def _dark_palette():
    """深色调色板（只换板、不换 style：windowsvista 原生 + 完整深色板实测白字正常；
    Fusion 方案已废——setStyle 删旧对象有 ownership 坑，且 offscreen 下 name() 无意义）。
    浅色回切 fresh QPalette()（恒为浅色标准板，不受深色系统污染）。"""
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtCore import Qt
    window = QColor(53, 53, 53)
    text = QColor(255, 255, 255)
    base = QColor(35, 35, 35)
    accent = QColor(42, 130, 218)
    dim = QColor(150, 150, 150)
    p = QPalette()
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        p.setColor(group, QPalette.Window, window)
        p.setColor(group, QPalette.WindowText, text)
        p.setColor(group, QPalette.Base, base)
        p.setColor(group, QPalette.AlternateBase, window)
        p.setColor(group, QPalette.Text, text)
        p.setColor(group, QPalette.Button, window)
        p.setColor(group, QPalette.ButtonText, text)
        p.setColor(group, QPalette.BrightText, QColor(255, 0, 0))
        p.setColor(group, QPalette.Highlight, accent)
        p.setColor(group, QPalette.HighlightedText, QColor(255, 255, 255))
        p.setColor(group, QPalette.PlaceholderText, dim)
        p.setColor(group, QPalette.Link, accent)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, dim)
    return p


def is_dark() -> bool:
    """当前生效是否为深色：显式意图优先；跟随只认系统 scheme（不读 palette，
    否则 follow 切回时会被自己刚刷的板子锁死）。"""
    if _FORCED["mode"] == "dark":
        return True
    if _FORCED["mode"] == "light":
        return False
    return _system_dark()


def _system_dark() -> bool:
    app = _app()
    if app is None:
        return False
    try:
        from PySide6.QtCore import Qt
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def hint_style() -> str:
    """提示灰（hint/说明行）：浅色沿用 legacy，深色换可读浅灰。"""
    return _HINT_DARK if is_dark() else _HINT_LIGHT


def error_style() -> str:
    """报错红：浅色沿用 legacy，深色换可读浅红。"""
    return _ERROR_DARK if is_dark() else _ERROR_LIGHT


def apply_mode(mode) -> str:
    """三态生效 + 全局 recolor；返回生效值（无 QApplication 时只返回，不崩）。
    深色走 Fusion+深色板（全控件跟随：输入框/下拉/tab/表/栏），浅色还原原厂。"""
    mode = mode if mode in MODES else "follow"
    _FORCED["mode"] = None if mode == "follow" else mode
    app = _app()
    if app is not None:
        try:
            from PySide6.QtCore import Qt
            target = {"follow": Qt.ColorScheme.Unknown,
                      "light": Qt.ColorScheme.Light,
                      "dark": Qt.ColorScheme.Dark}[mode]
            if hasattr(app.styleHints(), "setColorScheme"):
                app.styleHints().setColorScheme(target)
        except Exception:
            pass
        try:
            from PySide6.QtGui import QPalette
            want_dark = (mode == "dark") or (mode == "follow" and _system_dark())
            if want_dark and not _APPLIED["dark"]:
                app.setPalette(_dark_palette())
                _APPLIED["dark"] = True
            elif not want_dark and _APPLIED["dark"]:
                app.setPalette(QPalette())
                _APPLIED["dark"] = False
        except Exception:
            pass
        recolor_widgets()
    return mode


def recolor_widgets() -> dict:
    """全局归一提示色：认 legacy 精确串与已换肤值，按当前 scheme 重写。
    返回 {"hint": n, "error": n} 改写计数（单测断言用）。"""
    app = _app()
    counts = {"hint": 0, "error": 0}
    if app is None:
        return counts
    want_hint, want_error = hint_style(), error_style()
    try:
        widgets = app.allWidgets()
    except Exception:
        return counts
    for w in widgets:
        try:
            cur = w.styleSheet()
        except Exception:
            continue
        if not cur:
            continue
        if cur in (_HINT_LIGHT, _HINT_DARK) and cur != want_hint:
            try:
                w.setStyleSheet(want_hint)
                counts["hint"] += 1
            except Exception:
                pass
        elif cur in (_ERROR_LIGHT, _ERROR_DARK) and cur != want_error:
            try:
                w.setStyleSheet(want_error)
                counts["error"] += 1
            except Exception:
                pass
    return counts


def theme_combo_items():
    """（label, value）供配置栏外观下拉。"""
    return [(MODE_LABELS[m], m) for m in MODES]
