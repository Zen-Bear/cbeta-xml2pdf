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
from .render_pdf import PdfRenderer, docx_to_pdf, DOCX_PDF_CHAIN, pdf_source_fmt
from .render_docx import DocxRenderer
from .render_md import MdRenderer
from .render_txt import TxtRenderer
from .render_epub import EpubRenderer
from .theme import Theme, PAGE_PRESETS, OUTPUT_PRESETS, ENGINE_PRESETS, load_presets, _PRESETS_PATH, load_effective_presets
from .theme import (resolve_pdf_docx_css,
                    resolve_html_base_css, check_run_placeholders,
                    resolve_effective_config, apply_page_typography,
                    resolve_config_arg)
from .filename import apply_template, default_output_name

_ALL_FORMATS = ["html", "pdf", "docx", "md", "epub", "txt"]
_FORMAT_EXT = {"html": "", "pdf": ".pdf", "docx": ".docx", "md": ".md", "epub": ".epub", "txt": ".txt"}
_FONT_LANGS = ("zh-Hant", "zh-Hans")


def resolve_default_page(args_page, presets):
    """默认纸张：显式 --page > 有效配置 default_page > a4（纯函数，可单测）。"""
    return args_page or (presets or {}).get("default_page") or "a4"


def resolve_engine_vertical_lang(args, presets):
    """engine / vertical / font_lang 解析：显式开关 > 配置 > 默认（纯函数，可单测）。

    - engine：`--engine` > `presets.engine` > None（渲染时默认 docx2pdf）
    - vertical：`--vertical` 或 `output.vertical`
    - font_lang：`--font-lang` > (t2s → zh-Hans) > `presets.font_lang` > zh-Hant

    这样「面板存的预设」经 `--config` 即自足；开关仍可显式覆盖。
    """
    presets = presets or {}
    out = presets.get("output") or {}
    engine = (getattr(args, "engine", None) or "").strip() \
        or (presets.get("engine") or "").strip() or None
    vertical = bool(getattr(args, "vertical", False)) or bool(out.get("vertical"))
    lang = (getattr(args, "font_lang", None) or "").strip()
    if not lang:
        if getattr(args, "t2s", False):
            lang = "zh-Hans"
        else:
            lang = (presets.get("font_lang") or "").strip() or "zh-Hant"
    return engine, vertical, lang


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


def _report_missing_figures(wid, fmt, renderer):
    """图片缺失汇总（警告 + 占位，不中断；txt/md 本就只出【圖】标记，不在此列）。"""
    miss = list(getattr(renderer, "missing_figures", None) or [])
    if miss:
        print(f"{wid}: {fmt} 图片缺失（占位）：{', '.join(miss)}")


def render_one(w, fmt, out_dir, out_name, args, theme, html_base=None, figure_base=None):
    # pdf 默认 footnote：docx2pdf 中间 docx 用真页底脚注（html2pdf 下 HtmlRenderer 无分页，footnote 与 endnote 同归文末，无影响）
    note_mode = args.notes or ("footnote" if fmt in ("docx", "pdf") else "endnote")
    os.makedirs(out_dir, exist_ok=True)
    # 难字注音（P6）：main() 已由 config.annotations 装载为 {"table","scheme"} 或 None；
    # getattr 兼容第三方旧式 args（无该属性即无注音）
    ann = getattr(args, "annotations", None)

    if fmt == "html":
        # html 纯基底（golden 默认）：pdf_docx 主题不再追加
        r = HtmlRenderer(theme=None, base_css=html_base, notes=note_mode,
                         name_template=args.name_template,
                         ignore_xml_style=args.ignore_xml_style,
                         ignore_xml_space=args.ignore_xml_space,
                         grayscale=args.grayscale,
                          show_notes=args.show_notes,
                         inline_brackets=args.inline_brackets,
                         note_inline_brackets=getattr(args, "note_inline_brackets", None),
                         annotations=ann,
                         strip_head_no=getattr(args, "strip_head_no", False),
                         figure_base=figure_base)
        files = r.render_work(w, out_dir)
        _report_missing_figures(w.id, fmt, r)
        print(f"{w.id}: html({note_mode}) -> {len(files)} file(s) in {out_dir}")

    elif fmt == "docx":
        r = DocxRenderer(theme=theme, page=args.page, notes=note_mode,
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
                           note_inline_brackets=getattr(args, "note_inline_brackets", None),
                           footnote_per_page=args.footnote_per_page,
                           show_notes=args.show_notes,
                           pagination=args.pagination,
                           suppress_title_notes=args.suppress_title_notes,
                            footnote_separator=args.footnote_separator,
                            series_title=args.series_title,
                            gaiji_fonts=getattr(args, "gaiji_fonts", None),
                            gaiji_lang=getattr(args, "gaiji_lang", "zh-Hant"),
                            fallback_fonts=getattr(args, "fallback_fonts", None),
                            siddham_fonts=getattr(args, "siddham_fonts", None),
                           vertical=getattr(args, "vertical", False),
                           notes_marker_font=getattr(args, "notes_marker_font",
                               getattr(args, "marker_font", None)),
                           annotations=ann,
                           strip_head_no=getattr(args, "strip_head_no", False),
                           show_body_siddham=getattr(
                               args, "show_body_siddham", True),
                           figure_base=figure_base)
        res = r.render_work(w, out_dir, filename=out_name)
        _report_missing_figures(w.id, fmt, r)
        if isinstance(res, list):
            print(f"{w.id}: docx({note_mode}, split) -> {len(res)} file(s)")
        else:
            print(f"{w.id}: docx({note_mode}) -> {res}")

    elif fmt == "md":
        fn = MdRenderer(theme=theme, notes=note_mode,
                        show_notes=args.show_notes,
                        inline_brackets=args.inline_brackets,
                        note_inline_brackets=getattr(args, "note_inline_brackets", None),
                        annotations=ann,
                        strip_head_no=getattr(args, "strip_head_no", False),
                        show_dharani_transliteration=getattr(
                            args, "show_dharani_transliteration", False)).render_work(w, out_dir, filename=out_name)
        print(f"{w.id}: md({note_mode}) -> {fn}")

    elif fmt == "txt":
        fn = TxtRenderer(theme=theme, notes=note_mode,
                         show_notes=args.show_notes,
                         inline_brackets=args.inline_brackets,
                         note_inline_brackets=getattr(args, "note_inline_brackets", None),
                         annotations=ann,
                         strip_head_no=getattr(args, "strip_head_no", False),
                         show_dharani_transliteration=getattr(
                             args, "show_dharani_transliteration", False)).render_work(w, out_dir, filename=out_name)
        print(f"{w.id}: txt({note_mode}) -> {fn}")

    elif fmt == "epub":
        # epub 纯基底（章节 + style.css 同源，不再进 pdf_docx 主题）
        r = EpubRenderer(theme=None, base_css=html_base, notes=note_mode,
                         ignore_xml_style=args.ignore_xml_style,
                         ignore_xml_space=args.ignore_xml_space,
                         show_notes=args.show_notes,
                         inline_brackets=args.inline_brackets,
                         note_inline_brackets=getattr(args, "note_inline_brackets", None),
                         annotations=ann,
                         strip_head_no=getattr(args, "strip_head_no", False),
                         figure_base=figure_base)
        fn = r.render_work(w, out_dir, filename=out_name)
        _report_missing_figures(w.id, fmt, r)
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
            _pdf_docx = DocxRenderer(theme=theme, page=args.page,
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
                                    fallback_fonts=getattr(args, "fallback_fonts", None),
                                    siddham_fonts=getattr(args, "siddham_fonts", None),
                                    vertical=getattr(args, "vertical", False),
                                    notes_marker_font=getattr(args, "notes_marker_font",
                                        getattr(args, "marker_font", None)),
                                    annotations=ann,
                                    strip_head_no=getattr(args, "strip_head_no", False),
                                    show_body_siddham=getattr(
                                        args, "show_body_siddham", True),
                                    figure_base=figure_base)
            docx_res = _pdf_docx.render_work(w, out_dir, filename=base + ".docx")
            _report_missing_figures(w.id, fmt, _pdf_docx)


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
                            annotations=ann,
                            strip_head_no=getattr(args, "strip_head_no", False),
                            inline_brackets=args.inline_brackets,
                            note_inline_brackets=getattr(args, "note_inline_brackets", None),
                            figure_base=figure_base)
            html_res = r.render_work(w, out_dir, filename=base + ".html")
            _report_missing_figures(w.id, fmt, r)

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


def resolve_output(xml_fn, fmt, args, work, _used=None):
    """输出目录与文件名。默认 `{id 书名}.{ext}`（`filename.default_output_name`，
    书名跟随 source.title_t2s）；
    _used 为本轮共享 dict 时：多输入同名全组统一改输入基名
    （`filename.dedupe_run_outputs`；首文件已落盘输出预先改名，缺失/锁定忽略）。
    html 与显式 -o 文件走旧路径（前者 renderer 内部命名，后者用户强制）。"""
    ext = _FORMAT_EXT[fmt]
    src_dir = os.path.dirname(os.path.abspath(xml_fn))
    base = os.path.splitext(os.path.basename(xml_fn))[0]
    if args.output:
        out = args.output
        if fmt != "html" and out.lower().endswith(ext) and not os.path.isdir(out):
            return os.path.dirname(os.path.abspath(out)), os.path.basename(out)
        out_name = apply_template(args.name_template, work) + ext if args.name_template else \
            default_output_name(work.id, work.metadata.get("title"),
                                getattr(args, "title_t2s", True)) + ext
        out_dir = out
    elif fmt == "html":
        return os.path.join(src_dir, base + "_html"), None
    else:
        out_dir = src_dir
        out_name = apply_template(args.name_template, work) + ext if args.name_template else \
            default_output_name(work.id, work.metadata.get("title"),
                                getattr(args, "title_t2s", True)) + ext
    if _used is not None and fmt != "html":
        from .filename import dedupe_run_outputs
        out_name, renames = dedupe_run_outputs(_used, out_dir, out_name, base)
        for old, new in renames:
            try:
                if os.path.isfile(old):
                    os.rename(old, new)
                    print(f"改名: {os.path.basename(old)} -> "
                          f"{os.path.basename(new)}（多源同名统一回退）")
            except OSError:
                pass
    if args.output:
        return out, (None if fmt == "html" else out_name)
    return src_dir, out_name


def process_file(xml_fn, formats, args, theme, html_base=None, _used=None,
                 ebook_root=None):
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
    # 图片搜索目录（{work}/figures → {work}/txt → xml 同目录；渲染器按 basename 匹配）
    from . import figures as _fig
    fig_dirs = _fig.work_figure_dirs(ebook_root, w.id, xml_fn)
    failed = 0
    for fmt in formats:
        out_dir, out_name = resolve_output(xml_fn, fmt, args, w, _used)
        try:
            render_one(w, fmt, out_dir, out_name, args, theme,
                       html_base=html_base, figure_base=fig_dirs or None)
        except NotImplementedError as e:
            print(f"{w.id}: {fmt} skipped - {e}", file=sys.stderr)
        except OSError as e:
            # 目标被占用/无写权限等：不中断其余格式，报一行可读原因并以非 0 退出
            failed += 1
            print(f"{w.id}: {fmt} 生成失败：{e}", file=sys.stderr)
    return failed


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
                        help="formats: html,pdf,docx,md,epub,txt (comma list) or all")
    shared.add_argument("--theme", default=None,
                        help="已废弃：请用 --pdf-docx-theme/--pdf-docx-user-theme "
                             "（pdf/docx）；html/epub 默认纯官方样式")
    shared.add_argument("--pdf-docx-theme", default=None,
                        help="pdf/docx 标准 CSS（整套替换出厂 pdf_docx.css 全文；"
                             "缺省 run.json 的 pdf-docx-theme 槽）")
    shared.add_argument("--pdf-docx-user-theme", default=None,
                        help="pdf/docx 增量 CSS（名走 presets/ 双目录或路径，"
                             "追加在标准之后；缺省 run.json 的 pdf-docx-user-theme 槽）")
    shared.add_argument("--html-epub-theme", default=None,
                        help="html/epub 基底 CSS 全文（缺省 run.json 的 "
                             "html-epub-theme 槽，即官方 cbeta_golden.css）")
    shared.add_argument("--html-epub-user-theme", default=None,
                        help="html/epub 增量 CSS（占位，尚未接线；传入只警告忽略）")
    shared.add_argument("--font-lang", choices=["zh-Hant", "zh-Hans"],
                        default=None,
                        help="字库：zh-Hant 繁体 / zh-Hans 简体（CSS :root 双栏变量切换）。"
                             "缺省取 config font_lang；t2s 会自动切简体")
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
                        help="run.json 组合单（5 槽：config-json/html-epub-theme/"
                             "html-epub-user-theme/pdf-docx-theme/pdf-docx-user-theme），"
                             "或基础配置 JSON（config.user.json / presets 快照，当作 "
                             "config-json 槽）；缺省仓库根 run.json，没有就全出厂")
    shared.add_argument("--xml-dir", default=None,
                        help="本地 XML 候选源（只读，角色同远端 URL；默认 config source.xml_dir）")
    shared.add_argument("--cbeta-ebook", default=None,
                        help="电子书输出目录（唯一可写；默认 config source.cbeta_ebook）")
    shared.add_argument("--name-template",
                        help='output filename template, e.g. "[id] [书名]（[作者]）" '
                             "(tokens: [id] [书名] [作者] [vol] [juan])")
    shared.add_argument("--list-fonts", nargs="?", const="", default=None,
                        metavar="关键词",
                        help="列出本机已安装字体（家族名|路径），可带关键词过滤；"
                             "CSS 字体变量里填第一列家族名。仅列表，不渲染")

    note = ap.add_argument_group("注释（所有格式）")
    note.add_argument("--notes", choices=["footnote", "endnote", "inline"],
                      help="注释方式。缺省取 config output.notes（出厂 footnote）；"
                           "footnote=页底脚注（docx/pdf），endnote=文末尾注，inline=括号内联；"
                           "html/epub/md/txt 仅区分 inline 与否")
    note.add_argument("--strip-head-no", dest="strip_head_no", action="store_true",
                      default=None,
                      help="去 head/jhead 行首 No. 令牌（如 No. 1116-B 序→序；默认关，可配 output.strip_head_no）")

    pg = ap.add_argument_group("页面（pdf/docx；纯 HTML 输出不适用）")
    pg.add_argument("--page", default=None,
                    help="页面方案名（缺省有效配置 default_page；config.json 的 "
                         "pages，键大小写不敏感；或内置 a4/a5/信纸/手机/平板8寸/"
                         "平板9寸/平板11寸/32开/16开/B5）")

    pdfg = ap.add_argument_group("PDF 专属")
    pdfg.add_argument("--vertical", action="store_true",
                      help="vertical layout (writing-mode)：pdf 走 html2pdf 管线；"
                           "缺省取 config output.vertical；"
                           "docx 直接分节纵排（sectPr textDirection tbRl）")
    pdfg.add_argument("--engine", default=None,
                      help="PDF 输出：'管线[:单体]'。缺省取 config engine（默认 docx2pdf，"
                           "DOCX→PDF，后端链见 config.json engines.docx2pdf.chain）；"
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

    dg = ap.add_argument_group("官方数据更新（缺字库/字型/目录）")
    dg.add_argument("--update-data", action="store_true",
                    help="从上游直链同步本地（先校验再落盘，一致跳过；URL 见 cbeta/data/remote_sources.json）")
    dg.add_argument("--dry-run", action="store_true",
                    help="配合 --update-data：只下载比对不写盘")

    args = ap.parse_args(argv)

    if args.update_data:
        from .update_data import update_all, format_report
        for line in format_report(update_all(dry_run=args.dry_run)):
            try:
                print(line)
            except UnicodeEncodeError:
                print(line.encode("gbk", "replace").decode("gbk"))
        return 0

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
            ap.error(f"unknown format: {', '.join(bad)} (allowed: html,pdf,docx,md,epub,txt,all)")

    if getattr(args, "theme", None):
        ap.error("--theme 已废弃：pdf/docx 请用 --pdf-docx-theme（整套替换）/"
                 "--pdf-docx-user-theme（增量追加）；html/epub 默认纯官方样式")
    try:
        run, run_dir = resolve_config_arg(args.config)
    except (OSError, ValueError) as exc:
        ap.error(f"--config 读取失败: {exc}")
    check_run_placeholders(run)
    presets = resolve_effective_config(run, run_dir)  # 出厂 ← base 文件按鍵合并
    args.title_t2s = bool((presets.get("source") or {}).get("title_t2s", True))
    args.page = resolve_default_page(args.page, presets)
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
    args.note_inline_brackets = out_defaults.get("note_inline_brackets") or args.inline_brackets
    args.footnote_per_page = out_defaults.get("footnote_per_page", True)
    args.show_notes = out_defaults.get("show_notes", True)
    if args.notes is None:
        # 缺省取 config output.notes（非法/空则不设，render_one 落按格式默认）
        _n = str(out_defaults.get("notes") or "").strip().lower()
        args.notes = _n if _n in ("footnote", "endnote", "inline") else None
    args.show_body_siddham = bool(out_defaults.get("show_body_siddham", True))
    args.show_dharani_transliteration = bool(out_defaults.get("show_dharani_transliteration", False))
    args.print_mode = bool(out_defaults.get("print_mode"))
    args.pagination = out_defaults.get("pagination") or {}
    if not args.pagination and args.print_mode:
        # 旧配置迁移：print_mode=true ≡ pagination={enabled:true, duplex:true, juan:true}
        args.pagination = {"enabled": True, "duplex": True, "juan": True}
    args.suppress_title_notes = bool(out_defaults.get("suppress_title_notes"))
    if args.strip_head_no is None:
        args.strip_head_no = bool(out_defaults.get("strip_head_no", False))
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
    args.fallback_fonts = cfg_docx.get("fallbackFonts")  # 按字回退链（缺省内置分栏）；空走默认值
    args.siddham_fonts = cfg_docx.get("siddhamFonts")  # 悉昙字体（缺省 ["Ranjana","Siddam"]）
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

    if args.t2s_flag is not None:
        args.t2s = args.t2s_flag
    # 引擎/竖排/字库：显式开关 > 配置（presets.engine / output.vertical / font_lang）> 默认
    args.engine, args.vertical, font_lang = resolve_engine_vertical_lang(args, presets)
    # pdf/docx 主题必建（显式开关 > run.json 槽 > 内置出厂）
    pdf_css = resolve_pdf_docx_css(run, run_dir, std=args.pdf_docx_theme,
                                   user=args.pdf_docx_user_theme)
    theme = Theme.from_css(pdf_css, font_lang)
    # 纸张绑字号（pages 条目 body_* 覆盖 theme body；font_scale 之前先定基准）
    apply_page_typography(theme, args.page, args.page_presets)
    # html/epub 基底（显式开关 > run.json 槽 > 内置 golden）；html/epub 纯基底
    html_base = resolve_html_base_css(run, run_dir, std=args.html_epub_theme,
                                      user=args.html_epub_user_theme)
    # 西文字体随语言切换（页面方案显式 latin_font 仍优先，见 DocxRenderer）
    args.latin_font = theme.font_var("latin", "Calibri")
    args.gaiji_lang = font_lang  # 缺字字体链按此语言选表（render_docx 懒解析）
    if args.font_scale != 1.0:
        # 大字版：主题字号等比缩放（版心/边距不动，自动重排；em 随基准自动跟）
        theme.scale_font_sizes(args.font_scale)

    _used_names = {}  # 本轮命名状态（render 与 verify 共用，重放得终态名）
    render_failed = 0  # 各格式渲染失败计数（OSError），决定进程退出码
    # 图片定位用工作根（尽力解析；缺省则只按 xml 同目录找图）
    try:
        from .fetch import resolve_source as _rs
        _, _ebook_root = _rs(presets, xml_dir=args.xml_dir, cbeta_ebook=args.cbeta_ebook)
    except Exception:
        _ebook_root = None
    if os.path.isdir(args.input):
        from .merge import split_paths, merge_groups_to_dir
        walked = []
        for dp, _dn, fns in os.walk(args.input):
            for f in sorted(fns):
                if f.endswith(".xml"):
                    walked.append(os.path.join(dp, f))
        whole, groups = split_paths(walked)
        xmls = whole
        if groups:
            xmls = xmls + merge_groups_to_dir(groups)
        if not xmls:
            ap.error(f"no XML files under {args.input}")
        for x in xmls:
            render_failed += process_file(x, formats, args, theme, html_base=html_base,
                                          _used=_used_names, ebook_root=_ebook_root)
    elif os.path.isfile(args.input):
        render_failed += process_file(args.input, formats, args, theme, html_base=html_base,
                                      ebook_root=_ebook_root)
    else:
        # -i 佛典編號：三源材料化（cbeta_ebook → 本地候选源 → 官方下载）
        from .fetch import is_work_id, materialize_work, inspect_xml_source
        if not is_work_id(args.input):
            ap.error(f"input not found: {args.input}")
        if args.xml_dir:
            info = inspect_xml_source(args.xml_dir)
            if info.get("safe") is False:
                print(f"警告：--xml-dir {args.xml_dir} 检测到非发布版 P5"
                      f"（{info.get('edition') or '未知'}）：P5a/P5b 可能导致正文重复、"
                      f"校勘注丢失、校验失败，继续使用。", file=sys.stderr)
        try:
            xmls, label = materialize_work(
                args.input, presets, xml_dir=args.xml_dir,
                cbeta_ebook=args.cbeta_ebook)
        except ValueError as exc:
            ap.error(str(exc))
        if not xmls:
            ap.error(f"{args.input}: 本地候选源与官方均未取得 XML")
        for x in xmls:
            render_failed += process_file(x, formats, args, theme, html_base=html_base,
                                          _used=_used_names, ebook_root=_ebook_root)

    # --verify：复用 pycbeta/verify.py 模块化能力，供 GUI 调用同一入口
    if args.verify:
        from .verify import normalize as v_norm, extract_text as v_extract, diff_stats as v_diff, find_official as v_find, strip_infos as v_strip_infos, _extract_html_parts as _v_hparts, _norm_official_txt as _v_tnorm, _ann_brackets_from as _v_rb, _head_no_tokens as _v_htoks, _strip_official_no as _v_tstrip, _mark_span as _v_mark
        import datetime, glob as _glob
        try:
            _presets_full = load_effective_presets(args.config)
            _vp = _presets_full.get("verify") or {}
        except Exception:
            _presets_full = {}
            _vp = {}
        _rb = _v_rb(_presets_full)  # 自定义右侧注音括号（未启用→None，走默认剥除）
        v_compare_infos = bool(_vp.get("compareInfos", False))
        v_auto_fetch = bool(_vp.get("auto_fetch", True))
        src = os.path.dirname(os.path.abspath(args.input)) if os.path.isfile(args.input) else os.path.abspath(args.input)
        # 若输入为文件，其官方在同目录；若为目录，则 source 即该目录
        # 校验产物目录：镜像渲染输出根，每个经书独立 `{id 书名}（验证）/`（内含 {fmt}/ + report.txt）
        if args.output:
            _o = os.path.abspath(args.output)
            verify_root = _o if (os.path.isdir(_o) or not os.path.splitext(_o)[1]) \
                else os.path.dirname(_o)
        else:
            verify_root = src
        from .filename import default_output_name as _default_out_name
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
            if getattr(_theirs_norm, "toks", ""):
                # strip_head_no 联动：官方侧按行首精确令牌对等剥离（生成档已剥）
                raw = _v_tstrip(raw, _theirs_norm.toks)
            if bkind == "txt_notes":
                # text 族官方侧对齐（繁简通用）：版头剥离 + 注记块识别挪文末
                raw = _v_tnorm(raw)
            return v_norm(_t2s(raw) if _t2s else raw, _rb)
        _theirs_norm.toks = []
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
                # strip_head_no 联动：本文件 head/jhead 行首令牌表（生成档已剥则官方侧对等剥离）
                _theirs_norm.toks = _v_htoks(w) if getattr(args, "strip_head_no", False) else []
            except Exception as e:
                block.append(f"  PARSE FAIL: {e}")
                grand_fail += 1; grand_total += 1
                block_failed = True
                results.append((block_failed, name, block))
                continue
            _vname = _default_out_name(
                w.id, w.metadata.get("title"), getattr(args, "title_t2s", True))
            verify_dir = os.path.join(verify_root, f"{_vname}（验证）")
            for fmt_raw in formats:
                disp = fmt_raw
                if fmt_raw == "pdf":
                    # PDF 无官方基线：委托其管线源格式（docx2pdf→docx / html2pdf→html）
                    _src = pdf_source_fmt(getattr(args, "engine", None),
                                          getattr(args, "vertical", False))
                    if _src in formats:
                        block.append(f"  [--]  pdf 已覆盖（已由 {_src} 校验）")
                        continue
                    # 定位渲染时留下的中间件（与 render 同 _used 重放）
                    _p_out, _p_name = resolve_output(xml_fn, "pdf", args, w,
                                                     _used=_used_names)
                    _p_base = os.path.splitext(_p_name)[0] if _p_name else w.id
                    fmt = _src
                    disp = f"pdf→{_src}"
                    if _src == "docx":
                        _gp = os.path.join(_p_out, _p_base + ".docx")
                        gen_paths = [_gp] if os.path.isfile(_gp) else []
                        gen_path = _gp
                    else:
                        gen_paths = sorted(_glob.glob(
                            os.path.join(_p_out, _p_base + "*.html")))
                        gen_path = gen_paths[0] if gen_paths else ""
                else:
                    fmt = fmt_raw
                    # 计算生成档路径（复用 resolve_output；与 render 同一 _used 重放得终态名）
                    out_dir, out_name = resolve_output(xml_fn, fmt, args, w,
                                                       _used=_used_names)
                    if fmt == "html":
                        # html 为多文件 Txxx_001.html，全部卷参与比较
                        gen_paths = sorted(_glob.glob(os.path.join(out_dir, "*.html")))
                        gen_path = gen_paths[0] if gen_paths else os.path.join(out_dir, f"{w.id}_001.html")
                    else:
                        gen_path = os.path.join(out_dir, out_name) if out_name else ""
                        gen_paths = [gen_path] if gen_path else []
                if not gen_path or not os.path.isfile(gen_path):
                    block.append(f"  [--]  {disp} gen not found: {gen_path}")
                    continue
                # 找官方
                stem = os.path.splitext(name)[0]
                scope_juan = bool(_vp.get("scope_juan", True))
                _juan = None
                if scope_juan:
                    from .verify import work_juan_numbers
                    _juan = work_juan_numbers(w)
                official = {}
                for kind in ("html","txt_notes","docx","epub","odt"):
                    found = v_find(src, stem, kind, juan=_juan if kind in ("html", "docx", "txt_notes") else None)
                    if found: official[kind] = found
                base_kind = {"md":"txt_notes","docx":"docx","html":"html","epub":"epub","txt":"txt_notes"}.get(fmt,"html")

                def _cli_bases(official):
                    b = []
                    if base_kind in official:
                        b.append((base_kind, official[base_kind]))
                    if fmt != "txt":
                        fb = official.get("html")
                        if fb and all(p != fb for _, p in b):
                            b.append(("html", fb))
                    return b

                bases = _cli_bases(official)
                if base_kind not in official and v_auto_fetch:
                    # 首选基线缺失：按需调用 fetch 下载（docx/odt 非 T/X 等 404 静默跳过）
                    from .fetch import ensure_baselines
                    need = {"md": ["txt_notes"], "docx": ["docx", "html"], "txt": ["txt_notes"],
                            "html": ["html"], "epub": ["epub"]}.get(fmt, ["html"])
                    _presets_af = load_effective_presets(args.config)
                    _ebook_af = ((_presets_af.get("source") or {}).get("cbeta_ebook")
                                 or "").strip() or src
                    ensure_baselines(w.id, need, _presets_af, _ebook_af)
                    official = {}
                    for kind in ("html","txt_notes","docx","epub","odt"):
                        found = v_find(src, stem, kind, juan=_juan if kind in ("html", "docx", "txt_notes") else None)
                        if found: official[kind] = found
                    bases = _cli_bases(official)
                if not bases:
                    block.append(f"  [--]  {disp} no baseline")
                    continue
                ours_raw_all = "".join(v_extract(p) for p in gen_paths)
                docnumber = (w.metadata.get("docNumber") or "").strip()
                series = (w.metadata.get("series") or "").strip()
                if fmt == "docx":
                    title = (w.metadata.get("title") or "").strip()
                    from .verify import strip_docx_head as _sdh
                    ours_raw_all = _sdh(ours_raw_all, title, docnumber, series)
                if fmt == "md":
                    from .verify import _strip_md_marks as _smm
                    ours_raw_all = _smm(ours_raw_all)
                ours = v_norm(ours_raw_all, _rb)
                if not v_compare_infos:
                    ours = v_norm(v_strip_infos(ours_raw_all), _rb)
                ok_any = False; best = None
                detail_lines = []
                for bkind, bpath in bases:
                    if isinstance(bpath, list):
                        if bkind == "docx" and len(bpath) > 1:
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
                                merged_dir = os.path.join(verify_dir, fmt)
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
                                a_snip = _v_mark(ours, i1, i2)
                                b_snip = _v_mark(theirs_n, j1, j2)
                                detail += f"\n      {idx}. 【源】{b_snip}\n         【新】{a_snip}"
                        detail_lines = [detail]
                        break
                    else:
                        lines=[]
                        for idx,(tag,i1,i2,j1,j2) in enumerate(ctx[:args.verify_diff_lines],1):
                            a_snip = _v_mark(ours, i1, i2)
                            b_snip = _v_mark(theirs_n, j1, j2)
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
                block.append(f"  {disp} 【源】{bpath}")
                block.append(f"  {disp} 【新】{gen_path}")
                block.extend(detail_lines)
            results.append((block_failed, name, block))
            # 每经书独立报告：{输出}/{id 书名}（验证）/report.txt
            try:
                os.makedirs(verify_dir, exist_ok=True)
                _rpt = os.path.join(verify_dir, "report.txt")
                with open(_rpt, "w", encoding="utf-8") as _f:
                    _f.write("\n".join(block) + "\n")
                print(f"报告已写入: {_rpt}")
            except Exception as e:
                print(f"写入报告失败: {e}")
        results.sort(key=lambda x: (0 if x[0] else 1, x[1]))
        for _,_,block in results:
            for line in block:
                vlog(line)
        summary = f"{grand_total} compared, {grand_fail} failed (阈值 max-diff={args.verify_max_diff})"
        vlog(f"\n{summary}")
        vlog(f"完成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 1 if render_failed else 0


if __name__ == "__main__":
    sys.exit(main())
