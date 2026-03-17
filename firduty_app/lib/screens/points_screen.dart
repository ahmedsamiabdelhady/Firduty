// points_screen.dart — Teacher's monthly points summary and history
//
// UX/Performance improvements (v2.4):
//   • AutomaticKeepAliveClientMixin: scroll position survives tab switches
//   • Points header has larger, cleaner total display
//   • Stat chips (on-time / late / missed) show inside gradient header
//   • Confirmation rows use consistent card style matching week_screen
//   • Empty state and error state with retry
//   • No deprecated APIs

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';
import '../app_theme.dart';

class PointsScreen extends StatefulWidget {
  const PointsScreen({super.key});

  @override
  State<PointsScreen> createState() => _PointsScreenState();
}

class _PointsScreenState extends State<PointsScreen>
    with AutomaticKeepAliveClientMixin {
  bool _loading = true;
  String? _error;
  int _totalPoints = 0;
  List<Map<String, dynamic>> _details = [];
  int _year = DateTime.now().year;
  int _month = DateTime.now().month;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
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

      final data = await ApiService.getTeacherPoints(
        teacherId: teacherId,
        year: _year,
        month: _month,
      );

      setState(() {
        _totalPoints = data['total_points'] as int? ?? 0;
        _details = List<Map<String, dynamic>>.from(data['details'] ?? []);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  void _changeMonth(int delta) {
    setState(() {
      _month += delta;
      if (_month > 12) { _month = 1; _year++; }
      if (_month < 1)  { _month = 12; _year--; }
    });
    _load();
  }

  String _monthName(int m, bool isAr) {
    const en = ['', 'January','February','March','April','May','June',
        'July','August','September','October','November','December'];
    const ar = ['', 'يناير','فبراير','مارس','أبريل','مايو','يونيو',
        'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
    return isAr ? ar[m] : en[m];
  }

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
          slivers: [
            // ── Points Header ────────────────────────────────────────────
            SliverToBoxAdapter(
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      FirdutyColors.primaryGreen,
                      FirdutyColors.primaryGreen.withBlue(190),
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 28),
                child: Column(
                  children: [
                    // Month navigator
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        _NavButton(
                          icon: Icons.chevron_left,
                          onTap: () => _changeMonth(-1),
                        ),
                        Text(
                          '${_monthName(_month, isAr)} $_year',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.bold),
                        ),
                        _NavButton(
                          icon: Icons.chevron_right,
                          onTap: () => _changeMonth(1),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),

                    // Total points
                    if (_loading)
                      const CircularProgressIndicator(
                          color: Colors.white, strokeWidth: 2.5)
                    else ...[
                      Text(
                        '$_totalPoints',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 60,
                          fontWeight: FontWeight.w800,
                          height: 1,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        l10n.myPoints,
                        style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.75),
                            fontSize: 14),
                      ),
                      const SizedBox(height: 20),
                      _StatsRow(details: _details, l10n: l10n),
                    ],
                  ],
                ),
              ),
            ),

            // ── Error or empty state ─────────────────────────────────────
            if (_error != null)
              SliverFillRemaining(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(40),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.wifi_off_rounded,
                            size: 48, color: FirdutyColors.textMuted),
                        const SizedBox(height: 12),
                        Text(_error!,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                                color: FirdutyColors.textMuted)),
                        const SizedBox(height: 20),
                        ElevatedButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                ),
              )
            else if (!_loading && _details.isEmpty)
              SliverFillRemaining(
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.emoji_events_outlined,
                          size: 52,
                          color: FirdutyColors.textMuted.withValues(alpha: 0.5)),
                      const SizedBox(height: 16),
                      Text(
                        l10n.noConfirmationsYet,
                        style: const TextStyle(color: FirdutyColors.textMuted),
                      ),
                    ],
                  ),
                ),
              )
            else

            // ── Confirmation List ─────────────────────────────────────────
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
              sliver: SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, index) => _ConfirmationCard(
                    detail: _details[index],
                    isAr: isAr,
                    l10n: l10n,
                  ),
                  childCount: _details.length,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Month nav button ─────────────────────────────────────────────────────────

class _NavButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _NavButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.2),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(icon, color: Colors.white, size: 24),
      ),
    );
  }
}

// ─── Stats Row ────────────────────────────────────────────────────────────────

class _StatsRow extends StatelessWidget {
  final List<Map<String, dynamic>> details;
  final AppLocalizations l10n;

  const _StatsRow({required this.details, required this.l10n});

  @override
  Widget build(BuildContext context) {
    final onTime  = details.where((d) => d['points_earned'] == 2).length;
    final late    = details.where((d) => d['points_earned'] == 1).length;
    final missed  = details.where((d) => d['points_earned'] == 0).length;

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        _StatChip(label: l10n.onTime, value: '$onTime',
            color: Colors.white, bgColor: Colors.white.withValues(alpha: 0.2)),
        _StatChip(label: l10n.late, value: '$late',
            color: FirdutyColors.warning, bgColor: Colors.white.withValues(alpha: 0.15)),
        _StatChip(label: l10n.missed, value: '$missed',
            color: Colors.redAccent.shade100, bgColor: Colors.white.withValues(alpha: 0.12)),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  final Color bgColor;

  const _StatChip({
    required this.label,
    required this.value,
    required this.color,
    required this.bgColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Text(value,
              style: TextStyle(
                  color: color,
                  fontWeight: FontWeight.bold,
                  fontSize: 22)),
          const SizedBox(height: 2),
          Text(label,
              style: const TextStyle(color: Colors.white70, fontSize: 11)),
        ],
      ),
    );
  }
}

// ─── Confirmation Card ────────────────────────────────────────────────────────

class _ConfirmationCard extends StatelessWidget {
  final Map<String, dynamic> detail;
  final bool isAr;
  final AppLocalizations l10n;

  const _ConfirmationCard({
    required this.detail,
    required this.isAr,
    required this.l10n,
  });

  @override
  Widget build(BuildContext context) {
    final pts = detail['points_earned'] as int;
    final shiftName =
        isAr ? detail['shift_name_ar'] : detail['shift_name_en'];
    final date = detail['date'] as String;
    final confTime =
        (detail['confirmed_at_muscat'] as String).substring(11, 16);
    final startTime = (detail['shift_start'] as String).substring(0, 5);

    final dutyType = (detail['duty_type'] as String?) ?? 'morning_endofday';
    final isBreak = dutyType == 'break';

    final String secondaryLabel;
    if (isBreak) {
      final gc = (detail['grade_class'] as String?) ?? '—';
      secondaryLabel = '${l10n.gradeClass}: $gc';
    } else {
      final locName = isAr
          ? (detail['location_name_ar'] as String? ?? '—')
          : (detail['location_name_en'] as String? ?? '—');
      secondaryLabel = '${l10n.location}: $locName';
    }

    final ptColor = pts == 2
        ? FirdutyColors.primaryGreen
        : pts == 1
            ? FirdutyColors.warning
            : FirdutyColors.textMuted;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            // Points badge
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
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(shiftName as String,
                      style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 14,
                          color: FirdutyColors.textDark)),
                  const SizedBox(height: 3),
                  Text(secondaryLabel,
                      style: const TextStyle(
                          fontSize: 12, color: FirdutyColors.textMuted)),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(date,
                    style: const TextStyle(
                        fontSize: 12, color: FirdutyColors.textMuted)),
                const SizedBox(height: 4),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.schedule, size: 12,
                        color: FirdutyColors.textMuted),
                    const SizedBox(width: 3),
                    Text('$startTime → $confTime',
                        style: const TextStyle(
                            fontSize: 11, color: FirdutyColors.textMuted)),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}