# engines/ — 外部 PDF 引擎（可选）

本目录用于放置可选的外部 PDF 后端可执行文件。为控制仓库体积，`*.exe`
不入库，请从项目 **GitHub Releases** 页面下载后放入本目录：

- `cbetapdf.exe` — HTML→PDF 后端（`--engine html2pdf:cbetapdf`）
- `minipdf.exe` — DOCX→PDF 链尾兜底（`--engine docx2pdf:minipdf`）

未放置时相关引擎在探测/链式尝试中自动跳过，不影响其他后端。

路径可在 `pycbeta/config.json` 的 `engines.external` 中自定义。
