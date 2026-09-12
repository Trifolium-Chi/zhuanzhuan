import io, lzma, tarfile, struct, os

DEB = "转转找鸡-0.0.1-8+debug-iphoneos-arm64e.deb"
OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def load_dylib(deb):
    d = open(deb, "rb").read()
    pos = 8
    while pos + 60 <= len(d):
        hdr = d[pos:pos + 60]
        nm = hdr[0:16].decode("ascii", "replace").strip()
        sz = int(hdr[48:58].decode("ascii").strip())
        if nm.startswith("data.tar"):
            raw = lzma.decompress(d[pos + 60:pos + 60 + sz])
            with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
                for m in tf.getmembers():
                    if m.isfile() and m.name.endswith(".dylib"):
                        return tf.extractfile(m).read()
        pos += 60 + sz + (sz % 2)
    return None


b = load_dylib(DEB)
p("找鸡 dylib: %d 字节" % len(b))

# 解析加载命令，找 LC_MAIN / 各段
ncmds, sizeofcmds = struct.unpack_from("<II", b, 16)
segs = {}
secs = []
off = 32
for _ in range(ncmds):
    cmd, cmdsize = struct.unpack_from("<II", b, off)
    if cmd == 0x19:
        sn = b[off + 8:off + 24].rstrip(b"\x00").decode()
        vm, vs, fo, fs = struct.unpack_from("<QQQQ", b, off + 24)
        segs[sn] = (vm, vs, fo, fs)
        nsects, = struct.unpack_from("<I", b, off + 64)
        so = off + 72
        for _i in range(nsects):
            xn = b[so:so + 16].rstrip(b"\x00").decode()
            addr, size = struct.unpack_from("<QQ", b, so + 32)
            s_off, = struct.unpack_from("<I", b, so + 48)
            secs.append((sn, xn, addr, size, s_off))
            so += 80
    off += cmdsize

def va2off(va):
    for sn, (vm, vs, fo, fs) in segs.items():
        if vm <= va < vm + vs:
            return fo + (va - vm)
    return None

# 符号表：找 __logosLocalCtor__ / 构造函数
symoff, nsyms = struct.unpack_from("<II", b, 56)  # 需要从 LC_SYMTAB 取，改用手动
off = 32
symtab = None
for _ in range(ncmds):
    cmd, cmdsize = struct.unpack_from("<II", b, off)
    if cmd == 0x02:
        symtab = struct.unpack_from("<IIII", b, off + 8)
    off += cmdsize
symoff, nsyms, stroff, strsize = symtab
p("LC_SYMTAB symoff=%d nsyms=%d stroff=%d strsize=%d" % (symoff, nsyms, stroff, strsize))

def str_at(o):
    try:
        e = b.index(b"\x00", o)
    except ValueError:
        return ""
    return b[o:e].decode("utf-8", "replace")

p("")
p("=" * 72)
p("构造函数 / 初始化相关符号（这些是注入入口，改它们能让 dylib 不生效）")
p("=" * 72)
ctors = []
for i in range(nsyms):
    o = symoff + i * 16
    strx, ntype, sect, desc, value = struct.unpack_from("<IBBHQ", b, o)
    if strx == 0:
        continue
    nm = str_at(stroff + strx)
    if any(k in nm.lower() for k in ("ctor", "init", "construct", "logos", "zzfloat", "shared")):
        fo = va2off(value)
        p("   vm=0x%-8x fileoff=%-8s sect=%-3d type=0x%02x  %s"
          % (value, fo, sect, ntype, nm))
        ctors.append((nm, value, fo))

p("")
p("=" * 72)
p("__init_offsets 段（dyld 用来调用构造函数）")
p("=" * 72)
for sn, xn, addr, size, s_off in secs:
    if xn == "__init_offsets":
        p("   addr=0x%x size=%d fileoff=%d" % (addr, size, s_off))
        raw = b[s_off:s_off + size]
        p("   原始字节: %s" % raw.hex())
        # iOS 15+ 是 32 位相对偏移
        for i in range(0, min(size, 32), 4):
            v, = struct.unpack_from("<I", b, s_off + i)
            p("     [+%d] raw=0x%08x" % (i, v))
        # 也按 8 字节看
        for i in range(0, min(size, 32), 8):
            v, = struct.unpack_from("<Q", b, s_off + i)
            p("     (8B)[+%d] 0x%016x -> fileoff=%s" % (i, v, va2off(v) if va2off(v) else "?"))

io.open("_ctor_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
