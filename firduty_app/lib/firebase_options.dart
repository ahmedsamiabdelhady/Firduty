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
  // Get these from: Firebase Console → Project Settings → Your apps → Web
  static const FirebaseOptions web = FirebaseOptions(
    apiKey:            'YOUR_WEB_API_KEY',            // TODO
    appId:             'YOUR_WEB_APP_ID',             // TODO
    messagingSenderId: 'YOUR_SENDER_ID',              // TODO
    projectId:         'YOUR_PROJECT_ID',             // TODO
    authDomain:        'YOUR_PROJECT_ID.firebaseapp.com', // TODO
    storageBucket:     'YOUR_PROJECT_ID.appspot.com', // TODO
    // VAPID key for Web Push (FCM web):
    // Firebase Console → Project Settings → Cloud Messaging → Web Push certificates
    // → Generate key pair → copy the Key pair value
    measurementId:     'YOUR_MEASUREMENT_ID',        // TODO (optional)
  );

  // ── Android ───────────────────────────────────────────────────────────────
  // These values come from google-services.json.
  // Place that file at flutter_app/android/app/google-services.json.
  static const FirebaseOptions android = FirebaseOptions(
    apiKey:            'YOUR_ANDROID_API_KEY',        // TODO
    appId:             'YOUR_ANDROID_APP_ID',         // TODO
    messagingSenderId: 'YOUR_SENDER_ID',              // TODO
    projectId:         'YOUR_PROJECT_ID',             // TODO
    storageBucket:     'YOUR_PROJECT_ID.appspot.com', // TODO
  );
}

// ── VAPID Public Key ──────────────────────────────────────────────────────────
// Used when requesting FCM web push token.
// Firebase Console → Project Settings → Cloud Messaging →
//   Web Push certificates → Generate key pair → copy Key pair.
//
// Also set this as VAPID_PUBLIC_KEY in the backend .env.
//
// ignore: constant_identifier_names
const String kVapidPublicKey = 'YOUR_VAPID_PUBLIC_KEY'; // TODO