/// The route, endpoint markers and attribution button drawn by `RunMap`.
library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/ui/theme.dart';

/// [points] as map coordinates.
List<LatLng> toLatLngs(List<RunPoint> points) => [
  for (final p in points) LatLng(p.latitude, p.longitude),
];

/// The route as one polyline; drawn even when no tile ever loads.
PolylineLayer routeLayer(List<LatLng> coords, ColorScheme scheme) =>
    PolylineLayer(
      polylines: [
        Polyline(
          points: coords,
          strokeWidth: 5,
          color: scheme.primary,
          borderStrokeWidth: 2,
          borderColor: scheme.surface,
        ),
      ],
    );

Marker _dot(LatLng at, Color fill, IconData icon, Color ink) => Marker(
  point: at,
  child: DecoratedBox(
    decoration: BoxDecoration(
      color: fill,
      shape: BoxShape.circle,
      border: Border.all(color: ink, width: 2),
    ),
    child: Icon(icon, size: 16, color: ink),
  ),
);

/// Start marker (green play), and either the live position (accent dot) or
/// the finish flag (red); no end marker for a one-point track.
MarkerLayer endpointLayer(
  List<LatLng> coords, {
  required bool live,
  required ColorScheme scheme,
  required AppStatusColors status,
}) {
  final start = _dot(
    coords.first,
    status.success,
    Icons.play_arrow,
    scheme.surface,
  );
  final last = coords.last;
  return MarkerLayer(
    markers: [
      start,
      if (live)
        _dot(last, scheme.primary, Icons.navigation, scheme.surface)
      else if (coords.length > 1)
        _dot(last, scheme.error, Icons.flag, scheme.surface),
    ],
  );
}

/// The collapsed, icon-only OSM credit; the (c) text shows only when tapped.
RichAttributionWidget attributionButton(ColorScheme scheme) =>
    RichAttributionWidget(
      showFlutterMapAttribution: false,
      attributions: const [TextSourceAttribution('OpenStreetMap contributors')],
      popupBackgroundColor: scheme.surfaceContainerHigh,
      openButton: (context, open) => IconButton(
        onPressed: open,
        icon: Icon(
          Icons.info_outline,
          size: 20,
          color: scheme.onSurface,
          semanticLabel: 'Map attribution',
        ),
      ),
    );
