"""DOCX 所见即所得 CSS 编辑器（P1 GUI）。

三层出口（与 panel/__main__ 同构）：
- ``CssEditorDialog`` —— 纯对话框，``(sample_xml=None, engine_chain=None, parent=None)``，
  当前 GUI 样式表卡弹窗 + publish 侧同样 import 即用；
- ``main()`` —— ``python -m pycbeta.gui.css_editor [--sample 样张.xml]`` 独立运行；
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

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSignalBlocker, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
    QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSplitter, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STYLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "styles")
FACTORY_CSS = os.path.join(_STYLES_DIR, "pdf_docx.css")

# 样张候选（首选用户精简样本 css-presets/sample.xml；glob，按序取首个命中者）
SAMPLE_CANDIDATES = (
    os.path.join(REPO_ROOT, "css-presets", "sample.xml"),
    r"E:\dev\cbeta\test\T0349*\T12n0349.xml",
    r"E:\dev\cbeta\test\T1144*\T20n1144.xml",
)

# 左侧可调行（书本排版顺序）：(覆盖块选择器, 显示名)
EDITABLE_ROWS = (
    ("p.series-title", "经藏名"),
    ("h1.title", "书名"),
    ("div.div-xu p.head", "序标题"),
    ("p.author", "作者"),
    ("p.translator", "译者"),
    ("p.byline", "题署"),
    ("p.juan", "卷名"),
    ("p.pin", "品名"),
    ("p.head", "标题"),
    ("p", "正文"),
    ("p.dharani", "咒语"),
    ("p.form", "格式段"),
    ("pre", "预排"),
    ("div.lg", "偈颂"),
    ("div.div-note", "字义"),
    ("span.doube-line-note", "双行夹注"),
    ("span.interlinear-note", "单行夹注"),
    ("span.note-inline", "括号夹注"),
    ("sup.note-ref", "注释序号"),
    (".footnote", "脚注文字"),
    ("a.noteAnchor", "注锚"),
    ("a.noteAnchor.add", "注锚·新增"),
    ("a.noteAnchor.mod", "注锚·改字"),
    ("a.noteAnchor.orig", "注锚·原文"),
    ("a.noteAnchor.star", "注锚·星号"),
    ("[rend~=kaiti]", "行内·楷体"),
    ("[rend~=heiti]", "行内·黑体"),
    ("[rend~=fangsong]", "行内·仿宋"),
    ("[rend~=mingti]", "行内·明体"),
)

# 行提示（复杂规则去源码页；DOCX 忽略的属性选择器特别说明）
ROW_TIPS = {
    "p.series-title": "首页左上角一行；config 仅留开关",
    "p.head": "标题1–6级在源码页调（仅HTML/PDF，DOCX忽略）",
    "div.lg": "注记类偈行颜色在源码页（div.lg.note1/2）",
}

WEIGHT_ITEMS = [("（跟随）", ""), ("加粗", "bold"), ("正常", "normal")]

# 字体下拉分组：中文按关键字 buckets（首中即停；宋体在明体前吞掉 PMingLiU 类）
_CJK_BUCKETS = (
    ("黑体", ("黑", "雅黑", "苹方", "pingfang", "gothic", "hei")),
    ("宋体", ("宋", "sun", "明流", "mingliu", "pmingliu", "細明", "细明",
              "songti", "simsun", "nsimsun", "song")),
    ("楷体", ("楷", "kai")),
    ("仿宋", ("仿宋", "fangsong")),
    ("明体", ("明朝", "mincho", "ming")),
    ("隶书", ("隶", "lisu")),
    ("圆体", ("圆", "yuan")),
    ("魏碑", ("魏", "wei")),
    ("行草", ("行", "草", "xing", "cao")),
    ("标题", ("标题", "见出", "zhaohua")),
)
_WESTERN_FONTS = ("Times New Roman", "Courier New", "Aptos")

_GENERIC_FAMILIES = frozenset({
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace",
})

# 管线引用的跨平台已知字体：本机未装只警告（Word/他机可用），不报错。
# 覆盖出厂 CSS / 回退链 / 缺字链 / 悉昙配置里出现过的名字。
_KNOWN_FONTS = frozenset({
    "Songti TC", "Songti SC", "PMingLiU", "MingLiU", "SimSun", "NSimSun",
    "SimHei", "SimKai", "KaiTi", "FangSong", "FangSong_GB2312", "LiSu",
    "DFKaiShu", "DFKai-SB", "SimSun-ExtB", "MingLiU-ExtB",
    "Microsoft YaHei", "Microsoft JhengHei", "Microsoft JhengHei UI",
    "微軟正黑體", "微軟雅黑", "新細明體", "細明體", "標楷體",
    "宋体", "黑体", "楷体", "仿宋", "隶书", "隸書", "朝华标题B",
    "ZhaohuaMinB", "Calibri", "Cambria",
    "CBETA Supplement", "Ranjana", "Siddam",
})


def group_font_names(names):
    """[字体名] → {组名: [字体]}（纯函数，可单测）。西文三固定另行，不进 buckets。"""
    groups = {g: [] for g, _ks in _CJK_BUCKETS}
    groups["未分类"] = []
    for name in dict.fromkeys(n for n in (names or []) if n):
        groups[classify_font(name)].append(name)
    return groups


def classify_font(name):
    """单个字体名 → bucket 组名（纯函数）。"""
    key = (name or "").lower()
    for gname, kws in _CJK_BUCKETS:
        if any(k in key for k in kws):
            return gname
    return "未分类"


_CJK_NAME_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def pick_display_name(names, primary=""):
    """显示名优先中文：文件名表含 CJK 取首个中文名；否则 _ZH_ALIASES 补；再否则主名。"""
    from pycbeta import fonts as _fonts
    cands = list(dict.fromkeys([n for n in (names or []) if n]))
    if primary:
        alias = _fonts._ZH_ALIASES.get(_fonts._normalize(primary))
        if alias and alias not in cands:
            cands.append(alias)
    for n in cands:
        if _CJK_NAME_RE.search(n):
            return n
    return primary or (cands[0] if cands else "")


def font_group_model(fresh=False):
    """→ ({组名: [显示名]}, [(文件名, 显示名)], 字库目录)。

    显示名优先中文；纯英文且未分类、非西文精选的不陈列（下拉过滤）。
    fresh=True 重扫系统（刷新按钮用）。
    """
    from pycbeta import fonts as _fonts
    loc = _fonts.FontLocator() if fresh else _fonts.locator()
    groups = {g: [] for g, _ks in _CJK_BUCKETS}
    groups["未分类"] = []
    for primary, names, _path in _fonts.iter_installed(loc):
        bucket = classify_font(primary)
        display = pick_display_name(names, primary)
        if bucket == "未分类" and (display in _WESTERN_FONTS
                                   or not _CJK_NAME_RE.search(display or "")):
            continue  # 西文精选走固定组；纯英文非精选过滤
        if display and display not in groups[bucket]:
            groups[bucket].append(display)
    fonts_dir = os.path.join(REPO_ROOT, "cbeta", "fonts")
    bundled = []
    if os.path.isdir(fonts_dir):
        for fn in sorted(os.listdir(fonts_dir)):
            if not fn.lower().endswith(_fonts.FONT_EXTS):
                continue
            try:
                names = _fonts.read_family_names(os.path.join(fonts_dir, fn))
            except OSError:
                names = []
            disp = pick_display_name(names, os.path.splitext(fn)[0])
            bundled.append((fn, disp or fn))
    return groups, bundled, fonts_dir


def _norm_hex(val):
    """#rgb/#rrggbb → 小写 #rrggbb；其余返回 ""。"""
    m = re.match(r"#([0-9a-fA-F]{3})$", (val or "").strip())
    if m:
        return "#" + "".join(c * 2 for c in m.group(1)).lower()
    m = re.match(r"#([0-9a-fA-F]{6})$", (val or "").strip())
    return ("#" + m.group(1).lower()) if m else ""


def css_colors(css_text):
    """工作 CSS 全部 color → [(规范色值, 来源选择器)]（首次序；注释掉的不算）。"""
    import tinycss2
    out, seen = [], set()
    try:
        tokens = tinycss2.parse_stylesheet(css_text or "", skip_comments=True,
                                           skip_whitespace=True)
    except Exception:  # noqa: BLE001
        return []
    for tok in tokens:
        if tok.type != "qualified-rule":
            continue
        prelude = tinycss2.serialize(tok.prelude).strip()
        for d in tinycss2.parse_declaration_list(tok.content):
            if d.type == "declaration" and d.name == "color":
                norm = _norm_hex(tinycss2.serialize(d.value).strip())
                if norm and norm not in seen:
                    seen.add(norm)
                    out.append((norm, prelude))
    return out


def _safe_preset_stem(name):
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", (name or "").strip())
    stem = stem.strip().strip(".")
    return stem


def save_preset_file(name, full_css_text, user_dir=None):
    """另存用户预设（纯函数，可单测）；同名覆盖；返回路径。空名抛 ValueError。"""
    from pycbeta.theme import user_presets_dir
    stem = _safe_preset_stem(name)
    if not stem:
        raise ValueError("预设名为空")
    user_dir = os.path.abspath(user_dir or user_presets_dir())
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, stem + ".css")
    with open(path, "w", encoding="utf-8") as f:
        f.write(full_css_text)
    return path


def delete_preset_file(path, builtin_dir=None, user_dir=None):
    """删除用户预设；内置目录/目录外/不存在抛 ValueError（内置删不掉）。"""
    from pycbeta.theme import BUILTIN_PRESETS_DIR, user_presets_dir
    builtin_dir = os.path.abspath(builtin_dir or BUILTIN_PRESETS_DIR)
    user_dir = os.path.abspath(user_dir or user_presets_dir())
    ap = os.path.abspath(path or "")
    if not ap.lower().endswith(".css") or not os.path.isfile(ap):
        raise ValueError(f"预设不存在：{path}")
    if ap == builtin_dir or ap.startswith(builtin_dir + os.sep):
        raise ValueError("内置预设受保护，删不掉")
    if not (ap == user_dir or ap.startswith(user_dir + os.sep)):
        raise ValueError(f"不在预设目录内：{path}")
    os.remove(ap)
    return True


def strip_factory_prefix(text, factory=None):
    """预设全文 → 覆盖块部分（去掉出厂原文前缀；无前缀则原文）。"""
    factory = factory if factory is not None else factory_css_text()
    if (text or "").startswith(factory):
        return text[len(factory):].lstrip("\n")
    return text or ""


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


_FONT_PROPS = ("font-family", "font-size", "font-weight", "color")
_GEN_MARK = "可视化编辑器生成"
_GEN_HEADER = "/* 可视化编辑器生成：只覆盖字体四属性，后定义优先 */"
_EDITABLE_SET = frozenset(sel for sel, _label in EDITABLE_ROWS)


def _norm_sel(tag):
    """标签 → 规范可调选择器（EDITABLE_ROWS 成员）；落空返回 ""。"""
    from pycbeta.theme import TAG_SELECTOR, _SELECTOR_TAGS
    sel = (TAG_SELECTOR.get(tag) or "").split(",")[0].strip()
    if sel in _EDITABLE_SET:
        return sel
    for key, val in _SELECTOR_TAGS.items():
        if val == tag and key in _EDITABLE_SET:
            return key
    return ""


def _canonical_editable(prelude):
    """规则前奏 → 规范可调选择器|None。

    逗号分组每段都须落到 EDITABLE_ROWS（直接成员或经 _SELECTOR_TAGS 映射后
    规范形）；属性选择器（如 level）、三段以上落空 → None（原文透传）。
    """
    from pycbeta.theme import _SELECTOR_TAGS
    canon = []
    for part in (prelude or "").split(","):
        p = " ".join(part.split())
        if not p:
            continue
        if p in _EDITABLE_SET:
            canon.append(p)
            continue
        tag = _SELECTOR_TAGS.get(p)
        norm = _norm_sel(tag) if tag else ""
        if norm:
            canon.append(norm)
            continue
        return None
    return canon[0] if canon else None


def build_override_block(values, passthrough=""):
    """({selector: props}, 透传原文) → 覆盖块文本。

    只含字体四属性；空值跳过，无值行不输出（EDITABLE_ROWS 顺序）；
    控件不认识的规则原文缀尾（改控件不丢失）。
    """
    out = [_GEN_HEADER]
    order = [sel for sel, _label in EDITABLE_ROWS]
    for sel in order + [s for s in values if s not in order]:
        props = values.get(sel) or {}
        if sel == ":root" or sel == _HANS_BLOCK:
            decls = [f"{k}: {props[k]}" for k in props
                     if k.startswith("--font-") and props[k]]
        else:
            decls = [f"{k}: {props[k]}" for k in _FONT_PROPS if props.get(k)]
        if decls:
            out.append(f"{sel} {{ {'; '.join(decls)}; }}")
    if (passthrough or "").strip():
        out.append(passthrough.rstrip())
    return "\n".join(out) + "\n"


def split_override_block(text):
    """覆盖块文本 → (values, passthrough, 错误|None)。

    可调选择器的字体四属性进 values；其余规则（含注释、@规则、非字体声明）
    原文进 passthrough；tinycss2 错误 token 报红，不抛异常。
    """
    import tinycss2
    values, extras, errs = {}, [], []
    try:
        tokens = tinycss2.parse_stylesheet(text or "", skip_comments=False,
                                           skip_whitespace=False)
    except Exception as exc:  # noqa: BLE001 —— 非法输入只红字
        return {}, text or "", str(exc)

    def flush_comments(buf):
        keep = [c for c in buf if _GEN_MARK not in c]
        del buf[:]
        return keep

    pending = []
    _hans_re = re.compile(r'^html\[lang=(["\']?)zh-Hans\1\]$')
    for tok in tokens:
        if tok.type == "comment":
            pending.append(tinycss2.serialize([tok]))
            continue
        if tok.type == "whitespace":
            continue
        if tok.type == "error":
            errs.append(str(getattr(tok, "message", tok)))
            continue
        if tok.type == "at-rule":
            extras.extend(flush_comments(pending))
            extras.append(tinycss2.serialize([tok]).strip())
            continue
        if tok.type != "qualified-rule":
            continue
        prelude = tinycss2.serialize(tok.prelude).strip()
        var_key = ":root" if prelude == ":root" else (
            _HANS_BLOCK if _hans_re.match(prelude) else None)
        if var_key is not None:
            # 字体变量块：只收 --font-*，其余声明原文透传
            vkeep, vrest = {}, []
            for d in tinycss2.parse_declaration_list(tok.content):
                if d.type == "error":
                    errs.append(str(getattr(d, "message", d)))
                elif d.type == "declaration":
                    val = tinycss2.serialize(d.value).strip()
                    if d.name.startswith("--font-"):
                        if val:
                            vkeep[d.name] = val
                    else:
                        vrest.append(f"{d.name}: {val}"
                                     + (" !important" if d.important else ""))
            if vkeep:
                values.setdefault(var_key, {}).update(vkeep)
            if vrest:
                extras.extend(flush_comments(pending))
                extras.append(f"{prelude} {{ {'; '.join(vrest)}; }}")
            else:
                extras.extend(flush_comments(pending))
            continue
        canon = _canonical_editable(prelude)
        if canon is None:
            extras.extend(flush_comments(pending))
            extras.append(tinycss2.serialize([tok]).strip())
            continue
        keep, rest = {}, []
        for d in tinycss2.parse_declaration_list(tok.content):
            if d.type == "error":
                errs.append(str(getattr(d, "message", d)))
            elif d.type == "declaration":
                val = tinycss2.serialize(d.value).strip()
                if d.name in _FONT_PROPS:
                    if val:
                        keep[d.name] = val
                else:
                    rest.append(f"{d.name}: {val}"
                                + (" !important" if d.important else ""))
        if keep:
            values.setdefault(canon, {}).update(keep)
        if rest:
            extras.extend(flush_comments(pending))
            extras.append(f"{prelude} {{ {'; '.join(rest)}; }}")
        else:
            extras.extend(flush_comments(pending))
    extras.extend(flush_comments(pending))
    err = "; ".join(errs[:3]) if errs else None
    passthrough = "\n".join(e for e in extras if e and e.strip())
    if passthrough:
        passthrough += "\n"
    return values, passthrough, err


def parse_override_block(text):
    """覆盖块文本 → ({selector: props}, 错误信息|None)。透传部分丢弃（预览/旧调用用）。"""
    values, _passthrough, err = split_override_block(text)
    return values, err


# ---------------- DOCX 回读 → 预览规格（纯函数，可单测） ----------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(tag):
    return f"{{{_W_NS}}}{tag}"


def _a(el, name):
    """OOXML 属性取值（w: 命名空间限定，如 w:val/w:id）。"""
    return el.get(f"{{{_W_NS}}}{name}") if el is not None else None


def _para_line(p):
    """段落行距 → {"line": int, "rule": str} | None（Word w:spacing，240=单倍）。"""
    ppr = p.find(_w("pPr"))
    if ppr is None:
        return None
    sp = ppr.find(_w("spacing"))
    if sp is None:
        return None
    try:
        line = int(_a(sp, "line") or "")
    except (TypeError, ValueError):
        return None
    return {"line": line, "rule": _a(sp, "lineRule") or "auto"}


def _style_lines(styles_root):
    """styles.xml → {styleId: line}（无行距的不收；Normal 照收，供无样式段落回退）。"""
    out = {}
    if styles_root is None:
        return out
    for st in styles_root.findall(_w("style")):
        sid = _a(st, "styleId")
        line = _para_line(st)  # style 下同样是 w:pPr/w:spacing 结构
        if sid and line:
            out[sid] = line
    return out


def _run_text(run):
    return "".join(t.text or "" for t in run.iter(_w("t")))


def _para_margin(p):
    """段落上下边距 → {"before": twips, "after": twips}（缺项为 None）| None。"""
    ppr = p.find(_w("pPr"))
    if ppr is None:
        return None
    sp = ppr.find(_w("spacing"))
    if sp is None:
        return None
    out = {}
    for key in ("before", "after"):
        try:
            out[key] = int(_a(sp, key) or "")
        except (TypeError, ValueError):
            out[key] = None
    if out["before"] is None and out["after"] is None:
        return None
    return out


def _style_margins(styles_root):
    """styles.xml → {styleId: {"before","after"}}（供无行内边距段落回退，与 Word 一致）。"""
    out = {}
    if styles_root is None:
        return out
    for st in styles_root.findall(_w("style")):
        sid = _a(st, "styleId")
        if not sid:
            continue
        ppr = st.find(_w("pPr"))
        sp = ppr.find(_w("spacing")) if ppr is not None else None
        if sp is None:
            continue
        m = {}
        for key in ("before", "after"):
            try:
                m[key] = int(_a(sp, key) or "")
            except (TypeError, ValueError):
                m[key] = None
        if m["before"] is not None or m["after"] is not None:
            out[sid] = m
    return out


def _block_margins(fmt, margin):
    """QTextBlockFormat 上下边距：twips→px（96dpi 下 /15），与 Word 同值真实显示。"""
    if not margin:
        return
    if margin.get("before") is not None:
        fmt.setTopMargin(margin["before"] / 15.0)
    if margin.get("after") is not None:
        fmt.setBottomMargin(margin["after"] / 15.0)


def _block_line_height(fmt, line):
    """QTextBlockFormat 行距：auto→百分比（240=单倍），exact→固定磅，atLeast→最小磅。"""
    from PySide6.QtGui import QTextBlockFormat as _BF
    if not line:
        return
    rule, val = line.get("rule", "auto"), line.get("line", 0)
    if rule == "auto" and val > 0:
        fmt.setLineHeight(val / 2.4,
                          _BF.LineHeightTypes.ProportionalHeight.value)
    elif rule == "exact" and val > 0:
        fmt.setLineHeight(val / 20.0, _BF.LineHeightTypes.FixedHeight.value)
    elif rule == "atLeast" and val > 0:
        fmt.setLineHeight(val / 20.0, _BF.LineHeightTypes.MinimumHeight.value)


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


def _para_style(p):
    """段落命名样式Id（无则 ""）。"""
    ppr = p.find(_w("pPr"))
    if ppr is None:
        return ""
    ps = ppr.find(_w("pStyle"))
    return _a(ps, "val") or "" if ps is not None else ""


# 预览元素名标注：段落样式 → 左栏控件名（style 为空按正文）。
STYLE_ROW_LABEL = {"title": "书名", "head": "标题", "juan": "卷名",
                   "pin": "品名", "p": "正文", "verse": "偈颂",
                   "footnote": "脚注", "byline": "题署", "author": "作者",
                   "translator": "译者", "div-note": "字义", "": "正文"}


def div_note_color(css_text):
    """工作 CSS 里 div.div-note 的颜色（小写 #hex；无则 ""）。

    div 是祖先上下文，DOCX 不保留结构——预览用 run 颜色反推字义段
    （纯函数，可单测；后定义优先，取最后一个匹配）。
    """
    found = re.findall(
        r"div\.div-note\s*\{[^}]*?color\s*:\s*"
        r"(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)", css_text or "")
    last = (found or [""])[-1].strip().lower()
    return last if last.startswith("#") else ""


def _name_label_format():
    """元素名标签块格式：橙底（#cc6600）白字粗体（正文/脚注两处共用）。"""
    ncf = QTextCharFormat()
    ncf.setFontPointSize(8)
    ncf.setFontWeight(QFont.Bold)
    ncf.setForeground(QColor("#ffffff"))
    ncf.setBackground(QColor("#cc6600"))
    return ncf


def _para_runs(p, fn_id_to_num):
    """段落 → [run规格]；ruby/EQ 展开为 原文+灰小字〔读音〕；脚注引用取编号；
    w:br 记 {"br": True}（显示时换块，偈颂/预排分行用）。"""
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
        if run.find(_w("br")) is not None and not _run_text(run).strip():
            runs.append({"br": True})
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
    return [r for r in runs if r.get("br") or r.get("text")]


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
        st_root = (etree.fromstring(z.read("word/styles.xml"))
                   if "word/styles.xml" in names else None)
    style_lines = _style_lines(st_root)
    style_margins = _style_margins(st_root)
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
            fn_line = None
            fn_margin = None
            for p in fn.findall(_w("p")):
                if fn_line is None:
                    st = _para_style(p)
                    fn_line = _para_line(p) or style_lines.get(st) \
                        or style_lines.get("Normal")
                    fn_margin = _para_margin(p) or style_margins.get(st) \
                        or style_margins.get("Normal")
                runs.extend(_para_runs(p, {}))
            fn_bodies[num] = (runs, fn_line, fn_margin)
    for p in doc.iter(_w("p")):
        style = _para_style(p)
        align = _PSTYLE_ALIGN.get(style, "")
        if not align:
            ppr = p.find(_w("pPr"))
            if ppr is not None:
                jc = ppr.find(_w("jc"))
                if jc is not None:
                    align = {"center": "center", "right": "right",
                             "both": "justify"}.get(_a(jc, "val") or "", "")
        runs = _para_runs(p, fn_id_to_num)
        if runs:
            line = _para_line(p) or style_lines.get(style) \
                or style_lines.get("Normal")
            margin = _para_margin(p) or style_margins.get(style) \
                or style_margins.get("Normal")
            spec["paras"].append({"style": style, "align": align,
                                  "line": line, "margin": margin,
                                  "runs": runs})
    for num in sorted(fn_bodies):
        if fn_bodies[num][0]:
            spec["footnotes"].append({"num": num, "runs": fn_bodies[num][0],
                                      "line": fn_bodies[num][1],
                                      "margin": fn_bodies[num][2]})
    return spec


# 预览回退链：Qt 认不出请求字体（如本机未安装/未注册）时逐个顺延，
# 保证中文可读（SimSun/宋体系统必带）而非掉到默认西文字体。
PREVIEW_FALLBACKS = ("SimSun", "宋体", "Microsoft YaHei", "sans-serif")

_qt_alias_cache = None


def build_qt_aliases(rows, qt_families):
    """字体文件别名 → Qt 可认名（纯函数，可单测）。

    rows: [[同一文件的全部家族名]]；qt_families: QFontDatabase.families()。
    实测 Qt(DirectWrite) 常缺中文本地化名（如"朝华标题B"不认、"ZhaohuaMinB"认），
    用同文件英文名 bridging；找不到的保持缺失（警告用）。
    """
    have = set(qt_families or [])
    low = {h.lower(): h for h in have}
    mapping = {}
    for names in rows or []:
        names = [n for n in (names or []) if n]
        if not names:
            continue
        hit = next((n for n in names if n in have), None)
        if hit is None:
            hit = next((low[n.lower()] for n in names if n.lower() in low),
                       None)
        if hit:
            for n in names:
                mapping.setdefault(n, hit)
    return mapping


def qt_aliases():
    """本机别名表（进程级缓存；刷新字体列表后失效重建）。"""
    global _qt_alias_cache
    if _qt_alias_cache is None:
        try:
            from PySide6.QtGui import QFontDatabase
            from pycbeta.fonts import locator, iter_installed
            rows = [names for _p, names, _path in
                    iter_installed(locator())]
            _qt_alias_cache = build_qt_aliases(
                rows, QFontDatabase.families())
        except Exception:  # noqa: BLE001
            _qt_alias_cache = {}
    return _qt_alias_cache


def clear_qt_alias_cache():
    global _qt_alias_cache
    _qt_alias_cache = None


def resolve_qt_family(name, aliases=None):
    """请求字体名 → Qt 可认名；认不出返回 ""（警告用）。"""
    if not name:
        return ""
    mapping = aliases if aliases is not None else qt_aliases()
    if name in mapping:
        return mapping[name]
    low = name.lower()
    for k, v in mapping.items():
        if k.lower() == low:
            return v
    return ""


def preview_families(requested):
    """预览字体栈：请求字体（调用方已做 Qt 别名解析）+ 回退链（去重保序）。

    纯函数；Qt 按序取首个可用。
    """
    out = []
    for name in ([requested] if requested else []) + list(PREVIEW_FALLBACKS):
        if name and name not in out:
            out.append(name)
    return out


def missing_families(used, available):
    """used 中 Qt 字体库没有的 → 保序去重列表（状态行警告用）。大小写不敏感。"""
    have = {a.lower() for a in (available or [])}
    out = []
    for name in used or []:
        if name and name.lower() not in have and name not in out:
            out.append(name)
    return out


def factory_font_stacks():
    """出厂 :root 双栏 --font-* 栈去重（保序；纯函数，可单测）→ [栈]。

    左栏下拉"常用栈"选项来源；显示短名、值存完整栈，选不回问题不再有。
    --font-body（无左栏行）与 --font-latin（纯西文）不进 CJK 下拉。
    """
    stacks = []
    for m in re.finditer(
            r'(html\[lang=["\']zh-Hans["\']\]|:root)\s*\{([^}]*)\}',
            factory_css_text(), re.S):
        for vm in re.finditer(r'(--font-[\w-]+)\s*:\s*([^;{}]+);',
                               m.group(2)):
            if vm.group(1) in ("--font-body", "--font-latin"):
                continue
            stack = vm.group(2).strip()
            if stack and stack not in stacks:
                stacks.append(stack)
    return stacks


def stack_display_names(stacks):
    """[栈] → [(显示名, 栈)]：显示名取首段名；首段冲突用全栈（防选错）。"""
    firsts = {}
    for s in stacks or []:
        first = s.split(",")[0].strip().strip('"').strip("'")
        firsts.setdefault(first, []).append(s)
    out = []
    for s in stacks or []:
        first = s.split(",")[0].strip().strip('"').strip("'")
        out.append((first if len(firsts[first]) == 1 else s, s))
    return out


def _spec_fonts(spec):
    """预览规格用到的全部字体名（正文+注文，保序去重）。"""
    out = []
    for para in (spec.get("paras") or []) + [
            {"runs": fn.get("runs", [])} for fn in spec.get("footnotes", [])]:
        for r in para.get("runs", []):
            if r.get("font") and r["font"] not in out:
                out.append(r["font"])
    return out


def glyph_gaps(spec, path_of=None):
    """{字体: [缺字形码位...]}：各 run 实际字符查字体文件 cmap。

    Word 与预览同一结论（都没字形就是真 tofu）。path_of(font) 可注入
    （单测）；默认走 fonts.locator()；找不到文件跳过（Qt 缺字体警告另报）。
    """
    if path_of is None:
        from pycbeta.fonts import font_cmap, locator
        _loc = locator()
        path_of = _loc.path
    else:
        from pycbeta.fonts import font_cmap
    chars = {}
    for para in (spec.get("paras") or []) + [
            {"runs": fn.get("runs", [])} for fn in spec.get("footnotes", [])]:
        for r in para.get("runs", []):
            if r.get("font") and r.get("text"):
                chars.setdefault(r["font"], set()).update(r["text"])
    gaps = {}
    for font, chs in chars.items():
        try:
            path = path_of(font)
        except Exception:  # noqa: BLE001
            continue
        if not path:
            continue
        try:
            cmap = font_cmap(path)
        except Exception:  # noqa: BLE001 —— 读坏不断预览
            continue
        missing = sorted({c for c in chs if ord(c) not in cmap})
        if missing:
            gaps[font] = missing
    return gaps


def _gaps_text(gaps, limit=6):
    """缺字形摘要行（状态行/检查窗共用）：字体缺N字形（如U+10CCEB…）。"""
    bits = []
    for font, chs in gaps.items():
        shown = "、".join(f"U+{ord(c):04X}" for c in chs[:3])
        more = f"等{len(chs)}个" if len(chs) > 3 else ""
        bits.append(f"{font}缺字形{shown}{more}")
    out = "；".join(bits[:limit])
    if len(bits) > limit:
        out += f"；等{len(bits)}种字体"
    return out


_CJK_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")


def check_font_stacks(css_text, aliases=None, qt_families=None,
                      western=None, bundled=None):
    """字体栈检查（纯函数，可单测）→ [(栏, 变量, 栈, 级别, 说明)]。

    查有效 CSS 双栏全部 --font-*（--font-latin 豁免，本就纯西文）：
    名称正确性逐名判定——本机可认/通用族通过；已知但本机未装警告；
    未知（拼写？）/全角逗号/空名报错；整栈缺中文或缺英文回退警告。
    aliases: {别名: Qt可认名}；qt_families: Qt家族名；
    western/bundled: 额外已知名单（缺省西文三；bundled 缺省空——
    已装字体已在 aliases 键里）。
    """
    import re as _re
    aliases = aliases or {}
    low = {f.lower() for f in (qt_families or [])}
    known = set(_KNOWN_FONTS) | set(western or _WESTERN_FONTS) \
        | set(bundled or ()) | set(aliases or {})
    known_low = {k.lower() for k in known}

    def _classify(name):
        n = name.strip().strip('"').strip("'").strip()
        if not n:
            return ("empty", "")
        if n.lower() in _GENERIC_FAMILIES or n.lower() in low:
            return ("ok", n)
        tgt = (aliases or {}).get(n)
        if tgt and tgt.lower() in low:
            return ("ok", n)
        if n in known or n.lower() in known_low:
            return ("warn", n)
        return ("error", n)

    found = {}
    for m in _re.finditer(
            r'(html\[lang=["\']zh-Hans["\']\]|:root)\s*\{([^}]*)\}',
            css_text or "", _re.S):
        lang = "简体" if "zh-Hans" in m.group(1) else "繁体"
        for vm in _re.finditer(r'(--font-[\w-]+)\s*:\s*([^;{}]+);',
                               m.group(2)):
            found[(lang, vm.group(1))] = vm.group(2).strip()
    out = []
    for (lang, var), raw in found.items():
        if var == "--font-latin":
            continue
        if "，" in raw or "、" in raw:
            out.append((lang, var, raw, "error",
                        "含全角逗号/顿号，分隔失效（请用半角逗号）"))
            continue
        parts = [p.strip().strip('"').strip("'").strip()
                 for p in raw.split(",")]
        if any(not p for p in parts):
            out.append((lang, var, raw, "error", "含空字体名（多余逗号？）"))
            continue
        has_cjk = has_asc = False
        for p in parts:
            kind, _n = _classify(p)
            if kind == "error":
                out.append((lang, var, raw, "error",
                            f"{p} 未知（拼写？本机无此字体）"))
            elif kind == "warn":
                out.append((lang, var, raw, "warn",
                            f"{p} 本机未装（跨平台/Word 端可用，预览替代显示）"))
            if _CJK_RE.search(p):
                has_cjk = True
            if p.isascii():
                has_asc = True
        if not has_cjk:
            out.append((lang, var, raw, "warn",
                        "缺中文名（中日韩文字符可能降级显示）"))
        elif not has_asc:
            out.append((lang, var, raw, "warn",
                        "缺英文回退（建议补英文名或 serif，保拉丁/跨平台）"))
    return out


# ---------------- 后台重渲线程 ----------------

class _RenderThread(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, xml_path, css_text, out_dir, lang="zh-Hant",
                 t2s=False, parent=None):
        super().__init__(parent)
        self._xml = xml_path
        self._css = css_text
        self._out = out_dir
        self._lang = lang
        self._t2s = t2s

    def run(self):
        try:
            from pycbeta.parser import P5Parser
            from pycbeta.render_docx import DocxRenderer
            from pycbeta.theme import Theme
            work = P5Parser().parse(self._xml)
            lang = self._lang
            if self._t2s:
                from pycbeta.simplify import simplify_work
                simplify_work(work)
                lang = "zh-Hans"
            theme = Theme.from_css(self._css, lang)
            fn = DocxRenderer(theme=theme, notes="footnote",
                              bookmarks=False).render_work(
                work, self._out, filename="preview.docx")
            self.done.emit(fn if isinstance(fn, str) else fn[0])
        except Exception as exc:  # noqa: BLE001 —— 错误进状态行，不崩界面
            self.failed.emit(str(exc))


# ---------------- 对话框 ----------------

class _ColorPopup(QDialog):
    """颜色两组：上半=工作 CSS 现有色（标注来源元素），下半=自定义取色。"""

    def __init__(self, css_text, current="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择颜色")
        self._selected = ""
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        colors = css_colors(css_text)
        labels = {sel: label for sel, label in EDITABLE_ROWS}
        row, col = 0, 0
        for hexval, src in colors:
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setStyleSheet(f"background-color: {hexval}")
            canon = _canonical_editable(src)
            tip = labels.get(canon, src) if canon else src
            btn.setToolTip(f"{hexval} ← {tip}")
            btn.clicked.connect(lambda _v, h=hexval: self._choose(h))
            grid.addWidget(btn, row, col)
            col += 1
            if col >= 8:
                col, row = 0, row + 1
        if not colors:
            grid.addWidget(QLabel("（工作 CSS 暂无 color，见源码页）"), 0, 0)
        layout.addLayout(grid)
        custom = QPushButton("自定义…")
        custom.clicked.connect(lambda _v: self._custom(current))
        layout.addWidget(custom)

    def _choose(self, hexval):
        self._selected = hexval
        self.accept()

    def _custom(self, current):
        c = QColorDialog.getColor(QColor(current or "#000000"), self, "自定义颜色")
        if c.isValid():
            self._choose(c.name())

    def selected(self):
        return self._selected


class PreviewReportDialog(QDialog):
    """预览检查窗（modeless）：更新信息 + 字体可用性，缺字红色加粗（纠错用）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("预览检查")
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        layout.addWidget(self.view)

    def update_report(self, info):
        import html as _html
        parts = [f"<h3>预览检查（{ _html.escape(info.get('time', '')) }）</h3>"]
        parts.append(f"<p>基于：{_html.escape(info.get('base', ''))}<br>"
                     f"样张：{_html.escape(info.get('sample', ''))}<br>"
                     f"简体：{'开' if info.get('t2s') else '关'}</p>")
        fonts = info.get("fonts") or []
        if fonts:
            rows = []
            for name, ok in fonts:
                if ok:
                    rows.append(f"<li>{_html.escape(name)} ✓</li>")
                else:
                    rows.append(f"<li><b><font color='red'>{_html.escape(name)}"
                                " ✗ 无可用字形（预览替代显示，导出 DOCX 不受影响）"
                                "</font></b></li>")
            parts.append("<p>字体：</p><ul>" + "".join(rows) + "</ul>")
        gaps = info.get("gaps") or {}
        if gaps:
            grows = []
            for font, chs in gaps.items():
                shown = "、".join(f"U+{ord(c):04X}" for c in chs[:8])
                more = f"等{len(chs)}个" if len(chs) > 8 else ""
                grows.append(f"<li><b><font color='red'>{_html.escape(font)}"
                             f"缺字形：{shown}{more}（预览与 Word 均为 tofu）"
                             "</font></b></li>")
            parts.append("<p>缺字形（字库里没有这些字）：</p><ul>" +
                         "".join(grows) + "</ul>")
        if info.get("css_error"):
            parts.append(f"<p><b><font color='red'>CSS 错误："
                         f"{_html.escape(info['css_error'])}</font></b></p>")
        stacks = info.get("stacks") or []
        if stacks:
            srows = []
            for lang, var, stack, level, msg in stacks:
                label = (f"[{_html.escape(lang)}]{_html.escape(var)} = "
                         f"{_html.escape(stack)}：{_html.escape(msg)}")
                if level == "error":
                    srows.append("<li><b><font color='red'>"
                                 f"{label}</font></b></li>")
                else:
                    srows.append("<li><font color='#cc6600'>"
                                 f"{label}</font></li>")
            parts.append("<p>字体栈：</p><ul>" + "".join(srows) + "</ul>")
        if info.get("error"):
            parts.append(f"<p><b><font color='red'>渲染失败："
                         f"{_html.escape(info['error'])}</font></b></p>")
        if not fonts and not info.get("gaps") and not info.get("css_error") \
                and not info.get("error") and not info.get("stacks"):
            parts.append("<p>暂无检查项（等一次预览完成）。</p>")
        self.view.setHtml("".join(parts))


_HANS_BLOCK = 'html[lang="zh-Hans"]'


def _var_suffix(selector):
    """行选择器 → 字体变量后缀（无变量返回 None，供字体双栏用）。"""
    from pycbeta.theme import _SELECTOR_TAGS, FONT_VAR_TAGS, FONT_VAR_COMPOUNDS
    tag = _SELECTOR_TAGS.get(selector)
    if tag and tag in FONT_VAR_TAGS:
        return tag
    bits = (selector or "").split()
    if len(bits) == 2:
        anc = _SELECTOR_TAGS.get(bits[0])
        tgt = _SELECTOR_TAGS.get(bits[1])
        if anc and tgt:
            for suffix, (a, t) in FONT_VAR_COMPOUNDS.items():
                if (a, t) == (anc, tgt):
                    return suffix
    return None


def _suffix_rows():
    """变量后缀 → 行选择器（供 touched 反向映射；惰性构建）。"""
    out = {}
    for sel, _label in EDITABLE_ROWS:
        suffix = _var_suffix(sel)
        if suffix:
            out.setdefault(suffix, sel)
    return out


def current_theme_value(root=None):
    """有效默认槽值：用户槽 theme → 出厂 config theme → ''。"""
    import json
    from pycbeta.theme import load_presets
    root = root or REPO_ROOT
    try:
        with open(os.path.join(root, "config.user.json"), encoding="utf-8") as f:
            v = (json.load(f) or {}).get("theme", "")
        if isinstance(v, str) and v.strip():
            return v.strip()
    except (OSError, ValueError):
        pass
    try:
        v = load_presets(os.path.join(root, "pycbeta", "config.json")).get(
            "theme", "")
        if isinstance(v, str):
            return v.strip()
    except (OSError, ValueError):
        pass
    return ""


def set_user_theme(value, root=None):
    """用户槽 theme 键写入（只改此键；无用户槽时按出厂全量建）。返回用户槽路径。"""
    import json
    from pycbeta.theme import load_presets
    root = root or REPO_ROOT
    upath = os.path.join(root, "config.user.json")
    if os.path.isfile(upath):
        try:
            with open(upath, encoding="utf-8") as f:
                data = json.load(f) or {}
            if not isinstance(data, dict):
                data = {}
        except ValueError:
            bad = upath + ".bad"
            try:
                os.replace(upath, bad)
            except OSError:
                pass
            data = {}
    else:
        data = dict(load_presets(os.path.join(root, "pycbeta", "config.json")))
    data["theme"] = value
    with open(upath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return upath


class CssComboBox(QComboBox):
    """CSS 变种下拉（面板样式表卡 + 编辑器预设行共用）。

    顺序：当前默认（（默认））→ 出厂组 → 用户组；itemData={"value","path"}。
    选中只选择不写默认；设默认走独立按钮（set_user_theme）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.refresh("")

    def refresh(self, current=""):
        from pycbeta.theme import list_presets
        cur = (current or "").strip() or "pdf_docx.css"
        items = list_presets()
        builtin_css = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "styles",
            "pdf_docx.css"))

        def entry(value, path, label):
            return (value, path, label)

        def find_current():
            if cur == "pdf_docx.css":
                return ("pdf_docx.css", builtin_css)
            stem = cur[:-4] if cur.lower().endswith(".css") else cur
            for _k, n, p in items:
                if n == stem or n.lower() == stem.lower():
                    return (n, p)
            if os.path.isfile(cur):
                return (cur, os.path.abspath(cur))
            return None

        found = find_current()
        rows = []  # (value, path, label, header?)

        def label_of(value, path):
            for k, n, p in items:
                if p == path:
                    return f"［{'内置' if k == 'builtin' else '用户'}］{n}"
            return "出厂默认（pdf_docx.css）"

        if found:
            value, path = found
            rows.append((value, path, f"（默认）{label_of(value, path)}",
                         False))
        else:
            rows.append((cur, None, f"（默认）{cur}（找不到）", False))
        rows.append((None, None, "── 出厂 ──", True))
        rows.append(("pdf_docx.css", builtin_css, "出厂默认（pdf_docx.css）",
                     False))
        for k, n, p in items:
            if k == "builtin" and (not found or p != found[1]):
                rows.append((n, p, f"［内置］{n}", False))
        rows.append((None, None, "── 用户 ──", True))
        for k, n, p in items:
            if k == "user" and (not found or p != found[1]):
                rows.append((n, p, f"［用户］{n}", False))

        with QSignalBlocker(self):
            self.clear()
            for value, path, label, header in rows:
                if header:
                    self.addItem(label, None)
                    self.model().item(self.count() - 1).setEnabled(False)
                else:
                    self.addItem(label, {"value": value, "path": path})
            self.setCurrentIndex(0)

    def selected_value(self):
        d = self.currentData() or {}
        return d.get("value", "pdf_docx.css")

    def selected_path(self):
        d = self.currentData() or {}
        return d.get("path")

    def select_path(self, path):
        """按文件路径选中（另存后定位用）；找不到回首项。"""
        from PySide6.QtCore import QSignalBlocker
        if not path:
            return
        target = os.path.abspath(path)
        with QSignalBlocker(self):
            for i in range(self.count()):
                d = self.itemData(i) or {}
                if d.get("path") and os.path.abspath(d["path"]) == target:
                    self.setCurrentIndex(i)
                    return
            self.setCurrentIndex(0)


def _touched_from_values(values):
    """values → touched 集合（含字体 lang 维）。"""
    rev = _suffix_rows()
    touched = set()
    for s, props in (values or {}).items():
        if s == ":root" or s == _HANS_BLOCK:
            lang = "zh-Hans" if s == _HANS_BLOCK else "zh-Hant"
            for var in props:
                if var.startswith("--font-"):
                    row = rev.get(var[7:])
                    if row:
                        touched.add((row, "font-family", lang))
        else:
            for p in props:
                touched.add((s, p))
    return touched


class CssEditorDialog(QDialog):
    """所见即所得样式编辑器：左调参 / 右预览 / 底导出。"""

    def __init__(self, sample_xml=None, engine_chain=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSS 编辑器（DOCX 所见即所得）")
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowMaximizeButtonHint)
        self.resize(1180, 760)
        self._engine_chain = engine_chain
        self._tmp = tempfile.mkdtemp(prefix="css-editor-")
        self._work = None            # 当前解析后 Work（样张缓存）
        self._work_src = ("", 0)     # (path, mtime)
        self._last_docx = ""         # 最近一次重渲产物（导出用）
        self._last_good_css = ""     # 最近一次可预览的工作 CSS
        self._need_refresh = False   # 渲染中又有改动时补一轮
        self._passthrough = ""       # 覆盖块中控件不认识的规则原文
        self._touched = set()        # 用户碰过的 (selector, prop)；只输出这些
        self._status_linked = False    # 状态行 linkActivated 是否已连接
        self._preset_path = None       # 当前缓冲对应的预设文件（保存目标）；出厂/新建为 None
        self._report = None            # 预览检查信息（_push_report 更新）
        self._last_gaps = {}             # 字形覆盖缺口 {字体: [码位]}（纠错用）
        self._last_stacks = []           # 字体栈检查 [(栏, 变量, 栈, 级别, 说明)]
        self._report_dlg = None          # 检查窗（打开检查时懒建）
        self._thread = None
        self._rows = {}              # selector -> 控件组
        self._build(sample_xml or default_sample())

    # ----- 构造 -----
    def _build(self, sample):
        layout = QVBoxLayout(self)
        # 预设行（下拉仅载入；设默认走独立按钮）
        prow = QHBoxLayout()
        prow.addWidget(QLabel("预设"))
        self.preset_box = CssComboBox()
        self.preset_box.activated.connect(self._on_preset_chosen)
        self.preset_apply = QPushButton("设为默认")
        self.preset_apply.setToolTip("选中项写入用户槽 theme（永久生效）")
        self.preset_apply.clicked.connect(self._apply_default)
        self.preset_save = QPushButton("另存为预设…")
        self.preset_save.setToolTip("当前样式另存进用户预设库（css-presets/）")
        self.preset_save.clicked.connect(self._save_preset_as)
        self.preset_del = QPushButton("删除预设")
        self.preset_del.setToolTip("只删用户预设；内置预设受保护")
        self.preset_del.clicked.connect(self._delete_preset)
        prow.addWidget(self.preset_box, 1)
        prow.addWidget(self.preset_apply)
        prow.addWidget(self.preset_save)
        prow.addWidget(self.preset_del)
        layout.addLayout(prow)
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
        trow = QHBoxLayout()
        self.t2s_box = QCheckBox("繁转简")
        self.t2s_box.setToolTip("OpenCC t2s 简体预览/导出（自动用简体字库）")
        self.t2s_box.toggled.connect(lambda _v: self._on_t2s_toggled())
        trow.addWidget(self.t2s_box)
        trow.addWidget(QLabel("预览字库"))
        self.preview_lang = QComboBox()
        self.preview_lang.addItem("繁体", "zh-Hant")
        self.preview_lang.addItem("简体", "zh-Hans")
        self.preview_lang.setToolTip("切换 CSS :root 双栏变量列（样张文字不变，只看字体）")
        self.preview_lang.currentIndexChanged.connect(lambda _i: self._schedule())
        trow.addWidget(self.preview_lang)
        self.names_box = QCheckBox("元素名")
        self.names_box.setToolTip("每段前标注对应左栏控件名（如【标题】），方便找修改位置")
        self.names_box.toggled.connect(lambda _v: self._on_names_toggled())
        trow.addWidget(self.names_box)
        rl.addLayout(trow)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        rl.addWidget(self.preview, 1)
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color: gray")
        rl.addWidget(self.status)
        self.sim_tip = QLabel("预览为模拟显示（字体四参数为真值），分页/页边距以 Word 为准")
        self.sim_tip.setStyleSheet("color: gray")
        self.sim_tip.setWordWrap(True)
        rl.addWidget(self.sim_tip)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        # 底栏
        brow = QHBoxLayout()
        self.btn_docx = QPushButton("保存DOCX")
        self.btn_pdf = QPushButton("导出PDF")
        self.btn_save = QPushButton("保存")
        self.btn_save.setToolTip("保存当前修改到选中的预设文件（出厂默认则走另存）")
        self.btn_restore = QPushButton("恢复")
        self.btn_restore.setToolTip("回到载入时的状态（未修改前）；不碰预设选择与默认设置")
        self.btn_docx.clicked.connect(self._export_docx)
        self.btn_pdf.clicked.connect(self._export_pdf)
        self.btn_save.clicked.connect(lambda _v: self._save_current())
        self.btn_restore.clicked.connect(lambda _v: self._restore_loaded())
        for b in (self.btn_save, self.btn_restore, self.btn_docx, self.btn_pdf):
            brow.addWidget(b)
        brow.addStretch(1)
        layout.addLayout(brow)
        # 防抖重渲
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.refresh_preview)
        # 初始值：有效默认 CSS；控件预填（不算 touched，源码块保持空）
        self._base_css, self._base_label = self._effective_base_css()
        self._passthrough = ""
        self._touched = set()
        self._loaded_block = ""
        self._source_edit.setPlaceholderText("在此追加/覆盖规则；解析失败红字且预览保持上次")
        base_values, _, _ = split_override_block(self._base_css)
        self._base_values = base_values
        self._sync_controls_from_block(base_values)
        self.preset_box.refresh(current_theme_value())
        self.status.setText(f"基于：{self._base_label}")
        self.refresh_preview()

    def _effective_base_css(self):
        """有效默认 CSS → (全文, 说明)：出厂 + theme 文件（层叠，后者胜）。

        预设只存覆盖块，不存出厂快照——出厂进化（行距/边距修复）自动跟随，
        不会像旧全快照那样腐烂（2026-09-06 字義边距实锤）。"""
        from pycbeta.theme import resolve_theme_css, theme_file_text
        factory = factory_css_text()
        path, label = resolve_theme_css(current_theme_value())
        if path:
            try:
                return (theme_file_text(path, factory),
                        f"{label}：{os.path.basename(path)}")
            except OSError:
                pass
        return factory, "内置出厂"

    # ----- 预设库 -----
    def _display_values(self, values):
        """控件显示用有效值：base + 覆盖块层叠（后者胜）。
        touched 仍只记覆盖块自有——显示继承值、保存只写自有（与打开时一致）。"""
        merged = {s: dict(p) for s, p in
                  (getattr(self, "_base_values", None) or {}).items()}
        for s, props in (values or {}).items():
            merged.setdefault(s, {}).update(props)
        return merged

    def _load_block_text(self, block_text):
        """覆盖块文本装载进编辑器（源码页+控件+touched 联动）；返回 True/False。"""
        values, passthrough, err = split_override_block(block_text or "")
        if err:
            self._source_err.setText(f"CSS 解析失败（预览保持上次）：{err}")
            return False
        self._source_err.setText("")
        with QSignalBlocker(self._source_edit):
            self._source_edit.setPlainText(
                build_override_block(values, passthrough))
        self._passthrough = passthrough
        self._touched = _touched_from_values(values)
        self._loaded_block = self._source_edit.toPlainText()
        self._sync_controls_from_block(self._display_values(values))
        self._schedule()
        return True

    def _load_preset_path(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            QMessageBox.warning(self, "载入失败", str(exc))
            return
        if self._load_block_text(strip_factory_prefix(text)):
            self._preset_path = path

    def _on_preset_chosen(self, _index):
        if not self._confirm_discard():
            self.preset_box.refresh(current_theme_value())
            if self._preset_path:
                self.preset_box.select_path(self._preset_path)
            return
        value = self.preset_box.selected_value()
        path = self.preset_box.selected_path()
        if value == "pdf_docx.css" or not path:
            self._reset_editor_state()
            return
        self._load_preset_path(path)

    def _is_dirty(self):
        return self._source_edit.toPlainText() != (self._loaded_block or "")

    def _apply_default(self):
        """选中项设为默认（写用户槽 theme；未保存修改不在内）。"""
        value = self.preset_box.selected_value()
        try:
            set_user_theme(value)
        except OSError as exc:
            QMessageBox.warning(self, "设为默认失败", str(exc))
            return
        self.preset_box.refresh(value)
        msg = f"已设默认：{value}"
        if self._is_dirty():
            msg += "（当前未保存修改不在内，请先另存）"
        self.status.setText(msg)

    def _restore_loaded(self):
        """恢复到载入时的状态（未修改前）：源码页回到 _loaded_block，控件联动；
        base/预设选择/默认设置都不动。返回是否已恢复（无修改也返回 True）。"""
        if not self._is_dirty():
            return True
        with QSignalBlocker(self._source_edit):
            self._source_edit.setPlainText(self._loaded_block or "")
        self._source_err.setText("")
        values, passthrough, err = split_override_block(
            self._loaded_block or "")
        if err:
            self._source_err.setText(f"CSS 解析失败（预览保持上次）：{err}")
            return False
        self._passthrough = passthrough
        self._touched = _touched_from_values(values)
        self._sync_controls_from_block(self._display_values(values))
        self._schedule()
        return True

    def _reset_editor_state(self):
        """回到出厂缓冲（只装载出厂文本；不删预设、不改默认）。"""
        if not self._confirm_discard():
            return
        self._base_css = factory_css_text()
        self._preset_path = None
        self._passthrough = ""
        self._touched = set()
        with QSignalBlocker(self._source_edit):
            self._source_edit.setPlainText("")
        self._loaded_block = ""
        self._source_err.setText("")
        factory_values, _, _ = split_override_block(self._base_css)
        self._base_values = factory_values
        self._sync_controls_from_block(factory_values)
        self.preset_box.refresh("pdf_docx.css")
        self.status.setText("基于：内置出厂")
        self.refresh_preview()

    def _save_preset_as(self):
        """另存为预设：只存编辑块（源码页文本），不存出厂快照。

        预设 = 覆盖块；加载时出厂 + 覆盖合并，出厂进化自动跟随。"""
        from PySide6.QtWidgets import QInputDialog
        if self._source_err.text().strip():
            QMessageBox.warning(self, "另存失败", "源码页有解析错误，先修好再存。")
            return
        name, ok = QInputDialog.getText(self, "另存为预设", "预设名（存进用户库 css-presets/）：")
        if not ok:
            return
        try:
            path = save_preset_file(name, self._source_edit.toPlainText())
        except ValueError as exc:
            QMessageBox.warning(self, "另存失败", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "另存失败", str(exc))
            return
        self.preset_box.refresh(current_theme_value())
        self.preset_box.select_path(path)
        self._preset_path = path
        self._loaded_block = self._source_edit.toPlainText()
        self.status.setText(f"预设已存：{path}")

    def _save_current(self):
        """保存当前修改：有预设文件则直接写回；出厂默认/新建则走另存。返回是否已保存。"""
        if self._source_err.text().strip():
            QMessageBox.warning(self, "保存失败", "源码页有解析错误，先修好再存。")
            return False
        if not self._preset_path:
            self._save_preset_as()
            return not self._is_dirty()
        try:
            with open(self._preset_path, "w", encoding="utf-8") as f:
                f.write(self._source_edit.toPlainText())
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False
        self._loaded_block = self._source_edit.toPlainText()
        self.status.setText(f"已保存：{self._preset_path}")
        return True

    def _ask_save_discard_cancel(self):
        """未保存修改的三选一（纯交互，可单测 mock）；返回 save/discard/cancel。

        注意：全自定义按钮时 result() 不可靠，必须直接比对 clickedButton；
        点 X（无点击按钮）按取消处理。
        """
        box = QMessageBox(self)
        box.setWindowTitle("未保存的修改")
        box.setText("当前样式有未保存的修改，怎么办？")
        save_btn = box.addButton("保存", QMessageBox.AcceptRole)
        discard_btn = box.addButton("不保存", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == save_btn:
            return "save"
        if clicked == discard_btn:
            return "discard"
        return "cancel"

    def _confirm_discard(self):
        """无修改返回 True；有修改弹三选一。保存失败/取消返回 False。"""
        if not self._is_dirty():
            return True
        choice = self._ask_save_discard_cancel()
        if choice == "discard":
            return True
        if choice == "save":
            return self._save_current()
        return False

    def _delete_preset(self):
        path = self.preset_box.selected_path()
        if not path:
            QMessageBox.information(self, "删除预设", "出厂默认删不掉。")
            return
        try:
            delete_preset_file(path)
        except ValueError as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self.preset_box.refresh(current_theme_value())
        self.status.setText("用户预设已删除")

    def _left_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        # 控件页（29 行，包滚动区）
        cw = QWidget()
        cv = QVBoxLayout(cw)
        cv.setContentsMargins(4, 4, 4, 4)
        frow = QHBoxLayout()
        self.fonts_dir_btn = QPushButton("打开字库目录")
        self.fonts_dir_btn.setToolTip("cbeta/fonts/：拷入 TTF/OTF 后点刷新即用")
        self.fonts_dir_btn.clicked.connect(self._open_fonts_dir)
        self.fonts_refresh_btn = QPushButton("刷新字体列表")
        self.fonts_refresh_btn.setToolTip("重扫系统+字库目录（较慢，按需）")
        self.fonts_refresh_btn.clicked.connect(lambda _v: self._fill_font_combos(True))
        frow.addWidget(self.fonts_dir_btn)
        frow.addWidget(self.fonts_refresh_btn)
        frow.addStretch(1)
        cv.addLayout(frow)
        form = QFormLayout()
        cv.addLayout(form)
        # 列标题行（替代各输入框的占位提示）
        chead = QHBoxLayout()
        for text, stretch, width in (("繁字体", 1, 0), ("简字体", 1, 0),
                                     ("字号", 0, 80), ("粗细", 0, 80),
                                     ("颜色", 0, 64)):
            lab = QLabel(f"<b>{text}</b>")
            lab.setStyleSheet("color: gray")
            if width:
                lab.setFixedWidth(width)
            chead.addWidget(lab, stretch)
        form.addRow("", chead)
        for sel, label in EDITABLE_ROWS:
            row = QHBoxLayout()
            suffix = _var_suffix(sel)
            font_hant = QComboBox()
            font_hant.setEditable(False)  # 只从下拉选（防手打 typo）；特殊栈去源码页
            font_hant.setMinimumWidth(150)
            font_hans = QComboBox()
            font_hans.setEditable(False)
            font_hans.setMinimumWidth(150)
            if suffix is None:
                for _box in (font_hant, font_hans):
                    _box.setEnabled(False)
                    _box.setToolTip("该行无字体变量（只调字号/颜色）")
            else:
                for _box in (font_hant, font_hans):
                    _box.setToolTip("下拉选择字体栈；特殊栈去源码页手写")
            size_edit = QLineEdit()
            size_edit.setFixedWidth(80)
            weight = QComboBox()
            for wlabel, data in WEIGHT_ITEMS:
                weight.addItem(wlabel, data)
            weight.setFixedWidth(80)
            color_btn = QPushButton("颜色")
            color_btn.setFixedWidth(64)
            color_btn.clicked.connect(
                lambda _v, s=sel: self._pick_color(s))
            color_btn.setToolTip("CSS 现有颜色 / 自定义取色；右键清除")
            color_btn.setContextMenuPolicy(Qt.CustomContextMenu)
            color_btn.customContextMenuRequested.connect(
                lambda _p, s=sel: self._clear_color(s))
            row.addWidget(font_hant, 1)
            row.addWidget(font_hans, 1)
            row.addWidget(size_edit)
            row.addWidget(weight)
            row.addWidget(color_btn)
            lab = QLabel(label)
            if sel in ROW_TIPS:
                lab.setToolTip(ROW_TIPS[sel])
            form.addRow(lab, row)
            self._rows[sel] = {"font_hant": font_hant, "font_hans": font_hans,
                               "suffix": suffix, "size": size_edit,
                               "weight": weight, "color": color_btn,
                               "color_value": ""}
            font_hant.currentTextChanged.connect(
                lambda _v, s=sel: self._on_control_changed(s, "font-family",
                                                          "zh-Hant"))
            font_hans.currentTextChanged.connect(
                lambda _v, s=sel: self._on_control_changed(s, "font-family",
                                                          "zh-Hans"))
            size_edit.textChanged.connect(
                lambda _v, s=sel: self._on_control_changed(s, "font-size"))
            weight.currentIndexChanged.connect(
                lambda _i, s=sel: self._on_control_changed(s, "font-weight"))
        self._fill_font_combos(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cw)
        tabs.addTab(scroll, "控件")
        # 源码页
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(4, 4, 4, 4)
        self._source_edit = QPlainTextEdit()
        self._source_edit.setFont(QFont("Consolas"))
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
        """工作 CSS = 有效默认原文 + 覆盖块（源码页文本）。"""
        return self._base_css + "\n" + self._source_edit.toPlainText()

    def _control_value(self, sel, prop, lang=""):
        ctrls = self._rows[sel]
        if prop == "font-family":
            box = ctrls["font_hant"] if lang != "zh-Hans" else ctrls["font_hans"]
            data = box.currentData()
            return str(data).strip() if data else box.currentText().strip()
        if prop == "font-size":
            return ctrls["size"].text().strip()
        if prop == "font-weight":
            return ctrls["weight"].currentData() or ""
        if prop == "color":
            return ctrls["color_value"]
        return ""

    def _on_control_changed(self, sel=None, prop=None, lang=""):
        if sel and prop:
            key = (sel, prop, lang) if prop == "font-family" else (sel, prop)
            if self._control_value(sel, prop, lang):
                self._touched.add(key)
            else:
                self._touched.discard(key)
            if prop == "font-family" and lang:
                # 改哪栏字体，预览就切哪栏（否则改了简栏、看着繁栏，以为没生效）
                i = self.preview_lang.findData(lang)
                if i >= 0:
                    with QSignalBlocker(self.preview_lang):
                        self.preview_lang.setCurrentIndex(i)
        values = {}
        for entry in self._touched:
            if len(entry) == 3:
                s, _p, lg = entry
                v = self._control_value(s, "font-family", lg)
                if not v:
                    continue
                suffix = (self._rows[s] or {}).get("suffix")
                if not suffix:
                    continue
                block = ":root" if lg != "zh-Hans" else _HANS_BLOCK
                values.setdefault(block, {})["--font-" + suffix] = v
            else:
                s, p = entry
                v = self._control_value(s, p)
                if v:
                    values.setdefault(s, {})[p] = v
        block = build_override_block(values, self._passthrough)
        with QSignalBlocker(self._source_edit):
            self._source_edit.setPlainText(block)
        self._source_err.setText("")
        self._schedule()

    def _on_source_changed(self):
        values, passthrough, err = split_override_block(
            self._source_edit.toPlainText())
        if err:
            self._source_err.setText(f"CSS 解析失败（预览保持上次）：{err}")
            return
        self._source_err.setText("")
        self._passthrough = passthrough
        self._touched = _touched_from_values(values)
        self._sync_controls_from_block(self._display_values(values))
        self._schedule()

    def _sync_controls_from_block(self, values=None):
        if values is None:
            values, _err = parse_override_block(self._source_edit.toPlainText())
        values = values or {}
        hant_vars = values.get(":root", {})
        hans_vars = values.get(_HANS_BLOCK, {})
        for sel, ctrls in self._rows.items():
            props = values.get(sel, {})
            suffix = ctrls.get("suffix")
            with QSignalBlocker(ctrls["font_hant"]):
                self._select_font_value(
                    ctrls["font_hant"],
                    hant_vars.get("--font-" + suffix, "") if suffix else "")
            with QSignalBlocker(ctrls["font_hans"]):
                self._select_font_value(
                    ctrls["font_hans"],
                    hans_vars.get("--font-" + suffix, "") if suffix else "")
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
        dlg = _ColorPopup(self.work_css(), self._rows[sel]["color_value"], self)
        if dlg.exec() == QDialog.Accepted and dlg.selected():
            self._rows[sel]["color_value"] = dlg.selected()
            self._paint_color_button(sel)
            self._on_control_changed(sel, "color")

    def _clear_color(self, sel):
        self._rows[sel]["color_value"] = ""
        self._paint_color_button(sel)
        self._on_control_changed(sel, "color")

    # ----- 字体分组 -----
    def _select_font_value(self, box, value):
        """字体框按栈值选中（短名显示、存完整栈）。

        findData 命中按索引选；未命中（自定义栈）插临时项兜底——
        当前值恒为可选项，选不回问题不再有；上次临时项先删防堆积。
        空值回 0 号（"" 占位）。"""
        value = (value or "").strip()
        with QSignalBlocker(box):
            old = box.property("tempStack") or ""
            if old and old != value:
                i = box.findText(old)
                if i >= 0:
                    box.removeItem(i)
                box.setProperty("tempStack", "")
            if not value:
                box.setCurrentIndex(0)
                return
            i = box.findData(value)
            if i >= 0:
                box.setCurrentIndex(i)
                return
            if box.findText(value) < 0:
                box.insertItem(1, value, value)
            box.setProperty("tempStack", value)
            box.setCurrentIndex(box.findData(value))

    def _fill_font_combos(self, fresh=False):
        """全部字体下拉建模（不可编辑，只从下拉选；特殊栈去源码页）。

        选项 = ""占位 + 出厂常用栈（短名显示、存完整栈）
        + 中文buckets/西文/字库单名（名即值）；当前值按栈回选，
        自定义栈插临时项兜底（重建后仍可选中）。
        """
        from PySide6.QtGui import QStandardItem, QStandardItemModel
        if fresh:
            clear_qt_alias_cache()  # 重扫后别名表失效
        groups, bundled, _fonts_dir = font_group_model(fresh=fresh)
        order = [g for g, _ks in _CJK_BUCKETS if groups.get(g)] + \
                (["未分类"] if groups.get("未分类") else [])
        try:
            _stacks = stack_display_names(factory_font_stacks())
        except OSError:
            _stacks = []
        for _sel, ctrls in self._rows.items():
            for box in (ctrls["font_hant"], ctrls["font_hans"]):
                cur = box.currentData() or box.currentText()
                cur = (cur or "").strip()
                model = QStandardItemModel(box)

                def header(text, _m=model):
                    it = QStandardItem(f"── {text} ──")
                    it.setEnabled(False)
                    _m.appendRow(it)

                def item(text, data, _m=model):
                    it = QStandardItem(text)
                    it.setData(data, Qt.UserRole)
                    _m.appendRow(it)

                item("", "")
                if _stacks:
                    header("常用栈")
                    for text, data in _stacks:
                        item(text, data)
                header("中文")
                for gname in order:
                    header(f"中文·{gname}")
                    for n in sorted(set(groups[gname])):
                        item(n, n)
                header("西文")
                for n in _WESTERN_FONTS:
                    item(n, n)
                header("字库目录（cbeta/fonts）")
                for _fn, fam in bundled:
                    item(fam, fam)
                with QSignalBlocker(box):
                    box.setModel(model)
                self._select_font_value(box, cur)

    def _open_fonts_dir(self):
        fonts_dir = os.path.join(REPO_ROOT, "cbeta", "fonts")
        os.makedirs(fonts_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(fonts_dir)))

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

    def _on_t2s_toggled(self):
        self._work = None  # 简繁文字不同，重解样张
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
        t2s = self.t2s_box.isChecked()
        lang = "zh-Hans" if t2s else self._preview_lang()
        self._thread = _RenderThread(self.sample_edit.text().strip(), css, self._tmp,
                                     lang, t2s, self)
        self._thread.done.connect(self._on_rendered)
        self._thread.failed.connect(self._on_render_failed)
        self._thread.start()

    def _preview_lang(self):
        return self.preview_lang.currentData() or "zh-Hant"

    def _on_names_toggled(self):
        # 元素名开关：用缓存 spec 重画，不重渲
        spec = getattr(self, "_last_spec", None)
        if spec:
            self._show_spec(spec, qt_aliases())

    def _render_inline(self, css, lang=None):
        """同步重渲（单测/导出前保底用；界面走线程）。返回 docx 路径。"""
        import tempfile as _tf
        from pycbeta.parser import P5Parser
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.theme import Theme
        work = P5Parser().parse(self.sample_edit.text().strip())
        t2s = self.t2s_box.isChecked()
        if t2s:
            from pycbeta.simplify import simplify_work
            simplify_work(work)
            lang = "zh-Hans"
        theme = Theme.from_css(css, lang or self._preview_lang())
        out = _tf.mkdtemp(prefix="css-editor-")
        fn = DocxRenderer(theme=theme, notes="footnote",
                          bookmarks=False).render_work(work, out, "preview.docx")
        return fn if isinstance(fn, str) else fn[0]

    def _report_info(self, error=None):
        """当前预览检查信息（纯数据，可单测）；字体可用性经别名判定。"""
        import datetime
        aliases = qt_aliases()
        used = _spec_fonts(getattr(self, "_last_spec", None) or {"paras": []})
        fonts = [(f, bool(resolve_qt_family(f, aliases))) for f in used]
        return {"time": datetime.datetime.now().strftime("%H:%M:%S"),
                "base": getattr(self, "_base_label", ""),
                "sample": self.sample_edit.text().strip(),
                "t2s": self.t2s_box.isChecked(),
                "fonts": fonts,
                "gaps": getattr(self, "_last_gaps", None) or {},
                "stacks": list(getattr(self, "_last_stacks", None) or []),
                "css_error": self._source_err.text().strip() or "",
                "error": error or ""}

    def _push_report(self, error=None):
        self._report = self._report_info(error)
        if self._report_dlg is not None:
            self._report_dlg.update_report(self._report)

    def _open_report(self):
        if self._report_dlg is None:
            self._report_dlg = PreviewReportDialog(self)
        self._report_dlg.update_report(
            getattr(self, "_report", None) or self._report_info())
        self._report_dlg.show()
        self._report_dlg.raise_()
        self._report_dlg.activateWindow()

    def _set_status(self, text, issues=0, tip=""):
        """状态行：平时只显示正文；有问题追加可点击 ⚠（点开检查窗）。

        issues: 问题数；tip: 悬停摘要。连接状态走 _status_linked
        显式跟踪（裸 disconnect 无连接时打 RuntimeWarning）。
        """
        if issues:
            if not self._status_linked:
                self.status.linkActivated.connect(
                    lambda _u: self._open_report())
                self._status_linked = True
            self.status.setTextFormat(Qt.RichText)
            self.status.setText(
                f'{text} <a href="#" style="color:red">⚠{issues}</a>')
            self.status.setToolTip(tip or "点击打开预览检查")
            self.status.setOpenExternalLinks(False)
            self.status.setTextInteractionFlags(Qt.TextBrowserInteraction)
            self.status.setCursor(Qt.PointingHandCursor)
        else:
            if self._status_linked:
                self.status.linkActivated.disconnect()
                self._status_linked = False
            self.status.setTextFormat(Qt.PlainText)
            self.status.setText(text)
            self.status.setToolTip("")
            self.status.setTextInteractionFlags(Qt.NoTextInteraction)
            self.status.unsetCursor()

    def _on_rendered(self, docx_path):
        import datetime
        try:
            spec = docx_spec(docx_path)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"预览解析失败：{exc}")
            self._push_report(f"预览解析失败：{exc}")
            return
        self._last_docx = docx_path
        self._last_spec = spec
        aliases = qt_aliases()
        self._show_spec(spec, aliases)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        missing = [f for f in _spec_fonts(spec)
                   if f and not resolve_qt_family(f, aliases)]
        gaps = glyph_gaps(spec)
        self._last_gaps = gaps
        try:
            from PySide6.QtGui import QFontDatabase as _QFD
            _fams = _QFD.families()
        except Exception:  # noqa: BLE001
            _fams = []
        stacks = check_font_stacks(self.work_css(), aliases, _fams)
        self._last_stacks = stacks
        tips = []
        if missing:
            tips.append(f"{'、'.join(missing[:6])}无可用字形，替代显示；"
                        "导出 DOCX 不受影响")
        if gaps:
            tips.append(f"缺字形：{_gaps_text(gaps)}")
        if stacks:
            tips.append(f"字体栈{len(stacks)}项（详见检查窗）")
        self._set_status(f"预览已更新 {now}",
                         len(missing) + len(gaps) + len(stacks),
                         "；".join(tips))
        self._push_report()
        if self._need_refresh:
            self._need_refresh = False
            QTimer.singleShot(0, self.refresh_preview)

    def _on_render_failed(self, msg):
        self._set_status("重渲失败", 1, msg)
        self._push_report(msg)
        if self._need_refresh:
            self._need_refresh = False
            QTimer.singleShot(0, self.refresh_preview)

    def _show_spec(self, spec, aliases=None):
        from PySide6.QtGui import QTextBlockFormat
        show_names = self.names_box.isChecked()
        doc = self.preview.document()
        doc.clear()
        cur = QTextCursor(doc)
        prev_key = None
        # 字义（div-note）无段落样式，DOCX 只留 run 灰色：颜色全中即推断
        note_gray = div_note_color(self.work_css()) if show_names else ""
        for para in spec["paras"]:
            fmt = QTextBlockFormat()
            if para["align"] == "center":
                fmt.setAlignment(Qt.AlignCenter)
            elif para["align"] == "right":
                fmt.setAlignment(Qt.AlignRight)
            elif para["align"] == "justify":
                fmt.setAlignment(Qt.AlignJustify)
            _block_line_height(fmt, para.get("line"))
            _block_margins(fmt, para.get("margin"))
            cur.setBlockFormat(fmt)
            style = para.get("style", "")
            label_key = style
            if style in ("p", "") and note_gray:
                texts = [r for r in para["runs"]
                         if r.get("text") and not r.get("br")]
                if texts and all((r.get("color") or "").lower() == note_gray
                                 for r in texts):
                    label_key = "div-note"
            if show_names and label_key != prev_key:
                cur.insertText(f"【{STYLE_ROW_LABEL.get(label_key, label_key)}】",
                               _name_label_format())
            prev_key = label_key
            for r in para["runs"]:
                if r.get("br"):
                    # 段内换行（偈颂/预排）：新块并重挂本段格式
                    cur.insertBlock()
                    cur.setBlockFormat(fmt)
                    continue
                cf = QTextCharFormat()
                if r["size"]:
                    cf.setFontPointSize(r["size"])
                if r["font"]:
                    resolved = resolve_qt_family(r["font"], aliases)
                    cf.setFontFamilies(
                        preview_families(resolved or r["font"]))
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
            prev_fn = None
            for fn in spec["footnotes"]:
                ffmt = QTextBlockFormat()
                _block_line_height(ffmt, fn.get("line"))
                _block_margins(ffmt, fn.get("margin"))
                cur.setBlockFormat(ffmt)
                if show_names and prev_fn != "footnote":
                    cur.insertText("【脚注】", _name_label_format())
                prev_fn = "footnote"
                for r in fn["runs"]:
                    if r.get("br"):
                        cur.insertBlock()
                        cur.setBlockFormat(ffmt)
                        continue
                    cf = QTextCharFormat()
                    if r["size"]:
                        cf.setFontPointSize(r["size"])
                    if r["font"]:
                        resolved = resolve_qt_family(r["font"], aliases)
                        cf.setFontFamilies(
                            preview_families(resolved or r["font"]))
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

    def closeEvent(self, event):
        if not self._confirm_discard():
            event.ignore()
            return
        try:
            if self._thread is not None and self._thread.isRunning():
                self._thread.wait(2000)
        finally:
            super().closeEvent(event)


def suppress_font_warnings():
    """压住 Qt DirectWrite Fixedsys 噪音。QApplication 创建之前调用。

    背景：Qt 在 Windows 上解析默认等宽字体时 probing 到光栅字体 Fixedsys，
    DirectWrite 建 face 失败打警告（qt.qpa.fonts），与渲染无关的噪音。
    """
    key = "QT_LOGGING_RULES"
    rule = "qt.qpa.fonts.warning=false"
    cur = os.environ.get(key, "")
    if rule not in cur:
        os.environ[key] = (cur + ";" + rule) if cur else rule


def main(argv=None):
    """独立运行：python -m pycbeta.gui.css_editor [--sample 样张.xml]。"""
    import argparse
    suppress_font_warnings()
    ap = argparse.ArgumentParser(description="DOCX 所见即所得 CSS 编辑器")
    ap.add_argument("--sample", default="", help="预览样张 XML 路径")
    args = ap.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv or [])
    dlg = CssEditorDialog(sample_xml=args.sample or None)
    dlg.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
