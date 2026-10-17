"""pycbeta: CBETA XML P5 -> IR converter."""

from .gaiji import GaijiDb
from .parser import P5Parser

# 单点版本号（语义化版本）：
# GUI 标题栏 + CLI --version 都从这里取，改一处即全局生效。
# 0.1 = 首个公开发布（GPLv3）；0.5 = 出厂改名 + 边框三键 + 输入帮助；
# 0.7 = 校验基线 tab + 设置窗口收编 + 卷子集预分区 + 字库选择修复。
# 0.9 = 校验对齐修复（txt 科判注/星号位、epub 正文旁路；X0287 从数小时→秒级）
#       + 校验阶段进度（状态列）+ html 产物进文件列。
# 0.91 = 校验提速与报告瘦身：基线按卷核对补缺（残卷不再当全量）、行首 No. 令牌两侧恒剥、
#        报告差异段封顶（50 字 / 10 个 〓，报告 5.8MB→29KB）、校验汇总弹窗加「打开报告」链接
#        与生成/校验耗时、报告与 report.json 带基线覆盖（T1579 txt 5.4s、epub 9.1s 均 0/0）。
# 0.92 = 校验指纹提速与语义修正：基线发现改为"集中库布局直接定位优先、未命中回退通配符"
#        （单次 1738ms→45.9ms，结果与指纹逐字一致）；指纹载荷文件身份不含 mtime_ns
#        （同字节重写不再误触发重验）；指纹版本 verify-fp-1→verify-fp-2（并修掉返回串硬编码）。
# 0.93 = 表格与标题口径 + 校验基线链调整：docx 表格框线/整体对齐改由 CSS `table { border; text-align }`
#        控制（粗细/线型/颜色/不画线可调）、列宽智能分配（每列最多 T 行、保底 4 字）+ tblLayout fixed；
#        `<p cb:type="headN">` 当标题渲染（html class="head"+data-head-level、docx 命名样式 head+
#        outlineLvl N-1、md #×N）；`<cb:mulu>` 书签队列化（连续多条合并落地，不再覆盖丢弃）；
#        epub 校验基线链顺序改为 html → txt_notes → epub（缺基线自动下载跟链首）。
# 0.94 = 书签与校验修正（T31n1585 成唯识论案例）：docx 书签名 XML 转义（书签名含 `>`/`&` 等
#        不再产出非法 document.xml）；校验剥标签改引号感知（属性里的 `>` 不再被截成 `"/>` 伪差异）；
#        空「卷」标记以卷级提示入队（不落书签），卷题回到 Word 导航第一层。
__version__ = "0.94"

__all__ = ["P5Parser", "GaijiDb", "__version__"]
