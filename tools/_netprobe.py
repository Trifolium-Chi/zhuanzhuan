import io, sys, socket, ssl, json

OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))

PROXY = ("127.0.0.1", 10808)

p("=== 1. PySocks 是否可用 ===")
try:
    import socks  # PySocks
    p("  PySocks 可用")
    have_socks = True
except ImportError as e:
    p("  PySocks 不可用:", e)
    have_socks = False

p("")
p("=== 2. 直连 443 端口测试（不走代理）===")
for host in ("api.github.com", "github.com", "download.swift.org"):
    try:
        s = socket.create_connection((host, 443), timeout=10)
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(s, server_hostname=host)
        p("  [OK] %s  证书=%s" % (host, ss.version()))
        ss.close()
    except Exception as e:
        p("  [FAIL] %s -> %s: %s" % (host, type(e).__name__, e))

p("")
p("=== 3. 经 SOCKS5 代理测试 ===")
if have_socks:
    for host in ("api.github.com", "github.com"):
        try:
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, PROXY[0], PROXY[1])
            s.settimeout(20)
            s.connect((host, 443))
            ctx = ssl.create_default_context()
            ss = ctx.wrap_socket(s, server_hostname=host)
            p("  [OK] %s 经代理连通, TLS=%s" % (host, ss.version()))
            ss.close()
        except Exception as e:
            p("  [FAIL] %s 经代理 -> %s: %s" % (host, type(e).__name__, e))
else:
    p("  (无 PySocks，跳过)")

p("")
p("=== 4. 手写 SOCKS5 握手测试（不依赖任何库）===")
def socks5_get(host, port=443, path="/"):
    try:
        s = socket.create_connection(PROXY, timeout=15)
        s.sendall(b"\x05\x01\x00")
        resp = s.recv(2)
        if resp != b"\x05\x00":
            return "代理拒绝握手: %r" % resp
        hb = host.encode()
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + port.to_bytes(2, "big"))
        r = s.recv(4)
        if len(r) < 2 or r[1] != 0:
            return "连接失败, 回复=%r" % r
        # 读取 BND.ADDR/PORT
        atyp = r[3]
        if atyp == 1:
            s.recv(4 + 2)
        elif atyp == 3:
            n = s.recv(1)[0]
            s.recv(n + 2)
        elif atyp == 4:
            s.recv(16 + 2)
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(s, server_hostname=host)
        req = ("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: probe\r\nConnection: close\r\n\r\n"
               % (path, host)).encode()
        ss.sendall(req)
        buf = b""
        while len(buf) < 400:
            d = ss.recv(4096)
            if not d:
                break
            buf += d
        ss.close()
        return "OK 首行: " + buf.split(b"\r\n")[0].decode("utf-8", "replace")
    except Exception as e:
        return "异常 %s: %s" % (type(e).__name__, e)

p("  api.github.com :", socks5_get("api.github.com", 443, "/rate_limit"))
p("  raw.githubusercontent.com :", socks5_get("raw.githubusercontent.com", 443, "/theos/theos/master/bin/install-sdk"))

io.open("_netprobe.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
