importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'AIzaSyD0lAw3ym33tl8PVh7xjZBDJ64QhKbwv1k',
  appId: '1:442695383131:web:1ac5166bec55253b48677e',
  messagingSenderId: '442695383131',
  projectId: 'firduty-dede5',
  authDomain: 'firduty-dede5.firebaseapp.com',
  storageBucket: 'firduty-dede5.firebasestorage.app',
  measurementId: 'G-CF2WM5SL5D',
});

const messaging = firebase.messaging();

function buildNotificationFromPayload(payload) {
  const data = payload?.data || {};
  const title = (payload?.notification?.title || data.title || 'Firduty').trim();
  const body = (payload?.notification?.body || data.body || '').trim();
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
      requireInteraction: false,
      actions: [{ action: 'open', title: 'Open App' }],
    },
  };
}

messaging.onBackgroundMessage(function (payload) {
  console.log('[firebase-messaging-sw] Background payload:', payload);

  if (payload && payload.notification) {
    console.log('[firebase-messaging-sw] Skip manual render: notification payload already exists.');
    return;
  }

  const notif = buildNotificationFromPayload(payload);
  return self.registration.showNotification(notif.title, notif.options);
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  const targetUrl = '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (const client of clientList) {
        if ('focus' in client) {
          client.postMessage({ type: 'notification-click', payload: event.notification.data || {} });
          return client.focus();
        }
      }

      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }

      return null;
    }),
  );
});
