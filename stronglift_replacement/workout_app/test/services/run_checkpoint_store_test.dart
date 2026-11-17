@TestOn('vm')
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_checkpoint_store.dart';
import 'package:workout_app/services/run_phase.dart';

RunCheckpoint _checkpoint({int moving = 6}) => RunCheckpoint(
  startedAt: DateTime.utc(2026, 11, 9, 12),
  savedAt: DateTime.utc(2026, 11, 9, 12, 5),
  phase: RunPhase.recording,
  points: [
    RunPoint(
      time: DateTime.utc(2026, 11, 9, 12),
      latitude: 48.8584,
      longitude: 2.2945,
      distanceM: 0,
    ),
  ],
  movingSeconds: moving,
  distanceM: 0,
  km: 0,
  segmentBreak: false,
  jumps: 0,
);

void main() {
  late Directory dir;
  late File file;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('run_checkpoint_store_');
    file = File('${dir.path}/sub/run_checkpoint.json');
  });

  tearDown(() => dir.deleteSync(recursive: true));

  group('FileRunCheckpointStore', () {
    test('load with no file is null', () async {
      expect(await FileRunCheckpointStore(file).load(), isNull);
    });

    test('save then load returns the same checkpoint', () async {
      final store = FileRunCheckpointStore(file);
      await store.save(_checkpoint());
      final back = (await store.load())!;
      expect(back.movingSeconds, 6);
      expect(back.startedAt, DateTime.utc(2026, 11, 9, 12));
      expect(back.points, hasLength(1));
    });

    test('a save leaves no temp file behind', () async {
      await FileRunCheckpointStore(file).save(_checkpoint());
      final names = file.parent.listSync().map((e) => e.path).toList();
      expect(names, [file.path]);
    });

    test('a second save replaces the first', () async {
      final store = FileRunCheckpointStore(file);
      await store.save(_checkpoint());
      await store.save(_checkpoint(moving: 99));
      expect((await store.load())!.movingSeconds, 99);
    });

    test('overlapping saves keep the newest and all complete', () async {
      final store = FileRunCheckpointStore(file);
      final saves = [
        for (var i = 1; i <= 20; i++) store.save(_checkpoint(moving: i)),
      ];
      await Future.wait(saves);
      expect((await store.load())!.movingSeconds, 20);
      expect(file.parent.listSync(), hasLength(1));
    });

    test('clear removes the file and is safe when there is none', () async {
      final store = FileRunCheckpointStore(file);
      await store.clear();
      await store.save(_checkpoint());
      await store.clear();
      expect(file.existsSync(), isFalse);
      expect(await store.load(), isNull);
    });

    test(
      'a corrupt file is moved aside, logged loudly, load is null',
      () async {
        file.parent.createSync(recursive: true);
        file.writeAsStringSync('{"v":1, truncated');
        final logs = <String>[];
        final store = FileRunCheckpointStore(
          file,
          clock: () => DateTime.utc(2026, 11, 9, 13),
          onLoud: logs.add,
        );
        expect(await store.load(), isNull);
        expect(file.existsSync(), isFalse);
        final aside = file.parent
            .listSync()
            .map((e) => e.path)
            .where((p) => p.contains('.corrupt-'))
            .toList();
        expect(aside, hasLength(1));
        expect(File(aside.single).readAsStringSync(), contains('truncated'));
        expect(logs.single, contains('corrupt'));
        expect(aside.single, contains('.corrupt-'));
      },
    );

    test('valid JSON of the wrong shape is corrupt too', () async {
      file.parent.createSync(recursive: true);
      file.writeAsStringSync('[1, 2, 3]');
      expect(await FileRunCheckpointStore(file).load(), isNull);
      expect(file.existsSync(), isFalse);
    });

    test('JSON that fails the codec is corrupt too', () async {
      file.parent.createSync(recursive: true);
      file.writeAsStringSync('{"v": 1}');
      expect(await FileRunCheckpointStore(file).load(), isNull);
      expect(file.existsSync(), isFalse);
    });

    test('bytes that are not UTF-8 are corrupt too', () async {
      file.parent.createSync(recursive: true);
      file.writeAsBytesSync([0xff, 0xfe, 0x00, 0x80]);
      expect(await FileRunCheckpointStore(file).load(), isNull);
      expect(file.existsSync(), isFalse);
    });

    test(
      'an unreadable file surfaces the error instead of hiding it',
      () async {
        file.parent.createSync(recursive: true);
        file.writeAsStringSync('{}');
        Process.runSync('chmod', ['000', file.path]);
        addTearDown(() => Process.runSync('chmod', ['644', file.path]));
        await expectLater(
          FileRunCheckpointStore(file).load(),
          throwsA(isA<FileSystemException>()),
        );
      },
    );
  });

  group('MemoryRunCheckpointStore', () {
    test('keeps the last save until cleared', () async {
      final store = MemoryRunCheckpointStore();
      expect(await store.load(), isNull);
      await store.save(_checkpoint());
      expect((await store.load())!.movingSeconds, 6);
      await store.clear();
      expect(await store.load(), isNull);
    });
  });
}
