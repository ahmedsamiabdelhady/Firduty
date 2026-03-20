import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../app_theme.dart';
import '../services/notification_service.dart';

class NotificationBellButton extends StatefulWidget {
  final Color iconColor;

  const NotificationBellButton({
    super.key,
    this.iconColor = FirdutyColors.navBlue,
  });

  @override
  State<NotificationBellButton> createState() => _NotificationBellButtonState();
}

class _NotificationBellButtonState extends State<NotificationBellButton> {
  Future<void> _handleToggle(BuildContext context) async {
    final messenger = ScaffoldMessenger.maybeOf(context);
    final previousState = NotificationService.bellState.value;

    final prefs = await SharedPreferences.getInstance();
    final teacherId = prefs.getInt('teacher_id');
    const platform = kIsWeb ? 'web' : 'android';

    await NotificationService.toggle(
      teacherId: teacherId,
      platform: platform,
    );

    if (!mounted) return;

    final newState = NotificationService.bellState.value;
    if (!kIsWeb &&
        previousState != NotificationBellState.enabled &&
        newState == NotificationBellState.enabled) {
      await HapticFeedback.mediumImpact();
    }

    final message = switch (newState) {
      NotificationBellState.enabled => 'Notifications enabled',
      NotificationBellState.disabled => 'Notifications disabled',
      NotificationBellState.loading => 'Updating notifications...',
      NotificationBellState.unknown => 'Notification status unavailable',
    };

    messenger
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 2),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<NotificationBellState>(
      valueListenable: NotificationService.bellState,
      builder: (context, state, _) {
        final isLoading = state == NotificationBellState.loading;
        final isEnabled = state == NotificationBellState.enabled;

        final icon = switch (state) {
          NotificationBellState.enabled => Icons.notifications_active_rounded,
          NotificationBellState.disabled => Icons.notifications_off_rounded,
          NotificationBellState.loading => Icons.notifications_rounded,
          NotificationBellState.unknown => Icons.notifications_none_rounded,
        };

        final tooltip = switch (state) {
          NotificationBellState.enabled => 'Disable notifications',
          NotificationBellState.disabled => 'Enable notifications',
          NotificationBellState.loading => 'Updating notifications',
          NotificationBellState.unknown => 'Enable notifications',
        };

        final effectiveColor = isEnabled ? Colors.green : widget.iconColor;

        return IconButton(
          tooltip: tooltip,
          onPressed: isLoading ? null : () => _handleToggle(context),
          icon: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            transitionBuilder: (child, animation) => ScaleTransition(
              scale: Tween<double>(begin: 0.75, end: 1.0).animate(
                CurvedAnimation(parent: animation, curve: Curves.easeOutBack),
              ),
              child: FadeTransition(opacity: animation, child: child),
            ),
            child: isLoading
                ? SizedBox(
                    key: const ValueKey('loading'),
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        widget.iconColor,
                      ),
                    ),
                  )
                : AnimatedScale(
                    key: ValueKey(state),
                    scale: isEnabled ? 1.14 : 1.0,
                    duration: const Duration(milliseconds: 220),
                    curve: Curves.easeOutBack,
                    child: Icon(icon, color: effectiveColor),
                  ),
          ),
        );
      },
    );
  }
}
