/// Keeps the app on the live run: when it comes back to the front with a run
/// owed and nothing above home, the run screen opens again.
library;

import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:workout_app/screens/run_screen.dart';

/// Wraps the home route of the app.
class RunLanding extends StatefulWidget {
  /// Creates the wrapper; a null [owed] (no run can exist here) never lands.
  const RunLanding({required this.child, this.owed, super.key});

  /// Whether a run is owed right now.
  final Future<bool> Function()? owed;

  /// The home screen.
  final Widget child;

  @override
  State<RunLanding> createState() => _RunLandingState();
}

class _RunLandingState extends State<RunLanding> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_land());
  }

  Future<void> _land() async {
    final owed = widget.owed;
    // Anything above home (the run itself, a workout) already has the screen.
    if (owed == null || !(ModalRoute.of(context)?.isCurrent ?? false)) return;
    if (!await owed() || !mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const RunScreen(resuming: true)),
    );
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
