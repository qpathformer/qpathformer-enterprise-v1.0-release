# `build_csc_evidence_input_draft.py`

This script is the second mapper phase for the Access-PoD enterprise bridge.

It reads a mapper blueprint, derives draft `metric_observations` from live Path 2
and shared registry artifacts, and then wraps those observations into a full
enterprise CSC evidence input JSON that is ready for review and then for the CSC
builder.

It also supports optional scenario overlays so the same canonical blueprint can
be run as baseline, `50/50`, `75/25`, or other documented sector variants.

## What It Reads

- `shared\standards\access_pod\mappers\*.mapper_blueprint.json`
- optional `shared\standards\access_pod\mappers\scenarios\*.scenario.json`
- latest or explicit Path 2 runtime signal artifacts
- latest or explicit shared run registry and runtime run reference
- latest or explicit Path 2 candidate package and training package
- latest or explicit model benchmark summary when present

## What It Writes

- `shared\standards\access_pod\generated\evidence_input_drafts\*.evidence_input_draft.json`
- `shared\standards\access_pod\generated\evidence_input_drafts\*.evidence_input_draft.md`

## Current Scope

- supports the current finance, healthcare, and `ai.and.emerging_tech.v1` mapper blueprints
- supports optional scenario overlays for canonical blueprints
- emits a scorer-ready enterprise evidence input draft with:
  - issuer
  - subject
  - scope
  - telemetry window
  - evidence bundle
  - draft metric observations
  - ISO alignment notes
  - scoring policy
- uses the same human-readable sidecar pattern as the CSC certificate and report flows

## Important Note

The emitted evidence input is still a draft. The artifact is structured so it
can be passed to `build_csc_certificate.py`, but the mapped metric values should
still be reviewed, especially where the derivation depends on proxy signals
rather than direct telemetry.
