# Path 3 Client Custom Dataset Commands

Run from:

```powershell
Set-Location "C:\v1.0-qpathformer_enterprise"
py -3 -c "import sys; print(sys.executable)"
```

Path summary:

- This Path 3 branch ingests a structured client JSON file from `01_source\inbound` and normalizes it into a contained `STATE_3` onboarding package.
- it is separate from the `QPDS-PACKAGE-001` external freeze-bundle example and is documented in its own single-flow file

Release v1.0 note:

- the current populated client example is already provided in `C:\v1.0-qpathformer_enterprise`
- use the shipped client example first unless you are intentionally validating a different client JSON package

This branch is separate from the `QPDS-PACKAGE-001` freeze-bundle example. It uses a single structured client JSON file and the `client_governance_json` adapter profile.

Current validated example:

- `path_3_external_custom_adapter\01_source\inbound\CLIENT-DATASET-EXAMPLE-001\client_governance.json`

Current validated end point:

- `path_3_external_custom_adapter\03_dataset\normalized\CLIENT-DATASET-EXAMPLE-001`

Important note:

- this client branch uses `--input-file`
- it does not use `--input-root`
- the current validated automation ends at normalized onboarding in `STATE_3`
- it does not yet continue into promoted training preparation or freeze or archive for the release

## Source file used

Input file:

- `path_3_external_custom_adapter\01_source\inbound\CLIENT-DATASET-EXAMPLE-001\client_governance.json`

Quick source check:

```powershell
Get-Content .\path_3_external_custom_adapter\01_source\inbound\CLIENT-DATASET-EXAMPLE-001\client_governance.json
```

Key source fields:

- `dataset_id = CLIENT-DATASET-EXAMPLE-001`
- `dataset_version = v1.0-example`
- `source_type = client_governance_json`
- `record_count = 4`

## 1. Dry-run the client adapter intake

```powershell
py -3 .\scripts\run_external_adapter_ingestion.py `
  --input-file .\path_3_external_custom_adapter\01_source\inbound\CLIENT-DATASET-EXAMPLE-001\client_governance.json `
  --output-root .\path_3_external_custom_adapter\03_dataset\normalized `
  --template-family client_governance_json `
  --profile-path .\shared\configs\adapter_profiles\client_governance_json.profile.json `
  --write-rejected `
  --rejected-root .\path_3_external_custom_adapter\03_dataset\rejected `
  --dry-run
```

Current validated dry-run result:

- `status = ok`
- `package_id = CLIENT-DATASET-EXAMPLE-001`
- `template_family = client_governance_json`
- `profile_id = client_governance_json.default`
- `normalized_record_count = 4`
- `hash_verification_status = ok`

Dry-run note:

- no normalized package files are written in dry-run mode
- no onboarding log is written in dry-run mode
- if intake fails, check:
  - `path_3_external_custom_adapter\03_dataset\rejected\CLIENT-DATASET-EXAMPLE-001\rejection_report.json`

## 2. Write the normalized onboarding package

```powershell
py -3 .\scripts\run_external_adapter_ingestion.py `
  --input-file .\path_3_external_custom_adapter\01_source\inbound\CLIENT-DATASET-EXAMPLE-001\client_governance.json `
  --output-root .\path_3_external_custom_adapter\03_dataset\normalized `
  --template-family client_governance_json `
  --profile-path .\shared\configs\adapter_profiles\client_governance_json.profile.json `
  --write-rejected `
  --rejected-root .\path_3_external_custom_adapter\03_dataset\rejected
```

Output location:

- `path_3_external_custom_adapter\03_dataset\normalized\CLIENT-DATASET-EXAMPLE-001`

Files created:

- `onboarding_manifest.json`
- `normalized_onboarding.jsonl`
- `source_inventory.json`
- `normalization_report.json`
- `hash_verification_report.json`
- `path_3_external_custom_adapter\07_logs\onboarding_logs\CLIENT-DATASET-EXAMPLE-001\onboarding_run_<timestamp>.json`

Current validated write result:

- `status = ok`
- `source_file_count = 1`
- `normalized_record_count = 4`
- `hash_verification_status = ok`

## 3. Review the normalized onboarding outputs

Review these files:

- `path_3_external_custom_adapter\03_dataset\normalized\CLIENT-DATASET-EXAMPLE-001\onboarding_manifest.json`
- `path_3_external_custom_adapter\03_dataset\normalized\CLIENT-DATASET-EXAMPLE-001\normalization_report.json`
- `path_3_external_custom_adapter\03_dataset\normalized\CLIENT-DATASET-EXAMPLE-001\source_inventory.json`
- `path_3_external_custom_adapter\03_dataset\normalized\CLIENT-DATASET-EXAMPLE-001\hash_verification_report.json`
- `path_3_external_custom_adapter\03_dataset\normalized\CLIENT-DATASET-EXAMPLE-001\normalized_onboarding.jsonl`
- `path_3_external_custom_adapter\07_logs\onboarding_logs\CLIENT-DATASET-EXAMPLE-001\onboarding_run_<timestamp>.json`

Current validated output summary:

- `source_file_count = 1`
- `normalized_record_count = 4`
- `artifact_type = client_governance_json`
- `client_governance_record_count = 4`
- `hash_verification_overall_status = ok`
- `warnings = []`

Lifecycle and authorization posture:

- `state = STATE_3`
- `eligible_for_state_2 = false`
- `routing_decision = HOLD_IN_STATE_3`
- `fine_tuning_allowed_default = false`
- `external_training_allowed_default = false`
- `human_review_required_default = true`

This means the current client branch is a contained onboarding result, not a promoted training package.
