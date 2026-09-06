# cbeta/data（随包数据，缺字库本库）

`pycbeta/gaiji.py` 默认从本目录读取（`GaijiDb()` 无参即此）。ruby-cbeta 已删除，不要回指。

| 文件 | 来源（官方上游） | 更新办法 |
|---|---|---|
| `cbeta_gaiji.json`、`cbeta_sanskrit.json` | CBETA 缺字資料庫 https://github.com/cbeta-org/cbeta_gaiji | 从上游取新 JSON 直接覆盖本目录同名文件 |
| `sutra_mapping.txt` | publish 原件 `E:\dev\cbeta\publish\mulu\sutra_mapping.txt`（仓内版为备份快照） | 从上游复制覆盖 |

已删（2026-09-06，无代码引用）：`html-for-pdf.css` + `pdf-template.htm`（Prince 旧管线残留，互为唯一引用）；
`canons.csv`、`categories.json`、`unicode-1.1.json`（ruby-cbeta 旧数据；要用去上游 cbeta_gaiji 仓取）。

补充字形字体不在此目录，在 `../fonts/CBETASupplement.ttf`，
上游：CBETA 補充字型 https://github.com/cbeta-org/cbeta-fonts（取 release TTF 覆盖）。
