/// Countdown banner displayed at the top of the workout screen during a rest.
library;

import 'package:flutter/material.dart';

class BreakBanner extends StatelessWidget {
  const BreakBanner({
    super.key,
    required this.breakRemaining,
    required this.breakLabel,
    required this.onSkip,
  });

  final int breakRemaining;
  final String breakLabel;
  final VoidCallback onSkip;

  String _fmt(int secs) {
    final m = (secs ~/ 60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.indigo.shade900,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  breakLabel,
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
                Text(
                  _fmt(breakRemaining),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 26,
                    fontWeight: FontWeight.bold,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: onSkip,
            child: const Text(
              'Skip',
              style: TextStyle(color: Colors.white70),
            ),
          ),
        ],
      ),
    );
  }
}
