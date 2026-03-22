-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 006 — device_tokens: add installation_id + enforce per-device uniqueness
-- Version: v3.3.0
-- Idempotent — safe to run multiple times.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- DESIGN INTENT
-- ─────────────────────────────────────────────────────────────────────────────
-- One row per physical device per teacher.
--   Same teacher + same device + many FCM token rotations → ONE row (token updates)
--   Same teacher + 3 real devices                        → THREE rows (correct)
--
-- The authoritative device identity is: (teacher_id, installation_id)
-- NOT: token value, session, or app launch.
--
-- WHAT THIS MIGRATION DOES
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Add installation_id column (nullable — backward compat with old app versions)
-- 2. Add UNIQUE(teacher_id, installation_id) constraint
--    PostgreSQL treats NULL ≠ NULL, so rows without installation_id are NOT
--    constrained against each other — old devices keep working.
-- 3. Add supporting indexes
-- 4. Ensure UNIQUE(token) still exists
--
-- WHAT THIS MIGRATION INTENTIONALLY DOES NOT DO
-- ─────────────────────────────────────────────────────────────────────────────
-- It does NOT delete any existing rows.
--
-- Reason: rows without installation_id are ambiguous — they may represent
-- different real physical devices (one teacher, multiple phones/browsers).
-- Deleting the "older" ones would permanently destroy multi-device support
-- for teachers who have not yet updated the app.
--
-- Cleanup happens organically:
--   a) When each device opens the new app version, it re-registers with its
--      installation_id → the backend upserts by (teacher_id, installation_id)
--      → legacy NULL rows are superseded, not duplicated.
--   b) When FCM returns "token not registered" on send, the backend removes
--      stale tokens automatically (remove_invalid_tokens in notification_service.py).
--
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- ── Step 1: Add installation_id column ───────────────────────────────────────
-- Nullable: old app versions that don't send installation_id still work.
-- The backend uses a legacy fallback (upsert by token) for those clients.
ALTER TABLE device_tokens
    ADD COLUMN IF NOT EXISTS installation_id VARCHAR(100);

-- ── Step 2: Unique constraint on (teacher_id, installation_id) ───────────────
-- This is the deduplication guarantee for new-style registrations.
-- PostgreSQL UNIQUE constraints allow multiple NULLs, so NULL rows are
-- unaffected — backward compatibility preserved.
--
-- When the new Flutter app re-registers a device:
--   • First registration: INSERT new row with installation_id
--   • FCM token rotation: UPDATE the existing row's token (no new row)
--   • Different device, same teacher: INSERT new row (correct — different UUID)
ALTER TABLE device_tokens
    DROP CONSTRAINT IF EXISTS uq_device_token_teacher_installation;

ALTER TABLE device_tokens
    ADD CONSTRAINT uq_device_token_teacher_installation
    UNIQUE (teacher_id, installation_id);

-- ── Step 3: Supporting indexes ────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_device_token_installation_id
    ON device_tokens (installation_id);

CREATE INDEX IF NOT EXISTS ix_device_tokens_teacher_platform
    ON device_tokens (teacher_id, platform);

-- ── Step 4: Ensure UNIQUE(token) still exists ─────────────────────────────────
-- Created by alembic 0001. Re-create if missing.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname    = 'device_tokens_token_key'
          AND conrelid   = 'device_tokens'::regclass
    ) THEN
        ALTER TABLE device_tokens
            ADD CONSTRAINT device_tokens_token_key UNIQUE (token);
    END IF;
END $$;

-- ── Verify (run after COMMIT) ─────────────────────────────────────────────────
-- Count rows per teacher — multi-device teachers will have multiple rows,
-- which is correct. After all devices update, legacy NULL rows will disappear:
--
--   SELECT teacher_id, count(*), sum(CASE WHEN installation_id IS NULL THEN 1 ELSE 0 END) AS legacy
--   FROM device_tokens
--   GROUP BY teacher_id
--   ORDER BY count(*) DESC;

COMMIT;

-- ── Rollback (only before deploying new app) ──────────────────────────────────
-- BEGIN;
-- ALTER TABLE device_tokens DROP CONSTRAINT IF EXISTS uq_device_token_teacher_installation;
-- ALTER TABLE device_tokens DROP COLUMN IF EXISTS installation_id;
-- COMMIT;
