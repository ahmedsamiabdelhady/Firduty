// api_service.dart — REST API communication layer for Firduty
//
// ── API base URL ─────────────────────────────────────────────────────────────
// Injected at build/run time via --dart-define:
//
//   Platform              Command                                  Note
//   ─────────────────     ──────────────────────────────────────   ──────────
//   Flutter Web (Chrome)  --dart-define=API_BASE_URL=http://localhost:8000
//   Android Studio emu    --dart-define=API_BASE_URL=http://10.0.2.2:8000
//   Genymotion emulator   --dart-define=API_BASE_URL=http://10.0.3.2:8000
//   Physical device       --dart-define=API_BASE_URL=http://<LAN-IP>:8000
//   Production            --dart-define=API_BASE_URL=https://your-app.koyeb.app
//
//   API_BASE_URL must NOT have a trailing slash.
//
// ── Timezone-safe endpoints (preferred for Flutter mobile) ────────────────────
// The server resolves "today" and "current week" in Asia/Muscat timezone,
// so the result is correct regardless of the device's timezone setting.
//
//   getTeacherToday()        → GET /teachers/{id}/today
//   getTeacherCurrentWeek()  → GET /teachers/{id}/current-week
//
// The legacy methods (getTeacherSchedule, getTeacherWeek) that require the
// client to pass a date are kept for backward compatibility.
//
// ── Debug logging ─────────────────────────────────────────────────────────────
// Every HTTP response is logged in debug builds:
//   [API] GET http://…/teachers/5/today → 200 (143 ms)
//   [API] GET http://…/teachers/5/today → 404
//           body: {"detail":"Teacher not found"}
//
// ── Centralization ────────────────────────────────────────────────────────────
// ALL endpoint paths live here. No screen constructs URLs directly.

import 'dart:convert';
import 'package:flutter/foundation.dart' show kDebugMode, debugPrint;
import 'package:http/http.dart' as http;

class ApiService {
  // ── Single source of truth for the backend URL ─────────────────────────────
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://SERVER-NOT-CONFIGURED',
  );

  /// Reusable HTTP client — avoids re-opening a TCP socket on every request.
  static final http.Client _client = http.Client();

  /// Global request timeout — prevents indefinite hangs on slow networks.
  static const Duration _timeout = Duration(seconds: 15);

  // ── Endpoint paths (all defined here, not in screen code) ──────────────────
  static String _pathRegister()                   => '$baseUrl/teachers/register';
  static String _pathStatus(int id)               => '$baseUrl/teachers/$id/status';

  // Timezone-safe (server resolves Oman date) — PREFERRED for mobile
  static String _pathToday(int id)                => '$baseUrl/teachers/$id/today';
  static String _pathCurrentWeek(int id)          => '$baseUrl/teachers/$id/current-week';

  // Legacy (client supplies date) — kept for backward compatibility
  static String _pathSchedule(int id, String d)   => '$baseUrl/teachers/$id/schedule?date=$d';
  static String _pathWeek(int id, String ws)       => '$baseUrl/teachers/$id/week?week_start=$ws';

  static String _pathConfirm(int id)              => '$baseUrl/points/teachers/$id/confirm';
  static String _pathPoints(int id, int y, int m) => '$baseUrl/points/teachers/$id/monthly?year=$y&month=$m';
  static String _pathDeviceToken(int id)          => '$baseUrl/teachers/$id/device-token';
  static String _pathUpdateTeacher(int id)        => '$baseUrl/teachers/$id';

  // ── Debug logger ────────────────────────────────────────────────────────────

  static void _log(String method, String url, http.Response res, DateTime start) {
    if (!kDebugMode) return;
    final ms   = DateTime.now().difference(start).inMilliseconds;
    final code = res.statusCode;
    if (code >= 200 && code < 300) {
      debugPrint('[API] $method $url → $code ($ms ms)');
    } else {
      final raw = utf8.decode(res.bodyBytes);
      final snippet = raw.length > 300 ? '${raw.substring(0, 300)}…' : raw;
      debugPrint('[API] $method $url → $code ($ms ms)\n        body: $snippet');
    }
  }

  // ── Response helpers ────────────────────────────────────────────────────────

  static Map<String, dynamic>? _tryDecode(http.Response res) {
    try {
      final d = jsonDecode(utf8.decode(res.bodyBytes));
      return d is Map<String, dynamic> ? d : null;
    } catch (_) {
      return null;
    }
  }

  static String _errorMessage(http.Response res, String fallback) {
    final body = _tryDecode(res);
    if (body != null) {
      final detail = body['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
    }
    switch (res.statusCode) {
      case 404: return 'The requested resource was not found (404). Check API_BASE_URL.';
      case 500: return 'Server internal error (500). Check backend logs.';
      case 502: case 503:
        return 'Server starting up or temporarily unavailable. Try again in a moment.';
      default: return '$fallback (HTTP ${res.statusCode})';
    }
  }

  static void _checkBaseUrl() {
    if (baseUrl == 'http://SERVER-NOT-CONFIGURED') {
      throw Exception(
        'API_BASE_URL is not configured.\n'
        'Run with:\n'
        '  --dart-define=API_BASE_URL=http://10.0.3.2:8000   (Genymotion)\n'
        '  --dart-define=API_BASE_URL=http://10.0.2.2:8000   (Android Studio)\n'
        '  --dart-define=API_BASE_URL=http://localhost:8000   (Flutter Web)\n'
        '  --dart-define=API_BASE_URL=https://your-app.koyeb.app  (production)',
      );
    }
  }

  static Future<http.Response> _get(String url) async {
    return _client.get(Uri.parse(url)).timeout(_timeout);
  }

  // ── Registration & Status ───────────────────────────────────────────────────

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

  /// Login with name + email — returns the teacher record on success.
  /// Throws descriptive Exception on 404 (not found), 409 (name mismatch),
  /// 403 (pending / inactive).
  static Future<Map<String, dynamic>> loginTeacher({
    required String name,
    required String email,
  }) async {
    _checkBaseUrl();
    final url   = '$baseUrl/teachers/login';
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
        'Make sure the backend is running and API_BASE_URL is correct.',
      );
    }

    _log('POST', url, res, start);

    if (res.statusCode == 200) {
      final body = _tryDecode(res);
      if (body != null) return body;
      throw Exception('Unexpected response from server.');
    }
    if (res.statusCode == 404) {
      throw Exception(
          'No account found with this email. Please register first.');
    }
    if (res.statusCode == 409) {
      throw Exception(
          'The name you entered does not match the registered name for this email.');
    }
    if (res.statusCode == 403) {
      final body = _tryDecode(res);
      throw Exception(
          (body?['detail'] as String?) ??
          'Your account is pending admin approval.');
    }
    throw Exception(_errorMessage(res, 'Login failed'));
  }

  static Future<Map<String, dynamic>> getTeacherStatus(int teacherId) async {
    _checkBaseUrl();
    final url   = _pathStatus(teacherId);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _get(url);
    } catch (e) {
      debugPrint('[API] GET $url → CONNECTION ERROR: $e');
      throw Exception('Could not reach the server. Check API_BASE_URL.');
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

  // ── Schedule — Timezone-safe (PREFERRED for mobile today tab) ───────────────

  /// Fetch today's duties using the **server's** Asia/Muscat clock.
  ///
  /// No date parameter needed. The server resolves "today in Oman" correctly
  /// regardless of the device timezone setting.
  ///
  /// Returns `{teacher_id, teacher_name, week_status, duties}`.
  static Future<Map<String, dynamic>> getTeacherToday({
    required int teacherId,
  }) async {
    _checkBaseUrl();
    final url   = _pathToday(teacherId);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _get(url);
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

  /// Fetch the current week's duties using the **server's** Asia/Muscat clock.
  ///
  /// No week_start parameter needed. The server resolves the current Oman
  /// school week (Sunday–Thursday) correctly regardless of the device timezone.
  ///
  /// Returns `{teacher_id, teacher_name, week_status, duties}`.
  static Future<Map<String, dynamic>> getTeacherCurrentWeek({
    required int teacherId,
  }) async {
    _checkBaseUrl();
    final url   = _pathCurrentWeek(teacherId);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _get(url);
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
    throw Exception(_errorMessage(res, 'Could not load current week duties'));
  }

  // ── Schedule — Legacy (client supplies date) ──────────────────────────────

  /// Fetch duties for a specific date supplied by the client.
  ///
  /// Prefer [getTeacherToday] to avoid timezone mismatch on mobile.
  static Future<Map<String, dynamic>> getTeacherSchedule({
    required int teacherId,
    required String date, // YYYY-MM-DD
  }) async {
    _checkBaseUrl();
    final url   = _pathSchedule(teacherId, date);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _get(url);
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

  /// Fetch duties for a specific week supplied by the client.
  ///
  /// Prefer [getTeacherCurrentWeek] to avoid timezone mismatch on mobile.
  static Future<Map<String, dynamic>> getTeacherWeek({
    required int teacherId,
    required String weekStart, // YYYY-MM-DD (Sunday)
  }) async {
    _checkBaseUrl();
    final url   = _pathWeek(teacherId, weekStart);
    final start = DateTime.now();
    late http.Response res;

    try {
      res = await _get(url);
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
      res = await _get(url);
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

  static Future<void> registerDeviceToken({
    required int teacherId,
    required String token,
    required String platform,
    required String installationId,
  }) async {
    if (baseUrl == 'http://SERVER-NOT-CONFIGURED') return;
    if (token.trim().isEmpty || installationId.trim().isEmpty) return;

    final url   = _pathDeviceToken(teacherId);
    final start = DateTime.now();

    try {
      final res = await _client
          .post(
            Uri.parse(url),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'token': token,
              'platform': platform,
              'installation_id': installationId,
            }),
          )
          .timeout(_timeout);
      _log('POST', url, res, start);
    } catch (e) {
      debugPrint('[API] POST $url → device token registration failed: $e');
    }
  }

  static Future<void> deleteDeviceToken({
    required int teacherId,
    required String installationId,
  }) async {
    if (baseUrl == 'http://SERVER-NOT-CONFIGURED') return;
    if (installationId.trim().isEmpty) return;

    final url   = _pathDeviceToken(teacherId);
    final start = DateTime.now();

    try {
      final request = http.Request('DELETE', Uri.parse(url))
        ..headers['Content-Type'] = 'application/json'
        ..body = jsonEncode({'installation_id': installationId});

      final streamed = await _client.send(request).timeout(_timeout);
      final res = await http.Response.fromStream(streamed);
      _log('DELETE', url, res, start);
    } catch (e) {
      debugPrint('[API] DELETE $url → device token deletion failed: $e');
    }
  }

  // ── Teacher profile ──────────────────────────────────────────────────────

  static Future<void> updateTeacherLanguage({
    required int teacherId,
    required String lang,
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
