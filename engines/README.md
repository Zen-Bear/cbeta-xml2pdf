# engines/ — 外部 PDF 引擎（可选）

本目录用于放置可选的外部 PDF 后端可执行文件。为控制仓库体积，`*.exe`
不入库，请按下述地址自行下载后放入本目录（本项目 Releases **不**提供附件）：

- `minipdf.exe` — DOCX→PDF 链尾兜底（`--engine docx2pdf:minipdf`）；
  上游 `minipdf-win-x64.zip`（MiniPdf.Cli v0.38.5）：
  https://github.com/mini-software/MiniPdf/releases/download/v0.38.5/minipdf-win-x64.zip
  （解压即得，已验证与本机版本逐字节一致）
- `cbetapdf.exe` — HTML→PDF 备选后端（`--engine html2pdf:cbetapdf`）；
  暂无公开下载（可选；默认走 chromium）。如已持有该文件，直接放入本目录即可。

未放置时相关引擎在探测/链式尝试中自动跳过，不影响其他后端。

路径可在 `pycbeta/config.json` 的 `engines.external` 中自定义。
