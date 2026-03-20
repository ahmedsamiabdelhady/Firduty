-- 006_device_tokens_installation_id.sql
-- One token per device installation, multiple devices per teacher, no duplicates.
-- PostgreSQL / Supabase. Idempotent where practical.

ALTER TABLE device_tokens
    ADD COLUMN IF NOT EXISTS installation_id TEXT;

ALTER TABLE device_tokens
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE device_tokens
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE device_tokens
SET installation_id = CONCAT('legacy-', id::text)
WHERE installation_id IS NULL OR installation_id = '';

ALTER TABLE device_tokens
    ALTER COLUMN installation_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_device_tokens_teacher_installation'
    ) THEN
        ALTER TABLE device_tokens
            ADD CONSTRAINT uq_device_tokens_teacher_installation
            UNIQUE (teacher_id, installation_id);
    END IF;
END$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_device_tokens_token
    ON device_tokens (token);

CREATE INDEX IF NOT EXISTS idx_device_tokens_teacher
    ON device_tokens (teacher_id);

CREATE INDEX IF NOT EXISTS idx_device_tokens_last_seen
    ON device_tokens (last_seen_at);
