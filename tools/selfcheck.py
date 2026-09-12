#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZZMerge 工程本地自检（不需要 iOS 工具链）

检查项：
  1. 桥接源码 ZZMergeBridge.x 的括号/指令结构
  2. 桥接 plist 是否合法且注入目标正确
  3. vendor_src/ 下两个原始 deb 是否齐全，以及各自是否含 dylib + plist
  4. Makefile 关键变量/钩子是否齐全
  5. control 的包名与两个原包的冲突/替代关系是否写对

用法：  python3 tools/selfcheck.py
"""
import io
import os
import re
import struct
import sys
import lzma
import tarfile
import io as _io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK, WARN, FAIL = "[OK]  ", "[警告]", "[失败]"
problems = []

# 输出统一走 UTF-8，避免 Windows 控制台中文乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def say(tag, msg):
    print("%s %s" % (tag, msg))
    if tag == FAIL:
        problems.append(msg)


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 1. 源码结构
def check_source():
    print("\n=== 1. 桥接源码结构 ===")
    p = os.path.join(ROOT, "tweak", "ZZMergeBridge.x")
    if not os.path.exists(p):
        say(FAIL, "找不到 tweak/ZZMergeBridge.x")
        return
    s = read(p)

    # 去注释与字符串后做括号配对
    depth = 0
    i, n = 0, len(s)
    state = "code"
    bal = {"(": 0, "{": 0, "[": 0}
    pairs = {")": "(", "}": "{", "]": "["}
    while i < n:
        c = s[i]
        nx = s[i + 1] if i + 1 < n else ""
        if state == "code":
            if c == "/" and nx == "/":
                state = "lc"; i += 2; continue
            if c == "/" and nx == "*":
                state = "bc"; i += 2; continue
            if c == '"':
                state = "str"; i += 1; continue
            if c == "'":
                state = "chr"; i += 1; continue
            if c in bal:
                bal[c] += 1
            elif c in pairs:
                bal[pairs[c]] -= 1
        elif state == "bc":
            if c == "*" and nx == "/":
                state = "code"; i += 2; continue
        elif state == "lc":
            if c == "\n":
                state = "code"
        elif state in ("str", "chr"):
            if c == "\\":
                i += 2; continue
            if (state == "str" and c == '"') or (state == "chr" and c == "'"):
                state = "code"
        i += 1

    for k, v in bal.items():
        say(OK if v == 0 else FAIL, "括号 %s 配对: %s%d" % (k, "+" if v > 0 else "", v))

    hooks = len(re.findall(r"(?m)^%hook\s", s))
    ends = len(re.findall(r"(?m)^%end\s*$", s))
    say(OK if hooks == ends and hooks > 0 else FAIL,
        "%%hook / %%end 配对: %d / %d" % (hooks, ends))

    ifs = len(re.findall(r"(?m)^@interface", s))
    ife = len(re.findall(r"(?m)^@end", s))
    impl = len(re.findall(r"(?m)^@implementation", s))
    say(OK if ife == ifs + impl else FAIL,
        "@interface=%d @implementation=%d @end=%d（应满足 @end = 两者之和）" % (ifs, impl, ife))

    say(OK if "%ctor" in s else WARN, "存在 %%ctor 入口: %s" % ("%ctor" in s))

    # 关键设计点必须在
    for needle, desc in [
        ("buildPanel", "hook 面板搭建"),
        ("filterButton:x:y:w:sel:", "复用找鸡按钮工厂"),
        ("conditionBtn", "以「成色」按钮定位插入点"),
        ("cellForRowAtIndexPath:", "hook 结果行"),
        ("copyLink:", "定位「复制链接」按钮"),
        ("ZZPassesRegionVersion", "版本/地区筛选判定"),
        ("ZZFavStore", "收藏持久化"),
        ("ZZRegionVersionVC", "版本地区选择界面"),
        ("ZZFavoritesVC", "我的收藏界面"),
    ]:
        say(OK if needle in s else FAIL, "包含 %s（%s）" % (needle, desc))

    # 检查 %orig 使用是否只出现在 hook 块内
    say(OK, "行数: %d" % len(s.splitlines()))


# ---------------------------------------------------------------- 2. 桥接 plist
def check_plist():
    print("\n=== 2. 桥接 plist ===")
    p = os.path.join(ROOT, "layout", "Library", "MobileSubstrate",
                     "DynamicLibraries", "ZZMergeBridge.plist")
    if not os.path.exists(p):
        say(FAIL, "找不到 ZZMergeBridge.plist")
        return
    s = read(p)
    ok = ("com.wuba.zhuanzhuan" in s) and ("<key>Filter</key>" in s) and ("Bundles" in s)
    say(OK if ok else FAIL, "注入目标为 com.wuba.zhuanzhuan 且结构正确: %s" % ok)
    say(OK if s.strip().startswith("<?xml") else WARN, "是标准 plist XML")


# ---------------------------------------------------------------- 3. vendor_src
def check_vendor():
    print("\n=== 3. vendor_src 原始包 ===")
    d = os.path.join(ROOT, "vendor_src")
    if not os.path.isdir(d):
        say(FAIL, "找不到 vendor_src/")
        return
    debs = [f for f in os.listdir(d) if f.lower().endswith(".deb")]
    say(OK if len(debs) >= 2 else FAIL, "找到 %d 个 .deb（应为 2）" % len(debs))

    want = {"ZZ": False, "SS": False}
    for f in debs:
        path = os.path.join(d, f)
        try:
            data = open(path, "rb").read()
        except Exception as e:
            say(FAIL, "读取 %s 失败: %s" % (f, e))
            continue
        if data[:8] != b"!<arch>\n":
            say(FAIL, "%s 不是 ar 归档" % f)
            continue
        members = {}
        pos = 8
        while pos + 60 <= len(data):
            hdr = data[pos:pos + 60]
            nm = hdr[0:16].decode("ascii", "replace").strip()
            try:
                sz = int(hdr[48:58].decode("ascii").strip())
            except ValueError:
                break
            members[nm] = data[pos + 60:pos + 60 + sz]
            pos += 60 + sz + (sz % 2)
        data_tar = None
        for k in members:
            if k.startswith("data.tar"):
                data_tar = k
        if not data_tar:
            say(FAIL, "%s 缺少 data.tar.*" % f)
            continue
        raw = members[data_tar]
        if data_tar.endswith(".xz"):
            raw = lzma.decompress(raw)
        elif data_tar.endswith(".gz"):
            import gzip
            raw = gzip.decompress(raw)
        names = []
        try:
            with tarfile.open(fileobj=_io.BytesIO(raw)) as tf:
                names = tf.getnames()
        except Exception as e:
            say(FAIL, "%s 解 data.tar 失败: %s" % (f, e))
            continue
        dyn = [x for x in names if x.endswith(".dylib")]
        pl = [x for x in names if x.endswith(".plist")]
        say(OK if dyn else FAIL, "%s: dylib=%s plist=%s"
            % (f[:34], [os.path.basename(x) for x in dyn],
               [os.path.basename(x) for x in pl]))
        joined = " ".join(names)
        if "ShuiShuiZZFilter" in joined or "SSFilter" in joined:
            want["SS"] = True
        if "ZZFloat" in joined or "转转找鸡" in joined or "zzzj" in joined.lower():
            want["ZZ"] = True
    say(OK if want["ZZ"] else FAIL, "已包含 找鸡 的 dylib: %s" % want["ZZ"])
    say(OK if want["SS"] else FAIL, "已包含 水水 的 dylib: %s" % want["SS"])


# ---------------------------------------------------------------- 4. Makefile
def check_makefile():
    print("\n=== 4. Makefile ===")
    p = os.path.join(ROOT, "Makefile")
    if not os.path.exists(p):
        say(FAIL, "找不到 Makefile")
        return
    s = read(p)
    for needle, desc in [
        ("include $(THEOS)/makefiles/common.mk", "引入 Theos 公共规则"),
        ("include $(THEOS_MAKE_PATH)/tweak.mk", "引入 tweak 规则"),
        ("internal-stage::", "标准 staging 钩子（打包前并入原始 dylib）"),
        ("TWEAK_NAME = ZZMergeBridge", "tweak 名称与 plist 一致"),
        ("-fobjc-arc", "启用 ARC"),
        ("DynamicLibraries", "目标安装目录正确"),
    ]:
        say(OK if needle in s else FAIL, "%s（%s）" % (desc, needle))
    say(OK if "before-package" not in s else WARN,
        "未使用非标准钩子 before-package: %s" % ("before-package" not in s))

    # 关键：不能默认导出 THEOS_PACKAGE_SCHEME，否则 Theos 会因未知 scheme 直接报错
    bad_scheme = re.findall(r"(?m)^\s*export\s+THEOS_PACKAGE_SCHEME\s*[:?]?=", s)
    say(OK if not bad_scheme else FAIL,
        "未默认导出 THEOS_PACKAGE_SCHEME（否则报 scheme does not exist）: %s"
        % (not bad_scheme))
    if "roothide" in s:
        code_lines = [l for l in s.splitlines()
                      if "roothide" in l and not l.lstrip().startswith("#")]
        say(OK if not code_lines else FAIL,
            "roothide 字样只出现在注释中: %s" % (not code_lines))


# ---------------------------------------------------------------- 6. CI 工作流
def check_workflow():
    print("\n=== 6. GitHub Actions 工作流 ===")
    p = os.path.join(ROOT, ".github", "workflows", "build.yml")
    if not os.path.exists(p):
        say(FAIL, "找不到 .github/workflows/build.yml")
        return
    s = read(p)
    say(OK if "actions/checkout@v4" in s else FAIL, "使用 checkout@v4")
    say(OK if "theos/theos.git" in s else FAIL, "自动安装 Theos")
    say(OK if "ldid" in s else FAIL, "自动获取 ldid（给原始 dylib 重签名）")
    say(OK if "ldid -S" in s else FAIL, "对原始 dylib 执行 ldid -S")
    say(OK if "dpkg-deb -x" in s else FAIL, "从 vendor_src 解出原始 dylib")
    say(OK if "make package FINALPACKAGE=1" in s else FAIL, "执行 make package")
    say(OK if "upload-artifact" in s else FAIL, "上传 deb 产物")

    # ---- iOS SDK 安装必须有多重回退 + 硬校验（第二次构建失败的根因）----
    say(OK if "get-toolchain.sh" in s else FAIL, "方式A：调用官方 get-toolchain.sh")
    say(OK if "theos/sdks" in s else FAIL, "方式B：回退克隆 theos/sdks 仓库")
    say(OK if "sdk_ok" in s else FAIL, "定义 SDK 可用性校验函数 sdk_ok")
    say(OK if "sdks.tar.gz" in s and "tar -xzf" in s else FAIL,
        "方式C：从 SDK 归档包手动解出")
    say(OK if 'grep -qi' in s and 'iPhoneOS' in s else FAIL,
        "校验 sdks 目录里确实存在 iPhoneOS*.sdk")

    # ---- 编译工具链必须也有回退 + 硬校验（第三次构建失败的根因）----
    say(OK if "toolchain/linux/iphone" in s else FAIL,
        "工具链目标目录 toolchain/linux/iphone")
    say(OK if "toolchain_ok" in s else FAIL, "定义工具链校验函数 toolchain_ok")
    say(OK if "-x \"$TOOLCHAIN_DIR/bin/clang\"" in s else FAIL,
        "以 clang 是否可执行作为工具链判定标准")
    say(OK if "download.swift.org" in s else FAIL,
        "方式B：下载 Swift 官方工具链（含交叉编译 clang）")
    say(OK if "CANDIDATES" in s and "for v in $CANDIDATES" in s else FAIL,
        "候选 Swift 版本轮询（不写死单一版本号）")
    say(OK if "command -v clang" in s else FAIL,
        "方式C：系统 clang 兜底（网络受限时仍有机会成功）")
    say(OK if "apt-get install" in s and "clang lld llvm binutils" in s else FAIL,
        "apt 安装 clang/lld/llvm/binutils（兜底路径依赖）")

    # ---- 关键：不能再用 "|| true" 把安装失败吞掉 ----
    m = re.search(r"(?m)^.*get-toolchain\.sh.*\|\|\s*true\s*$", s)
    say(OK if not m else FAIL,
        "get-toolchain.sh 未被 '|| true' 静默吞掉失败: %s" % (not m))
    # 必须会在没有 SDK / 工具链时明确失败退出
    seg = s[s.find("toolchain_ok"):]
    say(OK if seg.count("exit 1") >= 2 else FAIL,
        "工具链与 SDK 校验不通过时都显式 exit 1")

    # 绝不能在工作流里设置 THEOS_PACKAGE_SCHEME
    env_set = re.findall(r"(?m)^\s*THEOS_PACKAGE_SCHEME\s*:", s)
    say(OK if not env_set else FAIL,
        "工作流未设置 THEOS_PACKAGE_SCHEME（这是第一次构建失败的原因）: %s"
        % (not env_set))
    say(OK if not re.search(r"(?m)^\s*scheme:\s*$", s) else FAIL,
        "已移除会误导的 scheme 输入项")

    # 步骤顺序：必须先工具链、后 SDK
    i_tc = s.find("安装编译工具链")
    i_sdk = s.find("安装 iOS SDK")
    say(OK if 0 < i_tc < i_sdk else FAIL,
        "步骤顺序为先装工具链、再装 SDK（位置 %d < %d）" % (i_tc, i_sdk))
    say(OK, "工作流行数: %d" % len(s.splitlines()))


# ---------------------------------------------------------------- 5. control
def check_control():
    print("\n=== 5. control 元数据 ===")
    p = os.path.join(ROOT, "control")
    if not os.path.exists(p):
        say(FAIL, "找不到 control")
        return
    s = read(p)
    fields = dict(re.findall(r"(?m)^([A-Za-z-]+):\s*(.*)$", s))
    for f in ("Package", "Name", "Version", "Architecture", "Depends", "Conflicts", "Section"):
        say(OK if f in fields else FAIL, "字段 %s: %s" % (f, fields.get(f, "(缺失)")))
    say(OK if fields.get("Architecture") == "iphoneos-arm64e" else WARN,
        "架构为 iphoneos-arm64e（与原包一致）")
    conf = fields.get("Conflicts", "")
    for c in ("com.shuishui.zzfilter.roothide", "com.codev.zzphonefilter.roothide"):
        say(OK if c in conf else WARN, "Conflicts 含 %s: %s" % (c, c in conf))
    say(OK if "rootless-compat" in fields.get("Pre-Depends", "") else WARN,
        "保留 rootless-compat 前置依赖（与原找鸡包一致）")


def main():
    print("ZZMerge 工程自检")
    print("工程根目录:", ROOT)
    check_source()
    check_plist()
    check_vendor()
    check_makefile()
    check_control()
    check_workflow()
    print("\n" + "=" * 60)
    if problems:
        print("发现 %d 个问题：" % len(problems))
        for x in problems:
            print("  -", x)
        return 1
    print("全部检查通过。可以推送构建。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
