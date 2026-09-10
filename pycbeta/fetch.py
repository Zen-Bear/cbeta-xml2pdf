# -*- coding: utf-8 -*-
"""CBETA 官方资源下载（独立工具 + 供 -i 佛典編號 / 校验按需调用）。

用法：python -m pycbeta.fetch T0349 [-f all] [--config ...] [--download-dir ...] [--xml-dir ...]
格式：xml, html, docx, epub, txt（无校注）, txt_notes（含校注）, odt；-f all = 全部。
落盘：XML → {download_dir}/{canon}/{canon}{vol}/{file}；基线 → {download_dir}/{canon}/{id}/。
统一根下已有平展 work 目录（如 `YP0021 異部宗輪論語體釋`）时优先落该目录
（XML 直接放根下，基线 html/docx/odt/epub 放根下、txt 进 {id}.txt/、txt_notes 进 {id}.txt_notes/），
没有才用仓库布局；已落盘（任一布局）不再重复下载。
txt 与 txt_notes 分目录存放（同名文件内容不同，混放会覆盖）。
说明：docx/odt 目前官方仅大正藏 T 与《卍續藏》X 提供，其它藏经 404 时静默跳过。
"""

import glob
import io
import os
import re
import shutil
import subprocess
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
    "download_dir": "",
}

_SOURCE_HINT = ("本地 XML 源未配置：在 config.user.json 的 source.xml_dir 填写 "
                "（GUI 数据源窗口可视编辑），或 --xml-dir 指定")
_DOWNLOAD_HINT = ("下载目录未配置：在 config.user.json 的 source.download_dir 填写 "
                  "（GUI 数据源窗口可视编辑），或 --download-dir 指定")


def resolve_source(presets=None, xml_dir=None, download_dir=None,
                   need_xml=True):
    """source 解析（显式参数 > presets source > 空即报错）。
    两键都必须显式有值（出厂留空），空即 ValueError 指引去处；"" 视同未配。
    need_xml=False 时不要求 xml_dir（纯下载场景；download_dir 仍必须）。"""
    cfg = (presets.get("source") or {}) if isinstance(presets, dict) else {}
    xml_dir = (xml_dir or cfg.get("xml_dir") or "").strip()
    if not xml_dir and need_xml:
        raise ValueError(_SOURCE_HINT)
    download_dir = (download_dir or cfg.get("download_dir") or "").strip()
    if not download_dir:
        raise ValueError(_DOWNLOAD_HINT)
    return xml_dir, download_dir
DEFAULT_DOWNLOADS = {
    "xml": "https://raw.githubusercontent.com/cbeta-org/xml-p5/master/{canon}/{canon}{vol}/{file}",
    "xml_repo": "https://github.com/cbeta-org/xml-p5",
    "html": "https://cbdata.dila.edu.tw/stable/download/html/{id}.html.zip",
    "docx": "https://cbdata.dila.edu.tw/stable/download/docx/{canon}/{id}.zip",
    "epub": "https://cbdata.dila.edu.tw/stable/download/epub/{canon}/{id}.epub",
    "txt": "https://cbdata.dila.edu.tw/stable/download/text/{id}.txt.zip",
    "txt_notes": "https://cbdata.dila.edu.tw/stable/download/text-with-notes/{id}.txt.zip",
    "odt": "https://cbdata.dila.edu.tw/stable/download/odt/{canon}/{id}.zip",
}


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
    """sutra_mapping.txt 查表：列 = canon,vol,no,… → [{vol, file}]（多冊全返）。"""
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
                out.append({"vol": vol, "file": f"{canon}{vol}n{no}.xml"})
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


def _git_sparse_xml(canon: str, no: str, xml_repo: str, dest_root: str,
                    flat: Optional[str] = None) -> List[str]:
    """目录表缺失或 raw 下载失败时的兜底：sparse clone 仓库的 canon 目录并查找。

    flat 给定时落入已有平展目录（与 _fetch_one 的优先规则一致），否则沿用仓库布局。"""
    try:
        repo_dir = os.path.join(dest_root, "xml-p5")
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none",
                            "--sparse", xml_repo, repo_dir],
                           check=True, capture_output=True)
        subprocess.run(["git", "sparse-checkout", "set", canon],
                       cwd=repo_dir, check=True, capture_output=True)
    except Exception:
        return []
    hits = sorted(glob.glob(os.path.join(repo_dir, canon, "**", f"*n{no}.xml"), recursive=True))
    saved = []
    for h in hits:
        if flat is not None:
            target = os.path.join(flat, os.path.basename(h))
        else:
            vol = os.path.basename(os.path.dirname(h))
            target = os.path.join(dest_root, canon, vol, os.path.basename(h))
        if not os.path.isfile(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(h, "rb") as src, open(target, "wb") as dst:
                dst.write(src.read())
        saved.append(target)
    return saved


def _flat_dir(download_root: str, work_id: str) -> Optional[str]:
    """统一根下已存在的平展 work 目录（如 `YP0021 異部宗輪論語體釋`），没有返回 None。

    下载优先落已有平展目录（与库内既有布局一致，一经一目录）；
    新书无平展目录时沿用仓库布局。只认目录，前缀须为完整 work id
    （`T` 这类藏目录不会被误命中）。"""
    for entry in sorted(glob.glob(os.path.join(download_root, f"{work_id}*"))):
        if os.path.isdir(entry):
            return entry
    return None


def _txt_subdir(fmt: str, work_id: str) -> str:
    """txt 族整理子目录名：txt → {id}.txt/，txt_notes → {id}.txt_notes/。

    两者必须隔离（同名文件内容不同，混放会互相覆盖）。"""
    return f"{work_id}.txt_notes" if fmt == "txt_notes" else f"{work_id}.txt"


def _fmt_existing(fmt: str, canon: str, work_id: str, base_dir: str) -> List[str]:
    """该格式已落盘的基线文件（避免重复下载；txt/txt_notes 独立子目录）。"""
    sub = {"html": "html", "docx": "docx", "odt": "odt", "epub": "epub",
           "txt": "text", "txt_notes": "text-with-notes"}[fmt]
    d = os.path.join(base_dir, sub)
    if fmt == "epub":
        p = os.path.join(d, f"{work_id}.epub")
        return [p] if os.path.isfile(p) else []
    if fmt in ("txt", "txt_notes"):
        return sorted(glob.glob(os.path.join(d, _txt_subdir(fmt, work_id), "*.txt")))
    return sorted(glob.glob(os.path.join(d, "**", f"{work_id}_*.{fmt}"), recursive=True))


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
                         flat: str) -> List[str]:
    """基线落已有平展目录（库内既有布局）：html/docx/odt/epub 文件放目录根下，
    txt 进 {id}.txt、txt_notes 进 {id}.txt_notes/；递归收集时排除 out/
    （平展目录自带 out/ 生成物）。失败静默返回 []。"""
    if fmt == "epub":
        p = os.path.join(flat, f"{work_id}.epub")
        existing = [p] if os.path.isfile(p) else []
    elif fmt in ("txt", "txt_notes"):
        existing = _collect_txt_flat(flat, fmt, work_id)
    else:
        existing = []
        for p in sorted(glob.glob(os.path.join(flat, "**", f"{work_id}_*.{fmt}"),
                                  recursive=True)):
            if f"{os.sep}out{os.sep}" in os.path.abspath(p):
                continue
            existing.append(p)
    if existing:
        return existing  # 平展已有，不重复下载

    if fmt == "epub":
        url = dl.get("epub", DEFAULT_DOWNLOADS["epub"]).format(canon=canon, id=work_id)
        dest = os.path.join(flat, f"{work_id}.epub")
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
    zip_path = os.path.join(flat, f"{work_id}.{fmt}.zip")
    if not os.path.isfile(zip_path):
        if not _http_download(url, zip_path):
            return []
    try:
        _unzip(zip_path, flat)
    except zipfile.BadZipFile:
        return []
    if fmt in ("txt", "txt_notes"):
        # 与仓库分支一致：顶层 {id}_*.txt 整理入 {id}.txt/ 或 {id}.txt_notes/ 目录；
        # 整理（move）只收顶层文件，不自动搬动用户已归档的文件
        d = os.path.join(flat, _txt_subdir(fmt, work_id))
        os.makedirs(d, exist_ok=True)
        for p in glob.glob(os.path.join(flat, f"{work_id}_*.txt")):
            shutil.move(p, os.path.join(d, os.path.basename(p)))
        return _collect_txt_flat(flat, fmt, work_id)
    out = []
    for p in sorted(glob.glob(os.path.join(flat, "**", f"{work_id}_*.{fmt}"),
                              recursive=True)):
        if f"{os.sep}out{os.sep}" in os.path.abspath(p):
            continue
        out.append(p)
    return out


def _fetch_one(work_id: str, fmt: str, canon: str, no: str,
               dl: Dict, source_cfg: Dict, download_dir: str) -> List[str]:
    """下载单个格式，失败静默返回 []。"""
    if fmt == "xml":
        saved = []
        flat = _flat_dir(download_dir, work_id)
        files = catalog_lookup(source_cfg.get("catalog", ""), canon, no)
        if not files:
            return _git_sparse_xml(canon, no, dl.get("xml_repo", DEFAULT_DOWNLOADS["xml_repo"]),
                                   download_dir, flat)
        for rec in files:
            url = dl.get("xml", DEFAULT_DOWNLOADS["xml"]).format(
                canon=canon, vol=rec["vol"], file=rec["file"])
            repo_dest = os.path.join(download_dir, canon, f"{canon}{rec['vol']}", rec["file"])
            dest = os.path.join(flat, rec["file"]) if flat else repo_dest
            if os.path.isfile(dest):
                saved.append(dest)
                continue
            if flat is not None and os.path.isfile(repo_dest):
                # 仓库已有：直接复用，不重复下载（布局以平展为准只影响新下载）
                saved.append(repo_dest)
                continue
            if _http_download(url, dest):
                saved.append(dest)
        if not saved:
            saved = _git_sparse_xml(canon, no, dl.get("xml_repo", DEFAULT_DOWNLOADS["xml_repo"]),
                                    download_dir, flat)
        return saved

    flat = _flat_dir(download_dir, work_id)
    if flat is not None:
        # 平展目录已存在：基线直接落该目录（库内既有布局），仓库已有则复用
        got = _fetch_baseline_flat(work_id, fmt, dl, canon, flat)
        if got:
            return got
        base_dir = os.path.join(download_dir, canon, work_id)
        return _fmt_existing(fmt, canon, work_id, base_dir)

    base_dir = os.path.join(download_dir, canon, work_id)
    existing = _fmt_existing(fmt, canon, work_id, base_dir)
    if existing:
        return existing  # 该格式已落盘，不重复下载
    sub = {"html": "html", "docx": "docx", "odt": "odt", "epub": "epub",
           "txt": "text", "txt_notes": "text-with-notes"}[fmt]
    out_dir = os.path.join(base_dir, sub)

    if fmt == "epub":
        url = dl.get("epub", DEFAULT_DOWNLOADS["epub"]).format(canon=canon, id=work_id)
        dest = os.path.join(out_dir, f"{work_id}.epub")
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
    zip_path = os.path.join(out_dir, f"{work_id}.{fmt}.zip")
    if not os.path.isfile(zip_path):
        if not _http_download(url, zip_path):
            return []
    try:
        _unzip(zip_path, out_dir)
    except zipfile.BadZipFile:
        return []
    if fmt in ("txt", "txt_notes"):
        # txt zip 顶层为 {id}_*.txt，整理入 {id}.txt/ 或 {id}.txt_notes/ 目录
        #（find_official 的 {s}.txt/*.txt 与 {s}.txt_notes/*.txt 模式）
        d = os.path.join(out_dir, _txt_subdir(fmt, work_id))
        os.makedirs(d, exist_ok=True)
        for p in glob.glob(os.path.join(out_dir, f"{work_id}_*.txt")):
            shutil.move(p, os.path.join(d, os.path.basename(p)))
        return sorted(glob.glob(os.path.join(d, "*.txt")))
    # html/docx/odt zip 内可能含 {id}/ 子目录，递归收集
    return sorted(glob.glob(os.path.join(out_dir, "**", f"{work_id}_*.{fmt}"), recursive=True))


def fetch_work(work_id: str, formats: List[str], presets: Optional[Dict] = None,
               download_dir: Optional[str] = None) -> Dict[str, List[str]]:
    """下载一部经的多个格式；返回 {fmt: [路径]}（失败格式为 []）。

    presets: load_presets() 结果（含 source/downloads）；缺省读默认配置。
    """
    if presets is None:
        presets = load_presets()
    source_cfg = {**DEFAULT_SOURCE, **(presets.get("source") or {})}
    dl = {**DEFAULT_DOWNLOADS, **(presets.get("downloads") or {})}
    _, download_dir = resolve_source(presets, download_dir=download_dir,
                                     need_xml=False)
    canon, no = parse_work_id(work_id)
    out = {}
    for fmt in formats:
        if fmt not in ALL_FORMATS:
            out[fmt] = []
            continue
        out[fmt] = _fetch_one(work_id, fmt, canon, no, dl, source_cfg, download_dir)
    return out


def ensure_baselines(work_id: str, kinds: List[str], presets: Optional[Dict],
                     download_dir: str) -> Dict[str, List[str]]:
    """校验按需调用：对缺失的基线格式下载（docx/odt 非 T/X 等 404 静默跳过）。

    xml 不是基线（由 -i/列表模式另行保证）、odt 从不参与比对，故跳过；
    其余 html/txt/docx/epub 缺啥下啥。返回本次新获取的 {kind: [路径]}（已有的不算）。"""
    from .verify import find_official
    fetched = {}
    for kind in kinds:
        if kind in ("xml", "odt"):
            continue
        existing = find_official(download_dir, work_id, kind)
        if existing:
            continue
        res = fetch_work(work_id, [kind], presets, download_dir)
        if res.get(kind):
            fetched[kind] = res[kind]
            print(f"  {work_id}: 官方基线缺失，已下载 {kind}（{len(res[kind])} 文件）")
    return fetched


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="pycbeta.fetch",
                                 description="CBETA 官方资源下载（XML 源 / html/docx/epub/txt/odt 基线）")
    ap.add_argument("id", help="CBETA 佛典編號，如 T0349 / T0099 / A1057 / X1271")
    ap.add_argument("-f", "--format", default="all",
                    help="格式：xml,html,docx,epub,txt,txt_notes,odt（逗号列表）或 all")
    ap.add_argument("--config", help="自定义 config.json")
    ap.add_argument("--download-dir", default=None, help="下载落盘目录（默认 config source.download_dir）")
    args = ap.parse_args(argv)

    work_id = args.id
    if not is_work_id(work_id):
        ap.error(f"不是有效的佛典編號: {work_id}")
    presets = load_presets(args.config) if args.config else load_presets()
    if args.format == "all":
        formats = list(ALL_FORMATS)
    else:
        formats = [f.strip() for f in args.format.split(",") if f.strip()]
    result = fetch_work(work_id, formats, presets, args.download_dir)
    ok = 0
    for fmt, paths in result.items():
        if paths:
            ok += 1
            print(f"{fmt:8} -> {len(paths)} 文件")
            for p in paths[:3]:
                print(f"          {p}")
            if len(paths) > 3:
                print(f"          … 共 {len(paths)}")
        else:
            print(f"{fmt:8} -> 下载失败（官方可能未提供该藏经此格式，如 docx/odt 仅 T/X）")
    print(f"完成：{work_id} 成功 {ok}/{len(formats)} 种格式")
    return 0


if __name__ == "__main__":
    sys.exit(main())