// api_service.dart — REST API communication layer.
//
// The backend URL is configured at build time via --dart-define:
//
//   flutter build apk  --dart-define=API_BASE_URL=https://your-app.koyeb.app
//   flutter build web  --dart-define=API_BASE_URL=https://your-app.koyeb.app
//   flutter run        --dart-define=API_BASE_URL=http://10.0.2.2:8000
//
// If not set, the placeholder default is used and all calls will fail with a
// clear "Server not configured" message rather than a raw JSON parse error.

import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  /// Backend base URL — injected at build time via --dart-define=API_BASE_URL=...
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://YOUR-APP-NAME.koyeb.app',
  );

  // ─── Internal helpers ──────────────────────────────────────────────────────

  /// Safely decode a JSON response body.
  /// Returns null if the body is not valid JSON (e.g. an HTML error page).
  static Map<String, dynamic>? _tryDecode(http.Response res) {
    try {
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      if (decoded is Map<String, dynamic>) return decoded;
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Extract a human-readable error message from a failed response.
  /// Falls back to a generic message if the body is not JSON (e.g. HTML 404).
  static String _errorMessage(http.Response res, String fallback) {
    final body = _tryDecode(res);
    if (body != null) {
      return (body['detail'] as String?) ?? fallback;
    }
    // Body is HTML or empty — the URL is probably wrong or the server is down.
    if (res.statusCode == 404) return 'Server endpoint not found (404). Check API_BASE_URL.';
    if (res.statusCode == 502 || res.statusCode == 503) return 'Server is starting up — please try again in a moment.';
    return '$fallback (HTTP ${res.statusCode})';
  }

  // ─── Registration & Status ─────────────────────────────────────────────────

  /// Self-register a new teacher. Returns {id, name, status:'pending'}.
  static Future<Map<String, dynamic>> registerTeacher({
    required String name,
    required String email,
  }) async {
    final http.Response res;
    try {
      res = await http.post(
        Uri.parse('$baseUrl/teachers/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'name': name, 'email': email}),
      );
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200 || res.statusCode == 201) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }

    // 409 = duplicate email
    if (res.statusCode == 409) {
      final body = _tryDecode(res);
      throw Exception(
        (body?['detail'] as String?) ?? 'This email is already registered.',
      );
    }

    throw Exception(_errorMessage(res, 'Registration failed'));
  }

  /// Get teacher approval status. Throws '404' in message when not found.
  static Future<Map<String, dynamic>> getTeacherStatus(int teacherId) async {
    final http.Response res;
    try {
      res = await http.get(Uri.parse('$baseUrl/teachers/$teacherId/status'));
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }

    if (res.statusCode == 404) throw Exception('404: Teacher not found');
    throw Exception(_errorMessage(res, 'Status check failed'));
  }

  // ─── Device Tokens ─────────────────────────────────────────────────────────

  /// Register a push notification token with the backend.
  static Future<void> registerDeviceToken({
    required int teacherId,
    required String token,
    required String platform,
  }) async {
    try {
      await http.post(
        Uri.parse('$baseUrl/teachers/$teacherId/device-token'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'token': token, 'platform': platform}),
      );
    } catch (_) {
      // Non-fatal — the app continues even if token registration fails.
    }
  }

  /// Update teacher's preferred language on the backend.
  static Future<void> updateTeacherLanguage({
    required int teacherId,
    required String lang,
  }) async {
    try {
      await http.put(
        Uri.parse('$baseUrl/teachers/$teacherId'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'preferred_language': lang}),
      );
    } catch (_) {
      // Non-fatal.
    }
  }

  // ─── Schedule ──────────────────────────────────────────────────────────────

  /// Get a teacher's duties for a specific date.
  static Future<Map<String, dynamic>> getTeacherSchedule({
    required int teacherId,
    required String date, // YYYY-MM-DD
  }) async {
    final http.Response res;
    try {
      res = await http.get(
        Uri.parse('$baseUrl/teachers/$teacherId/schedule?date=$date'),
      );
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Failed to load schedule'));
  }

  /// Get a teacher's duties for the entire week.
  static Future<Map<String, dynamic>> getTeacherWeek({
    required int teacherId,
    required String weekStart, // YYYY-MM-DD (Sunday)
  }) async {
    final http.Response res;
    try {
      res = await http.get(
        Uri.parse('$baseUrl/teachers/$teacherId/week?week_start=$weekStart'),
      );
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Failed to load week'));
  }

  // ─── Points & Confirmation ─────────────────────────────────────────────────

  /// Confirm duty presence — returns points earned and localised message.
  static Future<Map<String, dynamic>> confirmDuty({
    required int teacherId,
    required int assignmentId,
  }) async {
    final http.Response res;
    try {
      res = await http.post(
        Uri.parse('$baseUrl/points/teachers/$teacherId/confirm'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'assignment_id': assignmentId}),
      );
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Confirmation failed'));
  }

  /// Get teacher's monthly points and per-duty breakdown.
  static Future<Map<String, dynamic>> getTeacherPoints({
    required int teacherId,
    required int year,
    required int month,
  }) async {
    final http.Response res;
    try {
      res = await http.get(
        Uri.parse(
            '$baseUrl/points/teachers/$teacherId/monthly?year=$year&month=$month'),
      );
    } catch (e) {
      throw Exception('Could not reach the server. Check your internet connection.');
    }

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Failed to load points'));
  }
}