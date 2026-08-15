"""UI widget helper methods mixin for the screen locker."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import bind_activate

from screen_locker._ui_form_fields import UIFormFieldsMixin, disable_paste

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import SpaceStep, TypeRole

    from screen_locker._surface_group import FrameGroup, WidgetGroup

# disable_paste moved to _ui_form_fields with the fields that use it; it is
# re-exported here because _manual_workout_widgets and _sick_dialog import it
# from this module.
__all__ = ["UIWidgetsMixin", "disable_paste"]


class UIWidgetsMixin(UIFormFieldsMixin):
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
        role: TypeRole = "display",
        scale: float = 1.0,
        color: str | None = None,
        pad: SpaceStep = "md",
    ) -> WidgetGroup:
        """Create and pack a bold label on every monitor.

        ``role``/``pad`` name a design-system token instead of a pixel count.
        That is what makes a screen shrink on a short display: the tokens are
        compacted per screen height (``gatelock._density``), and a raw literal
        is not. It also fixes the unit bug the literals carried -- Tk reads a
        positive size as *points*, so ``36`` rendered ~37% larger than the
        36px it was meant to be, on every screen.

        ``scale`` is for deliberate emphasis (a hero countdown), kept explicit
        so an outlier is visible rather than hidden behind a fresh literal.
        """
        label = self.container.child_widgets(
            tk.Label,
            text=text,
            font=self._colors.font(role, bold=True, scale=scale),
            fg=color or self._colors.fg,
            bg=self._colors.bg,
        )
        label.pack(pady=self._colors.space(pad))
        return label

    def _text(
        self,
        text: str,
        *,
        role: TypeRole = "body",
        scale: float = 1.0,
        color: str | None = None,
        pad: SpaceStep = "sm",
    ) -> WidgetGroup:
        """Create and pack a non-bold text label on every monitor.

        See :meth:`_label` for why these are token names, not pixel counts.
        """
        label = self.container.child_widgets(
            tk.Label,
            text=text,
            font=self._colors.font(role, scale=scale),
            fg=color or self._colors.fg,
            bg=self._colors.bg,
        )
        label.pack(pady=self._colors.space(pad))
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
            font=self._colors.font("title", bold=True),
            bg=bg,
            fg=self._fg_for(bg),
            width=width,
            command=command,
            cursor="hand2" if self.demo_mode else "",
            relief="flat",
            padx=self._colors.space("lg"),
            pady=self._colors.space("sm"),
            **self._colors.focus_kwargs(),
        )
        # Every per-monitor copy, not just `.first` -- one flow paints N screens
        # and the user may be looking at any of them.
        for button in buttons:
            bind_activate(button)
        return buttons

    def _button_row(self) -> FrameGroup:
        """Create and pack a horizontal button container on every monitor.

        The gap is "sm" rather than "md" because this row is the last thing
        on every screen: the pixels it spends are the ones the manual-workout
        form has left over on a 1024x600 panel.
        """
        frame = self.container.child_frame(bg=self._colors.bg)
        frame.pack(pady=self._colors.space("sm"))
        return frame
