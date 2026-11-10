/// Reads and writes the TCX files the PC's RunnerUp verifier credits.
///
/// The contract is the PC's parser (`screen_locker/_runnerup_tcx.py`,
/// `_walk_tcx.py`), pinned by a shared golden fixture on both sides:
///
/// * File name `RunnerUp_YYYY-MM-DD-HH-MM-SS_<Sport>.tcx`, stamp in LOCAL
///   time (the PC globs today's local date in the name), suffix `Running` or
///   `Walking` (a walk is recognised by that suffix or `Sport="Walking"`; the
///   encoder writes `Sport="Other"` for it, as RunnerUp does).
/// * `<Id>` and every `<Time>` are UTC with a `Z`; one Lap whose
///   `TotalTimeSeconds` is moving time and `DistanceMeters` the credited
///   distance; every Trackpoint carries `Time` and a cumulative
///   `DistanceMeters` (the PC derives a walk's speed from those).
/// * The source tag is `Author/Name` and `Creator/Name`
///   ([kRunSourceName]); the PC ignores both.
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:xml/xml.dart';

/// Written into `Author/Name` and `Creator/Name`; marks an app-made file.
const String kRunSourceName = 'kuhy workout_app';

const String _ns = 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2';
const String _xsi = 'http://www.w3.org/2001/XMLSchema-instance';

String _utcStamp(DateTime t) => RunTrack.idFor(t);

String _num(double v, int digits) => v.toStringAsFixed(digits);

/// Encodes [track] as a TCX document the PC accepts unchanged.
String encodeTcx(RunTrack track) {
  final b = XmlBuilder()..processing('xml', 'version="1.0" encoding="UTF-8"');
  b.element(
    'TrainingCenterDatabase',
    attributes: {
      'xmlns': _ns,
      'xmlns:xsi': _xsi,
      'xsi:schemaLocation':
          '$_ns http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd',
    },
    nest: () {
      b
        ..element('Activities', nest: () => _activity(b, track))
        ..element(
          'Author',
          attributes: {'xsi:type': 'Application_t'},
          nest: () {
            b
              ..element('Name', nest: kRunSourceName)
              ..element('Build', nest: () => _version(b))
              ..element('LangID', nest: 'en')
              ..element('PartNumber', nest: '000-00000-00');
          },
        );
    },
  );
  return b.buildDocument().toXmlString(pretty: true, indent: '  ');
}

void _activity(XmlBuilder b, RunTrack track) => b.element(
  'Activity',
  attributes: {'Sport': track.sport.tcxSport},
  nest: () {
    b.element('Id', nest: track.id);
    _lap(b, track);
    b.element(
      'Creator',
      attributes: {'xsi:type': 'Device_t'},
      nest: () {
        b
          ..element('Name', nest: kRunSourceName)
          ..element('UnitId', nest: '0')
          ..element('ProductID', nest: '0');
        _version(b);
      },
    );
  },
);

void _version(XmlBuilder b) => b.element(
  'Version',
  nest: () {
    b
      ..element('VersionMajor', nest: '1')
      ..element('VersionMinor', nest: '0');
  },
);

void _lap(XmlBuilder b, RunTrack track) => b.element(
  'Lap',
  attributes: {'StartTime': _utcStamp(track.startedAt)},
  nest: () {
    b
      ..element('TotalTimeSeconds', nest: '${track.totalSeconds}')
      ..element('DistanceMeters', nest: _num(track.distanceM, 3))
      // Required by the TCX schema, as in RunnerUp's own files.
      ..element('Calories', nest: '0')
      ..element('Intensity', nest: 'Active')
      ..element('TriggerMethod', nest: 'Manual')
      ..element('Track', nest: () => track.points.forEach(_point(b)));
  },
);

void Function(RunPoint) _point(XmlBuilder b) =>
    (p) => b.element(
      'Trackpoint',
      nest: () {
        b
          ..element('Time', nest: _utcStamp(p.time))
          ..element(
            'Position',
            nest: () {
              b
                ..element('LatitudeDegrees', nest: _num(p.latitude, 7))
                ..element('LongitudeDegrees', nest: _num(p.longitude, 7));
            },
          );
        if (p.altitudeM != null) {
          b.element('AltitudeMeters', nest: _num(p.altitudeM!, 1));
        }
        b.element('DistanceMeters', nest: _num(p.distanceM, 3));
      },
    );

/// The export file name for [track]: `RunnerUp_<local stamp>_<Sport>.tcx`.
///
/// The stamp is local time. [utcOffset] overrides the device zone (tests,
/// and any caller that knows the zone the run happened in).
String tcxFilename(RunTrack track, {Duration? utcOffset}) {
  final local = utcOffset == null
      ? track.startedAt.toLocal()
      : track.startedAt.add(utcOffset);
  String two(int v) => v.toString().padLeft(2, '0');
  final stamp =
      '${local.year.toString().padLeft(4, '0')}-${two(local.month)}-'
      '${two(local.day)}-${two(local.hour)}-${two(local.minute)}-'
      '${two(local.second)}';
  return 'RunnerUp_${stamp}_${track.sport.tcxName}.tcx';
}

/// Hex SHA-256 of the TCX text: the dedupe key of the `runs` table.
String tcxSha256(String tcx) => sha256.convert(utf8.encode(tcx)).toString();

/// Decodes a RunnerUp or app-made TCX.
///
/// [fileName] is the ORIGINAL export name: RunnerUp writes `Sport="Other"`
/// for a walk and only the `_Walking.tcx` suffix says so. Throws
/// [FormatException] for malformed XML, a missing Activity, or a sport the
/// app does not record (cycling and the rest).
///
/// Trackpoints without a `Position` are skipped: the map and the
/// distance maths need coordinates. Laps are summed, as the PC sums them.
RunTrack decodeTcx(String tcx, {String? fileName}) {
  final XmlDocument doc;
  try {
    doc = XmlDocument.parse(tcx);
  } on XmlException catch (e) {
    throw FormatException('TCX is not valid XML: ${e.message}');
  }
  final activity = doc.descendantElements
      .where((e) => e.localName == 'Activity')
      .firstOrNull;
  if (activity == null) throw const FormatException('TCX has no Activity');
  final sport = _sportOf(activity.getAttribute('Sport'), fileName);
  var seconds = 0.0;
  var metres = 0.0;
  DateTime? lapStart;
  for (final lap in activity.childElements.where((e) => e.localName == 'Lap')) {
    seconds += double.tryParse(_text(lap, 'TotalTimeSeconds') ?? '') ?? 0;
    metres += double.tryParse(_text(lap, 'DistanceMeters') ?? '') ?? 0;
    lapStart ??= DateTime.tryParse(lap.getAttribute('StartTime') ?? '');
  }
  final points = _points(activity);
  final startedAt =
      DateTime.tryParse(_text(activity, 'Id') ?? '') ??
      lapStart ??
      (points.isEmpty ? null : points.first.time);
  if (startedAt == null) throw const FormatException('TCX has no start time');
  return RunTrack(
    id: _text(activity, 'Id') ?? RunTrack.idFor(startedAt),
    sport: sport,
    startedAt: startedAt,
    points: points,
    totalSeconds: seconds.round(),
    distanceM: metres,
    source: _isOurs(doc) ? RunSource.app : RunSource.runnerupImport,
  );
}

RunSport _sportOf(String? attribute, String? fileName) {
  for (final sport in RunSport.values) {
    if (fileName != null && fileName.endsWith('_${sport.tcxName}.tcx')) {
      return sport;
    }
  }
  return RunSport.fromTcxName(attribute) ??
      (throw FormatException('Unsupported TCX sport "$attribute"'));
}

bool _isOurs(XmlDocument doc) => doc.descendantElements.any(
  (e) =>
      (e.localName == 'Author' || e.localName == 'Creator') &&
      _text(e, 'Name') == kRunSourceName,
);

String? _text(XmlElement parent, String name) => parent.childElements
    .where((e) => e.localName == name)
    .firstOrNull
    ?.innerText
    .trim();

List<RunPoint> _points(XmlElement activity) {
  final points = <RunPoint>[];
  for (final tp in activity.descendantElements.where(
    (e) => e.localName == 'Trackpoint',
  )) {
    final time = DateTime.tryParse(_text(tp, 'Time') ?? '');
    final position = tp.childElements
        .where((e) => e.localName == 'Position')
        .firstOrNull;
    final lat = double.tryParse(
      position == null ? '' : _text(position, 'LatitudeDegrees') ?? '',
    );
    final lon = double.tryParse(
      position == null ? '' : _text(position, 'LongitudeDegrees') ?? '',
    );
    if (time == null || lat == null || lon == null) continue;
    points.add(
      RunPoint(
        time: time,
        latitude: lat,
        longitude: lon,
        altitudeM: double.tryParse(_text(tp, 'AltitudeMeters') ?? ''),
        distanceM: double.tryParse(_text(tp, 'DistanceMeters') ?? '') ?? 0,
      ),
    );
  }
  return points..sort((a, b) => a.time.compareTo(b.time));
}
