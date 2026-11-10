// Without an injected map builder the run screen shows the real map slot
// (over the disk-cached OSM source).
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/map_tile_cache.dart';
import 'package:workout_app/widgets/run_map.dart';

import '../fake_audio_platform.dart';
import '../fake_path_provider.dart';
import '_run_screen_fixtures.dart';

void main() {
  setUp(() {
    installFakeAudioPlatform();
    resetOsmTileProvider();
    final dir = installFakePathProvider();
    addTearDown(() => dir.deleteSync(recursive: true));
  });

  testWidgets('the default map is the run map slot', (tester) async {
    final h = RunHarness();
    await h.pump(tester, realMap: true);
    expect(key('run_map_slot'), findsOneWidget);
    expect(find.byType(RunMap), findsOneWidget);
  });
}
