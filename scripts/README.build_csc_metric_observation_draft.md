# `build_csc_metric_observation_draft.py`

This script is the first executable Access-PoD mapper runner for the enterprise
platform.

It reads a mapper blueprint, inspects live Path 2 and shared registry artifacts,
and emits a draft `metric_observations` JSON file plus a plain-language Markdown
summary for review.

It can also apply a lightweight scenario overlay so one canonical blueprint can
be tested under multiple sector-weighting variants such as baseline, `50/50`,
and `75/25`.

## What It Reads

- `shared\standards\access_pod\mappers\*.mapper_blueprint.json`
- optional `shared\standards\access_pod\mappers\scenarios\*.scenario.json`
- latest or explicit Path 2 runtime signal artifacts
- latest or explicit shared run registry and runtime run reference
- latest or explicit Path 2 candidate package and training package
- latest or explicit model benchmark summary when present

## What It Writes

- `shared\standards\access_pod\generated\metric_observation_drafts\*.metric_observation_draft.json`
- `shared\standards\access_pod\generated\metric_observation_drafts\*.metric_observation_draft.md`

## Current Scope

- supports the current finance, healthcare, and `ai.and.emerging_tech.v1` mapper blueprints
- supports optional scenario overlays for canonical blueprints
- auto-discovers the latest live Path 2 and registry artifacts unless overrides are provided
- emits draft observations with confidence, derivation method, source artifact references, and review notes
- keeps low-confidence proxy values explicit when the live repo does not yet expose a direct telemetry source

## Why The Markdown Sidecar Exists

Each generated JSON should have a human-readable companion note so governance,
standards, and operations reviewers do not need to read raw JSON first.

This script uses the shared Access-PoD human-readable sidecar renderer so the
output format stays consistent with the CSC certificate and report flows.
