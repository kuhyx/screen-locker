// Shared harness for the BreakTaskHandler tests: an in-memory intent store
// and a snapshot builder with every field defaulted.
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_intent_store.dart';

/// A [BreakIntentStore] backed by two maps.
class MemIntentStore implements BreakIntentStore {
  final ints = <String, int>{};
  final lists = <String, List<String>>{};

  @override
  Future<int> readInt(String key) async => ints[key] ?? 0;

  @override
  Future<void> writeInt(String key, int value) async => ints[key] = value;

  @override
  Future<List<String>> readStringList(String key) async =>
      lists[key] ?? const [];

  @override
  Future<void> writeStringList(String key, List<String> value) async =>
      lists[key] = List.of(value);
}

/// A snapshot map as the UI sends it, with every field defaulted.
Map<String, Object?> snapMap({
  int breakEndMs = 0,
  int breakDurationSecs = 180,
  int breakFailSecs = 300,
  int nextExIdx = 0,
  int nextSetIdx = 1,
  int lastExIdx = 0,
  int lastSetIdx = 0,
  int breakForExIdx = 0,
  int breakForSetIdx = 0,
  int setsRemaining = 4,
}) => BreakSnapshot(
  workoutType: 'A',
  breakEndMs: breakEndMs,
  breakDurationSecs: breakDurationSecs,
  breakFailSecs: breakFailSecs,
  breakLabel: 'Rest (3 min — well done!)',
  breakForExIdx: breakForExIdx,
  breakForSetIdx: breakForSetIdx,
  nextExIdx: nextExIdx,
  nextSetIdx: nextSetIdx,
  nextExName: 'Squat',
  nextSetNumber: nextSetIdx + 1,
  nextTotalSets: 5,
  nextReps: 5,
  nextWeight: 40,
  lastExIdx: lastExIdx,
  lastSetIdx: lastSetIdx,
  setsRemaining: setsRemaining,
).toMap();
