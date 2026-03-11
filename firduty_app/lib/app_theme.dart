// app_theme.dart — Firduty brand colors and Material 3 theme
//
// Brand palette (from official Firduty logo):
//   Primary Green  : #7FB33F  → buttons, primary actions, FAB
//   Secondary Blue : #2E7DA7  → AppBar, navigation, headers
//   Accent Green   : #9ED05A  → success states, confirmed badges
//   Accent Blue    : #4FA1CC  → hover / focus highlights
//   Background     : #F5F7FA  → scaffold background
//   Text Dark      : #1F2D3A  → body text, headings

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
}

ThemeData buildFirdutyTheme() {
  const seed = FirdutyColors.navBlue;

  return ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: seed,
      primary:    FirdutyColors.primaryGreen,
      secondary:  FirdutyColors.navBlue,
      tertiary:   FirdutyColors.accentBlue,
      surface:    FirdutyColors.surface,
      error:      FirdutyColors.danger,
      onPrimary:  Colors.white,
      onSecondary: Colors.white,
      onSurface:  FirdutyColors.textDark,
    ),
    scaffoldBackgroundColor: FirdutyColors.background,
    cardTheme: CardThemeData(
      color: FirdutyColors.surface,
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: FirdutyColors.navBlue,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(
        color: Colors.white,
        fontSize: 18,
        fontWeight: FontWeight.w600,
      ),
      iconTheme: IconThemeData(color: Colors.white),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: FirdutyColors.surface,
      indicatorColor: FirdutyColors.navBlue.withValues(alpha: 0.15),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const IconThemeData(color: FirdutyColors.navBlue);
        }
        return const IconThemeData(color: FirdutyColors.textMuted);
      }),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const TextStyle(
            color: FirdutyColors.navBlue,
            fontWeight: FontWeight.w600,
            fontSize: 12,
          );
        }
        return const TextStyle(
          color: FirdutyColors.textMuted,
          fontSize: 12,
        );
      }),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: FirdutyColors.primaryGreen,
        foregroundColor: Colors.white,
        elevation: 1,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: FirdutyColors.navBlue,
        side: const BorderSide(color: FirdutyColors.navBlue),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: FirdutyColors.navBlue,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: FirdutyColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: Color(0xFFD6DDE8)),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: Color(0xFFD6DDE8)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: FirdutyColors.accentBlue, width: 2),
      ),
      labelStyle: const TextStyle(color: FirdutyColors.textMuted),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: FirdutyColors.navBlue,
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: FirdutyColors.textDark,
      contentTextStyle: const TextStyle(color: Colors.white),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      behavior: SnackBarBehavior.floating,
    ),
    dividerTheme: const DividerThemeData(
      color: Color(0xFFD6DDE8),
      thickness: 1,
    ),
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w700,
      ),
      titleLarge: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w600,
      ),
      titleMedium: TextStyle(
        color: FirdutyColors.textDark,
        fontWeight: FontWeight.w500,
      ),
      bodyLarge: TextStyle(color: FirdutyColors.textDark),
      bodyMedium: TextStyle(color: FirdutyColors.textDark),
      bodySmall: TextStyle(color: FirdutyColors.textMuted),
    ),
  );
}