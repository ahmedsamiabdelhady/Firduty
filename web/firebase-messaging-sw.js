// firebase-messaging-sw.js — Firebase Cloud Messaging Service Worker
//
// This file must be in the web root (flutter_app/web/) so the browser can
// register it at the root scope, which is required for FCM web push.
//
// ── SETUP REQUIRED ──────────────────────────────────────────────────────────
// Replace the placeholder values below with your Firebase web app config.
// Get these from: Firebase Console → Project Settings → Your apps → Web app
//   → SDK setup and configuration → Config object.
//
// Run:  flutterfire configure
// This auto-generates lib/firebase_options.dart AND updates this file.
// ─────────────────────────────────────────────────────────────────────────────

importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

// ── TODO: Replace with your actual Firebase web config ────────────────────────
firebase.initializeApp({
  apiKey:            "YOUR_FIREBASE_API_KEY",
  authDomain:        "YOUR_PROJECT_ID.firebaseapp.com",
  projectId:         "YOUR_PROJECT_ID",
  storageBucket:     "YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID",
  appId:             "YOUR_APP_ID",
});
// ─────────────────────────────────────────────────────────────────────────────

const messaging = firebase.messaging();

// Handle background messages (app closed or in background)
messaging.onBackgroundMessage(function (payload) {
  console.log('[firebase-messaging-sw] Background message received:', payload);

  const title   = payload.notification?.title   ?? 'Firduty';
  const body    = payload.notification?.body    ?? '';
  const data    = payload.data ?? {};

  return self.registration.showNotification(title, {
    body:   body,
    icon:   '/icons/Icon-192.png',
    badge:  '/icons/Icon-192.png',
    data:   data,
    // Vibrate pattern for mobile (Android Chrome; ignored on iOS)
    vibrate: [200, 100, 200],
    // Action buttons (optional — add more as needed)
    actions: [
      { action: 'open', title: 'Open App' },
    ],
  });
});

// Handle notification click — bring app to foreground
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
        for (const client of clientList) {
          if ('focus' in client) return client.focus();
        }
        return clients.openWindow('/');
      })
    );
  }
});

// ── Push event fallback (VAPID raw push, if FCM SW is not intercepting) ──────
// This handles raw Web Push API events (e.g. sent directly via pywebpush)
// if Firebase Messaging is not used for web.
self.addEventListener('push', function (event) {
  if (event.data) {
    let payload = {};
    try { payload = event.data.json(); } catch (_) { payload = { title: 'Firduty', body: event.data.text() }; }

    const title   = payload.notification?.title ?? payload.title ?? 'Firduty';
    const options = {
      body:    payload.notification?.body  ?? payload.body  ?? '',
      icon:    '/icons/Icon-192.png',
      badge:   '/icons/Icon-192.png',
      data:    payload.data ?? {},
      vibrate: [200, 100, 200],
    };
    event.waitUntil(self.registration.showNotification(title, options));
  }
});