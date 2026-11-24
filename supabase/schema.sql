-- helprnd.com 상담 신청 저장용 테이블
-- Supabase 대시보드 → SQL Editor → New query 에 통째로 붙여 넣고 Run

create table if not exists public.leads (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  company     text not null check (char_length(company) between 1 and 60),
  name        text not null check (char_length(name) between 1 and 30),
  phone       text not null check (char_length(phone) between 8 and 20),
  email       text not null check (char_length(email) between 5 and 80),
  message     text check (char_length(message) <= 1000),
  consent     boolean not null check (consent = true),
  page        text,
  ip_hash     text,                      -- 같은 사람이 너무 많이 보내는지 확인용 (IP 원본은 저장하지 않음)
  status      text not null default '신규' -- 신규 / 연락함 / 상담완료 등 자유롭게 바꿔 쓰기
);

-- 2026-11-24 추가: 맞춤 지원사업 매칭용 소재지(시·도)·업종
alter table public.leads add column if not exists region   text check (char_length(region) <= 10);
alter table public.leads add column if not exists industry text check (char_length(industry) <= 40);

-- 보안: 행 수준 보안(RLS)을 켜고 공개 정책은 만들지 않는다.
-- → 사이트 방문자(공개 키)로는 읽기·쓰기 모두 불가. 저장은 서버 함수(lead)만 한다.
alter table public.leads enable row level security;

-- 서버 함수(service_role)만 쓰고 읽을 수 있게 권한을 명시한다 (새 표 자동 공개를 꺼 둔 프로젝트용)
grant usage on schema public to service_role;
grant select, insert, update on public.leads to service_role;
revoke all on public.leads from anon, authenticated;

create index if not exists leads_created_at_idx on public.leads (created_at desc);
create index if not exists leads_ip_hash_idx on public.leads (ip_hash, created_at desc);

-- 보유기간(상담 종료 후 1년) 관리용: 1년 지난 신청 확인
-- select * from public.leads where created_at < now() - interval '1 year';
