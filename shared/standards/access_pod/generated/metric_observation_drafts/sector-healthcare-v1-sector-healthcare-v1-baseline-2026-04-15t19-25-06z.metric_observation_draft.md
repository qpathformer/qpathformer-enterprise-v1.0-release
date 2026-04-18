# Metric Observation Draft Summary

## What This File Is

This is the plain-language companion note for the generated metric observation draft JSON.
The JSON is the structured draft that can be reviewed, edited, and then folded into an enterprise CSC evidence input.

## Plain-Language Summary

- Profile: sector.healthcare.v1
- Blueprint: shared/standards/access_pod/mappers/sector.healthcare.v1.mapper_blueprint.json
- Scenario: Healthcare Baseline
- Observation count: 12
- Generated at: 2026-04-15T19:25:06Z

## Canonical Factor Model

This release keeps the canonical Access-PoD six-factor model and reads it through the enterprise three-layer binding.

- 6.1 Security & Resilience: dominant layer Layer 1 (Q-Pathformer execution and internal governance), supporting layers Layer 2
- 6.2 Adaptive Best Practice: dominant layer Layer 1 (Q-Pathformer execution and internal governance), supporting layers Layer 2
- 6.3 Operational Compliance: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.4 Human-Centric Oversight: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.5 Transparency & Impact: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.6 Fair Competition & Ecosystem Trust: dominant layer Layer 3 (Profile and scenario interpretation), supporting layers Layer 2 and Layer 1

## Source Artifacts Used

- benchmark_summary_path: `shared/models/evaluation/model_runs/MRUN-grouped_sparse_e64-20260415T192312Z-v1repair/benchmark_summary.json`
- blueprint_path: `shared/standards/access_pod/mappers/sector.healthcare.v1.mapper_blueprint.json`
- candidate_package_dir: `path_2_access_mode_canonical/03_dataset/candidates/session-run-id2-20260411-1400-qpath-tr008-run/QPDS-PACKAGE-ID2_PREP/id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260412T104656Z`
- run_reference_path: `shared/registry/run_references/RTRUN-llm-runtime-registration-check-20260413T095208Z-77a538bc.runtime_signal_run_reference.json`
- run_registry_path: `shared/registry/run_registry.json`
- runtime_signal_path: `path_2_access_mode_canonical/02_signals/runtime_generated/signal_runtime_20260413T095208Z_77a538bc.json`
- scenario_path: `shared/standards/access_pod/mappers/scenarios/sector.healthcare.v1.baseline.scenario.json`
- training_package_dir: `path_2_access_mode_canonical/03_dataset/training_packages/id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260412T104656Z`

## Draft Metrics

- SEC_OUTPUT_SAFETY_VIOL_RATE: value 0.001 with confidence 0.56, dominant evidence layer Layer 1
  Proxy from low ambiguity, zero review exceptions, and mandatory human review in the live Path 2 governance chain.
- SEC_EVIDENCE_INTEGRITY_PASS: value 1.0 with confidence 0.90, dominant evidence layer Layer 1
  Derived from the presence of core governed artifacts and matching registry references for the live runtime signal chain.
- HARD_PRIVACY_TEST_PASS_RATE: value 0.97 with confidence 0.42, dominant evidence layer Layer 1
  Policy proxy from controlled training posture and human-review requirements, with a modest uplift when the linked benchmark path is clean and metadata-rich, but still reduced when outputs remain non-queryable. Replace with explicit privacy benchmark telemetry when available.
- HARD_TELEMETRY_COMPLETENESS: value 1.0 with confidence 0.74, dominant evidence layer Layer 1
  Derived from runtime, routing, review, freeze, and training telemetry continuity, with a small uplift when the linked benchmark path is clean and metadata-rich, but still penalized when outputs remain non-queryable.
- COMP_POLICY_TRACE_COVERAGE: value 0.978 with confidence 0.76, dominant evidence layer Layer 2
  Derived from the governed approval chain, policy-first review posture, and frozen-manifest linkage, then capped for proxy-only evidence and reduced when outputs remain non-queryable or the linked benchmark is not yet in a clean success state.
- COMP_MODEL_LINEAGE_COVERAGE: value 0.975 with confidence 0.78, dominant evidence layer Layer 2
  Derived from lineage, approval, freeze, and registry links across the Path 2 package chain, then bounded so proxy-only lineage evidence does not score as fully complete while runtime outputs remain non-queryable or linked benchmark evidence is still degraded.
- GOV_HIL_REVIEW_COVERAGE: value 0.9802 with confidence 0.82, dominant evidence layer Layer 2
  Derived from required human review, approved STATE_2 review, full review readiness, and a small governed sample-size floor so human oversight coverage stays strong without saturating purely from approval-chain completeness.
- GOV_AUDIT_EVIDENCE_COVERAGE: value 0.98 with confidence 0.80, dominant evidence layer Layer 2
  Derived from the presence of review, promotion, handoff, freeze, registry, runtime, and training artifacts, then bounded by cross-artifact evidence quality so audit coverage does not saturate from artifact presence alone.
- TRN_EXPLAIN_COMPLETE: value 1.0 with confidence 0.63, dominant evidence layer Layer 2
  Proxy from structured runtime summaries plus the metadata-rich training export package.
- TRN_HARM_EVENT_RATE: value 0.5 with confidence 0.47, dominant evidence layer Layer 2
  Low provisional harm-event rate derived from zero review exceptions and mandatory human oversight. Replace with validated harm telemetry when available.
- SECTOR_POLICY_PASS_RATE: value 0.97 with confidence 0.70, dominant evidence layer Layer 3
  Draft sector policy pass proxy from configurable sector evidence weighting, bounded so execution-independent approval signals do not overstate live operational readiness. Current blend: sector policy pass evidence 100%.
- SECTOR_AUDIT_INTEROP_SCORE: value 93.5 with confidence 0.66, dominant evidence layer Layer 3
  Draft audit interoperability score from configurable sector evidence weighting, with readiness penalties when queryable outputs and clean linked benchmark evidence are still missing. Current blend: audit interoperability evidence 100%.

## Notes

- These observations are first-pass governed drafts derived from live Path 2 and shared registry artifacts.
- Observations marked by proxy-style derivation methods should be reviewed before being promoted into a formal CSC evidence input.
- Scenario in use: Healthcare Baseline (sector.healthcare.v1.baseline).

## Related File

- Draft JSON: `C:\v1.0-qpathformer_enterprise\shared\standards\access_pod\generated\metric_observation_drafts\sector-healthcare-v1-sector-healthcare-v1-baseline-2026-04-15t19-25-06z.metric_observation_draft.json`
