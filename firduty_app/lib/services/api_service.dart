// api_service.dart — REST API communication layer

import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  // ⚠️ Update this to your Koyeb deployment URL after deploying the backend.
  static const String baseUrl = 'https://YOUR-APP-NAME.koyeb.app';

  // ─── Registration & Status ────────────────────────────────────────────────────

  /// Self-register a new teacher. Returns {id, name, status:'pending'}.
  /// Throws Exception with the server detail message on error (e.g. 409 duplicate email).
  static Future<Map<String, dynamic>> registerTeacher({
    required String name,
    required String email,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/teachers/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'email': email}),
    );
    if (res.statusCode == 200 || res.statusCode == 201) {
      return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    }
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    throw Exception(body['detail'] ?? 'Registration failed');
  }

  /// Get teacher status — returns {id, name, status:'pending'|'approved'}.
  /// Throws Exception with '404' in the message when not found.
  static Future<Map<String, dynamic>> getTeacherStatus(int teacherId) async {
    final res = await http.get(
      Uri.parse('$baseUrl/teachers/$teacherId/status'),
    );
    if (res.statusCode == 200) {
      return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    }
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    throw Exception(
      res.statusCode == 404 ? '404: Teacher not found' : (body['detail'] ?? 'Status check failed'),
    );
  }

  // ─── Teachers ────────────────────────────────────────────────────────────────

  /// Register FCM device token for a teacher
  static Future<void> registerDeviceToken({
    required int teacherId,
    required String token,
    required String platform,
  }) async {
    await http.post(
      Uri.parse('$baseUrl/teachers/$teacherId/device-token'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'token': token, 'platform': platform}),
    );
  }

  /// Update teacher's preferred language
  static Future<void> updateTeacherLanguage({
    required int teacherId,
    required String lang,
  }) async {
    await http.put(
      Uri.parse('$baseUrl/teachers/$teacherId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'preferred_language': lang}),
    );
  }

  // ─── Schedule ─────────────────────────────────────────────────────────────────

  /// Get a teacher's duties for a specific date (includes assignment_id)
  static Future<Map<String, dynamic>> getTeacherSchedule({
    required int teacherId,
    required String date, // YYYY-MM-DD
  }) async {
    final res = await http.get(
      Uri.parse('$baseUrl/teachers/$teacherId/schedule?date=$date'),
    );
    if (res.statusCode == 200) {
      return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Failed to load schedule: ${res.statusCode}');
  }

  /// Get a teacher's duties for the entire week
  static Future<Map<String, dynamic>> getTeacherWeek({
    required int teacherId,
    required String weekStart, // YYYY-MM-DD (Sunday)
  }) async {
    final res = await http.get(
      Uri.parse('$baseUrl/teachers/$teacherId/week?week_start=$weekStart'),
    );
    if (res.statusCode == 200) {
      return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Failed to load week: ${res.statusCode}');
  }

  // ─── Points & Confirmation ────────────────────────────────────────────────────

  /// Confirm duty presence — returns points earned and localised message
  static Future<Map<String, dynamic>> confirmDuty({
    required int teacherId,
    required int assignmentId,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/points/teachers/$teacherId/confirm'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'assignment_id': assignmentId}),
    );

    if (res.statusCode == 200) {
      return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    }

    // Parse error detail from FastAPI
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    final detail = body['detail'] ?? 'Confirmation failed';
    throw Exception(detail);
  }

  /// Get teacher's monthly points and per-duty breakdown
  static Future<Map<String, dynamic>> getTeacherPoints({
    required int teacherId,
    required int year,
    required int month,
  }) async {
    final res = await http.get(
      Uri.parse(
          '$baseUrl/points/teachers/$teacherId/monthly?year=$year&month=$month'),
    );
    if (res.statusCode == 200) {
      return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Failed to load points: ${res.statusCode}');
  }
}