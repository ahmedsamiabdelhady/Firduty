import 'dart:html' as html;

Future<bool> webIsAuthorized({required bool promptForPermission}) async {
  final currentPermission = html.Notification.permission;

  if (currentPermission == 'granted') {
    return true;
  }

  if (!promptForPermission) {
    return false;
  }

  final requested = await html.Notification.requestPermission();
  return requested == 'granted';
}

Future<void> registerWebServiceWorker() async {
  await html.window.navigator.serviceWorker
      ?.register('/firebase-messaging-sw.js');
}