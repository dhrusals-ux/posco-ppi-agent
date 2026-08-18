-- ============================================================
-- 매매일지 — Supabase 스키마
-- Supabase 대시보드 → SQL Editor 에 붙여넣고 실행하세요 (한 번만).
-- ============================================================

-- 1) 일지 테이블 ---------------------------------------------
create table if not exists public.entries (
  id          text primary key,
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  date        date not null,
  time        text,
  symbol      text not null,
  side        text default 'long',
  entry       double precision,
  "exit"      double precision,
  qty         double precision,
  fee         double precision,
  pnl         double precision,
  pnl_pct     double precision,
  tags        text[] not null default '{}',
  comment     text   not null default '',
  rating      int    not null default 0,
  images      text[] not null default '{}',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists entries_user_date_idx on public.entries (user_id, date);

-- 2) 내 일지만 보이도록 (Row Level Security) -------------------
alter table public.entries enable row level security;

drop policy if exists "entries are private" on public.entries;
create policy "entries are private" on public.entries
  for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- 3) 차트 이미지 버킷 (비공개) ---------------------------------
insert into storage.buckets (id, name, public)
values ('charts', 'charts', false)
on conflict (id) do nothing;

-- 4) 내 폴더(uid/...)의 이미지만 읽고 쓰도록 --------------------
drop policy if exists "charts are private" on storage.objects;
create policy "charts are private" on storage.objects
  for all to authenticated
  using      (bucket_id = 'charts' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'charts' and (storage.foldername(name))[1] = auth.uid()::text);
