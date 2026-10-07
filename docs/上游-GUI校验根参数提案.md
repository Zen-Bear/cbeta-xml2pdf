# 上游 GUI `--verify-root` 参数提案（下游 publish 请求）

> 状态：**已实现**（2026-10-07 下游请求并落地；实现记录见 §7）。
> 请求方：publish（`docs/链路B-设计契约.md` §9.4／§9.5；publish 侧同名文档
> `docs/上游-GUI校验根参数提案.md`）。
> 适用：`pycbeta` GUI 独立窗（`python -m pycbeta.gui`）。
> 相关：`docs/校验report.json说明.md` §1（校验根与 `report.json` 布局）；
> `docs/校验说明书.md` §4.4／§5（卷子集与校验落盘）。

## 1 背景

publish 的校验链分两条：

- **进程内 CLI**（publish `bridge.verify_work` → `pycbeta.cli.main`）：可显式传
  `--verify-root`，已把托管产物钉死在 `{输出}/验证/`。
- **独立窗**（publish 菜单「运行 xml2pdf 制作书籍…」→ `python -m pycbeta.gui`，
  publish 预填 `--out=<丛书校验目录>`）：**无法传 `--verify-root`**，校验根只能来自
  预设 `source.verify_root` 或默认 `{--out}/验证`。

问题：若所选预设带非空 `source.verify_root`，独立窗的校验产物会**静默落到 publish
托管区之外**，下游扫不到、也无法从命令行钉死；下游只能用预设对齐提示（清空
`verify_root`）兜底，属绕过而非根治。此外下游 P2（校验结论跨边复用）需要从
GUI 产物 `report.json` 导入通过结论，依赖一个**稳定可发现**的校验根。

目标：给 GUI 独立窗一个与 CLI **同名同语义**的 `--verify-root`，优先级一致，
使下游能把独立窗产物钉进托管目录，与进程内 CLI 行为完全一致。

## 2 现状（上游代码事实，2026-10-07）

- **CLI**：`pycbeta/cli.py:771` 定义 `--verify-root`（`default=""`）；
  `_cli_verify_custom`（`cli.py:470-476`）优先取显式值，否则配置 `source.verify_root`；
  落点规则 `verify.resolve_verify_root`（`verify.py:2817`）：
  **显式 `--verify-root` ＞ 配置 `source.verify_root` ＞ `default_verify_root(输出)`**
  （`verify.py:2811`，即 `{输出}/验证`）。
- **GUI**：`pycbeta/gui/__main__.py:1206-1212` 的 argparse 只有
  `--ids-file / --out / --preset / --formats / --verify / --autostart`，
  **没有 `--verify-root`**；`_apply_launch_args`（`gui/__main__.py:1159-1199`）
  只预填上述参数。
- **GUI 校验根来源**：`BatchWorker.run()`（`gui/__main__.py:244-248`）读预设
  `source.verify_root` → `_verify_custom`；`_verify_dir(out_dir, wid, title,
  verify_root="", sfx="")`（`gui/__main__.py:639`）生效顺序为
  显式形参 ＞ 预设 ＞ `default_verify_root(out_dir)`。面板另有
  `source.verify_root` 行（`panel.py:2356`）与 `_effective_verify_root`
  （`panel.py:2818`，仅展示/清理用）。
- **报告布局**：`{校验根}/{id 书名}（验证）/{fmt}/` ＋
  `{id}_{书名}_校验报告.txt` ＋ `report.json`（JSON 统一名，2026-10-07）。

## 3 最小改动（上游侧，约 10 行）

1. `gui/__main__.py:1206` argparse 增加：
   ```python
   _ap.add_argument("--verify-root", default=None,
                    help="校验根预填（为空=跟随预设 source.verify_root 或 {输出}/验证）")
   ```
2. `_apply_launch_args` 记录本次覆盖值（如 `win._verify_root_override`）；
   `MainWindow._start` 将其并入 worker `paths`（如 `{"verify_root": …}`）。
3. `BatchWorker.run()`：`self._verify_custom = override or 预设 source.verify_root`；
   `_verify_dir` 已接受 `verify_root` 形参，接线即可。
4. 优先级与 CLI 对齐：**显式 ＞ 预设 `source.verify_root` ＞ `{输出}/验证`**。
5. 只影响校验产物落点，不改渲染输出目录（渲染仍在 `--out` 顶层）；
   只读启动参数，不写回预设/配置（面板显示维持现状）。

## 4 优先级

- 对下游：**中**（publish P7 收尾项之一）——影响「运行独立窗 → 导入校验通过」
  链路的可预测性；进程内 CLI 路径不受影响。
- 对上游：小改（3 处、约 10 行）＋ 3 条单测；不传参数时与现状完全一致（零行为变化）。
- 建议排期：与下游消费 `report.json`（P2 校验结论跨边复用）同批，避免下游先做
  「预设清空」临时兜底后再返工。

## 5 验收

- 传 `--verify-root <abs>` 时，`report.json` 与 `{id}_{书名}_校验报告.txt` 落
  `<abs>/{id 书名}（验证）/`；不传时行为与现状一致（预设/默认）。
- 显式值能覆盖预设里的 `source.verify_root`（与 CLI 同断言）。
- 单测：无参回退、预设回退、显式优先三条；渲染输出路径不变（`--out` 顶层）。
- 建议 e2e：`python -m pycbeta.gui --out <tmp> --verify --verify-root <tmp2>
  --autostart`（需 Qt），或至少覆盖 `_apply_launch_args` + worker `paths` 的单测。

## 6 publish 侧影响

- 上游落地后，publish `_open_xml2pdf_window` 追加
  `--verify-root <丛书校验目录>/验证`，与进程内 CLI 路径一致；预设对齐提示可保留
  作兜底，但不再是唯一手段。
- 下游 P2 的「发现 GUI 产物 `report.json`」获得稳定根（不再依赖用户预设是否设置
  `source.verify_root`）。

## 7 实现记录（2026-10-07）

- `gui/__main__.py`：argparse 增 `--verify-root`（`default=None`）；`_apply_launch_args`
  记 `win._verify_root_override`（仅本次运行，不写回预设）；`MainWindow._start` 把
  `verify_root` 并入 worker `paths`；新增纯函数 `_pick_verify_root(override, presets)`
  （显式 ＞ 预设 ＞ `""`），`BatchWorker.run()` 用其得 `_verify_custom`，`_verify_dir`
  沿用既有 `verify_root` 形参与 `default_verify_root` 兜底。
- 单测 `test_gui.TestVerifyRootOverride` 4 项：优先级四态、`_apply_launch_args` 预填、
  无参数不设覆盖、worker `paths` 覆盖胜出；`test_gui` 285 OK。
- 仅影响校验产物落点（`{校验根}/{id 书名}（验证）/`），渲染输出仍在 `--out` 顶层。
