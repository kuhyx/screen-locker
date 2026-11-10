/// Uploads recorded runs to the PC's dufs inbox.
///
/// The PC credits a run from the TCX it finds in `/RunnerUp`; the credit is
/// anchored on the run's own time, so a late upload still counts in full. The
/// queue is the `runs` table itself (upload_state `pending`), so nothing here
/// can lose a run: a failure just leaves the row pending for the next try.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/run_upload_credentials.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

/// Server folder the PC watches.
const String kRunInboxFolder = 'RunnerUp';

/// How long one PUT may take.
const Duration kUploadTimeout = Duration(seconds: 30);

/// How long after a failure the queue tries again while the app is open.
const Duration kUploadRetryAfter = Duration(minutes: 1);

/// Where the queue stands (shown as an icon).
enum UploadHealth {
  /// Nothing waiting, or everything went through.
  idle,

  /// A pass is running.
  uploading,

  /// The last pass failed; a retry is scheduled.
  retrying,

  /// Runs are waiting but no login was provisioned.
  notConfigured,

  /// The sandbox flavor: runs are kept, nothing is ever sent.
  sandbox,
}

/// A snapshot of the queue.
@immutable
class RunUploadStatus {
  /// Creates a status.
  const RunUploadStatus(this.health, this.pending, [this.reason = '']);

  /// What the queue is doing.
  final UploadHealth health;

  /// Runs still waiting.
  final int pending;

  /// A sentence for the log.
  final String reason;
}

/// The pending-run upload queue.
class RunUploader {
  /// Creates a queue; the arguments are test seams.
  RunUploader({
    RunCredentialStore? credentials,
    this._client,
    this._storage,
    Timer Function(Duration, void Function())? scheduler,
  }) : _credentials = credentials ?? RunCredentialStore(),
       _schedule = scheduler ?? Timer.new;

  /// The app-wide queue.
  static final RunUploader instance = RunUploader();

  final RunCredentialStore _credentials;
  final http.Client? _client;
  final StorageService? _storage;
  final Timer Function(Duration, void Function()) _schedule;

  final _status = ValueNotifier<RunUploadStatus>(
    const RunUploadStatus(UploadHealth.idle, 0),
  );
  Future<RunUploadStatus>? _inFlight;
  Timer? _retry;

  /// The queue's state, for the badge.
  ValueListenable<RunUploadStatus> get status => _status;

  StorageService get _db => _storage ?? StorageService.instance;

  /// Uploads every pending run, oldest first. One pass at a time: a call
  /// while one runs joins it instead of racing it.
  Future<RunUploadStatus> uploadPending() =>
      _inFlight ??= _guarded().whenComplete(() => _inFlight = null);

  /// A pass that cannot throw: callers fire it and forget it, and an error
  /// nobody awaits would vanish. It is logged loudly and retried instead.
  Future<RunUploadStatus> _guarded() async {
    try {
      return await _pass();
    } on Exception catch (error, stack) {
      log(
        'RunUploader: the upload pass threw',
        level: 1000,
        error: error,
        stackTrace: stack,
      );
      return _fail(
        UploadHealth.retrying,
        _status.value.pending,
        'the upload pass crashed ($error); runs stay pending and are retried.',
      );
    }
  }

  Future<RunUploadStatus> _pass() async {
    _retry?.cancel();
    final pending = (await _db.listRuns(
      uploadState: RunUploadState.pending,
    )).reversed.toList();
    if (pending.isEmpty) return _set(UploadHealth.idle, 0);
    if (Sandbox.enabled) {
      SandboxLog.event('upload skipped', {'pending': pending.length});
      return _set(UploadHealth.sandbox, pending.length, 'sandbox: no uploads');
    }
    final login = await _credentials.read();
    if (login == null) {
      return _fail(
        UploadHealth.notConfigured,
        pending.length,
        '${pending.length} run(s) wait for upload but no login is '
        'provisioned. Run scripts/provision_run_upload.sh.',
        retry: false,
      );
    }
    _set(UploadHealth.uploading, pending.length);
    var left = pending.length;
    final client = _client ?? http.Client();
    try {
      for (final record in pending) {
        final problem = await _upload(client, login, record);
        if (problem != null) {
          return _fail(UploadHealth.retrying, left, problem);
        }
        left--;
      }
    } finally {
      if (_client == null) client.close();
    }
    return _set(UploadHealth.idle, 0);
  }

  /// A sentence naming the failure, or null once the run is uploaded.
  Future<String?> _upload(
    http.Client client,
    RunUploadCredentials login,
    RunRecord record,
  ) async {
    final full = await _db.getRun(record.track.id);
    if (full == null) return null;
    final tcx = encodeTcx(full.track);
    if (tcxSha256(tcx) != record.tcxSha256) {
      log(
        'RunUploader: ${record.tcxFilename} re-encodes to different bytes '
        'than were stored (the encoder changed since recording). Uploading '
        'the current encoding; the PC dedupes on the run id.',
        level: 900,
      );
    }
    final url = Uri.parse(
      '${login.baseUrl}/$kRunInboxFolder/${record.tcxFilename}',
    );
    final http.Response response;
    try {
      response = await client
          .put(
            url,
            headers: {
              'Authorization': login.basicAuth,
              'Content-Type': 'application/vnd.garmin.tcx+xml',
            },
            body: tcx,
          )
          .timeout(kUploadTimeout);
    } on Exception catch (error, stack) {
      log(
        'RunUploader: PUT ${record.tcxFilename} threw',
        level: 1000,
        error: error,
        stackTrace: stack,
      );
      return 'PUT ${record.tcxFilename} failed ($error); the run stays '
          'pending and is retried.';
    }
    if (response.statusCode < 200 || response.statusCode > 299) {
      return 'PUT ${record.tcxFilename} was answered ${response.statusCode}'
          '${response.statusCode == 401 ? ' (login rejected: re-run '
                    'scripts/provision_run_upload.sh)' : ''}; the run stays '
          'pending and is retried.';
    }
    if (!await _db.setRunUploadState(
      record.track.id,
      RunUploadState.uploaded,
    )) {
      log(
        'RunUploader: ${record.tcxFilename} was uploaded but its row is '
        'gone, so it could not be marked uploaded.',
        level: 900,
      );
    }
    return null;
  }

  RunUploadStatus _set(UploadHealth health, int pending, [String why = '']) {
    final status = RunUploadStatus(health, pending, why);
    _status.value = status;
    return status;
  }

  RunUploadStatus _fail(
    UploadHealth health,
    int pending,
    String reason, {
    bool retry = true,
  }) {
    log('RunUploader: $reason', level: 1000);
    if (retry) {
      _retry = _schedule(kUploadRetryAfter, () => unawaited(uploadPending()));
    }
    return _set(health, pending, reason);
  }

  /// Stops the retry timer.
  void dispose() {
    _retry?.cancel();
    _status.dispose();
  }
}
