import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart'
    show ValueNotifier, debugPrint, kDebugMode, kIsWeb;
import 'package:flutter/material.dart' show GlobalKey, NavigatorState;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../firebase_options.dart'
    show DefaultFirebaseOptions, kVapidPublicKey;
import 'api_service.dart';

enum NotificationBellState {
  enabled,
  disabled,
  loading,
  unknown,
}

enum FirdutyNotificationType {
  update,
  reminder,
  started,
  unknown,
}

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  } catch (_) {
    // Firebase may already be initialized in the background isolate.
  }

  debugPrint(
    '[FCM] Background message received: '
    'id=${message.messageId} '
    'type=${message.data['type'] ?? message.data['notification_type'] ?? 'unknown'}',
  );

  if (!kIsWeb) {
    await NotificationService._showLocalNotificationFromRemoteMessage(message);
  }
}

class NotificationService {
  NotificationService._();

  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  static bool _initialized = false;
  static bool _backgroundHandlerRegistered = false;
  static bool _localNotificationsInitialized = false;

  static StreamSubscription<RemoteMessage>? _onMessageSub;
  static StreamSubscription<String>? _onTokenRefreshSub;
  static StreamSubscription<RemoteMessage>? _onMessageOpenedAppSub;

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
    bellState.value =
        enabled ? NotificationBellState.enabled : NotificationBellState.disabled;
  }

  static Future<void> initialize({
    required int teacherId,
    required String platform,
  }) async {
    _currentPlatform = platform;

    final userEnabled = await _isUserEnabled();
    if (!userEnabled) {
      bellState.value = NotificationBellState.disabled;
      debugPrint(
        '[NotificationService] Notifications are disabled by user preference.',
      );
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

      if (!kIsWeb) {
        await _ensureLocalNotificationsInitialized();
      }

      if (kIsWeb) {
        await _initWeb(teacherId: teacherId);
      } else {
        await _initAndroid(teacherId: teacherId);
      }

      _initialized = true;
      bellState.value = NotificationBellState.enabled;
      debugPrint(
        '[NotificationService] Ready. bellState=${bellState.value}',
      );
    } catch (e, st) {
      debugPrint('[NotificationService] Failed to initialize: $e\n$st');

      // Do not visually turn notifications off unless the user explicitly
      // disabled them. A transient startup/network/token failure should not
      // reset the bell to disabled.
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

    final granted =
        settings.authorizationStatus == AuthorizationStatus.authorized ||
            settings.authorizationStatus == AuthorizationStatus.provisional;

    if (!granted) {
      throw Exception('Notification permission denied on Android.');
    }

    await _messaging.setForegroundNotificationPresentationOptions(
      alert: true,
      badge: true,
      sound: true,
    );

    await _attachMessageListeners();

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

    final granted =
        settings.authorizationStatus == AuthorizationStatus.authorized ||
            settings.authorizationStatus == AuthorizationStatus.provisional;

    if (!granted) {
      throw Exception('Notification permission denied by user.');
    }

    await _attachMessageListeners();

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

  static Future<void> _attachMessageListeners() async {
    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen((RemoteMessage message) async {
      debugPrint(
        '[FCM] Foreground message: '
        'id=${message.messageId} '
        'type=${message.data['type'] ?? message.data['notification_type'] ?? 'unknown'} '
        'title=${message.notification?.title ?? message.data['title']}',
      );

      await _showLocalNotificationFromRemoteMessage(message);
    });

    await _onMessageOpenedAppSub?.cancel();
    _onMessageOpenedAppSub =
        FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);

    final initial = await _messaging.getInitialMessage();
    if (initial != null) {
      _handleNotificationTap(initial);
    }
  }

  static Future<void> _ensureLocalNotificationsInitialized() async {
    if (_localNotificationsInitialized || kIsWeb) return;

    const channel = AndroidNotificationChannel(
      'firduty_channel',
      'Duty Notifications',
      description: 'Notifications about your duty assignments',
      importance: Importance.high,
    );

    final androidPlugin =
        _localNotifications.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();

    await androidPlugin?.createNotificationChannel(channel);

    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const darwinSettings = DarwinInitializationSettings();

    await _localNotifications.initialize(
      settings: InitializationSettings(
        android: androidSettings,
        iOS: darwinSettings,
      ),
      onDidReceiveNotificationResponse: (NotificationResponse response) {
        _handleLocalNotificationTap(response.payload);
      },
      onDidReceiveBackgroundNotificationResponse:
          _onDidReceiveBackgroundNotificationResponse,
    );

    _localNotificationsInitialized = true;
    debugPrint('[NotificationService] Local notifications initialized.');
  }

  @pragma('vm:entry-point')
  static void _onDidReceiveBackgroundNotificationResponse(
    NotificationResponse response,
  ) {
    debugPrint(
      '[NotificationService] Background local notification tapped: '
      'payload=${response.payload}',
    );
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
    await _onMessageOpenedAppSub?.cancel();

    _onMessageSub = null;
    _onTokenRefreshSub = null;
    _onMessageOpenedAppSub = null;

    _initialized = false;
    bellState.value = NotificationBellState.unknown;

    debugPrint('[NotificationService] Reset — ready for next login.');
  }

  static void _handleNotificationTap(RemoteMessage message) {
    final payload = _buildPayload(message);

    debugPrint(
      '[NotificationService] Notification tapped: '
      'id=${message.messageId} payload=$payload',
    );

    navigatorKey?.currentState?.pushNamedAndRemoveUntil(
      '/home',
      (route) => false,
    );
  }

  static void _handleLocalNotificationTap(String? payload) {
    debugPrint('[NotificationService] Local notification tapped: $payload');

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

      debugPrint(
        '[NotificationService] Token registered ($platform) '
        'install=${installationId?.substring(0, 8) ?? "legacy"}',
      );
    } catch (e) {
      debugPrint('[NotificationService] Token registration failed: $e');
      rethrow;
    }
  }

  static Future<void> _showLocalNotificationFromRemoteMessage(
    RemoteMessage message,
  ) async {
    if (kIsWeb) {
      if (kDebugMode) {
        debugPrint(
          '[FCM Web] Message received. '
          'type=${message.data['type'] ?? message.data['notification_type'] ?? 'unknown'} '
          'title=${message.notification?.title ?? message.data['title']}',
        );
      }
      return;
    }

    await _ensureLocalNotificationsInitialized();

    final title = _extractTitle(message);
    final body = _extractBody(message);

    if ((title == null || title.trim().isEmpty) &&
        (body == null || body.trim().isEmpty)) {
      debugPrint(
        '[NotificationService] Skipping local notification: empty title/body. '
        'data=${message.data}',
      );
      return;
    }

    final type = _extractNotificationType(message);
    final notificationId = _buildNotificationId(message, type);
    final payload = _buildPayload(message);

    final androidDetails = AndroidNotificationDetails(
      'firduty_channel',
      'Duty Notifications',
      channelDescription: 'Notifications about your duty assignments',
      importance: Importance.high,
      priority: Priority.high,
      playSound: true,
      ticker: 'ticker',
      category: _androidCategoryForType(type),
      styleInformation: const DefaultStyleInformation(true, true),
    );

    await _localNotifications.show(
      id: notificationId,
      title:title,
      body: body,
      notificationDetails: NotificationDetails(android: androidDetails),
      payload: payload,
    );

    debugPrint(
      '[NotificationService] Local notification shown: '
      'id=$notificationId type=$type title=$title body=$body',
    );
  }

  static String? _extractTitle(RemoteMessage message) {
    final notificationTitle = message.notification?.title;
    if (notificationTitle != null && notificationTitle.trim().isNotEmpty) {
      return notificationTitle.trim();
    }

    final data = message.data;

    final candidates = <String?>[
      data['title'],
      data['notification_title'],
      data['notif_title'],
      data['subject'],
    ];

    for (final value in candidates) {
      if (value != null && value.trim().isNotEmpty) {
        return value.trim();
      }
    }

    switch (_extractNotificationType(message)) {
      case FirdutyNotificationType.update:
        return 'Duty updated';
      case FirdutyNotificationType.reminder:
        return 'Duty reminder';
      case FirdutyNotificationType.started:
        return 'Duty started';
      case FirdutyNotificationType.unknown:
        return 'Firduty';
    }
  }

  static String? _extractBody(RemoteMessage message) {
    final notificationBody = message.notification?.body;
    if (notificationBody != null && notificationBody.trim().isNotEmpty) {
      return notificationBody.trim();
    }

    final data = message.data;

    final candidates = <String?>[
      data['body'],
      data['notification_body'],
      data['notif_body'],
      data['message'],
      data['text'],
    ];

    for (final value in candidates) {
      if (value != null && value.trim().isNotEmpty) {
        return value.trim();
      }
    }

    switch (_extractNotificationType(message)) {
      case FirdutyNotificationType.update:
        return 'Your duty assignment has been updated.';
      case FirdutyNotificationType.reminder:
        return 'Your duty starts in 15 minutes.';
      case FirdutyNotificationType.started:
        return 'Your duty has started now.';
      case FirdutyNotificationType.unknown:
        return 'You have a new duty notification.';
    }
  }

  static FirdutyNotificationType _extractNotificationType(RemoteMessage message) {
    final raw = (message.data['type'] ??
            message.data['notification_type'] ??
            message.data['event'] ??
            '')
        .toString()
        .trim()
        .toLowerCase();

    if (raw.contains('update')) return FirdutyNotificationType.update;
    if (raw.contains('reminder')) return FirdutyNotificationType.reminder;
    if (raw.contains('start')) return FirdutyNotificationType.started;

    return FirdutyNotificationType.unknown;
  }

  static AndroidNotificationCategory _androidCategoryForType(
  FirdutyNotificationType type,
) {
  switch (type) {
    case FirdutyNotificationType.update:
      return AndroidNotificationCategory.status;
    case FirdutyNotificationType.reminder:
      return AndroidNotificationCategory.reminder;
    case FirdutyNotificationType.started:
      return AndroidNotificationCategory.alarm;
    case FirdutyNotificationType.unknown:
      return AndroidNotificationCategory.status;
  }
}

  static int _buildNotificationId(
    RemoteMessage message,
    FirdutyNotificationType type,
  ) {
    final assignmentId =
        int.tryParse((message.data['assignment_id'] ?? '').toString()) ?? 0;

    final teacherId =
        int.tryParse((message.data['teacher_id'] ?? '').toString()) ?? 0;

    final typeBase = switch (type) {
      FirdutyNotificationType.update => 1000000,
      FirdutyNotificationType.reminder => 2000000,
      FirdutyNotificationType.started => 3000000,
      FirdutyNotificationType.unknown => 4000000,
    };

    if (assignmentId != 0) {
      return typeBase + assignmentId;
    }

    if (message.messageId != null && message.messageId!.isNotEmpty) {
      return typeBase + message.messageId.hashCode.abs();
    }

    return typeBase + teacherId + DateTime.now().millisecondsSinceEpoch.remainder(100000);
  }

  static String _buildPayload(RemoteMessage message) {
    return jsonEncode({
      'messageId': message.messageId,
      'type': message.data['type'] ?? message.data['notification_type'],
      'assignment_id': message.data['assignment_id'],
      'teacher_id': message.data['teacher_id'],
      'day_date': message.data['day_date'],
      'shift_name': message.data['shift_name'],
      'title': _extractTitle(message),
      'body': _extractBody(message),
      'data': message.data,
    });
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

        debugPrint(
          '[NotificationService] Notifications disabled for teacher $teacherId',
        );
        return;
      }

      final settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );

      final granted =
          settings.authorizationStatus == AuthorizationStatus.authorized ||
              settings.authorizationStatus ==
                  AuthorizationStatus.provisional;

      if (!granted) {
        await _setUserEnabled(false);
        bellState.value = NotificationBellState.disabled;
        debugPrint('[NotificationService] Permission denied — cannot enable.');
        return;
      }

      if (!kIsWeb) {
        await _ensureLocalNotificationsInitialized();
      }

      final installationId = await _getInstallationId();
      final token = kIsWeb
          ? await _messaging.getToken(vapidKey: kVapidPublicKey)
          : await _messaging.getToken();

      if (token == null || token.isEmpty) {
        throw Exception(
          'Could not obtain FCM token while enabling notifications.',
        );
      }

      await _registerToken(
        teacherId: teacherId,
        token: token,
        platform: _currentPlatform,
        installationId: installationId,
      );

      await _attachMessageListeners();
      await _setUserEnabled(true);

      _initialized = true;
      bellState.value = NotificationBellState.enabled;

      debugPrint(
        '[NotificationService] Notifications enabled for teacher $teacherId',
      );
    } catch (e, st) {
      debugPrint('[NotificationService] Toggle failed: $e\n$st');

      final restored = await _isUserEnabled();
      bellState.value = restored
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;
    }
  }
}