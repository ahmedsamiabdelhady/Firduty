import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'firebase_options.dart';
import 'screens/teacher_select_screen.dart' show RegistrationScreen;
import 'screens/login_screen.dart';
import 'screens/pending_screen.dart';
import 'screens/today_screen.dart';
import 'screens/week_screen.dart';
import 'screens/points_screen.dart';
import 'widgets/notification_bell.dart';
import 'services/api_service.dart';
import 'services/notification_service.dart';
import 'gen/app_localizations.dart';
import 'app_theme.dart';

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  debugPrint('[MAIN] Background message: ${message.data}');
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      debugPrint('[Firebase] Initialized successfully.');
    }
  } catch (e) {
    debugPrint('[Firebase] Init skipped: $e');
  }

  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

  runApp(const FirdutyApp());
}

// ── App root ─────────────────────────────────────────────────────────────────

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
    NotificationService.navigatorKey = _navigatorKey;
    _initLocale();
  }

  Future<void> _initLocale() async {
    final prefs = await SharedPreferences.getInstance();
    final savedLang = prefs.getString('language');
    setState(() {
      _locale = (savedLang != null && savedLang.isNotEmpty)
          ? Locale(savedLang)
          : const Locale('ar');
    });
  }

  Future<void> _changeLocale(Locale locale) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', locale.languageCode);
    setState(() => _locale = locale);

    final teacherId = prefs.getInt('teacher_id');
    if (teacherId != null) {
      try {
        await ApiService.updateTeacherLanguage(
          teacherId: teacherId,
          lang: locale.languageCode,
        );
      } catch (e) {
        debugPrint('[Locale] Sync failed: $e');
      }
    }
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
            return _FadeRoute(
              builder: (_) => StartupScreen(onLocaleChange: _changeLocale),
            );
          case '/login':
            return _FadeRoute(
              builder: (_) => LoginScreen(onLocaleChange: _changeLocale),
            );
          case '/register':
            return _FadeRoute(
              builder: (_) => RegistrationScreen(onLocaleChange: _changeLocale),
            );
          case '/pending':
            return _FadeRoute(
              builder: (_) => PendingScreen(onLocaleChange: _changeLocale),
            );
          case '/home':
            return _FadeRoute(
              builder: (_) => HomeScreen(onLocaleChange: _changeLocale),
            );
          default:
            return _FadeRoute(
              builder: (_) => StartupScreen(onLocaleChange: _changeLocale),
            );
        }
      },
    );
  }
}

// ── Route helper ──────────────────────────────────────────────────────────────

class _FadeRoute<T> extends MaterialPageRoute<T> {
  _FadeRoute({required super.builder});

  @override
  Widget buildTransitions(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    return FadeTransition(
      opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
      child: child,
    );
  }
}

// ── Startup screen — branded splash ──────────────────────────────────────────

class StartupScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const StartupScreen({super.key, required this.onLocaleChange});

  @override
  State<StartupScreen> createState() => _StartupScreenState();
}

class _StartupScreenState extends State<StartupScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _fade;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 700));
    _fade = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
    _slide = Tween<Offset>(begin: const Offset(0, 0.12), end: Offset.zero)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic));
    _ctrl.forward();
    WidgetsBinding.instance.addPostFrameCallback((_) => _route());
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _route() async {
    // Small delay so the branded splash is visible even on fast devices
    await Future.delayed(const Duration(milliseconds: 800));

    final prefs = await SharedPreferences.getInstance();
    final teacherId = prefs.getInt('teacher_id');

    if (teacherId == null) {
      if (mounted) Navigator.pushReplacementNamed(context, '/login');
      return;
    }

    try {
      final result = await ApiService.getTeacherStatus(teacherId);
      final status = result['status'];

      if (status == 'approved') {
        await NotificationService.initialize(
          teacherId: teacherId,
          navigator: (context.findAncestorStateOfType<_FirdutyAppState>())
              ?._navigatorKey,
        );
        if (mounted) Navigator.pushReplacementNamed(context, '/home');
      } else {
        if (mounted) Navigator.pushReplacementNamed(context, '/pending');
      }
    } catch (e) {
      if (mounted) Navigator.pushReplacementNamed(context, '/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [FirdutyColors.navDark, FirdutyColors.navBlue],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: SafeArea(
          child: Center(
            child: FadeTransition(
              opacity: _fade,
              child: SlideTransition(
                position: _slide,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // Logo
                    Container(
                      width: 100,
                      height: 100,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(28),
                        border: Border.all(
                            color: Colors.white.withValues(alpha: 0.2),
                            width: 1.5),
                      ),
                      padding: const EdgeInsets.all(14),
                      child: Image.asset('assets/logo.png', fit: BoxFit.contain),
                    ),
                    const SizedBox(height: 22),
                    // App name
                    const Text(
                      'Firduty',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 30,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'School Duty Roster',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.7),
                        fontSize: 14,
                        fontWeight: FontWeight.w400,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 52),
                    SizedBox(
                      width: 28,
                      height: 28,
                      child: CircularProgressIndicator(
                        color: Colors.white.withValues(alpha: 0.8),
                        strokeWidth: 2.5,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ── Home screen ───────────────────────────────────────────────────────────────

class HomeScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const HomeScreen({super.key, required this.onLocaleChange});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;
  int? _teacherId;

  static const List<Widget> _screens = [
    TodayScreen(),
    WeekScreen(),
    PointsScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _loadTeacherId();
    NotificationService.syncBellStateFromPrefs();
  }

  Future<void> _loadTeacherId() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) setState(() => _teacherId = prefs.getInt('teacher_id'));
  }

  Future<void> _handleLogout() async {
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text(
          l10n.logout,
          style: const TextStyle(
            fontWeight: FontWeight.w700,
            color: FirdutyColors.textDark,
          ),
        ),
        content: Text(
          isAr
              ? 'هل تريد تسجيل الخروج من التطبيق؟'
              : 'Are you sure you want to sign out?',
          style: const TextStyle(color: FirdutyColors.textMuted),
        ),
        actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        actions: [
          OutlinedButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(isAr ? 'إلغاء' : 'Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: FirdutyColors.danger,
              foregroundColor: Colors.white,
            ),
            child: Text(l10n.logout),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await NotificationService.reset();
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('teacher_id');
      if (mounted) Navigator.pushReplacementNamed(context, '/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    final titles = [l10n.todayDuties, l10n.weekDuties, l10n.myPoints];

    return Scaffold(
      appBar: AppBar(
        title: AnimatedSwitcher(
          duration: const Duration(milliseconds: 220),
          child: Text(
            titles[_selectedIndex],
            key: ValueKey(_selectedIndex),
          ),
        ),
        actions: [
          if (_teacherId != null) NotificationBell(teacherId: _teacherId!),
          TextButton(
            onPressed: () => widget.onLocaleChange(
              isAr ? const Locale('en') : const Locale('ar'),
            ),
            style: TextButton.styleFrom(foregroundColor: Colors.white),
            child: Text(
              isAr ? 'EN' : 'عربي',
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.logout_rounded),
            tooltip: l10n.logout,
            onPressed: _handleLogout,
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
            icon: const Icon(Icons.star_border_rounded),
            selectedIcon: const Icon(Icons.star_rounded),
            label: l10n.myPoints,
          ),
        ],
      ),
    );
  }
}
