"""简体转换：IR 文本层后处理（OpenCC t2s），渲染前调用，各渲染器零改动。

架构（docs/CBETA-P5-设计规格.md D7）：解析 → IR → 文本层后处理（本模块）→ 各渲染器。
只改 Text.text 与 metadata 字符串；节点结构 / line / Gaiji / NoteRef 不动。

正确性设计：
- 块级拼接：以顶层块/注释/校勘读本为拼接单元，把单元内 Text 文本顺序拼接成
  完整句子再整体转换，恢复跨节点短语上下文（如 乾|坤 被 lb/缺字打断时仍按
  乾坤 处理，不会误转成 干坤）。
- 长度守恒：OpenCC t2s 输出长度恒等于输入（1:1 字典），按原始偏移切回各
  Text 节点，零结构改动。
- NoteRef 以空格占位：上标注码在阅读上是停顿，「執著¹作」不合并为「执著作」。
- 佛典专名修正：t2s 词表对部分佛典专名过度泛化（乾 一律→干，而 qián 音
  规范保留 乾，如 乾闥婆/乾坤），转换后按表回写；繁体源文中不会自然出现
  「干闼婆」等输出，替换无副作用。

用法：
    from .simplify import simplify_work, simplify_text
    w = P5Parser().parse(xml_fn)
    if args.t2s:
        simplify_work(w)
    baseline_simplified = simplify_text(official_text)
"""

from typing import Dict, List, Optional

from .model import App, E, NoteRef, Text, Work

# OpenCC t2s 误转的佛典专名：键=OpenCC 输出，值=规范简体（转换后回写）。
# 乾 读 qián（乾坤/乾隆/乾闥婆 等）时规范保留「乾」；t2s 一律转「干」。
# 注意异体码点：闥 U+95E5 的异体 U+95A5（字形同为“闥”）经 t2s 转为 U+9600
# 而非 U+95FC，故“乾\x95a5婆”类输入会漏过 "干闼婆" 键，需单列变体条目
# （键内用 \u 转义书写，避免与 U+95E5/U+95FC 字形混淆）。
# 条目按长度降序应用（先长后短，避免子串截断）。
_SIMPLIFY_FIXES: List[tuple] = sorted([
    ("干闼婆王", "乾闼婆王"),
    ("干闼婆", "乾闼婆"),
    ("干" + chr(0x9600) + "婆", "乾闼婆"),  # U+95A5 异体经 t2s 的输出形态（子串覆盖王/城等）
    ("干陀罗", "乾陀罗"),
    ("干慧地", "乾慧地"),
    ("干沓和", "乾沓和"),
    ("干闼城", "乾闼城"),
    ("干闼王", "乾闼王"),
    ("目干连", "目乾连"),
], key=lambda kv: len(kv[0]), reverse=True)


class _Converter:
    """拼接单元转换器：把一组节点内的 Text 拼接成完整句子 → OpenCC → 切回。"""

    def __init__(self):
        from opencc import OpenCC
        self._cc = OpenCC("t2s")

    def _fix(self, s: str) -> str:
        for wrong, right in _SIMPLIFY_FIXES:
            s = s.replace(wrong, right)
        return s

    def convert_unit(self, nodes: List[object]) -> None:
        """把一个拼接单元（顶层块/注释/校勘读本）内的 Text 就地转为简体。"""
        buf: List[str] = []
        texts: List[tuple] = []  # (Text, start, end)
        pos = 0

        def walk(items: List[object]) -> None:
            nonlocal pos
            for n in items:
                if isinstance(n, Text):
                    if n.text:
                        texts.append((n, pos, pos + len(n.text)))
                        buf.append(n.text)
                        pos += len(n.text)
                elif isinstance(n, NoteRef):
                    # 上标注码是阅读停顿：以空格占位，阻断跨注码词表匹配
                    buf.append(" ")
                    pos += 1
                elif isinstance(n, App):
                    pass  # 校勘（lem/rdg）单独成单元，不参与正文拼接
                elif isinstance(n, E):
                    walk(n.children)

        walk(nodes)
        if not texts:
            return
        stitched = "".join(buf)
        converted = self._fix(self._cc.convert(stitched))
        if len(converted) == len(stitched):
            for node, a, b in texts:
                node.text = converted[a:b]
        else:
            # 长度守恒意外失效（OpenCC 版本差异）：逐节点转换兜底
            for node, _a, _b in texts:
                node.text = self._fix(self._cc.convert(node.text))

    def convert_string(self, s: str) -> str:
        return self._fix(self._cc.convert(s))


_cv = None


def simplify_text(s: str) -> str:
    """纯文本转简体（OpenCC t2s + 专名修正），与 simplify_work 同一管线。

    供校验侧转换官方基线：官方抽取文本已是连续纯文本，直接整串转换即可
    （无 IR 分片问题）；转换器模块级缓存，OpenCC 初始化只一次。"""
    global _cv
    if _cv is None:
        _cv = _Converter()
    return _cv.convert_string(s)


def simplify_work(work: Work) -> None:
    """把 Work 的正文 / 注释 / 校勘 / 元数据文本就地转为简体。"""
    cv = _Converter()
    # 正文：每个顶层块为一个拼接单元
    for block in work.body:
        cv.convert_unit([block])
    # 注释（校注/脚注文本）
    for notes in work.notes_by_n.values():
        for note in notes:
            cv.convert_unit([note])
    # 校勘异读：lem 与每个 rdg 各自独立成单元
    for app in work.apps:
        if app.lem is not None:
            cv.convert_unit([app.lem])
        for rdg in app.rdgs:
            cv.convert_unit([rdg])
    # 元数据（书名/作者/译者/经藏名等完整字符串，直接转换）
    for key, val in work.metadata.items():
        if isinstance(val, str) and val:
            work.metadata[key] = cv.convert_string(val)
    # 置位：渲染时解析的缺字（Gaiji 节点，渲染器 _resolve_gaiji）同样过 t2s 管线，
    # 与校验侧 t2s_baseline 对齐，否则简体校验会出现缺字简繁不一致
    work.simplified = True