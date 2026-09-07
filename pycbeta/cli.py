"""pycbeta 命令行应用（与核心库分离）。

核心库只做解析与渲染；本模块负责参数解析、配置装配与输出调度。
入口：python -m pycbeta … 或 from pycbeta.cli import main。
"""

import argparse
import json
import os
import re
import sys

from .parser import P5Parser
from .render_html import HtmlRenderer
from .render_pdf import PdfRenderer, docx_to_pdf, DOCX_PDF_CHAIN
from .render_docx import DocxRenderer
from .render_md import MdRenderer
from .render_epub import EpubRenderer
from .theme import Theme, PAGE_PRESETS, OUTPUT_PRESETS, ENGINE_PRESETS, load_presets, resolve_theme_css, _PRESETS_PATH
from .filename import apply_template

_ALL_FORMATS = ["html", "pdf", "docx", "md", "epub"]
_FORMAT_EXT = {"html": "", "pdf": ".pdf", "docx": ".docx", "md": ".md", "epub": ".epub"}
_FONT_LANGS = ("zh-Hant", "zh-Hans")


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _user_slot_theme():
    """用户槽 theme 键（无槽/无键/非法返回 ""）；CLI 无 --config 时优先于出厂。"""
    try:
        with open(os.path.join(_REPO_ROOT, "config.user.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    v = (data or {}).get("theme", "")
    return v if isinstance(v, str) else ""


def _resolve_cli_theme(args, presets, config_path):
    """CLI 主题四档 → (path|None, 说明)：显式 --theme > config.theme 槽 > 内置。
    无 --config 时用户槽 theme 优先于出厂 config。"""
    if getattr(args, "theme", None):
        return args.theme, "显式 --theme"
    value = (presets or {}).get("theme", "") or ""
    base_dir = os.path.dirname(os.path.abspath(config_path)) if config_path else None
    if not getattr(args, "config", None):
        value = _user_slot_theme() or value
    return resolve_theme_css(value, base_dir)





def scaled_page_presets(page_presets, factor: float):
    """大字版：页面方案的 doc_size 兜底字号跟随 font_scale 等比放大（不改原配置）。"""
    out = {}
    for name, cfg in (page_presets or {}).items():
        cfg = dict(cfg or {})
        try:
            if "doc_size" in cfg:
                cfg["doc_size"] = round(float(cfg["doc_size"]) * factor, 2)
        except (TypeError, ValueError):
            pass
        out[name] = cfg
    return out


def load_theme(path, lang="zh-Hant"):
    if path.endswith(".css"):
        from .theme import theme_file_text
        return Theme.from_css(theme_file_text(path), lang)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Theme(data.get("tags") or data)


def _notes_marker_font(out_defaults):
    """注释注码字体：output.notes_marker_font，旧键 marker_font 回退（None=Times New Roman）。"""
    return out_defaults.get("notes_marker_font", out_defaults.get("marker_font"))


def _annotations_source(config_path, presets):
    """annotations 配置来源（P6）：显式 --config 用其 presets；
    否则读内置 pycbeta/config.json——与其他 output.* 默认来源一致，
    否则直接改内置 config 开关会被静默忽略。返回 (spec, base_path)。"""
    if config_path:
        return (presets.get("annotations") if presets else None), config_path
    try:
        return load_presets().get("annotations"), _PRESETS_PATH
    except (OSError, ValueError):
        return None, None


def render_one(w, fmt, out_dir, out_name, args, theme):
    # pdf 默认 footnote：docx2pdf 中间 docx 用真页底脚注（html2pdf 下 HtmlRenderer 无分页，footnote 与 endnote 同归文末，无影响）
    note_mode = args.notes or ("footnote" if fmt in ("docx", "pdf") else "endnote")
    os.makedirs(out_dir, exist_ok=True)
    # 难字注音（P6）：main() 已由 config.annotations 装载为 {"table","scheme"} 或 None；
    # getattr 兼容第三方旧式 args（无该属性即无注音）
    ann = getattr(args, "annotations", None)

    if fmt == "html":
        files = HtmlRenderer(theme=theme, notes=note_mode,
                             name_template=args.name_template,
                             ignore_xml_style=args.ignore_xml_style,
                             ignore_xml_space=args.ignore_xml_space,
                             grayscale=args.grayscale,
                             show_notes=args.show_notes,
                             inline_brackets=args.inline_brackets,
                             annotations=ann).render_work(w, out_dir)
        print(f"{w.id}: html({note_mode}) -> {len(files)} file(s) in {out_dir}")

    elif fmt == "docx":
        res = DocxRenderer(theme=theme, page=args.page, notes=note_mode,
                           page_presets=args.page_presets,
                           latin_font=args.latin_font,
                           ignore_xml_style=args.ignore_xml_style,
                           ignore_xml_space=args.ignore_xml_space,
                           verse_caesura=args.verse_caesura,
                           verse_strip_quotes=args.verse_strip_quotes,
                           grayscale=args.grayscale,
                           page_border=args.page_border,
                           bookmarks=args.bookmarks,
                           split=args.split_juan,
                           show_close_juan=args.show_close_juan,
                           suppress_jhead_dup=args.suppress_jhead_dup,
                           inline_brackets=args.inline_brackets,
                           footnote_per_page=args.footnote_per_page,
                           show_notes=args.show_notes,
                           pagination=args.pagination,
                           suppress_title_notes=args.suppress_title_notes,
                            footnote_separator=args.footnote_separator,
                            series_title=args.series_title,
                            gaiji_fonts=getattr(args, "gaiji_fonts", None),
                            gaiji_lang=getattr(args, "gaiji_lang", "zh-Hant"),
                           vertical=getattr(args, "vertical", False),
                           notes_marker_font=getattr(args, "notes_marker_font",
                               getattr(args, "marker_font", None)),
                           annotations=ann) \
              .render_work(w, out_dir, filename=out_name)
        if isinstance(res, list):
            print(f"{w.id}: docx({note_mode}, split) -> {len(res)} file(s)")
        else:
            print(f"{w.id}: docx({note_mode}) -> {res}")

    elif fmt == "md":
        fn = MdRenderer(theme=theme, notes=note_mode,
                        show_notes=args.show_notes,
                        inline_brackets=args.inline_brackets,
                        annotations=ann).render_work(w, out_dir, filename=out_name)
        print(f"{w.id}: md({note_mode}) -> {fn}")

    elif fmt == "epub":
        fn = EpubRenderer(theme=theme, notes=note_mode,
                          ignore_xml_style=args.ignore_xml_style,
                          ignore_xml_space=args.ignore_xml_space,
                          show_notes=args.show_notes,
                          annotations=ann).render_work(
            w, out_dir, filename=out_name)
        print(f"{w.id}: epub({note_mode}) -> {fn}")

    elif fmt == "pdf":
        # 管线选择：默认 docx2pdf（保真度高、带经文资讯尾页）；
        # 竖排需要 HTML 管线（DOCX 渲染器未实现竖排），自动切换。
        # 语法：管线[:单体]，如 docx2pdf:wps、html2pdf:prince
        pipeline, _, single = (args.engine or "").partition(":")
        if not pipeline:
            pipeline = "html2pdf" if args.vertical else "docx2pdf"

        base = os.path.splitext(out_name)[0]
        target = os.path.join(out_dir, base + ".pdf")
        used = {}

        if pipeline == "docx2pdf":
            chain = ([single] if single else None) or args.docx_pdf_chain
            docx_res = DocxRenderer(theme=theme, page=args.page,
                                    page_presets=args.page_presets,
                                    latin_font=args.latin_font,
                                    ignore_xml_style=args.ignore_xml_style,
                                    ignore_xml_space=args.ignore_xml_space,
                                    notes=note_mode if note_mode != "footnote" else "footnote",
                                    grayscale=args.grayscale,
                                    page_border=args.page_border,
                                    bookmarks=args.bookmarks,
                                    split=args.split_juan,
                                    show_notes=args.show_notes,
                                    suppress_title_notes=args.suppress_title_notes,
                                    footnote_separator=args.footnote_separator,
                                    series_title=args.series_title,
                                    gaiji_fonts=getattr(args, "gaiji_fonts", None),
                                    gaiji_lang=getattr(args, "gaiji_lang", "zh-Hant"),
                                    vertical=getattr(args, "vertical", False),
                                    notes_marker_font=getattr(args, "notes_marker_font",
                                        getattr(args, "marker_font", None)),
                                    annotations=ann) \
                .render_work(w, out_dir, filename=base + ".docx")

            def emit(pdf, backend):
                if args.engine_tag:
                    want = os.path.join(out_dir, f"{base}_{backend}.pdf")
                    if os.path.abspath(want) != os.path.abspath(pdf):
                        os.rename(pdf, want)
                    pdf = want
                print(f"{w.id}: pdf({backend},{note_mode}) -> {pdf}")

            if isinstance(docx_res, list):
                for d in docx_res:
                    u = {}
                    pdf = docx_to_pdf(d, os.path.splitext(d)[0] + ".pdf",
                                      chain=chain, used=u)
                    emit(pdf, u.get("backend", "docx2pdf"))
            else:
                pdf = docx_to_pdf(docx_res, target, chain=chain, used=used)
                emit(pdf, used.get("backend", "docx2pdf"))
        else:
            # HTML 管线：chromium/prince/weasyprint/cbetapdf/外部注册引擎
            chain = ([single] if single else None) or args.html_engine_chain
            r = PdfRenderer(page=args.page, vertical=args.vertical, notes=note_mode,
                            theme=theme, engine=(single or None),
                            page_presets=args.page_presets,
                            ignore_xml_style=args.ignore_xml_style,
                            ignore_xml_space=args.ignore_xml_space,
                            grayscale=args.grayscale,
                            page_border=args.page_border,
                            bookmarks=args.bookmarks,
                            split=args.split_juan,
                            show_notes=args.show_notes,
                            html_engine_chain=chain,
                            zoom=args.pdf_zoom,
                            annotations=ann)
            html_res = r.render_work(w, out_dir, filename=base + ".html")

            def emit(pdf, backend):
                if args.engine_tag:
                    want = os.path.join(out_dir, f"{base}_{backend}.pdf")
                    if os.path.abspath(want) != os.path.abspath(pdf):
                        os.rename(pdf, want)
                    pdf = want
                print(f"{w.id}: pdf({backend},{note_mode}) -> {pdf}")

            if isinstance(html_res, list):
                for h in html_res:
                    r.convert_with_chain(h, os.path.splitext(h)[0] + ".pdf")
                    emit(os.path.splitext(h)[0] + ".pdf", getattr(r, "last_engine", pipeline))
            else:
                r.convert_with_chain(html_res, target)
                emit(target, getattr(r, "last_engine", pipeline))


def resolve_output(xml_fn, fmt, args, work):
    ext = _FORMAT_EXT[fmt]
    src_dir = os.path.dirname(os.path.abspath(xml_fn))
    base = os.path.splitext(os.path.basename(xml_fn))[0]
    if args.output:
        out = args.output
        if fmt != "html" and out.lower().endswith(ext) and not os.path.isdir(out):
            return os.path.dirname(os.path.abspath(out)), os.path.basename(out)
        out_name = apply_template(args.name_template, work) + ext if args.name_template else f"{work.id}{ext}"
        return out, (None if fmt == "html" else out_name)
    if fmt == "html":
        return os.path.join(src_dir, base + "_html"), None
    out_name = apply_template(args.name_template, work) + ext if args.name_template else f"{work.id}{ext}"
    return src_dir, out_name


def process_file(xml_fn, formats, args, theme):
    w = P5Parser().parse(xml_fn)
    if args.t2s:
        from .simplify import simplify_work
        simplify_work(w)
    if getattr(args, "font_check", False):
        try:
            _fc_dir, _ = resolve_output(xml_fn, formats[0], args, w)
        except Exception:
            _fc_dir = None
        _run_font_check(w, args, theme, _fc_dir)
    for fmt in formats:
        out_dir, out_name = resolve_output(xml_fn, fmt, args, w)
        try:
            render_one(w, fmt, out_dir, out_name, args, theme)
        except NotImplementedError as e:
            print(f"{w.id}: {fmt} skipped - {e}", file=sys.stderr)


def _stack_font_files(theme, latin_font):
    """渲染字表文件：theme 各 tag font-family（去 CSS 通用族）+ 西文字体 + 补充字形。
    返回 (files, fallbacks)：files=[(label, path|None)]（缺失字体 path 为 None，报告标 MISS）；
    fallbacks=系统回退字（SimSun-ExtB/ExtG，Word 常自动回退，报告单列 FB 档）。"""
    from .theme import Theme as _Theme, _UNQUOTED_FONT_FAMILIES as _GEN
    from .fonts import locator as _loc, supplement_path as _sup
    if theme is None:
        theme = _Theme()
    fams = []
    for props in (getattr(theme, "tags", None) or {}).values():
        for part in ((props or {}).get("font-family") or "").split(","):
            name = part.strip().strip('"').strip("'")
            if name and name.lower() not in _GEN and name not in fams:
                fams.append(name)
    if latin_font and latin_font not in fams:
        fams.append(latin_font)
    loc = _loc()
    files = [(fam, loc.path(fam)) for fam in fams]
    sup = _sup()
    if sup:
        files.append(("CBETA Supplement", sup))
    fallbacks = []
    for fam in ("SimSun-ExtB", "simsunb", "SimSunExtG"):
        p = loc.path(fam)
        if p and all(p != q for _, q in fallbacks):
            fallbacks.append((fam, p))
    return files, fallbacks


def _run_font_check(w, args, theme, out_dir=None):
    from .fonts import font_check_report, format_font_report
    from .gaiji import GaijiDb
    try:
        files, fallbacks = _stack_font_files(theme, getattr(args, "latin_font", None))
        rep = font_check_report(w, files, GaijiDb(), fallbacks)
    except RuntimeError as e:
        print(f"font-check {w.id}: 跳过（{e}）")
        return
    text = format_font_report(rep, w.id)
    try:
        print(text)
    except UnicodeEncodeError:
        # gbk 控制台打不出 ExtB/G 生僻字：码位 U+XXXX 可读，字形看同目录落盘文件
        print(text.encode("gbk", "replace").decode("gbk"))
    if out_dir:
        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, f"font-check-{w.id}.txt"),
                      "w", encoding="utf-8") as f:
                f.write(text + "\n")
            print(f"font-check {w.id}: 完整报告已写入 {out_dir}")
        except Exception as e:
            print(f"font-check {w.id}: 报告落盘失败（{e}）")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pycbeta", description="CBETA XML P5 -> HTML / PDF / DOCX / MD / EPUB")

    shared = ap.add_argument_group("共享参数（所有格式）")
    shared.add_argument("-i", "--input", required=False, default=None,
                        help="input XML file, directory, or CBETA 佛典編號 (e.g. T0349/T0099/A1057/X1271；"
                             "編號从本地 XML 源查找，缺失则自动从官方下载)")
    shared.add_argument("-o", "--output",
                        help="output file or directory (default: same name+ext in source dir)")
    shared.add_argument("-f", "--format", required=False, default=None,
                        help="formats: html,pdf,docx,md,epub (comma list) or all")
    shared.add_argument("--theme",
                        help="自定义主题，替换默认主题层 styles/pdf_docx.css "
                             "(作用于 pdf/docx)；html/epub 默认不带主题层，"
                             "传 --theme 会在官方基底 cbeta_golden.css 之上追加")
    shared.add_argument("--font-lang", choices=["zh-Hant", "zh-Hans"],
                        default=None,
                        help="字库：zh-Hant 繁体（默认）/ zh-Hans 简体（CSS :root 双栏变量切换）。"
                             "t2s 未显式指定时自动切简体")
    shared.add_argument("--t2s", dest="t2s_flag", action="store_true",
                        default=None,
                        help="简体输出：OpenCC t2s 把正文/注释/元数据转为简体"
                             "（未指定 --font-lang 时自动套用简体字库；"
                             "--no-t2s 可关闭）")
    shared.add_argument("--no-t2s", dest="t2s_flag", action="store_false",
                        default=None,
                        help="强制繁体输出（覆盖 config output.t2s=true）")
    shared.add_argument("--font-scale", type=float, default=None,
                        help="字号等比缩放（重排式大字，老人版推荐 1.33/1.5；"
                             "默认取 config output.font_scale；与 --verify 互斥）")
    shared.add_argument("--config", "--presets-file",
                        help="自定义全局配置 JSON（复制 pycbeta/config.json 修改，"
                             "含 pages/engines/output/theme）")
    shared.add_argument("--xml-dir", default=None,
                        help="本地 XML 源目录（-i 佛典編號 查找；默认 config source.xml_dir）")
    shared.add_argument("--download-dir", default=None,
                        help="官方下载落盘目录（默认 config source.download_dir）")
    shared.add_argument("--name-template",
                        help='output filename template, e.g. "[id] [书名]（[作者]）" '
                             "(tokens: [id] [书名] [作者] [vol] [juan])")
    shared.add_argument("--list-fonts", nargs="?", const="", default=None,
                        metavar="关键词",
                        help="列出本机已安装字体（家族名|路径），可带关键词过滤；"
                             "CSS 字体变量里填第一列家族名。仅列表，不渲染")

    note = ap.add_argument_group("注释（所有格式）")
    note.add_argument("--notes", choices=["footnote", "endnote", "inline"],
                      help="注释方式。默认：docx=footnote（页底脚注），"
                           "html/pdf/md/epub=endnote（文末校注）")

    pg = ap.add_argument_group("页面（pdf/docx；纯 HTML 输出不适用）")
    pg.add_argument("--page", default="a4",
                    help="页面方案名（config.json 的 pages，键大小写不敏感；"
                         "或内置 a4/a5/信纸/手机/平板8寸/平板9寸/平板11寸/32开/16开）")

    pdfg = ap.add_argument_group("PDF 专属")
    pdfg.add_argument("--vertical", action="store_true",
                      help="vertical layout (writing-mode)：pdf 走 html2pdf 管线；"
                           "docx 直接分节纵排（sectPr textDirection tbRl）")
    pdfg.add_argument("--engine", default=None,
                      help="PDF 输出：'管线[:单体]'。默认 docx2pdf（DOCX→PDF，"
                           "后端链见 config.json engines.docx2pdf.chain）；"
                           "html2pdf[:chromium/prince/…] = HTML→PDF 管线；"
                           "chromium/prince/weasyprint/cbetapdf 等具体引擎名 = HTML 单引擎")
    pdfg.add_argument("--engine-tag", action="store_true",
                      help="输出的 PDF 文件名追加实际使用的引擎名（如 X60n1116_wps.pdf）")

    vg = ap.add_argument_group("校验（模块化，供 GUI 复用 pycbeta/verify.py）")
    vg.add_argument("--verify", action="store_true",
                    help="生成后自动逐字校验（正式管线对比官方 html/txt）")
    vg.add_argument("--verify-max-diff", type=int, default=10,
                    help="校验阈值 max-diff（缺+多≤阈值判OK，默认10）")
    vg.add_argument("--verify-diff-lines", type=int, default=5,
                    help="校验失败时打印差异行数（默认5）")
    vg.add_argument("--font-check", action="store_true",
                    help="豆腐字检测：逐字核对渲染字表覆盖率并打印报告（TOFU/仅补充字形/缺失字体，不中断渲染）")

    args = ap.parse_args(argv)

    if args.list_fonts is not None:
        from .fonts import search_fonts
        rows = search_fonts(args.list_fonts or "")
        lines = []
        for name, names, path in rows:
            alias = " / ".join(n for n in names[1:] if n != name)
            lines.append(f"{name}" + (f"（{alias}）" if alias else "") + f" | {path}")
        if rows:
            lines.append(f"共 {len(rows)} 款。CSS 字体变量里填第一列家族名（中英文皆可，要装字体的 GDI 可见名）。")
        else:
            lines.append("未找到匹配字体（换关键词再试，如：楷体 / kaiti / song）")
        try:
            print("\n".join(lines))
        except UnicodeEncodeError:
            # gbk 控台打不出中文家族名：重定向到文件看全量（> fonts.txt）
            print("\n".join(lines).encode("gbk", "replace").decode("gbk"))
        return 0
    if not args.input:
        ap.error("the following arguments are required: -i/--input")
    if not args.format:
        ap.error("the following arguments are required: -f/--format")

    if args.format == "all":
        formats = list(_ALL_FORMATS)
    else:
        formats = [f.strip() for f in args.format.split(",") if f.strip()]
        bad = [f for f in formats if f not in _ALL_FORMATS]
        if bad:
            ap.error(f"unknown format: {', '.join(bad)} (allowed: html,pdf,docx,md,epub,all)")

    args.page_presets = PAGE_PRESETS
    out_defaults = OUTPUT_PRESETS
    engines_cfg = ENGINE_PRESETS
    if args.config:
        presets = load_presets(args.config)
        args.page_presets = presets.get("pages") or PAGE_PRESETS
        out_defaults = presets.get("output") or {}
        engines_cfg = presets.get("engines") or {}

    args.ignore_xml_style = bool(out_defaults.get("ignore_xml_style"))
    args.ignore_xml_space = bool(out_defaults.get("ignore_xml_space"))
    args.verse_caesura = out_defaults.get("verse_caesura") or "　　"
    args.verse_strip_quotes = bool(out_defaults.get("verse_strip_quotes"))
    args.grayscale = bool(out_defaults.get("grayscale"))
    args.page_border = bool(out_defaults.get("page_border"))
    args.bookmarks = out_defaults.get("bookmarks", True)
    args.split_juan = bool(out_defaults.get("split_juan"))
    args.show_close_juan = bool(out_defaults.get("show_close_juan"))
    args.suppress_jhead_dup = out_defaults.get("suppress_jhead_dup", True)
    args.inline_brackets = out_defaults.get("inline_brackets", "fullwidth")
    args.footnote_per_page = out_defaults.get("footnote_per_page", True)
    args.show_notes = out_defaults.get("show_notes", True)
    args.print_mode = bool(out_defaults.get("print_mode"))
    args.pagination = out_defaults.get("pagination") or {}
    if not args.pagination and args.print_mode:
        # 旧配置迁移：print_mode=true ≡ pagination={enabled:true, duplex:true, juan:true}
        args.pagination = {"enabled": True, "duplex": True, "juan": True}
    args.suppress_title_notes = bool(out_defaults.get("suppress_title_notes"))
    args.pdf_zoom = float(out_defaults.get("pdf_zoom", 1.0))
    args.t2s = bool(out_defaults.get("t2s"))
    if args.font_scale is None:
        try:
            args.font_scale = float(out_defaults.get("font_scale", 1.0))
        except (TypeError, ValueError):
            ap.error(f"config output.font_scale 无效: {out_defaults.get('font_scale')!r}")
    if not args.font_scale > 0:
        ap.error(f"--font-scale 必须为正数: {args.font_scale!r}")
    args.series_title = out_defaults.get("series_title") or {}
    args.footnote_separator = (cfg_docx := out_defaults.get("docx") or {}).get("footnoteSeparator")
    args.notes_marker_font = _notes_marker_font(out_defaults)  # 注释注码字体（旧键 marker_font 回退）
    args.gaiji_fonts = cfg_docx.get("gaijiFonts")  # 缺字字体链 {zh-Hant:[...], zh-Hans:[...]}，渲染时懒解析首个已装
    # 难字注音（P6）：config-only（无 CLI 开关），顶层 annotations；装载为 {"table","scheme"} 或 None
    from .annotate import resolve_annotations
    ann_spec, ann_base = _annotations_source(
        args.config, presets if args.config else None)
    args.annotations = resolve_annotations(ann_spec, ann_base)
    if args.annotations is not None:
        _zones = args.annotations.get("rare_zones") or frozenset()
        _zs = f", zones={'+'.join(sorted(_zones))}" if _zones else ""
        if args.annotations.get("full_text"):
            _zs += ", full"
        _sup = args.annotations.get("rare_cmap") or frozenset()
        _sup_s = f", sup={len(_sup)}" if _sup else ""
        _rep = args.annotations.get("repeat", "all")
        _rep_s = f", repeat={_rep}" if _rep != "all" else ""
        print(f"annotations: {args.annotations['scheme']}, "
              f"{len(args.annotations['table'])} terms, "
              f"style={args.annotations.get('style', 'inline')}{_zs}{_sup_s}{_rep_s}")
    args.docx_pdf_chain = ((engines_cfg.get("docx2pdf") or {}).get("chain")
                           or list(DOCX_PDF_CHAIN))
    args.html_engine_chain = ((engines_cfg.get("html2pdf") or {}).get("chain")
                              or [(engines_cfg.get("html2pdf") or {}).get("engine")
                                  or "chromium"])

    theme_path, _theme_label = _resolve_cli_theme(
        args, presets if args.config else None,
        args.config if args.config else None)
    if args.t2s_flag is not None:
        args.t2s = args.t2s_flag
    # 字库语言：显式 --font-lang > t2s 自动简体 > 繁体
    font_lang = args.font_lang or ("zh-Hans" if args.t2s else "zh-Hant")
    if theme_path:
        theme = load_theme(theme_path, font_lang)
    elif font_lang != "zh-Hant" or args.font_scale != 1.0:
        theme = Theme(lang=font_lang)
    else:
        theme = None  # 渲染器内置 Theme()（=出厂 pdf_docx.css 繁体）
    # 西文字体随语言切换（页面方案显式 latin_font 仍优先，见 DocxRenderer）
    _th = theme if theme is not None else Theme(lang=font_lang)
    args.latin_font = _th.font_var("latin", "Calibri")
    args.gaiji_lang = font_lang  # 缺字字体链按此语言选表（render_docx 懒解析）
    if args.font_scale != 1.0:
        # 大字版：主题字号等比缩放 + 页面兜底字号跟随（版心/边距不动，自动重排）
        if theme is None:
            theme = Theme(lang=font_lang)
        theme.scale_font_sizes(args.font_scale)
        args.page_presets = scaled_page_presets(args.page_presets, args.font_scale)

    if os.path.isdir(args.input):
        xmls = []
        for dp, _dn, fns in os.walk(args.input):
            for f in sorted(fns):
                if f.endswith(".xml"):
                    xmls.append(os.path.join(dp, f))
        if not xmls:
            ap.error(f"no XML files under {args.input}")
        for x in xmls:
            process_file(x, formats, args, theme)
    elif os.path.isfile(args.input):
        process_file(args.input, formats, args, theme)
    else:
        # -i 佛典編號：先查本地 XML 源，缺失则从官方下载
        from .fetch import is_work_id, parse_work_id, find_local_xml, fetch_work
        if not is_work_id(args.input):
            ap.error(f"input not found: {args.input}")
        work_id = args.input
        _presets = load_presets(args.config) if args.config else load_presets()
        source_cfg = {**({"xml_dir": r"E:\dev\cbeta\test", "download_dir": r"E:\dev\cbeta\test"}),
                      **(_presets.get("source") or {})}
        xml_dir = args.xml_dir or source_cfg["xml_dir"]
        canon, no = parse_work_id(work_id)
        xmls = find_local_xml(xml_dir, canon, no)
        if not xmls:
            print(f"{work_id}: 本地 XML 源 {xml_dir} 未找到，从官方下载…")
            fetch_work(work_id, ["xml"], _presets, args.download_dir or source_cfg["download_dir"])
            xmls = find_local_xml(xml_dir, canon, no)
        if not xmls:
            ap.error(f"{work_id}: 本地与官方均未取得 XML")
        for x in xmls:
            process_file(x, formats, args, theme)

    # --verify：复用 pycbeta/verify.py 模块化能力，供 GUI 调用同一入口
    if args.verify:
        from .verify import normalize as v_norm, extract_text as v_extract, diff_stats as v_diff, find_official as v_find, strip_infos as v_strip_infos, _extract_html_parts as _v_hparts, _extract_txt_parts as _v_tparts, _ann_brackets_from as _v_rb
        import datetime, glob as _glob
        try:
            _presets_full = load_presets(args.config) if args.config else load_presets()
            _vp = _presets_full.get("verify") or {}
        except Exception:
            _presets_full = {}
            _vp = {}
        _rb = _v_rb(_presets_full)  # 自定义右侧注音括号（未启用→None，走默认剥除）
        v_compare_infos = bool(_vp.get("compareInfos", False))
        v_auto_fetch = bool(_vp.get("auto_fetch", True))
        src = os.path.dirname(os.path.abspath(args.input)) if os.path.isfile(args.input) else os.path.abspath(args.input)
        # 若输入为文件，其官方在同目录；若为目录，则 source 即该目录
        verify_out = os.path.join(src, "out", "verify")
        os.makedirs(verify_out, exist_ok=True)
        report_lines = []
        def vlog(msg=""):
            try:
                print(msg)
            except UnicodeEncodeError:
                # Windows gbk 控制台：注音声调符号等超出 gbk 范围时降级输出，不断链
                print(str(msg).encode("gbk", "replace").decode("gbk", "replace"))
            report_lines.append(msg)
        grand_fail = grand_total = 0
        results = []
        _t2s = None
        if args.t2s:
            # 简体校验：官方基线（繁体）经同一 t2s 管线转简体后再比对
            from .simplify import simplify_text as _t2s

        def _theirs_norm(raw, bkind=None):
            if args.t2s and bkind in ("txt", "txt_notes"):
                # 简体：text 族注记块移文末，与生成侧文末注记对齐（传统不动）
                _tb, _tn = _v_tparts(raw)
                raw = _tb + "\n" + _tn if _tn.strip() else _tb
            return v_norm(_t2s(raw) if _t2s else raw, _rb)
        xmls_v = xmls if os.path.isdir(args.input) else [args.input]
        for xml_fn in xmls_v:
            name = os.path.basename(xml_fn)
            block = [f"=== {name}"]
            block_failed = False
            # 为本文件确定每个格式的生成路径（与 resolve_output 一致）
            try:
                from .parser import P5Parser as _P
                w = _P().parse(xml_fn)
                # 繁体剥离键：官方基线恒为繁体，官方侧 strip_docx_head 必须用繁体键
                t_title = (w.metadata.get("title") or "").strip()
                t_docnumber = (w.metadata.get("docNumber") or "").strip()
                t_series = (w.metadata.get("series") or "").strip()
                if args.t2s:
                    from .simplify import simplify_work as _sw
                    _sw(w)
            except Exception as e:
                block.append(f"  PARSE FAIL: {e}")
                grand_fail += 1; grand_total += 1
                block_failed = True
                results.append((block_failed, name, block))
                continue
            for fmt in formats:
                # 计算生成档路径（复用 resolve_output）
                out_dir, out_name = resolve_output(xml_fn, fmt, args, w)
                if fmt == "html":
                    # html 为多文件 Txxx_001.html，全部卷参与比较
                    gen_paths = sorted(_glob.glob(os.path.join(out_dir, "*.html")))
                    gen_path = gen_paths[0] if gen_paths else os.path.join(out_dir, f"{w.id}_001.html")
                else:
                    gen_path = os.path.join(out_dir, out_name) if out_name else ""
                    gen_paths = [gen_path] if gen_path else []
                if not gen_path or not os.path.isfile(gen_path):
                    block.append(f"  [--]  {fmt:5} gen not found: {gen_path}")
                    continue
                # 找官方
                stem = os.path.splitext(name)[0]
                scope_juan = bool(_vp.get("scope_juan", True))
                _juan = None
                if scope_juan:
                    from .verify import work_juan_numbers
                    _juan = work_juan_numbers(w)
                official = {}
                for kind in ("html","txt","txt_notes","docx","epub","odt"):
                    found = v_find(src, stem, kind, juan=_juan if kind in ("html", "docx", "txt_notes") else None)
                    if found: official[kind] = found
                base_kind = {"md":"txt","docx":"docx","html":"html","epub":"epub"}.get(fmt,"html")
                bases = []
                if base_kind in official:
                    bases.append((base_kind, official[base_kind]))
                fb = official.get("html")
                if fb and all(p != fb for _,p in bases): bases.append(("html", fb))
                if args.t2s and "txt_notes" in official and all(p != official["txt_notes"] for _, p in bases):
                    # 简体统一：txt_notes 优先（传统不动；缺失时落回现有顺序）
                    bases.insert(0, ("txt_notes", official["txt_notes"]))
                if not bases and v_auto_fetch:
                    # 基线缺失：按需调用 fetch 下载（docx/odt 非 T/X 等 404 静默跳过）
                    from .fetch import ensure_baselines
                    need = {"md": ["txt"], "docx": ["docx", "html"],
                            "html": ["html"], "epub": ["epub"]}.get(fmt, ["html"])
                    if args.t2s and "txt_notes" not in need:
                        need = ["txt_notes"] + need
                    ensure_baselines(w.id, need, load_presets(args.config) if args.config else load_presets(), src)
                    official = {}
                    for kind in ("html","txt","txt_notes","docx","epub","odt"):
                        found = v_find(src, stem, kind, juan=_juan if kind in ("html", "docx", "txt_notes") else None)
                        if found: official[kind] = found
                    bases = []
                    if base_kind in official:
                        bases.append((base_kind, official[base_kind]))
                    fb = official.get("html")
                    if fb and all(p != fb for _,p in bases): bases.append(("html", fb))
                    if args.t2s and "txt_notes" in official and all(p != official["txt_notes"] for _, p in bases):
                        bases.insert(0, ("txt_notes", official["txt_notes"]))
                if not bases:
                    block.append(f"  [--]  {fmt:5} no baseline")
                    continue
                ours_raw_all = "".join(v_extract(p) for p in gen_paths)
                docnumber = (w.metadata.get("docNumber") or "").strip()
                series = (w.metadata.get("series") or "").strip()
                if fmt == "docx":
                    title = (w.metadata.get("title") or "").strip()
                    from .verify import strip_docx_head as _sdh
                    ours_raw_all = _sdh(ours_raw_all, title, docnumber, series)
                ours = v_norm(ours_raw_all, _rb)
                if not v_compare_infos:
                    ours = v_norm(v_strip_infos(ours_raw_all), _rb)
                ok_any = False; best = None
                detail_lines = []
                for bkind, bpath in bases:
                    if isinstance(bpath, list):
                        if bkind in ("docx", "txt") and len(bpath) > 1:
                            from .verify import strip_docx_head as _sdh
                            title = t_title
                            parts = []
                            for p in bpath:
                                txt = v_extract(p)
                                if bkind == "docx":
                                    txt = _sdh(txt, title, t_docnumber, t_series)
                                if not v_compare_infos:
                                    txt = v_strip_infos(txt)
                                parts.append(txt)
                            merged_raw = "".join(parts)
                            # 保存合并文件到与生成文件相同的输出目录
                            try:
                                merged_dir = os.path.dirname(gen_path) if gen_path else os.path.join(verify_out, fmt)
                                os.makedirs(merged_dir, exist_ok=True)
                                merged_path = os.path.join(merged_dir, f"{stem}_official_merged_{bkind}.txt")
                                with open(merged_path, "w", encoding="utf-8") as mf:
                                    mf.write(merged_raw)
                            except Exception:
                                pass
                            theirs_n = _theirs_norm(merged_raw, bkind)
                            bpath_disp = f"{bpath[0]} (+{len(bpath)-1})"
                        elif len(bpath) > 1:
                            # 多卷官方 html：docx 回退时脚注统一放文末以对齐 docx；html 自身比较保持原样
                            if bkind == "html" and fmt == "docx":
                                bodies, foots = [], []
                                for p in bpath:
                                    b, f = _v_hparts(p)
                                    title = t_title
                                    from .verify import strip_docx_head as _sdh2
                                    b = _sdh2(b, title, t_docnumber, t_series)
                                    f = _sdh2(f, title, t_docnumber, t_series)
                                    if not v_compare_infos:
                                        b = v_strip_infos(b)
                                        f = v_strip_infos(f)
                                    bodies.append(b)
                                    foots.append(f)
                                theirs_n = _theirs_norm("".join(bodies) + "\n" + "".join(foots), bkind)
                            else:
                                from .verify import strip_docx_head as _sdh2
                                parts = []
                                for p in bpath:
                                    txt = v_extract(p)
                                    if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                                        title = t_title
                                        txt = _sdh2(txt, title, t_docnumber, t_series)
                                    if not v_compare_infos:
                                        txt = v_strip_infos(txt)
                                    parts.append(txt)
                                theirs_n = _theirs_norm("".join(parts), bkind)
                            bpath_disp = f"{bpath[0]} (+{len(bpath)-1})"
                        else:
                            _raw = v_extract(bpath[0])
                            if bkind == "docx":
                                from .verify import strip_docx_head as _sdh
                                title = t_title
                                _raw = _sdh(_raw, title, t_docnumber, t_series)
                            elif bkind == "html" and fmt == "docx":
                                from .verify import strip_docx_head as _sdh
                                title = t_title
                                _raw = _sdh(_raw, title, t_docnumber, t_series)
                            if not v_compare_infos:
                                _raw = v_strip_infos(_raw)
                            theirs_n = _theirs_norm(_raw, bkind)
                            bpath_disp = bpath[0]
                    else:
                        _raw = v_extract(bpath)
                        if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                            from .verify import strip_docx_head as _sdh
                            title = t_title
                            _raw = _sdh(_raw, title, t_docnumber)
                        if not v_compare_infos:
                            _raw = v_strip_infos(_raw)
                        theirs_n = _theirs_norm(_raw, bkind)
                        bpath_disp = bpath
                    m, mi, ex, ctx = v_diff(ours, theirs_n)
                    total = mi + ex
                    cur = (bkind,bpath_disp,m,mi,ex,ctx)
                    if best is None or total < (best[3]+best[4]):
                        best = cur
                    if total <= args.verify_max_diff:
                        ok_any = True
                        why = "仅含CBETA版本日期/版权等元数据微小差异" if total>0 else "逐字完全一致"
                        detail = f"      → {bkind} 通过: {why}"
                        if total>0 and ctx:
                            for idx,(tag,i1,i2,j1,j2) in enumerate(ctx[:args.verify_diff_lines],1):
                                a_snip = ours[max(0,i1-10):i1+40].replace("\n","")
                                b_snip = theirs_n[max(0,j1-10):j1+40].replace("\n","")
                                detail += f"\n      {idx}. 【源】{b_snip}\n         【新】{a_snip}"
                        detail_lines = [detail]
                        break
                    else:
                        lines=[]
                        for idx,(tag,i1,i2,j1,j2) in enumerate(ctx[:args.verify_diff_lines],1):
                            a_snip = ours[max(0,i1-10):i1+40].replace("\n","")
                            b_snip = theirs_n[max(0,j1-10):j1+40].replace("\n","")
                            lines.append(f"      {idx}. 【源】{b_snip}\n         【新】{a_snip}")
                        snippet = "\n".join(lines) if lines else ""
                        detail = f"      → {bkind} 失败: 缺{mi}字(生成档缺失) / 多{ex}字(生成档多出) 合计{total} >阈值{args.verify_max_diff}"
                        if snippet: detail += f"\n{snippet}"
                        detail_lines.append(detail)
                if best is None: continue
                bkind,bpath,_,best_mi,best_ex,_ = best
                grand_total += 1
                if not ok_any:
                    grand_fail += 1; block_failed = True
                mark = "[OK]" if ok_any else "[FAIL]"
                op = "≤" if ok_any else ">"
                block.append(f"  {mark} (缺{best_mi}/多{best_ex} {op}阈值{args.verify_max_diff})")
                block.append(f"  {fmt} 【源】{bpath}")
                block.append(f"  {fmt} 【新】{gen_path}")
                block.extend(detail_lines)
            results.append((block_failed, name, block))
        results.sort(key=lambda x: (0 if x[0] else 1, x[1]))
        for _,_,block in results:
            for line in block:
                vlog(line)
        summary = f"{grand_total} compared, {grand_fail} failed (阈值 max-diff={args.verify_max_diff})"
        vlog(f"\n{summary}")
        vlog(f"完成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            rpt = os.path.join(verify_out, "report.txt")
            with open(rpt, "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines)+"\n")
            print(f"报告已写入: {rpt}")
        except Exception as e:
            print(f"写入报告失败: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
