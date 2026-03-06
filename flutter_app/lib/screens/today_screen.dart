/// today_screen.dart — Teacher's duties for today with duty confirmation

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';

class TodayScreen extends StatefulWidget {
  const TodayScreen({super.key});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _duties = [];
  int _teacherId = -1;

  // Track which assignment IDs have been confirmed this session
  final Set<int> _confirmedThisSession = {};

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
      _teacherId = teacherId;

      final today = DateFormat('yyyy-MM-dd').format(DateTime.now());
      final data = await ApiService.getTeacherSchedule(
        teacherId: teacherId,
        date: today,
      );

      setState(() {
        _duties = List<Map<String, dynamic>>.from(data['duties'] ?? []);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  /// Call confirm endpoint and show result dialog
  Future<void> _confirmDuty(Map<String, dynamic> duty) async {
    final assignmentId = duty['assignment_id'] as int?;
    if (assignmentId == null) return;

    // Show loading
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    try {
      final result = await ApiService.confirmDuty(
        teacherId: _teacherId,
        assignmentId: assignmentId,
      );

      if (!mounted) return;
      Navigator.pop(context); // close loader

      final isAr = Localizations.localeOf(context).languageCode == 'ar';
      final message = isAr
          ? result['message_ar'] as String
          : result['message_en'] as String;
      final points = result['points_earned'] as int;

      // Add to confirmed set so button changes
      setState(() => _confirmedThisSession.add(assignmentId));

      // Result dialog
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                points == 2 ? '🏆' : points == 1 ? '⏱' : '❌',
                style: const TextStyle(fontSize: 48),
              ),
              const SizedBox(height: 12),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 16),
              ),
              const SizedBox(height: 8),
              _PointsBadge(points: points),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text(AppLocalizations.of(context)!.confirm),
            ),
          ],
        ),
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context); // close loader
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString()), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 16),
            Text(l10n.error),
            TextButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }

    if (_duties.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.event_available, size: 64, color: Colors.grey.shade300),
            const SizedBox(height: 16),
            Text(l10n.noDutiesToday,
                style: TextStyle(fontSize: 16, color: Colors.grey.shade500)),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _duties.length,
        itemBuilder: (ctx, i) {
          final d = _duties[i];
          final locName = isAr ? d['location_name_ar'] : d['location_name_en'];
          final shiftName = isAr ? d['shift_name_ar'] : d['shift_name_en'];
          final assignmentId = d['assignment_id'] as int?;
          final isConfirmed = assignmentId != null &&
              (d['already_confirmed'] == true ||
                  _confirmedThisSession.contains(assignmentId));

          return _DutyCard(
            shiftName: shiftName,
            location: locName,
            startTime: (d['shift_start'] as String).substring(0, 5),
            endTime: (d['shift_end'] as String).substring(0, 5),
            isConfirmed: isConfirmed,
            onConfirm: assignmentId != null && !isConfirmed
                ? () => _confirmDuty(d)
                : null,
            l10n: l10n,
          );
        },
      ),
    );
  }
}

// ─── Duty Card Widget ─────────────────────────────────────────────────────────

class _DutyCard extends StatelessWidget {
  final String shiftName;
  final String location;
  final String startTime;
  final String endTime;
  final bool isConfirmed;
  final VoidCallback? onConfirm;
  final AppLocalizations l10n;

  const _DutyCard({
    required this.shiftName,
    required this.location,
    required this.startTime,
    required this.endTime,
    required this.isConfirmed,
    required this.onConfirm,
    required this.l10n,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Shift name + confirmed badge
            Row(
              children: [
                Icon(Icons.access_time,
                    color: Theme.of(context).primaryColor, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(shiftName,
                      style: const TextStyle(
                          fontWeight: FontWeight.bold, fontSize: 16)),
                ),
                if (isConfirmed)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.green.shade100,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(l10n.confirmed,
                        style: TextStyle(
                            color: Colors.green.shade700,
                            fontSize: 12,
                            fontWeight: FontWeight.w600)),
                  ),
              ],
            ),
            const SizedBox(height: 10),

            // Location
            Row(
              children: [
                const Icon(Icons.location_on, size: 16, color: Colors.grey),
                const SizedBox(width: 6),
                Text(location,
                    style: const TextStyle(fontSize: 14, color: Colors.black87)),
              ],
            ),
            const SizedBox(height: 4),

            // Time
            Row(
              children: [
                const Icon(Icons.schedule, size: 16, color: Colors.grey),
                const SizedBox(width: 6),
                Text('$startTime – $endTime',
                    style: const TextStyle(fontSize: 14, color: Colors.black54)),
              ],
            ),
            const SizedBox(height: 14),

            // Points info row
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Text('🏆 ', style: TextStyle(fontSize: 14)),
                  Expanded(
                    child: Text(
                      l10n.pointsHint(startTime),
                      style: TextStyle(
                          fontSize: 12, color: Colors.blue.shade700),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // Confirm button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: onConfirm,
                icon: Icon(
                    isConfirmed ? Icons.check_circle : Icons.how_to_reg),
                label: Text(isConfirmed
                    ? l10n.confirmed
                    : l10n.confirmPresence),
                style: ElevatedButton.styleFrom(
                  backgroundColor:
                      isConfirmed ? Colors.green : Theme.of(context).primaryColor,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Points Badge Widget ──────────────────────────────────────────────────────

class _PointsBadge extends StatelessWidget {
  final int points;
  const _PointsBadge({required this.points});

  @override
  Widget build(BuildContext context) {
    final color = points == 2
        ? Colors.green
        : points == 1
            ? Colors.orange
            : Colors.grey;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      decoration: BoxDecoration(
          color: color.withOpacity(0.1),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withOpacity(0.4))),
      child: Text(
        '+$points pts',
        style: TextStyle(
            fontWeight: FontWeight.bold, fontSize: 20, color: color),
      ),
    );
  }
}