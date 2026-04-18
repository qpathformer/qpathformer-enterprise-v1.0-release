# Session Metadata Shape Report (ID_3 four-session mode)

- Working folder: C:\v1.0-Access-mode\modes\ID_3_operator_4.sessions\ID_3_review_packs\2026-04-11\ID3-20260411-qpath-tr008-run\10_working
- Pack root: C:\v1.0-Access-mode\modes\ID_3_operator_4.sessions\ID_3_review_packs\2026-04-11\ID3-20260411-qpath-tr008-run
- Rule file: C:\v1.0-Access-mode\modes\ID_3_operator_4.sessions\scripts\rules\session_completeness.rule.json

## Session id normalization preview

| Record | Surface | Raw session_id | Normalized session_id |
|---|---|---|---|
| baseline | 20_corrected | ID2-20260411-1400-qpath-tr008-run | ID2-20260411-1400-qpath-tr008-run |
| ambiguity | 20_corrected | ID2-20260411-1400-qpath-tr008-run | ID2-20260411-1400-qpath-tr008-run |
| lifecycleboundary | 20_corrected | ID2-20260411-1400-qpath-tr008-run | ID2-20260411-1400-qpath-tr008-run |
| timepressure | 20_corrected | ID2-20260411-1400-qpath-tr008-run | ID2-20260411-1400-qpath-tr008-run |

## Completeness (diagnostic)

| Record | Points | Percent |
|---|---:|---:|
| baseline | 40/47 | 85.11% |
| ambiguity | 42/47 | 89.36% |
| lifecycleboundary | 42/47 | 89.36% |
| timepressure | 40/47 | 85.11% |
| average | - | 87.24% |

> Completeness is diagnostic only. Do not modify records based on score. Only minimal metadata correction is permitted before hash and freeze.

## Top-level metadata differences (key names only)

### ambiguity vs baseline
No top-level metadata differences detected.

### lifecycleboundary vs baseline
No top-level metadata differences detected.

### timepressure vs baseline
No top-level metadata differences detected.

## Optional issues (present but empty or invalid)

### baseline
- session.participants[0].name (present_empty)
- session.participants[0].role (present_empty)
- signoff.signed_by (present_empty)
- signoff.signed_at_utc (present_empty)
- session_status.notes (present_empty)

### ambiguity
- signoff.signed_by (present_empty)
- signoff.signed_at_utc (present_empty)
- session_status.notes (present_empty)

### lifecycleboundary
- signoff.signed_by (present_empty)
- signoff.signed_at_utc (present_empty)
- session_status.notes (present_empty)

### timepressure
- session.participants[0].name (present_empty)
- session.participants[0].role (present_empty)
- signoff.signed_by (present_empty)
- signoff.signed_at_utc (present_empty)
- session_status.notes (present_empty)

## Required-field failures (diagnostic)

### baseline
- session_status.intended_reuse

### ambiguity
- session_status.intended_reuse

### lifecycleboundary
- session_status.intended_reuse

### timepressure
- session_status.intended_reuse

