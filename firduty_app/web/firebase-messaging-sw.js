importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'AIzaSyD0lAw3ym33tl8PVh7xjZBDJ64QhKbwv1k',
  authDomain: 'firduty-dede5.firebaseapp.com',
  projectId: 'firduty-dede5',
  storageBucket: 'firduty-dede5.firebasestorage.app',
  messagingSenderId: '442695383131',
  appId: '1:442695383131:web:1ac5166bec55253b48677e',
  measurementId: 'G-CF2WM5SL5D',
});

const messaging = firebase.messaging();
const recentlyShown = new Map();
const DEDUPE_WINDOW_MS = 15000;

function cleanupShownCache() {
  const now = Date.now();
  for (const [key, ts] of recentlyShown.entries()) {
    if (now - ts > DEDUPE_WINDOW_MS) {
      recentlyShown.delete(key);
    }
  }
}

function buildNotificationFromPayload(payload) {
  const data = payload?.data || {};
  const title = String(data.title || payload?.notification?.title || '').trim();
  const body = String(data.body || payload?.notification?.body || '').trim();
  const tag = [
    data.notification_type || data.type || 'general',
    data.assignment_id || 'no-assignment',
    data.day_date || 'no-date',
  ].join('-');

  if (!title && !body) {
    return null;
  }

  return {
    title: title || 'Firduty',
    options: {
      body,
      icon: '/icons/Icon-192.png',
      badge: '/icons/Icon-192.png',
      data,
      tag,
      renotify: false,
      actions: [{ action: 'open', title: 'Open App' }],
    },
  };
}

messaging.onBackgroundMessage(function (payload) {
  cleanupShownCache();

  const notif = buildNotificationFromPayload(payload);
  if (!notif) {
    console.log('[firebase-messaging-sw] Skip manual render: empty title/body.', payload);
    return;
  }

  const dedupeKey = `${notif.options.tag}|${notif.title}|${notif.options.body || ''}`;
  if (recentlyShown.has(dedupeKey)) {
    console.log('[firebase-messaging-sw] Skip duplicate notification:', dedupeKey);
    return;
  }

  recentlyShown.set(dedupeKey, Date.now());
  console.log('[firebase-messaging-sw] Showing notification:', dedupeKey, payload);
  return self.registration.showNotification(notif.title, notif.options);
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (const client of clientList) {
        if ('focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow('/');
    })
  );
});
