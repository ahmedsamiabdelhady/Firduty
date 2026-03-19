// notification_service.dart — Cross-platform push notification service.
//
// Platforms:
//   Android  → FCM via firebase_messaging + flutter_local_notifications
//   Web/PWA  → FCM Web Push; background handled by firebase-messaging-sw.js
//
// dart:io is NOT imported — unavailable on Flutter Web.
// All platform branching uses kIsWeb from flutter/foundation.dart.
//
// ── Idempotency ─────────────────────────────────────────────────────────────
// initialize() is safe to call multiple times from multiple code paths:
//   • StartupScreen calls it when status == approved
//   • PendingScreen calls it after the admin approves the teacher
//   • The _initialized flag ensures all setup logic runs exactly once
//
// ── Background handler registration ────────────────────────────────────────
// FirebaseMessaging.onBackgroundMessage() must be a top-level function and
// must be registered before any other FCM call. It is called at most once,
// guarded by _backgroundHandlerRegistered.
//
// ── Stream subscription management ─────────────────────────────────────────
// onMessage and onTokenRefresh subscriptions are stored so they can be
// cancelled before reassignment. This prevents ghost listeners accumulating
// if the guard is somehow bypassed.

import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb, kDebugMode, debugPrint;
import 'package:flutter/material.dart' show GlobalKey, NavigatorState;
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../firebase_options.dart' show kVapidPublicKey;
import 'api_service.dart';

// ── Top-level background message handler ──────────────────────────────────────
// Must be a TOP-LEVEL function (not a static or closure).
// The @pragma annotation keeps it alive in release/AOT builds.
// Web background messages are handled by firebase-messaging-sw.js.
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // The OS renders the notification for background messages automatically.
  // Add local state update logic here if needed in the future.
  debugPrint('[FCM] Background message: ${message.messageId}');
}

// ─── NotificationService ─────────────────────────────────────────────────────

class NotificationService {
  NotificationService._(); // purely static — never instantiate

  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  // ── Idempotency guards ───────────────────────────────────────────────────

  /// True after initialize() has completed successfully at least once.
  static bool _initialized = false;

  /// True after the FCM background handler has been registered.
  /// Separate from _initialized because background handler must be
  /// registered as early as possible, before any other FCM call.
  static bool _backgroundHandlerRegistered = false;

  // ── Stream subscriptions (stored so we can cancel before reassigning) ────

  static StreamSubscription<RemoteMessage>? _onMessageSub;
  static StreamSubscription<String>?        _onTokenRefreshSub;

  // ────────────────────────────────────────────────────────────────────────

  /// Initialize FCM for an approved teacher.
  ///
  /// Idempotent — all work is silently skipped on the second call.
  /// Never throws — notification failures must not crash the app.
  ///
  /// [teacherId] The teacher's numeric ID from the backend.
  /// [platform]  'android' for the native APK, 'web' for Flutter web / iOS PWA.
  static Future<void> initialize({
    required int teacherId,
    required String platform,
  }) async {
    if (_initialized) {
      debugPrint('[NotificationService] Already initialized — skipping.');
      return;
    }

    debugPrint('[NotificationService] Starting (platform: $platform)…');

    try {
      if (kIsWeb) {
        await _initWeb(teacherId: teacherId);
      } else {
        await _initAndroid(teacherId: teacherId);
      }
      _initialized = true;
      debugPrint('[NotificationService] Ready.');
    } catch (e, st) {
      // Non-fatal: log and continue. Teachers can still view their schedule.
      debugPrint('[NotificationService] Failed to initialize: $e\n$st');
    }
  }

  // ── Android ───────────────────────────────────────────────────────────────

  static Future<void> _initAndroid({required int teacherId}) async {
    // 1. Register background handler FIRST, and only once.
    if (!_backgroundHandlerRegistered) {
      FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
      _backgroundHandlerRegistered = true;
    }

    // 2. Request notification permission (required on Android 13+ / API 33+).
    await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    // 3. Create the high-importance channel required on Android 8+ (API 26+).
    const channel = AndroidNotificationChannel(
      'firduty_channel',
      'Duty Notifications',
      description: 'Notifications about your duty assignments',
      importance: Importance.high,
    );
    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

    // 4. Initialise the local notifications plugin.
    await _localNotifications.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
    );

    // 5. Foreground message → local notification.
    //    Cancel before subscribing (belt-and-suspenders).
    await _onMessageSub?.cancel();
    _onMessageSub =
        FirebaseMessaging.onMessage.listen(_showLocalNotification);

    // 5b. Handle notification taps when app is in background (onMessageOpenedApp)
    //     or terminated (getInitialMessage). Both navigate to the Today screen.
    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    final initial = await _messaging.getInitialMessage();
    if (initial != null) _handleNotificationTap(initial);

    // 6. Get FCM token and register with the backend.
    final token = await _messaging.getToken();
    if (token != null) {
      await _registerToken(
          teacherId: teacherId, token: token, platform: 'android');
    }

    // 7. Refresh token when FCM rotates it.
    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
      await _registerToken(
          teacherId: teacherId, token: newToken, platform: 'android');
    });
  }

  // ── Web / iOS PWA ──────────────────────────────────────────────────────────

  static Future<void> _initWeb({required int teacherId}) async {
    // 1. Request browser notification permission.
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.denied) {
      debugPrint('[NotificationService] Web notification permission denied.');
      // Return without setting _initialized = true so a future call can retry.
      // This is handled by the outer try/catch not setting _initialized.
      // Re-throw to propagate to caller.
      throw Exception('Notification permission denied by user.');
    }

    // 2. Get FCM web registration token using VAPID key.
    //    kVapidPublicKey comes from firebase_options.dart.
    final token = await _messaging.getToken(vapidKey: kVapidPublicKey);
    if (token != null) {
      await _registerToken(
          teacherId: teacherId, token: token, platform: 'web');
    }

    // 3. Foreground message handler (background is handled by SW).
    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen((RemoteMessage msg) {
      if (kDebugMode) {
        debugPrint('[FCM Web] Foreground: ${msg.notification?.title}');
      }
      // TODO: show an in-app SnackBar banner here if desired.
    });

    // 4. Refresh token listener.
    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
      await _registerToken(
          teacherId: teacherId, token: newToken, platform: 'web');
    });
  }

  // ── Shared helpers ────────────────────────────────────────────────────────

  // ── Logout / reset ───────────────────────────────────────────────────────────
  /// Call this when a teacher logs out so the next login can re-register tokens.
  /// Cancels stream subscriptions and resets the idempotency guard.
  static Future<void> reset() async {
    await _onMessageSub?.cancel();
    await _onTokenRefreshSub?.cancel();
    _onMessageSub = null;
    _onTokenRefreshSub = null;
    _initialized = false;
    debugPrint('[NotificationService] Reset — ready for next login.');
  }

  // ── Navigator key ──────────────────────────────────────────────────────────
  // Set this from main.dart so we can navigate from notification taps
  // without a BuildContext.
  //
  //   NotificationService.navigatorKey = GlobalKey<NavigatorState>();
  //   MaterialApp(navigatorKey: NotificationService.navigatorKey, ...)
  //
  static GlobalKey<NavigatorState>? navigatorKey;

  /// Navigate to the Today screen in response to a notification tap.
  /// Works whether the app was backgrounded or terminated.
  static void _handleNotificationTap(RemoteMessage message) {
    debugPrint('[NotificationService] Notification tapped: ${message.messageId}');
    navigatorKey?.currentState?.pushNamedAndRemoveUntil(
      '/home',
      (route) => false,
    );
  }

  /// Register a device/web token with the Firduty backend.
  /// Errors are caught and logged — never rethrown.
  static Future<void> _registerToken({
    required int    teacherId,
    required String token,
    required String platform,
  }) async {
    try {
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token:     token,
        platform:  platform,
      );
      debugPrint('[NotificationService] Token registered ($platform).');
    } catch (e) {
      debugPrint('[NotificationService] Token registration failed: $e');
    }
  }

  /// Display a local notification while the app is foregrounded on Android.
  /// Web foreground notifications are handled differently (no local plugin).
  static Future<void> _showLocalNotification(RemoteMessage message) async {
    if (kIsWeb) return; // safety guard — this listener is never set on web

    final notification = message.notification;
    if (notification == null) return;

    await _localNotifications.show(
      notification.hashCode, // stable ID — suppresses duplicates
      notification.title,
      notification.body,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'firduty_channel',
          'Duty Notifications',
          importance: Importance.high,
          priority:   Priority.high,
          icon:        '@mipmap/ic_launcher',
        ),
        iOS: DarwinNotificationDetails(),
      ),
    );
  }
}
