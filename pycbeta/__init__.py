"""pycbeta: CBETA XML P5 -> IR converter."""

from .gaiji import GaijiDb
from .parser import P5Parser

# 单点版本号（语义化版本）：
# GUI 标题栏 + CLI --version 都从这里取，改一处即全局生效。
# 0.1 = 首个公开发布（GPLv3）；0.5 = 出厂改名 + 边框三键 + 输入帮助后的版本。
__version__ = "0.5"

__all__ = ["P5Parser", "GaijiDb", "__version__"]
