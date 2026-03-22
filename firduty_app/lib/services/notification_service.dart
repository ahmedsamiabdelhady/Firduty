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
import 'dart:math';

import 'package:flutter/foundation.dart' show kIsWeb, kDebugMode, debugPrint, ValueNotifier;
import 'package:flutter/material.dart' show GlobalKey, NavigatorState;
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

// ─────────────────────────────────────────────────────────────────────────────
// Bell state enum
//
// Declared at library level so notification_bell.dart can import it with a
// single import of this file — no separate enum file needed.
// ─────────────────────────────────────────────────────────────────────────────

/// Represents the current state of the notification toggle button.
enum NotificationBellState {
  /// FCM token is registered; teacher will receive push notifications.
  enabled,

  /// FCM token is not registered (or was deleted); no push notifications sent.
  disabled,

  /// A toggle operation is in progress — button should be non-interactive.
  loading,

  /// Initial state before initialize() has run or permission status is unknown.
  unknown,
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

  // ── Bell state ────────────────────────────────────────────────────────────
  //
  // Reactive ValueNotifier consumed by NotificationBell via
  // ValueListenableBuilder<NotificationBellState>.  Starts as unknown and is
  // updated by initialize(), toggle(), and reset().

  static final ValueNotifier<NotificationBellState> bellState =
      ValueNotifier(NotificationBellState.unknown);

  // SharedPreferences key that persists the user's on/off preference across
  // app restarts and hot restarts.
  static const _kNotificationsEnabled = 'firduty_notifications_enabled';

  // Cached platform string set during initialize() so toggle() can reuse it
  // without requiring callers to pass it again.
  static String _currentPlatform = kIsWeb ? 'web' : 'android';

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

    _currentPlatform = platform;
    debugPrint('[NotificationService] Starting (platform: $platform)…');

    try {
      if (kIsWeb) {
        await _initWeb(teacherId: teacherId);
      } else {
        await _initAndroid(teacherId: teacherId);
      }
      _initialized = true;

      // Sync bell state from the persisted user preference.
      // Defaults to enabled (first-time / no preference stored).
      final prefs = await SharedPreferences.getInstance();
      final savedEnabled = prefs.getBool(_kNotificationsEnabled) ?? true;
      bellState.value = savedEnabled
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;

      debugPrint('[NotificationService] Ready. bellState=${bellState.value}');
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
      settings: const InitializationSettings(
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

    // 6. Get stable installation_id for this device.
    //    Stored in SharedPreferences — survives app restarts and token rotations.
    //    The backend upserts on (teacher_id, installation_id) so a rotated token
    //    UPDATES the existing row instead of creating a duplicate.
    final installationId = await _getInstallationId();

    // Get FCM token and register with backend.
    final token = await _messaging.getToken();
    if (token != null) {
      await _registerToken(
        teacherId:      teacherId,
        token:          token,
        platform:       'android',
        installationId: installationId,
      );
    }

    // 7. Refresh token when FCM rotates it — same installationId, new token.
    await _onTokenRefreshSub?.cancel();
    _onTokenRefreshSub = _messaging.onTokenRefresh.listen((newToken) async {
      await _registerToken(
        teacherId:      teacherId,
        token:          newToken,
        platform:       'android',
        installationId: installationId,
      );
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

    // 2. Get stable installation_id for this browser/device.
    final installationId = await _getInstallationId();

    // 3. Get FCM web registration token using VAPID key.
    //    kVapidPublicKey comes from firebase_options.dart.
    final token = await _messaging.getToken(vapidKey: kVapidPublicKey);
    if (token != null) {
      await _registerToken(
        teacherId: teacherId,
        token: token,
        platform: 'web',
        installationId: installationId,
      );
    }

    // 4. Foreground message handler (background is handled by SW).
    await _onMessageSub?.cancel();
    _onMessageSub = FirebaseMessaging.onMessage.listen((RemoteMessage msg) {
      if (kDebugMode) {
        debugPrint('[FCM Web] Foreground: ${msg.notification?.title}');
      }
    });

    // 5. Refresh token — same installationId, new token → backend upserts.
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

  // ── Shared helpers ────────────────────────────────────────────────────────

  // ── Installation ID ─────────────────────────────────────────────────────────
  // A stable UUID generated once per device/browser installation.
  // Stored in SharedPreferences so it survives app restarts and FCM token
  // rotations. The backend upserts device_tokens on (teacher_id, installation_id)
  // so that a rotated token replaces the old row instead of inserting a new one.
  // This prevents the teacher from receiving the same notification multiple times.

  static const _installationIdKey = 'firduty_installation_id';

  /// Returns the stable installation UUID for this device/browser.
  /// Creates and persists one on first call.
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

  /// Generate a UUID v4 without external packages.
  static String _generateUuidV4() {
    final rng = Random.secure();
    final bytes = List<int>.generate(16, (_) => rng.nextInt(256));
    // Set version 4 bits (4 = 0100 xxxx)
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    // Set variant bits (10xx xxxx)
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    String hex(List<int> b) =>
        b.map((v) => v.toRadixString(16).padLeft(2, '0')).join();
    return '${hex(bytes.sublist(0, 4))}-'
           '${hex(bytes.sublist(4, 6))}-'
           '${hex(bytes.sublist(6, 8))}-'
           '${hex(bytes.sublist(8, 10))}-'
           '${hex(bytes.sublist(10, 16))}';
  }

  // ── Logout / reset ───────────────────────────────────────────────────────────
  /// Call this when a teacher logs out so the next login can re-register tokens.
  /// Cancels stream subscriptions and resets the idempotency guard.
  static Future<void> reset() async {
    await _onMessageSub?.cancel();
    await _onTokenRefreshSub?.cancel();
    _onMessageSub = null;
    _onTokenRefreshSub = null;
    _initialized = false;
    bellState.value = NotificationBellState.unknown;
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
    String?         installationId,
  }) async {
    try {
      await ApiService.registerDeviceToken(
        teacherId:      teacherId,
        token:          token,
        platform:       platform,
        installationId: installationId,
      );
      debugPrint('[NotificationService] Token registered ($platform) '
                 'install=${installationId?.substring(0, 8) ?? "legacy"}');
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
      id:                  notification.hashCode, // stable ID — suppresses duplicates
      title:               notification.title,
      body:                notification.body,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          'firduty_channel',
          'Duty Notifications',
          importance: Importance.high,
          priority:   Priority.high,
          icon:       '@mipmap/ic_launcher',
        ),
        iOS: DarwinNotificationDetails(),
      ),
    );
  }

  // ── Bell toggle ──────────────────────────────────────────────────────────────
  //
  // Toggles push notifications on / off for [teacherId].
  //
  // State machine:
  //   enabled  → loading → disabled  (delete token on device + backend)
  //   disabled → loading → enabled   (re-request permission + re-register token)
  //   unknown  → loading → enabled   (treated same as disabled)
  //   loading  → (no-op — a toggle is already in flight)
  //
  // The user's preference is persisted in SharedPreferences so it survives
  // app restarts.  initialize() reads this preference on the next launch and
  // restores bellState accordingly.
  //
  // Uses the same installationId and platform as initialize(), so the backend
  // upserts correctly and no duplicate token rows are created.

  static Future<void> toggle({required int teacherId}) async {
    // Prevent double-tap while in progress.
    if (bellState.value == NotificationBellState.loading) return;

    final previous = bellState.value;
    bellState.value = NotificationBellState.loading;

    try {
      if (previous == NotificationBellState.enabled) {
        // ── Disable ────────────────────────────────────────────────────────
        // 1. Delete the on-device FCM token.
        await _messaging.deleteToken();

        // 2. Persist preference and update state.
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool(_kNotificationsEnabled, false);
        bellState.value = NotificationBellState.disabled;

        debugPrint('[NotificationService] Notifications disabled for teacher $teacherId');
      } else {
        // ── Enable (disabled | unknown) ────────────────────────────────────
        // 1. Re-request permission in case the user had revoked it in OS settings.
        final settings = await _messaging.requestPermission(
          alert: true,
          badge: true,
          sound: true,
        );

        final granted =
            settings.authorizationStatus == AuthorizationStatus.authorized ||
            settings.authorizationStatus == AuthorizationStatus.provisional;

        if (!granted) {
          // User denied permission in OS settings — stay disabled.
          final prefs = await SharedPreferences.getInstance();
          await prefs.setBool(_kNotificationsEnabled, false);
          bellState.value = NotificationBellState.disabled;
          debugPrint('[NotificationService] Permission denied — cannot enable.');
          return;
        }

        // 2. Get a fresh token (a new one was issued after deleteToken() on
        //    disable, or this is the first time enabling).
        final installationId = await _getInstallationId();
        final token = kIsWeb
            ? await _messaging.getToken(vapidKey: kVapidPublicKey)
            : await _messaging.getToken();

        if (token != null) {
          await _registerToken(
            teacherId:      teacherId,
            token:          token,
            platform:       _currentPlatform,
            installationId: installationId,
          );
        }

        // 3. Persist preference and update state.
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool(_kNotificationsEnabled, true);
        bellState.value = NotificationBellState.enabled;

        debugPrint('[NotificationService] Notifications enabled for teacher $teacherId');
      }
    } catch (e, st) {
      // Revert to the state before the toggle attempt so the UI is consistent.
      debugPrint('[NotificationService] Toggle failed: $e\n$st');
      bellState.value = previous == NotificationBellState.enabled
          ? NotificationBellState.enabled
          : NotificationBellState.disabled;
    }
  }
}
