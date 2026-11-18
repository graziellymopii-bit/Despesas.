-- ============================================================
-- Despesas. — tabelas e regras de segurança (Row Level Security)
--
-- Como usar: Supabase → SQL Editor → New query → cole este arquivo
-- inteiro → Run. Pode rodar mais de uma vez sem problema.
-- ============================================================


-- ------------------------------------------------------------
-- TABELAS
-- Todas têm a coluna user_id, preenchida automaticamente com o
-- id de quem está logado (auth.uid()). Ao apagar a conta, os
-- dados da pessoa são apagados junto (on delete cascade).
-- ------------------------------------------------------------
create table if not exists public.entries (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid()
              references auth.users (id) on delete cascade,
  type        text not null check (type in ('Despesa', 'Receita')),
  date        date not null,
  description text not null default '',
  category    text not null,
  method      text not null,
  amount      numeric(12, 2) not null check (amount > 0),
  fixed       boolean not null default false,
  created_at  timestamptz not null default now()
);

create index if not exists entries_user_date_idx on public.entries (user_id, date);

create table if not exists public.categories (
  id      bigint generated always as identity,
  user_id uuid not null default auth.uid()
          references auth.users (id) on delete cascade,
  name    text not null check (length(trim(name)) > 0),
  primary key (user_id, name)
);

create table if not exists public.budgets (
  user_id  uuid not null default auth.uid()
           references auth.users (id) on delete cascade,
  category text not null,
  amount   numeric(12, 2) not null check (amount > 0),
  primary key (user_id, category)
);


-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- Com o RLS ligado, o banco recusa qualquer linha que não seja
-- do usuário logado, mesmo que alguém altere o código do app
-- ou chame a API do Supabase diretamente.
-- ------------------------------------------------------------
alter table public.entries    enable row level security;
alter table public.categories enable row level security;
alter table public.budgets    enable row level security;

-- Visitantes sem login não têm acesso a nada.
revoke all on public.entries, public.categories, public.budgets from anon;
grant select, insert, update, delete
  on public.entries, public.categories, public.budgets to authenticated;

do $$
declare
  t text;
begin
  foreach t in array array['entries', 'categories', 'budgets'] loop
    execute format('drop policy if exists "dono pode ver"     on public.%I', t);
    execute format('drop policy if exists "dono pode criar"   on public.%I', t);
    execute format('drop policy if exists "dono pode editar"  on public.%I', t);
    execute format('drop policy if exists "dono pode apagar"  on public.%I', t);

    execute format($p$create policy "dono pode ver" on public.%I
      for select to authenticated
      using ((select auth.uid()) = user_id)$p$, t);

    execute format($p$create policy "dono pode criar" on public.%I
      for insert to authenticated
      with check ((select auth.uid()) = user_id)$p$, t);

    execute format($p$create policy "dono pode editar" on public.%I
      for update to authenticated
      using ((select auth.uid()) = user_id)
      with check ((select auth.uid()) = user_id)$p$, t);

    execute format($p$create policy "dono pode apagar" on public.%I
      for delete to authenticated
      using ((select auth.uid()) = user_id)$p$, t);
  end loop;
end
$$;
