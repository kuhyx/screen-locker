"""Presenting N per-monitor surfaces as if they were one container.

Since gatelock v0.2.0 the lock builds one window per live output, so every
widget the locker paints has to exist once per monitor. The rest of this
package is written against a single ``self.container``, and building the
screen is not a pure function here -- ``_ui_flows`` records workouts, credits
weeks and branches on state while it paints -- so re-running a flow once per
surface would double those side effects.

The fan-out therefore happens at the widget factory instead. A flow body runs
exactly once; each widget it asks for is created N times and handed back as a
proxy that mirrors later ``configure`` calls to every copy. Nesting works the
same way: a frame group can be the parent of another group, so
``_button_row()`` still reads like it returns one frame.

The degenerate case matters as much as the general one. The status window,
the post-sick-day verify window and the relaxed-day prompt are ordinary
single windows with no lock and no surfaces; they build a group of exactly
one frame and every call site below behaves as it always did.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator


class WidgetGroup:
    """One logical widget, mirrored onto every monitor.

    Only the operations the locker actually performs after creation are
    exposed. Anything reading a value back (``winfo_*``, ``get``) answers
    from the first copy, since all copies are built identically.
    """

    def __init__(self, widgets: list[Any]) -> None:
        """Wrap the per-monitor copies of one widget."""
        self._widgets = widgets

    def __iter__(self) -> Iterator[Any]:
        """Iterate the per-monitor copies, for callers that need each one."""
        return iter(self._widgets)

    @property
    def first(self) -> Any:
        """The primary monitor's copy, for reads that cannot fan out."""
        return self._widgets[0]

    def configure(self, **kwargs: Any) -> None:
        """Apply the same configuration to every copy."""
        for widget in self._widgets:
            with contextlib.suppress(tk.TclError):
                widget.configure(**kwargs)

    # Tk's own alias; several call sites here use the short spelling.
    config = configure

    def pack(self, **kwargs: Any) -> None:
        """Pack every copy with the same options."""
        for widget in self._widgets:
            with contextlib.suppress(tk.TclError):
                widget.pack(**kwargs)

    def pack_forget(self) -> None:
        """Unpack every copy."""
        for widget in self._widgets:
            with contextlib.suppress(tk.TclError):
                widget.pack_forget()

    def destroy(self) -> None:
        """Destroy every copy."""
        for widget in self._widgets:
            with contextlib.suppress(tk.TclError):
                widget.destroy()


class TextGroup(WidgetGroup):
    """A multi-line text box, mirrored onto every monitor.

    Entries can share a ``StringVar`` and so are typed once for all screens.
    ``tk.Text`` has no such variable, so the copies genuinely diverge: the
    user types into exactly one of them, whichever screen they are looking
    at. Reading therefore returns the first copy with anything in it, which
    keeps the "answer on any monitor" property the per-output lock exists
    for. Falls back to the primary's (empty) content so callers still get a
    string to validate and reject.
    """

    def get(self, start: str, end: str) -> str:
        """Return the content of whichever copy was actually typed into."""
        for widget in self._widgets:
            with contextlib.suppress(tk.TclError):
                content = widget.get(start, end)
                if content.strip():
                    return str(content)
        return str(self._widgets[0].get(start, end))


class FrameGroup(WidgetGroup):
    """A container, mirrored onto every monitor, that can parent more groups.

    This is what makes the incremental widget factory in ``UIWidgetsMixin``
    work unchanged: ``_button_row()`` returns a ``FrameGroup``, and passing
    it to ``_button()`` creates one button inside each of its frames.
    """

    def __init__(self, widgets: list[Any]) -> None:
        """Wrap the per-monitor frames, tracking which output each came from."""
        super().__init__(widgets)
        self._outputs: list[str] = []

    @classmethod
    def single(cls, parent: tk.Misc, **kwargs: Any) -> FrameGroup:
        """Build a group of exactly one centred frame, for non-lock windows."""
        frame = tk.Frame(parent, **kwargs)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        return cls([frame])

    @property
    def surfaces(self) -> list[Any]:
        """Every per-monitor frame; empty until the lock builds them."""
        return list(self._widgets)

    def add(self, frame: Any, output_name: str) -> None:
        """Register the frame built for one newly-live output."""
        self._widgets.append(frame)
        self._outputs.append(output_name)

    def discard(self, output_name: str) -> None:
        """Forget the frame for an output that went dark."""
        kept = [
            (frame, name)
            for frame, name in zip(self._widgets, self._outputs, strict=True)
            if name != output_name
        ]
        self._widgets = [frame for frame, _ in kept]
        self._outputs = [name for _, name in kept]

    def child_frame(self, **kwargs: Any) -> FrameGroup:
        """Create one child frame inside every copy."""
        return FrameGroup([tk.Frame(frame, **kwargs) for frame in self._widgets])

    def child_widgets(self, factory: Any, **kwargs: Any) -> WidgetGroup:
        """Create one ``factory(parent, **kwargs)`` widget inside every copy."""
        return WidgetGroup([factory(frame, **kwargs) for frame in self._widgets])

    def clear(self) -> None:
        """Destroy every child of every copy."""
        for frame in self._widgets:
            with contextlib.suppress(tk.TclError):
                for child in frame.winfo_children():
                    child.destroy()

    def winfo_toplevel(self) -> Any:
        """The primary monitor's toplevel.

        A dialog that needs *a* window to sit relative to gets the primary
        one; there is no meaningful "the" toplevel across N monitors.
        """
        return self._widgets[0].winfo_toplevel()

    def winfo_children(self) -> list[Any]:
        """Children of the primary copy, for tests and geometry queries."""
        return list(self._widgets[0].winfo_children())
