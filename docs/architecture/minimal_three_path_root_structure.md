# Minimal Three Path Root Structure

This document describes the live root layout in `C:\v1.0-qpathformer_enterprise`.

## Active Root

The active top-level folders are:

- `changes\`
- `docs\`
- `path_1_tr_corpus_reference\`
- `path_2_access_mode_canonical\`
- `path_3_external_custom_adapter\`
- `scripts\`
- `shared\`

## Design Rule

The root stays small on purpose:

- `docs\` holds orientation, architecture, project readmes, and reference releases
- `scripts\` stays at root so all execution entrypoints are easy to find
- `shared\` holds contracts and runtime dependencies used by more than one path
- each dataset lifecycle path gets one top-level folder with the same stage sequence

## Shared Layer

`shared\` currently contains:

- `configs\`
- `schemas\`
- `registry\`
- `runtime\`
- `models\`
- `evaluation\`

Use `shared\` for:

- adapter profiles
- lifecycle configs
- shared schemas
- shared registries
- runtime signal references
- model references and evaluation assets

## Mirrored Path Structure

Each path uses the same stage numbers:

- `01_source\`
- `02_signals\`
- `03_dataset\`
- `04_state1_package\`
- `05_runs\`
- `06_review\`
- `07_logs\`

Some stages are placeholders today, but they are present so the three paths stay readable in the same way.

## Path Summary

### `path_1_tr_corpus_reference\`

Purpose:

- TR corpus scanning
- governed signal extraction
- fine-tune dataset creation
- STATE_1 packaging and freeze outputs
- training runs

Main live content:

- `01_source\tr_docs\`
- `01_source\readme_refs\`
- `01_source\corpus_snapshot\tr_corpus.json`
- `02_signals\`
- `03_dataset\checkpoint_v1\`
- `03_dataset\checkpoint_v3\`
- `03_dataset\checkpoint_v3_strict\`
- `04_state1_package\QPDS-TR-STRICT-ID3-001\`
- `05_runs\`

### `path_2_access_mode_canonical\`

Purpose:

- canonical Access-Mode ID_2 to ID_3 lifecycle
- runtime signal generation
- candidate export and training-package preparation
- later STATE_1 package and promotion stages

Main live content:

- `01_source\id3_freeze_example\`
- `02_signals\runtime_generated\`
- `03_dataset\candidates\`
- `03_dataset\training_packages\`
- `05_runs\`
- `07_logs\logs\`

### `path_3_external_custom_adapter\`

Purpose:

- external or customer onboarding
- adapter normalization
- accepted and rejected dataset handling
- later package, review, and run stages

Main live content:

- `01_source\inbound\`
- `03_dataset\normalized\`
- `03_dataset\rejected\`
- `07_logs\onboarding_logs\`

## Script Rule

Scripts execute from `C:\v1.0-qpathformer_enterprise\scripts` and resolve path defaults through `scripts\path_layout.py`.

That keeps execution consistent even when the three path folders hold different artifact types.
