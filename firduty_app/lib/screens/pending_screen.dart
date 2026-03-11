// pending_screen.dart — Shown after registration while awaiting admin approval.

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../services/notification_service.dart';
import '../gen/app_localizations.dart';
import '../app_theme.dart';
import 'dart:io';

class PendingScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const PendingScreen({super.key, required this.onLocaleChange});

  @override
  State<PendingScreen> createState() => _PendingScreenState();
}

class _PendingScreenState extends State<PendingScreen> {
  bool _checking = false;
  String? _errorMsg;

  /// Poll the backend; if approved, init notifications and go to /home.
  Future<void> _checkStatus() async {
    setState(() { _checking = true; _errorMsg = null; });

    try {
      final prefs = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        if (mounted) Navigator.pushReplacementNamed(context, '/register');
        return;
      }

      final result = await ApiService.getTeacherStatus(teacherId);
      final status = result['status'] as String;

      if (status == 'approved') {
        // Initialize push notifications now that the account is active
        final platform = Platform.isIOS ? 'ios' : 'android';
        await NotificationService.initialize(
          teacherId: teacherId,
          platform: platform,
        );
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/home');
      } else {
        // Still pending
        setState(() { _checking = false; });
      }
    } catch (e) {
      // 404 means the record was deleted — send them back to register
      final msg = e.toString();
      if (msg.contains('404') || msg.contains('not found')) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.remove('teacher_id');
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/register');
        return;
      }
      setState(() {
        _errorMsg = msg.replaceFirst('Exception: ', '');
        _checking = false;
      });
    }
  }

  Future<void> _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('teacher_id');
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, '/register');
  }

  @override
  Widget build(BuildContext context) {
    final l10n  = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final isAr  = Localizations.localeOf(context).languageCode == 'ar';

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.appTitle),
        centerTitle: true,
        backgroundColor: theme.primaryColor,
        foregroundColor: Colors.white,
        actions: [
          TextButton(
            onPressed: () {
              widget.onLocaleChange(isAr ? const Locale('en') : const Locale('ar'));
            },
            child: Text(
              isAr ? 'EN' : 'عربي',
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Icon
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(
                  color: FirdutyColors.warning.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.hourglass_empty_rounded,
                  size: 48,
                  color: FirdutyColors.warning,
                ),
              ),
              const SizedBox(height: 24),

              // Title
              Text(
                l10n.pendingTitle,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),

              // Message
              Text(
                l10n.pendingMessage,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 15, color: Colors.black54, height: 1.5),
              ),
              const SizedBox(height: 32),

              // Error
              if (_errorMsg != null) ...[
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFDE8E8),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: const Color(0xFFF5BCBC)),
                  ),
                  child: Text(
                    _errorMsg!,
                    style: TextStyle(color: FirdutyColors.danger, fontSize: 13),
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: 16),
              ],

              // Check status button
              FilledButton.icon(
                onPressed: _checking ? null : _checkStatus,
                icon: _checking
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.refresh_rounded),
                label: Text(l10n.checkStatus),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                ),
              ),
              const SizedBox(height: 16),

              // Log out / use different account
              TextButton(
                onPressed: _logout,
                child: Text(
                  l10n.useAnotherAccount,
                  style: const TextStyle(color: Colors.black45),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}