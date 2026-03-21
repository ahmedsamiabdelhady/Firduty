import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart' show debugPrint, kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_theme.dart';
import 'firebase_options.dart';
import 'gen/app_localizations.dart';
import 'screens/login_screen.dart';
import 'screens/pending_screen.dart';
import 'screens/points_screen.dart';
import 'screens/teacher_select_screen.dart' show RegistrationScreen;
import 'screens/today_screen.dart';
import 'screens/week_screen.dart';
import 'services/api_service.dart';
import 'services/notification_service.dart';
import 'widgets/notification_bell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      debugPrint('[Firebase] Initialized successfully.');
    } else {
      debugPrint('[Firebase] Already initialized — skipping.');
    }
  } catch (e, st) {
    debugPrint('[Firebase] Init failed: $e');
    debugPrint('[Firebase] runtimeType: ${e.runtimeType}');
    debugPrint('$st');
  }

  runApp(const FirdutyApp());
}

class FirdutyApp extends StatefulWidget {
  const FirdutyApp({super.key});

  @override
  State<FirdutyApp> createState() => _FirdutyAppState();
}

class _FirdutyAppState extends State<FirdutyApp> {
  Locale? _locale;

  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  @override
  void initState() {
    super.initState();
    _initLocale();
    NotificationService.navigatorKey = _navigatorKey;
    NotificationService.loadBellState();
  }

  Future<void> _initLocale() async {
    final prefs = await SharedPreferences.getInstance();
    final savedLang = prefs.getString('language');

    if (!mounted) return;

    setState(() {
      _locale = savedLang != null ? Locale(savedLang) : const Locale('ar');
    });
  }

  Future<void> _changeLocale(Locale locale) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', locale.languageCode);

    if (!mounted) return;
    setState(() => _locale = locale);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Firduty',
      debugShowCheckedModeBanner: false,
      theme: buildFirdutyTheme(),
      navigatorKey: _navigatorKey,
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
          case '/login':
            return MaterialPageRoute(
              builder: (_) => LoginScreen(onLocaleChange: _changeLocale),
            );
          case '/register':
            return MaterialPageRoute(
              builder: (_) => RegistrationScreen(onLocaleChange: _changeLocale),
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

class StartupScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;

  const StartupScreen({
    super.key,
    required this.onLocaleChange,
  });

  @override
  State<StartupScreen> createState() => _StartupScreenState();
}

class _StartupScreenState extends State<StartupScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _route());
  }

  Future<void> _route() async {
    final prefs = await SharedPreferences.getInstance();
    final teacherId = prefs.getInt('teacher_id');

    if (teacherId == null) {
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/login');
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
      if (e.toString().contains('404')) {
        await prefs.remove('teacher_id');

        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/login');
      } else {
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

class HomeScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;

  const HomeScreen({
    super.key,
    required this.onLocaleChange,
  });

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
        backgroundColor: FirdutyColors.navBlue,
        foregroundColor: Colors.white,
        actions: [
          const NotificationBellButton(iconColor: Colors.white),
          TextButton(
            onPressed: () {
              widget.onLocaleChange(
                isAr ? const Locale('en') : const Locale('ar'),
              );
            },
            child: Text(
              isAr ? 'EN' : 'عربي',
              style: const TextStyle(color: Colors.white, fontSize: 14),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.logout, color: Colors.white),
            tooltip: isAr ? 'تسجيل الخروج' : 'Sign Out',
            onPressed: () async {
              final prefs = await SharedPreferences.getInstance();
              final teacherId = prefs.getInt('teacher_id');

              await NotificationService.reset(teacherId: teacherId);
              await prefs.remove('teacher_id');

              if (!context.mounted) return;
              Navigator.pushReplacementNamed(context, '/login');
            },
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