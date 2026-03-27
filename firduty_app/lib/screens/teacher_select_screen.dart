import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';
import '../app_theme.dart';

class RegistrationScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const RegistrationScreen({super.key, required this.onLocaleChange});

  @override
  State<RegistrationScreen> createState() => _RegistrationScreenState();
}

class _RegistrationScreenState extends State<RegistrationScreen> {
  final _formKey    = GlobalKey<FormState>();
  final _nameCtrl   = TextEditingController();
  final _emailCtrl  = TextEditingController();
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
      final currentLang = Localizations.localeOf(context).languageCode;

      final result = await ApiService.registerTeacher(
        name:  _nameCtrl.text.trim(),
        email: _emailCtrl.text.trim().toLowerCase(),
        preferredLanguage: currentLang,
      );

      final teacherId = result['id'] as int;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt('teacher_id', teacherId);

      await ApiService.updateTeacherLanguage(
        teacherId: teacherId,
        lang: currentLang,
      );

      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/pending');
    } catch (e) {
      setState(() {
        _errorMsg   = e.toString().replaceFirst('Exception: ', '');
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    return Scaffold(
      backgroundColor: FirdutyColors.background,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // ── Language toggle ─────────────────────────────────────
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        onPressed: () => widget.onLocaleChange(
                          isAr ? const Locale('en') : const Locale('ar'),
                        ),
                        child: Text(
                          isAr
                              ? l10n.languageButtonEnglish
                              : l10n.languageButtonArabic,
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            color: FirdutyColors.navBlue,
                          ),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 8),

                  // ── Brand header ────────────────────────────────────────
                  Center(
                    child: Column(
                      children: [
                        Container(
                          width: 84,
                          height: 84,
                          decoration: BoxDecoration(
                            color: FirdutyColors.navBlue.withValues(alpha: 0.08),
                            borderRadius: BorderRadius.circular(22),
                            border: Border.all(
                              color:
                                  FirdutyColors.navBlue.withValues(alpha: 0.12),
                            ),
                          ),
                          padding: const EdgeInsets.all(12),
                          child: Image.asset('assets/logo.png',
                              fit: BoxFit.contain),
                        ),
                        const SizedBox(height: 14),
                        const Text(
                          'Firduty',
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.w800,
                            color: FirdutyColors.navBlue,
                            letterSpacing: -0.3,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          l10n.registerTitle,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontSize: 13.5,
                            color: FirdutyColors.textMuted,
                            height: 1.4,
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 28),

                  // ── Form card ───────────────────────────────────────────
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            // Error banner
                            if (_errorMsg != null) ...[
                              _ErrorBanner(message: _errorMsg!),
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
                              validator: (v) =>
                                  (v == null || v.trim().isEmpty)
                                      ? l10n.nameRequired
                                      : null,
                            ),
                            const SizedBox(height: 14),

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
                                if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
                                    .hasMatch(v.trim())) {
                                  return l10n.emailRequired;
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 22),

                            // Submit
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
                                    ? const _LoadingIndicator()
                                    : Text(
                                        l10n.register,
                                        style: const TextStyle(
                                          fontSize: 16,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  // ── Login link (moved to BELOW the form — correct UX flow) ──
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        l10n.alreadyHaveAccount,
                        style: const TextStyle(
                          color: FirdutyColors.textMuted,
                          fontSize: 13,
                        ),
                      ),
                      TextButton(
                        onPressed: () => Navigator.pushReplacementNamed(
                            context, '/login'),
                        child: Text(
                          l10n.login,
                          style: const TextStyle(
                            color: FirdutyColors.navBlue,
                            fontWeight: FontWeight.w700,
                            fontSize: 13,
                          ),
                        ),
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

// ── Shared helpers ─────────────────────────────────────────────────────────────

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: FirdutyColors.danger.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: FirdutyColors.danger.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: FirdutyColors.danger, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(color: FirdutyColors.danger, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _LoadingIndicator extends StatelessWidget {
  const _LoadingIndicator();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      height: 20,
      width: 20,
      child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
    );
  }
}
