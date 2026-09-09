"""官方数据更新：缺字库 + 补充字型 + sutra_mapping 从上游直链同步本地。

URL 表在 cbeta/data/remote_sources.json（改 URL 只改文件，不改代码；
缺失/非法大声报错）。另含手动项（悉曇/蘭札字型，只有下载网页无直链，
仅记录展示、不自动下载）。

用法：python -m pycbeta --update-data [--dry-run]
流程（每项独立）：下到临时文件 → 先校验再落盘 → 与本地比对（一致跳过，
不一致覆盖，git 在管不另备份）→ 汇总报告。失败不写盘，不断其他项。
"""

import json
import os
import tempfile

REMOTE_SOURCES_NAME = ("cbeta", "data", "remote_sources.json")

_TTF_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1")
_TTF_MIN_SIZE = 1024 * 1024  # 1MB：防 404 页面冒充


def _repo_root(root=None):
    return os.path.abspath(root or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))


def load_sources(root=None):
    """读 URL 表 → [(key, kind, url, dest_tuple)]（dest 为空=手动项）。

    文件缺失/非法 JSON/顶层非对象 → 抛 OSError/ValueError（大声报错，不静默）。
    """
    from .theme import _strip_json_comments
    path = os.path.join(_repo_root(root), *REMOTE_SOURCES_NAME)
    with open(path, encoding="utf-8") as f:
        data = json.loads(_strip_json_comments(f.read()))
    if not isinstance(data, dict) or not data:
        raise ValueError(f"remote_sources 非空对象不符：{path}")
    out = []
    for key, spec in data.items():
        if not isinstance(spec, dict):
            raise ValueError(f"remote_sources[{key}] 非对象：{path}")
        kind = spec.get("kind", "")
        if kind not in ("json-dict", "ttf", "text", "manual"):
            raise ValueError(f"remote_sources[{key}].kind 未知：{kind!r}")
        dest = spec.get("dest", "") or ""
        parts = tuple(p for p in dest.replace("\\", "/").split("/") if p)
        if kind != "manual" and (not spec.get("url") or not parts):
            raise ValueError(f"remote_sources[{key}] 缺 url/dest：{path}")
        out.append({"key": key, "kind": kind, "url": spec.get("url", ""),
                    "dest": parts, "note": spec.get("note", "") or ""})
    return out


def _check_json_dict(raw):
    """(ok, 说明)：JSON 解析成非空 dict；返回条目数供报告。"""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        return False, f"JSON 非法：{exc}", None
    if not isinstance(data, dict) or not data:
        return False, "顶层非空对象不符", None
    return True, f"{len(data)} 条", data


def _check_ttf(raw):
    """(ok, 说明)：TrueType 头 + 体积门槛。"""
    if len(raw) < _TTF_MIN_SIZE:
        return False, f"体积过小（{len(raw)}B），疑似错误页", None
    if raw[:4] not in _TTF_MAGICS and raw[:5] != b"wOF2":
        return False, "文件头非字体", None
    return True, f"{len(raw)} 字节", None


def _check_text(raw):
    """(ok, 说明)：非空文本；返回行数供报告。"""
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        return False, f"非 UTF-8 文本：{exc}", None
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False, "空文件", None
    return True, f"{len(lines)} 行", text


def _diff_detail(kind, old_raw, new_data, new_raw):
    """新旧比对说明（给报告用）：新增/删除/修改数或体积/行数变化。"""
    if kind == "json-dict":
        try:
            old = json.loads(old_raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            return "本地非法，全量替换"
        if not isinstance(old, dict):
            return "本地非对象，全量替换"
        new_keys = [k for k in new_data if k not in old]
        gone = [k for k in old if k not in new_data]
        changed = [k for k in new_data
                   if k in old and new_data[k] != old[k]]
        bits = [f"{len(old)}→{len(new_data)} 条"]
        if new_keys:
            bits.append(f"新增 {len(new_keys)}（{', '.join(new_keys[:6])}"
                        + ("…" if len(new_keys) > 6 else "") + "）")
        if gone:
            bits.append(f"删除 {len(gone)}")
        if changed:
            bits.append(f"修改 {len(changed)}")
        return "；".join(bits)
    try:
        old_text = old_raw.decode("utf-8")
        new_text = new_raw.decode("utf-8")
        lo = [l for l in old_text.splitlines() if l.strip()]
        ln = [l for l in new_text.splitlines() if l.strip()]
        if lo == ln:
            return "内容一致（仅换行符差异），跳过"
        return f"{len(lo)}→{len(ln)} 行"
    except UnicodeError:
        pass
    if len(old_raw) == len(new_raw):
        return "体积一致但字节不同"
    return f"{len(old_raw)}→{len(new_raw)} 字节"


def update_all(root=None, dry_run=False, download=None, sources=None):
    """执行更新 → [{"key","status","detail"}]（纯逻辑，可单测）。

    status ∈ unchanged（一致跳过）/ updated（已覆盖）/ preview（dry-run 预告）/
    manual（手动项，仅展示）/ failed（下载失败或校验不通过，本地未动）。
    download(url, dest_tmp) -> bool 可注入（单测）；缺省走 fetch._http_download。
    sources 可注入（单测）；缺省读 remote_sources.json。
    """
    if download is None:
        from .fetch import _http_download as download
    base = _repo_root(root)
    if sources is None:
        sources = load_sources(base)
    report = []
    for src in sources:
        key, kind, url = src["key"], src["kind"], src["url"]
        if kind == "manual":
            report.append({"key": key, "status": "manual",
                           "detail": (src.get("note") or "请自行下载") +
                           f"（{url}）"})
            continue
        dest = os.path.join(base, *src["dest"])
        fd, tmp = tempfile.mkstemp(prefix="xml2pdf-data-")
        os.close(fd)
        try:
            try:
                ok = download(url, tmp)
            except Exception as exc:  # noqa: BLE001 —— 单项失败不断其他项
                ok = False
            if not ok:
                report.append({"key": key, "status": "failed",
                               "detail": "下载失败"})
                continue
            with open(tmp, "rb") as f:
                raw = f.read()
            if kind == "json-dict":
                good, info, data = _check_json_dict(raw)
            elif kind == "ttf":
                good, info, data = _check_ttf(raw)
            else:
                good, info, data = _check_text(raw)
            if not good:
                report.append({"key": key, "status": "failed",
                               "detail": info})
                continue
            old_raw = b""
            if os.path.isfile(dest):
                with open(dest, "rb") as f:
                    old_raw = f.read()
            if old_raw == raw:
                report.append({"key": key, "status": "unchanged",
                               "detail": info})
                continue
            detail = info + "；" + _diff_detail(kind, old_raw, data, raw)
            if dry_run:
                report.append({"key": key, "status": "preview",
                               "detail": "[预演，未写入] " + detail})
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.replace(tmp, dest)
            report.append({"key": key, "status": "updated", "detail": detail})
        finally:
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass
    return report


def format_report(report):
    """报告 → 打印行。"""
    lines = []
    for r in report:
        mark = {"unchanged": "＝", "updated": "←", "preview": "？",
                "manual": "○", "failed": "✗"}.get(r["status"], "?")
        lines.append(f"[{mark}] {r['key']}: {r['detail']}")
    return lines


def main(argv=None, root=None):
    """CLI 入口（--update-data 用）：返回进程退出码。"""
    import argparse
    ap = argparse.ArgumentParser(prog="pycbeta-update-data")
    ap.add_argument("--dry-run", action="store_true",
                    help="只下载比对不写盘")
    ns = ap.parse_args(argv)
    for line in format_report(update_all(root=root, dry_run=ns.dry_run)):
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("gbk", "replace").decode("gbk"))
    return 0
