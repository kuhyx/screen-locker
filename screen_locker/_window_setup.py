"""Auxiliary (non-lock) window setup for ScreenLocker.

The fullscreen lock-window mechanics (overrideredirect, input grab,
VT-disable) now live in the shared ``gatelock`` package. This module keeps
only the screen-locker-specific windows that are never the lock itself: the
post-sick-day verification window, the demo close button, and the optional
relaxed-day prompt.
"""

from __future__ import annotations

import tkinter as tk


class WindowSetupMixin:
    """Mixin providing the screen-locker-specific auxiliary windows."""

    def on_focus_ready(self) -> None:
        """No typed-input field in the lock window; nothing to focus."""

    def on_callback_error(self) -> None:
        """Surfaced via GateRoot's logging already; no extra action yet."""

    def on_close(self) -> None:
        """No extra hardware/state beyond what close() already handles."""

    def _setup_verify_window(self) -> None:
        """Configure window for post-sick-day workout verification."""
        self.root.geometry("600x400")
        self.root.configure(bg="#1a1a1a", cursor="arrow")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _setup_demo_close_button(self) -> None:
        """Add close button for demo mode."""
        close_btn = tk.Button(
            self.root,
            text="✕ Close Demo",
            font=("Arial", 12),
            bg="#ff4444",
            fg="white",
            command=self.close,
            cursor="hand2",
        )
        close_btn.place(x=10, y=10)

    def _setup_relaxed_day_window(self) -> None:
        """Configure a small non-locking window for the optional Tue-Thu prompt."""
        self.root.geometry("700x450")
        self.root.configure(bg="#1a1a1a", cursor="arrow")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
