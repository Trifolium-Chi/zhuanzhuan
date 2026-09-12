// ===========================================================================
//  ZZMergeBridge —— 转转「找鸡 + 水水」功能整合桥接层
// ===========================================================================
//
//  需求：
//    1. 筛选面板：在「成色」按钮之后插入「版本地区」按钮
//       —— 提供 系统版本区间(min/max) + 地区 两项筛选，作用于抓取结果。
//    2. 结果行：在「复制链接」下方插入「收藏」按钮，并可在面板查看收藏。
//
//  设计：
//    * 不修改两个原始 dylib 的字节，桥接层只做运行时补充。
//    * 主动防御：所有对 ZZFloat 私有结构的访问都判空兜底，找不到就静默跳过
//      并写日志，绝不因为内部实现变动而崩溃。
//    * 面板按钮按「相邻按钮间距」自适应插入，不写死坐标。
//
//  说明：以下私有方法/属性名均来自对 转转找鸡-0.0.1-8 dylib 符号表的分析，
//        不是猜测：buildPanel(0x7cd8)、filterButton:x:y:w:sel:(0x8b34)、
//        refilter(0xbc7c)、tableView:cellForRowAtIndexPath:(0xc8a0)、
//        ivar: _panel/_titleLabel/_table/_shown/_modelBtn/_batteryBtn/
//              _verBtn/_conditionBtn/_storageBtn
// ===========================================================================

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>

#pragma mark - 配置与工具

static const BOOL kDebugLog = YES;

#define ZMLOG(fmt, ...)                                                        \
    do {                                                                       \
        if (kDebugLog) NSLog(@"[ZZMerge] " fmt, ##__VA_ARGS__);                 \
    } while (0)

static NSString *const kFavKey    = @"com.hang.zzzj.merge.favorites";
static NSString *const kRegionKey = @"com.hang.zzzj.merge.region";
static NSString *const kVerMinKey = @"com.hang.zzzj.merge.ver.min";
static NSString *const kVerMaxKey = @"com.hang.zzzj.merge.ver.max";
static NSString *const kChangedNote = @"ZZMergeFilterChanged";

static NSArray<NSString *> *ZZRegionChoices(void) {
    return @[ @"不限", @"北京", @"上海", @"广州", @"深圳", @"杭州", @"成都",
              @"武汉", @"南京", @"西安", @"重庆", @"天津", @"苏州", @"长沙",
              @"郑州", @"青岛", @"东莞", @"宁波", @"佛山", @"合肥" ];
}

/// 把选择子名转成 C 字符串，用作 associated object 的 key
static const void *ZZKey(const char *name) { return (const void *)name; }

static id ZZSafeGet(id obj, NSString *selName) {
    if (!obj) return nil;
    SEL s = NSSelectorFromString(selName);
    if (![obj respondsToSelector:s]) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(obj, s);
}

static NSString *ZZStr(id obj) {
    if ([obj isKindOfClass:[NSString class]]) return (NSString *)obj;
    if ([obj isKindOfClass:[NSNumber class]]) return [(NSNumber *)obj stringValue];
    return nil;
}

#pragma mark - 商品快照

/// 从 ZZItem 抠出我们需要的字段（属性名以二进制符号表为准）
static NSDictionary *ZZItemSnapshot(id item) {
    if (!item) return nil;
    NSMutableDictionary *d = [NSMutableDictionary dictionary];
    NSArray *keys = @[ @"infoId", @"title", @"price", @"originalPrice",
                       @"jumpUrl", @"appearance", @"battery",
                       @"sysVer", @"storage", @"charge" ];
    for (NSString *k in keys) {
        NSString *v = ZZStr(ZZSafeGet(item, k));
        if (v.length) d[k] = v;
    }
    if (!d[@"infoId"] && !d[@"title"]) return nil;
    return d;
}

#pragma mark - 版本比较

/// "iOS 15.4.1" -> @[@15,@4,@1]
static NSArray<NSNumber *> *ZZVerParts(NSString *s) {
    if (!s.length) return @[];
    NSMutableString *buf = [NSMutableString string];
    for (NSUInteger i = 0; i < s.length; i++) {
        unichar c = [s characterAtIndex:i];
        if ((c >= '0' && c <= '9') || c == '.') {
            [buf appendFormat:@"%C", c];
        } else if (buf.length) {
            break;
        }
    }
    NSMutableArray<NSNumber *> *out = [NSMutableArray array];
    for (NSString *p in [buf componentsSeparatedByString:@"."]) {
        if (p.length) [out addObject:@(p.integerValue)];
    }
    return out;
}

static NSInteger ZZVerCmp(NSString *a, NSString *b) {
    NSArray<NSNumber *> *x = ZZVerParts(a), *y = ZZVerParts(b);
    NSUInteger n = MAX(x.count, y.count);
    for (NSUInteger i = 0; i < n; i++) {
        NSInteger xi = i < x.count ? x[i].integerValue : 0;
        NSInteger yi = i < y.count ? y[i].integerValue : 0;
        if (xi != yi) return xi > yi ? 1 : -1;
    }
    return 0;
}

#pragma mark - 筛选判定

static BOOL ZZPassesRegionVersion(NSDictionary *item) {
    if (!item) return NO;
    NSUserDefaults *ud = [NSUserDefaults standardUserDefaults];
    NSString *region = [ud stringForKey:kRegionKey];
    NSString *vmin   = [ud stringForKey:kVerMinKey];
    NSString *vmax   = [ud stringForKey:kVerMaxKey];

    if (region.length && ![region isEqualToString:@"不限"]) {
        NSMutableString *hay = [NSMutableString string];
        for (NSString *k in @[ @"title", @"appearance", @"storage", @"charge", @"sysVer" ]) {
            if (item[k]) [hay appendFormat:@" %@", item[k]];
        }
        if (![hay containsString:region]) return NO;
    }

    NSString *sv = item[@"sysVer"];
    if (sv.length) {
        if (vmin.length && ZZVerCmp(sv, vmin) < 0) return NO;
        if (vmax.length && ZZVerCmp(sv, vmax) > 0) return NO;
    }
    return YES;
}

static BOOL ZZAnyRegionVersionFilter(void) {
    NSUserDefaults *ud = [NSUserDefaults standardUserDefaults];
    NSString *region = [ud stringForKey:kRegionKey];
    NSString *vmin   = [ud stringForKey:kVerMinKey];
    NSString *vmax   = [ud stringForKey:kVerMaxKey];
    return (vmin.length || vmax.length ||
            (region.length && ![region isEqualToString:@"不限"]));
}

static NSString *ZZRegionVersionTitle(void) {
    NSUserDefaults *ud = [NSUserDefaults standardUserDefaults];
    NSString *region = [ud stringForKey:kRegionKey];
    NSString *vmin   = [ud stringForKey:kVerMinKey];
    NSString *vmax   = [ud stringForKey:kVerMaxKey];

    NSMutableArray *bits = [NSMutableArray array];
    if (vmin.length || vmax.length) {
        [bits addObject:[NSString stringWithFormat:@"%@~%@",
                         vmin.length ? vmin : @"不限",
                         vmax.length ? vmax : @"不限"]];
    }
    if (region.length && ![region isEqualToString:@"不限"]) [bits addObject:region];
    return bits.count ? [bits componentsJoinedByString:@" "] : @"版本地区";
}

#pragma mark - 收藏存储

@interface ZZFavStore : NSObject
+ (instancetype)shared;
- (NSArray<NSDictionary *> *)all;
- (BOOL)contains:(NSDictionary *)item;
- (BOOL)toggle:(NSDictionary *)item;   // 返回收藏后是否处于已收藏
- (void)remove:(NSDictionary *)item;
@end

@implementation ZZFavStore {
    NSMutableArray<NSDictionary *> *_cache;
}

+ (instancetype)shared {
    static ZZFavStore *s = nil;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ s = [ZZFavStore new]; });
    return s;
}

- (instancetype)init {
    if ((self = [super init])) {
        NSArray *raw = [[NSUserDefaults standardUserDefaults] arrayForKey:kFavKey];
        _cache = [raw isKindOfClass:[NSArray class]] ? [raw mutableCopy]
                                                     : [NSMutableArray array];
    }
    return self;
}

- (void)flush {
    [[NSUserDefaults standardUserDefaults] setObject:_cache forKey:kFavKey];
    [[NSUserDefaults standardUserDefaults] synchronize];
}

- (NSArray<NSDictionary *> *)all { return [_cache copy]; }

- (NSInteger)indexOf:(NSDictionary *)item {
    NSString *iid = item[@"infoId"];
    NSString *ttl = item[@"title"];
    for (NSInteger i = 0; i < (NSInteger)_cache.count; i++) {
        NSDictionary *d = _cache[i];
        if (iid.length && [ZZStr(d[@"infoId"]) isEqualToString:iid]) return i;
        if (!iid.length && ttl.length && [ZZStr(d[@"title"]) isEqualToString:ttl]) return i;
    }
    return -1;
}

- (BOOL)contains:(NSDictionary *)item {
    return item ? [self indexOf:item] >= 0 : NO;
}

- (BOOL)toggle:(NSDictionary *)item {
    if (!item) return NO;
    NSInteger i = [self indexOf:item];
    if (i >= 0) {
        [_cache removeObjectAtIndex:i];
        [self flush];
        return NO;
    }
    NSMutableDictionary *d = [item mutableCopy];
    d[@"savedAt"] = @([[NSDate date] timeIntervalSince1970]);
    [_cache insertObject:d atIndex:0];
    [self flush];
    return YES;
}

- (void)remove:(NSDictionary *)item {
    NSInteger i = [self indexOf:item];
    if (i < 0) return;
    [_cache removeObjectAtIndex:i];
    [self flush];
}

@end

#pragma mark - 轻提示 / 顶部控制器

static void ZZToast(UIView *host, NSString *text) {
    if (!text.length) return;
    UIWindow *win = host.window;
    if (!win) {
        for (UIScene *sc in UIApplication.sharedApplication.connectedScenes) {
            if (![sc isKindOfClass:[UIWindowScene class]]) continue;
            for (UIWindow *w in ((UIWindowScene *)sc).windows) {
                if (w.isKeyWindow) { win = w; break; }
            }
            if (win) break;
        }
    }
    if (!win) return;

    UILabel *l = [UILabel new];
    l.text = text;
    l.font = [UIFont boldSystemFontOfSize:14];
    l.textColor = UIColor.whiteColor;
    l.backgroundColor = [UIColor colorWithWhite:0 alpha:0.82];
    l.textAlignment = NSTextAlignmentCenter;
    l.numberOfLines = 0;
    l.layer.cornerRadius = 10;
    l.clipsToBounds = YES;
    l.alpha = 0;
    CGSize sz = [text boundingRectWithSize:CGSizeMake(win.bounds.size.width - 80, 200)
                                   options:NSStringDrawingUsesLineFragmentOrigin
                                attributes:@{ NSFontAttributeName: l.font }
                                   context:nil].size;
    l.frame = CGRectMake(0, 0, sz.width + 32, sz.height + 20);
    l.center = CGPointMake(win.bounds.size.width / 2, win.bounds.size.height - 130);
    [win addSubview:l];
    [UIView animateWithDuration:0.18 animations:^{ l.alpha = 1; }
                     completion:^(BOOL ok) {
        [UIView animateWithDuration:0.25 delay:1.1 options:0 animations:^{
            l.alpha = 0;
        } completion:^(BOOL done) { [l removeFromSuperview]; }];
    }];
}

static UIViewController *ZZTopViewController(void) {
    UIWindow *key = nil;
    for (UIScene *sc in UIApplication.sharedApplication.connectedScenes) {
        if (![sc isKindOfClass:[UIWindowScene class]]) continue;
        for (UIWindow *w in ((UIWindowScene *)sc).windows) {
            if (w.isKeyWindow) { key = w; break; }
        }
        if (key) break;
    }
    UIViewController *vc = key.rootViewController;
    while (vc.presentedViewController) vc = vc.presentedViewController;
    return vc;
}

#pragma mark - ZZFloat 前置声明（供后续辅助函数使用）

// 这些成员/方法名全部来自对 转转找鸡 dylib 符号表的分析，不是猜测：
//   ivar   _win _panel _titleLabel _table _shown
//          _modelBtn _batteryBtn _verBtn _conditionBtn _storageBtn
//   方法   +shared(0x6c70) -buildPanel(0x7cd8) -refilter(0xbc7c)
//          -filterButton:x:y:w:sel:(0x8b34) -copyLink:(0xd354)
//          -tableView:cellForRowAtIndexPath:(0xc8a0)
@interface ZZFloat : NSObject
+ (instancetype)shared;
@property (nonatomic, strong) UIView *win;
@property (nonatomic, strong) UIView *panel;
@property (nonatomic, strong) UILabel *titleLabel;
@property (nonatomic, strong) UITableView *table;
@property (nonatomic, strong) NSArray *shown;
@property (nonatomic, strong) UIButton *modelBtn;
@property (nonatomic, strong) UIButton *batteryBtn;
@property (nonatomic, strong) UIButton *verBtn;
@property (nonatomic, strong) UIButton *conditionBtn;
@property (nonatomic, strong) UIButton *storageBtn;
- (void)buildPanel;
- (void)refilter;
- (void)copyLink:(id)sender;
- (UIButton *)filterButton:(CGFloat)x y:(CGFloat)y w:(CGFloat)w sel:(SEL)sel;
// 本桥接层新增
- (void)zzOpenRegionVersion:(id)sender;
- (void)zzOpenFavorites:(id)sender;
- (void)zzFavoriteTapped:(UIButton *)sender;
@end

#pragma mark - 「版本地区」控制器

@interface ZZRegionVersionVC : UITableViewController
@end

@implementation ZZRegionVersionVC

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"版本 / 地区";
    self.navigationItem.rightBarButtonItem =
        [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone
                                                     target:self
                                                     action:@selector(zzDone)];
    self.navigationItem.leftBarButtonItem =
        [[UIBarButtonItem alloc] initWithTitle:@"重置"
                                         style:UIBarButtonItemStylePlain
                                        target:self
                                        action:@selector(zzReset)];
}

- (void)zzDone { [self dismissViewControllerAnimated:YES completion:nil]; }

- (void)zzReset {
    NSUserDefaults *ud = [NSUserDefaults standardUserDefaults];
    [ud removeObjectForKey:kRegionKey];
    [ud removeObjectForKey:kVerMinKey];
    [ud removeObjectForKey:kVerMaxKey];
    [ud synchronize];
    [self.tableView reloadData];
    [[NSNotificationCenter defaultCenter] postNotificationName:kChangedNote object:nil];
}

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tv { return 2; }

- (NSInteger)tableView:(UITableView *)tv numberOfRowsInSection:(NSInteger)s {
    return s == 0 ? 1 : (NSInteger)ZZRegionChoices().count;
}

- (NSString *)tableView:(UITableView *)tv titleForHeaderInSection:(NSInteger)s {
    return s == 0 ? @"系统版本区间（留空 = 不限）" : @"地区";
}

- (UITableViewCell *)tableView:(UITableView *)tv cellForRowAtIndexPath:(NSIndexPath *)ip {
    UITableViewCell *c = [tv dequeueReusableCellWithIdentifier:@"zzrv"];
    if (!c) c = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleValue1
                                     reuseIdentifier:@"zzrv"];
    NSUserDefaults *ud = [NSUserDefaults standardUserDefaults];

    if (ip.section == 0) {
        NSString *lo = [ud stringForKey:kVerMinKey] ?: @"";
        NSString *hi = [ud stringForKey:kVerMaxKey] ?: @"";
        c.textLabel.text = @"设置版本区间";
        c.detailTextLabel.text = [NSString stringWithFormat:@"%@ ~ %@",
                                  lo.length ? lo : @"不限",
                                  hi.length ? hi : @"不限"];
        c.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
    } else {
        NSString *cur  = [ud stringForKey:kRegionKey] ?: @"不限";
        NSString *name = ZZRegionChoices()[(NSUInteger)ip.row];
        c.textLabel.text = name;
        c.detailTextLabel.text = nil;
        c.accessoryType = [cur isEqualToString:name] ? UITableViewCellAccessoryCheckmark
                                                     : UITableViewCellAccessoryNone;
    }
    return c;
}

- (void)tableView:(UITableView *)tv didSelectRowAtIndexPath:(NSIndexPath *)ip {
    [tv deselectRowAtIndexPath:ip animated:YES];

    if (ip.section == 1) {
        [[NSUserDefaults standardUserDefaults] setObject:ZZRegionChoices()[(NSUInteger)ip.row]
                                                  forKey:kRegionKey];
        [[NSUserDefaults standardUserDefaults] synchronize];
        [tv reloadData];
        [[NSNotificationCenter defaultCenter] postNotificationName:kChangedNote object:nil];
        return;
    }

    NSUserDefaults *ud = [NSUserDefaults standardUserDefaults];
    UIAlertController *ac =
        [UIAlertController alertControllerWithTitle:@"系统版本区间"
                                            message:@"例如 15.0 到 17.2，留空表示不限"
                                     preferredStyle:UIAlertControllerStyleAlert];
    [ac addTextFieldWithConfigurationHandler:^(UITextField *tf) {
        tf.placeholder  = @"最低版本（如 15.0）";
        tf.keyboardType = UIKeyboardTypeDecimalPad;
        tf.text         = [ud stringForKey:kVerMinKey];
    }];
    [ac addTextFieldWithConfigurationHandler:^(UITextField *tf) {
        tf.placeholder  = @"最高版本（如 17.2）";
        tf.keyboardType = UIKeyboardTypeDecimalPad;
        tf.text         = [ud stringForKey:kVerMaxKey];
    }];
    [ac addAction:[UIAlertAction actionWithTitle:@"取消"
                                           style:UIAlertActionStyleCancel
                                         handler:nil]];
    __weak typeof(self) weakSelf = self;
    [ac addAction:[UIAlertAction actionWithTitle:@"确定"
                                           style:UIAlertActionStyleDefault
                                         handler:^(UIAlertAction *a) {
        NSString *lo = [ac.textFields[0].text
            stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        NSString *hi = [ac.textFields[1].text
            stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        if (lo.length) [ud setObject:lo forKey:kVerMinKey];
        else           [ud removeObjectForKey:kVerMinKey];
        if (hi.length) [ud setObject:hi forKey:kVerMaxKey];
        else           [ud removeObjectForKey:kVerMaxKey];
        [ud synchronize];
        [weakSelf.tableView reloadData];
        [[NSNotificationCenter defaultCenter] postNotificationName:kChangedNote object:nil];
    }]];
    [self presentViewController:ac animated:YES completion:nil];
}

@end

#pragma mark - 「我的收藏」控制器

@interface ZZFavoritesVC : UITableViewController
@end

@implementation ZZFavoritesVC

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"我的收藏";
    self.navigationItem.rightBarButtonItem =
        [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone
                                                     target:self
                                                     action:@selector(zzDone)];
}

- (void)zzDone { [self dismissViewControllerAnimated:YES completion:nil]; }

- (NSArray<NSDictionary *> *)rows {
    NSMutableArray *out = [NSMutableArray array];
    for (NSDictionary *d in [ZZFavStore shared].all) {
        if (ZZPassesRegionVersion(d)) [out addObject:d];
    }
    return out;
}

- (NSInteger)tableView:(UITableView *)tv numberOfRowsInSection:(NSInteger)s {
    return (NSInteger)[self rows].count;
}

- (UITableViewCell *)tableView:(UITableView *)tv cellForRowAtIndexPath:(NSIndexPath *)ip {
    UITableViewCell *c = [tv dequeueReusableCellWithIdentifier:@"zzfav"];
    if (!c) c = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle
                                     reuseIdentifier:@"zzfav"];
    NSDictionary *d = [self rows][(NSUInteger)ip.row];
    c.textLabel.text = ZZStr(d[@"title"]) ?: ZZStr(d[@"infoId"]) ?: @"(无标题)";
    c.textLabel.numberOfLines = 2;
    NSMutableArray *bits = [NSMutableArray array];
    if (d[@"price"])   [bits addObject:[NSString stringWithFormat:@"¥%@", d[@"price"]]];
    if (d[@"sysVer"])  [bits addObject:[NSString stringWithFormat:@"系统%@", d[@"sysVer"]]];
    if (d[@"storage"]) [bits addObject:ZZStr(d[@"storage"])];
    if (d[@"charge"])  [bits addObject:ZZStr(d[@"charge"])];
    c.detailTextLabel.text = [bits componentsJoinedByString:@"  "];
    return c;
}

- (void)tableView:(UITableView *)tv didSelectRowAtIndexPath:(NSIndexPath *)ip {
    [tv deselectRowAtIndexPath:ip animated:YES];
    NSDictionary *d = [self rows][(NSUInteger)ip.row];
    NSString *url = ZZStr(d[@"jumpUrl"]);
    if (!url.length) { ZZToast(tv, @"这条没有可用的链接"); return; }
    UIPasteboard.generalPasteboard.string = url;
    ZZToast(tv, @"链接已复制");
}

- (UISwipeActionsConfiguration *)tableView:(UITableView *)tv
    trailingSwipeActionsConfigurationForRowAtIndexPath:(NSIndexPath *)ip {
    __weak typeof(self) weakSelf = self;
    UIView *host = tv;
    UIContextualAction *del = [UIContextualAction
        contextualActionWithStyle:UIContextualActionStyleDestructive
                            title:@"删除"
                          handler:^(UIContextualAction *a, UIView *v, void (^done)(BOOL)) {
        NSArray *rows = [weakSelf rows];
        if (ip.row < (NSInteger)rows.count) {
            [[ZZFavStore shared] remove:rows[(NSUInteger)ip.row]];
        }
        [tv reloadData];
        done(YES);
    }];
    (void)host;
    return [UISwipeActionsConfiguration configurationWithActions:@[ del ]];
}

@end

#pragma mark - 结果 cell 上的「收藏」按钮

/// 收集 view 里所有按钮（递归）
static NSArray<UIButton *> *ZZButtonsInView(UIView *v) {
    NSMutableArray<UIButton *> *out = [NSMutableArray array];
    for (UIView *sub in v.subviews) {
        if ([sub isKindOfClass:[UIButton class]]) [out addObject:(UIButton *)sub];
        [out addObjectsFromArray:ZZButtonsInView(sub)];
    }
    return out;
}

/// 找出「复制链接」按钮：
///   1) 标题 / 无障碍标签含「复制」或「链接」
///   2) 该按钮的 action 就是 copyLink:（找鸡的复制链接方法名，见符号表 0xd354）
///   3) 都没有则返回 nil，由调用方退化为「最下方那个按钮的下面」
static UIButton *ZZFindCopyLinkButton(UIView *cell) {
    NSArray<UIButton *> *btns = ZZButtonsInView(cell);
    for (UIButton *b in btns) {
        NSString *t = b.currentTitle ?: b.titleLabel.text ?: @"";
        if ([t containsString:@"复制"] || [t containsString:@"链接"]) return b;
    }
    for (UIButton *b in btns) {
        NSString *al = b.accessibilityLabel ?: @"";
        if ([al containsString:@"复制"] || [al containsString:@"链接"]) return b;
    }
    // 通过 target/action 反查（copyLink: 是找鸡的复制方法）
    for (UIButton *b in btns) {
        for (id target in b.allTargets) {
            NSArray<NSString *> *acts =
                [b actionsForTarget:target forControlEvent:UIControlEventTouchUpInside];
            for (NSString *a in acts) {
                if ([a containsString:@"copyLink"] || [a containsString:@"copy"]) return b;
            }
        }
    }
    return nil;
}

/// 在 cell 上安装「收藏」按钮（幂等；已存在则只刷新标题）
static void ZZInstallFavoriteButton(UITableViewCell *cell, NSDictionary *snap) {
    if (!cell) return;
    const void *btnKey  = ZZKey("zzFavButton");
    const void *snapKey = ZZKey("zzFavSnapshot");

    UIButton *exist = objc_getAssociatedObject(cell, btnKey);
    if (exist) {
        BOOL fav = [[ZZFavStore shared] contains:snap];
        [exist setTitle:fav ? @"★ 已收藏" : @"☆ 收藏" forState:UIControlStateNormal];
        return;
    }

    NSArray<UIButton *> *btns = ZZButtonsInView(cell.contentView);
    if (!btns.count) return;

    UIButton *copyBtn = ZZFindCopyLinkButton(cell.contentView);
    UIButton *anchor  = copyBtn ?: btns.lastObject;
    if (!anchor) return;

    UIButton *fav = [UIButton buttonWithType:UIButtonTypeSystem];
    BOOL isFav = [[ZZFavStore shared] contains:snap];
    [fav setTitle:isFav ? @"★ 已收藏" : @"☆ 收藏" forState:UIControlStateNormal];
    fav.titleLabel.font = anchor.titleLabel.font ?: [UIFont boldSystemFontOfSize:12];
    [fav setTitleColor:(anchor.currentTitleColor ?: UIColor.systemBlueColor)
              forState:UIControlStateNormal];
    fav.backgroundColor  = anchor.backgroundColor;
    fav.layer.cornerRadius = anchor.layer.cornerRadius;
    fav.clipsToBounds    = YES;

    // 定位：优先放「复制链接」正下方；若已贴底则放其右侧
    CGRect af  = anchor.frame;
    CGFloat w  = MAX(64.0, af.size.width);
    CGFloat h  = af.size.height > 0 ? af.size.height : 28.0;
    CGFloat ny = CGRectGetMaxY(af) + 2.0;
    if (ny + h > cell.contentView.bounds.size.height - 1.0) {
        fav.frame = CGRectMake(CGRectGetMaxX(af) + 4.0, af.origin.y, w, h);
    } else {
        fav.frame = CGRectMake(af.origin.x, ny, w, h);
    }
    [cell.contentView addSubview:fav];

    objc_setAssociatedObject(cell, btnKey,  fav,  OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(cell, snapKey, snap, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    ZMLOG(@"收藏按钮已插入 cell=%@ frame=%@ anchor=%@",
          NSStringFromClass(cell.class), NSStringFromCGRect(fav.frame), anchor.currentTitle);
}

static NSDictionary *ZZSnapshotForCell(UITableViewCell *cell) {
    return objc_getAssociatedObject(cell, ZZKey("zzFavSnapshot"));
}

#pragma mark - 过滤快照（行数与 cell 绑定共用同一份数据）

/// 当前筛选条件的签名字符串，用于判断缓存是否失效
static NSString *ZZFilterSignature(void) {
    NSUserDefaults *ud = [NSUserDefaults standardUserDefaults];
    return [NSString stringWithFormat:@"%@|%@|%@",
            [ud stringForKey:kVerMinKey] ?: @"",
            [ud stringForKey:kVerMaxKey] ?: @"",
            [ud stringForKey:kRegionKey] ?: @""];
}

/// 取「当前筛选条件下应该显示的商品快照数组」。
/// 未开启版本/地区筛选时返回 nil，表示完全交给找鸡自己的逻辑。
static NSArray<NSDictionary *> *ZZFilteredSnapshots(id zzfloat) {
    if (!ZZAnyRegionVersionFilter()) return nil;
    if (!zzfloat) return @[];

    static const void *kSnapKey = "zzFilteredSnapshots";
    static const void *kSigKey  = "zzFilteredSignature";

    NSString *sig = ZZFilterSignature();
    NSString *cachedSig = objc_getAssociatedObject(zzfloat, kSigKey);
    NSArray *cached = objc_getAssociatedObject(zzfloat, kSnapKey);
    if (cached && [cachedSig isEqualToString:sig]) return cached;

    NSArray *shown = ZZSafeGet(zzfloat, @"shown");
    NSMutableArray<NSDictionary *> *out = [NSMutableArray array];
    if ([shown isKindOfClass:[NSArray class]]) {
        for (id it in shown) {
            NSDictionary *s = ZZItemSnapshot(it);
            if (s && ZZPassesRegionVersion(s)) [out addObject:s];
        }
    }
    objc_setAssociatedObject(zzfloat, kSnapKey, out, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(zzfloat, kSigKey, sig, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    ZMLOG(@"过滤快照重建: %lu -> %lu (sig=%@)",
          (unsigned long)([shown isKindOfClass:[NSArray class]] ? shown.count : 0),
          (unsigned long)out.count, sig);
    return out;
}

#pragma mark - Hooks

%hook ZZFloat

// ---- 「版本地区」按钮插入 ----
- (void)buildPanel {
    %orig;

    ZMLOG(@"buildPanel 触发，开始注入");

    UIView *panel = ZZSafeGet(self, @"panel");
    if (![panel isKindOfClass:[UIView class]]) {
        id win = ZZSafeGet(self, @"win");
        panel = ZZSafeGet(win, @"panel");
    }
    if (![panel isKindOfClass:[UIView class]]) {
        ZMLOG(@"找不到 panel，跳过注入");
        return;
    }

    // 找鸡的 5 个筛选按钮，按 ivar 名收集
    NSMutableArray<UIButton *> *btns = [NSMutableArray array];
    for (NSString *key in @[ @"modelBtn", @"batteryBtn", @"verBtn",
                             @"conditionBtn", @"storageBtn" ]) {
        id b = ZZSafeGet(self, key);
        if ([b isKindOfClass:[UIButton class]]) [btns addObject:b];
    }
    if (btns.count < 2) {
        ZMLOG(@"筛选按钮不足(%lu)，跳过", (unsigned long)btns.count);
        return;
    }
    [btns sortUsingComparator:^NSComparisonResult(UIButton *a, UIButton *b) {
        return a.frame.origin.x < b.frame.origin.x ? NSOrderedAscending
                                                   : NSOrderedDescending;
    }];

    CGFloat step = btns[1].frame.origin.x - btns[0].frame.origin.x;
    if (step <= 0) step = panel.bounds.size.width / 6.0;
    CGFloat y = btns[0].frame.origin.y;
    CGFloat h = btns[0].frame.size.height;
    CGFloat w = btns[0].frame.size.width > 0 ? btns[0].frame.size.width
                                             : MAX(58.0, step - 6.0);

    // 插入点 = 「成色」右侧一格
    UIButton *conditionBtn = ZZSafeGet(self, @"conditionBtn");
    CGFloat insertX = [conditionBtn isKindOfClass:[UIButton class]]
                          ? conditionBtn.frame.origin.x + step
                          : btns.lastObject.frame.origin.x + step;

    // 把插入点及其右侧的按钮整体右移一格，腾出位置
    for (UIButton *b in btns) {
        if (b.frame.origin.x >= insertX - 1.0) {
            CGRect f = b.frame;
            f.origin.x += step;
            b.frame = f;
        }
    }

    // 优先复用找鸡自己的工厂方法，保证样式一致
    UIButton *rvBtn = nil;
    SEL factory = NSSelectorFromString(@"filterButton:x:y:w:sel:");
    if ([self respondsToSelector:factory]) {
        rvBtn = ((id (*)(id, SEL, CGFloat, CGFloat, CGFloat, SEL))objc_msgSend)(
            self, factory, insertX, y, w, @selector(zzOpenRegionVersion:));
    }
    if ([rvBtn isKindOfClass:[UIButton class]]) {
        [rvBtn addTarget:self
                  action:@selector(zzOpenRegionVersion:)
        forControlEvents:UIControlEventTouchUpInside];
    } else {
        rvBtn = [UIButton buttonWithType:UIButtonTypeSystem];
        rvBtn.frame = CGRectMake(insertX, y, w, h > 0 ? h : 32.0);
        rvBtn.titleLabel.font = [UIFont boldSystemFontOfSize:12];
        [rvBtn setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
        rvBtn.backgroundColor = [UIColor colorWithWhite:1 alpha:0.14];
        rvBtn.layer.cornerRadius = 6;
        rvBtn.clipsToBounds = YES;
        [rvBtn addTarget:self
                  action:@selector(zzOpenRegionVersion:)
        forControlEvents:UIControlEventTouchUpInside];
    }
    [rvBtn setTitle:ZZRegionVersionTitle() forState:UIControlStateNormal];

    // 短标题时缩放字号，避免「15.0~17.2 北京」被截断
    rvBtn.titleLabel.adjustsFontSizeToFitWidth = YES;
    rvBtn.titleLabel.minimumScaleFactor = 0.6;
    rvBtn.titleLabel.numberOfLines = 2;
    rvBtn.titleLabel.textAlignment = NSTextAlignmentCenter;

    [panel addSubview:rvBtn];
    objc_setAssociatedObject(self, ZZKey("zzRVButton"), rvBtn,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    ZMLOG(@"「版本地区」按钮插入完成 x=%.1f y=%.1f w=%.1f step=%.1f",
          insertX, y, w, step);

    // ---- 「我的收藏」入口：面板右上角 ----
    UILabel *titleLabel = ZZSafeGet(self, @"titleLabel");
    UIButton *favBtn = [UIButton buttonWithType:UIButtonTypeSystem];
    [favBtn setTitle:@"我的收藏" forState:UIControlStateNormal];
    favBtn.titleLabel.font = [UIFont boldSystemFontOfSize:13];
    [favBtn setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    CGFloat tw = 76.0, th = 30.0;
    if ([titleLabel isKindOfClass:[UILabel class]]) {
        CGRect tf = titleLabel.frame;
        favBtn.frame = CGRectMake(panel.bounds.size.width - tw - 10.0,
                                  tf.origin.y + (tf.size.height - th) / 2.0, tw, th);
    } else {
        favBtn.frame = CGRectMake(panel.bounds.size.width - tw - 10.0, 8.0, tw, th);
    }
    [favBtn addTarget:self
               action:@selector(zzOpenFavorites:)
     forControlEvents:UIControlEventTouchUpInside];
    [panel addSubview:favBtn];
    objc_setAssociatedObject(self, ZZKey("zzFavEntry"), favBtn,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    ZMLOG(@"「我的收藏」入口插入完成 %@", NSStringFromCGRect(favBtn.frame));
}

- (void)zzOpenRegionVersion:(id)sender {
    ZZRegionVersionVC *vc = [ZZRegionVersionVC new];
    UINavigationController *nav =
        [[UINavigationController alloc] initWithRootViewController:vc];
    nav.modalPresentationStyle = UIModalPresentationPageSheet;
    [ZZTopViewController() presentViewController:nav animated:YES completion:nil];
}

- (void)zzOpenFavorites:(id)sender {
    ZZFavoritesVC *vc = [ZZFavoritesVC new];
    UINavigationController *nav =
        [[UINavigationController alloc] initWithRootViewController:vc];
    nav.modalPresentationStyle = UIModalPresentationPageSheet;
    [ZZTopViewController() presentViewController:nav animated:YES completion:nil];
}

// ---- 筛选变化后刷新 ----
- (void)refilter {
    %orig;
    UITableView *tv = ZZSafeGet(self, @"table");
    if ([tv isKindOfClass:[UITableView class]] && tv.dataSource == self) {
        [tv reloadData];
    }
}

// ---- 行数：叠加「版本地区」这一层过滤 ----
- (NSInteger)tableView:(UITableView *)tv numberOfRowsInSection:(NSInteger)section {
    if ([tv isKindOfClass:[UITableView class]] && tv.dataSource == self) {
        NSArray<NSDictionary *> *pass = ZZFilteredSnapshots(self);
        if (pass) return (NSInteger)pass.count;
    }
    return %orig;
}

// ---- 造 cell：绑定商品快照 + 插入收藏按钮 ----
- (UITableViewCell *)tableView:(UITableView *)tv cellForRowAtIndexPath:(NSIndexPath *)ip {
    UITableViewCell *cell = %orig;
    if (!cell) return cell;

    NSDictionary *snap = nil;
    NSArray<NSDictionary *> *pass = ZZFilteredSnapshots(self);
    if (pass) {
        if (ip.row < (NSInteger)pass.count) snap = pass[(NSUInteger)ip.row];
    } else {
        NSArray *shown = ZZSafeGet(self, @"shown");
        if ([shown isKindOfClass:[NSArray class]] && ip.row < (NSInteger)shown.count) {
            snap = ZZItemSnapshot(shown[(NSUInteger)ip.row]);
        }
    }
    if (!snap) return cell;

    objc_setAssociatedObject(cell, ZZKey("zzFavSnapshot"), snap,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    ZZInstallFavoriteButton(cell, snap);
    return cell;
}

// ---- 收藏按钮点击 ----
- (void)zzFavoriteTapped:(UIButton *)sender {
    // 从 sender 所在 cell 取快照
    UIView *v = sender;
    while (v && ![v isKindOfClass:[UITableViewCell class]]) v = v.superview;
    NSDictionary *snap = ZZSnapshotForCell((UITableViewCell *)v);
    if (!snap) { ZZToast(sender, @"没取到商品信息"); return; }
    BOOL now = [[ZZFavStore shared] toggle:snap];
    [sender setTitle:now ? @"★ 已收藏" : @"☆ 收藏" forState:UIControlStateNormal];
    ZZToast(sender, now ? @"已加入收藏" : @"已取消收藏");
}

%end

#pragma mark - 初始化

%ctor {
    ZMLOG(@"ZZMergeBridge 已加载 (bundle=%@)", NSBundle.mainBundle.bundleIdentifier);

    [[NSNotificationCenter defaultCenter]
        addObserverForName:kChangedNote
                    object:nil
                     queue:[NSOperationQueue mainQueue]
                usingBlock:^(NSNotification *n) {
        Class zf = objc_getClass("ZZFloat");
        if (!zf) {
            ZMLOG(@"ZZFloat 未找到，找鸡可能未安装");
            return;
        }
        id shared = ZZSafeGet((id)zf, @"shared");
        if (!shared) return;

        UIButton *btn = objc_getAssociatedObject(shared, ZZKey("zzRVButton"));
        if ([btn isKindOfClass:[UIButton class]]) {
            [btn setTitle:ZZRegionVersionTitle() forState:UIControlStateNormal];
        }
        id tv = ZZSafeGet(shared, @"table");
        if ([tv isKindOfClass:[UITableView class]]) [tv reloadData];
        ZMLOG(@"筛选已更新 -> %@", ZZRegionVersionTitle());
    }];
}
