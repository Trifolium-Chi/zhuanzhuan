import io, sys

path = "zzmerge/tweak/ZZMergeBridge.x"
s = io.open(path, encoding="utf-8").read()

depth = 0
line = 1
i = 0
n = len(s)
state = "code"       # code | line_comment | block_comment | string | char
report = []
while i < n:
    c = s[i]
    nxt = s[i + 1] if i + 1 < n else ""
    if c == "\n":
        line += 1
        if state == "line_comment":
            state = "code"
        i += 1
        continue
    if state == "code":
        if c == "/" and nxt == "/":
            state = "line_comment"; i += 2; continue
        if c == "/" and nxt == "*":
            state = "block_comment"; i += 2; continue
        if c == '"':
            state = "string"; i += 1; continue
        if c == "'":
            state = "char"; i += 1; continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                report.append(("NEG", line))
                depth = 0
        elif c == "{":
            pass
    elif state == "block_comment":
        if c == "*" and nxt == "/":
            state = "code"; i += 2; continue
    elif state == "string":
        if c == "\\":
            i += 2; continue
        if c == '"':
            state = "code"
    elif state == "char":
        if c == "\\":
            i += 2; continue
        if c == "'":
            state = "code"
    i += 1

print("扫描结束时圆括号深度 =", depth, "(应为 0)")
for kind, ln in report:
    print("  ", kind, "行", ln)
if depth > 0:
    print("\n有 %d 个左括号未闭合 —— 定位每行累计深度不为 0 的位置：" % depth)
    d = 0
    ln = 1
    i = 0
    state = "code"
    while i < n:
        c = s[i]
        nxt = s[i + 1] if i + 1 < n else ""
        if c == "\n":
            if d != 0:
                print("    行 %-4d 深度=%-3d | %s" % (ln, d, s.splitlines()[ln - 1][:110]))
            ln += 1
            if state == "line_comment":
                state = "code"
            i += 1
            continue
        if state == "code":
            if c == "/" and nxt == "/":
                state = "line_comment"; i += 2; continue
            if c == "/" and nxt == "*":
                state = "block_comment"; i += 2; continue
            if c == '"':
                state = "string"; i += 1; continue
            if c == "'":
                state = "char"; i += 1; continue
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
        elif state == "block_comment":
            if c == "*" and nxt == "/":
                state = "code"; i += 2; continue
        elif state == "string":
            if c == "\\":
                i += 2; continue
            if c == '"':
                state = "code"
        elif state == "char":
            if c == "\\":
                i += 2; continue
            if c == "'":
                state = "code"
        i += 1
