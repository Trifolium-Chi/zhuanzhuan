import io, socket, ssl, os, re

PROXY = ("127.0.0.1", 10808)
OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def get(host, path, timeout=60):
    s = socket.create_connection(PROXY, timeout=timeout)
    s.sendall(b"\x05\x01\x00")
    if s.recv(2) != b"\x05\x00":
        raise RuntimeError("SOCKS5 握手失败")
    hb = host.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + (443).to_bytes(2, "big"))
    r = s.recv(4)
    atyp = r[3]
    if atyp == 1:
        s.recv(6)
    elif atyp == 3:
        s.recv(s.recv(1)[0] + 2)
    elif atyp == 4:
        s.recv(18)
    ctx = ssl.create_default_context()
    ss = ctx.wrap_socket(s, server_hostname=host)
    ss.settimeout(timeout)
    ss.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: probe\r\nConnection: close\r\n\r\n"
                % (path, host)).encode())
    buf = b""
    while True:
        try:
            d = ss.recv(65536)
        except Exception:
            break
        if not d:
            break
        buf += d
    ss.close()
    head, _, body = buf.partition(b"\r\n\r\n")
    return head.split(b"\r\n")[0].decode("utf-8", "replace"), body


FILES = [
    "makefiles/common.mk",
    "makefiles/targets/_common/darwin_head.mk",
    "makefiles/targets/Darwin-arm64.mk",
    "makefiles/targets/Darwin-arm64e.mk",
    "makefiles/instance/rules.mk",
    "makefiles/instance/library.mk",
]

# 先列出 makefiles 目录结构，找到与链接相关的文件
p("=" * 72)
p("1. 列出 theos/makefiles 目录（找链接相关文件）")
p("=" * 72)
try:
    st, body = get("api.github.com", "/repos/theos/theos/git/trees/master?recursive=1")
    p("  " + st)
    import json
    j = json.loads(body.decode("utf-8"))
    paths = [t["path"] for t in j.get("tree", [])]
    mk = [x for x in paths if x.startswith("makefiles/") and x.endswith(".mk")]
    p("  makefiles 下共 %d 个 .mk，其中与 target/toolchain 相关的：" % len(mk))
    for x in sorted(mk):
        if any(k in x for k in ("target", "toolchain", "common", "link", "library", "rules")):
            p("     " + x)
    io.open("_theos_mklist.txt", "w", encoding="utf-8").write("\n".join(sorted(mk)))
except Exception as e:
    p("  失败: %s: %s" % (type(e).__name__, e))
    mk = []

# 抓关键文件
p("")
p("=" * 72)
p("2. 抓取关键 makefile")
p("=" * 72)
got = {}
for f in FILES + [x for x in mk if "target" in x][:12]:
    try:
        st, body = get("raw.githubusercontent.com", "/theos/theos/master/" + f)
        if "200" in st:
            name = "_theos_" + f.replace("/", "__")
            io.open(name, "wb").write(body)
            got[f] = body.decode("utf-8", "replace")
            p("  OK   %-52s %d 字节" % (f, len(body)))
    except Exception as e:
        p("  FAIL %-52s %s" % (f, e))

# 在所有抓到的文件里搜索链接器相关内容
p("")
p("=" * 72)
p("3. 搜索链接器调用相关设置（-fuse-ld / LD / ld64 / TARGET_LD 等）")
p("=" * 72)
pat = re.compile(r".*(fuse-ld|ld64|TARGET_LD|_LD\b|\bLD\b|linker|eh-frame|Wl,).*", re.I)
for f, txt in got.items():
    hits = [(i + 1, l.strip()) for i, l in enumerate(txt.splitlines()) if pat.match(l)]
    if hits:
        p("")
        p("  --- %s (%d 处) ---" % (f, len(hits)))
        for ln, l in hits[:60]:
            p("     %4d: %s" % (ln, l[:150]))

io.open("_theos_linkreport.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
