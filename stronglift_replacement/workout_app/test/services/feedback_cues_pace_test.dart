// The pace cues: two distinct buzz patterns and tones, silent sound switch.
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/pace_band.dart';

import '../fake_audio_platform.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late FakeAudioRecorder audio;

  setUp(() => audio = installFakeAudioPlatform());

  test('too slow is one long buzz, too fast three short ones', () {
    expect(paceCuePattern(PaceCue.tooSlow), [0, 700]);
    expect(paceCuePattern(PaceCue.tooFast), [0, 90, 70, 90, 70, 90]);
  });

  test('both differ from each other and from the kilometre double buzz', () {
    const kilometre = [0, 150, 100, 150];
    final slow = paceCuePattern(PaceCue.tooSlow);
    final fast = paceCuePattern(PaceCue.tooFast);
    expect(slow, isNot(fast));
    expect(slow, isNot(kilometre));
    expect(fast, isNot(kilometre));
  });

  test('each cue plays its own tone', () async {
    await FeedbackCues(AudioPlayer()).paceOff(PaceCue.tooSlow);
    await FeedbackCues(AudioPlayer()).paceOff(PaceCue.tooFast);
    expect(audio.resumedSources, hasLength(2));
    expect(audio.resumedSources.first, contains('pace_slow'));
    expect(audio.resumedSources.last, contains('pace_fast'));
    expect(paceCueSound(PaceCue.tooSlow), isNot(paceCueSound(PaceCue.tooFast)));
  });

  test('stays silent when sound is off (the buzz still carries it)', () async {
    await (FeedbackCues(
      AudioPlayer(),
    )..soundOn = false).paceOff(PaceCue.tooFast);
    expect(audio.resumedSources, isEmpty);
  });

  test('a tone that cannot play is logged, not thrown', () async {
    audio.failNextPlay = true;
    await FeedbackCues(AudioPlayer()).paceOff(PaceCue.tooSlow);
    expect(audio.resumedSources, isEmpty);
  });
}
