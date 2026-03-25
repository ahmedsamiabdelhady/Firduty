import 'package:flutter/material.dart';
import '../services/notification_service.dart';

class NotificationBell extends StatelessWidget {
  final int teacherId;

  const NotificationBell({super.key, required this.teacherId});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<NotificationBellState>(
      valueListenable: NotificationService.bellState,
      builder: (context, state, _) {
        return IconButton(
          tooltip: _tooltip(state),
          icon: _icon(state),
          onPressed: _isInteractable(state)
              ? () => NotificationService.toggle(teacherId: teacherId)
              : null,
        );
      },
    );
  }

  static String _tooltip(NotificationBellState state) {
    switch (state) {
      case NotificationBellState.enabled:
        return 'Disable notifications';
      case NotificationBellState.disabled:
        return 'Enable notifications';
      case NotificationBellState.loading:
        return 'Updating...';
      case NotificationBellState.unknown:
        return 'Checking...';
    }
  }

  static Widget _icon(NotificationBellState state) {
    switch (state) {
      case NotificationBellState.enabled:
        return const Icon(Icons.notifications_active);
      case NotificationBellState.disabled:
        return const Icon(Icons.notifications_off);
      case NotificationBellState.loading:
        return const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        );
      case NotificationBellState.unknown:
        return const Icon(Icons.notifications);
    }
  }

  static bool _isInteractable(NotificationBellState state) {
    return state == NotificationBellState.enabled ||
        state == NotificationBellState.disabled;
  }
}