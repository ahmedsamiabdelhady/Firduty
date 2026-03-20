// notification_service.dart — Cross-platform push notification service.
//
// Production token hygiene added:
//   - stable per-installation installation_id
//   - register token with installation_id
//   - delete backend token row for this installation on disable/reset
//
// NOTE:
//   This file assumes ApiService.registerDeviceToken(...) and
//   ApiService.deleteDeviceToken(...) support installationId.
//   If api_service.dart was not updated yet, add the same field there.

import 'dart:async';
import 'dart:html' as html;
import 'dart:math';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart'
    show ValueNotifier, debugPrint, kDebugMode, kIsWeb;
import 'package:flutter/material.dart' show GlobalKey, NavigatorState;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../firebase_options.dart' show kVapidPublicKey;
import 'api_service.dart';

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('[FCM] Background message: ${message.messageId}');
}

void handleLocalNotificationResponse(NotificationResponse response) {}

@pragma('vm:entry-point')
void handleBackgroundLocalNotificationResponse(NotificationResponse response) {}

enum NotificationBellState { unknown, loading, enabled, disabled }

class DeviceIdentityService {
  DeviceIdentityService._();

  static const String _installationIdKey = 'installation_id';

  static Future<String> getInstallationId() async {
    final prefs = await SharedPreferences.getInstance();
    var id = prefs.getString(_installationIdKey);
    if (id != null && id.isNotEmpty) return id;

    id = _generateInstallationId();
    await prefs.setString(_installationIdKey, id);
    return id;
  }

  static String _generateInstallationId() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-'
        '${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-'
        '${hex.substring(16, 20)}-'
        '${hex.substring(20, 32)}';
  }
}

class NotificationService {
  NotificationService._();

  static FirebaseMessaging get _messaging => FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  static const String _enabledKey = 'notifications_enabled';
  static final ValueNotifier<NotificationBellState> bellState =
      ValueNotifier(NotificationBellState.unknown);

  static bool _initialized = false;
  static bool _backgroundHandlerRegistered = false;
  static StreamSubscription<RemoteMessage>? _onMessageSub;
  static StreamSubscription<String>? _onTokenRefreshSub;
  static GlobalKey<NavigatorState>? navigatorKey;

  static Future<void> syncStatus() async {
    final prefs = await SharedPreferences.getInstance();
    final enabled = prefs.getBool(_enabledKey) ?? false;
    bellState.value =
        enabled ? NotificationBellState.enabled : NotificationBellState.disabled;
  }

  static Future<void> loadBellState() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedEnabled = prefs.getBool(_enabledKey) ?? false;

      if (!savedEnabled) {
        bellState.value = NotificationBellState.disabled;
        return;
      }

      final authorized = await _isAuthorized(promptForPermission: false);
      bellState.value = authorized
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;
    } catch (_) {
      bellState.value = NotificationBellState.unknown;
    }
  }

  static Future<void> initialize({
    required int teacherId,
    required String platform,
  }) async {
    await loadBellState();
    if (bellState.value != NotificationBellState.enabled) {
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
    if (bellState.value == NotificationBellState.loading) return;

    if (teacherId == null) {
      debugPrint('[NotificationService] No teacherId');
      bellState.value = NotificationBellState.disabled;
      return;
    }

    bellState.value = NotificationBellState.loading;

    try {
      final currentlyEnabled = await areNotificationsEnabled();
      debugPrint('[NotificationService] currentlyEnabled = $currentlyEnabled');

      if (currentlyEnabled) {
        await disable(teacherId: teacherId);
        bellState.value = NotificationBellState.disabled;
        debugPrint('[NotificationService] Notifications disabled by user.');
        return;
      }

      final enabled = await enable(teacherId: teacherId, platform: platform);
      debugPrint('[NotificationService] enable() returned = $enabled');

      bellState.value = enabled
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;
    } catch (e, st) {
      debugPrint('[NotificationService] Failed to initialize: $e
$st');
      rethrow;
    }
  }

  static Future<bool> areNotificationsEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    final savedEnabled = prefs.getBool(_enabledKey) ?? false;
    if (!savedEnabled) return false;

    return _isAuthorized(promptForPermission: false);
  }

  static Future<bool> enable({
    required int? teacherId,
    required String platform,
  }) async {
    debugPrint('[NotificationService] enable() started');

    final prefs = await SharedPreferences.getInstance();
    final authorized = await _isAuthorized(promptForPermission: true);
    debugPrint('[NotificationService] _isAuthorized(true) = $authorized');

    if (!authorized) {
      await prefs.setBool(_enabledKey, false);
      bellState.value = NotificationBellState.disabled;
      debugPrint('[NotificationService] Permission not granted.');
      return false;
    }

    await prefs.setBool(_enabledKey, true);
    bellState.value = NotificationBellState.enabled;

    if (teacherId != null) {
      try {
        await _configure(
          teacherId: teacherId,
          platform: platform,
          promptForPermission: false,
        );
      } catch (e, st) {
        debugPrint('[NotificationService] _configure failed: $e');
        debugPrint('$st');
        return false;
      }
    }

    return true;
  }

  static Future<void> disable({int? teacherId}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_enabledKey, false);

    try {
      if (teacherId != null) {
        final installationId = await DeviceIdentityService.getInstallationId();
        await ApiService.deleteDeviceToken(
          teacherId: teacherId,
          installationId: installationId,
        );
      }
    } catch (e) {
      debugPrint('[NotificationService] delete backend device token failed: $e');
    }

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

  static Future<void> reset({int? teacherId}) async {
    if (teacherId != null) {
      try {
        final installationId = await DeviceIdentityService.getInstallationId();
        await ApiService.deleteDeviceToken(
          teacherId: teacherId,
          installationId: installationId,
        );
      } catch (e) {
        debugPrint('[NotificationService] reset backend cleanup failed: $e');
      }
    }

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
      final authorized =
          await _isAuthorized(promptForPermission: promptForPermission);
      if (!authorized) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool(_enabledKey, false);
        bellState.value = NotificationBellState.disabled;
        return;
      }

      if (kIsWeb) {
        await _initWeb(teacherId: teacherId);
      } else {
        await _initAndroid(teacherId: teacherId);
      }

      _initialized = true;
      bellState.value = NotificationBellState.enabled;
      debugPrint('[NotificationService] Ready.');
    } catch (e, st) {
      debugPrint('[NotificationService] Failed to initialize: $e
$st');
    }
  }

  static Future<bool> _isAuthorized({required bool promptForPermission}) async {
    if (kIsWeb) {
      final currentPermission = html.Notification.permission;
      if (currentPermission == 'granted') return true;
      if (!promptForPermission) return false;
      final requested = await html.Notification.requestPermission();
      return requested == 'granted';
    }

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
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

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
    if (token != null && token.isNotEmpty) {
      await _registerToken(
        teacherId: teacherId,
        token: token,
        platform: 'android',
      );
    }

    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
      await _registerToken(
        teacherId: teacherId,
        token: newToken,
        platform: 'android',
      );
    });
  }

  static Future<void> _initWeb({required int teacherId}) async {
    try {
      await html.window.navigator.serviceWorker?.register('/firebase-messaging-sw.js');

      final token = await _messaging.getToken(vapidKey: kVapidPublicKey);
      if (token != null && token.isNotEmpty) {
        await _registerToken(
          teacherId: teacherId,
          token: token,
          platform: 'web',
        );
      }

      await _onMessageSub?.cancel();
      _onMessageSub = FirebaseMessaging.onMessage.listen((RemoteMessage msg) {
        if (kDebugMode) {
          debugPrint('[FCM Web] Foreground: ${msg.notification?.title}');
        }
      });

      await _onTokenRefreshSub?.cancel();
      _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
        await _registerToken(
          teacherId: teacherId,
          token: newToken,
          platform: 'web',
        );
      });
    } catch (e, st) {
      debugPrint('[FCM Web] getToken failed: $e');
      debugPrint('$st');
      rethrow;
    }
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
      final installationId = await DeviceIdentityService.getInstallationId();
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token: token,
        platform: platform,
        installationId: installationId,
      );
      debugPrint(
        '[NotificationService] Token registered ($platform, installation_id=$installationId).',
      );
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
