# -*- coding: utf-8 -*-
"""端到端组合测试：test\\*.xml -> test\\out\\

覆盖维度（尽可能全组合）：
  格式    : md / html / docx / pdf（epub 可加）
  颜色    : color(原色) / mono(grayscale 黑白)
  页面    : a4 / a5 / phone / tablet（md/html/epub 不分页，忽略此维度）
  注释    : footnote / endnote
  PDF 引擎: chromium / cbetapdf / docx2pdf（prince/weasyprint 未装会记 FAIL）

输出目录：test\\out\\<书名>\\<标签>\\<格式>\\
标签示例：a4-color-footnote、a4-mono-endnote-docx2pdf

用法:
  python test\\run_tests.py                          # 全组合（耗时较长）
  python test\\run_tests.py -f pdf --pages a4,a5     # 缩小范围
  python test\\run_tests.py -f pdf --pdf-engines chromium,docx2pdf
"""
import argparse
import glob
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from pycbeta.parser import P5Parser
from pycbeta.render_docx import DocxRenderer
from pycbeta.render_html import HtmlRenderer
from pycbeta.render_pdf import PdfRenderer, docx_to_pdf
from pycbeta.render_epub import EpubRenderer
from pycbeta.render_md import MdRenderer
from pycbeta.theme import Theme, OUTPUT_PRESETS, ENGINE_PRESETS


def render_job(xml_fn, work, fmt, outdir, page, mono, notes, engine):
    """渲染单个组合。返回 (ok, detail)。engine 仅 pdf 维度使用。"""
    stem = os.path.splitext(os.path.basename(xml_fn))[0]
    theme = Theme()
    gray = bool(mono == "mono")

    common = dict(ignore_xml_style=bool(OUTPUT_PRESETS.get("ignore_xml_style")),
                  ignore_xml_space=bool(OUTPUT_PRESETS.get("ignore_xml_space")))

    if fmt == "md":
        r = MdRenderer(theme=theme, notes=notes, show_notes=True) \
            .render_work(work=work, out_dir=outdir, filename=f"{stem}.md")
        return os.path.isfile(r), r

    if fmt == "epub":
        r = EpubRenderer(theme=theme, notes=notes,
                         ignore_xml_style=common["ignore_xml_style"],
                         ignore_xml_space=common["ignore_xml_space"],
                         show_notes=True).render_work(work=work, out_dir=outdir,
                                                      filename=f"{stem}.epub")
        return os.path.isfile(r), r

    if fmt == "html":
        files = HtmlRenderer(theme=theme, notes=notes,
                             ignore_xml_style=common["ignore_xml_style"],
                             ignore_xml_space=common["ignore_xml_space"],
                             grayscale=gray,
                             show_notes=True).render_work(work=work, out_dir=outdir)
        return bool(files), f"{len(files)} file(s)"

    if fmt == "docx":
        r = DocxRenderer(theme=theme, page=page, notes=notes,
                         page_presets=None,
                         grayscale=gray,
                         page_border=bool(OUTPUT_PRESETS.get("page_border")),
                         bookmarks=OUTPUT_PRESETS.get("bookmarks", True),
                         split=False,
                         show_close_juan=bool(OUTPUT_PRESETS.get("show_close_juan")),
                         footnote_per_page=OUTPUT_PRESETS.get("footnote_per_page", True),
                         print_mode=bool(OUTPUT_PRESETS.get("print_mode")),
                         suppress_title_notes=bool(OUTPUT_PRESETS.get("suppress_title_notes")),
                         footnote_separator=(OUTPUT_PRESETS.get("docx") or {}).get(
                             "footnoteSeparator"),
                         **common) \
            .render_work(work=work, out_dir=outdir, filename=f"{stem}.docx")
        return os.path.isfile(r), r

    if fmt == "pdf":
        if engine == "docx2pdf":
            # DOCX 管线：先渲染 DOCX（含 tei 尾页），再交 office 后端链转 PDF
            d = DocxRenderer(theme=theme, page=page, notes=notes,
                             page_presets=None,
                             grayscale=gray,
                             page_border=bool(OUTPUT_PRESETS.get("page_border")),
                             bookmarks=OUTPUT_PRESETS.get("bookmarks", True),
                             split=False,
                             show_close_juan=bool(OUTPUT_PRESETS.get("show_close_juan")),
                             footnote_per_page=OUTPUT_PRESETS.get("footnote_per_page", True),
                             print_mode=bool(OUTPUT_PRESETS.get("print_mode")),
                             suppress_title_notes=bool(OUTPUT_PRESETS.get("suppress_title_notes")),
                             footnote_separator=(OUTPUT_PRESETS.get("docx") or {}).get(
                                 "footnoteSeparator"),
                             **common) \
                .render_work(work=work, out_dir=outdir, filename=f"{stem}_{tag(page, mono, notes, engine)}.docx")
            chain = ((ENGINE_PRESETS.get("docx2pdf") or {}).get("chain")
                     or ["wps", "libreoffice"])
            from pycbeta.render_pdf import docx_to_pdf
            pdf = docx_to_pdf(d, os.path.join(outdir, f"{stem}_{tag(page, mono, notes, engine)}.pdf"),
                              chain=chain)
            return os.path.isfile(pdf), pdf

        # HTML 管线（chromium / cbetapdf / prince / weasyprint）
        pr = PdfRenderer(page=page, theme=theme, notes=notes,
                         engine=engine,
                         page_presets=None,
                         grayscale=gray,
                         page_border=bool(OUTPUT_PRESETS.get("page_border")),
                         bookmarks=OUTPUT_PRESETS.get("bookmarks", True),
                         split=False,
                         show_notes=True,
                         **common)
        html = pr.render_work(work=work, out_dir=outdir,
                              filename=f"{stem}_{tag(page, mono, notes, engine)}.html")
        pdf = pr.html_to_pdf(html, os.path.join(outdir,
                                                f"{stem}_{tag(page, mono, notes, engine)}.pdf"))
        return os.path.isfile(pdf), pdf

    return False, f"unknown format {fmt}"


def tag(page, mono, notes, engine):
    parts = [page, "mono" if mono else "color"]
    if notes != "endnote":
        parts.append(notes)
    if fmt_tag_engine(engine):
        parts.append(engine)
    return "-".join(parts)


def fmt_tag_engine(engine):
    return engine and engine != "chromium"


def main(argv=None):
    ap = argparse.ArgumentParser(description="test/*.xml 全组合端到端测试 -> test/out/")
    ap.add_argument("-f", "--formats", default="md,html,epub,docx,pdf",
                    help="逗号分隔格式（默认全部）")
    ap.add_argument("--colors", default="color,mono",
                    help="颜色维度：color,mono")
    ap.add_argument("--pages", default="a4,a5,phone,tablet",
                    help="页面方案维度（docx/pdf；md/html/epub 忽略）")
    ap.add_argument("--notes-list", default="footnote,endnote",
                    help="注释方式维度")
    ap.add_argument("--pdf-engines", default="chromium,cbetapdf,docx2pdf",
                    help="PDF 引擎维度（prince/weasyprint 未安装会 FAIL）")
    ap.add_argument("--config", "--presets-file", dest="config",
                    help="自定义全局配置 JSON")
    args = ap.parse_args(argv)

    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    colors = [c.strip() for c in args.colors.split(",") if c.strip()]
    pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    notes_list = [n.strip() for n in args.notes_list.split(",") if n.strip()]
    engines = [e.strip() for e in args.pdf_engines.split(",") if e.strip()]

    xmls = sorted(glob.glob(os.path.join(HERE, "*.xml")))
    if not xmls:
        print(f"no XML files in {HERE}")
        return 1

    total = fail = 0
    for xml_fn in xmls:
        name = os.path.basename(xml_fn)
        print(f"=== {name}")
        try:
            work = P5Parser().parse(xml_fn)
        except Exception as e:
            print(f"  PARSE FAIL: {type(e).__name__}: {e}")
            continue

        stem = os.path.splitext(name)[0]

        def do(fmt, outdir, page, mono, notes, engine):
            nonlocal total, fail
            try:
                ok, detail = render_job(xml_fn, work, fmt, outdir, page, mono, notes, engine)
                mark = "[OK]  " if ok else "[FAIL]"
                print(f"  {mark} {fmt:5} {detail}")
                if not ok:
                    fail += 1
            except Exception as e:
                fail += 1
                print(f"  [FAIL] {fmt:5} {type(e).__name__}: {e}")

        for notes in notes_list:
            if "md" in formats:
                outdir = os.path.join(HERE, "out", stem,
                                      f"{notes}", "md")
                do("md", outdir, None, False, notes, None)
            if "epub" in formats:
                outdir = os.path.join(HERE, "out", stem,
                                      f"{notes}", "epub")
                do("epub", outdir, None, False, notes, None)

        for color in colors:
            mono = (color == "mono")
            ctag = color
            if "html" in formats:
                for notes in notes_list:
                    outdir = os.path.join(HERE, "out", stem,
                                          f"{ctag}-{notes}", "html")
                    do("html", outdir, None, mono, notes, None)

            for page in pages:
                for notes in notes_list:
                    outdir = os.path.join(HERE, "out", stem,
                                          f"{page}-{ctag}-{notes}", "docx")
                    if "docx" in formats:
                        do("docx", outdir, page, mono, notes, None)
                    for engine in engines:
                        if "pdf" in formats:
                            outdir = os.path.join(HERE, "out", stem,
                                                  f"{page}-{ctag}-{notes}-{engine}", "pdf")
                            do("pdf", outdir, page, mono, notes, engine)

    print(f"\n完成：{total} 项，失败 {fail}"
          + ("（prince/weasyprint 未安装的 FAIL 属预期）" if fail else ""))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
