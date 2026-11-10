import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/storage_service.dart';

import '../run_test_fixtures.dart';
import 'run_uploader_support.dart';

void main() {
  useUploaderStorage();

  group('saveRecordedRun', () {
    test('stores a pending app run and starts the upload', () async {
      var enqueued = 0;
      final track = sampleTrack();
      final result = await saveRecordedRun(
        track,
        storage: db,
        enqueue: () async {
          enqueued++;
          return null;
        },
      );
      expect(result.stored, isTrue);
      expect(enqueued, 1);
      final record = (await db.getRun(track.id))!;
      expect(record.uploadState, RunUploadState.pending);
      expect(record.track.points, hasLength(3));
      expect(record.tcxFilename, endsWith('_Running.tcx'));
    });

    test('a run already stored is reported and not queued twice', () async {
      var enqueued = 0;
      Future<Object?> enqueue() async {
        enqueued++;
        return null;
      }

      final track = sampleTrack();
      await saveRecordedRun(track, storage: db, enqueue: enqueue);
      final again = await saveRecordedRun(track, storage: db, enqueue: enqueue);
      expect(again.stored, isFalse);
      expect(again.reason, contains('already stored'));
      expect(enqueued, 1);
    });
  });
}
