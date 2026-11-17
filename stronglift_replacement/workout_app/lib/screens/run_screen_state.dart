// The run screen's state: the controller's life, the finish modal, "new run".
part of 'run_screen.dart';

class _RunScreenState extends State<RunScreen> with WidgetsBindingObserver {
  late RunController _controller = _build();
  late final RunUploader _uploader = widget.uploader ?? RunUploader.instance;
  late final PaceTargetStore _paceStore =
      widget.paceStore ?? PrefsPaceTargetStore();
  bool _starting = false;
  bool _paceOn = false;
  bool _asking = false;
  int _paceTarget = kDefaultPaceTarget;

  RunController _build() =>
      (widget.controllerFactory ?? RunScreen.defaultControllerFactory!)();

  @override
  void initState() {
    super.initState();
    SandboxLog.event('open run');
    WidgetsBinding.instance.addObserver(this);
    _wire(_controller);
    unawaited(_controller.watchIdle());
    unawaited(_loadPaceTarget());
    // So the badge shows the real queue, not the pre-first-pass default.
    unawaited(_uploader.uploadPending());
  }

  /// Hears the host, so a notification tap or a started run reaches the
  /// screen; asks it where the run stands.
  void _wire(RunController c) {
    c.addListener(_onControllerChanged);
    unawaited(c.attach());
  }

  /// The notification asked for the finish modal: show it once.
  void _onControllerChanged() {
    if (_controller.view.promptFinish && !_asking && mounted) {
      unawaited(_askFinish());
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller
      ..removeListener(_onControllerChanged)
      // Hangs up only: the run is in the host and goes on.
      ..dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // A silent re-check: the permission prompt itself backgrounds the app, so
    // asking again here would loop.
    if (state == AppLifecycleState.resumed) {
      unawaited(_controller.recheckAccess());
    }
  }

  Future<void> _loadPaceTarget() async {
    final stored = await _paceStore.load();
    if (mounted) setState(() => _paceTarget = stored);
  }

  void _setPaceTarget(int seconds) {
    setState(() => _paceTarget = seconds);
    unawaited(_paceStore.save(seconds));
  }

  Future<void> _start() async {
    setState(() => _starting = true);
    try {
      await _controller.start(paceTarget: _paceOn ? _paceTarget : null);
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  /// The one way a run ends: the confirm modal's red check.
  Future<void> _askFinish() async {
    if (_asking) return;
    _asking = true;
    try {
      if (_controller.view.promptFinish) _controller.ackPrompt();
      final end = await showRunFinishDialog(context);
      if (end && mounted) await _controller.finish();
    } finally {
      _asking = false;
    }
  }

  void _again() {
    final old = _controller..removeListener(_onControllerChanged);
    setState(() => _controller = _build());
    _wire(_controller);
    unawaited(_controller.watchIdle());
    // Hangs up the old link; a run still going in the host is untouched.
    old.dispose();
  }

  /// Fixable refusals open the system settings; a plain denial asks again.
  VoidCallback? _issueTap(RunIssue issue) => switch (issue) {
    RunIssue.deniedForever ||
    RunIssue.serviceOff => () => unawaited(widget.openSettings()),
    RunIssue.denied => () => unawaited(_controller.watchIdle()),
    _ => null,
  };

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, _) {
      final c = _controller;
      final v = c.view;
      final blocked = c.blocked;
      final issue = _IssueButton(
        issue: v.issue,
        onTap: _issueTap(v.issue),
        size: blocked ? 96 : 24,
      );
      return PopScope(
        // The run lives in the host, but the screen still refuses to be left
        // while one is going (or while a resumed one has not shown up yet).
        canPop: !c.active && !(widget.resuming && !c.attachGaveUp && !v.synced),
        child: Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                children: [
                  _StatusRow(
                    controller: c,
                    uploader: _uploader,
                    issue: blocked ? null : issue,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  if (blocked)
                    Expanded(child: Center(child: issue))
                  else ...[
                    Expanded(
                      flex: 4,
                      child: KeyedSubtree(
                        key: ObjectKey(c),
                        child: (widget.mapBuilder ?? _defaultMap)(
                          context,
                          v.livePoints,
                          c.position,
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Expanded(flex: 3, child: _Numbers(view: v)),
                    const SizedBox(height: AppSpacing.md),
                    _Controls(
                      controller: c,
                      starting: _starting,
                      paceOn: _paceOn,
                      paceTarget: _paceTarget,
                      onPaceToggle: () => setState(() => _paceOn = !_paceOn),
                      onPaceChanged: _setPaceTarget,
                      onStart: () => unawaited(_start()),
                      onFinish: () => unawaited(_askFinish()),
                      onAgain: _again,
                      onClose: () => Navigator.of(context).maybePop(),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
    },
  );
}
