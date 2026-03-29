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
        final interactable = state == NotificationBellState.enabled ||
            state == NotificationBellState.disabled;

        return IconButton(
          tooltip: _tooltip(state),
          // Always provide an onPressed so Flutter never dims the button.
          // No-op when loading/unknown — the spinner communicates the state.
          onPressed: interactable
              ? () => NotificationService.toggle(teacherId: teacherId)
              : () {},
          icon: _icon(state),
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
        // Same size as an icon so the AppBar doesn't shift.
        // White color matches AppBar foreground.
        return const SizedBox(
          width: 22,
          height: 22,
          child: CircularProgressIndicator(
            strokeWidth: 2.2,
            color: Colors.white,
          ),
        );
      case NotificationBellState.unknown:
        return const Icon(Icons.notifications);
    }
  }
}
