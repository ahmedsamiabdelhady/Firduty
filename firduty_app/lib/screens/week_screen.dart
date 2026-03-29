// week_screen.dart — Teacher's duties for the current Oman school week.
//
// v3.2 UX improvements:
//   • Empty/draft state uses l10n.checkStatus instead of hardcoded 'Refresh'
//   • "Today" chip uses a stronger visual (filled accent, not just a pale tint)
//   • Duty cards in week view use consistent Card border same as today_screen
//   • Error state retry button is also localised

import 'package:flutter/foundation.dart' show kDebugMode, debugPrint;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';
import '../app_theme.dart';

class WeekScreen extends StatefulWidget {
  const WeekScreen({super.key});

  @override
  State<WeekScreen> createState() => _WeekScreenState();
}

class _WeekScreenState extends State<WeekScreen>
    with AutomaticKeepAliveClientMixin {
  bool   _loading = true;
  String? _error;
  List<Map<String, dynamic>> _duties = [];
  String? _weekStatus;
  String? _todayDate;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading    = true;
      _error      = null;
      _weekStatus = null;
      _todayDate  = null;
    });

    try {
      final prefs     = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        if (mounted) Navigator.pushReplacementNamed(context, '/');
        return;
      }

      if (kDebugMode) {
        debugPrint('[WeekScreen] GET /teachers/$teacherId/current-week');
      }

      final data = await ApiService.getTeacherCurrentWeek(
          teacherId: teacherId);

      if (kDebugMode) {
        debugPrint(
          '[WeekScreen] week_status=${data['week_status']}  '
          'duties=${(data['duties'] as List?)?.length ?? 0}',
        );
      }

      final todayFmt = DateFormat('yyyy-MM-dd').format(DateTime.now());

      setState(() {
        _weekStatus = data['week_status'] as String?;
        _duties     = List<Map<String, dynamic>>.from(data['duties'] ?? []);
        _todayDate  = todayFmt;
        _loading    = false;
      });
    } catch (e) {
      if (kDebugMode) debugPrint('[WeekScreen] Error: $e');
      setState(() {
        _error   = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  String _dayName(String dateStr, bool isAr) {
    final date     = DateTime.parse(dateStr);
    final dayIndex = date.weekday % 7;
    const en = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    const ar = ['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];
    return isAr ? ar[dayIndex] : en[dayIndex];
  }

  String _shortDate(String dateStr, bool isAr) {
    final date = DateTime.parse(dateStr);
    if (isAr) {
      const months = [
        'يناير','فبراير','مارس','أبريل','مايو','يونيو',
        'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر',
      ];
      return '${date.day} ${months[date.month - 1]}';
    }
    return DateFormat('d MMM').format(date);
  }

  Widget _buildEmptyOrDraft(AppLocalizations l10n, bool isAr) {
    final IconData icon;
    final String   message;
    final Color    iconColor;

    switch (_weekStatus) {
      case 'draft':
        icon      = Icons.edit_calendar_outlined;
        iconColor = FirdutyColors.warning;
        message   = l10n.scheduleBeingPrepared;
        break;
      case null:
        icon      = Icons.calendar_today_outlined;
        iconColor = FirdutyColors.textMuted;
        message   = l10n.noPlanForToday;
        break;
      default:
        icon      = Icons.calendar_today;
        iconColor = FirdutyColors.navBlue.withValues(alpha: 0.4);
        message   = l10n.noDutiesWeek;
        break;
    }

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
              child: Icon(icon, size: 52, color: iconColor),
            ),
            const SizedBox(height: 20),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 16,
                color: FirdutyColors.textMuted,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh, size: 16),
              label: Text(l10n.checkStatus), // was hardcoded 'Refresh'
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_error != null) {
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
                _error!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: FirdutyColors.textMuted),
              ),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: Text(l10n.checkStatus),
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

    // Group by date
    final Map<String, List<Map<String, dynamic>>> grouped = {};
    for (final d in _duties) {
      grouped.putIfAbsent(d['date'] as String, () => []).add(d);
    }
    final sortedDates = grouped.keys.toList()..sort((a, b) => b.compareTo(a));

    if (sortedDates.isEmpty) return _buildEmptyOrDraft(l10n, isAr);

    return RefreshIndicator(
      onRefresh: _load,
      color: FirdutyColors.navBlue,
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
        itemCount: sortedDates.length,
        itemBuilder: (context, i) {
          final date      = sortedDates[i];
          final dayDuties = grouped[date]!;
          final isToday   = date == (_todayDate ?? '');

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Day header ─────────────────────────────────────────
              Padding(
                padding: const EdgeInsets.only(top: 8, bottom: 8),
                child: Row(
                  children: [
                    // Day name pill
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: isToday
                            ? FirdutyColors.navBlue
                            : FirdutyColors.navBlue.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        _dayName(date, isAr),
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          color: isToday
                              ? Colors.white
                              : FirdutyColors.navBlue,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _shortDate(date, isAr),
                      style: const TextStyle(
                          fontSize: 13, color: FirdutyColors.textMuted),
                    ),
                    // "Today" badge — stronger styling
                    if (isToday) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 9, vertical: 3),
                        decoration: BoxDecoration(
                          color: FirdutyColors.warning,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          isAr ? 'اليوم' : 'Today',
                          style: const TextStyle(
                            fontSize: 11,
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              ...dayDuties.map(
                (d) => _WeekDutyCard(duty: d, isAr: isAr),
              ),
              const SizedBox(height: 4),
            ],
          );
        },
      ),
    );
  }
}

// ── Week duty card ────────────────────────────────────────────────────────────

class _WeekDutyCard extends StatelessWidget {
  final Map<String, dynamic> duty;
  final bool isAr;

  const _WeekDutyCard({required this.duty, required this.isAr});

  @override
  Widget build(BuildContext context) {
    final dutyType    = (duty['duty_type'] as String?) ?? 'morning_endofday';
    final isBreak     = dutyType == 'break';
    final isConfirmed = duty['already_confirmed'] == true;

    final String locationLabel = isBreak
        ? (duty['grade_class'] as String? ?? '—')
        : isAr
            ? (duty['location_name_ar'] as String? ?? '—')
            : (duty['location_name_en'] as String? ?? '—');

    final shiftName  = isAr
        ? duty['shift_name_ar'] as String? ?? ''
        : duty['shift_name_en'] as String? ?? '';
    final shiftStart = duty['shift_start'] as String? ?? '';
    final shiftEnd   = duty['shift_end']   as String? ?? '';
    final startTime  = shiftStart.length >= 5 ? shiftStart.substring(0, 5) : shiftStart;
    final endTime    = shiftEnd.length   >= 5 ? shiftEnd.substring(0, 5)   : shiftEnd;

    final accentColor =
        isBreak ? FirdutyColors.primaryGreen : FirdutyColors.navBlue;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: FirdutyColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isConfirmed
              ? FirdutyColors.primaryGreen.withValues(alpha: 0.35)
              : FirdutyColors.divider,
          width: 0.8,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            // Left accent bar
            Container(
              width: 4,
              height: 52,
              decoration: BoxDecoration(
                color: isConfirmed ? FirdutyColors.primaryGreen : accentColor,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 12),
            // Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    shiftName,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                      color: FirdutyColors.textDark,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(
                        isBreak ? Icons.school : Icons.location_on,
                        size: 14,
                        color: FirdutyColors.textMuted,
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          locationLabel,
                          style: const TextStyle(
                            fontSize: 13,
                            color: FirdutyColors.textMuted,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Right side: time + confirm status
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '$startTime – $endTime',
                  style: const TextStyle(
                    fontSize: 13,
                    color: FirdutyColors.textMuted,
                  ),
                ),
                const SizedBox(height: 6),
                if (isConfirmed)
                  Icon(Icons.check_circle,
                      size: 18, color: FirdutyColors.primaryGreen)
                else
                  Icon(Icons.radio_button_unchecked,
                      size: 18, color: FirdutyColors.textMuted),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
