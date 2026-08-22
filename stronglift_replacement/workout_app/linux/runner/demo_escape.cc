#include "demo_escape.h"

// Deliberately awkward, so it cannot be hit by accident mid-workout, and
// deliberately NOT Escape: the Dart side already binds Escape for in-app
// navigation, and a demo hatch that shadowed it would change the behaviour
// being tested.
static const guint kEscapeKey = GDK_KEY_Q;
static const GdkModifierType kEscapeMods =
    static_cast<GdkModifierType>(GDK_CONTROL_MASK | GDK_SHIFT_MASK);

static gboolean on_key_press(GtkWidget* widget, GdkEventKey* event,
                             gpointer user_data) {
  (void)user_data;
  const guint pressed = gdk_keyval_to_upper(event->keyval);
  if (pressed != kEscapeKey) return FALSE;
  if ((event->state & kEscapeMods) != kEscapeMods) return FALSE;

  // Drop the grab before quitting: destroying a window that still holds the
  // seat can leave the pointer and keyboard grabbed with nothing to release
  // them, which would need exactly the reboot this hatch exists to avoid.
  GdkWindow* gdk_window = gtk_widget_get_window(widget);
  if (gdk_window != nullptr) {
    GdkDisplay* display = gdk_window_get_display(gdk_window);
    gdk_seat_ungrab(gdk_display_get_default_seat(display));
  }
  g_print("WORKOUT_LOCK: demo escape pressed; releasing grab and exiting\n");
  fflush(stdout);
  gtk_window_close(GTK_WINDOW(widget));
  return TRUE;
}

void demo_escape_install(GtkWidget* window, gboolean enabled) {
  if (!enabled) return;
  gtk_widget_add_events(window, GDK_KEY_PRESS_MASK);
  g_signal_connect(window, "key-press-event", G_CALLBACK(on_key_press),
                   nullptr);
  g_print("WORKOUT_LOCK: demo escape armed (Ctrl+Shift+Q)\n");
  fflush(stdout);
}
