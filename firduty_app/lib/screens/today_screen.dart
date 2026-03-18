// today_screen.dart — Teacher's duties for today + attendance confirmation.
//
// v3.0 changes:
//   • Reads `week_status` from API response (new field added in backend v3.0)
//   • Shows contextual empty-state messages:
//       - week_status == null          → "No duty plan has been set up yet"
//       - week_status == "draft"       → "Your schedule is being prepared"
//       - week_status == "published"
//         + no duties for this teacher → "No duties scheduled for today"
//   • Added debugPrint logging of date sent + response to aid diagnosis
//   • Optimistic confirm UI (mark instantly, revert on error)
//   • AutomaticKeepAliveClientMixin: scroll position survives tab switches
//   • No deprecated APIs (.withValues instead of .withOpacity)

import 'package:flutter/foundation.dart' show kDebugMode, debugPrint;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';
import '../app_theme.dart';

class TodayScreen extends StatefulWidget {
  const TodayScreen({super.key});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen>
    with AutomaticKeepAliveClientMixin {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _duties = [];
  String? _weekStatus; // "published" | "draft" | null
  int _teacherId = -1;

  /// Assignment IDs confirmed during this session (avoids re-fetching).
  final Set<int> _confirmedThisSession = {};

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading   = true;
      _error     = null;
      _weekStatus = null;
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        if (mounted) Navigator.pushReplacementNamed(context, '/');
        return;
      }
      _teacherId = teacherId;

      // Use device-local date (correct for teachers in Oman).
      // If the device timezone is set incorrectly, this date will be wrong.
      // The backend logs the received date so server-side diagnosis is possible.
      final today = DateFormat('yyyy-MM-dd').format(DateTime.now());

      if (kDebugMode) {
        debugPrint(
          '[TodayScreen] Loading duties — '
          'teacher_id=$teacherId  date=$today  '
          'device_tz=${DateTime.now().timeZoneName}',
        );
      }

      final data = await ApiService.getTeacherSchedule(
        teacherId: teacherId,
        date: today,
      );

      if (kDebugMode) {
        debugPrint(
          '[TodayScreen] Response — '
          'week_status=${data['week_status']}  '
          'duties=${(data['duties'] as List?)?.length ?? 0}',
        );
      }

      setState(() {
        _weekStatus = data['week_status'] as String?;
        _duties     = List<Map<String, dynamic>>.from(data['duties'] ?? []);
        _loading    = false;
      });
    } catch (e) {
      if (kDebugMode) debugPrint('[TodayScreen] Error: $e');
      setState(() {
        _error   = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  /// Optimistic confirm: mark immediately, call API, revert on error.
  Future<void> _confirmDuty(Map<String, dynamic> duty) async {
    final assignmentId = duty['assignment_id'] as int?;
    if (assignmentId == null) return;

    // Immediate visual update
    setState(() => _confirmedThisSession.add(assignmentId));

    try {
      final result = await ApiService.confirmDuty(
        teacherId: _teacherId,
        assignmentId: assignmentId,
      );

      if (!mounted) return;
      final isAr = Localizations.localeOf(context).languageCode == 'ar';
      final pts     = result['points_earned'] as int? ?? 0;
      final message = isAr
          ? result['message_ar'] as String? ?? ''
          : result['message_en'] as String? ?? '';

      final color = pts == 2
          ? FirdutyColors.primaryGreen
          : pts == 1
              ? FirdutyColors.warning
              : Colors.grey.shade600;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.check_circle, color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(child: Text(message)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  '+$pts pts',
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, color: Colors.white),
                ),
              ),
            ],
          ),
          backgroundColor: color,
          duration: const Duration(seconds: 3),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          margin: const EdgeInsets.all(12),
        ),
      );
    } catch (e) {
      // Revert optimistic update
      setState(() => _confirmedThisSession.remove(assignmentId));
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.toString().replaceFirst('Exception: ', '')),
          backgroundColor: FirdutyColors.danger,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          margin: const EdgeInsets.all(12),
        ),
      );
    }
  }

  // ── Contextual empty-state messages ─────────────────────────────────────────

  /// Choose the right icon + message based on week_status.
  ///
  /// | week_status | Meaning                       | Message shown              |
  /// |-------------|-------------------------------|----------------------------|
  /// | null        | No week plan for this date    | "No plan set up yet"       |
  /// | "draft"     | Week exists but not published | "Schedule being prepared"  |
  /// | "published" | Published, no duties for me   | "No duties today"          |
  Widget _buildEmptyState(AppLocalizations l10n) {
    final IconData icon;
    final String   message;
    final Color    iconColor;

    switch (_weekStatus) {
      case "draft":
        icon      = Icons.edit_calendar_outlined;
        iconColor = FirdutyColors.warning;
        message   = l10n.scheduleBeingPrepared;   // "Your schedule is being prepared. Please check again later."
        break;
      case null:
        icon      = Icons.calendar_today_outlined;
        iconColor = FirdutyColors.textMuted;
        message   = l10n.noPlanForToday;          // "No weekly plan has been set up for today."
        break;
      default: // "published"
        icon      = Icons.event_available;
        iconColor = FirdutyColors.accentGreen;
        message   = l10n.noDutiesToday;           // "You have no duties scheduled for today."
        break;
    }

    return _EmptyState(icon: icon, iconColor: iconColor, message: message, onRetry: _load);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // required for AutomaticKeepAliveClientMixin
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return _ErrorState(message: _error!, onRetry: _load);
    }

    if (_duties.isEmpty) {
      return _buildEmptyState(l10n);
    }

    return RefreshIndicator(
      onRefresh: _load,
      color: FirdutyColors.navBlue,
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
        itemCount: _duties.length,
        itemBuilder: (context, index) {
          final d         = _duties[index];
          final dutyType  = (d['duty_type'] as String?) ?? 'morning_endofday';
          final isBreak   = dutyType == 'break';

          final String locationLabel;
          if (isBreak) {
            locationLabel = (d['grade_class'] as String?) ?? '—';
          } else {
            locationLabel = isAr
                ? ((d['location_name_ar'] as String?) ?? '—')
                : ((d['location_name_en'] as String?) ?? '—');
          }

          final shiftName   = isAr
              ? (d['shift_name_ar'] as String? ?? '')
              : (d['shift_name_en'] as String? ?? '');
          final assignmentId = d['assignment_id'] as int?;
          final isConfirmed  = assignmentId != null &&
              (d['already_confirmed'] == true ||
                  _confirmedThisSession.contains(assignmentId));

          return _DutyCard(
            shiftName:     shiftName,
            locationLabel: locationLabel,
            isBreak:       isBreak,
            startTime:     (d['shift_start'] as String? ?? '').substring(0, 5),
            endTime:       (d['shift_end']   as String? ?? '').substring(0, 5),
            isConfirmed:   isConfirmed,
            onConfirm:     assignmentId != null && !isConfirmed
                ? () => _confirmDuty(d)
                : null,
            l10n: l10n,
          );
        },
      ),
    );
  }
}

// ─── Empty State ──────────────────────────────────────────────────────────────

class _EmptyState extends StatelessWidget {
  final IconData icon;
  final Color    iconColor;
  final String   message;
  final VoidCallback onRetry;

  const _EmptyState({
    required this.icon,
    required this.iconColor,
    required this.message,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: iconColor.withValues(alpha: 0.08),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 48, color: iconColor),
            ),
            const SizedBox(height: 20),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 15,
                color: FirdutyColors.textMuted,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Refresh'),
              style: OutlinedButton.styleFrom(
                foregroundColor: FirdutyColors.navBlue,
                side: const BorderSide(color: FirdutyColors.navBlue),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Error State ──────────────────────────────────────────────────────────────

class _ErrorState extends StatelessWidget {
  final String       message;
  final VoidCallback onRetry;
  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.wifi_off_rounded,
                size: 52, color: FirdutyColors.textMuted),
            const SizedBox(height: 16),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: FirdutyColors.textMuted),
            ),
            const SizedBox(height: 20),
            ElevatedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
              style: ElevatedButton.styleFrom(
                backgroundColor: FirdutyColors.navBlue,
                foregroundColor: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Duty Card ────────────────────────────────────────────────────────────────

class _DutyCard extends StatelessWidget {
  final String         shiftName;
  final String         locationLabel;
  final bool           isBreak;
  final String         startTime;
  final String         endTime;
  final bool           isConfirmed;
  final VoidCallback?  onConfirm;
  final AppLocalizations l10n;

  const _DutyCard({
    required this.shiftName,
    required this.locationLabel,
    required this.isBreak,
    required this.startTime,
    required this.endTime,
    required this.isConfirmed,
    required this.onConfirm,
    required this.l10n,
  });

  @override
  Widget build(BuildContext context) {
    final accentColor = isBreak ? FirdutyColors.primaryGreen : FirdutyColors.navBlue;

    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      elevation: isConfirmed ? 0 : 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: isConfirmed
            ? BorderSide(
                color: FirdutyColors.primaryGreen.withValues(alpha: 0.4),
                width: 1.5)
            : BorderSide.none,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Coloured top accent bar ─────────────────────────────────────
          Container(
            height: 4,
            decoration: BoxDecoration(
              color: accentColor,
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(14)),
            ),
          ),

          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // ── Shift name + confirmed badge ──────────────────────────
                Row(
                  children: [
                    Icon(
                      isBreak ? Icons.groups : Icons.access_time,
                      color: accentColor,
                      size: 20,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        shiftName,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                          color: FirdutyColors.textDark,
                        ),
                      ),
                    ),
                    if (isConfirmed)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: FirdutyColors.accentGreen.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.check_circle,
                                size: 14, color: FirdutyColors.successDark),
                            const SizedBox(width: 4),
                            Text(
                              l10n.confirmed,
                              style: TextStyle(
                                color: FirdutyColors.successDark,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 10),

                // ── Location / Class row ──────────────────────────────────
                Row(
                  children: [
                    Icon(
                      isBreak ? Icons.school : Icons.location_on,
                      size: 16,
                      color: FirdutyColors.textMuted,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        '${isBreak ? l10n.gradeClass : l10n.location}: $locationLabel',
                        style: const TextStyle(
                            fontSize: 14, color: FirdutyColors.textDark),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),

                // ── Time row ─────────────────────────────────────────────
                Row(
                  children: [
                    const Icon(Icons.schedule,
                        size: 16, color: FirdutyColors.textMuted),
                    const SizedBox(width: 6),
                    Text(
                      '$startTime – $endTime',
                      style: const TextStyle(
                          fontSize: 14, color: FirdutyColors.textMuted),
                    ),
                  ],
                ),

                if (!isConfirmed) ...[
                  const SizedBox(height: 14),

                  // ── Points hint ───────────────────────────────────────
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: FirdutyColors.navBlue.withValues(alpha: 0.06),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        const Text('🏆 ', style: TextStyle(fontSize: 13)),
                        Expanded(
                          child: Text(
                            l10n.pointsHint(startTime),
                            style: TextStyle(
                                fontSize: 12, color: FirdutyColors.navBlue),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),

                  // ── Confirm button ────────────────────────────────────
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: onConfirm,
                      icon: const Icon(Icons.how_to_reg, size: 18),
                      label: Text(l10n.confirmPresence),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: FirdutyColors.navBlue,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10)),
                        elevation: 0,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
