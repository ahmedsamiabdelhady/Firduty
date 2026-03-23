importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyD0lAw3ym33tl8PVh7xjZBDJ64QhKbwv1k",
  authDomain: "firduty-dede5.firebaseapp.com",
  projectId: "firduty-dede5",
  storageBucket: "firduty-dede5.firebasestorage.app",
  messagingSenderId: "442695383131",
  appId: "1:442695383131:web:1ac5166bec55253b48677e",
  measurementId: "G-CF2WM5SL5D",
});

const messaging = firebase.messaging();

function buildNotificationFromPayload(payload) {
  const data = payload?.data || {};
  const title = data.title || 'Firduty';
  const body = data.body || '';
  const assignmentId = data.assignment_id || 'firduty-notification';

  return {
    title,
    options: {
      body,
      icon: '/icons/Icon-192.png',
      badge: '/icons/Icon-192.png',
      data,
      tag: `${data.type || 'general'}-${assignmentId}`,
      renotify: false,
      actions: [
        { action: 'open', title: 'Open App' },
      ],
    },
  };
}

messaging.onBackgroundMessage(function(payload) {
  console.log('[firebase-messaging-sw] Data-only background message:', payload);

  const notif = buildNotificationFromPayload(payload);
  return self.registration.showNotification(notif.title, notif.options);
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      for (const client of clientList) {
        if ('focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow('/');
    })
  );
});

/*
  Keep the raw push handler disabled for now to avoid double rendering.
  Firebase messaging already handles FCM web pushes through onBackgroundMessage.
*/