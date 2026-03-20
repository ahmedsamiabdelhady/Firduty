// firebase_options.dart — Firebase configuration for all platforms.
//
// ── SETUP REQUIRED ──────────────────────────────────────────────────────────
// This file is a TEMPLATE. You must fill in the actual values from your
// Firebase project before the app will connect to Firebase.
//
// RECOMMENDED: Run `flutterfire configure` in flutter_app/ — it will
// auto-populate this file for Android, iOS, and Web from your project.
//
// Manual steps:
//   1. Android: values come from google-services.json
//   2. Web:     Firebase Console → Project Settings → Web App → Config object
//
// Replace every "YOUR_*" placeholder below with actual values.
// The app will compile with placeholders but Firebase will fail at runtime.
// ─────────────────────────────────────────────────────────────────────────────

import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) return web;
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      default:
        // iOS native not used — PWA is the iOS delivery method.
        // If you add native iOS later, add a case for TargetPlatform.iOS.
        throw UnsupportedError(
          'DefaultFirebaseOptions: unsupported platform '
          '"$defaultTargetPlatform". Use the web build for iOS (PWA).',
        );
    }
  }

  // ── Web / iOS PWA ─────────────────────────────────────────────────────────

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyD0lAw3ym33tl8PVh7xjZBDJ64QhKbwv1k',
    appId: '1:442695383131:web:1ac5166bec55253b48677e',
    messagingSenderId: '442695383131',
    projectId: 'firduty-dede5',
    authDomain: 'firduty-dede5.firebaseapp.com',
    storageBucket: 'firduty-dede5.firebasestorage.app',
    measurementId: 'G-CF2WM5SL5D',
  );

  // Get these from: Firebase Console → Project Settings → Your apps → Web

  // ── Android ───────────────────────────────────────────────────────────────
  // These values come from google-services.json.

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyAN-zKgXX3rBEuO-ujq2KA5FoUS7eljOfE',
    appId: '1:442695383131:android:286520ab33cf231548677e',
    messagingSenderId: '442695383131',
    projectId: 'firduty-dede5',
    storageBucket: 'firduty-dede5.firebasestorage.app',
  );

  // Place that file at flutter_app/android/app/google-services.json.
}

// ── VAPID Public Key ──────────────────────────────────────────────────────────
// Used when requesting FCM web push token.
// Firebase Console → Project Settings → Cloud Messaging →
//   Web Push certificates → Generate key pair → copy Key pair.
//
// Also set this as VAPID_PUBLIC_KEY in the backend .env.
//
// ignore: constant_identifier_names
const String kVapidPublicKey = 'BD-hd89_Ah_4XM135fFtuK3UbVNDFPqB0SyhJqnuxtloz9Cw5MRktvdyQZXWm_mcHiz5NjoP6i0K7Qn9CHfxJao'; // TODO