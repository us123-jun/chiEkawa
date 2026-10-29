-- Run once in the Supabase project's SQL Editor.
create table if not exists public.game_saves (
  user_id uuid primary key references auth.users(id) on delete cascade,
  state jsonb not null check (jsonb_typeof(state) = 'object' and octet_length(state::text) <= 16384),
  revision bigint not null default 0 check (revision >= 0),
  updated_at timestamptz not null default now()
);
alter table public.game_saves enable row level security;
revoke all on public.game_saves from anon, authenticated;
grant select, insert, update on public.game_saves to authenticated;
drop policy if exists "Read own save" on public.game_saves;
create policy "Read own save" on public.game_saves for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Insert own save" on public.game_saves;
create policy "Insert own save" on public.game_saves for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "Update own save" on public.game_saves;
create policy "Update own save" on public.game_saves for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- Optimistic concurrency: a stale device cannot silently replace a newer save.
create or replace function public.save_game(p_state jsonb, p_expected_revision bigint)
returns bigint language plpgsql security invoker set search_path = '' as $$
declare next_revision bigint;
begin
  if auth.uid() is null then raise exception 'AUTH_REQUIRED'; end if;
  if p_expected_revision < 0 then raise exception 'INVALID_REVISION'; end if;
  insert into public.game_saves(user_id, state, revision)
  values (auth.uid(), p_state, 0) on conflict (user_id) do nothing;
  update public.game_saves set state = p_state, revision = revision + 1, updated_at = now()
  where user_id = auth.uid() and revision = p_expected_revision
  returning revision into next_revision;
  if next_revision is null then raise exception 'SAVE_CONFLICT'; end if;
  return next_revision;
end;
$$;
revoke all on function public.save_game(jsonb, bigint) from public, anon;
grant execute on function public.save_game(jsonb, bigint) to authenticated;
