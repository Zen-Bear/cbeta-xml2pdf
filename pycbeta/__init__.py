"""pycbeta: CBETA XML P5 -> IR converter."""

from .gaiji import GaijiDb
from .parser import P5Parser

# 单点版本号（语义化版本）：
# GUI 标题栏 + CLI --version 都从这里取，改一处即全局生效。
# v1.0 = 独立窗改名里程碑；1.1.0 = 其后加法功能合集
# （--verify-only/注音三选一/corr-cbeta/catalog 钉死/数据源 tab 化…）。
__version__ = "1.1.0"

__all__ = ["P5Parser", "GaijiDb", "__version__"]
