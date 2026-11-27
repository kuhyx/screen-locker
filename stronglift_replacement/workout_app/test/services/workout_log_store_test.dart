/// Where the local workout log lives, and that the app shares one instance.
@TestOn('vm')
library;

import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:workout_app/services/workout_log_store.dart';

import '../fake_path_provider.dart';

Record _record(String id) => Record(
  id: id,
  fields: {
    'payload': (
      {'date': '2026-07-05'},
      Hlc(wallTimeMs: 1, counter: 0, nodeId: 'phone'),
    ),
  },
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('lives in the app support directory, beside sync_state.json', () async {
    final support = installFakePathProvider();
    addTearDown(() => support.deleteSync(recursive: true));
    workoutLogDirOverride = null;

    await (await openWorkoutLogStore()).upsert(_record('a'));

    expect(
      File(p.join(support.path, kWorkoutLogFileName)).existsSync(),
      isTrue,
    );
  });

  test('one store per directory, reopened when the directory changes', () {
    final first = workoutLogDirOverride!;
    final other = Directory.systemTemp.createTempSync('wo_log_');
    addTearDown(() => other.deleteSync(recursive: true));

    return Future.wait([openWorkoutLogStore(), openWorkoutLogStore()]).then((
      same,
    ) async {
      expect(identical(same[0], same[1]), isTrue);
      workoutLogDirOverride = other.path;
      expect(identical(await openWorkoutLogStore(), same[0]), isFalse);
      workoutLogDirOverride = first;
    });
  });
}
