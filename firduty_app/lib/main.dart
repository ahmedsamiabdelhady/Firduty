// main.dart — Firduty Flutter App entry point
//
// Platforms:
//   Android  — native APK, FCM push notifications via firebase_messaging
//   Web/PWA  — Flutter web build, works on Chrome + iOS Safari 16.4+ PWA
//
// dart:io is NOT imported here — it is unavailable on Flutter Web.
// All platform branching uses kIsWeb from flutter/foundation.dart.
//
// ── Startup order ───────────────────────────────────────────────────────────
//  1. WidgetsFlutterBinding.ensureInitialized()
//  2. Firebase.initializeApp()  ← guarded + try/catch (never crashes the app)
//  3. runApp(FirdutyApp)        ← first frame rendered immediately after
//  4. FirdutyApp._initLocale()  ← reads SharedPreferences async, sets locale
//  5. StartupScreen._route()    ← deferred to post-frame, reads teacher_id
//  6. NotificationService.initialize()  ← only when teacher is approved
//
// ── Firebase duplicate-app safety ───────────────────────────────────────────
// Flutter Web hot restart does NOT tear down the JS runtime. The Firebase JS
// SDK therefore keeps its [DEFAULT] app alive between restarts. Calling
// Firebase.initializeApp() again throws [core/duplicate-app].
//
// The fix is two-layered:
//   (a) Firebase.apps.isEmpty guard  — skips the call when app already exists
//   (b) try/catch around the entire block — catches any unexpected edge case
//       (emulator weirdness, test environments, future SDK changes)
//
// On Android, the Dart VM IS torn down on hot restart, so Firebase.apps is
// always empty — the guard is harmless there.

import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'firebase_options.dart';
import 'screens/teacher_select_screen.dart' show RegistrationScreen;
import 'screens/pending_screen.dart';
import 'screens/today_screen.dart';
import 'screens/week_screen.dart';
import 'screens/points_screen.dart';
import 'services/api_service.dart';
import 'services/notification_service.dart';
import 'gen/app_localizations.dart';
import 'app_theme.dart';

Future<void> main() async {
  // ── Step 1: bind Flutter engine ─────────────────────────────────────────
  WidgetsFlutterBinding.ensureInitialized();

  // ── Step 2: safe Firebase initialization ───────────────────────────────
  // Both layers of protection are needed:
  //   (a) Firebase.apps.isEmpty  → prevents duplicate-app on web hot restart
  //   (b) try/catch              → catches emulator weirdness / edge cases
  try {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      debugPrint('[Firebase] Initialized successfully.');
    } else {
      debugPrint('[Firebase] Already initialized — skipping.');
    }
  } catch (e) {
    // Log the error but never crash. The app can still run without Firebase
    // (teachers can view their schedule; they just won't receive push).
    debugPrint('[Firebase] Init skipped / already exists: $e');
  }

  // ── Step 3: start the UI ───────────────────────────────────────────────
  // runApp() is called immediately after Firebase init. SharedPreferences
  // and NotificationService are initialised later (inside StartupScreen and
  // PendingScreen) so the first frame is rendered without blocking.
  runApp(const FirdutyApp());
}

// ─── Root widget ──────────────────────────────────────────────────────────────

class FirdutyApp extends StatefulWidget {
  const FirdutyApp({super.key});

  @override
  State<FirdutyApp> createState() => _FirdutyAppState();
}

class _FirdutyAppState extends State<FirdutyApp> {
  Locale? _locale;

  @override
  void initState() {
    super.initState();
    _initLocale();
  }

  Future<void> _initLocale() async {
    final prefs = await SharedPreferences.getInstance();
    final savedLang = prefs.getString('language');
    if (savedLang != null) {
      setState(() => _locale = Locale(savedLang));
    } else {
      setState(() => _locale = const Locale('ar')); // default: Arabic
    }
  }

  void _changeLocale(Locale locale) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', locale.languageCode);
    setState(() => _locale = locale);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Firduty',
      debugShowCheckedModeBanner: false,
      theme: buildFirdutyTheme(),
      locale: _locale,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('ar'), Locale('en')],
      initialRoute: '/',
      onGenerateRoute: (settings) {
        switch (settings.name) {
          case '/':
            return MaterialPageRoute(
              builder: (_) => StartupScreen(onLocaleChange: _changeLocale),
            );
          case '/register':
            return MaterialPageRoute(
              builder: (_) => const RegistrationScreen(),
            );
          case '/pending':
            return MaterialPageRoute(
              builder: (_) => PendingScreen(onLocaleChange: _changeLocale),
            );
          case '/home':
            return MaterialPageRoute(
              builder: (_) => HomeScreen(onLocaleChange: _changeLocale),
            );
          default:
            return MaterialPageRoute(
              builder: (_) => StartupScreen(onLocaleChange: _changeLocale),
            );
        }
      },
    );
  }
}

// ─── Startup Screen ───────────────────────────────────────────────────────────
// Renders immediately (splash logo + spinner), then routes based on teacher state.
//
// Routing:
//   no teacher_id in prefs          → /register
//   teacher_id + status=approved    → NotificationService.initialize() → /home
//   teacher_id + status=pending     → /pending
//   teacher_id + 404 from server    → clear prefs → /register
//   network / server error          → /pending  (graceful degradation)

class StartupScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const StartupScreen({super.key, required this.onLocaleChange});

  @override
  State<StartupScreen> createState() => _StartupScreenState();
}

class _StartupScreenState extends State<StartupScreen> {
  @override
  void initState() {
    super.initState();
    // Defer routing until after the first frame so the splash is visible.
    WidgetsBinding.instance.addPostFrameCallback((_) => _route());
  }

  Future<void> _route() async {
    final prefs     = await SharedPreferences.getInstance();
    final teacherId = prefs.getInt('teacher_id');

    if (teacherId == null) {
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/register');
      return;
    }

    try {
      final result = await ApiService.getTeacherStatus(teacherId);
      final status = result['status'] as String;

      if (status == 'approved') {
        // NotificationService.initialize() is idempotent — safe to call here
        // even if PendingScreen already called it (it skips if done).
        final platform = kIsWeb ? 'web' : 'android';
        await NotificationService.initialize(
          teacherId: teacherId,
          platform: platform,
        );
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/home');
      } else {
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/pending');
      }
    } catch (e) {
      if (e.toString().contains('404')) {
        await prefs.remove('teacher_id');
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/register');
      } else {
        // Server unreachable — show pending screen so teacher can retry.
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/pending');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FirdutyColors.navBlue,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Image.asset('assets/logo.png', width: 120, height: 120),
            const SizedBox(height: 32),
            const CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Home Screen — 3 tabs ─────────────────────────────────────────────────────

class HomeScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const HomeScreen({super.key, required this.onLocaleChange});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;

  final List<Widget> _screens = const [
    TodayScreen(),
    WeekScreen(),
    PointsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final l10n   = AppLocalizations.of(context);
    final isAr   = Localizations.localeOf(context).languageCode == 'ar';
    final titles = [l10n.todayDuties, l10n.weekDuties, l10n.myPoints];

    return Scaffold(
      appBar: AppBar(
        title: Text(titles[_selectedIndex]),
        centerTitle: true,
        backgroundColor: FirdutyColors.navBlue,
        foregroundColor: Colors.white,
        actions: [
          TextButton(
            onPressed: () {
              widget.onLocaleChange(
                  isAr ? const Locale('en') : const Locale('ar'));
            },
            child: Text(
              isAr ? 'EN' : 'عربي',
              style: const TextStyle(color: Colors.white, fontSize: 14),
            ),
          ),
        ],
      ),
      body: IndexedStack(
        // IndexedStack keeps screen state alive when switching tabs,
        // avoiding unnecessary reloads.
        index: _selectedIndex,
        children: _screens,
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (i) => setState(() => _selectedIndex = i),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.today_outlined),
            selectedIcon: const Icon(Icons.today),
            label: l10n.todayDuties,
          ),
          NavigationDestination(
            icon: const Icon(Icons.calendar_month_outlined),
            selectedIcon: const Icon(Icons.calendar_month),
            label: l10n.weekDuties,
          ),
          NavigationDestination(
            icon: const Icon(Icons.star_outline),
            selectedIcon: const Icon(Icons.star),
            label: l10n.myPoints,
          ),
        ],
      ),
    );
  }
}
