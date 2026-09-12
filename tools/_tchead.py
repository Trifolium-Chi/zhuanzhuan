import io, socket, ssl, os, lzma, tarfile, sys

PROXY = ("127.0.0.1", 10808)
OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def https_range(host, path, dest, nbytes=6 * 1024 * 1024, timeout=600, depth=0):
    """经 SOCKS5 取前 nbytes 字节（Range 请求），跟随重定向"""
    if depth > 5:
        raise RuntimeError("重定向过多")
    s = socket.create_connection(PROXY, timeout=30)
    s.sendall(b"\x05\x01\x00")
    if s.recv(2) != b"\x05\x00":
        raise RuntimeError("SOCKS5 握手失败")
    hb = host.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + (443).to_bytes(2, "big"))
    r = s.recv(4)
    if len(r) < 2 or r[1] != 0:
        raise RuntimeError("SOCKS5 连接失败")
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
    req = ("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: probe\r\n"
           "Range: bytes=0-%d\r\nConnection: close\r\n\r\n" % (path, host, nbytes - 1)).encode()
    ss.sendall(req)
    buf = b""
    while b"\r\n\r\n" not in buf:
        d = ss.recv(8192)
        if not d:
            break
        buf += d
    head, _, rest = buf.partition(b"\r\n\r\n")
    htxt = head.decode("utf-8", "replace")
    status = htxt.split("\r\n")[0]
    code = status.split()[1] if len(status.split()) > 1 else "?"
    if code in ("301", "302", "303", "307", "308"):
        loc = None
        for line in htxt.split("\r\n"):
            if line.lower().startswith("location:"):
                loc = line.split(":", 1)[1].strip()
        ss.close()
        rest_url = loc[len("https://"):]
        nh, _, np_ = rest_url.partition("/")
        return https_range(nh, "/" + np_, dest, nbytes, timeout, depth + 1)

    total = len(rest)
    with io.open(dest, "wb") as f:
        f.write(rest)
        while total < nbytes:
            try:
                d = ss.recv(262144)
            except Exception:
                break
            if not d:
                break
            f.write(d)
            total += len(d)
    ss.close()
    return status, total


dest = "_tc_head.tar.xz"
p("=" * 72)
p("只取工具链包的前 6MB，用于读取 tar 条目名（不必下载完整 86MB）")
p("=" * 72)
try:
    st, n = https_range("github.com",
                        "/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz",
                        dest, 6 * 1024 * 1024)
    p("HTTP: %s   取到 %d 字节 (%.1f MB)" % (st, n, n / 1048576.0))
except Exception as e:
    p("失败: %s: %s" % (type(e).__name__, e))

names = []
if os.path.exists(dest) and os.path.getsize(dest) > 100000:
    p("")
    p("--- 流式读取 tar 条目（到压缩边界为止）---")
    try:
        with lzma.open(dest, "rb") as fh:
            with tarfile.open(fileobj=fh, mode="r|") as tf:
                for m in tf:
                    names.append(m.name)
                    if len(names) >= 6000:
                        break
    except Exception as e:
        p("  读取在 %d 项后停止（正常，因为只取了前面一段）: %s"
          % (len(names), type(e).__name__))

p("  拿到条目数: %d" % len(names))
if names:
    p("")
    p("  [关键] 含 linux/iphone/bin/clang 的条目:")
    hits = [n for n in names if "linux/iphone/bin/clang" in n or n.endswith("iphone/bin/clang")]
    for h in hits[:10]:
        p("     " + h)
    if not hits:
        p("     (本段内未出现 —— 可能条目顺序靠后)")

    p("")
    p("  --- 含 'ld64' 的条目 ---")
    ld = [x for x in names if "ld64" in x]
    for x in ld[:20]:
        p("     " + x)
    if not ld:
        p("     (本段内没有)")

    p("")
    p("  --- 含 '/bin/' 的条目（最多 50）---")
    bx = [x for x in names if "/bin/" in x]
    for x in bx[:50]:
        p("     " + x)

    p("")
    p("  --- 顶层结构 ---")
    tops = sorted(set("/".join(x.split("/")[:3]) for x in names))
    for t in tops[:40]:
        p("     " + t)

io.open("_tc_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
