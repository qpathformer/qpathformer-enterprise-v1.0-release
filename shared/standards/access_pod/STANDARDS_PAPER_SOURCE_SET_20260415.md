# Standards Paper Source Set - 2026-04-15

## Purpose

This note declares which Access-PoD artifacts the `v1.0` standards paper should
treat as the active source set after release-set normalization.

The paper should cite the active set below and avoid treating archived draft
runs, scenario experiments, or superseded generated outputs as the current
release baseline.

## Active `v1.0` Source Set

### Finance

Use as the active finance baseline:

- report:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-access-mode-finance-draft-sector-finance-v1-baseline-sector-finance-v1__20260415T192431Z.csc_report.json`
- report summary:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-access-mode-finance-draft-sector-finance-v1-baseline-sector-finance-v1__20260415T192431Z.csc_report.md`
- certificate:
  `shared/standards/access_pod/generated/certificates/qpathformer-enterprise-access-mode-finance-draft-sector-finance-v1-baseline-sector-finance-v1__20260415T192431Z.csc_certificate.json`
- certificate summary:
  `shared/standards/access_pod/generated/certificates/qpathformer-enterprise-access-mode-finance-draft-sector-finance-v1-baseline-sector-finance-v1__20260415T192431Z.csc_certificate.md`
- evidence input draft:
  `shared/standards/access_pod/generated/evidence_input_drafts/sector-finance-v1-sector-finance-v1-baseline-2026-04-15t19-24-31z.evidence_input_draft.json`
- evidence input draft summary:
  `shared/standards/access_pod/generated/evidence_input_drafts/sector-finance-v1-sector-finance-v1-baseline-2026-04-15t19-24-31z.evidence_input_draft.md`
- metric observation draft:
  `shared/standards/access_pod/generated/metric_observation_drafts/sector-finance-v1-sector-finance-v1-baseline-2026-04-15t19-24-19z.metric_observation_draft.json`
- metric observation draft summary:
  `shared/standards/access_pod/generated/metric_observation_drafts/sector-finance-v1-sector-finance-v1-baseline-2026-04-15t19-24-19z.metric_observation_draft.md`

Release reading:

- mapper-driven baseline using repaired live `e64` benchmark evidence
- active finance default for `v1.0`
- `composite_score = 91.9`
- `CSC level = 5`
- note: `f6.1` and `f6.5` should be described as provisional saturated
  governance-chain factors, not as absolute validated perfection

### Healthcare

Use as the active healthcare baseline:

- report:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-access-mode-healthcare-draft-sector-healthcare-v1-baseline-sector-healthcare-v1__20260415T192523Z.csc_report.json`
- report summary:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-access-mode-healthcare-draft-sector-healthcare-v1-baseline-sector-healthcare-v1__20260415T192523Z.csc_report.md`
- certificate:
  `shared/standards/access_pod/generated/certificates/qpathformer-enterprise-access-mode-healthcare-draft-sector-healthcare-v1-baseline-sector-healthcare-v1__20260415T192523Z.csc_certificate.json`
- certificate summary:
  `shared/standards/access_pod/generated/certificates/qpathformer-enterprise-access-mode-healthcare-draft-sector-healthcare-v1-baseline-sector-healthcare-v1__20260415T192523Z.csc_certificate.md`
- evidence input draft:
  `shared/standards/access_pod/generated/evidence_input_drafts/sector-healthcare-v1-sector-healthcare-v1-baseline-2026-04-15t19-25-23z.evidence_input_draft.json`
- evidence input draft summary:
  `shared/standards/access_pod/generated/evidence_input_drafts/sector-healthcare-v1-sector-healthcare-v1-baseline-2026-04-15t19-25-23z.evidence_input_draft.md`
- metric observation draft:
  `shared/standards/access_pod/generated/metric_observation_drafts/sector-healthcare-v1-sector-healthcare-v1-baseline-2026-04-15t19-25-06z.metric_observation_draft.json`
- metric observation draft summary:
  `shared/standards/access_pod/generated/metric_observation_drafts/sector-healthcare-v1-sector-healthcare-v1-baseline-2026-04-15t19-25-06z.metric_observation_draft.md`

Release reading:

- mapper-driven tightened baseline using repaired live `e64` benchmark evidence
- active healthcare default for `v1.0`
- `composite_score = 84.6`
- `CSC level = 4`

### Public

Use as the active public release example:

- report:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-access-mode-runtime-sector-public-v1__20260413T100500Z.csc_report.json`
- report summary:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-access-mode-runtime-sector-public-v1__20260413T100500Z.csc_report.md`
- certificate:
  `shared/standards/access_pod/generated/certificates/qpathformer-enterprise-access-mode-runtime-sector-public-v1__20260413T100500Z.csc_certificate.json`
- certificate summary:
  `shared/standards/access_pod/generated/certificates/qpathformer-enterprise-access-mode-runtime-sector-public-v1__20260413T100500Z.csc_certificate.md`
- evidence input example:
  `shared/standards/access_pod/examples/enterprise_csc_evidence_input.example.json`

Release reading:

- curated `v1.0` standards example
- public example is now normalized to the active sidecar / presentation pattern
- no dedicated `sector.public.v1` mapper blueprint exists in the repo at this
  release point

### AI and Emerging Tech

Use as the active AI / emerging-tech release example:

- report:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-ai-emerging-tech-rollout-ai-and-emerging-tech-v1__20260413T122000Z.csc_report.json`
- report summary:
  `shared/standards/access_pod/generated/reports/qpathformer-enterprise-ai-emerging-tech-rollout-ai-and-emerging-tech-v1__20260413T122000Z.csc_report.md`
- certificate:
  `shared/standards/access_pod/generated/certificates/qpathformer-enterprise-ai-emerging-tech-rollout-ai-and-emerging-tech-v1__20260413T122000Z.csc_certificate.json`
- evidence input example:
  `shared/standards/access_pod/examples/enterprise_csc_evidence_input.ai_and_emerging_tech_v1.example.json`

Release reading:

- curated `v1.0` standards example
- the mapper rerun is retained as research but is not the active release
  baseline because coverage remains too thin and `CSC level` falls to `1`

## Paper Drafting Rule

When writing the standards paper:

- use the active source set above for the main release narrative
- reference archived scenario runs and superseded drafts only in research,
  limitations, or appendix sections
- do not mix archived draft scores with the active baseline statements in the
  executive summary or sector summary chapters

## Related Release Notes

- `shared/standards/access_pod/CANONICAL_FACTOR_LAYER_BINDING_v1_0.md`
- `shared/standards/access_pod/README.md`

Historical normalization, cleanup, scenario, and comparison notes were moved
out of the `v1.0` release tree during final release cleanup.
