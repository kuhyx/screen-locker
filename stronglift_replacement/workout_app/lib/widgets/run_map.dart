/// The map of a run: route polyline, start/end markers, live position.
///
/// Two constructors, both drop-ins (no other required argument):
///
/// * `RunMap.route(points: track.points)` -- a finished run. The camera
///   fits the whole route ([fitPadding] keeps it clear of overlays).
/// * `RunMap.live(pointsListenable: recorder.livePoints)` -- the live
///   screen. Pass a `ValueListenable<List<RunPoint>>` (the recorder's
///   accepted points, oldest first); the route
///   redraws on every change and, in follow mode (the default), the camera
///   keeps the last point centred. Dragging the map ends follow mode; the
///   recentre button (icon only) turns it back on. The listenable must stay
///   the same object for the widget's lifetime (give it a new `Key` to swap).
///
/// Tiles are OSM raster tiles from tile.openstreetmap.org, cached on disk
/// (`map_tile_cache.dart`) so revisited areas draw offline. The OSM credit is
/// a collapsed info icon; its text shows only when tapped. When no tile
/// loads (offline, first visit) the route still draws on the plain
/// background and ONE warning-level line is logged per map.
///
/// Tests inject `tileProviderOpener` with a fake provider: nothing here
/// touches the network by itself.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/map_tile_cache.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_map_layers.dart';

/// Where an empty map starts: Poland, zoomed out, until a first fix.
const _fallbackCenter = LatLng(52, 19);
const _fallbackZoom = 5.0;

/// The zoom a one-point track or a first live fix gets.
const _closeZoom = 17.0;

/// A map of a run; see the library comment for the two constructors.
class RunMap extends StatefulWidget {
  /// A finished run: [points] drawn and fitted.
  const RunMap.route({
    required List<RunPoint> this.points,
    super.key,
    this.fitPadding = const EdgeInsets.all(40),
    this.tileProviderOpener = openOsmTileProvider,
  }) : pointsListenable = null;

  /// A live run: follows the last point in [pointsListenable].
  const RunMap.live({
    required ValueListenable<List<RunPoint>> this.pointsListenable,
    super.key,
    this.tileProviderOpener = openOsmTileProvider,
  }) : points = null,
       fitPadding = const EdgeInsets.all(40);

  /// The route in detail mode; null in live mode.
  final List<RunPoint>? points;

  /// The accepted points in live mode; null in detail mode.
  final ValueListenable<List<RunPoint>>? pointsListenable;

  /// Space kept free around the fitted route (detail mode).
  final EdgeInsets fitPadding;

  /// Where the tile provider comes from; tests pass a fake.
  final TileProviderOpener tileProviderOpener;

  @override
  State<RunMap> createState() => _RunMapState();
}

class _RunMapState extends State<RunMap> {
  final _controller = MapController();
  TileProvider? _tiles;
  bool _ready = false;
  bool _follow = true;
  bool _warned = false;

  bool get _live => widget.pointsListenable != null;

  List<RunPoint> get _points => _live
      ? widget.pointsListenable!.value
      : widget.points!;

  @override
  void initState() {
    super.initState();
    widget.pointsListenable?.addListener(_followLast);
    unawaited(
      widget.tileProviderOpener().then((p) {
        if (mounted) setState(() => _tiles = p);
      }),
    );
  }

  @override
  void dispose() {
    widget.pointsListenable?.removeListener(_followLast);
    _controller.dispose();
    super.dispose();
  }

  void _followLast() {
    final coords = toLatLngs(_points);
    if (!_ready || !_follow || coords.isEmpty) return;
    final zoom = _controller.camera.zoom;
    _controller.move(coords.last, zoom < 12 ? _closeZoom : zoom);
  }

  void _warnOnce(Object error) {
    if (_warned) return;
    _warned = true;
    logMapWarning(
      'map tiles failed to load ($error); drawing the route on a plain '
      'background',
    );
  }

  MapOptions _options(List<LatLng> coords, ColorScheme scheme) {
    final fit = !_live && coords.length > 1
        ? CameraFit.coordinates(
            coordinates: coords,
            padding: widget.fitPadding,
            maxZoom: _closeZoom,
          )
        : null;
    return MapOptions(
      initialCenter: coords.isEmpty ? _fallbackCenter : coords.last,
      initialZoom: coords.isEmpty ? _fallbackZoom : _closeZoom,
      initialCameraFit: fit,
      backgroundColor: scheme.surfaceContainerHigh,
      onMapReady: () {
        _ready = true;
        _followLast();
      },
      onPositionChanged: (camera, byGesture) {
        if (_live && byGesture && _follow) setState(() => _follow = false);
      },
    );
  }

  Widget _map(BuildContext context, List<RunPoint> points) {
    final scheme = Theme.of(context).colorScheme;
    final coords = toLatLngs(points);
    return FlutterMap(
      mapController: _controller,
      options: _options(coords, scheme),
      children: [
        if (_tiles != null)
          TileLayer(
            urlTemplate: osmTileUrl,
            userAgentPackageName: osmUserAgentPackage,
            tileProvider: _tiles,
            errorTileCallback: (tile, error, stack) => _warnOnce(error),
          ),
        if (coords.length > 1) routeLayer(coords, scheme),
        if (coords.isNotEmpty)
          endpointLayer(
            coords,
            live: _live,
            scheme: scheme,
            status: Theme.of(context).extension<AppStatusColors>()!,
          ),
        attributionButton(scheme),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final listenable = widget.pointsListenable;
    if (listenable == null) return _map(context, widget.points!);
    return Stack(
      fit: StackFit.expand,
      children: [
        ValueListenableBuilder<List<RunPoint>>(
          valueListenable: listenable,
          builder: (context, points, _) => _map(context, points),
        ),
        if (!_follow)
          Positioned(
            left: AppSpacing.sm,
            bottom: AppSpacing.sm,
            child: IconButton.filled(
              onPressed: () {
                setState(() => _follow = true);
                _followLast();
              },
              icon: const Icon(
                Icons.my_location,
                semanticLabel: 'Follow position',
              ),
            ),
          ),
      ],
    );
  }
}
