# 预设目录（保留兼容，内置组已退役）

CSS 编辑器顶部的"预设"下拉只列：出厂默认（`pdf_docx.css`）+ 仓库根
`css-presets/`（用户预设，不入库）。`list_presets` 对旧内置名仍能查到
（向后兼容），但不再陈列、不再新增。

用户预设（含示例 `css-presets/large-print.css`、`my.css`）格式不变：
只存覆盖块（编辑器源码页文本），不存出厂快照。加载时出厂 + 覆盖合并
（层叠后胜；`theme_file_text`）。
