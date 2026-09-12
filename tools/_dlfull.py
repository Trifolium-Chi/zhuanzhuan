import io, socket, ssl, os, sys

PROXY = ("127.0.0.1", 10808)
OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def get_to_file(host, path, dest, timeout=1800, depth=0):
    """经 SOCKS5 下载（跟随重定向），断点续传式重试"""
    if depth > 5:
        raise RuntimeError("重定向过多")
    s = socket.create_connection(PROXY, timeout=30)
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
    ss.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: probe\r\n"
                "Accept: */*\r\nConnection: close\r\n\r\n" % (path, host)).encode())
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
        loc = [l.split(":", 1)[1].strip() for l in htxt.split("\r\n")
               if l.lower().startswith("location:")][0]
        ss.close()
        ru = loc[len("https://"):]
        nh, _, np_ = ru.partition("/")
        return get_to_file(nh, "/" + np_, dest, timeout, depth + 1)

    total = 0
    with io.open(dest, "wb") as f:
        f.write(rest)
        total += len(rest)
        while True:
            try:
                d = ss.recv(524288)
            except Exception:
                break
            if not d:
                break
            f.write(d)
            total += len(d)
    ss.close()
    return status, total


DEST = "_tc_pkg.tar.xz"
URL_HOST = "github.com"
URL_PATH = "/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz"

p("=" * 72)
p("下载完整工具链包（分片重试，直到拿全）")
p("=" * 72)

# 期望大小 86163280
EXPECT = 86163280
if os.path.exists(DEST) and os.path.getsize(DEST) == EXPECT:
    p("已有完整缓存: %d 字节" % os.path.getsize(DEST))
else:
    for attempt in range(1, 9):
        cur = os.path.getsize(DEST) if os.path.exists(DEST) else 0
        p("--- 第 %d 次尝试，当前 %d / %d 字节 (%.1f%%)"
          % (attempt, cur, EXPECT, cur * 100.0 / EXPECT))
        if cur >= EXPECT:
            break
        # 从 cur 处续传
        try:
            s = socket.create_connection(PROXY, timeout=30)
            s.sendall(b"\x05\x01\x00")
            s.recv(2)
            hb = URL_HOST.encode()
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
            ss = ctx.wrap_socket(s, server_hostname=URL_HOST)
            ss.settimeout(1800)
            ss.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: probe\r\n"
                        "Range: bytes=%d-\r\nConnection: close\r\n\r\n"
                        % (URL_PATH, URL_HOST, cur)).encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = ss.recv(8192)
                if not d:
                    break
                buf += d
            head, _, rest = buf.partition(b"\r\n\r\n")
            htxt = head.decode("utf-8", "replace")
            code = htxt.split("\r\n")[0].split()[1]
            p("    HTTP %s" % code)
            if code not in ("206", "200"):
                p("    无法续传，改为重新下载")
                ss.close()
                if os.path.exists(DEST):
                    os.remove(DEST)
                continue
            got = len(rest)
            with io.open(DEST, "ab" if code == "206" else "wb") as f:
                f.write(rest)
                while True:
                    try:
                        d = ss.recv(524288)
                    except Exception:
                        break
                    if not d:
                        break
                    f.write(d)
                    got += len(d)
            ss.close()
            p("    本次收到 %d 字节，累计 %d" % (got, os.path.getsize(DEST)))
            if os.path.getsize(DEST) >= EXPECT:
                break
        except Exception as e:
            p("    异常: %s: %s" % (type(e).__name__, e))

if os.path.exists(DEST):
    p("")
    p("最终大小: %d / %d 字节" % (os.path.getsize(DEST), EXPECT))
    p("完整: %s" % (os.path.getsize(DEST) == EXPECT))

io.open("_dl_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
