-- TraceAct / Supabase — Step 1 schema
-- Run this entire script in the Supabase SQL Editor.

-- ── Audit reports (persistent user reports) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS public.audit_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    system_name     TEXT,
    risk_tier       TEXT,
    system_profile  JSONB NOT NULL DEFAULT '{}'::jsonb,
    audit_results   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_reports_user_id
    ON public.audit_reports (user_id);

CREATE INDEX IF NOT EXISTS idx_audit_reports_created_at
    ON public.audit_reports (created_at DESC);

-- ── Outstanding compliance tasks ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.compliance_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id        UUID REFERENCES public.audit_reports (id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'in_progress', 'done', 'blocked')),
    due_date        DATE,
    citation        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_compliance_tasks_user_id
    ON public.compliance_tasks (user_id);

CREATE INDEX IF NOT EXISTS idx_compliance_tasks_audit_id
    ON public.compliance_tasks (audit_id);

CREATE INDEX IF NOT EXISTS idx_compliance_tasks_status
    ON public.compliance_tasks (status);

-- Optional: keep updated_at fresh on task edits
CREATE OR REPLACE FUNCTION public.set_compliance_tasks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_compliance_tasks_updated_at ON public.compliance_tasks;
CREATE TRIGGER trg_compliance_tasks_updated_at
    BEFORE UPDATE ON public.compliance_tasks
    FOR EACH ROW
    EXECUTE PROCEDURE public.set_compliance_tasks_updated_at();
