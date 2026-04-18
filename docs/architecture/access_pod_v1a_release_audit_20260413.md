# Access-PoD v1a Release Audit

Date: 2026-04-13

Source archive:

- `C:\Users\Alnotrea\Downloads\access-pod-artifacts-v1a-pack.zip`

## Summary

This note records why the Access-PoD `v1a` release was added to the
`v1.0` enterprise repository and which integration approach was used.

It should be read as a release audit and provenance record.

It should not be read as:

- implementation advice for developers
- a forward roadmap
- a recommendation to rewrite the upstream pack

What was done in this release:

- the upstream Access-PoD `v1a` pack was preserved under a dedicated standards
  namespace
- the vendor snapshot was kept intact as the canonical public-review baseline
- enterprise bridge, mapping, and generated CSC work were kept outside the
  vendored release

Why it was added:

- the pack already contains a usable standards-facing contract layer for CSC
  artifacts
- it provides a public-review governance vocabulary that complements the more
  operational enterprise execution layer
- it preserves provenance for the standards-facing side of the release

This pack is not just a concept drop. It already contains:

- an artifact manifest with checksums
- an MIT license
- a machine-readable CSC certificate example
- a machine-readable metric catalog
- sector weighting profiles
- a certificate schema
- a metric catalog schema

The pack is clearly positioned as a model-agnostic and execution-independent governance release for public review, not as a finished runtime platform.

## What Is Already Mature

The JSON layer is materially stronger than a typical first public draft:

- `schemas/csc-certificate.schema_v1a.json`
  Strong certificate structure with issuer, subject, scope, assessment, evidence, signature, and links.
- `schemas/csc_metric_catalog_schema_v1a.json`
  Basic but usable validation for metric catalog payloads.
- `catalogs/csc_metric_catalog_v1a.json`
  Defines 60 metrics across six factors (`6.1` through `6.6`), with normalization methods, thresholds, telemetry source hints, and event field expectations.
- `profiles/csc_sector_profiles_v1a.json`
  Adds sector-specific weighting and gate thresholds for healthcare, finance, and public-sector contexts.
- `examples/example_csc_certificate_v1a.json`
  Demonstrates factor scoring, composite score, CSC level, risk tier, gates, ISO alignment, evidence, and signing envelope.

Validation check:

- the example certificate validates against the certificate schema
- the metric catalog validates against the metric catalog schema

## What Is Missing Or Still Early

The pack is strong on contracts, but it is not yet a complete execution layer.

Missing or intentionally deferred pieces:

- no executable scoring engine is included
- no schema is included for `profiles/csc_sector_profiles_v1a.json`
- no schema is included for `manifest_v1a_pack.json`
- the catalog schema is fairly shallow for nested scoring structures
- the example certificate uses placeholder evidence digests and placeholder signature values
- the README names some files generically, while the actual archive uses explicit `v1a` filenames
- the manifest contains a machine-local `root_directory`, which is fine for provenance but not ideal as a portable release invariant

## Fit With The Current Enterprise Platform

The current `v1.0` enterprise repo is more operationally mature than the Access-PoD release in these areas:

- governed three-path lifecycle execution
- runtime signal generation and routing
- dataset promotion, freeze, and registry flow
- training-package preparation
- model evaluation runs and latency benchmarking

The Access-PoD release is stronger in a different layer:

- standards-facing governance vocabulary
- portable certificate shape
- cross-sector weighting logic
- explicit public-review artifact structure

Release reading:

- Access-PoD v1a = external/public standards contract layer
- current enterprise platform = internal governed execution and evidence-generation layer

In this release, the platform produces evidence and telemetry, while
Access-PoD provides the standards-facing structure used to express selected
outputs for external review and comparative CSC-style reporting.

## Approach Used In This Release

The approach used for `v1.0` was preserve-and-bridge, not replace-and-rewrite.

Specifically:

- the Access-PoD pack was preserved under a dedicated standards namespace
- the original JSON artifacts were kept unchanged as the canonical public-review
  release layer
- enterprise-side bridge logic maps live platform telemetry and governance
  artifacts into CSC-aligned structures outside the vendor snapshot

Current enterprise evidence sources used around that standards layer:

- runtime signals from Path 2
  Candidate source for SAPP/runtime-aligned metrics and review readiness traces.
- state registries and freeze artifacts
  Candidate source for evidence bundle references, lineage, and audit posture.
- model evaluation outputs under `shared\models\evaluation`
  Candidate source for selected metric contributions and benchmark-backed factor scoring.
- onboarding and adapter artifacts from Path 3
  Candidate source for external evidence admission and governance packaging.

## Namespace Location

The preserved local standards namespace for this release is:

- `shared/standards/access_pod/vendor/access-pod-artifacts-core/v1a/`

This keeps the upstream release intact while leaving room for enterprise-side
bridge and scoring work outside the vendor snapshot.

## Release Boundary

This note records the release approach only.

- It does not prescribe the next engineering tasks.
- It does not treat the vendored pack as a development surface to modify.
- It records that standards scoring and lifecycle gating were kept as separate
  layers in the release reading.

The resulting release posture is:

- public standards artifacts from Access-PoD v1a
- operational governance execution from the three-path platform
- enterprise bridge and generated CSC outputs layered around, not inside, the
  original public-review pack
