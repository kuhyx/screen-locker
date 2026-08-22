#include "my_application.h"

#include "demo_escape.h"

#include <flutter_linux/flutter_linux.h>
#ifdef GDK_WINDOWING_X11
#include <gdk/gdkx.h>
#endif

#include "flutter/generated_plugin_registrant.h"

struct _MyApplication {
  GtkApplication parent_instance;
  char** dart_entrypoint_arguments;
};

G_DEFINE_TYPE(MyApplication, my_application, GTK_TYPE_APPLICATION)

// ---------------------------------------------------------------------------
// Lock mode (--lock-mode): this window IS the screen lock.
//
// The Python locker (screen_locker) still owns the gatelock arbiter claim and
// keeps holding the X grab while we start up, so our first grab attempts fail
// by design. We map fullscreen + override-redirect FIRST -- covering the
// screen before anything is released -- then print the ready line, and retry
// the grab every 200ms until the supervisor drops its own. Ordering matters:
// releasing before we are up would expose the live desktop for the whole of
// Flutter's cold start.
//
// There is no Dart API for override-redirect or an X11 grab, which is why
// this lives in the runner rather than in lib/.
// ---------------------------------------------------------------------------

// Retry cadence for the grab, matching gatelock's _DEFAULT_GRAB_RETRY_MS.
static const guint kGrabRetryMs = 200;

static gboolean lock_mode_enabled = FALSE;
static gboolean lock_grab_held = FALSE;
// Demo harness only; the production supervisor never passes it.
static gboolean demo_escape_enabled = FALSE;

// Takes the exclusive seat grab. Returns TRUE while it should keep retrying.
static gboolean try_seat_grab(gpointer data) {
  GtkWidget* window = GTK_WIDGET(data);
  GdkWindow* gdk_window = gtk_widget_get_window(window);
  if (gdk_window == nullptr) return G_SOURCE_CONTINUE;  // not realized yet

  GdkDisplay* display = gdk_window_get_display(gdk_window);
  GdkSeat* seat = gdk_display_get_default_seat(display);
  GdkGrabStatus status =
      gdk_seat_grab(seat, gdk_window, GDK_SEAT_CAPABILITY_ALL,
                    TRUE, nullptr, nullptr, nullptr, nullptr);
  if (status != GDK_GRAB_SUCCESS) {
    // Expected until the supervisor releases. Never fatal: a lock that gave up
    // here would leave the machine unlocked, which is the whole failure mode
    // this design exists to prevent.
    return G_SOURCE_CONTINUE;
  }
  lock_grab_held = TRUE;
  g_print("WORKOUT_LOCK: grab acquired\n");
  return G_SOURCE_REMOVE;
}

// Applies override-redirect + fullscreen, then starts the grab retry loop.
static void enter_lock_mode(GtkWindow* window) {
  GtkWidget* widget = GTK_WIDGET(window);
  gtk_window_set_decorated(window, FALSE);
  gtk_window_set_deletable(window, FALSE);
  gtk_window_set_keep_above(window, TRUE);

  // An override-redirect window is invisible to the window manager, so
  // gtk_window_fullscreen() -- which merely ASKS the WM for fullscreen -- does
  // nothing here. Size and place it against the monitor geometry directly,
  // otherwise the window keeps its default 1280x720 and leaves an uncovered
  // strip of live desktop at the edge of a larger screen.
  GdkDisplay* display = gtk_widget_get_display(widget);
  GdkMonitor* monitor = gdk_display_get_primary_monitor(display);
  if (monitor == nullptr) monitor = gdk_display_get_monitor(display, 0);
  if (monitor != nullptr) {
    GdkRectangle geometry;
    gdk_monitor_get_geometry(monitor, &geometry);
    gtk_window_move(window, geometry.x, geometry.y);
    gtk_window_resize(window, geometry.width, geometry.height);
  }
  gtk_window_fullscreen(window);

  // Realize (create the X window) without mapping it, so override-redirect is
  // set on an unmapped window.
  gtk_widget_realize(widget);

  GdkWindow* gdk_window = gtk_widget_get_window(widget);
  if (gdk_window != nullptr) {
    // Bypass the WM entirely: i3 would otherwise re-tile or let the user
    // move/close this window.
    gdk_window_set_override_redirect(gdk_window, TRUE);
  }
  g_timeout_add(kGrabRetryMs, try_seat_grab, widget);
}

// Called when first Flutter frame received.
static void first_frame_cb(MyApplication* self, FlView* view) {
  GtkWidget* toplevel = gtk_widget_get_toplevel(GTK_WIDGET(view));
  if (lock_mode_enabled) {
    // Configure BEFORE the first map: toggling override-redirect on a window
    // that is already mapped leaves it mapped but never repainting (a blank
    // grey rectangle that still holds the grab -- the worst possible lock).
    enter_lock_mode(GTK_WINDOW(toplevel));
    // Installed before the window is shown, so the hatch is live for every
    // keystroke the grab will deliver -- including the first.
    demo_escape_install(toplevel, demo_escape_enabled);
    gtk_widget_show(toplevel);
    // The supervisor releases its own grab only after seeing this line, so the
    // screen is already covered by us when it does. Flushed because stdout to
    // a pipe is block-buffered and the handshake would otherwise deadlock.
    g_print("WORKOUT_LOCK: ready\n");
    fflush(stdout);
  } else {
    gtk_widget_show(toplevel);
  }
}

// Implements GApplication::activate.
static void my_application_activate(GApplication* application) {
  MyApplication* self = MY_APPLICATION(application);
  GtkWindow* window =
      GTK_WINDOW(gtk_application_window_new(GTK_APPLICATION(application)));

  // Use a header bar when running in GNOME as this is the common style used
  // by applications and is the setup most users will be using (e.g. Ubuntu
  // desktop).
  // If running on X and not using GNOME then just use a traditional title bar
  // in case the window manager does more exotic layout, e.g. tiling.
  // If running on Wayland assume the header bar will work (may need changing
  // if future cases occur).
  gboolean use_header_bar = !lock_mode_enabled;
#ifdef GDK_WINDOWING_X11
  GdkScreen* screen = gtk_window_get_screen(window);
  if (GDK_IS_X11_SCREEN(screen)) {
    const gchar* wm_name = gdk_x11_screen_get_window_manager_name(screen);
    if (g_strcmp0(wm_name, "GNOME Shell") != 0) {
      use_header_bar = FALSE;
    }
  }
#endif
  if (use_header_bar) {
    GtkHeaderBar* header_bar = GTK_HEADER_BAR(gtk_header_bar_new());
    gtk_widget_show(GTK_WIDGET(header_bar));
    gtk_header_bar_set_title(header_bar, "workout_app");
    gtk_header_bar_set_show_close_button(header_bar, TRUE);
    gtk_window_set_titlebar(window, GTK_WIDGET(header_bar));
  } else {
    gtk_window_set_title(window, "workout_app");
  }

  gtk_window_set_default_size(window, 1280, 720);

  g_autoptr(FlDartProject) project = fl_dart_project_new();
  fl_dart_project_set_dart_entrypoint_arguments(
      project, self->dart_entrypoint_arguments);

  FlView* view = fl_view_new(project);
  GdkRGBA background_color;
  // Background defaults to black, override it here if necessary, e.g. #00000000
  // for transparent.
  gdk_rgba_parse(&background_color, "#000000");
  fl_view_set_background_color(view, &background_color);
  gtk_widget_show(GTK_WIDGET(view));
  gtk_container_add(GTK_CONTAINER(window), GTK_WIDGET(view));

  // Show the window when Flutter renders.
  // Requires the view to be realized so we can start rendering.
  g_signal_connect_swapped(view, "first-frame", G_CALLBACK(first_frame_cb),
                           self);
  gtk_widget_realize(GTK_WIDGET(view));

  fl_register_plugins(FL_PLUGIN_REGISTRY(view));

  gtk_widget_grab_focus(GTK_WIDGET(view));
}

// Implements GApplication::local_command_line.
static gboolean my_application_local_command_line(GApplication* application,
                                                  gchar*** arguments,
                                                  int* exit_status) {
  MyApplication* self = MY_APPLICATION(application);
  // Strip out the first argument as it is the binary name.
  self->dart_entrypoint_arguments = g_strdupv(*arguments + 1);

  // --lock-mode is handled here AND forwarded to Dart: the runner needs it
  // for the grab, the Dart side for the no-exit UI.
  for (gchar** arg = self->dart_entrypoint_arguments; *arg != nullptr; arg++) {
    if (g_strcmp0(*arg, "--lock-mode") == 0) {
      lock_mode_enabled = TRUE;
    } else if (g_strcmp0(*arg, "--demo-escape") == 0) {
      demo_escape_enabled = TRUE;
    }
  }

  g_autoptr(GError) error = nullptr;
  if (!g_application_register(application, nullptr, &error)) {
    g_warning("Failed to register: %s", error->message);
    *exit_status = 1;
    return TRUE;
  }

  g_application_activate(application);
  *exit_status = 0;

  return TRUE;
}

// Implements GApplication::startup.
static void my_application_startup(GApplication* application) {
  // MyApplication* self = MY_APPLICATION(object);

  // Perform any actions required at application startup.

  G_APPLICATION_CLASS(my_application_parent_class)->startup(application);
}

// Implements GApplication::shutdown.
static void my_application_shutdown(GApplication* application) {
  // MyApplication* self = MY_APPLICATION(object);

  // Perform any actions required at application shutdown.

  G_APPLICATION_CLASS(my_application_parent_class)->shutdown(application);
}

// Implements GObject::dispose.
static void my_application_dispose(GObject* object) {
  MyApplication* self = MY_APPLICATION(object);
  g_clear_pointer(&self->dart_entrypoint_arguments, g_strfreev);
  G_OBJECT_CLASS(my_application_parent_class)->dispose(object);
}

static void my_application_class_init(MyApplicationClass* klass) {
  G_APPLICATION_CLASS(klass)->activate = my_application_activate;
  G_APPLICATION_CLASS(klass)->local_command_line =
      my_application_local_command_line;
  G_APPLICATION_CLASS(klass)->startup = my_application_startup;
  G_APPLICATION_CLASS(klass)->shutdown = my_application_shutdown;
  G_OBJECT_CLASS(klass)->dispose = my_application_dispose;
}

static void my_application_init(MyApplication* self) {}

MyApplication* my_application_new() {
  // Set the program name to the application ID, which helps various systems
  // like GTK and desktop environments map this running application to its
  // corresponding .desktop file. This ensures better integration by allowing
  // the application to be recognized beyond its binary name.
  g_set_prgname(APPLICATION_ID);

  return MY_APPLICATION(g_object_new(my_application_get_type(),
                                     "application-id", APPLICATION_ID, "flags",
                                     G_APPLICATION_NON_UNIQUE, nullptr));
}
