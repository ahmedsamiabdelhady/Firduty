// app_theme.dart — Firduty brand colors and Material 3 theme v2.0
//
// Improvements:
//   • Custom PageTransitionsTheme: smooth fade+slide on Android & iOS
//   • Better splash/ink colors for satisfying tap feedback
//   • ChipTheme for consistent status badges
//   • ListTileTheme for uniform list density
//   • Better card shadow and shape defaults
//   • FloatingActionButton theme

import 'package:flutter/material.dart';

class FirdutyColors {
  FirdutyColors._();

  static const primaryGreen  = Color(0xFF7FB33F);
  static const primaryDark   = Color(0xFF6A9A33);
  static const accentGreen   = Color(0xFF9ED05A);
  static const navBlue       = Color(0xFF2E7DA7);
  static const navDark       = Color(0xFF25678D);
  static const accentBlue    = Color(0xFF4FA1CC);
  static const background    = Color(0xFFF5F7FA);
  static const textDark      = Color(0xFF1F2D3A);
  static const textMuted     = Color(0xFF5A6A7E);
  static const surface       = Color(0xFFFFFFFF);
  static const success       = Color(0xFF9ED05A);
  static const successDark   = Color(0xFF6A9A33);
  static const warning       = Color(0xFFF5A623);
  static const danger        = Color(0xFFE05252);
  static const divider       = Color(0xFFD6DDE8);
}

ThemeData buildFirdutyTheme() {
  const seed = FirdutyColors.navBlue;

  return ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: seed,
      primary:     FirdutyColors.primaryGreen,
      secondary:   FirdutyColors.navBlue,
      tertiary:    FirdutyColors.accentBlue,
      surface:     FirdutyColors.surface,
      error:       FirdutyColors.danger,
      onPrimary:   Colors.white,
      onSecondary: Colors.white,
      onSurface:   FirdutyColors.textDark,
    ),
    scaffoldBackgroundColor: FirdutyColors.background,

    // ── Page transitions: fade on iOS, fade+slide on Android ──────────────
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: FadeForwardPageTransitionsBuilder(),
        TargetPlatform.iOS:     CupertinoPageTransitionsBuilder(),
      },
    ),

    // ── Splash / ink ───────────────────────────────────────────────────────
    splashColor:     FirdutyColors.accentBlue.withValues(alpha: 0.12),
    highlightColor:  FirdutyColors.navBlue.withValues(alpha: 0.07),
    splashFactory:   InkRipple.splashFactory,

    // ── Card ──────────────────────────────────────────────────────────────
    cardTheme: CardThemeData(
      color: FirdutyColors.surface,
      elevation: 0,
      shadowColor: Colors.black.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: FirdutyColors.divider, width: 0.8),
      ),
      margin: const EdgeInsets.symmetric(horizontal: 0, vertical: 0),
    ),

    // ── AppBar ─────────────────────────────────────────────────────────────
    appBarTheme: const AppBarTheme(
      backgroundColor: FirdutyColors.navBlue,
      foregroundColor: Colors.white,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(
        color: Colors.white,
        fontSize: 17,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.2,
      ),
      iconTheme: IconThemeData(color: Colors.white),
    ),

    // ── Navigation bar (bottom) ───────────────────────────────────────────
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: FirdutyColors.surface,
      elevation: 0,
      shadowColor: Colors.black12,
      indicatorColor: FirdutyColors.navBlue.withValues(alpha: 0.12),
      surfaceTintColor: Colors.transparent,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      iconTheme: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const IconThemeData(color: FirdutyColors.navBlue, size: 22);
        }
        return const IconThemeData(color: FirdutyColors.textMuted, size: 22);
      }),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const TextStyle(
            color: FirdutyColors.navBlue,
            fontWeight: FontWeight.w700,
            fontSize: 11.5,
          );
        }
        return const TextStyle(
          color: FirdutyColors.textMuted,
          fontSize: 11.5,
        );
      }),
    ),

    // ── Elevated button ───────────────────────────────────────────────────
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: FirdutyColors.primaryGreen,
        foregroundColor: Colors.white,
        elevation: 0,
        shadowColor: Colors.transparent,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 13),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
      ),
    ),

    // ── Outlined button ───────────────────────────────────────────────────
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: FirdutyColors.navBlue,
        side: const BorderSide(color: FirdutyColors.navBlue),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 11),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),

    // ── Text button ───────────────────────────────────────────────────────
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: FirdutyColors.navBlue,
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),

    // ── Input decoration ──────────────────────────────────────────────────
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: FirdutyColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: FirdutyColors.divider),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: FirdutyColors.divider),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: FirdutyColors.accentBlue, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: FirdutyColors.danger),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: FirdutyColors.danger, width: 2),
      ),
      labelStyle: const TextStyle(color: FirdutyColors.textMuted, fontSize: 14),
      hintStyle: const TextStyle(color: FirdutyColors.textMuted, fontSize: 14),
      prefixIconColor: FirdutyColors.textMuted,
      floatingLabelStyle: const TextStyle(
        color: FirdutyColors.navBlue,
        fontWeight: FontWeight.w600,
        fontSize: 13,
      ),
    ),

    // ── Chip ──────────────────────────────────────────────────────────────
    chipTheme: ChipThemeData(
      backgroundColor: FirdutyColors.background,
      selectedColor: FirdutyColors.navBlue.withValues(alpha: 0.12),
      labelStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      side: const BorderSide(color: FirdutyColors.divider, width: 0.8),
    ),

    // ── List tile ─────────────────────────────────────────────────────────
    listTileTheme: const ListTileThemeData(
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      titleTextStyle: TextStyle(
        color: FirdutyColors.textDark,
        fontSize: 14.5,
        fontWeight: FontWeight.w500,
      ),
      subtitleTextStyle: TextStyle(
        color: FirdutyColors.textMuted,
        fontSize: 12.5,
      ),
      iconColor: FirdutyColors.textMuted,
    ),

    // ── Progress indicator ────────────────────────────────────────────────
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: FirdutyColors.navBlue,
      linearMinHeight: 6,
    ),

    // ── SnackBar ──────────────────────────────────────────────────────────
    snackBarTheme: SnackBarThemeData(
      backgroundColor: FirdutyColors.textDark,
      contentTextStyle: const TextStyle(color: Colors.white, fontSize: 13.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      behavior: SnackBarBehavior.floating,
      insetPadding: const EdgeInsets.all(14),
      elevation: 6,
    ),

    // ── Divider ───────────────────────────────────────────────────────────
    dividerTheme: const DividerThemeData(
      color: FirdutyColors.divider,
      thickness: 0.8,
      space: 1,
    ),

    // ── Floating action button ────────────────────────────────────────────
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: FirdutyColors.navBlue,
      foregroundColor: Colors.white,
      elevation: 4,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(16)),
      ),
    ),

    // ── Text ──────────────────────────────────────────────────────────────
    textTheme: const TextTheme(
      headlineLarge: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w800,
        fontSize: 28,
        letterSpacing: -0.5,
      ),
      headlineMedium: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w700,
        fontSize: 24,
        letterSpacing: -0.3,
      ),
      titleLarge: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w700,
        fontSize: 18,
      ),
      titleMedium: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w600,
        fontSize: 15,
      ),
      titleSmall: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w600,
        fontSize: 13,
      ),
      bodyLarge: TextStyle(
        color: FirdutyColors.textDark,
        fontSize: 15,
        height: 1.5,
      ),
      bodyMedium: TextStyle(
        color: FirdutyColors.textDark,
        fontSize: 13.5,
        height: 1.45,
      ),
      bodySmall: TextStyle(
        color: FirdutyColors.textMuted,
        fontSize: 12,
        height: 1.4,
      ),
      labelLarge: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w600,
        fontSize: 13.5,
      ),
      labelSmall: TextStyle(
        color: FirdutyColors.textMuted,
        fontSize: 11,
        letterSpacing: 0.3,
      ),
    ),
  );
}

// ── Smooth fade + slide page transition ───────────────────────────────────────

class FadeForwardPageTransitionsBuilder extends PageTransitionsBuilder {
  const FadeForwardPageTransitionsBuilder();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    final fadeTween = CurveTween(curve: Curves.easeOut);
    final slideTween = Tween<Offset>(
      begin: const Offset(0.03, 0),
      end: Offset.zero,
    ).chain(CurveTween(curve: Curves.easeOutCubic));

    return FadeTransition(
      opacity: animation.drive(fadeTween),
      child: SlideTransition(
        position: animation.drive(slideTween),
        child: child,
      ),
    );
  }
}
