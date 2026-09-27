"""PDF-ready HTML renderer (from IR) + Chromium headless converter.

PDF pipeline: IR -> PDF-ready HTML+CSS (this module) -> Chromium headless -> PDF.
The engine (Chromium) is pluggable; WeasyPrint can replace it once GTK is installed.
"""

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import List, Optional

from .model import App, E, Gaiji, Note, NoteRef, Pb, Text, Work
from .render_html import HtmlRenderer, LINEHEAD_RE, _esc, split_juans
from .theme import Theme, resolve_page, bracket_pair, ensure_page_typography

def _find_soffice() -> Optional[str]:
    # config.json engines.paths.libreoffice 优先（支持自定义安装位置）
    try:
        from .theme import load_presets
        p = ((load_presets().get("engines") or {}).get("paths") or {}).get("libreoffice")
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    candidates = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        r"C:\Program Files\LibreOffice\program\soffice.com",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


# Word / WPS 的 COM ProgID
_COM_WORD = ("Word.Application",)
_COM_WPS = ("KWPS.Application", "wps.Application")

# COM 并发纪律：Office 是 STA 服务器，进程内转换串行化。
# 只约束本进程（subprocess 批量各进程独立，不受影响）。
_COM_LOCK = threading.Lock()
# 本进程内已确认 RPC 死亡的 ProgID：后续 work 直接跳过，不再鞭尸
_DEAD_PROGIDS = set()
# RPC 死亡码：RPC_S_CALL_FAILED / RPC_S_SERVER_UNAVAILABLE
_RPC_DEAD = frozenset((0x800706BE, 0x800706BA))


def _is_rpc_dead(exc) -> bool:
    """异常是否为 RPC 死亡（服务器端已死）。hresult 可正可负，归一化后比对；
    无 hresult（如普通 RuntimeError）一律按"非死亡"处理。"""
    code = getattr(exc, "hresult", None)
    if code is None:
        return False
    try:
        code &= 0xFFFFFFFF
    except TypeError:
        return False
    return code in _RPC_DEAD


def _ensure_com_apartment(_mod=None):
    """调用线程进 STA 公寓（Office COM 要求）→ (模块, 是否本次初始化)。
    pythoncom 缺失 / 线程已是 MTA（RPC_E_CHANGED_MODE）等一律返回 (mod|None, False)，
    调用方照常继续、不配对。_mod 供测试注入。"""
    try:
        mod = _mod if _mod is not None else __import__("pythoncom")
    except ImportError:
        return None, False
    try:
        mod.CoInitializeEx(mod.COINIT_APARTMENTTHREADED)
    except Exception:
        return mod, False
    return mod, True


def _prep_open_path(docx_fn: str):
    """返回 (用于打开的路径, 清理回调)。

    WPS/Word 对**同一路径**的文件 `Documents.Open` 会返回既有 Document 对象；
    若用户已打开同名文件，安全附着时 Close 会误关用户文档。故复制一份到临时目录，
    用副本转换（字节一致），转换完删副本。复制失败则退回原路径。
    """
    try:
        d = tempfile.mkdtemp(prefix="pycbeta_com_")
        p = os.path.join(d, os.path.basename(docx_fn) or "in.docx")
        shutil.copy2(docx_fn, p)
        return p, (lambda: shutil.rmtree(d, ignore_errors=True))
    except Exception:
        return os.path.abspath(docx_fn), (lambda: None)


def _com_convert(docx_fn: str, pdf_fn: str, progids, dispatch=None,
                 dispatch_ex=None, get_active=None) -> Optional[str]:
    """用指定 ProgID 的 office COM（Word/WPS）导出 PDF。失败返回 None。

    用户未开 Word/WPS 时优先 DispatchEx 新建**独立实例**（安全：隐藏、只读、Quit(0)）。
    若检测到用户已开着该程序，则**安全附着**（不动 Visible、不 Quit、只读打开、
    Close(0)、DisplayAlerts=0 后恢复），避免弹出「是否保存修改」或退出用户进程。
    始终从临时副本转换，避免误关用户已打开的同名文档。
    dispatch/dispatch_ex/get_active 可注入（测试用）。

    并发纪律：进程内串行（_COM_LOCK）+ 调用线程进 STA 公寓；
    已有实例先验活（Documents.Count 探针），僵尸不附着；
    RPC 死亡的 ProgID 记入 _DEAD_PROGIDS，本进程后续直接跳过。
    """
    if dispatch is None or dispatch_ex is None or get_active is None:
        try:
            import win32com.client
        except ImportError:
            return None
        if dispatch is None:
            dispatch = win32com.client.Dispatch
        if dispatch_ex is None:
            dispatch_ex = getattr(win32com.client, "DispatchEx", None)
        if get_active is None:
            get_active = getattr(win32com.client, "GetActiveObject", None)
    work_docx, cleanup = _prep_open_path(docx_fn)
    _com_mod, _com_init = _ensure_com_apartment()
    _COM_LOCK.acquire()
    try:
        for progid in progids:
            if progid in _DEAD_PROGIDS:
                continue  # 本进程已确认 RPC 死亡，不再鞭尸
            app = d = None
            owned = False
            prev = {}
            try:
                running = False
                if get_active is not None:
                    try:
                        _probe_app = get_active(progid)
                        # 活性探针：ROT 残留的僵尸实例必抛（含 RPC 错误），
                        # 不验活直接附着是批量第二部崩溃的根因
                        _probe_app.Documents.Count
                        running = True
                    except Exception as e:
                        if _is_rpc_dead(e):
                            _DEAD_PROGIDS.add(progid)
                        running = False
                if not running and dispatch_ex is not None:
                    try:
                        app = dispatch_ex(progid)
                        owned = True
                    except Exception:
                        app = None
                if app is None:
                    app = dispatch(progid)  # 安全附着既有实例
                for k in ("DisplayAlerts", "ScreenUpdating"):
                    try:
                        prev[k] = getattr(app, k)
                    except Exception:
                        prev[k] = None
                prev["SaveInterval"] = None
                try:
                    app.DisplayAlerts = 0        # wdAlertsNone
                except Exception:
                    pass
                try:
                    app.ScreenUpdating = False
                except Exception:
                    pass
                try:
                    prev["SaveInterval"] = app.Options.SaveInterval
                    app.Options.SaveInterval = 0  # 关自动备份/恢复弹窗
                except Exception:
                    prev["SaveInterval"] = None
                if owned:
                    try:
                        app.Visible = False
                    except Exception:
                        pass
                try:
                    d = app.Documents.Open(work_docx, ReadOnly=True,
                                           AddToRecentFiles=False, Visible=False)
                except Exception:
                    try:
                        d = app.Documents.Open(work_docx, ReadOnly=True,
                                               AddToRecentFiles=False)
                    except Exception:
                        d = app.Documents.Open(work_docx)
                try:
                    d.ExportAsFixedFormat(os.path.abspath(pdf_fn), 17)  # 17 = PDF
                except Exception:
                    d.SaveAs(os.path.abspath(pdf_fn), FileFormat=17)
                try:
                    d.Saved = True
                except Exception:
                    pass
                d.Close(0)  # wdDoNotSaveChanges：绝不弹保存框
                d = None
                if owned:
                    _com_quit(app)
                else:
                    _com_restore(app, prev)
                app = None
                return os.path.abspath(pdf_fn)
            except Exception as e:  # 该 ProgID 不可用或转换失败，尝试下一个
                if _is_rpc_dead(e):
                    _DEAD_PROGIDS.add(progid)
                if d is not None:
                    try:
                        d.Close(0)
                    except Exception:
                        pass
                if owned:
                    _com_quit(app)
                else:
                    _com_restore(app, prev)
        return None
    finally:
        try:
            _COM_LOCK.release()
        except Exception:
            pass
        if _com_init and _com_mod is not None:
            try:
                _com_mod.CoUninitialize()
            except Exception:
                pass
        cleanup()


def _com_quit(app) -> None:
    """退出我们创建的实例：显式 Quit(0)（不保存），失败退回 Quit()。"""
    if app is None:
        return
    try:
        app.Quit(0)
    except Exception:
        try:
            app.Quit()
        except Exception:
            pass


def _com_restore(app, prev: dict) -> None:
    """安全附着后恢复用户实例的 DisplayAlerts / ScreenUpdating / SaveInterval。"""
    if app is None:
        return
    for k in ("DisplayAlerts", "ScreenUpdating"):
        if prev.get(k) is not None:
            try:
                setattr(app, k, prev[k])
            except Exception:
                pass
    if prev.get("SaveInterval") is not None:
        try:
            app.Options.SaveInterval = prev["SaveInterval"]
        except Exception:
            pass



def _pdf_via_word(docx_fn: str, pdf_fn: str) -> Optional[str]:
    return _com_convert(docx_fn, pdf_fn, _COM_WORD)


def _pdf_via_wps(docx_fn: str, pdf_fn: str) -> Optional[str]:
    return _com_convert(docx_fn, pdf_fn, _COM_WPS)


def _pdf_via_libreoffice(docx_fn: str, pdf_fn: str) -> Optional[str]:
    soffice = _find_soffice()
    if not soffice:
        return None
    outdir = os.path.dirname(os.path.abspath(pdf_fn)) or "."
    subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                    "--outdir", outdir, os.path.abspath(docx_fn)], check=True)
    produced = os.path.join(outdir,
                            os.path.splitext(os.path.basename(docx_fn))[0] + ".pdf")
    if os.path.abspath(produced) != os.path.abspath(pdf_fn):
        if os.path.exists(pdf_fn):
            os.remove(pdf_fn)
        os.rename(produced, pdf_fn)
    return os.path.abspath(pdf_fn)


def _split_args(s: str):
    """按空格切分参数串，双引号内视为一个参数。"""
    out, cur, in_q = [], [], False
    for ch in s:
        if ch == '"':
            in_q = not in_q
            continue
        if ch == " " and not in_q:
            if cur:
                out.append("".join(cur))
                cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def _external_engine_cfg(name: str) -> Optional[dict]:
    """取 config.json engines.external 里注册的外部引擎定义。"""
    try:
        from .theme import load_presets
        cfg = (load_presets().get("engines") or {}).get("external") or {}
    except Exception:
        return None
    return cfg.get(name)


def _pdf_via_external(name: str, docx_fn: str, pdf_fn: str) -> Optional[str]:
    """外部引擎：engines.external 注册的 {executable, arguments, timeoutSeconds}。
    arguments 模板支持 {input}/{output} 占位符。"""
    cfg = _external_engine_cfg(name)
    if not cfg:
        return None
    exe = cfg.get("executable") or ""
    if not os.path.isabs(exe):
        exe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), exe)
    if not os.path.isfile(exe):
        return None
    args_s = (cfg.get("arguments") or 'convert "{input}" -o "{output}"') \
        .replace("{input}", os.path.abspath(docx_fn)) \
        .replace("{output}", os.path.abspath(pdf_fn))
    cmd = [exe] + _split_args(args_s)
    timeout = int(cfg.get("timeoutSeconds") or 120)
    subprocess.run(cmd, check=True, timeout=timeout)
    if not os.path.isfile(pdf_fn):
        raise RuntimeError(f"external engine '{name}' did not produce {pdf_fn}")
    return os.path.abspath(pdf_fn)


def _pdf_via_minipdf(docx_fn: str, pdf_fn: str) -> Optional[str]:
    return _pdf_via_external("minipdf", docx_fn, pdf_fn)


def _pdf_via_docbuilder(docx_fn: str, pdf_fn: str) -> Optional[str]:
    """ONLYOFFICE DocBuilder：生成临时 JS 脚本（OpenFile/SaveFile）后执行。
    引擎路径取 engines.paths.docbuilder。"""
    try:
        from .theme import load_presets
        exe = ((load_presets().get("engines") or {}).get("paths") or {}).get("docbuilder")
    except Exception:
        exe = None
    if not exe or not os.path.isfile(exe):
        return None
    script = (
        f'builder.OpenFile("{os.path.abspath(docx_fn).replace(chr(92), "/")}");\n'
        f'builder.SaveFile("pdf", "{os.path.abspath(pdf_fn).replace(chr(92), "/")}");\n'
        "builder.CloseFile();\n"
    )
    fd, js_fn = tempfile.mkstemp(suffix=".js", prefix="pycbeta_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(script)
    try:
        # DocBuilder 需以其安装目录为工作目录（加载 sdkjs 等资源）
        subprocess.run([exe, js_fn], check=True,
                       cwd=os.path.dirname(exe), timeout=180)
    finally:
        try:
            os.remove(js_fn)
        except OSError:
            pass
    if not os.path.isfile(pdf_fn):
        raise RuntimeError(f"docbuilder did not produce {pdf_fn}")
    return os.path.abspath(pdf_fn)


# DOCX->PDF 后端链（默认：Word → WPS → LibreOffice，保真度从高到低）
DOCX_PDF_CHAIN = ("word", "wps", "libreoffice")
_DOCX_BACKENDS = {
    "word": _pdf_via_word,
    "msword": _pdf_via_word,   # 别名（config.json defaultChain 用名）
    "wps": _pdf_via_wps,
    "libreoffice": _pdf_via_libreoffice,
    "minipdf": _pdf_via_minipdf,       # 外部引擎
    "docbuilder": _pdf_via_docbuilder,  # 外部引擎（ONLYOFFICE DocBuilder）
}


def pdf_source_fmt(engine=None, vertical: bool = False) -> str:
    """PDF 管线的源格式：docx2pdf→'docx'，html2pdf→'html'（与 render_one pdf 分支一致）。"""
    pipeline = (engine or "").partition(":")[0]
    if not pipeline:
        pipeline = "html2pdf" if vertical else "docx2pdf"
    return "docx" if pipeline == "docx2pdf" else "html"


def docx_to_pdf(docx_fn: str, pdf_fn: str, chain=None, used: dict = None) -> str:
    """Convert a .docx (real OOXML footnotes) to PDF.
    chain: 后端链（按序尝试），如 ["word","wps","libreoffice"]；
    缺省 DOCX_PDF_CHAIN（Word → WPS → LibreOffice）。
    used: 可选 dict，成功后写入 {"backend": 实际后端名}。
    Page-bottom footnotes are preserved by the office renderer."""
    chain = tuple(chain) if chain else DOCX_PDF_CHAIN
    errors = []
    for name in chain:
        backend = _DOCX_BACKENDS.get(name)
        if not backend:
            errors.append(f"unknown backend '{name}'")
            continue
        pdf = backend(docx_fn, pdf_fn)
        if pdf:
            if used is not None:
                used["backend"] = name
            return pdf
        errors.append(f"{name}: unavailable")
    raise RuntimeError(
        "docx2pdf engine needs Microsoft Word, WPS or LibreOffice installed "
        f"(chain={list(chain)}); pywin32 required for COM. 尝试记录: {'; '.join(errors)}")


def _draw_page_borders(pdf_fn: str, inset_pt: float = 24.0, width: float = 0.75) -> str:
    """在最终 PDF 每页四周画一个黑框（pymupdf 后处理，适配任意引擎）。

    边框与 DOCX 版一致：0.75pt 单线，距纸边 24pt。Chromium 不支持 @page
    边框，故统一在生成后逐页绘制，保证 chromium/prince/weasyprint 行为一致。
    """
    import pymupdf  # PyMuPDF
    doc = pymupdf.open(pdf_fn)
    for page in doc:
        r = page.rect
        page.draw_rect(pymupdf.Rect(inset_pt, inset_pt,
                                    r.width - inset_pt, r.height - inset_pt),
                       color=(0, 0, 0), width=width)
    doc.save(pdf_fn, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()
    return os.path.abspath(pdf_fn)


def _element_text(n) -> str:
    if isinstance(n, Text):
        return n.text
    out = []
    for c in getattr(n, "children", []):
        out.append(_element_text(c))
    return "".join(out)


def juan_heading(ops) -> str:
    """从一卷的 ops 里取出卷标题（<cb:juan><cb:jhead>…</cb:jhead></cb:juan>），
    找不到返回 ''（调用方回退为「卷N」）。"""
    for kind, n in ops:
        if kind == "node" and isinstance(n, E) and n.tag == "juan":
            for c in n.children:
                if isinstance(c, E) and c.tag == "jhead":
                    return _element_text(c).strip()
            return _element_text(n).strip()
    return ""


def _clean_marks(s: str) -> str:
    """去掉校勘注码 [12]（渲染进 PDF 的文字里带 [n]），便于与 IR 标题比对。"""
    return re.sub(r"\[\d+\]", "", s).replace(" ", "")


def _find_juan_page(doc, heading: str, start: int = 1):
    """找卷标题所在页：卷起于新页，标题是当页首行（去注码后匹配）。"""
    h = _clean_marks(heading)
    if not h:
        return None
    for pno in range(max(start, 1), len(doc) + 1):
        page = doc[pno - 1]
        for ln in page.get_text().splitlines():
            s = _clean_marks(ln).strip()
            if not s:
                continue
            if s == h or h.startswith(s) or s.startswith(h):
                return pno
            break
    return None


def _add_pdf_bookmarks(pdf_fn: str, headers: List[tuple]) -> str:
    """用 pymupdf 给 PDF 加目录书签（默认卷标题）。headers=[(卷号, 标题), …]。"""
    try:
        import pymupdf
    except ImportError:
        print("警告: 未安装 pymupdf，PDF 目录书签已跳过", file=sys.stderr)
        return os.path.abspath(pdf_fn)
    doc = pymupdf.open(pdf_fn)
    toc = []
    prev = 0
    n_pages = len(doc)
    for i, (_no, heading) in enumerate(headers):
        if i == 0:
            page = 1  # 第一卷必从第 1 页（标题页）开始
        else:
            page = _find_juan_page(doc, heading, start=prev + 1)
            if page is None:
                page = prev + 1
        page = max(1, min(page, n_pages))
        toc.append([1, heading, page])
        prev = page
    if toc:
        doc.set_toc(toc)
        doc.save(pdf_fn, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()
    return os.path.abspath(pdf_fn)



class PdfRenderer(HtmlRenderer):
    def __init__(self, page="a4", vertical=False, gaiji_db=None, figure_base=None,
                 font_stack=None, footnotes=False, theme=None, engine=None,
                 notes="endnote", page_presets=None, ignore_xml_style=False,
                 ignore_xml_space=False, grayscale=False, page_border=False,
                 bookmarks=True, split=False, show_notes=True,
                 html_engine_chain=None, zoom=1.0, annotations=None, strip_head_no=False,
                 inline_brackets="fullwidth", note_inline_brackets=None,
                 corr_cbeta=False):
        super().__init__(gaiji_db=gaiji_db, figure_base=figure_base,
                         ignore_xml_style=ignore_xml_style,
                         ignore_xml_space=ignore_xml_space,
                         show_notes=show_notes, annotations=annotations,
                         strip_head_no=strip_head_no,
                         inline_brackets=inline_brackets,
                         note_inline_brackets=note_inline_brackets,
                         corr_cbeta=corr_cbeta)
        cfg = resolve_page(page, page_presets)
        w_mm, h_mm = cfg["size"]
        self.page_size = f"{w_mm}mm {h_mm}mm"
        self.page_margins = cfg["margins"]  # mm
        self.vertical = vertical
        self.footnotes = footnotes or notes == "footnote"
        self.notes = notes  # 'footnote' | 'endnote' | 'inline'
        self.font_stack = font_stack or self._default_font_stack()
        self.theme = theme if theme is not None else Theme()
        # 纸张绑字号：库直接调用也生效；CLI 已在 font_scale 前应用过 → 跳过
        ensure_page_typography(self.theme, page, page_presets)
        self.engine = engine or os.environ.get("CBETA_PDF_ENGINE", "chromium")
        # HTML->PDF 引擎链：按序尝试，第一个成功者出 PDF（--engine 强制单个时为单元素链）
        self.html_engine_chain = (list(html_engine_chain) if html_engine_chain
                                  else [self.engine])
        self.grayscale = grayscale                # 全局黑白：忽略所有颜色（含 CSS 定义）
        self.page_border = page_border            # 每页四周加框
        self.bookmarks = bookmarks                # 每卷加目录书签（默认卷标题）
        self.split = split                        # 按卷输出多个文档
        self.zoom = zoom                          # HTML→PDF 缩放（Playwright page.pdf scale，范围 0.1-2.0）
        self._endnotes = []

    @staticmethod
    def _default_font_stack() -> List[str]:
        # Note: cbetarc is intentionally omitted. Embedding it via @font-face
        # triggers a Chromium print bug that drops CJK text on this platform.
        return ["微軟正黑體", "新細明體", "Songti TC", "Times New Roman"]

    def render_work(self, work: Work, out_dir: str, filename: str = "main.html") -> str:
        """默认返回单个 html 路径；split=True 时返回按卷切分的 html 路径列表。"""
        self._work = work
        self.missing_figures = []
        self._app_by_n = {}
        for n in self._iter_all(work.body):
            if isinstance(n, App) and n.key:
                self._app_by_n[n.key[3:]] = n
        juans = self._split_juans(work.body)
        self._juan_headers = [(no, juan_heading(ops) or f"卷{no}") for no, ops in juans]
        os.makedirs(out_dir, exist_ok=True)
        if self.split:
            return self._render_split(work, out_dir, filename, juans)
        self._endnotes = []
        self._note_seq = 0
        self._old_seq = 0
        parts = []
        for juan_no, ops in juans:
            self._div_stack = 0
            self._lb = None
            self._in_pre = False
            body = self._render_ops(ops)
            if parts:
                parts.append('<div class="juan-break"></div>')
            parts.append(body)
        body = "".join(parts)
        html = self._wrap(body, work)
        fn = os.path.join(out_dir, filename)
        with open(fn, "w", encoding="utf-8") as f:
            f.write(html)
        return fn

    def convert_with_chain(self, html_fn: str, pdf_fn: str,
                           landscape: bool = False) -> str:
        """按 html_engine_chain 依次尝试（第一个成功者出 PDF）。"""
        last = None
        for eng in self.html_engine_chain:
            try:
                return self.html_to_pdf(html_fn, pdf_fn, landscape=landscape,
                                        engine=eng)
            except Exception as e:
                last = e
        raise last or RuntimeError("no html->pdf engine available")

    def _render_split(self, work: Work, out_dir: str, filename: str,
                      juans) -> List[str]:
        """按卷输出：每卷一个独立 html（书名头 + 本卷正文 + 尾注）。"""
        stem = os.path.splitext(os.path.basename(filename))[0] or work.id
        files = []
        for juan_no, ops in juans:
            self._endnotes = []
            self._note_seq = 0
            self._old_seq = 0
            self._div_stack = 0
            self._lb = None
            self._in_pre = False
            body = self._render_ops(ops)
            html = self._wrap(body, work)
            fn = os.path.join(out_dir, f"{stem}_卷{juan_no}.html")
            with open(fn, "w", encoding="utf-8") as f:
                f.write(html)
            files.append(fn)
        return files

    def _render_noteref(self, ref: NoteRef) -> str:
        notes = ref.notes
        if not notes:
            return ""
        note = self._pick_note(notes)
        content = self._render_nodes(note.children).strip()
        app = self._app_by_n.get(note.n or "")
        if app is not None and app.lem is not None:
            cfs = [c for c in app.lem.children
                   if isinstance(c, Note) and (c.ntype or "").startswith("cf")]
            if cfs:
                refs = "; ".join(self._render_cf(app, c) for c in cfs)
                content += f"(cf. {refs})"
        self._note_seq += 1
        seq = self._note_seq
        if self.notes == "inline":
            lb, rb = bracket_pair(self.note_inline_brackets)
            return f'<span class="note-inline">{lb}{content}{rb}</span>'
        if self.footnotes:
            return (f'<sup class="footnote-call">[{seq}]</sup>'
                    f'<div class="fn"><span class="fn-marker">[{seq}]</span> {content}</div>')
        self._endnotes.append(f'<div class="endnote">{content}</div>')
        return f'<sup class="note-ref">[{seq}]</sup>'

    def _tei_info_html(self, work: Work) -> str:
        """经文资讯尾页（与 DOCX 版一致）：单独一页，从【經文資訊】开始。"""
        md = work.metadata or {}
        src = md.get("source") or "CBETA"
        vol = md.get("vol") or ""
        no = md.get("no") or ""
        pub = (md.get("publication_date") or "").split(" ")[0]
        contrib = md.get("contributors") or ""
        title = md.get("title") or ""
        info = [f"【經文資訊】{_esc(src)}" + (f" 第 {_esc(vol)} 冊 No. {_esc(no)}" if vol and no else "")
                + (f"　{_esc(title)}" if title else "")]
        if pub:
            info.append(f"【版本記錄】發行日期：{_esc(pub)}，最後更新：{_esc(pub)}")
        info.append(f"【編輯說明】本資料庫由 財團法人佛教電子佛典基金會（CBETA）依「{_esc(src)}」所編輯")
        if contrib:
            info.append(f"【原始資料】{_esc(contrib)}")
        lines = "".join(f'<p class="info">{l}</p>' for l in info)
        return f'<div class="tei-info"><h2 class="head">版本資訊</h2>{lines}</div>'

    def _wrap(self, body: str, work: Work) -> str:
        md = work.metadata
        title = md.get("title") or work.id
        css = self._pdf_css()
        lang = "zh-Hans" if getattr(work, "simplified", False) else "zh-Hant"
        endnotes = "".join(self._endnotes) if self._endnotes else ""
        head = f"<h1 class='title'>{_esc(title)}</h1>"
        meta = f"<p class='meta'>{_esc(md.get('author') or '')}</p>"
        script = self._paged_script() if self.footnotes else ""
        end = f'<div class="endnotes"><h2>校注</h2>{endnotes}</div>' if endnotes else ""
        tei_page = self._tei_info_html(work)
        return (
            f'<html lang="{lang}"><head>\n'
            '<meta charset="utf-8"/>\n'
            f"<title>{_esc(title)}</title>\n"
            f"<style>{css}</style>\n"
            f"{script}"
            + ("</head><body class=\"vertical-rl\">\n" if self.vertical else "</head><body>\n")
            + f"{head}{meta}\n"
            f'<div class="content">{body}</div>\n'
            f"{end}\n"
            f"{tei_page}\n"
            "</body></html>"
        )

    def _paged_script(self) -> str:
        if self.engine == "prince":
            return ""  # Prince handles float:footnote natively
        path = os.path.join(os.path.dirname(__file__), "assets", "paged.polyfill.js")
        if os.path.isfile(path):
            return f'<script src="file:///{os.path.abspath(path).replace(os.sep, "/")}"></script>\n'
        return ""

    def _pdf_css(self) -> str:
        font_uri = self._font_data_uri()
        face = ""
        if font_uri:
            face = f"""
@font-face {{
  font-family: cbetarc;
  src: url("data:font/ttf;base64,{font_uri}");
}}"""
        stack = [f for f in self.font_stack]
        if "cbetarc" in stack and not font_uri:
            stack.remove("cbetarc")
        fonts = ", ".join(f'"{f}"' if f != "cbetarc" else f for f in stack)
        orientation = "vertical-rl" if self.vertical else "horizontal-tb"
        theme_css = self.theme.raw_css or self.theme.css()
        # 纸张绑字号：apply_page_typography 写进 theme.tags body（raw_css 不会变），
        # 故在 theme_css 之后补 body 覆盖，令 html2pdf 也随纸张字号/行距。
        bt = self.theme.tags.get("body") or {}
        ov = []
        if bt.get("font-size"):
            ov.append(f"font-size: {bt['font-size']}")
        if bt.get("line-height"):
            ov.append(f"line-height: {bt['line-height']}")
        body_override = f"\nbody {{ {'; '.join(ov)}; }}" if ov else ""
        m = self.page_margins
        margin = f"{m['top']}mm {m['right']}mm {m['bottom']}mm {m['left']}mm"
        css = f"""
@page {{ size: {self.page_size}; margin: {margin}; }}{face}
body {{
  font-family: {fonts}, sans-serif;
  writing-mode: {orientation};
}}
.tei-info {{ break-before: page; }}
.tei-info h2 {{ text-align: center; }}
.tei-info p {{ margin: 0.3em 0; }}
{theme_css}{body_override}
div.lg {{ display: table; margin-left: 2em; }}
div.lg-cell {{ display: table-cell; padding: 0 0.5em; }}
div.lg-row {{ display: table-row; }}
.juan-break {{ break-before: page; }}
.endnotes {{ break-before: page; }}
.endnote {{ text-indent: 0; }}"""
        if self.footnotes and not self.vertical:
            css += """
.fn {{ float: footnote; }}
::footnote-call {{ content: none; }}
::footnote-marker {{ content: none; }}
sup.footnote-call {{ color: #06c; font-size: 0.7em; }}
@page {{ @footnote {{
  border-top: 0.5pt solid #999;
  padding-top: 3pt;
  margin-top: 8pt;
  font-size: 10pt;
}} }}"""
        if self.grayscale:
            # 全局黑白：!important 覆盖主题 CSS 与元素内联颜色，一律黑字白底黑边
            css += """
* {{ color: #000 !important; background-color: #fff !important; border-color: #000 !important; }}
a, a:visited {{ color: #000 !important; }}
@page {{ @footnote {{ border-top-color: #000; }} }}"""
        return css

    def _font_data_uri(self) -> str:
        from .fonts import supplement_path
        path = supplement_path() or ""
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        return ""

    def html_to_pdf(self, html_fn: str, pdf_fn: str, landscape: bool = False,
                    engine: Optional[str] = None) -> str:
        engine = engine or self.engine
        self.last_engine = engine
        if engine == "prince":
            self._prince_to_pdf(html_fn, pdf_fn, landscape)
        elif engine == "weasyprint":
            self._weasyprint_to_pdf(html_fn, pdf_fn)
        elif engine == "chromium":
            self._chromium_to_pdf(html_fn, pdf_fn, landscape, scale=self.zoom)
        else:
            # 其它引擎名 → 尝试 config.json engines.external 注册的外部命令行引擎
            r = _pdf_via_external(engine, html_fn, pdf_fn)
            if not r:
                raise RuntimeError(
                    f"unknown pdf engine '{engine}' "
                    "(built-in: chromium/prince/weasyprint; "
                    "external engines register in config.json engines.external)")
        if self.page_border:
            _draw_page_borders(pdf_fn)
        if self.bookmarks and not self.split and getattr(self, "_juan_headers", None):
            _add_pdf_bookmarks(pdf_fn, self._juan_headers)
        return os.path.abspath(pdf_fn)

    def convert_with_chain(self, html_fn: str, pdf_fn: str,
                           landscape: bool = False) -> str:
        """按 html_engine_chain 依次尝试，第一个成功者出 PDF。"""
        last = None
        for eng in self.html_engine_chain:
            try:
                return self.html_to_pdf(html_fn, pdf_fn, landscape=landscape,
                                        engine=eng)
            except Exception as e:
                last = e
        raise last or RuntimeError("no html->pdf engine available")

    def _prince_to_pdf(self, html_fn: str, pdf_fn: str, landscape: bool) -> None:
        prince = shutil.which("prince") or shutil.which("prince.exe")
        if not prince:
            raise RuntimeError(
                "Prince XML not found. Install from https://www.princexml.com/ "
                "or switch engine (default: chromium).")
        cmd = [prince, "--no-warn-css-unsupported"]
        if landscape:
            cmd.append("--page-size=landscape")
        cmd += [os.path.abspath(html_fn), "-o", os.path.abspath(pdf_fn)]
        subprocess.run(cmd, check=True)

    def _weasyprint_to_pdf(self, html_fn: str, pdf_fn: str) -> None:
        try:
            from weasyprint import HTML
        except Exception as exc:
            raise RuntimeError(
                "WeasyPrint 不可用：Python 包已装但缺系统运行库（GTK/Pango，"
                "如 libgobject-2.0-0）。Windows 请装 GTK 运行时并把 bin 加入 PATH，"
                "详见 https://doc.courtbouillon.org/weasyprint/stable/"
                "first_steps.html#installation "
                f"（原错：{exc}）")
        HTML(filename=os.path.abspath(html_fn)).write_pdf(os.path.abspath(pdf_fn))

    def _chromium_to_pdf(self, html_fn: str, pdf_fn: str, landscape: bool,
                         scale: float = 1.0) -> None:
        from playwright.sync_api import sync_playwright
        html_path = os.path.abspath(html_fn)
        pdf_path = os.path.abspath(pdf_fn)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file:///{html_path}")
            if self.footnotes:
                page.wait_for_selector(".pagedjs_pages", timeout=30000)
                page.wait_for_timeout(4000)
            page.pdf(path=pdf_path, prefer_css_page_size=True,
                     landscape=landscape, scale=scale)
            browser.close()
