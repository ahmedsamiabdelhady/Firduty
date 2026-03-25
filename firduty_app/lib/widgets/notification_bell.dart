import 'package:flutter/material.dart';

import '../services/notification_service.dart';

class NotificationBell extends StatelessWidget {
  final int teacherId;

  const NotificationBell({
    super.key,
    required this.teacherId,
  });

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<NotificationBellState>(
      valueListenable: NotificationService.bellState,
      builder: (context, state, _) {
        return Tooltip(
          message: _tooltip(state),
          child: IconButton(
            icon: _icon(state),
            onPressed: _isInteractable(state)
                ? () => NotificationService.toggle(teacherId: teacherId)
                : null,
          ),
        );
      },
    );
  }

  static String _tooltip(NotificationBellState state) {
    return switch (state) {
      NotificationBellState.enabled => 'Disable notifications',
      NotificationBellState.disabled => 'Enable notifications',
      NotificationBellState.loading => 'Updating...',
      NotificationBellState.unknown => 'Checking notifications...',
    };
  }

  static Widget _icon(NotificationBellState state) {
    return switch (state) {
      NotificationBellState.enabled => const Icon(Icons.notifications_active),
      NotificationBellState.disabled => const Icon(Icons.notifications_off),
      NotificationBellState.loading => const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      NotificationBellState.unknown => const Icon(Icons.notifications),
    };
  }

  static bool _isInteractable(NotificationBellState state) {
    return switch (state) {
      NotificationBellState.enabled => true,
      NotificationBellState.disabled => true,
      NotificationBellState.loading => false,
      NotificationBellState.unknown => false,
    };
  }
}