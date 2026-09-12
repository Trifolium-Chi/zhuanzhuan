#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作流 run 块的 shell 结构校验（不需要网络，也不需要 shell）

做法：把每个 `run: |` 块抽出来，剥掉注释和字符串，
用栈检查 if/fi、for/done、while/done、case/esac 是否配对。

用法：python3 tools/shellcheck_workflow.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WF = os.path.join(ROOT, ".github", "workflows", "build.yml")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OPENERS = {"if": "fi", "for": "done", "while": "done", "case": "esac"}
CLOSERS = {"fi", "done", "esac", "elif", "else"}


def get_run_blocks(text):
    """抽出所有 run: | 块的正文（按缩进判断块范围）"""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)run:\s*\|-?\s*$", lines[i])
        if not m:
            i += 1
            continue
        base = len(m.group(1))
        body = []
        j = i + 1
        while j < len(lines):
            l = lines[j]
            if l.strip() == "":
                body.append(l)
                j += 1
                continue
            ind = len(l) - len(l.lstrip())
            if ind <= base:
                break
            body.append(l)
            j += 1
        blocks.append((i + 1, body))
        i = j
    return blocks


def strip_noise(line):
    """去掉行内注释（粗略，够用即可），并把单双引号里的内容替换掉"""
    out = []
    i = 0
    n = len(line)
    quote = None
    while i < n:
        c = line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            out.append(" ")
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            out.append(" ")
            i += 1
            continue
        if c == "#":
            # 只在词首才算注释（避免 #! / ${#x}）
            if i == 0 or line[i - 1] in " \t;|&(":
                break
        out.append(c)
        i += 1
    return "".join(out)


def check_block(start_line, body):
    stack = []
    problems = []
    for k, raw in enumerate(body):
        ln = start_line + 1 + k
        code = strip_noise(raw)
        # 取行首第一个 shell 词
        toks = code.strip().split()
        if not toks:
            continue
        head = toks[0].rstrip(";")
        # `if` 也可能出现在 `; then` 之后的形式，这里只认行首
        if head in OPENERS and (
            head != "if" or line_starts_keyword(code, "if")
        ):
            stack.append((head, ln))
        elif head in ("fi", "done", "esac"):
            if not stack:
                problems.append("行 %d: 多余的 '%s'（没有对应的开启关键字）" % (ln, head))
                continue
            opener, oln = stack.pop()
            expect = OPENERS[opener]
            if expect != head:
                problems.append("行 %d: '%s' 与行 %d 的 '%s' 不匹配（应为 '%s'）"
                                % (ln, head, oln, opener, expect))
        elif head in ("elif", "else"):
            if not stack or stack[-1][0] != "if":
                problems.append("行 %d: '%s' 不在 if 块内" % (ln, head))
    for opener, oln in stack:
        problems.append("行 %d: '%s' 没有闭合（缺少 '%s'）" % (oln, opener, OPENERS[opener]))
    return problems


def line_starts_keyword(code, kw):
    return re.match(r"^\s*%s\b" % kw, code) is not None


def main():
    text = io.open(WF, encoding="utf-8").read()
    blocks = get_run_blocks(text)
    print("工作流:", os.path.relpath(WF, ROOT))
    print("发现 run 块:", len(blocks))
    total = 0
    for start, body in blocks:
        probs = check_block(start, body)
        if probs:
            total += len(probs)
            print("\n[run 块 @ 行 %d] 有问题：" % start)
            for p in probs:
                print("   -", p)
        else:
            print("  [OK] run 块 @ 行 %-4d 控制流配对正常（%d 行）" % (start, len(body)))

    # 额外：YAML 顶层键
    print("\n顶层键:", [l for l in text.splitlines()
                     if l and not l.startswith((" ", "#", "-"))])

    print()
    if total:
        print("发现 %d 处 shell 结构问题" % total)
        return 1
    print("所有 run 块 shell 结构检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
