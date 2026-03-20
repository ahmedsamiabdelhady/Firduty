// firebase-messaging-sw.js — FCM Service Worker for Firduty Web / PWA
//
// This file MUST be served from the web root (/) so the browser can register
// it at the root scope, which is required for FCM Web Push to work.
// Location: flutter_app/web/firebase-messaging-sw.js
//
// ── How it fits into the system ────────────────────────────────────────────
//   Flutter app (Dart)        → obtains FCM web registration token
//   Backend (Python)          → sends message via Firebase Admin SDK
//   Firebase Cloud Messaging  → delivers via Web Push to this service worker
//   This file                 → shows the notification when the app is closed
//                                or backgrounded
//
// ── Config values used ──────────────────────────────────────────────────────
// The values below come from:
//   firebase_options.dart  → FirebaseOptions.web
//   Firebase Console       → Project Settings → Your apps → Web app
//
// Web values that ARE known and filled in (from firebase_options.dart):
//   apiKey            ✓  AIzaSyD0lAw3ym33tl8PVh7xjZBDJ64QhKbwv1k
//   authDomain        ✓  firduty-dede5.firebaseapp.com
//   projectId         ✓  firduty-dede5
//   storageBucket     ✓  firduty-dede5.firebasestorage.app
//   messagingSenderId ✓  442695383131
//   measurementId     ✓  G-Y4DN8HJPC5  (optional, Analytics only)
//
// Values that still need to be filled in:
//   appId             ⚠  The WEB app's appId is in firebase_options.dart:
//                        appId: '1:442695383131:web:011bbb04af4dde2448677e'
//                        (already filled in below — verify it matches yours)
//
// ── TODO: VAPID key ─────────────────────────────────────────────────────────
// The service worker itself does not need the VAPID key directly.
// The VAPID key is used by the Flutter app (notification_service.dart) when
// calling messaging.getToken(vapidKey: kVapidPublicKey).
// Make sure kVapidPublicKey in firebase_options.dart is set to the value from:
//   Firebase Console → Project Settings → Cloud Messaging →
//   Web Push certificates → Generate key pair → copy the Key pair value
//
// ── Updating this file ──────────────────────────────────────────────────────
// If you re-run `flutterfire configure`, it will regenerate firebase_options.dart
// but may NOT update this file. Always verify the config values match.
// ────────────────────────────────────────────────────────────────────────────

importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

// ── Firebase web app configuration ──────────────────────────────────────────
// Source: firebase_options.dart → FirebaseOptions.web
// Verify these match your Firebase Console → Project Settings → Web app.
firebase.initializeApp({
  apiKey:            "AIzaSyD0lAw3ym33tl8PVh7xjZBDJ64QhKbwv1k",
  authDomain:        "firduty-dede5.firebaseapp.com",
  projectId:         "firduty-dede5",
  storageBucket:     "firduty-dede5.firebasestorage.app",
  messagingSenderId: "442695383131",
  appId:             "1:442695383131:web:1ac5166bec55253b48677e",
  measurementId:     "G-CF2WM5SL5D",
});
// ────────────────────────────────────────────────────────────────────────────

const messaging = firebase.messaging();

// ── Background message handler ───────────────────────────────────────────────
// Fires when the app is closed or the tab is backgrounded.
// When the app tab is open and focused, messages go to the Dart
// FirebaseMessaging.onMessage listener in notification_service.dart instead.
messaging.onBackgroundMessage(function(payload) {
  console.log('[firebase-messaging-sw] Background message received:', payload);

  const title = payload.notification?.title ?? 'Firduty';
  const body  = payload.notification?.body  ?? '';
  const data  = payload.data ?? {};

  return self.registration.showNotification(title, {
    body:    body,
    icon:    '/icons/Icon-192.png',
    badge:   '/icons/Icon-192.png',
    data:    data,
    vibrate: [200, 100, 200],  // Android Chrome; ignored on iOS
    actions: [
      { action: 'open', title: 'Open App' },
    ],
    // tag prevents duplicate notifications from the same source
    tag: data.assignment_id ?? 'firduty-notification',
  });
});

// ── Notification click handler ───────────────────────────────────────────────
// Brings an existing app window to focus, or opens a new one.
self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients
        .matchAll({ type: 'window', includeUncontrolled: true })
        .then(function(clientList) {
          for (const client of clientList) {
            if ('focus' in client) return client.focus();
          }
          return clients.openWindow('/');
        })
    );
  }
});

// ── Raw Web Push fallback ────────────────────────────────────────────────────
// Handles raw Web Push API `push` events that bypass the Firebase SDK.
// This fires when the backend sends a push via pywebpush (VAPID directly)
// rather than via Firebase Admin SDK.
self.addEventListener('push', function(event) {
  // If Firebase messaging already handled this, it will have called
  // showNotification, and the event.waitUntil chain is satisfied.
  // We only handle it here if Firebase did not.
  if (event.data) {
    let payload;
    try {
      payload = event.data.json();
    } catch (_) {
      payload = { notification: { title: 'Firduty', body: event.data.text() } };
    }

    // Only show notification if Firebase messaging hasn't already done so.
    // A rough heuristic: if the payload has a 'notification' key it's a raw push.
    if (payload.notification) {
      event.waitUntil(
        self.registration.showNotification(
          payload.notification.title ?? 'Firduty',
          {
            body:  payload.notification.body ?? '',
            icon:  '/icons/Icon-192.png',
            badge: '/icons/Icon-192.png',
            data:  payload.data ?? {},
          }
        )
      );
    }
  }
});
