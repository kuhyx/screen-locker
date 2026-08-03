"""Auxiliary (non-lock) window setup for ScreenLocker.

The fullscreen lock-window mechanics (overrideredirect, input grab,
VT-disable) now live in the shared ``gatelock`` package. This module keeps
only the screen-locker-specific windows that are never the lock itself: the
post-sick-day verification window, the demo close button, and the optional
relaxed-day prompt.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import (
    RANK_SCREEN_LOCKER,
    Arbiter,
    LockWindow,
    ScrollableSurface,
)

from screen_locker._surface_group import FrameGroup

if TYPE_CHECKING:
    from gatelock import SurfaceInfo

# Tk classes that accept keyboard focus by default. Checking ``takefocus`` alone
# is not enough: it is "" on most widgets, which means "ask ::tk::FocusOK", so an
# empty value indicates a default-focusable widget rather than an opted-out one.
_FOCUSABLE_CLASSES = frozenset(
    {"Button", "Checkbutton", "Entry", "Listbox", "Radiobutton", "Spinbox", "Text"}
)


def _first_focusable(widget: tk.Misc) -> tk.Misc | None:
    """Return the first descendant that would accept keyboard focus."""
    for child in widget.winfo_children():
        if str(child.cget("takefocus")) == "0":
            continue
        if child.winfo_class() in _FOCUSABLE_CLASSES:
            return child
        deeper = _first_focusable(child)
        if deeper is not None:
            return deeper
    return None


class WindowSetupMixin:
    """Mixin providing the screen-locker-specific auxiliary windows."""

    # Declared because this mixin both reads and *reassigns* it; without the
    # annotation mypy cannot infer the attribute's type through the mixin.
    container: FrameGroup

    @property
    def _scrollers(self) -> dict[str, ScrollableSurface]:
        """Viewports for the live outputs, keyed by output name.

        Held so a repaint can reset the scroll position and re-arm
        focus-following on the newly built widgets.

        Created lazily by this mixin rather than initialised by the host, so the
        mixin owns its own state: ``build_surface`` can be called before the
        host's ``__init__`` finishes (``LockWindow.setup()`` invokes it), and
        requiring the host to remember an assignment is the kind of coupling
        that breaks quietly when a new host appears.
        """
        # hasattr rather than try/except: an AttributeError here would be a real
        # bug worth surfacing, and catching it to mean "first call" is exactly
        # the swallowed-exception pattern this repo bans.
        if not hasattr(self, "_scroller_map"):
            self._scroller_map: dict[str, ScrollableSurface] = {}
        return self._scroller_map

    def _build_lock_window(self) -> LockWindow:
        """Claim the screen at this app's rank and build the lock.

        The arbiter is published here and then handed to ``LockWindow``,
        which owns releasing it on close -- so it is deliberately not kept
        as an attribute of the locker.
        """
        arbiter = Arbiter(
            "screen_locker",
            RANK_SCREEN_LOCKER,
            grab=self._colors.resolved_grab(),
            disable_vt=self._colors.resolved_disable_vt(),
        )
        arbiter.publish()
        arbiter.acquire_holder()
        lock = LockWindow(self.root, self._colors, hooks=self, arbiter=arbiter)
        lock.setup()
        return lock

    def _ensure_container(self) -> None:
        """Give the non-lock windows a scrollable container group of one.

        The verify and relaxed-day windows never build a lock, so nothing
        called ``build_surface`` and the group is still empty.

        They get the same viewport the lock surfaces do rather than a bare
        centred frame: their content already exceeds their window (see
        :meth:`_setup_aux_window`), and a centred frame clips symmetrically
        instead of scrolling. ``center_when_fits`` preserves the centred look
        for the screens that do fit.
        """
        if self.container.surfaces:
            return
        scroller = ScrollableSurface(self.root, self._colors, center_when_fits=True)
        scroller.container.pack(fill="both", expand=True)
        self._scrollers["__aux__"] = scroller
        self.container = FrameGroup([scroller.content])

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """Add one scrollable, keyboard-reachable container for a live output.

        Only the container is built here, not the screen inside it: which
        screen is showing depends on flow state the lock knows nothing
        about, so the caller repaints through the usual flow entry point
        once the surface exists.

        This was a bare ``place(relx=0.5, rely=0.5, anchor="center")`` frame.
        A ``place``d frame takes its *requested* size and is clipped by its
        parent, so any screen taller than the display lost content off the top
        **and** the bottom simultaneously -- the heading and the submit button
        at once -- with no scrollbar and nothing to indicate anything was
        missing. On a 768px panel several screens do exceed the display (the
        status view stacks a data-independent seven-day block plus four
        buttons), and this is a hard lock with a global grab and VT switching
        disabled, so unreachable content is unrecoverable.

        ``center_when_fits`` keeps short screens looking exactly as they did.
        """
        scroller = ScrollableSurface(parent, self._colors, center_when_fits=True)
        scroller.container.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._scrollers[surface.output_name] = scroller
        self.container.add(scroller.content, surface.output_name)

    def teardown_surface(self, surface: SurfaceInfo) -> None:
        """Forget the container and viewport for an output that went dark."""
        self.container.discard(surface.output_name)
        self._scrollers.pop(surface.output_name, None)

    def settle_surfaces(self) -> None:
        """Re-arm focus-following and reset scroll after a repaint.

        Called once a flow has finished painting a screen. Focus-following has
        to be re-armed because it binds ``<FocusIn>`` per widget, and a repaint
        replaces those widgets; the scroll reset matters because a new screen
        should start at its top, not wherever the previous one was left.
        """
        for scroller in self._scrollers.values():
            scroller.finalize()

    def on_focus_ready(self, surface: SurfaceInfo | None) -> None:
        """Focus the first button so the lock is operable without a pointer.

        This fires once, when the lock is mapped and grabbed. At that moment the
        screen is the phone-check status -- buttons only -- which this hook used
        to treat as "nothing to focus". That reasoning was wrong: buttons are
        exactly what needs focusing. The lock holds a *global* grab with VT
        switching disabled and there is no other window on screen, so starting
        with nothing focused meant a keyboard-only user had to blind-Tab into a
        ring that (before the focus-ring fix) was invisible black-on-black, with
        no way to tell what was selected or whether the keypress had landed.

        The screens that take typed input (the manual-workout form, the sick
        dialog) still focus their own first field as they are built; this only
        covers the button-only screens that previously focused nothing.

        ``surface`` is None when no output is live at all -- the lock is held
        with nothing to show, which is still a valid state and needs no focus.
        """
        if surface is None:
            return
        self._focus_first_focusable()

    def _focus_first_focusable(self) -> None:
        """Focus the first keyboard-focusable widget on the primary surface.

        Walks the tree rather than taking a widget reference, because which
        screen is painted depends on flow state this mixin does not track.
        """
        if not self.container.surfaces:
            return
        found = _first_focusable(self.container.first)
        if found is not None:
            found.focus_set()

    def on_callback_error(self) -> None:
        """Surfaced via GateRoot's logging already; no extra action yet."""

    def on_close(self) -> None:
        """No extra hardware/state beyond what close() already handles."""

    def _setup_verify_window(self) -> None:
        """Configure window for post-sick-day workout verification."""
        self._setup_aux_window(min_width=600, min_height=400)

    def _setup_demo_close_button(self) -> None:
        """Add close button for demo mode."""
        close_btn = tk.Button(
            self.root,
            text="✕ Close Demo",
            font=self._colors.font("caption"),
            bg=self._colors.danger,
            fg=self._colors.on_fill,
            command=self.close,
            cursor="hand2",
        )
        close_btn.place(x=10, y=10)

    def _setup_relaxed_day_window(self) -> None:
        """Configure a small non-locking window for the optional Tue-Thu prompt."""
        self._setup_aux_window(min_width=700, min_height=450)

    def _setup_aux_window(self, *, min_width: int, min_height: int) -> None:
        """Configure a non-locking window that grows to fit its own content.

        These two windows used to hardcode ``geometry("600x400")`` and
        ``geometry("700x450")``. Both were too small for what they display: the
        relaxed-day prompt's own button row requests **862px** against a 700px
        window, so it was sheared at *both* edges -- centred content clipped
        symmetrically, exactly as on the lock surfaces, and pre-dating the
        keyboard work by a wide margin (Tk's default focus ring accounts for
        4px of it).

        So the size is left to Tk (``geometry("")`` means "fit the content") with
        the old values kept only as a *minimum*, and clamped to the display so a
        wide screen's content cannot push the window off-screen. Content that
        still does not fit scrolls, because ``_ensure_container`` wraps these
        windows in a viewport too.
        """
        self.root.configure(bg=self._colors.bg, cursor="arrow")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        # "" hands sizing back to the geometry manager instead of pinning it.
        self.root.geometry("")
        self.root.minsize(
            min(min_width, self.root.winfo_screenwidth()),
            min(min_height, self.root.winfo_screenheight()),
        )
        self.root.maxsize(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
