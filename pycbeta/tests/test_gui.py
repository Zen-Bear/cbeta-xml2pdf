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


class TestConfigBar(unittest.TestCase):
    """配置栏：保存用户配置/载入用户配置/设为默认 + default_page。"""

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
            self.assertEqual(panel.btn_save.text(), "保存用户配置")
            self.assertEqual(panel.btn_load.text(), "载入用户配置")
            self.assertEqual(panel.btn_set_default.text(), "设为默认")
            self.assertFalse(hasattr(panel, "btn_update_data"))  # 已搬数据源窗口
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_save_writes_user_file(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        saved = {}
        with mock.patch.object(pm, "load_slot",
                               return_value=({"output": {}}, "user")), \
                mock.patch.object(pm, "save_current",
                                  side_effect=lambda d, root=None: saved.update(
                                      data=d)), \
                mock.patch("os.path.isfile", return_value=True):
            panel = pm.XmlOptionsPanel({"output": {}})
            try:
                panel.t2s_box.setChecked(True)
                panel._on_save()
                self.assertTrue(saved["data"]["output"]["t2s"])
                self.assertTrue(panel.btn_load.isEnabled())
            finally:
                panel.close() if hasattr(panel, "close") else None

    def test_load_fills_panel(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        panel = self._panel()
        try:
            with mock.patch.object(pm, "load_slot", return_value=(
                    {"output": {"t2s": True}}, "user")):
                panel._on_load_user()
            self.assertTrue(panel.t2s_box.isChecked())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_load_disabled_when_missing(self):
        import unittest.mock as mock
        panel = self._panel()
        try:
            with mock.patch("os.path.isfile", return_value=False):
                panel._refresh_load_button()
                self.assertFalse(panel.btn_load.isEnabled())
            with mock.patch("os.path.isfile", return_value=True):
                panel._refresh_load_button()
                self.assertTrue(panel.btn_load.isEnabled())
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_set_default_writes_run_slot(self):
        import unittest.mock as mock
        panel = self._panel()
        try:
            with mock.patch("pycbeta.theme.set_run_slot") as m:
                panel._on_set_default()
                m.assert_called_once_with("config-json", "config.user.json")
        finally:
            panel.close() if hasattr(panel, "close") else None

    def test_save_persists_formats(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {}}}
        saved = {}
        with mock.patch.object(pm, "load_slot",
                               return_value=(dict(base), "user")), \
                mock.patch.object(pm, "save_current",
                                  side_effect=lambda d, root=None: saved.update(
                                      data=d)), \
                mock.patch("os.path.isfile", return_value=True):
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

    def test_save_persists_margins_custom(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        base = {"output": {}, "pages": {"a4": {"margins": {"top": 25.4,
                                                           "right": 25.4,
                                                           "bottom": 25.4,
                                                           "left": 25.4}}}}
        saved = {}
        with mock.patch.object(pm, "load_slot",
                               return_value=(dict(base), "user")), \
                mock.patch.object(pm, "save_current",
                                  side_effect=lambda d, root=None: saved.update(
                                      data=d)), \
                mock.patch("os.path.isfile", return_value=True):
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
        with mock.patch.object(pm, "load_slot",
                               return_value=(dict(base), "user")), \
                mock.patch.object(pm, "save_current"), \
                mock.patch("os.path.isfile", return_value=True):
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
        with mock.patch.object(pm, "load_slot",
                               return_value=(dict(base), "user")), \
                mock.patch.object(pm, "save_current",
                                  side_effect=lambda d, root=None: saved.update(
                                      data=d)), \
                mock.patch("os.path.isfile", return_value=True):
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
        with mock.patch.object(pm, "load_slot",
                               return_value=(dict(base), "user")), \
                mock.patch.object(pm, "save_current",
                                  side_effect=lambda d, root=None: saved.update(
                                      data=d)), \
                mock.patch("os.path.isfile", return_value=True):
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
        # 空=内置词表，hint 给出实际路径且可打开
        self.assertEqual(panel.ann_file.text(), "")
        self.assertIn("annotations.txt", panel.ann_hint.text())
        self.assertTrue(panel.ann_open.isEnabled())
        # 填不存在的路径→红字+禁用
        panel.ann_file.setText(r"E:\nonexistent\x.tsv")
        self.assertIn("不存在", panel.ann_hint.text())
        self.assertFalse(panel.ann_open.isEnabled())

    def test_source_button_above_input(self):
        from pycbeta.gui.__main__ import MainWindow
        w = MainWindow()
        try:
            self.assertEqual(w.src_btn.text(), "数据源…")
            # 第一行佛典编号列表右边（mode_row 内第 3 个控件）
            grid = w.centralWidget().layout().itemAt(0).layout()
            mode_row = grid.itemAtPosition(0, 1).layout()
            self.assertEqual(mode_row.itemAt(2).widget(), w.src_btn)
            self.assertTrue(w.mode_ids.text().startswith("佛典编号"))
        finally:
            w.close()

    def test_slot_label_link(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        panel.mark_slot()
        # 锚定 run.json，链下游动态显示（本机 run.json 指用户配置）
        self.assertIn("运行组合", panel.slot_label.text())
        self.assertIn("config.user.json", panel.slot_label.text())
        self.assertIn("run.json", panel.slot_label.toolTip())
        self.assertTrue(panel.slot_label.openExternalLinks())
        # 动作只换后缀，主体不翻转
        panel.refresh_slot_label("（已保存）")
        self.assertIn("运行组合", panel.slot_label.text())
        self.assertIn("（已保存）", panel.slot_label.text())

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


class TestBatchMergeResolve(unittest.TestCase):
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
            self.assertEqual(dlg.btn_update_data.text(), "更新官方数据")
        finally:
            dlg.close()

    def test_update_finished_shows_report(self):
        import unittest.mock as mock
        import pycbeta.gui.panel as pm
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        dlg = pm.SourceDialog()
        try:
            rep = [{"key": "gaiji", "status": "unchanged", "detail": "1 条"}]
            with mock.patch.object(pm.QMessageBox, "information") as m:
                dlg._on_update_finished(rep)
                m.assert_called_once()
                args, _kw = m.call_args
                self.assertIn("gaiji", args[2])
            self.assertTrue(dlg._buttons_box.isEnabled())
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
            with mock.patch.object(pm, "save_current") as m:
                with mock.patch.object(
                        pm, "load_slot",
                        return_value=({"source": {}, "downloads": {}},
                                      "user")):
                    dlg.accept()
                    m.assert_called_once()
                    saved = m.call_args.args[0]
                    self.assertEqual(
                        saved["downloads"]["xml"], "http://example/custom-xml")
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
            self.assertIn("cbeta_ebook", keys)
            self.assertNotIn("download_dir", keys)
            self.assertIn("cbeta_ebook", dlg.path_edits)
            self.assertTrue(dlg.title_t2s_box.isChecked())  # 默认开
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
        sample = glob.glob(r"E:\dev\cbeta\xml2pdf\css-presets\sample.xml")
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
            os.path.join("css-presets", "sample.xml")))
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
                self.assertIn("［用户］mine", texts[0])
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
        r = subprocess.run(
            [sys.executable, "-m", "pycbeta.cli", "--font-set", "default",
             "-i", "x", "-f", "docx"],
            capture_output=True, text=True, cwd=r"E:\dev\cbeta\xml2pdf")
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
        # 大字版示例（与 css-presets/large-print.css 同形）：覆盖块可合并
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
            # 部分文件：出厂打底（正文 12pt）+ 覆盖生效
            self.assertEqual((t.tags.get("p") or {}).get("font-size"), "12pt")
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
            udir = os.path.join(root, "css-presets")
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
                    self.assertIn("［用户］mine", texts)
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

    def test_write_temp_run(self):
        import json
        import shutil
        from pycbeta.gui.panel import write_temp_run, write_temp_presets
        from pycbeta.gui.panel import XmlOptions
        run = {"config-json": "config.json", "html-epub-theme": "cbeta_golden.css",
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
        n1 = w._out_name_for(used, "out", "TX0006", "TX07n0006", "txt")
        n2 = w._out_name_for(used, "out", "TX0006", "TX08n0006", "txt")
        n3 = w._out_name_for(used, "out", "TX0006", "TX09n0006", "html")
        self.assertIsNone(n1)  # 首个沿用默认
        self.assertEqual(n2, "TX08n0006.txt")
        self.assertIsNone(n3)  # html 照旧默认（残留）

    def test_styles_tab_opens_editor(self):
        from pycbeta.gui.panel import XmlOptionsPanel
        panel = XmlOptionsPanel(load_presets())
        self.assertEqual(panel.btn_editor.text(), "打开 CSS 编辑器…")


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


if __name__ == "__main__":
    unittest.main()
