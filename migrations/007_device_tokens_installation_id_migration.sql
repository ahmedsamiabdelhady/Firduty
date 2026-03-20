-- device_tokens_installation_id_migration.sql
-- Adds installation_id support and collapses stale duplicate rows so each
-- teacher installation keeps only its newest token row.

BEGIN;

ALTER TABLE device_tokens
ADD COLUMN IF NOT EXISTS installation_id VARCHAR(100);

-- Backfill old rows that predate installation_id with a deterministic value.
UPDATE device_tokens
SET installation_id = CONCAT('legacy-', id)
WHERE installation_id IS NULL OR BTRIM(installation_id) = '';

ALTER TABLE device_tokens
ALTER COLUMN installation_id SET NOT NULL;

-- Keep only the newest row per teacher + installation.
DELETE FROM device_tokens t
USING device_tokens newer
WHERE t.id <> newer.id
  AND t.teacher_id = newer.teacher_id
  AND t.installation_id = newer.installation_id
  AND COALESCE(t.last_seen_at, t.created_at, NOW())
      < COALESCE(newer.last_seen_at, newer.created_at, NOW());

CREATE UNIQUE INDEX IF NOT EXISTS uq_device_tokens_teacher_installation
ON device_tokens (teacher_id, installation_id);

CREATE INDEX IF NOT EXISTS ix_device_tokens_teacher_platform
ON device_tokens (teacher_id, platform);

CREATE INDEX IF NOT EXISTS ix_device_tokens_installation_id
ON device_tokens (installation_id);

COMMIT;
