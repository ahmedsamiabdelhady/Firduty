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

function buildNotificationFromPayload(payload) {
  const data = payload?.data || {};
  const title = (data.title || '').trim();
  const body = (data.body || '').trim();
  const assignmentId = data.assignment_id || 'firduty-notification';

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
      tag: `${data.type || 'general'}-${assignmentId}`,
      renotify: false,
      actions: [{ action: 'open', title: 'Open App' }],
    },
  };
}

messaging.onBackgroundMessage(function (payload) {
  console.log('[firebase-messaging-sw] Background payload:', payload);

  // Prevent double notifications on web/iOS PWA.
  // If FCM already supplied a notification payload, let the browser show it.
  if (payload && payload.notification) {
    console.log('[firebase-messaging-sw] Skip manual render: notification payload already exists.');
    return;
  }

  const notif = buildNotificationFromPayload(payload);
  if (!notif) {
    console.log('[firebase-messaging-sw] Skip manual render: empty title/body.');
    return;
  }

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
