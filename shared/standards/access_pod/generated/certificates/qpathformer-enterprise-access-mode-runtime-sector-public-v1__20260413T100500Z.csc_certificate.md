# CSC Certificate Summary

## What This File Is

This is the plain-language companion note for the generated CSC certificate JSON.
The JSON remains the authoritative machine-readable artifact. This Markdown file explains the result in normal project language.

## Plain-Language Summary

- Subject: Q-Pathformer Enterprise Access-Mode Runtime
- Profile: sector.public.v1
- CSC ID: csc_qpathformer_enterprise_access_mode_runtime_demo_20260413
- Score: 93.0
- CSC level: 5
- Risk tier: medium
- Status: active
- Sectors: public

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

- 6.1 Security & Resilience: score 89.7, confidence 0.57, dominant evidence layer Layer 1 (Q-Pathformer execution and internal governance)
  Reading note: runtime safety, integrity, and containment evidence dominate this factor.
  Top metrics: SEC_FALSE_NEG_RATE, SEC_ATTACK_DETECT_RATE
- 6.2 Adaptive Best Practice: score 93.5, confidence 0.54, dominant evidence layer Layer 1 (Q-Pathformer execution and internal governance)
  Reading note: hardening, privacy, telemetry, and technical readiness evidence dominate this factor.
  Top metrics: HARD_PATCH_LATENCY, HARD_REDTEAM_PASS_RATE
- 6.3 Operational Compliance: score 90.8, confidence 0.57, dominant evidence layer Layer 2 (Organization and company governance)
  Reading note: policy traceability and lifecycle compliance dominate this factor.
  Top metrics: COMP_TIME_TO_ADAPT, COMP_POLICY_TRACE_COVERAGE
- 6.4 Human-Centric Oversight: score 95.0, confidence 0.55, dominant evidence layer Layer 2 (Organization and company governance)
  Reading note: human review, audit, escalation, and approval governance dominate this factor.
  Top metrics: GOV_HUMAN_LOAD_INDEX, GOV_HIL_REVIEW_COVERAGE
- 6.5 Transparency & Impact: score 95.0, confidence 0.53, dominant evidence layer Layer 2 (Organization and company governance)
  Reading note: explanation, harm handling, and transparency governance dominate this factor.
  Top metrics: TRN_EXPLAIN_COMPLETE, TRN_USER_COMPREHENSION
- 6.6 Fair Competition & Ecosystem Trust: score 93.7, confidence 0.52, dominant evidence layer Layer 3 (Profile and scenario interpretation)
  Reading note: sector profile and scenario interpretation dominate the release reading for this factor.
  Top metrics: SECTOR_REPUTATION_STABILITY, SECTOR_POLICY_PASS_RATE

## Related Files

- Certificate JSON: `C:\v1.0-qpathformer_enterprise\shared\standards\access_pod\generated\certificates\qpathformer-enterprise-access-mode-runtime-sector-public-v1__20260413T100500Z.csc_certificate.json`
- Report JSON: `C:\v1.0-qpathformer_enterprise\shared\standards\access_pod\generated\reports\qpathformer-enterprise-access-mode-runtime-sector-public-v1__20260413T100500Z.csc_report.json`
- Report summary Markdown: `C:\v1.0-qpathformer_enterprise\shared\standards\access_pod\generated\reports\qpathformer-enterprise-access-mode-runtime-sector-public-v1__20260413T100500Z.csc_report.md`

## Reading Note

Use the certificate JSON for integration or audit tooling.
Use the report JSON and its Markdown summary when you want the scoring breakdown and gate reasoning in more detail.
