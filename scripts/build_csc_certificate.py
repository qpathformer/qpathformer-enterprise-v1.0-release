#!/usr/bin/env python3
"""
Build a CSC certificate from Access-PoD v1a artifacts and enterprise evidence inputs.

This scorer treats the vendored Access-PoD release as the external contract
layer and maps enterprise-side evidence into a generated certificate plus a
scoring report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from access_pod_human_readable import (
    render_certificate_markdown,
    render_report_markdown,
    sidecar_markdown_path,
    write_markdown,
)
from path_layout import (
    ACCESS_POD_LOCAL_CERTIFICATES_ROOT,
    ACCESS_POD_LOCAL_EXAMPLES_ROOT,
    ACCESS_POD_LOCAL_PROFILE_EXTENSIONS_PATH,
    ACCESS_POD_LOCAL_REPORTS_ROOT,
    ACCESS_POD_LOCAL_SCHEMAS_ROOT,
    ACCESS_POD_VENDOR_V1A_CATALOGS_ROOT,
    ACCESS_POD_VENDOR_V1A_PROFILES_ROOT,
    ACCESS_POD_VENDOR_V1A_SCHEMAS_ROOT,
    REPO_ROOT,
)


DEFAULT_METRIC_CATALOG_PATH = ACCESS_POD_VENDOR_V1A_CATALOGS_ROOT / "csc_metric_catalog_v1a.json"
DEFAULT_SECTOR_PROFILES_PATH = ACCESS_POD_VENDOR_V1A_PROFILES_ROOT / "csc_sector_profiles_v1a.json"
DEFAULT_PROFILE_EXTENSIONS_PATH = ACCESS_POD_LOCAL_PROFILE_EXTENSIONS_PATH
DEFAULT_CERTIFICATE_SCHEMA_PATH = (
    ACCESS_POD_VENDOR_V1A_SCHEMAS_ROOT / "csc-certificate.schema_v1a.json"
)
DEFAULT_EVIDENCE_INPUT_SCHEMA_PATH = (
    ACCESS_POD_LOCAL_SCHEMAS_ROOT / "enterprise_csc_evidence_input.schema.json"
)
DEFAULT_CERTIFICATE_OUT_ROOT = ACCESS_POD_LOCAL_CERTIFICATES_ROOT
DEFAULT_REPORT_OUT_ROOT = ACCESS_POD_LOCAL_REPORTS_ROOT
DEFAULT_EXPIRES_IN_DAYS = 180
DEFAULT_TOP_METRICS_PER_FACTOR = 3
DEFAULT_MIN_OVERALL_COVERAGE_RATIO = 0.10
DEFAULT_MIN_METRICS_PER_FACTOR = 1
DEFAULT_MIN_FACTOR_SCORE = 60.0
DEFAULT_LEVEL_THRESHOLDS = {
    2: 60.0,
    3: 70.0,
    4: 80.0,
    5: 90.0,
    6: 97.0,
}


class CSCBuilderError(RuntimeError):
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
        raise CSCBuilderError(message)


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


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_hex_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def round_score(value: float) -> float:
    return round(value, 1)


def round_confidence(value: float) -> float:
    return round(clamp(value), 2)


def sanitize_token(raw: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(raw))
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned or "value"


def maybe_validate_json(payload: Dict[str, Any], schema_path: Path, label: str) -> None:
    try:
        import jsonschema  # type: ignore
    except Exception:
        return

    schema = read_json(schema_path)
    jsonschema.validate(payload, schema)


def infer_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def metric_key_from_factor(raw_factor: str) -> str:
    return f"f{raw_factor.replace('.', '_')}"


def parse_datetime(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_default_csc_id(subject_id: str, issued_at: str) -> str:
    return f"csc_{sanitize_token(subject_id)}_{issued_at.replace(':', '').replace('-', '')}"


def load_profile_document(path: Path) -> List[Dict[str, Any]]:
    payload = read_json(path)
    profiles = payload.get("profiles", [])
    ensure(isinstance(profiles, list) and profiles, f"No profiles found in {path}")
    return [item for item in profiles if isinstance(item, dict) and item.get("profile_id")]


def load_profiles(primary_path: Path, extension_path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for item in load_profile_document(primary_path):
        merged[str(item["profile_id"])] = item

    if extension_path is not None and extension_path.exists():
        for item in load_profile_document(extension_path):
            merged[str(item["profile_id"])] = item

    ensure(merged, f"No profiles found across {primary_path}")
    return merged


def load_metric_catalog(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    payload = read_json(path)
    metrics = payload.get("metrics", [])
    ensure(isinstance(metrics, list) and metrics, f"No metrics found in {path}")
    by_id: Dict[str, Dict[str, Any]] = {}
    by_factor: Dict[str, List[Dict[str, Any]]] = {}
    for item in metrics:
        metric_id = str(item.get("metric_id") or "").strip()
        factor = str(item.get("factor") or "").strip()
        ensure(metric_id, f"Metric missing metric_id in {path}")
        ensure(factor, f"Metric {metric_id} missing factor in {path}")
        by_id[metric_id] = item
        by_factor.setdefault(factor, []).append(item)
    return metrics, by_id, by_factor


def normalize_value(metric: Dict[str, Any], raw_value: float) -> float:
    normalization = metric.get("normalization", {}) or {}
    direction = str(metric.get("direction") or "")
    method = str(normalization.get("method") or "")
    cap = normalization.get("cap") or [raw_value, raw_value]
    capped = clamp(raw_value, float(cap[0]), float(cap[1]))

    if method == "minmax":
        low, high = normalization.get("good_range", [0.0, 1.0])
        low = float(low)
        high = float(high)
        if math.isclose(low, high):
            return 1.0
        if direction == "higher_is_better":
            return clamp((capped - low) / (high - low))
        if direction == "lower_is_better":
            return clamp((high - capped) / (high - low))
        raise CSCBuilderError(f"Unsupported minmax direction '{direction}' for {metric['metric_id']}")

    if method == "sigmoid":
        midpoint = float(normalization.get("midpoint", 0.0))
        steepness = float(normalization.get("steepness", 1.0))
        signed_delta = capped - midpoint
        if direction == "lower_is_better":
            signed_delta = midpoint - capped
        elif direction != "higher_is_better":
            raise CSCBuilderError(f"Unsupported sigmoid direction '{direction}' for {metric['metric_id']}")
        return clamp(1.0 / (1.0 + math.exp(-steepness * signed_delta)))

    if method == "target":
        target = float(normalization.get("target", 0.0))
        tolerance = float(normalization.get("tolerance", 1.0))
        ensure(tolerance > 0, f"Target normalization tolerance must be > 0 for {metric['metric_id']}")
        return clamp(1.0 - abs(capped - target) / tolerance)

    raise CSCBuilderError(f"Unsupported normalization method '{method}' for {metric['metric_id']}")


def detect_threshold_state(metric: Dict[str, Any], raw_value: float) -> Tuple[bool, bool]:
    thresholds = metric.get("thresholds", {}) or {}
    warning = thresholds.get("warning")
    critical = thresholds.get("critical")
    direction = str(metric.get("direction") or "")
    normalization = metric.get("normalization", {}) or {}

    def _fail(boundary: Optional[float]) -> bool:
        if boundary is None:
            return False
        boundary = float(boundary)
        if direction == "higher_is_better":
            return raw_value < boundary
        if direction == "lower_is_better":
            return raw_value > boundary
        if direction == "target_is_best":
            target = float(normalization.get("target", raw_value))
            if boundary >= target:
                return raw_value > boundary
            return raw_value < boundary
        return False

    return _fail(warning), _fail(critical)


def normalize_observation_weight(observation: Dict[str, Any]) -> float:
    raw_weight = observation.get("weight", 1.0)
    return max(0.0, float(raw_weight))


def normalize_observation_confidence(observation: Dict[str, Any]) -> float:
    return clamp(float(observation.get("confidence", 0.8)))


def resolve_observation_window(
    observation: Dict[str, Any],
    default_window: Dict[str, Any],
) -> Dict[str, str]:
    start = observation.get("telemetry_start") or default_window.get("start")
    end = observation.get("telemetry_end") or default_window.get("end")
    ensure(start and end, "Each observation requires telemetry window values or a top-level telemetry_window.")
    return {"start": str(start), "end": str(end)}


def finalize_evidence_item(item: Dict[str, Any]) -> Dict[str, Any]:
    digest_alg = str(item.get("digest_alg") or "sha256")
    ensure(digest_alg == "sha256", "Only sha256 evidence digests are currently supported.")

    path_value = item.get("path")
    uri_value = item.get("uri")
    resolved_path: Optional[Path] = None
    if path_value:
        resolved_path = resolve_path(str(path_value))
        ensure(resolved_path.exists(), f"Evidence item path not found: {resolved_path}")
        uri_value = uri_value or resolved_path.as_uri()

    digest = item.get("digest")
    if digest is None and resolved_path is not None:
        digest = sha256_hex_file(resolved_path)
    ensure(digest is not None, "Evidence item requires a digest or a resolvable local path.")

    content_type = item.get("content_type")
    if content_type is None and resolved_path is not None:
        content_type = infer_content_type(resolved_path)

    created_at = item.get("created_at")
    if created_at is None and resolved_path is not None:
        created_at = isoformat_utc(datetime.fromtimestamp(resolved_path.stat().st_mtime, timezone.utc))

    ensure(uri_value, "Evidence item requires a uri or a local path.")

    finalized = {
        "type": item["type"],
        "uri": str(uri_value),
        "digest_alg": digest_alg,
        "digest": str(digest),
    }
    if content_type:
        finalized["content_type"] = str(content_type)
    if created_at:
        finalized["created_at"] = str(created_at)
    return finalized


def finalize_evidence_bundle(raw_bundle: Dict[str, Any]) -> Dict[str, Any]:
    items = raw_bundle.get("items", [])
    ensure(isinstance(items, list) and items, "Evidence bundle requires at least one item.")
    finalized_items = [finalize_evidence_item(item) for item in items]

    digest_alg = str(raw_bundle.get("digest_alg") or "sha256")
    ensure(digest_alg == "sha256", "Only sha256 evidence bundle digests are currently supported.")
    digest = raw_bundle.get("digest")
    if digest is None:
        digest = sha256_hex_text(canonical_json({"items": finalized_items, "digest_alg": digest_alg}))

    return {
        "bundle_id": str(raw_bundle.get("bundle_id") or f"bundle_{utc_now_iso().replace(':', '').replace('-', '')}"),
        "digest_alg": digest_alg,
        "digest": str(digest),
        "items": finalized_items,
    }


def derive_csc_level(
    composite_score: float,
    gates: Dict[str, bool],
    thresholds: Dict[int, float],
) -> int:
    level = 1
    for candidate_level, threshold in sorted(thresholds.items()):
        if composite_score >= threshold:
            level = candidate_level

    if level >= 6 and not gates["sector_validation_met"]:
        level = 5

    if level >= 4:
        state4_ready = (
            gates["no_critical_failures"]
            and gates["telemetry_minimum_met"]
            and gates["f6_1_min_met"]
            and gates["f6_4_min_met"]
            and gates["all_factors_min_met"]
        )
        if not state4_ready:
            level = 3

    if level >= 2 and (not gates["no_critical_failures"] or not gates["telemetry_minimum_met"]):
        level = 1

    return level


def build_signature_block(
    certificate_without_signature: Dict[str, Any],
    issuer: Dict[str, Any],
    signed_at: str,
) -> Dict[str, Any]:
    digest = sha256_hex_text(canonical_json(certificate_without_signature))
    return {
        "alg": "EdDSA",
        "kid": str(issuer["key_id"]),
        "canonicalization": "JCS",
        "signed_payload_digest": {
            "digest_alg": "sha256",
            "digest": digest,
        },
        "signature": "UNSIGNED_PENDING_ENTERPRISE_REVIEW",
        "signed_at": signed_at,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an Access-PoD CSC certificate from enterprise evidence inputs."
    )
    parser.add_argument(
        "--evidence-input",
        required=True,
        help="Path to the enterprise CSC evidence input JSON.",
    )
    parser.add_argument(
        "--profile-id",
        default=None,
        help="Optional override for the sector profile id.",
    )
    parser.add_argument(
        "--metric-catalog",
        default=str(DEFAULT_METRIC_CATALOG_PATH),
        help=f"Metric catalog JSON. Default: {DEFAULT_METRIC_CATALOG_PATH}",
    )
    parser.add_argument(
        "--sector-profiles",
        default=str(DEFAULT_SECTOR_PROFILES_PATH),
        help=f"Base sector profiles JSON. Default: {DEFAULT_SECTOR_PROFILES_PATH}",
    )
    parser.add_argument(
        "--profile-extensions",
        default=str(DEFAULT_PROFILE_EXTENSIONS_PATH),
        help=(
            "Optional local profile extension JSON merged over the base sector profiles. "
            f"Default: {DEFAULT_PROFILE_EXTENSIONS_PATH}"
        ),
    )
    parser.add_argument(
        "--certificate-schema",
        default=str(DEFAULT_CERTIFICATE_SCHEMA_PATH),
        help=f"CSC certificate schema. Default: {DEFAULT_CERTIFICATE_SCHEMA_PATH}",
    )
    parser.add_argument(
        "--evidence-input-schema",
        default=str(DEFAULT_EVIDENCE_INPUT_SCHEMA_PATH),
        help=f"Enterprise evidence input schema. Default: {DEFAULT_EVIDENCE_INPUT_SCHEMA_PATH}",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional explicit output path for the certificate JSON.",
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Optional explicit output path for the scoring report JSON.",
    )
    parser.add_argument(
        "--skip-schema-validation",
        action="store_true",
        help="Skip optional jsonschema validation if the dependency is available.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        evidence_input_path = resolve_path(args.evidence_input)
        metric_catalog_path = resolve_path(args.metric_catalog)
        sector_profiles_path = resolve_path(args.sector_profiles)
        profile_extensions_path = resolve_path(args.profile_extensions) if args.profile_extensions else None
        certificate_schema_path = resolve_path(args.certificate_schema)
        evidence_input_schema_path = resolve_path(args.evidence_input_schema)

        evidence_input = read_json(evidence_input_path)
        if not args.skip_schema_validation and evidence_input_schema_path.exists():
            maybe_validate_json(evidence_input, evidence_input_schema_path, "enterprise evidence input")

        metrics, metrics_by_id, metrics_by_factor = load_metric_catalog(metric_catalog_path)
        profiles_by_id = load_profiles(sector_profiles_path, profile_extensions_path)

        profile_id = args.profile_id or evidence_input.get("profile_id")
        ensure(profile_id, "Evidence input must define profile_id or --profile-id must be provided.")
        ensure(profile_id in profiles_by_id, f"Unknown profile_id: {profile_id}")
        profile = profiles_by_id[str(profile_id)]

        default_window = evidence_input.get("telemetry_window", {}) or {}
        observations = evidence_input.get("metric_observations", [])
        ensure(isinstance(observations, list) and observations, "Evidence input requires metric_observations.")

        observations_by_factor: Dict[str, List[Dict[str, Any]]] = {}
        warning_metrics: List[str] = []
        critical_metrics: List[str] = []

        for observation in observations:
            metric_id = str(observation.get("metric_id") or "").strip()
            ensure(metric_id in metrics_by_id, f"Unknown metric_id in evidence input: {metric_id}")
            metric = metrics_by_id[metric_id]
            factor = str(metric["factor"])
            value = float(observation["value"])
            normalized = normalize_value(metric, value)
            warning_hit, critical_hit = detect_threshold_state(metric, value)
            window = resolve_observation_window(observation, default_window)

            enriched = {
                **observation,
                "metric": metric,
                "metric_id": metric_id,
                "factor": factor,
                "value": value,
                "normalized": normalized,
                "warning_hit": warning_hit,
                "critical_hit": critical_hit,
                "window": window,
                "confidence": normalize_observation_confidence(observation),
                "raw_weight": normalize_observation_weight(observation),
            }
            observations_by_factor.setdefault(factor, []).append(enriched)

            if warning_hit:
                warning_metrics.append(metric_id)
            if critical_hit:
                critical_metrics.append(metric_id)

        factor_scores: Dict[str, Any] = {}
        factor_coverages: Dict[str, Any] = {}
        factor_score_values: Dict[str, float] = {}
        total_observed_metrics = 0

        top_metrics_per_factor = int(
            evidence_input.get("scoring_policy", {}).get(
                "top_metrics_per_factor",
                DEFAULT_TOP_METRICS_PER_FACTOR,
            )
        )

        for factor, factor_metrics in sorted(metrics_by_factor.items()):
            observed = observations_by_factor.get(factor, [])
            ensure(observed, f"At least one metric observation is required for factor {factor}.")

            total_observed_metrics += len(observed)
            total_weight = sum(item["raw_weight"] for item in observed)
            if total_weight <= 0:
                total_weight = float(len(observed))

            contributions: List[Dict[str, Any]] = []
            weighted_score = 0.0
            weighted_confidence = 0.0
            window_starts = [parse_datetime(item["window"]["start"]) for item in observed]
            window_ends = [parse_datetime(item["window"]["end"]) for item in observed]

            for item in observed:
                weight = item["raw_weight"] / total_weight if total_weight > 0 else 1.0 / len(observed)
                weighted_score += item["normalized"] * weight
                weighted_confidence += item["confidence"] * weight
                contributions.append(
                    {
                        "metric_id": item["metric_id"],
                        "value": item["value"],
                        "unit": item["metric"].get("unit"),
                        "weight": round(weight, 4),
                        "normalized": round(item["normalized"], 4),
                        "direction": item["metric"].get("direction"),
                    }
                )

            coverage_ratio = len(observed) / max(len(factor_metrics), 1)
            factor_key = metric_key_from_factor(factor)
            factor_score = round_score(weighted_score * 100.0)
            factor_confidence = round_confidence(weighted_confidence * (0.6 + 0.4 * coverage_ratio))

            contributions.sort(key=lambda item: item["normalized"] * item["weight"], reverse=True)

            factor_scores[factor_key] = {
                "score": factor_score,
                "confidence": factor_confidence,
                "telemetry_window": {
                    "start": isoformat_utc(min(window_starts)),
                    "end": isoformat_utc(max(window_ends)),
                },
                "top_metrics": contributions[:top_metrics_per_factor],
            }
            factor_coverages[factor_key] = {
                "observed_metrics": len(observed),
                "total_factor_metrics": len(factor_metrics),
                "coverage_ratio": round(coverage_ratio, 4),
            }
            factor_score_values[factor_key] = factor_score

        overall_coverage_ratio = total_observed_metrics / max(len(metrics), 1)
        scoring_policy = evidence_input.get("scoring_policy", {}) or {}
        min_overall_coverage_ratio = float(
            scoring_policy.get("min_overall_metric_coverage_ratio", DEFAULT_MIN_OVERALL_COVERAGE_RATIO)
        )
        min_metrics_per_factor = int(
            scoring_policy.get("min_metrics_per_factor", DEFAULT_MIN_METRICS_PER_FACTOR)
        )
        min_factor_score = float(
            scoring_policy.get("min_factor_score", DEFAULT_MIN_FACTOR_SCORE)
        )

        profile_weights = profile.get("weights", {})
        weighted_sum = 0.0
        for factor_key, factor_score in factor_score_values.items():
            weighted_sum += factor_score * float(profile_weights[factor_key])
        composite_score = round_score(weighted_sum)

        gates = {
            "no_critical_failures": len(critical_metrics) == 0,
            "telemetry_minimum_met": (
                overall_coverage_ratio >= min_overall_coverage_ratio
                and all(item["observed_metrics"] >= min_metrics_per_factor for item in factor_coverages.values())
            ),
            "f6_1_min_met": factor_score_values["f6_1"] >= float(profile.get("gates", {}).get("f6_1_min_for_4star", 0)),
            "f6_4_min_met": factor_score_values["f6_4"] >= float(profile.get("gates", {}).get("f6_4_min_for_4star", 0)),
            "all_factors_min_met": all(score >= min_factor_score for score in factor_score_values.values()),
            "sector_validation_met": factor_score_values["f6_6"] >= float(profile.get("gates", {}).get("f6_6_min_for_6star", 0)),
        }

        level_thresholds_raw = scoring_policy.get("level_thresholds", DEFAULT_LEVEL_THRESHOLDS)
        level_thresholds = {int(key): float(value) for key, value in level_thresholds_raw.items()}
        csc_level = derive_csc_level(composite_score, gates, level_thresholds)

        issued_at = evidence_input.get("issued_at") or utc_now_iso()
        if evidence_input.get("expires_at"):
            expires_at = str(evidence_input["expires_at"])
        else:
            issued_at_dt = parse_datetime(str(issued_at))
            expires_at = isoformat_utc(issued_at_dt + timedelta(days=int(evidence_input.get("expires_in_days", DEFAULT_EXPIRES_IN_DAYS))))

        issuer = evidence_input["issuer"]
        subject = evidence_input["subject"]
        scope = evidence_input["scope"]
        csc_id = str(evidence_input.get("csc_id") or build_default_csc_id(subject["subject_id"], str(issued_at)))
        risk_tier = str(
            evidence_input.get("risk_tier")
            or scope.get("risk_tier_declared")
            or "medium"
        )

        evidence_bundle = finalize_evidence_bundle(evidence_input["evidence"])
        iso_alignment = evidence_input.get("iso_alignment", {})

        certificate_without_signature = {
            "schema_version": "1.0.0",
            "csc_id": csc_id,
            "issued_at": str(issued_at),
            "expires_at": expires_at,
            "status": str(evidence_input.get("status", "active")),
            "issuer": issuer,
            "subject": subject,
            "scope": scope,
            "assessment": {
                "sapp": evidence_input["sapp"],
                "factor_scores": factor_scores,
                "weights": {
                    "profile_id": str(profile_id),
                    **profile_weights,
                },
                "composite_score": composite_score,
                "csc_level": csc_level,
                "risk_tier": risk_tier,
                "gates": gates,
                "iso_alignment": iso_alignment,
            },
            "evidence": evidence_bundle,
        }
        if evidence_input.get("revocation") is not None:
            certificate_without_signature["revocation"] = evidence_input["revocation"]
        if evidence_input.get("links") is not None:
            certificate_without_signature["links"] = evidence_input["links"]

        certificate = {
            **certificate_without_signature,
            "signature": build_signature_block(certificate_without_signature, issuer, str(issued_at)),
        }

        if not args.skip_schema_validation and certificate_schema_path.exists():
            maybe_validate_json(certificate, certificate_schema_path, "certificate")

        output_token = sanitize_token(f"{subject['subject_id']}--{profile_id}")
        issued_token = str(issued_at).replace(":", "").replace("-", "")
        certificate_out_path = (
            resolve_path(args.out)
            if args.out
            else DEFAULT_CERTIFICATE_OUT_ROOT / f"{output_token}__{issued_token}.csc_certificate.json"
        )
        report_out_path = (
            resolve_path(args.report_out)
            if args.report_out
            else DEFAULT_REPORT_OUT_ROOT / f"{output_token}__{issued_token}.csc_report.json"
        )

        report = {
            "report_version": "access_pod_csc_scoring_report_v1.0",
            "generated_at_utc": utc_now_iso(),
            "inputs": {
                "evidence_input_path": relativize_if_possible(evidence_input_path),
                "metric_catalog_path": relativize_if_possible(metric_catalog_path),
                "sector_profiles_path": relativize_if_possible(sector_profiles_path),
                "profile_extensions_path": (
                    relativize_if_possible(profile_extensions_path)
                    if profile_extensions_path is not None and profile_extensions_path.exists()
                    else None
                ),
                "certificate_schema_path": relativize_if_possible(certificate_schema_path),
            },
            "profile_id": str(profile_id),
            "csc_id": csc_id,
            "observed_metric_count": total_observed_metrics,
            "catalog_metric_count": len(metrics),
            "overall_metric_coverage_ratio": round(overall_coverage_ratio, 4),
            "factor_coverages": factor_coverages,
            "warning_metrics": sorted(set(warning_metrics)),
            "critical_metrics": sorted(set(critical_metrics)),
            "gates": gates,
            "assessment_summary": {
                "composite_score": composite_score,
                "csc_level": csc_level,
                "risk_tier": risk_tier,
            },
            "factor_scores": factor_scores,
        }

        write_json(certificate_out_path, certificate)
        write_json(report_out_path, report)
        certificate_summary_path = sidecar_markdown_path(certificate_out_path)
        report_summary_path = sidecar_markdown_path(report_out_path)
        write_markdown(
            certificate_summary_path,
            render_certificate_markdown(certificate, report, certificate_out_path, report_out_path),
        )
        write_markdown(
            report_summary_path,
            render_report_markdown(report, report_out_path),
        )

        result = {
            "status": "completed",
            "csc_id": csc_id,
            "profile_id": str(profile_id),
            "composite_score": composite_score,
            "csc_level": csc_level,
            "certificate_path": str(certificate_out_path),
            "certificate_summary_path": str(certificate_summary_path),
            "report_path": str(report_out_path),
            "report_summary_path": str(report_summary_path),
            "observed_metric_count": total_observed_metrics,
            "catalog_metric_count": len(metrics),
            "overall_metric_coverage_ratio": round(overall_coverage_ratio, 4),
        }
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    except (CSCBuilderError, KeyError, TypeError, ValueError, OSError) as exc:
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
