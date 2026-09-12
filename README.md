# My TV（OptimalTV 工程）

Android 原生影视应用（TV 大屏 + 手机/平板双端）+ 云端网页版。Kotlin + Jetpack Compose + Media3，
tvOS 深色风格；Python 后端内嵌进 app（Chaquopy），设备端自给自足。商业化 = 卡密付费（公测版）。

> 📋 **详细项目信息**（架构/模块/云端/部署/运维/版本史入口）全部在 **[docs/项目文档.md](docs/项目文档.md)**，
> 本 README 只做结构介绍与快速上手。

## 快速使用

| 我想… | 怎么做 |
|---|---|
| 用网页版 | 手机浏览器打开 https://appletv-d5ge1bth794873f76.service.tcloudbase.com/web/ （首次「风险提醒」点确定即过） |
| 进后台管理 | https://appletv-d5ge1bth794873f76.service.tcloudbase.com/admin/ · 账号 `admin`，密码 = otv-admin 函数环境变量 `OTV_ADMIN_PASS` |
| 前后端一起发 | `python tools/release_all.py`（云端 /web/ 即时生效 + App 热更 zip 含 www 前端）→ 后台「热更新」页点**「上传最新版本」**（首次点击选 zip 输出目录，之后一键直传；版本号系统自动分配）→ 选发布方式 |
| 发新 APK | `android/` 或 `internal/mobile/` 下 `./gradlew assembleRelease`（v1.19 起双 flavor 退役，单线发布），产物自动归档到 `apk/` |
| 签发卡密 | `python tools/license_gen.py gen --plan <套餐> --count <数量>` → `python tools/db_import.py out/<批次>` |
| 验证改动 | MuMu 模拟器实测（截图 + logcat tag `OTV`），记录进 `docs/测试记录.md`；网页版改动**必须浏览器实测** |

## 目录结构

```
My TV/
├── android/                  # TV 版工程（Kotlin + Compose TV）
│   └── app/src/main/
│       ├── java/com/qiubo/optimaltv/
│       │   ├── data/         # 数据层：repo（直播/点播/IPTV）、source、db(Room)、prefs；UrlGuard 双层 SSRF 防护
│       │   ├── playback/     # 播放层：引擎调度、解密中继、VlcEngine 兜底
│       │   ├── license/      # 卡密激活/本地验签/离线授权
│       │   ├── hotupdate/    # HotUpdateManager 热更下载与坏包防护
│       │   ├── ui/           # 界面：home/all/detail/search/live/tv/player/paywall…
│       │   │                 #   （OtvNav 焦点引擎在 components/Focus.kt）
│       │   └── App.kt / MainActivity.kt / EmbeddedBackend.kt   # 启动门闸、内嵌后端管理
│       ├── assets/           # python-backend.zip（内嵌后端=热更对象）、iptv_curated.m3u、logos/、拼音词典
│       ├── python/           # Chaquopy Python 源码（proxy.py 后端、scraper 等）
│       └── cpp/pinyinime/    # AOSP 谷歌拼音解码器（搜索页拼音候选）
├── internal/mobile/          # 移动版工程（触屏；data/playback/license 与 TV 版字节级一致，sync_shared.py 监管）
├── cloudfunctions/           # CloudBase 云函数（部署包）
│   ├── activate/             # 卡密激活
│   ├── hotupdate/            # 热更 check/report + 公告下发
│   ├── iptv-rebuild/         # 电视源每日 06:30 自动推流
│   ├── otv-admin/            # 后台管理（源码在 tools/，构建脚本打包过来）
│   └── otv-web/              # 网页版（含 www/ 前端；源码 tools/backend-src/）
├── tools/                    # 构建/运维脚本 + 后台 UI 源码（admin.html/admin_server.py）+ SQL 迁移
├── docs/
│   ├── 项目文档.md           # ★ 唯一详细项目文档（架构/模块/云端/部署/运维/安全）
│   ├── 版本史.md             # 逐版本变更流水（追加式）
│   └── 测试记录.md           # MuMu 验收记录流水（追加式）
└── apk/                      # 构建产物（TV版/ 移动版/ 归档-旧版/）
```

## 三条铁律

1. **改动默认同步所有版本**（TV + 移动 + 网页版，共享层跑 `tools/sync_shared.py`，改 proxy.py 需双构建重部署）——除非明确说只改某端。
2. **私钥与凭据不出本机**（`tools/keys/`、codes.csv 不进 git、不进云、不贴会话）。
3. **两工程不要并行构建**（构建目录虽已分治，历史教训仍在）。

## 当前版本

TV / 移动 APK **v1.24**（versionCode 26）· 网页版 **v1.25** · 热更 **v10**（已发布）。逐版本变更与实测证据见
`docs/版本史.md` 与 `docs/测试记录.md`。
