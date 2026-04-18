# Path 3 Commands

Run from:

```powershell
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 -c "import sys; print(sys.executable)"
```

Path summary:

- Path 3 external intake normalizes an inbound governed bundle from `01_source\inbound` into a contained `STATE_3` onboarding package.
- the current release path ends at normalized onboarding review. It does not yet continue into a promoted training package or frozen archive.

Release v1.0 note:

- the current populated `01_source` example bundle for this path is already provided in `C:\v1.0-qpathformer_enterprise`
- use the shipped inbound bundle before swapping in a new external package

This version focuses on the completed external governed bundle intake for:

- `path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001`

The client dataset branch is documented separately in:

- `docs\execution\path_3_client_custom_dataset_commands.md`

## Current Path 3 run scope

The current validated automated flow is:

1. inbound source bundle in `01_source`
2. dry-run adapter intake
3. write normalized onboarding package
4. review normalized onboarding outputs

The current validated end point is:

- `03_dataset\normalized\QPDS-PACKAGE-001`

This Path 3 run does not yet continue into package build, pre-freeze, or frozen archive in the current release note.

## Source bundle used

Current source folder:

- `path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001`

Files expected in the source bundle:

- `hashes.txt`
- `ID3_FREEZE_NOTE.md`
- `module_03_baseline.canonical.json`
- `module_03_variant.canonical.json`
- `session_baseline.canonical.json`
- `session_variant.canonical.json`

Quick source check:

```powershell
Get-ChildItem .\path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001
```

## 1. Dry-run the adapter intake

```powershell
py -3 .\scripts\run_external_adapter_ingestion.py `
  --input-root .\path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001 `
  --output-root .\path_3_external_custom_adapter\03_dataset\normalized `
  --template-family id3_freeze_bundle `
  --profile-path .\shared\configs\adapter_profiles\id3_freeze_bundle.profile.json `
  --write-rejected `
  --rejected-root .\path_3_external_custom_adapter\03_dataset\rejected `
  --dry-run
```

What this checks:

- source bundle shape
- freeze note structure
- canonical file presence
- hash manifest compatibility

Current validated dry-run result:

- `status = ok`
- `package_id = QPDS-PACKAGE-001`
- `template_family = id3_freeze_bundle`
- `normalized_record_count = 6`
- `hash_verification_status = ok`

Dry-run note:

- no output files are written in dry-run mode
- no onboarding log is written in dry-run mode
- if dry-run fails, check `03_dataset\rejected\QPDS-PACKAGE-001\rejection_report.json`

## 2. Write the normalized onboarding package

```powershell
py -3 .\scripts\run_external_adapter_ingestion.py `
  --input-root .\path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001 `
  --output-root .\path_3_external_custom_adapter\03_dataset\normalized `
  --template-family id3_freeze_bundle `
  --profile-path .\shared\configs\adapter_profiles\id3_freeze_bundle.profile.json `
  --write-rejected `
  --rejected-root .\path_3_external_custom_adapter\03_dataset\rejected
```

Output location:

- `path_3_external_custom_adapter\03_dataset\normalized\QPDS-PACKAGE-001`

Files created:

- `onboarding_manifest.json`
- `normalized_onboarding.jsonl`
- `source_inventory.json`
- `normalization_report.json`
- `hash_verification_report.json`
- `path_3_external_custom_adapter\07_logs\onboarding_logs\QPDS-PACKAGE-001\onboarding_run_<timestamp>.json`

Failure output if intake fails:

- `path_3_external_custom_adapter\03_dataset\rejected\QPDS-PACKAGE-001\rejection_report.json`

## 3. Review the normalized onboarding outputs

Review these files:

- `path_3_external_custom_adapter\03_dataset\normalized\QPDS-PACKAGE-001\onboarding_manifest.json`
- `path_3_external_custom_adapter\03_dataset\normalized\QPDS-PACKAGE-001\source_inventory.json`
- `path_3_external_custom_adapter\03_dataset\normalized\QPDS-PACKAGE-001\normalization_report.json`
- `path_3_external_custom_adapter\03_dataset\normalized\QPDS-PACKAGE-001\hash_verification_report.json`
- `path_3_external_custom_adapter\03_dataset\normalized\QPDS-PACKAGE-001\normalized_onboarding.jsonl`
- `path_3_external_custom_adapter\07_logs\onboarding_logs\QPDS-PACKAGE-001\onboarding_run_<timestamp>.json`

Current validated output summary:

- `source_file_count = 6`
- `normalized_record_count = 6`
- artifact counts:
  - `module_record = 2`
  - `session_record = 2`
  - `freeze_note = 1`
  - `hash_manifest = 1`
- `hash_verification_overall_status = ok`
- `warnings = []`

Lifecycle and authorization posture confirmed in the outputs:

- lifecycle initializes to `STATE_3`
- `eligible_for_state_2 = false`
- `routing_decision = HOLD_IN_STATE_3`
- `fine_tuning_allowed_default = false`
- `external_training_allowed_default = false`
- `human_review_required_default = true`

This means the current Path 3 result is an onboarding and normalization result, not a promoted training package.

## 4. Current release interpretation

Describe the current Path 3 run like this:

- source type: external governed bundle intake
- source bundle: `QPDS-PACKAGE-001`
- validated automation: inbound bundle -> normalized onboarding package
- current outcome: `STATE_3` onboarding package held in contained lifecycle posture
- training posture: restricted by default

Do not describe this current Path 3 run as:

- a training-authorized package
- a `STATE_1` promoted package
- a completed freeze or archive package
