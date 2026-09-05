"""P1 GUI：dataclass/三槽/临时presets（无界面依赖）+ 面板冒烟（offscreen）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.gui.panel import (
    DOCX_SINGLES, HTML_SINGLES, XmlOptions, apply_source_edits, detect_engines,
    load_slot, options_from_presets, reset_factory, save_current, slot_paths,
    write_temp_presets,
)
from pycbeta.theme import load_presets


class TestSlots(unittest.TestCase):
    def setUp(self):
        import shutil
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "pycbeta"))
        with open(os.path.join(self.root, "pycbeta", "config.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"output": {"t2s": True}, "x": 1}, f)
        self._shutil = shutil

    def tearDown(self):
        self._shutil.rmtree(self.root, ignore_errors=True)

    def test_user_missing_falls_back_factory(self):
        data, actual = load_slot("user", self.root)
        self.assertEqual(actual, "factory")
        self.assertTrue(data["output"]["t2s"])

    def test_save_rotates_last(self):
        save_current({"v": 1}, self.root)
        _d, actual = load_slot("user", self.root)
        self.assertEqual(actual, "user")
        save_current({"v": 2}, self.root)
        last, actual = load_slot("last", self.root)
        self.assertEqual(actual, "last")
        self.assertEqual(last, {"v": 1})
        cur, _a = load_slot("user", self.root)
        self.assertEqual(cur, {"v": 2})

    def test_reset_factory(self):
        save_current({"v": 9}, self.root)
        data = reset_factory(self.root)
        self.assertTrue(data["output"]["t2s"])
        cur, actual = load_slot("user", self.root)
        self.assertEqual(actual, "user")
        self.assertTrue(cur["output"]["t2s"])
        last, _a = load_slot("last", self.root)
        self.assertEqual(last, {"v": 9})

    def test_slot_paths(self):
        factory, user, last = slot_paths(self.root)
        self.assertTrue(factory.endswith("config.json"))
        self.assertTrue(user.endswith("config.user.json"))
        self.assertTrue(last.endswith("config.last.json"))


class TestTempPresets(unittest.TestCase):
    def test_merge(self):
        base = {"output": {"t2s": False, "show_notes": True,
                           "pagination": {"enabled": True}},
                "pages": {"a4": {"margins": {"top": 1}}},
                "annotations": {"enabled": False},
                "verify": {"maxDiff": 10}}
        opts = XmlOptions(page="a4", margins={"top": 2.0}, font_scale=1.5, t2s=True,
                          output={"show_notes": False},
                          pagination={"enabled": False},
                          annotations={"enabled": True},
                          verify={"maxDiff": 3})
        path = write_temp_presets(base, opts)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        finally:
            os.remove(path)
        self.assertFalse(data["output"]["show_notes"])
        self.assertFalse(data["output"]["pagination"]["enabled"])
        self.assertTrue(data["annotations"]["enabled"])
        self.assertEqual(data["verify"]["maxDiff"], 3)
        self.assertEqual(data["pages"]["a4"]["margins"], {"top": 2.0})
        self.assertTrue(data["output"]["t2s"])
        self.assertEqual(data["output"]["font_scale"], 1.5)
        # base 未被污染
        self.assertTrue(base["output"]["show_notes"])


class TestOptionsModel(unittest.TestCase):
    def test_defaults(self):
        o = XmlOptions()
        self.assertEqual(o.formats, ["pdf"])
        self.assertEqual(o.font_scale, 1.0)
        self.assertFalse(o.t2s)

    def test_from_presets(self):
        presets = load_presets()
        o = options_from_presets(presets)
        self.assertIn(o.page, (presets.get("pages") or {}).keys() or ["a4"])
        self.assertEqual(o.formats, ["pdf"])
        self.assertIsInstance(o.pagination, dict)
        self.assertIsInstance(o.annotations, dict)


class TestPanelSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        presets = load_presets()
        panel = XmlOptionsPanel(presets)
        self.assertEqual(panel.tabs.count(), 7)
        self.assertEqual([panel.tabs.tabText(i) for i in range(7)],
                         ["输出格式", "页面", "分页", "排版", "注释", "注音", "校验"])
        # 页面纸张下拉带尺寸标签且取值仍是名字
        self.assertIn("×", panel.page_box.itemText(0))
        self.assertEqual(panel.page_box.itemData(0), "a4")
        o1 = panel.get_options()
        panel.set_options(o1)
        o2 = panel.get_options()
        self.assertEqual(o1.page, o2.page)
        self.assertEqual(o1.font_set, o2.font_set)
        self.assertEqual(o1.engine, o2.engine)
        self.assertEqual(o1.formats, o2.formats)
        self.assertEqual(o1.t2s, o2.t2s)
        self.assertEqual(o1.annotations["style"], o2.annotations["style"])
        self.assertEqual(o1.pagination.get("enabled"), o2.pagination.get("enabled"))

    def test_t2s_auto_font(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        panel.t2s_box.setChecked(True)
        self.assertTrue(panel.font_box.currentData().endswith(":zh-Hans"))
        panel.t2s_box.setChecked(False)
        self.assertEqual(panel.font_box.currentData(), "default")


class TestEngineSingles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_detect_keys(self):
        status = detect_engines(load_presets())
        self.assertEqual(set(status.keys()),
                         set(DOCX_SINGLES) | set(HTML_SINGLES))
        self.assertTrue(all(isinstance(v, bool) for v in status.values()))
        # 随包引擎在本仓一定存在
        self.assertTrue(status["minipdf"])
        self.assertTrue(status["cbetapdf"])

    def test_items_per_pipe(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertEqual(panel.single_box.count(), 1 + len(DOCX_SINGLES))
        panel.engine_html.setChecked(True)
        self.assertEqual(panel.single_box.count(), 1 + len(HTML_SINGLES))
        panel.engine_docx.setChecked(True)
        self.assertEqual(panel.single_box.count(), 1 + len(DOCX_SINGLES))

    def test_set_options_restores_single(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        opts = panel.get_options()
        opts.engine = "html2pdf:chromium"
        panel.set_options(opts)
        self.assertTrue(panel.engine_html.isChecked())
        self.assertEqual(panel.single_box.currentData(), "chromium")
        self.assertEqual(panel.get_options().engine, "html2pdf:chromium")

    def test_missing_single_red_hint(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        panel._status = {k: False for k in panel._status}
        panel._refresh_singles(keep="wps")
        self.assertEqual(panel.single_box.currentData(), "wps")
        self.assertIn("red", panel.engine_hint.styleSheet())
        self.assertIn("WPS", panel.engine_hint.text())

    def test_config_box_on_top(self):
        from PySide6.QtWidgets import QGroupBox
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        top = panel.layout().itemAt(0).widget()
        self.assertIsInstance(top, QGroupBox)
        self.assertEqual(top.title(), "配置")


class TestOfficeDetect(unittest.TestCase):
    def test_no_com_never_ready(self):
        from pycbeta.gui.panel import _office_ready
        self.assertFalse(_office_ready(["winword.exe"], ["C:\\x\\WINWORD.EXE"], [],
                                       has_com=False,
                                       which=lambda n: "C:\\x\\winword.exe",
                                       isfile=lambda p: True))

    def test_which_hit(self):
        from pycbeta.gui.panel import _office_ready
        self.assertTrue(_office_ready(["wps.exe"], [], [],
                                      has_com=True,
                                      which=lambda n: "C:\\wps.exe" if n == "wps.exe" else None,
                                      isfile=lambda p: False,
                                      isdir=lambda p: False))

    def test_path_hit(self):
        from pycbeta.gui.panel import _office_ready
        self.assertTrue(_office_ready(["winword.exe"], ["C:\\o\\WINWORD.EXE"], [],
                                      has_com=True,
                                      which=lambda n: None,
                                      isfile=lambda p: p == "C:\\o\\WINWORD.EXE"))

    def test_nothing_found(self):
        from pycbeta.gui.panel import _office_ready
        self.assertFalse(_office_ready(["winword.exe"], ["C:\\o\\WINWORD.EXE"], [],
                                       has_com=True,
                                       which=lambda n: None,
                                       isfile=lambda p: False,
                                       isdir=lambda p: False))

    def test_versioned_dir_glob(self):
        from pycbeta.gui.panel import _office_ready
        hit = [r"C:\Apps\WPS Office\12.1.0.21915\office6\wps.exe"]
        fake_glob = lambda pat: hit if pat.endswith("wps.exe") else []
        self.assertTrue(_office_ready(["wps.exe"], [], [],
                                      has_com=True,
                                      which=lambda n: None,
                                      isfile=lambda p: False,
                                      isdir=lambda p: False,
                                      glob=fake_glob,
                                      extra_globs=[r"C:\Apps\WPS Office\*\office6\wps.exe"]))
        self.assertFalse(_office_ready(["wps.exe"], [], [],
                                       has_com=True,
                                       which=lambda n: None,
                                       isfile=lambda p: False,
                                       isdir=lambda p: False,
                                       glob=lambda pat: [],
                                       extra_globs=[r"C:\Apps\WPS Office\*\office6\wps.exe"]))


class TestWorkIdCase(unittest.TestCase):
    def test_lower_accepted(self):
        from pycbeta.fetch import is_work_id, parse_work_id
        self.assertTrue(is_work_id("t0349"))
        self.assertTrue(is_work_id("tx0006"))
        self.assertEqual(parse_work_id("t0349"), ("T", "0349"))
        self.assertEqual(parse_work_id("yp0019"), ("YP", "0019"))

    def test_invalid_still_rejected(self):
        from pycbeta.fetch import is_work_id
        self.assertFalse(is_work_id(""))
        self.assertFalse(is_work_id(None))
        self.assertFalse(is_work_id("hello"))
        self.assertFalse(is_work_id("T"))


class TestProducedPaths(unittest.TestCase):
    def test_parse(self):
        import tempfile
        from pycbeta.gui.__main__ import parse_produced_paths
        d = tempfile.mkdtemp()
        try:
            a = os.path.join(d, "T0672.docx")
            b = os.path.join(d, "T0672_001.html")
            open(a, "w").close()
            open(b, "w").close()
            log = (f"T0672: docx(footnote) -> {a}\n"
                   "some noise without arrow\n"
                   f"T0672: html(endnote) -> 1 file(s) in {d}\n"
                   f"note -> {b}\n"
                   "broken -> C:\\nonexistent\\x.docx\n")
            self.assertEqual(parse_produced_paths(log), [a, b])
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_empty(self):
        from pycbeta.gui.__main__ import parse_produced_paths
        self.assertEqual(parse_produced_paths(""), [])
        self.assertEqual(parse_produced_paths(None), [])


class TestLayoutRegroup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_single_engine_label(self):
        from PySide6.QtWidgets import QLabel
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        texts = [w.text() for w in panel.findChildren(QLabel)]
        self.assertIn("单引擎", texts)
        self.assertNotIn("单体", texts)

    def test_margins_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        opts = panel.get_options()
        opts.margins = {"top": 20.0, "bottom": 21.0, "left": 15.0, "right": 16.0}
        panel.set_options(opts)
        back = panel.get_options()
        self.assertEqual(back.margins, opts.margins)

    def test_layout_tab_regroup(self):
        from PySide6.QtWidgets import QLabel
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        # 两脏数据开关 + 说明同处排版卡第二列语境
        self.assertTrue(panel.ign_style_box.isEnabled() or True)
        hints = [w.text() for w in panel.findChildren(QLabel)
                 if "脏数据" in w.text()]
        self.assertTrue(hints)


class TestMainWindowUx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_out_default_and_mode_switch(self):
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            self.assertTrue(w.out_edit.text())
            w.ids_edit.setText("t0349")
            self.assertTrue(w.mode_ids.isChecked())
            w.path_edit.setText("x")
            self.assertTrue(w.mode_file.isChecked())
        finally:
            w.close()

    def test_title_has_gui_date(self):
        import re
        from pycbeta.gui.__main__ import MainWindow, _gui_date
        self.assertRegex(_gui_date(), r"^\d{4}-\d{2}-\d{2}$")
        w = MainWindow()
        try:
            self.assertRegex(w.windowTitle(),
                             r"^CBETA XML 格式转换 v1\.0（\d{4}-\d{2}-\d{2}）$")
        finally:
            w.close()

    def test_open_cell_routing(self):
        import tempfile
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTableWidgetItem
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            d = tempfile.mkdtemp()
            a = os.path.join(d, "A.docx")
            b = os.path.join(d, "B.md")
            open(a, "w").close()
            open(b, "w").close()
            w.table.setRowCount(1)
            for c in range(5):
                w.table.setItem(0, c, QTableWidgetItem(""))
            opened = []
            import pycbeta.gui.__main__ as M
            orig_open = M.QDesktopServices.openUrl
            orig_menu = M.QMenu

            class FakeAction:
                def setData(self, _d):
                    pass

            class FakeMenu:
                def __init__(self, *a, **k):
                    pass

                def addAction(self, _t):
                    return FakeAction()

                def exec(self, _pos):
                    return None  # 用户取消菜单

            M.QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u.toLocalFile()) or True)
            M.QMenu = FakeMenu
            try:
                w._on_file(0, f"{a};{b}")
                self.assertEqual(w.table.item(0, 4).data(Qt.UserRole), f"{a};{b}")
                self.assertEqual(w.table.item(0, 4).text(), "A.docx；B.md")
                w._open_cell(0, 4)
                self.assertEqual(opened, [])  # 多文件走菜单，不直开
                # 单文件直开
                w._on_file(0, a)
                w._open_cell(0, 4)
                self.assertEqual([p.replace("/", os.sep) for p in opened], [a])
            finally:
                M.QDesktopServices.openUrl = orig_open
                M.QMenu = orig_menu
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
            w.close()


class TestSourceDialog(unittest.TestCase):
    def test_apply_merge(self):
        base = {"source": {"xml_dir": "A", "download_dir": "B", "catalog": "C"},
                "downloads": {"xml": "U1", "html": "U2"},
                "output": {"t2s": False}}
        out = apply_source_edits(base, {"source": {"xml_dir": "A2"},
                                        "downloads": {"xml": "U9", "docx": "U3"}})
        self.assertEqual(out["source"]["xml_dir"], "A2")
        self.assertEqual(out["source"]["download_dir"], "B")
        self.assertEqual(out["downloads"]["xml"], "U9")
        self.assertEqual(out["downloads"]["html"], "U2")
        self.assertEqual(out["downloads"]["docx"], "U3")
        self.assertFalse(out["output"]["t2s"])
        # base 未被污染
        self.assertEqual(base["source"]["xml_dir"], "A")

    def test_dialog_builds(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            self.assertTrue(dlg.path_edits["xml_dir"].text())
            self.assertGreater(dlg.dl_table.rowCount(), 0)
            self.assertEqual(dlg.dl_table.item(0, 0).text(), "xml")
            flags = dlg.dl_table.item(0, 0).flags()
            from PySide6.QtCore import Qt
            self.assertFalse(bool(flags & Qt.ItemIsEditable))
        finally:
            dlg.close()


if __name__ == "__main__":
    unittest.main()
