-- Migration 003 — Web Push (v2.3)
-- Documents the device_tokens.platform column change:
-- platform now accepts 'web' in addition to 'android'.
-- No structural changes are needed — the column is VARCHAR(10)
-- and already stores any string value.

-- Verify the column exists and its type
SELECT column_name, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'device_tokens' AND column_name = 'platform';

-- No ALTER needed. Confirm FCM web tokens are stored with platform = 'web'.