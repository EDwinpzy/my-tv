-- One-time protocol-v2 inventory reset RPC.
-- Apply only after license_v2_migration.sql and a verified local snapshot.

create or replace function public.admin_license_v2_clear(p_environment text, p_confirm text)
returns json language plpgsql security definer set search_path to 'public'
as $function$
declare v_licenses integer; v_logs integer;
begin
  if coalesce(auth.uid(), '') <> '2094843486709620737' then raise exception 'forbidden'; end if;
  if p_environment <> 'appletv-d5ge1bth794873f76' or p_confirm <> 'CLEAR-ALL-LICENSES' then
    return json_build_object('ok', false, 'msg', 'confirmation_mismatch');
  end if;
  select count(*) into v_licenses from public.licenses;
  select count(*) into v_logs from public.activate_log;
  delete from public.activate_log;
  delete from public.licenses;
  return json_build_object('ok', true, 'deletedLicenses', v_licenses, 'deletedLogs', v_logs);
end;
$function$;

revoke all on function public.admin_license_v2_clear(text,text) from public, anon;
grant execute on function public.admin_license_v2_clear(text,text) to authenticated;
