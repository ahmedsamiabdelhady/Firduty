-- ============================================================
-- Migration 003: Web Push support (iOS PWA + desktop browsers)
-- ============================================================
-- The DeviceToken table already stores web tokens via platform='web'.
-- No schema changes are required — the existing token VARCHAR(500)
-- column is large enough for FCM web registration tokens.
--
-- This migration is documentation-only and is safe to run on any
-- existing database; it makes no structural changes.
-- ============================================================

-- Verify the device_tokens table supports web tokens.
-- FCM web tokens are stored as the 'token' column with platform='web'.
-- They are obtained from firebase_messaging.getToken(vapidKey=...) in
-- the Flutter Web app and delivered to iOS Safari / desktop browsers
-- via Firebase's Web Push (VAPID) infrastructure.

-- Optional: add a comment to document the platform column values.
DO $$
BEGIN
    COMMENT ON COLUMN device_tokens.platform IS
        'android = FCM registration token from native Android app; '
        'web = FCM web registration token from Flutter Web / iOS PWA';
EXCEPTION
    WHEN OTHERS THEN
        -- COMMENT ON COLUMN fails on SQLite; safe to ignore.
        NULL;
END $$;

-- ============================================================
-- No further SQL required.
--
-- To enable Web Push, set the following env vars on your backend:
--   VAPID_PUBLIC_KEY  — from Firebase Console → Cloud Messaging → Web Push certificates
--   VAPID_PRIVATE_KEY — same location
--   VAPID_CONTACT_EMAIL — your admin email
--
-- And set kVapidPublicKey in:
--   flutter_app/lib/firebase_options.dart
-- ============================================================