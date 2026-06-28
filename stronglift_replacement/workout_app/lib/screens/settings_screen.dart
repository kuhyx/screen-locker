/// Settings screen: per-exercise streak thresholds and manual weight overrides.
/// Changes are saved immediately; a "Reset to defaults" button reverts all.
library;

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

/// Screen for editing per-exercise thresholds and manual weight overrides.
class SettingsScreen extends StatefulWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _loading = true;

  final Map<String, int> _successThresholds = {};
  final Map<String, int> _failThresholds = {};
  final Map<String, double> _weights = {};

  // Debounce weight saves to avoid resetting streaks on every tap.
  final Map<String, Timer> _weightTimers = {};

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    for (final t in _weightTimers.values) {
      t.cancel();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final states = await StorageService.instance.getAllExerciseStates();
    if (mounted) {
      setState(() {
        for (final s in states) {
          _successThresholds[s.name] = s.successThreshold;
          _failThresholds[s.name] = s.failThreshold;
          _weights[s.name] = s.weight;
        }
        _loading = false;
      });
    }
  }

  void _onWeightChanged(String name, double value) {
    setState(() => _weights[name] = value);
    _weightTimers[name]?.cancel();
    _weightTimers[name] = Timer(const Duration(milliseconds: 600), () {
      unawaited(StorageService.instance.setExerciseWeight(name, value));
    });
  }

  Future<void> _onThresholdChanged(String name, int success, int fail) async {
    setState(() {
      _successThresholds[name] = success;
      _failThresholds[name] = fail;
    });
    await StorageService.instance.setExerciseThresholds(
      name,
      successThreshold: success,
      failThreshold: fail,
    );
  }

  Future<void> _resetToDefaults() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text(
          'Reset to defaults?',
          style: TextStyle(color: Colors.white),
        ),
        content: const Text(
          'All weights and thresholds will be reset. '
          'Streak counters will be cleared.',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text(
              'Cancel',
              style: TextStyle(color: Colors.white70),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text(
              'Reset',
              style: TextStyle(color: Colors.redAccent),
            ),
          ),
        ],
      ),
    );
    if (ok == true) {
      for (final name in _orderedNames) {
        await StorageService.instance.resetExerciseToDefaults(name);
      }
      await _load();
    }
  }

  List<String> get _orderedNames {
    final seen = <String>{};
    return [
      ...workoutA,
      ...workoutB,
    ].map((e) => e.name).where(seen.add).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.grey.shade900,
      appBar: AppBar(
        backgroundColor: Colors.grey.shade800,
        title: const Text('Settings', style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          TextButton(
            onPressed: _loading ? null : _resetToDefaults,
            child: const Text(
              'Reset defaults',
              style: TextStyle(color: Colors.redAccent),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const _SectionHeader('WEIGHTS'),
                const SizedBox(height: 4),
                const Text(
                  'Override current working weight. '
                  'Resets streak counters. Rounded to 2.5 kg.',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const SizedBox(height: 12),
                ..._orderedNames.map((name) {
                  final w = _weights[name];
                  if (w == null) return const SizedBox.shrink();
                  return _WeightRow(
                    name: name,
                    weight: w,
                    onChanged: (v) => _onWeightChanged(name, v),
                  );
                }),
                const SizedBox(height: 20),
                const _SectionHeader('PROGRESSION THRESHOLDS'),
                const SizedBox(height: 4),
                const Text(
                  'Consecutive successes (↑) or failures (↓) '
                  'before weight changes.',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const SizedBox(height: 12),
                ..._orderedNames.map((name) {
                  final sThresh = _successThresholds[name] ?? 3;
                  final fThresh = _failThresholds[name] ?? 2;
                  return _ExerciseThresholdCard(
                    name: name,
                    successThreshold: sThresh,
                    failThreshold: fThresh,
                    onSuccessChanged: (v) =>
                        _onThresholdChanged(name, v, _failThresholds[name]!),
                    onFailChanged: (v) =>
                        _onThresholdChanged(name, _successThresholds[name]!, v),
                  );
                }),
              ],
            ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: Colors.white54,
        fontSize: 11,
        letterSpacing: 1.4,
      ),
    );
  }
}

class _WeightRow extends StatelessWidget {
  const _WeightRow({
    required this.name,
    required this.weight,
    required this.onChanged,
  });

  final String name;
  final double weight;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              name,
              style: const TextStyle(color: Colors.white70, fontSize: 13),
            ),
          ),
          _StepperButton(
            icon: Icons.remove,
            onTap: () => onChanged(
              (weight - kWeightIncrement).clamp(0.0, 999.0),
            ),
          ),
          // Fixed-width container supports up to "999.9kg" (7 chars).
          SizedBox(
            width: 72,
            child: Text(
              '${weight}kg',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.add,
            onTap: () => onChanged(weight + kWeightIncrement),
          ),
        ],
      ),
    );
  }
}

class _StepperButton extends StatelessWidget {
  const _StepperButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: Colors.grey.shade700,
          borderRadius: BorderRadius.circular(6),
        ),
        alignment: Alignment.center,
        child: Icon(icon, color: Colors.white, size: 18),
      ),
    );
  }
}

class _ExerciseThresholdCard extends StatelessWidget {
  const _ExerciseThresholdCard({
    required this.name,
    required this.successThreshold,
    required this.failThreshold,
    required this.onSuccessChanged,
    required this.onFailChanged,
  });

  final String name;
  final int successThreshold;
  final int failThreshold;
  final ValueChanged<int> onSuccessChanged;
  final ValueChanged<int> onFailChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            name,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 10),
          _ThresholdRow(
            label: '↑ Increase after N successes',
            value: successThreshold,
            color: Colors.green,
            onChanged: onSuccessChanged,
          ),
          const SizedBox(height: 6),
          _ThresholdRow(
            label: '↓ Decrease after N failures',
            value: failThreshold,
            color: Colors.red,
            onChanged: onFailChanged,
          ),
        ],
      ),
    );
  }
}

class _ThresholdRow extends StatelessWidget {
  const _ThresholdRow({
    required this.label,
    required this.value,
    required this.color,
    required this.onChanged,
  });

  final String label;
  final int value;
  final Color color;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(color: Colors.white70, fontSize: 12),
          ),
        ),
        const SizedBox(width: 8),
        for (int i = 1; i <= 5; i++)
          Padding(
            padding: const EdgeInsets.only(left: 4),
            child: GestureDetector(
              onTap: () => onChanged(i),
              child: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i == value ? color : Colors.grey.shade700,
                ),
                alignment: Alignment.center,
                child: Text(
                  '$i',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
