#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 本地一键构建（如果你有 Linux 或 macOS，可以不用 GitHub Actions）
#
#   ./build_local.sh            # 默认 roothide
#   ./build_local.sh rootless   # 普通无根
#
# 需要预先具备：git, make, perl, curl, dpkg-deb, fakeroot, ldid
# 脚本会自动下载 Theos 到 ../theos（若不存在）
# ---------------------------------------------------------------------------
set -euo pipefail

SCHEME="${1:-roothide}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

export THEOS="${THEOS:-$HERE/../theos}"
export THEOS_PACKAGE_SCHEME="$SCHEME"

echo ">>> THEOS = $THEOS"
echo ">>> SCHEME = $THEOS_PACKAGE_SCHEME"

# ---- 1. Theos ----
if [ ! -d "$THEOS/makefiles" ]; then
  echo ">>> 安装 Theos"
  git clone --recursive --depth 1 https://github.com/theos/theos.git "$THEOS"
fi
if [ ! -d "$THEOS/sdks" ] || [ -z "$(ls -A "$THEOS/sdks" 2>/dev/null)" ]; then
  echo ">>> 下载 iOS SDK"
  git clone --depth 1 https://github.com/theos/sdks.git "$THEOS/sdks"
fi
if [ ! -d "$THEOS/toolchain" ] || [ -z "$(ls -A "$THEOS/toolchain" 2>/dev/null)" ]; then
  echo ">>> 下载 iOS 工具链"
  "$THEOS/bin/get-toolchain.sh" || echo "   (脚本失败，请手动准备工具链)"
fi

# ---- 2. ldid ----
if ! command -v ldid >/dev/null 2>&1; then
  echo ">>> 未找到 ldid，尝试下载到 ~/.local/bin"
  mkdir -p "$HOME/.local/bin"
  curl -sSL -o "$HOME/.local/bin/ldid" \
    https://github.com/ProcursusTeam/ldid/releases/download/v2.1.5-procursus7/ldid_linux_x86_64
  chmod +x "$HOME/.local/bin/ldid"
  export PATH="$HOME/.local/bin:$PATH"
fi

# ---- 3. 从原始 deb 取出 dylib 与 plist ----
echo ">>> 解出原始 dylib"
rm -rf vendor .tmp_x
mkdir -p vendor .tmp_x
shopt -s nullglob
for f in vendor_src/*.deb; do
  echo "    - $f"
  rm -rf .tmp_x/*; mkdir -p .tmp_x
  dpkg-deb -x "$f" .tmp_x
  find .tmp_x -name '*.dylib' -exec cp -v {} vendor/ \;
  find .tmp_x -name '*.plist' -path '*DynamicLibraries*' -exec cp -v {} vendor/ \;
done
shopt -u nullglob
rm -rf .tmp_x
echo ">>> vendor 内容:"; ls -la vendor/

# ---- 4. 重新签名 ----
for d in vendor/*.dylib; do
  echo ">>> ldid -S $d"
  ldid -S "$d"
done

# ---- 5. 构建 ----
echo ">>> make package"
make clean || true
make package FINALPACKAGE=1

echo
echo ">>> 完成，产物："
find . -maxdepth 2 -name '*.deb' -exec ls -la {} \;
echo
echo ">>> 校验："
for d in $(find . -maxdepth 2 -name '*.deb'); do
  dpkg-deb -I "$d"
  dpkg-deb -c "$d"
done
