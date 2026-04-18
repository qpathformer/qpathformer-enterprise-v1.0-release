#!/usr/bin/env python3
"""
Plain-language sidecar renderers for Access-PoD generated artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List


LAYER_LABELS: Dict[str, str] = {
    "Layer 1": "Q-Pathformer execution and internal governance",
    "Layer 2": "Organization and company governance",
    "Layer 3": "Profile and scenario interpretation",
}


FACTOR_METADATA: Dict[str, Dict[str, str]] = {
    "f6_1": {
        "number": "6.1",
        "name": "Security & Resilience",
        "layer": "Layer 1",
        "supporting_layers": "Layer 2",
        "reading": "runtime safety, integrity, and containment evidence dominate this factor",
    },
    "f6_2": {
        "number": "6.2",
        "name": "Adaptive Best Practice",
        "layer": "Layer 1",
        "supporting_layers": "Layer 2",
        "reading": "hardening, privacy, telemetry, and technical readiness evidence dominate this factor",
    },
    "f6_3": {
        "number": "6.3",
        "name": "Operational Compliance",
        "layer": "Layer 2",
        "supporting_layers": "Layer 1",
        "reading": "policy traceability and lifecycle compliance dominate this factor",
    },
    "f6_4": {
        "number": "6.4",
        "name": "Human-Centric Oversight",
        "layer": "Layer 2",
        "supporting_layers": "Layer 1",
        "reading": "human review, audit, escalation, and approval governance dominate this factor",
    },
    "f6_5": {
        "number": "6.5",
        "name": "Transparency & Impact",
        "layer": "Layer 2",
        "supporting_layers": "Layer 1",
        "reading": "explanation, harm handling, and transparency governance dominate this factor",
    },
    "f6_6": {
        "number": "6.6",
        "name": "Fair Competition & Ecosystem Trust",
        "layer": "Layer 3",
        "supporting_layers": "Layer 2 and Layer 1",
        "reading": "sector profile and scenario interpretation dominate the release reading for this factor",
    },
}


def sidecar_markdown_path(json_path: Path) -> Path:
    return json_path.with_suffix(".md")


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _format_bool(value: bool) -> str:
    return "Yes" if value else "No"


def _format_float(value: Any, decimals: int = 1) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return str(value)


def _bullet_lines(items: Iterable[str]) -> List[str]:
    return [f"- {item}" for item in items]


def _factor_display_name(factor_key: str) -> str:
    metadata = FACTOR_METADATA.get(factor_key, {})
    number = metadata.get("number")
    name = metadata.get("name")
    if number and name:
        return f"{number} {name}"
    return factor_key


def _factor_layer_summary(factor_key: str) -> str:
    metadata = FACTOR_METADATA.get(factor_key, {})
    layer = metadata.get("layer", "Unknown layer")
    layer_label = LAYER_LABELS.get(layer, layer)
    return f"{layer} ({layer_label})"


def _metric_layer(metric_id: str) -> str:
    if metric_id.startswith("SECTOR_"):
        return "Layer 3"
    if metric_id.startswith("COMP_") or metric_id.startswith("GOV_") or metric_id.startswith("TRN_"):
        return "Layer 2"
    if metric_id.startswith("SEC_") or metric_id.startswith("HARD_"):
        return "Layer 1"
    return "Unclassified"


def _render_factor_model_section() -> List[str]:
    lines = [
        "## Canonical Factor Model",
        "",
        "This release keeps the canonical Access-PoD six-factor model and reads it through the enterprise three-layer binding.",
        "",
    ]
    for factor_key in sorted(FACTOR_METADATA):
        metadata = FACTOR_METADATA[factor_key]
        lines.append(
            f"- {metadata['number']} {metadata['name']}: dominant layer {metadata['layer']} ({LAYER_LABELS[metadata['layer']]}), supporting layers {metadata['supporting_layers']}"
        )
    return lines


def _render_factor_results_section(factor_scores: Dict[str, Any]) -> List[str]:
    lines = ["## Factor Results", ""]
    for factor_key in sorted(factor_scores):
        factor = factor_scores[factor_key]
        metadata = FACTOR_METADATA.get(factor_key, {})
        lines.append(
            f"- {_factor_display_name(factor_key)}: score {_format_float(factor.get('score', 0.0))}, confidence {_format_float(factor.get('confidence', 0.0), 2)}, dominant evidence layer {_factor_layer_summary(factor_key)}"
        )
        reading = metadata.get("reading")
        if reading:
            lines.append(f"  Reading note: {reading}.")
        top_metric_ids = [
            str(item.get("metric_id"))
            for item in factor.get("top_metrics", [])
            if item.get("metric_id")
        ]
        if top_metric_ids:
            lines.append(f"  Top metrics: {', '.join(top_metric_ids)}")
    return lines


def render_certificate_markdown(
    certificate: Dict[str, Any],
    report: Dict[str, Any],
    certificate_path: Path,
    report_path: Path,
) -> str:
    assessment = certificate.get("assessment", {})
    gates = assessment.get("gates", {})
    subject = certificate.get("subject", {})
    scope = certificate.get("scope", {})
    factor_scores = assessment.get("factor_scores", {})
    lines = [
        "# CSC Certificate Summary",
        "",
        "## What This File Is",
        "",
        "This is the plain-language companion note for the generated CSC certificate JSON.",
        "The JSON remains the authoritative machine-readable artifact. This Markdown file explains the result in normal project language.",
        "",
        "## Plain-Language Summary",
        "",
        f"- Subject: {subject.get('name', 'Unknown subject')}",
        f"- Profile: {assessment.get('weights', {}).get('profile_id', 'Unknown profile')}",
        f"- CSC ID: {certificate.get('csc_id', 'Unknown')}",
        f"- Score: {_format_float(assessment.get('composite_score', 0.0))}",
        f"- CSC level: {assessment.get('csc_level', 'Unknown')}",
        f"- Risk tier: {assessment.get('risk_tier', 'Unknown')}",
        f"- Status: {certificate.get('status', 'Unknown')}",
        f"- Sectors: {', '.join(scope.get('sectors', [])) or 'Not declared'}",
        "",
    ]
    lines.extend(_render_factor_model_section())
    lines.extend(
        [
            "",
            "## Gate Check",
            "",
            f"- No critical failures: {_format_bool(bool(gates.get('no_critical_failures')))}",
            f"- Minimum telemetry met: {_format_bool(bool(gates.get('telemetry_minimum_met')))}",
            f"- F6.1 threshold met: {_format_bool(bool(gates.get('f6_1_min_met')))}",
            f"- F6.4 threshold met: {_format_bool(bool(gates.get('f6_4_min_met')))}",
            f"- All factor minimums met: {_format_bool(bool(gates.get('all_factors_min_met')))}",
            f"- Sector validation met: {_format_bool(bool(gates.get('sector_validation_met')))}",
            "",
        ]
    )
    lines.extend(_render_factor_results_section(factor_scores))
    lines.extend(
        [
            "",
            "## Related Files",
            "",
            f"- Certificate JSON: `{certificate_path}`",
            f"- Report JSON: `{report_path}`",
            f"- Report summary Markdown: `{sidecar_markdown_path(report_path)}`",
            "",
            "## Reading Note",
            "",
            "Use the certificate JSON for integration or audit tooling.",
            "Use the report JSON and its Markdown summary when you want the scoring breakdown and gate reasoning in more detail.",
        ]
    )
    return "\n".join(lines)


def render_report_markdown(report: Dict[str, Any], report_path: Path) -> str:
    summary = report.get("assessment_summary", {})
    gates = report.get("gates", {})
    factor_coverages = report.get("factor_coverages", {})
    lines = [
        "# CSC Report Summary",
        "",
        "## What This File Is",
        "",
        "This is the plain-language companion note for the generated CSC scoring report JSON.",
        "It explains the result, gates, and coverage without making you read the raw JSON first.",
        "",
        "## Plain-Language Summary",
        "",
        f"- Profile: {report.get('profile_id', 'Unknown')}",
        f"- CSC ID: {report.get('csc_id', 'Unknown')}",
        f"- Composite score: {_format_float(summary.get('composite_score', 0.0))}",
        f"- CSC level: {summary.get('csc_level', 'Unknown')}",
        f"- Risk tier: {summary.get('risk_tier', 'Unknown')}",
        f"- Observed metrics: {report.get('observed_metric_count', 0)} out of {report.get('catalog_metric_count', 0)}",
        f"- Overall coverage ratio: {_format_float(report.get('overall_metric_coverage_ratio', 0.0), 2)}",
        "",
    ]
    lines.extend(_render_factor_model_section())
    lines.extend(
        [
            "",
            "## Gate Check",
            "",
            f"- No critical failures: {_format_bool(bool(gates.get('no_critical_failures')))}",
            f"- Minimum telemetry met: {_format_bool(bool(gates.get('telemetry_minimum_met')))}",
            f"- F6.1 threshold met: {_format_bool(bool(gates.get('f6_1_min_met')))}",
            f"- F6.4 threshold met: {_format_bool(bool(gates.get('f6_4_min_met')))}",
            f"- All factor minimums met: {_format_bool(bool(gates.get('all_factors_min_met')))}",
            f"- Sector validation met: {_format_bool(bool(gates.get('sector_validation_met')))}",
            "",
        ]
    )
    lines.extend(_render_factor_results_section(report.get("factor_scores", {})))
    lines.extend(["", "## Coverage By Factor", ""])
    for factor_key in sorted(factor_coverages):
        factor = factor_coverages[factor_key]
        lines.append(
            f"- {_factor_display_name(factor_key)}: {factor.get('observed_metrics', 0)} of {factor.get('total_factor_metrics', 0)} metrics observed"
        )
    warning_metrics = report.get("warning_metrics", [])
    critical_metrics = report.get("critical_metrics", [])
    lines.extend(
        [
            "",
            "## Alerts",
            "",
            f"- Warning metrics: {', '.join(warning_metrics) if warning_metrics else 'None'}",
            f"- Critical metrics: {', '.join(critical_metrics) if critical_metrics else 'None'}",
            "",
            "## Related File",
            "",
            f"- Report JSON: `{report_path}`",
        ]
    )
    return "\n".join(lines)


def render_mapper_draft_markdown(draft: Dict[str, Any], draft_path: Path) -> str:
    observations = draft.get("metric_observations", [])
    artifact_inputs = draft.get("artifact_inputs", {})
    scenario_id = draft.get("scenario_id")
    scenario_label = draft.get("scenario_label")
    lines = [
        "# Metric Observation Draft Summary",
        "",
        "## What This File Is",
        "",
        "This is the plain-language companion note for the generated metric observation draft JSON.",
        "The JSON is the structured draft that can be reviewed, edited, and then folded into an enterprise CSC evidence input.",
        "",
        "## Plain-Language Summary",
        "",
        f"- Profile: {draft.get('profile_id', 'Unknown')}",
        f"- Blueprint: {draft.get('blueprint_path', 'Unknown')}",
        f"- Scenario: {scenario_label or scenario_id or 'Canonical blueprint'}",
        f"- Observation count: {len(observations)}",
        f"- Generated at: {draft.get('generated_at_utc', 'Unknown')}",
        "",
    ]
    lines.extend(_render_factor_model_section())
    lines.extend(["", "## Source Artifacts Used", ""])
    for key in sorted(artifact_inputs):
        lines.append(f"- {key}: `{artifact_inputs[key]}`")
    lines.extend(
        [
            "",
            "## Draft Metrics",
            "",
        ]
    )
    for observation in observations:
        layer = _metric_layer(str(observation.get("metric_id") or ""))
        lines.append(
            f"- {observation.get('metric_id')}: value {observation.get('value')} with confidence {_format_float(observation.get('confidence', 0.0), 2)}, dominant evidence layer {layer}"
        )
        note = observation.get("derivation_note")
        if note:
            lines.append(f"  {note}")
    notes = draft.get("notes", [])
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(_bullet_lines(str(note) for note in notes))
    lines.extend(["", "## Related File", "", f"- Draft JSON: `{draft_path}`"])
    return "\n".join(lines)


def render_evidence_input_draft_markdown(evidence_input: Dict[str, Any], evidence_input_path: Path) -> str:
    scope = evidence_input.get("scope", {})
    observations = evidence_input.get("metric_observations", [])
    evidence = evidence_input.get("evidence", {})
    subject = evidence_input.get("subject", {}) or {}
    subject_name = subject.get("name", "Unknown subject")
    scenario_label = "Canonical blueprint"
    if "(" in subject_name and subject_name.endswith(")"):
        scenario_label = subject_name.rsplit("(", 1)[-1].rstrip(")").strip() or scenario_label
    lines = [
        "# Evidence Input Draft Summary",
        "",
        "## What This File Is",
        "",
        "This is the plain-language companion note for the generated enterprise CSC evidence input draft JSON.",
        "The JSON is meant to be scorer-ready after review, while this Markdown file explains the draft in normal language.",
        "",
        "## Plain-Language Summary",
        "",
        f"- Profile: {evidence_input.get('profile_id', 'Unknown')}",
        f"- Scenario: {scenario_label}",
        f"- CSC ID: {evidence_input.get('csc_id', 'Unknown')}",
        f"- Subject: {subject_name}",
        f"- Risk tier: {scope.get('risk_tier_declared', evidence_input.get('risk_tier', 'Unknown'))}",
        f"- Sectors: {', '.join(scope.get('sectors', [])) or 'Not declared'}",
        f"- Observation count: {len(observations)}",
        f"- Evidence item count: {len(evidence.get('items', []))}",
        "",
    ]
    lines.extend(_render_factor_model_section())
    lines.extend(
        [
            "",
            "## Telemetry Window",
            "",
            f"- Start: {(evidence_input.get('telemetry_window', {}) or {}).get('start', 'Unknown')}",
            f"- End: {(evidence_input.get('telemetry_window', {}) or {}).get('end', 'Unknown')}",
            "",
            "## Evidence Bundle",
            "",
        ]
    )
    for item in evidence.get("items", []):
        path_or_uri = item.get("path") or item.get("uri") or "Unknown evidence location"
        lines.append(f"- {item.get('type', 'unknown')}: `{path_or_uri}`")
    lines.extend(
        [
            "",
            "## Next Use",
            "",
            "Run the CSC builder against this JSON after review if you want to generate a certificate and report.",
            "",
            "```powershell",
            f"py -3 .\\scripts\\build_csc_certificate.py --evidence-input \"{evidence_input_path}\"",
            "```",
            "",
            "## Related File",
            "",
            f"- Evidence input JSON: `{evidence_input_path}`",
        ]
    )
    return "\n".join(lines)
