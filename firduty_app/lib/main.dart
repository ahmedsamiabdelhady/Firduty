import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
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
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

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


  FirebaseMessaging.onBackgroundMessage(
    firebaseMessagingBackgroundHandler,
  );

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
  const StartupScreen({super.key, required this.onLocaleChange});

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
      Navigator.pushReplacementNamed(context, '/login');
      return;
    }

    try {
      final result = await ApiService.getTeacherStatus(teacherId);
      final status = result['status'];

      if (status == 'approved') {
        final platform = kIsWeb ? 'web' : 'android';

        /// 🔥 أهم نقطة
        await NotificationService.initialize(
          teacherId: teacherId,
          platform: platform,
        );

        Navigator.pushReplacementNamed(context, '/home');
      } else {
        Navigator.pushReplacementNamed(context, '/pending');
      }
    } catch (e) {
      Navigator.pushReplacementNamed(context, '/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: CircularProgressIndicator()),
    );
  }
}

class HomeScreen extends StatefulWidget {
  final void Function(Locale) onLocaleChange;
  const HomeScreen({super.key, required this.onLocaleChange});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;
  int? _teacherId;

  final List<Widget> _screens = const [
    TodayScreen(),
    WeekScreen(),
    PointsScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _loadTeacherId();

    /// 🔥 sync bell
    NotificationService.syncBellStateFromPrefs();
  }

  Future<void> _loadTeacherId() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() => _teacherId = prefs.getInt('teacher_id'));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final isAr = Localizations.localeOf(context).languageCode == 'ar';

    return Scaffold(
      appBar: AppBar(
        title: Text([
          l10n.todayDuties,
          l10n.weekDuties,
          l10n.myPoints
        ][_selectedIndex]),
        actions: [
          if (_teacherId != null)
            NotificationBell(teacherId: _teacherId!),

          TextButton(
            onPressed: () {
              widget.onLocaleChange(
                isAr ? const Locale('en') : const Locale('ar'),
              );
            },
            child: Text(isAr ? 'EN' : 'عربي'),
          ),

          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await NotificationService.reset();
              final prefs = await SharedPreferences.getInstance();
              await prefs.remove('teacher_id');
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
            icon: const Icon(Icons.today),
            label: l10n.todayDuties,
          ),
          NavigationDestination(
            icon: const Icon(Icons.calendar_month),
            label: l10n.weekDuties,
          ),
          NavigationDestination(
            icon: const Icon(Icons.star),
            label: l10n.myPoints,
          ),
        ],
      ),
    );
  }
}