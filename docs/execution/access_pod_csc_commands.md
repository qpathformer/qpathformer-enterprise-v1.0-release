# Access-PoD CSC Commands

Run from:

- `C:\v1.0-qpathformer_enterprise`

## Build A CSC Certificate From Enterprise Evidence

```powershell
py -3 .\scripts\build_csc_certificate.py `
  --evidence-input .\shared\standards\access_pod\examples\enterprise_csc_evidence_input.example.json
```

Default outputs:

- `shared\standards\access_pod\generated\certificates\*.csc_certificate.json`
- `shared\standards\access_pod\generated\certificates\*.csc_certificate.md`
- `shared\standards\access_pod\generated\reports\*.csc_report.json`
- `shared\standards\access_pod\generated\reports\*.csc_report.md`

Inputs used by default:

- vendored metric catalog under `shared\standards\access_pod\vendor\access-pod-artifacts-core\v1a\catalogs\`
- vendored sector profiles under `shared\standards\access_pod\vendor\access-pod-artifacts-core\v1a\profiles\`
- local profile extensions under `shared\standards\access_pod\profiles\` when present
- enterprise evidence input schema under `shared\standards\access_pod\schemas\`

## Useful Overrides

```powershell
py -3 .\scripts\build_csc_certificate.py `
  --evidence-input .\my_evidence.json `
  --profile-id sector.finance.v1 `
  --out .\shared\standards\access_pod\generated\certificates\finance_demo.csc_certificate.json `
  --report-out .\shared\standards\access_pod\generated\reports\finance_demo.csc_report.json
```

## Sector Example Runs

```powershell
py -3 .\scripts\build_csc_certificate.py `
  --evidence-input .\shared\standards\access_pod\examples\enterprise_csc_evidence_input.sector_finance_v1.example.json
```

```powershell
py -3 .\scripts\build_csc_certificate.py `
  --evidence-input .\shared\standards\access_pod\examples\enterprise_csc_evidence_input.sector_healthcare_v1.example.json
```

```powershell
py -3 .\scripts\build_csc_certificate.py `
  --evidence-input .\shared\standards\access_pod\examples\enterprise_csc_evidence_input.ai_and_emerging_tech_v1.example.json
```

## Build Draft Metric Observations From A Mapper Blueprint

```powershell
py -3 .\scripts\build_csc_metric_observation_draft.py `
  --blueprint .\shared\standards\access_pod\mappers\sector.finance.v1.mapper_blueprint.json
```

Scenario example:

```powershell
py -3 .\scripts\build_csc_metric_observation_draft.py `
  --blueprint .\shared\standards\access_pod\mappers\sector.finance.v1.mapper_blueprint.json `
  --scenario .\shared\standards\access_pod\mappers\scenarios\sector.finance.v1.50_50.scenario.json
```

Default mapper outputs:

- `shared\standards\access_pod\generated\metric_observation_drafts\*.metric_observation_draft.json`
- `shared\standards\access_pod\generated\metric_observation_drafts\*.metric_observation_draft.md`

## Build A Full Draft Evidence Input From A Mapper Blueprint

```powershell
py -3 .\scripts\build_csc_evidence_input_draft.py `
  --blueprint .\shared\standards\access_pod\mappers\sector.finance.v1.mapper_blueprint.json
```

Scenario example:

```powershell
py -3 .\scripts\build_csc_evidence_input_draft.py `
  --blueprint .\shared\standards\access_pod\mappers\sector.finance.v1.mapper_blueprint.json `
  --scenario .\shared\standards\access_pod\mappers\scenarios\sector.finance.v1.75_25.scenario.json
```

Default second-phase outputs:

- `shared\standards\access_pod\generated\evidence_input_drafts\*.evidence_input_draft.json`
- `shared\standards\access_pod\generated\evidence_input_drafts\*.evidence_input_draft.md`

## Notes

- the scorer preserves the vendored `v1a` release as the standards baseline
- enterprise-only profile additions such as `ai.and.emerging_tech.v1` belong in
  `shared\standards\access_pod\profiles\`, not in the vendored `v1a` snapshot
- the mapper runner emits draft values, not final authoritative sector scores
- the second-phase evidence input draft is scorer-ready in structure, but its
  mapped values still need human review before being treated as final
- use scenario overlays when comparing weighting variants instead of copying
  whole mapper folders
- local evidence item paths can be repo-relative
- local evidence digests are computed automatically when `path` is supplied
- generated JSON artifacts should be kept with their Markdown sidecars for
  easier governance review
- the generated signature block is a placeholder digest/signature envelope for
  enterprise review, not a production signing implementation
