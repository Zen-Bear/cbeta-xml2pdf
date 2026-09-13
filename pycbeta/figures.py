"""图片（<graphic url="../figures/{canon}/{file}">）来源解析与缺失预取。

- 本地搜索顺序：{work}/figures/ → {work}/txt/（官方 text-with-notes 自带 gif）→ xml 候选源 figures/
- 远端：cbeta-git/CBR2X-figures（raw.githubusercontent.com/.../master/{canon}/{file}）
- 缺图策略：警告 + 占位，不中断渲染（调用方汇总 missing）。
"""

import os
import re

FIGURES_REPO_RAW = "https://raw.githubusercontent.com/cbeta-git/CBR2X-figures/master"
FIGURES_PREFIX = "../figures/"
GRAPHIC_URL_RE = re.compile(r'<graphic\b[^>]*\burl\s*=\s*"([^"]+)"', re.I)

EMU_PER_PX = 9525  # 914400 EMU/inch @96dpi


def split_graphic_url(url):
    """'../figures/X/X59p0224_01.gif' -> ('X', 'X59p0224_01.gif')。

    取不到目录段时返回 (None, basename)；空 url 返回 (None, "")。
    """
    u = (url or "").replace("\\", "/").strip()
    if not u:
        return None, ""
    m = re.match(r"^(?:\.\./)*figures/([^/]+)/([^/]+)$", u)
    if m:
        return m.group(1), m.group(2)
    return None, u.split("/")[-1]


def graphic_basename(url):
    """graphic url → 文件名（X59p0224_01.gif）。"""
    return split_graphic_url(url)[1]


def download_url(canon, basename, tmpl):
    """按模板拼远端地址（模板变量 {canon}/{file}）。"""
    return tmpl.format(canon=canon, file=basename)


def looks_like_image(path):
    """本地文件是否像图片（存在、非空、不以 '<' 开头，防 404 页面）。"""
    try:
        if not (os.path.isfile(path) and os.path.getsize(path) > 0):
            return False
        with open(path, "rb") as f:
            return not f.read(1).startswith(b"<")
    except OSError:
        return False


def find_figure(basename, dirs):
    """按顺序在目录中找 basename；返回首个存在且非空的文件路径，否则 None。"""
    if not basename:
        return None
    for d in dirs or []:
        if not d:
            continue
        p = os.path.join(d, basename)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return p
        except OSError:
            continue
    return None


def normalize_dirs(dirs):
    """只保留存在的目录（去重，绝对路径）。"""
    out = []
    for d in dirs or []:
        if d and os.path.isdir(d):
            ap = os.path.abspath(d)
            if ap not in out:
                out.append(ap)
    return out


def search_dirs(work_dir=None, xml_file=None, xml_repo=None):
    """渲染用图片搜索目录（存在才收）。

    顺序：{work}/figures → {work}/txt → xml 同目录 figures/txt → 仓库 figures。
    """
    cands = []
    if work_dir:
        cands += [os.path.join(work_dir, "figures"), os.path.join(work_dir, "txt")]
    if xml_file:
        d = os.path.dirname(os.path.abspath(xml_file))
        cands += [os.path.join(d, "figures"), os.path.join(d, "txt")]
    if xml_repo:
        cands.append(os.path.join(xml_repo, "figures"))
    return normalize_dirs(cands)


def work_figure_dirs(ebook_root, work_id, xml_file=None):
    """按 work 定位搜索目录（create=False，只找已有 work 目录；找不到回退 xml 同目录）。"""
    dirs = []
    if ebook_root and work_id:
        try:
            from .fetch import work_dir
            wd = work_dir(ebook_root, work_id, "", None, create=False)
        except Exception:
            wd = None
        if wd:
            dirs += [os.path.join(wd, "figures"), os.path.join(wd, "txt")]
    if xml_file:
        d = os.path.dirname(os.path.abspath(xml_file))
        dirs += [os.path.join(d, "figures"), os.path.join(d, "txt")]
    return normalize_dirs(dirs)


def graphic_urls_in_text(text):
    """轻量抽取 XML 文本中全部 <graphic url>（去重保序；不做全量解析）。"""
    out = []
    for m in GRAPHIC_URL_RE.finditer(text or ""):
        u = m.group(1).strip()
        if u and u not in out:
            out.append(u)
    return out


def is_figure_only(el):
    """元素是否仅含图片（子节点忽略空白文本与 Lb/Pb/anchor/milestone 空节点后，
    全为 figure/graphic 且至少一个）。duck-typed，不依赖 model。"""
    found = False
    for c in getattr(el, "children", None) or []:
        tag = getattr(c, "tag", None)
        tl = tag.lower() if isinstance(tag, str) else None
        if tl in ("lb", "pb", "anchor", "milestone"):
            continue
        if tag in ("figure", "graphic"):
            found = True
            continue
        if tag is None and not (getattr(c, "text", "") or "").strip():
            continue
        return False
    return found


def gif_size(path):
    """读 GIF 文件头取 (宽, 高) 像素；非 GIF/失败返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
    except OSError:
        return None
    if len(head) < 10 or head[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    w = head[6] + (head[7] << 8)
    h = head[8] + (head[9] << 8)
    return (w, h) if w > 0 and h > 0 else None


def png_size(path):
    """读 PNG IHDR 取 (宽, 高) 像素；非 PNG/失败返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    import struct
    w, h = struct.unpack(">II", head[16:24])
    return (w, h) if w > 0 and h > 0 else None


def jpeg_size(path):
    """读 JPEG SOF 取 (宽, 高) 像素；非 JPEG/失败返回 None（SOS 之前无 SOF 即放弃）。"""
    try:
        with open(path, "rb") as f:
            data = f.read(1 << 16)
    except OSError:
        return None
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 9 > n:
                return None
            h = (data[i + 5] << 8) + data[i + 6]
            w = (data[i + 7] << 8) + data[i + 8]
            return (w, h) if w > 0 and h > 0 else None
        if m == 0xDA:
            return None  # 进熵编码区，SOF 应在其前；没见到即放弃
        if m in (0xD8, 0xD9) or (0xD0 <= m <= 0xD7) or m == 0x01:
            i += 2
            continue
        if i + 4 > n:
            return None
        ln = (data[i + 2] << 8) + data[i + 3]
        if ln < 2:
            return None
        i += 2 + ln
    return None


def image_size(path):
    """图片像素尺寸 (w, h)；未知格式/失败返回 None。"""
    return gif_size(path) or png_size(path) or jpeg_size(path)
