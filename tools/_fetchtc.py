import io, socket, ssl, sys, subprocess, os

PROXY = ("127.0.0.1", 10808)
OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def https_download(host, path, dest, timeout=900, depth=0):
    """经 SOCKS5 流式下载，自动跟随 302 重定向（GitHub releases 会跳到 objects.githubusercontent.com）"""
    if depth > 5:
        raise RuntimeError("重定向次数过多")
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
           "Accept: */*\r\nConnection: close\r\n\r\n" % (path, host)).encode()
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
                break
        ss.close()
        if not loc:
            raise RuntimeError("重定向但没有 Location")
        # 解析 Location
        if loc.startswith("https://"):
            rest_url = loc[len("https://"):]
            nh, _, np_ = rest_url.partition("/")
            return https_download(nh, "/" + np_, dest, timeout, depth + 1)
        raise RuntimeError("不支持的 Location: " + loc[:120])

    total = 0
    with io.open(dest, "wb") as f:
        f.write(rest)
        total += len(rest)
        while True:
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


# ---- 解析 tar.xz 的文件清单（不落盘解压，直接读）----
def list_xz_tar(path, limit=4000):
    names = []
    try:
        import lzma, tarfile
        with lzma.open(path, "rb") as fh:
            with tarfile.open(fileobj=fh, mode="r|") as tf:
                for m in tf:
                    names.append(m.name)
                    if len(names) >= limit:
                        break
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return names, None


p("=" * 72)
p("下载并核实 L1ghtmann/llvm-project iOSToolchain-x86_64.tar.xz")
p("（这是 install-theos 在 CI 环境下第 461 行实际安装的那个包）")
p("=" * 72)

url_host = "github.com"
url_path = "/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz"
dest = "_iOSToolchain-x86_64.tar.xz"

if os.path.exists(dest):
    p("已存在本地缓存:", os.path.getsize(dest), "字节")
else:
    try:
        st, n = https_download(url_host, url_path, dest)
        p("HTTP: %s   下载 %d 字节 (%.1f MB)" % (st, n, n / 1048576.0))
    except Exception as e:
        p("下载失败: %s: %s" % (type(e).__name__, e))

if os.path.exists(dest) and os.path.getsize(dest) > 1000000:
    p("")
    p("--- 包内文件清单（前 4000 项，只列关键项）---")
    names, err = list_xz_tar(dest)
    if err:
        p("  读取失败:", err)
    else:
        p("  总条目数（上限内）:", len(names))
        # 关键：确认目标路径存在
        hits = [n for n in names if "toolchain/linux/iphone/bin/clang" in n
                or n.endswith("linux/iphone/bin/clang")]
        p("")
        p("  [关键] 含 linux/iphone/bin/clang 的条目: %d" % len(hits))
        for h in hits[:10]:
            p("     " + h)
        p("")
        p("  --- 所有包含 'ld64' 的条目 ---")
        ld = [n for n in names if "ld64" in n]
        for x in ld[:20]:
            p("     " + x)
        if not ld:
            p("     (没有 ld64 相关文件！)")
        p("")
        p("  --- linux/iphone/bin 下的内容 ---")
        binx = [n for n in names if "/linux/iphone/bin/" in n or n.endswith("/iphone/bin")]
        for x in binx[:60]:
            p("     " + x)
        p("")
        p("  --- 顶层目录结构（前 40 项）---")
        tops = sorted(set("/".join(n.split("/")[:3]) for n in names))
        for t in tops[:40]:
            p("     " + t)
else:
    p("  包不可用，跳过清单分析")

io.open("_tc_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
