// notification_service.dart — Cross-platform push notification service.
//
// Platform routing:
//   Android  → Firebase Cloud Messaging (FCM) via firebase_messaging
//              + flutter_local_notifications for foreground display
//   Web/PWA  → FCM Web Push (Firebase JS SDK in service worker)
//              Foreground messages handled inline; background via SW.
//
// dart:io is NOT imported — unavailable on Flutter Web.
// All platform branching uses kIsWeb from flutter/foundation.dart.

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import '../firebase_options.dart' show kVapidPublicKey;
import 'api_service.dart';

// ── Background handler (native Android only) ──────────────────────────────────
// This pragma is ignored on web — background push is handled by the
// firebase-messaging-sw.js service worker instead.
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // The OS handles the notification display for background messages.
  // No action needed here unless you want to update local state.
}

class NotificationService {
  static final _messaging = FirebaseMessaging.instance;

  // Local notifications plugin — Android only (not supported on web).
  static final _localNotifications = FlutterLocalNotificationsPlugin();

  /// Initialize notifications for an approved teacher.
  ///
  /// [platform] should be 'android' for the native app or 'web' for the
  /// Flutter web build (including iOS PWA). The backend uses this to route
  /// notifications via the correct delivery path.
  static Future<void> initialize({
    required int teacherId,
    required String platform,
  }) async {
    if (kIsWeb) {
      await _initWeb(teacherId: teacherId);
    } else {
      await _initAndroid(teacherId: teacherId);
    }
  }

  // ── Android / Native ────────────────────────────────────────────────────────

  static Future<void> _initAndroid({required int teacherId}) async {
    // Register background handler
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Request permission (required on Android 13+)
    await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    // Create the Android notification channel
    const androidChannel = AndroidNotificationChannel(
      'firduty_channel',
      'Duty Notifications',
      description: 'Notifications about your duty assignments',
      importance: Importance.high,
    );
    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(androidChannel);

    // Initialize local notifications plugin (Android + iOS native)
    await _localNotifications.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
    );

    // Show local notification when app is in foreground
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      _showLocalNotification(message);
    });

    // Get FCM token and register with backend
    final token = await _messaging.getToken();
    if (token != null) {
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token: token,
        platform: 'android',
      );
    }

    // Re-register on token refresh
    _messaging.onTokenRefresh.listen((newToken) async {
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token: newToken,
        platform: 'android',
      );
    });
  }

  // ── Web / iOS PWA ───────────────────────────────────────────────────────────

  static Future<void> _initWeb({required int teacherId}) async {
    // Request Notification permission via the browser
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.denied) {
      // User denied — notifications will not work. App continues to function.
      return;
    }

    // Get FCM web registration token.
    // vapidKey is the Web Push VAPID public key from Firebase Console →
    // Project Settings → Cloud Messaging → Web Push certificates.
    final token = await _messaging.getToken(vapidKey: kVapidPublicKey);
    if (token != null) {
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token: token,
        platform: 'web',
      );
    }

    // Foreground message handler on web
    // (background messages are handled by firebase-messaging-sw.js)
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      // On web, we can't use flutter_local_notifications.
      // The message arrives here when the app tab is open and focused.
      // We could show a custom in-app banner, but for now we log it.
      // TODO: show a SnackBar/banner using a global key if desired.
      if (kDebugMode) {
        debugPrint('[FCM Web] Foreground message: ${message.notification?.title}');
      }
    });

    // Re-register on token refresh
    _messaging.onTokenRefresh.listen((newToken) async {
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token: newToken,
        platform: 'web',
      );
    });
  }

  // ── Private helpers ─────────────────────────────────────────────────────────

  /// Show a local notification — Android only.
  /// Web background notifications are displayed by the service worker.
  static Future<void> _showLocalNotification(RemoteMessage message) async {
    if (kIsWeb) return; // never called on web, but guard anyway

    final notification = message.notification;
    if (notification == null) return;

    await _localNotifications.show(
      notification.hashCode,
      notification.title,
      notification.body,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'firduty_channel',
          'Duty Notifications',
          importance: Importance.high,
          priority: Priority.high,
          icon: '@mipmap/ic_launcher',
        ),
        iOS: DarwinNotificationDetails(),
      ),
    );
  }
}

// ── Debug helper ───────────────────────────────────────────────────────────────
// ignore: avoid_print
void debugPrint(String message) => kDebugMode ? print(message) : null;
// ignore: constant_identifier_names
const bool kDebugMode = bool.fromEnvironment('dart.vm.product') == false;