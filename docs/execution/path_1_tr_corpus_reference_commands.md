# Path 1 Commands

Run from:

```powershell
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 -c "import sys; print(sys.executable)"
```

Path summary:

- Path 1 converts TR reference material already staged in `01_source` into deterministic signals, a strict fine-tune dataset, a `STATE_1` package, and an optional local LoRA validation run.
- `build_tr_signals.py` is a deterministic extractor in the current release. It does not call `gpt-oss:20b`, Ollama, or a remote model.

Release v1.0 note:

- the current `01_source` example data for this path is already populated in `C:\v1.0-qpathformer_enterprise`
- use the shipped `tr_docs` and `readme_refs` folders first, then replace them only when you are intentionally testing a new source set

Current populated `01_source` folders:

- `path_1_tr_corpus_reference\01_source\tr_docs`
- `path_1_tr_corpus_reference\01_source\readme_refs`
- `path_1_tr_corpus_reference\01_source\corpus_snapshot`

Reviewer and test-run note:

- for validation of the current v1.0 release record, use `checkpoint_v4_strict` in both step 3 and step 4
- for a future rerun, replace `checkpoint_v5_strict` with a new dataset version token, but keep the same token aligned across step 3 and step 4
- after step 4, inspect `state1_training_manifest.json` if you want to confirm that the package now points at the expected dataset version before running step 5

## 1. Build the corpus snapshot

```powershell
py -3 .\scripts\build_tr_corpus_json.py `
  --input-root .\path_1_tr_corpus_reference\01_source\tr_docs `
  --output .\path_1_tr_corpus_reference\01_source\corpus_snapshot\tr_corpus.json
```

Check locations:

- `path_1_tr_corpus_reference\01_source\tr_docs\`
- `path_1_tr_corpus_reference\01_source\corpus_snapshot\tr_corpus.json`

Created files:

- `tr_corpus.json`

## 2. Build TR signals

```powershell
py -3 .\scripts\build_tr_signals.py `
  --input-root .\path_1_tr_corpus_reference\01_source\tr_docs `
  --output .\path_1_tr_corpus_reference\02_signals\tr_signals.json `
  --jsonl-output .\path_1_tr_corpus_reference\02_signals\tr_signals.jsonl
```

Check locations:

- `path_1_tr_corpus_reference\02_signals\tr_signals.json`
- `path_1_tr_corpus_reference\02_signals\tr_signals.jsonl`

Created files:

- `tr_signals.json`
- `tr_signals.jsonl`

Current note:

- this step reads local TR source files and emits governed signal records from deterministic parsing only
- if you want a `gpt-oss:20b` runtime signal path, that is currently a Path 2 runtime flow, not a Path 1 feature

## 3. Build the strict fine-tune dataset - change "checkpoint_v5_strict" for different session runs and between different datasets. The v1.0 release records use "checkpoint_v4_strict".

```powershell
py -3 .\scripts\build_tr_finetune_dataset.py `
  --signals-jsonl .\path_1_tr_corpus_reference\02_signals\tr_signals.jsonl `
  --docs-root .\path_1_tr_corpus_reference\01_source\readme_refs `
  --reference-layer .\shared\schemas\access-mode\access_mode_training_governance_reference.jsonl `
  --output-root .\path_1_tr_corpus_reference\03_dataset\checkpoint_v5_strict `
  --include-command-examples `
  --include-readme-docs `
  --require-reference-match
```

Check locations:

- `path_1_tr_corpus_reference\03_dataset\checkpoint_v5_strict\dataset_manifest.json`
- `path_1_tr_corpus_reference\03_dataset\checkpoint_v5_strict\dataset_preview.json`
- `path_1_tr_corpus_reference\03_dataset\checkpoint_v5_strict\reference_layer_report.json`

Created files:

- `train.sft.jsonl`
- `validation.sft.jsonl`
- `dataset_manifest.json`
- `dataset_preview.json`
- `reference_layer_report.json`
- `source_mix_report.json`
- `skipped_records.json`

Current note:

- the strict dataset build does not currently emit `state1_training_manifest.json` or `training_backend_profile.json`
- those training-control files are synthesized or copied during step 4
- if you are reviewing the shipped release record rather than creating a fresh rerun, substitute `checkpoint_v4_strict` in this step and in step 4 below

## 4. Build the STATE_1 package

```powershell
py -3 .\scripts\run_tr_state1_autopackage.py `
  --dataset-dir .\path_1_tr_corpus_reference\03_dataset\checkpoint_v5_strict `
  --notes "Path 1 TR strict wrapper run from the three-path root"
```

Check locations:

- `path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001\manifest.json`
- `path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001\state1_training_manifest.json`
- `path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001\training_backend_profile.json`
- `path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001\state1_handoff.json`
- `path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001\freeze\frozen_manifest.json`
- `path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001\freeze\state1_registry_update.json`

Created files:

- `dataset.jsonl`
- `train.sft.jsonl`
- `validation.sft.jsonl`
- `manifest.json`
- `dataset_preview.json`
- `reference_layer_report.json`
- `source_mix_report.json`
- `skipped_records.json`
- `state2_review.json`
- `state2_promotion_decision.json`
- `state1_handoff.json`
- `freeze_ready_manifest.json`
- `state1_training_manifest.json`
- `training_backend_profile.json`
- `freeze\frozen_dataset.jsonl`
- `freeze\frozen_manifest.json`
- `freeze\state1_freeze.json`
- `freeze\state1_registry_update.json`

Current note:

- the package training manifest now backfills the matching `STATE_1` registry entry when one already exists for the same `dataset_version`
- if `freeze\state1_registry_update.json` returns `HOLD_STATE1_REGISTRY_UPDATE` because the dataset version is already registered, that is expected and does not block training
- reviewers can confirm the package/dataset linkage in `state1_training_manifest.json` before starting the finetune step

## 5. Run the local LoRA validation pass

Dry-run validation:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package .\path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001 `
  --output-root .\path_1_tr_corpus_reference\05_runs `
  --run-label tr_v14_tinyllama_run `
  --dry-run
```

Optional one-step smoke test:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package .\path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001 `
  --output-root .\path_1_tr_corpus_reference\05_runs `
  --run-label tr_v14_tinyllama_smoke `
  --max-steps 1
```

Live run:

```powershell
py -3 .\scripts\run_state1_finetune_local_lora.py `
  --training-package .\path_1_tr_corpus_reference\04_state1_package\QPDS-TR-STRICT-ID3-001 `
  --output-root .\path_1_tr_corpus_reference\05_runs `
  --run-label tr_v14_tinyllama_run
```

Check locations:

- newest folder under `path_1_tr_corpus_reference\05_runs\FTRUN-*`
- newest folder under `path_1_tr_corpus_reference\07_logs\run_logs\FTRUN-*`
- `finetune_run_manifest.json`
- `training_log.json`
- `path1_finetune_run_*.json`
- `trainer_summary.json`
- `trainer_command_summary.txt`
- `checkpoints\`
- `model\`

Created files:

- `finetune_run_manifest.json`
- `training_log.json`
- `path1_finetune_run_*.json`
- `trainer_summary.json`
- `trainer_command_summary.txt`
- `checkpoints\`
- `model\`

Expected runtime notes:

- `local_lora` is the current default backend for this script
- both dry-run and live runs emit a Path 1 run log under `path_1_tr_corpus_reference\07_logs\run_logs\<run-id>\`
- the HF Hub warning about `HF_TOKEN` is optional and does not block the run
- the tokenizer PAD, BOS, and EOS alignment message is expected on this TinyLlama path
- CUDA is used automatically when available because the package backend profile is set to `device: auto`
- inspect `trainer_summary.json` to confirm the actual device used for the run
- for release verification, also confirm that `finetune_run_manifest.json` and `trainer_summary.json` both report the expected `dataset_version`
