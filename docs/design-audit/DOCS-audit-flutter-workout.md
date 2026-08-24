## Flutter app (stronglift_replacement/workout_app/)

Design-token entry point: `lib/main.dart:68-74` declares
`ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo,
brightness: Brightness.dark), useMaterial3: true)` — a real Material 3 seed
theme exists. However, **`Theme.of(context)` / `colorScheme` is referenced
zero times anywhere in `lib/screens/` or `lib/widgets/`** (confirmed via
repo-wide grep). The theme is declared but never consumed — every one of the
24 .dart files under `lib/` hardcodes colors directly instead.

- `Colors.*` literals: **~210 occurrences** across `screens/` and
  `widgets/`, 27 distinct named colors. Most common: `Colors.white` (98×),
  `Colors.grey.shade800` (18×), `Colors.redAccent` (12×),
  `Colors.greenAccent` (11×), `Colors.grey.shade900` (10×).
- Raw hex `Color(0xFF...)` literals bypassing `Colors.*` entirely:
  `manual_workout_screen.dart:173,201` (`Color(0xFFFF4444)`) and
  `manual_workout_screen.dart:238,246` (`Color(0xFF88CCFF)`) — these are the
  **exact same hex values** independently hardcoded on the Python/Tkinter
  side (`#ff4444` and `#88ccff`, see e.g. `_sick_dialog.py:70`,
  `_manual_workout_dialog.py:58`), coincidentally kept in sync only because
  no one has touched either yet.
- `fontSize:`/`fontWeight:` literals: 72 occurrences; `history_screen.dart`
  alone uses 12 distinct font sizes (9, 11, 12, 13, 14, 15, 16, 17, 18, 20,
  22, 26).

### Violations

- **Rule 4 (everything deliberate / single source of truth)** — `main.dart`
  builds a `ColorScheme.fromSeed`, but it is dead code from a theming
  standpoint: no screen or widget reads it. Every screen re-derives its own
  ad hoc dark palette from `Colors.grey.shade900/800/700` plus assorted
  accent colors, so a single rebrand (e.g. changing the seed color) would
  require manually editing all 24 files instead of one.
- **Rule 1 (near-black/white, not pure)** — `Colors.white` (pure `#FFFFFF`)
  used 98 times for primary text/icons, e.g. `home_screen.dart:113,122,128,
  211,248,267`, `settings_screen.dart:231,278,430`,
  `history_screen.dart:209,410`. `Colors.black` also appears at
  `rep_circle.dart:76` (`Colors.black87`, near-pure) as text-on-white in the
  neutral rep-circle state. None of these are the theme's actual
  near-white/near-black — they're Flutter's pure-value constants.
- **Rule 2 (saturate your neutrals)** — `Colors.grey.shade900/800/700/400`
  are Material's standard zero-saturation grays (equal R=G=B), used as the
  entire background/surface system in place of `colorScheme.surface`
  (which, being seeded from indigo, *would* be saturated). Bypassing the
  theme produces exactly the generic-gray outcome the theme was set up to
  avoid.
- **Rule 9 (distinct brightness values)** — `Colors.redAccent` (errors) and
  `Colors.orangeAccent`/`Colors.orange.shade800` (pending/resume state) are
  both used as status-signal colors of similar brightness in adjacent UI
  (e.g. `home_screen.dart:222` orangeAccent for active-session text next to
  `Colors.greenAccent` for success at line 200 — three status colors of
  comparable weight competing in one card).
- **Rule 18 (container brightness limits, dark ≤~12%)** — The repeated
  `Scaffold(backgroundColor: Colors.grey.shade900)` /
  `AppBar(backgroundColor: Colors.grey.shade800)` pairing (Material
  `shade900`=`#212121`, luma 12.9%; `shade800`=`#424242`, luma 25.9% — a
  ~13-point jump) appears in every screen's `Scaffold`/`AppBar`:
  `home_screen.dart:104,106`, `settings_screen.dart:275,277`,
  `history_screen.dart:206,208`, `workout_screen.dart:495,498`,
  `manual_workout_screen.dart:154,156`. This exceeds the ~12% dark-interface
  guideline every time it's used.
- **Rule 20 (body text ≥16px)** — Extensive small body text below 16px:
  `fontSize: 9` at `history_screen.dart:612`, `fontSize: 11` (11 occurrences,
  e.g. `home_screen.dart:311`, `history_screen.dart:333,486,612`,
  `settings_screen.dart:388`), `fontSize: 12` (14 occurrences),
  `fontSize: 13` (7 occurrences) — well under the 16px minimum for
  supporting/secondary text throughout.
- **Rule 22 (button padding: horizontal ≈2x vertical)** — `home_screen.dart:
  242` and `:261` set `padding: const EdgeInsets.symmetric(vertical: 14)`
  on full-width `ElevatedButton`s with no `horizontal:` argument, which
  defaults `horizontal` to `0.0` — the inverse of "horizontal ≈2x vertical".
- **Rule 26 (no shadows in dark interfaces)** — The app declares
  `brightness: Brightness.dark` (`main.dart:71`), yet `rep_circle.dart:
  105-111` adds an explicit `BoxShadow(color: Colors.black26, blurRadius: 4,
  offset: Offset(0, 2))` to the rep-tracking circle — the one shadow in the
  whole app, in a UI this rule says shouldn't have any.

### Not applicable

- Rule 5 (optical alignment) — standard Material icons/widgets are already
  optically centered by the framework; no custom asymmetric glyphs.
- Rule 6 (letter-spacing/line-height by size) — the only `letterSpacing`
  uses found (`home_screen.dart:311` → 1.1, `history_screen.dart:333` → 1.3,
  `settings_screen.dart:388` → 1.4) are all on the same small `fontSize: 11`
  eyebrow-label text, consistently given positive tracking as the rule
  recommends for small text — no counter-example at larger sizes to check
  against, so marked N/A rather than a forced Pass.
- Rule 7 (border contrast) — `Border.all(color: color.withValues(alpha:
  0.4))` (`settings_screen.dart:491`) derives border color from the same
  status color as the fill, by design (a tinted pill), not a
  container-edge border this rule targets.
- Rule 8 (align with something else) — standard `Column`/`Row`/`ListView`
  layouts; no cross-screen alignment grid to check.
- Rule 12 (order by visual weight) — screens are single-column flows
  (cards stacked top-to-bottom); no left/right or center/edge weight
  arrangement to evaluate.
- Rule 13 (12-column grid) — mobile single-column layouts throughout; no
  multi-column grid system in use.
- Rule 14 (space between contrast edges) — cannot be verified statically
  without rendering the widget tree.
- Rule 15 (closer elements lighter) — `Card`s at `shade800` sit on
  `shade900` backgrounds (lighter-on-darker as they "lift"), which is
  directionally correct, but see Rule 18 above for the magnitude issue.
- Rule 17 (simple on complex) — flat-colored cards/containers throughout;
  nothing complex to conflict with.
- Rule 19 (outer padding ≥ inner padding) — spot-checked
  `home_screen.dart:143` (`EdgeInsets.all(24)` outer) vs. its nested
  `_WorkoutCard` internal padding (`EdgeInsets.all(16)`,
  `home_screen.dart:188`) — outer ≥ inner, consistent with the rule; not
  exhaustively checked across all 24 files.
- Rule 21 (line length ~70 chars) — Flutter `Text` wraps by default at
  widget width; no unbounded-line risk equivalent to the Tk surface.
- Rule 23 (two typefaces max) — no custom `fontFamily` set anywhere; the
  whole app uses the Material/system default typeface. Trivially compliant.
- Rule 24 (nest corners) — `BorderRadius.circular(8)` is reused verbatim
  across unrelated containers (`home_screen.dart:301`,
  `calendar_widget.dart:63`, `history_screen.dart:402,643,705,772`,
  `settings_screen.dart:490,548,587`) but none of these visibly nest inside
  another rounded container in the surrounding code, so there's no
  outer/inner radius relationship to check.
- Rule 25 (avoid adjacent hard divides) — only one `Divider` found
  (`exercise_tile.dart:115`), not adjacent to another border/divide.
- Rule 27 (don't mix depth techniques) — the app consistently uses flat
  `Container`/`Card` fills with no shadow except the single instance flagged
  under Rule 26; effectively one depth style (none) throughout, so no
  mixing to flag.
- Rule 28 (lower icon contrast next to text) — icons consistently use
  `Colors.white54`/`Colors.white38`/`Colors.white70` (already
  lower-contrast than adjacent full-white/near-white text) rather than full
  `Colors.white`, e.g. `exercise_tile.dart:150,160,167,177,248,252`,
  `history_screen.dart:331,486,507` — this one is actually already followed
  reasonably consistently. Pass.

### Notes

- Rule 4 is the dominant finding for this surface too: an unused
  `ColorScheme.fromSeed` plus ~210 ad hoc `Colors.*`/`Color(0x...)` literals
  means every other color/contrast rule (1, 2, 9, 18) is failing as a direct
  consequence of the same root cause, not independently. Routing all 24
  files through `Theme.of(context).colorScheme` (or a small shared
  `AppColors`/`AppTextStyles` class) would be the highest-leverage single
  fix.
- The coincidental hex overlap between `Color(0xFFFF4444)`/`Color(0xFF88CCFF)`
  (Flutter) and `#ff4444`/`#88ccff` (Python/Tkinter) shows the two UI
  surfaces are visually related by convention only — there is no shared
  token file either could import from, on either language side.
