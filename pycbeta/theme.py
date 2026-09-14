"""Theme: one style definition set shared across HTML / PDF / DOCX renderers.

Users may write styles either as JSON ({"tags": {...}}) or as a CSS file.
The project ships a default theme (styles/pdf_docx.css, used by PDF/DOCX;
HTML/EPUB use styles/cbeta_golden.css instead) that is used by default;
user CSS/JSON overrides it per tag.

CSS is used directly by HTML/PDF and parsed (via tinycss2) into the same
tag -> property map for DOCX translation.

字体单一来源（2026-09-06 起）：CSS :root 双栏变量（繁体 + html[lang="zh-Hans"]
简体覆盖），规则内 font-family: var(--font-标签) 引用；Theme(lang) 代入解析。
config.json font_sets 已删除（历史包袱，不再读取）。
"""

import copy
import json
import os
import re
from typing import Dict, List, Optional

_DEFAULT_CSS = os.path.join(os.path.dirname(__file__), "styles", "pdf_docx.css")

# CSS properties we can translate to OOXML for DOCX.
TRANSLATABLE = {
    "font-size", "font-weight", "color", "font-family",
    "text-align", "text-indent", "line-height", "margin", "margin-left",
    "margin-top", "margin-bottom", "list-style-type",
}

TAG_SELECTOR = {
    "body": "body",
    "title": "h1.title",
    "series-title": "p.series-title",
    "author": "p.author",
    "translator": "p.translator",
    "byline": "p.byline",
    "head": "p.head",
    "juan": "p.juan",
    "pin": "p.pin",
    "p": "p",
    "pre": "pre",
    "verse": "div.lg",
    "form": "p.form",
    "figure": "p.figure",
    "dharani": "p.dharani",
    "footnote": ".endnote, .fn, .footnote",
    "note-ref": "sup.note-ref, sup.footnote-call",
    "note-inline": "span.note-inline",
    "doube-line-note": "span.doube-line-note",
    "interlinear-note": "span.interlinear-note",
    "transliteration": "span.transliteration",
    "list": "ul, ol",
    "item": "li",
    "kaiti": "[rend~=kaiti]",
    "heiti": "[rend~=heiti]",
    "fangsong": "[rend~=fangsong]",
    "mingti": "[rend~=mingti]",
    "def": "cb:def",
}

# 竖排取消居中的段落标签（横排居中、竖排默认对齐）：书名/标题/卷名/品名。
# docx 与 pdf 共用此名单（docx 走 _para 内联覆盖，pdf 走 body.vertical-rl CSS 块）。
VERTICAL_UNCENTER = ("title", "head", "juan", "pin")

# reverse: css selector -> tag
_SELECTOR_TAGS = {}
for _tag, _sel in TAG_SELECTOR.items():
    for _s in _sel.split(","):
        _SELECTOR_TAGS[_s.strip()] = _tag
# common short forms
_SELECTOR_TAGS.update({
    ".title": "title", ".meta": "author", ".byline": "byline",
    ".author": "author", "p.author": "author",
    ".translator": "translator", "p.translator": "translator",
    ".head": "head", ".juan": "juan", ".lg": "verse",
    "p.pin": "pin", ".pin": "pin",
    "pre": "pre",
    ".form": "form", ".dharani": "dharani", ".endnote": "footnote",
    "p.form": "form", "p.dharani": "dharani",
    "p.series-title": "series-title",
    # 以下仅解析方向（DOCX 渲染器不查这些标签，HTML/PDF 走原文 CSS）：
    # 注锚颜色（a.noteAnchor 及按校勘类型着色）、注记类偈行颜色
    "a.noteAnchor": "note-anchor", "a.noteAnchor.add": "note-anchor-add",
    "a.noteAnchor.mod": "note-anchor-mod", "a.noteAnchor.orig": "note-anchor-orig",
    "a.noteAnchor.star": "note-anchor-star",
    "div.lg.note1": "lg-note1", "div.lg.note2": "lg-note2",
    ".fn": "footnote", ".footnote": "footnote", ".note-inline": "note-inline",
    ".doube-line-note": "doube-line-note", "span.doube-line-note": "doube-line-note",
    ".interlinear-note": "interlinear-note", "span.interlinear-note": "interlinear-note",
    ".transliteration": "transliteration", "span.transliteration": "transliteration",
    "sup.note-ref": "note-ref", "sup.footnote-call": "note-ref", "li": "item",
    "ul": "list", "ol": "list",
    "[rend~=kaiti]": "kaiti", "[rend~=heiti]": "heiti",
    "[rend~=fangsong]": "fangsong", "[rend~=mingti]": "mingti",
    '[rend~="kaiti"]': "kaiti", '[rend~="heiti"]': "heiti",
    '[rend~="fangsong"]': "fangsong", '[rend~="mingti"]': "mingti",
})
# CBETA div/@type semantic hooks (div-orig, div-xu, ...)
_DIV_TYPES = ["orig", "commentary", "xu", "jing", "pin", "fen", "hui", "w",
              "note", "other", "di", "mu", "jie", "she", "shi", "toc",
              "xiang", "zhang", "廣釋", "續補", "chu", "lg"]
for _dt in _DIV_TYPES:
    _SELECTOR_TAGS[f"div.div-{_dt}"] = f"div-{_dt}"
    _SELECTOR_TAGS[f".div-{_dt}"] = f"div-{_dt}"
    # div 标签也要进 TAG_SELECTOR，否则 css()/scale_font_sizes() 重序列化时丢弃
    # div 规则（如 --theme xxx.json 路径下 html/pdf 的 div-xu 颜色）。安全：
    # font_sets 预设不含 div 标签，不会误注入 font-family；无 font-size 的 div 不产生字号规则。
    TAG_SELECTOR.setdefault(f"div-{_dt}", f"div.div-{_dt}")


# 主题默认值唯一定义处 = `styles/pdf_docx.css`（不再有 Python DEFAULT_THEME，
# 避免"删 CSS 键仍被 Python 兜底"造成 DOCX/HTML 不一致）。
# 必需元素由 REQUIRED_THEME_TAGS 声明、test_theme.TestRequiredThemeTags 守护；
# 缺失时提示往 pdf_docx.css 补对应选择器/属性。
#
# 约定：`p` 不写 font-size（跟随 `body`，DOCX 经 docDefaults 继承）；字号相对处用 em。
REQUIRED_THEME_TAGS: Dict[str, tuple] = {
    "body": ("font-size", "line-height"),
    "title": ("font-size", "font-weight"),
    "author": (),                 # 字号继承 body（单源）
    "translator": (),
    "byline": (),
    "head": ("font-size", "font-weight"),
    "juan": ("font-size", "font-weight"),
    "pin": ("font-size", "font-weight"),
    "p": ("text-indent",),        # 刻意不要求 font-size/line-height：跟随 body
    "pre": ("text-indent",),
    "verse": (),                  # 字号继承 body；色/字体另行要求
    "form": ("font-weight",),
    "dharani": (),
    "footnote": ("font-size",),
    "note-ref": ("font-size",),
    "note-inline": ("font-size",),
    "doube-line-note": ("font-size",),
    "interlinear-note": ("font-size",),
    "list": ("list-style-type",),
    "item": (),
    "kaiti": ("font-family",),
    "heiti": ("font-family",),
    "fangsong": ("font-family",),
    "mingti": ("font-family",),
    "div-orig": ("font-weight",),
}


def missing_required_theme(theme: "Theme") -> list:
    """检查主题是否缺少 REQUIRED_THEME_TAGS 的元素/属性；返回人类可读缺失项。

    空列表 = 齐全。文案含应加的选择器，便于直接补进 pdf_docx.css。
    """
    tags = getattr(theme, "tags", None) or {}
    missing = []
    for tag, props in REQUIRED_THEME_TAGS.items():
        if tag not in tags:
            sel = TAG_SELECTOR.get(tag, tag)
            missing.append(f"元素 {tag}（选择器 {sel}）整体缺失")
            continue
        for p in props:
            if not (tags.get(tag) or {}).get(p):
                sel = TAG_SELECTOR.get(tag, tag)
                missing.append(f"元素 {tag}（{sel}）缺少属性 {p}")
    return missing


# 代码兜底值（保命值，集中定义；值恒定）：CSS/配置缺失时的最后取值，
# 保证任何输入都能出文件。清单与触发条件见 docs/兜底值清单.md，新增请登记。
FALLBACKS = {
    "base_pt": 12.0,            # em/% 换算基准（body、p 均无绝对 pt）
    "doc_size_pt": 11,          # docDefaults 文档默认字号（body、p 均无字号）
    "line_height": 1.5,         # Normal 样式行距（body、p 均无行距）
    "verse_hang_em": 2.0,       # 偈颂 div.lg 无 margin-left 时首句悬挂缩进
    "body_font": "微軟正黑體",    # body 无字体时 docDefaults eastAsia
}

# 预设（字体方案 + 页面设置）：外部 JSON 配置，见 styles/presets.json，
# 用户可直接改或复制后用 --presets-file 指定。
_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def _strip_json_comments(text: str) -> str:
    """去掉 JSON 里的 // 行注释 和 /* */ 块注释（跳过字符串内的 // 等）。"""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


def load_presets(path: str = _PRESETS_PATH) -> Dict[str, dict]:
    """Load presets JSON (支持 // 与 /* */ 注释): {"pages": {...}, ...}."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return json.loads(_strip_json_comments(text))


def load_effective_presets(path: Optional[str] = None) -> Dict[str, dict]:
    """宽容读取配置：run.json（含任一 RUN_KEYS 槽）→ 按 5 槽合并后的 presets；
    否则按 presets JSON 直读。path=None → 出厂 config.json。

    供既可能收到 run.json 又可能收到 presets 文件的调用方（如 verify_one）。"""
    if not path:
        return load_presets()
    try:
        raw = load_presets(path)
    except (OSError, ValueError):
        return load_presets()
    if isinstance(raw, dict) and any(k in raw for k in RUN_KEYS):
        run = load_run_config(path)
        return resolve_effective_config(run, os.path.dirname(os.path.abspath(path)))
    return raw


try:
    _PRESETS = load_presets()
    PAGE_PRESETS: Dict[str, Dict] = _PRESETS.get("pages") or {}
    OUTPUT_PRESETS: Dict = _PRESETS.get("output") or {}
    ENGINE_PRESETS: Dict = _PRESETS.get("engines") or {}
    VERIFY_PRESETS: Dict = _PRESETS.get("verify") or {}
except (OSError, ValueError) as _e:
    PAGE_PRESETS = {}
    OUTPUT_PRESETS = {}
    ENGINE_PRESETS = {}
    VERIFY_PRESETS = {}

NOTES_MODES = ("footnote", "endnote", "inline")
_DEFAULT_NOTE_MODE = "footnote"

# 内联括号形态：正文夹注（output.inline_brackets）与校注内联（output.note_inline_brackets）共用取值
INLINE_BRACKET_PAIRS = {
    "fullwidth": ("（", "）"),
    "halfwidth": ("(", ")"),
    "corner": ("〔", "〕"),
    "square": ("[", "]"),
}


def bracket_pair(value) -> tuple:
    """括号键 → (左, 右)；未知/空回退全角圆括号（保持旧行为）。"""
    return INLINE_BRACKET_PAIRS.get(value or "", INLINE_BRACKET_PAIRS["fullwidth"])


def resolve_notes(presets=None, fmt: Optional[str] = None,
                  explicit: Optional[str] = None) -> str:
    """注释方式解析：显式 > presets `output.notes`（非空合法值）> 默认。

    默认 `footnote`（docx/pdf 页底脚注；html/epub/md/txt 对 footnote/endnote
    不作区分，均文末集中，只有 inline 变括号内联）。`fmt` 仅作保留参数。
    """
    if explicit in NOTES_MODES:
        return explicit
    cfg = (presets or {}).get("output") or {}
    val = (cfg.get("notes") or "").strip().lower()
    return val if val in NOTES_MODES else _DEFAULT_NOTE_MODE

# CSS 通用字体族在序列化时保持不加引号，否则会变成普通字体名。
_UNQUOTED_FONT_FAMILIES = frozenset({
    "serif", "sans-serif", "monospace", "cursive", "fantasy",
    "system-ui", "ui-serif", "ui-sans-serif", "ui-monospace", "cbetarc",
})


def _format_font_stack(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parts = []
    for raw in value.split(","):
        name = raw.strip().strip('"').strip("'")
        if not name:
            continue
        if name.lower() in _UNQUOTED_FONT_FAMILIES:
            parts.append(name)
        else:
            parts.append(f'"{name}"')
    return ", ".join(parts)


def _hex6(color: object):
    """CSS 颜色 → OOXML 6 位十六进制（大小写原样保留）。
    3 位简写展开（#000→000000）；非法值返回 None（调用方跳过，不输出 w:color）。
    背景：ST_HexColor 只要 6/8 位，旧代码 lstrip("#") 会把 #000 写成非法的 w:val="000"。"""
    if not isinstance(color, str):
        return None
    s = color.strip().lstrip("#")
    if re.match(r"^[0-9a-fA-F]{3}$", s):
        s = "".join(c * 2 for c in s)
    if re.match(r"^[0-9a-fA-F]{6}$", s):
        return s
    return None


def _abs_pt(value: object, base_pt: float):
    """font-size 值 → pt 浮点（pt 直接；em/% 按 base 换算；非法 None）。纯函数。"""
    m = re.match(r"^\s*([\d.]+)\s*pt\s*$", value or "")
    if m:
        return float(m.group(1))
    m = re.match(r"^\s*([\d.]+)\s*(em|%)\s*$", value or "")
    if m:
        v = float(m.group(1))
        return v / 100.0 * base_pt if m.group(2) == "%" else v * base_pt
    return None


def _scale_font_size(value: object, factor: float) -> Optional[str]:
    """把单个 font-size 值等比缩放：只放绝对单位 pt；em/% 是相对单位，
    随其基准（段落字号/父元素）自动放大，不在此乘——否则与放大的基准相乘造成双重放大
    （2026-09-06 实锤：1.5 下注码 1em×18pt=27pt，而非 18pt）。非数值格式返回 None（保持原值）。"""
    m = re.match(r"^\s*([\d.]+)\s*(pt|em|%)\s*$", value or "")
    if not m:
        return None
    if m.group(2) != "pt":
        return f"{float(m.group(1)):g}{m.group(2)}"  # 相对单位原样返回
    num = float(m.group(1)) * factor
    text = f"{num:.4f}".rstrip("0").rstrip(".")
    return f"{text}{m.group(2)}"


def _scale_font_dict(props: Dict[str, str], factor: float) -> None:
    """单个属性字典的 font-size 原地等比缩放（绝对 pt 才乘；缺键/非数值不动）。"""
    scaled = _scale_font_size(props.get("font-size"), factor)
    if scaled is not None:
        props["font-size"] = scaled


_HEAD_NO_RE = re.compile(r"\ANo\.\s*[A-Za-z0-9][A-Za-z0-9\-]*")


def strip_head_no(children):
    """head/jhead 行首 `No. XXXX` 令牌剥离（`output.strip_head_no` 用）。

    非变异：跳过 Lb/Pb/anchor 空节点，首个有文本 Text 去行首令牌，
    余部 lstrip（吃掉 `<lb/>` 后的版式空格，如 ` 序`→`序`）；余部为空则整节点丢弃，
    并对后续首个 Text 再做一次 lstrip（单令牌，只剥一次 No.）。
    返回 (new_children, token)；无命中 token 为 ""。正文内的 No.（非行首）不动。
    """
    from .model import Lb, Pb, Text
    out = []
    token = ""
    phase = "skip"  # skip 空节点 → strip 首文本 → lstrip 后续 → done
    for n in children or []:
        if phase == "done":
            out.append(n)
            continue
        if isinstance(n, (Lb, Pb)):
            out.append(n)
            continue
        tag = getattr(n, "tag", None)
        if tag == "anchor":
            out.append(n)
            continue
        if isinstance(n, Text):
            t = n.text or ""
            if phase == "skip":
                s = t.lstrip()
                if not s:
                    continue  # 纯空白 Text 丢弃（版式空格）
                m = _HEAD_NO_RE.match(s)
                if not m:
                    out.append(n)
                    phase = "done"
                    continue
                token = m.group(0)
                rest = s[m.end():].lstrip()
                phase = "lstrip"
                if rest:
                    out.append(Text(rest, line=n.line))
                continue
            else:  # lstrip：No. 后的首个文本去前导空格
                s = t.lstrip()
                phase = "done"
                if s:
                    out.append(Text(s, line=n.line))
                continue
        out.append(n)
        phase = "done"
    return out, token


# ---------------- CSS 字体变量（:root 双栏，font_sets 已删除） ----------------
# var 名规则：单标签 "--font-<tag>"（如 --font-note-inline），后代组合
# "--font-<anc>-<tgt>"（如 --font-div-xu-head）；latin 不是标签，单独取。
FONT_VAR_TAGS = {
    "body": "body", "title": "title", "series-title": "series-title",
    "author": "author", "translator": "translator", "byline": "byline",
    "head": "head", "juan": "juan", "pin": "pin", "p": "p",
    "verse": "verse", "form": "form", "dharani": "dharani",
    "footnote": "footnote", "note-inline": "note-inline",
    "kaiti": "kaiti", "heiti": "heiti", "fangsong": "fangsong",
    "mingti": "mingti", "def": "def",
}
FONT_VAR_COMPOUNDS = {"div-xu-head": ("div-xu", "head")}

_HANS_SELECTOR_RE = re.compile(r'^html\[lang=(["\']?)zh-Hans\1\]$')
_VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*(.*?))?\)")


def resolve_font_vars(css_text):
    """收 :root + html[lang=zh-Hans] 两组 --font-* 变量 → (hant, hans)。
    同名后定义优先；非法输入返回空对，不抛异常。"""
    hant, hans = {}, {}
    try:
        import tinycss2
        rules = tinycss2.parse_stylesheet(css_text or "", skip_comments=True,
                                          skip_whitespace=True)
    except Exception:
        return hant, hans
    for rule in rules:
        if rule.type != "qualified-rule":
            continue
        sel = tinycss2.serialize(rule.prelude).strip()
        if sel == ":root":
            target = hant
        elif _HANS_SELECTOR_RE.match(sel):
            target = hans
        else:
            continue
        for d in tinycss2.parse_declaration_list(rule.content):
            if d.type == "declaration" and d.name.startswith("--"):
                target[d.name] = tinycss2.serialize(d.value).strip()
    return hant, hans


def _subst_vars(value, vars):
    """var(--x[, fallback]) 按变量表代入；未知变量用 fallback，无则原文。"""
    def rep(m):
        name, fb = m.group(1), m.group(2)
        if name in vars and vars[name]:
            return vars[name]
        return fb.strip() if fb else m.group(0)
    prev, out = None, value or ""
    while prev != out:
        prev = out
        out = _VAR_RE.sub(rep, out)
    return out


# ---------------- 默认主题槽（config.theme，变种 CSS 选择） ----------------
_STYLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles")
BUILTIN_PRESETS_DIR = os.path.join(_STYLES_DIR, "presets")
USER_PRESETS_DIRNAME = "css-presets"


def user_presets_dir(root=None):
    """用户预设目录（仓库根 css-presets/；git 忽略）。"""
    base = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, USER_PRESETS_DIRNAME)


def list_presets(builtin_dir=None, user_dir=None):
    """预设列表 → [(kind, stem, path)]，kind ∈ builtin/user；
    同名用户遮蔽内置。"""
    found = []
    builtin_dir = os.path.abspath(builtin_dir or BUILTIN_PRESETS_DIR)
    user_dir = os.path.abspath(user_dir or user_presets_dir())
    for kind, d in (("builtin", builtin_dir), ("user", user_dir)):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith(".css"):
                found.append((kind, os.path.splitext(fn)[0],
                              os.path.join(d, fn)))
    user_names = {n for k, n, _p in found if k == "user"}
    return [(k, n, p) for k, n, p in found
            if k == "user" or n not in user_names]


def theme_file_text(path, factory_text=None):
    """主题文件全文 = 出厂原文 + 文件原文（CSS 层叠，后者胜）。

    预设只存覆盖块（不存出厂快照，出厂进化自动跟随）；旧全快照同样安全
    （重复规则值一致，文件缺失/非法抛 OSError/UnicodeError 由调用方处理）。
    """
    if factory_text is None:
        with open(_DEFAULT_CSS, encoding="utf-8") as f:
            factory_text = f.read()
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return factory_text + "\n" + text


def resolve_theme_css(value, base_dir=None):
    """默认 CSS 解析 → (path|None, 说明)。None=内置出厂 pdf_docx.css。
    - 空 → 内置；"pdf_docx.css" → 内置文件
    - 名字（无路径分隔符）：<name>[.css] 先用户库后内置库
    - 路径：绝对直接；相对先相对 base_dir（config 所在目录）再相对仓库根
    - 找不到 → 警告 + 内置（不崩）。"""
    value = (value or "").strip() if isinstance(value, str) else ""
    if not value:
        return None, "内置出厂"
    if value == "pdf_docx.css" or value.endswith("/pdf_docx.css") or \
            value.endswith("\\pdf_docx.css"):
        return None, "内置出厂"
    if "/" not in value and "\\" not in value:
        stem = value[:-4] if value.lower().endswith(".css") else value
        for kind, _n, path in list_presets():
            if _n == stem or _n.lower() == stem.lower():
                return path, f"{'用户' if kind == 'user' else '内置'}预设"
        # 非预设名时再试相对路径（config 目录 → 仓库根）
        rels = []
        if base_dir:
            rels.append(os.path.join(base_dir, value))
        rels.append(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            value))
        for c in rels:
            if os.path.isfile(c):
                return os.path.abspath(c), "路径指定"
        print(f"theme: 预设 {value!r} 不存在，回内置出厂")
        return None, "内置出厂（预设缺失）"
    cands = []
    if os.path.isabs(value):
        cands.append(value)
    else:
        if base_dir:
            cands.append(os.path.join(base_dir, value))
        cands.append(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            value))
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c), "路径指定"
    print(f"theme: 文件 {value!r} 不存在，回内置出厂")
    return None, "内置出厂（文件缺失）"


# ---------------- run.json（一次运行的组合单；替代旧 --config 全量快照） ----------------
# 5 槽：config-json（基础配置）+ 按格式分的标准/增量主题槽。
# 优先级（逐槽）：显式开关 > run.json 槽 > 内置默认。
# 不带 --config 时自动读仓库根 run.json（没有就全出厂）；config.user.json 已废弃。
RUN_CONFIG_NAME = "run.json"
RUN_KEYS = ("config-json", "html-epub-theme", "html-epub-user-theme",
            "pdf-docx-theme", "pdf-docx-user-theme")
DEFAULT_RUN_CONFIG = {
    "config-json": "config.json",          # 基础配置：出厂 pycbeta/config.json
    "html-epub-theme": "cbeta_golden.css",  # html/epub 标准基底（官方）
    "html-epub-user-theme": "",            # 占位：非空警告+忽略（纯 golden）
    "pdf-docx-theme": "pdf_docx.css",      # pdf/docx 标准（整套替换出厂全文）
    "pdf-docx-user-theme": "",             # pdf/docx 增量（双目录名/路径，追加）
}
_LEGACY_CONFIG_KEYS = ("pages", "output", "engines", "theme", "verify",
                       "annotations", "source")
_RUN_TEMPLATE = """{{
  // 一次运行的组合单（5 槽；显式开关优先）。常改文件，不入库。
  // config-json：基础配置（名或路径；缺省出厂 pycbeta/config.json）
  "config-json": {config_json},
  // html/epub 标准基底（默认官方 cbeta_golden.css，一般不动）
  "html-epub-theme": {html_epub_theme},
  // html/epub 增量：占位（非空警告+忽略，html/epub 纯基底）
  "html-epub-user-theme": {html_epub_user_theme},
  // pdf/docx 标准（整套替换出厂 pdf_docx.css 全文）
  "pdf-docx-theme": {pdf_docx_theme},
  // pdf/docx 增量（名走 css-presets/ 双目录或路径，追加在标准之后）
  "pdf-docx-user-theme": {pdf_docx_user_theme}
}}
"""


def _render_run_template(values):
    """注释模板渲染（新建 run.json 用；注释是文档的一部分，必须保留）。"""
    return _RUN_TEMPLATE.format(**{
        k.replace("-", "_"): json.dumps(values.get(k, DEFAULT_RUN_CONFIG[k]),
                                        ensure_ascii=False)
        for k in RUN_KEYS})
_DEFAULT_CSS = os.path.join(_STYLES_DIR, "pdf_docx.css")
_GOLDEN_CSS = os.path.join(_STYLES_DIR, "cbeta_golden.css")


def default_run_path(root=None):
    """默认 run.json 路径（仓库根；不入库，常改）。"""
    base = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, RUN_CONFIG_NAME)


def load_run_config(path=None, root=None):
    """读 run.json → 5 键 dict（缺键按 DEFAULT_RUN_CONFIG 补）。

    path=None → root/run.json，不存在则全缺省（静默）。
    非法 JSON → ValueError；旧全量快照（有 pages/output/engines/theme 等
    且无 run 键）→ ValueError 指新格式（硬切换，不兼容）。
    """
    if path is None:
        path = default_run_path(root)
        if not os.path.isfile(path):
            return dict(DEFAULT_RUN_CONFIG)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(_strip_json_comments(text))
    except ValueError as exc:
        raise ValueError(f"run.json 非法 JSON（{path}）：{exc}")
    if not isinstance(data, dict):
        raise ValueError(f"run.json 顶层必须是对象（{path}）")
    if not any(k in data for k in RUN_KEYS) and \
            any(k in data for k in _LEGACY_CONFIG_KEYS):
        raise ValueError(
            f"旧 --config 全量快照已废弃（{path}）：请改用 run.json（5 槽组合单，"
            "见 docs/主题与样式.md），旧 theme 键对应 pdf-docx-user-theme")
    out = dict(DEFAULT_RUN_CONFIG)
    for k in RUN_KEYS:
        v = data.get(k)
        out[k] = v if isinstance(v, str) else DEFAULT_RUN_CONFIG[k]
    out["_path"] = os.path.abspath(path)
    return out


def _resolve_run_file(value, run_dir, label):
    """run.json 槽值 → 文件 abspath；缺文件警告+None（调用方回内置）。"""
    value = (value or "").strip()
    if not value:
        return None
    cands = []
    if os.path.isabs(value):
        cands.append(value)
    else:
        if run_dir:
            cands.append(os.path.join(run_dir, value))
        cands.append(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            value))
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    print(f"run.json: {label} {value!r} 不存在，回内置")
    return None


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def resolve_base_config(run, run_dir=None):
    """config-json 槽 → 基础配置文件 abspath（默认出厂；缺文件警告+出厂）。"""
    value = (run.get("config-json") or "").strip() or "config.json"
    if value == "config.json":
        return _PRESETS_PATH
    hit = _resolve_run_file(value, run_dir, "config-json")
    return hit or _PRESETS_PATH


def _builtin_text(path):
    try:
        return _read_text(path)
    except OSError:
        return ""


def resolve_pdf_docx_css(run, run_dir=None, std=None, user=None):
    """pdf/docx 生效 CSS 全文：显式开关 > run.json 槽 > 内置。

    标准槽：内置名（pdf_docx.css）用出厂全文；自定义文件全文替换出厂。
    增量槽：双目录名/路径，追加（复用 theme_file_text 层叠语义）。
    """
    std = (std if std is not None else run.get("pdf-docx-theme") or "").strip() \
        or "pdf_docx.css"
    if std == "pdf_docx.css" or std.endswith("/pdf_docx.css") or \
            std.endswith("\\pdf_docx.css"):
        base = _builtin_text(_DEFAULT_CSS)
    else:
        hit = _resolve_run_file(std, run_dir, "pdf-docx-theme")
        base = _read_text(hit) if hit else _builtin_text(_DEFAULT_CSS)
    usr = (user if user is not None else run.get("pdf-docx-user-theme")
           or "").strip()
    if usr:
        upath, _label = resolve_theme_css(usr, run_dir)
        if upath:
            return theme_file_text(upath, base)
    return base


def resolve_html_base_css(run, run_dir=None, std=None):
    """html/epub 基底 CSS 全文：显式开关 > run.json 槽 > 内置 golden。"""
    std = (std if std is not None else run.get("html-epub-theme") or "").strip() \
        or "cbeta_golden.css"
    if std == "cbeta_golden.css" or std.endswith("/cbeta_golden.css") or \
            std.endswith("\\cbeta_golden.css"):
        return _builtin_text(_GOLDEN_CSS)
    hit = _resolve_run_file(std, run_dir, "html-epub-theme")
    return _read_text(hit) if hit else _builtin_text(_GOLDEN_CSS)


def check_run_placeholders(run):
    """占位槽非空 → 警告（html-epub-user-theme 尚未接线，忽略）。"""
    if (run.get("html-epub-user-theme") or "").strip():
        print("run.json: html-epub-user-theme 尚未接线，已忽略（html/epub 纯基底）")


def _replace_json_string_slot(text, key, value):
    """文本级换槽值：只动目标行，其余字节（含注释/空行/顺序）原样保留。
    键不存在则插到末尾 `}` 之前。"""
    pat = re.compile(r'("%s"\s*:\s*)"(?:[^"\\\n]|\\.)*"' % re.escape(key))
    rep = r"\1" + json.dumps(value, ensure_ascii=False)
    new, n = pat.subn(rep, text, count=1)
    if n:
        return new
    ins = '\n  "%s": %s\n' % (key, json.dumps(value, ensure_ascii=False))
    idx = text.rfind("}")
    if idx < 0:
        return text.rstrip("\n") + "\n{" + ins + "}\n"
    head, tail = text[:idx], text[idx:]
    if head.rstrip().endswith("{"):
        return head + ins + tail
    return head.rstrip("\n") + ",\n" + ins.lstrip("\n") + tail


def set_run_slot(key, value, root=None):
    """run.json 单槽写入（文本级手术，只改目标行；注释/顺序/其余键原样保留）。
    无文件按注释模板建；非法原文件改名 .bad 后按模板建。返回 run.json 路径。"""
    if key not in RUN_KEYS:
        raise ValueError(f"未知 run.json 槽：{key!r}")
    path = default_run_path(root)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        try:
            data = json.loads(_strip_json_comments(text))
            if not isinstance(data, dict):
                raise ValueError("顶层非对象")
        except ValueError:
            bad = path + ".bad"
            try:
                os.replace(path, bad)
            except OSError:
                pass
            text = None
        if text is None:
            vals = dict(DEFAULT_RUN_CONFIG)
            vals[key] = value
            text = _render_run_template(vals)
        else:
            text = _replace_json_string_slot(text, key, value)
    else:
        vals = dict(DEFAULT_RUN_CONFIG)
        vals[key] = value
        text = _render_run_template(vals)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    return path


def deep_merge(base, over):
    """递归合并（over 按鍵胜；list/标量整体替换；仅 dict 递归）。纯函数。"""
    out = dict(base or {})
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve_effective_config(run, run_dir=None):
    """有效配置（面板显示/CLI 输出选项共用）：出厂 ← base 文件，按鍵深合并。

    base 文件的遗留 theme 键警告（出厂文件除外；主题唯一来源是 run.json 槽）。
    工厂文件损坏 → {}（调用方用 or 回退）。
    """
    try:
        factory = load_presets(_PRESETS_PATH)
    except (OSError, ValueError):
        return {}
    try:
        bpath = resolve_base_config(run, run_dir)
        base = load_presets(bpath)
    except (OSError, ValueError):
        return dict(factory)
    if os.path.abspath(bpath) != os.path.abspath(_PRESETS_PATH) and \
            isinstance(base, dict) and "theme" in base:
        print("配置：基础配置文件的 theme 键已废弃，请用 run.json 主题槽")
    return deep_merge(factory, base)


# 内置页面尺寸（mm），presets.json 的 pages 可覆盖/扩展
BUILTIN_PAGES: Dict[str, Dict] = {
    "a4": {"size": [210, 297]},
    "a5": {"size": [148, 210]},
    "信纸": {"size": [216, 279]},
    "手机": {"size": [100, 178]},
    "平板8寸": {"size": [108, 172]},
    "平板9寸": {"size": [121, 194]},
    "平板11寸": {"size": [148, 237]},
    "32开": {"size": [130, 184]},
    "16开": {"size": [185, 260]},
}


def _lookup_ci(mapping: Dict, name: str):
    """大小写不敏感取键（页面方案名 A4/a4 通吃）；无则 None。"""
    if not isinstance(mapping, dict) or not isinstance(name, str):
        return None
    if name in mapping:
        return mapping[name]
    low = name.lower()
    for k, v in mapping.items():
        if isinstance(k, str) and k.lower() == low:
            return v
    return None


def apply_page_typography(theme, page, page_presets):
    """纸张绑字号：pages.<page> 的 body_font_size/body_line_height 覆盖 theme body。

    纸张赢 CSS（纸张是更具体的上下文；CSS 编辑器改 body 只影响没写键的纸）。
    p 没亲笔写过字号/行距时跟 body 走（否则 DOCX 里 DEFAULT 的 p=12pt 会盖住
    body 覆盖——OOXML 无继承，run/命名样式都取 p 自身值）。
    无键/非法值 → 不动（并打印警告）。返回同一 theme（链式）。纯逻辑（除打印）。
    """
    entry = _lookup_ci(page_presets or {}, page or "")
    theme._page_typography_applied = (page, id(page_presets))
    if not isinstance(entry, dict):
        return theme
    props = theme.tags.setdefault("body", {})
    explicit = getattr(theme, "_explicit", set())
    fs = entry.get("body_font_size")
    if isinstance(fs, str) and fs.strip():
        m = re.match(r"^\s*([\d.]+)\s*pt\s*$", fs)
        if m and float(m.group(1)) > 0:
            props["font-size"] = f"{float(m.group(1)):g}pt"
            if ("p", "font-size") not in explicit:
                theme.tags.setdefault("p", {})["font-size"] = props["font-size"]
        else:
            print(f"pages[{page}].body_font_size 非法，已忽略：{fs!r}"
                  "（只要绝对 pt，如 10.5pt）")
    lh = entry.get("body_line_height")
    if lh is not None and str(lh).strip():
        if re.match(r"^\s*[\d.]+\s*$", str(lh)):
            props["line-height"] = str(lh).strip()
            if ("p", "line-height") not in explicit:
                theme.tags.setdefault("p", {})["line-height"] = props["line-height"]
        else:
            print(f"pages[{page}].body_line_height 非法，已忽略：{lh!r}")
    return theme


def ensure_page_typography(theme, page, page_presets):
    """渲染器入口：若该 theme 尚未按同一 (page, presets) 应用过纸张排版则应用一次。

    CLI 在 `font_scale` **之前**已调用 `apply_page_typography`（缩放要基于纸张基准）；
    此时标记命中直接跳过，避免在缩放之后被纸张值重置。库直接调用渲染器（无标记）
    则在此应用，使直接调用也能按纸张生效。
    """
    if getattr(theme, "_page_typography_applied", None) == (page, id(page_presets)):
        return theme
    return apply_page_typography(theme, page, page_presets)


def resolve_page(name: str, page_presets: Optional[Dict] = None) -> Dict:
    """把 --page 名字解析成页面配置。

    返回 {size: [w_mm, h_mm], margins: {top,right,bottom,left} mm,
          latin_font: 西文字体}。
    presets.json 的 pages 优先（键大小写不敏感）；否则回退内置 BUILTIN_PAGES/a4。
    边距 custom_margins（用户改的）> margins（预设自带）> 25.4 默认；
    兜底字号不走这里（跟主题 base，见 Theme.base_pt）。
    """
    p = _lookup_ci(page_presets or {}, name)
    if not p:
        p = dict(_lookup_ci(BUILTIN_PAGES, name) or BUILTIN_PAGES["a4"])
    margins = dict(p.get("custom_margins") or p.get("margins") or {})
    for k in ("top", "right", "bottom", "left"):
        margins.setdefault(k, 25.4)
    return {
        "size": list(p.get("size") or BUILTIN_PAGES["a4"]["size"]),
        "margins": margins,
        "latin_font": p.get("latin_font", "Calibri"),
    }

_ALIGN_MAP = {"center": "center", "left": "left", "right": "right", "justify": "both"}


class Theme:
    def __init__(self, tags: Optional[Dict[str, Dict[str, str]]] = None,
                 raw_css: str = "", lang: str = "zh-Hant"):
        self.lang = lang if lang in ("zh-Hant", "zh-Hans") else "zh-Hant"
        # 默认值唯一定义处 = pdf_docx.css（无 Python DEFAULT_THEME 兜底）。
        # 缺省读出厂 CSS；CSS 规则即 tags（DOCX）+ raw_css（HTML/PDF）。
        if not raw_css and os.path.isfile(_DEFAULT_CSS):
            try:
                with open(_DEFAULT_CSS, encoding="utf-8") as f:
                    raw_css = f.read()
            except OSError:
                raw_css = ""
        if raw_css:
            parsed, compounds = self._parse_css_tags(raw_css, self.lang)
        else:
            parsed, compounds = {}, []
        merged: Dict[str, Dict[str, str]] = \
            {tag: dict(props) for tag, props in parsed.items()}
        if tags:
            for tag, props in tags.items():
                merged.setdefault(tag, {}).update(props)
        self.tags = merged
        self.compounds = compounds
        # 显式来源：CSS 解析出的 (tag, prop) + 构造参数（默认值即 CSS，不再区分）。
        # 供 apply_page_typography 判定 p 是否"亲笔写过"（写过则纸张不覆盖它）。
        explicit = {(t, k) for t, props in parsed.items() for k in props}
        if tags:
            explicit |= {(t, k) for t, props in tags.items() for k in props}
        self._explicit = explicit
        # 字体变量（CSS :root 双栏，active lang 代入）：缺 font-family 的标签
        # 按变量表填充；CSS 已指定的不覆盖（与旧缺省填充同语义）。
        hant, hans = resolve_font_vars(raw_css)
        self._font_vars = dict(hant)
        if self.lang == "zh-Hans":
            self._font_vars.update(hans)
        default_rules = []
        for suffix, tag in FONT_VAR_TAGS.items():
            v = self._font_vars.get("--font-" + suffix)
            if not v:
                continue
            target = merged.setdefault(tag, {})
            if not target.get("font-family"):
                target["font-family"] = v
                sel = TAG_SELECTOR.get(tag)
                formatted = _format_font_stack(v)
                if sel and formatted:
                    default_rules.append(f"{sel} {{ font-family: {formatted}; }}")
        for suffix, (anc, tgt) in FONT_VAR_COMPOUNDS.items():
            v = self._font_vars.get("--font-" + suffix)
            if not v:
                continue
            self._set_compound_font(
                anc, tgt, v,
                f"{TAG_SELECTOR.get(anc, anc)} "
                f"{TAG_SELECTOR.get(tgt, tgt).split(',')[0].strip()}",
                overwrite=False)
        if default_rules:
            extra = "\n".join(default_rules)
            raw_css = (raw_css + "\n" + extra) if raw_css else extra
        self.raw_css = raw_css

    def font_var(self, suffix: str, default: str = "") -> str:
        """active lang 的 --font-<suffix> 值（如 latin）；缺省 default。"""
        v = (self._font_vars or {}).get("--font-" + suffix)
        return v if v else default

    def base_pt(self, fallback: float = FALLBACKS["base_pt"]) -> float:
        """基准字号：body → p 的绝对 pt；找不到回 fallback。
        单源：body{font-size} 为唯一源（p 继承）；DOCX em 换算与文档默认锚定它。
        注意只认绝对 pt（em 基准必须保持绝对，否则复利）；body 优先于 p，
        否则 p 的 DEFAULT 默认值（12pt）会盖住 body 显式值。"""
        for tag in ("body", "p"):
            m = re.match(r"^\s*([\d.]+)\s*pt\s*$",
                         (self.tags.get(tag) or {}).get("font-size") or "")
            if m:
                return float(m.group(1))
        return fallback

    @staticmethod
    def _parse_css_tags(css_text: str, lang: str = "zh-Hant"):
        """解析 CSS → (tags, compounds)。
        tags: 精确选择器 → 标签属性（供 DOCX）；compounds: 两段后代 `A B` 列表
        [(anc_tag, tgt_tag, props, selector)]（A 须在祖先栈、B 为栈顶时覆盖，CSS 后定义优先）。
        三段及以上、属性选择器等无法解析的精确选择器忽略（仍保留在 raw CSS 文本供 HTML/PDF）。

        TRANSLATABLE 之外的声明（如 display）不进 tags（仍保留在 raw 文本）。
        """
        import tinycss2
        hant, hans = resolve_font_vars(css_text)
        active = dict(hant)
        if lang == "zh-Hans":
            active.update(hans)
        tags: Dict[str, Dict[str, str]] = {}
        compounds = []
        rules = tinycss2.parse_stylesheet(css_text, skip_comments=True,
                                          skip_whitespace=True)
        for rule in rules:
            if rule.type != "qualified-rule":
                continue
            sel = tinycss2.serialize(rule.prelude).strip()
            decls = {}
            for d in tinycss2.parse_declaration_list(rule.content):
                if d.type == "declaration" and d.name in TRANSLATABLE:
                    decls[d.name] = _subst_vars(
                        tinycss2.serialize(d.value).strip(), active)
            if not decls:
                continue
            for part in sel.split(","):
                part = part.strip()
                tag = _SELECTOR_TAGS.get(part)
                if tag:
                    tags.setdefault(tag, {}).update(decls)
                    continue
                # 后代选择器：全段可解析时记录（祖先按序，供 CSS 式逐层继承）
                bits = part.split()
                if len(bits) == 2:
                    anc = _SELECTOR_TAGS.get(bits[0])
                    tgt = _SELECTOR_TAGS.get(bits[1])
                    if anc and tgt:
                        compounds.append((anc, tgt, dict(decls), part))
                elif len(bits) > 2:
                    anc_tags = [_SELECTOR_TAGS.get(b) for b in bits[:-1]]
                    tgt = _SELECTOR_TAGS.get(bits[-1])
                    if tgt and all(anc_tags):
                        compounds.append((tuple(anc_tags), tgt, dict(decls), part))
        return tags, compounds

    @classmethod
    def from_css(cls, css_text: str, lang: str = "zh-Hant") -> "Theme":
        """Parse a user CSS file into a Theme (CSS kept for HTML/PDF, tags for DOCX)."""
        return cls(raw_css=css_text, lang=lang)  # __init__ 内解析 tags + compounds（与旧版合并结果一致）

    def css(self) -> str:
        out = []
        for tag, props in self.tags.items():
            sel = TAG_SELECTOR.get(tag)
            if not sel or not props:
                continue
            rule = "; ".join(f"{k}: {v}" for k, v in props.items() if v)
            out.append(f"{sel} {{ {rule} }}")
        for _anc, _tgt, cprops, selector in self.compounds:
            rule = "; ".join(f"{k}: {v}" for k, v in cprops.items() if v)
            if rule:
                out.append(f"{selector} {{ {rule} }}")
        return "\n".join(out)

    def scale_font_sizes(self, factor: float) -> "Theme":
        """等比缩放全部标签字号（仅绝对单位 pt；em/% 相对单位随基准自动放大，不在此乘）。
        用于大字版；版心/边距不动。

        - DOCX: tags 的 font-size 直接参与 docx_run/docx_para
        - PDF/HTML: 同步追加逐标签 font-size 覆盖规则到 raw_css
        只调用一次（重复调用会复利叠加）。
        """
        try:
            factor = float(factor)
        except (TypeError, ValueError):
            raise ValueError(f"invalid font-scale: {factor!r}")
        if factor <= 0:
            raise ValueError(f"invalid font-scale: {factor!r}")
        if factor == 1.0:
            return self
        for props in self.tags.values():
            _scale_font_dict(props, factor)
        for _anc, _tgt, cprops, _sel in self.compounds:
            _scale_font_dict(cprops, factor)
        rules = []
        for tag, props in self.tags.items():
            sel = TAG_SELECTOR.get(tag)
            if sel and props.get("font-size"):
                rules.append(f"{sel} {{ font-size: {props['font-size']}; }}")
        if rules:
            extra = "\n".join(rules)
            self.raw_css = (self.raw_css + "\n" + extra) if self.raw_css else extra
        return self

    def _set_compound_font(self, anc, tgt, font, selector, overwrite):
        """compound 字体写入：overwrite=False 时已有 font-family 的不覆盖
        （CSS 文件明确指定优先）；无匹配项则追加。"""
        for c in self.compounds:
            if c[0] == anc and c[1] == tgt:
                if overwrite or not c[2].get("font-family"):
                    c[2]["font-family"] = font
                return
        self.compounds.append((anc, tgt, {"font-family": font}, selector))

    def _props(self, *tags: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for t in tags:
            out.update(self.tags.get(t) or {})
        return self._apply_compounds(out, tags)

    def _apply_compounds(self, props: Dict[str, str], tags) -> Dict[str, str]:
        """后代选择器：target = 栈顶标签。
        - 两段 `A B`：A 在祖先中出现即生效（anc 为 str）。
        - 三段+ `A B C`：祖先按序出现（anc 为 tuple；CSS 后代语义）。
        后定义的规则后应用（CSS 顺序优先）。"""
        if not self.compounds or not tags:
            return props
        target = tags[-1]
        ancestors = set(tags[:-1])
        for anc, tgt, cprops, _sel in self.compounds:
            if tgt != target:
                continue
            if isinstance(anc, tuple):
                seq = list(tags[:-1])
                i = 0
                ok = True
                for a in anc:
                    while i < len(seq) and seq[i] != a:
                        i += 1
                    if i >= len(seq):
                        ok = False
                        break
                    i += 1
                if ok:
                    props.update(cprops)
            elif anc in ancestors:
                props.update(cprops)
        return props

    def docx_run(self, *tags: str, base_pt: Optional[float] = None,
                 latin: Optional[str] = None) -> str:
        """Inner run-level properties (no <w:rPr> wrapper), merging across tags.

        base_pt: 所在段落字号，用于把 em 字号换算成 pt（1em == base_pt）。
        latin: 西文字体（w:ascii/w:hAnsi，默认 --font-latin）；缺省回落首个
        font-family 名（旧行为，供不经渲染器的调用方）。eastAsia 恒取首个中文字体名，
        与 pdf_docx.css 头注释「DOCX 只取首个中文字体作 eastAsia，西文另走 --font-latin」
        一致。不加 w:hint="eastAsia"：带附加符号的拉丁字母（ā ī 等 EAW=A，
        见「舍衛【大】，～Sāvatthī」）会因 hint 被判给 eastAsia 而落中文字体；
        不带 hint 时按 Unicode script 走 hAnsi=西文字体（CJK 全角标点仍是 eastAsia）。
        """
        props = self._props(*tags)
        out = []
        base = base_pt if base_pt is not None else self.base_pt()
        pt = _abs_pt(props.get("font-size"), base)
        if pt is not None:
            # round（非 int 截断）：em 写法精确还原（如 1.333em@12→32）；
            # 附带 0.9em 由 21 变 22（10.5→11pt，注音小字类，目检确认）
            half = round(pt * 2)
            out.append(f'<w:sz w:val="{half}"/><w:szCs w:val="{half}"/>')
        if props.get("font-weight") == "bold":
            out.append("<w:b/>")
        color = _hex6(props.get("color"))
        if color:
            out.append(f'<w:color w:val="{color}"/>')
        font = props.get("font-family")
        if font:
            names = [n.strip().strip('"').strip("'") for n in font.split(",")]
            names = [n for n in names if n]
            if names:
                latin_name = (latin or "").strip().strip('"').strip("'") or names[0]
                out.append(f'<w:rFonts w:ascii="{latin_name}" w:eastAsia="{names[0]}" '
                           f'w:hAnsi="{latin_name}"/>')
        return "".join(out)

    def _em_to_twips(self, em: float, font_pt: float) -> int:
        # 1em == font-size; 1pt == 20 twips
        return int(em * font_pt * 20)

    @staticmethod
    def _parse_margin(value: str) -> Dict[str, float]:
        """Parse CSS margin shorthand (1-4 em values) into {top,right,bottom,left}."""
        vals = value.split()
        out = {}

        def em(s):
            m = re.match(r"([\d.]+)em", s)
            return float(m.group(1)) if m else 0.0

        if not vals:
            return out
        if len(vals) == 1:
            out.update(top=em(vals[0]), bottom=em(vals[0]), left=em(vals[0]))
        elif len(vals) == 2:
            out.update(top=em(vals[0]), bottom=em(vals[0]), left=em(vals[1]))
        elif len(vals) == 3:
            out.update(top=em(vals[0]), left=em(vals[1]), bottom=em(vals[2]))
        else:
            out.update(top=em(vals[0]), bottom=em(vals[2]), left=em(vals[3]))
        return out

    def docx_para(self, *tags: str, indent_em: float = 0, no_first_line: bool = False) -> str:
        """Paragraph properties (w:pPr inner), in OOXML schema order:
        spacing -> ind -> jc. Returns ''.join when a key missing.
        合并时 div 标签（靠前）的段落属性优先于 p（靠后），
        使 div.div-xu 的 margin-top 等能覆盖到其内段落。后代选择器最后覆盖。"""
        props: Dict[str, str] = {}
        for t in reversed(tags):
            props.update(self.tags.get(t) or {})
        props = self._apply_compounds(props, tags)
        base = self.base_pt()
        # em 边距/缩进的基准是元素自身解算字号（未知则 base），与 docx_run 一致
        font_pt = _abs_pt(props.get("font-size"), base) or base
        parts = {}
        spacing_attrs = []
        lh = props.get("line-height")
        if lh is None and "body" not in tags:
            # CSS 层叠：无本标签行距时继承 body（与浏览器/PDF 一致；
            # 2026-09-06 实锤 DOCX 曾全员单倍、PDF 按 1.8，两边打架）
            lh = (self.tags.get("body") or {}).get("line-height")
        m = re.match(r"([\d.]+)", lh or "")
        if m:
            # CSS line-height -> Word "N 倍行距" (240 = 单倍)
            spacing_attrs.append(f'w:line="{int(float(m.group(1)) * 240)}" '
                                 f'w:lineRule="auto"')
        mgn = self._parse_margin(props.get("margin") or "")
        for css_prop, key in (("margin-top", "top"), ("margin-bottom", "bottom")):
            v = props.get(css_prop)
            mm = re.match(r"([\d.]+)em", v or "")
            if mm:
                mgn[key] = float(mm.group(1))
        if "top" in mgn:
            spacing_attrs.append(f'w:before="{self._em_to_twips(mgn["top"], font_pt)}"')
        if "bottom" in mgn:
            spacing_attrs.append(f'w:after="{self._em_to_twips(mgn["bottom"], font_pt)}"')
        if spacing_attrs:
            parts["spacing"] = f"<w:spacing {' '.join(spacing_attrs)}/>"
        ind_parts = []
        ti = None if no_first_line else props.get("text-indent")
        m = re.match(r"([\d.]+)em", ti or "")
        if m:
            ind_parts.append(f'w:firstLine="{self._em_to_twips(float(m.group(1)), font_pt)}"')
        ind_left = indent_em
        ml = props.get("margin-left")
        m = re.match(r"([\d.]+)em", ml or "")
        if m:
            ind_left += float(m.group(1))
        if "left" in mgn:
            ind_left += mgn["left"]
        if ind_left:
            ind_parts.append(f'w:left="{self._em_to_twips(ind_left, font_pt)}"')
        if ind_parts:
            parts["ind"] = f"<w:ind {' '.join(ind_parts)}/>"
        align = props.get("text-align")
        if align and align in _ALIGN_MAP:
            parts["jc"] = f'<w:jc w:val="{_ALIGN_MAP[align]}"/>'
        return "".join(parts[k] for k in ("spacing", "ind", "jc") if k in parts)
