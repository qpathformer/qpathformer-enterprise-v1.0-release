#!/usr/bin/env python3
"""
Build draft CSC metric observations from live Path 2 and shared registry artifacts.

This is the first executable mapper runner for the Access-PoD bridge. It reads a
profile mapper blueprint, discovers the latest governed Path 2 artifacts by
default, and emits a draft observation JSON plus a plain-language Markdown
summary for review.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from access_pod_human_readable import (
    render_mapper_draft_markdown,
    sidecar_markdown_path,
    write_markdown,
)
from path_layout import (
    ACCESS_POD_LOCAL_DRAFTS_ROOT,
    ACCESS_POD_LOCAL_MAPPERS_ROOT,
    ACCESS_POD_LOCAL_MAPPER_SCENARIOS_ROOT,
    PATH2_CANDIDATES_ROOT,
    PATH2_RUNTIME_SIGNALS_ROOT,
    PATH2_TRAINING_PACKAGES_ROOT,
    REPO_ROOT,
    SHARED_MODEL_EVALUATION_ROOT,
    SHARED_RUN_REFERENCES_ROOT,
    SHARED_RUN_REGISTRY_PATH,
)


DEFAULT_BLUEPRINT_PATH = ACCESS_POD_LOCAL_MAPPERS_ROOT / "sector.finance.v1.mapper_blueprint.json"
DEFAULT_DRAFT_OUT_ROOT = ACCESS_POD_LOCAL_DRAFTS_ROOT


class MapperError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise MapperError(message)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def resolve_path(raw: str | Path) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def relativize_if_possible(path_value: str | Path) -> str:
    candidate = Path(path_value)
    try:
        resolved = candidate.resolve() if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()
        return str(resolved.relative_to(REPO_ROOT)).replace("\\", "/")
    except Exception:
        return str(candidate).replace("\\", "/")


def sanitize_token(raw: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(raw))
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "value"


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def round_ratio(value: float) -> float:
    return round(clamp(value, 0.0, 1.0), 4)


def round_score(value: float) -> float:
    return round(clamp(value, 0.0, 100.0), 1)


def parse_datetime(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def latest_path(paths: Iterable[Path], description: str) -> Path:
    candidates = [path for path in paths if path.exists()]
    ensure(candidates, f"No {description} found.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def find_latest_runtime_signal() -> Path:
    return latest_path(
        [
            path
            for path in PATH2_RUNTIME_SIGNALS_ROOT.glob("signal_runtime_*.json")
            if not path.name.endswith(".routing.json")
        ],
        "runtime signal files",
    )


def find_latest_run_reference() -> Path:
    return latest_path(
        SHARED_RUN_REFERENCES_ROOT.glob("*.runtime_signal_run_reference.json"),
        "runtime signal run reference files",
    )


def find_latest_candidate_package() -> Path:
    review_file = latest_path(PATH2_CANDIDATES_ROOT.rglob("state2_review.json"), "Path 2 candidate review files")
    return review_file.parent


def find_training_package_for_candidate(candidate_package_dir: Path) -> Path:
    expected = PATH2_TRAINING_PACKAGES_ROOT / candidate_package_dir.name
    if expected.exists():
        return expected
    return latest_path(
        [path for path in PATH2_TRAINING_PACKAGES_ROOT.iterdir() if path.is_dir()],
        "Path 2 training packages",
    )


def find_latest_benchmark_summary() -> Optional[Path]:
    grouped = list(
        SHARED_MODEL_EVALUATION_ROOT.glob("model_runs/MRUN-grouped_sparse_e64-*/benchmark_summary.json")
    )
    if grouped:
        return latest_path(grouped, "grouped sparse e64 benchmark summaries")
    summaries = list(SHARED_MODEL_EVALUATION_ROOT.glob("model_runs/*/benchmark_summary.json"))
    if summaries:
        return latest_path(summaries, "benchmark summaries")
    return None


def select_run_record(registry_payload: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    for record in registry_payload.get("runs", []):
        if record.get("run_id") == run_id:
            return record
    raise MapperError(f"Run registry does not contain run_id {run_id}")


def safe_read_json(path: Path) -> Optional[Dict[str, Any]]:
    if path.exists():
        return read_json(path)
    return None


def artifact_exists_ratio(paths: Iterable[Optional[Path]]) -> float:
    materialized = [path for path in paths if path is not None]
    if not materialized:
        return 0.0
    return sum(1 for path in materialized if path.exists()) / len(materialized)


def truthy_ratio(values: Iterable[bool]) -> float:
    materialized = list(values)
    if not materialized:
        return 0.0
    return sum(1 for value in materialized if value) / len(materialized)


def normalized_source_mix(
    metric_config: Dict[str, Any], default_weights: Dict[str, float]
) -> Dict[str, float]:
    raw_weights = dict(default_weights)
    for key, value in (metric_config.get("source_mix") or {}).items():
        try:
            raw_weights[str(key)] = max(float(value), 0.0)
        except (TypeError, ValueError):
            continue
    total = sum(raw_weights.values())
    ensure(total > 0.0, f"Metric {metric_config.get('metric_id')} defines an empty source mix.")
    return {key: value / total for key, value in raw_weights.items() if value > 0.0}


def format_source_mix(mix: Dict[str, float]) -> str:
    labels = {
        "market_integrity": "market-integrity telemetry",
        "partner_attestations": "partner attestations",
        "policy_pass": "sector policy pass evidence",
        "audit_interop": "audit interoperability evidence",
    }
    parts = []
    for key, weight in mix.items():
        label = labels.get(key, key.replace("_", " "))
        parts.append(f"{label} {round(weight * 100)}%")
    return ", ".join(parts)


def weighted_signal_ratio(signals: Dict[str, float], mix: Dict[str, float]) -> float:
    return clamp(
        sum(clamp(float(signals.get(key, 0.0)), 0.0, 1.0) * weight for key, weight in mix.items()),
        0.0,
        1.0,
    )


def merge_dicts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def apply_scenario_overlay(blueprint: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    profile_id = str(blueprint.get("profile_id") or "")
    scenario_profile_id = str(scenario.get("profile_id") or profile_id)
    ensure(
        not scenario.get("profile_id") or scenario_profile_id == profile_id,
        f"Scenario profile_id {scenario_profile_id} does not match blueprint profile_id {profile_id}.",
    )

    effective = deepcopy(blueprint)
    metric_mapping = effective.get("metric_mapping", [])
    metric_index = {
        str(metric.get("metric_id") or "").strip(): idx
        for idx, metric in enumerate(metric_mapping)
        if str(metric.get("metric_id") or "").strip()
    }

    metric_overrides = scenario.get("metric_overrides", {}) or {}
    for metric_id, override in metric_overrides.items():
        ensure(metric_id in metric_index, f"Scenario override references unknown metric_id {metric_id}.")
        idx = metric_index[metric_id]
        metric_mapping[idx] = merge_dicts(metric_mapping[idx], override)

    effective["scenario"] = {
        "scenario_id": str(scenario.get("scenario_id") or sanitize_token(scenario.get("scenario_label") or "scenario")),
        "scenario_label": str(scenario.get("scenario_label") or scenario.get("scenario_id") or "Scenario"),
        "description": str(scenario.get("description") or ""),
        "scenario_path": str(scenario.get("scenario_path") or ""),
    }
    return effective


def build_context(args: argparse.Namespace) -> Dict[str, Any]:
    blueprint_path = resolve_path(args.blueprint)
    blueprint = read_json(blueprint_path)
    scenario_path = resolve_path(args.scenario) if getattr(args, "scenario", None) else None
    scenario = read_json(scenario_path) if scenario_path else None
    if scenario:
        scenario["scenario_path"] = relativize_if_possible(scenario_path)
        blueprint = apply_scenario_overlay(blueprint, scenario)
    scenario_meta = blueprint.get("scenario") or {}

    runtime_signal_path = resolve_path(args.runtime_signal) if args.runtime_signal else find_latest_runtime_signal()
    runtime_signal = read_json(runtime_signal_path)

    run_reference_path = resolve_path(args.run_reference) if args.run_reference else find_latest_run_reference()
    run_reference = read_json(run_reference_path)

    run_registry_path = resolve_path(args.run_registry) if args.run_registry else SHARED_RUN_REGISTRY_PATH
    run_registry = read_json(run_registry_path)
    run_record = select_run_record(run_registry, str(run_reference["run_id"]))

    candidate_package_dir = (
        resolve_path(args.candidate_package_dir)
        if args.candidate_package_dir
        else find_latest_candidate_package()
    )
    training_package_dir = (
        resolve_path(args.training_package_dir)
        if args.training_package_dir
        else find_training_package_for_candidate(candidate_package_dir)
    )
    benchmark_summary_path = (
        resolve_path(args.benchmark_summary)
        if args.benchmark_summary
        else find_latest_benchmark_summary()
    )

    candidate_artifacts = {
        "state2_review_path": candidate_package_dir / "state2_review.json",
        "state2_promotion_path": candidate_package_dir / "state2_promotion_decision.json",
        "state1_handoff_path": candidate_package_dir / "state1_handoff.json",
        "state1_freeze_path": candidate_package_dir / "freeze" / "state1_freeze.json",
        "manifest_path": candidate_package_dir / "manifest.json",
        "lineage_path": candidate_package_dir / "lineage.json",
        "dataset_path": candidate_package_dir / "dataset.jsonl",
    }
    training_artifacts = {
        "training_manifest_path": training_package_dir / "state1_training_manifest.json",
        "train_file_path": training_package_dir / "train.sft.jsonl",
        "training_preview_path": training_package_dir / "training_preview.json",
        "backend_profile_path": training_package_dir / "training_backend_profile.json",
    }

    state2_review = safe_read_json(candidate_artifacts["state2_review_path"])
    state2_promotion = safe_read_json(candidate_artifacts["state2_promotion_path"])
    state1_handoff = safe_read_json(candidate_artifacts["state1_handoff_path"])
    state1_freeze = safe_read_json(candidate_artifacts["state1_freeze_path"])
    training_manifest = safe_read_json(training_artifacts["training_manifest_path"])
    benchmark_summary = safe_read_json(benchmark_summary_path) if benchmark_summary_path else None

    timestamp_fields: List[datetime] = []
    for raw in [
        runtime_signal.get("timestamp"),
        run_reference.get("recorded_at_utc"),
        state2_review.get("review_timestamp") if state2_review else None,
        state2_promotion.get("promotion_timestamp") if state2_promotion else None,
        state1_handoff.get("handoff_timestamp") if state1_handoff else None,
        state1_freeze.get("freeze_timestamp") if state1_freeze else None,
        training_manifest.get("generated_at") if training_manifest else None,
    ]:
        if raw:
            timestamp_fields.append(parse_datetime(str(raw)))
    ensure(timestamp_fields, "Could not derive telemetry window from live artifacts.")

    artifact_inputs = {
        "blueprint_path": relativize_if_possible(blueprint_path),
        "scenario_path": relativize_if_possible(scenario_path) if scenario_path else "not_used",
        "runtime_signal_path": relativize_if_possible(runtime_signal_path),
        "run_reference_path": relativize_if_possible(run_reference_path),
        "run_registry_path": relativize_if_possible(run_registry_path),
        "candidate_package_dir": relativize_if_possible(candidate_package_dir),
        "training_package_dir": relativize_if_possible(training_package_dir),
        "benchmark_summary_path": (
            relativize_if_possible(benchmark_summary_path) if benchmark_summary_path else "not_found"
        ),
    }

    return {
        "blueprint_path": blueprint_path,
        "blueprint": blueprint,
        "blueprint_source_path": blueprint_path,
        "scenario_path": scenario_path,
        "scenario": scenario,
        "scenario_id": str(scenario_meta.get("scenario_id") or ""),
        "scenario_label": str(scenario_meta.get("scenario_label") or ""),
        "scenario_description": str(scenario_meta.get("description") or ""),
        "runtime_signal_path": runtime_signal_path,
        "runtime_signal": runtime_signal,
        "run_reference_path": run_reference_path,
        "run_reference": run_reference,
        "run_registry_path": run_registry_path,
        "run_registry": run_registry,
        "run_record": run_record,
        "candidate_package_dir": candidate_package_dir,
        "candidate_artifacts": candidate_artifacts,
        "training_package_dir": training_package_dir,
        "training_artifacts": training_artifacts,
        "benchmark_summary_path": benchmark_summary_path,
        "state2_review": state2_review,
        "state2_promotion": state2_promotion,
        "state1_handoff": state1_handoff,
        "state1_freeze": state1_freeze,
        "training_manifest": training_manifest,
        "benchmark_summary": benchmark_summary,
        "artifact_inputs": artifact_inputs,
        "telemetry_window": {
            "start": isoformat_utc(min(timestamp_fields)),
            "end": isoformat_utc(max(timestamp_fields)),
        },
    }


def runtime_metric(context: Dict[str, Any], name: str, default: float = 0.0) -> float:
    return float(context["runtime_signal"].get("metrics", {}).get(name, default))


def review_metric(context: Dict[str, Any], name: str, default: float = 0.0) -> float:
    review = context.get("state2_review") or {}
    return float(review.get("review_metrics", {}).get(name, default))


def approval_ratio(context: Dict[str, Any]) -> float:
    return truthy_ratio(
        [
            bool((context.get("state2_review") or {}).get("decision", {}).get("approved")),
            bool((context.get("state2_promotion") or {}).get("decision", {}).get("approved")),
            bool((context.get("state1_handoff") or {}).get("decision", {}).get("approved")),
            bool((context.get("state1_freeze") or {}).get("decision", {}).get("approved")),
        ]
    )


def governance_artifact_ratio(context: Dict[str, Any]) -> float:
    return artifact_exists_ratio(
        [
            context["candidate_artifacts"]["state2_review_path"],
            context["candidate_artifacts"]["state2_promotion_path"],
            context["candidate_artifacts"]["state1_handoff_path"],
            context["candidate_artifacts"]["state1_freeze_path"],
            context["training_artifacts"]["training_manifest_path"],
            context["run_reference_path"],
            context["runtime_signal_path"],
            context["candidate_artifacts"]["manifest_path"],
            context["candidate_artifacts"]["lineage_path"],
        ]
    )


def evidence_integrity_ratio(context: Dict[str, Any]) -> float:
    run_record = context["run_record"]
    expected_paths = [
        context["runtime_signal_path"],
        context["run_reference_path"],
        context["candidate_artifacts"]["state2_review_path"],
        context["candidate_artifacts"]["state2_promotion_path"],
        context["candidate_artifacts"]["state1_handoff_path"],
        context["candidate_artifacts"]["state1_freeze_path"],
        context["training_artifacts"]["training_manifest_path"],
    ]
    ratio = artifact_exists_ratio(expected_paths)
    record_path_matches = (
        str(run_record.get("run_reference_path", "")).replace("\\", "/")
        == relativize_if_possible(context["run_reference_path"])
    )
    signal_path_matches = (
        str(run_record.get("signal_path", "")).replace("\\", "/")
        == relativize_if_possible(context["runtime_signal_path"])
    )
    ratio = 0.8 * ratio + 0.1 * float(record_path_matches) + 0.1 * float(signal_path_matches)
    return clamp(ratio, 0.0, 1.0)


def benchmark_status(context: Dict[str, Any]) -> str:
    return str((context.get("benchmark_summary") or {}).get("status") or "").strip().lower()


def benchmark_is_clean(context: Dict[str, Any]) -> bool:
    benchmark_summary = context.get("benchmark_summary") or {}
    status = benchmark_status(context)
    execution = benchmark_summary.get("execution") or {}
    return status in {"success", "completed"} and not bool(execution.get("timed_out"))


def benchmark_quality_ratio(context: Dict[str, Any]) -> float:
    benchmark_summary = context.get("benchmark_summary") or {}
    if not benchmark_summary:
        return 0.0

    run = benchmark_summary.get("run") or {}
    configuration = benchmark_summary.get("configuration") or {}
    environment = benchmark_summary.get("environment") or {}
    wrapper_probe = benchmark_summary.get("wrapper_probe") or {}
    checks = [
        benchmark_is_clean(context),
        str(benchmark_summary.get("execution_surface") or "").strip().lower() == "safe_wrapper",
        bool(wrapper_probe),
        bool(run.get("dataset_ref")),
        str(run.get("device") or "").strip().lower() not in {"", "unknown"},
        any(configuration.get(key) is not None for key in ("seq_len", "batch_size", "steps", "top_k", "num_experts")),
        bool(environment) and bool(environment.get("manifest_repo_root_matches_current")),
    ]
    return truthy_ratio(checks)


def benchmark_readiness_penalty(
    context: Dict[str, Any],
    *,
    failure_penalty: float = 0.0,
    timeout_penalty: float = 0.0,
) -> float:
    benchmark_summary = context.get("benchmark_summary") or {}
    penalty = 0.0
    status = benchmark_status(context)
    if status and not benchmark_is_clean(context):
        penalty += failure_penalty
    if bool((benchmark_summary.get("execution") or {}).get("timed_out")):
        penalty += timeout_penalty
    return penalty


def queryability_penalty(context: Dict[str, Any], penalty: float) -> float:
    return 0.0 if bool(context["run_reference"].get("frozen_output_queryable")) else penalty


def proxy_ratio_cap(confidence: float, evidence_ratio: float, *, upper: float = 0.985) -> float:
    return clamp(0.92 + 0.05 * confidence + 0.02 * clamp(evidence_ratio, 0.0, 1.0), 0.0, upper)


def sector_partner_attestation_ratio(context: Dict[str, Any]) -> float:
    training_manifest = context.get("training_manifest") or {}
    checks = [
        bool((context.get("state2_review") or {}).get("decision", {}).get("approved")),
        bool((context.get("state2_promotion") or {}).get("decision", {}).get("approved")),
        bool((context.get("state1_handoff") or {}).get("decision", {}).get("approved")),
        bool((context.get("state1_freeze") or {}).get("decision", {}).get("approved")),
        bool(context["run_reference"].get("inspection_ready")),
        bool(context["run_record"].get("eligible_for_state_2")),
        str(training_manifest.get("registry_state")) == "STATE_1",
        bool(training_manifest.get("registry_entry_id")),
    ]
    return round_ratio(0.82 + 0.18 * truthy_ratio(checks))


def sector_policy_pass_ratio(context: Dict[str, Any]) -> float:
    training_manifest = context.get("training_manifest") or {}
    checks = [
        bool((context["runtime_signal"].get("authorization", {}) or {}).get("human_review_required")),
        bool((context["runtime_signal"].get("validation", {}) or {}).get("candidate_for_validation")),
        bool((context["runtime_signal"].get("governance_flags", {}) or {}).get("promotion_blocked")),
        bool((context.get("state2_review") or {}).get("posture", {}).get("governance_first")),
        review_metric(context, "routing_mismatch_count") == 0,
        review_metric(context, "missing_content_count") == 0,
        str(training_manifest.get("registry_state")) == "STATE_1",
        bool((training_manifest.get("authorization_posture", {}) or {}).get("training_preparation_only")),
    ]
    return round_ratio(0.84 + 0.16 * truthy_ratio(checks))


def sector_market_integrity_ratio(context: Dict[str, Any]) -> float:
    value = (
        0.52
        + 0.10 * runtime_metric(context, "stability")
        + 0.08 * runtime_metric(context, "coherence")
        + 0.08 * (1.0 - runtime_metric(context, "ambiguity"))
        + 0.06 * float(bool((context.get("state2_review") or {}).get("decision", {}).get("approved")))
        + 0.04 * float(review_metric(context, "routing_mismatch_count") == 0)
    )
    return round_ratio(value)


def sector_audit_interop_ratio(context: Dict[str, Any]) -> float:
    run_record = context["run_record"]
    relative_path_checks = [
        "/" in str(run_record.get("run_reference_path", "")).replace("\\", "/"),
        "/" in str(run_record.get("signal_path", "")).replace("\\", "/"),
        "/" in str(run_record.get("routing_log_path", "")).replace("\\", "/"),
    ]
    checks = [
        context["candidate_artifacts"]["state2_review_path"].exists(),
        context["candidate_artifacts"]["state2_promotion_path"].exists(),
        context["candidate_artifacts"]["state1_handoff_path"].exists(),
        context["candidate_artifacts"]["state1_freeze_path"].exists(),
        context["training_artifacts"]["training_manifest_path"].exists(),
        bool(context["run_reference"].get("inspection_ready")),
        bool((context.get("state1_freeze") or {}).get("decision", {}).get("approved")),
        bool((context.get("training_manifest") or {}).get("registry_entry_id")),
        truthy_ratio(relative_path_checks) >= 1.0,
    ]
    return round_ratio(0.80 + 0.20 * truthy_ratio(checks))


def metric_priority_weight(metric_config: Dict[str, Any]) -> float:
    return 1.2 if str(metric_config.get("priority")) == "core" else 1.0


def build_observation(
    metric_config: Dict[str, Any],
    context: Dict[str, Any],
    value: float,
    confidence: float,
    method: str,
    note: str,
) -> Dict[str, Any]:
    preferred_sources = metric_config.get("preferred_sources", [])
    source_map = {
        "path2_runtime_signal": context["artifact_inputs"]["runtime_signal_path"],
        "shared_run_registry": context["artifact_inputs"]["run_registry_path"],
        "path2_governance_review": context["artifact_inputs"]["candidate_package_dir"],
        "path2_training_package": context["artifact_inputs"]["training_package_dir"],
        "model_evaluation_summary": context["artifact_inputs"]["benchmark_summary_path"],
    }
    return {
        "metric_id": metric_config["metric_id"],
        "value": value,
        "confidence": round(clamp(confidence, 0.0, 1.0), 2),
        "weight": metric_priority_weight(metric_config),
        "telemetry_start": context["telemetry_window"]["start"],
        "telemetry_end": context["telemetry_window"]["end"],
        "draft_status": "provisional",
        "derivation_method": method,
        "derivation_note": note,
        "source_artifacts": [source_map[source] for source in preferred_sources if source in source_map],
    }


def map_sec_policy_enforce_success(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    routing_bonus = 0.02 if context["run_record"].get("routing_decision") == "SEND_TO_STATE_2_REVIEW" else 0.0
    eligible_bonus = 0.01 if bool(context["run_record"].get("eligible_for_state_2")) else 0.0
    success_bonus = 0.03 if context["run_record"].get("status") == "success" else 0.0
    value = round_ratio(
        0.90
        + success_bonus
        + routing_bonus
        + eligible_bonus
        + 0.03 * runtime_metric(context, "stability")
        + 0.02 * runtime_metric(context, "coherence")
        - 0.05 * runtime_metric(context, "ambiguity")
    )
    return build_observation(
        metric_config,
        context,
        value,
        0.74,
        "proxy_runtime_success_and_routing",
        "Draft proxy from successful runtime signal execution, state routing, and low ambiguity in the live Path 2 signal.",
    )


def map_sec_evidence_integrity_pass(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    value = round_ratio(evidence_integrity_ratio(context))
    return build_observation(
        metric_config,
        context,
        value,
        0.9,
        "artifact_presence_and_registry_path_match",
        "Derived from the presence of core governed artifacts and matching registry references for the live runtime signal chain.",
    )


def map_hard_supplychain_attest_coverage(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    benchmark_manifest_path = None
    if context.get("benchmark_summary"):
        manifest_rel = context["benchmark_summary"].get("manifest_path")
        if manifest_rel:
            benchmark_manifest_path = resolve_path(str(manifest_rel))
    coverage_ratio = artifact_exists_ratio(
        [
            context.get("benchmark_summary_path"),
            benchmark_manifest_path,
            context["training_artifacts"]["backend_profile_path"],
            context["candidate_artifacts"]["manifest_path"],
        ]
    )
    quality_ratio = benchmark_quality_ratio(context)
    value = round_ratio(0.62 + 0.20 * coverage_ratio + 0.10 * quality_ratio)
    return build_observation(
        metric_config,
        context,
        value,
        0.58,
        "attestation_ready_artifact_proxy_with_runtime_quality",
        "Proxy from the presence of benchmark, model, backend profile, and governed package artifacts, with a small quality uplift when the linked benchmark path is clean, wrapper-backed, and metadata-complete.",
    )


def map_hard_key_mgmt_health(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    endpoint_local = str((context["run_reference"].get("model", {}) or {}).get("endpoint_type")) == "local"
    inspection_ready = bool(context["run_reference"].get("inspection_ready"))
    value = round_score(
        60
        + 10 * float(context["run_record"].get("status") == "success")
        + 10 * float(inspection_ready)
        + 10 * evidence_integrity_ratio(context)
        + 5 * float(endpoint_local)
    )
    return build_observation(
        metric_config,
        context,
        value,
        0.52,
        "control_health_proxy_from_local_execution",
        "Proxy score from local endpoint posture, inspection readiness, and evidence integrity. This should be replaced by explicit key-management telemetry later.",
    )


def map_hard_telemetry_completeness(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    run_record = context["run_record"]
    run_reference = context["run_reference"]
    runtime_signal = context["runtime_signal"]
    benchmark_summary = context.get("benchmark_summary") or {}
    routing_log_path = (
        resolve_path(run_record.get("routing_log_path"))
        if run_record.get("routing_log_path")
        else None
    )
    artifact_checks = [
        context["runtime_signal_path"].exists(),
        bool(routing_log_path and routing_log_path.exists()),
        context["run_reference_path"].exists(),
        context["candidate_artifacts"]["state2_review_path"].exists(),
        context["candidate_artifacts"]["state2_promotion_path"].exists(),
        context["candidate_artifacts"]["state1_handoff_path"].exists(),
        context["candidate_artifacts"]["state1_freeze_path"].exists(),
        context["training_artifacts"]["training_manifest_path"].exists(),
        context["training_artifacts"]["training_preview_path"].exists(),
        context["training_artifacts"]["backend_profile_path"].exists(),
    ]
    telemetry_checks = [
        bool((context["runtime_signal"].get("signal", {}) or {}).get("structured_summary")),
        bool((runtime_signal.get("signal", {}) or {}).get("raw_output")),
        bool((runtime_signal.get("signal", {}) or {}).get("tags")),
        bool(context["runtime_signal"].get("routing_trace")),
        bool(context["run_reference"].get("validation")),
        bool(run_record.get("routing_log_path")),
    ]
    artifact_ratio = truthy_ratio(artifact_checks)
    telemetry_ratio = truthy_ratio(telemetry_checks)
    queryability_adjustment = 0.02 if bool(run_reference.get("frozen_output_queryable")) else -0.02
    benchmark_penalty = 0.01 if not benchmark_is_clean(context) else 0.0
    benchmark_quality_bonus = 0.01 * benchmark_quality_ratio(context)
    value = round_ratio(
        0.83
        + 0.08 * artifact_ratio
        + 0.08 * telemetry_ratio
        + 0.03 * float(bool((run_reference.get("validation") or {}).get("validation_requested")))
        + benchmark_quality_bonus
        + queryability_adjustment
        - benchmark_penalty
    )
    return build_observation(
        metric_config,
        context,
        value,
        0.74,
        "cross_artifact_telemetry_with_queryability_penalty",
        "Derived from runtime, routing, review, freeze, and training telemetry continuity, with a small uplift when the linked benchmark path is clean and metadata-rich, but still penalized when outputs remain non-queryable.",
    )


def map_comp_change_approval_trace(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    value = round_ratio(approval_ratio(context))
    return build_observation(
        metric_config,
        context,
        value,
        0.88,
        "review_promotion_handoff_freeze_approval_ratio",
        "Derived from the governed Path 2 approval chain across review, promotion, handoff, and freeze artifacts.",
    )


def map_comp_policy_trace_coverage(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = context.get("training_manifest") or {}
    review_ready_ratio = clamp(review_metric(context, "review_ready_ratio", 0.0), 0.0, 1.0)
    governance_first = bool((context.get("state2_review") or {}).get("posture", {}).get("governance_first"))
    human_review_required = bool((context["runtime_signal"].get("authorization", {}) or {}).get("human_review_required"))
    frozen_manifest_present = bool((training_manifest.get("source", {}) or {}).get("frozen_manifest_path"))
    trace_checks = [
        governance_first,
        human_review_required,
        frozen_manifest_present,
        review_metric(context, "routing_mismatch_count") == 0,
        review_metric(context, "missing_content_count") == 0,
    ]
    trace_ratio = truthy_ratio(trace_checks)
    evidence_ratio = clamp(
        0.45 * trace_ratio
        + 0.30 * review_ready_ratio
        + 0.25 * evidence_integrity_ratio(context)
    , 0.0, 1.0)
    raw_value = (
        0.70
        + 0.12 * approval_ratio(context)
        + 0.08 * review_ready_ratio
        + 0.10 * trace_ratio
        + 0.015 * evidence_integrity_ratio(context)
        - queryability_penalty(context, 0.008)
        - benchmark_readiness_penalty(context, failure_penalty=0.004, timeout_penalty=0.003)
    )
    value = round_ratio(min(raw_value, proxy_ratio_cap(0.76, evidence_ratio)))
    return build_observation(
        metric_config,
        context,
        value,
        0.76,
        "approval_trace_with_readiness_aware_cap",
        "Derived from the governed approval chain, policy-first review posture, and frozen-manifest linkage, then capped for proxy-only evidence and reduced when outputs remain non-queryable or the linked benchmark is not yet in a clean success state.",
    )


def map_gov_model_approval_trace(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = context.get("training_manifest") or {}
    checks = [
        bool((context.get("state2_review") or {}).get("decision", {}).get("approved")),
        bool((context.get("state2_promotion") or {}).get("decision", {}).get("approved")),
        bool((context.get("state1_handoff") or {}).get("decision", {}).get("approved")),
        str(training_manifest.get("registry_state")) == "STATE_1",
        str(training_manifest.get("dataset_version", "")) == context["candidate_package_dir"].name,
    ]
    value = round_ratio(truthy_ratio(checks))
    return build_observation(
        metric_config,
        context,
        value,
        0.86,
        "governed_model_approval_chain_ratio",
        "Derived from approval-chain continuity into the STATE_1 training package and registry state.",
    )


def map_trn_decision_trace_rate(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = context.get("training_manifest") or {}
    backend_profile = training_manifest.get("backend_profile", {}) or {}
    checks = [
        bool((context["runtime_signal"].get("signal", {}) or {}).get("structured_summary")),
        bool(backend_profile.get("include_metadata")),
        context["training_artifacts"]["train_file_path"].exists(),
        context["training_artifacts"]["training_preview_path"].exists(),
        str(training_manifest.get("registry_state")) == "STATE_1",
    ]
    value = round_ratio(truthy_ratio(checks))
    return build_observation(
        metric_config,
        context,
        value,
        0.72,
        "training_traceability_artifact_ratio",
        "Derived from structured runtime summaries and the traceable training package outputs present in the live Path 2 export.",
    )


def map_sector_market_integrity_signal(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    mix = normalized_source_mix(
        metric_config,
        {
            "market_integrity": 1.0,
        },
    )
    blended_ratio = weighted_signal_ratio(
        {
            "market_integrity": sector_market_integrity_ratio(context),
            "partner_attestations": sector_partner_attestation_ratio(context),
            "policy_pass": sector_policy_pass_ratio(context),
            "audit_interop": sector_audit_interop_ratio(context),
        },
        mix,
    )
    value = round_score(70 + 25 * blended_ratio)
    return build_observation(
        metric_config,
        context,
        value,
        0.62,
        "sector_signal_blend_proxy",
        (
            "Proxy score from configurable sector-signal weighting. "
            f"Current blend: {format_source_mix(mix)}."
        ),
    )


def map_sec_output_safety_viol_rate(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    candidate_count = max(int(review_metric(context, "candidate_count", 1)), 1)
    value = round_ratio(
        0.001
        + 0.01 * runtime_metric(context, "ambiguity")
        + 0.01 * review_metric(context, "missing_content_count") / candidate_count
        + 0.01 * review_metric(context, "routing_mismatch_count") / candidate_count
        + (0.0 if bool((context["runtime_signal"].get("authorization", {}) or {}).get("human_review_required")) else 0.005)
    )
    return build_observation(
        metric_config,
        context,
        value,
        0.56,
        "governed_output_safety_proxy",
        "Proxy from low ambiguity, zero review exceptions, and mandatory human review in the live Path 2 governance chain.",
    )


def map_hard_privacy_test_pass_rate(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = context.get("training_manifest") or {}
    run_reference = context["run_reference"]
    auth_posture = training_manifest.get("authorization_posture", {}) or {}
    record_counts = training_manifest.get("record_counts", {}) or {}
    checks = [
        bool(auth_posture.get("training_preparation_only")),
        int(record_counts.get("fine_tuning_allowed_count", 0)) == 0,
        bool((context["runtime_signal"].get("authorization", {}) or {}).get("human_review_required")),
        bool((context.get("state2_review") or {}).get("posture", {}).get("governance_first")),
    ]
    privacy_penalty = benchmark_readiness_penalty(context, failure_penalty=0.015, timeout_penalty=0.005)
    privacy_penalty += queryability_penalty(context, 0.005)
    quality_bonus = 0.015 * benchmark_quality_ratio(context)
    value = round_ratio(0.86 + 0.1 * truthy_ratio(checks) + quality_bonus - privacy_penalty)
    return build_observation(
        metric_config,
        context,
        value,
        0.42,
        "privacy_control_proxy_with_benchmark_readiness_penalty",
        "Policy proxy from controlled training posture and human-review requirements, with a modest uplift when the linked benchmark path is clean and metadata-rich, but still reduced when outputs remain non-queryable. Replace with explicit privacy benchmark telemetry when available.",
    )


def map_comp_model_lineage_coverage(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = context.get("training_manifest") or {}
    frozen_manifest_path = resolve_path(training_manifest.get("source", {}).get("frozen_manifest_path")) if training_manifest.get("source", {}).get("frozen_manifest_path") else None
    checks = [
        context["candidate_artifacts"]["lineage_path"].exists(),
        context["candidate_artifacts"]["manifest_path"].exists(),
        bool((context.get("state2_review") or {}).get("decision", {}).get("approved")),
        bool((context.get("state2_promotion") or {}).get("decision", {}).get("approved")),
        bool((context.get("state1_handoff") or {}).get("decision", {}).get("approved")),
        bool((context.get("state1_freeze") or {}).get("decision", {}).get("approved")),
        bool(training_manifest.get("registry_entry_id")),
        bool(frozen_manifest_path and frozen_manifest_path.exists()),
    ]
    check_ratio = truthy_ratio(checks)
    evidence_ratio = clamp(
        0.50 * check_ratio
        + 0.25 * approval_ratio(context)
        + 0.25 * evidence_integrity_ratio(context)
    , 0.0, 1.0)
    raw_value = (
        0.89
        + 0.05 * check_ratio
        + 0.02 * approval_ratio(context)
        + 0.02 * evidence_integrity_ratio(context)
        - queryability_penalty(context, 0.005)
        - benchmark_readiness_penalty(context, failure_penalty=0.002, timeout_penalty=0.001)
    )
    value = round_ratio(min(raw_value, proxy_ratio_cap(0.78, evidence_ratio)))
    return build_observation(
        metric_config,
        context,
        value,
        0.78,
        "governed_lineage_chain_with_readiness_cap",
        "Derived from lineage, approval, freeze, and registry links across the Path 2 package chain, then bounded so proxy-only lineage evidence does not score as fully complete while runtime outputs remain non-queryable or linked benchmark evidence is still degraded.",
    )


def map_gov_hil_review_coverage(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    review_ready_ratio = clamp(review_metric(context, "review_ready_ratio", 0.0), 0.0, 1.0)
    candidate_count_ratio = clamp(review_metric(context, "candidate_count", 0.0) / 5.0, 0.0, 1.0)
    checks = [
        bool((context["runtime_signal"].get("authorization", {}) or {}).get("human_review_required")),
        bool((context.get("state2_review") or {}).get("decision", {}).get("approved")),
        review_ready_ratio >= 1.0,
        review_metric(context, "routing_mismatch_count") == 0,
    ]
    check_ratio = truthy_ratio(checks)
    evidence_ratio = clamp(
        0.50 * check_ratio
        + 0.30 * review_ready_ratio
        + 0.20 * candidate_count_ratio
    , 0.0, 1.0)
    raw_value = (
        0.90
        + 0.04 * check_ratio
        + 0.02 * review_ready_ratio
        + 0.02 * candidate_count_ratio
        + 0.01 * approval_ratio(context)
    )
    value = round_ratio(min(raw_value, proxy_ratio_cap(0.82, evidence_ratio)))
    return build_observation(
        metric_config,
        context,
        value,
        0.82,
        "human_review_control_ratio_with_sample_floor",
        "Derived from required human review, approved STATE_2 review, full review readiness, and a small governed sample-size floor so human oversight coverage stays strong without saturating purely from approval-chain completeness.",
    )


def map_gov_audit_evidence_coverage(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    run_record = context["run_record"]
    relative_path_checks = [
        "/" in str(run_record.get("run_reference_path", "")).replace("\\", "/"),
        "/" in str(run_record.get("signal_path", "")).replace("\\", "/"),
        "/" in str(run_record.get("routing_log_path", "")).replace("\\", "/"),
    ]
    governance_ratio = governance_artifact_ratio(context)
    path_ratio = truthy_ratio(relative_path_checks)
    evidence_ratio = clamp(
        0.45 * governance_ratio
        + 0.35 * evidence_integrity_ratio(context)
        + 0.20 * path_ratio
    , 0.0, 1.0)
    raw_value = (
        0.90
        + 0.04 * governance_ratio
        + 0.02 * evidence_integrity_ratio(context)
        + 0.015 * approval_ratio(context)
        + 0.01 * path_ratio
        - queryability_penalty(context, 0.005)
    )
    value = round_ratio(min(raw_value, proxy_ratio_cap(0.80, evidence_ratio)))
    return build_observation(
        metric_config,
        context,
        value,
        0.80,
        "governed_artifact_presence_with_audit_quality_cap",
        "Derived from the presence of review, promotion, handoff, freeze, registry, runtime, and training artifacts, then bounded by cross-artifact evidence quality so audit coverage does not saturate from artifact presence alone.",
    )


def map_trn_explain_complete(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = context.get("training_manifest") or {}
    checks = [
        bool((context["runtime_signal"].get("signal", {}) or {}).get("structured_summary")),
        bool((training_manifest.get("backend_profile", {}) or {}).get("include_metadata")),
        context["training_artifacts"]["training_preview_path"].exists(),
        context["training_artifacts"]["backend_profile_path"].exists(),
    ]
    value = round_ratio(0.75 + 0.25 * truthy_ratio(checks))
    return build_observation(
        metric_config,
        context,
        value,
        0.63,
        "structured_summary_and_metadata_proxy",
        "Proxy from structured runtime summaries plus the metadata-rich training export package.",
    )


def map_trn_harm_event_rate(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    candidate_count = max(int(review_metric(context, "candidate_count", 1)), 1)
    value = round_score(
        0.5
        + 5 * runtime_metric(context, "ambiguity")
        + 5 * review_metric(context, "missing_content_count") / candidate_count
        + (0.0 if bool((context["runtime_signal"].get("authorization", {}) or {}).get("human_review_required")) else 1.5)
        + (0.0 if bool((context.get("state2_review") or {}).get("decision", {}).get("approved")) else 2.0)
    )
    return build_observation(
        metric_config,
        context,
        value,
        0.47,
        "harm_proxy_from_review_exceptions",
        "Low provisional harm-event rate derived from zero review exceptions and mandatory human oversight. Replace with validated harm telemetry when available.",
    )


def map_hard_patch_latency(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    review = context.get("state2_review") or {}
    freeze = context.get("state1_freeze") or {}
    raw_hours = 24.0
    if review.get("review_timestamp") and freeze.get("freeze_timestamp"):
        delta = parse_datetime(str(freeze["freeze_timestamp"])) - parse_datetime(str(review["review_timestamp"]))
        raw_hours = max(24.0, delta.total_seconds() / 3600.0)
    if review_metric(context, "missing_content_count") > 0 or review_metric(context, "routing_mismatch_count") > 0:
        raw_hours += 24.0
    return build_observation(
        metric_config,
        context,
        round(raw_hours, 1),
        0.41,
        "governed_resolution_latency_floor",
        "Draft proxy from the elapsed governed review-to-freeze window, with a 24-hour floor because direct patch-event telemetry is not yet available.",
    )


def map_comp_time_to_adapt(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    review = context.get("state2_review") or {}
    training_manifest = context.get("training_manifest") or {}
    raw_hours = 1.0
    if review.get("review_timestamp") and training_manifest.get("generated_at"):
        delta = parse_datetime(str(training_manifest["generated_at"])) - parse_datetime(str(review["review_timestamp"]))
        raw_hours = max(1.0, delta.total_seconds() / 3600.0)
    return build_observation(
        metric_config,
        context,
        round(raw_hours, 1),
        0.69,
        "review_to_training_adaptation_window",
        "Derived from the elapsed time between governed review selection and training package generation, with a 1-hour floor for same-window approvals.",
    )


def map_trn_model_limits_disclosed(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    training_manifest = context.get("training_manifest") or {}
    backend_profile = training_manifest.get("backend_profile", {}) or {}
    benchmark_summary = context.get("benchmark_summary") or {}
    checks = [
        bool(backend_profile.get("model", {}).get("model_base")),
        bool(backend_profile.get("notes")),
        bool(training_manifest.get("authorization_posture")),
        bool(training_manifest.get("source", {}).get("frozen_manifest_path")),
        bool(benchmark_summary.get("model", {}).get("variant")),
    ]
    value = round_ratio(0.7 + 0.3 * truthy_ratio(checks))
    return build_observation(
        metric_config,
        context,
        value,
        0.6,
        "model_limits_disclosure_proxy",
        "Proxy from model identification, backend notes, authorization posture, and benchmark lineage fields that expose operational limits to reviewers.",
    )


def map_sector_policy_pass_rate(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    mix = normalized_source_mix(
        metric_config,
        {
            "policy_pass": 1.0,
        },
    )
    blended_ratio = weighted_signal_ratio(
        {
            "policy_pass": sector_policy_pass_ratio(context),
            "market_integrity": sector_market_integrity_ratio(context),
            "partner_attestations": sector_partner_attestation_ratio(context),
            "audit_interop": sector_audit_interop_ratio(context),
        },
        mix,
    )
    evidence_ratio = clamp(
        0.40 * blended_ratio
        + 0.30 * approval_ratio(context)
        + 0.30 * evidence_integrity_ratio(context)
    , 0.0, 1.0)
    raw_value = (
        0.86
        + 0.09 * blended_ratio
        + 0.02 * approval_ratio(context)
        + 0.015 * evidence_integrity_ratio(context)
        - queryability_penalty(context, 0.015)
        - benchmark_readiness_penalty(context, failure_penalty=0.006, timeout_penalty=0.003)
    )
    value = round_ratio(min(raw_value, proxy_ratio_cap(0.70, evidence_ratio)))
    return build_observation(
        metric_config,
        context,
        value,
        0.70,
        "sector_policy_signal_blend_with_readiness_cap",
        (
            "Draft sector policy pass proxy from configurable sector evidence weighting, bounded so execution-independent approval signals do not overstate live operational readiness. "
            f"Current blend: {format_source_mix(mix)}."
        ),
    )


def map_sector_partner_attest_rate(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    mix = normalized_source_mix(
        metric_config,
        {
            "partner_attestations": 1.0,
        },
    )
    blended_ratio = weighted_signal_ratio(
        {
            "partner_attestations": sector_partner_attestation_ratio(context),
            "market_integrity": sector_market_integrity_ratio(context),
            "policy_pass": sector_policy_pass_ratio(context),
            "audit_interop": sector_audit_interop_ratio(context),
        },
        mix,
    )
    value = round_ratio(0.80 + 0.18 * blended_ratio)
    return build_observation(
        metric_config,
        context,
        value,
        0.76,
        "partner_attestation_signal_blend",
        (
            "Draft partner-attestation proxy from configurable sector evidence weighting. "
            f"Current blend: {format_source_mix(mix)}."
        ),
    )


def map_sector_audit_interop_score(metric_config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    mix = normalized_source_mix(
        metric_config,
        {
            "audit_interop": 1.0,
        },
    )
    blended_ratio = weighted_signal_ratio(
        {
            "audit_interop": sector_audit_interop_ratio(context),
            "partner_attestations": sector_partner_attestation_ratio(context),
            "market_integrity": sector_market_integrity_ratio(context),
            "policy_pass": sector_policy_pass_ratio(context),
        },
        mix,
    )
    evidence_ratio = clamp(
        0.45 * blended_ratio
        + 0.35 * evidence_integrity_ratio(context)
        + 0.20 * approval_ratio(context)
    , 0.0, 1.0)
    raw_score = (
        75
        + 12 * blended_ratio
        + 4 * evidence_integrity_ratio(context)
        + 4 * approval_ratio(context)
        - (1.5 if not bool(context["run_reference"].get("frozen_output_queryable")) else 0.0)
        - (1.5 if (benchmark_status(context) and not benchmark_is_clean(context)) else 0.0)
        - (0.5 if bool((context.get("benchmark_summary") or {}).get("execution", {}).get("timed_out")) else 0.0)
    )
    score_cap = 70 + 25 * proxy_ratio_cap(0.66, evidence_ratio)
    score = round_score(min(raw_score, score_cap))
    return build_observation(
        metric_config,
        context,
        score,
        0.66,
        "audit_interoperability_signal_blend_with_readiness_cap",
        (
            "Draft audit interoperability score from configurable sector evidence weighting, with readiness penalties when queryable outputs and clean linked benchmark evidence are still missing. "
            f"Current blend: {format_source_mix(mix)}."
        ),
    )


MAPPING_FUNCTIONS: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = {
    "SEC_POLICY_ENFORCE_SUCCESS": map_sec_policy_enforce_success,
    "SEC_EVIDENCE_INTEGRITY_PASS": map_sec_evidence_integrity_pass,
    "HARD_SUPPLYCHAIN_ATTEST_COVERAGE": map_hard_supplychain_attest_coverage,
    "HARD_KEY_MGMT_HEALTH": map_hard_key_mgmt_health,
    "HARD_TELEMETRY_COMPLETENESS": map_hard_telemetry_completeness,
    "COMP_CHANGE_APPROVAL_TRACE": map_comp_change_approval_trace,
    "COMP_POLICY_TRACE_COVERAGE": map_comp_policy_trace_coverage,
    "GOV_MODEL_APPROVAL_TRACE": map_gov_model_approval_trace,
    "TRN_DECISION_TRACE_RATE": map_trn_decision_trace_rate,
    "SECTOR_MARKET_INTEGRITY_SIGNAL": map_sector_market_integrity_signal,
    "SEC_OUTPUT_SAFETY_VIOL_RATE": map_sec_output_safety_viol_rate,
    "HARD_PRIVACY_TEST_PASS_RATE": map_hard_privacy_test_pass_rate,
    "COMP_MODEL_LINEAGE_COVERAGE": map_comp_model_lineage_coverage,
    "GOV_HIL_REVIEW_COVERAGE": map_gov_hil_review_coverage,
    "GOV_AUDIT_EVIDENCE_COVERAGE": map_gov_audit_evidence_coverage,
    "TRN_EXPLAIN_COMPLETE": map_trn_explain_complete,
    "TRN_HARM_EVENT_RATE": map_trn_harm_event_rate,
    "HARD_PATCH_LATENCY": map_hard_patch_latency,
    "COMP_TIME_TO_ADAPT": map_comp_time_to_adapt,
    "TRN_MODEL_LIMITS_DISCLOSED": map_trn_model_limits_disclosed,
    "SECTOR_POLICY_PASS_RATE": map_sector_policy_pass_rate,
    "SECTOR_PARTNER_ATTEST_RATE": map_sector_partner_attest_rate,
    "SECTOR_AUDIT_INTEROP_SCORE": map_sector_audit_interop_score,
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build draft CSC metric observations from a mapper blueprint and live Path 2 artifacts."
    )
    parser.add_argument(
        "--blueprint",
        default=str(DEFAULT_BLUEPRINT_PATH),
        help=f"Mapper blueprint JSON. Default: {DEFAULT_BLUEPRINT_PATH}",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help=(
            "Optional mapper scenario overlay JSON. "
            f"Recommended location: {ACCESS_POD_LOCAL_MAPPER_SCENARIOS_ROOT}"
        ),
    )
    parser.add_argument(
        "--runtime-signal",
        default=None,
        help="Optional explicit runtime signal JSON path. Defaults to the latest Path 2 runtime signal.",
    )
    parser.add_argument(
        "--run-reference",
        default=None,
        help="Optional explicit runtime run reference path. Defaults to the latest runtime signal run reference.",
    )
    parser.add_argument(
        "--run-registry",
        default=str(SHARED_RUN_REGISTRY_PATH),
        help=f"Shared run registry JSON. Default: {SHARED_RUN_REGISTRY_PATH}",
    )
    parser.add_argument(
        "--candidate-package-dir",
        default=None,
        help="Optional explicit Path 2 candidate package directory. Defaults to the latest reviewed package.",
    )
    parser.add_argument(
        "--training-package-dir",
        default=None,
        help="Optional explicit Path 2 training package directory. Defaults to the package matching the candidate version.",
    )
    parser.add_argument(
        "--benchmark-summary",
        default=None,
        help="Optional explicit benchmark summary JSON. Defaults to the latest grouped_sparse_e64 summary when available.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional explicit output path for the draft observation JSON.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        context = build_context(args)
        blueprint = context["blueprint"]
        metric_observations: List[Dict[str, Any]] = []
        unsupported_metrics: List[str] = []

        for metric_config in blueprint.get("metric_mapping", []):
            metric_id = str(metric_config.get("metric_id") or "").strip()
            ensure(metric_id, "Blueprint contains a metric mapping entry without metric_id.")
            mapper = MAPPING_FUNCTIONS.get(metric_id)
            if mapper is None:
                unsupported_metrics.append(metric_id)
                continue
            metric_observations.append(mapper(metric_config, context))

        ensure(not unsupported_metrics, f"Unsupported metric mappings: {', '.join(unsupported_metrics)}")

        profile_id = str(blueprint.get("profile_id") or "unknown_profile")
        generated_at = utc_now_iso()
        scenario_id = context.get("scenario_id") or ""
        scenario_label = context.get("scenario_label") or ""
        output_token = sanitize_token(
            f"{profile_id}__{scenario_id or 'default'}__{generated_at}"
        )
        out_path = (
            resolve_path(args.out)
            if args.out
            else DEFAULT_DRAFT_OUT_ROOT / f"{output_token}.metric_observation_draft.json"
        )

        draft = {
            "draft_version": "access_pod_metric_observation_draft_v1.0",
            "status": "completed",
            "generated_at_utc": generated_at,
            "profile_id": profile_id,
            "blueprint_path": relativize_if_possible(context["blueprint_path"]),
            "scenario_id": scenario_id or None,
            "scenario_label": scenario_label or None,
            "scenario_path": (
                relativize_if_possible(context["scenario_path"])
                if context.get("scenario_path")
                else None
            ),
            "purpose": blueprint.get("purpose"),
            "telemetry_window": context["telemetry_window"],
            "artifact_inputs": context["artifact_inputs"],
            "metric_observations": metric_observations,
            "notes": [
                "These observations are first-pass governed drafts derived from live Path 2 and shared registry artifacts.",
                "Observations marked by proxy-style derivation methods should be reviewed before being promoted into a formal CSC evidence input.",
                (
                    f"Scenario in use: {scenario_label} ({scenario_id})."
                    if scenario_id
                    else "No scenario overlay applied; using the canonical mapper blueprint."
                ),
            ],
        }

        write_json(out_path, draft)
        summary_path = sidecar_markdown_path(out_path)
        write_markdown(summary_path, render_mapper_draft_markdown(draft, out_path))

        result = {
            "status": "completed",
            "profile_id": profile_id,
            "scenario_id": scenario_id or None,
            "draft_path": str(out_path),
            "draft_summary_path": str(summary_path),
            "metric_count": len(metric_observations),
            "telemetry_window": context["telemetry_window"],
        }
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    except (MapperError, KeyError, TypeError, ValueError, OSError) as exc:
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
