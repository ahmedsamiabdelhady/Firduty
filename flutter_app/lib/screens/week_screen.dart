/// week_screen.dart — Shows teacher's duties for the current week

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
  String _weekStatus = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  String _getCurrentSunday() {
    final now = DateTime.now();
    final daysFromSunday = now.weekday % 7; // Sunday=0 in Dart weekday (Mon=1..Sun=7, so %7 gives Sun=0)
    final sunday = now.subtract(Duration(days: daysFromSunday));
    return '${sunday.year}-${sunday.month.toString().padLeft(2, '0')}-${sunday.day.toString().padLeft(2, '0')}';
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final prefs = await SharedPreferences.getInstance();
      final teacherId = prefs.getInt('teacher_id');
      if (teacherId == null) {
        Navigator.pushReplacementNamed(context, '/');
        return;
      }

      final weekStart = _getCurrentSunday();
      final data = await ApiService.getTeacherWeek(
        teacherId: teacherId,
        weekStart: weekStart,
      );

      setState(() {
        _duties = List<Map<String, dynamic>>.from(data['duties'] ?? []);
        _weekStatus = data['week_status'] ?? '';
        _loading = false;
      });
    } catch (e) {
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    // Group duties by date
    final Map<String, List<Map<String, dynamic>>> grouped = {};
    for (final d in _duties) {
      final date = d['date'] as String;
      grouped.putIfAbsent(date, () => []).add(d);
    }
    final sortedDates = grouped.keys.toList()..sort();

    return RefreshIndicator(
      onRefresh: _load,
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(l10n.error))
              : _duties.isEmpty
                  ? Center(child: Text(l10n.noDutiesWeek,
                      style: const TextStyle(fontSize: 16, color: Colors.grey)))
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: sortedDates.map((date) {
                        final dayDuties = grouped[date]!;
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              child: Text(
                                date,
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14,
                                  color: Theme.of(context).primaryColor,
                                ),
                              ),
                            ),
                            ...dayDuties.map((d) {
                              final locName = isAr ? d['location_name_ar'] : d['location_name_en'];
                              final shiftName = isAr ? d['shift_name_ar'] : d['shift_name_en'];
                              return Card(
                                margin: const EdgeInsets.only(bottom: 8),
                                child: ListTile(
                                  leading: const Icon(Icons.assignment, color: Colors.blue),
                                  title: Text(shiftName),
                                  subtitle: Text('${l10n.location}: $locName\n'
                                      '${d['shift_start'].toString().substring(0, 5)} – '
                                      '${d['shift_end'].toString().substring(0, 5)}'),
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