// points_screen.dart — Teacher's monthly points summary and history
//
// v2.6 UX improvements:
//   • _monthProgress() now uses a sensible 60-point cap (30 duties × 2pts)
//     instead of the % 100 modulo that cycled oddly at exactly 100, 200 pts
//   • Retry button uses l10n string instead of hardcoded English
//   • Empty state icon is more prominent
//   • ConfirmationCard uses a thin left-accent bar matching today/week style

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../app_theme.dart';
import '../gen/app_localizations.dart';
import '../services/api_service.dart';

class PointsScreen extends StatefulWidget {
  const PointsScreen({super.key});

  @override
  State<PointsScreen> createState() => _PointsScreenState();
}

class _PointsScreenState extends State<PointsScreen>
    with AutomaticKeepAliveClientMixin {
  bool   _loading = true;
  String? _error;
  int    _totalPoints = 0;
  List<Map<String, dynamic>> _details = [];
  int    _year  = DateTime.now().year;
  int    _month = DateTime.now().month;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });

    try {
      final prefs     = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        if (mounted) Navigator.pushReplacementNamed(context, '/');
        return;
      }

      final data = await ApiService.getTeacherPoints(
        teacherId: teacherId,
        year:  _year,
        month: _month,
      );

      final confirmations =
          List<Map<String, dynamic>>.from(data['confirmations'] ?? []);

      confirmations.sort((a, b) {
        final aDate = '${a['date'] ?? ''} ${a['confirmed_at_muscat'] ?? ''}';
        final bDate = '${b['date'] ?? ''} ${b['confirmed_at_muscat'] ?? ''}';
        return bDate.compareTo(aDate);
      });

      setState(() {
        _totalPoints = data['total_points'] as int? ?? 0;
        _details     = confirmations;
        _loading     = false;
      });
    } catch (e) {
      setState(() {
        _error   = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  void _changeMonth(int delta) {
    setState(() {
      _month += delta;
      if (_month > 12) { _month = 1;  _year++; }
      if (_month < 1)  { _month = 12; _year--; }
    });
    _load();
  }

  String _monthName(int m, bool isAr) {
    const en = ['','January','February','March','April','May','June',
        'July','August','September','October','November','December'];
    const ar = ['','يناير','فبراير','مارس','أبريل','مايو','يونيو',
        'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
    return isAr ? ar[m] : en[m];
  }

  String _scoreMessage(bool isAr) {
    if (_totalPoints >= 100) return isAr ? 'أداء ممتاز جدًا 🔥' : 'Excellent performance 🔥';
    if (_totalPoints >= 60)  return isAr ? 'شغل رائع 👏' : 'Great job 👏';
    if (_totalPoints >= 25)  return isAr ? 'أداء جيد 👍' : 'Good progress 👍';
    if (_totalPoints > 0)    return isAr ? 'كمّل، أنت ماشي كويس 💪' : 'Keep going, you are doing well 💪';
    return isAr ? 'ابدأ أول تأكيد لك لتحصد النقاط ✨' : 'Start confirming duties to earn points ✨';
  }

  String _scoreSubMessage(bool isAr) {
    final count = _details.length;
    if (count == 0) {
      return isAr
          ? 'لا توجد تأكيدات مسجلة لهذا الشهر'
          : 'No confirmations recorded this month';
    }
    return isAr
        ? '$count تأكيد هذا الشهر'
        : '$count confirmation${count == 1 ? '' : 's'} this month';
  }

  /// Progress bar capped at 60 points (≈ 30 duties × 2 pts each).
  /// Previously used `% 100` which cycled oddly at exactly 100/200 pts.
  double _monthProgress() {
    if (_totalPoints <= 0) return 0;
    return (_totalPoints.clamp(0, 60) / 60).clamp(0.0, 1.0);
  }

  String _recentSectionTitle(bool isAr) =>
      isAr ? 'آخر التأكيدات' : 'Recent confirmations';

  String _emptyTitle(bool isAr) =>
      isAr ? 'لا توجد نقاط بعد' : 'No points yet';

  String _emptySubtitle(bool isAr) => isAr
      ? 'أكمل أول مناوبة مؤكدة لتبدأ في جمع النقاط'
      : 'Complete your first confirmed duty to start earning points';

  @override
  Widget build(BuildContext context) {
    super.build(context);

    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _load,
        color: FirdutyColors.navBlue,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: _PointsHeader(
                loading:         _loading,
                monthLabel:      '${_monthName(_month, isAr)} $_year',
                totalPoints:     _totalPoints,
                scoreMessage:    _scoreMessage(isAr),
                scoreSubMessage: _scoreSubMessage(isAr),
                progress:        _monthProgress(),
                details:         _details,
                l10n:            l10n,
                onPrev:          () => _changeMonth(-1),
                onNext:          () => _changeMonth(1),
              ),
            ),

            if (_error != null)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(28),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.wifi_off_rounded,
                            size: 52, color: FirdutyColors.textMuted),
                        const SizedBox(height: 14),
                        Text(
                          _error!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              color: FirdutyColors.textMuted, fontSize: 14),
                        ),
                        const SizedBox(height: 18),
                        ElevatedButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh),
                          label: Text(l10n.checkStatus),
                        ),
                      ],
                    ),
                  ),
                ),
              )

            else if (!_loading && _details.isEmpty)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 28),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(24),
                          decoration: BoxDecoration(
                            color: FirdutyColors.textMuted
                                .withValues(alpha: 0.07),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            Icons.emoji_events_outlined,
                            size: 52,
                            color:
                                FirdutyColors.textMuted.withValues(alpha: 0.5),
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          _emptyTitle(isAr),
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: FirdutyColors.textDark,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          _emptySubtitle(isAr),
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: FirdutyColors.textMuted,
                            fontSize: 13,
                            height: 1.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              )

            else ...[
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 18, 16, 8),
                  child: Row(
                    children: [
                      Text(
                        _recentSectionTitle(isAr),
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: FirdutyColors.textDark,
                        ),
                      ),
                      const Spacer(),
                      if (!_loading)
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 5),
                          decoration: BoxDecoration(
                            color: FirdutyColors.navBlue
                                .withValues(alpha: 0.08),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            '${_details.length}',
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                              color: FirdutyColors.navBlue,
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) => _ConfirmationCard(
                      detail: _details[index],
                      isAr:   isAr,
                      l10n:   l10n,
                    ),
                    childCount: _details.length,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ── Points header ─────────────────────────────────────────────────────────────

class _PointsHeader extends StatelessWidget {
  final bool   loading;
  final String monthLabel;
  final int    totalPoints;
  final String scoreMessage;
  final String scoreSubMessage;
  final double progress;
  final List<Map<String, dynamic>> details;
  final AppLocalizations l10n;
  final VoidCallback onPrev;
  final VoidCallback onNext;

  const _PointsHeader({
    required this.loading,
    required this.monthLabel,
    required this.totalPoints,
    required this.scoreMessage,
    required this.scoreSubMessage,
    required this.progress,
    required this.details,
    required this.l10n,
    required this.onPrev,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            FirdutyColors.primaryGreen,
            FirdutyColors.primaryGreen.withBlue(190),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: const BorderRadius.vertical(bottom: Radius.circular(24)),
        boxShadow: [
          BoxShadow(
            color: FirdutyColors.primaryGreen.withValues(alpha: 0.18),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 22),
      child: Column(
        children: [
          // Month navigation
          Row(
            children: [
              _NavButton(icon: Icons.chevron_left, onTap: onPrev),
              Expanded(
                child: Text(
                  monthLabel,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              _NavButton(icon: Icons.chevron_right, onTap: onNext),
            ],
          ),
          const SizedBox(height: 22),

          if (loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 28),
              child: CircularProgressIndicator(
                  color: Colors.white, strokeWidth: 2.6),
            )
          else ...[
            // Points value
            Text(
              '$totalPoints',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 60,
                fontWeight: FontWeight.w900,
                height: 1,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              l10n.myPoints,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.82),
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              scoreMessage,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 17,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              scoreSubMessage,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.85),
                fontSize: 12.5,
              ),
            ),
            const SizedBox(height: 18),

            // Progress bar (capped at 60 pts)
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                minHeight: 8,
                value: progress,
                backgroundColor: Colors.white.withValues(alpha: 0.18),
                valueColor:
                    const AlwaysStoppedAnimation<Color>(Colors.white),
              ),
            ),
            const SizedBox(height: 16),

            // On-time / Late / Missed stats
            _StatsRow(details: details, l10n: l10n),
          ],
        ],
      ),
    );
  }
}

// ── Nav button ────────────────────────────────────────────────────────────────

class _NavButton extends StatelessWidget {
  final IconData     icon;
  final VoidCallback onTap;
  const _NavButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: Ink(
        padding: const EdgeInsets.all(7),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.18),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(icon, color: Colors.white, size: 24),
      ),
    );
  }
}

// ── Stats row ─────────────────────────────────────────────────────────────────

class _StatsRow extends StatelessWidget {
  final List<Map<String, dynamic>> details;
  final AppLocalizations l10n;
  const _StatsRow({required this.details, required this.l10n});

  String _percent(int value, int total) {
    if (total == 0) return '0%';
    return '${((value / total) * 100).round()}%';
  }

  @override
  Widget build(BuildContext context) {
    final onTime = details.where((d) => d['points_earned'] == 2).length;
    final late   = details.where((d) => d['points_earned'] == 1).length;
    final missed = details.where((d) => d['points_earned'] == 0).length;
    final total  = details.length;

    return Row(
      children: [
        Expanded(
          child: _StatChip(
            label:   l10n.onTime,
            value:   '$onTime',
            percent: _percent(onTime, total),
            color:   Colors.white,
            bgColor: Colors.white.withValues(alpha: 0.18),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _StatChip(
            label:   l10n.late,
            value:   '$late',
            percent: _percent(late, total),
            color:   FirdutyColors.warning,
            bgColor: Colors.white.withValues(alpha: 0.14),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _StatChip(
            label:   l10n.missed,
            value:   '$missed',
            percent: _percent(missed, total),
            color:   Colors.redAccent.shade100,
            bgColor: Colors.white.withValues(alpha: 0.12),
          ),
        ),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final String percent;
  final Color  color;
  final Color  bgColor;

  const _StatChip({
    required this.label,
    required this.value,
    required this.percent,
    required this.color,
    required this.bgColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 10),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          Text(
            value,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.w800,
              fontSize: 22,
              height: 1,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 11.5,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            percent,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.78),
              fontSize: 10.5,
            ),
          ),
        ],
      ),
    );
  }
}

// ── Confirmation card ─────────────────────────────────────────────────────────

class _ConfirmationCard extends StatelessWidget {
  final Map<String, dynamic> detail;
  final bool isAr;
  final AppLocalizations l10n;

  const _ConfirmationCard({
    required this.detail,
    required this.isAr,
    required this.l10n,
  });

  String _statusText(int pts) {
    if (isAr) {
      if (pts == 2) return 'في الموعد';
      if (pts == 1) return 'متأخر';
      return 'فاتت';
    }
    if (pts == 2) return 'On time';
    if (pts == 1) return 'Late';
    return 'Missed';
  }

  @override
  Widget build(BuildContext context) {
    final pts        = detail['points_earned'] as int? ?? 0;
    final shiftName  = (isAr
            ? detail['shift_name_ar']
            : detail['shift_name_en']) as String? ?? '—';
    final date       = detail['date'] as String? ?? '—';
    final confirmedAt = detail['confirmed_at_muscat'] as String?;
    final confTime   = confirmedAt != null && confirmedAt.length >= 16
        ? confirmedAt.substring(11, 16)
        : '—';
    final shiftStart = detail['shift_start'] as String?;
    final startTime  = shiftStart != null && shiftStart.length >= 5
        ? shiftStart.substring(0, 5)
        : '—';
    final dutyType   = (detail['duty_type'] as String?) ?? 'morning_endofday';
    final isBreak    = dutyType == 'break';
    final secondaryLabel = isBreak
        ? '${l10n.gradeClass}: ${(detail['grade_class'] as String?) ?? '—'}'
        : '${l10n.location}: ${isAr ? ((detail['location_name_ar'] as String?) ?? '—') : ((detail['location_name_en'] as String?) ?? '—')}';

    final ptColor = pts == 2
        ? FirdutyColors.primaryGreen
        : pts == 1
            ? FirdutyColors.warning
            : FirdutyColors.textMuted;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: FirdutyColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: FirdutyColors.divider, width: 0.8),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: IntrinsicHeight(
        child: Row(
          children: [
            // Left accent bar matching today/week card style
            Container(
              width: 4,
              decoration: BoxDecoration(
                color: ptColor,
                borderRadius: const BorderRadius.horizontal(
                  left: Radius.circular(14),
                ),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Points circle
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: ptColor.withValues(alpha: 0.12),
                        shape: BoxShape.circle,
                      ),
                      child: Center(
                        child: Text(
                          '+$pts',
                          style: TextStyle(
                            color: ptColor,
                            fontWeight: FontWeight.w800,
                            fontSize: 14,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),

                    // Shift info
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            shiftName,
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14.5,
                              color: FirdutyColors.textDark,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            secondaryLabel,
                            style: const TextStyle(
                              fontSize: 12.5,
                              color: FirdutyColors.textMuted,
                            ),
                          ),
                          const SizedBox(height: 8),
                          // Status chip
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 9, vertical: 3),
                            decoration: BoxDecoration(
                              color: ptColor.withValues(alpha: 0.10),
                              borderRadius: BorderRadius.circular(999),
                            ),
                            child: Text(
                              _statusText(pts),
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: ptColor,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 10),

                    // Date + time
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          date,
                          style: const TextStyle(
                            fontSize: 12,
                            color: FirdutyColors.textMuted,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.schedule,
                                size: 12, color: FirdutyColors.textMuted),
                            const SizedBox(width: 4),
                            Text(
                              '$startTime → $confTime',
                              style: const TextStyle(
                                fontSize: 11.5,
                                color: FirdutyColors.textMuted,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
