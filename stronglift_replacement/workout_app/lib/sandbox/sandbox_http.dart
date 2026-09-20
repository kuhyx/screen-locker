/// Network refusal for the sandbox flavor.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';

/// Makes every `dart:io` HTTP connection fail before a socket is opened.
///
/// Installed as `HttpOverrides.global` by `main` in the sandbox. Firebase and
/// GitHub sync both go through `package:http`, whose IO client is built from
/// `HttpClient()` and therefore from these overrides — one seam, not one
/// guard per service. A refused connection surfaces as a normal sync failure
/// in the UI, which is the honest answer: the sandbox is offline by design.
class SandboxHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..connectionFactory = (uri, proxyHost, proxyPort) {
        debugPrint(
          'WorkoutSandbox: refused network connection to ${uri.host} — the '
          'sandbox never talks to Firebase or GitHub.',
        );
        throw const SocketException(
          'sandbox flavor: network disabled by design',
        );
      };
  }
}
