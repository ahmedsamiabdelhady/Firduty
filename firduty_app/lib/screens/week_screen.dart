// week_screen.dart — Teacher's duties for the current week
//
// UX/Performance improvements (v2.4):
//   • AutomaticKeepAliveClientMixin: scroll position survives tab switches
//   • Day headers now show localised day names (not just dates)
//   • Confirmed duties show green accent strip
//   • Proper empty state and error state with retry
//   • No deprecated APIs

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
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _duties = [];

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// Returns the Sunday that starts the current Omani school week.
  String _getCurrentSunday() {
    final now = DateTime.now();
    // weekday: Mon=1 … Sun=7 → Sunday offset = weekday % 7
    final daysFromSunday = now.weekday % 7;
    final sunday = now.subtract(Duration(days: daysFromSunday));
    return '${sunday.year}-'
        '${sunday.month.toString().padLeft(2, '0')}-'
        '${sunday.day.toString().padLeft(2, '0')}';
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final prefs = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        if (mounted) Navigator.pushReplacementNamed(context, '/');
        return;
      }

      final weekStart = _getCurrentSunday();
      final data = await ApiService.getTeacherWeek(
        teacherId: teacherId,
        weekStart: weekStart,
      );

      setState(() {
        _duties = List<Map<String, dynamic>>.from(data['duties'] ?? []);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  /// Localised day name for a given date string (YYYY-MM-DD).
  String _dayName(String dateStr, bool isAr) {
    final date = DateTime.parse(dateStr);
    final dayIndex = date.weekday % 7; // Sun=0 … Sat=6
    const en = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
        'Friday', 'Saturday'];
    const ar = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس',
        'الجمعة', 'السبت'];
    return isAr ? ar[dayIndex] : en[dayIndex];
  }

  /// Formatted date like "17 Mar" or "١٧ مار"
  String _shortDate(String dateStr, bool isAr) {
    final date = DateTime.parse(dateStr);
    if (isAr) {
      const months = ['يناير','فبراير','مارس','أبريل','مايو','يونيو',
          'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
      return '${date.day} ${months[date.month - 1]}';
    }
    return DateFormat('d MMM').format(date);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

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
              Text(_error!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: FirdutyColors.textMuted)),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    // Group duties by date
    final Map<String, List<Map<String, dynamic>>> grouped = {};
    for (final d in _duties) {
      grouped.putIfAbsent(d['date'] as String, () => []).add(d);
    }
    final sortedDates = grouped.keys.toList()..sort();

    if (sortedDates.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: FirdutyColors.navBlue.withValues(alpha: 0.07),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.calendar_today,
                    size: 52,
                    color: FirdutyColors.navBlue.withValues(alpha: 0.4)),
              ),
              const SizedBox(height: 20),
              Text(
                l10n.noDutiesWeek,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 16, color: FirdutyColors.textMuted, height: 1.5),
              ),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      color: FirdutyColors.navBlue,
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
        itemCount: sortedDates.length,
        itemBuilder: (context, i) {
          final date = sortedDates[i];
          final dayDuties = grouped[date]!;
          final isToday =
              date == DateFormat('yyyy-MM-dd').format(DateTime.now());

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Day Header ──────────────────────────────────────────────
              Padding(
                padding: const EdgeInsets.only(top: 8, bottom: 8),
                child: Row(
                  children: [
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
                    if (isToday) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: FirdutyColors.warning.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          isAr ? 'اليوم' : 'Today',
                          style: const TextStyle(
                              fontSize: 11,
                              color: FirdutyColors.warning,
                              fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ],
                ),
              ),

              // ── Duty cards for this day ─────────────────────────────────
              ...dayDuties.map((d) => _WeekDutyCard(duty: d, isAr: isAr)),
              const SizedBox(height: 4),
            ],
          );
        },
      ),
    );
  }
}

// ─── Week Duty Card ───────────────────────────────────────────────────────────

class _WeekDutyCard extends StatelessWidget {
  final Map<String, dynamic> duty;
  final bool isAr;

  const _WeekDutyCard({required this.duty, required this.isAr});

  @override
  Widget build(BuildContext context) {
    final dutyType = (duty['duty_type'] as String?) ?? 'morning_endofday';
    final isBreak = dutyType == 'break';
    final isConfirmed = duty['already_confirmed'] == true;

    final String locationLabel = isBreak
        ? (duty['grade_class'] as String? ?? '—')
        : isAr
            ? (duty['location_name_ar'] as String? ?? '—')
            : (duty['location_name_en'] as String? ?? '—');

    final shiftName = isAr
        ? duty['shift_name_ar'] as String
        : duty['shift_name_en'] as String;
    final startTime = (duty['shift_start'] as String).substring(0, 5);
    final endTime = (duty['shift_end'] as String).substring(0, 5);

    final accentColor =
        isBreak ? FirdutyColors.primaryGreen : FirdutyColors.navBlue;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 1,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: isConfirmed
            ? BorderSide(
                color: FirdutyColors.primaryGreen.withValues(alpha: 0.35),
                width: 1)
            : BorderSide.none,
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            // Vertical colour bar
            Container(
              width: 4,
              height: 52,
              decoration: BoxDecoration(
                color: isConfirmed ? FirdutyColors.primaryGreen : accentColor,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(shiftName,
                      style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 15,
                          color: FirdutyColors.textDark)),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(
                          isBreak ? Icons.school : Icons.location_on,
                          size: 14,
                          color: FirdutyColors.textMuted),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          locationLabel,
                          style: const TextStyle(
                              fontSize: 13,
                              color: FirdutyColors.textMuted),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '$startTime – $endTime',
                  style: const TextStyle(
                      fontSize: 13, color: FirdutyColors.textMuted),
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