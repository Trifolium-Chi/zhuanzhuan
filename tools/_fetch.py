import io, json, socket, ssl, sys

PROXY = ("127.0.0.1", 10808)
OUT = []


def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def https_get(host, path, timeout=30, maxbytes=400000):
    """经 SOCKS5 取 HTTPS 内容；返回 (status, body_bytes)"""
    s = socket.create_connection(PROXY, timeout=timeout)
    s.sendall(b"\x05\x01\x00")
    if s.recv(2) != b"\x05\x00":
        raise RuntimeError("SOCKS5 握手被拒")
    hb = host.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + (443).to_bytes(2, "big"))
    r = s.recv(4)
    if len(r) < 2 or r[1] != 0:
        raise RuntimeError("SOCKS5 连接失败: %r" % r)
    atyp = r[3]
    if atyp == 1:
        s.recv(6)
    elif atyp == 3:
        n = s.recv(1)[0]
        s.recv(n + 2)
    elif atyp == 4:
        s.recv(18)
    ctx = ssl.create_default_context()
    ss = ctx.wrap_socket(s, server_hostname=host)
    req = ("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: dsh-probe\r\n"
           "Accept: */*\r\nConnection: close\r\n\r\n" % (path, host)).encode()
    ss.sendall(req)
    buf = b""
    while True:
        d = ss.recv(65536)
        if not d:
            break
        buf += d
        if len(buf) > maxbytes:
            break
    ss.close()
    head, _, body = buf.partition(b"\r\n\r\n")
    status = head.split(b"\r\n")[0].decode("utf-8", "replace")
    return status, body


def save(name, data):
    io.open(name, "wb").write(data)
    return len(data)


# ---------------------------------------------------------------- 1. Theos 脚本
p("=" * 70)
p("1. 抓取 Theos 真实安装脚本")
p("=" * 70)
for f in ("install-sdk", "install-theos", "swift-bootstrapper.pl"):
    try:
        st, body = https_get("raw.githubusercontent.com", "/theos/theos/master/bin/" + f)
        n = save("_theos_" + f, body)
        p("  %-22s %s  %d 字节" % (f, st, n))
    except Exception as e:
        p("  %-22s 失败: %s: %s" % (f, type(e).__name__, e))

# ---------------------------------------------------------------- 2. install-sdk 内的 URL
p("")
p("=" * 70)
p("2. install-sdk 里出现的 URL（SDK 的真实来源）")
p("=" * 70)
try:
    txt = io.open("_theos_install-sdk", encoding="utf-8", errors="replace").read()
    import re
    for m in sorted(set(re.findall(r"https?://[^\s\"'`\\)>]+", txt))):
        p("  " + m)
except Exception as e:
    p("  读取失败:", e)

# ---------------------------------------------------------------- 3. SDK releases API
p("")
p("=" * 70)
p("3. theos/sdks releases API（SDK 下载地址）")
p("=" * 70)
try:
    st, body = https_get("api.github.com", "/repos/theos/sdks/releases/latest")
    p("  " + st)
    j = json.loads(body.decode("utf-8"))
    p("  tag_name: %s" % j.get("tag_name"))
    p("  assets:")
    for a in j.get("assets", [])[:20]:
        p("    %-40s %10d  %s" % (a["name"], a["size"], a["browser_download_url"]))
except Exception as e:
    p("  失败: %s: %s" % (type(e).__name__, e))

# ---------------------------------------------------------------- 4. kabiroberai releases
p("")
p("=" * 70)
p("4. kabiroberai/swift-toolchain-linux 可用文件")
p("=" * 70)
try:
    st, body = https_get("api.github.com", "/repos/kabiroberai/swift-toolchain-linux/releases")
    p("  " + st)
    rels = json.loads(body.decode("utf-8"))
    for r in rels[:3]:
        p("  release %s" % r.get("tag_name"))
        for a in r.get("assets", []):
            p("    %-52s %10d" % (a["name"], a["size"]))
except Exception as e:
    p("  失败: %s: %s" % (type(e).__name__, e))

# ---------------------------------------------------------------- 5. L1ghtmann releases
p("")
p("=" * 70)
p("5. L1ghtmann/llvm-project releases（iOSToolchain）")
p("=" * 70)
try:
    st, body = https_get("api.github.com", "/repos/L1ghtmann/llvm-project/releases/latest")
    p("  " + st)
    j = json.loads(body.decode("utf-8"))
    p("  tag_name: %s" % j.get("tag_name"))
    for a in j.get("assets", [])[:20]:
        p("    %-52s %10d" % (a["name"], a["size"]))
except Exception as e:
    p("  失败: %s: %s" % (type(e).__name__, e))

# ---------------------------------------------------------------- 6. LLVM 候选验证
p("")
p("=" * 70)
p("6. LLVM 官方包候选验证（用 HEAD 逐个试）")
p("=" * 70)
cands = []
for ver in ("18.1.8", "17.0.6", "16.0.6", "15.0.7"):
    for os_ in ("ubuntu-18.04", "ubuntu-20.04", "ubuntu-22.04", "ubuntu-24.04"):
        cands.append((ver, os_))
for ver, os_ in cands:
    path = ("/llvm/llvm-project/releases/download/llvmorg-%s/"
            "clang+llvm-%s-x86_64-linux-gnu-%s.tar.xz" % (ver, ver, os_))
    try:
        st, _ = https_get("github.com", path, timeout=25, maxbytes=200)
        code = st.split()[1] if len(st.split()) > 1 else "?"
        if code in ("200", "302"):
            p("  [可用 %s] %s / %s" % (code, ver, os_))
        else:
            p("  [%s] %s / %s" % (code, ver, os_))
    except Exception as e:
        p("  [异常] %s / %s -> %s" % (ver, os_, e))

io.open("_fetch_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
