# Q-Pathformer DEV - System Overview

## Purpose

Q-Pathformer DEV is a controlled execution environment for moving governed reasoning artifacts through a dataset lifecycle without implying authority, approval, or certification.

The project organizes work into three execution paths:

- Path 1: TR corpus and reference training flow
- Path 2: Access-Mode ID_2 to ID_3 canonical lifecycle flow
- Path 3: external or custom dataset adapter flow

## Governing References

The project operates within the boundaries defined by:

- APOD-TR-006 for reasoning posture control
- APOD-TR-006-E.2 for artifact lifecycle interpretation
- APOD-TR-007 for governed dataset lifecycle and passport concepts
- APOD-TR-008 for execution-layer packaging and orchestration

## Non-Claims

This repository does not:

- grant governance authority
- certify outputs
- imply compliance
- replace human review

All outputs remain:

- non-authoritative
- non-certifying
- traceable
- lifecycle-contained

## Developer Phase Connection

The current development posture connects the paths in this order:

1. source intake or source reference capture under `01_source`
2. structured signal emission under `02_signals`
3. dataset shaping under `03_dataset`
4. package and freeze preparation under `04_state1_package`
5. execution and validation under `05_runs`

This means the source layer must explain phase intent clearly before any generated artifact exists.

## Three Path Summary

### Path 1

Source:

- `path_1_tr_corpus_reference\01_source\tr_docs\`
- `path_1_tr_corpus_reference\01_source\readme_refs\`

Purpose:

- convert TR material and selected developer guidance into governed training signals and strict fine-tune datasets

### Path 2

Source:

- `path_2_access_mode_canonical\01_source\id3_freeze_example\`

Purpose:

- carry canonical Access-Mode runtime artifacts through candidate review, promotion, handoff, freeze, and training preparation

### Path 3

Source:

- `path_3_external_custom_adapter\01_source\inbound\`

Purpose:

- admit external or customer bundles into a contained onboarding structure before any dataset promotion work is allowed

## Model Roles

The visible model roles in the project are:

- `gpt-oss:20b` for runtime or signal-oriented generation
- `TinyLlama/TinyLlama-1.1B-Chat-v1.0` for local LoRA fine-tuning targets

## Source Layer Rule

Markdown in `01_source` should strengthen phase understanding, not add noise.

A strong source markdown file should make these items explicit:

- what phase it belongs to
- what the phase is responsible for
- what the phase must not do
- which scripts or outputs connect to the next phase
- which non-claims must be preserved
