// The kilometre cue of a run: a buzz, and the chime unless sound is off.
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/feedback_cues.dart';

import '../fake_audio_platform.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late FakeAudioRecorder audio;

  setUp(() => audio = installFakeAudioPlatform());

  test('chimes with the finish sound', () async {
    await FeedbackCues(AudioPlayer()).kilometreReached(1);
    expect(audio.resumedSources.single, contains('workout_done'));
  });

  test('stays silent when sound is off', () async {
    await (FeedbackCues(AudioPlayer())..soundOn = false).kilometreReached(2);
    expect(audio.resumedSources, isEmpty);
  });

  test('a chime that cannot play is logged, not thrown', () async {
    audio.failNextPlay = true;
    await FeedbackCues(AudioPlayer()).kilometreReached(3);
    expect(audio.resumedSources, isEmpty);
  });
}
