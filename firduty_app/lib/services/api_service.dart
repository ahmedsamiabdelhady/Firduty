// api_service.dart — REST API communication layer
//
// Performance improvements (v2.4):
//   • 15-second timeout on all requests — no indefinite hangs
//   • Reusable http.Client instance (connection pooling on Android)
//   • Cleaner _errorMessage helper distinguishes server-down vs wrong endpoint
//   • All public methods documented

import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  /// Backend base URL — injected at build time via --dart-define=API_BASE_URL=...
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://YOUR-APP-NAME.koyeb.app',
  );

  /// Reusable HTTP client — avoids opening a new socket on every request.
  static final _client = http.Client();

  /// Maximum time to wait for any API response.
  static const _timeout = Duration(seconds: 15);

  // ─── Internal helpers ──────────────────────────────────────────────────────

  static Map<String, dynamic>? _tryDecode(http.Response res) {
    try {
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  static String _errorMessage(http.Response res, String fallback) {
    final body = _tryDecode(res);
    if (body != null) {
      return (body['detail'] as String?) ?? fallback;
    }
    switch (res.statusCode) {
      case 404: return 'Endpoint not found (404). Check API_BASE_URL.';
      case 502:
      case 503: return 'Server is starting up — please try again shortly.';
      default:  return '$fallback (HTTP ${res.statusCode})';
    }
  }

  // ─── Registration & Status ─────────────────────────────────────────────────

  /// Self-register a new teacher. Returns `{id, name, status:'pending'}`.
  static Future<Map<String, dynamic>> registerTeacher({
    required String name,
    required String email,
  }) async {
    late http.Response res;
    try {
      res = await _client
          .post(
            Uri.parse('$baseUrl/teachers/register'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'name': name, 'email': email}),
          )
          .timeout(_timeout);
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200 || res.statusCode == 201) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    if (res.statusCode == 409) {
      final body = _tryDecode(res);
      throw Exception(
          (body?['detail'] as String?) ?? 'This email is already registered.');
    }
    throw Exception(_errorMessage(res, 'Registration failed'));
  }

  /// Poll the approval status for a teacher.
  /// Returns `{id, name, email, status}`.
  static Future<Map<String, dynamic>> getTeacherStatus(int teacherId) async {
    late http.Response res;
    try {
      res = await _client
          .get(Uri.parse('$baseUrl/teachers/$teacherId/status'))
          .timeout(_timeout);
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    if (res.statusCode == 404) throw Exception('Teacher not found (404).');
    throw Exception(_errorMessage(res, 'Could not fetch status'));
  }

  // ─── Schedule ─────────────────────────────────────────────────────────────

  /// Returns today's duties for a teacher.
  /// `date` is `YYYY-MM-DD`.
  static Future<Map<String, dynamic>> getTeacherSchedule({
    required int teacherId,
    required String date,
  }) async {
    late http.Response res;
    try {
      res = await _client
          .get(Uri.parse('$baseUrl/teachers/$teacherId/schedule?date=$date'))
          .timeout(_timeout);
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Could not load today\'s duties'));
  }

  /// Returns the full week's duties for a teacher.
  /// `weekStart` is the Sunday date as `YYYY-MM-DD`.
  static Future<Map<String, dynamic>> getTeacherWeek({
    required int teacherId,
    required String weekStart,
  }) async {
    late http.Response res;
    try {
      res = await _client
          .get(Uri.parse(
              '$baseUrl/teachers/$teacherId/week?week_start=$weekStart'))
          .timeout(_timeout);
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Could not load week duties'));
  }

  // ─── Confirmation ─────────────────────────────────────────────────────────

  /// Confirm a duty assignment.
  /// Returns `{assignment_id, teacher_id, points_earned, message_en, message_ar}`.
  static Future<Map<String, dynamic>> confirmDuty({
    required int teacherId,
    required int assignmentId,
  }) async {
    late http.Response res;
    try {
      res = await _client
          .post(
            Uri.parse('$baseUrl/points/teachers/$teacherId/confirm'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'assignment_id': assignmentId}),
          )
          .timeout(_timeout);
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Could not confirm duty'));
  }

  // ─── Points ───────────────────────────────────────────────────────────────

  /// Returns monthly points summary for a teacher.
  /// Returns `{total_points, details: [...]}`.
  static Future<Map<String, dynamic>> getTeacherPoints({
    required int teacherId,
    required int year,
    required int month,
  }) async {
    late http.Response res;
    try {
      res = await _client
          .get(Uri.parse(
              '$baseUrl/points/teachers/$teacherId/monthly?year=$year&month=$month'))
          .timeout(_timeout);
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Could not load points'));
  }

  // ─── Device token registration ────────────────────────────────────────────

  /// Register an FCM / VAPID push token for a teacher.
  static Future<void> registerDeviceToken({
    required int teacherId,
    required String token,
    required String platform,
  }) async {
    try {
      await _client
          .post(
            Uri.parse('$baseUrl/teachers/$teacherId/device-token'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'token': token, 'platform': platform}),
          )
          .timeout(_timeout);
    } catch (_) {
      // Non-critical — silently swallow. Push notifications will simply not work.
    }
  }
}