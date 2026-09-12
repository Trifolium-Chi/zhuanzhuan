import io, lzma, tarfile, os

OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))

DEST = "_tc_pkg.tar.xz"
p("包大小: %d 字节" % os.path.getsize(DEST))
p("")

names = []
sizes = {}
modes = {}
try:
    with lzma.open(DEST, "rb") as fh:
        with tarfile.open(fileobj=fh, mode="r|") as tf:
            for m in tf:
                names.append(m.name)
                sizes[m.name] = m.size
                modes[m.name] = m.mode
except Exception as e:
    p("读取中断: %s: %s" % (type(e).__name__, e))

p("总条目数: %d" % len(names))
p("")

p("=" * 72)
p("A. linux/iphone/bin 下的全部内容（这是 Theos 实际调用的目录）")
p("=" * 72)
bins = [n for n in names if n.startswith("linux/iphone/bin/")]
for n in sorted(bins):
    p("   %-56s %10d  mode=%o" % (n, sizes[n], modes[n]))
if not bins:
    p("   (没有 linux/iphone/bin/ 目录！)")

p("")
p("=" * 72)
p("B. 所有含 ld64 / ld.lld / 链接器 的条目")
p("=" * 72)
for n in sorted(names):
    b = os.path.basename(n).lower()
    if "ld64" in b or b in ("ld", "ld.lld", "lld", "ld-classic", "ld64.lld"):
        p("   %-56s %10d  mode=%o" % (n, sizes[n], modes[n]))

p("")
p("=" * 72)
p("C. 工具链顶层可见结构")
p("=" * 72)
tops = sorted(set("/".join(n.split("/")[:2]) for n in names))
for t in tops[:60]:
    p("   " + t)

p("")
p("=" * 72)
p("D. 关键判定：链接器到底是什么")
p("=" * 72)
for cand in ("linux/iphone/bin/ld", "linux/iphone/bin/ld64.lld",
             "linux/iphone/bin/ld.lld", "linux/iphone/bin/lld"):
    if cand in sizes:
        p("   存在: %-40s %10d 字节 mode=%o" % (cand, sizes[cand], modes[cand]))
    else:
        p("   缺失: %s" % cand)

io.open("_tc_full_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
