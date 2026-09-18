#!/usr/bin/env python3
"""talk-like-scarletkc 风格检查器。

检测输出文本中的 AI 写作特征和标点硬规则违规，只提示，不改写。
误报和漏报都可能存在，最终判断由使用者负责。

用法:
    python lint_style.py FILE [FILE ...]
    python lint_style.py -              # 从 stdin 读取
    echo "文本" | python lint_style.py

退出码: 0 = 未发现问题, 1 = 有提示, 2 = 用法或读取错误。
"""

from __future__ import annotations

import re
import sys

# 每条规则: (规则 id, 正则, 提示信息)
RULES = [
    (
        "em-dash",
        re.compile(r"[—―]"),
        "长破折号，中英文都禁止使用",
    ),
    (
        "binary-reversal",
        re.compile(
            r"不是[^。！？!?\n]{1,40}[，,]\s*而是"
            r"|不(?:只|仅|单)(?:仅|单)?是[^。！？!?\n]{1,40}[，,]?\s*(?:更|而)是"
            r"|真正的[^。！？!?\n]{0,12}不是[^。！？!?\n]{1,40}[，,]"
            r"|不再是[^。！？!?\n]{1,40}[，,]\s*而(?:是|变成)"
            r"|与其说[^。！？!?\n]{1,40}不如说"
        ),
        "反转句候选：删掉刻意反差，保留必要的纠错或对比",
    ),
    (
        "negative-framing",
        re.compile(
            r"(?:是)?为了(?:避免|防止|不让)"
            r"|[，,]\s*(?:以)?(?:避免|防止)[^。！？!?\n]{2,20}"
            r"|只(?:做|改|动|加|写|返回|处理|读|取)了?[^。！？!?\n]{0,20}[，,]?\s*(?:没有?|不)"
            r"(?:做|改|动|加|写|返回|处理|读|取|抛)"
            r"|直接[^。！？!?\n]{1,15}[，,]?\s*不(?:做|改|动|返回|处理|抛出?|走|调用)"
        ),
        "否定表达候选：保留必要原因、行为差异和范围，只删无关分支",
    ),
    (
        "vague-experience-word",
        re.compile(r"手感|质感|调性"),
        "体验词候选：具体材质或反馈描述可保留，指代不清时补充细节",
    ),
    (
        "hollow-phrase",
        re.compile(
            r"值得注意的是|毫无疑问|不可否认|从某种意义上来?说"
            r"|在一定程度上|让我们深入探讨|归根结底|总而言之|说到底"
            r"|这背后反映的?是|这也让我意识到|综上所述"
            r"|在当今[^。！？!?\n]{0,10}(?:时代|世界|社会)"
        ),
        "空洞铺垫短语，删掉后直接进入内容",
    ),
    (
        "ai-opener",
        re.compile(
            r"\A\s*(?:当然可以|这是一个很有意思的问题|以下是[^。\n]{0,15}(?:版本|内容)"
            r"|关于这个问题|最近我一直在思考)"
        ),
        "AI 式开场，第一句应该承载真正想说的东西",
    ),
    (
        "robot-ending",
        re.compile(
            r"希望(?:这|以上)?(?:篇|条|些)?(?:内容)?能?帮(?:助)?到?(?:你|您|大家)"
            r"|有(?:任何)?需要(?:请)?随时(?:告诉|联系|找)我"
            r"|你怎么看[？?]?|大家觉得呢|欢迎在?评论区"
            r"|如果你愿意[，,]?我还?可以|需要的话我可以再?"
        ),
        "聊天机器人结尾，除非用户明确要求互动引导",
    ),
    (
        "canned-metaphor",
        re.compile(
            r"一路狂奔|踩下?油门|泥潭里?(?:挣扎|打转)|陷入泥潭"
            r"|插上了?翅膀|高歌猛进"
        ),
        "比喻候选：保留帮助理解的类比和原有幽默，删掉纯装饰性加工，修正具体误导",
    ),
    (
        "hedging-filler",
        re.compile(
            r"双方都有道理|因人而异|理性看待|技术本身没有好坏"
            r"|这取决于每个人的需求"
        ),
        "和稀泥表达，确认这确实是用户想说的再保留",
    ),
]

QUOTE_CHARS = re.compile(r"[“”]")  # 中文双引号 “ ”
SUMMARY_OPENER = re.compile(
    r"(?:^|[。！？!?\n])\s*(?:总之|总的来说|简单来说|一句话|所以说|总结一下)"
)


def mask_code(text: str) -> str:
    """把代码块和行内代码替换成空格，保留行列位置，避免误报技术标识。"""

    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"```.*?(?:```|\Z)", blank, text, flags=re.S)
    text = re.sub(r"`[^`\n]+`", blank, text)
    return text


def line_col(text: str, pos: int) -> tuple[int, int]:
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def lint(text: str, source: str) -> list[str]:
    findings = []
    masked = mask_code(text)

    for rule_id, pattern, message in RULES:
        for match in pattern.finditer(masked):
            line, col = line_col(masked, match.start())
            snippet = match.group(0).strip()[:30]
            findings.append(
                f"{source}:{line}:{col} [{rule_id}] {snippet!r} 提示: {message}"
            )

    # 中文引号: 少量属于合法用法(直接引用、作品名), 只在偏多时提示。
    quotes = list(QUOTE_CHARS.finditer(masked))
    prose_len = len(re.sub(r"\s", "", masked))
    if len(quotes) > 4 or (prose_len > 0 and len(quotes) / prose_len > 0.02):
        line, col = line_col(masked, quotes[0].start())
        findings.append(
            f"{source}:{line}:{col} [quote-density] 中文引号出现 "
            f"{len(quotes)} 次 提示: 只保留直接引用和作品名，其余删掉"
        )

    # 连续总结: 同一段文本里反复收尾是生成文本的典型特征。
    summaries = list(SUMMARY_OPENER.finditer(masked))
    if len(summaries) >= 2:
        line, col = line_col(masked, summaries[-1].start())
        findings.append(
            f"{source}:{line}:{col} [summary-stack] 出现 {len(summaries)} 个"
            f"总结句式 提示: 核心判断说清楚一次就够，最后一条有用信息说完即可结束"
        )

    return findings


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = argv[1:]
    if not args or args == ["-"]:
        sources = [("<stdin>", sys.stdin.read())]
    else:
        sources = []
        for path in args:
            try:
                with open(path, encoding="utf-8") as fh:
                    sources.append((path, fh.read()))
            except OSError as err:
                print(f"无法读取 {path}: {err}", file=sys.stderr)
                return 2

    findings = []
    for source, text in sources:
        findings.extend(lint(text, source))

    for item in findings:
        print(item)

    if findings:
        print(f"\n共 {len(findings)} 处提示。提示不等于必须修改，请自行判断。")
        return 1
    print("未发现问题。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
