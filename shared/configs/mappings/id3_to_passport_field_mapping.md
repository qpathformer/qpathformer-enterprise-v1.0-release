# ID_3 to Dataset Passport Field Mapping

## Purpose

This document maps Access-PoD ID_3 freeze artifacts into Dataset Passport fields used by the Governed Dataset Lifecycle Framework.

It provides a repeatable conversion reference for:

- dataset converters,
- passport generators,
- routing tools,
- validation workflows.

## Source Package

Typical ID_3 freeze package inputs include:

- `session_baseline.canonical.json`
- `session_variant.canonical.json`
- `module_03_baseline.canonical.json`
- `module_03_variant.canonical.json`
- `hashes.txt`
- `ID3_FREEZE_NOTE.md`

## Mapping Overview

| ID_3 Source | Passport Field | Notes |
|---|---|---|
| freeze note `frozen_at_utc` | `provenance.frozen_at_utc` | Freeze anchor timestamp |
| freeze note outbox folder / freeze name | `provenance.source_freeze_id` | Freeze package identifier |
| hash manifest entries | `provenance.canonical_artifacts[].sha256` | Canonical integrity anchors |
| `inspection_status` | `provenance.inspection_status` | Usually `frozen_under_ID_3` |
| `record_class` | `provenance.source_record_class` | Session/module/mixed |
| `session.session_id` | `provenance.source_session_id` | Parent session reference |
| `module.module_id` | `provenance.source_module_id` | Module reference |
| `intended_use` | `authorization_scope.authorization_note` and `governance_flags.signals_not_decisions` | Non-authoritative use note |
| `human_decision_required` | `governance_flags.human_decision_required` and `authorization_scope.human_review_required` | Review requirement |
| `scenario_seeds` | `signal_profile.teacher_signals` or derived dataset signal note | Teacher signal inputs |
| `stressors` | `signal_profile.teacher_signals` or derived dataset signal note | Runtime and stress context |
| `signals_observed` | `signal_profile.teacher_signals` | Observed reasoning signals |
| `fragility_points` | `signal_profile.teacher_signals` | Convergence/review relevance |
| `authority_drift_flags` | `signal_profile.teacher_signals` | Important for containment |
| `uncertainty_notes` | `signal_profile.signal_note` | Supports non-claim posture |
| `escalation_triggers` | `signal_profile.signal_note` or routing rationale | State 2 / promotion relevance |
| session signoff non-inspection acknowledgements | `governance_flags.non_certifying`, `non_compliance_claim`, `non_trust_claim` | Converted as governance flags |

## Recommended Passport Defaults for ID_3 Freeze Inputs

For ID_3-derived inputs, use these defaults unless policy explicitly overrides them:

| Passport Field | Default |
|---|---|
| `dataset_origin` | `access_pod_id3_freeze` |
| `provenance.source_system` | `Access-PoD` |
| `provenance.source_access_mode` | `ID_3` |
| `lifecycle.state` | `STATE_3` |
| `authorization_scope.runtime_reasoning` | `true` |
| `authorization_scope.synthetic_generation` | `true` |
| `authorization_scope.fine_tuning` | `false` |
| `authorization_scope.external_training` | `false` |
| `authorization_scope.human_review_required` | `true` |
| `governance_flags.signals_not_decisions` | `true` |
| `governance_flags.non_certifying` | `true` |
| `governance_flags.non_compliance_claim` | `true` |
| `governance_flags.non_trust_claim` | `true` |

## Session-Level Mapping

### From session records

Map these fields from `session_baseline.canonical.json` and `session_variant.canonical.json`:

| Session Field | Passport Destination |
|---|---|
| `session.session_id` | `provenance.source_session_id` |
| `session.project_context.project_name` | `dataset_title` or `dataset_description` support text |
| `session.project_context.purpose_statement` | `dataset_description` |
| `validation.human_review_required_before_external_use` | `authorization_scope.human_review_required` |
| `signoff.non_inspection_acknowledged` | `governance_flags.non_certifying` support |
| `signoff.no_adequacy_or_compliance_claims_acknowledged` | `governance_flags.non_compliance_claim` |
| `session_status.intended_reuse` | `lineage.parent_refs[].note` or `authorization_scope.authorization_note` |
| `frozen_at_utc` | `provenance.frozen_at_utc` |

## Module-Level Mapping

### From module records

Map these fields from `module_03_baseline.canonical.json` and `module_03_variant.canonical.json`:

| Module Field | Passport Destination |
|---|---|
| `module.module_id` | `provenance.source_module_id` |
| `module.module_title` | `dataset_title` support |
| `inputs.scenario_seeds` | `signal_profile.teacher_signals` or derived signal notes |
| `inputs.stressors` | `signal_profile.teacher_signals` |
| `captures.objective` | `dataset_description` support |
| `captures.scope_in` | `authorization_scope.authorization_note` support |
| `captures.scope_out` | `authorization_scope.authorization_note` and routing blockers |
| `simulation_runs[].signals_observed` | `signal_profile.teacher_signals` |
| `simulation_runs[].fragility_points` | `signal_profile.signal_note` |
| `simulation_runs[].authority_drift_flags` | `signal_profile.signal_note` |
| `simulation_runs[].uncertainty_notes` | `signal_profile.signal_note` |
| `simulation_runs[].escalation_triggers` | `lifecycle.promotion_blockers` and routing review notes |
| `status` and `completed_at_utc` | provenance note only; not approval status |

## Hash Mapping

From `hashes.txt`:

Each canonical artifact entry should map into:

- `provenance.canonical_artifacts[].artifact_name`
- `provenance.canonical_artifacts[].artifact_role`
- `provenance.canonical_artifacts[].sha256`

Recommended artifact roles:

| Artifact Name | Artifact Role |
|---|---|
| `module_03_baseline.canonical.json` | `primary_module_record` |
| `module_03_variant.canonical.json` | `variant_module_record` |
| `session_baseline.canonical.json` | `parent_session_record` |
| `session_variant.canonical.json` | `variant_session_record` |
| `ID3_FREEZE_NOTE.md` | `freeze_note` |
| `hashes.txt` | `hash_manifest` |

## Freeze Note Interpretation Rule

The freeze note definition of `final` under ID_3 shall be preserved in passport generation logic.

Interpretation:

- `final` means final packaging under ID_3,
- `final` does not mean compliant,
- `final` does not mean approved,
- `final` does not mean regulator-accepted,
- `final` does not mean operationally complete.

This rule should populate or reinforce:

- `governance_flags.non_certifying`
- `governance_flags.non_compliance_claim`
- `governance_flags.non_trust_claim`
- `lifecycle.state_reason`

## Converter Guidance

A converter should:

1. ingest canonical session and module records,
2. verify hashes against `hashes.txt`,
3. read freeze note metadata,
4. build provenance anchors,
5. extract session and module signal fields,
6. assign default lifecycle state `STATE_3`,
7. apply governance flags,
8. output a passport ready for routing.

## Summary

ID_3 freeze artifacts are ideal provenance-rich inputs for dataset passport generation. They provide:

- deterministic integrity anchors,
- strong lineage references,
- explicit non-claim posture,
- structured reasoning signals,
- a clean basis for contained onboarding into State 3.