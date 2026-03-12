-- Migration 002 — Teacher Registration (v2.2)
-- Adds email and status to teachers table.
-- IDEMPOTENT: safe to run multiple times.

-- teacher_status_enum type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'teacher_status_enum'
    ) THEN
        CREATE TYPE teacher_status_enum AS ENUM ('pending', 'approved');
    END IF;
END$$;

-- teachers.email
ALTER TABLE teachers
    ADD COLUMN IF NOT EXISTS email VARCHAR(255);

-- Unique index on email (only for non-NULL values)
CREATE UNIQUE INDEX IF NOT EXISTS uq_teacher_email
    ON teachers (email)
    WHERE email IS NOT NULL;

-- teachers.status
ALTER TABLE teachers
    ADD COLUMN IF NOT EXISTS status teacher_status_enum NOT NULL DEFAULT 'approved';

-- Existing admin-created teachers are already approved — no data migration needed.