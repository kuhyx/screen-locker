## Shared gatelock library

`~/utils/gatelock` is **not** its own git repo — `git -C ~/utils/gatelock
rev-parse --show-toplevel` resolves to `/home/kuhy/utils`, so it's a
subdirectory of the `~/utils` monorepo. Per audit scope, gatelock itself was
not walked against all 28 rules and no separate
`~/utils/gatelock/DESIGN_AUDIT_TODO.md` was written.

What's relevant here: gatelock defines exactly **one** real design token —
`LockConfig.bg: str = "#1a1a1a"` (`~/utils/gatelock/gatelock/_window.py:71`),
applied via `self.root.configure(bg=self._config.bg, ...)` in
`LockWindow.setup()` (`_window.py:143`). Both consumer repos re-hardcode
this same literal instead of reading it back off their own `LockConfig`
instance:

- **screen-locker** (this repo) — `#1a1a1a` appears 31 times across 9 files
  (see the Tkinter section above) despite `screen_lock.py:148-153`
  constructing a `LockConfig` instance (as `config`) just a few lines above
  each of those files' widget-creation call sites.
- **diet-guard** — not inspected as part of this audit (out of scope for
  this repo's report), but per the shared-infra note in the task, it is the
  other known consumer of `LockConfig`/`LockWindow` and should be checked
  for the same duplication pattern if/when a design audit is run there.

Fixing the screen-locker Rule 4 finding above by having widget-creation code
read `self._lock_config.bg` (threaded through from the `LockConfig` already
built in `ScreenLocker.__init__`) instead of re-typing `"#1a1a1a"` would
close this loop without needing any gatelock-side change.
