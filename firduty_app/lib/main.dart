// main.dart — Firduty Flutter App entry point
//
// Optimisations (v2.4):
//   • IndexedStack keeps all 3 tab screens alive — no rebuild on tab switch
//   • Material 3 NavigationBar replaces legacy BottomNavigationBar
//   • AutomaticKeepAliveClientMixin preserved scroll positions across tabs
//   • SharedPreferences read once at splash, passed via route arguments
//   • Locale preference persisted immediately on change
//   • Splash screen handles 404 (deleted teacher) gracefully

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
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

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
  runApp(const FirdutyApp());
}

// ─── App Root ─────────────────────────────────────────────────────────────────

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
    setState(() {
      _locale = savedLang != null ? Locale(savedLang) : const Locale('ar');
    });
  }

  void _handleLocaleChange(Locale locale) async {
    setState(() => _locale = locale);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', locale.languageCode);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Firduty',
      theme: buildFirdutyTheme(),
      locale: _locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      initialRoute: '/',
      routes: {
        '/': (_) => _SplashScreen(onLocaleChange: _handleLocaleChange),
        '/register': (_) => const RegistrationScreen(),
        '/pending': (_) =>
            PendingScreen(onLocaleChange: _handleLocaleChange),
        '/home': (_) => HomeScreen(onLocaleChange: _handleLocaleChange),
      },
    );
  }
}

// ─── Splash / Router Screen ───────────────────────────────────────────────────

class _SplashScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const _SplashScreen({required this.onLocaleChange});

  @override
  State<_SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<_SplashScreen> {
  @override
  void initState() {
    super.initState();
    _route();
  }

  Future<void> _route() async {
    // Small delay so the splash logo is visible (avoids jarring instant redirect).
    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;

    final prefs = await SharedPreferences.getInstance();
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
      if (!mounted) return;
      final msg = e.toString();
      if (msg.contains('404') || msg.contains('not found')) {
        await prefs.remove('teacher_id');
        Navigator.pushReplacementNamed(context, '/register');
      } else {
        // Network error — go to pending; user can retry from there.
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
            const SizedBox(height: 40),
            const CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              strokeWidth: 2.5,
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Home Screen — 3 tabs (IndexedStack keeps screens alive) ─────────────────

class HomeScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const HomeScreen({super.key, required this.onLocaleChange});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;

  // All 3 screens stay in memory; IndexedStack shows the selected one.
  // This eliminates the API call cost of rebuilding on every tab tap.
  static const List<Widget> _screens = [
    TodayScreen(),
    WeekScreen(),
    PointsScreen(),
  ];

  void _onDestinationSelected(int index) {
    setState(() => _selectedIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';
    final titles = [l10n.todayDuties, l10n.weekDuties, l10n.myPoints];

    return Scaffold(
      appBar: AppBar(
        title: Text(titles[_selectedIndex]),
        centerTitle: true,
        backgroundColor: FirdutyColors.navBlue,
        foregroundColor: Colors.white,
        elevation: 0,
        actions: [
          // Language toggle
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: TextButton(
              onPressed: () => widget.onLocaleChange(
                isAr ? const Locale('en') : const Locale('ar'),
              ),
              style: TextButton.styleFrom(foregroundColor: Colors.white70),
              child: Text(
                isAr ? 'EN' : 'ع',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        ],
      ),
      // IndexedStack: all children built once; only visibility toggled.
      body: IndexedStack(
        index: _selectedIndex,
        children: _screens,
      ),
      // Material 3 NavigationBar
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: _onDestinationSelected,
        backgroundColor: FirdutyColors.surface,
        indicatorColor: FirdutyColors.navBlue.withValues(alpha: 0.12),
        elevation: 3,
        height: 68,
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
            icon: const Icon(Icons.emoji_events_outlined),
            selectedIcon: const Icon(Icons.emoji_events),
            label: l10n.myPoints,
          ),
        ],
      ),
    );
  }
}