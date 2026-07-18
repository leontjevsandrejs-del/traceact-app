-- TraceAct / Supabase — FRIA assessments + framework mapping
-- Run in the Supabase SQL Editor.
-- Does NOT modify Auth policies, RLS, or existing triggers.

-- ── Fundamental Rights Impact Assessments (FRIA) ────────────────────────────
CREATE TABLE IF NOT EXISTS public.fria_assessments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    system_id       UUID REFERENCES public.audit_reports (id) ON DELETE SET NULL,
    results         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fria_assessments_user_id
    ON public.fria_assessments (user_id);

CREATE INDEX IF NOT EXISTS idx_fria_assessments_system_id
    ON public.fria_assessments (system_id);

CREATE INDEX IF NOT EXISTS idx_fria_assessments_created_at
    ON public.fria_assessments (created_at DESC);

-- Optional: GIN index for querying inside JSONB results payloads
CREATE INDEX IF NOT EXISTS idx_fria_assessments_results_gin
    ON public.fria_assessments USING GIN (results);

-- Keep updated_at fresh on FRIA edits (mirrors compliance_tasks pattern)
CREATE OR REPLACE FUNCTION public.set_fria_assessments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fria_assessments_updated_at ON public.fria_assessments;
CREATE TRIGGER trg_fria_assessments_updated_at
    BEFORE UPDATE ON public.fria_assessments
    FOR EACH ROW
    EXECUTE PROCEDURE public.set_fria_assessments_updated_at();

-- ── Expand compliance_tasks: framework mapping ────────────────────────────
ALTER TABLE public.compliance_tasks
    ADD COLUMN IF NOT EXISTS framework_mapping TEXT NOT NULL DEFAULT 'EU AI Act';

-- Backfill any pre-existing rows (safe if column was just added)
UPDATE public.compliance_tasks
SET framework_mapping = 'EU AI Act'
WHERE framework_mapping IS NULL;

-- Constrain to known frameworks (extend this list as you add more)
ALTER TABLE public.compliance_tasks
    DROP CONSTRAINT IF EXISTS compliance_tasks_framework_mapping_check;

ALTER TABLE public.compliance_tasks
    ADD CONSTRAINT compliance_tasks_framework_mapping_check
    CHECK (framework_mapping IN ('EU AI Act', 'ISO 42001'));

CREATE INDEX IF NOT EXISTS idx_compliance_tasks_framework_mapping
    ON public.compliance_tasks (framework_mapping);
