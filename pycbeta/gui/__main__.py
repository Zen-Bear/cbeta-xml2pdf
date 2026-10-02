"""独立转换窗：`python -m pycbeta.gui`。

两种输入：目录/文件，或佛典編號列表（含自动下载缺失 XML/官方电子书）。
批量经 QThread 执行，可取消；转换走子进程，校验走 verify_one。
"""
import glob
import os
import re
import subprocess
import sys
from html import escape

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton,
    QRadioButton, QTableWidget, QTableWidgetItem, QTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from pycbeta.gui.panel import (
    XmlOptionsPanel, load_run_and_presets, write_temp_presets,
    write_temp_run,
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
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QFont, QPalette


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


def build_render_cmd(opts, xml, fmt, out_dir, tmpcfg, out_name=None):
    """子进程桥命令（纯函数，可单测）：批量渲染一行。

    - 字库语言只在简体时传 --font-lang（默认繁体省略；t2s 自动简体）；
    - tmpcfg 是临时 run.json（5 槽组合单；主题走槽，不传 --theme）。
    - out_name 给定时 -o 指向确切文件（多源同名统一回退用；html 忽略，见残留）。
    """
    out_target = os.path.join(out_dir, out_name) if out_name else out_dir
    cmd = [sys.executable, "-m", "pycbeta", "-i", xml, "-f", fmt,
           "--page", opts.page, "--config", tmpcfg, "-o", out_target]
    if (opts.font_lang or "zh-Hant") == "zh-Hans" and not opts.t2s:
        cmd += ["--font-lang", "zh-Hans"]
    if abs(float(opts.font_scale or 1.0) - 1.0) > 1e-9:
        cmd += ["--font-scale", str(opts.font_scale)]
    if opts.vertical:
        cmd += ["--vertical"]
    cmd += ["--t2s"] if opts.t2s else ["--no-t2s"]
    if opts.engine:
        cmd += ["--engine", opts.engine]
    return cmd


_ERR_RE = re.compile(r"(?i)(error|exception|permission|denied|traceback|失败|错误)")


def _last_error_line(text):
    """从子进程输出取最可能的错误行（截 300 字）。

    优先最后一次 traceback 的异常行（stdout 块缓冲会让正常行落在 traceback 之后），
    否则取含 error/失败 关键词的末行，再否则取末行。
    """
    lines = [l.rstrip() for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return "未知错误"
    tb = [i for i, l in enumerate(lines)
          if l.strip().startswith("Traceback (most recent call last):")]
    scope = lines[tb[-1] + 1:] if tb else lines
    for l in reversed(scope):
        if _ERR_RE.search(l):
            return l.strip()[:300]
    for l in reversed(scope):
        if l and not l[0].isspace():
            return l.strip()[:300]
    return lines[-1].strip()[:300]


def parse_work_ids_file(path):
    """从 ID 列表文本解析佛典编号：逐行取 `is_work_id` 命中的 token（去重保序）。

    兼容 `test/mini-test.txt` 形态（`T0349 彌勒菩薩所問本願經`）、逗号/分号/顿号
    分隔、行首序号与 `#` 注释；无命中返回 []。"""
    from pycbeta.fetch import is_work_id
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        try:
            with open(path, encoding="gbk", errors="replace") as f:
                text = f.read()
        except OSError:
            return []
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        for tok in re.split(r"[\s,;，；、]+", line):
            tok = tok.strip().strip(".").strip()
            if tok and is_work_id(tok):
                up = tok.upper()
                if up not in out:
                    out.append(up)
    return out


def _row_outcome(render_ok, row_ver, verify_on, render_errors=None):
    """行终态（状态列文本, 配色等级）。等级 ∈ ok/fail/none/"" 。"""
    if not render_ok:
        detail = "；".join(render_errors or [])
        base = f"失败：{detail}" if detail else "失败"
        return base, "fail"
    base = "完成"
    if not verify_on or not row_ver:
        return base, ""
    ok = sum(1 for r in row_ver if r.get("status") == "ok")
    fail = sum(1 for r in row_ver if r.get("status") in ("fail", "error"))
    none = sum(1 for r in row_ver if r.get("status") == "no_baseline")
    parts = []
    if ok:
        parts.append(f"OK{ok}" if (fail or none) else "OK")
    if fail:
        parts.append(f"失败{fail}")
    if none:
        parts.append(f"无对照{none}")
    suffix = "｜校验 " + "/".join(parts) if parts else "｜校验"
    level = "fail" if fail else ("ok" if ok else ("none" if none else ""))
    return base + suffix, level


class BatchWorker(QThread):
    row_status = Signal(int, str)
    row_source = Signal(int, str)
    row_title = Signal(int, str)
    row_file = Signal(int, str)
    row_verify = Signal(int, str)      # 行校验等级 ok/fail/none（驱动状态列配色）
    verify_result = Signal(dict)       # 单次校验详情（汇总弹窗/打开报告用）
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
        self._last_render_err = ""

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
        from pycbeta.verify import verify_one, format_verify_report
        presets, out_dir = self.paths["presets"], self.paths["out"]
        self._title_t2s = fetch.title_t2s(presets)
        run, snapshot, tmpcfg = self.paths.get("run") or {}, None, None
        import tempfile as _tf
        import shutil as _sh
        merge_tmp = _tf.mkdtemp(prefix="xml2pdf-merge-")
        self._merge_tmp = merge_tmp
        try:
            snapshot = write_temp_presets(presets, self.opts)
            tmpcfg = write_temp_run(run, snapshot)
            verify_on = bool(self.opts.verify.get("enabled"))
            n_fmt = len(self.opts.formats)
            # 校验与渲染各占一格进度；进度条不再在校验期间停死
            total_units = sum(n_fmt for _j in self.jobs) * (2 if verify_on else 1)
            done_units = 0
            used_names = {}  # 本轮命名状态（多源同名统一回退，与 CLI 同规则）
            for idx, job in enumerate(self.jobs):
                if self._cancel:
                    self.row_status.emit(idx, "已取消")
                    continue
                xmls = self._resolve(job, idx, fetch, presets)
                if not xmls:
                    continue
                row_ver = []      # 本行校验结果
                row_produced = []  # 本行全部产物（跨 xml 累积，行末一次发文件列）
                render_errors = []
                render_ok = True
                row_stem = None
                row_wid = None
                row_title = ""
                verify_dir = None
                for xml in xmls:
                    if self._cancel:
                        break
                    title, wid = self._title_of(xml, idx, P5Parser)
                    if row_stem is None:
                        row_stem = wid or os.path.splitext(
                            os.path.basename(xml))[0]
                    if row_wid is None:
                        row_wid, row_title = wid, title
                    if verify_on and verify_dir is None:
                        # 校验产物独立成 {(id) 书名}（验证）/ 子目录（保持 {fmt}/ 结构）
                        verify_dir = self._verify_dir(out_dir, wid, title)
                    for fmt in self.opts.formats:
                        if self._cancel:
                            break
                        out_name = self._out_name_for(
                            used_names, out_dir, wid, title,
                            os.path.splitext(os.path.basename(xml))[0], fmt)
                        ok, paths = self._render_one(xml, fmt, out_dir, tmpcfg,
                                                     out_name=out_name)
                        row_produced += paths
                        gen_name = os.path.basename(paths[0]) if paths else ""
                        render_ok = render_ok and ok
                        if not ok:
                            render_errors.append(
                                f"{fmt}: {self._last_render_err or '未知错误'}")
                        done_units += 1
                        self.total_progress.emit(done_units, max(total_units, 1))
                        if ok and verify_on:
                            self.row_status.emit(idx, f"校验中（{fmt}）…")
                            vr = self._verify_one(xml, fmt, verify_dir or out_dir,
                                                  tmpcfg, verify_one, wid,
                                                  gen_name=gen_name)
                            row_ver.append(vr)
                            self.verify_result.emit(vr)
                            done_units += 1
                            self.total_progress.emit(
                                done_units, max(total_units, 1))
                # 验证总报告：每行一份，放该行（验证）子目录，排文件列最后
                if verify_on and row_ver and row_stem:
                    report = os.path.join(
                        verify_dir or out_dir, f"{row_stem}_verify_report.txt")
                    try:
                        vv = self.opts.verify
                        lines = format_verify_report(
                            row_ver,
                            diff_lines=int(vv.get("diffLines", 5) or 5),
                            max_diff=int(vv.get("maxDiff", 10) or 10))
                        with open(report, "w", encoding="utf-8") as f:
                            f.write("\n".join(lines) + "\n")
                        if report not in row_produced:
                            row_produced.append(report)
                    except Exception as e:
                        self.log.emit(f"verify report fail: {e}")
                if row_produced:
                    self.row_file.emit(
                        idx, ";".join(dict.fromkeys(row_produced)))
                text, level = _row_outcome(
                    render_ok, row_ver, verify_on, render_errors)
                self.row_status.emit(idx, text)
                self.row_verify.emit(idx, level)
        finally:
            for p in (tmpcfg, snapshot):
                if p and os.path.isfile(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            try:
                _sh.rmtree(merge_tmp, ignore_errors=True)
            except Exception:
                pass
            self.finished_all.emit()

    def _resolve(self, job, idx, fetch, presets):
        try:
            xml_dir, cbeta_ebook = fetch.resolve_source(presets)
        except ValueError as e:
            self.row_status.emit(idx, f"未配置: {e}")
            return []
        if job["kind"] == "file":
            return [job["xml"]] if os.path.isfile(job["xml"]) else []
        if job["kind"] == "merged":
            # 目录模式碎片组：worker 内合成（tmpdir 随批量清），一行一部一册
            from pycbeta.merge import merge_groups_to_dir
            key, files = job["group"]
            try:
                paths = merge_groups_to_dir(
                    {key: files}, getattr(self, "_merge_tmp", None), quiet=True)
            except Exception as e:
                self.row_status.emit(idx, f"合册失败: {e}")
                return []
            if paths:
                self.row_source.emit(idx, "合册合成")
            return paths
        wid = job["id"]
        if not fetch.is_work_id(wid):
            self.row_status.emit(idx, "非法編號")
            return []
        # 三源材料化：cbeta_ebook → 本地候选源（拷/合册）→ 官方下载
        try:
            found, label = fetch.materialize_work(
                wid, presets, xml_dir=xml_dir, cbeta_ebook=cbeta_ebook,
                download=bool(self.flags.get("auto_xml")), quiet=True)
        except ValueError as e:
            self.row_status.emit(idx, f"未配置: {e}")
            return []
        if found:
            self.row_source.emit(idx, {
                "cbeta_ebook": "本地XML", "xml_copy": "本地拷贝",
                "xml_merge": "合册合成", "downloaded": "已下载",
            }.get(label, ""))
            if self.flags.get("auto_base"):
                try:
                    fetch.ensure_baselines(wid, ["html", "docx", "txt_notes"],
                                           presets, cbeta_ebook)
                except Exception:
                    pass
            return found
        if not bool(self.flags.get("auto_xml")):
            self.row_status.emit(idx, "缺 XML（未勾选自动下载）")
        else:
            self.row_status.emit(idx, self._missing_xml_reason(wid, presets))
        return []

    def _missing_xml_reason(self, wid, presets):
        """自动下载已开仍无 XML：区分 catalog 未收录 vs 下载失败。
        catalog 钉死内置（fetch.resolve_catalog），此处不再读 presets 自定义值。"""
        from pycbeta import fetch
        try:
            canon, no = fetch.parse_work_id(fetch.canonical_work_id(wid, presets))
            cat = fetch.resolve_catalog()
            if os.path.isfile(cat) \
                    and not fetch.catalog_lookup(cat, canon, no):
                return "缺 XML（catalog 未收录）"
        except Exception:
            pass
        return "缺 XML（下载失败）"

    def _title_of(self, xml, idx, P5Parser):
        try:
            w = P5Parser().parse(xml)
            title = (w.metadata.get("title") or "").strip() or w.id
            self.row_title.emit(idx, title)
            return title, w.id
        except Exception:
            return os.path.basename(xml), ""

    def _out_name_for(self, used, out_dir, wid, title, stem, fmt):
        """本轮统一命名：默认 `{workid 书名}`（title_t2s 跟随 source）。
        多源同名全组改输入基名（与 CLI 同规则，共 filename helper）。
        返回最终名；None 表示沿用默认（单文件/html/无 wid）。改名执行缺失忽略。"""
        if fmt == "html" or not wid:
            return None
        from pycbeta.filename import dedupe_run_outputs, default_output_name
        from pycbeta.cli import _FORMAT_EXT
        ext = _FORMAT_EXT.get(fmt)
        if not ext:
            return None
        default = default_output_name(
            wid, title, getattr(self, "_title_t2s", True)) + ext
        final, renames = dedupe_run_outputs(used, out_dir, default, stem)
        for old, new in renames:
            try:
                if os.path.isfile(old):
                    os.rename(old, new)
            except OSError:
                pass
        return None if final == default else final

    def _verify_dir(self, out_dir, wid, title):
        """校验产物子目录 `{输出}/{id 书名}（验证）/`（内部保持 {fmt}/ 结构）。"""
        from pycbeta.filename import default_output_name
        name = default_output_name(
            wid or "", title, getattr(self, "_title_t2s", True))
        path = os.path.join(out_dir, f"{name}（验证）")
        os.makedirs(path, exist_ok=True)
        return path

    def _render_one(self, xml, fmt, out_dir, tmpcfg, out_name=None):
        cmd = build_render_cmd(self.opts, xml, fmt, out_dir, tmpcfg,
                               out_name=out_name)
        self.log.emit("$ " + " ".join(cmd))
        self._last_render_err = ""
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            out, err = self._proc.communicate()
            for chunk in (out, err):
                if chunk and chunk.strip():
                    self.log.emit(chunk[-2000:])
            ok = self._proc.returncode == 0
            if not ok:
                # stderr 优先（traceback/报错），stdout 兜底（友好信息可能走 stdout）
                self._last_render_err = (_last_error_line(err)
                                         or _last_error_line(out))
                self.log.emit(f"✗ {fmt} 生成失败：{self._last_render_err}")
            return ok, parse_produced_paths(out) if ok else []
        except Exception as e:
            self._last_render_err = str(e)
            self.log.emit(f"✗ {fmt} 生成失败：{e}")
            return False, []
        finally:
            self._proc = None

    def _verify_one(self, xml, fmt, out_dir, tmpcfg, verify_one, wid="", gen_name=""):
        v = self.opts.verify
        rec = {"id": wid or os.path.basename(xml), "fmt": fmt, "xml": xml,
               "gen_name": gen_name}
        try:
            eff, disp = fmt, fmt
            if fmt == "pdf":
                # PDF 无官方基线：委托管线源格式（docx2pdf→docx / html2pdf→html）
                from pycbeta.render_pdf import pdf_source_fmt
                src = pdf_source_fmt(getattr(self.opts, "engine", None),
                                     getattr(self.opts, "vertical", False))
                if src in self.opts.formats:
                    rec.update({"status": "covered", "cover_by": src,
                                "detail": f"已由 {src} 校验覆盖（未重复）"})
                    self.log.emit(f"verify {rec['id']} pdf: covered by {src}")
                    return rec
                eff, disp = src, f"pdf→{src}"
            r = verify_one(xml, eff, os.path.dirname(os.path.abspath(xml)),
                           out_dir,
                           max_diff=int(v.get("maxDiff", 10) or 10),
                           diff_lines=int(v.get("diffLines", 5) or 5),
                           config_path=tmpcfg, t2s=self.opts.t2s)
            if isinstance(r, dict):
                rec.update(r)
            rec["id"] = wid or os.path.basename(xml)
            rec["fmt"] = disp
            rec["xml"] = xml
            self.log.emit(f"verify {rec['id']} {disp}: {rec.get('status')} "
                          f"缺{rec.get('missing')} 多{rec.get('extra')}")
        except Exception as e:
            rec.update({"status": "error", "detail": str(e)})
            self.log.emit(f"verify fail: {e}")
        return rec


class VerifySummaryDialog(QDialog):
    """转换后校验汇总：通过（0/0 绿、有差警告色）/失败（红）/无对照（灰）+ 明细。"""

    _KIND = {
        "ok0": ("通过", "#2e7d32"),
        "okw": ("通过(有差)", "#1565c0"),
        "none": ("无对照", "gray"),
        "covered": ("已覆盖", "gray"),
        "error": ("异常", "#c62828"),
        "fail": ("失败", "#c62828"),
    }

    def __init__(self, results, report_dir="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("校验结果汇总")
        self.resize(620, 440)
        self._report_dir = report_dir or ""
        counts = {"ok0": 0, "okw": 0, "fail": 0, "none": 0, "covered": 0}
        for r in results:
            k = self._rec_kind(r)
            key = "fail" if k == "error" else k
            counts[key] = counts.get(key, 0) + 1
        layout = QVBoxLayout(self)
        head = QLabel(f"校验 {len(results)} 项："
                      f"<b><font color='#2e7d32'>通过 {counts['ok0']}</font></b> / "
                      f"<b><font color='#1565c0'>通过(有差) {counts['okw']}</font></b> / "
                      f"<b><font color='#c62828'>失败 {counts['fail']}</font></b> / "
                      f"<font color='gray'>无对照 {counts['none']}</font> / "
                      f"<font color='gray'>已覆盖 {counts['covered']}</font>")
        head.setTextFormat(Qt.RichText)
        layout.addWidget(head)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setHtml("<br>".join(self._line(r) for r in results))
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        btn_open = QPushButton("打开报告目录")
        btn_open.setEnabled(bool(self._report_dir))
        btn_open.clicked.connect(self._open_report)
        row.addWidget(btn_open)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _rec_kind(r):
        st = r.get("status")
        if st == "no_baseline":
            return "none"
        if st == "covered":
            return "covered"
        if st == "error":
            return "error"
        if st == "ok":
            return "ok0" if not (r.get("missing") or 0) and not (r.get("extra") or 0) \
                else "okw"
        return "fail"

    @classmethod
    def _line(cls, r):
        kind = cls._rec_kind(r)
        tag, color = cls._KIND[kind]
        miss, extra = r.get("missing"), r.get("extra")
        cnt = (f"  缺{miss}/多{extra}" if miss is not None else
               ("  " + str(r.get("detail", "")) if r.get("detail") else ""))
        # 名称优先用生成的目标文件名（gen_name），回退「编号 格式」
        name = r.get("gen_name") or f"{r.get('id','')} {r.get('fmt','')}".strip()
        body = escape(f"[{tag}] {name}{cnt}")
        return f"<span style='color:{color}'>{body}</span>"

    def _open_report(self):
        d = self._report_dir
        if d and os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from pycbeta import __version__ as _ver
        self.setWindowTitle(f"CBETA XML 格式转换 v{_ver}（{_gui_date()}）")
        self.resize(817, 720)
        menu = self.menuBar()
        act_cfg = menu.addAction("设置…")
        act_cfg.setToolTip("查看/编辑数据源与配置（存当前选中预设）")
        act_cfg.triggered.connect(self._edit_source)
        act_about = menu.addAction("关于")
        act_about.triggered.connect(self._show_about)
        self.worker = None
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        # 输入来源（两 radio 同格左对齐相邻；数据源按钮在编号列表行最右）
        src = QGridLayout()
        # 标签列贴内容、输入列吃掉多余宽度（否则各列平分导致输入框远离标签）
        src.setColumnStretch(1, 1)
        self.mode_file = QRadioButton("目录/文件")
        self.mode_ids = QRadioButton("佛典编号列表")
        self.mode_file.setChecked(True)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(18)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.addWidget(self.mode_file)
        mode_row.addWidget(self.mode_ids)
        mode_row.addStretch(1)
        # 配置区总开关：蓝底白字小箭头（tab 区 +「配置」分组整体收起/复原，收起后批量列表放大）；
        # 各态同色（checked 也不变），只靠箭头方向区分
        self.cfg_toggle = QToolButton()
        self.cfg_toggle.setCheckable(True)
        self.cfg_toggle.setChecked(True)
        self.cfg_toggle.setAutoRaise(True)
        self.cfg_toggle.setFixedSize(22, 22)
        self.cfg_toggle.setArrowType(Qt.DownArrow)
        self.cfg_toggle.setToolTip("收起/展开配置面板")
        # 箭头走 QStyle 调色板（stylesheet 的 color 管不到），显式设白
        _pal = self.cfg_toggle.palette()
        _pal.setColor(QPalette.ButtonText, Qt.white)
        _pal.setColor(QPalette.WindowText, Qt.white)
        self.cfg_toggle.setPalette(_pal)
        self.cfg_toggle.setStyleSheet(
            "QToolButton { background-color: #1565c0; color: white; border: none; border-radius: 4px; }"
            "QToolButton:checked { background-color: #1565c0; color: white; }"
            "QToolButton:hover { background-color: #1565c0; color: white; }"
            "QToolButton:pressed { background-color: #1565c0; color: white; }"
            "QToolButton:disabled { background-color: #1565c0; color: white; }")
        self.cfg_toggle.toggled.connect(self._toggle_panel)
        src.addWidget(QLabel("输入来源"), 0, 0)
        src.addLayout(mode_row, 0, 1, 1, 3)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("XML 目录 / 单个 .xml")
        self.path_edit.textChanged.connect(lambda _t: self.mode_file.setChecked(True))
        browse = QPushButton("目录…")
        browse.setToolTip("选择 XML 目录（递归扫描其中的 .xml）")
        browse.clicked.connect(self._browse)
        browse_file = QPushButton("文件…")
        browse_file.setToolTip("选择 ID 列表 .txt（逐行取佛典編號批量转换，如 test/mini-test.txt）")
        browse_file.clicked.connect(self._browse_file)
        for b in (browse, browse_file):
            b.setFixedWidth(
                b.fontMetrics().boundingRect("目录…").width() + 24)
        src.addWidget(QLabel("目录/文件"), 1, 0)
        src.addWidget(self.path_edit, 1, 1, 1, 2)
        src.addWidget(browse, 1, 3)
        self.ids_edit = QLineEdit()
        self.ids_edit.setPlaceholderText("T0349, X1116（逗号/空格分隔）；或用右边的「文件…」选 ID 列表 .txt")
        self.ids_edit.textChanged.connect(lambda _t: self.mode_ids.setChecked(True))
        src.addWidget(QLabel("编号列表"), 2, 0)
        src.addWidget(self.ids_edit, 2, 1, 1, 2)
        src.addWidget(browse_file, 2, 3)
        self.auto_xml = QCheckBox("自动下载缺失 XML")
        self.auto_xml.setChecked(True)
        self.auto_base = QCheckBox("同时下载官方电子书")
        dl_row = QHBoxLayout()
        dl_row.setSpacing(18)
        dl_row.setContentsMargins(0, 0, 0, 0)
        dl_row.addWidget(self.auto_xml)
        dl_row.addWidget(self.auto_base)
        dl_row.addStretch(1)
        dl_row.addWidget(self.cfg_toggle)   # 收起/展开配置：本行最右
        src.addLayout(dl_row, 3, 1, 1, 3)
        # 输出目录行已并入数据源「输入输出」tab；此处保留隐藏 edit 作会话值载体
        self.out_edit = QLineEdit(os.path.join(os.getcwd(), "out"))
        layout.addLayout(src)
        # 设置面板（有效配置：run.json → base 文件 → 出厂）
        run, presets = load_run_and_presets()
        self._run = run
        self.panel = XmlOptionsPanel(presets)
        self.panel.mark_slot()
        _out0 = ((presets.get("source") or {}).get("out_dir") or "").strip()
        if _out0:
            self.out_edit.setText(_out0)
        layout.addWidget(self.panel, 1)
        # 批量列表
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["经号", "经名", "来源", "状态", "文件"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMouseTracking(True)
        # 只读但可选中拷贝：禁止编辑触发，保留选择/复制（Ctrl+C）
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.cellClicked.connect(self._open_cell)
        layout.addWidget(self.table, 1)
        # 进度与按钮
        bar = QHBoxLayout()
        self.btn_start = QPushButton("转换")
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._stop)
        self.progress = QProgressBar()
        bar.addWidget(self.btn_start)
        bar.addWidget(self.btn_cancel)
        bar.addWidget(self.progress, 1)
        layout.addLayout(bar)
        from pycbeta.theme import default_run_path
        self.statusBar().showMessage(f"运行组合: {default_run_path()}")

    def _toggle_panel(self, show: bool):
        self.panel.setVisible(show)
        self.cfg_toggle.setArrowType(Qt.DownArrow if show else Qt.RightArrow)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择 XML 目录")
        if d:
            self.path_edit.setText(d)
            self.mode_file.setChecked(True)

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择 XML 文件或 ID 列表文件", "",
            "XML 与 ID 列表 (*.xml *.txt);;XML (*.xml);;ID 列表 (*.txt);;所有文件 (*)")
        if f:
            self.path_edit.setText(f)
            self.mode_file.setChecked(True)

    def _show_about(self):
        from pycbeta import __version__ as _ver
        QMessageBox.about(self, "关于", f"v{_ver}")

    def _edit_source(self):
        from pycbeta.gui.panel import SourceDialog
        preset = self.panel._selected_preset() if hasattr(self, "panel") else ""
        dlg = SourceDialog(
            self, preset_path=preset or None,
            out_dir=self.out_edit.text().strip())
        if dlg.exec():
            self.out_edit.setText(dlg.out_dir())
            name = os.path.basename(preset) if preset else "config.user.json"
            self.statusBar().showMessage(f"数据源已保存到{name}")

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
            if os.path.isfile(src):
                if src.lower().endswith(".xml"):
                    jobs.append({"kind": "file", "id": os.path.basename(src), "xml": src})
                else:
                    # ID 列表文本（如 test/mini-test.txt）：逐行取佛典編號批量转换
                    for wid in parse_work_ids_file(src):
                        jobs.append({"kind": "id", "id": wid})
            elif os.path.isdir(src):
                from pycbeta.merge import split_paths
                walked = []
                for fn in sorted(glob.glob(os.path.join(src, "**", "*.xml"), recursive=True)):
                    walked.append(fn)
                whole, groups = split_paths(walked)
                for fn in whole:
                    jobs.append({"kind": "file", "id": os.path.basename(fn), "xml": fn})
                for (canon, vol, no) in sorted(groups):
                    jobs.append({"kind": "merged",
                                 "id": f"{canon}{no}（{vol}合册）",
                                 "group": ((canon, vol, no), groups[(canon, vol, no)])})
        return jobs

    def _start(self):
        jobs = self._collect_jobs()
        if not jobs:
            QMessageBox.warning(self, "提示", "没有可转换的输入")
            return
        out_dir = self.out_edit.text().strip() or os.path.join(os.getcwd(), "out")
        os.makedirs(out_dir, exist_ok=True)
        opts = self.panel.get_options()
        _run, presets = load_run_and_presets()
        from pycbeta.gui.panel import apply_selected_preset_theme
        presets = apply_selected_preset_theme(
            presets, self.panel._selected_preset()
            if hasattr(self, "panel") else "")
        if hasattr(self, "panel"):
            # 「生效样式」下拉若被改选：本次运行即时生效（不落盘），盖过预设键/run 槽
            _ov = self.panel.theme_override()
            if _ov is not None:
                presets["pdf-docx-user-theme"] = _ov
                if _ov == "":
                    # 选「出厂默认」：连同 run 槽一起清空，否则回退 run 槽又套上
                    _run = dict(_run or {})
                    _run["pdf-docx-user-theme"] = ""
        presets = self._warn_xml_dir(presets)
        if presets is None:
            return
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
                                   {"presets": presets, "run": _run,
                                    "out": out_dir},
                                   flags)
        self._verify_results = []
        self._out_dir = out_dir
        self.worker.row_status.connect(self._on_status)
        self.worker.row_source.connect(lambda i, v: self.table.item(i, 2).setText(v))
        self.worker.row_title.connect(lambda i, v: self.table.item(i, 1).setText(v))
        self.worker.row_file.connect(self._on_file)
        self.worker.row_verify.connect(self._on_verify_level)
        self.worker.verify_result.connect(self._verify_results.append)
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

    def _on_verify_level(self, i, level):
        """状态列配色：通过绿 / 失败红 / 无基线灰。"""
        item = self.table.item(i, 3)
        if item is None or not level:
            return
        color = {"ok": "#2e7d32", "fail": "#c62828", "none": "gray"}.get(level)
        if color:
            item.setForeground(QColor(color))

    def _warn_xml_dir(self, presets):
        """转换前抽检 xml_dir；非发布版 P5 → 告警（仍使用/清除/取消）。

        返回（可能更新的）presets；用户选「取消」返回 None（中止本轮）。"""
        if getattr(self, "_xml_dir_checked", False):
            return presets
        self._xml_dir_checked = True
        xml_dir = ((presets.get("source") or {}).get("xml_dir") or "").strip()
        if not xml_dir:
            return presets
        from pycbeta.fetch import inspect_xml_source
        from pycbeta.gui.panel import xml_dir_warning, clear_xml_dir
        info = inspect_xml_source(xml_dir)
        if info.get("safe") is not False:
            return presets
        choice = xml_dir_warning(self, xml_dir, info.get("edition"))
        if choice is None:
            return None
        if choice == "clear":
            preset = self.panel._selected_preset() if hasattr(self, "panel") else ""
            clear_xml_dir(preset_path=preset or None)
            return {**presets,
                    "source": {**(presets.get("source") or {}), "xml_dir": ""}}
        return presets

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
        results = getattr(self, "_verify_results", [])
        if results:
            VerifySummaryDialog(results, getattr(self, "_out_dir", ""),
                                self).exec()
        # 注音待审字落盘（P6）：本轮收集的多音/无收录字写入词表 stub 行并告知
        try:
            from pycbeta.annotate import pending_review, append_review_stubs
            _pending = pending_review()
            _table = ""
            try:
                _table = self.panel._ann_table_path() \
                    if hasattr(self, "panel") else ""
            except Exception:
                _table = ""
            _new = append_review_stubs(_table) if _table else []
            if _new:
                _poly = "".join(sorted(
                    c for c in _new if _pending.get(c) == "polyphonic")) or "无"
                _unk = "".join(sorted(
                    c for c in _new if _pending.get(c) != "polyphonic")) or "无"
                self.statusBar().showMessage(
                    f"注音待审已写入词表（多音：{_poly}；无收录：{_unk}）："
                    f"{_table}，请填写读音后重跑")
        except Exception:
            pass


def _apply_launch_args(win, a):
    """启动参数预填（publish 一键送校验用；无参数时零作用，只填控件，不开跑）。"""
    if getattr(a, "ids_file", None):
        win.path_edit.setText(a.ids_file)
        win.mode_file.setChecked(True)
    if getattr(a, "out", None):
        win.out_edit.setText(a.out)
    if getattr(a, "preset", None):
        import os as _os
        box = win.panel.cfg_preset_box
        # 三种写法都认：stem（如 my）、文件名（如 my.json，publish 传的就是这个）、绝对路径
        want = (a.preset or "").strip()
        want_stem = (want[:-5] if want.lower().endswith(".json") else want)
        idx = -1
        for i in range(box.count()):
            try:
                data = box.itemData(i) or ""
                base = _os.path.splitext(_os.path.basename(str(data)))[0] if data else ""
                if box.itemText(i) in (want, want_stem) or base in (want, want_stem) \
                        or str(data) == want:
                    idx = i
                    break
            except Exception:
                continue
        if idx >= 0:
            box.setCurrentIndex(idx)   # 触发 _on_preset_chosen，载入面板值
    if getattr(a, "formats", None):
        want = [s.strip() for s in str(a.formats).split(",") if s.strip()]
        try:
            boxes = win.panel.format_boxes
            for fmt, box in boxes.items():
                box.setChecked(fmt in want)
            if want and not any(b.isChecked() for b in boxes.values()) and "pdf" in boxes:
                boxes["pdf"].setChecked(True)
        except Exception:
            pass
    if getattr(a, "verify", False):
        try:
            win.panel.verify_on.setChecked(True)
        except Exception:
            pass


def main(argv=None):
    from pycbeta.gui.css_editor import suppress_font_warnings
    suppress_font_warnings()
    import argparse
    _ap = argparse.ArgumentParser(prog="pycbeta.gui", add_help=False)
    _ap.add_argument("--ids-file", default=None, help="ID 列表文件，填入输入来源")
    _ap.add_argument("--out", default=None, help="输出目录预填")
    _ap.add_argument("--preset", default=None, help="预设（stem/文件名/路径），选中即载入面板")
    _ap.add_argument("--formats", default=None, help="逗号分隔输出格式，如 pdf,epub（预填格式勾选）")
    _ap.add_argument("--verify", action="store_true", help="打开转换后校验")
    _ap.add_argument("--autostart", action="store_true", help="窗现即开始转换")
    _raw = sys.argv[1:] if argv is None else list(argv)
    _known, _rest = _ap.parse_known_args(_raw)
    app = QApplication.instance() or QApplication([sys.argv[0]] + _rest)
    from pycbeta.gui.css_editor import ensure_tooltip_style
    ensure_tooltip_style()  # 黑 tooltip 可见（应用级一次）
    win = MainWindow()
    _apply_launch_args(win, _known)
    win.show()
    if _known.autostart:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, win._start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
