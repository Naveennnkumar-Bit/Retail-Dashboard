-- GO DESi | Retail P&L - Supabase schema.
-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query -> paste -> Run).
-- Safe to run again after a change: everything is CREATE OR REPLACE / IF NOT EXISTS.

-- ============================================================= base table
-- One row per invoice line (kind 'sales') or per employee-cost line (kind 'cost'),
-- the same layout as the tracker's Base sheet / the local retail_pnl.db.
create table if not exists base (
    id bigint generated always as identity primary key,
    date text not null default '',
    month text not null default '',
    customer text not null default '',
    sub_channel text not null default '',
    cust_group text not null default '',
    city text not null default '',
    state text not null default '',
    zone text not null default '',
    rsm text not null default '',
    asm text not null default '',
    sku text not null default '',
    l0 text not null default '',
    l1 text not null default '',
    l2 text not null default '',
    l3 text not null default '',
    pack text not null default '',
    type text not null default '',
    is_return text not null default '',
    invoice text not null default '',
    employee text not null default '',
    scheme text not null default '',
    year int not null,
    mnum int not null,
    qty double precision,
    revenue double precision,
    cogs double precision,
    transport double precision,
    opex double precision,
    rsm_salary double precision,
    rsm_travel double precision,
    rsm_incentive double precision,
    asm_salary double precision,
    asm_travel double precision,
    asm_incentive double precision,
    db_claim double precision,
    so_salary double precision,
    so_incentive double precision,
    so_travel double precision,
    kind text not null check (kind in ('sales', 'cost'))
);
create index if not exists ix_base_period on base (year, mnum, kind);
create index if not exists ix_base_rsm on base (rsm);

create table if not exists meta (
    key text primary key,
    value text
);

create table if not exists uploads (
    id bigint generated always as identity primary key,
    at timestamptz not null default now(),
    what text not null,
    months text not null,
    rows_added int not null,
    rows_replaced int not null,
    source text
);

-- ============================================================= security
-- RLS on, and no policies: nobody reads the tables directly (not even signed-in users).
-- Reading happens only through the dash_* functions below, which are granted to
-- signed-in (authenticated) users. Writing happens only with the service key
-- (the Python scripts), which bypasses RLS.
alter table base enable row level security;
alter table meta enable row level security;
alter table uploads enable row level security;

-- ============================================================= helpers
create or replace function norm_dim(v text, fallback text)
returns text language sql immutable as $$
    select case when btrim(coalesce(v, '')) in ('', '0', '0.0', 'nan', 'None') then fallback
                else btrim(v) end;
$$;

create or replace function base_period(y int, m int)
returns text language sql immutable as $$
    select y::text || '-' || lpad(m::text, 2, '0');
$$;

-- ============================================================= read functions
-- Each returns exactly the JSON the dashboard's data files hold, so the website
-- can read from here or from static files interchangeably.

create or replace function dash_sales()
returns jsonb language sql stable security definer set search_path = public as $$
    select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) from (
        select base_period(year, mnum) as period,
               norm_dim(rsm, 'Unassigned') as rsm,
               norm_dim(asm, 'Unassigned') as asm,
               norm_dim(zone, 'Not set') as zone,
               norm_dim(state, 'Not set') as state,
               norm_dim(sub_channel, 'Not set') as sub_channel,
               norm_dim(l0, 'Not set') as l0,
               norm_dim(l1, 'Not set') as l1,
               norm_dim(l2, 'Not set') as l2,
               norm_dim(pack, 'Not set') as pack,
               norm_dim(type, 'Not set') as type,
               case when btrim(is_return) = 'Yes' then 1 else 0 end as is_return,
               round(sum(coalesce(qty, 0))::numeric, 2)::float8 as qty,
               round(sum(coalesce(revenue, 0))::numeric, 2)::float8 as revenue,
               round(sum(coalesce(cogs, 0))::numeric, 2)::float8 as cogs,
               round(sum(coalesce(transport, 0))::numeric, 2)::float8 as transport,
               round(sum(coalesce(opex, 0))::numeric, 2)::float8 as opex
        from base where kind = 'sales'
        group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
    ) t;
$$;

create or replace function dash_costs()
returns jsonb language sql stable security definer set search_path = public as $$
    select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) from (
        select base_period(year, mnum) as period,
               norm_dim(rsm, 'Unassigned') as rsm,
               norm_dim(asm, 'Unassigned') as asm,
               round(sum(coalesce(so_salary, 0))::numeric, 2)::float8 as so_salary,
               round(sum(coalesce(so_travel, 0))::numeric, 2)::float8 as so_travel,
               round(sum(coalesce(so_incentive, 0))::numeric, 2)::float8 as so_incentive,
               round(sum(coalesce(asm_salary, 0))::numeric, 2)::float8 as asm_salary,
               round(sum(coalesce(asm_travel, 0))::numeric, 2)::float8 as asm_travel,
               round(sum(coalesce(asm_incentive, 0))::numeric, 2)::float8 as asm_incentive,
               round(sum(coalesce(rsm_salary, 0))::numeric, 2)::float8 as rsm_salary,
               round(sum(coalesce(rsm_travel, 0))::numeric, 2)::float8 as rsm_travel,
               round(sum(coalesce(rsm_incentive, 0))::numeric, 2)::float8 as rsm_incentive,
               round(sum(coalesce(db_claim, 0))::numeric, 2)::float8 as db_claim
        from base where kind = 'cost'
        group by 1, 2, 3
    ) t;
$$;

create or replace function dash_skus()
returns jsonb language sql stable security definer set search_path = public as $$
    select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) from (
        select base_period(year, mnum) as period,
               norm_dim(sku, 'Not set') as sku,
               norm_dim(type, 'Not set') as type,
               case when btrim(is_return) = 'Yes' then 1 else 0 end as is_return,
               norm_dim(rsm, 'Unassigned') as rsm,
               norm_dim(asm, 'Unassigned') as asm,
               min(norm_dim(l0, 'Not set')) as l0,
               min(norm_dim(l1, 'Not set')) as l1,
               min(norm_dim(l2, 'Not set')) as l2,
               min(norm_dim(pack, 'Not set')) as pack,
               round(sum(coalesce(qty, 0))::numeric, 2)::float8 as qty,
               round(sum(coalesce(revenue, 0))::numeric, 2)::float8 as revenue,
               round(sum(coalesce(cogs, 0))::numeric, 2)::float8 as cogs
        from base where kind = 'sales'
        group by 1, 2, 3, 4, 5, 6
    ) t;
$$;

create or replace function dash_customers()
returns jsonb language sql stable security definer set search_path = public as $$
    select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) from (
        select base_period(year, mnum) as period,
               norm_dim(customer, 'Not set') as customer,
               case when btrim(is_return) = 'Yes' then 1 else 0 end as is_return,
               min(norm_dim(state, 'Not set')) as state,
               min(norm_dim(zone, 'Not set')) as zone,
               min(norm_dim(rsm, 'Unassigned')) as rsm,
               min(norm_dim(asm, 'Unassigned')) as asm,
               min(norm_dim(sub_channel, 'Not set')) as sub_channel,
               round(sum(coalesce(qty, 0))::numeric, 2)::float8 as qty,
               round(sum(coalesce(revenue, 0))::numeric, 2)::float8 as revenue,
               round(sum(coalesce(cogs, 0))::numeric, 2)::float8 as cogs,
               count(distinct invoice) filter (where btrim(invoice) <> '') as invoices
        from base where kind = 'sales'
        group by 1, 2, 3
    ) t;
$$;

create or replace function dash_daily()
returns jsonb language sql stable security definer set search_path = public as $$
    select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) from (
        select date as day,
               norm_dim(rsm, 'Unassigned') as rsm,
               round(sum(coalesce(revenue, 0))::numeric, 2)::float8 as revenue
        from base where kind = 'sales' and btrim(date) <> ''
        group by 1, 2
    ) t;
$$;

create or replace function dash_meta()
returns jsonb language sql stable security definer set search_path = public as $$
    select jsonb_build_object(
        'source', coalesce((select value from meta where key = 'source'), 'Supabase'),
        'source_modified', coalesce((select value from meta where key = 'updated'), ''),
        'generated', coalesce((select value from meta where key = 'updated'), ''),
        'base_rows', (select count(*) from base),
        'sales_rows', (select count(*) from base where kind = 'sales'),
        'cost_rows', (select count(*) from base where kind = 'cost')
    );
$$;

-- a fast full wipe for re-imports (service key only)
create or replace function truncate_base()
returns void language sql security definer set search_path = public as $$
    truncate table base restart identity;
$$;

-- ============================================================= grants
-- Signed-in users can read through the dash_* functions; nobody else can.
revoke all on function dash_sales(), dash_costs(), dash_skus(), dash_customers(),
    dash_daily(), dash_meta(), truncate_base(), norm_dim(text, text), base_period(int, int)
    from public, anon;
grant execute on function dash_sales(), dash_costs(), dash_skus(), dash_customers(),
    dash_daily(), dash_meta() to authenticated, service_role;
grant execute on function norm_dim(text, text), base_period(int, int) to authenticated, service_role;
grant execute on function truncate_base() to service_role;
