# 校验 `report.json` 说明（给下游）

> 面向下游消费者（复用校验结论、跳过重复校验）。
> 上游（`pycbeta`）已落地 Phase 1：指纹函数 + `report.json`；
> 通过记录库与跳过逻辑（Phase 2）在下游做，上游不做跳过、每次真校验。

## 1. 文件在哪里

每次 `--verify` / `--verify-only` / GUI 转换后校验，都在校验目录旁写一份机读结论：

- CLI：`{校验根}/{id 书名}（验证）/report.json`
  （校验根默认 `{输出}/验证`；`--verify-root` 或配置 `source.verify_root` 可改）
- GUI：`{校验根}/{id 书名}（验证）/{id}_{书名}_校验报告.json`
  （与 `{id}_{书名}_校验报告.txt` 配对，不进文件列）

文本报告（给人看）与 JSON（给机器读）同目录、每次覆盖写；
`fail` / `undetermined` / `error` 照写不缺席。

真实例子（X1077 docx，`verdict: pass`）：

```text
out/验证/X1077 准提净业（验证）/X1077_准提净业_校验报告.json
out/验证/X1077 准提净业（验证）/X1077_准提净业_校验报告.txt
```

## 2. 结论枚举（`fmts.<fmt>.verdict`）

| 值 | 含义 | 可否复用 |
|---|---|---|
| `pass` | 真实通过（缺数/多余数 ≤ 阈值且结构合法） | ✅ 唯一可入库/可复用的结论 |
| `fail` | 真实未通过（差异超阈值或结构非法），`reason` 必带缺数/多余数或结构原因 | ❌（这是"没通过"，不是"没结果"） |
| `undetermined` | 无法判定：`no_baseline` / `covered:docx` / `gen_not_found` / `no_record` | ❌ 不入库 |
| `error` | 环境/流程失败（渲染失败、异常、未知状态），`reason` 保留可读原因 | ❌ 不入库、不删旧有效记录 |

规则：`undetermined` / `error` 既不入库，也不删除旧有效记录。

## 3. 字段结构

```json
{
  "schema": 1,
  "fingerprint_version": "verify-fp-1",
  "tool": {"name": "pycbeta", "version": "0.1"},
  "verify_impl": {"module": "pycbeta.verify", "digest": "sha256:…",
                   "algorithm": "verify-1"},
  "work": "X1077",
  "requested_formats": ["docx"],
  "thresholds": {"max_diff": 5, "diff_lines": 5},
  "inputs": {
    "xml_files": [{"name": "X59n1077.xml", "size": 317298,
                   "mtime_ns": 1790017377561217800}],
    "config_digest": "sha256:…",
    "baselines": {"docx": [{"name": "…", "size": 0, "mtime_ns": 0}]},
    "coverage": {"pdf": "docx"}
  },
  "fmts": {
    "docx": {
      "verdict": "pass",
      "fingerprint": "verify-fp-1:sha256:…",
      "missing": 0,
      "extra": 0,
      "reason": null,
      "formal_outputs": ["…/X59n1077.docx"],
      "report": "X1077_准提净业_校验报告.txt"
    }
  },
  "created_at": "2026-…"
}
```

- `xml_files` / `baselines` 只有 `name/size/mtime_ns`（无 sha；sha 只进指纹）。
- `coverage` 只在请求了 `pdf` 时出现（`pdf` 无官方基线，结论随其管线源格式）。
- 新增字段向后兼容；语义变化会升级 `schema` 或 `fingerprint_version`；未知字段请忽略。

## 4. 指纹复用契约（下游 Phase 2 用）

- 上游 API：`pycbeta.verify.verify_fingerprint(work_id, fmt, xml_files=…,
  config_path=…, max_diff=…, diff_lines=…, …) -> str | None`。
  返回 `None` = "不能证明仍然有效"，**一律重验**（找不到 XML、基线缺失、
  配置不可解析、不支持的格式等都返回 `None`；无副作用，不下载不渲染不写文件）。
- 指纹按 `(work, fmt)` 粒度，纳入：XML 内容标识、生效配置摘要、校验实现摘要
  （`pycbeta.__version__` + 相关模块源码哈希，改实现即失效）、实际基线、
  阈值与覆盖关系。本机有效，不保证跨机器可比。
- 建议的跳过条件（全部成立才跳过）：库中有该 `(work, fmt)` 的 `pass` 记录、
  且 `verify_fingerprint` 现算值与记录一致、`verify_impl.digest` 一致、
  产物存在、复用开关开。
- 发现接口：`pycbeta.verify.find_verify_reports(verify_root)` 掃
  `{校验根}/*（验证）/`，返回 `[{id, title, dir, report_json, report_txt}]`；
  `parse_verify_report_name(name)` 解析目录名。

## 5. 文本报告兼容性

`report.txt` / `{id}_{书名}_校验报告.txt` 的现有文本格式、命名（除本次更名外）
保持不变；`{输出}/验证` 总目录、`--verify-root`、`source.verify_root`
见本说明 §1。
