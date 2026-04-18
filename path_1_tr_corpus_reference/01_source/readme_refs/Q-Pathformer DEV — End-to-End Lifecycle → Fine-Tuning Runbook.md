# Q-Pathformer DEV - End-to-End Lifecycle to Fine-Tuning Runbook

## Purpose

This runbook connects the current development phases from source material to a governed training run.

It does not replace the execution command sheets. It explains how the phases connect and where the handoff boundaries sit.

## Development Phase Chain

### Phase 1. Source

Inputs:

- TR documents under `path_1_tr_corpus_reference\01_source\tr_docs\`
- selected developer references under `path_1_tr_corpus_reference\01_source\readme_refs\`

Responsibility:

- establish the intent, scope, and phase boundaries of the training flow

Non-responsibility:

- source markdown does not create approval, routing, or training authority

### Phase 2. Signals

Outputs:

- `path_1_tr_corpus_reference\02_signals\tr_signals.json`
- `path_1_tr_corpus_reference\02_signals\tr_signals.jsonl`

Responsibility:

- convert TR references into structured signals with lineage

### Phase 3. Dataset

Outputs:

- `train.sft.jsonl`
- `validation.sft.jsonl`
- `state1_training_manifest.json`
- `training_backend_profile.json`

Responsibility:

- build a strict dataset package suitable for governed training preparation

### Phase 4. STATE_1 Package

Outputs:

- `manifest.json`
- `state1_handoff.json`
- `freeze_ready_manifest.json`
- `freeze\frozen_manifest.json`

Responsibility:

- bridge the strict dataset into a lifecycle-contained package and freeze boundary

### Phase 5. Training Run

Outputs:

- `finetune_run_manifest.json`
- `training_log.json`
- `trainer_summary.json`
- `checkpoints\`
- `model\`

Responsibility:

- consume the governed training package and record reproducible run lineage

## Phase Gate Rule

A later phase may consume an earlier phase output only when the intermediate package or manifest exists and preserves the non-authoritative lifecycle boundary.

## Developer Signal Rule

Source markdown should help the builder answer these questions clearly:

- what is this phase responsible for
- what must this phase not do
- what output is created here
- what next phase consumes that output

Low-signal markdown weakens the readme and runbook contribution inside the strict dataset build.
