# CSC Report Summary

## What This File Is

This is the plain-language companion note for the generated CSC scoring report JSON.
It explains the result, gates, and coverage without making you read the raw JSON first.

## Plain-Language Summary

- Profile: sector.finance.v1
- CSC ID: csc_qpathformer-enterprise-access-mode-finance-draft-sector-finance-v1-baseline_20260415T192431Z
- Composite score: 91.9
- CSC level: 5
- Risk tier: high
- Observed metrics: 16 out of 60
- Overall coverage ratio: 0.27

## Canonical Factor Model

This release keeps the canonical Access-PoD six-factor model and reads it through the enterprise three-layer binding.

- 6.1 Security & Resilience: dominant layer Layer 1 (Q-Pathformer execution and internal governance), supporting layers Layer 2
- 6.2 Adaptive Best Practice: dominant layer Layer 1 (Q-Pathformer execution and internal governance), supporting layers Layer 2
- 6.3 Operational Compliance: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.4 Human-Centric Oversight: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.5 Transparency & Impact: dominant layer Layer 2 (Organization and company governance), supporting layers Layer 1
- 6.6 Fair Competition & Ecosystem Trust: dominant layer Layer 3 (Profile and scenario interpretation), supporting layers Layer 2 and Layer 1

## Gate Check

- No critical failures: Yes
- Minimum telemetry met: Yes
- F6.1 threshold met: Yes
- F6.4 threshold met: Yes
- All factor minimums met: Yes
- Sector validation met: Yes

## Factor Results

- 6.1 Security & Resilience: score 100.0, confidence 0.56, dominant evidence layer Layer 1 (Q-Pathformer execution and internal governance)
  Reading note: runtime safety, integrity, and containment evidence dominate this factor.
  Top metrics: SEC_POLICY_ENFORCE_SUCCESS, SEC_EVIDENCE_INTEGRITY_PASS
- 6.2 Adaptive Best Practice: score 79.2, confidence 0.43, dominant evidence layer Layer 1 (Q-Pathformer execution and internal governance)
  Reading note: hardening, privacy, telemetry, and technical readiness evidence dominate this factor.
  Top metrics: HARD_TELEMETRY_COMPLETENESS, HARD_PRIVACY_TEST_PASS_RATE, HARD_KEY_MGMT_HEALTH
- 6.3 Operational Compliance: score 87.5, confidence 0.56, dominant evidence layer Layer 2 (Organization and company governance)
  Reading note: policy traceability and lifecycle compliance dominate this factor.
  Top metrics: COMP_CHANGE_APPROVAL_TRACE, COMP_MODEL_LINEAGE_COVERAGE
- 6.4 Human-Centric Oversight: score 90.0, confidence 0.56, dominant evidence layer Layer 2 (Organization and company governance)
  Reading note: human review, audit, escalation, and approval governance dominate this factor.
  Top metrics: GOV_MODEL_APPROVAL_TRACE, GOV_AUDIT_EVIDENCE_COVERAGE
- 6.5 Transparency & Impact: score 100.0, confidence 0.46, dominant evidence layer Layer 2 (Organization and company governance)
  Reading note: explanation, harm handling, and transparency governance dominate this factor.
  Top metrics: TRN_DECISION_TRACE_RATE, TRN_EXPLAIN_COMPLETE
- 6.6 Fair Competition & Ecosystem Trust: score 93.2, confidence 0.52, dominant evidence layer Layer 3 (Profile and scenario interpretation)
  Reading note: sector profile and scenario interpretation dominate the release reading for this factor.
  Top metrics: SECTOR_PARTNER_ATTEST_RATE, SECTOR_POLICY_PASS_RATE, SECTOR_AUDIT_INTEROP_SCORE

## Coverage By Factor

- 6.1 Security & Resilience: 2 of 10 metrics observed
- 6.2 Adaptive Best Practice: 4 of 10 metrics observed
- 6.3 Operational Compliance: 2 of 10 metrics observed
- 6.4 Human-Centric Oversight: 2 of 10 metrics observed
- 6.5 Transparency & Impact: 2 of 10 metrics observed
- 6.6 Fair Competition & Ecosystem Trust: 4 of 10 metrics observed

## Alerts

- Warning metrics: None
- Critical metrics: None

## Related File

- Report JSON: `C:\v1.0-qpathformer_enterprise\shared\standards\access_pod\generated\reports\qpathformer-enterprise-access-mode-finance-draft-sector-finance-v1-baseline-sector-finance-v1__20260415T192431Z.csc_report.json`
