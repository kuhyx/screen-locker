# Task: replace blind coordinate tapping with element-targeted Android UI automation

> **STATUS 2026-08-10: BUILT.** The tool now exists at
> `~/testsAndMisc/python_pkg/android_ui/` (see its README). It covers `dump` /
> `find` / `tap` / `type` / `wait` / `focus` with verified typing, ambiguity as
> an error, keyboard detection, and partial-tree retries — all exercised
> against the physical Pixel 6a. What remains from the spec below is the
> optional MCP wrapper, `scroll_to()`, and rolling it out to `~/todo` and
> `~/dufs-cloud/app`. Everything after this line is the original brief, kept
> because it records WHY each guarantee exists.

## what

Every Flutter/Android app in these repos is currently driven by an agent the
same bad way: screenshot -> read pixel positions by eye -> `adb shell input tap
<x> <y>`. Replace that with a reusable tool that finds elements by *identity*
(text, content-desc, resource-id) and taps their real bounds, and that can
report what is on screen as structured text instead of an image.

## why this is not a nicety

Observed in one session (2026-08-10, workout_app Firebase verification):

- **Silent mis-taps.** A tap at `(540, 1705)` intended for the password field
  landed with the field unfocused. The typed password went nowhere. Nothing
  errored — the next screenshot just showed an empty box. A no-op and a hit are
  indistinguishable without dumping the tree and diffing.
- **Layout shift invalidates every coordinate.** Opening the soft keyboard moved
  the email field from y=1572 to y=1319. Coordinates captured one step earlier
  were already wrong.
- **Screenshot scaling is a manual multiply.** The harness renders 1080x2400 at
  900x2000, so every read coordinate needs `* 1.20`. One forgotten multiply is
  an off-screen tap.
- **Screenshots are expensive.** A full-page PNG per step burns far more context
  than the equivalent element list, and can't be grepped or asserted on.

`uiautomator dump` already solves this and is on every device — no new
dependency:

```bash
adb shell uiautomator dump /sdcard/ui.xml
adb pull /sdcard/ui.xml
# -> <node text="Connect Firebase" class="android.widget.Button"
#           bounds="[32,1808][1048,1878]" .../>
```

This is how the same session recovered: dumping the tree found both `EditText`
nodes by class and gave exact centers, and the retry worked first time.

## where

New shared tool, not a per-repo copy. Two options, pick one:

- `~/testsAndMisc/python_pkg/android_ui/` — a CLI (`android-ui find "Connect
  Firebase"`, `android-ui tap "Connect Firebase"`, `android-ui dump`), matching
  how `app_icons` is already shared across repos.
- An MCP server exposing the same as tools, which is what makes it available to
  the agent without shelling out. Preferred if MCP is acceptable — the user
  asked for "some tool ... (mcp?) which also translates to UI".

Consumers (every repo with an Android surface):
- `~/screen-locker/stronglift_replacement/workout_app`
- `~/todo`
- `~/dufs-cloud/app`
- any future Flutter app (this should be part of the app scaffold)

## must

- `find(query)` -> matching elements with class, text/content-desc, bounds,
  center, and enabled/focused state. Match on text, content-desc, or
  resource-id; substring and exact.
- `tap(query)` -> resolves the query, taps the center of the *current* bounds
  (re-dump before every tap; never reuse a stale coordinate), and **fails
  loudly with a non-zero exit when the query matches zero or >1 elements**.
  Ambiguity must be an error, not a silent first-match.
- `type(query, text)` -> focus the field, type, then **verify the field's text
  actually changed** and fail if not. This is the specific bug that cost this
  session a round trip.
- `dump()` -> flat, greppable text list of visible elements. This replaces the
  screenshot for most steps.
- Waits: `wait_for(query, timeout)` that polls the tree, so no more blind
  `sleep 14`.
- must not: require root, an emulator, a running Flutter debug connection, or
  any change to app source. It must work against a plain release APK on a
  physical device over adb.
- optional: `flutter drive` / integration_test as a second backend when a debug
  build IS available — richer (widget keys, no dump latency), but it cannot
  drive a release APK, so it can't be the only path.
- optional: screenshot fallback for genuinely visual checks (theming, icon
  rendering) — where a picture is the point, not a workaround.

## done

A verification script that drives workout_app's "connect Firebase" flow
end-to-end with **zero hardcoded pixel coordinates** in it, and:

- passes on the current layout;
- still passes after the SYNC and OFFLINE BACKUP sections are reordered in
  `settings_screen.dart` (the test that coordinate-based automation fails);
- exits non-zero, naming the query, when an element is missing.

## verify

On the physical Pixel 6a over adb, against an installed release APK — not an
emulator and not a debug-only Flutter driver session.

## read first

- This session's working recovery: `uiautomator dump` + the bounds-parsing
  python in the screen-locker scratchpad (`ui.xml`, `ui2.xml`).
- `~/screen-locker/CLAUDE.md` — "You are NOT done until you install the new
  version on the phone itself", which is why agent-driven UI is on the critical
  path for every task in this repo.
- Note `uiautomator dump` returns an empty/partial tree while an animation is
  in flight; retry-with-backoff belongs in the tool, not in each caller.
- **Observed 2026-08-10, must be handled:** while a Flutter `TextField` holds
  focus, the dump returns ONLY the `EditText` nodes — the rest of the tree
  (including the button you are about to tap) is missing, and it stays missing
  across retries, so a naive retry loop never converges. Worse, `KEYCODE_BACK`
  to dismiss the keyboard is treated by Flutter as a route pop: it navigated
  out of Settings and discarded the typed credentials, twice. The tool must
  unfocus without popping the route (tap dead space, or `dumpsys input_method`
  to check `mInputShown` first) and must distinguish "tree is partial" from
  "element is genuinely absent" rather than reporting a false negative.
