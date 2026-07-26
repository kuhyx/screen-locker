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

from gatelock import RANK_SCREEN_LOCKER, Arbiter, LockWindow

from screen_locker._surface_group import FrameGroup

if TYPE_CHECKING:
    from gatelock import SurfaceInfo


class WindowSetupMixin:
    """Mixin providing the screen-locker-specific auxiliary windows."""

    # Declared because this mixin both reads and *reassigns* it; without the
    # annotation mypy cannot infer the attribute's type through the mixin.
    container: FrameGroup

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
        """Give the non-lock windows a container group of exactly one.

        The verify and relaxed-day windows never build a lock, so nothing
        called ``build_surface`` and the group is still empty. They are
        ordinary single windows, and one frame is all they need.
        """
        if not self.container.surfaces:
            self.container = FrameGroup.single(self.root, bg=self._colors.bg)

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """Add one centred container for a newly-live output.

        Only the container is built here, not the screen inside it: which
        screen is showing depends on flow state the lock knows nothing
        about, so the caller repaints through the usual flow entry point
        once the surface exists.
        """
        frame = tk.Frame(parent, bg=self._colors.bg)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        self.container.add(frame, surface.output_name)

    def teardown_surface(self, surface: SurfaceInfo) -> None:
        """Forget the container for an output that went dark."""
        self.container.discard(surface.output_name)

    def on_focus_ready(self, surface: SurfaceInfo | None) -> None:
        """Nothing to focus yet: the lock's first screen has no input field.

        This fires once, when the lock is mapped and grabbed, and at that
        moment the screen is the phone-check status -- buttons only. The
        screens that DO take typed input (the manual-workout form, the sick
        dialog) are painted later, in response to a button, so each focuses
        its own first field as it is built rather than relying on this hook.

        ``surface`` is None when no output is live at all -- the lock is
        held with nothing to show, which is still a valid state.
        """

    def on_callback_error(self) -> None:
        """Surfaced via GateRoot's logging already; no extra action yet."""

    def on_close(self) -> None:
        """No extra hardware/state beyond what close() already handles."""

    def _setup_verify_window(self) -> None:
        """Configure window for post-sick-day workout verification."""
        self.root.geometry("600x400")
        self.root.configure(bg=self._colors.bg, cursor="arrow")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _setup_demo_close_button(self) -> None:
        """Add close button for demo mode."""
        close_btn = tk.Button(
            self.root,
            text="✕ Close Demo",
            font=(self._colors.font_family, 12),
            bg=self._colors.danger,
            fg=self._colors.on_fill,
            command=self.close,
            cursor="hand2",
        )
        close_btn.place(x=10, y=10)

    def _setup_relaxed_day_window(self) -> None:
        """Configure a small non-locking window for the optional Tue-Thu prompt."""
        self.root.geometry("700x450")
        self.root.configure(bg=self._colors.bg, cursor="arrow")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
