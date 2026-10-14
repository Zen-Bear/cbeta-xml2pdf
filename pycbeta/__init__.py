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
__version__ = "0.91"

__all__ = ["P5Parser", "GaijiDb", "__version__"]
