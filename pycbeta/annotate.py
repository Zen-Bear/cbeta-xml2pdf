"""难字注音（P6）：外部词表驱动，作用于正文 Text 节点与解析后缺字。

缺字（``<g>``）经 gaiji 解析出 Unicode 后走同一注音管线（词表单字匹配+生僻字兜底）；
未解析的 PUA 码、图片、校勘记/题署不注（标题块由各渲染器 ``_no_ann`` 压制）。

词表格式（TSV，无表头，UTF-8）::

    词语<TAB>拼音<TAB>注音

``#`` 开头为注释行，空行跳过。词形列必须与渲染文本逐字一致
（含繁简：t2s 先行，注音匹配发生在 simplfiy/gaiji 解析之后）。
某列缺失时，该 scheme 下该词不注音。

渲染器约定：``annotations`` 参数为 ``None`` 或已规整的 ``{"table", "scheme",
"style", "brackets", "rt_size", "rt_font", "ruby_up", "repeat",
"rare_zones", "rare_all", "rare_cmap"}``；
文件装载只发生在 CLI 入口（``resolve_annotations``），渲染器内部不做 IO，
第三方调用同样先调 ``resolve_annotations`` 再传入。

自动注音（词表之外）：``rare_zones`` 为分区 frozenset（空=关闭，如 {"G","H"}），
``rare_cmap`` 为补充字形码位集，二者为"或"关系，词表优先；
读音取 pypinyin，未收录时回退到 CBETA gaiji 的规范化字（norm_big5_char/norm_uni_char/
norm_unicode）取音（如 𭣛→變→biàn）；与词表同样受 first/page 去重（同页只注首次）。
``rare_all`` 为 True 时全文逐字注音（忽略词表与 repeat，专音必错，慎用）。

``style`` 为注音位置：``ruby`` = 汉字上方（html/epub ``<ruby>``、docx ``w:ruby``，
仅浏览器/Word 可见）；``inline`` = 汉字右侧行内（各格式统一 ``X〔注音〕`` 式括注，
所有阅读器可见）；``field`` = 汉字上方 EQ 拼音指南域（docx 专用，WPS/Word 可见，
html 回退 ``<ruby>``，md 回退行内括注；LibreOffice 下仍建议 ``inline``）。
默认 ``inline``（宁丑勿丢）。md 无上方注音，恒为行内。
``brackets`` 为右侧注音括号一对单字（默认 ``["〔", "〕"]``）；verify 侧剥除规则见
``verify.normalize``（默认对透明；自定义符号仅读音字符内容被剥除，正文/校勘括号不受影响）。
"""
import os
import re
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TABLE = os.path.join(_HERE, "data", "annotations.txt")

SCHEMES = ("pinyin", "zhuyin")
STYLES = ("ruby", "inline", "field")
REPEATS = ("all", "first", "page")
DEFAULT_BRACKETS = ["〔", "〕"]
DEFAULT_RT_SIZE = "50%"
DEFAULT_RUBY_UP = "100%"

# CJK 扩展区分区（A–I；I 在数值上位于 F 与 G 之间，故分区选择不用码位阈值）
_ZONE_RANGES = {
    "A": [(0x3400, 0x4DBF)],
    "B": [(0x20000, 0x2A6DF)],
    "C": [(0x2A700, 0x2B73F)],
    "D": [(0x2B740, 0x2B81F)],
    "E": [(0x2B820, 0x2CEAF)],
    "F": [(0x2CEB0, 0x2EBEF)],
    "G": [(0x30000, 0x3134F)],
    "H": [(0x31350, 0x323AF)],
    "I": [(0x2EBF0, 0x2EE5F)],
}


def valid_brackets(value):
    """右侧注音括号：一对单字 [左, 右］；非法回退默认〔〕（verify 侧复用）。"""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        l, r = value
        if isinstance(l, str) and isinstance(r, str) and len(l) == 1 and len(r) == 1:
            return [l, r]
    return list(DEFAULT_BRACKETS)


def parse_rt_size(value, base_pt):
    """注音字号 → pt（float）。"60%"=相对所在段落字号；"7pt"/纯数字=绝对磅值；非法→None（走默认）。"""
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r"^([\d.]+)\s*%\s*$", s)
    if m:
        try:
            return base_pt * float(m.group(1)) / 100.0
        except ValueError:
            return None
    m = re.match(r"^([\d.]+)\s*(pt)?\s*$", s, re.I)
    if m:
        try:
            v = float(m.group(1))
            return v if v > 0 else None
        except ValueError:
            return None
    return None


_RT_SIZE_RE = re.compile(r"^[\d.]+\s*(%|pt)?\s*$", re.I)


def rt_css_rule(ann):
    """html <style> 附加规则：ruby style 时输出 `ruby rt{font-size; font-family}`，
    行内模式无 rt 元素则不输出。非法值跳过（防 CSS 注入）。"""
    if (ann or {}).get("style", "inline") != "ruby":
        return ""
    decls = []
    rs = (ann or {}).get("rt_size", DEFAULT_RT_SIZE)
    if isinstance(rs, str) and _RT_SIZE_RE.match(rs.strip()):
        decls.append(f"font-size: {rs.strip()}")
    rf = (ann or {}).get("rt_font") or ""
    if isinstance(rf, str) and rf.strip():
        safe = re.sub(r'[";{}]', "", rf.strip())
        if safe:
            decls.append(f'font-family: "{safe}"')
    if not decls:
        return ""
    return "\n    ruby rt { " + "; ".join(decls) + " }"


def parse_rare_zones(value):
    """生僻区分区 → frozenset（如 {"G","H"}），空输入/全非法 → 空集（关闭）。
    接受 "G" / "B,C" / ["G", "H"]；兼容 "Ext G" / "CJK Ext G" 前缀（大小写不敏感）；
    非法项（含 All）忽略——全文注音走独立的 full_text 开关。"""
    zones = set()
    items = []
    if isinstance(value, str):
        items = re.split(r"[,;\s]+", value)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for v in value:
            items += re.split(r"[,;\s]+", str(v))
    for it in items:
        s = re.sub(r"^(CJK\s*)?(EXT\s*)?", "", it.strip().upper())
        if s in _ZONE_RANGES:
            zones.add(s)
    return frozenset(zones)


def in_rare_zones(cp, zones):
    """码位是否落在所选分区内。"""
    return any(lo <= cp <= hi for z in zones for lo, hi in _ZONE_RANGES[z])


_READING_CACHE = {}

# 规范化字回退表（缺字码位 → 规范化字形候选）：pypinyin 未收录生僻字时，
# 用 CBETA gaiji 的 norm_big5_char / norm_uni_char / norm_unicode 取读音。
_NORM_ALT = None


def _norm_alts(char):
    """生僻字 → 规范化字形候选元组（懒建一次；失败空表）。"""
    global _NORM_ALT
    if _NORM_ALT is None:
        m = {}
        try:
            from .gaiji import GaijiDb
            for rec in GaijiDb().records():
                src = rec.get("uni_char")
                if not src:
                    continue
                alts = []
                for key in ("norm_big5_char", "norm_uni_char"):
                    v = rec.get(key)
                    if v and v != src:
                        alts.append(v)
                hexn = rec.get("norm_unicode")
                if hexn:
                    try:
                        ch = chr(int(hexn, 16))
                        if ch != src:
                            alts.append(ch)
                    except ValueError:
                        pass
                if alts:
                    m[src] = tuple(dict.fromkeys(alts))
        except Exception:  # noqa: BLE001 —— 缺库/损坏只关回退
            m = {}
        _NORM_ALT = m
    return _NORM_ALT.get(char, ())


def auto_reading(char, scheme="pinyin", review=True):
    """生僻字读音（pypinyin 按字取音）：未知字 → 规范化字回退 → None。
    多音字取最常用读音，可能不准（词表优先于此）。结果进程级常驻缓存
    （全文模式同字高频复用，避免重复查询）。
    review=True 时登记待审字（多音/未知，见 `_record_review`；全文模式不登记）。"""
    key = (char, scheme)
    if key in _READING_CACHE:
        return _READING_CACHE[key]
    rd = _auto_reading_uncached(char, scheme)
    if rd is None:
        for alt in _norm_alts(char):
            rd = _auto_reading_uncached(alt, scheme)
            if rd:
                break
    _READING_CACHE[key] = rd
    if review:
        _record_review(char, scheme)
    return rd


# 待审字登记（注音模式自动收集，供 CLI/GUI 落盘告知；渲染器零 IO，只记内存）
_REVIEW = {}  # char -> "unknown" | "polyphonic"
_REVIEW_CHECKED = set()  # 已评估过的 (char, scheme)，避免重复查 heteronym


def _record_review(char, scheme="pinyin"):
    """登记待审字：pypinyin 多音（heteronym>1，保留最常用读音行为）或无收录。
    pypinyin 缺失时无法判断，静默跳过。"""
    key = (char, scheme)
    if key in _REVIEW_CHECKED:
        return
    _REVIEW_CHECKED.add(key)
    try:
        from pypinyin import pinyin, Style
    except ImportError:
        return
    try:
        style = Style.BOPOMOFO if scheme == "zhuyin" else Style.TONE
        rows = pinyin(char, style=style, heteronym=True)
        rds = [r.strip() for r in (rows[0] if rows else [])]
    except Exception:
        return
    if not rds or all(r.replace("˙", "") == char for r in rds):
        _REVIEW.setdefault(char, "unknown")
    elif len(set(rds)) > 1:
        _REVIEW.setdefault(char, "polyphonic")


def pending_review():
    """当前待审字（{字: unknown|polyphonic} 副本）。"""
    return dict(_REVIEW)


def clear_reviewed():
    """清空待审登记（单测/多轮运行时隔离用）。"""
    _REVIEW.clear()
    _REVIEW_CHECKED.clear()


def append_review_stubs(table_path):
    """待审字写入词表：空读音 stub 行（`字\\t\\t`；load_table 天然跳过空读音，
    零行为变化，用户填读音后下次生效）。已在表内不写；返回本次新增字符表。
    写失败返回 []，不抛异常（渲染器零 IO 约定：只由此入口落盘）。"""
    try:
        chars = [c for c, s in _REVIEW.items()
                 if s in ("unknown", "polyphonic")]
        if not chars or not table_path:
            return []
        have = set(load_table(table_path))
        new = [c for c in chars if c not in have]
        if not new:
            return []
        with open(table_path, "a", encoding="utf-8") as f:
            for c in new:
                f.write(f"{c}\t\t\n")
        return new
    except Exception:
        return []


def _auto_reading_uncached(char, scheme="pinyin"):
    try:
        from pypinyin import lazy_pinyin, Style
    except ImportError:
        return None
    try:
        style = Style.BOPOMOFO if scheme == "zhuyin" else Style.TONE
        out = lazy_pinyin(char, style=style)
    except Exception:
        return None
    if not out or len(out) != 1:
        return None
    rd = out[0].strip()
    # 未收录字：TONE 原样返回本字；BOPOMOFO 返回本字+˙——均视为未知
    if not rd or rd.replace("˙", "") == char:
        return None
    return rd


def _resolve_asset_path(path, config_path=None):
    """资源路径解析：空→None；原文存在→直接用；相对路径→先相对 config 所在目录，再相对包目录；否则 None。"""
    if not path:
        return None
    if os.path.isabs(path) and os.path.isfile(path):
        return path
    if os.path.isfile(path):
        return os.path.abspath(path)
    base = os.path.dirname(os.path.abspath(config_path)) if config_path else _HERE
    cand = os.path.join(base, path)
    if os.path.isfile(cand):
        return cand
    cand2 = os.path.join(_HERE, path)
    if os.path.isfile(cand2):
        return cand2
    return None


def _resolve_table_path(table, config_path=None):
    """空→内置表；其余走通用资源解析（缺失→None，由 load_table 判空）。"""
    if not table:
        return DEFAULT_TABLE
    return _resolve_asset_path(table, config_path)


_CMAP_CACHE = {}


def load_supplement_cmap(path=None, config_path=None):
    """补充字形 cmap → frozenset(码位)；路径空/文件缺失/无 fontTools → 空集（关闭）。
    按解析后绝对路径缓存（verify 逐本调 resolve 时不重复读盘）。"""
    fn = _resolve_asset_path(path, config_path)
    if not fn:
        return frozenset()
    if fn in _CMAP_CACHE:
        return _CMAP_CACHE[fn]
    cmap = frozenset()
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(fn, lazy=True)
        try:
            cmap = frozenset(tt.getBestCmap() or ())
        finally:
            try:
                tt.close()
            except Exception:
                pass
    except Exception:
        cmap = frozenset()
    _CMAP_CACHE[fn] = cmap
    return cmap


def load_table(path=None, config_path=None):
    """装载外部词表 → ``{词: {"pinyin": str, "zhuyin": str}}``；文件缺失返回 ``{}``。"""
    fn = _resolve_table_path(path, config_path)
    table = {}
    if not fn:
        return table
    with open(fn, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            term = parts[0].strip()
            if not term or term in table:
                continue
            table[term] = {
                "pinyin": parts[1].strip() if len(parts) > 1 else "",
                "zhuyin": parts[2].strip() if len(parts) > 2 else "",
            }
    return table


def resolve_annotations(spec, config_path=None):
    """规整 ``annotations`` 配置 → ``None`` 或 ``{"table", "scheme", "style", "brackets",
    "rt_size", "rt_font", "repeat", "rare_zones", "full_text", "rare_cmap"}``。

    ``spec`` 为 None/非 dict/``enabled`` 非真 → None（关闭）。
    表文件缺失或装载为空 → None（静默关闭，渲染走无注音路径）。
    未知 ``scheme`` → 回退 ``pinyin``；未知 ``style`` → 回退 ``inline``；
    非法 ``brackets`` → 回退默认〔〕。
    ``full_text`` 为 True 时全文注音（词表优先整词，其余逐字；忽略 zones/repeat）。
    """
    if not isinstance(spec, dict) or not spec.get("enabled"):
        return None
    scheme = spec.get("scheme", "pinyin")
    if scheme not in SCHEMES:
        scheme = "pinyin"
    style = spec.get("style", "inline")
    if style not in STYLES:
        style = "inline"
    table = load_table(spec.get("file"), config_path)
    if not table:
        return None
    rt_font = spec.get("rt_font") or ""
    rare_cmap = load_supplement_cmap(spec.get("rare_font"), config_path)
    if spec.get("rare_font") and not rare_cmap:
        print(f"annotations: 补充字形 {spec.get('rare_font')!r} 未载入（路径缺失/无 fontTools），仅分区自动生效")
    repeat = spec.get("repeat", "all")
    if repeat not in REPEATS:
        repeat = "all"
    zones = parse_rare_zones(spec.get("rare_zones"))
    return {"table": table, "scheme": scheme, "style": style,
            "brackets": valid_brackets(spec.get("brackets")),
            "rt_size": spec.get("rt_size", DEFAULT_RT_SIZE),
            "rt_font": rt_font if isinstance(rt_font, str) else "",
            "ruby_up": spec.get("ruby_up", DEFAULT_RUBY_UP),
            "repeat": repeat,
            "rare_zones": zones, "full_text": bool(spec.get("full_text", False)),
            "rare_cmap": rare_cmap}


def active(spec):
    """渲染器入口规整：已规整的 dict 原样返回（表为空则 None），其余 None。
    兼容旧键 ``docx_style``（ruby→ruby，其余→inline）。"""
    if isinstance(spec, dict):
        table = spec.get("table") or {}
        if not table:
            return None
        scheme = spec.get("scheme", "pinyin")
        if scheme not in SCHEMES:
            scheme = "pinyin"
        style = spec.get("style", spec.get("docx_style", "inline"))
        if style == "bracket":
            style = "inline"
        if style not in STYLES:
            style = "inline"
        rt_font = spec.get("rt_font") or ""
        zones = parse_rare_zones(spec.get("rare_zones"))
        cmap = spec.get("rare_cmap")
        if cmap is None and spec.get("rare_font"):
            cmap = load_supplement_cmap(spec.get("rare_font"))
        cmap = cmap if isinstance(cmap, (set, frozenset)) else frozenset()
        repeat = spec.get("repeat", "all")
        if repeat not in REPEATS:
            repeat = "all"
        return {"table": table, "scheme": scheme, "style": style,
                "brackets": valid_brackets(spec.get("brackets")),
                "rt_size": spec.get("rt_size", DEFAULT_RT_SIZE),
                "rt_font": rt_font if isinstance(rt_font, str) else "",
                "ruby_up": spec.get("ruby_up", DEFAULT_RUBY_UP),
                "repeat": repeat,
                "rare_zones": zones, "full_text": bool(spec.get("full_text", False)),
                "rare_cmap": cmap}
    return None


def _pattern(table, scheme):
    """最长优先：按词长降序交替，finditer 自带左到右非重叠语义。"""
    terms = sorted(
        (t for t, r in table.items() if t and r.get(scheme)),
        key=len, reverse=True,
    )
    if not terms:
        return None
    return re.compile("|".join(re.escape(t) for t in terms))


def repeat_mode(ann):
    """注音频率：all=每次都注（默认）；first=全文只注首次；page=每分页单元/卷文件首次。"""
    m = (ann or {}).get("repeat", "all")
    return m if m in REPEATS else "all"


def track_seen(ann, seen):
    """all → None（不过滤）；first/page → seen 集合（调用方负责重置时机：
    文档起始终置零；page 在 docx 分节/html 分卷文件起重置）。"""
    return seen if repeat_mode(ann) in ("first", "page") else None


def page_repeat(ann):
    """是否为按分页单元重置模式（docx 分节 / html 分卷文件 / md 整篇）。"""
    return repeat_mode(ann) == "page"


def _dedup(segs, seen):
    """已注词再次出现 → 去注音（保留原文）；seen 为 None 时原样返回。"""
    if seen is None:
        return segs
    out = []
    for seg, reading in segs:
        if reading is not None:
            if seg in seen:
                out.append((seg, None))
                continue
            seen.add(seg)
        out.append((seg, reading))
    return out


def split_eq_reading(term, reading):
    """EQ 域注音分配：WPS 原生为逐字域；读音按空格切音节，音节数==字数时逐字配对，
    否则整词 single 域兜底（读音含空格时 WPS 渲染效果未定，尽量少见）。"""
    chars = list(term)
    parts = reading.split()
    if len(chars) > 1 and len(parts) == len(chars):
        return list(zip(chars, parts))
    return [(term, reading)]


def split_annotated(text, table, scheme="pinyin", rare_zones=frozenset(),
                    rare_cmap=None, seen=None, full=False):
    """切分 ``[(片段, 注音或None)]``；无匹配/空表 → ``[(text, None)]``（空片段已过滤）。
    ``rare_zones`` 非空或 ``rare_cmap`` 非空时，未匹配片段内生僻字按字取音
    （pypinyin，词表优先）：码位落在所选分区，或落在补充字形 cmap 内。
    ``full`` 为 True 时全文注音：词表优先整词匹配，其余逐字取音，
    忽略 rare_zones/repeat（seen 不过滤）。
    ``seen`` 非空集合时，已注词去注音（repeat first/page 用，调用方维护集合）。"""
    if not text:
        return []
    if scheme not in SCHEMES:
        scheme = "pinyin"
    if full:
        return _split_full(text, table or {}, scheme)
    if not table:
        return [(text, None)]
    pat = _pattern(table, scheme)
    if pat is None:
        if not rare_zones and not rare_cmap:
            return [(text, None)]
        out = [(text, None)]
    else:
        out, pos = [], 0
        for m in pat.finditer(text):
            if m.start() > pos:
                out.append((text[pos:m.start()], None))
            out.append((m.group(0), table[m.group(0)][scheme]))
            pos = m.end()
        if pos < len(text):
            out.append((text[pos:], None))
        out = [(s, r) for s, r in out if s]
    if not rare_zones and not rare_cmap:
        return _dedup(out, seen)
    # 生僻字兜底：未匹配片段内逐字判定（读音进程级缓存）
    def allow(c):
        oc = ord(c)
        return (in_rare_zones(oc, rare_zones) or (rare_cmap and oc in rare_cmap)) \
            and unicodedata.category(c) == "Lo"
    return _dedup(_expand_chars(out, scheme, allow), seen)


def _expand_chars(out, scheme, allow, review=True):
    """未匹配片段按 allow(c) 逐字取音展开（词表匹配段原样保留）。
    review=False 时不登记待审字（全文模式：量大，专音必错已全局告知）。"""
    final = []
    for seg, reading in out:
        if reading is not None or not seg:
            if seg:
                final.append((seg, reading))
            continue
        buf = []
        for c in seg:
            if allow(c):
                rd = auto_reading(c, scheme, review=review)
                if rd:
                    if buf:
                        final.append(("".join(buf), None))
                        buf = []
                    final.append((c, rd))
                    continue
            buf.append(c)
        if buf:
            final.append(("".join(buf), None))
    return final


def _split_full(text, table, scheme):
    """全文注音：词表最长优先整词匹配（专音保留），其余 Lo 字符逐字取音；
    忽略 zones/repeat（seen 不过滤）。"""
    pat = _pattern(table, scheme) if table else None
    if pat is None:
        out = [(text, None)] if text else []
    else:
        out, pos = [], 0
        for m in pat.finditer(text):
            if m.start() > pos:
                out.append((text[pos:m.start()], None))
            out.append((m.group(0), table[m.group(0)][scheme]))
            pos = m.end()
        if pos < len(text):
            out.append((text[pos:], None))
        out = [(s, r) for s, r in out if s]
    return _expand_chars(out, scheme,
                         lambda c: unicodedata.category(c) == "Lo",
                         review=False)
