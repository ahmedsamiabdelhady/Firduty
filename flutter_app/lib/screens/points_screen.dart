/// points_screen.dart — Teacher's monthly points summary and history

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';

class PointsScreen extends StatefulWidget {
  const PointsScreen({super.key});

  @override
  State<PointsScreen> createState() => _PointsScreenState();
}

class _PointsScreenState extends State<PointsScreen> {
  bool _loading = true;
  String? _error;
  int _totalPoints = 0;
  List<Map<String, dynamic>> _details = [];
  int _year = DateTime.now().year;
  int _month = DateTime.now().month;
  int _teacherId = -1;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final prefs = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        if (mounted) Navigator.pushReplacementNamed(context, '/');
        return;
      }
      _teacherId = teacherId;

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
      setState(() { _error = e.toString(); _loading = false; });
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

  // Localized month names
  String _monthName(int m, bool isAr) {
    const en = ['','January','February','March','April','May','June',
                    'July','August','September','October','November','December'];
    const ar = ['','يناير','فبراير','مارس','أبريل','مايو','يونيو',
                    'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
    return isAr ? ar[m] : en[m];
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          slivers: [
            // ─── Points Header ───────────────────────────────────────────────
            SliverToBoxAdapter(
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Theme.of(context).primaryColor,
                      Theme.of(context).primaryColor.withBlue(200),
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
                child: Column(
                  children: [
                    // Month navigator
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.chevron_left, color: Colors.white),
                          onPressed: () => _changeMonth(-1),
                        ),
                        Text(
                          '${_monthName(_month, isAr)} $_year',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.bold),
                        ),
                        IconButton(
                          icon: const Icon(Icons.chevron_right, color: Colors.white),
                          onPressed: () => _changeMonth(1),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Points circle
                    Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.white.withOpacity(0.15),
                        border: Border.all(color: Colors.white.withOpacity(0.4), width: 2),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            '$_totalPoints',
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 40,
                                fontWeight: FontWeight.bold),
                          ),
                          Text(
                            l10n.points,
                            style: TextStyle(
                                color: Colors.white.withOpacity(0.85),
                                fontSize: 13),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 16),

                    // Mini stats row
                    if (!_loading && _details.isNotEmpty)
                      _MiniStats(details: _details, l10n: l10n),
                  ],
                ),
              ),
            ),

            // ─── Details List ─────────────────────────────────────────────────
            if (_loading)
              const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              SliverFillRemaining(
                child: Center(child: Text(l10n.error, style: const TextStyle(color: Colors.red))),
              )
            else if (_details.isEmpty)
              SliverFillRemaining(
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.emoji_events_outlined, size: 64, color: Colors.grey.shade300),
                      const SizedBox(height: 16),
                      Text(l10n.noConfirmationsYet,
                          style: TextStyle(color: Colors.grey.shade500, fontSize: 15)),
                    ],
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.all(16),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (ctx, i) {
                      final d = _details[i];
                      return _ConfirmationRow(
                        detail: d,
                        isAr: isAr,
                        l10n: l10n,
                      );
                    },
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

// ─── Mini Stats Row ───────────────────────────────────────────────────────────

class _MiniStats extends StatelessWidget {
  final List<Map<String, dynamic>> details;
  final AppLocalizations l10n;

  const _MiniStats({required this.details, required this.l10n});

  @override
  Widget build(BuildContext context) {
    final onTime = details.where((d) => d['points_earned'] == 2).length;
    final late   = details.where((d) => d['points_earned'] == 1).length;
    final missed = details.where((d) => d['points_earned'] == 0).length;

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        _StatChip(label: l10n.onTime, value: '$onTime', color: Colors.green.shade400),
        _StatChip(label: l10n.late,   value: '$late',   color: Colors.orange.shade400),
        _StatChip(label: l10n.missed, value: '$missed', color: Colors.red.shade300),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _StatChip({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        children: [
          Text(value, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 18)),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(color: Colors.white70, fontSize: 11)),
        ],
      ),
    );
  }
}

// ─── Confirmation Row ─────────────────────────────────────────────────────────

class _ConfirmationRow extends StatelessWidget {
  final Map<String, dynamic> detail;
  final bool isAr;
  final AppLocalizations l10n;

  const _ConfirmationRow({
    required this.detail,
    required this.isAr,
    required this.l10n,
  });

  @override
  Widget build(BuildContext context) {
    final pts       = detail['points_earned'] as int;
    final locName   = isAr ? detail['location_name_ar'] : detail['location_name_en'];
    final shiftName = isAr ? detail['shift_name_ar']    : detail['shift_name_en'];
    final date      = detail['date'] as String;
    final confTime  = (detail['confirmed_at_muscat'] as String).substring(11, 19);
    final startTime = (detail['shift_start'] as String).substring(0, 5);

    final ptColor = pts == 2
        ? Colors.green
        : pts == 1
            ? Colors.orange
            : Colors.grey;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        leading: CircleAvatar(
          backgroundColor: ptColor.withOpacity(0.12),
          child: Text(
            '+$pts',
            style: TextStyle(
                color: ptColor,
                fontWeight: FontWeight.bold,
                fontSize: 14),
          ),
        ),
        title: Text(
          shiftName,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('$locName · $date',
                style: const TextStyle(fontSize: 12, color: Colors.black54)),
            Row(
              children: [
                Icon(Icons.schedule, size: 12, color: Colors.grey.shade400),
                const SizedBox(width: 4),
                Text(
                  '${l10n.shift}: $startTime  |  ${l10n.confirmed}: $confTime',
                  style: const TextStyle(fontSize: 11, color: Colors.black45),
                ),
              ],
            ),
          ],
        ),
        trailing: _StatusBadge(points: pts, l10n: l10n),
        isThreeLine: true,
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final int points;
  final AppLocalizations l10n;
  const _StatusBadge({required this.points, required this.l10n});

  @override
  Widget build(BuildContext context) {
    final (label, color) = points == 2
        ? (l10n.onTime, Colors.green)
        : points == 1
            ? (l10n.late, Colors.orange)
            : (l10n.missed, Colors.grey);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }
}