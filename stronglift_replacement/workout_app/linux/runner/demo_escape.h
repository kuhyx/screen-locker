// Demo-only escape hatch for the lock-mode window.
//
// In lock mode the app takes an exclusive seat grab and never releases it, so
// while it is up X delivers every keystroke to this app and to nothing else.
// That is the point in production -- but it also means a human testing the
// handoff cannot reach a terminal, a VT, or the supervisor's own key bindings
// to get out. An escape has to be handled INSIDE the grab, by this app, or it
// cannot be reached at all.
//
// Enabled only by --demo-escape, which the demo harness passes and the
// production supervisor never does. The grab itself is unchanged, so the
// locking mechanism under test is the real one.

#ifndef RUNNER_DEMO_ESCAPE_H_
#define RUNNER_DEMO_ESCAPE_H_

#include <gtk/gtk.h>

// Installs the Ctrl+Shift+Q handler on `window`. No-op unless `enabled`.
void demo_escape_install(GtkWidget* window, gboolean enabled);

#endif  // RUNNER_DEMO_ESCAPE_H_
