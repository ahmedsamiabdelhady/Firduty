import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart' show kIsWeb, kDebugMode, debugPrint, ValueNotifier;
import 'package:flutter/material.dart' show GlobalKey, NavigatorState;
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../firebase_options.dart' show kVapidPublicKey;
import 'api_service.dart';

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('[FCM] Background message: ${message.messageId}');
}

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

  static bool _initialized = false;
  static bool _backgroundHandlerRegistered = false;

  static StreamSubscription<RemoteMessage>? _onMessageSub;
  static StreamSubscription<String>? _onTokenRefreshSub;

  static final ValueNotifier<NotificationBellState> bellState =
      ValueNotifier(NotificationBellState.unknown);

  static const _kNotificationsEnabled = 'firduty_notifications_enabled';
  static String _currentPlatform = kIsWeb ? 'web' : 'android';

  static Future<void> initialize({
    required int teacherId,
    required String platform,
  }) async {
    _currentPlatform = platform;

    try {
      final prefs = await SharedPreferences.getInstance();
      final savedEnabled = prefs.getBool(_kNotificationsEnabled) ?? true;

      if (!savedEnabled) {
        bellState.value = NotificationBellState.disabled;
        debugPrint('[NotificationService] Notifications are disabled by user preference.');
        return;
      }

      if (_initialized) {
        bellState.value = NotificationBellState.enabled;
        debugPrint('[NotificationService] Already initialized — skipping.');
        return;
      }

      debugPrint('[NotificationService] Starting (platform: $platform)…');

      if (kIsWeb) {
        await _initWeb(teacherId: teacherId);
      } else {
        await _initAndroid(teacherId: teacherId);
      }

      _initialized = true;
      bellState.value = NotificationBellState.enabled;
      debugPrint('[NotificationService] Ready. bellState=${bellState.value}');
    } catch (e, st) {
      debugPrint('[NotificationService] Failed to initialize: $e\n$st');
      bellState.value = NotificationBellState.disabled;
    }
  }

  static Future<void> _initAndroid({required int teacherId}) async {
    if (!_backgroundHandlerRegistered) {
      FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
      _backgroundHandlerRegistered = true;
    }

    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    final granted = settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;

    if (!granted) {
      throw Exception('Notification permission denied on Android.');
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
    );

    await _onMessageSub?.cancel();
      _onMessageSub = FirebaseMessaging.onMessage.listen((RemoteMessage msg) async {
        if (kDebugMode) {
          debugPrint('[FCM] Foreground message received: ${msg.data}');
        }
        await _showLocalNotification(msg);
      });

    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    final initial = await _messaging.getInitialMessage();
    if (initial != null) _handleNotificationTap(initial);

    final installationId = await _getInstallationId();
    final token = await _messaging.getToken();
    if (token == null || token.isEmpty) {
      throw Exception('FCM token was null on Android.');
    }

    await _registerToken(
      teacherId: teacherId,
      token: token,
      platform: 'android',
      installationId: installationId,
    );

    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
      await _registerToken(
        teacherId: teacherId,
        token: newToken,
        platform: 'android',
        installationId: installationId,
      );
    });
  }

  static Future<void> _initWeb({required int teacherId}) async {
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    final granted = settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;

    if (!granted) {
      throw Exception('Notification permission denied by user.');
    }

    final installationId = await _getInstallationId();
    final token = await _messaging.getToken(vapidKey: kVapidPublicKey);
    if (token == null || token.isEmpty) {
      throw Exception('FCM web token was null.');
    }

    await _registerToken(
      teacherId: teacherId,
      token: token,
      platform: 'web',
      installationId: installationId,
    );

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
        installationId: installationId,
      );
    });
  }

  static const _installationIdKey = 'firduty_installation_id';

  static Future<String> _getInstallationId() async {
    final prefs = await SharedPreferences.getInstance();
    String? id = prefs.getString(_installationIdKey);
    if (id == null || id.isEmpty) {
      id = _generateUuidV4();
      await prefs.setString(_installationIdKey, id);
      debugPrint('[NotificationService] Generated new installation_id: $id');
    }
    return id;
  }

  static String _generateUuidV4() {
    final rng = Random.secure();
    final bytes = List<int>.generate(16, (_) => rng.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    String hex(List<int> b) =>
        b.map((v) => v.toRadixString(16).padLeft(2, '0')).join();
    return '${hex(bytes.sublist(0, 4))}-'
        '${hex(bytes.sublist(4, 6))}-'
        '${hex(bytes.sublist(6, 8))}-'
        '${hex(bytes.sublist(8, 10))}-'
        '${hex(bytes.sublist(10, 16))}';
  }

  static Future<void> reset() async {
    await _onMessageSub?.cancel();
    await _onTokenRefreshSub?.cancel();
    _onMessageSub = null;
    _onTokenRefreshSub = null;
    _initialized = false;
    bellState.value = NotificationBellState.unknown;
    debugPrint('[NotificationService] Reset — ready for next login.');
  }

  static GlobalKey<NavigatorState>? navigatorKey;

  static void _handleNotificationTap(RemoteMessage message) {
    debugPrint('[NotificationService] Notification tapped: ${message.messageId}');
    navigatorKey?.currentState?.pushNamedAndRemoveUntil(
      '/home',
      (route) => false,
    );
  }

  static Future<void> _registerToken({
    required int teacherId,
    required String token,
    required String platform,
    String? installationId,
  }) async {
    try {
      await ApiService.registerDeviceToken(
        teacherId: teacherId,
        token: token,
        platform: platform,
        installationId: installationId,
      );
      debugPrint('[NotificationService] Token registered ($platform) '
          'install=${installationId?.substring(0, 8) ?? "legacy"}');
    } catch (e) {
      debugPrint('[NotificationService] Token registration failed: $e');
      rethrow;
    }
  }

  static Future<void> _showLocalNotification(RemoteMessage message) async {
  if (kIsWeb) return;

  final data = message.data;
  final title = (data['title'] ?? '').toString().trim();
  final body = (data['body'] ?? '').toString().trim();

  if (title.isEmpty && body.isEmpty) {
    debugPrint('[NotificationService] Skipping local notification: empty data payload.');
    return;
  }

  final notifId = Object.hash(
    data['type'] ?? '',
    data['assignment_id'] ?? '',
    data['teacher_id'] ?? '',
    title,
    body,
  );

    await _localNotifications.show(
    id: notifId,
    title: title,
    body: body,
    notificationDetails: const NotificationDetails(
      android: AndroidNotificationDetails(
        'firduty_channel',
        'Duty Notifications',
        channelDescription: 'Notifications about your duty assignments',
        importance: Importance.high,
        priority: Priority.high,
      ),
      iOS: DarwinNotificationDetails(),
    ),
  );
}

  static Future<void> toggle({required int teacherId}) async {
    if (bellState.value == NotificationBellState.loading) return;

    final previous = bellState.value;
    bellState.value = NotificationBellState.loading;

    try {
      if (previous == NotificationBellState.enabled) {
        await _messaging.deleteToken();
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool(_kNotificationsEnabled, false);
        _initialized = false;
        bellState.value = NotificationBellState.disabled;
        debugPrint('[NotificationService] Notifications disabled for teacher $teacherId');
      } else {
        final settings = await _messaging.requestPermission(
          alert: true,
          badge: true,
          sound: true,
        );

        final granted = settings.authorizationStatus == AuthorizationStatus.authorized ||
            settings.authorizationStatus == AuthorizationStatus.provisional;

        if (!granted) {
          final prefs = await SharedPreferences.getInstance();
          await prefs.setBool(_kNotificationsEnabled, false);
          bellState.value = NotificationBellState.disabled;
          debugPrint('[NotificationService] Permission denied — cannot enable.');
          return;
        }

        final installationId = await _getInstallationId();
        final token = kIsWeb
            ? await _messaging.getToken(vapidKey: kVapidPublicKey)
            : await _messaging.getToken();

        if (token == null || token.isEmpty) {
          throw Exception('Could not obtain FCM token while enabling notifications.');
        }

        await _registerToken(
          teacherId: teacherId,
          token: token,
          platform: _currentPlatform,
          installationId: installationId,
        );

        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool(_kNotificationsEnabled, true);
        _initialized = true;
        bellState.value = NotificationBellState.enabled;
        debugPrint('[NotificationService] Notifications enabled for teacher $teacherId');
      }
    } catch (e, st) {
      debugPrint('[NotificationService] Toggle failed: $e\n$st');
      bellState.value = previous == NotificationBellState.enabled
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;
    }
  }
}
