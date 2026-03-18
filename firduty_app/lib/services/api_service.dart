// api_service.dart — REST API communication layer for Firduty
//
// ── API base URL ─────────────────────────────────────────────────────────────
// The backend URL is injected at build/run time via --dart-define:
//
//   Platform              Command                                  Note
//   ─────────────────     ──────────────────────────────────────   ──────────────────────────────
//   Flutter Web (Chrome)  --dart-define=API_BASE_URL=http://localhost:8000
//   Android Studio emu    --dart-define=API_BASE_URL=http://10.0.2.2:8000   AVD host alias
//   Genymotion emulator   --dart-define=API_BASE_URL=http://10.0.3.2:8000   Genymotion host alias
//   Physical device       --dart-define=API_BASE_URL=http://<LAN-IP>:8000   find with `ipconfig`/`ifconfig`
//   Production            --dart-define=API_BASE_URL=https://your-app.koyeb.app
//
//   API_BASE_URL must NOT have a trailing slash.
//
//   To find your LAN IP (host machine):
//     macOS / Linux:  ifconfig | grep "inet " | grep -v 127
//     Windows:        ipconfig | findstr "IPv4"
//
// ── Debug logging ─────────────────────────────────────────────────────────────
// Every HTTP response is logged in debug mode:
//   [API] POST http://10.0.3.2:8000/teachers/register → 201 (143 ms)
//   [API] GET  http://10.0.3.2:8000/teachers/5/status → 404
//           body: {"detail":"Teacher not found"}
//
// ── Centralization ────────────────────────────────────────────────────────────
// ALL endpoint paths live here. No screen or service constructs URLs directly.

import 'dart:convert';
import 'package:flutter/foundation.dart' show kDebugMode, debugPrint;
import 'package:http/http.dart' as http;

class ApiService {
  // ── Single source of truth for the backend URL ─────────────────────────────
  //
  // If API_BASE_URL was not passed via --dart-define, the app will still compile
  // but every request will fail with a clear "server not configured" message
  // (not a raw connection error or JSON parse crash).
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://SERVER-NOT-CONFIGURED',
  );

  /// Reusable HTTP client — avoids re-opening a TCP socket on every request.
  static final http.Client _client = http.Client();

  /// Global request timeout — prevents indefinite hangs on slow networks.
  static const Duration _timeout = Duration(seconds: 15);

  // ── Endpoint paths (all defined here, not in screen code) ──────────────────
  static String _pathRegister()               => '$baseUrl/teachers/register';
  static String _pathStatus(int id)           => '$baseUrl/teachers/$id/status';
  static String _pathSchedule(int id, String date)   => '$baseUrl/teachers/$id/schedule?date=$date';
  static String _pathWeek(int id, String ws)  => '$baseUrl/teachers/$id/week?week_start=$ws';
  static String _pathConfirm(int id)          => '$baseUrl/points/teachers/$id/confirm';
  static String _pathPoints(int id, int y, int m)    => '$baseUrl/points/teachers/$id/monthly?year=$y&month=$m';
  static String _pathDeviceToken(int id)      => '$baseUrl/teachers/$id/device-token';
  static String _pathUpdateTeacher(int id)    => '$baseUrl/teachers/$id';

  // ── Debug logger ────────────────────────────────────────────────────────────

  /// Log every HTTP response in debug builds.
  ///
  /// Format:
  ///   [API] POST http://10.0.3.2:8000/teachers/register → 201 (87 ms)
  ///   [API] GET  http://10.0.3.2:8000/teachers/5/status → 404
  ///           body: {"detail":"Teacher not found"}
  static void _log(
    String method,
    String url,
    http.Response res,
    DateTime start,
  ) {
    if (!kDebugMode) return;

    final ms      = DateTime.now().difference(start).inMilliseconds;
    final code    = res.statusCode;
    final timeTag = '($ms ms)';

    // Only show body on non-2xx responses — keeps success logs concise.
    if (code >= 200 && code < 300) {
      debugPrint('[API] $method $url → $code $timeTag');
    } else {
      final rawBody = utf8.decode(res.bodyBytes);
      // Truncate very long bodies (e.g. HTML error pages from Nginx/Koyeb).
      final snippet = rawBody.length > 300
          ? '${rawBody.substring(0, 300)}…'
          : rawBody;
      debugPrint('[API] $method $url → $code $timeTag\n        body: $snippet');
    }
  }

  // ── Response helpers ────────────────────────────────────────────────────────

  /// Safely decode a JSON response body.
  /// Returns null if the body is not valid JSON (e.g. an HTML 502 page).
  static Map<String, dynamic>? _tryDecode(http.Response res) {
    try {
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  /// Build a user-friendly error message from a failed HTTP response.
  ///
  /// Priority:
  ///  1. Backend JSON `detail` field
  ///  2. Status-code-specific human messages (404, 500, 502/503)
  ///  3. Fallback + raw status code
  static String _errorMessage(http.Response res, String fallback) {
    final body = _tryDecode(res);
    if (body != null) {
      final detail = body['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
    }
    switch (res.statusCode) {
      case 404:
        return 'The requested resource was not found (404). '
               'Check that API_BASE_URL is correct and the backend is running.';
      case 500:
        return 'The server encountered an internal error (500). '
               'Check the backend logs.';
      case 502:
      case 503:
        return 'The server is starting up or temporarily unavailable. '
               'Please try again in a few seconds.';
      default:
        return '$fallback (HTTP ${res.statusCode})';
    }
  }

  /// Thrown when the app was built without a valid API_BASE_URL.
  static void _checkBaseUrl() {
    if (baseUrl == 'http://SERVER-NOT-CONFIGURED') {
      throw Exception(
        'API_BASE_URL is not configured.\n'
        'Run the app with:\n'
        '  --dart-define=API_BASE_URL=http://10.0.3.2:8000   (Genymotion)\n'
        '  --dart-define=API_BASE_URL=http://10.0.2.2:8000   (Android Studio emulator)\n'
        '  --dart-define=API_BASE_URL=http://localhost:8000   (Flutter Web / Chrome)\n'
        '  --dart-define=API_BASE_URL=https://your-app.koyeb.app  (production)',
      );
    }
  }

  // ── Registration & Status ───────────────────────────────────────────────────

  /// Self-register a new teacher.
  ///
  /// Returns `{id, name, email, status: "pending"}` on success.
  /// Throws a user-friendly [Exception] on failure.
  static Future<Map<String, dynamic>> registerTeacher({
    required String name,
    required String email,
  }) async {
    _checkBaseUrl();
    final url   = _pathRegister();
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _client
          .post(
            Uri.parse(url),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'name': name, 'email': email}),
          )
          .timeout(_timeout);
    } catch (e) {
      debugPrint('[API] POST $url → CONNECTION ERROR: $e');
      throw Exception(
        'Could not reach the server.\n'
        'Make sure the backend is running and API_BASE_URL is correct.\n'
        '  Genymotion:      http://10.0.3.2:8000\n'
        '  Android Studio:  http://10.0.2.2:8000\n'
        '  Flutter Web:     http://localhost:8000',
      );
    }

    _log('POST', url, res, start);

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
  ///
  /// Returns `{id, name, email, status}`.
  /// Throws `Exception('404: ...')` when the teacher record is not found.
  static Future<Map<String, dynamic>> getTeacherStatus(int teacherId) async {
    _checkBaseUrl();
    final url   = _pathStatus(teacherId);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _client.get(Uri.parse(url)).timeout(_timeout);
    } catch (e) {
      debugPrint('[API] GET $url → CONNECTION ERROR: $e');
      throw Exception(
        'Could not reach the server. '
        'Check that the backend is running and API_BASE_URL is set correctly.',
      );
    }

    _log('GET', url, res, start);

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    if (res.statusCode == 404) {
      throw Exception('404: Teacher record not found. Please register again.');
    }
    throw Exception(_errorMessage(res, 'Could not fetch teacher status'));
  }

  // ── Schedule ────────────────────────────────────────────────────────────────

  /// Returns today's duties for a teacher.
  ///
  /// [date] is `YYYY-MM-DD`.
  static Future<Map<String, dynamic>> getTeacherSchedule({
    required int teacherId,
    required String date,
  }) async {
    _checkBaseUrl();
    final url   = _pathSchedule(teacherId, date);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _client.get(Uri.parse(url)).timeout(_timeout);
    } catch (e) {
      debugPrint('[API] GET $url → CONNECTION ERROR: $e');
      throw Exception('Could not reach the server. Check your connection.');
    }

    _log('GET', url, res, start);

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, "Could not load today's duties"));
  }

  /// Returns the full week's duties for a teacher.
  ///
  /// [weekStart] is the Sunday of that week as `YYYY-MM-DD`.
  static Future<Map<String, dynamic>> getTeacherWeek({
    required int teacherId,
    required String weekStart,
  }) async {
    _checkBaseUrl();
    final url   = _pathWeek(teacherId, weekStart);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _client.get(Uri.parse(url)).timeout(_timeout);
    } catch (e) {
      debugPrint('[API] GET $url → CONNECTION ERROR: $e');
      throw Exception('Could not reach the server. Check your connection.');
    }

    _log('GET', url, res, start);

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Could not load week duties'));
  }

  // ── Confirmation ─────────────────────────────────────────────────────────

  /// Confirm a duty assignment.
  ///
  /// Returns `{assignment_id, teacher_id, points_earned, message_en, message_ar}`.
  static Future<Map<String, dynamic>> confirmDuty({
    required int teacherId,
    required int assignmentId,
  }) async {
    _checkBaseUrl();
    final url   = _pathConfirm(teacherId);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _client
          .post(
            Uri.parse(url),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'assignment_id': assignmentId}),
          )
          .timeout(_timeout);
    } catch (e) {
      debugPrint('[API] POST $url → CONNECTION ERROR: $e');
      throw Exception('Could not reach the server. Check your connection.');
    }

    _log('POST', url, res, start);

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Could not confirm duty'));
  }

  // ── Points ───────────────────────────────────────────────────────────────

  /// Returns monthly points summary for a teacher.
  ///
  /// Returns `{total_points, duties: [...], confirmations: N, ...}`.
  static Future<Map<String, dynamic>> getTeacherPoints({
    required int teacherId,
    required int year,
    required int month,
  }) async {
    _checkBaseUrl();
    final url   = _pathPoints(teacherId, year, month);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _client.get(Uri.parse(url)).timeout(_timeout);
    } catch (e) {
      debugPrint('[API] GET $url → CONNECTION ERROR: $e');
      throw Exception('Could not reach the server. Check your connection.');
    }

    _log('GET', url, res, start);

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    throw Exception(_errorMessage(res, 'Could not load points'));
  }

  // ── Device token ─────────────────────────────────────────────────────────

  /// Register an FCM / VAPID push token for a teacher.
  ///
  /// Non-fatal — silently swallowed if it fails so the app continues.
  static Future<void> registerDeviceToken({
    required int teacherId,
    required String token,
    required String platform,
  }) async {
    if (baseUrl == 'http://SERVER-NOT-CONFIGURED') return;
    final url   = _pathDeviceToken(teacherId);
    final start = DateTime.now();

    try {
      final res = await _client
          .post(
            Uri.parse(url),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'token': token, 'platform': platform}),
          )
          .timeout(_timeout);
      _log('POST', url, res, start);
    } catch (e) {
      // Non-critical — push notifications will simply not work.
      debugPrint('[API] POST $url → device token registration failed: $e');
    }
  }

  // ── Teacher profile ──────────────────────────────────────────────────────

  /// Update the teacher's preferred display language on the backend.
  ///
  /// Non-fatal — silently swallowed if it fails.
  static Future<void> updateTeacherLanguage({
    required int teacherId,
    required String lang, // 'ar' or 'en'
  }) async {
    if (baseUrl == 'http://SERVER-NOT-CONFIGURED') return;
    final url   = _pathUpdateTeacher(teacherId);
    final start = DateTime.now();

    try {
      final res = await _client
          .put(
            Uri.parse(url),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'preferred_language': lang}),
          )
          .timeout(_timeout);
      _log('PUT', url, res, start);
    } catch (e) {
      debugPrint('[API] PUT $url → language update failed: $e');
    }
  }
}
