-- ============================================================
-- Migration 002: Teacher self-registration support
-- ============================================================
-- Adds email and status columns to the teachers table.
-- Safe to run on an existing database:
--   - email  : NULL allowed (existing records have no email)
--   - status : defaults to 'approved' (existing teachers are not blocked)
-- ============================================================

-- 1. Create the status enum type (PostgreSQL)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'teacher_status_enum') THEN
        CREATE TYPE teacher_status_enum AS ENUM ('pending', 'approved');
    END IF;
END $$;

-- 2. Add email column (nullable, unique)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'teachers' AND column_name = 'email'
    ) THEN
        ALTER TABLE teachers ADD COLUMN email VARCHAR(255) NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_teacher_email ON teachers (email)
            WHERE email IS NOT NULL;
        COMMENT ON COLUMN teachers.email IS
            'Unique email address; set by self-registration flow. NULL for admin-created records.';
    END IF;
END $$;

-- 3. Add status column (default 'approved' — existing teachers remain active)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'teachers' AND column_name = 'status'
    ) THEN
        ALTER TABLE teachers
            ADD COLUMN status teacher_status_enum NOT NULL DEFAULT 'approved';
        COMMENT ON COLUMN teachers.status IS
            'pending = awaiting admin approval after self-registration; approved = can use the app';
    END IF;
END $$;


-- ============================================================
-- SQLite (local dev) notes
-- ============================================================
-- SQLite does not support enums or IF NOT EXISTS on ADD COLUMN.
-- For local dev, the simplest approach is to delete firduty.db and let
-- Base.metadata.create_all() recreate it with the new schema.
--
-- To add columns to an existing SQLite database manually:
--   ALTER TABLE teachers ADD COLUMN email TEXT;
--   ALTER TABLE teachers ADD COLUMN status TEXT NOT NULL DEFAULT 'approved';
--   CREATE UNIQUE INDEX IF NOT EXISTS uq_teacher_email ON teachers (email)
--     WHERE email IS NOT NULL;
-- ============================================================