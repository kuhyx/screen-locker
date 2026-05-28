"""Window configuration and input-grab helpers for ScreenLocker."""

from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
import tkinter as tk

_logger = logging.getLogger(__name__)


class WindowSetupMixin:
    """Mixin providing window setup, VT switching control, and input-grab helpers."""

    def _disable_vt_switching(self) -> None:
        """Disable VT switching in X11 while the lock is active.

        Prevents bypassing the lock by switching to a TTY with Ctrl+Alt+Fn.
        Best-effort: silently ignored if setxkbmap is unavailable.
        """
        setxkbmap = shutil.which("setxkbmap")
        if setxkbmap is None:
            _logger.warning("setxkbmap not found; VT switching will not be disabled")
            return
        subprocess.run([setxkbmap, "-option", "srvrkeys:none"], check=False)

    def _restore_vt_switching(self) -> None:
        """Restore VT switching after the lock is dismissed."""
        setxkbmap = shutil.which("setxkbmap")
        if setxkbmap is None:
            return
        subprocess.run([setxkbmap, "-option", ""], check=False)

    def _setup_window(self) -> None:
        """Configure the window for fullscreen lock."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.overrideredirect(boolean=True)
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.root.attributes(fullscreen=True)
        self.root.attributes(topmost=True)
        self.root.configure(bg="#1a1a1a", cursor="arrow")
        if not self.demo_mode:
            self._disable_vt_switching()

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

    def _grab_input(self) -> None:
        """Force input focus to the locker window."""
        self.root.update_idletasks()
        self.root.focus_force()
        if self.demo_mode:
            with contextlib.suppress(tk.TclError):
                self.root.grab_set()
        else:
            try:
                self.root.grab_set_global()
            except tk.TclError:
                _logger.warning("Global grab failed, falling back to local grab")
                with contextlib.suppress(tk.TclError):
                    self.root.grab_set()
