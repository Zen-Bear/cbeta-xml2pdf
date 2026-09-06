"""独立转换窗：`python -m pycbeta.gui`。

两种输入：目录/文件，或佛典編號列表（含自动下载缺失 XML/官方基线）。
批量经 QThread 执行，可取消；转换走子进程，校验走 verify_one。
"""
import glob
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QRadioButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from pycbeta.gui.panel import (
    XmlOptionsPanel, load_slot, slot_paths, write_temp_presets,
)


def _gui_date() -> str:
    """GUI 最后更新日期：gui 目录下 .py 文件最新 mtime（标题栏用，免手工维护）。"""
    import datetime
    import glob
    gui_dir = os.path.dirname(os.path.abspath(__file__))
    latest = 0.0
    for fn in glob.glob(os.path.join(gui_dir, "*.py")):
        try:
            latest = max(latest, os.path.getmtime(fn))
        except OSError:
            pass
    if not latest:
        return "未知日期"
    return datetime.datetime.fromtimestamp(latest).strftime("%Y-%m-%d")
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QFont


def parse_produced_paths(log):
    r"""子进程 stdout（如 `T0672: docx(footnote) -> C:\out\T0672.docx`）→ 存在的产物路径列表。
    只认 `->` 行尾且文件存在的路径，避免误吞日志文本。"""
    import re
    out = []
    for line in (log or "").splitlines():
        m = re.search(r"->\s*(.+?\.\w+)\s*$", line)
        if m and os.path.isfile(m.group(1).strip()):
            out.append(m.group(1).strip())
    return out


class BatchWorker(QThread):
    row_status = Signal(int, str)
    row_source = Signal(int, str)
    row_title = Signal(int, str)
    row_file = Signal(int, str)
    total_progress = Signal(int, int)
    finished_all = Signal()
    log = Signal(str)

    def __init__(self, jobs, opts, paths, flags, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.opts = opts
        self.paths = paths
        self.flags = flags
        self._cancel = False
        self._proc = None

    def cancel(self):
        self._cancel = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(self):
        from pycbeta import fetch
        from pycbeta.parser import P5Parser
        from pycbeta.verify import verify_one
        presets, out_dir, tmpcfg = self.paths["presets"], self.paths["out"], None
        try:
            tmpcfg = write_temp_presets(presets, self.opts)
            total_units = sum(len(self.opts.formats) for _j in self.jobs)
            done_units = 0
            for idx, job in enumerate(self.jobs):
                if self._cancel:
                    self.row_status.emit(idx, "已取消")
                    continue
                xmls = self._resolve(job, idx, fetch, presets)
                if not xmls:
                    continue
                for xml in xmls:
                    if self._cancel:
                        break
                    title = self._title_of(xml, idx, P5Parser)
                    produced, ok = [], True
                    for fmt in self.opts.formats:
                        if self._cancel:
                            break
                        ok, paths = self._render_one(xml, fmt, out_dir, tmpcfg)
                        produced += paths
                        done_units += 1
                        self.total_progress.emit(done_units, max(total_units, 1))
                        if ok and self.opts.verify.get("enabled"):
                            self._verify_one(xml, fmt, out_dir, tmpcfg, verify_one)
                    if produced:
                        self.row_file.emit(idx, ";".join(dict.fromkeys(produced)))
                    self.row_status.emit(idx, "完成" if ok else "失败")
        finally:
            if tmpcfg and os.path.isfile(tmpcfg):
                try:
                    os.remove(tmpcfg)
                except Exception:
                    pass
            self.finished_all.emit()

    def _resolve(self, job, idx, fetch, presets):
        src = (presets.get("source") or {})
        xml_dir = src.get("xml_dir") or r"E:\dev\cbeta\test"
        dl_dir = src.get("download_dir") or xml_dir
        if job["kind"] == "file":
            return [job["xml"]] if os.path.isfile(job["xml"]) else []
        wid = job["id"]
        if not fetch.is_work_id(wid):
            self.row_status.emit(idx, "非法編號")
            return []
        canon, no = fetch.parse_work_id(wid)
        found = fetch.find_local_xml(xml_dir, canon, no)
        if found:
            self.row_source.emit(idx, "本地XML")
            return found
        if self.flags.get("auto_xml"):
            self.row_status.emit(idx, "下载XML…")
            try:
                fetch.fetch_work(wid, ["xml"], presets, dl_dir)
            except Exception as e:
                self.row_status.emit(idx, f"下载失败: {e}")
                return []
            found = fetch.find_local_xml(xml_dir, canon, no) or \
                fetch.find_local_xml(dl_dir, canon, no)
            if found:
                self.row_source.emit(idx, "已下载")
                return found
        if self.flags.get("auto_base"):
            try:
                fetch.ensure_baselines(wid, ["html", "docx", "txt"], presets, dl_dir)
            except Exception:
                pass
        self.row_status.emit(idx, "缺 XML")
        return []

    def _title_of(self, xml, idx, P5Parser):
        try:
            w = P5Parser().parse(xml)
            title = (w.metadata.get("title") or "").strip() or w.id
            self.row_title.emit(idx, title)
            return title
        except Exception:
            return os.path.basename(xml)

    def _render_one(self, xml, fmt, out_dir, tmpcfg):
        cmd = [sys.executable, "-m", "pycbeta", "-i", xml, "-f", fmt,
               "--page", self.opts.page, "--font-set", self.opts.font_set,
               "--config", tmpcfg, "-o", out_dir]
        if abs(float(self.opts.font_scale or 1.0) - 1.0) > 1e-9:
            cmd += ["--font-scale", str(self.opts.font_scale)]
        if self.opts.vertical:
            cmd += ["--vertical"]
        cmd += ["--t2s"] if self.opts.t2s else ["--no-t2s"]
        if self.opts.engine:
            cmd += ["--engine", self.opts.engine]
        self.log.emit("$ " + " ".join(cmd))
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            out, _ = self._proc.communicate()
            self.log.emit(out[-2000:])
            ok = self._proc.returncode == 0
            return ok, parse_produced_paths(out) if ok else []
        except Exception as e:
            self.log.emit(f"render fail: {e}")
            return False, []
        finally:
            self._proc = None

    def _verify_one(self, xml, fmt, out_dir, tmpcfg, verify_one):
        v = self.opts.verify
        try:
            r = verify_one(xml, fmt, os.path.dirname(os.path.abspath(xml)), out_dir,
                           max_diff=int(v.get("maxDiff", 10) or 10),
                           diff_lines=int(v.get("diffLines", 5) or 5),
                           config_path=tmpcfg, t2s=self.opts.t2s)
            status = r.get("status", "?")
            self.log.emit(f"verify {os.path.basename(xml)} {fmt}: {status}")
        except Exception as e:
            self.log.emit(f"verify fail: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"CBETA XML 格式转换 v1.0（{_gui_date()}）")
        self.resize(980, 720)
        self.worker = None
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        # 输入来源（两 radio 同格左对齐相邻；数据源按钮同行最右）
        src = QGridLayout()
        self.mode_file = QRadioButton("目录/文件")
        self.mode_ids = QRadioButton("佛典編號列表")
        self.mode_file.setChecked(True)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(18)
        mode_row.addWidget(self.mode_file)
        mode_row.addWidget(self.mode_ids)
        mode_row.addStretch(1)
        src.addWidget(QLabel("输入来源"), 0, 0)
        src.addLayout(mode_row, 0, 1, 1, 2)
        self.src_btn = QPushButton("数据源…")
        self.src_btn.setToolTip("查看/编辑 XML 来源目录与官方下载地址（存用户配置）")
        self.src_btn.clicked.connect(self._edit_source)
        src.addWidget(self.src_btn, 0, 3)
        self.path_edit = QLineEdit()
        self.path_edit.textChanged.connect(lambda _t: self.mode_file.setChecked(True))
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        src.addWidget(QLabel("目录/文件"), 1, 0)
        src.addWidget(self.path_edit, 1, 1, 1, 2)
        src.addWidget(browse, 1, 3)
        self.ids_edit = QLineEdit()
        self.ids_edit.setPlaceholderText("T0349, X1116, TX0006（逗号/空格分隔）")
        self.ids_edit.textChanged.connect(lambda _t: self.mode_ids.setChecked(True))
        src.addWidget(QLabel("編號列表"), 2, 0)
        src.addWidget(self.ids_edit, 2, 1, 1, 2)
        self.auto_xml = QCheckBox("自动下载缺失 XML")
        self.auto_xml.setChecked(True)
        self.auto_base = QCheckBox("同时下载官方电子书")
        dl_row = QHBoxLayout()
        dl_row.setSpacing(18)
        dl_row.addWidget(self.auto_xml)
        dl_row.addWidget(self.auto_base)
        dl_row.addStretch(1)
        src.addLayout(dl_row, 3, 1, 1, 3)
        src.addWidget(QLabel("输出"), 4, 0)
        self.out_edit = QLineEdit(os.path.join(os.getcwd(), "out"))
        out_browse = QPushButton("浏览…")
        out_browse.clicked.connect(self._browse_out)
        out_open = QPushButton("打开目录")
        out_open.clicked.connect(self._open_out)
        src.addWidget(self.out_edit, 4, 1)
        src.addWidget(out_browse, 4, 2)
        src.addWidget(out_open, 4, 3)
        layout.addLayout(src)
        # 设置面板
        presets, actual = load_slot("user")
        self.panel = XmlOptionsPanel(presets)
        self.panel.mark_slot(actual)
        layout.addWidget(self.panel, 1)
        # 批量列表
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["经号", "经名", "来源", "状态", "文件"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMouseTracking(True)
        self.table.cellClicked.connect(self._open_cell)
        layout.addWidget(self.table, 1)
        # 进度与按钮
        bar = QHBoxLayout()
        self.btn_start = QPushButton("开始")
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._stop)
        self.progress = QProgressBar()
        bar.addWidget(self.btn_start)
        bar.addWidget(self.btn_cancel)
        bar.addWidget(self.progress, 1)
        layout.addLayout(bar)
        factory, _u, _l = slot_paths()
        self.statusBar().showMessage(f"配置槽: {factory}")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择 XML 目录")
        if d:
            self.path_edit.setText(d)
            self.mode_file.setChecked(True)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.out_edit.setText(d)

    def _open_out(self):
        d = self.out_edit.text().strip() or os.path.join(os.getcwd(), "out")
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))

    def _edit_source(self):
        from pycbeta.gui.panel import SourceDialog
        dlg = SourceDialog(self)
        if dlg.exec():
            self.statusBar().showMessage("数据源已保存到用户配置")

    def _collect_jobs(self):
        jobs = []
        if self.mode_ids.isChecked():
            import re
            for tok in re.split(r"[,;\s，；]+", self.ids_edit.text()):
                tok = tok.strip().upper()
                if tok:
                    jobs.append({"kind": "id", "id": tok})
        else:
            src = self.path_edit.text().strip()
            if os.path.isfile(src) and src.lower().endswith(".xml"):
                jobs.append({"kind": "file", "id": os.path.basename(src), "xml": src})
            elif os.path.isdir(src):
                for fn in sorted(glob.glob(os.path.join(src, "**", "*.xml"), recursive=True)):
                    if os.sep + "out" + os.sep in fn:
                        continue
                    jobs.append({"kind": "file", "id": os.path.basename(fn), "xml": fn})
        return jobs

    def _start(self):
        jobs = self._collect_jobs()
        if not jobs:
            QMessageBox.warning(self, "提示", "没有可转换的输入")
            return
        out_dir = self.out_edit.text().strip() or os.path.join(os.getcwd(), "out")
        os.makedirs(out_dir, exist_ok=True)
        opts = self.panel.get_options()
        presets, _a = load_slot("user")
        self.table.setRowCount(len(jobs))
        for i, job in enumerate(jobs):
            self.table.setItem(i, 0, QTableWidgetItem(job.get("id", "")))
            for c in (1, 2, 3, 4):
                self.table.setItem(i, c, QTableWidgetItem(""))
            self.table.item(i, 3).setText("待转换")
            if job["kind"] == "file":
                self.table.item(i, 4).setText(job["xml"])
        flags = {"auto_xml": self.auto_xml.isChecked(),
                 "auto_base": self.auto_base.isChecked()}
        self.worker = BatchWorker(jobs, opts,
                                  {"presets": presets, "out": out_dir},
                                  flags)
        self.worker.row_status.connect(self._on_status)
        self.worker.row_source.connect(lambda i, v: self.table.item(i, 2).setText(v))
        self.worker.row_title.connect(lambda i, v: self.table.item(i, 1).setText(v))
        self.worker.row_file.connect(self._on_file)
        self.worker.total_progress.connect(
            lambda d, t: (self.progress.setMaximum(t), self.progress.setValue(d)))
        self.worker.log.connect(lambda m: self.statusBar().showMessage(m[-160:]))
        self.worker.finished_all.connect(self._on_done)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.worker.start()

    def _on_status(self, i, text):
        if self.table.item(i, 3) is not None:
            self.table.item(i, 3).setText(text)

    def _on_file(self, i, paths):
        """文件列：显示 basename 链接样式，全路径存 UserRole + tooltip；单击打开。"""
        item = self.table.item(i, 4)
        if item is None:
            return
        files = [p for p in (paths or "").split(";") if p]
        item.setData(Qt.UserRole, ";".join(files))
        item.setToolTip("\n".join(files))
        if files:
            item.setText("；".join(os.path.basename(p) for p in files))
            item.setForeground(QColor("blue"))
            font = QFont(item.font())
            font.setUnderline(True)
            item.setFont(font)

    def _open_cell(self, row, col):
        if col != 4:
            return
        item = self.table.item(row, col)
        if item is None:
            return
        files = [p for p in (item.data(Qt.UserRole) or item.text() or "").split(";") if p.strip()]
        if not files:
            return
        if len(files) == 1:
            if os.path.isfile(files[0]):
                QDesktopServices.openUrl(QUrl.fromLocalFile(files[0]))
            return
        menu = QMenu(self.table)
        for p in files:
            act = menu.addAction(f"{os.path.basename(p)}  （{p}）")
            act.setData(p)
        chosen = menu.exec(QCursor.pos())
        if chosen is not None and os.path.isfile(chosen.data()):
            QDesktopServices.openUrl(QUrl.fromLocalFile(chosen.data()))

    def _stop(self):
        if self.worker is not None:
            self.worker.cancel()

    def _on_done(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.statusBar().showMessage("批量完成")


def main(argv=None):
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
