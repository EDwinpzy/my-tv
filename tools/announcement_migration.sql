-- My TV v1.20 运营公告 PG 迁移（2026-09-03）
-- 通过 managePgDatabase(applyMigration) 执行；配套 hotupdate 云函数 GET /announce
-- 与本地 admin_server.py 公告管理页。
--
-- 组成：
--   1) 表 announcements（RLS 关闭，沿用 licenses 约定：全部访问收口到 RPC）
--   2) 公开 RPC：announcement_latest（app 经 hotupdate 云函数拉取；仅返回 published）
--   3) 管理 RPC：announcement_admin_get / announcement_admin_publish
--      （SECURITY DEFINER + auth.uid() 白名单 = svc_import，同 hotupdate_admin_* 模式）

-- ===== 1) 表 =====
create table if not exists public.announcements (
  id         bigint generated always as identity primary key,
  title      text not null,
  content    text not null default '',
  status     text not null default 'published' check (status in ('published', 'offline')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ===== 2) 公开 RPC（app 拉取最新生效公告）=====
create or replace function public.announcement_latest()
returns json
language plpgsql security definer set search_path to public as $$
declare r announcements%ROWTYPE;
begin
  select * into r from announcements
   where status = 'published'
   order by id desc limit 1;
  if not found then
    return json_build_object('ret', 0, 'ann', null);
  end if;
  return json_build_object('ret', 0, 'ann', json_build_object(
    'id', r.id, 'title', r.title, 'content', r.content, 'updatedAt', r.updated_at));
end $$;

-- ===== 3) 管理 RPC（本地后台，svc_import 白名单）=====
create or replace function public.announcement_admin_get()
returns json
language plpgsql security definer set search_path to public as $$
declare r announcements%ROWTYPE;
begin
  if coalesce(auth.uid(), '') <> '2094843486709620737' then raise exception 'forbidden'; end if;
  select * into r from announcements order by id desc limit 1;
  if not found then
    return json_build_object('ret', 0, 'ann', null);
  end if;
  return json_build_object('ret', 0, 'ann', json_build_object(
    'id', r.id, 'title', r.title, 'content', r.content,
    'status', r.status, 'updatedAt', r.updated_at));
end $$;

create or replace function public.announcement_admin_publish(
  p_title text, p_content text default '', p_status text default 'published')
returns json
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(auth.uid(), '') <> '2094843486709620737' then raise exception 'forbidden'; end if;
  if p_status not in ('published', 'offline') then raise exception 'bad_status'; end if;
  if p_status = 'published' then
    if p_title is null or length(btrim(p_title)) < 1 or length(p_title) > 60 then
      raise exception 'bad_title';
    end if;
    if p_content is null or length(p_content) > 600 then raise exception 'bad_content'; end if;
    -- 单条语义：发布 = 新增一条 published（id 递增，客户端按 id 变化识别新公告并重新弹出）
    insert into announcements (title, content, status)
    values (btrim(p_title), coalesce(p_content, ''), 'published');
  else
    -- 下线 = 把所有 published 置 offline（v1.20 修正：此前误插 offline 新行，
    -- 旧 published 行仍在，app 端公告下不掉）
    update announcements set status = 'offline', updated_at = now()
     where status = 'published';
  end if;
  return json_build_object('ret', 0, 'id', (select max(id) from announcements));
end $$;

-- ===== 4) 权限收口 =====
grant execute on function public.announcement_latest() to anon, authenticated;
revoke execute on function public.announcement_admin_get() from public, anon;
revoke execute on function public.announcement_admin_publish(text, text, text) from public, anon;
grant execute on function public.announcement_admin_get() to authenticated;
grant execute on function public.announcement_admin_publish(text, text, text) to authenticated;
