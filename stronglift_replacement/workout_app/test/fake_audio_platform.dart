/// Fakes the `audioplayers` platform channels so widget tests exercising
/// [AudioPlayer] (e.g. WorkoutScreen's break-end sound) don't hit a real
/// platform and throw `MissingPluginException`.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers_platform_interface/audioplayers_platform_interface.dart';

import 'fake_path_provider.dart';

/// What the fake actually saw, so a test can assert the cue really played.
///
/// `AudioPlayer.play(AssetSource(...))` lands here as `setSourceUrl` followed
/// by `resume`, so a non-empty [resumedSources] is proof the break-end sound
/// was triggered — not merely that the code path compiled.
class FakeAudioRecorder {
  /// Sources handed to the player, in order.
  final sources = <String>[];

  /// Sources that were actually played.
  final resumedSources = <String>[];

  /// When set, the next `play` fails — for exercising the cue's error path,
  /// which is otherwise only reachable on a device with no audio route.
  var failNextPlay = false;

  /// Forgets everything recorded so far.
  void clear() {
    sources.clear();
    resumedSources.clear();
  }
}

class _FakeAudioplayersPlatform extends AudioplayersPlatformInterface {
  _FakeAudioplayersPlatform(this.recorder);

  final FakeAudioRecorder recorder;
  final _controllers = <String, StreamController<AudioEvent>>{};
  final _lastSource = <String, String>{};

  StreamController<AudioEvent> _controllerFor(String playerId) =>
      _controllers.putIfAbsent(
        playerId,
        () => StreamController<AudioEvent>.broadcast(),
      );

  @override
  Future<void> create(String playerId) async {}

  @override
  Future<void> dispose(String playerId) async {
    await _controllers.remove(playerId)?.close();
  }

  @override
  Future<void> pause(String playerId) async {}

  @override
  Future<void> stop(String playerId) async {}

  @override
  Future<void> resume(String playerId) async {
    if (recorder.failNextPlay) {
      recorder.failNextPlay = false;
      throw Exception('no audio route');
    }
    recorder.resumedSources.add(_lastSource[playerId] ?? '');
    // Complete immediately. A real play starts audioplayers'
    // FramePositionUpdater, which registers a persistent frame callback and
    // keeps ticking after the widget tree is torn down -- the test framework
    // reports that as "An animation is still running even after the widget
    // tree was disposed". The cue is a one-shot sound, so finishing it the
    // instant it starts is both harmless and what the real thing does a
    // second later.
    //
    // Emitted off the current microtask: audioplayers is still inside its own
    // `addStream` when `resume` returns, and adding synchronously there throws
    // "Bad state: Cannot add event while adding stream".
    scheduleMicrotask(
      () => _controllerFor(
        playerId,
      ).add(const AudioEvent(eventType: AudioEventType.complete)),
    );
  }

  @override
  Future<void> release(String playerId) async {}

  @override
  Future<void> seek(String playerId, Duration position) async {}

  @override
  Future<void> setBalance(String playerId, double balance) async {}

  @override
  Future<void> setVolume(String playerId, double volume) async {}

  @override
  Future<void> setReleaseMode(
    String playerId,
    ReleaseMode releaseMode,
  ) async {}

  @override
  Future<void> setPlaybackRate(String playerId, double playbackRate) async {}

  @override
  Future<void> setSourceUrl(
    String playerId,
    String url, {
    bool? isLocal,
    String? mimeType,
  }) async {
    _lastSource[playerId] = url;
    recorder.sources.add(url);
    _controllerFor(
      playerId,
    ).add(const AudioEvent(eventType: AudioEventType.prepared, isPrepared: true));
  }

  @override
  Future<void> setSourceBytes(
    String playerId,
    Uint8List bytes, {
    String? mimeType,
  }) async {
    _controllerFor(
      playerId,
    ).add(const AudioEvent(eventType: AudioEventType.prepared, isPrepared: true));
  }

  @override
  Future<void> setAudioContext(
    String playerId,
    AudioContext audioContext,
  ) async {}

  @override
  Future<void> setPlayerMode(String playerId, PlayerMode playerMode) async {}

  @override
  Future<int?> getDuration(String playerId) async => 0;

  @override
  Future<int?> getCurrentPosition(String playerId) async => 0;

  @override
  Future<void> emitLog(String playerId, String message) async {}

  @override
  Future<void> emitError(String playerId, String code, String message) async {}

  @override
  Stream<AudioEvent> getEventStream(String playerId) =>
      _controllerFor(playerId).stream;
}

class _FakeGlobalAudioplayersPlatform
    implements GlobalAudioplayersPlatformInterface {
  final _controller = StreamController<GlobalAudioEvent>.broadcast();

  @override
  Future<void> init() async {}

  @override
  Future<void> setGlobalAudioContext(AudioContext ctx) async {}

  @override
  Future<void> emitGlobalLog(String message) async {}

  @override
  Future<void> emitGlobalError(String code, String message) async {}

  @override
  Stream<GlobalAudioEvent> getGlobalEventStream() => _controller.stream;
}

/// Installs fake `audioplayers` platform implementations and returns the
/// recorder they write to. Call once from a test's `setUp` before pumping
/// any widget that creates an [AudioPlayer].
FakeAudioRecorder installFakeAudioPlatform() {
  // AssetSource playback goes through the temp directory, so the audio fake
  // is not enough on its own -- see fake_path_provider.dart.
  installFakePathProvider();
  final recorder = FakeAudioRecorder();
  AudioplayersPlatformInterface.instance = _FakeAudioplayersPlatform(recorder);
  GlobalAudioplayersPlatformInterface.instance =
      _FakeGlobalAudioplayersPlatform();
  return recorder;
}
