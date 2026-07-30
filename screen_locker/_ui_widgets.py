"""UI widget helper methods mixin for the screen locker."""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import bind_activate, escape_text_tab_trap

if TYPE_CHECKING:
    from collections.abc import Callable

    from screen_locker._surface_group import FrameGroup, WidgetGroup


def disable_paste(widget: tk.Widget) -> None:
    """Disable paste in a Tk Entry/Text widget.

    Friction-only: a determined user can still bypass via xdotool, but the
    point is removing the trivial Ctrl+V shortcut so the user must
    actually type their input.
    """
    for sequence in ("<<Paste>>", "<Control-v>", "<Control-V>", "<Button-2>"):
        with contextlib.suppress(tk.TclError, AttributeError):
            widget.bind(sequence, lambda _e: "break")


class UIWidgetsMixin:
    """Mixin providing low-level widget creation helpers."""

    def clear_container(self) -> None:
        """Remove all widgets from the main container, on every monitor.

        Also schedules the surface viewports to re-settle once the new screen
        has been painted. Every repaint in the app starts by calling this, so
        hooking it here is what makes focus-following and scroll-reset
        unforgettable -- there are ~19 repaint sites, and "remember to call
        settle after painting" is a rule that would eventually be missed, on a
        lock where a missed re-arm means unreachable content.

        ``after_idle`` is what defers the work until *after* the caller has
        finished building widgets; running it inline here would settle an empty
        container. Repeated calls within one repaint coalesce harmlessly.
        """
        self.container.clear()
        settle = getattr(self, "settle_surfaces", None)
        if settle is not None:
            self.root.after_idle(settle)

    def _label(
        self,
        text: str,
        *,
        font_size: int = 36,
        color: str | None = None,
        pady: int = 20,
    ) -> WidgetGroup:
        """Create and pack a bold label on every monitor."""
        label = self.container.child_widgets(
            tk.Label,
            text=text,
            font=(self._colors.font_family, font_size, "bold"),
            fg=color or self._colors.fg,
            bg=self._colors.bg,
        )
        label.pack(pady=pady)
        return label

    def _text(
        self,
        text: str,
        *,
        font_size: int = 18,
        color: str | None = None,
        pady: int = 10,
    ) -> WidgetGroup:
        """Create and pack a non-bold text label on every monitor."""
        label = self.container.child_widgets(
            tk.Label,
            text=text,
            font=(self._colors.font_family, font_size),
            fg=color or self._colors.fg,
            bg=self._colors.bg,
        )
        label.pack(pady=pady)
        return label

    def _fg_for(self, bg: str) -> str:
        """Return the correct label color for a widget with background `bg`.

        The four filled semantic surfaces (accent/success/warning/danger)
        all sit in the same mid-light lightness band, so `fg` (near-white,
        meant for the neutral `bg`/`field_bg` surfaces) under-contrasts on
        every one of them -- `on_fill` (dark) is required instead. Deriving
        this from `bg` means a new filled-button call site can't reintroduce
        the bug by omission.
        """
        fills = {
            self._colors.accent,
            self._colors.success,
            self._colors.warning,
            self._colors.danger,
        }
        return self._colors.on_fill if bg in fills else self._colors.fg

    def _button(
        self,
        parent: FrameGroup,
        text: str,
        *,
        bg: str,
        command: Callable[[], None],
        width: int = 10,
    ) -> WidgetGroup:
        """Create a styled button on every monitor (caller must pack).

        Every copy gets the *same* ``command``, so pressing the button on
        whichever screen the user is actually looking at does the one thing
        once -- the same trick the shared entry variable plays for typing.

        Padding follows the shared 2x horizontal:vertical ratio (rule 22);
        `relief="flat"` is the one depth technique every button in the app
        uses now (rule 27), matching what `_heat_skip.py` already did alone.

        Two keyboard properties are wired here rather than per call site, so a
        new button cannot omit them:

        * A **visible focus ring** (`focus_kwargs`). Tk's default is a 1px
          *black* ring, which on ``bg`` (#211D1B) is invisible -- and
          `relief="flat"` removes the depth cue too, so an unringed button
          gives a keyboard user no indication of where they are.
        * **Enter activates.** Tk's X11 class bindings give ``Button`` only
          ``<space>``; there is no ``<Return>`` binding at all. Under a global
          grab with no pointer, "the obvious key does nothing" is the
          difference between satisfying the lock and being stuck at it.
        """
        buttons = parent.child_widgets(
            tk.Button,
            text=text,
            font=(self._colors.font_family, 24, "bold"),
            bg=bg,
            fg=self._fg_for(bg),
            width=width,
            command=command,
            cursor="hand2" if self.demo_mode else "",
            relief="flat",
            padx=24,
            pady=12,
            **self._colors.focus_kwargs(),
        )
        # Every per-monitor copy, not just `.first` -- one flow paints N screens
        # and the user may be looking at any of them.
        for button in buttons:
            bind_activate(button)
        return buttons

    def _button_row(self) -> FrameGroup:
        """Create and pack a horizontal button container on every monitor."""
        frame = self.container.child_frame(bg=self._colors.bg)
        frame.pack(pady=20)
        return frame

    def _add_label_entry(
        self,
        parent: FrameGroup,
        *,
        label: str,
        variable: tk.StringVar,
        focus: bool = False,
    ) -> None:
        """Add a label + single-line entry pair on every monitor.

        All copies share one ``variable``, so typing on any screen is the
        same text everywhere and reading it back needs no idea which monitor
        the user actually used.

        ``focus`` gives the primary surface's copy the keyboard focus. Exactly
        one field per screen should ask: the lock takes a global grab, so with
        nothing focused the user's typing goes nowhere and there is no other
        window on screen to make that obvious.
        """
        row = parent.child_frame(bg=self._colors.bg)
        row.pack(pady=8, fill="x")
        row.child_widgets(
            tk.Label,
            text=label,
            font=(self._colors.font_family, 14),
            fg=self._colors.fg,
            bg=self._colors.bg,
            anchor="w",
        ).pack(side="top", anchor="w")
        entries = row.child_widgets(
            tk.Entry,
            textvariable=variable,
            width=50,
            font=(self._colors.font_family, 14),
            bg=self._colors.field_bg,
            fg=self._colors.fg,
            insertbackground=self._colors.fg,
            **self._colors.focus_kwargs(),
        )
        entries.pack(side="top", anchor="w", pady=4)
        for entry in entries:
            disable_paste(entry)
        if focus:
            entries.first.focus_set()

    def _add_label_text(
        self,
        parent: FrameGroup,
        *,
        label: str,
        height: int = 4,
    ) -> WidgetGroup:
        """Add a label + multi-line ``Text`` pair on every monitor.

        Use this instead of building a bare ``tk.Text``: it un-traps Tab.
        Tk makes ``<Tab>`` insert a literal tab and refocus the widget, and
        binds ``<Shift-Tab>`` to nothing, so an untreated multi-line field is a
        keyboard dead end whose only exits (``Ctrl+Tab``/``Ctrl+Shift+Tab``) are
        not advertised anywhere. On a lock surface that means a user who tabs
        into it can never reach the submit button.
        """
        row = parent.child_frame(bg=self._colors.bg)
        row.pack(pady=8, fill="x")
        row.child_widgets(
            tk.Label,
            text=label,
            font=(self._colors.font_family, 14),
            fg=self._colors.fg,
            bg=self._colors.bg,
            anchor="w",
        ).pack(side="top", anchor="w")
        boxes = row.child_widgets(
            tk.Text,
            width=60,
            height=height,
            wrap="word",
            font=(self._colors.font_family, 14),
            bg=self._colors.field_bg,
            fg=self._colors.fg,
            insertbackground=self._colors.fg,
            **self._colors.focus_kwargs(),
        )
        boxes.pack(side="top", anchor="w", pady=4)
        for box in boxes:
            disable_paste(box)
            escape_text_tab_trap(box)
        return boxes

    def _focus_first_button(self, row: FrameGroup) -> None:
        """Give the primary surface's first button keyboard focus.

        The lock takes a global grab and there is no other window on screen, so
        a surface that starts with *nothing* focused leaves the user pressing
        keys into the void with no visible ring to hint where focus went. The
        retry screen (TRY AGAIN / I'm sick / Log Manual Workout) had exactly
        that problem, because ``on_focus_ready`` is a documented no-op.
        """
        for child in row.first.winfo_children():
            if child.winfo_class() == "Button":
                child.focus_set()
                return
