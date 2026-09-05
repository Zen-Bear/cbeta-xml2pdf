"""python -m pycbeta 入口。

命令行应用与核心库分离：CLI 实现见 pycbeta/cli.py，
核心（解析/渲染/主题）不依赖本模块。
"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
