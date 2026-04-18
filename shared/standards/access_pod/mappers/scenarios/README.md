# Mapper Scenarios

These files are lightweight scenario overlays for canonical mapper blueprints.

They exist so the repo can keep one canonical source blueprint while testing
multiple sector-weighting or policy variants without copying whole folders.

## Current Finance Scenarios

- `sector.finance.v1.baseline.scenario.json`
- `sector.finance.v1.50_50.scenario.json`
- `sector.finance.v1.75_25.scenario.json`

## Current Healthcare Scenarios

- `sector.healthcare.v1.baseline.scenario.json`
- `sector.healthcare.v1.clinical_safety_heavy.scenario.json`
- `sector.healthcare.v1.interop_audit_heavy.scenario.json`

These healthcare scenarios are scaffolded for comparison only and have not been
run yet. The current release default remains the healthcare baseline.

## What A Scenario Can Change

- `source_mix` weights for sector-sensitive metrics
- later, other per-metric overlay settings if the standards workstream needs them

## Intended Use

Run the canonical finance blueprint with one scenario overlay at a time and
keep the generated JSON plus Markdown sidecars as immutable evidence for
comparison.
