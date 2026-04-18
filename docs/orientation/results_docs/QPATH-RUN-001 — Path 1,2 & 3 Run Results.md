# QPATH-RUN-001 - Path 1,2 & 3 Run Results

## 1. Purpose and Release Note

This document records the validated execution results for the v1.0 Q-Pathformer Enterprise release.

It summarizes:

- the validated result from each release path and option
- what to expect when each path is run from the shipped v1.0 release tree
- the lifecycle boundary reached by each path
- the current controlled interpretation of those results

Release note:

- the populated `01_source` folders in `C:\v1.0-qpathformer_enterprise` are example inputs provided with the v1.0 release
- they are included so the release can be validated end to end without first sourcing external material
- these example roots are:
  - `path_1_tr_corpus_reference\01_source`
  - `path_2_access_mode_canonical\01_source`
  - `path_3_external_custom_adapter\01_source`

This document is descriptive and evidence-bound.

It does not redefine governance, lifecycle semantics, or CSC interpretation, which remain established in the core release material.

All training-related outputs described here remain:

- controlled local validation only
- not unrestricted training authorization

## 2. Validated Paths and Options

### 2.1 Path 1 - TR Corpus Reference Path

Purpose:

- transform internal technical-report material into governed training-ready data and a `STATE_1` package

Release entry:

- `path_1_tr_corpus_reference\01_source\tr_docs`
- `path_1_tr_corpus_reference\01_source\readme_refs`

What to expect:

- deterministic corpus snapshot build
- deterministic signal extraction
- strict fine-tune dataset generation
- `STATE_1` wrapper package creation
- local LoRA dry-run validation
- optional one-step smoke run

Important note:

- `build_tr_signals.py` is deterministic in the current release
- this path does not use `gpt-oss:20b`

Validated v1.0 release record:

- `checkpoint_v4_strict` is the current Path 1 release record
- `document_count = 16`
- `signal_count = 846`
- `dataset_version = checkpoint_v4_strict`
- `source_signal_rows = 1241`
- `train_rows = 1117`
- `validation_rows = 124`
- `package_id = QPDS-TR-STRICT-ID3-001`
- package build passed
- full local LoRA finetune run passed
- `device = cuda`
- `train_loss = 3.4113`
- `train_loss_final = 3.4135`

Lifecycle outcome:

- `STATE_1`

Interpretation:

- strongest internal reference training path
- demonstrates the full internal flow from source to dataset to package to controlled local training validation

### 2.2 Path 2 - Source-First Access-Mode Lifecycle Path

Purpose:

- demonstrate governed lifecycle routing from Access-Mode source freeze into a controlled `STATE_1` package

Release entry:

- `path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z`

What to expect:

- use the populated `ID_3` freeze bundle already shipped in `01_source`
- bridge the four release scenarios into governed Path 2 signals
- export one grouped candidate package
- pass `STATE_2` review
- pass promotion toward `STATE_1`
- materialize handoff, freeze, and registry update
- build the local LoRA training package
- run dry-run validation and optional smoke training

Validated v1.0 release record:

- `dataset_version = id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260418T044710Z`
- grouped release scenarios = `4`
- `candidate_count = 4`
- `source_record_count = 16`
- `routing_decision = SEND_TO_STATE_2_REVIEW`
- `STATE_2` review passed
- promotion passed
- handoff passed
- freeze passed
- registry update passed
- training package build passed
- full local LoRA finetune run passed
- `record_count = 4`
- `device = cuda`
- `train_loss = 3.7577`
- `train_loss_final = 3.2855`

Critical constraints:

- `fine_tuning_globally_allowed = false`
- training remains controlled validation only
- governance traceability is preserved through freeze, review, and registry artifacts

Lifecycle outcome:

- `STATE_1`

Interpretation:

- strongest governed lifecycle path in the release
- primary evidence path for release-grade lifecycle traceability
- preserves provenance, freeze discipline, and explicit review gates

### 2.3 Path 2 - Runtime `gpt-oss:20b` Option

Purpose:

- test the live runtime signal route without starting from the shipped `01_source` freeze bundle

Release entry:

- local Ollama server on `http://localhost:11434`
- local model tag `gpt-oss:20b`
- output root `path_2_access_mode_canonical\02_signals\runtime_generated`

Important source note:

- the Path 2 runtime `gpt-oss:20b` option does not read the shipped `path_2_access_mode_canonical\01_source` freeze bundle
- the populated `01_source` files remain the release example for the source-first Path 2 route only
- for the runtime route, new source material is created at run time as signal files under `path_2_access_mode_canonical\02_signals\runtime_generated`

What to expect:

- runtime signal emission from local Ollama
- the shipped `01_source` files are not consumed in this route
- signal lands in `STATE_3`
- export creates candidate packages grouped by `session_id`
- if older runtime signals are already present in `runtime_generated`, export can emit multiple separate session-group packages in one run
- review can pass with a single valid candidate
- promotion still requires the current grouped threshold of `min_candidates = 4`

Validated result from the runtime run executed on April 18, 2026 in the local `Australia/Sydney` timezone:

- local Ollama service started successfully
- local model `gpt-oss:20b` was present and used
- `session_id = llm-runtime-session-20260418-codex`
- runtime signal emission passed
- `eligible_for_state_2 = true`
- `routing_decision = SEND_TO_STATE_2_REVIEW`
- candidate export passed
- `candidate_count = 1`
- `source_record_count = 1`
- `STATE_2` review passed
- promotion held with `candidate_count_below_threshold:1<4`

Critical constraint:

- this option did not fail because of content quality, routing mismatch, or missing review approval
- it held because the grouped runtime package contained only one candidate for that session

Lifecycle outcome:

- `STATE_3 -> STATE_2 review package approved`
- promotion held before `STATE_1`

Interpretation:

- the runtime route now executes successfully in the release
- it is a valid controlled runtime-to-review path
- it needs four non-duplicate candidates under the same session grouping, or a policy change, to cross the current promotion gate

### 2.4 Path 3 - External Bundle Intake Option

Purpose:

- normalize an external governed bundle into a contained onboarding package

Release entry:

- `path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001`

What to expect:

- dry-run structure and hash validation
- live normalization into onboarding outputs
- lifecycle remains contained in `STATE_3`
- no promotion to training package in the current release path

Validated v1.0 result:

- `package_id = QPDS-PACKAGE-001`
- `template_family = id3_freeze_bundle`
- `profile_id = id3_freeze_bundle.default`
- `profile_version = v13.2`
- `source_file_count = 6`
- `normalized_record_count = 6`
- `module_record_count = 2`
- `session_record_count = 2`
- `freeze_note_count = 1`
- `hash_manifest_count = 1`
- `hash_verification_status = ok`
- live normalization passed

Lifecycle outcome:

- `STATE_3`
- `eligible_for_state_2 = false`
- `routing_decision = HOLD_IN_STATE_3`

Constraints:

- `fine_tuning_allowed_default = false`
- `external_training_allowed_default = false`
- `human_review_required_default = true`

Interpretation:

- controlled onboarding path only
- not a promoted training package
- not a `STATE_1` lifecycle result in the current release

### 2.5 Path 3 - Client Structured JSON Option

Purpose:

- normalize a structured client JSON package into the same controlled onboarding format

Release entry:

- `path_3_external_custom_adapter\01_source\inbound\CLIENT-DATASET-EXAMPLE-001\client_governance.json`

What to expect:

- dry-run validation of client JSON structure
- live normalization into onboarding rows
- contained `STATE_3` result only

Validated v1.0 result:

- `package_id = CLIENT-DATASET-EXAMPLE-001`
- `template_family = client_governance_json`
- `profile_id = client_governance_json.default`
- `profile_version = v13.2`
- `source_file_count = 1`
- `normalized_record_count = 4`
- `client_governance_record_count = 4`
- `hash_verification_status = ok`
- live normalization passed

Lifecycle outcome:

- `STATE_3`
- `eligible_for_state_2 = false`
- `routing_decision = HOLD_IN_STATE_3`

Constraints:

- `fine_tuning_allowed_default = false`
- `external_training_allowed_default = false`
- `human_review_required_default = true`

Interpretation:

- controlled client onboarding path only
- not a promoted training package
- separate from the external bundle example, but under the same release containment posture

## 3. Comparative Summary

| Path / Option | Example Entry in Release | Lifecycle Reached | Expected Result |
| --- | --- | --- | --- |
| Path 1 - TR corpus reference | `path_1_tr_corpus_reference\01_source` | `STATE_1` | Full internal reference flow through controlled local validation |
| Path 2 - source-first | `path_2_access_mode_canonical\01_source\2026-04-11--FREEZE-20260412-000400Z` | `STATE_1` | Full governed lifecycle flow through freeze, registry, and controlled local validation |
| Path 2 - runtime `gpt-oss:20b` | `path_2_access_mode_canonical\02_signals\runtime_generated` | `STATE_2` review approved, promotion held | Live runtime-to-review path; promotion depends on grouped candidate count |
| Path 3 - external bundle | `path_3_external_custom_adapter\01_source\inbound\QPDS-PACKAGE-001` | `STATE_3` | Controlled onboarding and normalization only |
| Path 3 - client JSON | `path_3_external_custom_adapter\01_source\inbound\CLIENT-DATASET-EXAMPLE-001` | `STATE_3` | Controlled onboarding and normalization only |

## 4. Key Interpretation and Boundaries

The validated release runs demonstrate:

- separate controlled systems for reference training, lifecycle governance, and external onboarding
- strict lifecycle enforcement with no bypass around review and promotion gates
- preservation of provenance in the source-first governed path
- separation between dataset preparation and training authorization

Critical boundary:

- no result in this release should be read as unrestricted fine-tuning authorization

Path reading:

- Path 1 is the strongest internal reference training path
- Path 2 source-first is the strongest governed lifecycle path
- Path 2 runtime is now a working live runtime option, but its promotion result depends on grouped runtime candidate count
- Path 3 external and client options are onboarding-only paths in the current release

Final release reading:

- v1.0 is a controlled, evidence-producing release
- the populated `01_source` folders are example release inputs for validation
- the release demonstrates executable source-to-lifecycle pathways without changing the governance boundary around authorization
