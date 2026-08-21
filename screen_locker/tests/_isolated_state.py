"""On-disk state paths every test must redirect away from the real files.

Split out of ``conftest.py`` (250-line cap) -- the *fixture* itself has to
stay in ``conftest.py`` (pytest only applies autouse fixtures declared
there), but this static table has no such constraint.
"""

from __future__ import annotations

# Each on-disk state path, and every module that bound it by value at import
# time. All of them need patching, not just the _constants source -- a missed
# binding lets a test write to the real file.
ISOLATED_STATE: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "sick_history.json",
        ("_sick_tracker.SICK_HISTORY_FILE", "_constants.SICK_HISTORY_FILE"),
    ),
    (
        "early_bird_pending.json",
        (
            "_early_bird.EARLY_BIRD_PENDING_FILE",
            "_constants.EARLY_BIRD_PENDING_FILE",
        ),
    ),
    (
        "extra_benefits_state.json",
        (
            "_constants.EXTRA_BENEFITS_FILE",
            "_startup_checks.EXTRA_BENEFITS_FILE",
            "_sync_mixin.EXTRA_BENEFITS_FILE",
            "_early_bird.EXTRA_BENEFITS_FILE",
            "_status.EXTRA_BENEFITS_FILE",
        ),
    ),
    (
        "sick_day_state.json",
        (
            "_constants.SICK_DAY_STATE_FILE",
            "_startup_checks.SICK_DAY_STATE_FILE",
            "_shutdown_sick_state.SICK_DAY_STATE_FILE",
        ),
    ),
    ("scheduled_skips.json", ("_log_mixin.SCHEDULED_SKIPS_FILE",)),
    # The durable lock-decision trail. Written on EVERY locker run, so without
    # this the suite would append test decisions to the user's real
    # enforcement history in ~/.local/share/screen_locker/.
    ("decisions.jsonl", ("_decision_log.DECISION_LOG_FILE",)),
    # Real $XDG_RUNTIME_DIR/gatelock file; unisolated, only the first test in
    # the whole suite would win it, since it is shared across all of them.
    (
        "instance.lock",
        ("_constants.INSTANCE_LOCK_FILE", "screen_lock.INSTANCE_LOCK_FILE"),
    ),
)
