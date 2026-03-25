import 'dart:async';
import 'dart:math';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show ValueNotifier, debugPrint, kDebugMode, kIsWeb;
import 'package:flutter/material.dart' show GlobalKey, NavigatorState;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../firebase_options.dart' show kVapidPublicKey;
import 'api_service.dart';

const AndroidNotificationChannel _firdutyChannel = AndroidNotificationChannel(
  'firduty_channel',
  'Duty Notifications',
  description: 'Notifications about your duty assignments',
  importance: Importance.high,
);

int _stableNotificationId(Map<String, dynamic> data, String fallback) {
  final seed = [
    data['notification_type'],
    data['type'],
    data['assignment_id'],
    data['teacher_id'],
    data['day_date'],
    data['shift_name'],
  ].where((v) => v != null && v.toString().trim().isNotEmpty).join('|');

  return (seed.isNotEmpty ? seed : fallback).hashCode & 0x7fffffff;
}

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('[FCM] Background message: ${message.messageId} data=${message.data}');

  if (kIsWeb) return;

  final title = (message.data['title'] ?? message.notification?.title ?? '').toString().trim();
  final body = (message.data['body'] ?? message.notification?.body ?? '').toString().trim();

  if (title.isEmpty && body.isEmpty) {
    debugPrint('[FCM] Background skip: empty payload');
    return;
  }

  final plugin = FlutterLocalNotificationsPlugin();
  await plugin.initialize(
    settings:  InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      iOS: DarwinInitializationSettings(),
    ),
  );

  await plugin
      .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
      ?.createNotificationChannel(_firdutyChannel);

  await plugin.show(
    id:_stableNotificationId(message.data, message.messageId ?? 'firduty-bg'),
    title: title.isEmpty ? 'Firduty' : title,
    body: body,
    notificationDetails:  NotificationDetails(
      android: AndroidNotificationDetails(
        'firduty_channel',
        'Duty Notifications',
        channelDescription: 'Notifications about your duty assignments',
        importance: Importance.high,
        priority: Priority.high,
      ),
      iOS: DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      ),
    ),
  );
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
  static StreamSubscription? _onMessageSub;
  static StreamSubscription? _onTokenRefreshSub;

  static final ValueNotifier<NotificationBellState> bellState =
      ValueNotifier(NotificationBellState.unknown);

  static const String _kNotificationsEnabled = 'firduty_notifications_enabled';
  static const String _installationIdKey = 'firduty_installation_id';

  static String _currentPlatform = kIsWeb ? 'web' : 'android';
  static GlobalKey<NavigatorState>? navigatorKey;

  static Future<bool> _isUserEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_kNotificationsEnabled) ?? true;
  }

  static Future<void> _setUserEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kNotificationsEnabled, value);
  }

  static Future<void> syncBellStateFromPrefs() async {
    final enabled = await _isUserEnabled();
    bellState.value = enabled
        ? NotificationBellState.enabled
        : NotificationBellState.disabled;
  }

  static Future<void> initialize({
    required int teacherId,
    required String platform,
  }) async {
    _currentPlatform = platform;

    final userEnabled = await _isUserEnabled();
    if (!userEnabled) {
      bellState.value = NotificationBellState.disabled;
      debugPrint('[NotificationService] Notifications are disabled by user preference.');
      return;
    }

    if (_initialized) {
      bellState.value = NotificationBellState.enabled;
      debugPrint('[NotificationService] Already initialized — skipping.');
      return;
    }

    bellState.value = NotificationBellState.loading;
    try {
      debugPrint('[NotificationService] Starting (platform: $platform)...');
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
      final stillEnabled = await _isUserEnabled();
      bellState.value = stillEnabled
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;
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

    await _localNotifications
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(_firdutyChannel);

    await _localNotifications.initialize(
      settings:InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
    );

    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen(_showLocalNotification);

    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    final initial = await _messaging.getInitialMessage();
    if (initial != null) {
      _handleNotificationTap(initial);
    }

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
        debugPrint('[FCM Web] Foreground title=${msg.notification?.title} data=${msg.data}');
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
    final bytes = List.generate(16, (_) => rng.nextInt(256));
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

  static void _handleNotificationTap(RemoteMessage message) {
    debugPrint('[NotificationService] Notification tapped: ${message.messageId}');
    navigatorKey?.currentState?.pushNamedAndRemoveUntil('/home', (route) => false);
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
      debugPrint(
        '[NotificationService] Token registered ($platform) '
        'install=${installationId?.substring(0, 8) ?? "legacy"}',
      );
    } catch (e) {
      debugPrint('[NotificationService] Token registration failed: $e');
      rethrow;
    }
  }

  static Future<void> _showLocalNotification(RemoteMessage message) async {
    if (kIsWeb) return;

    final title = (message.data['title'] ?? message.notification?.title ?? '').toString().trim();
    final body = (message.data['body'] ?? message.notification?.body ?? '').toString().trim();

    if (title.isEmpty && body.isEmpty) {
      debugPrint('[NotificationService] Skip local notification: empty payload');
      return;
    }

    await _localNotifications.show(
      id: _stableNotificationId(message.data, message.messageId ?? 'firduty-fg'),
      title: title.isEmpty ? 'Firduty' : title,
      body: body,
      notificationDetails: NotificationDetails(
        android: AndroidNotificationDetails(
          'firduty_channel',
          'Duty Notifications',
          channelDescription: 'Notifications about your duty assignments',
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
        ),
      ),
    );
  }

  static Future<void> toggle({required int teacherId}) async {
    if (bellState.value == NotificationBellState.loading) return;

    final wasEnabled = await _isUserEnabled();
    bellState.value = NotificationBellState.loading;

    try {
      if (wasEnabled) {
        await _setUserEnabled(false);
        try {
          await _messaging.deleteToken();
        } catch (e) {
          debugPrint('[NotificationService] Local token delete failed: $e');
        }
        _initialized = false;
        bellState.value = NotificationBellState.disabled;
        debugPrint('[NotificationService] Notifications disabled for teacher $teacherId');
        return;
      }

      final settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );
      final granted = settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional;
      if (!granted) {
        await _setUserEnabled(false);
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

      await _setUserEnabled(true);
      _initialized = true;
      bellState.value = NotificationBellState.enabled;
      debugPrint('[NotificationService] Notifications enabled for teacher $teacherId');
    } catch (e, st) {
      debugPrint('[NotificationService] Toggle failed: $e\n$st');
      final restored = await _isUserEnabled();
      bellState.value = restored
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;
    }
  }
}
