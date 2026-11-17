// The long cue of a run: advice to finish and the 5 h auto-end.
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/feedback_cues.dart';

import '../fake_audio_platform.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late FakeAudioRecorder audio;

  setUp(() => audio = installFakeAudioPlatform());

  for (final (name, cue) in <(String, Future<void> Function(FeedbackCues))>[
    ('advice to finish', (c) => c.finishSuggested()),
    ('the auto end', (c) => c.autoEnded()),
  ]) {
    group(name, () {
      test('chimes', () async {
        await cue(FeedbackCues(AudioPlayer()));
        expect(audio.resumedSources.single, contains('workout_done'));
      });

      test('stays silent when sound is off', () async {
        await cue(FeedbackCues(AudioPlayer())..soundOn = false);
        expect(audio.resumedSources, isEmpty);
      });

      test('a chime that cannot play is logged, not thrown', () async {
        audio.failNextPlay = true;
        await cue(FeedbackCues(AudioPlayer()));
        expect(audio.resumedSources, isEmpty);
      });
    });
  }
}
