-- My TV PostgreSQL CU 降耗（2026-09-09）
-- 幂等，可重复执行。配套：hotupdate 云函数公告/热更查询缓存、客户端前台轮询门控。

-- 公告公开接口的核心查询：where status='published' order by id desc limit 1。
create index if not exists idx_announcements_status_id
  on public.announcements (status, id desc);

-- 后台总览统计最近 24 小时激活量、日志页按时间倒序读取。
create index if not exists idx_activate_log_at
  on public.activate_log (at desc);

-- 卡密管理默认按最近操作排序，旧库只有 code 主键，会反复全表排序。
create index if not exists idx_licenses_updated_at
  on public.licenses (updated_at desc);
create index if not exists idx_licenses_created_at
  on public.licenses (created_at desc);

-- 热更新检查按状态过滤并取最高版本。
create index if not exists idx_hotupdate_pkg_status_version
  on public.hotupdate_pkg (status, hot_version_code desc);

analyze public.announcements;
analyze public.activate_log;
analyze public.licenses;
analyze public.hotupdate_pkg;
analyze public.hotupdate_log;
