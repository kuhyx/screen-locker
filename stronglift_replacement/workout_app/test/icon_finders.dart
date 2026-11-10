/// Finders for icon-only controls (textgate: the old words survive only as
/// the icon's spoken `semanticLabel`).
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The [Icon] whose spoken label is exactly [label].
Finder iconLabeled(String label) => find.byWidgetPredicate(
  (w) => w is Icon && w.semanticLabel == label,
  description: 'Icon labelled "$label"',
);

/// The nearest [T] (a button type) around the icon labelled [label].
Finder buttonLabeled<T extends Widget>(String label) =>
    find.ancestor(of: iconLabeled(label), matching: find.byType(T));
