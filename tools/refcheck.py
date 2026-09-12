import io, os, re

f = "zzmerge/tweak/ZZMergeBridge.x"
s = io.open(f, encoding="utf-8").read()

# 收集所有 static 函数名
decls = re.findall(r"static\s+[A-Za-z_][A-Za-z0-9_ *]*?\b(ZZ[A-Za-z0-9_]+)\s*\(", s)
names = sorted(set(decls))
print("=== static 函数清单 (%d) ===" % len(names))
unused = []
for n in names:
    uses = len(re.findall(r"\b" + re.escape(n) + r"\b", s))
    mark = "OK " if uses > 1 else "未使用!"
    if uses <= 1:
        unused.append(n)
    print("  %s %-32s 出现 %d 次" % (mark, n, uses))

print("\n=== 被引用但未在本文件定义的 ZZ 前缀标识符 ===")
defined = set(names) | set(re.findall(r"@interface\s+(ZZ[A-Za-z0-9_]+)", s)) \
    | set(re.findall(r"@implementation\s+(ZZ[A-Za-z0-9_]+)", s)) \
    | set(re.findall(r"static\s+NSString\s*\*\s*const\s+(ZZ[A-Za-z0-9_]+)", s))
used = set(re.findall(r"\b(ZZ[A-Za-z0-9_]+)\b", s))
missing = sorted(used - defined)
for m in missing:
    print("  ", m)
if not missing:
    print("   (无)")

print("\n=== 检查 %orig 是否都在 hook 块内 ===")
start = s.find("%hook")
end = s.find("%end")
bad = []
for m in re.finditer(r"%orig", s):
    if not (start < m.start() < end):
        bad.append(s[:m.start()].count("\n") + 1)
print("  %orig 出现在 hook 块外:", bad if bad else "无")

print("\n=== 检查 objc_msgSend 调用处 ===")
for m in re.finditer(r"objc_msgSend", s):
    ln = s[:m.start()].count("\n") + 1
    line = s.splitlines()[ln - 1].strip()
    print("  行 %-4d %s" % (ln, line[:100]))

if unused:
    print("\n注意：以下 static 函数未被使用 ->", unused)
