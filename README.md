# 转转合并版 ——「找鸡 + 水水」功能整合

把 **水水(ZzFilter) 的「版本/地区」筛选** 和 **「收藏」功能** 整合进 **找鸡** 的界面里，
最终只产出一个 `.deb`，装法与你现在用的完全一样。

---

## 一、整合后的效果

以 **找鸡** 为主体（保留它自动抓取、速度快的优点）：

| 位置 | 改动 |
|---|---|
| 悬浮球面板筛选行 | 在「成色」按钮**之后**插入 **「版本地区」** 按钮 |
| 点「版本地区」 | 弹出面板：可设 **系统版本区间**（如 15.0 ~ 17.2）+ **地区**（下拉列表） |
| 抓取结果每一行 | 在「复制链接」**下方**插入 **「收藏」** 按钮（★ 已收藏 / ☆ 收藏） |
| 面板右上角 | 新增 **「我的收藏」** 入口：查看收藏、按版本/地区筛选、复制链接、左滑删除 |

「版本地区」一旦设置，会**同时作用于**：
- 抓取结果列表（行数按条件过滤）
- 「我的收藏」列表

---

## 二、得到 deb 的方法（不需要你本地装任何东西）

已经配好 GitHub Actions 云编译，你只要：

1. 在 GitHub 上新建一个仓库（私有/公开都行）。
2. 把本文件夹 `zzmerge/` 里的**所有内容**（注意包含 `.github` 这个隐藏文件夹）上传上去。
   - 网页上传：直接把 `zzmerge` 里的文件拖进去
   - 或用 git：
     ```
     cd zzmerge
     git init
     git add -A
     git commit -m "转转合并版"
     git branch -M main
     git remote add origin https://github.com/<你的用户名>/<仓库名>.git
     git push -u origin main
     ```
3. 推送后会自动开始构建。也可以到 **Actions → Build ZZMerge deb → Run workflow** 手动触发，
   那里可以选越狱方案：
   - **roothide**（默认）—— 你现在用的这个版本就是 RootHide/Rootless，保持一致
   - **rootless** —— 普通无根越狱
4. 构建完成后，在该次运行的页面底部 **Artifacts** 里下载 `zzmerge-deb-roothide`，
   解压得到 `.deb`。

拿到 deb 后，用你平时的方式（爱思助手 / Sileo / Filza 等）安装即可。

---

## 三、装之前要注意

- **必须先卸载原来的「转转找鸡」和「水水·转转手机筛选」**，
  否则会出现两组悬浮球和重复按钮。
  本包的 control 里已经写了 `Conflicts` / `Replaces`，正常安装时包管理器会帮你处理。
- 本包**同时包含**两个原始 dylib（找鸡 + 水水，一个字节都没改）和一个桥接 dylib。
  也就是说装完之后设备上会有 3 个 dylib：
  - `转转找鸡.dylib` —— 提供主体功能
  - `ShuiShuiZZFilter.dylib` —— 保留（功能已被桥接层复用，不影响使用）
  - `ZZMergeBridge.dylib` —— 新增的整合层，负责上面表格里的所有改动
- 安装/卸载时会自动 `killall zhuanzhuan`，重开 App 生效。

---

## 四、目录结构

```
zzmerge/
├── .github/workflows/build.yml   # 云编译：自动出 deb
├── Makefile                      # Theos 构建脚本
├── control                       # deb 包元数据（包名/版本/依赖/冲突）
├── layout/                       # 静态资源，会原样进 deb
│   └── Library/MobileSubstrate/DynamicLibraries/ZZMergeBridge.plist
├── tweak/
│   └── ZZMergeBridge.x           # ★ 桥接层源码（所有新功能都在这里）
├── tools/
│   └── paren_check.py            # 源码静态自检小工具
└── vendor_src/                   # 你给的两个原始 deb（构建时自动解出 dylib）
    ├── 转转找鸡-0.0.1-8+debug-iphoneos-arm64e.deb
    └── 转转ShuiShuiZZFilter_2.6.3_RootHide_iphoneos-arm64e.deb
```

构建时 CI 会做这几件事：
1. 装 Theos + iOS 工具链 + ldid
2. 用 `dpkg-deb -x` 把 `vendor_src/` 里两个原始 deb 解开，取出其中的 dylib 和 plist
3. 用 `ldid -S` 给两个原始 dylib **重新签名**（二进制在 Linux 上搬运后必须重签，否则加载不了）
4. 编译 `tweak/ZZMergeBridge.x` → `ZZMergeBridge.dylib`
5. 把三者 + 两个 plist 一起打成新的 deb
6. 打包后校验：打印 control、文件清单、每个 dylib 的架构与签名状态

---

## 五、桥接层是怎么做到「插入到成色之后」的

桥接层没有改动任何原始机器码，全部是**运行时**完成。用到的私有成员名都来自
对找鸡 dylib 符号表的实际分析（不是猜的）：

| 用到的成员 | 地址 | 用途 |
|---|---|---|
| `+[ZZFloat shared]` | 0x6c70 | 拿面板单例 |
| `-[ZZFloat buildPanel]` | 0x7cd8 | 面板搭建完成时注入按钮 |
| `-[ZZFloat filterButton:x:y:w:sel:]` | 0x8b34 | **复用找鸡自己的工厂方法**造按钮，保证样式一致 |
| `-[ZZFloat refilter]` | 0xbc7c | 找鸡筛选变化后，跟着刷新 |
| `-[ZZFloat tableView:cellForRowAtIndexPath:]` | 0xc8a0 | 每行插入「收藏」按钮 |
| `-[ZZFloat copyLink:]` | 0xd354 | 用它定位「复制链接」按钮的位置 |
| ivar `_modelBtn _batteryBtn _verBtn _conditionBtn _storageBtn` | — | 5 个筛选按钮，按 x 排序定插入点 |
| ivar `_panel _titleLabel _table _shown` | — | 面板 / 标题 / 表 / 当前结果数组 |

插入算法（`-buildPanel` 里）：
1. 收齐 5 个筛选按钮，按 x 坐标排序；
2. 算出相邻按钮间距 `step`（不写死坐标，换机型/改布局都能适应）；
3. 插入点 = 「成色」按钮的 x + step；
4. 把插入点及其右侧的按钮整体右移一格，腾出位置；
5. 用 `filterButton:x:y:w:sel:` 造出「版本地区」按钮放进去，标题动态显示当前条件。

「收藏」按钮定位：在 cell 里递归找按钮 → 优先按标题/无障碍标签含「复制」「链接」
找到「复制链接」→ 放在它正下方；如果已经贴底，就放到它右侧，避免压到内容。

---

## 六、如果装上去发现哪里不对

因为我看不到你的手机屏幕，桥接层里有**自动降级 + 日志**：

- 找不到 panel / 按钮数量不足 → 跳过注入，不崩溃，只打日志
- 找不到「复制链接」按钮 → 退化成「最下面那个按钮的下面」
- 取不到商品字段 → 该行不显示收藏按钮

**看日志**（在手机终端里执行）：

```
log stream --predicate 'eventMessage CONTAINS "[ZZMerge]"' --level debug
```

或者用 Filza 看系统日志，筛选 `ZZMerge`。

需要调整时，改 `tweak/ZZMergeBridge.x` 里对应部分再推一次即可，
比如地区候选列表在 `ZZRegionChoices()`，收藏入口位置在 `buildPanel` 末尾。

---

## 七、免责说明

- 两个原始 dylib 未做任何字节修改，只做了重新签名。
- 桥接层只依赖公开的 Objective-C 运行时机制（method swizzling / associated object），
  不 hook 系统框架，不改 App 自身二进制。
- 仍建议先在测试机上验证；数据（筛选条件、收藏）存在 App 自己的
  `NSUserDefaults` 里，卸载重装会清空。
