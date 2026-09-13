# 文档导航

- [项目文档](项目文档.md)：架构、模块、构建和运维边界。
- [版本史](版本史.md)：按日期追加的功能变更。
- [测试记录](测试记录.md)：自动化与真机/模拟器验收证据。
- [本轮设计](superpowers/specs/2026-09-12-football-live-player-hotupdate-flash-design.md)：足球、播放器和热更新快闪设计。
- [本轮实施计划](superpowers/plans/2026-09-13-football-player-startup-release.md)：分任务实施与验证清单。

当前发布方式以本机 Git/构建为准；设备端运行内置 Python 后端并直接访问公网内容及播放源，不依赖自建业务服务器。后端与 Web 资源可静默热更新，原生 Compose 代码变化必须发布签名 APK。
