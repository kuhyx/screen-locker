"""Maintenance and verification scripts for screen-locker.

A real package rather than a loose directory, so the shared helpers split out
of the verification gates (``_xvfb_reexec``, ``_popup_form_check``) are
importable as ``scripts.<name>``.

Both invocation styles still work and both are used:

* ``python3 -m scripts.verify_screen_fits`` -- pre-commit
* ``python3 scripts/verify_lock_popup_safety.py`` -- CI

The second puts ``scripts/`` itself on ``sys.path`` instead of the repo root,
so the gates that import a sibling try the package-qualified name first and
fall back to the bare one.
"""
