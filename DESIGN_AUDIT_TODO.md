# Design audit — screen-locker

Generated against safe-design-rules (anthonyhobday.com/sideprojects/saferules).
Report only — nothing in this repo was changed by the audit itself.

This repo has two UI surfaces, audited separately below. `~/utils/gatelock`
was checked with `git -C ~/utils/gatelock rev-parse --show-toplevel` → prints
`/home/kuhy/utils`, i.e. gatelock is a subdirectory of the `~/utils` monorepo,
**not its own git repo**. Per audit scope, no separate gatelock report was
written; see the "Shared gatelock library" section at the end instead.

## Python/Tkinter lock UI (screen_locker/)

Design-token entry point check: **no `ttk.Style()` call anywhere in the
package** (confirmed via repo-wide grep) and `_constants.py` holds only
business-logic constants (budgets, timeouts, file paths) — zero color/font/
spacing tokens. Every color, font, and padding value is a literal typed
directly at each `tk.Label`/`tk.Button`/`tk.Frame`/`tk.Entry` call site,
independently, in 9 files. Evidence:

- Hex color literals: **100 occurrences, 23 distinct values**, across
  `screen_lock.py` (6), `_ui_widgets.py` (6), `_window_setup.py` (3),
  `status_view.py` (21), `_heat_skip.py` (7 + 4 module-level constants),
  `_manual_workout_dialog.py` (15), `_manual_workout_widgets.py` (12),
  `_sick_dialog.py` (18), `_temperature_status_mixin.py` (5).
  `#1a1a1a` alone (the background) appears **31 times** — and it is *also*
  already defined once, correctly, as `LockConfig.bg = "#1a1a1a"` in
  `~/utils/gatelock/gatelock/_window.py:71`. None of the 31 in-repo literals
  import or reference it; `LockWindow.setup()` in gatelock applies
  `config.bg` to the root window (`_window.py:143`), and then every
  screen-locker dialog re-hardcodes the same string as if gatelock's value
  didn't exist.
- `font=("Arial", N[, "bold"])` literals: **25 occurrences**, 6 distinct
  size/weight combos, e.g. `_ui_widgets.py:45,64`, `_sick_dialog.py:111,121`,
  `_manual_workout_widgets.py:70,89,97,116,126,137,145,164,174`.
  `_heat_skip.py:12-17` breaks pattern entirely with its own local
  `_FONT = "monospace"` constant (line 17) plus four color constants
  (`_BG`, `_FG_MAIN`, `_FG_SUB`, `_BTN_SKIP`, `_BTN_NO`) — the only file in
  the package that centralizes *anything*, and it does so locally/unshared
  rather than in a common module.
- `padx=`/`pady=` literals: **59 occurrences**, 13 distinct values (1, 2, 5,
  6, 8, 10, 12, 14, 15, 20, 28, 30) spread across 7 of the 9 files.

### Violations

- **Rule 4 (everything deliberate / single source of truth)** — No
  `ttk.Style()`, no shared colors/fonts/spacing module. Same visual decision
  (e.g. background `#1a1a1a`) is independently re-typed 31 times across 9
  files instead of imported once. `_heat_skip.py:12-17` even invents its own
  local token block, proving the pattern was known and simply not applied
  package-wide. Fixing any single visual value (e.g. rebranding the
  background) means editing up to 9 files by hand with no compiler/lint
  check that all sites were caught.
- **Rule 1 (near-black/white, not pure)** — `bg="#1a1a1a"` (near-black,
  fine) is paired with pure white text: `_ui_widgets.py:38,57` default
  `color: str = "white"`, plus explicit `fg="white"` at `_window_setup.py:40`,
  `_sick_dialog.py:112,128,138` (X11 name `"white"` = `#FFFFFF`), and 6 more
  in `_manual_workout_widgets.py` (lines 90, 112→ label fg, 116, 137, 158,
  165). Pure-white-on-near-black is the harsh contrast this rule warns
  against; should be a near-white (e.g. `#f0f0f0`/`#eaeaea`).
- **Rule 2 (saturate your neutrals)** — `#1a1a1a` and `#2a2a2a` have equal
  R=G=B (26,26,26 and 42,42,42): true zero-saturation gray, not tinted warm
  or cool. Generic gray per the rule's definition.
- **Rule 9 (distinct brightness values in a palette)** — `#ffaa00` (warning/
  bonus amber, e.g. `screen_lock.py:319`, `status_view.py:181`) and
  `#ff8844` (network/temp-check failure, e.g. `status_view.py:121,243`,
  `_temperature_status_mixin.py:50,57,65`) are near-identical in hue and
  brightness despite signaling different states (bonus/pending vs.
  error/failure) — they will read as the same color at a glance.
- **Rule 11 (mathematically related measurements)** — `padx`/`pady` values
  (1, 2, 5, 6, 8, 10, 12, 14, 15, 20, 28, 30) don't follow a consistent
  scale (not all multiples of 4 or 8); e.g. `pady=1` at `status_view.py:177`
  sits next to `pady=2` (`status_view.py:160`) and `pady=28`
  (`_heat_skip.py:74`) elsewhere — no discernible spacing system.
- **Rule 20 (body text ≥16px)** — Multiple body-text sizes sit well under
  16px: `font_size=10` at `status_view.py:248,253,255` (the last one,
  line 255, also uses the lowest-contrast color in the file, `#666666`, for
  a 10px label — compounding readability), `font_size=11` at
  `status_view.py:199`, `_heat_skip.py:91,104` (`font=(_FONT, 11)`),
  `font_size=12` at `status_view.py:160,212,225,239,243`,
  `_temperature_status_mixin.py:43,50,57,65`, `_sick_dialog.py:135`
  (`font=("Arial", 12)` on the `tk.Text` justification box), `font_size=13`
  at `status_view.py:121,123,181`.
- **Rule 21 (line length ~70 chars)** — No widget in the package sets
  `wraplength` (confirmed: zero matches for `wraplength` repo-wide), so long
  strings render as one unbroken line regardless of window width. Concrete
  case: `_sick_dialog.py:205-207`, the commitment-prompt text "If you say
  YES and skip via 'I'm sick' tomorrow, the sick day costs 2x normal." is
  ~80 characters and will render as a single line at `font_size=16` with no
  wrap control.
- **Rule 22 (button padding: horizontal ≈2x vertical)** — Only
  `_heat_skip.py:92,93,105,106` sets explicit button padding
  (`padx=14, pady=5`, ratio 2.8x — roughly compliant). Every other button in
  the package goes through `UIWidgetsMixin._button()`
  (`_ui_widgets.py:71-90`), which sets no `padx`/`pady` at all and relies on
  Tk's built-in default padding — a different, unspecified ratio. Button
  proportions are therefore inconsistent across dialogs, not a deliberate
  choice.
- **Rule 27 (don't mix depth techniques)** — `UIWidgetsMixin._button()`
  (`_ui_widgets.py:71-90`) sets no `relief`, so every button in
  `status_view.py`, `_sick_dialog.py`, `_manual_workout_dialog.py`, and
  `_manual_workout_widgets.py` uses Tk's default `relief="raised"` (a faux
  3D bevel). `_heat_skip.py:94,107` explicitly overrides to
  `relief="flat"` for its two buttons only — one dialog in the app uses a
  flat depth style while every other dialog uses a raised/beveled one.

### Not applicable

- Rule 5 (optical alignment) — no asymmetric icon/shape glyphs requiring
  eye-adjusted centering; text/emoji labels only.
- Rule 6 (letter-spacing/line-height by size) — Tk's `font=` tuple has no
  letter-spacing or line-height controls; not expressible in this stack.
- Rule 7 (border contrast) — no widget in the package sets `borderwidth`
  or a visible border color (only one incidental `highlightthickness=0` at
  `_manual_workout_dialog.py:72`, which removes a border, not adds one).
- Rule 8 (align with something else) — pack/grid layouts are internally
  consistent per-dialog; no cross-dialog layout grid to check against.
- Rule 12 (order by visual weight) — button rows use uniform-weight buttons
  (same size/style, only color differs); no weight hierarchy to evaluate.
- Rule 13 (12-column grid) — fixed 2-column form grid
  (`_manual_workout_widgets.py:26-49`) is a bespoke field layout, not a page
  grid system this rule targets.
- Rule 14 (space between contrast edges, not bounding box) — cannot be
  verified from source without rendering; Tk widgets' effective visual
  edges vs. bounding boxes aren't determinable statically.
- Rule 15 (closer elements lighter) — single flat z-plane throughout; no
  layered/stacked surfaces.
- Rule 16 (shadow blur ≈ 2x offset) — no shadows anywhere in the package.
- Rule 17 (simple on complex) — flat solid backgrounds behind all text;
  trivially compliant, nothing to flag.
- Rule 18 (container brightness limits) — the one adjacent pair found,
  `#1a1a1a` (bg, luma 10.2%) vs. `#2a2a2a` (entry/spinbox fields, luma
  16.5%), differs by ~6.3 percentage points — within the ~12% dark-mode
  limit. Pass.
- Rule 19 (outer padding ≥ inner padding) — the lock window has no bounded
  "container" with edge padding (content is `place(relx=0.5, rely=0.5,
  anchor="center")` on a fullscreen root); the outer/inner relationship this
  rule assumes doesn't apply to a centered-content-on-fullscreen-canvas
  layout.
- Rule 23 (two typefaces max) — only "Arial" and "monospace"
  (`_heat_skip.py:17`) appear; 2 total, within the limit (the inconsistency
  of *where* each is used is captured under Rule 4 above, not this rule).
- Rule 24 (nest corners) — no widget sets a corner radius (stock Tk widgets
  are rectangular); nothing to nest.
- Rule 25 (avoid adjacent hard divides) — no borders/dividers used anywhere;
  nothing to conflict.
- Rule 26 (no shadows in dark interfaces) — Pass by omission: no shadows
  exist in this dark-background UI.
- Rule 28 (lower icon contrast next to text) — emoji glyphs (💪, 😷, ✓, ☀,
  ⚠, 🔥) share the same `fg=` color as their surrounding text; Tk offers no
  per-glyph opacity control within one Label's text, so this can't be
  addressed without moving emoji into separate, independently-colored
  widgets.

### Notes

- The absence of any shared theme/constants module means every rule above
  that *did* pass (18, 26) did so incidentally, not by design — there's no
  guard rail keeping it that way as new dialogs get added.
- `_heat_skip.py`'s local `_BG`/`_FG_MAIN`/`_FG_SUB`/`_BTN_SKIP`/`_BTN_NO`/
  `_FONT` constants are the one place in the package that already knows
  centralizing tokens is worth doing — promoting this pattern to a shared
  `screen_locker/_theme.py` (or, better, sourcing from gatelock's
  `LockConfig`) would fix Rule 4 and cascade-fix several of the violations
  above in one pass.

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

## Shared gatelock library

`~/utils/gatelock` is **not** its own git repo — `git -C ~/utils/gatelock
rev-parse --show-toplevel` resolves to `/home/kuhy/utils`, so it's a
subdirectory of the `~/utils` monorepo. Per audit scope, gatelock itself was
not walked against all 28 rules and no separate
`~/utils/gatelock/DESIGN_AUDIT_TODO.md` was written.

What's relevant here: gatelock defines exactly **one** real design token —
`LockConfig.bg: str = "#1a1a1a"` (`~/utils/gatelock/gatelock/_window.py:71`),
applied via `self.root.configure(bg=self._config.bg, ...)` in
`LockWindow.setup()` (`_window.py:143`). Both consumer repos re-hardcode
this same literal instead of reading it back off their own `LockConfig`
instance:

- **screen-locker** (this repo) — `#1a1a1a` appears 31 times across 9 files
  (see the Tkinter section above) despite `screen_lock.py:148-153`
  constructing a `LockConfig` instance (as `config`) just a few lines above
  each of those files' widget-creation call sites.
- **diet-guard** — not inspected as part of this audit (out of scope for
  this repo's report), but per the shared-infra note in the task, it is the
  other known consumer of `LockConfig`/`LockWindow` and should be checked
  for the same duplication pattern if/when a design audit is run there.

Fixing the screen-locker Rule 4 finding above by having widget-creation code
read `self._lock_config.bg` (threaded through from the `LockConfig` already
built in `ScreenLocker.__init__`) instead of re-typing `"#1a1a1a"` would
close this loop without needing any gatelock-side change.
