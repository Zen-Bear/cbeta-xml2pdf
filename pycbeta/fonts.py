"""字体查找与解析：系统字体 -> 用户字体 -> 随包 fonts/ 目录（优先级递减）。

移植自 CbetaPdfEngine.Core 的 FontLocator / FontNameReader / UserFontInstaller 设计：
- CJK 字体的 name 表常只存英文名，而 GDI/WPS/LibreOffice 按本地化中文名匹配，
  故索引时同时登记中英文别名（kaiti<->楷体、simsun<->宋体…）。
- 经验修正：標楷體 在 Windows 上的 GDI 名是 DFKai-SB。
"""

import os
import struct
from pathlib import Path

FONT_EXTS = (".ttf", ".otf", ".ttc")

# 常见 CJK 字体的中英文名对应（键为规范化英文名）
_ZH_ALIASES = {
    "kaiti": "楷體",
    "pmingliu": "新細明體",
    "mingliu": "細明體",
    "simsun": "宋體",
    "nsimsun": "新宋体",
    "simhei": "黑体",
    "simfang": "仿宋",
    "fangsong": "仿宋",
    "dengxian": "等线",
    "microsoftyahei": "微软雅黑",
    "msjh": "微軟正黑體",
    "msjhbd": "微軟正黑體",
    "msjhl": "微軟正黑體 Light",
}

# GDI 可见名 与 LibreOffice/WPS 可匹配名的经验对照
_CANONICAL_NAMES = {
    "biaukai": "DFKai-SB",
    "dfkaisb": "DFKai-SB",
    "dfkaishusbestdbf": "DFKai-SB",
    "標楷體": "DFKai-SB",
    "正楷體": "DFKai-SB",
}


def _normalize(name: str) -> str:
    buf = []
    for ch in name:
        if ch.isalnum() or ord(ch) > 0x2E80:
            buf.append(ch.lower())
    return "".join(buf)


def _has_cjk(s: str) -> bool:
    return any(ord(c) > 0x2E80 for c in (s or ""))


_syslang_cache = {"env": None, "lang": "unset"}


def _system_lang():
    """本机系统语言 ID（如简体中文 Windows → 0x804；取不到 → None）。
    PYCBETA_UI_LANG 可覆盖（0x804 或 804，单测用）；带缓存，env 变则重取。"""
    ov = os.environ.get("PYCBETA_UI_LANG", "").strip()
    if _syslang_cache["env"] == ov and _syslang_cache["lang"] != "unset":
        return _syslang_cache["lang"]
    lang = None
    if ov:
        try:
            lang = int(ov, 16) if ov.lower().startswith("0x") else int(ov)
        except ValueError:
            lang = None
    if lang is None:
        try:
            import ctypes
            lang = ctypes.windll.kernel32.GetSystemDefaultUILanguage()
        except Exception:
            lang = None
    _syslang_cache.update(env=ov, lang=lang)
    return lang


_WARNED_CANON = set()


def _note_canon(orig, new):
    if new != orig and (orig, new) not in _WARNED_CANON:
        _WARNED_CANON.add((orig, new))
        print(f"字体：{orig!r} 按本机 GDI 可见名归一为 {new!r}")
    return new


def read_family_names(path: str) -> list:
    """解析 TTF/TTC 的 name 表，返回家族名列表（nameId 1/16）。
    取名优先级（逐字重）：nameId 16(全名) > 1(家族)；platform 3(Windows) > 0 > 1；
    TTC 按字重拼接（与旧行为一致）。"""
    with open(path, "rb") as f:
        data = f.read()
    # 取名优先级：nameId 16(全名) > 1(家族)；platform 3(Windows) > 0 > 1
    results = []
    for off in _face_offsets(data):
        try:
            records = _read_names_at(data, off)
        except Exception:
            continue
        for nid in (16, 1):
            for pid in (3, 0, 1):
                for r_name, r_pid, _lang, r_val in records:
                    if r_name == nid and r_pid == pid and r_val not in results:
                        results.append(r_val)
    return results


def _read_names_at(data: bytes, header_offset: int) -> list:
    """单字体 name 表原始记录 → [(nameId, platformId, langId, value)]，保文件序。"""
    num_tables = struct.unpack_from(">H", data, header_offset + 4)[0]
    name_off = 0
    for i in range(num_tables):
        rec = header_offset + 12 + 16 * i
        tag = data[rec:rec + 4]
        offset = struct.unpack_from(">I", data, rec + 8)[0]
        if tag == b"name":
            name_off = offset
            break
    if not name_off:
        return []

    count = struct.unpack_from(">H", data, name_off + 2)[0]
    storage = name_off + struct.unpack_from(">H", data, name_off + 4)[0]
    records = []  # (nameId, platformId, langId, value)，保文件序
    for i in range(count):
        rec = name_off + 6 + 12 * i
        if rec + 12 > len(data):
            break
        platform_id, _enc, lang_id, name_id, length, off = struct.unpack_from(">6H", data, rec)
        if name_id not in (1, 16):
            continue
        raw = data[storage + off: storage + off + length]
        try:
            value = (raw.decode("utf-16-be") if platform_id in (0, 3)
                     else raw.decode("latin-1"))
        except Exception:
            continue
        if value:
            records.append((name_id, platform_id, lang_id, value))
    return records


def _face_offsets(data: bytes) -> list:
    """TTF → [0]；TTC → 各字重表头偏移（坏文件 → []，不抛）。"""
    if len(data) < 12:
        return []
    try:
        if struct.unpack_from(">I", data, 0)[0] == 0x74746366:  # 'ttcf'
            count = struct.unpack_from(">I", data, 8)[0]
            return [struct.unpack_from(">I", data, 12 + 4 * i)[0]
                    for i in range(min(count, 64))]
        return [0]
    except Exception:
        return []


def _font_records(data: bytes) -> list:
    """TTF/TTC 全字重 name 原始记录 → [(face, nameId, platformId, langId, value)]
    （坏文件 → []，不抛）。face 为字重序号（TTF 恒 0）。"""
    out = []
    for face, off in enumerate(_face_offsets(data)):
        try:
            for nid, pid, lang, val in _read_names_at(data, off):
                out.append((face, nid, pid, lang, val))
        except Exception:
            pass
    return out


def read_family_lang_names(path: str) -> list:
    """nameId 1 → [(face, langId, value)]（保文件序，去重；供 GDI 可见名归一）。
    同一字体繁/简拼写并存时（如霞鹜文楷 TC 的 0x404 鶩 U+9DA9 与 0x804 鹜 U+9E5C），
    OOXML 精确匹配要求写 GDI 实际暴露的那个，否则 Word/WPS 回退宋体。
    face 用于同字重取英文名（多字重 TTC 不能串字重）。"""
    with open(path, "rb") as f:
        data = f.read()
    seen = set()
    ret = []
    for face, nid, _pid, lang, val in _font_records(data):
        if nid != 1 or (face, lang, val) in seen:
            continue
        seen.add((face, lang, val))
        ret.append((face, lang, val))
    return ret


class FontLocator:
    """字体索引：家族名（含别名）-> 字体文件路径。

    查找优先级（后扫不覆盖先扫）：Windows 系统字体（权威）->
    用户安装字体 -> extra_dirs（如项目 fonts/ 缺字库目录）。
    """

    def __init__(self, extra_dirs=(), scan_system=True):
        self._index = {}          # 规范化名 -> 路径
        self._families_by_path = {}
        self._lang_families_by_path = {}  # 路径 -> [(face, langId, nameId1)]
        dirs = list(extra_dirs)
        if scan_system:
            windir = os.environ.get("WINDIR", r"C:\Windows")
            dirs = [
                os.path.join(windir, "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
                *dirs,
            ]
        first = True
        for d in dirs:
            if d and os.path.isdir(d):
                self._scan(d, overwrite=first)
            first = False

    def _scan(self, directory: str, overwrite: bool):
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                if not fn.lower().endswith(FONT_EXTS):
                    continue
                path = os.path.join(root, fn)
                families = read_family_names(path)
                keys = [_normalize(f) for f in families]
                stem = _normalize(os.path.splitext(fn)[0])
                if stem:
                    keys.append(stem)
                for key in keys:
                    if key:
                        self._add(key, path, overwrite)
                for key in keys:
                    zh = _ZH_ALIASES.get(key)
                    if zh:
                        self._add(_normalize(zh), path, overwrite)
                if families:
                    self._families_by_path[path] = families
                    try:
                        _langs = read_family_lang_names(path)
                    except (OSError, ValueError):
                        _langs = []
                    if _langs:
                        self._lang_families_by_path[path] = _langs

    def _add(self, key, path, overwrite):
        if overwrite or key not in self._index:
            self._index[key] = path

    def exists(self, family: str) -> bool:
        return bool(family) and _normalize(family) in self._index

    def path(self, family: str):
        """家族名 → 字体文件路径（未找到返回 None）。"""
        if not family:
            return None
        return self._index.get(_normalize(family))

    def preferred_family(self, family: str) -> str:
        """返回该字体在本机最易被 Word/WPS 匹配的家族名；字体不存在时原样返回。

        OOXML 字体匹配是精确字符串比对：同一字体繁/简拼写并存时（如霞鹜文楷 TC
        的 0x404 鶩 U+9DA9 与 0x804 鹜 U+9E5C），必须写 GDI 实际暴露的那个
        （跟系统语言走），否则回退宋体——WPS 字名框照抄 run 值，看着对、渲不对。
        显式经验对照（DFKai-SB 类）优先；纯英文名原样返回（各地都可解）。
        改名时打印一次（stdout），方便发现 CSS 名与本机拼写不一致。"""
        if not family:
            return family
        path = self._index.get(_normalize(family))
        if not path:
            return family
        candidates = list(self._families_by_path.get(path, []))
        candidates.append(os.path.splitext(os.path.basename(path))[0])
        candidates.append(family)
        for c in candidates:
            canon = _CANONICAL_NAMES.get(_normalize(c))
            if canon:
                return _note_canon(family, canon)
        recs = self._lang_families_by_path.get(path, [])
        norm = _normalize(family)
        infaces = {f for f, _l, v in recs if _normalize(v) == norm}
        sysname = self._system_lang_name(path, family)
        if sysname and _normalize(sysname) != norm and _has_cjk(family):
            return _note_canon(family, sysname)
        for c in candidates:
            # 別名只看输入命中的字重，防止 TTC 串字重（如 MingLiU/PMingLiU）；
            # 输入未命中任何字重（如纯文件名解析）时不限。
            if infaces and not {f for f, _l, v in recs
                                if _normalize(v) == _normalize(c)} & infaces:
                continue
            zh = _ZH_ALIASES.get(_normalize(c))
            if not zh:
                continue
            # 別名必须在文件中有记录（否则 GDI 不可见，写了比原文更糟）
            if not any(_normalize(v) == _normalize(zh) for _f, _l, v in recs):
                continue
            _zh_sys = self._system_lang_name(path, zh)
            if _has_cjk(zh) and _zh_sys \
                    and _normalize(_zh_sys) != _normalize(zh):
                return _note_canon(family, _zh_sys)  # 別名繁简与本机不一致时跟本机
            return _note_canon(family, zh)
        return family

    def _system_lang_name(self, path, family):
        """该字体与本机系统语言对应的 nameId1（无 → None）。

        同字重优先：输入命中的字重内找系统语言名（如 PMingLiU 字重不出 MingLiU），
        命中字重内无时才回退全文件首个（单字重 TTF 无此问题）。"""
        syslang = _system_lang()
        if syslang is None:
            return None
        recs = self._lang_families_by_path.get(path, [])
        norm = _normalize(family)
        faces = {f for f, _l, v in recs if _normalize(v) == norm}
        cands = [(f, v) for f, l, v in recs
                 if l == syslang and (not faces or f in faces)]
        if not cands and faces:
            cands = [(f, v) for f, l, v in recs if l == syslang]
        for _f, v in cands:
            if v:
                return v
        return None


_locator = None


def locator(extra_dirs=()) -> FontLocator:
    global _locator
    if _locator is None:
        bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
        _locator = FontLocator([*extra_dirs, bundled] if os.path.isdir(bundled) else extra_dirs)
    return _locator


def font_exists(family: str) -> bool:
    return locator().exists(family)


def iter_installed(loc=None):
    """已安装字体 [(主家族名, [全部名], 路径)]，按主名排序；供 --list-fonts。"""
    loc = loc or locator()
    rows = []
    for path, fams in loc._families_by_path.items():
        names = [f for f in dict.fromkeys(fams) if f]
        if names:
            rows.append((names[0], names, path))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def search_fonts(keyword: str = "", loc=None):
    """按关键词过滤已安装字体（匹配任一家族名/文件名，大小写不敏感，中英文皆可）。
    返回 [(主家族名, [全部名], 路径)]。config font_sets 里填主家族名（第一列）。"""
    kw = (_normalize(keyword or "") or "").lower()
    out = []
    for name, names, path in iter_installed(loc):
        if not kw or kw in _normalize(name).lower() \
                or any(kw in _normalize(n).lower() for n in names) \
                or kw in os.path.basename(path).lower():
            out.append((name, names, path))
    return out


def preferred_family(family: str) -> str:
    """本机最易匹配的家族名（单测 mock locator 时原样返回，保证 hermetic）。"""
    loc = locator()
    if not isinstance(loc, FontLocator):
        return family
    return loc.preferred_family(family)


def word_line_height_ratio(path: str):
    """读取字体的单倍行距/字号比（Word 兼容算法），供 docx.lineHeightRatios 接线。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if len(data) < 12:
            return None
        magic = struct.unpack_from(">I", data, 0)[0]
        header = 0
        if magic == 0x74746366:
            header = struct.unpack_from(">I", data, 12)[0]
        upm = _table_u16(data, header, b"head", 18)
        if not upm:
            return None
        os2 = _find_table(data, header, b"OS/2")
        if os2:
            fs_sel = struct.unpack_from(">H", data, os2 + 62)[0]
            asc, desc, gap = struct.unpack_from(">3h", data, os2 + 66)
            height = (asc - desc + gap) if (fs_sel & 0x80) else (
                struct.unpack_from(">H", data, os2 + 72)[0]
                + struct.unpack_from(">H", data, os2 + 74)[0])
            return height / upm
        hhea = _find_table(data, header, b"hhea")
        if hhea:
            asc, desc, gap = struct.unpack_from(">3h", data, hhea + 4)
            return (asc - desc + gap) / upm
    except Exception:
        pass
    return None


def _table_u16(data, header, tag, field_off):
    tbl = _find_table(data, header, tag)
    return struct.unpack_from(">H", data, tbl + field_off)[0] if tbl else None


def _find_table(data, header, tag):
    num_tables = struct.unpack_from(">H", data, header + 4)[0]
    for i in range(num_tables):
        rec = header + 12 + 16 * i
        if data[rec:rec + 4] == tag:
            return struct.unpack_from(">I", data, rec + 8)[0]
    return None


# ---- 豆腐字检测（P5 --font-check） ----

# Unicode 分区（起止码位，起止含端点；生僻字判定与报告用）
_BLOCKS = (
    (0x3400, 0x4DBF, "CJK Ext A"),
    (0x4E00, 0x9FFF, "CJK Unified"),
    (0x20000, 0x2A6DF, "CJK Ext B"),
    (0x2A700, 0x2B73F, "CJK Ext C"),
    (0x2B740, 0x2B81F, "CJK Ext D"),
    (0x2B820, 0x2CEAF, "CJK Ext E"),
    (0x2CEB0, 0x2EBEF, "CJK Ext F"),
    (0x2EBF0, 0x2EE5F, "CJK Ext I"),
    (0x30000, 0x3134F, "CJK Ext G"),
    (0x31350, 0x323AF, "CJK Ext H"),
    (0xF900, 0xFAFF, "CJK Compat"),
    (0x2F800, 0x2FA1F, "CJK Compat Sup"),
    (0x2E80, 0x2EFF, "CJK Radicals"),
    (0x2F00, 0x2FDF, "Kangxi Radicals"),
    (0x2FF0, 0x2FFF, "IDC"),
    (0xE000, 0xF8FF, "PUA"),
    (0xF0000, 0xFFFFD, "PUA-A"),
    (0x100000, 0x10FFFD, "PUA-B"),
)


def block_name(cp: int) -> str:
    """码位 → 分区名（未知返回 U+XXXX）。"""
    for lo, hi, name in _BLOCKS:
        if lo <= cp <= hi:
            return name
    return f"U+{cp:04X}"


_font_cmap_cache = {}


def font_cmap(path: str) -> frozenset:
    """字体 cmap → frozenset(码位)。需 fontTools（requirements core）。
    TTC 按全部字重取并集（如 simsun.ttc 含 SimSun + NSimSun，mingliu.ttc 含 HKSCS）。
    文件缺失/损坏/空 cmap 抛 RuntimeError（由覆盖报告记 MISS）。"""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        raise RuntimeError("font-check 需要 fontTools（pip install fontTools）")
    if not path or not os.path.isfile(path):
        raise RuntimeError(f"字体文件不存在: {path}")
    key = os.path.abspath(path)
    if key not in _font_cmap_cache:
        n = 1
        try:
            with open(path, "rb") as f:
                if f.read(4) == b"ttcf":
                    f.seek(8)
                    n = struct.unpack(">I", f.read(4))[0]
        except Exception:
            n = 1
        agg = set()
        for k in range(min(n, 64)):
            try:
                tt = TTFont(path, fontNumber=k, lazy=True)
            except Exception:
                break
            try:
                agg |= set(tt.getBestCmap() or ())
            finally:
                try:
                    tt.close()
                except Exception:
                    pass
        if not agg:
            raise RuntimeError(f"字体无可用 cmap: {path}")
        _font_cmap_cache[key] = frozenset(agg)
    return _font_cmap_cache[key]


def _resolve_gaiji_char(gaiji_db, chard, code: str, raw: str, simplified: bool = False) -> str:
    """缺字解析（优先级与各渲染器 _resolve_gaiji 一致）：gaiji_db → charDecl → raw；简体再过 t2s。"""
    char = raw
    data = gaiji_db.get(code) if gaiji_db else None
    if data:
        for k in ("unicode", "norm_unicode"):
            v = data.get(k)
            if v:
                try:
                    char = chr(int(v, 16))
                    break
                except ValueError:
                    pass
        else:
            for k in ("norm_big5_char", "norm_uni_char", "uni_char", "composition"):
                v = data.get(k)
                if v:
                    char = v
                    break
    else:
        rec = (chard or {}).get(code)
        if rec:
            if rec.get("unicode"):
                try:
                    char = chr(int(rec["unicode"], 16))
                except ValueError:
                    pass
            elif rec.get("normal"):
                char = rec["normal"]
            elif rec.get("composition"):
                char = rec["composition"]
    if simplified and char:
        try:
            from .simplify import simplify_text
            char = simplify_text(char)
        except Exception:
            pass
    return char or ""


def collect_work_chars(work, gaiji_db=None):
    """遍历 IR 收字 → {char: {"count", "context", "sources"}}。
    ASCII（<0x80）与空白跳过（必有字形）；Text 与解析后缺字全收；标题/作者计入。
    sources 记出处：text / gaiji:<code>。context 取首次出现片段（前后各 ~10 字）。"""
    info = {}
    chard = (work.metadata.get("charDecl") or {}) if work.metadata else {}
    simplified = bool(getattr(work, "simplified", False))

    def add(ch, source, ctx):
        if ord(ch) < 0x80 or ch.isspace():
            return
        rec = info.get(ch)
        if rec is None:
            info[ch] = {"count": 1, "context": ctx, "sources": {source}}
        else:
            rec["count"] += 1
            rec["sources"].add(source)

    def add_text(t):
        for i, ch in enumerate(t):
            lo = max(0, i - 10)
            add(ch, "text", t[lo:i + 11].replace("\n", ""))

    def walk(nodes):
        from .model import App, E, Gaiji, Note, NoteRef, Text
        for n in nodes:
            if isinstance(n, Text):
                add_text(n.text or "")
            elif isinstance(n, Gaiji):
                raw = n.char or n.code
                char = _resolve_gaiji_char(gaiji_db, chard, n.code, raw, simplified)
                for ch in char:
                    add(ch, f"gaiji:{n.code}", f"<g:{n.code}>")
            elif isinstance(n, NoteRef):
                for note in (n.notes or []):
                    walk([note])
            elif isinstance(n, App):
                if n.lem is not None:
                    walk([n.lem])
                walk(n.rdgs)
            elif isinstance(n, E):
                walk(n.children)

    walk(work.body or [])
    md = work.metadata or {}
    for key in ("title", "author"):
        v = md.get(key)
        if isinstance(v, str) and v:
            add_text(v)
    return info


def check_coverage(char_info, font_files):
    """覆盖判定。font_files: [(label, path)]；cmap 读失败的文件覆盖视为空集（记入 missing_files）。
    返回 {"cover": {char: [labels]}, "missing_files": [(label, path)]}。"""
    cover, missing = {}, []
    cmaps = []
    for label, path in font_files:
        try:
            cmaps.append((label, font_cmap(path)))
        except Exception:
            cmaps.append((label, frozenset()))
            missing.append((label, path))
    for ch in char_info:
        cover[ch] = [label for label, cm in cmaps if ord(ch) in cm]
    return {"cover": cover, "missing_files": missing}


def font_check_report(work, font_files, gaiji_db=None, fallback_files=None):
    """豆腐字报告：{"total", "ok", "sup_only", "fallback", "tofu": [...], "missing_files", "fonts"}。
    sup_only = 仅补充字形覆盖（需用户安装该字体，否则仍是豆腐）；
    fallback = 仅系统回退字覆盖（SimSun-ExtB/ExtG，Word 通常自动回退，跨机/WPS/LO 有风险）；
    tofu 按出现次数降序。"""
    info = collect_work_chars(work, gaiji_db)
    cov = check_coverage(info, list(font_files) + list(fallback_files or []))
    cover = cov["cover"]
    fb_labels = {_normalize(l) for l, _ in (fallback_files or [])}
    sup_labels = {"cbetasupplement", "supplement"}
    tofu, sup_only, fallback, ok = [], [], [], 0
    for ch, rec in info.items():
        labels = cover.get(ch, [])
        plain = [l for l in labels if _normalize(l) not in sup_labels | fb_labels]
        if plain:
            ok += 1
            continue
        # 渲染结果优先：回退字能显示就按 FB（用户零操作），否则才报 SUP（需装字库）
        if any(_normalize(l) in fb_labels for l in labels):
            fallback.append((ch, rec))
        elif labels:
            sup_only.append((ch, rec))
        else:
            tofu.append((ch, rec))
    def row(ch, rec):
        cp = ord(ch)
        return {"char": ch, "codepoint": f"U+{cp:04X}",
                "block": block_name(cp), "count": rec["count"],
                "context": rec["context"], "sources": sorted(rec["sources"])}
    key = lambda kv: -kv[1]["count"]
    tofu = [row(ch, r) for ch, r in sorted(tofu, key=key)]
    sup_only = [row(ch, r) for ch, r in sorted(sup_only, key=key)]
    fallback = [row(ch, r) for ch, r in sorted(fallback, key=key)]
    return {"total": len(info), "ok": ok, "sup_only": sup_only,
            "fallback": fallback, "tofu": tofu,
            "missing_files": cov["missing_files"],
            "fonts": [(l, p) for l, p in font_files]}


def format_font_report(rep, work_id="") -> str:
    """报告渲染（stdout 用）。"""
    lines = [f"font-check {work_id}: {rep['total']} distinct chars, "
             f"{len(rep['tofu'])} tofu, {len(rep['sup_only'])} supplement-only, "
             f"{len(rep.get('fallback', []))} fallback"]
    for r in rep["tofu"]:
        lines.append(f"  [TOFU] {r['char']} {r['codepoint']} {r['block']} "
                     f"x{r['count']} ｜ {r['context']} ｜ {','.join(r['sources'])}")
    for r in rep["sup_only"]:
        lines.append(f"  [SUP ] {r['char']} {r['codepoint']} {r['block']} "
                     f"x{r['count']} ｜ {r['context']} ｜ 需安装补充字形")
    for r in rep.get("fallback", []):
        lines.append(f"  [FB  ] {r['char']} {r['codepoint']} {r['block']} "
                     f"x{r['count']} ｜ {r['context']} ｜ 系统回退字（Word 常自动用，跨机有风险）")
    for label, path in rep["missing_files"]:
        lines.append(f"  [MISS] 字体缺失: {label} ({path})")
    return "\n".join(lines)


def supplement_path():
    """随仓补充字形路径（cbeta/fonts/CBETASupplement.ttf），不存在返回 None。"""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "cbeta", "fonts", "CBETASupplement.ttf")
    return p if os.path.isfile(p) else None
