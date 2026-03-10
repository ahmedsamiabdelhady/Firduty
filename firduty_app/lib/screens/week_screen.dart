// week_screen.dart — Shows teacher's duties for the current week
//
// Changes from original:
// • Reads `duty_type` from each duty entry.
// • For `morning_endofday` duties: shows location name.
// • For `break` duties: shows grade_class with a "Class:" label.

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';

class WeekScreen extends StatefulWidget {
  const WeekScreen({super.key});

  @override
  State<WeekScreen> createState() => _WeekScreenState();
}

class _WeekScreenState extends State<WeekScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _duties = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// Returns the Sunday that starts the current week (ISO: Mon=1 … Sun=7).
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
        _error = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    // Group duties by date
    final Map<String, List<Map<String, dynamic>>> grouped = {};
    for (final d in _duties) {
      grouped.putIfAbsent(d['date'] as String, () => []).add(d);
    }
    final sortedDates = grouped.keys.toList()..sort();

    return RefreshIndicator(
      onRefresh: _load,
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.error_outline,
                          size: 48, color: Colors.red),
                      const SizedBox(height: 12),
                      Text(l10n.error),
                      TextButton(
                          onPressed: _load,
                          child: const Text('Retry')),
                    ],
                  ),
                )
              : _duties.isEmpty
                  ? Center(
                      child: Text(l10n.noDutiesWeek,
                          style: const TextStyle(
                              fontSize: 16, color: Colors.grey)),
                    )
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: sortedDates.map((date) {
                        final dayDuties = grouped[date]!;
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // ── Date header ────────────────────────────
                            Padding(
                              padding:
                                  const EdgeInsets.symmetric(vertical: 8),
                              child: Text(
                                date,
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14,
                                  color: Theme.of(context).primaryColor,
                                ),
                              ),
                            ),

                            // ── Duty cards for that day ────────────────
                            ...dayDuties.map((d) {
                              final dutyType =
                                  (d['duty_type'] as String?) ??
                                      'morning_endofday';
                              final isBreak = dutyType == 'break';

                              final shiftName = isAr
                                  ? d['shift_name_ar']
                                  : d['shift_name_en'];

                              final String locationLine;
                              if (isBreak) {
                                final gc =
                                    (d['grade_class'] as String?) ?? '—';
                                locationLine =
                                    '${l10n.gradeClass}: $gc';
                              } else {
                                final locName = isAr
                                    ? ((d['location_name_ar'] as String?) ??
                                        '—')
                                    : ((d['location_name_en'] as String?) ??
                                        '—');
                                locationLine =
                                    '${l10n.location}: $locName';
                              }

                              final timeRange =
                                  '${(d['shift_start'] as String).substring(0, 5)}'
                                  ' – '
                                  '${(d['shift_end'] as String).substring(0, 5)}';

                              return Card(
                                margin: const EdgeInsets.only(bottom: 8),
                                shape: RoundedRectangleBorder(
                                    borderRadius:
                                        BorderRadius.circular(10)),
                                child: ListTile(
                                  leading: Icon(
                                    isBreak
                                        ? Icons.groups
                                        : Icons.assignment,
                                    color: isBreak
                                        ? Colors.purple.shade400
                                        : Colors.blue,
                                  ),
                                  title: Text(shiftName as String),
                                  subtitle: Text(
                                    '$locationLine\n$timeRange',
                                    style: const TextStyle(fontSize: 13),
                                  ),
                                  isThreeLine: true,
                                ),
                              );
                            }),
                          ],
                        );
                      }).toList(),
                    ),
    );
  }
}