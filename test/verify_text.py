# -*- coding: utf-8 -*-
"""内容逐字校验：生成的书 vs 官方产物。"""
import argparse, datetime, glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from pycbeta.verify import (generate_formal, extract_text, normalize, diff_stats,
                            find_official, strip_infos, strip_docx_head, merge_docx,
                            _extract_html_parts, _norm_official_txt, _strip_md_marks,
                            _head_no_tokens, _strip_official_no, _strip_no_from,
                            t2s_baseline, _ann_brackets_from, trial_pass_line)
from pycbeta.simplify import simplify_work
from pycbeta.parser import P5Parser
from pycbeta.theme import load_presets

def main(argv=None):
    ap = argparse.ArgumentParser(description="内容逐字校验")
    ap.add_argument("--source", default=r"E:\dev\cbeta\cbeta_ebook")
    ap.add_argument("-f", "--formats", default="html,md,docx,epub")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-diff", type=int, default=None)
    ap.add_argument("--diff-lines", type=int, default=None)
    ap.add_argument("--config", help="自定义 config.json")
    ap.add_argument("--t2s", action="store_true",
                    help="简体校验：生成侧转简体，官方基线经同一 t2s 管线转简体后比对")
    ap.add_argument("--list", default=None,
                    help="ID 列表文件（默认 test/mini-test.txt；每行首 token 为佛典編號，后面都是注释；缺 XML 自动下载到 source）")
    ap.add_argument("--all", action="store_true",
                    help="忽略 ID 列表，校验 source 下全部 XML（旧行为）")
    ap.add_argument("--baseline", choices=["render", "xml"], default="render",
                    help="render=官方渲染产物基线（默认主轨）；xml=P3 辅轨：IR→TXT vs 输入XML直抽（仅 -f txt）")
    args = ap.parse_args(argv)
    src = args.source
    out_root = args.out or os.path.join(src, "out", "verify")
    try:
        _presets = load_presets(args.config) if args.config else load_presets()
        _verify_cfg = _presets.get("verify") or {}
    except Exception:
        _presets = {}
        _verify_cfg = {}
    _ruby_brackets = _ann_brackets_from(_presets)  # 自定义右侧注音括号（未启用→None）
    list_path = args.list or os.path.join(HERE, "mini-test.txt")
    if not args.all and os.path.isfile(list_path):
        print(f"用 ID 列表: {list_path}")
        from pycbeta.fetch import fetch_work, find_local_xml, is_work_id, parse_work_id
        xmls = []
        # utf-8-sig：兼容记事本等带 BOM 的列表文件
        for raw in open(list_path, encoding="utf-8-sig").read().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            wid = re.split(r"[\s,;，；]+", line)[0]
            if not is_work_id(wid):
                print(f"  跳过非法行: {line}")
                continue
            canon, no = parse_work_id(wid)
            found = find_local_xml(src, canon, no)
            if not found:
                print(f"  {wid}: 本地无 XML，从官方下载到 {src}…")
                try:
                    fetch_work(wid, ["xml"], _presets, src)
                except Exception as e:
                    print(f"  {wid}: 下载失败: {e}")
                found = find_local_xml(src, canon, no)
            if not found:
                print(f"  {wid}: 缺 XML（本地无且下载失败），跳过")
                continue
            xmls.extend(found)
        xmls = list(dict.fromkeys(xmls))
    else:
        if not args.all:
            print(f"ID 列表 {list_path} 不存在，回退全部 XML 模式")
        xmls = sorted(glob.glob(os.path.join(src, "**", "*.xml"), recursive=True))
    if not xmls:
        print(f"no XML files in {src}"); return 1
    # 以配置文件 verify 块为准，CLI 显式传参覆盖
    verify_overrides = {k: v for k, v in _verify_cfg.items() if k in ("inline_brackets", "suppress_jhead_dup", "show_close_juan")}
    max_diff = args.max_diff if args.max_diff is not None else _verify_cfg.get("maxDiff", 10)
    diff_lines = args.diff_lines if args.diff_lines is not None else _verify_cfg.get("diffLines", 5)
    compare_infos = bool(_verify_cfg.get("compareInfos", False))
    grand_fail = 0; grand_total = 0; grand_nobase = 0
    log_lines = []
    def log(msg=""):
        print(msg)
        log_lines.append(msg)
    log("校验配置 verify：")
    if _verify_cfg:
        for k, v in _verify_cfg.items():
            log(f"  {k}: {v}")
    else:
        log("  (无 verify 配置，使用默认)")
    log("")
    results = []
    if args.baseline == "xml":
        # P3 辅轨：IR→TXT vs 官方XML→TXT（输入 XML 本身直抽，委托 verify_one）
        fmts = [f.strip() for f in args.formats.split(",") if f.strip()]
        if fmts != ["txt"]:
            print("--baseline xml 仅支持 -f txt"); return 2
        from pycbeta.verify import verify_one
        for xml_fn in xmls:
            name = os.path.basename(xml_fn)
            block = [f"=== {name}"]
            try:
                r = verify_one(xml_fn, "txt", src, out_root, max_diff, diff_lines,
                               config_path=args.config, t2s=args.t2s, baseline="xml")
            except Exception as e:
                block.append(f"  [FAIL] txt aux: {e}")
                results.append((True, name, block))
                grand_fail += 1; grand_total += 1
                continue
            grand_total += 1
            ok = r["status"] == "ok"
            if not ok:
                grand_fail += 1
            mark = "[OK]" if ok else "[FAIL]"
            op = "≤" if ok else ">"
            block.append(f"  {mark} (缺{r['missing']}/多{r['extra']} {op}阈值{max_diff})")
            block.append(f"  txt 【源】{r['official']} (XML直抽)")
            block.append(f"  txt 【新】{(r['gen'] or [''])[0]}")
            if r.get("src_cmp") and r.get("gen_cmp"):
                block.append(f"  txt 【源】{r['src_cmp']}")
                block.append(f"  txt 【新】{r['gen_cmp']}")
            if not ok and r.get("ctx"):
                ours = normalize(extract_text((r["gen"] or [""])[0]), _ruby_brackets) \
                    if r.get("gen") else ""
                theirs = normalize(extract_text(r["src_cmp"]), _ruby_brackets) \
                    if r.get("src_cmp") else ""
                for idx, (tag, i1, i2, j1, j2) in enumerate(r["ctx"][:diff_lines], 1):
                    a_snip = ours[max(0, i1-10):i1+40].replace("\n", "")
                    b_snip = theirs[max(0, j1-10):j1+40].replace("\n", "")
                    block.append(f"      {idx}. 【源】{b_snip}\n         【新】{a_snip}")
            results.append((not ok, name, block))
        results.sort(key=lambda item: (0, item[1]) if item[0] else (1, item[1]))
        done_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = f"{grand_total} compared, {grand_fail} failed (baseline=xml, 阈值 max-diff={max_diff})"
        log(f"完成时间: {done_at}")
        log(f"源: {src}  输出: {out_root}  基线: 输入XML直抽  阈值: {max_diff}")
        log("")
        log(summary)
        log("说明: P3 辅轨 IR→TXT vs 官方XML→TXT，查解析层丢字（渲染层问题归主轨）")
        log("")
        for _, _, block in results:
            for line in block:
                log(line)
        try:
            os.makedirs(out_root, exist_ok=True)
            report_path = os.path.join(out_root, "report_xml.txt")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(log_lines) + "\n")
            print(f"报告已写入: {report_path}")
        except Exception as e:
            print(f"写入报告失败: {e}")
        return 0 if grand_fail == 0 else 1
    for xml_fn in xmls:
        name = os.path.basename(xml_fn)
        block = [f"=== {name}"]
        block_failed = False
        try:
            work = P5Parser().parse(xml_fn)
            # 繁体剥离键：官方基线恒为繁体，官方侧 strip_docx_head 必须用繁体键
            t_title = (work.metadata.get("title") or "").strip()
            t_docnumber = (work.metadata.get("docNumber") or "").strip()
            t_series = (work.metadata.get("series") or "").strip()
            if args.t2s:
                simplify_work(work)
        except Exception as e:
            block.append(f"  PARSE FAIL: {e}")
            grand_fail += 1; grand_total += 1
            block_failed = True
            results.append((block_failed, name, block))
            continue
        official = {}
        scope_juan = bool(_verify_cfg.get("scope_juan", True))
        # strip_head_no 联动：生成侧（generate_formal 同源开关）已剥则官方侧对等剥离
        _strip_no = _strip_no_from(args.config)
        strip_tokens = _head_no_tokens(work) if _strip_no else []
        _juan = None
        if scope_juan:
            from pycbeta.verify import work_juan_numbers
            _juan = work_juan_numbers(work)
        for kind in ("html", "txt_notes", "docx", "epub", "odt"):
            found = find_official(src, os.path.splitext(name)[0], kind,
                                  juan=_juan if kind in ("html", "docx", "txt_notes") else None)
            if found: official[kind] = found
        for fmt in [f.strip() for f in args.formats.split(",") if f.strip()]:
            outdir = os.path.join(out_root, fmt)
            try:
                gen_paths = generate_formal(xml_fn, work, fmt, outdir, config_path=args.config, overrides=verify_overrides)
            except Exception as e:
                block.append(f"  [FAIL] {fmt:5} gen: {e}")
                grand_fail += 1; grand_total += 1
                block_failed = True
                continue
            ours_raw = "".join(extract_text(p) for p in gen_paths)
            docnumber = (work.metadata.get("docNumber") or "").strip()
            series = (work.metadata.get("series") or "").strip()
            if fmt == "docx":
                title = (work.metadata.get("title") or "").strip()
                ours_raw = strip_docx_head(ours_raw, title, docnumber, series)
            if fmt == "md":
                ours_raw = _strip_md_marks(ours_raw)
            if not compare_infos:
                ours_raw = strip_infos(ours_raw)
            ours = normalize(ours_raw, _ruby_brackets)
            base_kind = {"md":"txt_notes","docx":"docx","html":"html","epub":"epub","txt":"txt_notes"}.get(fmt,"html")

            def _bases(official):
                b = []
                if base_kind in official:
                    b.append((base_kind, official[base_kind]))
                if fmt != "txt":
                    fb = official.get("html")
                    if fb and all(p != fb for _, p in b): b.append(("html", fb))
                return b

            bases = _bases(official)
            if base_kind not in official and bool(_verify_cfg.get("auto_fetch", True)):
                # 首选基线缺失：按需调用 fetch 下载（docx/odt 非 T/X 等 404 静默跳过）
                from pycbeta.fetch import ensure_baselines
                need = {"md": ["txt_notes"], "docx": ["docx", "html"], "txt": ["txt_notes"],
                        "html": ["html"], "epub": ["epub"]}.get(fmt, ["html"])
                _presets_af = load_presets(args.config) if args.config else load_presets()
                _ebook_af = ((_presets_af.get("source") or {}).get("cbeta_ebook")
                             or "").strip() or src
                ensure_baselines(work.id, need, _presets_af, _ebook_af)
                official = {}
                for kind in ("html", "txt_notes", "docx", "epub", "odt"):
                    found = find_official(src, os.path.splitext(name)[0], kind,
                                          juan=_juan if kind in ("html", "docx", "txt_notes") else None)
                    if found: official[kind] = found
                bases = _bases(official)
            if not bases:
                block.append(f"  [--]  {fmt:5} no baseline")
                grand_total += 1; grand_nobase += 1
                block_failed = True
                continue
            ok_any = False; best = None; detail_lines = []
            stem = os.path.splitext(name)[0]
            for bkind, bpath in bases:
                if isinstance(bpath, list):
                    if bkind == "docx" and len(bpath) > 1:
                        title = t_title
                        if bkind == "docx":
                            # 多卷官方 docx 先合并为单个 docx，再抽取 TXT：脚注统一在文末
                            merged_docx = os.path.join(outdir, f"{stem}_official_merged_{bkind}.docx")
                            merged_docx = merge_docx(bpath, merged_docx)
                            merged_raw = extract_text(merged_docx)
                            merged_raw = strip_docx_head(merged_raw, title, t_docnumber, t_series)
                            if not compare_infos:
                                merged_raw = strip_infos(merged_raw)
                            theirs_raw = merged_raw
                        else:
                            parts = []
                            for p in bpath:
                                txt = extract_text(p)
                                if not compare_infos:
                                    txt = strip_infos(txt)
                                parts.append(txt)
                            theirs_raw = "".join(parts)
                        bpath_disp = f"{bpath[0]} (+{len(bpath)-1})"
                    elif len(bpath) > 1:
                        # 多卷官方 html：docx 回退时脚注统一放文末以对齐 docx；html 自身比较保持原样
                        if bkind == "html" and fmt == "docx":
                            bodies, foots = [], []
                            for p in bpath:
                                b, f = _extract_html_parts(p)
                                title = t_title
                                b = strip_docx_head(b, title, t_docnumber, t_series)
                                f = strip_docx_head(f, title, t_docnumber, t_series)
                                if not compare_infos:
                                    b = strip_infos(b)
                                    f = strip_infos(f)
                                bodies.append(b)
                                foots.append(f)
                            theirs_raw = "".join(bodies) + "\n" + "".join(foots)
                        else:
                            parts = []
                            for p in bpath:
                                txt = extract_text(p)
                                if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                                    title = t_title
                                    txt = strip_docx_head(txt, title, t_docnumber, t_series)
                                if not compare_infos:
                                    txt = strip_infos(txt)
                                parts.append(txt)
                            theirs_raw = "".join(parts)
                        bpath_disp = f"{bpath[0]} (+{len(bpath)-1})"
                    elif bkind == "docx":
                        txt = extract_text(bpath[0])
                        title = t_title
                        txt = strip_docx_head(txt, title, t_docnumber, t_series)
                        if not compare_infos:
                            txt = strip_infos(txt)
                        theirs_raw = txt
                        bpath_disp = bpath[0]
                    else:
                        theirs_raw = extract_text(bpath[0])
                        if bkind == "html" and fmt == "docx":
                            title = t_title
                            theirs_raw = strip_docx_head(theirs_raw, title, t_docnumber, t_series)
                        if not compare_infos:
                            theirs_raw = strip_infos(theirs_raw)
                        bpath_disp = bpath[0]
                else:
                    theirs_raw = extract_text(bpath)
                    if bkind == "docx" or (bkind == "html" and fmt == "docx"):
                        title = t_title
                        theirs_raw = strip_docx_head(theirs_raw, title, t_docnumber, t_series)
                    if not compare_infos:
                        theirs_raw = strip_infos(theirs_raw)
                    bpath_disp = bpath
                if bkind == "txt_notes":
                    # text 族官方侧对齐（繁简通用）：版头剥离 + 注记块识别挪文末
                    theirs_raw = _norm_official_txt(theirs_raw)
                if strip_tokens:
                    theirs_raw = _strip_official_no(theirs_raw, strip_tokens)
                if args.t2s:
                    # 简体校验：官方基线（繁体）经同一 t2s 管线转简体后再比对；
                    # 作用于剥离后的纯文本，落盘 _compare 文件与比对输入一致
                    theirs_raw = t2s_baseline(theirs_raw)
                theirs = normalize(theirs_raw, _ruby_brackets)
                # 保存比较用 TXT
                try:
                    stem = os.path.splitext(name)[0]
                    os.makedirs(outdir, exist_ok=True)
                    src_cmp = os.path.join(outdir, f"{stem}_compare_{bkind}_official.txt")
                    gen_cmp = os.path.join(outdir, f"{stem}_compare_{fmt}_generated.txt")
                    theirs_disp = re.sub(r"\[[^\]\[]{1,8}\]", "", theirs_raw)
                    ours_disp = re.sub(r"\[[^\]\[]{1,8}\]", "", ours_raw)
                    theirs_disp = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", theirs_disp)
                    ours_disp = re.sub(r"[A-Z]{1,2}\d{1,4}[A-Za-z]?n\d+[A-Za-z]?_p[0-9a-z]+", "", ours_disp)
                    theirs_disp = __import__('re').sub(r"\n{3,}", "\n\n", theirs_disp).strip() + "\n"
                    ours_disp = __import__('re').sub(r"\n{3,}", "\n\n", ours_disp).strip() + "\n"
                    with open(src_cmp, "w", encoding="utf-8") as f:
                        f.write(theirs_disp)
                    with open(gen_cmp, "w", encoding="utf-8") as f:
                        f.write(ours_disp)
                except Exception:
                    src_cmp = gen_cmp = ""
                m, mi, ex, ctx = diff_stats(ours, theirs)
                total = mi + ex
                cur = (bkind, bpath_disp, m, mi, ex, ctx, total, src_cmp, gen_cmp)
                if best is None or total < best[6]:
                    best = cur
                if total <= max_diff:
                    ok_any = True
                    detail = trial_pass_line(bkind, mi, ex, total, max_diff)
                    if total>0 and ctx:
                        for idx, (tag,i1,i2,j1,j2) in enumerate(ctx[:diff_lines], 1):
                            a_snip = ours[max(0,i1-10):i1+40].replace("\n","")
                            b_snip = theirs[max(0,j1-10):j1+40].replace("\n","")
                            detail += f"\n      {idx}. 【源】{b_snip}\n         【新】{a_snip}"
                    detail_lines = [detail]
                    break
                else:
                    lines = []
                    for idx, (tag,i1,i2,j1,j2) in enumerate(ctx[:diff_lines], 1):
                        a_snip = ours[max(0,i1-10):i1+40].replace("\n","")
                        b_snip = theirs[max(0,j1-10):j1+40].replace("\n","")
                        lines.append(f"      {idx}. 【源】{b_snip}\n         【新】{a_snip}")
                    snippet = "\n".join(lines) if lines else ""
                    detail = f"      → {bkind} 失败: 缺{mi}字(生成档缺失) / 多{ex}字(生成档多出)，合计{total} >阈值{max_diff}，需检查正文/卷拆分/脚注/标题处理"
                    if snippet:
                        detail += f"\n{snippet}"
                    detail_lines.append(detail)
            if best is None: continue
            bkind, bpath, _, best_mi, best_ex, _, _, src_cmp, gen_cmp = best
            grand_total += 1
            if not ok_any:
                grand_fail += 1
                block_failed = True
            mark = "[OK]" if ok_any else "[FAIL]"
            op = "≤" if ok_any else ">"
            block.append(f"  {mark} (缺{best_mi}/多{best_ex} {op}阈值{max_diff})")
            block.append(f"  {fmt} 【源】{bpath}")
            block.append(f"  {fmt} 【新】{gen_paths[0] if gen_paths else ''}")
            if src_cmp and gen_cmp:
                block.append(f"  {fmt} 【源】{src_cmp}")
                block.append(f"  {fmt} 【新】{gen_cmp}")
            block.extend(detail_lines)
        results.append((block_failed, name, block))
    def _sort_key(item):
        failed, name, block = item
        if failed:
            return (0, name)
        text = "".join(block)
        if "逐字完全一致" in text:
            return (2, name)
        return (1, name)
    results.sort(key=_sort_key)
    done_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if grand_nobase:
        summary = f"{grand_total} compared, {grand_fail} failed, {grand_nobase} no baseline (阈值 max-diff={max_diff})"
    else:
        summary = f"{grand_total} compared, {grand_fail} failed (阈值 max-diff={max_diff})"
    log(f"完成时间: {done_at}")
    log(f"源: {src}  输出: {out_root}  格式: {args.formats}  阈值: {max_diff}")
    log("")
    log(summary)
    log("说明: 缺=生成档比官方少(可能漏正文/脚注/标题)；多=生成档比官方多(可能多出版信息/重复标题)；合计≤阈值则判OK")
    log("说明: 源 TXT 的注释在 TXT 最后，因 CBETA TXT 导出将校注（footnotes/endnotes）统一附于文末；docx 合并后抽取时亦将 footnotes 统一放文末，故新比较 TXT 同在末尾")
    log("")
    for _, _, block in results:
        for line in block:
            log(line)
    try:
        os.makedirs(out_root, exist_ok=True)
        report_path = os.path.join(out_root, "report.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        print(f"报告已写入: {report_path}")
    except Exception as e:
        print(f"写入报告失败: {e}")
    return 0 if grand_fail == 0 else 1

if __name__ == "__main__": sys.exit(main())
