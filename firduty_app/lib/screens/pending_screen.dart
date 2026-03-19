// pending_screen.dart — Shown after registration while awaiting admin approval.
//
// UX improvements (v2.4):
//   • Auto-polls every 30 seconds instead of requiring a manual tap
//   • Visual progress indicator shows poll countdown
//   • Better illustration-style empty state
//   • Logout confirmation dialog

import 'dart:async';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../services/notification_service.dart';
import '../gen/app_localizations.dart';
import '../app_theme.dart';

class PendingScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const PendingScreen({super.key, required this.onLocaleChange});

  @override
  State<PendingScreen> createState() => _PendingScreenState();
}

class _PendingScreenState extends State<PendingScreen>
    with SingleTickerProviderStateMixin {
  bool _checking = false;
  String? _errorMsg;

  /// Auto-poll interval in seconds.
  static const _pollIntervalSec = 30;
  Timer? _pollTimer;
  int _countdown = _pollIntervalSec;

  late final AnimationController _pulseController;

  @override
  void initState() {
    super.initState();

    // Pulse animation for the waiting icon
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    // First check immediately, then poll every 30 s.
    _checkStatus();
    _startPollTimer();
  }

  void _startPollTimer() {
    _pollTimer?.cancel();
    setState(() => _countdown = _pollIntervalSec);

    // Tick down every second for the countdown display.
    _pollTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) { timer.cancel(); return; }
      setState(() {
        _countdown--;
        if (_countdown <= 0) {
          _countdown = _pollIntervalSec;
          _checkStatus();
        }
      });
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _checkStatus() async {
    if (_checking) return;
    setState(() {
      _checking = true;
      _errorMsg = null;
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        if (mounted) Navigator.pushReplacementNamed(context, '/login');
        return;
      }

      final result = await ApiService.getTeacherStatus(teacherId);
      final status = result['status'] as String;

      if (status == 'approved') {
        _pollTimer?.cancel();
        final platform = kIsWeb ? 'web' : 'android';
        await NotificationService.initialize(
          teacherId: teacherId,
          platform: platform,
        );
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/home');
      } else {
        setState(() => _checking = false);
        _startPollTimer();
      }
    } catch (e) {
      final msg = e.toString();
      if (msg.contains('404') || msg.contains('not found')) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.remove('teacher_id');
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/login');
        return;
      }
      setState(() {
        _errorMsg = msg.replaceFirst('Exception: ', '');
        _checking = false;
      });
    }
  }

  Future<void> _logout() async {
    final isAr = mounted
        ? Localizations.localeOf(context).languageCode == 'ar'
        : true;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(isAr ? 'تسجيل الخروج' : 'Sign out'),
        content: Text(isAr
            ? 'هل تريد الخروج والعودة لصفحة تسجيل الدخول؟'
            : 'Sign out and return to the login screen?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(isAr ? 'إلغاء' : 'Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(isAr ? 'خروج' : 'Sign out',
                style: const TextStyle(color: FirdutyColors.danger)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      _pollTimer?.cancel();
      await NotificationService.reset();
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('teacher_id');
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.appTitle),
        centerTitle: true,
        backgroundColor: FirdutyColors.navBlue,
        foregroundColor: Colors.white,
        elevation: 0,
        actions: [
          TextButton(
            onPressed: () => widget.onLocaleChange(
                isAr ? const Locale('en') : const Locale('ar')),
            style: TextButton.styleFrom(foregroundColor: Colors.white),
            child: Text(isAr ? 'EN' : 'ع',
                style: const TextStyle(
                    fontWeight: FontWeight.w600, color: Colors.white)),
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // ── Animated waiting icon ─────────────────────────────────
              AnimatedBuilder(
                animation: _pulseController,
                builder: (_, child) => Transform.scale(
                  scale: 0.92 + _pulseController.value * 0.08,
                  child: child,
                ),
                child: Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    color: FirdutyColors.navBlue.withValues(alpha: 0.1),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.hourglass_top_rounded,
                    size: 52,
                    color: FirdutyColors.navBlue,
                  ),
                ),
              ),
              const SizedBox(height: 28),

              // ── Pending message ───────────────────────────────────────
              Text(
                l10n.pendingTitle,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: FirdutyColors.textDark,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                l10n.pendingMessage,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 15,
                  color: FirdutyColors.textMuted,
                  height: 1.5,
                ),
              ),

              // ── Error message ─────────────────────────────────────────
              if (_errorMsg != null) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: FirdutyColors.danger.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                        color: FirdutyColors.danger.withValues(alpha: 0.25)),
                  ),
                  child: Text(
                    _errorMsg!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        color: FirdutyColors.danger, fontSize: 13),
                  ),
                ),
              ],

              const SizedBox(height: 32),

              // ── Auto-poll countdown + manual check ────────────────────
              if (_checking)
                const CircularProgressIndicator()
              else
                Column(
                  children: [
                    // Countdown ring
                    Stack(
                      alignment: Alignment.center,
                      children: [
                        SizedBox(
                          width: 60,
                          height: 60,
                          child: CircularProgressIndicator(
                            value: _countdown / _pollIntervalSec,
                            backgroundColor:
                                FirdutyColors.navBlue.withValues(alpha: 0.12),
                            color: FirdutyColors.navBlue,
                            strokeWidth: 4,
                          ),
                        ),
                        Text(
                          '$_countdown',
                          style: const TextStyle(
                              fontWeight: FontWeight.bold,
                              color: FirdutyColors.navBlue),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      isAr ? 'التحقق التلقائي' : 'Auto-checking',
                      style: const TextStyle(
                          fontSize: 12, color: FirdutyColors.textMuted),
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      onPressed: () {
                        _startPollTimer();
                        _checkStatus();
                      },
                      icon: const Icon(Icons.refresh, size: 18),
                      label: Text(l10n.checkStatus),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: FirdutyColors.navBlue,
                        side: const BorderSide(color: FirdutyColors.navBlue),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10)),
                      ),
                    ),
                  ],
                ),

              const SizedBox(height: 24),

              // ── Logout ────────────────────────────────────────────────
              TextButton(
                onPressed: _logout,
                child: Text(
                  isAr ? 'إلغاء الطلب' : 'Cancel request',
                  style: const TextStyle(color: FirdutyColors.textMuted),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
