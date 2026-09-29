-- SC-01 baseline. Applied as postgres. Idempotent.
CREATE TABLE IF NOT EXISTS public.orders (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  amount numeric(12,2) NOT NULL,
  status text NOT NULL DEFAULT 'open',
  payload text NOT NULL
);
CREATE TABLE IF NOT EXISTS public.order_notes (
  id bigserial PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
  body text NOT NULL
);
CREATE TABLE IF NOT EXISTS public.workload_commits (
  id bigserial PRIMARY KEY,
  commit_lsn pg_lsn NOT NULL,
  commit_ts timestamptz NOT NULL,
  operation text NOT NULL,
  relation text NOT NULL,
  row_ids bigint[] NOT NULL,
  row_count integer NOT NULL
);
ALTER TABLE public.orders REPLICA IDENTITY FULL;
ALTER TABLE public.order_notes REPLICA IDENTITY FULL;
ALTER TABLE public.workload_commits REPLICA IDENTITY FULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.orders TO lab_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.order_notes TO lab_app;
GRANT SELECT, INSERT ON public.workload_commits TO lab_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lab_app;

GRANT SELECT, DELETE ON public.orders TO lab_agent;
GRANT SELECT ON public.order_notes TO lab_agent;
REVOKE INSERT, UPDATE ON public.orders FROM lab_agent;
REVOKE ALL ON public.workload_commits FROM lab_agent;

-- Seed data is applied by lab-workload seed, not this file, so re-applying DDL is safe.

-- X002-4 HEAD probe: harness_commit must follow this commit.
