import io, socket, ssl, os, re, json

PROXY = ("127.0.0.1", 10808)
OUT = []
def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def get(host, path, timeout=60):
    s = socket.create_connection(PROXY, timeout=timeout)
    s.sendall(b"\x05\x01\x00"); s.recv(2)
    hb = host.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + (443).to_bytes(2, "big"))
    r = s.recv(4)
    atyp = r[3]
    if atyp == 1: s.recv(6)
    elif atyp == 3: s.recv(s.recv(1)[0] + 2)
    elif atyp == 4: s.recv(18)
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
        if not d: break
        buf += d
    ss.close()
    head, _, body = buf.partition(b"\r\n\r\n")
    return head.split(b"\r\n")[0].decode("utf-8", "replace"), body


# ---- 列出仓库文件树（用 git tree API，走 raw 避免 JSON 问题）----
p("=" * 72)
p("1. 列出 theos 仓库中和 PREFIX / platform 相关的文件")
p("=" * 72)
st, body = get("api.github.com", "/repos/theos/theos/git/trees/master?recursive=1")
txt = body.decode("utf-8", "replace")
paths = re.findall(r'"path":"([^"]+)"', txt)
p("  文件总数: %d" % len(paths))
cands = [x for x in paths if x.startswith("makefiles/") and x.endswith(".mk")]
p("  makefiles 下 .mk: %d 个" % len(cands))
for x in sorted(cands):
    p("     " + x)

# ---- 抓 platform 相关文件，搜索 PREFIX ----
p("")
p("=" * 72)
p("2. 搜索 PREFIX 的定义（这决定 Theos 调用哪个 clang）")
p("=" * 72)
targets = [x for x in cands if ("platform" in x or "target" in x or x.endswith("common.mk"))]
for f in sorted(set(targets)):
    try:
        st, body = get("raw.githubusercontent.com", "/theos/theos/master/" + f)
        if "200" not in st:
            continue
        t = body.decode("utf-8", "replace")
        hits = []
        for i, l in enumerate(t.splitlines()):
            if re.search(r"\bPREFIX\b", l):
                hits.append((i + 1, l.strip()))
        if hits:
            p("")
            p("  === %s (%d 处) ===" % (f, len(hits)))
            for ln, l in hits[:40]:
                p("     %4d: %s" % (ln, l[:160]))
    except Exception as e:
        p("  FAIL %s: %s" % (f, e))

io.open("_prefix_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
