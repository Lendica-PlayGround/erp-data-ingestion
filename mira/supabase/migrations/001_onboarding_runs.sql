-- Onboarding control plane (PRD §2.2, §6.1). Apply in Supabase SQL editor or supabase db push.

create table if not exists public.onboarding_runs (
  run_id uuid primary key,
  company_id text not null,
  state text not null,
  document jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists onboarding_runs_company_id_idx on public.onboarding_runs (company_id);
create index if not exists onboarding_runs_state_idx on public.onboarding_runs (state);

create table if not exists public.onboarding_run_state_history (
  id bigserial primary key,
  run_id uuid not null references public.onboarding_runs (run_id) on delete cascade,
  actor text not null,
  previous_state text,
  new_state text,
  patch jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.mapping_versions (
  id bigserial primary key,
  run_id uuid not null references public.onboarding_runs (run_id) on delete cascade,
  company_id text not null,
  mapping_version text not null,
  midlayer_schema_version text not null,
  contract jsonb not null,
  created_at timestamptz not null default now(),
  unique (mapping_version, company_id)
);

-- Legal state edges (subset enforced; full preconditions live in app + mapping validation).
create or replace function public.enforce_onboarding_transition()
returns trigger as $$
declare
  o text := old.state;
  n text := new.state;
begin
  if tg_op = 'UPDATE' and o = n then
    return new;
  end if;
  if n = 'failed' then
    return new;
  end if;
  if (o = 'intake' and n = 'research') then
    if coalesce(new.document->'source'->>'system', 'unknown') = 'unknown' then
      raise exception 'intake→research blocked: source.system is unknown';
    end if;
    return new;
  end if;
  if (o = 'intake' and n not in ('research', 'failed')) then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'research' and n not in ('map', 'failed')) then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'map' and n = 'awaiting_approval') then
    if new.document->'mapping_contract' is null then
      raise exception 'map→awaiting_approval blocked: mapping_contract missing';
    end if;
    return new;
  end if;
  if (o = 'map' and n not in ('awaiting_approval', 'failed')) then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'awaiting_approval' and n = 'code') then
    if new.document->'approval'->>'customer_confirmed_at' is null
       or new.document->'approval'->>'fde_confirmed_at' is null then
      raise exception 'awaiting_approval→code blocked: missing approvals';
    end if;
    return new;
  end if;
  if (o = 'awaiting_approval' and n not in ('code', 'failed')) then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'code' and n = 'dry_run') then
    if coalesce(new.document->'phase3'->>'pr_url', '') = '' then
      raise exception 'code→dry_run blocked: phase3.pr_url missing';
    end if;
    return new;
  end if;
  if (o = 'code' and n not in ('dry_run', 'failed')) then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'dry_run' and n = 'initial_sync') then
    if jsonb_array_length(coalesce(new.document->'phase3'->'dry_run_errors', '[]'::jsonb)) > 0 then
      raise exception 'dry_run→initial_sync blocked: dry_run_errors non-empty';
    end if;
    return new;
  end if;
  if (o = 'dry_run' and n not in ('initial_sync', 'failed')) then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'initial_sync' and n = 'scheduled') then
    if new.document->'phase3'->'initial_sync_manifest' is null then
      raise exception 'initial_sync→scheduled blocked: manifest missing';
    end if;
    return new;
  end if;
  if (o = 'initial_sync' and n not in ('scheduled', 'failed')) then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'scheduled' and n <> 'failed') then
    raise exception 'illegal transition %→%', o, n;
  end if;
  if (o = 'failed') then
    raise exception 'terminal failed state cannot transition to %', n;
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_onboarding_transition on public.onboarding_runs;
create trigger trg_onboarding_transition
before update of state on public.onboarding_runs
for each row
execute function public.enforce_onboarding_transition();
