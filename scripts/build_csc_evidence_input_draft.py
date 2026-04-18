#!/usr/bin/env python3
"""
Build a full draft enterprise CSC evidence input from a mapper blueprint and live artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from access_pod_human_readable import (
    render_evidence_input_draft_markdown,
    sidecar_markdown_path,
    write_markdown,
)
from build_csc_metric_observation_draft import (
    MAPPING_FUNCTIONS,
    build_context,
    ensure,
    relativize_if_possible,
    resolve_path,
    sanitize_token,
    utc_now_iso,
)
from path_layout import ACCESS_POD_LOCAL_EVIDENCE_INPUT_DRAFTS_ROOT


DEFAULT_OUT_ROOT = ACCESS_POD_LOCAL_EVIDENCE_INPUT_DRAFTS_ROOT
DEFAULT_EXPIRES_IN_DAYS = 180
DEFAULT_SCORING_POLICY = {
    "top_metrics_per_factor": 3,
    "min_overall_metric_coverage_ratio": 0.2,
    "min_metrics_per_factor": 2,
    "min_factor_score": 60.0,
    "level_thresholds": {
        "2": 60.0,
        "3": 70.0,
        "4": 80.0,
        "5": 90.0,
        "6": 97.0,
    },
}
DEFAULT_ISSUER = {
    "org_id": "policyofdevelopments.qpathformer",
    "name": "Policy of Developments - Q-Pathformer Enterprise",
    "key_id": "kid-qpathformer-enterprise-demo-001",
    "contact": {
        "email": "registry@policyofdevelopments.org",
        "web": "https://policyofdevelopments.org",
    },
    "jurisdiction": "AU",
}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def title_case_token(token: str) -> str:
    return " ".join(piece.capitalize() for piece in token.replace("_", " ").replace(".", " ").split())


def profile_scope_defaults(profile_id: str) -> Dict[str, Any]:
    if profile_id == "sector.finance.v1":
        return {
            "subject_id": "qpathformer_enterprise_access_mode_finance_draft",
            "subject_name": "Q-Pathformer Enterprise Access-Mode Finance Draft",
            "sectors": ["finance"],
            "risk_tier_declared": "high",
            "ai_types": ["LLM", "agentic"],
            "use_constraints": [
                "No transaction-impacting action without human review.",
                "Finance-sector rollout remains governed until evidence review is complete.",
            ],
            "iso_alignment": {
                "iso_iec_42001": {
                    "status": "partial",
                    "notes": "Finance-oriented governance and approval traces are present, but external certification is still pending.",
                    "controls_mapped": ["AIMS-governance", "AIMS-assurance", "AIMS-improvement-loop"],
                },
                "iso_iec_23894": {
                    "status": "aligned",
                    "notes": "Risk identification, escalation, review, and freeze traces are present in the governed Path 2 flow.",
                    "controls_mapped": ["risk-identify", "risk-analyze", "risk-treat", "risk-monitor"],
                },
                "iso_iec_22989": {
                    "status": "aligned",
                    "notes": "Platform vocabulary for model, runtime signal, dataset, and governance package remains consistent across the standards bridge.",
                    "controls_mapped": ["ai-system", "ai-model", "training", "inference"],
                },
            },
        }
    if profile_id == "sector.healthcare.v1":
        return {
            "subject_id": "qpathformer_enterprise_access_mode_healthcare_draft",
            "subject_name": "Q-Pathformer Enterprise Access-Mode Healthcare Draft",
            "sectors": ["healthcare"],
            "risk_tier_declared": "high",
            "ai_types": ["LLM", "agentic"],
            "use_constraints": [
                "No patient-impacting action without qualified human oversight.",
                "Healthcare adoption remains governed until evidence review is complete.",
            ],
            "iso_alignment": {
                "iso_iec_42001": {
                    "status": "partial",
                    "notes": "Healthcare-oriented oversight and governance traces are present, but external certification is still pending.",
                    "controls_mapped": ["AIMS-governance", "AIMS-assurance", "AIMS-improvement-loop"],
                },
                "iso_iec_23894": {
                    "status": "aligned",
                    "notes": "Risk review, human review coverage, and freeze readiness are present in the controlled healthcare flow.",
                    "controls_mapped": ["risk-identify", "risk-analyze", "risk-treat", "risk-monitor"],
                },
                "iso_iec_22989": {
                    "status": "aligned",
                    "notes": "Healthcare bridge artifacts preserve consistent terminology for system, model, training, and runtime oversight.",
                    "controls_mapped": ["ai-system", "ai-model", "training", "inference"],
                },
            },
        }
    if profile_id == "ai.and.emerging_tech.v1":
        return {
            "subject_id": "qpathformer_enterprise_ai_emerging_tech_draft",
            "subject_name": "Q-Pathformer Enterprise AI And Emerging Tech Draft",
            "sectors": ["enterprise", "ai_and_emerging_technology"],
            "risk_tier_declared": "high",
            "ai_types": ["LLM", "agentic", "other"],
            "use_constraints": [
                "New capability rollout must remain staged and reversible until governance approval is complete.",
                "Regulatory and policy adaptation checks are required before broader enterprise release.",
            ],
            "iso_alignment": {
                "iso_iec_42001": {
                    "status": "partial",
                    "notes": "Rollout governance and approval checkpoints are present, but external certification is not yet complete.",
                    "controls_mapped": ["AIMS-governance", "AIMS-deployment-control", "AIMS-improvement-loop"],
                },
                "iso_iec_23894": {
                    "status": "aligned",
                    "notes": "Risk escalation, rollout gating, and policy adaptation traces are present for the controlled introduction of new capability.",
                    "controls_mapped": ["risk-identify", "risk-analyze", "risk-treat", "risk-monitor"],
                },
                "iso_iec_22989": {
                    "status": "aligned",
                    "notes": "System, model, training, deployment, and runtime terminology is kept consistent across the enterprise standards bridge.",
                    "controls_mapped": ["ai-system", "ai-model", "training", "deployment"],
                },
            },
        }
    token = sanitize_token(profile_id)
    return {
        "subject_id": f"qpathformer_enterprise_{token}_draft",
        "subject_name": f"Q-Pathformer Enterprise {title_case_token(profile_id)} Draft",
        "sectors": [token],
        "risk_tier_declared": "medium",
        "ai_types": ["LLM", "agentic"],
        "use_constraints": [
            "Governed review is required before broader enterprise use.",
        ],
        "iso_alignment": {},
    }


def build_evidence_items(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = [
        {"type": "telemetry_export", "path": context["artifact_inputs"]["runtime_signal_path"]},
        {"type": "attestation", "path": context["artifact_inputs"]["run_reference_path"]},
        {"type": "policy_bundle", "path": context["artifact_inputs"]["run_registry_path"]},
    ]
    candidate = context["candidate_artifacts"]
    training = context["training_artifacts"]
    if candidate["state2_review_path"].exists():
        items.append({"type": "human_review_log", "path": relativize_if_possible(candidate["state2_review_path"])})
    if candidate["state2_promotion_path"].exists():
        items.append({"type": "attestation", "path": relativize_if_possible(candidate["state2_promotion_path"])})
    if candidate["state1_handoff_path"].exists():
        items.append({"type": "attestation", "path": relativize_if_possible(candidate["state1_handoff_path"])})
    if candidate["state1_freeze_path"].exists():
        items.append({"type": "attestation", "path": relativize_if_possible(candidate["state1_freeze_path"])})
    if training["training_manifest_path"].exists():
        items.append({"type": "dataset_card", "path": relativize_if_possible(training["training_manifest_path"])})
    if context.get("benchmark_summary_path") and context["benchmark_summary_path"].exists():
        items.append({"type": "simulation_report", "path": relativize_if_possible(context["benchmark_summary_path"])})
        benchmark_summary = context.get("benchmark_summary") or {}
        manifest_rel = benchmark_summary.get("manifest_path")
        if manifest_rel:
            manifest_path = resolve_path(str(manifest_rel))
            if manifest_path.exists():
                items.append({"type": "model_card", "path": relativize_if_possible(manifest_path)})
    return items


def build_metric_observations(blueprint: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []
    for metric_config in blueprint.get("metric_mapping", []):
        metric_id = str(metric_config.get("metric_id") or "").strip()
        ensure(metric_id, "Blueprint contains a metric mapping entry without metric_id.")
        mapper = MAPPING_FUNCTIONS.get(metric_id)
        ensure(mapper is not None, f"Unsupported metric mapping: {metric_id}")
        raw = mapper(metric_config, context)
        observations.append(
            {
                "metric_id": raw["metric_id"],
                "value": raw["value"],
                "confidence": raw["confidence"],
                "weight": raw["weight"],
                "telemetry_start": raw["telemetry_start"],
                "telemetry_end": raw["telemetry_end"],
                "notes": raw["derivation_note"],
            }
        )
    return observations


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a full enterprise CSC evidence input draft from a mapper blueprint and live artifacts."
    )
    parser.add_argument("--blueprint", required=True, help="Mapper blueprint JSON.")
    parser.add_argument("--scenario", default=None, help="Optional mapper scenario overlay JSON.")
    parser.add_argument("--runtime-signal", default=None)
    parser.add_argument("--run-reference", default=None)
    parser.add_argument("--run-registry", default=None)
    parser.add_argument("--candidate-package-dir", default=None)
    parser.add_argument("--training-package-dir", default=None)
    parser.add_argument("--benchmark-summary", default=None)
    parser.add_argument("--out", default=None, help="Optional explicit output path for the evidence input draft JSON.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        context = build_context(args)
        blueprint = context["blueprint"]
        profile_id = str(blueprint.get("profile_id") or "unknown_profile")
        profile_defaults = profile_scope_defaults(profile_id)
        now = utc_now_iso()
        scenario_id = context.get("scenario_id") or ""
        scenario_label = context.get("scenario_label") or ""
        subject_id = (
            f"{profile_defaults['subject_id']}__{sanitize_token(scenario_id)}"
            if scenario_id
            else profile_defaults["subject_id"]
        )
        subject_name = (
            f"{profile_defaults['subject_name']} ({scenario_label})"
            if scenario_label
            else profile_defaults["subject_name"]
        )

        metric_observations = build_metric_observations(blueprint, context)
        evidence_items = build_evidence_items(context)
        run_reference = context["run_reference"]

        evidence_input = {
            "evidence_input_version": "access_pod_enterprise_evidence_input_v1.0",
            "csc_id": f"csc_{sanitize_token(subject_id)}_{now.replace(':', '').replace('-', '')}",
            "status": "active",
            "issued_at": now,
            "expires_in_days": DEFAULT_EXPIRES_IN_DAYS,
            "profile_id": profile_id,
            "issuer": DEFAULT_ISSUER,
            "subject": {
                "subject_id": subject_id,
                "name": subject_name,
                "type": "platform",
                "owner": {
                    "org_id": "policyofdevelopments",
                    "name": "Policy of Developments",
                },
                "version": "v1.0",
            },
            "scope": {
                "ai_types": profile_defaults["ai_types"],
                "deployment": "hybrid",
                "jurisdictions": ["AU"],
                "sectors": profile_defaults["sectors"],
                "risk_tier_declared": profile_defaults["risk_tier_declared"],
                "use_constraints": profile_defaults["use_constraints"],
            },
            "telemetry_window": context["telemetry_window"],
            "sapp": {
                "maturity_level": int(str(run_reference.get("maturity", "LEVEL_4")).replace("LEVEL_", "") or "4"),
                "run_id": run_reference["run_id"],
                "run_at": run_reference.get("recorded_at_utc", now),
                "environment": "preprod",
            },
            "evidence": {
                "bundle_id": f"bundle_{sanitize_token(subject_id)}_{now.replace(':', '').replace('-', '')}",
                "items": evidence_items,
            },
            "metric_observations": metric_observations,
            "iso_alignment": profile_defaults["iso_alignment"],
            "scoring_policy": DEFAULT_SCORING_POLICY,
        }

        output_token = sanitize_token(f"{profile_id}__{scenario_id or 'default'}__{now}")
        out_path = resolve_path(args.out) if args.out else DEFAULT_OUT_ROOT / f"{output_token}.evidence_input_draft.json"
        write_json(out_path, evidence_input)
        summary_path = sidecar_markdown_path(out_path)
        write_markdown(summary_path, render_evidence_input_draft_markdown(evidence_input, out_path))

        result = {
            "status": "completed",
            "profile_id": profile_id,
            "scenario_id": scenario_id or None,
            "evidence_input_path": str(out_path),
            "evidence_input_summary_path": str(summary_path),
            "metric_count": len(metric_observations),
            "evidence_item_count": len(evidence_items),
        }
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        payload = {
            "status": "failed",
            "error": str(exc),
            "generated_at_utc": utc_now_iso(),
        }
        json.dump(payload, sys.stderr, indent=2, ensure_ascii=False)
        sys.stderr.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
