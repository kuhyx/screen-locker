/// Fakes the `audioplayers` platform channels so widget tests exercising
/// [AudioPlayer] (e.g. WorkoutScreen's break-end sound) don't hit a real
/// platform and throw `MissingPluginException`.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers_platform_interface/audioplayers_platform_interface.dart';

class _FakeAudioplayersPlatform extends AudioplayersPlatformInterface {
  final _controllers = <String, StreamController<AudioEvent>>{};

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
  Future<void> resume(String playerId) async {}

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

/// Installs fake `audioplayers` platform implementations. Call once from a
/// test's `setUp` before pumping any widget that creates an [AudioPlayer].
void installFakeAudioPlatform() {
  AudioplayersPlatformInterface.instance = _FakeAudioplayersPlatform();
  GlobalAudioplayersPlatformInterface.instance =
      _FakeGlobalAudioplayersPlatform();
}
