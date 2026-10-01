import os
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.parser import P5Parser
from pycbeta.render_pdf import PdfRenderer, _draw_page_borders, _add_pdf_bookmarks, \
    _com_convert
from types import SimpleNamespace

from pycbeta.tests._data import DATA_ROOT as CBETA
from pycbeta.tests._data import requires_data


def extract_text(pdf):
    import pymupdf
    doc = pymupdf.open(pdf)
    return len(doc), "".join(p.get_text() for p in doc)


@requires_data
class TestPdfHorizontal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xml = os.path.join(CBETA, "X1116 毗尼日用切要香乳記", "X60n1116.xml")
        cls.work = P5Parser().parse(xml)
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_horizontal_a4(self):
        r = PdfRenderer(page="a4")
        html = r.render_work(self.work, self.tmp, "main.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "out.pdf"))
        pages, text = extract_text(pdf)
        self.assertGreater(pages, 50)
        self.assertIn("原夫文", text)
        self.assertIn("校注", text)
        self.assertGreater(len(text), 30000)

    def test_page_size_phone(self):
        import pymupdf
        r = PdfRenderer(page="手机")
        html = r.render_work(self.work, self.tmp, "phone.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "phone.pdf"))
        doc = pymupdf.open(pdf)
        w, h = doc[0].rect.width, doc[0].rect.height
        self.assertLess(w, h)  # portrait
        self.assertAlmostEqual(w, 283.5, delta=10)  # ~100mm

    def test_vertical(self):
        r = PdfRenderer(page="a4", vertical=True)
        html = r.render_work(self.work, self.tmp, "vert.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "vert.pdf"))
        pages, text = extract_text(pdf)
        self.assertGreater(pages, 50)
        self.assertIn("原夫文".replace("", "\n").replace("\n\n", "\n")[0:1], text)
        self.assertGreater(len(text), 30000)

    def test_grayscale_css(self):
        r = PdfRenderer(page="a4", grayscale=True)
        html = r.render_work(self.work, self.tmp, "gray.html")
        with open(html, encoding="utf-8") as f:
            css = f.read()
        self.assertIn("color: #000 !important", css)
        self.assertIn("background-color: #fff !important", css)
        r2 = PdfRenderer(page="a4")
        html2 = r2.render_work(self.work, self.tmp, "color.html")
        with open(html2, encoding="utf-8") as f:
            css2 = f.read()
        self.assertNotIn("!important", css2)

    def test_page_border_drawn(self):
        import pymupdf
        src = os.path.join(self.tmp, "tiny.pdf")
        d = pymupdf.open()
        d.new_page(width=595, height=842)
        d.save(src)
        d.close()
        _draw_page_borders(src)
        doc = pymupdf.open(src)
        self.assertEqual(len(doc), 1)
        drawings = doc[0].get_drawings()
        self.assertEqual(len(drawings), 1)
        rect = drawings[0]["rect"]
        self.assertGreater(rect.width, 500)
        self.assertGreater(rect.height, 700)

    def test_bookmarks_toc(self):
        import pymupdf
        src = os.path.join(self.tmp, "bm.pdf")
        d = pymupdf.open()
        d.new_page(width=595, height=842)
        d.new_page(width=595, height=842)
        d.save(src)
        d.close()
        _add_pdf_bookmarks(src, [(1, "卷一"), (2, "卷二")])
        doc = pymupdf.open(src)
        self.assertEqual(doc.get_toc(), [[1, "卷一", 1], [1, "卷二", 2]])

    def test_split_by_juan(self):
        xml = os.path.join(CBETA, "T0349 彌勒菩薩所問本願經", "T12n0349.xml")
        w = P5Parser().parse(xml)
        r = PdfRenderer(page="a4", split=True)
        htmls = r.render_work(w, self.tmp, "sp.html")
        self.assertEqual(len(htmls), 1)
        pdfs = [os.path.splitext(h)[0] + ".pdf" for h in htmls]
        for h, p in zip(htmls, pdfs):
            r.html_to_pdf(h, p)
        for p in pdfs:
            self.assertTrue(os.path.isfile(p))

    def test_juan_heading_pages(self):
        """目录书签页号：多卷书每卷从新页开始。"""
        r = PdfRenderer(page="a4")
        html = r.render_work(self.work, self.tmp, "jh.html")
        pdf = r.html_to_pdf(html, os.path.join(self.tmp, "jh.pdf"))
        import pymupdf
        doc = pymupdf.open(pdf)
        toc = doc.get_toc()
        self.assertEqual(len(toc), 2)
        self.assertEqual(toc[0], [1, "毗尼日用切要香乳記卷上", 1])
        pages = [t[2] for t in toc]
        self.assertEqual(len(set(pages)), 2)  # 两卷不同页


class TestVerticalWrap(unittest.TestCase):
    """竖排 body class 开关（纯字符串，不调引擎/字体）。"""

    def _work(self):
        from pycbeta.model import Work
        return Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                    body=[], notes_by_n={}, apps=[], simplified=False)

    def test_vertical_body_class(self):
        r = PdfRenderer(page="a4", vertical=True)
        r._pdf_css = lambda: "BASE"
        out = r._wrap("<p>x</p>", self._work())
        self.assertIn('<body class="vertical-rl">', out)

    def test_horizontal_no_class(self):
        r = PdfRenderer(page="a4", vertical=False)
        r._pdf_css = lambda: "BASE"
        out = r._wrap("<p>x</p>", self._work())
        self.assertIn("<body>", out)
        self.assertNotIn("vertical-rl", out)


class TestComConvert(unittest.TestCase):
    """COM 转换安全策略：无用户实例→DispatchEx 独立实例（隐藏/只读/Quit(0)）；
    用户已开→安全附着（不改 Visible、不 Quit、只读、Close(0)、设置后恢复）。"""

    class _Doc:
        def __init__(self, can_export=True, can_saveas=True):
            self.closed = None
            self.saved = None
            self.calls = []
            self._can_export = can_export
            self._can_saveas = can_saveas

        def ExportAsFixedFormat(self, out, fmt):
            if not self._can_export:
                raise RuntimeError("no ExportAsFixedFormat")
            self.calls.append(("export", out, fmt))

        def SaveAs(self, out, FileFormat=None):
            if not self._can_saveas:
                raise RuntimeError("no SaveAs")
            self.calls.append(("saveas", out, FileFormat))

        def Close(self, save):
            self.closed = save

    class _App:
        def __init__(self, display_alerts=5, screen_updating=True,
                     save_interval=10, doc=None):
            self.DisplayAlerts = display_alerts
            self.ScreenUpdating = screen_updating
            self.Options = SimpleNamespace(SaveInterval=save_interval)
            self.doc = doc or TestComConvert._Doc()
            self.Documents = self
            self.Count = 1  # 活性探针（Documents.Count）：健康实例不断言
            self.quit_calls = []
            self.open_kwargs = None
            self.open_args = None

        def Open(self, *a, **k):
            self.open_args = a
            self.open_kwargs = k
            return self.doc

        def Quit(self, *a):
            self.quit_calls.append(a)

    @staticmethod
    def _no_active(progid):
        raise RuntimeError("not running")

    def test_new_instance_hidden_quit(self):
        apps = []

        def dex(progid):
            a = self._App()
            apps.append(a)
            return a

        def dsp(progid):
            raise AssertionError("不应附着")

        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("KWPS.Application",),
                         dispatch=dsp, dispatch_ex=dex,
                         get_active=self._no_active)
        self.assertTrue(r.endswith("out.pdf"))
        a = apps[0]
        self.assertIs(a.Visible, False)          # 自建隐藏
        self.assertEqual(a.quit_calls, [(0,)])   # Quit(0) 不保存
        self.assertEqual(a.doc.closed, 0)        # Close(0)
        self.assertIs(a.doc.Saved, True)
        self.assertEqual(a.DisplayAlerts, 0)
        self.assertEqual(a.open_kwargs.get("ReadOnly"), True)
        self.assertEqual(a.open_kwargs.get("AddToRecentFiles"), False)

    def test_running_instance_safe_attach(self):
        a = self._App(display_alerts=5, screen_updating=True, save_interval=30)

        def dex(progid):
            raise AssertionError("用户已开，不应新建")

        def dsp(progid):
            return a

        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("KWPS.Application",),
                         dispatch=dsp, dispatch_ex=dex,
                         get_active=lambda progid: a)  # 探针验活走同一对象
        self.assertTrue(r.endswith("out.pdf"))
        self.assertEqual(a.quit_calls, [])            # 不退出用户实例
        self.assertIsNone(getattr(a, "Visible", None))  # 不动 Visible
        self.assertEqual(a.doc.closed, 0)
        self.assertEqual(a.DisplayAlerts, 5)            # 恢复
        self.assertEqual(a.ScreenUpdating, True)        # 恢复
        self.assertEqual(a.Options.SaveInterval, 30)    # 恢复

    def test_dispatchex_failure_attaches_safely(self):
        a = self._App()

        def dex(progid):
            raise RuntimeError("no DispatchEx")

        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("KWPS.Application",),
                         dispatch=lambda progid: a, dispatch_ex=dex,
                         get_active=self._no_active)
        self.assertTrue(r.endswith("out.pdf"))
        self.assertEqual(a.quit_calls, [])
        self.assertIsNone(getattr(a, "Visible", None))
        self.assertEqual(a.doc.closed, 0)

    def test_saveas_fallback(self):
        a = self._App(doc=self._Doc(can_export=False))
        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("KWPS.Application",),
                         dispatch=lambda progid: a,
                         dispatch_ex=self._no_active,
                         get_active=self._no_active)
        self.assertTrue(r.endswith("out.pdf"))
        self.assertEqual(a.doc.calls[0][0], "saveas")

    def test_failure_cleans_up_owned_and_returns_none(self):
        a = self._App(doc=self._Doc(can_export=False, can_saveas=False))

        def dex(progid):
            return a

        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("KWPS.Application",),
                         dispatch=lambda progid: a, dispatch_ex=dex,
                         get_active=self._no_active)
        self.assertIsNone(r)
        self.assertEqual(a.quit_calls, [(0,)])   # 自建实例失败也退出
        self.assertEqual(a.doc.closed, 0)

    def test_opens_temp_copy_not_original(self):
        import shutil
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        src = os.path.join(d, "in.docx")
        with open(src, "wb") as f:
            f.write(b"PK\x03\x04dummy")
        app = self._App()
        r = _com_convert(src, os.path.join(d, "o.pdf"), ("WPS",),
                         dispatch=lambda p: app, dispatch_ex=self._no_active,
                         get_active=self._no_active)
        self.assertTrue(r)
        self.assertNotEqual(os.path.abspath(app.open_args[0]), os.path.abspath(src))
        self.assertTrue(os.path.isfile(src))          # 原文件未被动
        self.assertFalse(os.path.exists(app.open_args[0]))  # 临时副本已清

    def test_all_backends_fail_returns_none(self):
        def bad(progid):
            raise RuntimeError("unavailable")

        self.assertIsNone(_com_convert(
            "x.docx", os.path.abspath("out.pdf"), ("A", "B"),
            dispatch=bad, dispatch_ex=bad, get_active=self._no_active))

    def _rpc_dead(self, msg="RPC failed"):
        e = RuntimeError(msg)
        e.hresult = 0x800706BE  # RPC_S_CALL_FAILED（pywintypes.com_error 同款载荷）
        return e

    def _clean_dead(self):
        import pycbeta.render_pdf as R
        saved = set(R._DEAD_PROGIDS)
        R._DEAD_PROGIDS.clear()
        self.addCleanup(R._DEAD_PROGIDS.update, saved)
        self.addCleanup(R._DEAD_PROGIDS.difference_update,
                        set(R._DEAD_PROGIDS) - saved)

    def test_zombie_probe_falls_back_to_new_instance(self):
        # ROT 残留僵尸：探针抛 RPC 死 → 不附着，转 DispatchEx 新实例且成功
        import pycbeta.render_pdf as R
        self._clean_dead()
        zombie = self._App()

        class _ZombieDocs:
            @property
            def Count(self):
                raise self._err

        _z = _ZombieDocs()
        _z._err = self._rpc_dead()
        zombie.Documents = _z
        fresh = self._App()
        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("KWPS.Application",),
                         dispatch=lambda p: zombie,
                         dispatch_ex=lambda p: fresh,
                         get_active=lambda p: zombie)
        self.assertTrue(r.endswith("out.pdf"))
        self.assertEqual(fresh.quit_calls, [(0,)])  # 新实例照常 Quit
        self.assertIn("KWPS.Application", R._DEAD_PROGIDS)

    def test_rpc_death_skips_progid_and_returns_none(self):
        # COM 全灭（RPC 死码）：该 progid 返回 None 走链，不抛回 CLI
        import pycbeta.render_pdf as R
        self._clean_dead()

        def dead(progid):
            raise self._rpc_dead()

        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("GONE-APP",),
                         dispatch=dead, dispatch_ex=dead,
                         get_active=self._no_active)
        self.assertIsNone(r)
        self.assertIn("GONE-APP", R._DEAD_PROGIDS)

    def test_dead_progid_skipped_on_retry(self):
        # 死亡名单命中：第二次调用不再碰 dispatch，直接跳过
        import pycbeta.render_pdf as R
        self._clean_dead()
        R._DEAD_PROGIDS.add("ZOMBIE-APP")
        calls = []

        def dsp(progid):
            calls.append(progid)
            return self._App()

        r = _com_convert("x.docx", os.path.abspath("out.pdf"),
                         ("ZOMBIE-APP",),
                         dispatch=dsp, dispatch_ex=dsp,
                         get_active=self._no_active)
        self.assertIsNone(r)
        self.assertEqual(calls, [])

    def test_apartment_helper_tolerates_missing_pythoncom(self):
        import builtins
        import pycbeta.render_pdf as R
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "pythoncom":
                raise ImportError("no pywin32")
            return real_import(name, *a, **k)

        with unittest.mock.patch.object(builtins, "__import__",
                                        side_effect=fake_import):
            mod, inited = R._ensure_com_apartment()
        self.assertIsNone(mod)
        self.assertFalse(inited)

    def test_is_rpc_dead_signed_and_plain(self):
        import pycbeta.render_pdf as R
        e = RuntimeError("x")
        e.hresult = -2147023170  # 0x800706BE 有符号形态
        self.assertTrue(R._is_rpc_dead(e))
        e2 = RuntimeError("y")
        e2.hresult = 0x800706BA
        self.assertTrue(R._is_rpc_dead(e2))
        self.assertFalse(R._is_rpc_dead(RuntimeError("z")))
        self.assertFalse(R._is_rpc_dead(None))


class TestPdfPageTypography(unittest.TestCase):
    """html2pdf：纸张 body 字号/行距经 theme.tags 补到 CSS（在 theme_css 之后覆盖）。"""

    def test_css_body_override(self):
        from pycbeta.theme import PAGE_PRESETS
        r = PdfRenderer(page="16开", page_presets=PAGE_PRESETS,
                        font_stack=["SimSun"])
        self.assertIn("body { font-size: 10.5pt; line-height: 1.5; }", r._pdf_css())

    def test_css_no_presets_keeps_css_body(self):
        r = PdfRenderer(page="16开", font_stack=["SimSun"])
        # 无 page_presets → 不应用纸张键；tags body 仍是 CSS 的 12pt/1.4
        self.assertIn("body { font-size: 12pt; line-height: 1.4; }", r._pdf_css())


if __name__ == "__main__":
    unittest.main(verbosity=2)
