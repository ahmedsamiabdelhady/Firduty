/// teacher_select_screen.dart — First screen: teacher selection

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../gen/app_localizations.dart';

class TeacherSelectScreen extends StatefulWidget {
  const TeacherSelectScreen({super.key});

  @override
  State<TeacherSelectScreen> createState() => _TeacherSelectScreenState();
}

class _TeacherSelectScreenState extends State<TeacherSelectScreen> {
  List<Map<String, dynamic>> _teachers = [];
  int? _selectedTeacherId;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadTeachers();
  }

  Future<void> _loadTeachers() async {
    try {
      final teachers = await ApiService.getTeachers();
      setState(() {
        _teachers = teachers;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Future<void> _saveAndContinue() async {
    if (_selectedTeacherId == null) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('teacher_id', _selectedTeacherId!);

    if (!mounted) return;
    Navigator.pushReplacementNamed(context, '/home');
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.appTitle),
        centerTitle: true,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Icon(Icons.school, size: 80, color: Theme.of(context).primaryColor),
            const SizedBox(height: 24),
            Text(
              l10n.chooseTeacher,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 32),
            if (_loading)
              const Center(child: CircularProgressIndicator())
            else
              DropdownButtonFormField<int>(
                value: _selectedTeacherId,
                decoration: InputDecoration(
                  labelText: l10n.teacher,
                  border: const OutlineInputBorder(),
                ),
                items: _teachers.map((t) {
                  return DropdownMenuItem<int>(
                    value: t['id'] as int,
                    child: Text(t['name'] as String),
                  );
                }).toList(),
                onChanged: (val) => setState(() => _selectedTeacherId = val),
              ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: _selectedTeacherId != null ? _saveAndContinue : null,
              style: ElevatedButton.styleFrom(padding: const EdgeInsets.all(16)),
              child: Text(l10n.confirm),
            ),
          ],
        ),
      ),
    );
  }
}