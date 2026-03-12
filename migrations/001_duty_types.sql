-- Migration 001 — Duty Types (v2.1)
-- Adds duty_type to shifts, makes location_id nullable, adds grade_class to assignments.
-- IDEMPOTENT: safe to run multiple times.

-- shifts.duty_type
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'duty_type_enum'
    ) THEN
        CREATE TYPE duty_type_enum AS ENUM ('morning_endofday', 'break');
    END IF;
END$$;

ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS duty_type duty_type_enum NOT NULL DEFAULT 'morning_endofday';

-- shift_locations.location_id — make nullable (break duties have no fixed location)
ALTER TABLE shift_locations
    ALTER COLUMN location_id DROP NOT NULL;

-- assignments.grade_class
ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS grade_class VARCHAR(100);