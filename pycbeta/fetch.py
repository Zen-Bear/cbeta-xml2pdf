# -*- coding: utf-8 -*-
"""CBETA 官方资源下载 + 编号流三源材料化。

用法：python -m pycbeta.fetch T0349 [-f all] [--config ...] [--cbeta-ebook ...] [--xml-dir ...]
格式：xml, html, docx, epub, txt_notes（含校注，官方 text-with-notes）, odt；-f all = 全部。
（官方 plain text（无校注）已弃用。）

模型（2026-09-11 定稿）：`xml_dir` 为只读候选源（角色同远端 URL），`cbeta_ebook`
为唯一可写工作根；两者不得相同。落盘：`cbeta_ebook/{id} {书名}/` 下，XML 放 work 根，
基线进**格式同名子目录平展**（html/ docx/ epub/ odt/ txt/＝text-with-notes），
zip 解压后即删（忽略 zip 内部目录层次）。
说明：docx/odt 目前官方仅大正藏 T 与《卍續藏》X 提供，其它藏经 404 时静默跳过。

共享层：URL 模板 / work id 大小写规范化 / catalog 查表 / 下载与 zip 解压 / 条件更新
已抽到独立仓库 `cbeta-fetch`（纯标准库），本模块以 vendored 副本
`pycbeta/_vendor/cbeta_fetch.py` 复用（此处函数多为薄封装）。同步：
`python <cbeta-fetch>/tools/sync_into.py pycbeta/_vendor`。
"""

import glob
import io
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from .names import CANON, WORK_ID, get_canon_id_from_work_id  # noqa: E402
from .theme import load_presets  # noqa: E402
from ._vendor import cbeta_fetch as _cf  # noqa: E402  共享下载层（vendor 副本）

ALL_FORMATS = _cf.ALL_FORMATS
_ZIP_FORMATS = {"html", "docx", "txt_notes", "odt"}

DEFAULT_SOURCE = {
    "xml_dir": "",
    # catalog 默认用仓内版（cbeta/data/sutra_mapping.txt，随包更新；publish 原件仅作上游备份）
    "catalog": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "cbeta", "data", "sutra_mapping.txt"),
    "cbeta_ebook": "",
    "title_t2s": True,
}
# 共享层模板（含 pdf）+ xml2pdf 专有的 figures
DEFAULT_DOWNLOADS = {
    **_cf.DEFAULT_DOWNLOADS,
    "figures": "https://raw.githubusercontent.com/cbeta-git/CBR2X-figures/master/{canon}/{file}",
}

_EBOOK_HINT = ("电子书工作根未配置：在 presets/config.user.json 的 "
               "source.cbeta_ebook 填写（GUI 数据源窗口可视编辑），"
               "或 --cbeta-ebook 指定")
_SAME_HINT = ("本地 XML 候选源与电子书工作根不能相同（source.xml_dir == "
              "source.cbeta_ebook）：候选源只读，工作根写入")


def resolve_source(presets=None, xml_dir=None, cbeta_ebook=None):
    """source 解析（显式参数 > presets source > 空即报错）。
    cbeta_ebook 必须显式有值（出厂留空）；xml_dir 可选（缺省即无本地候选源）。
    两者不得相同（候选源只读，工作根写入）；"" 视同未配。"""
    cfg = (presets.get("source") or {}) if isinstance(presets, dict) else {}
    xml_dir = (xml_dir or cfg.get("xml_dir") or "").strip()
    cbeta_ebook = (cbeta_ebook or cfg.get("cbeta_ebook") or "").strip()
    if not cbeta_ebook:
        raise ValueError(_EBOOK_HINT)
    if xml_dir and os.path.normcase(os.path.abspath(xml_dir)) == \
            os.path.normcase(os.path.abspath(cbeta_ebook)):
        raise ValueError(_SAME_HINT)
    return xml_dir, cbeta_ebook


def title_t2s(presets=None) -> bool:
    """工作目录名书名是否转简体（source.title_t2s，默认 true）。"""
    cfg = (presets.get("source") or {}) if isinstance(presets, dict) else {}
    return bool(cfg.get("title_t2s", True))


def inspect_xml_source(xml_dir: str, sample: int = 5) -> Dict:
    """抽检本地 XML 候选源的 TEI 版本，判断是否发布版 P5（安全）。

    返回 {"safe": True|False|None, "edition": str, "sample": str, "reason": str}：
    - 目录空/不存在/无 XML → safe=None（未判定，不告警）
    - 抽样若干文件读文件头 <edition>：归一化 == "XML TEI P5" → safe=True
    - P5a/P5b/其它 → safe=False（正文/校勘渲染不完整，可能致重复/丢注/校验红）
    - 未检出 <edition> → 按 safe=True 处理（发布版恒有，避免误报）
    """
    xml_dir = (xml_dir or "").strip()
    if not xml_dir or not os.path.isdir(xml_dir):
        return {"safe": None, "edition": "", "sample": "", "reason": "目录不存在"}
    files = []
    for root, dirs, fns in os.walk(xml_dir):
        dirs[:] = [d for d in dirs if d not in ("out", "__pycache__", ".git")]
        for fn in sorted(fns):
            if fn.lower().endswith(".xml"):
                files.append(os.path.join(root, fn))
        if len(files) >= sample:
            break
    if not files:
        return {"safe": None, "edition": "", "sample": "", "reason": "无 XML"}
    editions = set()
    for p in files[:sample]:
        try:
            with io.open(p, encoding="utf-8-sig", errors="replace") as f:
                head = f.read(8192)
        except OSError:
            continue
        m = re.search(r"<edition[^>]*>([^<]*)</edition>", head)
        if m:
            editions.add(" ".join(m.group(1).split()))
    if not editions:
        return {"safe": True, "edition": "", "sample": files[0],
                "reason": "未检出 <edition>（按发布版 P5 处理）"}
    bad = sorted(e for e in editions if e.upper() != "XML TEI P5")
    if bad:
        return {"safe": False, "edition": bad[0], "sample": files[0],
                "reason": f"检测到非发布版 P5 源（{bad[0]}）"}
    return {"safe": True, "edition": "XML TEI P5", "sample": files[0],
            "reason": "XML TEI P5"}


def is_work_id(s: str) -> bool:
    """是否 CBETA 佛典編號（如 T0349 / T0099 / A1057 / X1271 / T0128a / TXa001）。
    大小写不敏感；字母后缀原始大小写由 catalog 决定（见 canonical_work_id）。"""
    return _cf.is_work_id(s)


def parse_work_id(work_id: str) -> tuple:
    """(canon, no)。canon 可能为多字母（GA/GB/LC/TX/YP/ZS/ZW/CC）。
    canon 转大写、no **保留原大小写**（如 `("TX","a001")`）。"""
    return _cf.parse_work_id(work_id)


def catalog_lookup(catalog: str, canon: str, no: str) -> List[Dict]:
    """sutra_mapping.txt 查表（委托共享层）：canon/no 大小写不敏感，
    返回项保留 catalog 原始大小写 `[{vol,no,file,title}]`（多冊全返）。"""
    return _cf.catalog_lookup(catalog, canon, no)


def canonical_work_id(work_id: str, presets=None) -> str:
    """按 catalog 原始大小写规范化 work id（canon 大写 + no 原样，如 TXa001/T0128a）。
    catalog 未命中（离线/本地/未知）→ 原样返回。用于下载 URL 与工作目录命名。"""
    cfg = (presets.get("source") or {}) if isinstance(presets, dict) else {}
    cat = cfg.get("catalog", DEFAULT_SOURCE.get("catalog", ""))
    return _cf.canonical_work_id(work_id, cat)


def find_local_xml(xml_dir: str, canon: str, no: str) -> List[str]:
    """本地 XML 源中查找 {canon}*n{no}.xml（排除 out/）。

    统一根目录（如 E:\\dev\\cbeta\\test）下两档查找：
    - 平展优先：根目录下以 work id（canon+no，如 YP0021）开头的条目内，
      如 `YP0021 異部宗輪論語體釋\\*.xml`；
    - 仓库次之：全树递归，含 github 镜像布局 `{canon}/{canon}{vol}/`
      （如 `YP/YP14/YP14n0021.xml`；下载落盘即此布局）。
    同一文件只返回一次，平展命中排在前面。"""
    out, seen = [], set()

    def add(p: str) -> None:
        ap = os.path.abspath(p)
        if "out" + os.sep in ap:
            return
        if ap not in seen and os.path.isfile(ap):
            seen.add(ap)
            out.append(ap)

    work_id = f"{canon}{no}"
    for entry in sorted(glob.glob(os.path.join(xml_dir, f"{work_id}*"))):
        if os.path.isdir(entry):
            for p in sorted(glob.glob(os.path.join(entry, "**", f"{canon}*n{no}.xml"),
                                      recursive=True)):
                add(p)
        elif (os.path.isfile(entry)
                and re.fullmatch(rf"{canon}.*n{re.escape(no)}\.xml",
                                 os.path.basename(entry))):
            add(entry)
    for p in sorted(glob.glob(os.path.join(xml_dir, "**", f"{canon}*n{no}.xml"),
                               recursive=True)):
        add(p)
    return out


def _http_download(url: str, dest: str, timeout: int = 90) -> bool:
    """委托共享层下载（unverified SSL + 重试 + 原子替换）。"""
    return _cf.download(url, dest, timeout=timeout)


def _unzip_flat(zip_path: str, dest_dir: str) -> None:
    """平展解压（委托共享层）：忽略 zip 自带目录层次，按 basename 写入 dest_dir（防 zip-slip）。"""
    _cf.unzip_flat(zip_path, dest_dir)


def _find_work_dir(root: str, work_id: str) -> Optional[str]:
    """工作根下已存在的平展 work 目录（`{id} {书名}` 或恰为 `{id}`），没有返回 None。

    排除更长編號的误命中（如查 T0349 不命中 T0349a 目录：work id 后紧跟字母数字即跳过）。"""
    if not root:
        return None
    for entry in sorted(glob.glob(os.path.join(root, f"{work_id}*"))):
        if not os.path.isdir(entry):
            continue
        rest = os.path.basename(entry)[len(work_id):]
        if rest and rest[0].isalnum():
            continue
        return entry
    return None


def _maybe_t2s(text: str, presets=None) -> str:
    """书名转简体（source.title_t2s，默认 true）；缺 opencc 等失败原样返回。"""
    if not text or not title_t2s(presets):
        return text
    try:
        from .simplify import simplify_text
        return simplify_text(text)
    except Exception:
        return text


def work_dir(root: str, work_id: str, title: str = "", presets=None,
             create: bool = False) -> Optional[str]:
    """work 目录解析：已有 `{id}*` 复用；无则 create=True 时建 `{id} {书名}`。
    书名取 catalog（经 source.title_t2s 转换 + 文件名净化）。"""
    # 防嵌套：root 本身已是该 work 目录（如 GUI/CLI 兜底把 work 目录当根传入）
    if root and _work_id_from_dirname(
            os.path.basename(os.path.normpath(root))) == work_id:
        return root
    hit = _find_work_dir(root, work_id)
    if hit or not create:
        return hit
    from .filename import sanitize
    name = work_id
    if title:
        name = f"{work_id} {sanitize(_maybe_t2s(title, presets))}"
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    return path


def _catalog_title(presets, canon: str, no: str) -> str:
    cfg = (presets.get("source") or {}) if isinstance(presets, dict) else {}
    for rec in catalog_lookup(cfg.get("catalog", ""), canon, no):
        if rec.get("title"):
            return rec["title"]
    return ""


def _fmt_dir(fmt: str) -> str:
    """基线格式目录名：txt_notes（官方 text-with-notes）→ `txt/`；其余同名。"""
    return "txt" if fmt == "txt_notes" else fmt


def _fmt_ext(fmt: str) -> str:
    return ".txt" if fmt == "txt_notes" else f".{fmt}"


def _collect_fmt(wdir: str, fmt: str, work_id: str) -> List[str]:
    """收集某格式目录内本 work 的文件：`{wdir}/{fmt}/{id}_*{ext}`；
    epub 为单文件 `{wdir}/epub/{id}.epub`。空文件不计。"""
    d = os.path.join(wdir, _fmt_dir(fmt))
    if fmt == "epub":
        p = os.path.join(d, f"{work_id}.epub")
        return [p] if os.path.isfile(p) and os.path.getsize(p) > 0 else []
    ext = _fmt_ext(fmt)
    return [p for p in sorted(glob.glob(os.path.join(d, f"{work_id}_*{ext}")))
            if os.path.isfile(p) and os.path.getsize(p) > 0]


def _fetch_baseline_flat(work_id: str, fmt: str, dl: Dict, canon: str,
                         wdir: str, force: bool = False) -> List[str]:
    """基线落 `{wdir}/{格式目录}/`（html/docx/epub/odt/txt），zip 平展解压后删除。
    失败静默返回 []。force=True 时忽略「已有」短路，强制重下覆盖。"""
    existing = _collect_fmt(wdir, fmt, work_id)
    if existing and not force:
        return existing  # 已落盘，不重复下载

    tmpl = dl.get(fmt, DEFAULT_DOWNLOADS.get(fmt, ""))
    if not tmpl:
        return existing if force else []
    dest_dir = os.path.join(wdir, _fmt_dir(fmt))

    if fmt == "epub":
        url = tmpl.format(canon=canon, id=work_id)
        dest = os.path.join(dest_dir, f"{work_id}.epub")
        if force or not os.path.isfile(dest):
            if not _http_download(url, dest):
                return existing if force else []
        return [dest]

    url = tmpl.format(id=work_id) if fmt in ("html", "txt_notes") \
        else tmpl.format(canon=canon, id=work_id)
    # 下载到临时 zip → 平展解压进格式目录 → 删 zip（不留残留）
    import tempfile
    fd, zip_path = tempfile.mkstemp(prefix=f"{work_id}.{fmt}.", suffix=".zip")
    os.close(fd)
    try:
        if not _http_download(url, zip_path):
            return existing if force else []
        try:
            _unzip_flat(zip_path, dest_dir)
        except zipfile.BadZipFile:
            return existing if force else []
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass
    return _collect_fmt(wdir, fmt, work_id)


_BASELINE_FORMATS = ("html", "docx", "epub", "txt_notes", "odt")


def _present_baseline_formats(wdir: str, work_id: str) -> List[str]:
    """work 目录内本地已有的基线格式（不会为不存在者新下载）。"""
    return [fmt for fmt in _BASELINE_FORMATS
            if _collect_fmt(wdir, fmt, work_id)]


def _fetch_one(work_id: str, fmt: str, canon: str, no: str,
               dl: Dict, source_cfg: Dict, cbeta_ebook: str,
               presets=None) -> List[str]:
    """下载单个格式，失败静默返回 []。一律落平展 work 目录。"""
    title = ""
    if fmt == "xml":
        files = catalog_lookup(source_cfg.get("catalog", ""), canon, no)
        if not files:
            print(f"{work_id}: catalog 未收录（书名/冊号缺失），无法拼 XML 下载地址")
            return []
        title = next((r["title"] for r in files if r.get("title")), "")
    wdir = work_dir(cbeta_ebook, work_id, title, presets, create=True)
    if fmt == "xml":
        saved = []
        for rec in files:
            url = dl.get("xml", DEFAULT_DOWNLOADS["xml"]).format(
                canon=canon, vol=rec["vol"], file=rec["file"])
            dest = os.path.join(wdir, rec["file"])
            if os.path.isfile(dest):
                saved.append(dest)
                continue
            if _http_download(url, dest):
                saved.append(dest)
        return saved

    return _fetch_baseline_flat(work_id, fmt, dl, canon, wdir)


def materialize_work(work_id: str, presets: Optional[Dict] = None,
                     xml_dir: Optional[str] = None,
                     cbeta_ebook: Optional[str] = None,
                     download: bool = True, quiet: bool = False):
    """编号流三源材料化：cbeta_ebook（已材料化）→ xml_dir（拷/合册）→ URL（下载）。

    返回 (paths, label)；paths = work 目录内 XML 列表；label 说明来源
    ∈ {"cbeta_ebook","xml_copy","xml_merge","downloaded",""}。
    本地源刷新：xml_dir 源文件比工作目录副本新时重拷/重合力
    （整文件比 mtime；碎片合并自带 mtime 跳过）。
    """
    from .merge import collect_work_frags, merge_groups_to_dir
    if presets is None:
        presets = load_presets()
    xml_dir, cbeta_ebook = resolve_source(
        presets, xml_dir=xml_dir, cbeta_ebook=cbeta_ebook)
    work_id = canonical_work_id(work_id, presets)
    canon, no = parse_work_id(work_id)
    title = _catalog_title(presets, canon, no)
    wdir = work_dir(cbeta_ebook, work_id, title, presets, create=bool(xml_dir))
    have = find_local_xml(wdir, canon, no) if wdir else []

    whole = find_local_xml(xml_dir, canon, no) if xml_dir else []
    frags = collect_work_frags(xml_dir, canon, no) if xml_dir else {}
    if whole or frags:
        wdir = work_dir(cbeta_ebook, work_id, title, presets, create=True)
        if whole:
            changed = False
            for src in whole:
                dst = os.path.join(wdir, os.path.basename(src))
                if not os.path.isfile(dst) or \
                        os.path.getmtime(src) > os.path.getmtime(dst):
                    shutil.copy2(src, dst)
                    changed = True
            have = find_local_xml(wdir, canon, no)
            if not quiet and changed:
                print(f"{work_id}: 本地源拷贝 → {len(have)} 文件（{wdir}）")
            _ensure_work_figures(work_id, presets, cbeta_ebook)
            return have, "xml_copy"
        merge_groups_to_dir(frags, wdir, quiet=quiet)
        have = find_local_xml(wdir, canon, no)
        if not quiet:
            n = sum(len(v) for v in frags.values())
            print(f"{work_id}: 碎片合册 → {len(have)} 册（{n} 碎片，{wdir}）")
        _ensure_work_figures(work_id, presets, cbeta_ebook)
        return have, "xml_merge"

    if have:
        _ensure_work_figures(work_id, presets, cbeta_ebook)
        return have, "cbeta_ebook"
    if not download:
        return [], ""
    res = fetch_work(work_id, ["xml"], presets, cbeta_ebook)
    wdir = work_dir(cbeta_ebook, work_id, title, presets, create=False)
    have = find_local_xml(wdir, canon, no) if wdir else []
    if have and not quiet:
        print(f"{work_id}: 官方下载 → {len(have)} 文件（{wdir}）")
    _ensure_work_figures(work_id, presets, cbeta_ebook)
    return have, ("downloaded" if have else "")


def fetch_work(work_id: str, formats: List[str], presets: Optional[Dict] = None,
               cbeta_ebook: Optional[str] = None) -> Dict[str, List[str]]:
    """下载一部经的多个格式；返回 {fmt: [路径]}（失败格式为 []）。
    一律落平展 work 目录 `cbeta_ebook/{id} {书名}/`。
    presets: load_presets() 结果（含 source/downloads）；缺省读默认配置。
    """
    if presets is None:
        presets = load_presets()
    source_cfg = {**DEFAULT_SOURCE, **(presets.get("source") or {})}
    dl = {**DEFAULT_DOWNLOADS, **(presets.get("downloads") or {})}
    _, cbeta_ebook = resolve_source(presets, cbeta_ebook=cbeta_ebook)
    work_id = canonical_work_id(work_id, presets)
    canon, no = parse_work_id(work_id)
    out = {}
    for fmt in formats:
        if fmt not in ALL_FORMATS:
            out[fmt] = []
            continue
        out[fmt] = _fetch_one(work_id, fmt, canon, no, dl, source_cfg,
                              cbeta_ebook, presets)
    return out


def ensure_baselines(work_id: str, kinds: List[str], presets: Optional[Dict],
                     cbeta_ebook: str) -> Dict[str, List[str]]:
    """校验按需调用：对缺失的基线格式下载（docx/odt 非 T/X 等 404 静默跳过）。

    xml 不是基线（由 -i/列表模式另行保证）、odt 从不参与比对，故跳过；
    其余 html/txt_notes/docx/epub 缺啥下啥。返回本次新获取的 {kind: [路径]}。"""
    from .verify import find_official
    fetched = {}
    work_id = canonical_work_id(work_id, presets)
    canon, no = parse_work_id(work_id)
    title = _catalog_title(presets or {}, canon, no)
    wdir = work_dir(cbeta_ebook, work_id, title, presets, create=bool(kinds))
    for kind in kinds:
        if kind in ("xml", "odt"):
            continue
        existing = find_official(wdir, work_id, kind) if wdir else []
        if existing:
            continue
        res = fetch_work(work_id, [kind], presets, cbeta_ebook)
        if res.get(kind):
            fetched[kind] = res[kind]
            print(f"  {work_id}: 官方基线缺失，已下载 {kind}（{len(res[kind])} 文件）")
    _ensure_work_figures(work_id, presets, cbeta_ebook, wdir=wdir)
    return fetched


def _ensure_work_figures(work_id: str, presets, cbeta_ebook, wdir=None) -> None:
    """work 内 XML 含 <graphic> 时预取缺失图片（失败只打印，不中断）。"""
    try:
        from .figures import graphic_urls_in_text
        if wdir is None:
            try:
                canon0, no0 = parse_work_id(work_id)
            except ValueError:
                return
            title0 = _catalog_title(presets or {}, canon0, no0)
            wdir = work_dir(cbeta_ebook, work_id, title0, presets, create=False)
        if not wdir:
            return
        urls = []
        for xp in find_local_xml(wdir, *parse_work_id(work_id)):
            try:
                with open(xp, encoding="utf-8", errors="replace") as f:
                    urls += graphic_urls_in_text(f.read())
            except OSError:
                continue
        urls = list(dict.fromkeys(urls))
        if urls:
            ensure_figures(work_id, urls, presets, cbeta_ebook, wdir=wdir)
    except Exception as e:
        print(f"  {work_id}: 图片预取跳过（{e}）")


def ensure_figures(work_id: str, urls, presets=None, cbeta_ebook=None,
                   wdir=None) -> tuple:
    """图片预取：缺的下到 {work}/figures/。返回 (ok_paths, missing_basenames)。

    顺序：{work}/figures 已有 → {work}/txt 基线 bonus 拷贝 → 远端下载；
    404/失败只记录缺失，不抛错。"""
    from .figures import (split_graphic_url, download_url, find_figure,
                          looks_like_image)
    presets = presets or {}
    work_id = canonical_work_id(work_id, presets)
    try:
        canon, no = parse_work_id(work_id)
    except ValueError:
        return [], []
    if wdir is None:
        title = _catalog_title(presets, canon, no)
        wdir = work_dir(cbeta_ebook, work_id, title, presets, create=False)
        if not wdir:
            return [], [split_graphic_url(u)[1] for u in urls or [] if split_graphic_url(u)[1]]
    dl = {**DEFAULT_DOWNLOADS, **(presets.get("downloads") or {})}
    tmpl = dl.get("figures") or DEFAULT_DOWNLOADS["figures"]
    fig_dir = os.path.join(wdir, "figures")
    txt_dir = os.path.join(wdir, "txt")
    ok, missing, downloaded = [], [], 0
    for url in urls or []:
        ucanon, base = split_graphic_url(url)
        if not base:
            continue
        hit = find_figure(base, [fig_dir, txt_dir])
        if hit:
            if os.path.dirname(os.path.abspath(hit)) != os.path.abspath(fig_dir):
                # 基线 bonus：拷贝一份进 figures/（统一渲染搜索口径；失败忽略）
                try:
                    os.makedirs(fig_dir, exist_ok=True)
                    shutil.copy2(hit, os.path.join(fig_dir, base))
                    hit = os.path.join(fig_dir, base)
                except OSError:
                    pass
            ok.append(hit)
            continue
        dest = os.path.join(fig_dir, base)
        try:
            os.makedirs(fig_dir, exist_ok=True)
            if _http_download(download_url(ucanon or canon, base, tmpl), dest) \
                    and looks_like_image(dest):
                ok.append(dest)
                downloaded += 1
                continue
            try:
                os.remove(dest)
            except OSError:
                pass
        except Exception:
            pass
        missing.append(base)
    if downloaded:
        print(f"  {work_id}: 图片缺失，已下载 figures（{downloaded} 张）")
    if missing:
        print(f"  {work_id}: 图片仍缺失（{', '.join(missing)}），渲染用占位")
    return ok, missing


def _work_id_from_dirname(name: str) -> str:
    """work 目录名 → 佛典編號（首个空白前 token），非 work 目录返回 ""。
    `T0349 彌勒菩薩...` → T0349；`out`/`T` 等 → ""。"""
    tok = re.split(r"[\s\u3000]+", name.strip(), 1)[0].upper()
    return tok if is_work_id(tok) else ""


def _download_if_changed(url: str, dest: str, timeout: int = 90):
    """条件下载（委托共享层 `fetch_if_changed`，保留本项目 (status, detail) 口径）。

    本地已有则带 If-Modified-Since（304 免下载）；200 先落临时再与本地字节比对，
    一致则**不落盘**（保持 mtime），不同才替换。status ∈ changed/unchanged/failed。
    """
    import email.utils
    last_modified = None
    if os.path.isfile(dest):
        last_modified = email.utils.formatdate(os.path.getmtime(dest), usegmt=True)
    old = b""
    if os.path.isfile(dest):
        try:
            with open(dest, "rb") as f:
                old = f.read()
        except OSError:
            old = b""
    tmp = dest + f".chk{os.getpid()}"
    try:
        status, _etag, _lm = _cf.fetch_if_changed(
            url, tmp, last_modified=last_modified, timeout=timeout)
        if status == "not-modified":
            return "unchanged", ""
        if status == "failed":
            return "failed", "download failed"
        with open(tmp, "rb") as f:
            new = f.read()
        if old == new:
            return "unchanged", ""
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(tmp, dest)
        return "changed", f"{len(old)}→{len(new)}"
    except OSError as e:
        return "failed", type(e).__name__
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass



def check_ebook_updates(cbeta_ebook: str, presets: Optional[Dict] = None,
                        probe=None, progress=None, with_baselines: bool = True):
    """远程源更新检查：遍历 cbeta_ebook 各 work 目录，对 XML 逐册条件下载
    （If-Modified-Since/字节比对；不改项不落盘）。返回报告：
    [{"id","status","detail"}]，status ∈ updated/unchanged/failed/skipped。

    只走远程源（catalog 记录的 XML URL）——**不读本地 xml_dir 候选源**
    （远程永远最新；本地 CBReader 仅用于材料化首次导入，不参与更新）。
    with_baselines=True：XML 有更新的 work，其**本地已有的基线**一并强制刷新
    （只为已存在格式重下，不新增格式）。
    probe(url, dest) 可注入（单测）；progress(id, done, total) 可注入。"""
    if probe is None:
        probe = _download_if_changed
    if presets is None:
        presets = load_presets()
    src = presets.get("source") or {}
    catalog = src.get("catalog", "")
    dl = {**DEFAULT_DOWNLOADS, **(presets.get("downloads") or {})}
    xml_tmpl = dl.get("xml", DEFAULT_DOWNLOADS["xml"])
    entries = []
    if os.path.isdir(cbeta_ebook):
        for name in sorted(os.listdir(cbeta_ebook)):
            d = os.path.join(cbeta_ebook, name)
            if not os.path.isdir(d):
                continue
            wid = _work_id_from_dirname(name)
            if wid:
                entries.append((wid, d))
    report = []
    for i, (wid, d) in enumerate(entries):
        if progress:
            progress(wid, i, len(entries))
        wid = canonical_work_id(wid, presets)
        canon, no = parse_work_id(wid)
        recs = catalog_lookup(catalog, canon, no)
        if not recs:
            report.append({"id": wid, "status": "skipped",
                           "detail": "catalog 无记录"})
            continue
        changed, failed, details = 0, 0, []
        for rec in recs:
            dest = os.path.join(d, rec["file"])
            url = xml_tmpl.format(canon=canon, vol=rec["vol"], file=rec["file"])
            st, detail = probe(url, dest)
            if st == "changed":
                changed += 1
                details.append(f"{rec['file']} {detail}")
            elif st == "failed":
                failed += 1
                details.append(f"{rec['file']} 失败:{detail}")
        if changed and with_baselines:
            refreshed = []
            for fmt in _present_baseline_formats(d, wid):
                if _fetch_baseline_flat(wid, fmt, dl, canon, d, force=True):
                    refreshed.append(fmt)
            # 文本族必备替代品（text-with-notes）：老 work 缺失则补下
            if "txt_notes" not in _present_baseline_formats(d, wid):
                if _fetch_baseline_flat(wid, "txt_notes", dl, canon, d):
                    refreshed.append("txt_notes")
            if refreshed:
                details.append("基线已刷新:" + ",".join(refreshed))
        status = "updated" if changed else ("failed" if failed else "unchanged")
        report.append({"id": wid, "status": status, "detail": "; ".join(details)})
    return report


def format_update_report(report) -> list:
    """更新检查报告 → 文本行（供 GUI 弹窗/CLI）。"""
    n_up = sum(1 for r in report if r["status"] == "updated")
    n_fail = sum(1 for r in report if r["status"] == "failed")
    n_skip = sum(1 for r in report if r["status"] == "skipped")
    n_same = len(report) - n_up - n_fail - n_skip
    lines = [f"已更新 {n_up} / 无变化 {n_same} / 失败 {n_fail}"
             + (f" / 跳过 {n_skip}" if n_skip else "")]
    if n_up:
        lines.append("")
        lines.append("【需重新生成电子书】")
        for r in report:
            if r["status"] == "updated":
                lines.append(f"  {r['id']}  {r['detail']}")
    for r in report:
        if r["status"] == "failed":
            lines.append(f"  失败 {r['id']}  {r['detail']}")
    return lines


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="pycbeta.fetch",
                                 description="CBETA 官方资源下载（XML / html/docx/epub/txt_notes/odt 基线，落 cbeta_ebook 格式子目录）")
    ap.add_argument("id", help="CBETA 佛典編號，如 T0349 / T0099 / A1057 / X1271")
    ap.add_argument("-f", "--format", default="all",
                    help="格式：xml,html,docx,epub,txt_notes,odt（逗号列表）或 all")
    ap.add_argument("--config", help="自定义 config.json")
    ap.add_argument("--cbeta-ebook", default=None,
                    help="电子书工作根（默认 config source.cbeta_ebook）")
    ap.add_argument("--xml-dir", default=None,
                    help="本地 XML 候选源（只读；给定时先材料化再下载）")
    args = ap.parse_args(argv)

    work_id = args.id
    if not is_work_id(work_id):
        ap.error(f"不是有效的佛典編號: {work_id}")
    presets = load_presets(args.config) if args.config else load_presets()
    if args.format == "all":
        formats = list(ALL_FORMATS)
    else:
        formats = [f.strip() for f in args.format.split(",") if f.strip()]
    ok = 0
    need_xml = "xml" in formats or bool(args.xml_dir)
    if need_xml:
        paths, label = materialize_work(work_id, presets,
                                        xml_dir=args.xml_dir,
                                        cbeta_ebook=args.cbeta_ebook)
        if paths:
            ok += 1
        print(f"{'xml':8} -> {len(paths)} 文件（{label or '未取得'}）")
        for p in paths[:3]:
            print(f"          {p}")
        formats = [f for f in formats if f != "xml"]
    result = fetch_work(work_id, formats, presets, args.cbeta_ebook)
    for fmt, got in result.items():
        if got:
            ok += 1
            print(f"{fmt:8} -> {len(got)} 文件")
            for p in got[:3]:
                print(f"          {p}")
            if len(got) > 3:
                print(f"          … 共 {len(got)}")
        else:
            print(f"{fmt:8} -> 下载失败（官方可能未提供该藏经此格式，如 docx/odt 仅 T/X）")
    print(f"完成：{work_id} 成功 {ok} 种格式")
    return 0


if __name__ == "__main__":
    sys.exit(main())