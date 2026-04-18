# Access-PoD Mapper Blueprints

These mapper blueprints define the first extraction plan for converting live
enterprise artifacts into `metric_observations` for CSC scoring.

They are intentionally not full automation yet. Each blueprint names:

- the target profile
- the primary enterprise artifact families to read
- the first metric set to map
- the expected extraction direction for each metric
- optional `source_mix` weights for sector-sensitive metrics when one industry
  should emphasize different evidence sources than another

## Current Status

- `sector.finance.v1` blueprint is prepared
- `sector.healthcare.v1` blueprint is prepared
- `ai.and.emerging_tech.v1` blueprint is prepared as a local enterprise profile
- finance scenario overlays now live under `mappers\scenarios\`

## Intended Next Step

Implement a mapper runner that reads one blueprint, loads the referenced live
artifacts, derives metric values, and emits a draft enterprise evidence input
JSON for review before CSC certificate generation.

## Output Pattern

Generated mapper drafts should be emitted as:

- JSON for machine-readable review and downstream scoring
- Markdown sidecar for plain-language review by governance and standards teams

## Sector-Sensitive Weighting

For sector-facing metrics, a blueprint can declare a `source_mix` block to make
the evidence blend explicit. For example:

- finance may weight partner attestations at `75%` and market-integrity
  telemetry at `25%`
- another sector may invert that ratio or use a more even `50/50` split

This keeps the option visible in the blueprint and in the generated plain-language
artifact notes, while still allowing the standards team to move toward direct
telemetry later.

When you want to compare variants without editing the canonical blueprint, use a
scenario overlay from `mappers\scenarios\` instead of copying folders.
