-- ============================================================
-- Migration 001: Add duty types to Firduty
-- ============================================================
-- Run against your PostgreSQL (Supabase) database.
-- Safe to run on an existing database — uses IF NOT EXISTS / DO blocks.
-- For SQLite (local dev): see notes at the bottom.
-- ============================================================

-- 1. Add duty_type column to shifts table
--    All existing shifts are assigned 'morning_endofday' (backward-compatible default)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'shifts' AND column_name = 'duty_type'
    ) THEN
        -- Create the enum type if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'duty_type_enum') THEN
            CREATE TYPE duty_type_enum AS ENUM ('morning_endofday', 'break');
        END IF;

        ALTER TABLE shifts
            ADD COLUMN duty_type duty_type_enum NOT NULL DEFAULT 'morning_endofday';

        COMMENT ON COLUMN shifts.duty_type IS
            'morning_endofday = show location; break = show grade/class';
    END IF;
END $$;

-- 2. Make location_id nullable on shift_locations (break duties have no fixed location)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'shift_locations'
          AND column_name = 'location_id'
          AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE shift_locations
            ALTER COLUMN location_id DROP NOT NULL;
    END IF;
END $$;

-- 3. Add grade_class column to assignments
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'assignments' AND column_name = 'grade_class'
    ) THEN
        ALTER TABLE assignments
            ADD COLUMN grade_class VARCHAR(100) NULL;

        COMMENT ON COLUMN assignments.grade_class IS
            'Populated for break duties: the grade/class this teacher monitors (e.g. Grade 5A)';
    END IF;
END $$;


-- ============================================================
-- SQLite (local dev) notes
-- ============================================================
-- SQLite does not support ALTER COLUMN or IF NOT EXISTS on columns.
-- For local dev, the simplest approach is to delete firduty.db and let
-- Base.metadata.create_all() recreate it with the new schema.
--
-- If you need to preserve SQLite data, run these statements manually:
--   ALTER TABLE shifts ADD COLUMN duty_type TEXT NOT NULL DEFAULT 'morning_endofday';
--   ALTER TABLE assignments ADD COLUMN grade_class TEXT;
--   (SQLite location_id is already effectively nullable — no action needed)
-- ============================================================