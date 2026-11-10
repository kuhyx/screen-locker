@TestOn('vm')
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/storage_service.dart';

import 'storage_service_runs_fixtures.dart';

void main() {
  useRunsTransferSandbox();

  group('user export / merge-import', () {
    test(
      'round trip keeps every run and point; a re-import adds nothing',
      () async {
        await insertAll();
        final originals = {
          for (final r in await svc.listRuns())
            r.track.id: (await svc.getRun(r.track.id))!,
        };
        final data =
            jsonDecode(jsonEncode(await svc.exportData()))
                as Map<String, dynamic>;
        expect(data['version'], kExportVersion);
        expect(data['runs'], hasLength(3));

        await freshInstall();
        final report = await svc.importDataReport(data);

        expect(report.rows, greaterThanOrEqualTo(3));
        for (final run in originals.values) {
          final back = (await svc.getRun(run.track.id))!;
          expect(back.track.points, run.track.points);
          expect(back.track.source, run.track.source);
          expect(back.uploadState, run.uploadState);
        }
        final again = await svc.importDataReport(data);
        expect(again.rows, 0);
        expect(await svc.listRuns(), hasLength(3));
      },
    );

    test('an old export without runs still imports', () async {
      final report = await svc.importDataReport({
        'format': kExportFormat,
        'version': 2,
        'settings': <Object?>[],
      });
      expect(report.rows, 0);
      expect(await svc.listRuns(), isEmpty);
    });

    test(
      'a runs entry that is not a list is skipped, the rest merges',
      () async {
        final report = await svc.importDataReport({
          'settings': <Object?>[],
          'runs': 5,
        });
        expect(report.rows, 0);
      },
    );

    test('an export holding only runs is accepted; junk is not', () async {
      await insertAll();
      final runs = (await svc.exportData())['runs']! as List<dynamic>;
      await freshInstall();
      expect((await svc.importDataReport({'runs': runs})).rows, 3);
      await expectLater(
        svc.importDataReport({'runs': 'nope'}),
        throwsFormatException,
      );
    });

    test(
      'bad entries are skipped, good ones kept, imports stay never',
      () async {
        await insertAll();
        final good = ((await svc.exportData())['runs']! as List<dynamic>)
            .cast<Map<String, Object?>>();
        await freshInstall();
        final forged = {
          ...good.first,
          'source': 'runnerup_import',
          'upload_state': 'pending',
        };
        final clash = {...good[1], 'id': 'other-id'}; // same hash, new id
        final badPoints = {...good[2], 'points': 'not json'};
        final badSport = {...good[2], 'id': 'z', 'sport': 'Cycling'};
        final noId = {...good[2], 'id': ''};

        final report = await svc.importDataReport({
          'runs': [forged, good[1], clash, badPoints, badSport, noId, 'str', 7],
        });

        expect(report.rows, 2);
        final stored = await svc.listRuns();
        expect(stored, hasLength(2));
        final coerced = stored.firstWhere((r) => r.track.id == forged['id']);
        expect(coerced.track.source, RunSource.runnerupImport);
        expect(coerced.uploadState, RunUploadState.never);
      },
    );
  });
}
