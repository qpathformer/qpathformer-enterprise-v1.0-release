#!/usr/bin/env python3
"""
Shared run registry updater for the live three-path enterprise root.

Supports two sources:
- lifecycle engine summaries
- runtime signal run-reference records

The registry is intentionally lightweight and query-friendly. Detailed per-run
artifacts stay in their own JSON files, while `shared/registry/run_registry.json`
acts as the live index.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from path_layout import SHARED_RUN_REGISTRY_PATH


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = SHARED_RUN_REGISTRY_PATH
REGISTRY_VERSION = "qpds_run_registry_v1.1"
REGISTRY_RECORD_VERSION = "qpds_run_registry_record_v1.0"
REGISTRY_WORKFLOW_ID = "qpds_three_path_live_registry"
REGISTRY_SCOPE = "shared_runtime_and_lifecycle_runs"
REGISTRY_NOTE = (
    "Active run registry for live three-path runtime signal and lifecycle executions."
)


class RegistryUpdateError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryUpdateError(message)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def resolve_path(raw: str, base: Path = REPO_ROOT) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base / candidate).resolve()


def relativize_if_possible(
    path_value: Optional[str | Path],
    repo_root: Path = REPO_ROOT,
) -> Optional[str]:
    if path_value in (None, ""):
        return None

    raw = Path(path_value)
    try:
        resolved = raw.resolve() if raw.is_absolute() else (repo_root / raw).resolve()
        return str(resolved.relative_to(repo_root)).replace("\\", "/")
    except Exception:
        return str(raw).replace("\\", "/")


def compact_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }


def normalize_notes(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return " | ".join(normalized) if normalized else None
    text = str(value).strip()
    return text or None


def collect_step_digest(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    digest: List[Dict[str, Any]] = []
    for step in summary.get("steps", []):
        if not isinstance(step, dict):
            continue
        digest.append(
            {
                "step_name": step.get("step_name"),
                "status": step.get("status"),
                "return_code": step.get("return_code"),
                "started_at_utc": step.get("started_at_utc"),
                "completed_at_utc": step.get("completed_at_utc"),
            }
        )
    return digest


def latest_completed_step(summary: Dict[str, Any]) -> Optional[str]:
    last_completed = None
    for step in summary.get("steps", []):
        if isinstance(step, dict) and step.get("status") == "completed":
            last_completed = step.get("step_name")
    return last_completed


def load_or_init_registry(registry_path: Path) -> Dict[str, Any]:
    if registry_path.exists():
        registry = read_json(registry_path)
        ensure(isinstance(registry, dict), "Registry file is not a JSON object")
        runs = registry.get("runs", [])
        ensure(isinstance(runs, list), "Registry 'runs' field must be a list")
        return {
            "registry_version": REGISTRY_VERSION,
            "workflow_id": registry.get("workflow_id") or REGISTRY_WORKFLOW_ID,
            "registry_scope": registry.get("registry_scope") or REGISTRY_SCOPE,
            "registry_note": registry.get("registry_note") or REGISTRY_NOTE,
            "legacy_snapshot_path": registry.get("legacy_snapshot_path"),
            "runs": [item for item in runs if isinstance(item, dict)],
            "updated_at_utc": registry.get("updated_at_utc") or utc_now(),
        }

    return {
        "registry_version": REGISTRY_VERSION,
        "workflow_id": REGISTRY_WORKFLOW_ID,
        "registry_scope": REGISTRY_SCOPE,
        "registry_note": REGISTRY_NOTE,
        "runs": [],
        "updated_at_utc": utc_now(),
    }


def _existing_run_number(registry: Dict[str, Any], run_id: str) -> Optional[int]:
    for item in registry.get("runs", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("run_id") or "") != run_id:
            continue
        run_number = item.get("run_number")
        if isinstance(run_number, int) and run_number >= 1:
            return run_number
    return None


def _next_run_number(registry: Dict[str, Any]) -> int:
    highest = 0
    for item in registry.get("runs", []):
        if not isinstance(item, dict):
            continue
        run_number = item.get("run_number")
        if isinstance(run_number, int) and run_number > highest:
            highest = run_number
    return highest + 1


def _assigned_run_number(registry: Dict[str, Any], run_id: str) -> int:
    existing = _existing_run_number(registry, run_id)
    if existing is not None:
        return existing
    return _next_run_number(registry)


def build_registry_record_from_summary(
    summary: Dict[str, Any],
    *,
    summary_path: Path,
    registry: Dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> Dict[str, Any]:
    run_id = str(summary.get("run_id") or "").strip()
    ensure(run_id, "Summary missing run_id")

    final_outputs = summary.get("final_outputs", {}) or {}
    recorded_at = (
        summary.get("completed_at_utc")
        or summary.get("generated_at_utc")
        or utc_now()
    )

    record = {
        "registry_record_version": REGISTRY_RECORD_VERSION,
        "run_id": run_id,
        "run_number": _assigned_run_number(registry, run_id),
        "run_type": "lifecycle_engine",
        "workflow_id": str(summary.get("workflow_id") or "qpath_lifecycle_engine_v1.2"),
        "status": str(summary.get("status") or "failed"),
        "recorded_at_utc": recorded_at,
        "generated_at_utc": summary.get("generated_at_utc"),
        "completed_at_utc": summary.get("completed_at_utc"),
        "failure_step": summary.get("failure_step"),
        "failure_reason": summary.get("failure_reason"),
        "package_id": summary.get("package_id"),
        "engine_version": summary.get("engine_version"),
        "requested_mode": summary.get("requested_mode", summary.get("mode")),
        "resolved_mode": summary.get("resolved_mode", summary.get("mode")),
        "summary_path": relativize_if_possible(summary_path, repo_root),
        "run_reference_path": relativize_if_possible(summary_path, repo_root),
        "package_root": relativize_if_possible(final_outputs.get("package_root"), repo_root),
        "manifest_path": relativize_if_possible(final_outputs.get("manifest_path"), repo_root),
        "finalize_report_path": relativize_if_possible(
            final_outputs.get("finalize_report_path"),
            repo_root,
        ),
        "step_count": len(summary.get("steps", [])),
        "last_completed_step": latest_completed_step(summary),
        "step_digest": collect_step_digest(summary),
        "inspection_ready": True,
        "frozen_output_queryable": bool(final_outputs.get("manifest_path")),
        "notes": normalize_notes(summary.get("notes")),
        "updated_at_utc": utc_now(),
    }

    detection = summary.get("detection")
    if isinstance(detection, dict):
        record["detection"] = detection

    return compact_dict(record)


def build_registry_record_from_run_reference(
    run_reference: Dict[str, Any],
    *,
    run_reference_path: Path,
    registry: Dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> Dict[str, Any]:
    run_id = str(run_reference.get("run_id") or "").strip()
    ensure(run_id, "Run reference missing run_id")

    run_status = str(
        run_reference.get("run_status") or run_reference.get("status") or ""
    ).strip()
    ensure(run_status, "Run reference missing run_status")

    recorded_at = str(run_reference.get("recorded_at_utc") or "").strip()
    ensure(recorded_at, "Run reference missing recorded_at_utc")

    outputs = run_reference.get("outputs", {}) or {}
    routing = run_reference.get("routing", {}) or {}
    model = run_reference.get("model", {}) or {}

    record = {
        "registry_record_version": REGISTRY_RECORD_VERSION,
        "run_id": run_id,
        "run_number": _assigned_run_number(registry, run_id),
        "run_type": str(run_reference.get("run_type") or "runtime_signal_emitter"),
        "workflow_id": str(run_reference.get("workflow_id") or "path2_runtime_signal_emitter"),
        "path_id": run_reference.get("path_id"),
        "status": run_status,
        "lifecycle_state": run_reference.get("lifecycle_state"),
        "target_state": run_reference.get("target_state"),
        "dataset_passport_id": run_reference.get("dataset_passport_id"),
        "signal_id": run_reference.get("signal_id"),
        "session_id": run_reference.get("session_id"),
        "routing_decision": routing.get("decision") or run_reference.get("routing_decision"),
        "eligible_for_state_2": routing.get("eligible_for_state_2"),
        "routing_ids": run_reference.get("routing_ids"),
        "run_reference_path": relativize_if_possible(run_reference_path, repo_root),
        "signal_path": relativize_if_possible(outputs.get("signal_path"), repo_root),
        "routing_log_path": relativize_if_possible(outputs.get("routing_log_path"), repo_root),
        "recorded_at_utc": recorded_at,
        "inspection_ready": bool(run_reference.get("inspection_ready", True)),
        "frozen_output_queryable": bool(
            run_reference.get("frozen_output_queryable", False)
        ),
        "model_id": model.get("model_id"),
        "model_version": model.get("model_version") or model.get("version"),
        "notes": normalize_notes(run_reference.get("notes")),
        "updated_at_utc": utc_now(),
    }

    return compact_dict(record)


def upsert_record(registry: Dict[str, Any], record: Dict[str, Any]) -> str:
    runs = registry["runs"]
    run_id = str(record["run_id"])

    for index, existing in enumerate(runs):
        if str(existing.get("run_id") or "") == run_id:
            runs[index] = record
            registry["updated_at_utc"] = utc_now()
            return "updated"

    runs.append(record)
    runs.sort(
        key=lambda item: (
            int(item.get("run_number") or 0),
            str(item.get("recorded_at_utc") or ""),
            str(item.get("run_id") or ""),
        )
    )
    registry["updated_at_utc"] = utc_now()
    return "inserted"


def register_run_reference(
    run_reference: Dict[str, Any],
    *,
    run_reference_path: Path,
    registry_path: Path,
    repo_root: Path = REPO_ROOT,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    registry = load_or_init_registry(registry_path)
    record = build_registry_record_from_run_reference(
        run_reference,
        run_reference_path=run_reference_path,
        registry=registry,
        repo_root=repo_root,
    )
    action = upsert_record(registry, record)
    write_json(registry_path, registry)
    return action, record, registry


def register_summary(
    summary: Dict[str, Any],
    *,
    summary_path: Path,
    registry_path: Path,
    repo_root: Path = REPO_ROOT,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    registry = load_or_init_registry(registry_path)
    record = build_registry_record_from_summary(
        summary,
        summary_path=summary_path,
        registry=registry,
        repo_root=repo_root,
    )
    action = upsert_record(registry, record)
    write_json(registry_path, registry)
    return action, record, registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update the shared live run registry from a summary or run-reference file."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--summary",
        help="Path to lifecycle_engine_summary.json",
    )
    source_group.add_argument(
        "--run-reference",
        help="Path to a runtime signal run-reference JSON file.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY_PATH),
        help="Path to shared run_registry.json.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        registry_path = resolve_path(args.registry, REPO_ROOT)

        if args.summary:
            summary_path = resolve_path(args.summary, REPO_ROOT)
            ensure(summary_path.exists(), f"Summary not found: {summary_path}")
            summary = read_json(summary_path)
            action, record, registry = register_summary(
                summary,
                summary_path=summary_path,
                registry_path=registry_path,
            )
        else:
            run_reference_path = resolve_path(args.run_reference, REPO_ROOT)
            ensure(
                run_reference_path.exists(),
                f"Run reference not found: {run_reference_path}",
            )
            run_reference = read_json(run_reference_path)
            action, record, registry = register_run_reference(
                run_reference,
                run_reference_path=run_reference_path,
                registry_path=registry_path,
            )

        result = {
            "registry_version": registry["registry_version"],
            "action": action,
            "run_id": record["run_id"],
            "run_type": record.get("run_type"),
            "status": record.get("status"),
            "registry_path": str(registry_path),
            "updated_at_utc": registry["updated_at_utc"],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    except RegistryUpdateError as exc:
        payload = {
            "status": "failed",
            "error": str(exc),
            "updated_at_utc": utc_now(),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
