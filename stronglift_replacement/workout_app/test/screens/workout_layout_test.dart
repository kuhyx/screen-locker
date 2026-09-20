// The workout screen at the phone's real logical size (1080x2400 @ 420 dpi):
// every tile visible without scrolling, and nothing moves when a rest starts.
//
// Set WORKOUT_LAYOUT_SHOTS=<dir> to also dump idle.png / break.png there for
// eyeballing the render when the phone cannot show the screen (done for
// today).
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/break_banner.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/rep_circle.dart';

import '../fake_audio_platform.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

const _phonePhysical = Size(1080, 2400);
const _phoneDpr = 420 / 160;

Future<void> _shot(WidgetTester tester, String name) async {
  final dir = Platform.environment['WORKOUT_LAYOUT_SHOTS'];
  if (dir == null) {
    return;
  }
  final boundary =
      tester.renderObject(find.byKey(const Key('shot')))
          as RenderRepaintBoundary;
  await tester.runAsync(() async {
    final image = await boundary.toImage(pixelRatio: _phoneDpr);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    File('$dir/$name.png').writeAsBytesSync(bytes!.buffer.asUint8List());
  });
}

/// Registers the SDK's Roboto as the test font.
///
/// The default test font draws every glyph one em wide, which makes the
/// header and warmup rows overflow at the phone's width; the geometry under
/// test only means something with the font the phone actually uses.
Future<void> _loadRoboto() async {
  // The test runner's dart lives at <sdk>/bin/cache/dart-sdk/bin/dart; walk
  // up to <sdk>/bin/cache, where the SDK keeps the Material fonts.
  final cache = File(Platform.resolvedExecutable).parent.parent.parent.parent;
  final loader = FontLoader('Roboto');
  for (final weight in ['Regular', 'Medium', 'Bold']) {
    final ttf = File(
      '${cache.path}/artifacts/material_fonts/Roboto-$weight.ttf',
    );
    loader.addFont(Future.value(ByteData.sublistView(ttf.readAsBytesSync())));
  }
  await loader.load();
}

void main() {
  setUpAll(() async {
    await _loadRoboto();
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    installFakeAudioPlatform();
  });

  testWidgets('all tiles fit the phone and stay put when a rest starts', (
    tester,
  ) async {
    tester.view.physicalSize = _phonePhysical;
    tester.view.devicePixelRatio = _phoneDpr;
    // The phone's status bar: it is what tips the four tiles over the
    // viewport, so the scale-to-fit guarantee is exercised, not just present.
    tester.view.padding = const FakeViewPadding(top: 24 * _phoneDpr);
    addTearDown(tester.view.reset);

    await pumpWorkout(
      tester,
      RepaintBoundary(
        key: const Key('shot'),
        child: wrapWorkout(type: 'B', exercises: workoutB),
      ),
    );
    final viewport = tester.view.physicalSize / _phoneDpr;

    Map<String, Rect> tileRects() => {
      for (final e in workoutB)
        e.name: tester.getRect(
          find.ancestor(
            of: find.text(e.name),
            matching: find.byType(ExerciseTile),
          ),
        ),
    };

    final idle = tileRects();
    expect(idle, hasLength(workoutB.length));
    // FittedBox(scaleDown) makes "fits" true by construction; the property
    // that can actually regress is HOW MUCH it had to shrink. Measured at
    // 0.96 on the phone with four tiles; a fifth exercise or a taller tile
    // would push this through the floor and be caught here, not on the phone.
    final scale = idle.values.first.width / (viewport.width - 24);
    expect(scale, greaterThanOrEqualTo(0.9));
    expect(scale, lessThanOrEqualTo(1.0));
    expect(find.byType(Scrollable), findsNothing);
    expect(tester.getSize(find.byType(BreakBanner)).height, BreakBanner.height);
    expect(restRunning(tester), isFalse);
    expect(find.text('Rest'), findsOneWidget);
    expect(find.text('00:00'), findsOneWidget);
    await _shot(tester, 'idle');

    await tapReal(tester, find.byType(RepCircle).first);
    expect(restRunning(tester), isTrue);
    expect(tester.getSize(find.byType(BreakBanner)).height, BreakBanner.height);
    expect(tileRects(), idle);
    await _shot(tester, 'break');

    await tapReal(tester, find.text('Skip'));
    expect(restRunning(tester), isFalse);
    expect(tileRects(), idle);
  });

  testWidgets('landscape would need the scale floor; portrait is locked', (
    tester,
  ) async {
    // Documents why the manifest pins portrait: at the phone's landscape
    // size the column shrinks to roughly half, which is unreadable. The
    // guarantee still holds (nothing scrolls), the lock keeps it from
    // mattering.
    tester.view.physicalSize = Size(
      _phonePhysical.height,
      _phonePhysical.width,
    );
    tester.view.devicePixelRatio = _phoneDpr;
    addTearDown(tester.view.reset);
    await pumpWorkout(tester, wrapWorkout(type: 'B', exercises: workoutB));
    expect(find.byType(Scrollable), findsNothing);
    // getRect, not getSize: only the global rect carries the FittedBox scale.
    final width = tester.getRect(find.byType(ExerciseTile).first).width;
    expect(
      width / (tester.view.physicalSize.width / _phoneDpr - 24),
      lessThan(0.6),
    );
  });

  testWidgets('sandbox rests are short and say so', (tester) async {
    Sandbox.enabled = true;
    Sandbox.restSecs = 7;
    addTearDown(() {
      Sandbox.enabled = false;
      Sandbox.restSecs = Sandbox.defaultRestSecs;
    });
    await pumpWorkout(tester, wrapWorkout(type: 'B', exercises: workoutB));
    await tapReal(tester, find.byType(RepCircle).first);
    expect(find.text('Rest (7 s — sandbox)'), findsOneWidget);
    expect(find.text('00:07'), findsOneWidget);
  });
}
