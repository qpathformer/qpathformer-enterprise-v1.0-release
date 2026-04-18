# Evidence Input Draft Summary

## What This File Is

This is the plain-language companion note for the generated enterprise CSC evidence input draft JSON.
The JSON is meant to be scorer-ready after review, while this Markdown file explains the draft in normal language.

## Plain-Language Summary

- Profile: sector.finance.v1
- Scenario: Finance Baseline
- CSC ID: csc_qpathformer-enterprise-access-mode-finance-draft-sector-finance-v1-baseline_20260415T192431Z
- Subject: Q-Pathformer Enterprise Access-Mode Finance Draft (Finance Baseline)
- Risk tier: high
- Sectors: finance
- Observation count: 16
- Evidence item count: 10

## Canonical Factor Model

This release keeps the canonical Access-PoD six-factor model and reads it through the enterprise three-layer binding.

- 6.1 Security & Resilience: dominant layer Layer 1 (Q-Pathformer execution and internal governance), supporting layers Layer 2
- 6.2 Adaptive Best Practice: dominant layer Layer 1 (Q-Pathformer execution and internal governance), supporting layers Layer 2
- 6.3 Operational Compliance: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.4 Human-Centric Oversight: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.5 Transparency & Impact: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.6 Fair Competition & Ecosystem Trust: dominant layer Layer 3 (Profile and scenario interpretation), supporting layers Layer 2 and Layer 1

## Telemetry Window

- Start: 2026-04-12T11:00:45Z
- End: 2026-04-13T09:52:08Z

## Evidence Bundle

- telemetry_export: `path_2_access_mode_canonical/02_signals/runtime_generated/signal_runtime_20260413T095208Z_77a538bc.json`
- attestation: `shared/registry/run_references/RTRUN-llm-runtime-registration-check-20260413T095208Z-77a538bc.runtime_signal_run_reference.json`
- policy_bundle: `shared/registry/run_registry.json`
- human_review_log: `path_2_access_mode_canonical/03_dataset/candidates/session-run-id2-20260411-1400-qpath-tr008-run/QPDS-PACKAGE-ID2_PREP/id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260412T104656Z/state2_review.json`
- attestation: `path_2_access_mode_canonical/03_dataset/candidates/session-run-id2-20260411-1400-qpath-tr008-run/QPDS-PACKAGE-ID2_PREP/id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260412T104656Z/state2_promotion_decision.json`
- attestation: `path_2_access_mode_canonical/03_dataset/candidates/session-run-id2-20260411-1400-qpath-tr008-run/QPDS-PACKAGE-ID2_PREP/id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260412T104656Z/state1_handoff.json`
- attestation: `path_2_access_mode_canonical/03_dataset/candidates/session-run-id2-20260411-1400-qpath-tr008-run/QPDS-PACKAGE-ID2_PREP/id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260412T104656Z/freeze/state1_freeze.json`
- dataset_card: `path_2_access_mode_canonical/03_dataset/training_packages/id2-20260411-1400-qpath-tr008-run__v10-1-path2-source-bridge__20260412T104656Z/state1_training_manifest.json`
- simulation_report: `shared/models/evaluation/model_runs/MRUN-grouped_sparse_e64-20260415T192312Z-v1repair/benchmark_summary.json`
- model_card: `shared/models/evaluation/model_runs/MRUN-grouped_sparse_e64-20260415T192312Z-v1repair/model_run_manifest.json`

## Next Use

Run the CSC builder against this JSON after review if you want to generate a certificate and report.

```powershell
py -3 .\scripts\build_csc_certificate.py --evidence-input "C:\v1.0-qpathformer_enterprise\shared\standards\access_pod\generated\evidence_input_drafts\sector-finance-v1-sector-finance-v1-baseline-2026-04-15t19-24-31z.evidence_input_draft.json"
```

## Related File

- Evidence input JSON: `C:\v1.0-qpathformer_enterprise\shared\standards\access_pod\generated\evidence_input_drafts\sector-finance-v1-sector-finance-v1-baseline-2026-04-15t19-24-31z.evidence_input_draft.json`
