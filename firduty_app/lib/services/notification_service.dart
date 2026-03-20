// notification_service.dart — Cross-platform push notification service.
//
// Platforms:
//   Android  → FCM via firebase_messaging + flutter_local_notifications
//   Web/PWA  → FCM Web Push; background handled by firebase-messaging-sw.js

import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show ValueNotifier, kDebugMode, kIsWeb, debugPrint;
import 'package:flutter/material.dart' show GlobalKey, NavigatorState;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../firebase_options.dart' show kVapidPublicKey;
import 'api_service.dart';

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('[FCM] Background message: ${message.messageId}');
}

class NotificationService {
  NotificationService._();

  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  static const String _enabledKey = 'notifications_enabled';

  static final ValueNotifier<bool> isEnabled = ValueNotifier<bool>(false);

  static bool _initialized = false;
  static bool _backgroundHandlerRegistered = false;

  static StreamSubscription<RemoteMessage>? _onMessageSub;
  static StreamSubscription<String>? _onTokenRefreshSub;

  static GlobalKey<NavigatorState>? navigatorKey;

  static Future<void> syncStatus() async {
    final prefs = await SharedPreferences.getInstance();
    isEnabled.value = prefs.getBool(_enabledKey) ?? false;
  }

  static Future<void> initialize({
    required int teacherId,
    required String platform,
  }) async {
    await syncStatus();
    if (!isEnabled.value) {
      debugPrint('[NotificationService] Notifications disabled — skipping setup.');
      return;
    }
    await _configure(
      teacherId: teacherId,
      platform: platform,
      promptForPermission: false,
    );
  }

  static Future<void> toggle({
    required int? teacherId,
    required String platform,
  }) async {
    await syncStatus();
    if (isEnabled.value) {
      await disable();
    } else {
      await enable(teacherId: teacherId, platform: platform);
    }
  }

  static Future<void> enable({
    required int? teacherId,
    required String platform,
  }) async {
    final prefs = await SharedPreferences.getInstance();

    final authorized = await _isAuthorized(promptForPermission: true);
    if (!authorized) {
      await prefs.setBool(_enabledKey, false);
      isEnabled.value = false;
      return;
    }

    await prefs.setBool(_enabledKey, true);
    isEnabled.value = true;

    if (teacherId != null) {
      await _configure(
        teacherId: teacherId,
        platform: platform,
        promptForPermission: false,
      );
    }
  }

  static Future<void> disable() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_enabledKey, false);
    isEnabled.value = false;

    try {
      await _messaging.deleteToken();
    } catch (e) {
      debugPrint('[NotificationService] deleteToken failed: $e');
    }

    await _onMessageSub?.cancel();
    await _onTokenRefreshSub?.cancel();
    _onMessageSub = null;
    _onTokenRefreshSub = null;
    _initialized = false;
  }

  static Future<void> reset() async {
    await _onMessageSub?.cancel();
    await _onTokenRefreshSub?.cancel();
    _onMessageSub = null;
    _onTokenRefreshSub = null;
    _initialized = false;
    debugPrint('[NotificationService] Reset — ready for next login.');
  }

  static Future<void> _configure({
    required int teacherId,
    required String platform,
    required bool promptForPermission,
  }) async {
    if (_initialized) {
      debugPrint('[NotificationService] Already initialized — skipping.');
      return;
    }

    try {
      final authorized = await _isAuthorized(promptForPermission: promptForPermission);
      if (!authorized) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool(_enabledKey, false);
        isEnabled.value = false;
        return;
      }

      if (kIsWeb) {
        await _initWeb(teacherId: teacherId);
      } else {
        await _initAndroid(teacherId: teacherId);
      }

      _initialized = true;
      debugPrint('[NotificationService] Ready.');
    } catch (e, st) {
      debugPrint('[NotificationService] Failed to initialize: $e\n$st');
    }
  }

  static Future<bool> _isAuthorized({required bool promptForPermission}) async {
    final current = await _messaging.getNotificationSettings();
    if (current.authorizationStatus == AuthorizationStatus.authorized ||
        current.authorizationStatus == AuthorizationStatus.provisional) {
      return true;
    }
    if (!promptForPermission) return false;

    final requested = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );
    return requested.authorizationStatus == AuthorizationStatus.authorized ||
        requested.authorizationStatus == AuthorizationStatus.provisional;
  }

  static Future<void> _initAndroid({required int teacherId}) async {
    if (!_backgroundHandlerRegistered) {
      FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
      _backgroundHandlerRegistered = true;
    }

    const channel = AndroidNotificationChannel(
      'firduty_channel',
      'Duty Notifications',
      description: 'Notifications about your duty assignments',
      importance: Importance.high,
    );
    await _localNotifications
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

    void handleLocalNotificationResponse(NotificationResponse response) {
      // handle tap
    }

    @pragma('vm:entry-point')
    void handleBackgroundLocalNotificationResponse(NotificationResponse response) {
      // handle background tap
    }
    await _localNotifications.initialize(
  settings: const InitializationSettings(
    android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    iOS: DarwinInitializationSettings(),
  ),
    onDidReceiveNotificationResponse: handleLocalNotificationResponse,

    onDidReceiveBackgroundNotificationResponse:
        handleBackgroundLocalNotificationResponse,
  );

    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen(_showLocalNotification);

    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    final initial = await _messaging.getInitialMessage();
    if (initial != null) _handleNotificationTap(initial);

    final token = await _messaging.getToken();
    if (token != null) {
      await _registerToken(teacherId: teacherId, token: token, platform: 'android');
    }

    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
      await _registerToken(teacherId: teacherId, token: newToken, platform: 'android');
    });
  }

  static Future<void> _initWeb({required int teacherId}) async {
    final token = await _messaging.getToken(vapidKey: kVapidPublicKey);
    if (token != null) {
      await _registerToken(teacherId: teacherId, token: token, platform: 'web');
    }

    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen((RemoteMessage msg) {
      if (kDebugMode) {
        debugPrint('[FCM Web] Foreground: ${msg.notification?.title}');
      }
    });

    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
      await _registerToken(teacherId: teacherId, token: newToken, platform: 'web');
    });
  }

  static void _handleNotificationTap(RemoteMessage message) {
    debugPrint('[NotificationService] Notification tapped: ${message.messageId}');
    navigatorKey?.currentState?.pushNamedAndRemoveUntil('/home', (route) => false);
  }

  static Future<void> _registerToken({
    required int teacherId,
    required String token,
    required String platform,
  }) async {
    try {
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token: token,
        platform: platform,
      );
      debugPrint('[NotificationService] Token registered ($platform).');
    } catch (e) {
      debugPrint('[NotificationService] Token registration failed: $e');
    }
  }

  static Future<void> _showLocalNotification(RemoteMessage message) async {
    if (kIsWeb) return;

    final notification = message.notification;
    if (notification == null) return;

    await _localNotifications.show(
      id: notification.hashCode,
      title: notification.title,
      body: notification.body,
      notificationDetails: const NotificationDetails(
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
