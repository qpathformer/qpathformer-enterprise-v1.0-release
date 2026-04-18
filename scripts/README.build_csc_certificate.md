# `build_csc_certificate.py`

This script is the enterprise bridge for the vendored Access-PoD `v1a` release.
It reads the standards-side CSC metric catalog and sector profiles, combines them
with enterprise evidence inputs, and generates a CSC certificate plus a scoring
report for local platform review.

## What It Reads

- `shared\standards\access_pod\vendor\access-pod-artifacts-core\v1a\catalogs\csc_metric_catalog_v1a.json`
- `shared\standards\access_pod\vendor\access-pod-artifacts-core\v1a\profiles\csc_sector_profiles_v1a.json`
- `shared\standards\access_pod\profiles\enterprise_sector_profile_extensions.json`
- `shared\standards\access_pod\schemas\enterprise_csc_evidence_input.schema.json`
- an enterprise evidence input JSON passed with `--evidence-input`

## What It Writes

- `shared\standards\access_pod\generated\certificates\*.csc_certificate.json`
- `shared\standards\access_pod\generated\certificates\*.csc_certificate.md`
- `shared\standards\access_pod\generated\reports\*.csc_report.json`
- `shared\standards\access_pod\generated\reports\*.csc_report.md`

## Current Scope

- preserves the upstream Access-PoD `v1a` pack as the external standards baseline
- merges local enterprise profile extensions over the vendored `v1a` sector profiles when present
- computes normalized metric scores from enterprise observations
- builds factor scores, CSC composite score, gates, and CSC level
- resolves local evidence file paths and computes `sha256` digests automatically
- emits a placeholder enterprise signature block for review workflows
- emits Markdown sidecar summaries so each final JSON artifact has a plain-language companion note

This script is intentionally platform-side logic. It is not part of the
vendored `v1a` release and should stay outside the preserved upstream snapshot.

## Next Phase Dev

1. Add a mapper that derives `metric_observations` directly from live platform artifacts such as Path 2 runtime signals, run registry entries, freeze outputs, and model evaluation summaries.
2. Add more enterprise evidence examples for sector variants such as finance and healthcare so scoring can be checked against more than the current public-sector example.
3. Tighten schema coverage with local manifest/profile bridge schemas for enterprise inputs, generated certificate packaging, and evidence bundle provenance.
4. Replace the placeholder signature envelope with real signing and verification flows, including enterprise key handling and certificate validation checks.
5. Add scoring trace output that explains how each observation affected factor scores, warnings, critical gates, and final CSC level for audit review.
6. Decide which benchmark outputs from `shared\models\evaluation` should become first-class CSC evidence inputs so model benchmarking is tied to standards scoring in a controlled way.

## Command Reference

Use the command guide at `docs\execution\access_pod_csc_commands.md` for the
current run commands and override examples.
