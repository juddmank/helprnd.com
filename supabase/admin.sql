-- 관리자 페이지(admin.html)용: 로그인한 관리자 이메일만 상담 신청을 보고·고치고·지울 수 있게 한다
-- Supabase → SQL Editor 에서 실행

alter table public.leads add column if not exists memo text check (char_length(memo) <= 2000);
alter table public.leads add column if not exists updated_at timestamptz;

-- 관리자 이메일 목록 (바꾸려면 이 함수만 수정)
create or replace function public.is_helprnd_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(auth.jwt() ->> 'email', '') in ('juddmank@gmail.com');
$$;
revoke all on function public.is_helprnd_admin() from public;
grant execute on function public.is_helprnd_admin() to authenticated;

grant select, update, delete on public.leads to authenticated;

drop policy if exists "admin read leads" on public.leads;
drop policy if exists "admin update leads" on public.leads;
drop policy if exists "admin delete leads" on public.leads;
create policy "admin read leads"   on public.leads for select to authenticated using (public.is_helprnd_admin());
create policy "admin update leads" on public.leads for update to authenticated using (public.is_helprnd_admin()) with check (public.is_helprnd_admin());
create policy "admin delete leads" on public.leads for delete to authenticated using (public.is_helprnd_admin());
