// Shared fixtures for the progression-sync test files.
//
// A sibling library rather than a `part`, so each split test file imports what
// it needs: the in-memory Firebase stand-in, the remote-seeding helper, and
// the HLC reader every group asserts against.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';

/// In-memory stand-in for [FirebaseRestClient].
///
/// Records every write so a test can assert not just the final state but that
/// no write happened at all -- the difference between "the guard held" and
/// "the guard wrote defaults and then wrote them back".
class FakeStore implements FirebaseRestClient {
  final Map<String, String> files = {};
  int writes = 0;
  bool closed = false;
  Object? throwOnGet;

  @override
  Future<String?> getFileText(String path) async {
    if (throwOnGet != null) throw throwOnGet!;
    return files[path];
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    writes++;
    files[path] = text;
  }

  @override
  Future<List<String>> listDirectory(String path) async => files.keys
      .where((k) => k.startsWith('$path/'))
      .map((k) => k.substring(path.length + 1).split('/').first)
      .toSet()
      .toList();

  @override
  void close() => closed = true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void seedRemote(
  FakeStore store,
  String name, {
  double weight = 20,
  int reps = 12,
  double maxWeight = 27.5,
}) {
  final record = Record(
    id: 'exercise_state:$name',
    fields: {
      'payload': (
        {
          'name': name,
          'weight': weight,
          'reps': reps,
          'success_streak': 0,
          'fail_streak': 0,
          'max_weight': maxWeight,
          'success_threshold': 3,
          'fail_threshold': 2,
        },
        Hlc.newTick('remote-device'),
      ),
    },
  );
  store.files[ProgressionSyncService.pathForExercise(name)] = jsonEncode(
    record.toJson(),
  );
}

Hlc hlcAt(FakeStore store, String name) => Record.fromJson(
  jsonDecode(store.files[ProgressionSyncService.pathForExercise(name)]!)
      as Map<String, dynamic>,
).fields['payload']!.$2;

/// A store whose writes always fail, for the push-error paths.
class ExplodingStore extends FakeStore {
  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async => throw FirebaseSyncError('write refused');
}

/// Marks this install as having reconciled with Firebase, which is what
/// unblocks pushing.
Future<void> markSynced() => StorageService.instance.markProgressionSynced();
