# 转转合并版 —— 找鸡(ZZ) + 水水(SS) 功能整合
#
# 架构：
#   1. 本包同时携带 找鸡 与 水水 两个原始 dylib（原封不动，CI 里重新签名），
#      二者注入同一个 App（com.wuba.zhuanzhuan）。类名前缀不同（ZZ* / SS*），
#      实测零冲突，可安全共存。
#   2. 另有一个桥接 tweak（本工程编译产物），负责：
#        - 在 找鸡 筛选面板的「成色」按钮之后插入「版本地区」按钮；
#        - 在 找鸡 抓取结果的「复制链接」下方插入「收藏」按钮；
#        - 面板右上角增加「我的收藏」入口（可按版本/地区筛选、复制链接、删除）。
#
# 打包方式说明：
#   vendor/  放两个原始 dylib + 它们的 MobileSubstrate plist（由 CI 从原始 deb 解出）
#   layout/  放静态文件（桥接 plist 等），Theos 会自动 stage 进 deb
#   tweak/   放桥接源码，Theos 编译后自动 stage
#   internal-stage:: 钩子在 Theos staging 完成后、打包前，把 vendor 里的
#   原始 dylib/plist 也拷进 same staging 目录，从而一起进 deb。
#
# 本地构建：
#   export THEOS=~/theos
#   export THEOS_PACKAGE_SCHEME=roothide     # 或 rootless
#   make package FINALPACKAGE=1

export ARCHS = arm64 arm64e
export TARGET = iphone:clang:latest:15.0
export THEOS_PACKAGE_SCHEME ?=

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = ZZMergeBridge

ZZMergeBridge_FILES = tweak/ZZMergeBridge.x
ZZMergeBridge_CFLAGS = -fobjc-arc -Wno-unused-variable -Wno-deprecated-declarations
ZZMergeBridge_FRAMEWORKS = UIKit Foundation

include $(THEOS_MAKE_PATH)/tweak.mk

# ---------------------------------------------------------------------------
# 在 staging 完成后、真正打 deb 之前，把两个原始 dylib 与 plist 一起塞进去
# ---------------------------------------------------------------------------
DYLIB_DEST = $(THEOS_STAGING_DIR)/Library/MobileSubstrate/DynamicLibraries

# vendor/ 里的原始 dylib 由 CI（或 build_local.sh）从 vendor_src/*.deb 解出。
# 这里再加一层保险：若 vendor/ 为空，就在构建期现解一次。
vendor-guard::
	@mkdir -p "$(THEOS_PROJECT_DIR)/vendor"
	@if ! ls "$(THEOS_PROJECT_DIR)"/vendor/*.dylib >/dev/null 2>&1; then \
		echo ">>> [ZZMerge] vendor/ 为空，尝试从 vendor_src/*.deb 现场解包"; \
		command -v dpkg-deb >/dev/null 2>&1 || \
			(echo ">>> [ZZMerge] 错误：缺少 dpkg-deb，无法解包"; exit 1); \
		TMP="$$(mktemp -d)"; \
		for f in "$(THEOS_PROJECT_DIR)"/vendor_src/*.deb; do \
			[ -e "$$f" ] || continue; \
			echo "    - $$f"; \
			dpkg-deb -x "$$f" "$$TMP"; \
			find "$$TMP" -name '*.dylib' -exec cp -f {} "$(THEOS_PROJECT_DIR)/vendor/" \; ; \
			find "$$TMP" -name '*.plist' -path '*DynamicLibraries*' \
				-exec cp -f {} "$(THEOS_PROJECT_DIR)/vendor/" \; ; \
		done; \
		rm -rf "$$TMP"; \
	fi

internal-stage:: vendor-guard
	@echo ">>> [ZZMerge] 把原始 dylib 并入打包目录"
	@mkdir -p "$(DYLIB_DEST)"
	@for f in $(THEOS_PROJECT_DIR)/vendor/*.dylib; do \
		[ -e "$$f" ] || continue; \
		cp -f "$$f" "$(DYLIB_DEST)/"; \
		echo "    + $$(basename "$$f")"; \
	done
	@for f in $(THEOS_PROJECT_DIR)/vendor/*.plist; do \
		[ -e "$$f" ] || continue; \
		cp -f "$$f" "$(DYLIB_DEST)/"; \
		echo "    + $$(basename "$$f")"; \
	done
	@echo ">>> [ZZMerge] 打包目录内容："
	@ls -la "$(DYLIB_DEST)/"
	@test -f "$(DYLIB_DEST)/转转找鸡.dylib" || \
		(echo ">>> [ZZMerge] 错误：缺少 vendor/转转找鸡.dylib"; exit 1)
	@test -f "$(DYLIB_DEST)/ShuiShuiZZFilter.dylib" || \
		(echo ">>> [ZZMerge] 错误：缺少 vendor/ShuiShuiZZFilter.dylib"; exit 1)
	@test -f "$(DYLIB_DEST)/ZZMergeBridge.dylib" || \
		(echo ">>> [ZZMerge] 警告：桥接 dylib 未出现在打包目录（编译可能失败）"; true)

after-install::
	install.exec "killall -9 zhuanzhuan 2>/dev/null || true"
