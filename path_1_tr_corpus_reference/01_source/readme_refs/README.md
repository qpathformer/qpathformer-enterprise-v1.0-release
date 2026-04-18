# Q-Pathformer DEV - Development Phase Boundary Reference

## Purpose

This file is a compact developer reference for how source markdown should behave inside the project.

## Current Development Position

The project is preparing a clean release root that can rerun all three lifecycle paths from source.

That means source markdown must favor:

- phase clarity
- explicit non-claims
- clean script naming
- direct connection to the next lifecycle stage

## Source Markdown Structure

A high-signal source markdown file should follow this order:

1. purpose
2. phase responsibility
3. non-responsibility
4. phase connection to the next output
5. key script or artifact names
6. non-claims and governance boundary

## Why This Matters

Path 1 dataset preparation ingests markdown sections and uses:

- section titles
- file names
- relative paths
- command mentions

This means unclear headings or duplicated historical files can reduce dataset quality.

## Naming Rule

Keep stable filenames where the builder uses explicit name matching.

Current examples that should remain stable unless the script is updated:

- `main_readme.md`
- `Q-Pathformer DEV — End-to-End Command Profile.md`
- `Q-Pathformer DEV — End-to-End Lifecycle → Fine-Tuning Runbook.md`

If filenames are changed later, update the allowlists in `scripts\build_tr_finetune_dataset.py` at the same time.
