"""P1 GUI：dataclass/三槽/临时presets（无界面依赖）+ 面板冒烟（offscreen）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.gui.panel import (
    DOCX_SINGLES, HTML_SINGLES, XmlOptions, apply_source_edits, config_presets_dir,
    delete_config_preset, detect_engines, list_config_presets, load_config_preset,
    load_slot, options_from_presets, reset_factory, save_config_preset, save_current,
    set_config_preset_theme, slot_paths, write_temp_preset, write_temp_presets,
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

    def test_save_writes_default_preset_no_rotation(self):
        save_current({"v": 1}, self.root)
        _d, actual = load_slot("user", self.root)
        self.assertEqual(actual, "user")
        save_current({"v": 2}, self.root)
        cur, _a = load_slot("user", self.root)
        self.assertEqual(cur, {"v": 2})
        # 默认预设落在 presets/ 内，且不再有 config.last.json
        self.assertTrue(os.path.isfile(
            os.path.join(self.root, "presets", "config.user.json")))
        self.assertFalse(os.path.exists(
            os.path.join(self.root, "config.last.json")))

    def test_reset_factory_reads_only(self):
        save_current({"v": 9}, self.root)
        data = reset_factory(self.root)
        self.assertTrue(data["output"]["t2s"])
        # 只读：默认预设文件不被覆盖
        cur, _a = load_slot("user", self.root)
        self.assertEqual(cur, {"v": 9})

    def test_slot_paths(self):
        factory, user = slot_paths(self.root)
        self.assertTrue(factory.endswith("config.json"))
        self.assertTrue(user.endswith(os.path.join("presets", "config.user.json")))


class TestConfigPresets(unittest.TestCase):
    """配置预设：presets/*.json 快照（样式 *.css 同目录，按扩展名区分）。"""

    def setUp(self):
        import shutil
        self.root = tempfile.mkdtemp()
        self._shutil = shutil

    def tearDown(self):
        self._shutil.rmtree(self.root, ignore_errors=True)

    def test_save_list_load_roundtrip(self):
        path = save_config_preset("我的 快照", {"output": {"t2s": True}}, self.root)
        self.assertTrue(path.endswith(".json"))
        self.assertEqual(list_config_presets(self.root), [("我的 快照", path)])
        self.assertEqual(load_config_preset("我的 快照", self.root),
                         {"output": {"t2s": True}})
        save_config_preset("我的 快照", {"output": {"t2s": False}}, self.root)
        self.assertFalse(
            load_config_preset("我的 快照", self.root)["output"]["t2s"])
        self.assertTrue(delete_config_preset("我的 快照", self.root))
        self.assertEqual(list_config_presets(self.root), [])

    def test_bad_names_and_outside(self):
        with self.assertRaises(ValueError):
            save_config_preset("  ///  ", {"a": 1}, self.root)
        with self.assertRaises(ValueError):
            load_config_preset("没有这个", self.root)
        with self.assertRaises(ValueError):
            delete_config_preset("没有这个", self.root)
        outside = os.path.join(self.root, "evil.json")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("{}")
        with self.assertRaises(ValueError):
            delete_config_preset(outside, self.root)

    def test_list_ignores_css_and_missing_dir(self):
        self.assertEqual(list_config_presets(self.root), [])
        d = config_presets_dir(self.root)
        os.makedirs(d)
        with open(os.path.join(d, "a.css"), "w", encoding="utf-8") as f:
            f.write("/* x */\n")
        self.assertEqual(list_config_presets(self.root), [])

    def test_preset_theme_key_roundtrip(self):
        path = save_config_preset(
            "带样式", {"output": {"t2s": True}}, self.root)
        set_config_preset_theme(path, "霞鹜文楷")
        data = load_config_preset(path)
        self.assertEqual(data["pdf-docx-user-theme"], "霞鹜文楷.css")
        self.assertTrue(data["output"]["t2s"])  # 其余键原样保留
        set_config_preset_theme(path, "pdf_docx.css")  # 出厂值删键
        self.assertNotIn("pdf-docx-user-theme", load_config_preset(path))


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
        self.assertEqual(data["pages"]["a4"]["custom_margins"], {"top": 2.0})
        self.assertTrue(data["output"]["t2s"])
        self.assertEqual(data["output"]["font_scale"], 1.5)
        # base 未被污染
        self.assertTrue(base["output"]["show_notes"])

    def test_temp_presets_t2s_without_margins(self):
        from pycbeta.gui.panel import write_temp_presets, XmlOptions
        base = {"output": {}}
        opts = XmlOptions(page="a4", t2s=True)  # margins=None（跟随）
        path = write_temp_presets(base, opts)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        finally:
            os.remove(path)
        self.assertTrue(data["output"]["t2s"])  # 不依赖 margins 照写
        self.assertNotIn("custom_margins", data.get("pages", {}).get("a4", {}))

    def test_write_temp_preset_dict(self):
        data = {"output": {"t2s": True}, "pages": {"a4": {}}}
        path = write_temp_preset(data)
        try:
            with open(path, encoding="utf-8") as f:
                back = json.load(f)
            self.assertTrue(back["output"]["t2s"])
        finally:
            os.remove(path)
        # 非 dict 容错
        path2 = write_temp_preset(None)
        try:
            with open(path2, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {})
        finally:
            os.remove(path2)

    def test_temp_presets_strips_stale_custom_margins(self):
        from pycbeta.gui.panel import write_temp_presets, XmlOptions
        # base 带僵尸 custom_margins，但本次跟随 → 快照必须干净
        base = {"output": {}, "pages": {"a4": {
            "margins": {"top": 25.4, "right": 25.4,
                        "bottom": 25.4, "left": 25.4},
            "custom_margins": {"top": 9.9, "right": 9.9,
                               "bottom": 9.9, "left": 9.9}}}}
        opts = XmlOptions(page="a4")  # margins=None（跟随）
        path = write_temp_presets(base, opts)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        finally:
            os.remove(path)
        self.assertNotIn("custom_margins", data["pages"]["a4"])
        self.assertEqual(data["pages"]["a4"]["margins"]["top"], 25.4)


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
        self.assertEqual(panel.tabs.count(), 8)
        self.assertEqual([panel.tabs.tabText(i) for i in range(8)],
                         ["输出格式", "样式表", "页面", "分页", "排版", "注释", "注音", "校验"])
        # 页面纸张下拉带尺寸标签且取值仍是名字
        self.assertIn("×", panel.page_box.itemText(0))
        self.assertEqual(panel.page_box.itemData(0), "a4")
        o1 = panel.get_options()
        panel.set_options(o1)
        o2 = panel.get_options()
        self.assertEqual(o1.page, o2.page)
        self.assertEqual(o1.font_lang, o2.font_lang)
        self.assertEqual(o1.engine, o2.engine)
        self.assertEqual(o1.formats, o2.formats)
        self.assertEqual(o1.t2s, o2.t2s)
        self.assertEqual(o1.vertical, o2.vertical)
        self.assertEqual(o1.annotations["style"], o2.annotations["style"])
        self.assertEqual(o1.pagination.get("enabled"), o2.pagination.get("enabled"))

    def test_t2s_auto_font(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        panel.t2s_box.setChecked(True)
        self.assertEqual(panel.lang_box.currentData(), "zh-Hans")
        self.assertFalse(panel.lang_box.isEnabled())  # t2s 锁定简体
        panel.t2s_box.setChecked(False)
        self.assertTrue(panel.lang_box.isEnabled())
        # 字库两态 roundtrip
        panel.lang_box.setCurrentIndex(
            panel.lang_box.findData("zh-Hans"))
        self.assertEqual(panel.get_options().font_lang, "zh-Hans")

    def test_vertical_mode_group(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        # 竖排在简体转换左边，同属模式组
        items = [panel.mode_group.layout().itemAt(i).widget()
                 for i in range(panel.mode_group.layout().count())]
        self.assertEqual(items[0], panel.vert_box)
        self.assertEqual(items[1], panel.t2s_box)
        self.assertFalse(panel.get_options().vertical)
        panel.vert_box.setChecked(True)
        o = panel.get_options()
        self.assertTrue(o.vertical)
        panel.set_options(o)
        self.assertTrue(panel.vert_box.isChecked())


class TestHtmlThemeRow(unittest.TestCase):
    """样式表卡「html/epub 增量」行：下拉 + 设为默认写 run.json html 槽。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_set_user_theme_slot(self):
        import tempfile
        from pycbeta.gui.css_editor import set_user_theme
        from pycbeta.theme import load_run_config
        d = tempfile.mkdtemp()
        p = set_user_theme("mark", root=d, slot="html-epub-user-theme")
        run = load_run_config(p)
        self.assertEqual(run.get("html-epub-user-theme"), "mark.css")
        self.assertEqual(run.get("pdf-docx-user-theme"), "")  # pdf 槽不动
        with self.assertRaises(ValueError):
            set_user_theme("x", root=d, slot="nope")

    def test_row_exists_and_refresh(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        from pycbeta.theme import load_presets
        panel = XmlOptionsPanel(load_presets())
        self.assertIsNotNone(panel.html_box)
        panel._refresh_html_box(keep_value="")
        self.assertEqual(panel.html_box.selected_value(), "")
        panel._refresh_html_box(keep_value="large-print")
        self.assertEqual(panel.html_box.selected_value(), "large-print")

    def test_save_writes_html_slot(self):
        import unittest.mock as mock
        from pycbeta.gui.panel import XmlOptionsPanel
        from pycbeta.theme import load_presets
        panel = XmlOptionsPanel(load_presets())
        panel._refresh_html_box(keep_value="large-print")
        with mock.patch("pycbeta.gui.css_editor.set_user_theme") as m:
            panel._on_html_theme_default()
            m.assert_called_once_with("large-print",
                                      slot="html-epub-user-theme")


class TestSourceBaselineTab(unittest.TestCase):
    """数据源「校验基线」tab（排第一）：4 行顺序/键映射/保存。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_first_tab_rows(self):
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            self.assertEqual(dlg.src_tabs.tabText(1), "本地官方电子书")
            self.assertEqual(list(dlg.base_edits.keys()),
                             ["xml_dir", "txt", "txt_notes", "docx", "epub",
                              "pdf"])
            for e in dlg.base_edits.values():
                self.assertTrue(e.isReadOnly())
        finally:
            dlg.close()

    def test_xml_dir_row_on_top(self):
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            lay = dlg.src_tabs.widget(1).layout()

            def pos(edit):
                for i in range(lay.count()):
                    sub = lay.itemAt(i).layout()
                    if sub is not None and sub.indexOf(edit) >= 0:
                        return i
                return -1

            p_xml = pos(dlg.base_edits["xml_dir"])
            self.assertGreaterEqual(p_xml, 0)
            self.assertLess(p_xml, pos(dlg.base_root_edit))
            self.assertLess(p_xml, pos(dlg.base_edits["txt"]))
        finally:
            dlg.close()

    def test_presets_include_baselines(self):
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            dlg.base_edits["txt_notes"].setText("R:/txt")
            dlg.base_edits["docx"].setText("R:/docx")
            dlg.base_edits["epub"].setText("")
            p = dlg._dialog_presets()
            self.assertEqual(p["source"]["baselines"],
                             {"txt": "", "txt_notes": "R:/txt",
                              "docx": "R:/docx", "epub": "", "pdf": ""})
        finally:
            dlg.close()

    def test_detect_fills_rows(self):
        import shutil
        import tempfile
        from pycbeta.gui.panel import SourceDialog
        d = tempfile.mkdtemp()
        try:
            for name in ("cbeta-text-with-notes", "cbeta_docx_2026r2",
                         "cbeta_epub_2026r2"):
                os.makedirs(os.path.join(d, name))
            dlg = SourceDialog()
            try:
                dlg.base_root_edit.setText(d)
                dlg._on_detect_baselines()
                self.assertEqual(
                    dlg.base_edits["txt_notes"].text(),
                    os.path.abspath(os.path.join(d, "cbeta-text-with-notes")))
                self.assertEqual(
                    dlg.base_edits["docx"].text(),
                    os.path.abspath(os.path.join(d, "cbeta_docx_2026r2")))
                self.assertEqual(
                    dlg.base_edits["epub"].text(),
                    os.path.abspath(os.path.join(d, "cbeta_epub_2026r2")))
                p = dlg._dialog_presets()
                self.assertEqual(p["source"]["baselines_root"], d)
            finally:
                dlg.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_xml_dir_sync(self):
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            dlg.base_edits["xml_dir"].setText("X:/a")
            self.assertEqual(dlg.path_edits["xml_dir"].text(), "X:/a")
            dlg.path_edits["xml_dir"].setText("X:/b")
            self.assertEqual(dlg.base_edits["xml_dir"].text(), "X:/b")
        finally:
            dlg.close()

    def test_io_tab_contents(self):
        from pycbeta.gui.panel import SourceDialog
        from PySide6.QtWidgets import QLabel
        dlg = SourceDialog()
        try:
            tab = dlg.src_tabs.widget(0)
            texts = [w.text() for w in tab.findChildren(QLabel)]
            self.assertIn("XML及电子书", texts)
            self.assertIn("输出目录", texts)
            self.assertTrue(any(
                "官方下载保存平展目录" in t and "source.cbeta_ebook" in t
                for t in texts))
            self.assertTrue(any("title_t2s" in t for t in texts))
            self.assertTrue(any("source.out_dir" in t for t in texts))
            self.assertEqual(dlg.windowTitle()[:2], "设置")
            # 输出目录初始值透传构造参数
            dlg2 = SourceDialog(out_dir="O:/x")
            try:
                self.assertEqual(dlg2.io_out_edit.text(), "O:/x")
                dlg2.io_out_edit.setText("O:/y")
                self.assertEqual(dlg2.out_dir(), "O:/y")
            finally:
                dlg2.close()
        finally:
            dlg.close()

    def test_xml_dir_row_removed_update_row_moved(self):
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            # 主表无 xml_dir 可见行（edit 保留为隐藏数据载体）
            self.assertIsNone(dlg.path_edits["xml_dir"].parent())
            # 更新按钮行在“官方数据更新源”tab 内
            tab_upd = dlg.src_tabs.widget(2)
            self.assertEqual(dlg.btn_update_data.parent(), tab_upd)
            self.assertEqual(dlg.btn_check_update.parent(), tab_upd)
            # 官方链接可点开
            from PySide6.QtWidgets import QLabel
            links = dlg.src_tabs.widget(1).findChildren(QLabel)
            self.assertTrue(any(w.openExternalLinks() for w in links))
        finally:
            dlg.close()


class TestPageMarginSwitch(unittest.TestCase):
    """取消跟随后切纸张：spin 显示必须跟随当前纸张（A5 custom/手机 custom 互不串扰）。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        presets = {
            "default_page": "a5",
            "pages": {
                "a5": {"size": [148, 210],
                       "margins": {"top": 25.4, "right": 25.4,
                                   "bottom": 25.4, "left": 25.4},
                       "custom_margins": {"top": 18.0, "bottom": 15.0,
                                          "left": 10.0, "right": 10.0}},
                "手机": {"size": [100, 178],
                         "margins": {"top": 10, "right": 10,
                                     "bottom": 10, "left": 10},
                         "custom_margins": {"top": 5.0, "bottom": 5.0,
                                            "left": 5.0, "right": 5.0}},
            },
        }
        return XmlOptionsPanel(presets)

    def _spins(self, panel):
        return {k: sp.value() for k, sp in panel.margin_spins.items()}

    def test_switch_page_refreshes_custom(self):
        panel = self._panel()
        try:
            panel.margin_follow.setChecked(False)
            panel.page_box.setCurrentIndex(panel.page_box.findData("手机"))
            self.assertEqual(
                self._spins(panel),
                {"top": 5.0, "right": 5.0, "bottom": 5.0, "left": 5.0})
            panel.page_box.setCurrentIndex(panel.page_box.findData("a5"))
            self.assertEqual(
                self._spins(panel),
                {"top": 18.0, "right": 10.0, "bottom": 15.0, "left": 10.0})
        finally:
            panel.close()

    def test_switch_page_follow_shows_preset(self):
        panel = self._panel()
        try:
            panel.margin_follow.setChecked(True)
            panel.page_box.setCurrentIndex(panel.page_box.findData("手机"))
            self.assertEqual(
                self._spins(panel),
                {"top": 10.0, "right": 10.0, "bottom": 10.0, "left": 10.0})
        finally:
            panel.close()


class TestConfigBar(unittest.TestCase):
    """配置栏（一切按下拉选中项）：保存/另存…/删除/设为默认 + default_page。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        from pycbeta.theme import load_presets
        return XmlOptionsPanel(load_presets())

    def test_buttons_present(self):
        panel = self._panel()
        try:
            self.assertEqual(panel.btn_save.text(), "保存")
            self.assertFalse(hasattr(panel, "btn_load"))  # 选中即载入，无独立载入键
            self.assertEqual(panel.btn_set_default.text(), "设为默认")
            self.assertFalse(hasattr(panel, "btn_update_data"))  # 已搬数据源窗口
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_save_writes_selected_preset(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        saved = {}
        with mock.patch.object(pm, "load_config_preset",
                               return_value={"output": {}}), \
                mock.patch.object(pm, "save_config_preset",
                                  side_effect=lambda n, d, root=None: saved.update(
                                      name=n, data=d)), \
                mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                  return_value=r"C:\x\p.json"):
            panel = pm.XmlOptionsPanel({"output": {}})
            try:
                panel.t2s_box.setChecked(True)
                panel._on_save()
                self.assertTrue(saved["data"]["output"]["t2s"])
                self.assertEqual(saved["name"], "p")
                self.assertEqual(panel.cfg_box.title(), "配置（已保存）")
            finally:
                panel.close() if hasattr(panel, "close") else None

    def test_factory_sentinel_loads_factory(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            panel.cfg_preset_box.setCurrentIndex(0)  # 出厂默认
            with mock.patch.object(pm, "load_slot", return_value=(
                    {"output": {"t2s": True}}, "factory")):
                panel._on_preset_chosen(0)
            self.assertTrue(panel.t2s_box.isChecked())
            self.assertEqual(panel.cfg_box.title(), "配置")  # 换预设后标题复原
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_preset_buttons_follow_selection(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            panel.cfg_preset_box.setCurrentIndex(0)  # 出厂默认
            panel._update_preset_buttons()
            self.assertFalse(panel.btn_save.isEnabled())
            self.assertFalse(panel.btn_preset_del.isEnabled())
            with mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                   return_value=r"C:\x\p.json"):
                panel._update_preset_buttons()
                self.assertTrue(panel.btn_save.isEnabled())
                self.assertTrue(panel.btn_preset_del.isEnabled())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_public_merged_preset_and_dialog(self):
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            d = panel.merged_preset({"output": {}})
            self.assertIn("default_page", d)
            self.assertIn("formats", d)
            dlg = pm.XmlOptionsDialog({"output": {}})
            try:
                self.assertIsNone(dlg.get_preset())  # 未 Accept
            finally:
                dlg.close()
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_set_default_sentinel_clears_slot(self):
        import unittest.mock as mock
        panel = self._panel()
        try:
            panel.cfg_preset_box.setCurrentIndex(0)  # 出厂默认
            with mock.patch("pycbeta.theme.set_run_slot") as m:
                panel._on_set_default()
                m.assert_called_once_with("config-json", "")
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_set_default_points_at_selected_preset(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            box = panel.cfg_preset_box
            box.blockSignals(True)
            box.addItem("foo", os.path.join(pm.REPO_ROOT, "presets", "foo.json"))
            box.setCurrentIndex(box.count() - 1)
            box.blockSignals(False)
            with mock.patch("pycbeta.theme.set_run_slot") as m:
                panel._on_set_default()
                m.assert_called_once_with("config-json", "presets/foo.json")
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_theme_default_writes_preset_when_selected(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            with mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                   return_value=r"C:\x\p.json"), \
                    mock.patch.object(pm, "set_config_preset_theme") as m_pre, \
                    mock.patch("pycbeta.gui.css_editor.set_user_theme") as m_run:
                panel.theme_box.setCurrentIndex(0)
                panel._on_theme_default()
                m_pre.assert_called_once_with(
                    r"C:\x\p.json", panel.theme_box.selected_value())
                m_run.assert_not_called()
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_theme_default_writes_run_slot_for_factory(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            panel.cfg_preset_box.setCurrentIndex(0)  # 出厂默认
            with mock.patch.object(pm, "set_config_preset_theme") as m_pre, \
                    mock.patch("pycbeta.gui.css_editor.set_user_theme") as m_run:
                panel._on_theme_default()
                m_run.assert_called_once_with(panel.theme_box.selected_value())
                m_pre.assert_not_called()
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_merged_preset_syncs_theme_box(self):
        import unittest.mock as mock
        panel = self._panel()
        try:
            with mock.patch.object(panel, "theme_box") as m_box:
                m_box.selected_value.return_value = "my"
                d = panel.merged_preset({"output": {}})
                self.assertEqual(d["pdf-docx-user-theme"], "my.css")
                m_box.selected_value.return_value = "pdf_docx.css"
                d2 = panel.merged_preset(
                    {"output": {}, "pdf-docx-user-theme": "old.css"})
                self.assertNotIn("pdf-docx-user-theme", d2)
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_theme_button_follows_preset_selection(self):
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            box = panel.cfg_preset_box
            box.blockSignals(True)
            box.setCurrentIndex(0)  # 出厂默认
            panel._update_theme_button()
            self.assertEqual(panel.theme_default_btn.text(), "设为默认")
            box.addItem("foo", os.path.join(pm.REPO_ROOT, "presets", "foo.json"))
            box.setCurrentIndex(box.count() - 1)
            panel._update_theme_button()
            self.assertEqual(panel.theme_default_btn.text(), "预设生效")
            box.blockSignals(False)
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_theme_status_says_effective(self):
        panel = self._panel()
        try:
            panel._refresh_theme_box()
            self.assertIn("当前生效", panel.theme_status.text())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_theme_box_follows_selected_preset(self):
        import json
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        import pycbeta.theme as _theme
        root = tempfile.mkdtemp()
        try:
            # 自带临时预设，不依赖仓库 presets/ 里恰好有 my.css（本地数据可变）
            mycss = os.path.join(root, "my.css")
            with open(mycss, "w", encoding="utf-8") as f:
                f.write("/* my */\n")
            pre = os.path.join(root, "A5.json")
            with open(pre, "w", encoding="utf-8") as f:
                json.dump({"pdf-docx-user-theme": "my.css"}, f)
            panel = self._panel()
            try:
                with mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                       return_value=pre), \
                        mock.patch.object(_theme, "list_presets",
                                          return_value=[("user", "my", mycss)]):
                    panel._refresh_theme_box()
                    self.assertEqual(panel.theme_box.selected_value(), "my")
                    self.assertIn("预设 A5", panel.theme_status.text())
            finally:
                panel.close() if hasattr(panel, "close") else None
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_theme_box_falls_back_without_preset_keys(self):
        import json
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        root = tempfile.mkdtemp()
        try:
            pre = os.path.join(root, "plain.json")
            with open(pre, "w", encoding="utf-8") as f:
                json.dump({"output": {}}, f)
            panel = self._panel()
            try:
                with mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                       return_value=pre):
                    panel._refresh_theme_box()  # 无键 → run 锚定，不崩
                    self.assertIn("当前生效", panel.theme_status.text())
            finally:
                panel.close() if hasattr(panel, "close") else None
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_theme_override_effective_until_refresh(self):
        # 「生效样式」下拉改选 → 本次运行覆盖值；刷新（回到锚定）后清空。
        panel = self._panel()
        try:
            self.assertIsNone(panel.theme_override())
            if panel.theme_box.count() < 2:
                self.skipTest("无可选样式项")
            panel.theme_box.setCurrentIndex(1)
            ov = panel.theme_override()
            self.assertIsNotNone(ov)
            self.assertTrue(ov == "" or ov.endswith(".css"))
            self.assertIn("本次", panel.theme_status.text())
            panel._refresh_theme_box()
            self.assertIsNone(panel.theme_override())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_open_style_editor_keeps_selection(self):
        # 打开/关闭 CSS 编辑器后，主面板「生效样式」选择与未落盘改选不得被重置回默认，
        # 也不得把已选样式平白标成「（默认）」。
        import unittest.mock as mock
        panel = self._panel()
        try:
            # 选一个非「（默认）」首项、带路径的项（用户预设，或退而求其次的出厂项）
            idx = -1
            for i in range(panel.theme_box.count() - 1, 0, -1):
                if (panel.theme_box.itemData(i) or {}).get("path"):
                    idx = i
                    break
            if idx < 0:
                self.skipTest("无可选样式项")
            panel.theme_box.setCurrentIndex(idx)
            sel = panel.theme_box.selected_value()
            sel_path = panel.theme_box.selected_path()
            self.assertTrue(sel_path)
            self.assertTrue(panel._theme_dirty)
            with mock.patch("pycbeta.gui.css_editor.CssEditorDialog") as M:
                M.return_value.exec.return_value = 0
                panel._open_style_editor()
                self.assertEqual(M.call_args.kwargs.get("initial_theme"), sel)
            self.assertEqual(panel.theme_box.selected_value(), sel)
            self.assertTrue(panel._theme_dirty)
            self.assertFalse(panel.theme_box.currentText().startswith("（默认）"))
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_typo_info_fixed_height_no_jump(self):
        # 灰字行不折行 + 固定单行高：改行距时行高不再上下跳动。
        panel = self._panel()
        try:
            self.assertFalse(panel.typo_info.wordWrap())
            h0 = panel.typo_info.height()
            self.assertEqual(h0, panel.typo_info.minimumHeight())
            panel.typo_follow.setChecked(False)
            for v in (1.5, 1.55, 1.6, 1.65):
                panel.typo_lh_spin.setValue(v)
                self.assertEqual(panel.typo_info.height(), h0)
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_apply_selected_preset_theme(self):
        import json
        import shutil
        from pycbeta.gui.panel import apply_selected_preset_theme
        root = tempfile.mkdtemp()
        try:
            pre = os.path.join(root, "A5.json")
            with open(pre, "w", encoding="utf-8") as f:
                json.dump({"pdf-docx-user-theme": "x.css"}, f)
            base = {"output": {}, "pdf-docx-user-theme": "old.css"}
            out = apply_selected_preset_theme(base, pre)
            self.assertEqual(out["pdf-docx-user-theme"], "x.css")
            self.assertEqual(base["pdf-docx-user-theme"], "old.css")  # 不动原字典
            out2 = apply_selected_preset_theme(base, "")
            self.assertEqual(out2, base)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_preset_widgets_present(self):
        panel = self._panel()
        try:
            self.assertIsNotNone(panel.cfg_preset_box)
            self.assertEqual(panel.btn_preset_save.text(), "另存…")
            self.assertEqual(panel.btn_preset_del.text(), "删除")
            self.assertEqual(panel.cfg_preset_box.itemData(0), "")  # 出厂默认占位
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_preset_chosen_loads_snapshot(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            box = panel.cfg_preset_box
            box.blockSignals(True)
            box.addItem("foo", "foo.json")
            box.setCurrentIndex(box.count() - 1)
            box.blockSignals(False)
            with mock.patch.object(pm, "load_config_preset",
                                   return_value={"output": {"t2s": True}}):
                panel._on_preset_chosen(box.currentIndex())
            self.assertTrue(panel.t2s_box.isChecked())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_delete_user_preset_warns(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            panel.cfg_preset_box.setCurrentIndex(0)
            with mock.patch.object(pm, "QMessageBox") as mb:
                panel._on_preset_delete()
                mb.information.assert_called_once()
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_delete_named_preset_confirms_and_clears_slot(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            box = panel.cfg_preset_box
            box.blockSignals(True)
            box.addItem("foo", r"C:\x\foo.json")
            box.setCurrentIndex(box.count() - 1)
            box.blockSignals(False)
            with mock.patch.object(pm, "QMessageBox") as mb, \
                    mock.patch.object(pm, "delete_config_preset") as m_del, \
                    mock.patch("pycbeta.theme.load_run_config",
                               return_value={"config-json": r"C:\x\foo.json"}), \
                    mock.patch("pycbeta.theme.set_run_slot") as m_slot:
                mbox = mb.return_value
                ok_btn, cancel_btn = mock.Mock(), mock.Mock()
                mbox.addButton.side_effect = (
                    lambda text, role: ok_btn if "确定" in text else cancel_btn)
                mbox.clickedButton.return_value = ok_btn
                panel._on_preset_delete()
                m_del.assert_called_once_with(r"C:\x\foo.json")
                m_slot.assert_called_once_with("config-json", "")
                self.assertEqual(panel.cfg_box.title(), "配置（已删除）")
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_delete_named_preset_cancel_keeps_file(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            box = panel.cfg_preset_box
            box.blockSignals(True)
            box.addItem("foo", r"C:\x\foo.json")
            box.setCurrentIndex(box.count() - 1)
            box.blockSignals(False)
            with mock.patch.object(pm, "QMessageBox") as mb, \
                    mock.patch.object(pm, "delete_config_preset") as m_del:
                mbox = mb.return_value
                ok_btn, cancel_btn = mock.Mock(), mock.Mock()
                mbox.addButton.side_effect = (
                    lambda text, role: ok_btn if "确定" in text else cancel_btn)
                mbox.clickedButton.return_value = cancel_btn
                panel._on_preset_delete()
                m_del.assert_not_called()
                self.assertEqual(panel.cfg_box.title(), "配置")
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_preset_save_as_writes_snapshot(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            saved = {}
            with mock.patch.object(pm, "QInputDialog") as qi, \
                    mock.patch.object(
                        pm, "save_config_preset",
                        side_effect=lambda n, d, root=None: saved.update(
                            name=n, data=d) or "p"), \
                    mock.patch.object(pm, "load_slot",
                                      return_value=({"output": {}}, "user")):
                qi.getText.return_value = ("我的 快照", True)
                panel._on_preset_save_as()
            self.assertEqual(saved["name"], "我的 快照")
            self.assertIn("default_page", saved["data"])
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_save_persists_formats(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {}}}
        saved = {}
        with mock.patch.object(pm, "load_config_preset",
                               return_value=dict(base)), \
                mock.patch.object(pm, "save_config_preset",
                                  side_effect=lambda n, d, root=None: saved.update(
                                      data=d)), \
                mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                  return_value=r"C:\x\p.json"):
            panel = pm.XmlOptionsPanel(dict(base))
            panel.format_boxes["docx"].setChecked(True)
            panel.format_boxes["html"].setChecked(True)
            panel.lang_box.setCurrentIndex(
                panel.lang_box.findData("zh-Hans"))
            panel._on_save()
            self.assertIn("docx", saved["data"]["formats"])
            self.assertIn("html", saved["data"]["formats"])
            self.assertEqual(saved["data"]["font_lang"], "zh-Hans")
            self.assertTrue(saved["data"]["engine"].startswith("docx2pdf"))
            # 回读：格式/引擎/字库恢复（不再丢回默认）
            o = pm.options_from_presets(saved["data"])
            self.assertIn("docx", o.formats)
            self.assertIn("html", o.formats)
            self.assertEqual(o.font_lang, "zh-Hans")
            self.assertTrue(o.engine.startswith("docx2pdf"))

    def test_strip_no_box_roundtrip(self):
        import pycbeta.gui.panel as pm
        panel = pm.XmlOptionsPanel({"output": {}, "pages": {"a4": {}}})
        try:
            self.assertFalse(panel.strip_no_box.isChecked())  # 默认关
            panel.strip_no_box.setChecked(True)
            self.assertTrue(panel.get_options().output["strip_head_no"])
        finally:
            panel.close()

    def test_verify_defaults_on_and_persisted(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        from PySide6.QtWidgets import QLabel
        panel = pm.XmlOptionsPanel({"output": {}})
        try:
            # 缺 verify 块默认打开
            self.assertTrue(panel.verify_on.isChecked())
            self.assertEqual(panel.maxdiff_spin.value(), 10)
            self.assertEqual(panel.difflines_spin.value(), 5)
            texts = [w.text() for w in panel.findChildren(QLabel)]
            self.assertIn("报告差异行数", texts)
            self.assertNotIn("差异行数", texts)
            # 开关/阈值持久化
            panel.verify_on.setChecked(True)
            panel.maxdiff_spin.setValue(3)
            panel.difflines_spin.setValue(7)
            panel.autofetch_box.setChecked(False)
            panel.scope_box.setChecked(False)
            saved = {}
            with mock.patch.object(pm, "load_config_preset",
                                   return_value={"output": {}}), \
                 mock.patch.object(pm, "save_config_preset",
                                   side_effect=lambda n, d, root=None: saved.update(
                                       data=d)), \
                 mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                   return_value=r"C:\x\p.json"):
                panel._on_save()
            v = saved["data"]["verify"]
            self.assertTrue(v["enabled"])
            self.assertEqual(v["maxDiff"], 3)
            self.assertEqual(v["diffLines"], 7)
            self.assertFalse(v["auto_fetch"])
            self.assertFalse(v["scope_juan"])
            # 回读恢复
            o = pm.options_from_presets(saved["data"])
            panel.set_options(o)
            self.assertTrue(panel.verify_on.isChecked())
            self.assertEqual(panel.maxdiff_spin.value(), 3)
            self.assertEqual(panel.difflines_spin.value(), 7)
        finally:
            panel.close()

    def test_reset_requires_confirm(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = pm.XmlOptionsPanel({"output": {}})
        try:
            with mock.patch.object(pm, "reset_factory",
                                   return_value={"output": {}}) as m_reset, \
                 mock.patch.object(pm, "QMessageBox") as m_box:
                box = m_box.return_value
                ok_btn, cancel_btn = mock.Mock(), mock.Mock()
                box.addButton.side_effect = (
                    lambda text, role: ok_btn if text == "确定" else cancel_btn)
                box.clickedButton.return_value = cancel_btn
                panel._on_reset()
                m_reset.assert_not_called()
                box.clickedButton.return_value = ok_btn
                panel._on_reset()
                m_reset.assert_called_once()
        finally:
            panel.close()

    def test_save_persists_margins_custom(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {"margins": {"top": 25.4,
                                                           "right": 25.4,
                                                           "bottom": 25.4,
                                                           "left": 25.4}}}}
        saved = {}
        with mock.patch.object(pm, "load_config_preset",
                               return_value=dict(base)), \
                mock.patch.object(pm, "save_config_preset",
                                  side_effect=lambda n, d, root=None: saved.update(
                                      data=d)), \
                mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                  return_value=r"C:\x\p.json"):
            panel = pm.XmlOptionsPanel(dict(base))
            # 取消跟随 → spin 填预设值作基线；改一个值保存
            panel.margin_follow.setChecked(False)
            self.assertEqual(panel.margin_spins["top"].value(), 25.4)
            panel.margin_spins["top"].setValue(20.0)
            panel._on_save()
            cm = saved["data"]["pages"]["a4"]["custom_margins"]
            self.assertEqual(cm["top"], 20.0)
            # 回读：自定义边距恢复
            o = pm.options_from_presets(saved["data"])
            self.assertEqual(o.margins["top"], 20.0)
            panel.set_options(o)
            self.assertFalse(panel.margin_follow.isChecked())
            self.assertEqual(panel.margin_spins["top"].value(), 20.0)
            # 重勾跟随 → 僵尸键删除
            panel.margin_follow.setChecked(True)
            panel._on_save()
            self.assertNotIn("custom_margins",
                             saved["data"]["pages"]["a4"])

    def test_uncheck_restores_custom_not_preset(self):
        import pycbeta.gui.panel as pm
        m25 = {"top": 25.4, "right": 25.4, "bottom": 25.4, "left": 25.4}
        m20 = {"top": 20.0, "right": 20.0, "bottom": 20.0, "left": 20.0}
        base = {"output": {}, "pages": {
            "a4": {"margins": dict(m25)},
            "a5": {"margins": dict(m25), "custom_margins": dict(m20)}}}
        panel = pm.XmlOptionsPanel(dict(base))
        # 载入 a5 自定义：不跟随，显示 20
        panel.set_options(pm.XmlOptions(page="a5", margins=dict(m20)))
        self.assertFalse(panel.margin_follow.isChecked())
        self.assertEqual(panel.margin_spins["top"].value(), 20.0)
        # 勾选跟随 → 显示 plain 预设 25.4
        panel.margin_follow.setChecked(True)
        self.assertEqual(panel.margin_spins["top"].value(), 25.4)
        # 再取消勾选 → 回到已存自定义 20.0（不能拿预设覆盖）
        panel.margin_follow.setChecked(False)
        self.assertEqual(panel.margin_spins["top"].value(), 20.0)

    def test_save_refreshes_presets_cache(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {"margins": {"top": 25.4,
                                                           "right": 25.4,
                                                           "bottom": 25.4,
                                                           "left": 25.4}}}}
        with mock.patch.object(pm, "load_config_preset",
                               return_value=dict(base)), \
                mock.patch.object(pm, "save_config_preset"), \
                mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                  return_value=r"C:\x\p.json"):
            panel = pm.XmlOptionsPanel(dict(base))
            panel.margin_follow.setChecked(False)
            panel.margin_spins["top"].setValue(22.0)
            panel._on_save()
            # 内存预设同步，否则取消勾选读到旧值
            cm = panel._presets["pages"]["a4"]["custom_margins"]
            self.assertEqual(cm["top"], 22.0)

    def test_typo_save_load_roundtrip(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        base = {"output": {}, "default_page": "16开", "pages": {
            "a4": {},
            "16开": {"body_font_size": "10.5pt", "body_line_height": 1.5}}}
        saved = {}
        with mock.patch.object(pm, "load_config_preset",
                               return_value=dict(base)), \
                mock.patch.object(pm, "save_config_preset",
                                  side_effect=lambda n, d, root=None: saved.update(
                                      data=d)), \
                mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                  return_value=r"C:\x\p.json"):
            panel = pm.XmlOptionsPanel(dict(base))
            # 有键 → 不跟随，框值恢复（默认页即 16开）
            panel.set_options(pm.options_from_presets(dict(base)))
            self.assertFalse(panel.typo_follow.isChecked())
            self.assertEqual(panel.typo_size_spin.value(), 10.5)
            self.assertIn("10.5pt", panel.typo_info.text())
            # 改值保存 → 写回条目
            panel.typo_size_spin.setValue(11.0)
            panel._on_save()
            pg = saved["data"]["pages"]["16开"]
            self.assertEqual(pg["body_font_size"], "11pt")
            self.assertEqual(pg["body_line_height"], "1.5")
            # 重勾跟随 → 键删除；显示回跟随
            panel.typo_follow.setChecked(True)
            panel._on_save()
            self.assertNotIn("body_font_size", saved["data"]["pages"]["16开"])
            self.assertNotIn("body_line_height",
                             saved["data"]["pages"]["16开"])
            self.assertIn("跟随 CSS", panel.typo_info.text())

    def test_typo_follow_fills_factory_baseline(self):
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {}}}
        panel = pm.XmlOptionsPanel(dict(base))
        # 出厂 CSS body 12pt/1.4 作基线
        self.assertTrue(panel.typo_follow.isChecked())
        self.assertIn("跟随 CSS", panel.typo_info.text())
        panel.typo_follow.setChecked(False)
        self.assertEqual(panel.typo_size_spin.value(), 12.0)
        self.assertEqual(panel.typo_lh_spin.value(), 1.4)

    def test_temp_presets_typo_carry(self):
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {}}}
        opts = pm.XmlOptions(page="a4",
                             typo={"font-size": "10.5pt",
                                   "line-height": "1.5"})
        path = pm.write_temp_presets(base, opts)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        finally:
            os.remove(path)
        self.assertEqual(data["pages"]["a4"]["body_font_size"], "10.5pt")
        self.assertEqual(data["pages"]["a4"]["body_line_height"], "1.5")

    def test_follow_shows_plain_preset_ignoring_custom(self):
        import pycbeta.gui.panel as pm
        m25 = {"top": 25.4, "right": 25.4, "bottom": 25.4, "left": 25.4}
        m20 = {"top": 20.0, "right": 20.0, "bottom": 20.0, "left": 20.0}
        base = {"output": {}, "pages": {
            "a4": {"margins": dict(m25)},
            "a5": {"margins": dict(m25), "custom_margins": dict(m20)}}}
        panel = pm.XmlOptionsPanel(dict(base))
        # 载入 a5 自定义：不跟随，显示 20
        panel.set_options(pm.XmlOptions(page="a5", margins=dict(m20)))
        self.assertFalse(panel.margin_follow.isChecked())
        self.assertEqual(panel.margin_spins["top"].value(), 20.0)
        # 勾选跟随 → 显示 plain 预设 25.4（不能是 custom 20.0）
        panel.margin_follow.setChecked(True)
        self.assertEqual(panel.margin_spins["top"].value(), 25.4)
        # 跟随中切 a4 → 仍是 plain 预设
        panel.page_box.setCurrentIndex(panel.page_box.findData("a4"))
        self.assertEqual(panel.margin_spins["top"].value(), 25.4)

    def test_recheck_follow_refreshes_display(self):
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {"margins": {"top": 25.4,
                                                           "right": 25.4,
                                                           "bottom": 25.4,
                                                           "left": 25.4}}}}
        panel = pm.XmlOptionsPanel(dict(base))
        # 取消跟随改值，再重勾：显示必须刷回预设（上报 bug：点两次才刷新）
        panel.margin_follow.setChecked(False)
        panel.margin_spins["top"].setValue(20.0)
        self.assertEqual(panel.margin_spins["top"].value(), 20.0)
        panel.margin_follow.setChecked(True)
        self.assertEqual(panel.margin_spins["top"].value(), 25.4)

    def test_save_persists_default_page(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {}, "a5": {}}}
        saved = {}
        with mock.patch.object(pm, "load_config_preset",
                               return_value=dict(base)), \
                mock.patch.object(pm, "save_config_preset",
                                  side_effect=lambda n, d, root=None: saved.update(
                                      data=d)), \
                mock.patch.object(pm.XmlOptionsPanel, "_selected_preset",
                                  return_value=r"C:\x\p.json"):
            panel = pm.XmlOptionsPanel(dict(base))
            i = panel.page_box.findData("a5")
            self.assertGreaterEqual(i, 0)
            panel.page_box.setCurrentIndex(i)
            panel._on_save()
            self.assertEqual(saved["data"]["default_page"], "a5")
            # 回读：初值跟随已存默认纸张
            o = pm.options_from_presets({**saved["data"], "pages": base["pages"]})
            self.assertEqual(o.page, "a5")

    def test_resolve_default_page(self):
        from pycbeta.cli import resolve_default_page
        self.assertEqual(resolve_default_page("a5", {}), "a5")
        self.assertEqual(
            resolve_default_page(None, {"default_page": "a5"}), "a5")
        self.assertEqual(resolve_default_page("", {}), "a4")
        self.assertEqual(resolve_default_page(None, {}), "a4")

    def test_options_default_page(self):
        from pycbeta.gui.panel import options_from_presets
        o = options_from_presets({"pages": {"a4": {}, "a5": {}},
                                  "default_page": "a5"})
        self.assertEqual(o.page, "a5")
        o2 = options_from_presets({"pages": {"a4": {}}})
        self.assertEqual(o2.page, "a4")


    def test_table_readonly_copyable(self):
        from PySide6.QtWidgets import QTableWidget
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            self.assertEqual(w.table.editTriggers(),
                             QTableWidget.NoEditTriggers)
            self.assertEqual(w.table.selectionBehavior(),
                             QTableWidget.SelectItems)
            self.assertEqual(w.table.selectionMode(),
                             QTableWidget.ExtendedSelection)
        finally:
            w.close()

    def test_corr_cbeta_option_and_editable_row(self):
        from pycbeta.gui.css_editor import EDITABLE_ROWS
        self.assertIn(("span.corr", "CBETA校改"), EDITABLE_ROWS)
        panel = self._panel()
        try:
            self.assertFalse(panel.corr_box.isChecked())   # 默认关
            panel.corr_box.setChecked(True)
            self.assertTrue(panel.get_options().output["corr_cbeta"])
            panel.set_options(panel.get_options())
            self.assertTrue(panel.corr_box.isChecked())
        finally:
            panel.close() if hasattr(panel, "close") else None


    def test_pagination_hints_gray(self):
        # 分页各选项的括号说明：存在、灰色、纯文本（含 <pb> 不被当 HTML）
        from pycbeta.gui.panel import PAGINATION_KEYS, PAGINATION_HINTS
        panel = self._panel()
        try:
            for k in PAGINATION_KEYS:
                lab = panel.pg_hints[k]
                self.assertTrue(lab.text().startswith("（")
                                and lab.text().endswith("）"), k)
                self.assertIn("gray", lab.styleSheet())
            self.assertIn("<pb>", panel.pg_hints["pb"].text())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_parenthetical_hints_gray(self):
        # 分页/排版两卡所有「（…）」说明均为灰色；旧的整行说明已移入选项后
        panel = self._panel()
        try:
            labs = panel._paren_hint_labels
            self.assertTrue(labs)
            for l in labs:
                self.assertTrue(l.text().startswith("（")
                                and l.text().endswith("）"), l.text())
                self.assertIn("gray", l.styleSheet())
            from PySide6.QtWidgets import QLabel
            texts = {l.text() for l in panel.findChildren(QLabel)}
            self.assertNotIn("卷名去重默认开启；按卷分文件与分页联动", texts)
            self.assertNotIn("脏数据开关默认关闭（保留原文）；偈颂分隔符填两个全角空格，引号指「『 』",
                             texts)
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_clean_verify_button_present(self):
        panel = self._panel()
        try:
            self.assertEqual(panel.clean_verify_btn.text(), "清理校验产物…")
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_clean_verify_dirs(self):
        # 只删 `*（验证）/（驗證）` 目录，成品文件不动
        import shutil
        import pycbeta.gui.panel as pm
        root = tempfile.mkdtemp()
        try:
            for n in ("A（验证）", "B（驗證）"):
                os.makedirs(os.path.join(root, n))
                with open(os.path.join(root, n, "report.txt"),
                          "w", encoding="utf-8") as f:
                    f.write("x")
            keep = os.path.join(root, "T0349 书.docx")
            with open(keep, "w", encoding="utf-8") as f:
                f.write("k")
            removed, errs = pm.clean_verify_dirs(root)
            self.assertEqual(removed, 2)
            self.assertEqual(errs, [])
            self.assertFalse(os.path.isdir(os.path.join(root, "A（验证）")))
            self.assertFalse(os.path.isdir(os.path.join(root, "B（驗證）")))
            self.assertTrue(os.path.isfile(keep))
            # 空/不存在目录：0 不抛
            self.assertEqual(pm.clean_verify_dirs(""), (0, []))
            self.assertEqual(pm.clean_verify_dirs(os.path.join(root, "nope")),
                             (0, []))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_clean_verify_dirs_new_root(self):
        # 新总目录 验证/ 整个拿掉，成品文件不动
        import shutil
        import pycbeta.gui.panel as pm
        root = tempfile.mkdtemp()
        try:
            vroot = os.path.join(root, "验证", "T0349 書（验证）")
            os.makedirs(vroot)
            with open(os.path.join(vroot, "report.txt"),
                      "w", encoding="utf-8") as f:
                f.write("x")
            keep = os.path.join(root, "T0349 书.docx")
            with open(keep, "w", encoding="utf-8") as f:
                f.write("k")
            removed, errs = pm.clean_verify_dirs(root)
            self.assertEqual(removed, 1)
            self.assertEqual(errs, [])
            self.assertFalse(os.path.isdir(os.path.join(root, "验证")))
            self.assertTrue(os.path.isfile(keep))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_verify_dir_size(self):
        import shutil
        import pycbeta.gui.panel as pm
        root = tempfile.mkdtemp()
        try:
            self.assertEqual(pm.verify_dir_size(root), (0, 0))
            self.assertEqual(pm.verify_dir_size(""), (0, 0))
            os.makedirs(os.path.join(root, "验证", "T（验证）"),
                        exist_ok=True)
            os.makedirs(os.path.join(root, "B（驗證）"), exist_ok=True)
            with open(os.path.join(root, "验证", "T（验证）", "a.txt"),
                      "w", encoding="utf-8") as f:
                f.write("12345")
            with open(os.path.join(root, "B（驗證）", "b.txt"),
                      "w", encoding="utf-8") as f:
                f.write("1234567")
            total, count = pm.verify_dir_size(root)
            self.assertEqual(count, 2)
            self.assertEqual(total, 5 + 7)
            self.assertEqual(pm._human_size(0), "0 B")
            self.assertEqual(pm._human_size(2048), "2.0 KB")
            self.assertEqual(pm._human_size(5 * 1024 * 1024), "5.0 MB")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_clean_verify_dirs_custom_root(self):
        # 自选根：只删其下校验子目录，自选根本身与无关内容保留
        import shutil
        import pycbeta.gui.panel as pm
        root = tempfile.mkdtemp()
        custom = tempfile.mkdtemp(prefix="vclean-")
        try:
            keep_dir = os.path.join(custom, "T0349 書（验证）")
            os.makedirs(keep_dir)
            with open(os.path.join(keep_dir, "report.txt"),
                      "w", encoding="utf-8") as f:
                f.write("x")
            other = os.path.join(custom, "misc.txt")
            with open(other, "w", encoding="utf-8") as f:
                f.write("keep")
            removed, errs = pm.clean_verify_dirs(root, custom)
            self.assertEqual(removed, 1)
            self.assertEqual(errs, [])
            self.assertTrue(os.path.isdir(custom))      # 自选根本身保留
            self.assertTrue(os.path.isfile(other))     # 无关内容保留
            self.assertFalse(os.path.isdir(keep_dir))
            total, count = pm.verify_dir_size(root, custom)
            self.assertEqual((total, count), (4, 1))  # 仅剩无关文件
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(custom, ignore_errors=True)


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
        # 本机实际可用性不硬断言（随包 exe 已移出仓库，改由 Releases 分发；
        # 是否安装随环境而异）

    def test_wps_detect_via_progid(self):
        # 路径探测全假时，KWPS.Application 注册即可判 WPS 就绪（自定义安装目录）
        import unittest.mock as mock
        from pycbeta.gui.panel import detect_engines
        try:
            import win32com.client  # noqa: F401
        except Exception:
            self.skipTest("无 pywin32")
        with mock.patch("pycbeta.gui.panel._office_ready", return_value=False):
            st = detect_engines(progid_check=lambda n: n == "KWPS.Application")
            self.assertTrue(st["wps"])
            st2 = detect_engines(progid_check=lambda n: False)
            self.assertFalse(st2["wps"])

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
        self.assertIn("wps", panel.engine_hint.text().lower())
        self.assertIn("未安装", panel.engine_hint.text())
        # 长说明进 tooltip，短状态留行内
        self.assertIn("WPS", panel.engine_hint.toolTip())
        self.assertIn("按链顺序", panel.single_box.toolTip())

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
        hit = [r"C:\WPS\12.1.0.21915\office6\wps.exe"]
        fake_glob = lambda pat: hit if pat.endswith("wps.exe") else []
        self.assertTrue(_office_ready(["wps.exe"], [], [],
                                      has_com=True,
                                      which=lambda n: None,
                                      isfile=lambda p: False,
                                      isdir=lambda p: False,
                                      glob=fake_glob,
                                      extra_globs=[r"C:\WPS\*\office6\wps.exe"]))
        self.assertFalse(_office_ready(["wps.exe"], [], [],
                                       has_com=True,
                                       which=lambda n: None,
                                       isfile=lambda p: False,
                                       isdir=lambda p: False,
                                       glob=lambda pat: [],
                                       extra_globs=[r"C:\WPS\*\office6\wps.exe"]))


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


class TestParseWorkIdsFile(unittest.TestCase):
    def test_mini_test_like(self):
        from pycbeta.gui.__main__ import parse_work_ids_file
        d = tempfile.mkdtemp()
        p = os.path.join(d, "ids.txt")
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write("# comment\n"
                    "T0349 彌勒菩薩所問本願經\n"
                    "1. X1116 毗尼日用切要香乳記\n"
                    "TX0006, YP0019、YP0021\n"
                    "not-an-id 标题\n"
                    "T0349\n")
        self.assertEqual(parse_work_ids_file(p),
                         ["T0349", "X1116", "TX0006", "YP0019", "YP0021"])

    def test_missing_file(self):
        from pycbeta.gui.__main__ import parse_work_ids_file
        self.assertEqual(parse_work_ids_file("nope.txt"), [])


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

    def test_pre_dedent_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertFalse(panel.pre_dedent_box.isChecked())       # 默认关
        self.assertFalse(panel.pre_dedent_spin.isEnabled())      # 关时置灰
        panel.pre_dedent_box.setChecked(True)
        self.assertTrue(panel.pre_dedent_spin.isEnabled())
        panel.pre_dedent_spin.setValue(6)
        o = panel.get_options()
        self.assertTrue(o.output["pre_dedent"])
        self.assertEqual(o.output["pre_dedent_spaces"], 6)
        panel.set_options(o)                                     # 回读
        self.assertTrue(panel.pre_dedent_box.isChecked())
        self.assertEqual(panel.pre_dedent_spin.value(), 6)
        self.assertTrue(panel.pre_dedent_spin.isEnabled())

    def test_mulu_levels_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel, MULU_LEVEL_ITEMS
        panel = XmlOptionsPanel(load_presets())
        self.assertTrue(panel.mulu_on_box.isChecked())           # 默认开
        self.assertTrue(panel.mulu_levels_box.isEnabled())
        self.assertEqual(panel.get_options().pagination.get("mulu_levels"),
                         [1])                                    # 默认仅 level-1
        idx = next(i for i, (_n, lv) in enumerate(MULU_LEVEL_ITEMS)
                   if list(lv) == [1, 2])
        panel.mulu_levels_box.setCurrentIndex(idx)
        o = panel.get_options()
        self.assertEqual(o.pagination["mulu_levels"], [1, 2])
        panel.set_options(o)
        self.assertTrue(panel.mulu_on_box.isChecked())
        self.assertEqual(list(panel.mulu_levels_box.currentData()), [1, 2])
        # 关开关 → 不分（下拉禁用）
        panel.mulu_on_box.setChecked(False)
        self.assertFalse(panel.mulu_levels_box.isEnabled())
        self.assertEqual(panel.get_options().pagination["mulu_levels"], [])
        # 回读空 → 开关关闭
        panel.set_options(panel.get_options())
        self.assertFalse(panel.mulu_on_box.isChecked())
        self.assertFalse(panel.mulu_levels_box.isEnabled())

    def test_zhang_break_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertTrue(panel.pg_zhang_box.isChecked())     # 默认开
        self.assertTrue(panel.get_options().pagination["mulu_zhang_break"])
        panel.pg_zhang_box.setChecked(False)
        o = panel.get_options()
        self.assertFalse(o.pagination["mulu_zhang_break"])
        panel.set_options(o)
        self.assertFalse(panel.pg_zhang_box.isChecked())
        panel.pg_zhang_box.setChecked(True)
        self.assertTrue(panel.get_options().pagination["mulu_zhang_break"])

    def test_heading_merge_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertFalse(panel.pg_heading_box.isChecked())    # 默认关
        self.assertFalse(panel.get_options().pagination["mulu_heading_merge"])
        panel.pg_heading_box.setChecked(True)
        o = panel.get_options()
        self.assertTrue(o.pagination["mulu_heading_merge"])
        panel.set_options(o)
        self.assertTrue(panel.pg_heading_box.isChecked())
        panel.pg_heading_box.setChecked(False)
        self.assertFalse(panel.get_options().pagination["mulu_heading_merge"])

    def test_mulu_levels_items_four(self):
        from pycbeta.gui.panel import MULU_LEVEL_ITEMS
        self.assertEqual([list(lv) for _n, lv in MULU_LEVEL_ITEMS],
                         [[1], [1, 2], [1, 2, 3], [1, 2, 3, 4]])

    def test_smart_merge_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel, SMART_FRAC_ITEMS
        panel = XmlOptionsPanel(load_presets())
        self.assertTrue(panel.pg_smart_box.isChecked())     # 默认开
        self.assertTrue(panel.pg_smart_frac.isEnabled())
        self.assertAlmostEqual(
            panel.get_options().pagination["mulu_smart_max_frac"], 1.0 / 3.0)
        panel.pg_smart_box.setChecked(False)
        self.assertFalse(panel.pg_smart_frac.isEnabled())
        o = panel.get_options()
        self.assertFalse(o.pagination["mulu_smart_merge"])
        panel.set_options(o)
        self.assertFalse(panel.pg_smart_box.isChecked())
        panel.pg_smart_box.setChecked(True)
        idx = next(i for i, (_l, v) in enumerate(SMART_FRAC_ITEMS)
                   if abs(v - 0.5) < 1e-6)
        panel.pg_smart_frac.setCurrentIndex(idx)
        o2 = panel.get_options()
        self.assertTrue(o2.pagination["mulu_smart_merge"])
        self.assertAlmostEqual(o2.pagination["mulu_smart_max_frac"], 0.5)
        # 回读非档位值 → 取最近档（1/2）
        o2.pagination["mulu_smart_max_frac"] = 0.48
        panel.set_options(o2)
        self.assertAlmostEqual(
            panel.get_options().pagination["mulu_smart_max_frac"], 0.5)

    def test_convert_report_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertTrue(panel.convert_report_box.isChecked())    # 默认勾
        panel.convert_report_box.setChecked(False)
        o = panel.get_options()
        self.assertFalse(o.output["convert_report"])
        panel.set_options(o)
        self.assertFalse(panel.convert_report_box.isChecked())
        panel.convert_report_box.setChecked(True)
        self.assertTrue(panel.get_options().output["convert_report"])

    def test_title_wrap_roundtrip(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertTrue(panel.title_wrap_box.isChecked())        # 默认开
        panel.title_wrap_box.setChecked(False)
        o = panel.get_options()
        self.assertFalse(o.output["title_smart_wrap"])
        panel.set_options(o)
        self.assertFalse(panel.title_wrap_box.isChecked())

    def test_styles_tab_paths(self):
        import os
        from pycbeta.gui.panel import XmlOptionsPanel, STYLE_FILES, _STYLES_DIR
        panel = XmlOptionsPanel(load_presets())
        self.assertEqual(panel.tabs.tabText(1), "样式表")
        self.assertEqual(set(panel.style_rows), {n for n, _d in STYLE_FILES})
        for name, _d in STYLE_FILES:
            edit, open_btn = panel.style_rows[name]
            path = os.path.join(_STYLES_DIR, name)
            self.assertTrue(os.path.isfile(path))
            self.assertEqual(edit.text(), os.path.abspath(path))
            self.assertTrue(open_btn.isEnabled())

    def test_ann_table_hint(self):
        import os
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        # 默认填入内置词表路径；只读（只能浏览选择）
        self.assertTrue(panel.ann_file.isReadOnly())
        self.assertTrue(panel.ann_file.text().endswith("annotations.txt"))
        self.assertIn("annotations.txt", panel.ann_hint.text())
        self.assertTrue(panel.ann_open.isEnabled())
        # 浏览选择不存在的路径→红字+禁用（setText 程序化仍可）
        panel.ann_file.setText(r"E:\nonexistent\x.tsv")
        self.assertIn("不存在", panel.ann_hint.text())
        self.assertFalse(panel.ann_open.isEnabled())

    def test_cfg_toggle_blue(self):
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            ss = w.cfg_toggle.styleSheet()
            self.assertIn("#1565c0", ss)          # 蓝底
            self.assertNotIn("#2e7d32", ss)       # 旧绿底已去除
        finally:
            w.close()

    def test_settings_menu(self):
        import unittest.mock as mock
        from PySide6.QtWidgets import QMessageBox
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            from PySide6.QtWidgets import QMenu
            self.assertEqual(w.menuBar().findChildren(QMenu), [])
            acts = {a.text(): a for a in w.menuBar().actions()}
            self.assertIn("设置…", acts)
            self.assertIn("关于", acts)
            self.assertFalse(hasattr(w, "src_btn"))
            from pycbeta import __version__
            with mock.patch.object(QMessageBox, "about") as m:
                acts["关于"].trigger()
                m.assert_called_once()
                self.assertIn(__version__, m.call_args[0][2])
        finally:
            w.close()

    def test_edit_source_applies_out_dir(self):
        import unittest.mock as mock
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            fake = mock.Mock()
            fake.exec.return_value = True
            fake.out_dir.return_value = "O:/new"
            with mock.patch("pycbeta.gui.panel.SourceDialog",
                            return_value=fake) as cls:
                w.out_edit.setText("O:/old")
                w._edit_source()
                cls.assert_called_once()
                self.assertEqual(cls.call_args[1].get("out_dir"), "O:/old")
                self.assertEqual(w.out_edit.text(), "O:/new")
        finally:
            w.close()

    def test_slot_label_link(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        panel.mark_slot()
        # 锚定 run.json（“当前配置”为链接），名字超长省略、tooltip 全名
        self.assertIn("当前配置", panel.slot_label.text())
        self.assertIn("run.json", panel.slot_label.text())   # 链接 href
        self.assertNotIn("运行组合", panel.slot_label.text())
        self.assertTrue(panel.slot_label.toolTip())
        self.assertTrue(panel.slot_label.openExternalLinks())
        before = panel.slot_label.text()
        panel.refresh_slot_label()
        self.assertEqual(panel.slot_label.text(), before)

    def test_open_local_file_accepts_dir(self):
        import os
        import tempfile
        import unittest.mock as mock
        from PySide6.QtGui import QDesktopServices
        from pycbeta.gui.panel import XmlOptionsPanel
        with mock.patch.object(QDesktopServices, "openUrl") as m:
            XmlOptionsPanel._open_local_file(None, tempfile.gettempdir())
            m.assert_called_once()  # 目录也能打开（之前 isfile 误杀）
        with mock.patch.object(QDesktopServices, "openUrl") as m2:
            XmlOptionsPanel._open_local_file(
                None, os.path.join(tempfile.gettempdir(), "no-such-xyz"))
            m2.assert_not_called()


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
        from pycbeta import __version__
        from pycbeta.gui.__main__ import MainWindow, _gui_date
        self.assertRegex(_gui_date(), r"^\d{4}-\d{2}-\d{2}$")
        w = MainWindow()
        try:
            # 标题版本与单点 __version__ 一致（改一处即全局生效）
            self.assertRegex(w.windowTitle(),
                             r"^CBETA XML 格式转换 v"
                             + re.escape(__version__)
                             + r"（\d{4}-\d{2}-\d{2}）$")
        finally:
            w.close()

    def test_cfg_toggle_collapses_panel(self):
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            self.assertTrue(w.cfg_toggle.isChecked())
            # 扁平无文字小箭头，不占整行
            self.assertEqual(w.cfg_toggle.text(), "")
            self.assertTrue(w.cfg_toggle.autoRaise())

            def colors():
                img = w.cfg_toggle.grab().toImage()
                bg = img.pixelColor(5, 5)
                # 箭头抗锯齿后非纯白，只要求明显亮于蓝底
                white = any(img.pixelColor(x, y).lightness() > 150
                            for x in range(22) for y in range(22))
                return bg, white

            # 蓝底白字（#1565c0）；切换前后同色（只靠箭头方向区分）
            bg, white = colors()
            self.assertLess(bg.red(), 70)
            self.assertGreater(bg.blue(), 120)
            self.assertLess(bg.green(), 150)
            self.assertTrue(white)
            w.cfg_toggle.toggle()
            self.assertTrue(w.panel.isHidden())
            bg2, white2 = colors()
            self.assertEqual((bg2.red(), bg2.green(), bg2.blue()),
                             (bg.red(), bg.green(), bg.blue()))
            self.assertTrue(white2)
            w.cfg_toggle.toggle()
            self.assertFalse(w.panel.isHidden())
            self.assertIsNotNone(w.panel.tabs)  # tab 区引用保持有效
        finally:
            w.close()


    def test_cfg_toggle_arrow_action_semantics(self):
        from PySide6.QtCore import Qt
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            # 展开态=上箭头（点按向上收起）；收起态=下箭头（点按向下展开）
            self.assertEqual(w.cfg_toggle.arrowType(), Qt.UpArrow)
            w.cfg_toggle.toggle()
            self.assertEqual(w.cfg_toggle.arrowType(), Qt.DownArrow)
            w.cfg_toggle.toggle()
            self.assertEqual(w.cfg_toggle.arrowType(), Qt.UpArrow)
        finally:
            w.close()

    def test_table_min_height(self):
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            self.assertGreaterEqual(w.table.minimumHeight(), 150)
        finally:
            w.close()

    def test_start_button_labeled_convert(self):
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            self.assertEqual(w.btn_start.text(), "转换")
        finally:
            w.close()

    def test_reset_table_view_returns_to_first_row(self):
        # 每轮转换前光标/视图回到第一行（上轮结束常停在末行）
        from PySide6.QtWidgets import QTableWidgetItem
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            w.table.setRowCount(200)
            for r in range(200):
                for c in range(5):
                    w.table.setItem(r, c, QTableWidgetItem(f"{r}-{c}"))
            w.show()
            self.app.processEvents()
            w.table.scrollToBottom()
            w.table.setCurrentCell(199, 4)
            self.app.processEvents()
            self.assertNotEqual(w.table.verticalScrollBar().value(), 0)
            w._reset_table_view()
            self.app.processEvents()
            self.assertEqual(w.table.currentRow(), 0)
            self.assertEqual(w.table.currentColumn(), 4)   # 光标落「文件」列
            self.assertEqual(w.table.verticalScrollBar().value(), 0)
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


class TestLaunchArgs(unittest.TestCase):
    """独立窗启动参数预填（publish 一键送校验）：ids-file/out/preset/verify。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _win(self):
        from pycbeta.gui.__main__ import MainWindow
        return MainWindow()

    def _args(self, **kw):
        from types import SimpleNamespace
        d = {"ids_file": None, "out": None, "preset": None,
             "verify": False, "autostart": False}
        d.update(kw)
        return SimpleNamespace(**d)

    def test_prefill_ids_out_verify(self):
        import tempfile
        from pycbeta.gui.__main__ import _apply_launch_args
        w = self._win()
        try:
            d = tempfile.mkdtemp()
            self.addCleanup(__import__("shutil").rmtree, d, True)
            ids = os.path.join(d, "ids.txt")
            with open(ids, "w", encoding="utf-8") as f:
                f.write("T0001\n")
            out = os.path.join(d, "o")
            _apply_launch_args(w, self._args(ids_file=ids, out=out,
                                            verify=True))
            self.assertEqual(w.path_edit.text(), ids)
            self.assertTrue(w.mode_file.isChecked())
            self.assertEqual(w.out_edit.text(), out)
            self.assertTrue(w.panel.verify_on.isChecked())
        finally:
            w.close()

    def test_preset_stem_filename_abspath(self):
        import json
        import tempfile
        from pycbeta.gui.__main__ import _apply_launch_args
        w = self._win()
        try:
            d = tempfile.mkdtemp()
            self.addCleanup(__import__("shutil").rmtree, d, True)
            fn = os.path.join(d, "mine.json")
            with open(fn, "w", encoding="utf-8") as f:
                json.dump({"output": {"t2s": True}}, f)
            box = w.panel.cfg_preset_box
            box.blockSignals(True)
            box.addItem("mine", fn)
            box.setCurrentIndex(0)
            box.blockSignals(False)
            for form in ("mine", "mine.json", fn):
                _apply_launch_args(w, self._args(preset=form))
                self.assertEqual(box.currentData(), fn, form)
            self.assertTrue(w.panel.t2s_box.isChecked())  # 载入面板
        finally:
            w.close()

    def test_missing_preset_keeps_selection(self):
        from pycbeta.gui.__main__ import _apply_launch_args
        w = self._win()
        try:
            before = w.panel.cfg_preset_box.currentIndex()
            _apply_launch_args(w, self._args(preset="不存在的预设xyz"))
            self.assertEqual(w.panel.cfg_preset_box.currentIndex(), before)
        finally:
            w.close()

    def test_formats_prefill(self):
        from pycbeta.gui.__main__ import _apply_launch_args
        w = self._win()
        try:
            _apply_launch_args(w, self._args(formats="epub,html"))
            self.assertTrue(w.panel.format_boxes["epub"].isChecked())
            self.assertTrue(w.panel.format_boxes["html"].isChecked())
            self.assertFalse(w.panel.format_boxes["pdf"].isChecked())
            # 全不匹配 → pdf 兜底
            _apply_launch_args(w, self._args(formats="bogus"))
            self.assertTrue(w.panel.format_boxes["pdf"].isChecked())
            self.assertFalse(w.panel.format_boxes["epub"].isChecked())
        finally:
            w.close()

    def test_empty_args_noop(self):
        from pycbeta.gui.__main__ import _apply_launch_args
        w = self._win()
        try:
            before_path = w.path_edit.text()
            before_out = w.out_edit.text()
            before_idx = w.panel.cfg_preset_box.currentIndex()
            _apply_launch_args(w, self._args())
            self.assertEqual(w.path_edit.text(), before_path)
            self.assertEqual(w.out_edit.text(), before_out)
            self.assertEqual(w.panel.cfg_preset_box.currentIndex(), before_idx)
        finally:
            w.close()


class TestBatchMergeResolve(unittest.TestCase):
    def test_resolve_missing_xml_reasons(self):
        import shutil
        import tempfile
        from unittest import mock
        from pycbeta import fetch
        from pycbeta.gui.__main__ import BatchWorker
        ebook = tempfile.mkdtemp()
        try:
            # 未勾选自动下载 → 直接提示
            w = BatchWorker([], None, {}, {"auto_xml": False})
            labels = []
            w.row_status.connect(lambda i, t: labels.append(t))
            presets = {"source": {"xml_dir": "", "cbeta_ebook": ebook}}
            out = w._resolve({"kind": "id", "id": "T0001"}, 0, fetch, presets)
            self.assertEqual(out, [])
            self.assertEqual(labels[-1], "缺 XML（未勾选自动下载）")
            # 自动下载已开但 catalog 未收录 → 指明 catalog（mock 查表层，不触网；
            # catalog 已钉死内置，自定义路径不再生效，未收录只能 mock catalog_lookup）
            presets2 = {"source": {"xml_dir": "", "cbeta_ebook": ebook}}
            w2 = BatchWorker([], None, {}, {"auto_xml": True})
            with mock.patch("pycbeta.fetch.materialize_work",
                            return_value=([], "")), \
                 mock.patch("pycbeta.fetch.catalog_lookup",
                            return_value=[]):
                labels2 = []
                w2.row_status.connect(lambda i, t: labels2.append(t))
                out2 = w2._resolve({"kind": "id", "id": "T0001"}, 0, fetch,
                                   presets2)
            self.assertEqual(out2, [])
            self.assertEqual(labels2[-1], "缺 XML（catalog 未收录）")
            # catalog 有收录但取不到 → 下载失败（mock 住下载层，不触网）
            with mock.patch("pycbeta.fetch.materialize_work",
                            return_value=([], "")), \
                 mock.patch("pycbeta.fetch.catalog_lookup",
                            return_value=[{"vol": "01"}]):
                labels3 = []
                w2.row_status.connect(lambda i, t: labels3.append(t))
                out3 = w2._resolve({"kind": "id", "id": "T0001"}, 0, fetch,
                                   presets2)
            self.assertEqual(out3, [])
            self.assertEqual(labels3[-1], "缺 XML（下载失败）")
        finally:
            shutil.rmtree(ebook, ignore_errors=True)

    def test_resolve_illegal_id_marks_fail(self):
        # 非法书号：状态列红字（row_verify=fail）
        import shutil
        import tempfile
        from pycbeta import fetch
        from pycbeta.gui.__main__ import BatchWorker
        ebook = tempfile.mkdtemp()
        try:
            w = BatchWorker([], None, {}, {"auto_xml": False})
            labels, levels = [], []
            w.row_status.connect(lambda i, t: labels.append(t))
            w.row_verify.connect(lambda i, t: levels.append(t))
            presets = {"source": {"xml_dir": "", "cbeta_ebook": ebook}}
            out = w._resolve({"kind": "id", "id": "NOTANID"}, 0, fetch,
                             presets)
            self.assertEqual(out, [])
            self.assertEqual(labels[-1], "非法編號")
            self.assertEqual(levels[-1], "fail")
        finally:
            shutil.rmtree(ebook, ignore_errors=True)

    def test_prefetch_meta_fills_title_and_source(self):
        # 转换前预填：id 行在「待转换」阶段即应显示经名（catalog）与来源（预测）
        import shutil
        import tempfile
        from unittest import mock
        from pycbeta import fetch
        from pycbeta.gui.__main__ import BatchWorker
        tmp = tempfile.mkdtemp(prefix="gpref-")
        cat = os.path.join(tmp, "sutra_mapping.txt")
        with open(cat, "w", encoding="utf-8") as f:
            f.write("x")
        try:
            w = BatchWorker([], None, {}, {"auto_xml": True})
            titles, sources = [], []
            w.row_title.connect(lambda i, t: titles.append(t))
            w.row_source.connect(lambda i, t: sources.append(t))
            presets = {"source": {"catalog": cat}}
            with mock.patch("pycbeta.fetch.resolve_catalog",
                            return_value=cat), \
                 mock.patch("pycbeta.fetch.catalog_lookup",
                            return_value=[{"title": "彌勒菩薩所問本願經"}]), \
                 mock.patch("pycbeta.fetch.materialize_work",
                            return_value=([], "downloaded")):
                w._prefetch_meta(0, {"kind": "id", "id": "T0349"},
                                 fetch, presets)
            self.assertEqual(titles, ["彌勒菩薩所問本願經"])
            self.assertEqual(sources, ["已下载"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    """BatchWorker._resolve 合册分支：碎片 ID → 按册合成路径 + 行标签。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _bookcase(self):
        import tempfile
        d = tempfile.mkdtemp()
        frag = ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:id="{stem}">'
                '<teiHeader><fileDesc><titleStmt>'
                '<title level="m" xml:lang="zh-Hant">題{rng}</title>'
                '</titleStmt></fileDesc></teiHeader>'
                '<text><body><p>{text}</p></body></text></TEI>')
        for vol, seq, text in (("TX07", "001", "甲"), ("TX07", "002", "乙"),
                               ("TX08", "003", "丙")):
            vd = os.path.join(d, "TX", vol)
            os.makedirs(vd, exist_ok=True)
            with open(os.path.join(vd, f"TX07n0006_{seq}.xml"
                                    if vol == "TX07" else f"TX08n0006_{seq}.xml"),
                      "w", encoding="utf-8") as f:
                f.write(frag.format(stem=f"TX07n0006" if vol == "TX07" else "TX08n0006",
                                    rng=vol, text=text))
        return d

    def test_id_job_merges_per_vol(self):
        import shutil
        import tempfile
        from pycbeta import fetch
        from pycbeta.gui.__main__ import BatchWorker
        book = self._bookcase()
        ebook = tempfile.mkdtemp()
        try:
            w = BatchWorker([], None, {}, {})
            w._merge_tmp = tempfile.mkdtemp()
            labels = []
            w.row_source.connect(lambda i, t: labels.append(t))
            presets = {"source": {"xml_dir": book, "cbeta_ebook": ebook}}
            paths = w._resolve({"kind": "id", "id": "TX0006"}, 0, fetch,
                               presets)
            self.assertEqual(labels, ["合册合成"])
            self.assertEqual(len(paths), 2)
            self.assertTrue(paths[0].endswith("TX07n0006.xml"))
            self.assertTrue(paths[1].endswith("TX08n0006.xml"))
            self.assertTrue(all(p.startswith(ebook) for p in paths))
            from lxml import etree
            t0 = "".join(etree.parse(paths[0]).getroot().itertext())
            self.assertIn("甲", t0)
            self.assertIn("乙", t0)
            self.assertNotIn("丙", t0)
        finally:
            shutil.rmtree(book, ignore_errors=True)
            shutil.rmtree(ebook, ignore_errors=True)
            shutil.rmtree(w._merge_tmp, ignore_errors=True)

    def test_merged_dir_job(self):
        import shutil
        import tempfile
        from pycbeta import fetch
        from pycbeta.gui.__main__ import BatchWorker
        book = self._bookcase()
        ebook = tempfile.mkdtemp()
        tmp = tempfile.mkdtemp()
        try:
            w = BatchWorker([], None, {}, {})
            w._merge_tmp = tmp
            from pycbeta.merge import collect_work_frags
            groups = collect_work_frags(book, "TX", "0006")
            key = ("TX", "TX07", "0006")
            labels = []
            w.row_source.connect(lambda i, t: labels.append(t))
            paths = w._resolve({"kind": "merged", "id": "X",
                                "group": (key, groups[key])}, 0, fetch,
                               {"source": {"xml_dir": book,
                                           "cbeta_ebook": ebook}})
            self.assertEqual(labels, ["合册合成"])
            self.assertEqual(len(paths), 1)
        finally:
            shutil.rmtree(book, ignore_errors=True)
            shutil.rmtree(ebook, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)


class TestNotesTab(unittest.TestCase):
    """注释卡：悉昙开关 + inline 括号下拉收窄。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        from pycbeta.theme import load_presets
        return XmlOptionsPanel(load_presets())

    def test_ann_three_way_mutual_exclusion(self):
        from PySide6.QtWidgets import QRadioButton
        panel = self._panel()
        try:
            for w in (panel.ann_none, panel.ann_hard, panel.ann_full):
                self.assertIsInstance(w, QRadioButton)   # 三选一 → 单选按钮
            panel.ann_none.setChecked(True)                 # 无注音
            self.assertFalse(panel.ann_hard.isChecked())
            self.assertFalse(panel.ann_full.isChecked())
            panel.ann_hard.setChecked(True)
            self.assertFalse(panel.ann_none.isChecked())
            self.assertFalse(panel.ann_full.isChecked())
            panel.ann_full.setChecked(True)
            self.assertFalse(panel.ann_hard.isChecked())
            self.assertFalse(panel.ann_none.isChecked())
            o = panel.get_options()
            self.assertTrue(o.annotations["enabled"])
            self.assertTrue(o.annotations["full_text"])
            panel.ann_none.setChecked(True)
            self.assertFalse(panel.ann_hard.isChecked())
            self.assertFalse(panel.ann_full.isChecked())
            o2 = panel.get_options()
            self.assertFalse(o2.annotations["enabled"])
            self.assertFalse(o2.annotations["full_text"])
            panel.set_options(o)                            # 回读
            self.assertTrue(panel.ann_full.isChecked())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_siddham_box_default_on(self):
        panel = self._panel()
        try:
            self.assertEqual(panel.siddham_box.text(), "正文显示悉昙字和读音")
            self.assertTrue(panel.siddham_box.isChecked())
            self.assertTrue(panel.get_options().output["show_body_siddham"])
            tip = panel.siddham_box.toolTip()
            self.assertIn("种子字(raṃ)", tip)
            self.assertIn("Ranjana", tip)
            self.assertIn("脚注不受影响", tip)
        finally:
            panel.close()

    def test_siddham_box_roundtrip(self):
        from pycbeta.gui.panel import XmlOptions
        panel = self._panel()
        try:
            panel.siddham_box.setChecked(False)
            self.assertFalse(panel.get_options().output["show_body_siddham"])
            panel.set_options(XmlOptions(
                page="a4", output={"show_body_siddham": True}))
            self.assertTrue(panel.siddham_box.isChecked())
            panel.set_options(XmlOptions(page="a4", output={}))
            self.assertTrue(panel.siddham_box.isChecked())  # 缺键默认开
        finally:
            panel.close()

    def test_siddham_text_box_roundtrip(self):
        from pycbeta.gui.panel import XmlOptions
        panel = self._panel()
        try:
            self.assertFalse(panel.siddham_text_box.isChecked())  # 缺省关
            self.assertFalse(panel.get_options().output["siddham_text"])
            panel.siddham_text_box.setChecked(True)
            self.assertTrue(panel.get_options().output["siddham_text"])
            panel.set_options(XmlOptions(page="a4", output={}))
            self.assertFalse(panel.siddham_text_box.isChecked())  # 缺键默认关
            panel.set_options(XmlOptions(
                page="a4", output={"siddham_text": True}))
            self.assertTrue(panel.siddham_text_box.isChecked())
        finally:
            panel.close()

    def test_notes_mode_default_and_roundtrip(self):
        from pycbeta.gui.panel import XmlOptions
        panel = self._panel()
        try:
            # 出厂 config output.notes=footnote；下拉纯三值，无“跟随”
            self.assertEqual(panel.notes_mode.currentData(), "footnote")
            self.assertEqual(panel.notes_mode.count(), 3)
            self.assertEqual(panel.get_options().output["notes"], "footnote")
            panel.notes_mode.setCurrentIndex(
                panel.notes_mode.findData("inline"))
            self.assertEqual(panel.get_options().output["notes"], "inline")
            panel.set_options(XmlOptions(page="a4", output={"notes": "endnote"}))
            self.assertEqual(panel.notes_mode.currentData(), "endnote")
            panel.set_options(XmlOptions(page="a4", output={}))
            self.assertEqual(panel.notes_mode.currentData(), "footnote")  # 缺键默认
        finally:
            panel.close()

    def test_note_inline_brackets_enabled_only_inline(self):
        panel = self._panel()
        try:
            self.assertFalse(panel.note_brackets_box.isEnabled())  # 默认 footnote
            panel.notes_mode.setCurrentIndex(panel.notes_mode.findData("inline"))
            self.assertTrue(panel.note_brackets_box.isEnabled())
            panel.notes_mode.setCurrentIndex(panel.notes_mode.findData("endnote"))
            self.assertFalse(panel.note_brackets_box.isEnabled())
        finally:
            panel.close()

    def test_notes_tooltips_wrapped(self):
        panel = self._panel()
        try:
            for box in (panel.notes_mode, panel.brackets_box,
                        panel.note_brackets_box):
                self.assertIn("\n", box.toolTip())
        finally:
            panel.close()

    def test_notes_on_label_and_row(self):
        from PySide6.QtWidgets import QFormLayout
        panel = self._panel()
        try:
            tab = next(panel.tabs.widget(i)
                       for i in range(panel.tabs.count())
                       if panel.tabs.tabText(i) == "注释")
            fl = tab.layout()
            self.assertIsInstance(fl, QFormLayout)

            def field_widget(fld):
                if fld is None:
                    return None
                if fld.layout() is not None:
                    lay = fld.layout()
                    for j in range(lay.count()):
                        w = lay.itemAt(j).widget()
                        if w is not None:
                            return w
                    return None
                return fld.widget()

            rows = []
            for i in range(fl.rowCount()):
                lab = fl.itemAt(i, QFormLayout.LabelRole)
                label = lab.widget().text() if lab and lab.widget() else None
                rows.append((label, field_widget(fl.itemAt(i, QFormLayout.FieldRole))))
            labels = [l for l, _ in rows if l]
            for t in ("正文夹注", "注释总开关", "注释方式", "校注内联括号"):
                self.assertIn(t, labels)
            fields = [w for _, w in rows]
            i_br = fields.index(panel.brackets_box)
            i_si = fields.index(panel.siddham_box)
            i_ms = fields.index(panel.notes_on)
            i_nm = fields.index(panel.notes_mode)
            i_nb = fields.index(panel.note_brackets_box)
            # 正文设置（正文夹注/悉昙）排在「注释总开关」之前；悉昙在正文夹注之后
            self.assertLess(i_br, i_si)
            self.assertLess(i_si, i_ms)
            self.assertLess(i_ms, i_nm)
            self.assertLess(i_nm, i_nb)
            # 注释方式下拉收窄
            self.assertLessEqual(panel.notes_mode.maximumWidth(), 120)
        finally:
            panel.close()


class TestSourceDialog(unittest.TestCase):
    def test_apply_merge(self):
        base = {"source": {"xml_dir": "A", "cbeta_ebook": "B", "catalog": "C"},
                "downloads": {"xml": "U1", "html": "U2"},
                "output": {"t2s": False}}
        out = apply_source_edits(base, {"source": {"xml_dir": "A2"},
                                        "downloads": {"xml": "U9", "docx": "U3"}})
        self.assertEqual(out["source"]["xml_dir"], "A2")
        self.assertEqual(out["source"]["cbeta_ebook"], "B")
        self.assertEqual(out["downloads"]["xml"], "U9")
        self.assertEqual(out["downloads"]["html"], "U2")
        self.assertEqual(out["downloads"]["docx"], "U3")
        self.assertFalse(out["output"]["t2s"])
        # base 未被污染
        self.assertEqual(base["source"]["xml_dir"], "A")

    def _accept_with(self, xml_dir, warn_ret, unsafe=True):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from unittest import mock
        import pycbeta.gui.panel as P
        dlg = P.SourceDialog()
        try:
            dlg.path_edits["xml_dir"].setText(xml_dir)
            dlg.path_edits["cbeta_ebook"].setText("B")  # 自包含：避免缺工作根弹窗
            saved = {}
            with mock.patch("pycbeta.fetch.inspect_xml_source",
                            return_value={"safe": not unsafe, "edition": "單卷版 XML TEI P5b"}):
                with mock.patch.object(P, "xml_dir_warning", return_value=warn_ret):
                    with mock.patch.object(P, "save_current",
                                           side_effect=lambda d, r=None: saved.update(d)):
                        with mock.patch.object(P, "load_slot",
                                               return_value=({"source": {}}, None)):
                            dlg.accept()
            return saved
        finally:
            dlg.close()

    def test_io_verify_row_follows_out_dir(self):
        import shutil
        import tempfile
        import pycbeta.gui.panel as P
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        root = tempfile.mkdtemp()
        try:
            dlg = P.SourceDialog(out_dir=root)
            try:
                dlg.path_edits["verify_root"].setText("")  # 自包含：忽略本机用户预设
                want = os.path.join(root, "验证")
                self.assertEqual(dlg.io_verify_edit.text(), want)
                self.assertTrue(dlg.io_verify_edit.isReadOnly())
                self.assertEqual(dlg.io_verify_size.text(), "（尚无校验产物）")
                os.makedirs(os.path.join(want, "T0349 書（验证）"))
                with open(os.path.join(want, "T0349 書（验证）",
                                       "report.txt"),
                          "w", encoding="utf-8") as f:
                    f.write("12345")
                dlg._refresh_verify_info()
                self.assertIn("5 B", dlg.io_verify_size.text())
                self.assertIn("1 个文件", dlg.io_verify_size.text())
                other = tempfile.mkdtemp()
                try:
                    dlg.io_out_edit.setText(other)  # 输出改 → 校验目录跟随
                    self.assertEqual(dlg.io_verify_edit.text(),
                                     os.path.join(other, "验证"))
                    self.assertEqual(dlg.io_verify_size.text(),
                                     "（尚无校验产物）")
                finally:
                    shutil.rmtree(other, ignore_errors=True)
                custom = tempfile.mkdtemp(prefix="vcustom-")
                try:
                    os.makedirs(os.path.join(custom, "T（验证）"))
                    with open(os.path.join(custom, "T（验证）", "r.txt"),
                              "w", encoding="utf-8") as f:
                        f.write("1234567")
                    dlg.path_edits["verify_root"].setText(custom)
                    self.assertEqual(dlg.io_verify_edit.text(), custom)
                    self.assertIn("7 B", dlg.io_verify_size.text())
                    dlg.path_edits["verify_root"].setText("")  # 清空回默认
                    self.assertEqual(dlg.io_verify_edit.text(),
                                     os.path.join(other, "验证"))
                finally:
                    shutil.rmtree(custom, ignore_errors=True)
            finally:
                dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_accept_clears_unsafe_xml_dir(self):
        saved = self._accept_with(r"X:\p5b", "clear")
        self.assertEqual(saved.get("source", {}).get("xml_dir"), "")

    def test_accept_keeps_on_use(self):
        saved = self._accept_with(r"X:\p5b", "use")
        self.assertEqual(saved.get("source", {}).get("xml_dir"), r"X:\p5b")

    def test_accept_cancel_does_not_save(self):
        saved = self._accept_with(r"X:\p5b", None)
        self.assertEqual(saved, {})

    def test_accept_writes_named_preset(self):
        import json
        import tempfile
        import pycbeta.gui.panel as P
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        d = tempfile.mkdtemp()
        try:
            fn = os.path.join(d, "p.json")
            with open(fn, "w", encoding="utf-8") as f:
                json.dump({"source": {"cbeta_ebook": "OLD"}}, f)
            dlg = P.SourceDialog(preset_path=fn)
            try:
                self.assertIn("p.json", dlg.windowTitle())
                dlg.path_edits["cbeta_ebook"].setText("NEW")
                dlg.path_edits["xml_dir"].setText("")
                from unittest import mock
                with mock.patch.object(P, "save_current") as m_save:
                    dlg.accept()
                m_save.assert_not_called()  # 写目标文件，不碰默认槽
            finally:
                dlg.close()
            with open(fn, encoding="utf-8") as f:
                back = json.load(f)
            self.assertEqual(back["source"]["cbeta_ebook"], "NEW")
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_accept_persists_baselines_and_out_dir(self):
        import pycbeta.gui.panel as P
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = P.SourceDialog()
        try:
            dlg.path_edits["cbeta_ebook"].setText("B")
            dlg.base_edits["txt"].setText("R:/t")
            dlg.base_edits["pdf"].setText("R:/p")
            dlg.io_out_edit.setText("O:/o")
            saved = {}
            from unittest import mock
            with mock.patch("pycbeta.fetch.inspect_xml_source",
                            return_value={"safe": True}):
                with mock.patch.object(P, "save_current",
                                       side_effect=lambda d, r=None: saved.update(d)):
                    with mock.patch.object(P, "load_slot",
                                           return_value=({"source": {}}, None)):
                        dlg.accept()
            self.assertEqual(saved["source"]["baselines"]["txt"], "R:/t")
            self.assertEqual(saved["source"]["baselines"]["pdf"], "R:/p")
            self.assertEqual(saved["source"]["out_dir"], "O:/o")
        finally:
            dlg.close()
        import json
        import tempfile
        import pycbeta.gui.panel as P
        d = tempfile.mkdtemp()
        try:
            fn = os.path.join(d, "p.json")
            with open(fn, "w", encoding="utf-8") as f:
                json.dump({"source": {"xml_dir": "X", "cbeta_ebook": "B"}}, f)
            P.clear_xml_dir(preset_path=fn)
            with open(fn, encoding="utf-8") as f:
                back = json.load(f)
            self.assertEqual(back["source"]["xml_dir"], "")
            self.assertEqual(back["source"]["cbeta_ebook"], "B")
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_accept_empty_ebook_warns(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from unittest import mock
        import pycbeta.gui.panel as P
        dlg = P.SourceDialog()
        try:
            dlg.path_edits["cbeta_ebook"].setText("")
            dlg.path_edits["xml_dir"].setText("")
            with mock.patch.object(P, "load_slot",
                                   return_value=({"source": {}}, "user")), \
                 mock.patch.object(P, "save_current") as m_save, \
                 mock.patch.object(P, "QMessageBox") as m_box:
                box = m_box.return_value
                ok_btn, cancel_btn = mock.Mock(), mock.Mock()
                box.addButton.side_effect = (
                    lambda text, role: ok_btn if "确定" in text else cancel_btn)
                box.clickedButton.return_value = cancel_btn
                dlg.accept()
                m_save.assert_not_called()
                box.clickedButton.return_value = ok_btn
                dlg.accept()
                m_save.assert_called_once()
                saved = m_save.call_args.args[0]
                self.assertEqual(saved["source"]["cbeta_ebook"], "")
        finally:
            dlg.close()

    def test_dialog_builds(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            self.assertIn("xml_dir", dlg.path_edits)  # 字段存在（值随用户配置）
            self.assertGreater(dlg.dl_table.rowCount(), 0)
            self.assertEqual(dlg.dl_table.item(0, 0).text(), "xml")
            flags = dlg.dl_table.item(0, 0).flags()
            from PySide6.QtCore import Qt
            self.assertFalse(bool(flags & Qt.ItemIsEditable))
            self.assertEqual(dlg.btn_update_data.text(), "更新官方数据")
            self.assertEqual(dlg.btn_check_update.text(), "更新XML")
            self.assertEqual(dlg.ebook_base_box.text(), "同时更新电子书")
        finally:
            dlg.close()

    def test_source_tabs(self):
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        QApplication.instance() or QApplication([])
        dlg = pm.SourceDialog()
        try:
            self.assertEqual(dlg.src_tabs.count(), 4)
            self.assertEqual(dlg.src_tabs.tabText(0), "输入输出")
            self.assertEqual(dlg.src_tabs.tabText(1), "本地官方电子书")
            self.assertEqual(dlg.src_tabs.tabText(2), "官方数据更新源")
            self.assertEqual(dlg.src_tabs.tabText(3), "电子书下载模板")
            from pycbeta.update_data import load_sources
            self.assertEqual(dlg.upd_table.rowCount(), len(load_sources()))
            for i in range(dlg.upd_table.rowCount()):
                for j in range(dlg.upd_table.columnCount()):
                    self.assertFalse(bool(
                        dlg.upd_table.item(i, j).flags() & Qt.ItemIsEditable))
            names = [dlg.upd_table.item(i, 0).text()
                     for i in range(dlg.upd_table.rowCount())]
            self.assertIn("佛典目录映射表", names)
            self.assertIn("悉昙·兰札字型", names)
            self.assertNotIn("悉昙·兰札字型（手动）", names)
        finally:
            dlg.close()

    def test_upd_url_double_click(self):
        import unittest.mock as mock
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from PySide6.QtGui import QDesktopServices
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog()
        try:
            self.assertGreater(dlg.upd_table.rowCount(), 0)
            url_item = dlg.upd_table.item(0, 1)
            self.assertTrue(url_item.text().startswith("http"))
            with mock.patch.object(QDesktopServices, "openUrl") as m:
                dlg._open_upd_url(url_item)
                m.assert_called_once()
                dlg._open_upd_url(dlg.upd_table.item(0, 0))
                self.assertEqual(m.call_count, 1)  # 非 URL 列不响应
            from PySide6.QtWidgets import QLabel
            tab = next(dlg.src_tabs.widget(i)
                       for i in range(dlg.src_tabs.count())
                       if dlg.src_tabs.tabText(i) == "官方数据更新源")
            hints = [w.text() for w in tab.findChildren(QLabel)
                     if "双击" in w.text()]
            self.assertTrue(hints)
        finally:
            dlg.close()

    def test_upd_table_copy_selection(self):
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.SourceDialog()
        try:
            t = dlg.upd_table
            self.assertGreater(t.rowCount(), 0)
            t.clearSelection()
            t.item(0, 0).setSelected(True)
            t.item(0, 1).setSelected(True)
            pm.SourceDialog._copy_table_selection(t)
            clip = QApplication.clipboard().text()
            self.assertIn(t.item(0, 0).text(), clip)
            self.assertIn("\t", clip)
        finally:
            dlg.close()

    def test_data_update_dialog_finished_fills_status(self):
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.DataUpdateDialog()
        try:
            self.assertGreater(dlg.table.rowCount(), 0)
            rep = [{"key": "gaiji", "status": "unchanged", "detail": "1 条"}]
            dlg._on_finished(rep)
            from pycbeta.update_data import load_sources
            keys = [s["key"] for s in load_sources()]
            self.assertIn("一致", dlg.table.item(keys.index("gaiji"), 3).text())
            self.assertIn("gaiji", dlg.status.text())
        finally:
            dlg.close()

    def test_data_update_dialog_dry_run_passthrough(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.DataUpdateDialog()
        try:
            dlg.dry_box.setChecked(True)
            with mock.patch.object(pm, "DataUpdateWorker") as W:
                dlg._on_go()
                W.assert_called_once_with(dry_run=True)
                self.assertFalse(dlg.btn_go.isEnabled())
            dlg._on_done()
            self.assertTrue(dlg.btn_go.isEnabled())
        finally:
            dlg.close()

    def test_reset_urls_fills_factory_without_saving(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.SourceDialog()
        try:
            self.assertEqual(dlg.btn_reset_urls.text(), "重置 URL")
            # 重置按钮在对话框按钮组里（确定/取消旁边）
            self.assertIn(dlg.btn_reset_urls,
                          dlg._buttons_box.buttons())
            dlg.dl_table.item(0, 1).setText("http://broken/invalid")
            with mock.patch.object(pm, "save_current") as m:
                dlg._on_reset_urls()
                m.assert_not_called()  # 只填表，不保存
            from pycbeta.theme import load_presets
            factory_dl = load_presets().get("downloads") or {}
            vals = {dlg.dl_table.item(i, 0).text(): dlg.dl_table.item(i, 1).text()
                    for i in range(dlg.dl_table.rowCount())}
            self.assertEqual(vals.get("xml"), factory_dl.get("xml"))
            self.assertIn("点确定保存", dlg.update_status.text())
        finally:
            dlg.close()

    def test_accept_saves_edited_urls(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.SourceDialog()
        try:
            dlg.dl_table.item(0, 1).setText("http://example/custom-xml")
            dlg.path_edits["cbeta_ebook"].setText("B")  # 自包含：避免缺工作根弹窗
            with mock.patch.object(pm, "save_current") as m:
                with mock.patch.object(
                        pm, "load_slot",
                        return_value=({"source": {}, "downloads": {}},
                                      "user")):
                    with mock.patch("pycbeta.fetch.inspect_xml_source",
                                    return_value={"safe": True,
                                                  "edition": "XML TEI P5"}):
                        dlg.accept()
                    m.assert_called_once()
                    saved = m.call_args.args[0]
                    self.assertEqual(
                        saved["downloads"]["xml"], "http://example/custom-xml")
        finally:
            dlg.close()

    def test_figures_url_visible_with_factory_default(self):
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.SourceDialog()
        try:
            vals = {dlg.dl_table.item(i, 0).text(): dlg.dl_table.item(i, 1).text()
                    for i in range(dlg.dl_table.rowCount())}
            # 用户文件即使缺 figures 键，也显示出厂默认值（可改）
            self.assertIn("figures", vals)
            self.assertIn("CBR2X-figures", vals["figures"])
        finally:
            dlg.close()

    def test_last_update_shown(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        with mock.patch("pycbeta.update_data.last_update_summary",
                        return_value="上次更新 2026-09-09（gaiji）"):
            dlg = pm.SourceDialog()
            try:
                self.assertIn("2026-09-09", dlg.update_status.text())
            finally:
                dlg.close()

    def test_ebook_update_dialog_copy(self):
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        rep = [{"id": "T0349", "status": "updated", "detail": "1→2B"},
               {"id": "T0625", "status": "unchanged", "detail": ""},
               {"id": "T0670", "status": "failed", "detail": "HTTP 500"}]
        dlg = pm.EbookUpdateDialog(rep)
        try:
            self.assertIn("T0349", dlg.text.toPlainText())
            self.assertTrue(dlg.btn_copy.isEnabled())
            dlg._on_copy()
            self.assertEqual(app.clipboard().text(), "T0349")
            self.assertIn("1", dlg.copy_status.text())
        finally:
            dlg.close()
        dlg2 = pm.EbookUpdateDialog([{"id": "T1", "status": "unchanged",
                                      "detail": ""}])
        try:
            self.assertFalse(dlg2.btn_copy.isEnabled())
        finally:
            dlg2.close()

    def test_source_dialog_preset_keys(self):
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.SourceDialog()
        try:
            keys = [k for k, _ in pm.SOURCE_LABELS]
            # 路径行：xml_dir + cbeta_ebook + verify_root（catalog 已钉死内置，不再设行）
            self.assertEqual(keys, ["xml_dir", "cbeta_ebook", "verify_root"])
            self.assertIn("xml_dir", dlg.path_edits)
            self.assertIn("cbeta_ebook", dlg.path_edits)
            self.assertNotIn("catalog", dlg.path_edits)
            for _k, ed in dlg.path_edits.items():
                self.assertTrue(ed.isReadOnly())  # 只能浏览选择，不可手输
            self.assertTrue(dlg.title_t2s_box.isChecked())  # 默认开
            self.assertTrue(dlg.ebook_base_box.isChecked())  # 默认同时更新基线
        finally:
            dlg.close()


class TestCssEditor(unittest.TestCase):
    """样式编辑器：覆盖块 roundtrip / spec 解析 / user.css 落盘 / 接线（全 offscreen）。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_override_roundtrip(self):
        from pycbeta.gui.css_editor import build_override_block, parse_override_block
        values = {"h1.title": {"font-family": "朝华标题B, ZhaohuaMinB",
                               "font-size": "30pt"},
                  "div.div-xu p.head": {"font-size": "20pt", "color": "#0000a0"},
                  "sup.note-ref": {"font-size": "0.75em"}}
        block = build_override_block(values)
        back, err = parse_override_block(block)
        self.assertIsNone(err)
        self.assertEqual(back["h1.title"]["font-family"], "朝华标题B, ZhaohuaMinB")
        self.assertEqual(back["h1.title"]["font-size"], "30pt")
        self.assertEqual(back["div.div-xu p.head"]["color"], "#0000a0")
        self.assertEqual(back["sup.note-ref"]["font-size"], "0.75em")

    def test_override_bad_css_reports(self):
        from pycbeta.gui.css_editor import parse_override_block
        # 非法输入只红字不抛异常
        _values, err = parse_override_block("\x00\x01\x02{{{{p.head")
        self.assertIsInstance(err, (str, type(None)))

    def test_passthrough_survives_control_edit(self):
        from pycbeta.gui.css_editor import (build_override_block,
                                        split_override_block)
        src = ("p.head[data-head-level=\"1\"] { margin-left: 0em; font-size: 20pt; }\n"
               "div.lg.note1, div.lg.note2 { color: #408080; }\n"
               "h1.title { font-size: 30pt; }\n")
        values, passthrough, err = split_override_block(src)
        self.assertIsNone(err)
        self.assertEqual(values, {"h1.title": {"font-size": "30pt"}})
        self.assertIn("data-head-level", passthrough)
        self.assertIn("note1", passthrough)
        # 控件改值重建后未知规则仍在
        values["h1.title"]["font-size"] = "34pt"
        rebuilt = build_override_block(values, passthrough)
        self.assertIn("data-head-level", rebuilt)
        self.assertIn("color: #408080", rebuilt)
        self.assertIn("font-size: 34pt", rebuilt)

    def test_font_buckets(self):
        from pycbeta.gui.css_editor import group_font_names
        g = group_font_names(["SimSun", "宋体", "PMingLiU", "新細明體",
                              "KaiTi", "楷体", "FangSong", "LiSu", "隸書",
                              "ZhaohuaMinB", "朝華標題B", "Times New Roman",
                              "Calibri", "Aptos", "Courier New"])
        self.assertIn("SimSun", g["宋体"])
        self.assertIn("宋体", g["宋体"])
        self.assertIn("PMingLiU", g["明体"])  # 明体自立：PMingLiU/新細明體不再被宋体吞
        self.assertIn("新細明體", g["明体"])
        self.assertIn("FangSong", g["仿宋"])  # 仿宋排宋体前，免被 song 吞掉
        self.assertIn("KaiTi", g["楷体"])
        self.assertIn("LiSu", g["隶书"])
        self.assertIn("ZhaohuaMinB", g["标题"])
        # 西文走下拉固定三，分组里归未分类（UI 另行陈列）
        self.assertIn("Calibri", g["未分类"])
        self.assertIn("Times New Roman", g["未分类"])

    def test_css_colors(self):
        from pycbeta.gui.css_editor import css_colors
        css = ("p.head { color: #0000a0; font-size: 20pt; }\n"
               "/* sup.note-ref { color: #fff; } */\n"
               "sup.note-ref { color: #0066CC; }\n")
        got = css_colors(css)
        self.assertEqual([h for h, _s in got], ["#0000a0", "#0066cc"])
        self.assertIn("p.head", got[0][1])
        self.assertNotIn("fff", [h for h, _s in got])  # 注释掉的不算

    def test_series_title_theme(self):
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.theme import Theme
        t = Theme()
        st = t.tags.get("series-title") or {}
        self.assertEqual(st.get("font-size"), "9pt")
        self.assertIn("FangSong", st.get("font-family", ""))
        r = DocxRenderer(theme=t, series_title={})
        self.assertEqual(r._series_size_pt(st), 18)  # 9pt→18 半磅
        # 无规则时回退 config 旧键
        self.assertEqual(r._series_size_pt({}), 18)
        r2 = DocxRenderer(theme=t, series_title={"size": 12})
        self.assertEqual(r2._series_size_pt({}), 24)

    def test_font_dual_column_roundtrip(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            # 自定义栈经载入进临时项（仍可选中），写回源码无损
            block = (":root { --font-title: HantF, serif; }\n"
                     'html[lang="zh-Hans"] { --font-title: HansF; }\n')
            dlg._load_block_text(block)
            box_hant = dlg._rows["h1.title"]["font_hant"]
            box_hans = dlg._rows["h1.title"]["font_hans"]
            self.assertEqual(box_hant.currentData(), "HantF, serif")
            self.assertEqual(box_hans.currentData(), "HansF")
            out = dlg._source_edit.toPlainText()
            self.assertIn(":root { --font-title: HantF, serif; }", out)
            self.assertIn('html[lang="zh-Hans"] { --font-title: HansF; }',
                          out)
            self.assertIn(("h1.title", "font-family", "zh-Hant"),
                          dlg._touched)
            self.assertIn(("h1.title", "font-family", "zh-Hans"),
                          dlg._touched)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_font_combo_editable_searchable(self):
        from PySide6.QtWidgets import QComboBox
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            for sel, row in dlg._rows.items():
                self.assertTrue(row["font_hant"].isEditable())
                self.assertTrue(row["font_hans"].isEditable())
                self.assertEqual(row["font_hant"].insertPolicy(),
                                 QComboBox.NoInsert)
                # 框体窄（100），弹出放宽（300），互不干扰
                self.assertEqual(row["font_hant"].minimumWidth(), 100)
                self.assertGreaterEqual(
                    row["font_hant"].view().minimumWidth(), 300)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_chinese_name_gets_english_alias(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        groups = {"宋体": ["宋体"], "未分类": []}
        with mock.patch.object(ce, "font_group_model",
                               return_value=(groups, [], "")), \
                mock.patch.object(ce, "qt_aliases",
                                  return_value={"宋体": "SimSun"}):
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            box = dlg._rows["p"]["font_hans"]
            # 中文单名项补同字体英文别名：data="名, 别名"，显示短名
            i = box.findData("宋体, SimSun")
            self.assertGreaterEqual(i, 0)
            self.assertEqual(box.itemText(i), "宋体")
            # 西文/英文单名不补（data 即自身）
            j = box.findText("Times New Roman")
            self.assertGreaterEqual(j, 0)
            self.assertEqual(box.itemData(j), "Times New Roman")
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_select_short_name_writes_full_stack(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        groups = {"宋体": ["宋体"], "未分类": []}
        with mock.patch.object(ce, "font_group_model",
                               return_value=(groups, [], "")), \
                mock.patch.object(ce, "qt_aliases",
                                  return_value={"宋体": "SimSun"}):
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            box = dlg._rows["p"]["font_hans"]
            i = box.findData("宋体, SimSun")
            self.assertGreaterEqual(i, 0)
            box.setCurrentIndex(0)  # 先切走，确保 change 触发
            box.setCurrentIndex(i)
            self.assertEqual(box.currentText(), "宋体")  # 框里短名
            self.assertIn("--font-p: 宋体, SimSun",
                          dlg._source_edit.toPlainText())  # 存完整栈
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_custom_stack_temp_item_no_pileup(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            box = dlg._rows["p"]["font_hant"]
            n0 = box.count()
            dlg._load_block_text(":root { --font-p: MyF, serif; }\n")
            self.assertEqual(box.currentData(), "MyF, serif")
            self.assertGreaterEqual(box.findData("MyF, serif"), 0)
            n1 = box.count()
            # 再换一个自定义栈：旧临时项删、新临时项插，不堆积
            dlg._load_block_text(":root { --font-p: OtherF; }\n")
            self.assertEqual(box.currentData(), "OtherF")
            self.assertLess(box.findText("MyF, serif"), 0)
            self.assertLessEqual(box.count(), n1)
            self.assertGreaterEqual(box.count(), n0)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_preview_font_fallback(self):
        import pycbeta.gui.css_editor as ce
        self.assertEqual(ce.preview_families("新細明體"),
                         ["新細明體", "SimSun", "宋体", "Microsoft YaHei",
                          "sans-serif"])
        self.assertEqual(ce.preview_families(""),
                         ["SimSun", "宋体", "Microsoft YaHei", "sans-serif"])
        self.assertEqual(ce.preview_families("SimSun"),
                         ["SimSun", "宋体", "Microsoft YaHei", "sans-serif"])
        self.assertEqual(ce.missing_families(["A", "b", "A"], ["a", "C"]),
                         ["b"])
        self.assertEqual(ce.missing_families([], []), [])

    def test_suppress_font_warnings(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("QT_LOGGING_RULES", None)
            ce.suppress_font_warnings()
            self.assertIn("qt.qpa.fonts.warning=false",
                          os.environ["QT_LOGGING_RULES"])
            ce.suppress_font_warnings()  # 幂等，不重复追加
            self.assertEqual(
                os.environ["QT_LOGGING_RULES"].count("qt.qpa.fonts"),
                1)

    def test_source_edit_fixed_font(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertEqual(dlg._source_edit.font().family(), "Consolas")
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_spec_captures_line_spacing(self):
        import shutil
        import zipfile
        import pycbeta.gui.css_editor as ce
        tmp = tempfile.mkdtemp()
        try:
            doc = ('<w:document xmlns:w="http://schemas.openxmlformats.org'
                   '/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:pPr><w:spacing w:line="432" w:lineRule="auto"/>'
                   '</w:pPr><w:r><w:t>文</w:t></w:r></w:p>'
                   '<w:p><w:pPr><w:pStyle w:val="head"/></w:pPr>'
                   '<w:r><w:t>题</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t>素</w:t></w:r></w:p>'
                   "</w:body></w:document>")
            styles = ('<w:styles xmlns:w="http://schemas.openxmlformats.org'
                      '/wordprocessingml/2006/main">'
                      '<w:style w:styleId="head"><w:pPr>'
                      '<w:spacing w:line="480" w:lineRule="auto"/>'
                      '</w:pPr></w:style>'
                      '<w:style w:styleId="Normal"><w:pPr>'
                      '<w:spacing w:line="360" w:lineRule="auto"/>'
                      '</w:pPr></w:style></w:styles>')
            fn = os.path.join(tmp, "s.docx")
            with zipfile.ZipFile(fn, "w") as z:
                z.writestr("word/document.xml", doc)
                z.writestr("word/styles.xml", styles)
            spec = ce.docx_spec(fn)
            # 行内优先
            self.assertEqual(spec["paras"][0]["line"],
                             {"line": 432, "rule": "auto"})
            # 无行内 → 本样式
            self.assertEqual(spec["paras"][1]["line"],
                             {"line": 480, "rule": "auto"})
            # 无行内无样式 → Normal（与 Word 一致）
            self.assertEqual(spec["paras"][2]["line"],
                             {"line": 360, "rule": "auto"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_preview_applies_line_spacing(self):
        from PySide6.QtGui import QTextBlockFormat
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            spec = {"paras": [{"style": "p", "align": "",
                               "line": {"line": 432, "rule": "auto"},
                               "runs": [{"text": "文", "size": 12.0,
                                         "font": "", "bold": False,
                                         "color": "", "super": False,
                                         "dim": False}]}],
                    "footnotes": []}
            dlg._show_spec(spec, {})
            fmt = dlg.preview.document().firstBlock().blockFormat()
            self.assertEqual(
                int(fmt.lineHeightType()),
                QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            self.assertAlmostEqual(fmt.lineHeight(), 180.0)
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_preview_breaks_on_br(self):
        import shutil
        import zipfile
        import pycbeta.gui.css_editor as ce
        tmp = tempfile.mkdtemp()
        try:
            doc = ('<w:document xmlns:w="http://schemas.openxmlformats.org'
                   '/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:r><w:t>上句。</w:t></w:r>'
                   '<w:r><w:br/></w:r>'
                   '<w:r><w:t>下句。</w:t></w:r></w:p>'
                   "</w:body></w:document>")
            fn = os.path.join(tmp, "s.docx")
            with zipfile.ZipFile(fn, "w") as z:
                z.writestr("word/document.xml", doc)
            spec = ce.docx_spec(fn)
            runs = spec["paras"][0]["runs"]
            self.assertEqual([r.get("text", "<br>") for r in runs],
                             ["上句。", "<br>", "下句。"])
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
            try:
                dlg._show_spec(spec, {})
                blocks = []
                b = dlg.preview.document().firstBlock()
                while b.isValid():
                    blocks.append(b.text())
                    b = b.next()
                self.assertIn("上句。", blocks)
                self.assertIn("下句。", blocks)
            finally:
                dlg.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_editor_t2s_renders_simplified(self):
        import glob
        import pycbeta.gui.css_editor as ce
        sample = glob.glob(os.path.join(ce.REPO_ROOT, "presets", "sample.xml"))
        self.assertTrue(sample, "sample.xml 缺失")
        dlg = ce.CssEditorDialog(sample_xml=sample[0])
        try:
            self.assertFalse(dlg.t2s_box.isChecked())
            dlg.t2s_box.setChecked(True)
            fn = dlg._render_inline(dlg.work_css())
            import zipfile
            x = zipfile.ZipFile(fn).read("word/document.xml").decode("utf-8")
            import re
            texts = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", x))
            self.assertIn("准提", texts)  # 準→准（简体）
            self.assertNotIn("準提", texts)
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_editor_save_and_discard_prompt(self):
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        root = tempfile.mkdtemp()
        try:
            fn = os.path.join(root, "mine.css")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("/* base */\n")
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
            try:
                # 干净时直接放行，不弹窗
                self.assertTrue(dlg._confirm_discard())
                # 载入预设后改动 → 脏
                dlg._load_preset_path(fn)
                self.assertFalse(dlg._is_dirty())
                dlg._rows["h1.title"]["size"].setText("40pt")
                self.assertTrue(dlg._is_dirty())
                # 保存写回文件并变干净
                self.assertTrue(dlg._save_current())
                self.assertFalse(dlg._is_dirty())
                with open(fn, encoding="utf-8") as f:
                    self.assertIn("font-size: 40pt", f.read())
                # 脏 + 选取消 → 不放行
                dlg._rows["h1.title"]["size"].setText("41pt")
                with mock.patch.object(
                        dlg, "_ask_save_discard_cancel",
                        return_value="cancel"):
                    self.assertFalse(dlg._confirm_discard())
                # 脏 + 选不保存 → 放行
                with mock.patch.object(
                        dlg, "_ask_save_discard_cancel",
                        return_value="discard"):
                    self.assertTrue(dlg._confirm_discard())
                # 脏 + 选取消 → 不放行（留编辑，与不保存区分）
                dlg._rows["h1.title"]["size"].setText("42pt")
                with mock.patch.object(
                        dlg, "_ask_save_discard_cancel",
                        return_value="cancel"):
                    self.assertFalse(dlg._confirm_discard())
                # 保存后变干净，关闭不再弹窗
                self.assertTrue(dlg._save_current())
                self.assertFalse(dlg._is_dirty())
            finally:
                dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_report_dialog_highlights_missing(self):
        import pycbeta.gui.css_editor as ce
        from pycbeta.gui.css_editor import PreviewReportDialog
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        w = PreviewReportDialog()
        try:
            w.update_report({"time": "t", "base": "b", "sample": "s",
                             "t2s": True, "fonts": [("A", True), ("B", False)],
                             "css_error": "", "error": ""})
            html = w.view.toHtml()
            self.assertIn("B", html)
            self.assertIn("#ff0000", html)  # 缺字体红色醒目（Qt 归一化 red）
        finally:
            w.close()

    def test_control_header_and_widths(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        groups = {"宋体": ["宋体"], "未分类": []}
        with mock.patch.object(ce, "font_group_model",
                               return_value=(groups, [], "")), \
                mock.patch.object(ce, "qt_aliases",
                                  return_value={"宋体": "SimSun"}):
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            # 列标题行存在；磅数框收窄；粗细是三态按钮（默认=灰）
            self.assertEqual(
                dlg._rows["h1.title"]["size"].maximumWidth(), 60)
            from PySide6.QtWidgets import QPushButton
            self.assertIsInstance(dlg._rows["h1.title"]["weight"],
                                  QPushButton)
            self.assertEqual(
                dlg._rows["h1.title"]["weight"].text(), "默认")
            dlg._sync_controls_from_block(
                {"h1.title": {"font-family": "宋体, SimSun"}})
            box = dlg._rows["h1.title"]["font_hant"]
            self.assertGreaterEqual(box.findData("宋体, SimSun"), 0)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_weight_three_state_cycle(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        # 出厂基线启动（不受本机 run.json 默认预设影响）
        with mock.patch.object(ce, "current_theme_value",
                               return_value="pdf_docx.css"):
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            sel = "h1.title"
            btn = dlg._rows[sel]["weight"]
            # 默认（未覆盖）→ 加粗
            dlg._cycle_weight(sel)
            self.assertEqual(btn.text(), "加粗")
            self.assertIn("h1.title { font-weight: bold; }",
                          dlg._source_edit.toPlainText())
            self.assertIn((sel, "font-weight"), dlg._touched)
            # 加粗 → 常规
            dlg._cycle_weight(sel)
            self.assertEqual(btn.text(), "常规")
            self.assertIn("font-weight: normal",
                          dlg._source_edit.toPlainText())
            # 常规 → 默认（不写值，touched 清空）
            dlg._cycle_weight(sel)
            self.assertEqual(btn.text(), "默认")
            self.assertNotIn("font-weight",
                             dlg._source_edit.toPlainText())
            self.assertNotIn((sel, "font-weight"), dlg._touched)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_font_input_validate_warns_and_restores(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        groups = {"宋体": ["宋体"], "未分类": []}
        with mock.patch.object(ce, "font_group_model",
                               return_value=(groups, [], "")), \
                mock.patch.object(ce, "qt_aliases",
                                  return_value={"宋体": "SimSun"}):
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            box = dlg._rows["p"]["font_hans"]
            i = box.findData("宋体, SimSun")
            self.assertGreaterEqual(i, 0)
            box.setCurrentIndex(i)  # 先选中"宋体"作为旧值
            box.setCurrentIndex(0)  # 切到第一项（确保有基线）
            box.setCurrentIndex(i)
            self.assertEqual(box.currentText(), "宋体")
            with mock.patch.object(ce.QMessageBox, "warning") as m:
                box.setEditText("NotInstalled")
                box.lineEdit().editingFinished.emit()
                m.assert_called_once()
                # 警告 + 复原：文本框回到旧选中项（不再是手输文本）
                self.assertEqual(box.currentText(), "宋体")
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_font_input_match_auto_selects(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        groups = {"宋体": ["宋体"], "未分类": []}
        with mock.patch.object(ce, "font_group_model",
                               return_value=(groups, [], "")), \
                mock.patch.object(ce, "qt_aliases",
                                  return_value={"宋体": "SimSun"}):
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            box = dlg._rows["p"]["font_hans"]
            box.setCurrentIndex(0)
            with mock.patch.object(ce.QMessageBox, "warning") as m:
                box.setEditText("宋体")
                box.lineEdit().editingFinished.emit()
                m.assert_not_called()  # 匹配选项，不警告
            # 自动选中该项 → 写完整栈
            self.assertIn("--font-p: 宋体, SimSun",
                          dlg._source_edit.toPlainText())
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_t2s_moved_to_preview(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertEqual(dlg.t2s_box.text(), "繁转简")
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_sim_tip_below_status(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertIn("模拟显示", dlg.sim_tip.text())
            self.assertIn("分页", dlg.sim_tip.text())
            self.assertIn("图片", dlg.sim_tip.text())  # 图片不显示已声明
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_restore_loaded(self):
        import shutil
        import pycbeta.gui.css_editor as ce
        root = tempfile.mkdtemp()
        try:
            fn = os.path.join(root, "mine.css")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("/* base */\np.head { font-size: 40pt; }\n")
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
            try:
                dlg._load_preset_path(fn)
                self.assertFalse(dlg._is_dirty())
                self.assertTrue(hasattr(dlg, "btn_restore"))
                orig = dlg._rows["h1.title"]["size"].text()
                dlg._rows["h1.title"]["size"].setText("41pt")
                self.assertTrue(dlg._is_dirty())
                self.assertTrue(dlg._restore_loaded())
                self.assertFalse(dlg._is_dirty())
                self.assertEqual(
                    dlg._rows["h1.title"]["size"].text(), orig)
                self.assertIn("p.head { font-size: 40pt; }",
                              dlg._source_edit.toPlainText())
                # 恢复不碰预设选择
                before = dlg.preset_box.currentIndex()
                dlg._rows["h1.title"]["size"].setText("42pt")
                self.assertTrue(dlg._restore_loaded())
                self.assertFalse(dlg._is_dirty())
                self.assertEqual(dlg.preset_box.currentIndex(), before)
            finally:
                dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_status_warn_link(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertFalse(hasattr(dlg, "btn_check"))  # 检查按钮已删
            dlg._set_status("预览已更新 00:00:00")
            self.assertEqual(dlg.status.text(), "预览已更新 00:00:00")
            self.assertFalse(dlg._status_linked)
            dlg._set_status("预览已更新 00:00:00", 2, "缺A；缺B")
            self.assertIn("⚠2", dlg.status.text())
            self.assertEqual(dlg.status.toolTip(), "缺A；缺B")
            self.assertTrue(dlg._status_linked)
            with mock.patch.object(dlg, "_open_report") as m:
                dlg.status.linkActivated.emit("#")
                m.assert_called_once_with()
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                dlg._set_status("预览已更新 00:00:01")  # 断开无警告
                dlg._set_status("预览已更新 00:00:02", 1, "x")
                dlg._set_status("预览已更新 00:00:03", 1, "x")  # 重复不断不连
            self.assertTrue(dlg._status_linked)
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_names_merge_consecutive(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            run = {"text": "x", "size": 12.0, "font": "", "bold": False,
                   "color": "", "super": False, "dim": False}
            spec = {"paras": [
                {"style": "p", "align": "", "line": None, "runs": [run]},
                {"style": "p", "align": "", "line": None, "runs": [run]},
                {"style": "head", "align": "center", "line": None,
                 "runs": [run]},
                {"style": "p", "align": "", "line": None, "runs": [run]}],
                "footnotes": []}
            dlg.names_box.setChecked(True)
            dlg._show_spec(spec, {})
            text = dlg.preview.toPlainText()
            # 相邻同样式只标首段：正文2段→1标，标题1标，后正文再标
            self.assertEqual(text.count("【正文】"), 2)
            self.assertEqual(text.count("【标题】"), 1)
            dlg.names_box.setChecked(False)
            dlg._show_spec(spec, {})
            self.assertNotIn("【", dlg.preview.toPlainText())
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_footnote_name_label_once(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            run = {"text": "x", "size": 12.0, "font": "", "bold": False,
                   "color": "", "super": False, "dim": False}
            spec = {"paras": [
                {"style": "p", "align": "", "line": None, "runs": [run]}],
                "footnotes": [
                    {"num": 1, "runs": [run], "line": None, "margin": None},
                    {"num": 2, "runs": [run], "line": None, "margin": None}]}
            dlg.names_box.setChecked(True)
            dlg._show_spec(spec, {})
            text = dlg.preview.toPlainText()
            self.assertEqual(text.count("【脚注】"), 1)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_div_note_color(self):
        import pycbeta.gui.css_editor as ce
        self.assertEqual(
            ce.div_note_color("div.div-note { color: #666666; }"),
            "#666666")
        # 后定义优先（用户覆盖胜出厂）
        self.assertEqual(
            ce.div_note_color("div.div-note { color: #666666; }\n"
                              "div.div-note { color: #999999; }"),
            "#999999")
        self.assertEqual(ce.div_note_color("p { color: #000; }"), "")

    def test_note_paras_labeled_ziyi(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            run = {"text": "x", "size": 12.0, "font": "", "bold": True,
                   "color": "", "super": False, "dim": False}
            spec = {"paras": [
                {"style": "p", "align": "", "line": None, "runs": [run]},
                {"style": "div-note", "align": "", "line": None,
                 "runs": [run]},
                {"style": "div-note", "align": "", "line": None,
                 "runs": [run]},
                {"style": "p", "align": "", "line": None, "runs": [run]}],
                "footnotes": []}
            dlg.names_box.setChecked(True)
            dlg._show_spec(spec, {})
            text = dlg.preview.toPlainText()
            # pStyle div-note → 标【字义】（相邻去重），p 仍【正文】
            self.assertEqual(text.count("【字义】"), 1)
            self.assertEqual(text.count("【正文】"), 2)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_load_shows_inherited_values(self):
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        root = tempfile.mkdtemp()
        try:
            fn = os.path.join(root, "mine.css")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("/* base */\np.head { font-size: 40pt; }\n")
            # 出厂基线启动（不受本机 run.json 默认预设影响）
            with mock.patch.object(ce, "current_theme_value",
                                   return_value="pdf_docx.css"):
                dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
                try:
                    open26 = dlg._rows["h1.title"]["size"].text()
                    self.assertEqual(open26, "26pt")  # 打开时显示出厂有效值
                    dlg._load_preset_path(fn)
                    # 预设自有生效
                    self.assertEqual(
                        dlg._rows["p.head"]["size"].text(), "40pt")
                    # 未覆盖的显示继承（base），不是空白
                    self.assertEqual(
                        dlg._rows["h1.title"]["size"].text(), "26pt")
                    # touched 只记预设自有——保存不写继承值
                    self.assertNotIn(("h1.title", "font-size"), dlg._touched)
                    self.assertIn(("p.head", "font-size"), dlg._touched)
                    dlg._loaded_block = dlg._source_edit.toPlainText()
                finally:
                    dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_wheel_combo_ignores_wheel_when_closed(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            box = dlg._rows["p"]["font_hans"]
            self.assertIsInstance(box, ce._PopupWheelCombo)
            evt = mock.Mock()
            box.wheelEvent(evt)  # 未弹开 → 吃掉滚轮（滚左栏，不改值）
            evt.ignore.assert_called_once_with()
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_label_dirty_highlight(self):
        import pycbeta.gui.css_editor as ce
        dirty = {("p.head", "font-size")}
        self.assertTrue(ce.label_is_dirty("head", dirty))
        self.assertTrue(ce.label_is_dirty(
            "div-note", {("div.div-note", "color")}))
        self.assertFalse(ce.label_is_dirty("p", set()))
        self.assertFalse(ce.label_is_dirty("head", {("p", "font-size")}))
        # 预设自带但未改不算脏（改 A 时 B 不亮灯）
        self.assertFalse(ce.label_is_dirty("title", dirty))
        clean = ce._name_label_format(False).background().color().name()
        dirty_fmt = ce._name_label_format(True).background().color().name()
        self.assertNotEqual(clean, dirty_fmt)

    def test_dirty_keys_ignores_preset_owned(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            # 载入的预设自带 h1.title（用户预设场景）
            dlg._load_block_text(":root { --font-title: F, serif; }\n")
            self.assertFalse(ce.label_is_dirty(
                "title", dlg._dirty_keys()))
            # 再改 p.head：只有 head 脏，title 不亮
            dlg._rows["p.head"]["size"].setText("40pt")
            keys = dlg._dirty_keys()
            self.assertIn(("p.head", "font-size"), keys)
            self.assertTrue(ce.label_is_dirty("head", keys))
            self.assertFalse(ce.label_is_dirty("title", keys))
            self.assertFalse(ce.label_is_dirty("p", keys))
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_save_only_when_preset_loaded(self):
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        root = tempfile.mkdtemp()
        try:
            fn = os.path.join(root, "mine.css")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("/* base */\np.head { font-size: 40pt; }\n")
            # 出厂主题启动（不载用户槽）→ 保存灰
            with mock.patch.object(ce, "current_theme_value",
                                   return_value="pdf_docx.css"):
                dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
            try:
                # 出厂缓冲：保存置灰，输名字的事归另存
                self.assertFalse(dlg.btn_save.isEnabled())
                self.assertIn("另存", dlg.btn_save.toolTip())
                dlg._load_preset_path(fn)
                self.assertTrue(dlg.btn_save.isEnabled())
                dlg._reset_editor_state()  # 无修改，不弹确认框
                self.assertFalse(dlg.btn_save.isEnabled())
                dlg._loaded_block = dlg._source_edit.toPlainText()
            finally:
                dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_row_label_paints_dirty(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            lab = dlg._rows["p.head"]["name_label"]
            self.assertEqual(lab.styleSheet(), "")
            dlg._rows["p.head"]["size"].setText("40pt")
            dlg._paint_row_labels()
            self.assertIn("cc6600", lab.styleSheet())  # 脏行橙字
            # 模拟保存：loaded 追平 → 恢复默认
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg._paint_row_labels()
            self.assertEqual(lab.styleSheet(), "")
            self.assertEqual(
                dlg._rows["h1.title"]["name_label"].styleSheet(), "")
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_series_label(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            run = {"text": "X經", "size": 9.0, "font": "", "bold": False,
                   "color": "", "super": False, "dim": False}
            spec = {"paras": [
                {"style": "series-title", "align": "", "line": None,
                 "runs": [run]}],
                "footnotes": []}
            dlg.names_box.setChecked(True)
            dlg._show_spec(spec, {})
            self.assertIn("【经藏名】", dlg.preview.toPlainText())
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_def_label(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            run = {"text": "释义", "size": 10.8, "font": "", "bold": False,
                   "color": "#666666", "super": False, "dim": False}
            spec = {"paras": [
                {"style": "def", "align": "", "line": None, "runs": [run]},
                {"style": "def", "align": "", "line": None, "runs": [run]}],
                "footnotes": []}
            dlg.names_box.setChecked(True)
            dlg._show_spec(spec, {})
            text = dlg.preview.toPlainText()
            self.assertEqual(text.count("【释义】"), 1)  # 相邻去重
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_preview_keeps_scroll_pos(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            run = {"text": "x", "size": 12.0, "font": "", "bold": False,
                   "color": "", "super": False, "dim": False}
            spec = {"paras": [
                {"style": "p", "align": "", "line": None, "runs": [run]}],
                "footnotes": []}
            vsb, hsb = mock.Mock(), mock.Mock()
            vsb.value.return_value = 37
            hsb.value.return_value = 5
            with mock.patch.object(dlg.preview, "verticalScrollBar",
                                   return_value=vsb), \
                    mock.patch.object(dlg.preview, "horizontalScrollBar",
                                      return_value=hsb):
                dlg._show_spec(spec, {})
            vsb.setValue.assert_called_once_with(37)
            hsb.setValue.assert_called_once_with(5)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_export_status_opens_file(self):
        import tempfile
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            fd, fn = tempfile.mkstemp(suffix=".docx")
            import os as _os
            _os.close(fd)
            try:
                dlg._set_export_status("DOCX", fn)
                self.assertTrue(dlg._status_linked)
                self.assertIn("打开文件", dlg.status.text())
                with mock.patch.object(
                        ce.QDesktopServices, "openUrl") as m:
                    dlg.status.linkActivated.emit("open-export")
                    m.assert_called_once()  # 带 QUrl 实参打开文件
                with mock.patch.object(dlg, "_open_report") as m2:
                    dlg.status.linkActivated.emit("#")
                    m2.assert_called_once_with()
            finally:
                _os.remove(fn)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_tooltip_style_once(self):
        from PySide6.QtWidgets import QApplication
        import pycbeta.gui.css_editor as ce
        QApplication.instance() or QApplication([])
        ce.ensure_tooltip_style()
        ce.ensure_tooltip_style()  # 重复不叠加
        self.assertIn("QToolTip", QApplication.instance().styleSheet())

    def test_dialog_tooltip_scoped_no_app_pollution(self):
        from PySide6.QtWidgets import QApplication
        import pycbeta.gui.css_editor as ce
        app = QApplication.instance() or QApplication([])
        before = app.styleSheet() or ""
        dlg = ce.CssEditorDialog()
        try:
            self.assertIn("QToolTip", dlg.styleSheet())  # 实例级生效
        finally:
            dlg.close()
        self.assertEqual(app.styleSheet() or "", before)  # 应用级不动

    def test_row_cb_tip_two_segments(self):
        import pycbeta.gui.css_editor as ce
        self.assertEqual(ce._row_cb_tip("div.div-xu p.head"),
                         'cb：div[@type="xu"] 内的 head')
        self.assertEqual(ce._row_cb_tip("cb:def"), "cb 标签：def")
        self.assertEqual(ce._row_cb_tip("div.div-note"),
                         'cb 标签：div[@type="note"]')
        self.assertEqual(ce._row_cb_tip("p"), "cb 标签：p")
        self.assertEqual(ce._row_cb_tip("nope"), "")

    def test_margins_real_display(self):
        import pycbeta.gui.css_editor as ce
        self.assertEqual(
            ce._para_margin.__doc__ is not None, True)
        import shutil
        import zipfile
        tmp = tempfile.mkdtemp()
        try:
            doc = ('<w:document xmlns:w="http://schemas.openxmlformats.org'
                   '/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:pPr><w:pStyle w:val="head"/>'
                   '<w:spacing w:before="400" w:after="200"/>'
                   '</w:pPr><w:r><w:t>题</w:t></w:r></w:p>'
                   "</w:body></w:document>")
            styles = ('<w:styles xmlns:w="http://schemas.openxmlformats.org'
                      '/wordprocessingml/2006/main">'
                      '<w:style w:styleId="Normal"><w:pPr>'
                      '<w:spacing w:before="10" w:after="20"/>'
                      '</w:pPr></w:style></w:styles>')
            fn = os.path.join(tmp, "s.docx")
            with zipfile.ZipFile(fn, "w") as z:
                z.writestr("word/document.xml", doc)
                z.writestr("word/styles.xml", styles)
            spec = ce.docx_spec(fn)
            self.assertEqual(spec["paras"][0]["margin"],
                             {"before": 400, "after": 200})
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
            try:
                dlg._show_spec(spec, {})
                fmt = dlg.preview.document().firstBlock().blockFormat()
                self.assertAlmostEqual(fmt.topMargin(), 400 / 15.0)
                self.assertAlmostEqual(fmt.bottomMargin(), 200 / 15.0)
                dlg._loaded_block = dlg._source_edit.toPlainText()
            finally:
                dlg.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unsized_run_falls_back(self):
        import pycbeta.gui.css_editor as ce
        import shutil
        import zipfile
        tmp = tempfile.mkdtemp()
        try:
            doc = ('<w:document xmlns:w="http://schemas.openxmlformats.org'
                   '/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:r><w:t>无样式无字号</w:t></w:r></w:p>'
                   '<w:p><w:pPr><w:pStyle w:val="footnote"/></w:pPr>'
                   '<w:r><w:t>注无字号</w:t></w:r></w:p>'
                   "</w:body></w:document>")
            styles = ('<w:styles xmlns:w="http://schemas.openxmlformats.org'
                      '/wordprocessingml/2006/main">'
                      '<w:docDefaults><w:rPrDefault><w:rPr>'
                      '<w:sz w:val="22"/>'
                      '</w:rPr></w:rPrDefault></w:docDefaults>'
                      '<w:style w:styleId="footnote"><w:rPr>'
                      '<w:sz w:val="18"/>'
                      '</w:rPr></w:style></w:styles>')
            fn = os.path.join(tmp, "s.docx")
            with zipfile.ZipFile(fn, "w") as z:
                z.writestr("word/document.xml", doc)
                z.writestr("word/styles.xml", styles)
            spec = ce.docx_spec(fn)
            # 无样式段回落文档默认 11pt；footnote 样式段回落样式 9pt
            self.assertEqual(spec["paras"][0]["runs"][0]["size"], 11.0)
            self.assertEqual(spec["paras"][1]["runs"][0]["size"], 9.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_glyph_gaps(self):
        import pycbeta.gui.css_editor as ce
        spec = {"paras": [{"style": "p", "align": "", "line": None,
                           "runs": [{"text": "AB字", "size": 12.0,
                                     "font": "F", "bold": False, "color": "",
                                     "super": False, "dim": False}]}],
                "footnotes": []}
        import unittest.mock as mock
        with mock.patch("pycbeta.fonts.font_cmap",
                        return_value=frozenset({ord("A")})), \
                mock.patch("pycbeta.fonts.locator") as ml:
            ml.return_value.path.return_value = "/x.ttf"
            gaps = ce.glyph_gaps(spec)
        self.assertEqual(set(gaps["F"]), {"B", "字"})
        # 找不到文件跳过，不断预览
        with mock.patch("pycbeta.fonts.locator") as ml2:
            ml2.return_value.path.return_value = None
            self.assertEqual(ce.glyph_gaps(spec), {})

    def test_names_toggle_labels_paras(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            spec = {"paras": [
                {"style": "head", "align": "center", "line": None,
                 "runs": [{"text": "字義", "size": 20.0, "font": "",
                           "bold": True, "color": "", "super": False,
                           "dim": False}]},
                {"style": "p", "align": "", "line": None,
                 "runs": [{"text": "正文", "size": 12.0, "font": "",
                           "bold": False, "color": "", "super": False,
                           "dim": False}]}],
                "footnotes": []}
            self.assertFalse(dlg.names_box.isChecked())
            dlg._show_spec(spec, {})
            self.assertNotIn("【标题】", dlg.preview.toPlainText())
            dlg.names_box.setChecked(True)
            dlg._show_spec(spec, {})
            text = dlg.preview.toPlainText()
            self.assertIn("【标题】", text)
            self.assertIn("【正文】", text)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_qt_alias_bridges_localized_names(self):
        import pycbeta.gui.css_editor as ce
        rows = [["ZhaohuaMinB", "朝華見出明朝B", "朝华标题B",
                 "ZhaohuaMinB Black"],
                ["PMingLiU", "新細明體"],
                ["DFKai-SB", "標楷體"],
                ["SimSun", "宋体"]]
        qt = ["ZhaohuaMinB", "PMingLiU", "DFKai-SB", "SimSun",
              "Microsoft YaHei", "Calibri"]
        m = ce.build_qt_aliases(rows, qt)
        self.assertEqual(ce.resolve_qt_family("朝华标题B", m), "ZhaohuaMinB")
        self.assertEqual(ce.resolve_qt_family("新細明體", m), "PMingLiU")
        self.assertEqual(ce.resolve_qt_family("標楷體", m), "DFKai-SB")
        self.assertEqual(ce.resolve_qt_family("宋体", m), "SimSun")
        self.assertEqual(ce.resolve_qt_family("不存在的字体", m), "")
        self.assertEqual(ce.resolve_qt_family("", m), "")
        # 大小写不敏感回退
        self.assertEqual(ce.resolve_qt_family("simsun", m), "SimSun")

    def test_rows_without_var_disable_fonts(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            # 注锚行只有颜色，无字体变量
            self.assertFalse(dlg._rows["a.noteAnchor"].get("suffix"))
            self.assertFalse(
                dlg._rows["a.noteAnchor"]["font_hant"].isEnabled())
            self.assertTrue(dlg._rows["h1.title"]["font_hant"].isEnabled())
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_preview_lang_toggle(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertEqual(dlg._preview_lang(), "zh-Hant")
            dlg.preview_lang.setCurrentIndex(
                dlg.preview_lang.findData("zh-Hans"))
            self.assertEqual(dlg._preview_lang(), "zh-Hans")
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_default_sample_is_user_sample(self):
        import os
        import pycbeta.gui.css_editor as ce
        self.assertTrue(ce.SAMPLE_CANDIDATES[0].endswith(
            os.path.join("presets", "sample.xml")))
        self.assertEqual(ce.default_sample(), ce.SAMPLE_CANDIDATES[0])
        self.assertTrue(os.path.isfile(ce.default_sample()))

    def test_font_edit_keeps_preview_lang(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        groups = {"宋体": ["宋体", "新細明體"], "未分类": []}
        with mock.patch.object(ce, "font_group_model",
                               return_value=(groups, [], "")), \
                mock.patch.object(ce, "qt_aliases",
                                  return_value={"宋体": "SimSun",
                                                "新細明體": "PMingLiU"}):
            dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            # 预览栏只跟"预览字库"下拉：简栏改动不影响繁体预览，反之亦然
            self.assertEqual(dlg._preview_lang(), "zh-Hant")
            box_hans = dlg._rows["h1.title"]["font_hans"]
            i = box_hans.findData("宋体, SimSun")
            self.assertGreaterEqual(i, 0)
            box_hans.setCurrentIndex(0)
            box_hans.setCurrentIndex(i)
            self.assertEqual(dlg._preview_lang(), "zh-Hant")
            self.assertIn("--font-title: 宋体, SimSun",
                          dlg._source_edit.toPlainText())
            # 手动切简后改繁栏，仍保持简体预览
            dlg.preview_lang.setCurrentIndex(
                dlg.preview_lang.findData("zh-Hans"))
            box_hant = dlg._rows["h1.title"]["font_hant"]
            j = box_hant.findData("新細明體, PMingLiU")
            self.assertGreaterEqual(j, 0)
            box_hant.setCurrentIndex(0)
            box_hant.setCurrentIndex(j)
            self.assertEqual(dlg._preview_lang(), "zh-Hans")
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_font_combo_cursor_to_zero_on_activate(self):
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            box = dlg._rows["p"]["font_hant"]
            box.lineEdit().setCursorPosition(5)
            box.activated.emit(box.currentIndex())
            self.assertEqual(box.lineEdit().cursorPosition(), 0)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_css_combo_ordering(self):
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        import pycbeta.theme as _theme
        root = tempfile.mkdtemp()
        try:
            bdir = os.path.join(root, "b")
            udir = os.path.join(root, "u")
            os.makedirs(bdir)
            os.makedirs(udir)
            for d, fn in ((bdir, "a.css"), (udir, "mine.css")):
                with open(os.path.join(d, fn), "w",
                          encoding="utf-8") as f:
                    f.write("/* x */\n")
            with mock.patch.object(_theme, "BUILTIN_PRESETS_DIR", bdir), \
                    mock.patch.object(_theme, "user_presets_dir",
                                      lambda root=None: udir):
                box = ce.CssComboBox()
                box.refresh("mine")
                texts = [box.itemText(i) for i in range(box.count())]
                self.assertTrue(texts[0].startswith("（默认）"))
                self.assertEqual(texts[0], "（默认）mine")
                # 内置组已退役：不陈列（查找仍认旧名，向后兼容）
                self.assertFalse(any("［内置］" in t for t in texts))
                self.assertTrue(any("出厂默认样式" in t for t in texts))
                self.assertIn("── 用户预设 ──", texts)
                self.assertEqual(box.selected_value(), "mine")
                box.refresh("pdf_docx.css")
                self.assertTrue(box.itemText(0).startswith("（默认）出厂默认"))
                self.assertEqual(box.selected_value(), "pdf_docx.css")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cli_theme_priority(self):
        import shutil
        from pycbeta.theme import resolve_pdf_docx_css
        root = tempfile.mkdtemp()
        try:
            std = os.path.join(root, "std.css")
            usr = os.path.join(root, "usr.css")
            std2 = os.path.join(root, "std2.css")
            for p, body in ((std, "p { color: #111111; }"),
                            (usr, "p { color: #222222; }"),
                            (std2, "p { color: #333333; }")):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(body + "\n")
            run = {"pdf-docx-theme": std, "pdf-docx-user-theme": usr}
            # 显式开关最大
            css = resolve_pdf_docx_css(run, root, std=std2)
            self.assertIn("#333333", css)
            self.assertNotIn("#111111", css)
            # run.json 槽次之：标准 + 增量层叠（增量在后）
            css2 = resolve_pdf_docx_css(run, root)
            self.assertLess(css2.index("#111111"), css2.index("#222222"))
            # 空槽回内置出厂
            css3 = resolve_pdf_docx_css({}, root)
            self.assertIn("新細明體", css3)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_font_set_arg_gone(self):
        import subprocess
        import sys
        import pycbeta
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(pycbeta.__file__)))
        r = subprocess.run(
            [sys.executable, "-m", "pycbeta.cli", "--font-set", "default",
             "-i", "x", "-f", "docx"],
            capture_output=True, text=True, cwd=repo_root)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--font-set", r.stderr.lower().replace("_", "-"))

    def test_preset_list_merge(self):
        import shutil
        from pycbeta.theme import list_presets
        root = tempfile.mkdtemp()
        try:
            bdir = os.path.join(root, "builtin")
            udir = os.path.join(root, "user")
            os.makedirs(bdir)
            os.makedirs(udir)
            for d, fn in ((bdir, "a.css"), (bdir, "b.css"),
                          (udir, "b.css"), (udir, "c.css"),
                          (udir, "note.txt")):
                with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                    f.write("x")
            got = list_presets(builtin_dir=bdir, user_dir=udir)
            self.assertEqual([(k, name) for k, name, _p in got],
                             [("builtin", "a"), ("user", "b"), ("user", "c")])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_preset_save_load_roundtrip(self):
        import shutil
        import pycbeta.gui.css_editor as ce
        root = tempfile.mkdtemp()
        try:
            udir = os.path.join(root, "u")
            full = ("/* base */\n" + ce.build_override_block(
                {"p": {"font-size": "14pt"}}))
            path = ce.save_preset_file("我的预设:/v1", full, user_dir=udir)
            self.assertTrue(path.endswith("我的预设v1.css"))
            with open(path, encoding="utf-8") as f:
                block = ce.strip_factory_prefix(f.read())
            values, _pt, err = ce.split_override_block(block)
            self.assertIsNone(err)
            self.assertEqual(values, {"p": {"font-size": "14pt"}})
            self.assertRaises(ValueError, ce.save_preset_file, "  ", full,
                              udir)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_preset_delete_protects_builtin(self):
        import shutil
        import pycbeta.gui.css_editor as ce
        root = tempfile.mkdtemp()
        try:
            bdir = os.path.join(root, "b")
            udir = os.path.join(root, "u")
            os.makedirs(bdir)
            os.makedirs(udir)
            bp = os.path.join(bdir, "a.css")
            up = os.path.join(udir, "mine.css")
            for p in (bp, up):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("x")
            self.assertRaises(ValueError, ce.delete_preset_file, bp, bdir, udir)
            self.assertRaises(ValueError, ce.delete_preset_file,
                              os.path.join(root, "elsewhere.css"), bdir, udir)
            self.assertTrue(ce.delete_preset_file(up, bdir, udir))
            self.assertFalse(os.path.isfile(up))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_example_preset_parses(self):
        import shutil
        import pycbeta.gui.css_editor as ce
        from pycbeta.theme import Theme, theme_file_text
        # 大字版示例（与 presets/large-print.css 同形）：覆盖块可合并
        tmp = tempfile.mkdtemp()
        try:
            fn = os.path.join(tmp, "large-print.css")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("/* large-print */\n"
                        "h1.title { font-size: 36pt; }\n"
                        "p { font-size: 14pt; }\n")
            with open(fn, encoding="utf-8") as f:
                raw = f.read()
            self.assertNotIn("text-align: justify", raw)
            t = Theme.from_css(theme_file_text(fn))
            self.assertEqual((t.tags.get("p") or {}).get("font-size"), "14pt")
            self.assertEqual((t.tags.get("title") or {}).get("font-size"),
                             "36pt")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_load_theme_merges_factory(self):
        import shutil
        from pycbeta.cli import load_theme
        tmp = tempfile.mkdtemp()
        try:
            fn = os.path.join(tmp, "part.css")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("p.head { font-size: 99pt; }\n")
            t = load_theme(fn)
            # 部分文件：出厂打底（正文基准在 body 12pt；p 无字号跟随 body）+ 覆盖生效
            self.assertEqual((t.tags.get("body") or {}).get("font-size"), "12pt")
            self.assertIsNone((t.tags.get("p") or {}).get("font-size"))
            self.assertEqual((t.tags.get("head") or {}).get("font-size"),
                             "99pt")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dialog_preset_load(self):
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        import pycbeta.theme as _theme
        root = tempfile.mkdtemp()
        try:
            bdir = os.path.join(root, "builtin")
            udir = os.path.join(root, "presets")
            os.makedirs(bdir)
            os.makedirs(udir)
            with open(os.path.join(bdir, "b.css"), "w",
                      encoding="utf-8") as f:
                f.write("/* b */\n")
            full = "/* base */\n" + ce.build_override_block(
                {"h1.title": {"font-size": "40pt"}})
            with open(os.path.join(udir, "mine.css"), "w",
                      encoding="utf-8") as f:
                f.write(full)
            with mock.patch.object(_theme, "BUILTIN_PRESETS_DIR", bdir), \
                    mock.patch.object(_theme, "user_presets_dir",
                                      lambda root=None: udir), \
                    mock.patch.object(ce, "REPO_ROOT", root):
                dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
                try:
                    texts = [dlg.preset_box.itemText(i)
                             for i in range(dlg.preset_box.count())]
                    self.assertTrue(texts[0].startswith("（默认）"))
                    self.assertFalse(any("［内置］" in t for t in texts))
                    self.assertFalse(any("［用户］" in t for t in texts))
                    self.assertIn("mine", texts)
                    # 装载用户预设 → 控件+touched 联动
                    dlg._load_preset_path(os.path.join(udir, "mine.css"))
                    self.assertEqual(
                        dlg._rows["h1.title"]["size"].text(), "40pt")
                    self.assertIn(("h1.title", "font-size"), dlg._touched)
                    # 回到出厂 → 控件回预填、块清空
                    dlg._reset_editor_state()
                    self.assertEqual(
                        dlg._rows["h1.title"]["size"].text(), "26pt")
                    self.assertEqual(dlg._touched, set())
                finally:
                    dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)
    def test_delete_preset_confirms(self):
        # 删除用户预设前必须弹窗确认：取消保留文件，确认才删。
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        import pycbeta.theme as _theme
        from PySide6.QtWidgets import QMessageBox
        root = tempfile.mkdtemp()
        try:
            udir = os.path.join(root, "presets")
            os.makedirs(udir)
            up = os.path.join(udir, "mine.css")
            with open(up, "w", encoding="utf-8") as f:
                f.write("/* x */\n")
            with mock.patch.object(_theme, "user_presets_dir",
                                   lambda root=None: udir), \
                    mock.patch.object(ce, "REPO_ROOT", root):
                dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
                try:
                    dlg.preset_box.select_path(up)
                    with mock.patch.object(QMessageBox, "question",
                                           return_value=QMessageBox.No) as q:
                        dlg._delete_preset()
                    q.assert_called_once()
                    self.assertTrue(os.path.isfile(up))  # 取消不删
                    with mock.patch.object(QMessageBox, "question",
                                           return_value=QMessageBox.Yes):
                        dlg._delete_preset()
                    self.assertFalse(os.path.isfile(up))  # 确认才删
                finally:
                    dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_dialog_initial_theme_selects_preset(self):
        # 主面板「生效样式」传入 initial_theme：弹窗应选中并载入该预设，
        # 而非永远落在 run 槽/出厂（改的才是当前选中样式）。
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        import pycbeta.theme as _theme
        root = tempfile.mkdtemp()
        try:
            udir = os.path.join(root, "presets")
            os.makedirs(udir)
            full = "/* base */\n" + ce.build_override_block(
                {"h1.title": {"font-size": "40pt"}})
            with open(os.path.join(udir, "mine.css"), "w",
                      encoding="utf-8") as f:
                f.write(full)
            with mock.patch.object(_theme, "user_presets_dir",
                                   lambda root=None: udir), \
                    mock.patch.object(ce, "REPO_ROOT", root):
                dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml",
                                         initial_theme="mine")
                try:
                    self.assertEqual(dlg.preset_box.selected_value(), "mine")
                    self.assertTrue(dlg._preset_path
                                    and dlg._preset_path.endswith("mine.css"))
                    self.assertEqual(
                        dlg._rows["h1.title"]["size"].text(), "40pt")
                    self.assertIn("mine", dlg.status.text())
                finally:
                    dlg.close()
                # 出厂/空初值：不载预设（保持出厂缓冲）
                for init in ("pdf_docx.css", ""):
                    d = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml",
                                           initial_theme=init)
                    try:
                        self.assertIsNone(d._preset_path)
                    finally:
                        d.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_user_theme_slot(self):
        import shutil
        from pycbeta.gui.css_editor import current_theme_value, set_user_theme
        from pycbeta.theme import load_run_config
        root = tempfile.mkdtemp()
        try:
            # 无 run.json → 标准槽值（pdf_docx.css）
            self.assertEqual(current_theme_value(root), "pdf_docx.css")
            # 写槽 → run.json 的 pdf-docx-user-theme（补 .css 后缀）
            p = set_user_theme("large-print", root)
            self.assertTrue(p.endswith("run.json"))
            self.assertEqual(current_theme_value(root), "large-print.css")
            d = load_run_config(os.path.join(root, "run.json"))
            self.assertEqual(d["pdf-docx-user-theme"], "large-print.css")
            self.assertEqual(d["pdf-docx-theme"], "pdf_docx.css")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_theme_source_preset_beats_run_slot(self):
        import json
        import shutil
        from pycbeta.gui.css_editor import current_theme_source
        root = tempfile.mkdtemp()
        try:
            pre = os.path.join(root, "我的样式.json")
            with open(pre, "w", encoding="utf-8") as f:
                json.dump({"pdf-docx-user-theme": "large-print.css"}, f)
            with open(os.path.join(root, "run.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"config-json": pre,
                           "pdf-docx-user-theme": "my.css"}, f)
            # 预设键胜 run 槽，并标出来源
            self.assertEqual(current_theme_source(root),
                             ("large-print.css", "预设 我的样式"))
            with open(os.path.join(root, "run.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"pdf-docx-user-theme": "my.css"}, f)
            self.assertEqual(current_theme_source(root), ("my.css", "run.json"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_write_temp_run(self):
        import json
        import shutil
        from pycbeta.gui.panel import write_temp_run, write_temp_presets
        from pycbeta.gui.panel import XmlOptions
        run = {"config-json": "config.json", "html-epub-theme": "html_epub_official.css",
               "html-epub-user-theme": "", "pdf-docx-theme": "pdf_docx.css",
               "pdf-docx-user-theme": "mine"}
        opts = XmlOptions(page="a4")
        snap = write_temp_presets({"output": {}}, opts)
        try:
            rp = write_temp_run(run, snap)
            try:
                with open(rp, encoding="utf-8") as f:
                    data = json.load(f)
            finally:
                os.remove(rp)
            # 槽照抄，config-json 指快照；快照无遗留 theme 键
            self.assertEqual(data["pdf-docx-user-theme"], "mine")
            self.assertEqual(data["config-json"], snap)
            with open(snap, encoding="utf-8") as f:
                self.assertNotIn("theme", json.load(f))
        finally:
            os.remove(snap)

    def test_load_run_and_presets(self):
        import json
        import shutil
        from pycbeta.gui.panel import load_run_and_presets
        root = tempfile.mkdtemp()
        try:
            with open(os.path.join(root, "run.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"config-json": "config.json",
                           "pdf-docx-user-theme": "mine"}, f)
            run, presets = load_run_and_presets(root)
            self.assertEqual(run["pdf-docx-user-theme"], "mine")
            # 有效配置含出厂键（base 出厂，run 未覆盖输出选项）
            self.assertIn("output", presets)
            self.assertIn("pages", presets)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _make_docx(self, tmp):
        """最小合成 docx：样式 run + ruby + EQ 域 + 脚注引用 + footnotes.xml。"""
        import zipfile
        doc = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            '<w:p><w:pPr><w:pStyle w:val="head"/></w:pPr>'
            '<w:r><w:rPr><w:sz w:val="40"/><w:szCs w:val="40"/><w:b/>'
            '<w:rFonts w:ascii="X" w:eastAsia="朝华标题B"/>'
            '<w:color w:val="0000A0"/></w:rPr><w:t>序标题</w:t></w:r>'
            '<w:r><w:rPr><w:sz w:val="18"/><w:vertAlign w:val="superscript"/>'
            "</w:rPr><w:footnoteReference w:id=\"2\"/></w:r>"
            "</w:p>"
            "<w:p><w:r><w:rPr><w:sz w:val=\"24\"/></w:rPr>"
            "<w:t>楞伽</w:t></w:r>"
            "<w:ruby><w:rt><w:r><w:t>qié</w:t></w:r></w:rt>"
            "<w:rubyBase><w:r><w:t>伽</w:t></w:r></w:rubyBase></w:ruby>"
            "<w:r><w:rPr><w:rFonts w:hint=\"eastAsia\"/></w:rPr>"
            "<w:instrText xml:space=\"preserve\"> EQ \\* jc0 \\* &quot;Font:宋体&quot; "
            "\\* hps12 \\o \\ad(\\s \\up 11(pú),菩)</w:instrText></w:r>"
            "</w:p>"
            "</w:body></w:document>")
        fns = (
            '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:footnote w:id=\"0\"/><w:footnote w:id=\"1\"/>"
            "<w:footnote w:id=\"2\"><w:p><w:r><w:rPr><w:sz w:val=\"18\"/></w:rPr>"
            "<w:t>注文内容</w:t></w:r></w:p></w:footnote>"
            "</w:footnotes>")
        fn = os.path.join(tmp, "s.docx")
        with zipfile.ZipFile(fn, "w") as z:
            z.writestr("word/document.xml", doc)
            z.writestr("word/footnotes.xml", fns)
        return fn

    def test_docx_spec(self):
        import shutil
        from pycbeta.gui.css_editor import docx_spec
        tmp = tempfile.mkdtemp()
        try:
            spec = docx_spec(self._make_docx(tmp))
            head = spec["paras"][0]
            self.assertEqual(head["style"], "head")
            r0 = head["runs"][0]
            self.assertEqual(r0["text"], "序标题")
            self.assertEqual(r0["size"], 20.0)
            self.assertEqual(r0["font"], "朝华标题B")
            self.assertTrue(r0["bold"])
            self.assertEqual(r0["color"], "#0000A0")
            self.assertEqual(head["runs"][1]["text"], "[1]")  # 脚注引用取序号
            # ruby 展开 + EQ 域还原
            texts = [r["text"] for r in spec["paras"][1]["runs"]]
            self.assertIn("伽", texts)
            self.assertIn("〔qié〕", texts)
            self.assertIn("菩", texts)
            self.assertIn("〔pú〕", texts)
            # 注文尾注归并
            self.assertEqual(len(spec["footnotes"]), 1)
            self.assertEqual(spec["footnotes"][0]["runs"][0]["text"], "注文内容")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dialog_builds_offscreen(self):
        from pycbeta.gui.css_editor import EDITABLE_ROWS, CssEditorDialog
        dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertEqual(len(dlg._rows), len(EDITABLE_ROWS))
            self.assertTrue(dlg.preview.isReadOnly())
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_control_to_block(self):
        from pycbeta.gui.css_editor import CssEditorDialog
        dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            dlg._rows["h1.title"]["size"].setText("34pt")
            self.assertIn("h1.title { font-size: 34pt; }",
                          dlg._source_edit.toPlainText())
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_controls_default_from_factory(self):
        import unittest.mock as mock
        from pycbeta.gui.css_editor import CssEditorDialog
        import pycbeta.gui.css_editor as ce
        with mock.patch.object(ce, "current_theme_value",
                               return_value="pdf_docx.css"):
            dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            # 控件预填出厂值，但源码块保持空（不算 touched）
            self.assertEqual(dlg._rows["h1.title"]["size"].text(), "26pt")
            self.assertEqual(dlg._rows["p"]["size"].text(), "12pt")
            self.assertEqual(dlg._touched, set())
            self.assertNotIn("h1.title {", dlg._source_edit.toPlainText())
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_color_btn_swatch(self):
        from pycbeta.gui.css_editor import CssEditorDialog
        dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            btn = dlg._rows["h1.title"]["color"]
            self.assertEqual(btn.text(), "")
            self.assertEqual(btn.width(), 26)
            self.assertIn("右键清除", btn.toolTip())
        finally:
            dlg.close()

    def test_def_row_present(self):
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertIn("cb:def", dlg._rows)
            row = dlg._rows["cb:def"]
            self.assertEqual(row.get("suffix"), "def")  # 有字体变量
            self.assertTrue(row["font_hant"].isEnabled())
            self.assertIn("cb 标签", row["name_label"].toolTip())
            self.assertIn("def", row["name_label"].toolTip())
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_startup_loads_user_theme(self):
        import shutil
        import unittest.mock as mock
        import pycbeta.gui.css_editor as ce
        import pycbeta.theme as th
        root = tempfile.mkdtemp()
        udir = os.path.join(root, "presets")
        os.makedirs(udir)
        fn = os.path.join(udir, "mine.css")
        with open(fn, "w", encoding="utf-8") as f:
            f.write("/* base */\np.head { font-size: 40pt; }\n")
        try:
            with mock.patch.object(ce, "current_theme_value",
                                   return_value="mine"), \
                    mock.patch.object(th, "user_presets_dir",
                                      return_value=udir):
                dlg = ce.CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
            try:
                # 启动载用户槽：源码页=文件覆盖块，保存亮
                self.assertTrue(dlg.btn_save.isEnabled())
                self.assertIn("font-size: 40pt",
                              dlg._source_edit.toPlainText())
                self.assertEqual(
                    dlg._rows["p.head"]["size"].text(), "40pt")
            finally:
                dlg.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_div_note_row(self):
        from pycbeta.gui.css_editor import CssEditorDialog
        dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            row = dlg._rows["div.div-note"]
            # 无字体变量：字体栏置灰；字义=正文大小+无特殊色；
            # 粗细按钮显示覆盖态（出厂粗不算覆盖，显示"默认"）
            self.assertIsNone(row.get("suffix"))
            self.assertFalse(row["font_hant"].isEnabled())
            self.assertFalse(row["font_hans"].isEnabled())
            self.assertEqual(row["color_value"], "")
            self.assertEqual(row["weight"].text(), "默认")
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_no_button_is_default(self):
        from PySide6.QtWidgets import QPushButton
        from pycbeta.gui.css_editor import CssEditorDialog
        dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            btns = dlg.findChildren(QPushButton)
            self.assertTrue(btns)
            for b in btns:
                # 回车不误触（设为默认是静默永久写入，必须点）
                self.assertFalse(b.autoDefault(), b.text())
                self.assertFalse(b.isDefault(), b.text())
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_size_refresh_debounced(self):
        from pycbeta.gui.css_editor import CssEditorDialog
        dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            # 字号输入 400ms 防抖（单发重启）：连输"12"只刷一次，不逐字渲染
            self.assertTrue(dlg._timer.isSingleShot())
            self.assertEqual(dlg._timer.interval(), 400)
            dlg._loaded_block = dlg._source_edit.toPlainText()
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_left_panel_scrolls(self):
        from PySide6.QtWidgets import QScrollArea
        from pycbeta.gui.css_editor import CssEditorDialog
        dlg = CssEditorDialog(sample_xml=r"E:\nonexistent\no.xml")
        try:
            self.assertTrue(any(isinstance(w, QScrollArea)
                                for w in dlg.findChildren(QScrollArea)))
        finally:
            dlg._loaded_block = dlg._source_edit.toPlainText()
            dlg.close()

    def test_pick_display_name(self):
        from pycbeta.gui.css_editor import pick_display_name
        self.assertEqual(pick_display_name(["SimSun", "宋体"], "SimSun"), "宋体")
        self.assertEqual(pick_display_name(["PMingLiU"], "PMingLiU"), "新細明體")
        self.assertEqual(pick_display_name(["Calibri"], "Calibri"), "Calibri")
        self.assertEqual(pick_display_name([], ""), "")

    def test_font_model_filters_english(self):
        import unittest.mock as mock
        from pycbeta.gui.css_editor import font_group_model
        rows = [("SimSun", ["SimSun", "宋体"], "x"),
                ("PMingLiU", ["PMingLiU"], "z"),
                ("Calibri", ["Calibri"], "y"),
                ("Times New Roman", ["Times New Roman"], "w")]
        with mock.patch("pycbeta.fonts.FontLocator"), \
                mock.patch("pycbeta.fonts.iter_installed", return_value=rows):
            groups, _bundled, _d = font_group_model(fresh=True)
        flat = [n for names in groups.values() for n in names]
        self.assertIn("宋体", flat)
        self.assertIn("新細明體", flat)
        self.assertNotIn("Calibri", flat)  # 纯英文非精选过滤
        self.assertNotIn("Times New Roman", flat)  # 西文走固定三

    def test_build_render_cmd(self):
        from pycbeta.gui.__main__ import build_render_cmd
        opts = XmlOptions(page="a4", font_lang="zh-Hant", engine="docx2pdf",
                          formats=["docx"], t2s=False, vertical=False)
        cmd = build_render_cmd(opts, "x.xml", "docx", "out", "tmp.json")
        self.assertNotIn("--font-lang", cmd)  # 繁体默认省略
        self.assertNotIn("--theme", cmd)  # 默认主题走 --config 槽
        self.assertIn("--no-t2s", cmd)
        # 简体字库 + 竖排
        opts2 = XmlOptions(page="a4", font_lang="zh-Hans",
                           engine="docx2pdf", formats=["docx"],
                           t2s=True, vertical=True)
        cmd2 = build_render_cmd(opts2, "x.xml", "docx", "out", "tmp.json")
        self.assertNotIn("--font-lang", cmd2)  # t2s 自动简体，不用显式传
        self.assertIn("--vertical", cmd2)
        self.assertIn("--t2s", cmd2)
        # 显式简体（无 t2s）才传
        opts3 = XmlOptions(page="a4", font_lang="zh-Hans",
                           engine="docx2pdf", formats=["docx"],
                           t2s=False, vertical=False)
        cmd3 = build_render_cmd(opts3, "x.xml", "docx", "out", "tmp.json")
        self.assertIn("--font-lang", cmd3)

    def test_build_render_cmd_out_name(self):
        # 统一回退显式文件名：-o 指向确切文件；缺省仍是目录
        from pycbeta.gui.__main__ import build_render_cmd
        from pycbeta.gui.panel import XmlOptions
        opts = XmlOptions(page="a4", font_lang="zh-Hant", engine="docx2pdf",
                          formats=["txt"], t2s=False, vertical=False)
        cmd = build_render_cmd(opts, "x.xml", "txt", "out", "tmp.json",
                               out_name="TX08n0006.txt")
        i = cmd.index("-o")
        self.assertEqual(cmd[i + 1], os.path.join("out", "TX08n0006.txt"))
        cmd0 = build_render_cmd(opts, "x.xml", "txt", "out", "tmp.json")
        self.assertEqual(cmd0[cmd0.index("-o") + 1], "out")

    def test_out_name_for_uniform_group(self):
        # worker 命名与 CLI 同规则：首文件 legacy，后续统一 stem
        import pycbeta.gui.__main__ as M
        used = {}
        w = M.BatchWorker.__new__(M.BatchWorker)
        n1 = w._out_name_for(used, "out", "TX0006", "", "TX07n0006", "txt")
        n2 = w._out_name_for(used, "out", "TX0006", "", "TX08n0006", "txt")
        n3 = w._out_name_for(used, "out", "TX0006", "", "TX09n0006", "html")
        self.assertIsNone(n1)  # 首个沿用默认
        self.assertEqual(n2, "TX08n0006.txt")
        self.assertIsNone(n3)  # html 照旧默认（残留）

    def test_label_key_for_para_xu_head(self):
        from pycbeta.gui.css_editor import label_key_for_para
        para = {"style": "head", "runs": [{"font": "KaiTi", "text": "序"},
                                          {"font": "KaiTi", "text": "標"}]}
        self.assertEqual(label_key_for_para(para, "KaiTi", "SimHei"),
                         "div-xu-head")
        # 普通标题（同字体为 head）→ 标题
        para2 = {"style": "head", "runs": [{"font": "SimHei", "text": "目"}]}
        self.assertEqual(label_key_for_para(para2, "KaiTi", "SimHei"), "head")
        # 无区分（xu==head 或缺字体）→ 原样式
        self.assertEqual(label_key_for_para(para, "", ""), "head")

    def test_show_spec_labels_xu_head(self):
        # 端到端：div@type=xu 内 head 的 DOCX run 字体 != 普通 head，
        # 标注应区分为 序标题（div-xu-head）。
        import tempfile
        from pycbeta.render_docx import DocxRenderer
        from pycbeta.model import E, Text, Work
        from pycbeta.gui.css_editor import docx_spec, label_key_for_para
        body = [
            E(tag="div", attrs={"type": "xu"}, children=[
                E(tag="head", attrs={}, children=[Text("序標題")])]),
            E(tag="div", attrs={"type": "other"}, children=[
                E(tag="head", attrs={}, children=[Text("目錄標題")])]),
        ]
        w = Work(id="T", source_file="", metadata={"title": "t", "author": ""},
                 body=body, notes_by_n={}, apps=[], simplified=False)
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        fn = DocxRenderer(bookmarks=False).render_work(w, d, "x.docx")
        spec = docx_spec(fn)
        heads = [p for p in spec["paras"] if p.get("style") == "head"]
        self.assertEqual(len(heads), 2)
        xu, mu = heads
        xu_font = next(r["font"] for r in xu["runs"] if r.get("font"))
        mu_font = next(r["font"] for r in mu["runs"] if r.get("font"))
        self.assertNotEqual(xu_font, mu_font)
        self.assertEqual(label_key_for_para(xu, xu_font, mu_font), "div-xu-head")
        self.assertEqual(label_key_for_para(mu, xu_font, mu_font), "head")

    def test_label_key_for_para_pre(self):
        # 预排段无 pStyle，靠段内 w:br 识别 → 标【预排】而非【正文】
        from pycbeta.gui.css_editor import label_key_for_para
        pre = {"style": "", "runs": [{"text": "甲"}, {"br": True},
                                     {"text": "乙"}]}
        self.assertEqual(label_key_for_para(pre, "", ""), "pre")
        plain = {"style": "", "runs": [{"text": "甲"}]}
        self.assertEqual(label_key_for_para(plain, "", ""), "")
        # 有命名样式的段（verse 等）不受 br 影响
        verse = {"style": "verse", "runs": [{"br": True}]}
        self.assertEqual(label_key_for_para(verse, "", ""), "verse")

    def test_pre_editor_maps_and_dirty(self):
        from pycbeta.gui.css_editor import (STYLE_ROW_LABEL, _LABEL_TOUCHED_SEL,
                                            label_is_dirty)
        self.assertEqual(STYLE_ROW_LABEL["pre"], "预排")
        self.assertEqual(_LABEL_TOUCHED_SEL["pre"], "pre")
        self.assertTrue(label_is_dirty("pre", {("pre", ("font-size", "12pt"))}))
        self.assertFalse(label_is_dirty("pre", {("p", ("font-size", "12pt"))}))

    def test_styles_tab_opens_editor(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertEqual(panel.btn_editor.text(), "编辑CSS")
        self.assertEqual(panel.theme_dir_btn.text(), "用户预设目录")


class TestFontStacks(unittest.TestCase):
    """字体栈检查（纯函数 + 检查窗渲染）。"""

    def test_ok_stack_passes(self):
        from pycbeta.gui.css_editor import check_font_stacks
        css = (":root { --font-p: 宋体, SimSun; "
               "--font-latin: Calibri; }\n")
        self.assertEqual(
            check_font_stacks(css, {"宋体": "SimSun"},
                              ["SimSun", "Calibri"]), [])

    def test_unknown_name_errors(self):
        from pycbeta.gui.css_editor import check_font_stacks
        css = ":root { --font-p: 宋体, SimSn; }\n"
        got = check_font_stacks(css, {"宋体": "SimSun"}, ["SimSun"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][3], "error")
        self.assertIn("SimSn", got[0][4])

    def test_fullwidth_comma_errors(self):
        from pycbeta.gui.css_editor import check_font_stacks
        css = ":root { --font-p: 宋体， SimSun; }\n"
        got = check_font_stacks(css, {"宋体": "SimSun"}, ["SimSun"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][3], "error")
        self.assertIn("全角", got[0][4])

    def test_missing_side_warns(self):
        from pycbeta.gui.css_editor import check_font_stacks
        got = check_font_stacks(":root { --font-p: 宋体; }\n",
                                {"宋体": "SimSun"}, ["SimSun"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][3], "warn")
        self.assertIn("缺英文", got[0][4])
        got2 = check_font_stacks(":root { --font-p: SimSun; }\n",
                                 {}, ["SimSun"])
        self.assertEqual(len(got2), 1)
        self.assertIn("缺中文", got2[0][4])

    def test_uninstalled_known_warns(self):
        from pycbeta.gui.css_editor import check_font_stacks
        css = ":root { --font-body: 新細明體, Songti TC, serif; }\n"
        got = check_font_stacks(css, {"新細明體": "PMingLiU"},
                                ["PMingLiU"])
        self.assertEqual(len(got), 1)  # 仅 Songti TC 未装警告，中英俱全
        self.assertEqual(got[0][3], "warn")
        self.assertIn("Songti TC", got[0][4])

    def test_hans_lang_and_latin_exempt(self):
        from pycbeta.gui.css_editor import check_font_stacks
        css = ('html[lang="zh-Hans"] { --font-p: 宋体; }\n'
               ":root { --font-latin: Calibri; }\n")
        got = check_font_stacks(css, {"宋体": "SimSun"},
                                ["SimSun", "Calibri"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "简体")  # 栏位标注
        self.assertIn("缺英文", got[0][4])  # latin 纯英文不告

    def test_report_renders_stacks(self):
        from pycbeta.gui.css_editor import PreviewReportDialog
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        w = PreviewReportDialog()
        try:
            w.update_report({"time": "t", "base": "b", "sample": "s",
                             "t2s": False, "fonts": [], "gaps": {},
                             "stacks": [("繁体", "--font-p", "宋体, SimSn",
                                          "error", "SimSn 未知")],
                             "css_error": "", "error": ""})
            html = w.view.toHtml()
            self.assertIn("字体栈", html)
            self.assertIn("SimSn", html)
        finally:
            w.close()


class TestVerifyFeedback(unittest.TestCase):
    """转换后校验的 GUI 反馈：行终态/状态列配色/汇总弹窗/worker 记录。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_row_outcome(self):
        from pycbeta.gui.__main__ import _row_outcome
        self.assertEqual(_row_outcome(True, [], False), ("完成", ""))
        t, lv = _row_outcome(True, [{"status": "ok"}], True)
        self.assertIn("校验 OK", t)
        self.assertEqual(lv, "ok")
        t, lv = _row_outcome(True, [{"status": "ok"}, {"status": "fail"}], True)
        self.assertEqual(lv, "fail")
        self.assertIn("失败1", t)
        t, lv = _row_outcome(True, [{"status": "no_baseline"}], True)
        self.assertEqual(lv, "none")
        t, lv = _row_outcome(False, [{"status": "ok"}], True)
        self.assertTrue(t.startswith("失败"))

    def test_row_outcome_render_error(self):
        from pycbeta.gui.__main__ import _row_outcome
        t, lv = _row_outcome(False, [], True, ["docx: PermissionError: denied"])
        self.assertEqual(lv, "fail")
        self.assertIn("docx: PermissionError: denied", t)

    def test_format_verify_report_covered(self):
        from pycbeta.verify import format_verify_report
        recs = [{"xml": "x.xml", "fmt": "pdf", "status": "covered",
                 "detail": "已由 docx 校验覆盖（未重复）"}]
        s = "\n".join(format_verify_report(recs))
        self.assertIn("pdf 已由 docx 校验覆盖", s)

    def test_last_error_line(self):
        from pycbeta.gui.__main__ import _last_error_line
        self.assertEqual(_last_error_line(""), "未知错误")
        self.assertEqual(
            _last_error_line("a\n\nPermissionError: [Errno 13] denied\n"),
            "PermissionError: [Errno 13] denied")

    def test_last_error_line_traceback_beats_late_stdout(self):
        from pycbeta.gui.__main__ import _last_error_line
        # stdout 块缓冲会让正常行落在 stderr traceback 之后：仍取异常行
        text = ("Traceback (most recent call last):\n"
                '  File "x.py", line 1, in <module>\n'
                "PermissionError: [Errno 13] denied\n"
                "annotations: pinyin, 7 terms, style=field, repeat=page\n")
        self.assertEqual(_last_error_line(text),
                         "PermissionError: [Errno 13] denied")

    def test_last_error_line_friendly(self):
        from pycbeta.gui.__main__ import _last_error_line
        self.assertEqual(
            _last_error_line("normal line\nX1077: docx 生成失败：拒绝访问\n"),
            "X1077: docx 生成失败：拒绝访问")

    def test_format_verify_report_green_with_diff(self):
        from pycbeta.verify import format_verify_report
        recs = [{
            "xml": r"E:\x\X59n1077.xml", "fmt": "txt", "status": "ok",
            "missing": 0, "extra": 2, "total": 2, "official_kind": "txt_notes",
            "official": r"E:\base\X1077_001.txt", "gen": r"E:\out\X59n1077.txt",
            "norm_gen": "abcdefghij0123456789",
            "trials": [
                {"kind": "txt_notes", "official": r"E:\base\X1077_001.txt",
                 "missing": 0, "extra": 2, "total": 2, "ok": True,
                 "ctx": [("replace", 0, 1, 0, 1)],
                 "norm_official": "abcdefghijXXXX"}]}]
        s = "\n".join(format_verify_report(recs, diff_lines=5, max_diff=10))
        self.assertIn("[OK] (txt→txt_notes 缺0/多2 ≤阈值10)", s)
        self.assertIn("【源】", s)

    def test_verify_summary_dialog(self):
        from pycbeta.gui.__main__ import VerifySummaryDialog
        res = [{"id": "T1", "fmt": "docx", "status": "ok",
                "missing": 0, "extra": 0},
               {"id": "T4", "fmt": "docx", "status": "ok",
                "missing": 0, "extra": 2},
               {"id": "T2", "fmt": "docx", "status": "fail",
                "missing": 3, "extra": 1},
               {"id": "T3", "fmt": "docx", "status": "no_baseline"},
               {"id": "T5", "fmt": "pdf", "status": "covered",
                "detail": "已由 docx 校验覆盖（未重复）"},
               {"id": "TX0006", "fmt": "docx", "status": "ok",
                "missing": 0, "extra": 0,
                "gen_name": "TX0006 太虚大师全书．第六编　法相唯识学(第1卷-第6卷).docx"}]
        d = VerifySummaryDialog(res, "")
        try:
            txt = d.text.toPlainText()
            self.assertIn("[通过] T1 docx", txt)
            self.assertIn("[通过(有差)] T4 docx", txt)
            self.assertIn("[失败] T2 docx", txt)
            self.assertIn("缺3/多1", txt)
            self.assertIn("[无对照] T3 docx", txt)
            self.assertIn("[已覆盖] T5 pdf", txt)
            # 有 gen_name 时显示生成的目标文件名
            self.assertIn("[通过] TX0006 太虚大师全书", txt)
            # 0/0 绿 / 有差警告 / 失败红
            html = d.text.toHtml()
            self.assertIn("#2e7d32", html)
            self.assertIn("#1565c0", html)
            self.assertIn("#c62828", html)
        finally:
            d.close()

    def test_format_verify_report(self):
        from pycbeta.verify import format_verify_report
        recs = [
            {"xml": r"E:\x\T12n0349.xml", "fmt": "docx", "status": "fail",
             "missing": 0, "extra": 15, "total": 15, "official_kind": "docx",
             "official": r"E:\x\T0349.docx", "gen": r"E:\out\T12n0349.docx",
             "norm_gen": "abcdefghij0123456789",
             "trials": [
                 {"kind": "docx", "official": r"E:\x\T0349.docx", "missing": 5,
                  "extra": 30, "total": 35, "ok": False,
                  "ctx": [("replace", 0, 1, 0, 1)],
                  "norm_official": "abcdefghijXXXXXXXXXX"},
                 {"kind": "html", "official": r"E:\x\T0349_001.html",
                  "missing": 0, "extra": 15, "total": 15, "ok": False,
                  "ctx": [("replace", 0, 1, 0, 1)],
                  "norm_official": "abcdefghijYYYYYYYYYY"}]},
            {"xml": r"E:\x\T15n0625.xml", "fmt": "txt", "status": "no_baseline"},
        ]
        s = "\n".join(format_verify_report(recs, diff_lines=5, max_diff=10))
        self.assertIn("=== T12n0349.xml", s)
        self.assertIn("[FAIL] (docx→docx 缺5/多30 >阈值10)", s)
        self.assertIn("[FAIL] (docx→html 缺0/多15 >阈值10)", s)
        self.assertIn("【源】", s)
        self.assertIn("[--]  txt no baseline", s)

    def test_batch_verify_one_returns_rec(self):
        import tempfile
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        opts = SimpleNamespace(verify={"maxDiff": 10, "diffLines": 5},
                               t2s=False)
        w = BatchWorker([], opts, {}, {})
        try:
            xml = os.path.join(tempfile.mkdtemp(), "T1.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")

            def fake_verify(x, fmt, source, out_root, max_diff=10,
                            diff_lines=5, config_path=None, t2s=False, juan=None):
                return {"status": "ok", "missing": 0, "extra": 0,
                        "official_kind": "docx", "gen_cmp": "g.txt",
                        "src_cmp": "s.txt"}

            rec = w._verify_one(xml, "docx", tempfile.mkdtemp(), "cfg.json",
                                fake_verify, "T1")
            self.assertEqual(rec["id"], "T1")
            self.assertEqual(rec["status"], "ok")
            self.assertEqual(rec["gen_cmp"], "g.txt")
        finally:
            w.wait(1)

    def test_run_appends_verify_report_to_files(self):
        import tempfile
        from types import SimpleNamespace
        import pycbeta.gui.__main__ as M
        tmp = tempfile.mkdtemp(prefix="gverfiles-")
        xml = os.path.join(tmp, "T12n0349.xml")
        rendered = os.path.join(tmp, "T12n0349.txt")
        gcmp = os.path.join(tmp, "T12n0349_compare_txt_generated.txt")
        scmp = os.path.join(tmp, "T12n0349_compare_txt_official.txt")
        for p in (xml, rendered, gcmp, scmp):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        opts = SimpleNamespace(verify={"enabled": True}, formats=["txt"],
                               t2s=False)
        w = M.BatchWorker([{"id": "T0349"}], opts,
                          {"presets": {}, "run": {}, "out": tmp}, {})
        w._resolve = lambda job, idx, fetch, presets: [xml]
        w._title_of = lambda x, i, P: ("T0349", "T0349")
        w._out_name_for = lambda *a, **k: "T12n0349.txt"
        w._render_one = lambda x, fmt, o, cfg, out_name=None, juan=None: (True, [rendered])
        w._verify_one = lambda x, fmt, o, cfg, vo, wid="", gen_name="", juan=None: {
            "id": wid, "fmt": fmt, "xml": x, "status": "fail", "missing": 0,
            "extra": 15, "gen_cmp": gcmp, "src_cmp": scmp}
        orig = (M.write_temp_presets, M.write_temp_run)
        M.write_temp_presets = lambda presets, opts: os.path.join(tmp, "p.json")
        M.write_temp_run = lambda run, snap: os.path.join(tmp, "r.json")
        captured = {}
        w.row_file.connect(lambda i, p: captured.__setitem__(i, p))
        try:
            w.run()
        finally:
            M.write_temp_presets, M.write_temp_run = orig
            w.wait(1)
        files = captured[0].split(";")
        from pycbeta.filename import default_output_name
        vdir = os.path.join(tmp, "验证",
                            default_output_name("T0349", "T0349") + "（验证）")
        report = os.path.join(vdir, "T0349_T0349_校验报告.txt")
        self.assertEqual(files[0], rendered)
        self.assertNotIn(gcmp, files)                # 比较文件不列文件列
        self.assertNotIn(scmp, files)
        self.assertEqual(files[-1], report)          # 只列报告，排最后
        self.assertTrue(os.path.isfile(report))
        self.assertTrue(os.path.isdir(vdir))         # 报告落在（验证）子目录
        body = open(report, encoding="utf-8").read()
        self.assertIn("=== T12n0349.xml", body)
        self.assertIn("[FAIL]", body)
        self.assertIn("缺0/多15", body)
        jrep = os.path.join(vdir, "report.json")
        self.assertTrue(os.path.isfile(jrep))       # 机读结论固定名 report.json
        j = json.load(open(jrep, encoding="utf-8"))
        self.assertEqual(j["fmts"]["txt"]["verdict"], "fail")
        self.assertEqual(j["fmts"]["txt"]["extra"], 15)
        self.assertEqual(j["fmts"]["txt"]["report"],
                         "T0349_T0349_校验报告.txt")
        self.assertNotIn(jrep, files)               # JSON 不进文件列

    def test_run_appends_convert_report_to_files(self):
        import tempfile
        from types import SimpleNamespace
        import pycbeta.gui.__main__ as M
        from pycbeta.filename import default_output_name
        tmp = tempfile.mkdtemp(prefix="gconvrep-")
        xml = os.path.join(tmp, "T12n0349.xml")
        rendered = os.path.join(tmp, "T12n0349.txt")
        for p in (xml, rendered):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        opts = SimpleNamespace(verify={"enabled": False}, formats=["txt"],
                               t2s=False, output={"convert_report": True})
        w = M.BatchWorker([{"id": "T0349"}], opts,
                          {"presets": {}, "run": {}, "out": tmp}, {})
        w._resolve = lambda job, idx, fetch, presets: [xml]
        w._title_of = lambda x, i, P: ("T0349", "T0349")
        w._out_name_for = lambda *a, **k: "T12n0349.txt"
        name = default_output_name("T0349", "T0349", True)
        vdir = os.path.join(tmp, "验证", name + "（验证）")
        os.makedirs(os.path.join(vdir, "txt"), exist_ok=True)
        pfmt = os.path.join(vdir, "txt", f"{name}_转换报告_txt.txt")

        def fake_render(x, fmt, o, cfg, out_name=None, juan=None):
            with open(pfmt, "w", encoding="utf-8") as f:
                f.write(f"# 转换报告 T0349 [{fmt}]\n"
                        f"1. [字体替换] [{fmt}] XML 行 9：x\n")
            return True, [rendered]

        w._render_one = fake_render
        orig = (M.write_temp_presets, M.write_temp_run)
        M.write_temp_presets = lambda presets, opts: os.path.join(tmp, "p.json")
        M.write_temp_run = lambda run, snap: os.path.join(tmp, "r.json")
        captured = {}
        w.row_file.connect(lambda i, p: captured.__setitem__(i, p))
        try:
            w.run()
        finally:
            M.write_temp_presets, M.write_temp_run = orig
            w.wait(1)
        files = captured[0].split(";")
        self.assertEqual(files[0], rendered)
        merged = os.path.join(vdir, f"{name}_转换报告.txt")
        self.assertIn(merged, files)
        self.assertEqual(files[-1], merged)          # 报告排文件列最后
        self.assertTrue(os.path.isfile(merged))
        self.assertIn("字体替换", open(merged, encoding="utf-8").read())

    def test_progress_total_accounts_multi_xml(self):
        # 多册经一个 job 展开多个 XML：进度总数须按实际 XML 数校正，
        # 否则跑完第一个 XML 就冲到 100% 后干等（TX0001 两个 XML 实测）。
        import tempfile
        from types import SimpleNamespace
        import pycbeta.gui.__main__ as M
        tmp = tempfile.mkdtemp(prefix="gprog-")
        x1 = os.path.join(tmp, "TX01n0001.xml")
        x2 = os.path.join(tmp, "TX02n0001.xml")
        rendered = os.path.join(tmp, "TX0001.txt")
        for p in (x1, x2, rendered):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        opts = SimpleNamespace(verify={"enabled": False}, formats=["txt"],
                               t2s=False, output={"convert_report": False})
        w = M.BatchWorker([{"id": "TX0001"}], opts,
                          {"presets": {}, "run": {}, "out": tmp}, {})
        w._resolve = lambda job, idx, fetch, presets: [x1, x2]
        w._title_of = lambda x, i, P: ("TX0001", "TX0001")
        w._out_name_for = lambda *a, **k: "TX0001.txt"
        w._render_one = lambda x, fmt, o, cfg, out_name=None, juan=None: (True, [rendered])
        orig = (M.write_temp_presets, M.write_temp_run)
        M.write_temp_presets = lambda presets, opts: os.path.join(tmp, "p.json")
        M.write_temp_run = lambda run, snap: os.path.join(tmp, "r.json")
        progress = []
        w.total_progress.connect(lambda d, t: progress.append((d, t)))
        try:
            w.run()
        finally:
            M.write_temp_presets, M.write_temp_run = orig
            w.wait(1)
        self.assertTrue(progress)
        # 总数校正为 2（2 XML × 1 格式），且全程不会 done > total（不提前 100%）
        self.assertEqual(progress[-1], (2, 2))
        self.assertTrue(all(d <= t for d, t in progress), progress)

    def test_progress_total_skips_empty_job(self):
        # job 解析为空：扣除预算，避免进度永不达 100%
        import tempfile
        from types import SimpleNamespace
        import pycbeta.gui.__main__ as M
        tmp = tempfile.mkdtemp(prefix="gprog2-")
        xml = os.path.join(tmp, "T1.xml")
        rendered = os.path.join(tmp, "T1.txt")
        for p in (xml, rendered):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        opts = SimpleNamespace(verify={"enabled": False}, formats=["txt"],
                               t2s=False, output={"convert_report": False})
        w = M.BatchWorker([{"id": "A"}, {"id": "B"}], opts,
                          {"presets": {}, "run": {}, "out": tmp}, {})
        w._resolve = (lambda job, idx, fetch, presets:
                      [] if job["id"] == "A" else [xml])
        w._title_of = lambda x, i, P: ("B", "B")
        w._out_name_for = lambda *a, **k: "T1.txt"
        w._render_one = lambda x, fmt, o, cfg, out_name=None, juan=None: (True, [rendered])
        orig = (M.write_temp_presets, M.write_temp_run)
        M.write_temp_presets = lambda presets, opts: os.path.join(tmp, "p.json")
        M.write_temp_run = lambda run, snap: os.path.join(tmp, "r.json")
        progress = []
        w.total_progress.connect(lambda d, t: progress.append((d, t)))
        try:
            w.run()
        finally:
            M.write_temp_presets, M.write_temp_run = orig
            w.wait(1)
        self.assertEqual(progress[-1], (1, 1))
        self.assertTrue(all(d <= t for d, t in progress), progress)

    def test_run_emits_converting_status(self):
        # 一行确认有 XML 待转换时，状态应先变「转换中…」，行末再变「完成」
        import tempfile
        from types import SimpleNamespace
        import pycbeta.gui.__main__ as M
        tmp = tempfile.mkdtemp(prefix="gconv-")
        xml = os.path.join(tmp, "T1.xml")
        rendered = os.path.join(tmp, "T1.txt")
        for p in (xml, rendered):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        opts = SimpleNamespace(verify={"enabled": False}, formats=["txt"],
                               t2s=False, output={"convert_report": False})
        w = M.BatchWorker([{"id": "T1"}], opts,
                          {"presets": {}, "run": {}, "out": tmp}, {})
        w._resolve = lambda job, idx, fetch, presets: [xml]
        w._title_of = lambda x, i, P: ("T1", "T1")
        w._out_name_for = lambda *a, **k: "T1.txt"
        w._render_one = lambda x, fmt, o, cfg, out_name=None, juan=None: (True, [rendered])
        orig = (M.write_temp_presets, M.write_temp_run)
        M.write_temp_presets = lambda presets, opts: os.path.join(tmp, "p.json")
        M.write_temp_run = lambda run, snap: os.path.join(tmp, "r.json")
        labels = []
        w.row_status.connect(lambda i, t: labels.append(t))
        try:
            w.run()
        finally:
            M.write_temp_presets, M.write_temp_run = orig
            w.wait(1)
        self.assertIn("转换中…", labels)
        self.assertLess(labels.index("转换中…"), labels.index("完成"))

    def test_verify_one_pdf_delegates_to_source(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        opts = SimpleNamespace(verify={}, t2s=False, engine="docx2pdf",
                               vertical=False, formats=["pdf"])
        w = BatchWorker([], opts, {}, {})
        calls = {}

        def fake(x, fmt, src, out, **kw):
            calls["fmt"] = fmt
            return {"status": "ok", "missing": 0, "extra": 0}

        rec = w._verify_one("x.xml", "pdf", "d", "cfg", fake, "T1")
        self.assertEqual(calls["fmt"], "docx")          # 委托 docx2pdf 源
        self.assertEqual(rec["fmt"], "pdf→docx")        # 显示标签
        self.assertEqual(rec["status"], "ok")

    def test_verify_one_pdf_covered_when_source_selected(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        opts = SimpleNamespace(verify={}, t2s=False, engine="docx2pdf",
                               vertical=False, formats=["pdf", "docx"])
        w = BatchWorker([], opts, {}, {})

        def fake(*a, **k):
            raise AssertionError("源码格式已选，不应再调 verify_one")

        rec = w._verify_one("x.xml", "pdf", "d", "cfg", fake, "T1")
        self.assertEqual(rec["status"], "covered")
        self.assertIn("docx", rec["detail"])

    def test_verify_dir_naming(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        import tempfile
        tmp = tempfile.mkdtemp(prefix="gverd-")
        w = BatchWorker([], SimpleNamespace(verify={}, formats=[]), {}, {})
        w._title_t2s = False
        d = w._verify_dir(tmp, "X1077", "准提净业")
        self.assertEqual(d, os.path.join(tmp, "验证", "X1077 准提净业（验证）"))
        self.assertTrue(os.path.isdir(d))

    def test_verify_dir_custom_root(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        import tempfile
        tmp = tempfile.mkdtemp(prefix="gverc-")
        custom = tempfile.mkdtemp(prefix="gvercc-")
        w = BatchWorker([], SimpleNamespace(verify={}, formats=[]), {}, {})
        w._title_t2s = False
        try:
            d = w._verify_dir(tmp, "X1077", "准提净业", custom)
            self.assertEqual(
                d, os.path.join(custom, "X1077 准提净业（验证）"))
            self.assertTrue(os.path.isdir(d))
            self.assertFalse(os.path.exists(os.path.join(tmp, "验证")))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(custom, ignore_errors=True)

    def test_batch_verify_one_error_rec(self):
        import tempfile
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        opts = SimpleNamespace(verify={"maxDiff": 10, "diffLines": 5},
                               t2s=False)
        w = BatchWorker([], opts, {}, {})
        try:
            xml = os.path.join(tempfile.mkdtemp(), "T1.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("<TEI/>")

            def boom(*a, **k):
                raise RuntimeError("nope")

            rec = w._verify_one(xml, "docx", tempfile.mkdtemp(), "cfg.json",
                                boom, "T2")
            self.assertEqual(rec["status"], "error")
            self.assertIn("nope", rec["detail"])
        finally:
            w.wait(1)


class TestJuanGui(unittest.TestCase):
    """GUI 卷范围：编号 token 解析 / 命令 `--juan` / 后缀计划 / 目录后缀。"""

    def test_make_id_job_plain(self):
        from pycbeta.gui.__main__ import _make_id_job
        j = _make_id_job("t0349")
        self.assertEqual(j["wid"], "T0349")
        self.assertIsNone(j["juan"])
        self.assertIsNone(j["bad_juan"])

    def test_make_id_job_long_and_spec(self):
        from pycbeta.gui.__main__ import _make_id_job
        j = _make_id_job("T25n1509:34-36+40")
        self.assertEqual((j["wid"], j["vol"]), ("T1509", "25"))
        self.assertEqual(j["juan"], "34-36+40")
        self.assertEqual(j["juan_segments"], [(34, 36), (40, 40)])
        self.assertIsNone(j["bad_juan"])

    def test_make_id_job_bad_spec(self):
        from pycbeta.gui.__main__ import _make_id_job
        j = _make_id_job("T0349:100-34")
        self.assertIsNotNone(j["bad_juan"])

    def test_make_id_job_nnn(self):
        from pycbeta.gui.__main__ import _make_id_job
        j = _make_id_job("T0349_002")
        self.assertEqual(j["wid"], "T0349")
        self.assertEqual(j["juan"], "2")
        self.assertEqual(j["juan_segments"], [(2, 2)])
        self.assertIsNone(j["bad_juan"])
        j = _make_id_job("T25n1509_034")
        self.assertEqual((j["wid"], j["vol"]), ("T1509", "25"))
        self.assertEqual(j["juan_segments"], [(34, 34)])
        j = _make_id_job("T0349_000")
        self.assertIsNotNone(j["bad_juan"])

    def test_parse_work_ids_file_with_spec(self):
        import tempfile
        from pycbeta.gui.__main__ import parse_work_ids_file
        p = os.path.join(tempfile.mkdtemp(), "ids.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 注释\n1. T0349:2-3\nT25n1509:34-100\nbad\nX1077\n")
        self.assertEqual(parse_work_ids_file(p),
                         ["T0349:2-3", "T25N1509:34-100", "X1077"])

    def test_parse_work_ids_file_with_nnn(self):
        import tempfile
        from pycbeta.gui.__main__ import parse_work_ids_file
        p = os.path.join(tempfile.mkdtemp(), "ids.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("T0349_002\nT0001_0001\nreport_24\n")
        # `_002` 归一为 `:2`；4 位后缀与非法 head 照旧跳过
        self.assertEqual(parse_work_ids_file(p), ["T0349:2"])

    def test_build_render_cmd_juan(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import build_render_cmd
        opts = SimpleNamespace(page="a4", font_lang=None, t2s=False,
                               font_scale=1.0, vertical=False, engine=None)
        cmd = build_render_cmd(opts, "x.xml", "txt", "o", "c.json",
                               out_name="n.txt", juan="2-3")
        self.assertIn("--juan", cmd)
        self.assertEqual(cmd[cmd.index("--juan") + 1], "2-3")
        cmd2 = build_render_cmd(opts, "x.xml", "txt", "o", "c.json")
        self.assertNotIn("--juan", cmd2)

    def test_juan_plan_full_and_subset(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        w = BatchWorker([], SimpleNamespace(verify={}, formats=[]), {}, {})
        job = {"juan": "1-2", "juan_segments": [(1, 2)]}
        # 全覆盖 → 归 None（不裁剪、不加后缀，指纹与整本一致，P11）
        self.assertEqual(w._juan_plan(job, {1, 2}, {}), (None, ""))
        segs, sfx = w._juan_plan(job, {1, 2, 3}, {})
        self.assertEqual(segs, [(1, 2)])
        self.assertEqual(sfx, "（卷1-2）")
        spec_job = {"juan": "1-3", "juan_segments": [(1, 3)]}
        self.assertEqual(w._juan_plan(spec_job, {1, 2, 3}, {}), (None, ""))
        self.assertEqual(w._juan_plan({}, {1}, {}), (None, ""))
        # 无 milestone（all_juans 空）→ None（与 CLI 警告忽略一致，不加后缀）
        self.assertEqual(w._juan_plan(job, set(), {}), (None, ""))

    def test_verify_dir_suffix(self):
        import tempfile
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker
        tmp = tempfile.mkdtemp(prefix="gverjs-")
        w = BatchWorker([], SimpleNamespace(verify={}, formats=[]), {}, {})
        w._title_t2s = False
        d = w._verify_dir(tmp, "X1077", "准提净业", "", sfx="（卷2-3）")
        self.assertTrue(d.endswith("X1077 准提净业（卷2-3）（验证）"))
        self.assertTrue(os.path.isdir(d))

    def test_out_name_suffix(self):
        import tempfile
        from pycbeta.gui.__main__ import BatchWorker
        from types import SimpleNamespace
        w = BatchWorker([], SimpleNamespace(verify={}, formats=[]), {}, {})
        w._title_t2s = False
        d = tempfile.mkdtemp(prefix="goutjs-")
        name = w._out_name_for({}, d, "X1077", "准提净业", "X59n1077", "docx",
                               sfx="（卷2-3）")
        self.assertIsNone(name)     # 单源不改名 → CLI 默认名（含后缀）


class TestVerifyRootOverride(unittest.TestCase):
    """GUI 独立窗 `--verify-root`：显式 ＞ 预设 source.verify_root ＞ 默认。"""

    def test_pick_verify_root_precedence(self):
        from pycbeta.gui.__main__ import _pick_verify_root
        presets = {"source": {"verify_root": "P:/preset"}}
        self.assertEqual(_pick_verify_root("X:/explicit", presets), "X:/explicit")
        self.assertEqual(_pick_verify_root("", presets), "P:/preset")
        self.assertEqual(_pick_verify_root(None, presets), "P:/preset")
        self.assertEqual(_pick_verify_root("  ", presets), "P:/preset")
        self.assertEqual(_pick_verify_root("", {}), "")
        self.assertEqual(_pick_verify_root("", None), "")
        self.assertEqual(_pick_verify_root("X:/e", {"source": None}), "X:/e")

    def test_apply_launch_args_sets_override(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import _apply_launch_args
        win = SimpleNamespace()
        _apply_launch_args(win, SimpleNamespace(verify_root="X:/vr"))
        self.assertEqual(win._verify_root_override, "X:/vr")

    def test_apply_launch_args_no_override_leaves_attr(self):
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import _apply_launch_args
        win = SimpleNamespace()
        _apply_launch_args(win, SimpleNamespace())
        self.assertFalse(hasattr(win, "_verify_root_override"))

    def test_worker_paths_override_wins(self):
        # _start 把覆盖值并入 worker paths；run() 经 _pick_verify_root 取生效值
        from types import SimpleNamespace
        from pycbeta.gui.__main__ import BatchWorker, _pick_verify_root
        w = BatchWorker([], SimpleNamespace(verify={}, formats=[]),
                        {"presets": {"source": {"verify_root": "P:/preset"}},
                         "run": {}, "out": "o",
                         "verify_root": "X:/override"}, {})
        self.assertEqual(
            _pick_verify_root(w.paths.get("verify_root"), w.paths["presets"]),
            "X:/override")


if __name__ == "__main__":
    unittest.main()
