-- Mid-layer + target-layer relational storage (Supabase Postgres-first).
-- Apply in the Supabase SQL editor, via psycopg, or with a future supabase db push flow.

create extension if not exists pgcrypto;

create table if not exists public.ingestion_load_batches (
  id bigserial primary key,
  batch_id uuid not null default gen_random_uuid(),
  company_id text not null,
  source_system text not null,
  entity_name text not null check (entity_name in ('customers', 'contacts', 'invoices')),
  sync_type text not null check (sync_type in ('initial', 'delta')),
  mapping_version text not null,
  source_file text,
  source_path text,
  status text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
  row_count integer not null default 0,
  inserted_count integer not null default 0,
  updated_count integer not null default 0,
  failed_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (batch_id)
);

create index if not exists ingestion_load_batches_company_idx
  on public.ingestion_load_batches (company_id, entity_name, started_at desc);

create index if not exists ingestion_load_batches_status_idx
  on public.ingestion_load_batches (status, started_at desc);


create table if not exists public.ingestion_validation_failures (
  id bigserial primary key,
  load_batch_id bigint references public.ingestion_load_batches (id) on delete cascade,
  company_id text not null,
  entity_name text not null check (entity_name in ('customers', 'contacts', 'invoices')),
  source_system text not null,
  source_record_id text,
  row_number integer,
  row_hash text,
  error_code text not null,
  error_message text not null,
  raw_row jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ingestion_validation_failures_batch_idx
  on public.ingestion_validation_failures (load_batch_id, entity_name);

create index if not exists ingestion_validation_failures_company_idx
  on public.ingestion_validation_failures (company_id, created_at desc);


create table if not exists public.mid_customers (
  id bigserial primary key,
  load_batch_id bigint references public.ingestion_load_batches (id) on delete set null,
  external_id text not null,
  name text,
  is_supplier boolean not null default false,
  is_customer boolean not null default true,
  email_address text,
  tax_number text,
  status text check (status in ('ACTIVE', 'ARCHIVED')),
  currency char(3),
  remote_updated_at timestamptz,
  phone_number text,
  addresses text,
  remote_was_deleted boolean not null default false,
  _unmapped jsonb not null default '{}'::jsonb,
  _source_system text not null,
  _source_record_id text not null,
  _company_id text not null,
  _ingested_at timestamptz not null,
  _source_file text not null,
  _mapping_version text not null,
  _row_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (_company_id, _source_system, _source_record_id)
);

create index if not exists mid_customers_company_idx
  on public.mid_customers (_company_id, external_id);

create index if not exists mid_customers_batch_idx
  on public.mid_customers (load_batch_id, _ingested_at desc);


create table if not exists public.mid_contacts (
  id bigserial primary key,
  load_batch_id bigint references public.ingestion_load_batches (id) on delete set null,
  external_id text not null,
  first_name text,
  last_name text,
  account_external_id text,
  addresses text,
  email_addresses text,
  phone_numbers text,
  last_activity_at timestamptz,
  remote_created_at timestamptz,
  remote_was_deleted boolean not null default false,
  _unmapped jsonb not null default '{}'::jsonb,
  _source_system text not null,
  _source_record_id text not null,
  _company_id text not null,
  _ingested_at timestamptz not null,
  _source_file text not null,
  _mapping_version text not null,
  _row_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (_company_id, _source_system, _source_record_id)
);

create index if not exists mid_contacts_company_idx
  on public.mid_contacts (_company_id, external_id);

create index if not exists mid_contacts_batch_idx
  on public.mid_contacts (load_batch_id, _ingested_at desc);


create table if not exists public.mid_invoices (
  id bigserial primary key,
  load_batch_id bigint references public.ingestion_load_batches (id) on delete set null,
  external_id text not null,
  type text check (type in ('ACCOUNTS_RECEIVABLE', 'ACCOUNTS_PAYABLE')),
  number text,
  contact_external_id text,
  issue_date timestamptz,
  due_date timestamptz,
  paid_on_date timestamptz,
  memo text,
  currency char(3),
  exchange_rate numeric(18, 6),
  total_discount numeric(18, 4),
  sub_total numeric(18, 4),
  total_tax_amount numeric(18, 4),
  total_amount numeric(18, 4),
  balance numeric(18, 4),
  status text check (status in ('DRAFT', 'OPEN', 'PAID', 'UNCOLLECTIBLE', 'VOID', 'PARTIALLY_PAID', 'SUBMITTED')),
  remote_was_deleted boolean not null default false,
  _unmapped jsonb not null default '{}'::jsonb,
  _source_system text not null,
  _source_record_id text not null,
  _company_id text not null,
  _ingested_at timestamptz not null,
  _source_file text not null,
  _mapping_version text not null,
  _row_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (_company_id, _source_system, _source_record_id)
);

create index if not exists mid_invoices_company_idx
  on public.mid_invoices (_company_id, external_id);

create index if not exists mid_invoices_contact_idx
  on public.mid_invoices (_company_id, contact_external_id);

create index if not exists mid_invoices_batch_idx
  on public.mid_invoices (load_batch_id, _ingested_at desc);


create table if not exists public.target_customers (
  id bigserial primary key,
  mid_customer_id bigint not null references public.mid_customers (id) on delete cascade,
  load_batch_id bigint references public.ingestion_load_batches (id) on delete set null,
  company_id text not null,
  source_system text not null,
  source_record_id text not null,
  customer_external_id text not null,
  customer_company_name text,
  description text,
  email_address text,
  phone_number text,
  tax_number text,
  customer_status text,
  currency char(3),
  is_supplier boolean not null default false,
  is_customer boolean not null default true,
  addresses text,
  remote_updated_at timestamptz,
  remote_was_deleted boolean not null default false,
  default_payment_terms text,
  credit_limit numeric(18, 4),
  data_source_type text,
  data_source_name text,
  data_sources jsonb not null default '[]'::jsonb,
  transform_version text not null default 'v1',
  transform_metadata jsonb not null default '{}'::jsonb,
  transformed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, source_system, source_record_id)
);

create index if not exists target_customers_company_idx
  on public.target_customers (company_id, customer_external_id);


create table if not exists public.target_contacts (
  id bigserial primary key,
  mid_contact_id bigint not null references public.mid_contacts (id) on delete cascade,
  load_batch_id bigint references public.ingestion_load_batches (id) on delete set null,
  target_customer_id bigint references public.target_customers (id) on delete set null,
  company_id text not null,
  source_system text not null,
  source_record_id text not null,
  contact_external_id text not null,
  account_external_id text,
  first_name text,
  last_name text,
  full_name text,
  addresses text,
  email_addresses text,
  phone_numbers text,
  last_activity_at timestamptz,
  remote_created_at timestamptz,
  remote_was_deleted boolean not null default false,
  data_source_type text,
  data_source_name text,
  data_sources jsonb not null default '[]'::jsonb,
  transform_version text not null default 'v1',
  transform_metadata jsonb not null default '{}'::jsonb,
  transformed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, source_system, source_record_id)
);

create index if not exists target_contacts_company_idx
  on public.target_contacts (company_id, contact_external_id);

create index if not exists target_contacts_customer_idx
  on public.target_contacts (target_customer_id);


create table if not exists public.target_invoices (
  id bigserial primary key,
  mid_invoice_id bigint not null references public.mid_invoices (id) on delete cascade,
  load_batch_id bigint references public.ingestion_load_batches (id) on delete set null,
  target_customer_id bigint references public.target_customers (id) on delete set null,
  company_id text not null,
  source_system text not null,
  source_record_id text not null,
  invoice_external_id text not null,
  invoice_number text,
  contact_external_id text,
  customer_external_id text,
  invoice_type text,
  issue_date date,
  due_date date,
  paid_on_date date,
  memo text,
  currency char(3),
  exchange_rate numeric(18, 6),
  total_discount numeric(18, 4),
  sub_total numeric(18, 4),
  total_tax_amount numeric(18, 4),
  total_amount numeric(18, 4),
  paid_amount numeric(18, 4),
  balance numeric(18, 4),
  merge_status text,
  status text,
  days_outstanding integer,
  aging_bucket text,
  disposition text,
  remote_was_deleted boolean not null default false,
  data_source_type text,
  data_source_name text,
  data_sources jsonb not null default '[]'::jsonb,
  transform_version text not null default 'v1',
  transform_metadata jsonb not null default '{}'::jsonb,
  transformed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, source_system, source_record_id)
);

create index if not exists target_invoices_company_idx
  on public.target_invoices (company_id, invoice_external_id);

create index if not exists target_invoices_customer_idx
  on public.target_invoices (target_customer_id, due_date);

create index if not exists target_invoices_status_idx
  on public.target_invoices (status, aging_bucket);
