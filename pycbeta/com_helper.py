# -*- coding: utf-8 -*-
"""COM 转换隔离子进程入口：只做 Word/WPS → PDF。

父进程（`render_pdf._com_convert_isolated`）负责超时与终止进程树；
本模块被 `python -m pycbeta.com_helper` 调用，退出码 0=成功，2=失败。
"""
import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pycbeta.com_helper", add_help=False)
    ap.add_argument("--docx", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--progids", required=True)
    ap.add_argument("--pid-file", default=None)
    args = ap.parse_args(argv)
    from .render_pdf import _com_convert
    progids = tuple(p for p in args.progids.split(",") if p)
    try:
        out = _com_convert(args.docx, args.pdf, progids,
                           owned_pid_file=args.pid_file)
    except Exception:  # noqa: BLE001 —— 任何异常都按失败退出，父进程降级
        return 2
    return 0 if out else 2


if __name__ == "__main__":
    sys.exit(main())
