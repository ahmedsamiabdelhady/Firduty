import 'dart:async';
import 'dart:math';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../firebase_options.dart';
import 'api_service.dart';

enum NotificationBellState {
  enabled,
  disabled,
  loading,
  unknown,
}

class NotificationService {
  NotificationService._();

  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  static final ValueNotifier<NotificationBellState> bellState =
      ValueNotifier(NotificationBellState.unknown);

  static const String _kNotificationsEnabled = 'firduty_notifications_enabled';
  static const String _kInstallationId = 'firduty_installation_id';

  static bool _initialized = false;
  static bool _localNotificationsReady = false;
  static StreamSubscription<RemoteMessage>? _onMessageSub;
  static StreamSubscription<String>? _onTokenRefreshSub;
  static GlobalKey<NavigatorState>? navigatorKey;

  static String get _platform => kIsWeb ? 'web' : 'android';

  static Future<void> initialize({
    required int teacherId,
    GlobalKey<NavigatorState>? navigator,
  }) async {
    navigatorKey = navigator ?? navigatorKey;
    bellState.value = NotificationBellState.loading;

    final enabled = await _isUserEnabled();
    if (!enabled) {
      _initialized = false;
      bellState.value = NotificationBellState.disabled;
      return;
    }

    try {
      await _ensureFirebase();
      await _initializePlatform(teacherId: teacherId);
      _initialized = true;
      bellState.value = NotificationBellState.enabled;
    } catch (e) {
      debugPrint('[NotificationService] initialize failed: $e');
      _initialized = false;
      bellState.value = NotificationBellState.disabled;
    }
  }

  static Future<void> syncBellStateFromPrefs() async {
    final enabled = await _isUserEnabled();
    bellState.value = enabled
        ? NotificationBellState.enabled
        : NotificationBellState.disabled;
  }

  static Future<void> toggle({required int teacherId}) async {
    if (bellState.value == NotificationBellState.loading) return;

    final wasEnabled = await _isUserEnabled();
    bellState.value = NotificationBellState.loading;

    if (wasEnabled) {
      await _disableNotifications();
      return;
    }

    try {
      await _setUserEnabled(true);
      await initialize(teacherId: teacherId);
      if (bellState.value != NotificationBellState.enabled) {
        await _setUserEnabled(false);
        bellState.value = NotificationBellState.disabled;
      }
    } catch (e) {
      await _setUserEnabled(false);
      bellState.value = NotificationBellState.disabled;
      debugPrint('[NotificationService] toggle enable failed: $e');
    }
  }

  static Future<void> reset() async {
    await _onMessageSub?.cancel();
    await _onTokenRefreshSub?.cancel();
    _onMessageSub = null;
    _onTokenRefreshSub = null;
    _initialized = false;
    _localNotificationsReady = false;

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kNotificationsEnabled);
    bellState.value = NotificationBellState.disabled;
  }

  static Future<bool> _isUserEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_kNotificationsEnabled) ?? false;
  }

  static Future<void> _setUserEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kNotificationsEnabled, value);
  }

  static Future<void> _ensureFirebase() async {
    if (Firebase.apps.isNotEmpty) return;
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  }

  static Future<void> _initializePlatform({required int teacherId}) async {
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );

    final granted =
        settings.authorizationStatus == AuthorizationStatus.authorized ||
            settings.authorizationStatus == AuthorizationStatus.provisional;
    if (!granted) {
      throw Exception('Notification permission denied by user.');
    }

    if (!kIsWeb) {
      await _ensureLocalNotificationsReady();
      await _bindMessageStreamsForAndroid();
    } else {
      await _bindMessageStreamsForWeb();
    }

    final installationId = await _getInstallationId();
    final token = kIsWeb
        ? await _messaging.getToken(vapidKey: kVapidPublicKey)
        : await _messaging.getToken();

    if (token == null || token.isEmpty) {
      throw Exception('Could not obtain FCM token.');
    }

    await _registerToken(
      teacherId: teacherId,
      token: token,
      platform: _platform,
      installationId: installationId,
    );

    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((String refreshed) async {
      if (refreshed.isEmpty) return;
      try {
        await _registerToken(
          teacherId: teacherId,
          token: refreshed,
          platform: _platform,
          installationId: installationId,
        );
        debugPrint('[NotificationService] Token refreshed ($_platform)');
      } catch (e) {
        debugPrint('[NotificationService] Token refresh registration failed: $e');
      }
    });
  }

  static Future<void> _bindMessageStreamsForAndroid() async {
    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen(_showLocalNotification);

    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    final initial = await _messaging.getInitialMessage();
    if (initial != null) {
      _handleNotificationTap(initial);
    }
  }

  static Future<void> _bindMessageStreamsForWeb() async {
    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      debugPrint(
        '[FCM Web] Foreground message notification=${message.notification?.title} data=${message.data}',
      );
    });

    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    final initial = await _messaging.getInitialMessage();
    if (initial != null) {
      _handleNotificationTap(initial);
    }
  }

  static Future<void> _ensureLocalNotificationsReady() async {
    if (_localNotificationsReady || kIsWeb) return;

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const darwin = DarwinInitializationSettings();

    await _localNotifications.initialize(
      settings: InitializationSettings(android: android, iOS: darwin),
    );

    const channel = AndroidNotificationChannel(
      'firduty_channel',
      'Duty Notifications',
      description: 'Duty reminder and update notifications',
      importance: Importance.high,
    );

    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

    _localNotificationsReady = true;
  }

  static Future<void> _registerToken({
    required int teacherId,
    required String token,
    required String platform,
    required String installationId,
  }) async {
    await ApiService.registerDeviceToken(
      teacherId: teacherId,
      token: token,
      platform: platform,
      installationId: installationId,
    );
    debugPrint(
      '[NotificationService] Token registered ($platform) install=${installationId.substring(0, 8)}',
    );
  }

  static Future<void> _showLocalNotification(RemoteMessage message) async {
    if (kIsWeb) return;

    final title =
        (message.notification?.title ?? message.data['title'] ?? '').toString().trim();
    final body =
        (message.notification?.body ?? message.data['body'] ?? '').toString().trim();

    if (title.isEmpty && body.isEmpty) {
      debugPrint('[NotificationService] Skip local notification: empty payload');
      return;
    }

    await _ensureLocalNotificationsReady();

    await _localNotifications.show(
      id: (message.messageId ?? '${DateTime.now().millisecondsSinceEpoch}').hashCode,
      title: title.isEmpty ? 'Firduty' : title,
      body: body,
      notificationDetails: NotificationDetails(
        android: AndroidNotificationDetails(
          'firduty_channel',
          'Duty Notifications',
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      ),
      payload: message.data.toString(),
    );
  }

  static void _handleNotificationTap(RemoteMessage message) {
    debugPrint('[NotificationService] Notification tapped: ${message.messageId}');
    navigatorKey?.currentState?.pushNamedAndRemoveUntil('/home', (_) => false);
  }

  static Future<void> _disableNotifications() async {
    await _setUserEnabled(false);
    try {
      await _messaging.deleteToken();
    } catch (e) {
      debugPrint('[NotificationService] Local token delete failed: $e');
    }

    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = null;
    _initialized = false;
    bellState.value = NotificationBellState.disabled;
  }

  static Future<String> _getInstallationId() async {
    final prefs = await SharedPreferences.getInstance();
    final existing = prefs.getString(_kInstallationId);
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }

    final created = _generateInstallationId();
    await prefs.setString(_kInstallationId, created);
    return created;
  }

  static String _generateInstallationId() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));

    String hex(List<int> values) =>
        values.map((value) => value.toRadixString(16).padLeft(2, '0')).join();

    return '${hex(bytes.sublist(0, 4))}-'
        '${hex(bytes.sublist(4, 6))}-'
        '${hex(bytes.sublist(6, 8))}-'
        '${hex(bytes.sublist(8, 10))}-'
        '${hex(bytes.sublist(10, 16))}';
  }
}
