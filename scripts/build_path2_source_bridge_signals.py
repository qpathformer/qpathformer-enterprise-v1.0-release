#!/usr/bin/env python3
"""
Q-Pathformer DEV — Path 2 Source Bridge Signals

Builds governed Path 2 signal artifacts from a frozen ID_3 source bundle.

Purpose:
- preserve the ID_3 freeze pack as the authoritative Path 2 source entry
- emit export-ready v0.2-dev signal records into 02_signals/source_bridge
- keep non-authoritative posture and explicit STATE_3 entry discipline

Posture:
- reads frozen source artifacts only
- does not mutate the source freeze bundle
- emits governed signal records for later STATE_2 review routing
- does not grant approval, compliance, or governance authority
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from uuid import uuid4


ROOT_SCRIPTS_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT_SCRIPTS_DIR / "runtime"
if str(ROOT_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_SCRIPTS_DIR))
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from path_layout import PATH2_SOURCE_BRIDGE_SIGNALS_ROOT, PATH2_SOURCE_ROOT  # noqa: E402
from run_signal_routing import route_signal  # noqa: E402
from run_signal_validation import evaluate_validation_readiness  # noqa: E402


DEFAULT_MODEL_VERSION = "v10.1-path2-source-bridge"
DEFAULT_PARAMETER_CLASS = "12B-14B"
DEFAULT_ROLE = "enterprise"


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    allowed = [ch if ch.isalnum() else "-" for ch in lowered]
    compact = "".join(allowed)
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact.strip("-") or "unknown"


def discover_latest_freeze_root() -> Path:
    candidates = []
    for entry in PATH2_SOURCE_ROOT.iterdir():
        if not entry.is_dir():
            continue
        if (entry / "ID3_FREEZE_NOTE.md").exists() and (entry / "hashes.txt").exists():
            candidates.append(entry)
    if not candidates:
        raise RuntimeError(
            f"No Path 2 freeze bundles found under source root: {PATH2_SOURCE_ROOT}"
        )
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


@dataclass(frozen=True)
class ScenarioArtifacts:
    label: str
    session_path: Path
    module_path: Path
    session_payload: Dict[str, Any]
    module_payload: Dict[str, Any]


def iter_scenarios(freeze_root: Path) -> List[ScenarioArtifacts]:
    artifacts: List[ScenarioArtifacts] = []
    for session_path in sorted(freeze_root.glob("session_*.canonical.json")):
        label = session_path.name.removeprefix("session_").removesuffix(".canonical.json")
        module_path = freeze_root / f"module_03_{label}.canonical.json"
        if not module_path.exists():
            raise RuntimeError(
                f"Missing paired module canonical record for scenario '{label}': {module_path}"
            )
        artifacts.append(
            ScenarioArtifacts(
                label=label,
                session_path=session_path,
                module_path=module_path,
                session_payload=read_json(session_path),
                module_payload=read_json(module_path),
            )
        )
    if not artifacts:
        raise RuntimeError(f"No session canonical files found in freeze root: {freeze_root}")
    return artifacts


def ensure_shared_session_id(artifacts: Iterable[ScenarioArtifacts]) -> str:
    session_ids = {
        str(item.session_payload.get("session", {}).get("session_id") or "").strip()
        for item in artifacts
    }
    session_ids.discard("")
    if not session_ids:
        raise RuntimeError("No shared session_id found in canonical session records.")
    if len(session_ids) != 1:
        raise RuntimeError(f"Expected one normalized session_id, found: {sorted(session_ids)}")
    return next(iter(session_ids))


def sanitize_tag(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    return normalized.replace("/", "_").replace("\\", "_")


def build_prompt(item: ScenarioArtifacts) -> str:
    session_block = item.session_payload.get("session", {}) or {}
    project_context = session_block.get("project_context", {}) or {}
    purpose = str(project_context.get("purpose_statement") or "").strip()
    module_block = item.module_payload.get("module", {}) or {}
    module_title = str(module_block.get("module_title") or "Module 03").strip()
    return (
        f"Path 2 source bridge for scenario '{item.label}'. "
        f"Use frozen canonical session and {module_title} records as governed runtime inputs. "
        f"Purpose: {purpose}"
    ).strip()


def build_structured_summary(item: ScenarioArtifacts) -> str:
    scenario_run = ((item.module_payload.get("simulation_runs") or [{}])[0]) or {}
    scenario_summary = str(scenario_run.get("scenario_summary") or "").strip()
    if not scenario_summary:
        scenario_summary = (
            f"Scenario {item.label} preserves shared session grouping and explicit review routing."
        )
    return (
        f"Path 2 {item.label} bridge signal packages a frozen ID_2 session and Module 03 record "
        f"into a governed STATE_3 signal for later STATE_2 review. {scenario_summary}"
    ).strip()


def build_raw_output(item: ScenarioArtifacts, freeze_root: Path) -> str:
    session_block = item.session_payload.get("session", {}) or {}
    project_context = session_block.get("project_context", {}) or {}
    scenario_run = ((item.module_payload.get("simulation_runs") or [{}])[0]) or {}
    payload = {
        "bridge_type": "path2_source_bridge",
        "scenario_label": item.label,
        "source_freeze_root": str(freeze_root),
        "session_file": item.session_path.name,
        "module_file": item.module_path.name,
        "session_id": session_block.get("session_id"),
        "purpose_statement": project_context.get("purpose_statement"),
        "audience": project_context.get("audience"),
        "scenario_summary": scenario_run.get("scenario_summary"),
        "source_record_class": {
            "session": item.session_payload.get("record_class"),
            "module": item.module_payload.get("record_class"),
        },
        "source_final_status": {
            "session_inspection_status": item.session_payload.get("inspection_status"),
            "module_status": item.module_payload.get("status"),
            "module_completed_at_utc": item.module_payload.get("completed_at_utc"),
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def build_tags(item: ScenarioArtifacts) -> List[str]:
    session_block = item.session_payload.get("session", {}) or {}
    project_context = session_block.get("project_context", {}) or {}
    audience = project_context.get("audience", []) or []

    tags = [
        "path2_source_bridge",
        "id3_freeze",
        "state3",
        "governance",
        "module_03",
        sanitize_tag(item.label),
        "shared_session_id",
        "non_authoritative",
        "signals_not_decisions",
        "tr008",
    ]
    for value in audience:
        normalized = sanitize_tag(str(value))
        if normalized:
            tags.append(normalized)

    deduped: List[str] = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            deduped.append(tag)
            seen.add(tag)
    return deduped


def build_signal_record(
    *,
    item: ScenarioArtifacts,
    freeze_root: Path,
    session_id: str,
    model_version: str,
    parameter_class: str,
    role: str,
) -> Dict[str, Any]:
    return {
        "signal_id": str(uuid4()),
        "timestamp": utc_now_iso(),
        "access_mode_primary": "ID_2",
        "schema_version": "v0.2-dev",
        "interaction_type": "enterprise_only",
        "session_id": session_id,
        "model": {
            "model_id": "path2-source-bridge",
            "parameter_class": parameter_class,
            "role": role,
            "endpoint_type": "local",
            "invocation_reason": "source_bridge_structuring",
            "version": model_version,
        },
        "source": {
            "initiator": "id3-freeze-source",
            "amplifier": None,
        },
        "source_bridge": {
            "bridge_type": "path2_source_bridge",
            "source_root": str(freeze_root),
            "source_freeze_name": freeze_root.name,
            "scenario_label": item.label,
            "session_file": item.session_path.name,
            "module_file": item.module_path.name,
            "source_access_mode": "ID_3_packaging_of_ID_2_records",
            "preserves_source_freeze": True,
            "top_level_final_interpreted_from_id3_freeze": True,
        },
        "input": {
            "prompt": build_prompt(item),
            "context_ref": item.session_path.name,
        },
        "signal": {
            "raw_output": build_raw_output(item, freeze_root),
            "structured_summary": build_structured_summary(item),
            "tags": build_tags(item),
        },
        "metrics": {
            "coherence": 0.0,
            "novelty": 0.0,
            "stability": 0.0,
            "ambiguity": 0.0,
        },
        "maturity": "LEVEL_0",
        "governance_flags": {
            "provisional": True,
            "context_bound": True,
            "requires_validation": True,
            "promotion_blocked": True,
            "signals_not_decisions": True,
            "source_freeze_preserved": True,
        },
        "authorization": {
            "state2_candidate_allowed": True,
            "fine_tuning_allowed": False,
            "human_review_required": True,
        },
        "validation": {
            "candidate_for_validation": False,
            "validation_requested": False,
        },
        "lifecycle": {
            "state": "STATE_3",
            "eligible_for_state_2": False,
            "routing_decision": "HOLD_IN_STATE_3",
        },
    }


def finalize_signal_record(signal_record: Dict[str, Any]) -> Dict[str, Any]:
    validation_result = evaluate_validation_readiness(signal_record)
    signal_record["metrics"] = validation_result["metrics"]
    signal_record["maturity"] = validation_result["maturity"]
    signal_record["validation"] = validation_result["validation"]
    return route_signal(signal_record)


def write_signal(output_root: Path, freeze_name: str, label: str, signal_record: Dict[str, Any]) -> tuple[Path, Path]:
    target_dir = output_root / freeze_name
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"signal_path2_source_{timestamp_token()}_{slugify(label)}_"
        f"{signal_record['signal_id'].split('-')[0]}"
    )
    signal_path = target_dir / f"{stem}.json"
    routing_path = target_dir / f"{stem}.routing.json"

    signal_path.write_text(
        json.dumps(signal_record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    routing_payload = {
        "signal_id": signal_record["signal_id"],
        "timestamp": signal_record["timestamp"],
        "source_state": "STATE_3",
        "target_state": signal_record["lifecycle"].get("target_state", "STATE_3"),
        "decision": signal_record["lifecycle"].get("routing_decision", "HOLD_IN_STATE_3"),
        "eligible_for_state_2": bool(signal_record["lifecycle"].get("eligible_for_state_2")),
        "reasons": list(signal_record["lifecycle"].get("routing_reasons", [])),
        "metrics": signal_record["metrics"],
        "maturity": signal_record["maturity"],
        "model": signal_record["model"],
        "scenario_label": label,
        "source_freeze_name": freeze_name,
    }
    routing_path.write_text(
        json.dumps(routing_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return signal_path, routing_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build Path 2 governed source-bridge signals from a frozen ID_3 canonical pack."
        )
    )
    parser.add_argument(
        "--freeze-root",
        help="Explicit Path 2 source freeze root. Defaults to the latest bundle in 01_source.",
    )
    parser.add_argument(
        "--output-root",
        default=str(PATH2_SOURCE_BRIDGE_SIGNALS_ROOT),
        help=(
            "Output folder for bridged Path 2 signals. "
            f"Default: {PATH2_SOURCE_BRIDGE_SIGNALS_ROOT}"
        ),
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_MODEL_VERSION,
        help=f"Model version label written into emitted signals. Default: {DEFAULT_MODEL_VERSION}",
    )
    parser.add_argument(
        "--parameter-class",
        default=DEFAULT_PARAMETER_CLASS,
        help=(
            "Target parameter class to encode for governed enterprise routing. "
            f"Default: {DEFAULT_PARAMETER_CLASS}"
        ),
    )
    parser.add_argument(
        "--role",
        default=DEFAULT_ROLE,
        help=f"Model role to encode in emitted signals. Default: {DEFAULT_ROLE}",
    )
    parser.add_argument(
        "--allow-hold",
        action="store_true",
        help="Allow bridged signals to remain held in STATE_3 instead of failing the run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate bridge records without writing them to disk.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    freeze_root = Path(args.freeze_root) if args.freeze_root else discover_latest_freeze_root()
    if not freeze_root.exists():
        raise SystemExit(
            json.dumps(
                {"status": "error", "error": f"freeze_root_not_found:{freeze_root}"},
                indent=2,
            )
        )

    output_root = Path(args.output_root)
    artifacts = iter_scenarios(freeze_root)
    session_id = ensure_shared_session_id(artifacts)

    written_records: List[Dict[str, Any]] = []
    written_paths: List[Dict[str, str]] = []

    for item in artifacts:
        signal_record = build_signal_record(
            item=item,
            freeze_root=freeze_root,
            session_id=session_id,
            model_version=args.model_version,
            parameter_class=args.parameter_class,
            role=args.role,
        )
        finalized = finalize_signal_record(signal_record)

        if (
            not args.allow_hold
            and finalized.get("lifecycle", {}).get("routing_decision") != "SEND_TO_STATE_2_REVIEW"
        ):
            raise SystemExit(
                json.dumps(
                    {
                        "status": "error",
                        "error": "bridge_signal_not_state2_ready",
                        "scenario": item.label,
                        "routing_decision": finalized.get("lifecycle", {}).get("routing_decision"),
                        "routing_reasons": finalized.get("lifecycle", {}).get("routing_reasons", []),
                    },
                    indent=2,
                )
            )

        written_records.append(finalized)
        if not args.dry_run:
            signal_path, routing_path = write_signal(output_root, freeze_root.name, item.label, finalized)
            written_paths.append(
                {
                    "scenario": item.label,
                    "signal_path": str(signal_path),
                    "routing_log_path": str(routing_path),
                }
            )

    result = {
        "status": "ok",
        "freeze_root": str(freeze_root),
        "output_root": str(output_root / freeze_root.name),
        "record_count": len(written_records),
        "session_id": session_id,
        "model_version": args.model_version,
        "parameter_class": args.parameter_class,
        "role": args.role,
        "routing_decisions": {
            item["source_bridge"]["scenario_label"]: item["lifecycle"]["routing_decision"]
            for item in written_records
        },
        "written": not args.dry_run,
        "files": written_paths,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
