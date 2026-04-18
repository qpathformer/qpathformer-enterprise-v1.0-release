# Path 2 Runtime-Signal Commands

Run from:

```powershell
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 -c "import sys; print(sys.executable)"
```

Path summary:

- This Path 2 route starts from a runtime-generated `STATE_3` signal instead of the populated source freeze bundle in `01_source`.
- It uses the local Ollama-served `gpt-oss:20b` model to emit a governed runtime signal, exports a candidate package from that signal root, and can continue through the same controlled review, promotion, registry, training-package, and local validation steps.

Release v1.0 note:

- this route uses the v1.0 release folder and writes runtime outputs under `path_2_access_mode_canonical\02_signals\runtime_generated`
- the current populated `01_source` bundle remains available in the release, but this file does not use it

When to use this file:

- use it for `gpt-oss:20b` runtime signal tests
- use it for routing checks or controlled lifecycle checks that do not need full source-freeze provenance
- do not describe this path as unrestricted fine-tuning authorization

Preflight:

- make sure Ollama is reachable at `http://localhost:11434`
- make sure the local model name `gpt-oss:20b` is available before you run step 1

## Start Here

Run this block once before step 1:

```powershell
. .\scripts\path2_current_release_env.ps1
$Path2RuntimeSessionId = 'llm-runtime-session'
$Path2TrainingPackagesRoot = Join-Path $Path2RepoRoot 'path_2_access_mode_canonical\03_dataset\training_packages'
$Path2RuntimeSignalRoot
$Path2RuntimeSessionId
```

That startup block sets or confirms these values for the runtime route:

- `$Path2RuntimeSignalRoot`
- `$Path2RegistryPath`
- `$Path2BackendProfile`
- `$Path2RuntimeSessionId`
- `$Path2TrainingPackagesRoot`

Reviewer note:

- keep the same `$Path2RuntimeSessionId` value aligned between step 1 and the package-resolution snippet after step 2
- if you intentionally use a different session id in step 1, change it in this startup block first and then reuse the same value below

## Controlled note

- the runtime-only `gpt-oss:20b` path remains a controlled reference path in the current release
- it does not include the full `01_source` freeze provenance bundle
- any downstream training package or local LoRA run should still be described as controlled local validation only

## 1. Emit the runtime-generated `gpt-oss:20b` signal

```powershell
py -3 .\scripts\runtime\run_runtime_signal_emitter.py `
  --prompt "Summarize runtime governance signals for the current Access-Mode session." `
  --model gpt-oss:20b `
  --session-id $Path2RuntimeSessionId `
  --signal-root $Path2RuntimeSignalRoot
```

Check locations:

- `path_2_access_mode_canonical\02_signals\runtime_generated\`
- `shared\registry\run_references\`
- `shared\registry\run_registry.json`

Created files:

- `signal_runtime_*.json`
- `signal_runtime_*.routing.json`
- `RTRUN-*.runtime_signal_run_reference.json`

Important things to confirm:

- the signal is written in `STATE_3`
- the routing file sits beside the signal file
- the run reference lands in `shared\registry\run_references\`
- `shared\registry\run_registry.json` records the live runtime run with a current relative `run_reference_path`
- repeated runs must reuse the same `session_id` if you want grouped candidate export later

## 2. Export candidate datasets from runtime-generated `gpt-oss:20b` signals

```powershell
py -3 .\scripts\export_candidates_v2.py `
  --input $Path2RuntimeSignalRoot `
  --require-routing-review `
  --output-root .\path_2_access_mode_canonical `
  --dataset-kind enterprise_structuring `
  --dataset-passport .\shared\runtime\signal_references\governance_reference\signal_dataset_passport_001.json
```

Check locations:

- `path_2_access_mode_canonical\03_dataset\candidates\`
- `path_2_access_mode_canonical\07_logs\`

Important things to confirm:

- this path exports from runtime signals only
- candidate count depends on how many non-duplicate signals were emitted with the same session id
- this is useful for routing tests, but it is not the full source-first release path

Resolve the newest exported package once after this step:

```powershell
$Path2CandidateLatestRoot = Join-Path $Path2RepoRoot "path_2_access_mode_canonical\03_dataset\candidates\session-run-$Path2RuntimeSessionId\QPDS-PACKAGE-ID2_PREP"
$Path2PackageDir = Get-ChildItem -LiteralPath $Path2CandidateLatestRoot -Directory |
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

Current note:

- the runtime route should always set `$Path2CandidateLatestRoot` explicitly before review
- once `$Path2PackageDir` is populated, steps 3 through 7 can use it directly

## 3. Review the candidate package for `STATE_2`

```powershell
py -3 .\scripts\run_state2_review.py `
  --package-dir $Path2PackageDir `
  --notes "Path 2 STATE_2 review from the three-path root"
```

Check location:

- `$Path2PackageDir`

Created file:

- `state2_review.json`

## 4. Evaluate promotion toward `STATE_1`

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

Current note:

- promotion approval depends on the runtime export meeting the current threshold checks
- a single runtime signal may not be enough to satisfy the default promotion criteria

## 5. Materialize the `STATE_1` handoff package

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

## 6. Freeze the approved candidate package

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

## 7. Register the approved `STATE_1` dataset

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

## 8. Build the training package from the approved registry entry

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

## 9. Optional local LoRA run from the training package

Dry-run validation:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package $Path2TrainingPackage `
  --output-root .\path_2_access_mode_canonical\05_runs `
  --run-label path2_runtime_dry_run `
  --dry-run
```

Optional one-step smoke test:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package $Path2TrainingPackage `
  --output-root .\path_2_access_mode_canonical\05_runs `
  --run-label path2_runtime_smoke `
  --max-steps 1
```

Live run:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package $Path2TrainingPackage `
  --output-root .\path_2_access_mode_canonical\05_runs `
  --run-label path2_runtime_run
```

Check location:

- newest folder under `path_2_access_mode_canonical\05_runs\FTRUN-*`
- newest folder under `path_2_access_mode_canonical\07_logs\run_logs\FTRUN-*`

Important things to confirm:

- backend is `local_lora`
- the top-level run log is written under `07_logs\run_logs\...` with `path_id = path_2_access_mode_canonical`
- the run remains a controlled local reference run
