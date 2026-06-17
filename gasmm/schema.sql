-- gasmm — schema do ledger do paper MM (Supabase / Postgres).
-- Rode UMA vez no SQL Editor do Supabase (mesmo projeto do progno_bot/poly5m).
-- Escritas via PostgREST com a SERVICE ROLE KEY (server-side, GitHub Secret).

create table if not exists public.gasmm_strikes (
    ticker        text primary key,            -- 1 linha por strike cotado
    event         text,
    strike        double precision,
    opened_ts     bigint,
    close_ts      bigint,
    last_ts       bigint,                       -- último candle de 1-min processado
    posted_bid    double precision,            -- cotação que estamos mantendo
    posted_ask    double precision,
    inv           double precision default 0,  -- inventário (contratos)
    cash          double precision default 0,
    gross         double precision default 0,  -- captura de meio-spread (bruta)
    fills         int default 0,
    vol_seen      double precision default 0,  -- volume real visto na janela processada
    status        text default 'active',       -- 'active' | 'settled'
    settle_value  double precision,            -- 1.0 (yes) | 0.0 (no)
    pnl           double precision,
    updated_ts    bigint,
    created_at    timestamptz default now()
);

create table if not exists public.gasmm_equity (
    id           bigint generated always as identity primary key,
    ts           bigint,
    realized     double precision,             -- PnL dos strikes liquidados
    open_mtm     double precision,             -- inventário ativo marcado a mercado
    equity       double precision,             -- bankroll + realized + open_mtm
    n_active     int,
    total_fills  int,
    total_vol    double precision,
    created_at   timestamptz default now()
);

create index if not exists idx_gasmm_strikes_status on public.gasmm_strikes (status);
create index if not exists idx_gasmm_equity_ts      on public.gasmm_equity (ts);

alter table public.gasmm_strikes enable row level security;
alter table public.gasmm_equity  enable row level security;
-- Sem policy pública: só a SERVICE ROLE key (bypassa RLS) lê/escreve. A anon não vê nada.
