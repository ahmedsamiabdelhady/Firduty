import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum NotificationBellState {
  enabled,
  disabled,
  loading,
  unknown,
}

class NotificationService {
  static final ValueNotifier<NotificationBellState> bellState =
      ValueNotifier(NotificationBellState.unknown);

  static const _key = 'notifications_enabled';

  static Future<void> initialize({required int teacherId}) async {
    bellState.value = NotificationBellState.loading;

    final prefs = await SharedPreferences.getInstance();
    final enabled = prefs.getBool(_key) ?? false;

    bellState.value =
        enabled ? NotificationBellState.enabled : NotificationBellState.disabled;
  }

  static Future<void> toggle({required int teacherId}) async {
    final prefs = await SharedPreferences.getInstance();
    final current = prefs.getBool(_key) ?? false;

    bellState.value = NotificationBellState.loading;

    await prefs.setBool(_key, !current);

    bellState.value = !current
        ? NotificationBellState.enabled
        : NotificationBellState.disabled;
  }

  static Future<void> reset() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
    bellState.value = NotificationBellState.disabled;
  }

  static void syncBellStateFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    final enabled = prefs.getBool(_key) ?? false;

    bellState.value =
        enabled ? NotificationBellState.enabled : NotificationBellState.disabled;
  }
}