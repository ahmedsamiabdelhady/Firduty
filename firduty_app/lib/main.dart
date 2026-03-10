// main.dart — Firduty Flutter App entry point

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/teacher_select_screen.dart' show RegistrationScreen;
import 'screens/pending_screen.dart';
import 'screens/today_screen.dart';
import 'screens/week_screen.dart';
import 'screens/points_screen.dart';
import 'services/api_service.dart';
import 'services/notification_service.dart';
import 'gen/app_localizations.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  runApp(const FirdutyApp());
}

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
      final deviceLang = Platform.localeName.split('_').first;
      final lang = ['ar', 'en'].contains(deviceLang) ? deviceLang : 'ar';
      setState(() => _locale = Locale(lang));
    }
    // Note: notification initialisation is intentionally deferred to StartupScreen
    // so it only runs after account approval is confirmed.
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
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
      ),
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

// ─── Startup Screen ─────────────────────────────────────────────────────────
// Shown on every launch. Reads local state and checks the backend,
// then redirects to /register, /pending, or /home.

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
    // Defer past the first frame so BuildContext / Navigator are ready
    WidgetsBinding.instance.addPostFrameCallback((_) => _route());
  }

  Future<void> _route() async {
    final prefs = await SharedPreferences.getInstance();
    final teacherId = prefs.getInt('teacher_id');

    if (teacherId == null) {
      // No local identity → show registration
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/register');
      return;
    }

    // Local identity exists → verify with backend
    try {
      final result = await ApiService.getTeacherStatus(teacherId);
      final status = result['status'] as String;

      if (status == 'approved') {
        // Init notifications only for approved teachers
        final platform = Platform.isIOS ? 'ios' : 'android';
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
      // 404 = teacher record deleted remotely; clear local state
      if (e.toString().contains('404')) {
        await prefs.remove('teacher_id');
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/register');
      } else {
        // Network error — fall through to pending screen; it has a retry button
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/pending');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // Shown for a fraction of a second while routing logic runs
    return const Scaffold(
      body: Center(child: CircularProgressIndicator()),
    );
  }
}

// ─── Home Screen — 3 tabs ──────────────────────────────────────────────────────

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
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    final titles = [l10n.todayDuties, l10n.weekDuties, l10n.myPoints];

    return Scaffold(
      appBar: AppBar(
        title: Text(titles[_selectedIndex]),
        centerTitle: true,
        backgroundColor: Theme.of(context).primaryColor,
        foregroundColor: Colors.white,
        actions: [
          TextButton(
            onPressed: () {
              widget.onLocaleChange(
                  isAr ? const Locale('en') : const Locale('ar'));
            },
            child: Text(
              isAr ? 'EN' : 'عربي',
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
      body: IndexedStack(
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
            icon: const Icon(Icons.calendar_view_week_outlined),
            selectedIcon: const Icon(Icons.calendar_view_week),
            label: l10n.weekDuties,
          ),
          NavigationDestination(
            icon: const Icon(Icons.emoji_events_outlined),
            selectedIcon: const Icon(Icons.emoji_events),
            label: l10n.myPoints,
          ),
        ],
      ),
    );
  }
}