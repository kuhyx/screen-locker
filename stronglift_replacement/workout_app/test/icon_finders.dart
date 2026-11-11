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

/// The [Icon] whose spoken label contains [part].
Finder iconLabelContaining(String part) => find.byWidgetPredicate(
  (w) => w is Icon && (w.semanticLabel?.contains(part) ?? false),
  description: 'Icon labelled with "$part"',
);

/// The [Semantics] widget whose label is exactly [label] (a painted-glyph
/// group whose old sentence is spoken only).
Finder semanticsLabeled(String label) => find.byWidgetPredicate(
  (w) => w is Semantics && w.properties.label == label,
  description: 'Semantics labelled "$label"',
);
