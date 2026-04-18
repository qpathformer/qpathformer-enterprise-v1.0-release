# Path 2 Source-First Commands

Run from:

```powershell
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 -c "import sys; print(sys.executable)"
```

Path summary:

- This is the release-default Path 2 route.
- It starts with the completed Access-Mode `ID_3` freeze bundle already staged in `01_source`, bridges that bundle into governed Path 2 signals, exports a grouped candidate package, advances the package through review and promotion, and can optionally validate the training package with a local LoRA run.

Release v1.0 note:

- the current populated source example is already provided in `path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z`
- use that shipped freeze bundle for the current release validation unless you are intentionally testing a different freeze

Path 2 release shape:

- `01_source` holds the completed `ID_3` operator freeze bundle copied from Access-Mode
- `02_signals\source_bridge` is the repo-side bridge from frozen source artifacts into governed Path 2 signal records
- `03_dataset` holds candidate export, review, promotion, freeze, registry, and training-package outputs
- `05_runs` holds the optional local LoRA validation run

Important distinction:

- the `ID_3` source freeze in `01_source` is the canonical inspection bundle from Access-Mode
- the repo-side `STATE_1` freeze written later in `03_dataset\...\freeze` is a lifecycle artifact created after review, promotion, and handoff
- step 9 uses the repo-side `STATE_1` registry entry and frozen dataset, not the original `01_source` freeze folder directly

## Current release fast path

If you are running the current validated Path 2 source-first release, use these direct commands and keep one resolved package path plus one resolved dataset version all the way through the run.

Current release anchor paths:

- freeze root:
  `.\path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z`
- source bridge root:
  `.\path_2_access_mode_canonical\02_signals\source_bridge\2026-04-11--FREEZE-20260412-000400Z`
- candidate latest-root:
  `.\path_2_access_mode_canonical\03_dataset\candidates\session-run-id2-20260411-1400-qpath-tr008-run\QPDS-PACKAGE-ID2_PREP`
- training packages root:
  `.\path_2_access_mode_canonical\03_dataset\training_packages`

Current release startup block:

```powershell
$Path2FreezeRoot = '.\path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z'
$Path2BridgeRoot = '.\path_2_access_mode_canonical\02_signals\source_bridge\2026-04-11--FREEZE-20260412-000400Z'
$Path2CandidateLatestRoot = '.\path_2_access_mode_canonical\03_dataset\candidates\session-run-id2-20260411-1400-qpath-tr008-run\QPDS-PACKAGE-ID2_PREP'
$Path2TrainingPackagesRoot = '.\path_2_access_mode_canonical\03_dataset\training_packages'
```

Current release commands:

```powershell
py -3 .\scripts\build_path2_source_bridge_signals.py `
  --freeze-root .\path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z

py -3 .\scripts\export_candidates_v2.py `
  --input .\path_2_access_mode_canonical\02_signals\source_bridge\2026-04-11--FREEZE-20260412-000400Z `
  --require-routing-review `
  --output-root .\path_2_access_mode_canonical `
  --dataset-kind enterprise_structuring `
  --dataset-passport .\shared\runtime\signal_references\governance_reference\signal_dataset_passport_001.json

$Path2PackageDir = Get-ChildItem $Path2CandidateLatestRoot -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
$Path2DatasetVersion = Split-Path $Path2PackageDir -Leaf

py -3 .\scripts\run_state2_review.py `
  --package-dir $Path2PackageDir `
  --notes "Path 2 STATE_2 review from the three-path root"

py -3 .\scripts\run_state2_promotion.py `
  --package-dir $Path2PackageDir `
  --require-approved-review `
  --notes "Path 2 STATE_2 promotion check from the three-path root"

py -3 .\scripts\run_state1_handoff.py `
  --package-dir $Path2PackageDir `
  --require-approved-review `
  --require-approved-promotion `
  --notes "Path 2 STATE_1 handoff from the three-path root"

py -3 .\scripts\run_state1_freeze.py `
  --package-dir $Path2PackageDir `
  --require-approved-review `
  --require-approved-promotion `
  --require-approved-handoff `
  --require-freeze-ready `
  --notes "Path 2 STATE_1 freeze from the three-path root"

py -3 .\scripts\run_state1_registry_update.py `
  --package-dir $Path2PackageDir `
  --registry-path .\shared\registry\state1_dataset_registry.json `
  --require-approved-freeze `
  --require-state1 `
  --notes "Path 2 registry update from the three-path root"

py -3 .\scripts\run_training_state1.py `
  --dataset-version $Path2DatasetVersion `
  --registry-path .\shared\registry\state1_dataset_registry.json `
  --output-root .\path_2_access_mode_canonical\03_dataset\training_packages `
  --backend-profile .\shared\configs\training_backend_profile.local_lora.json

$Path2TrainingPackage = Join-Path $Path2TrainingPackagesRoot $Path2DatasetVersion

py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package $Path2TrainingPackage `
  --output-root .\path_2_access_mode_canonical\05_runs `
  --run-label path2_state1_run
```

Use this fast path unless you are intentionally changing freeze folders, candidate roots, or package targets.

## Optional helper mode

Dot-source the helper once if you want the current source-first Path 2 run to be copy-paste friendly.

```powershell
. .\scripts\path2_current_release_env.ps1
```

That helper sets these core values for the current release:

- `$Path2FreezeRoot`
- `$Path2BridgeRoot`
- `$Path2CandidateLatestRoot`
- `$Path2RuntimeSignalRoot`
- `$Path2RegistryPath`
- `$Path2BackendProfile`

These stay unresolved until after step 3:

- `$Path2PackageDir`
- `$Path2DatasetVersion`
- `$Path2TrainingPackage`

Those are created from the latest exported package later in the run, so they stay accurate.

If you already changed into the freeze folder under `01_source`, capture that folder first and then go back to the repo root before running the numbered steps:

```powershell
$Path2FreezeRoot = $PWD.Path
Set-Location "C:\v1.0-qpathformer_enterprise"
$Path2BridgeRoot = Join-Path ".\path_2_access_mode_canonical\02_signals\source_bridge" (Split-Path $Path2FreezeRoot -Leaf)
```

## Controlled note

- this source-driven Path 2 run remains a controlled reference path in the current release
- it does not by itself authorize unrestricted fine-tuning
- any step 9 or step 10 run should still be described as controlled local validation, not as a governance authorization outcome

## 0. Verify the completed `ID_3` freeze bundle in `01_source`

Directory check:

```powershell
Get-ChildItem .\path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z
```

Files you should see immediately:

- `hashes.txt`
- `ID3_FREEZE_NOTE.md`
- `session_baseline.canonical.json`
- `session_ambiguity.canonical.json`
- `session_lifecycleboundary.canonical.json`
- `session_timepressure.canonical.json`
- `module_03_baseline.canonical.json`
- `module_03_ambiguity.canonical.json`
- `module_03_lifecycleboundary.canonical.json`
- `module_03_timepressure.canonical.json`

## 1. Verify the imported `ID_3` freeze bundle metadata

If `$Path2FreezeRoot` is null in the current shell, dot-source the helper first:

```powershell
. .\scripts\path2_current_release_env.ps1
```

If you are already inside the freeze folder, you can also use:

```powershell
$Path2FreezeRoot = $PWD.Path
```

Directory check:

```powershell
Get-ChildItem $Path2FreezeRoot
```

Shared-session check:

```powershell
Get-ChildItem (Join-Path $Path2FreezeRoot "session_*.canonical.json") |
  ForEach-Object {
    $json = Get-Content $_.FullName -Raw | ConvertFrom-Json
    [pscustomobject]@{
      file = $_.Name
      session_id = $json.session.session_id
      created_utc = $json.session.created_utc
    }
  }
```

Hash check:

```powershell
Get-Content (Join-Path $Path2FreezeRoot "hashes.txt")
```

Important things to confirm:

- the freeze folder contains 8 canonical JSONs plus `hashes.txt` and `ID3_FREEZE_NOTE.md`
- all 4 session canonical files share the same normalized base `session_id`
- the `pack\` folder preserves the Access-Mode provenance structure

Created files at this stage:

- source freeze artifacts only
- no repo-side signal, candidate, or training files yet

## 2. Build bridged Path 2 signals from the frozen source bundle

```powershell
py -3 .\scripts\build_path2_source_bridge_signals.py `
  --freeze-root $Path2FreezeRoot
```

If you started inside the freeze folder, this is the safest handoff back to the repo root before running the bridge step:

```powershell
$Path2FreezeRoot = $PWD.Path
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 .\scripts\build_path2_source_bridge_signals.py `
  --freeze-root $Path2FreezeRoot
```

Check locations:

- `path_2_access_mode_canonical\02_signals\source_bridge\2026-04-11--FREEZE-20260412-000400Z\`

Created files:

- 4 `signal_path2_source_*.json`
- 4 `signal_path2_source_*.routing.json`

Important things to confirm:

- all 4 bridged records share the normalized `session_id`
- each bridged record has `routing_decision = SEND_TO_STATE_2_REVIEW`
- scenario labels are preserved:
  - `baseline`
  - `ambiguity`
  - `lifecycleboundary`
  - `timepressure`

## 3. Export candidate datasets from the bridged source signals

```powershell
py -3 .\scripts\export_candidates_v2.py `
  --input $Path2BridgeRoot `
  --require-routing-review `
  --output-root .\path_2_access_mode_canonical `
  --dataset-kind enterprise_structuring `
  --dataset-passport .\shared\runtime\signal_references\governance_reference\signal_dataset_passport_001.json
```

Check locations:

- `path_2_access_mode_canonical\03_dataset\candidates\`
- `path_2_access_mode_canonical\07_logs\`

Main files to inspect:

- `manifest.json`
- `dataset.jsonl`
- `lineage.json`
- newest `candidate_export_run_*.json`

Important things to confirm:

- all 4 bridged scenarios land in one grouped package
- `candidate_count = 4`
- `source_record_count = 8`
- routing profile shows `SEND_TO_STATE_2_REVIEW`
- target parameter class is the Path 2 governed range, not the runtime emitter range

Resolve the newest exported package once after this step:

```powershell
$Path2PackageDir = Get-ChildItem $Path2CandidateLatestRoot -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
$Path2DatasetVersion = Split-Path $Path2PackageDir -Leaf
```

Quick check:

```powershell
$Path2CandidateLatestRoot
$Path2PackageDir
$Path2DatasetVersion
```

## 4. Review the candidate package for `STATE_2`

```powershell
py -3 .\scripts\run_state2_review.py `
  --package-dir $Path2PackageDir `
  --notes "Path 2 STATE_2 review from the three-path root"
```

Check location:

- `$Path2PackageDir`

Created file:

- `state2_review.json`

Important things to confirm:

- `review_ready_ratio = 1.0`
- `routing_mismatch_count = 0`
- decision is `APPROVE_STATE_2_REVIEW_PACKAGE`

## 5. Evaluate promotion toward `STATE_1`

```powershell
py -3 .\scripts\run_state2_promotion.py `
  --package-dir $Path2PackageDir `
  --require-approved-review `
  --notes "Path 2 STATE_2 promotion check from the three-path root"
```

Check location:

- `$Path2PackageDir`

Created file:

- `state2_promotion_decision.json`

Important things to confirm:

- default threshold remains `min_candidates = 4`
- decision is `APPROVE_STATE_1` for the 4-scenario release pack

## 6. Materialize the `STATE_1` handoff package

```powershell
py -3 .\scripts\run_state1_handoff.py `
  --package-dir $Path2PackageDir `
  --require-approved-review `
  --require-approved-promotion `
  --notes "Path 2 STATE_1 handoff from the three-path root"
```

Check location:

- `$Path2PackageDir`

Created files:

- `state1_handoff.json`
- `freeze_ready_manifest.json`

Important things to confirm:

- `promotion_approved = true`
- `freeze_ready_manifest.freeze_posture.freeze_ready = true`

## 7. Freeze the approved candidate package

```powershell
py -3 .\scripts\run_state1_freeze.py `
  --package-dir $Path2PackageDir `
  --require-approved-review `
  --require-approved-promotion `
  --require-approved-handoff `
  --require-freeze-ready `
  --notes "Path 2 STATE_1 freeze from the three-path root"
```

Check location:

- `$Path2PackageDir\freeze\`

Created files:

- `freeze\state1_freeze.json`
- `freeze\frozen_manifest.json`
- `freeze\frozen_dataset.jsonl`

Important things to confirm:

- decision is `FREEZE_STATE1_PACKAGE`
- `frozen_dataset.jsonl` exists
- this is the repo-side lifecycle freeze, not the original source freeze

## 8. Register the approved `STATE_1` dataset

```powershell
py -3 .\scripts\run_state1_registry_update.py `
  --package-dir $Path2PackageDir `
  --registry-path $Path2RegistryPath `
  --require-approved-freeze `
  --require-state1 `
  --notes "Path 2 registry update from the three-path root"
```

Check locations:

- `shared\registry\state1_dataset_registry.json`
- `$Path2PackageDir\freeze\`

Created files:

- `freeze\state1_registry_update.json`
- one registry entry in `shared\registry\state1_dataset_registry.json`

Important things to confirm:

- decision is `REGISTER_STATE1_PACKAGE`
- the registered dataset version matches `$Path2DatasetVersion`
- if decision is `HOLD_STATE1_REGISTRY_UPDATE` because the same dataset version is already registered, that is expected and step 9 can still reuse that registered dataset version

## 9. Build the training package from the approved registry entry

Use the registered dataset version from step 8. This step accepts the full `local_lora_reference` backend profile.

If `$Path2DatasetVersion` is not yet set in the current shell, resolve it from the selected package path first:

```powershell
$Path2DatasetVersion = Split-Path $Path2PackageDir -Leaf
$Path2TrainingPackagesRoot = Join-Path $Path2RepoRoot 'path_2_access_mode_canonical\03_dataset\training_packages'
```

```powershell
py -3 .\scripts\run_training_state1.py `
  --dataset-version $Path2DatasetVersion `
  --registry-path $Path2RegistryPath `
  --output-root .\path_2_access_mode_canonical\03_dataset\training_packages `
  --backend-profile $Path2BackendProfile
```

Check location:

- `path_2_access_mode_canonical\03_dataset\training_packages\$Path2DatasetVersion\`

Created files:

- `train.sft.jsonl`
- `state1_training_manifest.json`
- `training_backend_profile.json`
- `training_preview.json`

Set the resolved training package path once after this step:

```powershell
$Path2TrainingPackage = Join-Path $Path2TrainingPackagesRoot $Path2DatasetVersion
$Path2TrainingPackage
```

Important things to confirm:

- `training_backend_profile.json` contains:
  - `backend_profile_id = local_lora_reference`
  - `backend = local_lora`
  - `model.model_base = TinyLlama/TinyLlama-1.1B-Chat-v1.0`
- `state1_training_manifest.json` points back to the repo-side `STATE_1` frozen dataset
- training preparation here is still controlled and does not mean fine-tuning is broadly authorized

## 10. Optional local LoRA run from the training package

Dry-run validation:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package $Path2TrainingPackage `
  --output-root .\path_2_access_mode_canonical\05_runs `
  --run-label path2_state1_dry_run `
  --dry-run
```

Optional one-step smoke test:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package $Path2TrainingPackage `
  --output-root .\path_2_access_mode_canonical\05_runs `
  --run-label path2_state1_smoke `
  --max-steps 1
```

Live run:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package $Path2TrainingPackage `
  --output-root .\path_2_access_mode_canonical\05_runs `
  --run-label path2_state1_run
```

Check location:

- newest folder under `path_2_access_mode_canonical\05_runs\FTRUN-*`
- newest folder under `path_2_access_mode_canonical\07_logs\run_logs\FTRUN-*`

Created files:

- `finetune_run_manifest.json`
- `training_log.json`
- `path2_finetune_run_<timestamp>.json`
- `trainer_summary.json`
- `trainer_command_summary.txt`
- `checkpoints\`
- `model\`

Important things to confirm:

- backend is `local_lora`
- backend profile id is `local_lora_reference`
- model base is `TinyLlama/TinyLlama-1.1B-Chat-v1.0`
- the top-level run log is written under `07_logs\run_logs\...` with `path_id = path_2_access_mode_canonical`
- the run is a controlled local reference run, not a governance authorization signal

## Current validated release example

For the current release anchor points, these are the main stable roots:

- source freeze:
  `path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z\`
- source bridge root:
  `path_2_access_mode_canonical\02_signals\source_bridge\2026-04-11--FREEZE-20260412-000400Z\`
- candidate latest-root:
  `path_2_access_mode_canonical\03_dataset\candidates\session-run-id2-20260411-1400-qpath-tr008-run\QPDS-PACKAGE-ID2_PREP\`

The timestamped package directory, dataset version, training package path, and optional run folder should be resolved from the current run as you move through the steps above.
