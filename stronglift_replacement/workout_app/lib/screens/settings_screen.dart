/// Settings screen: per-exercise streak thresholds and manual weight overrides.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  List<ExerciseState>? _states;
  bool _loading = true;
  bool _saving = false;

  final Map<String, int> _successThresholds = {};
  final Map<String, int> _failThresholds = {};
  final Map<String, double> _weights = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final states = await StorageService.instance.getAllExerciseStates();
    if (mounted) {
      setState(() {
        _states = states;
        for (final s in states) {
          _successThresholds[s.name] = s.successThreshold;
          _failThresholds[s.name] = s.failThreshold;
          _weights[s.name] = s.weight;
        }
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final storage = StorageService.instance;
    for (final s in _states!) {
      await storage.setExerciseThresholds(
        s.name,
        successThreshold: _successThresholds[s.name]!,
        failThreshold: _failThresholds[s.name]!,
      );
      final newWeight = _weights[s.name] ?? s.weight;
      if ((newWeight - s.weight).abs() > 0.001) {
        await storage.setExerciseWeight(s.name, newWeight);
      }
    }
    if (mounted) Navigator.of(context).pop();
  }

  List<String> get _orderedNames {
    final seen = <String>{};
    return [...workoutA, ...workoutB]
        .map((e) => e.name)
        .where(seen.add)
        .toList();
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
            onPressed: (_loading || _saving) ? null : _save,
            child: const Text('Save', style: TextStyle(color: Colors.white)),
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
                    onChanged: (v) => setState(() => _weights[name] = v),
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
                        setState(() => _successThresholds[name] = v),
                    onFailChanged: (v) =>
                        setState(() => _failThresholds[name] = v),
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
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Text(
              '${weight}kg',
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
