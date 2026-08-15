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
