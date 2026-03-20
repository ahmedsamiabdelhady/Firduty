// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Firduty';

  @override
  String get registerTitle => 'Create Your Account';

  @override
  String get fullName => 'Full Name';

  @override
  String get email => 'Email Address';

  @override
  String get register => 'Register';

  @override
  String get registering => 'Registering...';

  @override
  String get nameRequired => 'Name is required';

  @override
  String get emailRequired => 'Please enter a valid email address';

  @override
  String get emailAlreadyRegistered =>
      'This email is already registered. Please use a different email.';

  @override
  String get loginTitle => 'Sign In to Your Account';

  @override
  String get login => 'Sign In';

  @override
  String get noAccount => 'Don\'t have an account?';

  @override
  String get alreadyHaveAccount => 'Already registered?';

  @override
  String get logout => 'Sign Out';

  @override
  String get pendingTitle => 'Waiting for Approval';

  @override
  String get pendingMessage =>
      'Your account registration has been submitted. An administrator will review and approve your account shortly.';

  @override
  String get checkStatus => 'Check Status';

  @override
  String get useAnotherAccount => 'Use a different account';

  @override
  String get selectTeacher => 'Select Teacher';

  @override
  String get teacher => 'Teacher';

  @override
  String get chooseTeacher => 'Choose your name';

  @override
  String get todayDuties => 'Today';

  @override
  String get weekDuties => 'This Week';

  @override
  String get myPoints => 'My Points';

  @override
  String get settings => 'Settings';

  @override
  String get language => 'Language';

  @override
  String get arabic => 'Arabic';

  @override
  String get english => 'English';

  @override
  String get noDutiesToday => 'No duties assigned for today.';

  @override
  String get noDutiesWeek => 'No duties assigned this week.';

  @override
  String get scheduleBeingPrepared =>
      'Your schedule is being prepared. Please check back later.';

  @override
  String get noPlanForToday => 'No weekly duty plan has been set up for today.';

  @override
  String get location => 'Location';

  @override
  String get gradeClass => 'Class';

  @override
  String get shift => 'Shift';

  @override
  String get date => 'Date';

  @override
  String get time => 'Time';

  @override
  String get loading => 'Loading...';

  @override
  String get error => 'Error loading data. Please try again.';

  @override
  String get save => 'Save';

  @override
  String get confirm => 'OK';

  @override
  String get confirmPresence => 'Confirm Presence';

  @override
  String get confirmed => 'Confirmed ✓';

  @override
  String get notificationsEnabled => 'Notifications enabled';

  @override
  String get sunday => 'Sunday';

  @override
  String get monday => 'Monday';

  @override
  String get tuesday => 'Tuesday';

  @override
  String get wednesday => 'Wednesday';

  @override
  String get thursday => 'Thursday';

  @override
  String get points => 'Points';

  @override
  String get totalPoints => 'Total Points';

  @override
  String pointsHint(String time) {
    return 'On time = 2pts  |  1–5 min late = 1pt  |  After 5 min = 0pt\nDuty starts at $time';
  }

  @override
  String get onTime => 'On Time';

  @override
  String get late => 'Late';

  @override
  String get missed => 'No Points';

  @override
  String get noConfirmationsYet => 'No confirmations yet this month.';

  @override
  String get close => 'Close';

  @override
  String get month => 'Month';
}
