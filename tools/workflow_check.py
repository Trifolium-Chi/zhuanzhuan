import io, os, sys, re

p = "zzmerge/.github/workflows/build.yml"
s = io.open(p, encoding="utf-8").read()
lines = s.splitlines()

print("=" * 70)
print("工作流结构检查")
print("=" * 70)
print("总行数:", len(lines))

# 1. 顶层键
top = [(i + 1, l) for i, l in enumerate(lines)
       if l and not l.startswith(" ") and not l.startswith("#")]
print("\n--- 顶层键 ---")
for ln, l in top:
    print("  %4d  %s" % (ln, l))

# 2. steps 缩进与 name 列表
print("\n--- steps ---")
in_steps = False
for i, l in enumerate(lines):
    if re.match(r"^\s+steps:\s*$", l):
        in_steps = True
        continue
    if in_steps:
        m = re.match(r"^(\s+)- name:\s*(.*)$", l)
        if m:
            print("  %4d  [%d空格] %s" % (i + 1, len(m.group(1)), m.group(2)))
        elif l.strip() and not l.strip().startswith("#") and \
             len(l) - len(l.lstrip()) <= 6 and not l.strip().startswith("-"):
            break

# 3. run 块里的 shell 语法粗检
print("\n--- run 块 shell 关键字 ---")
for kw in ("set -e", "set -uo pipefail", "exit 1", "sdk_ok", "get-toolchain.sh",
           "theos/sdks", "curl ", "tar -xzf"):
    n = s.count(kw)
    print("  %-22s 出现 %d 次" % (kw, n))

# 4. if/fi 配对（每个 run 块内）
print("\n--- if/fi 与 do/done 配对 ---")
body = s
print("  if  =", len(re.findall(r"\bif\b", body)),
      " fi =", len(re.findall(r"\bfi\b", body)))
print("  for =", len(re.findall(r"\bfor\b", body)),
      " do =", len(re.findall(r"\bdo\b", body)),
      " done =", len(re.findall(r"\bdone\b", body)))

# 5. 缩进一致性：run 块内容至少要比 "run:" 多 2 空格
print("\n--- run: 行及其首行内容缩进 ---")
for i, l in enumerate(lines):
    if re.match(r"^\s*(run:|uses:)\s*", l):
        ind = len(l) - len(l.lstrip())
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        nind = len(nxt) - len(nxt.lstrip()) if nxt.strip() else -1
        flag = "OK" if (l.strip().startswith("uses:") or nind > ind) else "!! 缩进可疑"
        print("  %4d  %-6s ind=%-3d next_ind=%-3d %s | %s"
              % (i + 1, l.strip().split(":")[0], ind, nind, flag, l.strip()[:60]))

# 6. 明确不能出现的东西
print("\n--- 禁止项 ---")
print("  THEOS_PACKAGE_SCHEME 赋值:",
      re.findall(r"(?m)^\s*THEOS_PACKAGE_SCHEME\s*:", s) or "无 (OK)")
print("  scheme 输入项:",
      [l.strip() for l in lines if "scheme:" in l] or "无 (OK)")
print("  || true 后接关键命令:",
      [l.strip() for l in lines if "|| true" in l] or "无")
