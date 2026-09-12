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
#   make package FINALPACKAGE=1
#
# ---------------------------------------------------------------------------
# 【构建模式说明 —— 很重要，别乱改】
#
# 本包采用 **rootful（默认）** 方式构建，刻意不设置 THEOS_PACKAGE_SCHEME。
#
# 依据：原版「转转找鸡」包本身就是 rootful 构建，证据在它自己的 control 里：
#     Pre-Depends: rootless-compat (>= 0.9)
#     安装路径:    /Library/MobileSubstrate/DynamicLibraries/
# rootless-compat 会在无根 / RootHide 设备上把 /Library/... 自动映射到真实路径
# （如 /var/jb/Library/...）。既然找鸡在目标设备上能正常工作，照抄它的构建
# 方式是最稳的选择。
#
# 另外：Theos 官方只有默认(rootful) 与 rootless 两个 package scheme，
# 不存在 "roothide"；写了会直接报错
#     *** 'roothide' package scheme does not exist.  Stop.
#
# 若将来确实需要换成 rootless（普通无根越狱、且设备上没装 rootless-compat），
# 再显式导出：export THEOS_PACKAGE_SCHEME=rootless
# 此时安装路径会自动变成 /var/jb/Library/...，且需要同步修改 control 的
# Pre-Depends（去掉 rootless-compat）。
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 架构选择：只出 arm64，不出 arm64e
#
# 原因（已核对 Theos 源码 makefiles/instance/rules.mk 第 124-131 行）：
#     124: # Static libraries do not support having multiple arm64e ABIs, ...
#     125: IS_NEW_ABI := $(call __vercmp,$(_THEOS_TARGET_CC_VERSION),ge,12.0.0)
#     127: ifneq ($(THEOS_PLATFORM_NAME),macosx)
#     128: # On non macOS, always use old ABI as only macOS can compile with new ABI
#     129:     IS_NEW_ABI = 0
#   即：**在 Linux 上只能产出 arm64e 的旧 ABI**。而实际构建时链接器会报
#       ld: warning: object file ... was built with an incompatible arm64e ABI compiler
#   这个 arm64e 切片有无法在真机加载的风险，且 CI 里无法验证。
#
#   反过来，arm64 切片在 iOS 11 及以上的所有 arm64 设备上都可正常加载，
#   而本包的依赖要求 firmware >= 15.0，所以 arm64 完全够用，且更可靠。
#   若你确需 arm64e（例如要给 arm64e 进程原生性能），把它加回 ARCHS 即可，
#   但要清楚那个 ABI 警告意味着什么。
# ---------------------------------------------------------------------------

export ARCHS = arm64
export TARGET = iphone:clang:latest:15.0

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = ZZMergeBridge

ZZMergeBridge_FILES = tweak/ZZMergeBridge.x
ZZMergeBridge_CFLAGS = -fobjc-arc -Wno-unused-variable -Wno-deprecated-declarations
ZZMergeBridge_FRAMEWORKS = UIKit Foundation

include $(THEOS_MAKE_PATH)/tweak.mk

# ---------------------------------------------------------------------------
# 打包含义开关
#
#   BUNDLE_BASE=0（默认，推荐）
#       只产出「附加插件」：ZZMergeBridge.dylib + .plist
#       找鸡由你自己保留，本包不碰它。
#       —— 这是符合需求的形态：把两个功能「加进」找鸡，而不是替换/合并文件。
#
#   BUNDLE_BASE=1
#       额外把原版 转转找鸡.dylib/.plist 也打进包（一键安装用）。
#       注意：这条路径会覆盖你原有的找鸡，且一旦找鸡本身出问题会一起崩。
#
# 用法：  make package FINALPACKAGE=1 BUNDLE_BASE=1
# ---------------------------------------------------------------------------
BUNDLE_BASE ?= 0
export BUNDLE_BASE

DYLIB_DEST = $(THEOS_STAGING_DIR)/Library/MobileSubstrate/DynamicLibraries

internal-stage::
	@echo ">>> [ZZMerge] staging 收尾（BUNDLE_BASE=$(BUNDLE_BASE)）"
	@mkdir -p "$(DYLIB_DEST)"
ifeq ($(BUNDLE_BASE),1)
	@echo ">>> BUNDLE_BASE=1：把原版「转转找鸡」也并入打包目录"
	@echo ">>> 注意：这会在安装时覆盖你原有的找鸡"
	@for f in "$(THEOS_PROJECT_DIR)/vendor/转转找鸡.dylib" \
	          "$(THEOS_PROJECT_DIR)/vendor/转转找鸡.plist"; do \
		if [ -e "$$f" ]; then \
			cp -f "$$f" "$(DYLIB_DEST)/"; \
			echo "    + $$(basename "$$f")"; \
		else \
			echo "    !!! 缺少 $$f（需要先解出 vendor/）"; exit 1; \
		fi; \
	done
else
	@echo ">>> BUNDLE_BASE=0：只出附加插件，不动你原有的找鸡"
	@echo ">>> 水水同样不进包（桥接层已自行实现其两项功能）"
endif
	@echo ">>> [ZZMerge] 打包目录内容："
	@ls -la "$(DYLIB_DEST)/" 2>/dev/null || true
	@test -f "$(DYLIB_DEST)/ZZMergeBridge.dylib" || \
		(echo ">>> [ZZMerge] 错误：桥接 dylib 未生成，编译可能失败"; exit 1)
	@test -f "$(DYLIB_DEST)/ZZMergeBridge.plist" || \
		(echo ">>> [ZZMerge] 错误：桥接 plist 未就位"; exit 1)
	@echo ">>> 最终清单："
	@ls -1 "$(DYLIB_DEST)/" | grep -Ev '\.(dSYM|txt|log)$$' || true

after-install::
	install.exec "killall -9 zhuanzhuan 2>/dev/null || true"
