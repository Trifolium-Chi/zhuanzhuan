import io, socket, ssl, os

PROXY = ("127.0.0.1", 10808)
OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def http_get(host, path, headers=None, timeout=1800, writer=None, maxbytes=None):
    """返回 (status_code, headers_dict, body_bytes_or_None)"""
    s = socket.create_connection(PROXY, timeout=30)
    s.sendall(b"\x05\x01\x00")
    s.recv(2)
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
    hdr = "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: probe\r\nAccept: */*\r\n" % (path, host)
    for k, v in (headers or {}).items():
        hdr += "%s: %s\r\n" % (k, v)
    hdr += "Connection: close\r\n\r\n"
    ss.sendall(hdr.encode())

    buf = b""
    while b"\r\n\r\n" not in buf:
        d = ss.recv(8192)
        if not d:
            break
        buf += d
    head, _, rest = buf.partition(b"\r\n\r\n")
    htxt = head.decode("utf-8", "replace")
    lines = htxt.split("\r\n")
    code = lines[0].split()[1]
    hdrs = {}
    for l in lines[1:]:
        if ":" in l:
            k, v = l.split(":", 1)
            hdrs[k.strip().lower()] = v.strip()

    if writer is not None and code in ("200", "206"):
        n = len(rest)
        writer(rest)
        while True:
            if maxbytes and n >= maxbytes:
                break
            try:
                d = ss.recv(524288)
            except Exception:
                break
            if not d:
                break
            writer(d)
            n += len(d)
        ss.close()
        return code, hdrs, n
    ss.close()
    return code, hdrs, rest


def resolve(host, path, depth=0):
    if depth > 6:
        raise RuntimeError("重定向过多")
    code, hdrs, _ = http_get(host, path, maxbytes=0)
    if code in ("301", "302", "303", "307", "308"):
        loc = hdrs.get("location", "")
        ru = loc[len("https://"):]
        nh, _, np_ = ru.partition("/")
        return resolve(nh, "/" + np_, depth + 1)
    return host, path


DEST = "_tc_pkg.tar.xz"
EXPECT = 86163280
SIGNED = resolve("github.com",
                 "/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz")
p("最终下载地址主机: %s" % SIGNED[0])
p("路径前缀: %s" % SIGNED[1][:120])
p("")

for attempt in range(1, 13):
    cur = os.path.getsize(DEST) if os.path.exists(DEST) else 0
    if cur >= EXPECT:
        break
    p("--- 第 %d 次，已有 %d / %d (%.1f%%)"
      % (attempt, cur, EXPECT, cur * 100.0 / EXPECT))
    try:
        f = io.open(DEST, "ab" if cur else "wb")
        code, hdrs, n = http_get(
            SIGNED[0], SIGNED[1],
            headers={"Range": "bytes=%d-" % cur} if cur else None,
            writer=f.write)
        f.close()
        p("    HTTP %s, 写入 %s 字节, 现共 %d" % (code, n, os.path.getsize(DEST)))
        if code == "200" and cur > 0:
            p("    (服务器不支持续传，已从头覆盖)")
    except Exception as e:
        p("    异常: %s: %s" % (type(e).__name__, e))

if os.path.exists(DEST):
    sz = os.path.getsize(DEST)
    p("")
    p("最终: %d / %d 字节  完整=%s" % (sz, EXPECT, sz == EXPECT))

io.open("_dl_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
