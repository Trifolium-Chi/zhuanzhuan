import io, socket, ssl, os, re

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


st, body = get("raw.githubusercontent.com", "/theos/theos/master/makefiles/instance/tweak.mk")
t = body.decode("utf-8", "replace")
io.open("_theos_tweak.mk", "w", encoding="utf-8", newline="\n").write(t)
p("makefiles/instance/tweak.mk  %s  %d 字节" % (st, len(body)))
p("")
p("=" * 72)
p("全文")
p("=" * 72)
for i, l in enumerate(t.splitlines()):
    p("%4d: %s" % (i + 1, l))

# 也看 library.mk / stage.mk 里的 install 逻辑
for f in ("makefiles/instance/library.mk", "makefiles/stage.mk"):
    st2, b2 = get("raw.githubusercontent.com", "/theos/theos/master/" + f)
    t2 = b2.decode("utf-8", "replace")
    io.open("_theos_" + f.replace("/", "__"), "w", encoding="utf-8", newline="\n").write(t2)
    p("")
    p("=" * 72)
    p("%s  (%s, %d 字节)" % (f, st2, len(b2)))
    p("=" * 72)
    for i, l in enumerate(t2.splitlines()):
        if re.search(r"plist|filter|Filter|install|stage", l, re.I):
            p("%4d: %s" % (i + 1, l))

io.open("_tweakmk_report.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
print("done")
