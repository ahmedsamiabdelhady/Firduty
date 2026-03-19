// login_screen.dart — Teacher login screen
//
// Teachers log in with name + email only (no password, no OTP).
// On success the teacher_id is stored in SharedPreferences and the app
// navigates to /pending (if still awaiting approval) or /home (if approved).
//
// Matches the registration screen layout for visual consistency.

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';
import '../app_theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey   = GlobalKey<FormState>();
  final _nameCtrl  = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _emailFocus = FocusNode();

  bool    _submitting = false;
  String? _errorMsg;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _emailFocus.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _submitting = true; _errorMsg = null; });

    try {
      final result = await ApiService.loginTeacher(
        name:  _nameCtrl.text.trim(),
        email: _emailCtrl.text.trim().toLowerCase(),
      );

      final teacherId = result['id'] as int;
      final status    = result['status'] as String? ?? 'pending';

      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt('teacher_id', teacherId);

      if (!mounted) return;
      if (status == 'approved') {
        Navigator.pushReplacementNamed(context, '/home');
      } else {
        Navigator.pushReplacementNamed(context, '/pending');
      }
    } catch (e) {
      setState(() {
        _errorMsg = e.toString().replaceFirst('Exception: ', '');
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: FirdutyColors.background,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // ── Logo ──────────────────────────────────────────────────
                  Center(
                    child: Image.asset('assets/logo.png',
                        width: 120, height: 120),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    l10n.loginTitle,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        fontSize: 14,
                        color: FirdutyColors.textMuted,
                        height: 1.5),
                  ),
                  const SizedBox(height: 28),

                  // ── Form card ──────────────────────────────────────────────
                  Card(
                    elevation: 2,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            // Error banner
                            if (_errorMsg != null) ...[
                              Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  color: FirdutyColors.danger
                                      .withValues(alpha: 0.08),
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(
                                      color: FirdutyColors.danger
                                          .withValues(alpha: 0.3)),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(Icons.error_outline,
                                        color: FirdutyColors.danger, size: 18),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(_errorMsg!,
                                          style: const TextStyle(
                                              color: FirdutyColors.danger,
                                              fontSize: 13)),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 16),
                            ],

                            // Name field
                            TextFormField(
                              controller: _nameCtrl,
                              textInputAction: TextInputAction.next,
                              onFieldSubmitted: (_) =>
                                  _emailFocus.requestFocus(),
                              decoration: InputDecoration(
                                labelText: l10n.fullName,
                                prefixIcon:
                                    const Icon(Icons.person_outline),
                              ),
                              validator: (v) {
                                if (v == null || v.trim().isEmpty) {
                                  return l10n.nameRequired;
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 16),

                            // Email field
                            TextFormField(
                              controller: _emailCtrl,
                              focusNode: _emailFocus,
                              keyboardType: TextInputType.emailAddress,
                              textInputAction: TextInputAction.done,
                              onFieldSubmitted: (_) => _submit(),
                              decoration: InputDecoration(
                                labelText: l10n.email,
                                prefixIcon:
                                    const Icon(Icons.email_outlined),
                              ),
                              validator: (v) {
                                if (v == null || v.trim().isEmpty) {
                                  return l10n.emailRequired;
                                }
                                final emailRegex = RegExp(
                                    r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
                                if (!emailRegex.hasMatch(v.trim())) {
                                  return l10n.emailRequired;
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 24),

                            // Login button
                            SizedBox(
                              height: 50,
                              child: ElevatedButton(
                                onPressed: _submitting ? null : _submit,
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: FirdutyColors.navBlue,
                                  foregroundColor: Colors.white,
                                  shape: RoundedRectangleBorder(
                                      borderRadius:
                                          BorderRadius.circular(12)),
                                  elevation: 0,
                                ),
                                child: _submitting
                                    ? const SizedBox(
                                        height: 20, width: 20,
                                        child: CircularProgressIndicator(
                                          color: Colors.white,
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : Text(
                                        l10n.login,
                                        style: const TextStyle(
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600),
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 20),

                  // ── Switch to Register ────────────────────────────────────
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(l10n.noAccount,
                          style: const TextStyle(
                              color: FirdutyColors.textMuted,
                              fontSize: 13)),
                      TextButton(
                        onPressed: () =>
                            Navigator.pushReplacementNamed(
                                context, '/register'),
                        child: Text(l10n.register,
                            style: const TextStyle(
                                color: FirdutyColors.navBlue,
                                fontWeight: FontWeight.w600,
                                fontSize: 13)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
