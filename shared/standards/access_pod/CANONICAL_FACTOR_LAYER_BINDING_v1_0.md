# Canonical Factor Layer Binding v1.0

Date: 2026-04-15

## Purpose

This table defines how the canonical Access-PoD CSC factor model is bound to
the enterprise three-layer release model for `v1.0`.

The six factors remain canonical.

The three layers explain where the evidence comes from and how the release
should be interpreted.

## Layer Reference

- `Layer 1`
  Q-Pathformer execution, internal runtime controls, governed dataset/package
  flow, and the current `grouped_sparse_e64` benchmark summary / run-manifest
  reference line
- `Layer 2`
  organization, operator, and company governance controls such as approvals,
  audit, ownership, policy, review, and accountability
- `Layer 3`
  profile and scenario interpretation such as sector baselines and controlled
  comparison overlays

## Canonical Binding Table

| Factor | Canonical name | Dominant layer for `v1.0` | Layer 1 role | Layer 2 role | Layer 3 role |
| --- | --- | --- | --- | --- | --- |
| `6.1` | Security & Resilience | `Layer 1` | runtime safety, containment, integrity, constraint enforcement | authorization posture and review gates support the score | sector profile may tighten gates, but does not redefine the source evidence |
| `6.2` | Adaptive Best Practice | `Layer 1` | benchmark readiness, privacy checks, telemetry completeness, key-management and hardening proxies | patching, tuning, and control process maturity support the score | profile may change emphasis, but baseline evidence remains technical and operational |
| `6.3` | Operational Compliance | `Layer 2` | lineage, provenance, registry health, topology visibility support compliance traceability | policy traceability, change approvals, jurisdiction and controlled lifecycle semantics dominate | scenarios should not replace compliance meaning; they only alter interpretation emphasis |
| `6.4` | Human-Centric Oversight | `Layer 2` | routing triggers and runtime escalation signals feed oversight decisions | human review, audit evidence, escalation handling, approval traceability, and oversight load dominate | profile gates can raise or lower strictness for high-impact domains |
| `6.5` | Transparency & Impact | `Layer 2` | runtime outputs, harm signals, and model-limit artifacts provide evidence inputs | explanation quality, complaint handling, remediation, transparency posture, and impact review dominate | profiles may shift which impacts matter most, but not the underlying factor intent |
| `6.6` | Fair Competition & Ecosystem Trust | `Layer 3` | marketplace integrity, provenance, and execution evidence contribute supporting signals | partner attestations, policy posture, and audit interoperability provide governance support | sector baseline or scenario interpretation dominates the release reading for this factor |

## Metric Family Reading

Use this shorthand in release notes and sidecars:

- `SEC_*` and most `HARD_*` metrics read primarily as `Layer 1`
- `COMP_*`, `GOV_*`, and most `TRN_*` metrics read primarily as `Layer 2`
- `SECTOR_*` metrics read primarily as `Layer 3`, even when they are fed by
  Layer 1 and Layer 2 supporting evidence

This is a release-reading rule, not a schema change.

## Current Enterprise Binding

For the current live repo, the three-layer factor model binds to:

- Path 2 runtime signals and routing artifacts
- shared run registry and run references
- review, promotion, handoff, freeze, and training package artifacts
- `gpt-oss:20b` runtime signal emitter
- `grouped_sparse_e64` benchmark summaries and model run manifests as the
  current enterprise benchmark reference line

## Release Rule

For `v1.0`:

- keep the canonical six Access-PoD factors
- use this table to explain the enterprise release
- do not replace the factor ontology with six new layers or six new factors
- if the factor model is ever reworked, do that in a later extension release
  and not inside the `v1.0` baseline
