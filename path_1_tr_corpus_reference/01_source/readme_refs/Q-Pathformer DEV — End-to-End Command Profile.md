# Q-Pathformer DEV - End-to-End Command Profile

## Purpose

This profile describes which script families belong to each lifecycle path and what boundary each script must preserve.

Run commands from the repository root:

```powershell
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 -c "import sys; print(sys.executable)"
```

## Path 1 Command Family

Path 1 moves from source references to a strict STATE_1 training package.

Primary scripts:

- `scripts\build_tr_corpus_json.py`
- `scripts\build_tr_signals.py`
- `scripts\build_tr_finetune_dataset.py`
- `scripts\run_tr_state1_autopackage.py`
- `scripts\run_state1_finetune_local_lora.py`

Primary phase connection:

- `01_source` explains the corpus and developer boundaries
- `02_signals` emits structured TR signal rows
- `03_dataset` builds strict fine-tune datasets
- `04_state1_package` materializes the governed package and freeze record
- `05_runs` records the training execution surface

Representative command:

```powershell
py -3 .\scripts\run_tr_state1_autopackage.py `
  --dataset-dir .\path_1_tr_corpus_reference\03_dataset\checkpoint_v3_strict `
  --notes "Path 1 strict wrapper run"
```

Boundary:

- package creation must not imply approval or release authority

## Path 2 Command Family

Path 2 carries Access-Mode runtime artifacts into candidate review and STATE_1 preparation.

Primary scripts:

- `scripts\runtime\run_runtime_signal_emitter.py`
- `scripts\export_candidates_v2.py`
- `scripts\run_state2_review.py`
- `scripts\run_state2_promotion.py`
- `scripts\run_state1_handoff.py`
- `scripts\run_state1_freeze.py`
- `scripts\run_state1_registry_update.py`
- `scripts\run_training_state1.py`

Representative command:

```powershell
py -3 .\scripts\export_candidates_v2.py `
  --input .\path_2_access_mode_canonical\02_signals\runtime_generated `
  --require-routing-review `
  --output-root .\path_2_access_mode_canonical
```

Boundary:

- runtime signals remain provisional until explicit review, promotion, handoff, and freeze artifacts exist

## Path 3 Command Family

Path 3 normalizes external bundles into a contained onboarding contract before any package assembly is attempted.

Primary scripts:

- `scripts\run_external_adapter_ingestion.py`
- `scripts\build_dataset_package.py`
- `scripts\prepare_dataset_freeze.py`
- `scripts\freeze_dataset_package.py`

Representative command:

```powershell
py -3 .\scripts\run_external_adapter_ingestion.py `
  --input-root .\path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001 `
  --output-root .\path_3_external_custom_adapter\03_dataset\normalized `
  --template-family id3_freeze_bundle
```

Boundary:

- onboarding does not authorize training, promotion, or approval

## Command Selection Rule

Choose commands by lifecycle phase, not by convenience.

Use this rule:

- source clarification belongs in `01_source`
- signal generation belongs in `02_signals`
- dataset shaping belongs in `03_dataset`
- freeze and registry actions belong after review and handoff gates
- training commands only consume governed training packages
