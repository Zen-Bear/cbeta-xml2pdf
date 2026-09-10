# -*- coding: utf-8 -*-
"""CBETA 官方资源下载 + 编号流三源材料化。

用法：python -m pycbeta.fetch T0349 [-f all] [--config ...] [--cbeta-ebook ...] [--xml-dir ...]
格式：xml, html, docx, epub, txt（无校注）, txt_notes（含校注）, odt；-f all = 全部。

模型（2026-09-10 定稿）：`xml_dir` 为只读候选源（角色同远端 URL），`cbeta_ebook`
为唯一可写工作根；两者不得相同。落盘一律**平展**：`cbeta_ebook/{id} {书名}/`，
XML（整文件拷贝 / 碎片按册合册）与基线同目录（html/docx/odt/epub 放根、
txt 进 {id}.txt/、txt_notes 进 {id}.txt_notes/）。
txt 与 txt_notes 分目录存放（同名文件内容不同，混放会覆盖）。
说明：docx/odt 目前官方仅大正藏 T 与《卍續藏》X 提供，其它藏经 404 时静默跳过。
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

ALL_FORMATS = ("xml", "html", "docx", "epub", "txt", "txt_notes", "odt")
_ZIP_FORMATS = {"html", "docx", "txt", "txt_notes", "odt"}

DEFAULT_SOURCE = {
    "xml_dir": "",
    # catalog 默认用仓内版（cbeta/data/sutra_mapping.txt，随包更新；publish 原件仅作上游备份）
    "catalog": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "cbeta", "data", "sutra_mapping.txt"),
    "cbeta_ebook": "",
    "title_t2s": True,
}
DEFAULT_DOWNLOADS = {
    "xml": "https://raw.githubusercontent.com/cbeta-org/xml-p5/master/{canon}/{canon}{vol}/{file}",
    "html": "https://cbdata.dila.edu.tw/stable/download/html/{id}.html.zip",
    "docx": "https://cbdata.dila.edu.tw/stable/download/docx/{canon}/{id}.zip",
    "epub": "https://cbdata.dila.edu.tw/stable/download/epub/{canon}/{id}.epub",
    "txt": "https://cbdata.dila.edu.tw/stable/download/text/{id}.txt.zip",
    "txt_notes": "https://cbdata.dila.edu.tw/stable/download/text-with-notes/{id}.txt.zip",
    "odt": "https://cbdata.dila.edu.tw/stable/download/odt/{canon}/{id}.zip",
}

_EBOOK_HINT = ("电子书工作根未配置：在 config.user.json 的 source.cbeta_ebook 填写 "
               "（GUI 数据源窗口可视编辑），或 --cbeta-ebook 指定")
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


def is_work_id(s: str) -> bool:
    """是否 CBETA 佛典編號（如 T0349 / T0099 / A1057 / X1271 / T0128a）。
    大小写不敏感（内部归一化为大写，下游查找/下载 URL 统一用大写）。"""
    return bool(s) and bool(WORK_ID.match((s or "").strip().upper()))


def parse_work_id(work_id: str) -> tuple:
    """(canon, no)。canon 可能为多字母（GA/GB/LC/TX/YP/ZS/ZW/CC）。大小写不敏感。"""
    m = re.match(rf"^({CANON})(.*)$", (work_id or "").strip().upper())
    if not m:
        raise ValueError(f"invalid work id: {work_id}")
    return m.group(1), m.group(2)


def catalog_lookup(catalog: str, canon: str, no: str) -> List[Dict]:
    """sutra_mapping.txt 查表：列 = canon,vol,no,…,书名,… → [{vol, file, title}]（多冊全返）。"""
    if not catalog or not os.path.isfile(catalog):
        return []
    out = []
    try:
        f = io.open(catalog, encoding="utf-8")
    except OSError:
        return []
    with f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 3 and parts[0] == canon and parts[2] == no:
                vol = parts[1]
                title = parts[6].strip() if len(parts) >= 7 else ""
                out.append({"vol": vol, "file": f"{canon}{vol}n{no}.xml",
                            "title": title})
    return out


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
    import ssl
    # cbdata 证书缺 Subject Key Identifier，系统校验失败；公共数据集用 unverified context
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "pycbeta/1.0"})
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception:
            continue
    return False


def _unzip(zip_path: str, dest_dir: str) -> None:
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            # 防 zip-slip：仅接受相对路径且不越界
            safe = os.path.normpath(n)
            if safe.startswith("..") or os.path.isabs(safe):
                continue
            target = os.path.join(dest_dir, safe)
            if n.endswith("/"):
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(n) as src, open(target, "wb") as dst:
                    dst.write(src.read())


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


def _txt_subdir(fmt: str, work_id: str) -> str:
    """txt 族整理子目录名：txt → {id}.txt/，txt_notes → {id}.txt_notes/。

    两者必须隔离（同名文件内容不同，混放会互相覆盖）。"""
    return f"{work_id}.txt_notes" if fmt == "txt_notes" else f"{work_id}.txt"


def _collect_txt_flat(flat: str, fmt: str, work_id: str) -> List[str]:
    """平展目录内收集 txt 族文件：父目录名须为 {id}.txt/ 或 {id}.txt_notes/，
    递归但排除 out/（兼容 zip 自带子目录或手工整理的嵌套形态）。"""
    out = []
    for p in sorted(glob.glob(os.path.join(flat, "**", "*.txt"), recursive=True)):
        if f"{os.sep}out{os.sep}" in os.path.abspath(p):
            continue
        if os.path.basename(os.path.dirname(p)) != _txt_subdir(fmt, work_id):
            continue
        out.append(p)
    return out


def _fetch_baseline_flat(work_id: str, fmt: str, dl: Dict, canon: str,
                         wdir: str) -> List[str]:
    """基线落 work 目录（平展）：html/docx/odt/epub 放目录根下，
    txt 进 {id}.txt、txt_notes 进 {id}.txt_notes/；递归收集时排除 out/
    （work 目录自带 out/ 生成物）。失败静默返回 []。"""
    if fmt == "epub":
        p = os.path.join(wdir, f"{work_id}.epub")
        existing = [p] if os.path.isfile(p) else []
    elif fmt in ("txt", "txt_notes"):
        existing = _collect_txt_flat(wdir, fmt, work_id)
    else:
        existing = []
        for p in sorted(glob.glob(os.path.join(wdir, "**", f"{work_id}_*.{fmt}"),
                                  recursive=True)):
            if f"{os.sep}out{os.sep}" in os.path.abspath(p):
                continue
            existing.append(p)
    if existing:
        return existing  # work 目录已有，不重复下载

    if fmt == "epub":
        url = dl.get("epub", DEFAULT_DOWNLOADS["epub"]).format(canon=canon, id=work_id)
        dest = os.path.join(wdir, f"{work_id}.epub")
        if not os.path.isfile(dest):
            if not _http_download(url, dest):
                return []
        return [dest]

    tmpl = dl.get(fmt, DEFAULT_DOWNLOADS.get(fmt, ""))
    if not tmpl:
        return []
    if fmt in ("html", "txt", "txt_notes"):
        url = tmpl.format(id=work_id)
    else:  # docx / odt：需 {canon} 前缀
        url = tmpl.format(canon=canon, id=work_id)
    zip_path = os.path.join(wdir, f"{work_id}.{fmt}.zip")
    if not os.path.isfile(zip_path):
        if not _http_download(url, zip_path):
            return []
    try:
        _unzip(zip_path, wdir)
    except zipfile.BadZipFile:
        return []
    if fmt in ("txt", "txt_notes"):
        # 顶层 {id}_*.txt 整理入 {id}.txt/ 或 {id}.txt_notes/ 目录
        #（find_official 的 {s}.txt/*.txt 与 {s}.txt_notes/*.txt 模式）
        d = os.path.join(wdir, _txt_subdir(fmt, work_id))
        os.makedirs(d, exist_ok=True)
        for p in glob.glob(os.path.join(wdir, f"{work_id}_*.txt")):
            shutil.move(p, os.path.join(d, os.path.basename(p)))
        return _collect_txt_flat(wdir, fmt, work_id)
    out = []
    for p in sorted(glob.glob(os.path.join(wdir, "**", f"{work_id}_*.{fmt}"),
                              recursive=True)):
        if f"{os.sep}out{os.sep}" in os.path.abspath(p):
            continue
        out.append(p)
    return out


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
            return have, "xml_copy"
        merge_groups_to_dir(frags, wdir, quiet=quiet)
        have = find_local_xml(wdir, canon, no)
        if not quiet:
            n = sum(len(v) for v in frags.values())
            print(f"{work_id}: 碎片合册 → {len(have)} 册（{n} 碎片，{wdir}）")
        return have, "xml_merge"

    if have:
        return have, "cbeta_ebook"
    if not download:
        return [], ""
    res = fetch_work(work_id, ["xml"], presets, cbeta_ebook)
    wdir = work_dir(cbeta_ebook, work_id, title, presets, create=False)
    have = find_local_xml(wdir, canon, no) if wdir else []
    if have and not quiet:
        print(f"{work_id}: 官方下载 → {len(have)} 文件（{wdir}）")
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
    其余 html/txt/docx/epub 缺啥下啥。返回本次新获取的 {kind: [路径]}（已有的不算）。"""
    from .verify import find_official
    fetched = {}
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
    return fetched


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="pycbeta.fetch",
                                 description="CBETA 官方资源下载（XML / html/docx/epub/txt/odt 基线，平展落 cbeta_ebook）")
    ap.add_argument("id", help="CBETA 佛典編號，如 T0349 / T0099 / A1057 / X1271")
    ap.add_argument("-f", "--format", default="all",
                    help="格式：xml,html,docx,epub,txt,txt_notes,odt（逗号列表）或 all")
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