-- Migration 004 — Production schema sync / emergency fix
-- Idempotent: safe to run multiple times on PostgreSQL / Supabase

-- ─────────────────────────────────────────
-- Enums
-- ─────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'duty_type_enum'
    ) THEN
        CREATE TYPE duty_type_enum AS ENUM ('morning_endofday', 'break');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'teacher_status_enum'
    ) THEN
        CREATE TYPE teacher_status_enum AS ENUM ('pending', 'approved');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'week_status'
    ) THEN
        CREATE TYPE week_status AS ENUM ('draft', 'published');
    END IF;
END$$;


-- ─────────────────────────────────────────
-- teachers
-- ─────────────────────────────────────────

ALTER TABLE teachers
    ADD COLUMN IF NOT EXISTS email VARCHAR(255);

ALTER TABLE teachers
    ADD COLUMN IF NOT EXISTS status teacher_status_enum DEFAULT 'approved';

ALTER TABLE teachers
    ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;

ALTER TABLE teachers
    ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(2) DEFAULT 'ar';

UPDATE teachers
SET status = 'approved'
WHERE status IS NULL;

UPDATE teachers
SET active = TRUE
WHERE active IS NULL;

UPDATE teachers
SET preferred_language = 'ar'
WHERE preferred_language IS NULL;

ALTER TABLE teachers
    ALTER COLUMN status SET NOT NULL;

ALTER TABLE teachers
    ALTER COLUMN status SET DEFAULT 'approved';

ALTER TABLE teachers
    ALTER COLUMN active SET NOT NULL;

ALTER TABLE teachers
    ALTER COLUMN active SET DEFAULT TRUE;

ALTER TABLE teachers
    ALTER COLUMN preferred_language SET NOT NULL;

ALTER TABLE teachers
    ALTER COLUMN preferred_language SET DEFAULT 'ar';

CREATE UNIQUE INDEX IF NOT EXISTS uq_teacher_email
    ON teachers (email)
    WHERE email IS NOT NULL;


-- ─────────────────────────────────────────
-- locations
-- ─────────────────────────────────────────

ALTER TABLE locations
    ADD COLUMN IF NOT EXISTS name_ar VARCHAR(200);

ALTER TABLE locations
    ADD COLUMN IF NOT EXISTS "order" INTEGER DEFAULT 0;

UPDATE locations
SET name_ar = COALESCE(name_ar, name_en)
WHERE name_ar IS NULL;

UPDATE locations
SET "order" = 0
WHERE "order" IS NULL;

ALTER TABLE locations
    ALTER COLUMN name_ar SET NOT NULL;

ALTER TABLE locations
    ALTER COLUMN "order" SET NOT NULL;

ALTER TABLE locations
    ALTER COLUMN "order" SET DEFAULT 0;


-- ─────────────────────────────────────────
-- shifts
-- ─────────────────────────────────────────

ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS "order" INTEGER DEFAULT 0;

ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS duty_type duty_type_enum DEFAULT 'morning_endofday';

UPDATE shifts
SET "order" = 0
WHERE "order" IS NULL;

UPDATE shifts
SET duty_type = 'morning_endofday'
WHERE duty_type IS NULL;

ALTER TABLE shifts
    ALTER COLUMN "order" SET NOT NULL;

ALTER TABLE shifts
    ALTER COLUMN "order" SET DEFAULT 0;

ALTER TABLE shifts
    ALTER COLUMN duty_type SET NOT NULL;

ALTER TABLE shifts
    ALTER COLUMN duty_type SET DEFAULT 'morning_endofday';


-- ─────────────────────────────────────────
-- shift_locations
-- ─────────────────────────────────────────

ALTER TABLE shift_locations
    ALTER COLUMN location_id DROP NOT NULL;

ALTER TABLE shift_locations
    ADD COLUMN IF NOT EXISTS slots_count INTEGER DEFAULT 1;

ALTER TABLE shift_locations
    ADD COLUMN IF NOT EXISTS "order" INTEGER DEFAULT 0;

UPDATE shift_locations
SET slots_count = 1
WHERE slots_count IS NULL;

UPDATE shift_locations
SET "order" = 0
WHERE "order" IS NULL;

ALTER TABLE shift_locations
    ALTER COLUMN slots_count SET NOT NULL;

ALTER TABLE shift_locations
    ALTER COLUMN slots_count SET DEFAULT 1;

ALTER TABLE shift_locations
    ALTER COLUMN "order" SET NOT NULL;

ALTER TABLE shift_locations
    ALTER COLUMN "order" SET DEFAULT 0;


-- ─────────────────────────────────────────
-- assignments
-- ─────────────────────────────────────────

ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS grade_class VARCHAR(100);


-- ─────────────────────────────────────────
-- week_plans
-- ─────────────────────────────────────────

ALTER TABLE week_plans
    ADD COLUMN IF NOT EXISTS status week_status DEFAULT 'draft';

ALTER TABLE week_plans
    ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;

ALTER TABLE week_plans
    ADD COLUMN IF NOT EXISTS cloned_from_week_start DATE;

UPDATE week_plans
SET status = 'draft'
WHERE status IS NULL;

UPDATE week_plans
SET version = 1
WHERE version IS NULL;

ALTER TABLE week_plans
    ALTER COLUMN status SET NOT NULL;

ALTER TABLE week_plans
    ALTER COLUMN status SET DEFAULT 'draft';

ALTER TABLE week_plans
    ALTER COLUMN version SET NOT NULL;

ALTER TABLE week_plans
    ALTER COLUMN version SET DEFAULT 1;


-- ─────────────────────────────────────────
-- day_plans
-- ─────────────────────────────────────────

ALTER TABLE day_plans
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT FALSE;

UPDATE day_plans
SET is_published = FALSE
WHERE is_published IS NULL;

ALTER TABLE day_plans
    ALTER COLUMN is_published SET NOT NULL;

ALTER TABLE day_plans
    ALTER COLUMN is_published SET DEFAULT FALSE;


-- ─────────────────────────────────────────
-- duty_confirmations
-- ─────────────────────────────────────────

ALTER TABLE duty_confirmations
    ADD COLUMN IF NOT EXISTS points_earned INTEGER DEFAULT 0;

UPDATE duty_confirmations
SET points_earned = 0
WHERE points_earned IS NULL;

ALTER TABLE duty_confirmations
    ALTER COLUMN points_earned SET NOT NULL;

ALTER TABLE duty_confirmations
    ALTER COLUMN points_earned SET DEFAULT 0;