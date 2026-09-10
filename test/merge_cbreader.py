"""CBReader 按卷碎片按组合册（手动一次性工具；库见 pycbeta/merge.py）。

CBReader 书库布局 `XML/<CANON>/<VOL>/<canon><vol>n<no>_<seq>.xml`
（如 `T/T01/T01n0001_001.xml`…`_022.xml`），每卷一个独立 TEI；
落盘 `<out>/<CANON>/<VOL>/<stem>.xml`（一册一书，与出版书一致；
find_local_xml 可直接命中，管线按册渲染）。
输出比输入新则跳过（除非 --force）。

用例：
  python test/merge_cbreader.py --only T01n0001 -o E:\\dev\\cbeta\\test\\_cbreader
  python test/merge_cbreader.py --only TX0006 -o E:\\dev\\cbeta\\test\\_cbreader
  python test/merge_cbreader.py --canon T -o E:\\dev\\cbeta\\test\\_cbreader
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pycbeta.merge import collect, merge, _only_match


def main(argv=None):
    ap = argparse.ArgumentParser(description="合并 CBReader 按卷碎片（按组合册）")
    ap.add_argument("--src", default=r"E:\CBETA\CBReader2X\Bookcase\CBETA\XML")
    ap.add_argument("-o", "--out", required=True, help="落盘根目录")
    ap.add_argument("--canon", default="", help="只合某部（如 T），空=全部")
    ap.add_argument("--only", default="",
                    help="只合某本（碎片 stem 如 T01n0001 / 归一 TXn0006 / 佛典編號如 TX0006，多册全中）")
    ap.add_argument("--force", action="store_true", help="输出已最新也重写")
    args = ap.parse_args(argv)
    n_work, n_skip = 0, 0
    for (canon, vol, no), files in sorted(collect(args.src).items()):
        if args.canon and canon.upper() != args.canon.upper():
            continue
        files = sorted(files)
        stems = {s for _, _, _, s in files}
        if not _only_match(args.only, canon, no, stems):
            continue
        stem0 = files[0][3]
        out = os.path.join(args.out, canon, vol, f"{stem0}.xml")
        if not args.force and os.path.isfile(out) and os.path.getmtime(out) >= max(
                os.path.getmtime(p) for _, _, p, _ in files):
            n_skip += 1
            continue
        got = merge(files, out)
        if got is None:
            n_skip += 1
            continue
        n_work += 1
        print(f"{stem0}: {got[0]} 卷 → {out}（body 子节点 {got[1]}）")
    print(f"done: 合并 {n_work} 本，跳过 {n_skip} 本（已最新）。")


if __name__ == "__main__":
    main()
