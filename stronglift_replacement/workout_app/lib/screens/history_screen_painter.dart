// The CustomPainter that draws the weight/volume line chart.
//
// Separated from the chart *widgets* because painting is the part that
// changes for visual reasons; see history_screen_charts.dart for why
// these are `part` files.
part of 'history_screen.dart';


class _ChartPainter extends CustomPainter {
  _ChartPainter(
    this.points, {
    required this.lineColor,
    required this.labelColor,
  });

  final List<(DateTime, double)> points;

  // CustomPainter.paint() has no BuildContext, so the caller (which does)
  // passes the themed colors in explicitly.
  final Color lineColor;
  final Color labelColor;

  // Layout constants
  static const _topPad = 14.0; // room for top Y label
  static const _bottomPad = 22.0; // room for X-axis dates
  static const _hPad = 8.0;

  static const _months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  static String _shortDate(DateTime d) => '${_months[d.month - 1]} ${d.day}';

  @override
  void paint(Canvas canvas, Size size) {
    final minW = points.map((p) => p.$2).reduce(min);
    final maxW = points.map((p) => p.$2).reduce(max);
    final minMs = points.first.$1.millisecondsSinceEpoch.toDouble();
    final maxMs = points.last.$1.millisecondsSinceEpoch.toDouble();
    final wRange = maxW - minW;
    final tRange = maxMs - minMs;

    const plotTop = _topPad;
    final plotBottom = size.height - _bottomPad;
    const plotLeft = _hPad;
    final plotRight = size.width - _hPad;
    final plotHeight = plotBottom - plotTop;
    final plotWidth = plotRight - plotLeft;

    double xOf(DateTime t) => tRange == 0
        ? (plotLeft + plotRight) / 2
        : (t.millisecondsSinceEpoch - minMs) / tRange * plotWidth + plotLeft;
    double yOf(double w) => wRange == 0
        ? (plotTop + plotBottom) / 2
        : (1 - (w - minW) / wRange) * plotHeight + plotTop;

    final linePaint = Paint()
      ..color = lineColor
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    final dotPaint = Paint()
      ..color = lineColor
      ..style = PaintingStyle.fill;

    final path = Path()..moveTo(xOf(points.first.$1), yOf(points.first.$2));
    for (final p in points.skip(1)) {
      path.lineTo(xOf(p.$1), yOf(p.$2));
    }
    canvas.drawPath(path, linePaint);
    for (final p in points) {
      canvas.drawCircle(Offset(xOf(p.$1), yOf(p.$2)), 4, dotPaint);
    }

    // Y-axis labels
    final tp = TextPainter(textDirection: TextDirection.ltr);
    void drawText(String text, Offset offset, {double fontSize = 10}) {
      tp
        ..text = TextSpan(
          text: text,
          style: TextStyle(color: labelColor, fontSize: fontSize),
        )
        ..layout()
        ..paint(canvas, offset);
    }

    drawText('${maxW.round()}kg', const Offset(plotLeft, 0));
    drawText('${minW.round()}kg', Offset(plotLeft, plotBottom + 2));

    // X-axis date labels: first, middle, last
    final n = points.length;
    final xIndices = n <= 2 ? [0, n - 1] : [0, n ~/ 2, n - 1];
    for (final i in xIndices) {
      final p = points[i];
      final label = _shortDate(p.$1);
      tp
        ..text = TextSpan(
          text: label,
          style: TextStyle(color: labelColor, fontSize: 9),
        )
        ..layout();
      final cx = xOf(p.$1);
      final dx = (cx - tp.width / 2).clamp(plotLeft, plotRight - tp.width);
      tp.paint(canvas, Offset(dx, size.height - tp.height));
    }
  }

  // lineColor/labelColor come from the app's single fixed dark theme, so
  // they never actually change at runtime — only points varies.
  @override
  bool shouldRepaint(_ChartPainter old) => old.points != points;
}

/// One workout the PC published that this phone has no local session for.
