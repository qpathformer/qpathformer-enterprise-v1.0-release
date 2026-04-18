# Path 2 Commands

Run from:

```powershell
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 -c "import sys; print(sys.executable)"
```

Path summary:

- Path 2 turns an Access-Mode `ID_3` freeze or a contained runtime signal into a governed candidate package, moves it through `STATE_2`, and can optionally build a controlled `STATE_1` training package plus a local LoRA validation run.
- each command file now covers one end-to-end route only

Release v1.0 note:

- the current `01_source` example bundle for the source-first route is already populated in `C:\v1.0-qpathformer_enterprise`
- use the shipped release examples first unless you are intentionally swapping to a new source freeze or runtime session

Current release examples:

- source-first example:
  `path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z`
- runtime-only example root:
  `path_2_access_mode_canonical\02_signals\runtime_generated`

Use exactly one of these command files per run:

1. `docs\execution\path_2_access_mode_canonical_source_first_commands.md`
   This is the release-default route. Start from the populated `ID_3` freeze bundle in `01_source`.
2. `docs\execution\path_2_access_mode_canonical_runtime_signal_commands.md`
    Use this when you want the `gpt-oss:20b` runtime signal route instead of the source freeze route.
    After runtime export, set the session-specific candidate root and resolve `$Path2PackageDir` before starting review.

Recommended release default:

- use the source-first file for the main v1.0 validation pass
- use the runtime-only file for controlled signal-routing and partial lifecycle checks
