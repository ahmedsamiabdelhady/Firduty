// GENERATED CODE - DO NOT MODIFY BY HAND
// After editing .arb files, regenerate with:  flutter gen-l10n

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  static const List<Locale> supportedLocales = <Locale>[
    Locale('ar'),
    Locale('en'),
  ];

  String get appTitle;
  String get registerTitle;
  String get fullName;
  String get email;
  String get register;
  String get registering;
  String get nameRequired;
  String get emailRequired;
  String get emailAlreadyRegistered;
  String get pendingTitle;
  String get pendingMessage;
  String get checkStatus;
  String get useAnotherAccount;
  String get selectTeacher;
  String get teacher;
  String get chooseTeacher;
  String get todayDuties;
  String get weekDuties;
  String get myPoints;
  String get settings;
  String get language;
  String get arabic;
  String get english;

  /// "No duties assigned for today."
  String get noDutiesToday;

  /// "No duties assigned this week."
  String get noDutiesWeek;

  /// "Your schedule is being prepared. Please check back later."
  /// Shown when the week exists but is still a draft.
  String get scheduleBeingPrepared;

  /// "No weekly duty plan has been set up for today."
  /// Shown when there is no week plan at all covering today.
  String get noPlanForToday;

  String get location;
  String get gradeClass;
  String get shift;
  String get date;
  String get time;
  String get loading;
  String get error;
  String get save;
  String get confirm;
  String get confirmPresence;
  String get confirmed;
  String get notificationsEnabled;
  String get sunday;
  String get monday;
  String get tuesday;
  String get wednesday;
  String get thursday;
  String get points;
  String get totalPoints;

  /// "On time = 2pts  |  1–5 min late = 1pt  |  After 5 min = 0pt\nDuty starts at {time}"
  String pointsHint(String time);

  String get onTime;
  String get late;
  String get missed;
  String get noConfirmationsYet;
  String get close;
  String get month;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['ar', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  switch (locale.languageCode) {
    case 'ar':
      return AppLocalizationsAr();
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale".');
}
