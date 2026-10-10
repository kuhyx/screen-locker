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
            "_poke_credit.EXTRA_BENEFITS_FILE",
            "_status.EXTRA_BENEFITS_FILE",
        ),
    ),
    # Pushed to the shared sync store on every tick; a test that wrote here
    # would tombstone a real workout on the phone.
    (
        "sync_tombstones.json",
        (
            "_constants.SYNC_TOMBSTONES_FILE",
            "_sync_tombstones.SYNC_TOMBSTONES_FILE",
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
    # The durable lock-decision trail. Written on EVERY locker run, so without
    # this the suite would append test decisions to the user's real
    # enforcement history in ~/.local/share/screen_locker/.
    # BOTH bindings: _decision_trail owns the writer and reads its own
    # module global, so patching only _decision_log would silently let
    # the suite write into the real enforcement history.
    (
        "decisions.jsonl",
        (
            "_decision_log.DECISION_LOG_FILE",
            "_decision_trail.DECISION_LOG_FILE",
        ),
    ),
    # Written whenever a locker run waits in gatelock's queue.
    (
        "queue_state.json",
        ("_constants.QUEUE_STATE_FILE", "_queue_state.QUEUE_STATE_FILE"),
    ),
    # Real $XDG_RUNTIME_DIR/gatelock file; unisolated, only the first test in
    # the whole suite would win it, since it is shared across all of them.
    (
        "instance.lock",
        ("_constants.INSTANCE_LOCK_FILE", "screen_lock.INSTANCE_LOCK_FILE"),
    ),
    # The home every earner's ledger (leetcode-guard's, book-guard's, ...) is
    # resolved under. Read-only from here, but a test must never see the
    # user's real credits: one would earn a fake shutdown hour inside an
    # assertion written against an empty day.
    (
        "ledger_home",
        ("_earned.LEDGER_HOME",),
    ),
    # The key those ledgers are verified with, as ``_earned`` binds it. Absent
    # by default, so a read no test asked for fails closed instead of using
    # the host's real key; earner tests write their own (_earned_fixtures).
    (
        "earned_hmac.key",
        ("_earned.HMAC_KEY_FILE",),
    ),
    # Declared rest days: read by every workout credit and every reset, so an
    # unredirected test would see the user's real rest days.
    (
        "rest_days.json",
        ("_constants.REST_DAY_FILE", "_rest_day.REST_DAY_FILE"),
    ),
    # Today's grace-floor lift; every shutdown add reads and writes it.
    (
        "grace_floor.json",
        ("_constants.GRACE_STATE_FILE", "_grace_floor.GRACE_STATE_FILE"),
    ),
    # wake-alarm's workday-stick file. A test that forgot this would read
    # the developer's real penalty state.
    (
        "workday_penalty.json",
        ("_constants.WORKDAY_PENALTY_FILE", "_workday_penalty.WORKDAY_PENALTY_FILE"),
    ),
)
