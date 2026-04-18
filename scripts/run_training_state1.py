#!/usr/bin/env python3
"""
run_training_state1.py

Deterministic STATE_1 training-preparation layer for governed datasets.

Contract:
- read state1_dataset_registry.json
- resolve exactly one dataset via --latest or --dataset-version
- resolve frozen_manifest.json from the registry entry
- resolve frozen_dataset.jsonl from frozen_manifest.json
- optionally read ingestion/ingestion_summary.json
- validate source records against the governed frozen dataset contract
- map records into portable SFT JSONL
- emit a versioned training package

This script does not:
- modify source dataset content
- change lifecycle state
- update registry files
- authorize training
- perform training
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from path_layout import PATH2_TRAINING_PACKAGES_ROOT, SHARED_REGISTRY_ROOT


DEFAULT_DATASET_FILENAME = "frozen_dataset.jsonl"
DEFAULT_OUTPUT_ROOT = PATH2_TRAINING_PACKAGES_ROOT
DEFAULT_TRAIN_FILENAME = "train.sft.jsonl"
DEFAULT_MANIFEST_FILENAME = "state1_training_manifest.json"
DEFAULT_BACKEND_PROFILE_FILENAME = "training_backend_profile.json"
DEFAULT_PREVIEW_FILENAME = "training_preview.json"
DEFAULT_INGESTION_SUMMARY_FILENAME = "ingestion_summary.json"


class TrainingPrepError(RuntimeError):
    """Raised when deterministic training preparation cannot proceed."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise TrainingPrepError(f"json_not_found:{path}") from exc
    except json.JSONDecodeError as exc:
        raise TrainingPrepError(f"json_invalid:{path}:{exc}") from exc

    if not isinstance(data, dict):
        raise TrainingPrepError(f"json_root_must_be_object:{path}")

    return data


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_number, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    raise TrainingPrepError(f"blank_line_not_allowed:{path}:{line_number}")
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TrainingPrepError(f"invalid_jsonl_record:{path}:{line_number}:{exc}") from exc
                if not isinstance(obj, dict):
                    raise TrainingPrepError(f"jsonl_record_must_be_object:{path}:{line_number}")
                records.append(obj)
    except FileNotFoundError as exc:
        raise TrainingPrepError(f"jsonl_not_found:{path}") from exc

    if not records:
        raise TrainingPrepError(f"jsonl_empty:{path}")

    return records


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def _require_dict(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise TrainingPrepError(f"{label}_must_be_object")
    return value


def _require_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise TrainingPrepError(f"{label}_must_be_array")
    return value


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingPrepError(f"{label}_must_be_non_empty_string")
    return value.strip()


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise TrainingPrepError(f"{label}_must_be_boolean")
    return value


def _validate_enum(value: Any, allowed: Iterable[str], label: str) -> str:
    v = _require_str(value, label)
    allowed_set = set(allowed)
    if v not in allowed_set:
        raise TrainingPrepError(f"{label}_invalid_enum:{v}:allowed={','.join(sorted(allowed_set))}")
    return v


def _normalize_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def _validate_registry(registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    _require_str(registry.get("registry_id"), "registry.registry_id")
    _require_str(registry.get("created_at"), "registry.created_at")
    _require_str(registry.get("updated_at"), "registry.updated_at")

    entries = _require_list(registry.get("entries"), "registry.entries")
    if not entries:
        raise TrainingPrepError("registry_entries_empty")

    validated: List[Dict[str, Any]] = []
    for i, entry in enumerate(entries):
        label = f"registry.entries[{i}]"
        e = _require_dict(entry, label)

        _require_str(e.get("registry_entry_id"), f"{label}.registry_entry_id")
        _require_str(e.get("registered_at"), f"{label}.registered_at")
        _require_str(e.get("state"), f"{label}.state")
        _require_str(e.get("dataset_version"), f"{label}.dataset_version")
        _require_str(e.get("package_dir"), f"{label}.package_dir")
        _require_str(e.get("freeze_dir"), f"{label}.freeze_dir")
        _require_str(e.get("frozen_manifest_path"), f"{label}.frozen_manifest_path")
        _require_str(e.get("freeze_artifact_path"), f"{label}.freeze_artifact_path")

        validated.append(e)

    return validated


def _resolve_registry_entry(
    entries: List[Dict[str, Any]],
    use_latest: bool,
    dataset_version: Optional[str],
    package_dir_contains: Optional[str],
) -> Dict[str, Any]:
    if use_latest and dataset_version:
        raise TrainingPrepError("choose_only_one_of_latest_or_dataset_version")
    if not use_latest and not dataset_version:
        raise TrainingPrepError("one_of_latest_or_dataset_version_required")

    filtered_entries = entries
    if package_dir_contains:
        needle = package_dir_contains.casefold()
        filtered_entries = [
            e
            for e in entries
            if needle in _require_str(e.get("package_dir"), "entry.package_dir").casefold()
        ]
        if not filtered_entries:
            raise TrainingPrepError(
                f"no_registry_entries_match_package_dir_contains:{package_dir_contains}"
            )

    if use_latest:
        ordered = sorted(filtered_entries, key=lambda x: x["registered_at"], reverse=True)
        return ordered[0]

    matches = [e for e in filtered_entries if e["dataset_version"] == dataset_version]
    if not matches:
        if package_dir_contains:
            raise TrainingPrepError(
                f"dataset_version_not_found_with_package_dir_filter:{dataset_version}:{package_dir_contains}"
            )
        raise TrainingPrepError(f"dataset_version_not_found:{dataset_version}")
    if len(matches) > 1:
        raise TrainingPrepError(f"dataset_version_not_unique:{dataset_version}")
    return matches[0]

def _resolve_frozen_manifest_and_dataset(
    entry: Dict[str, Any],
    dataset_filename: str,
) -> Tuple[Path, Dict[str, Any], Path]:
    if entry["state"] != "STATE_1":
        raise TrainingPrepError(f"registry_entry_not_state1:{entry['dataset_version']}")

    frozen_manifest_path = _normalize_path(
        _require_str(entry.get("frozen_manifest_path"), "entry.frozen_manifest_path")
    )

    if not frozen_manifest_path.exists():
        raise TrainingPrepError(f"frozen_manifest_not_found:{frozen_manifest_path}")

    frozen_manifest = _load_json(frozen_manifest_path)

    manifest_dataset_version = _require_str(
        frozen_manifest.get("dataset_version"),
        "frozen_manifest.dataset_version",
    )
    if manifest_dataset_version != entry["dataset_version"]:
        raise TrainingPrepError(
            f"dataset_version_mismatch_between_registry_and_manifest:"
            f"{entry['dataset_version']}!={manifest_dataset_version}"
        )

    manifest_state = _require_str(
        frozen_manifest.get("state"),
        "frozen_manifest.state",
    )
    if manifest_state != entry["state"]:
        raise TrainingPrepError(
            f"state_mismatch_between_registry_and_manifest:{entry['state']}!={manifest_state}"
        )

    if manifest_state != "STATE_1":
        raise TrainingPrepError(f"frozen_manifest_not_state1:{manifest_dataset_version}")

    frozen_dataset_path_raw = frozen_manifest.get("frozen_dataset_path")
    if isinstance(frozen_dataset_path_raw, str) and frozen_dataset_path_raw.strip():
        frozen_dataset_path = _normalize_path(frozen_dataset_path_raw)
        if frozen_dataset_path.exists():
            return frozen_manifest_path, frozen_manifest, frozen_dataset_path

    freeze_dir = _normalize_path(_require_str(entry.get("freeze_dir"), "entry.freeze_dir"))
    fallback_path = (freeze_dir / dataset_filename).resolve()
    if fallback_path.exists():
        return frozen_manifest_path, frozen_manifest, fallback_path

    raise TrainingPrepError(f"frozen_dataset_not_found_for_entry:{entry['dataset_version']}")


def _resolve_ingestion_summary(dataset_path: Path) -> Optional[Path]:
    dataset_dir = dataset_path.parent
    candidate_paths = [
        dataset_dir / "ingestion" / DEFAULT_INGESTION_SUMMARY_FILENAME,
        dataset_dir.parent / "ingestion" / DEFAULT_INGESTION_SUMMARY_FILENAME,
    ]
    for path in candidate_paths:
        if path.exists():
            return path.resolve()
    return None


def _validate_source_record(record: Dict[str, Any], index: int) -> Dict[str, Any]:
    label = f"record[{index}]"

    candidate_id = _require_str(record.get("candidate_id"), f"{label}.candidate_id")
    source_signal_id = _require_str(record.get("source_signal_id"), f"{label}.source_signal_id")
    source_state = _validate_enum(
        record.get("source_state"),
        {"STATE_3", "STATE_2", "STATE_1"},
        f"{label}.source_state",
    )

    target_model = _require_dict(record.get("target_model"), f"{label}.target_model")
    parameter_class = _require_str(
        target_model.get("parameter_class"),
        f"{label}.target_model.parameter_class",
    )
    role = _validate_enum(
        target_model.get("role"),
        {"enterprise", "strategic"},
        f"{label}.target_model.role",
    )

    transformation_type = _require_str(
        record.get("transformation_type"),
        f"{label}.transformation_type",
    )

    content = _require_dict(record.get("content"), f"{label}.content")
    input_text = _require_str(content.get("input"), f"{label}.content.input")
    output_text = _require_str(content.get("output"), f"{label}.content.output")

    authorization = _require_dict(record.get("authorization"), f"{label}.authorization")
    fine_tuning_allowed = _require_bool(
        authorization.get("fine_tuning_allowed"),
        f"{label}.authorization.fine_tuning_allowed",
    )
    authorization_status = _require_str(
        authorization.get("status"),
        f"{label}.authorization.status",
    )

    review = _require_dict(record.get("review"), f"{label}.review")
    review_required = _require_bool(
        review.get("review_required"),
        f"{label}.review.review_required",
    )
    review_status = _require_str(
        review.get("status"),
        f"{label}.review.status",
    )

    routing = _require_dict(record.get("routing"), f"{label}.routing")
    eligible_for_state_2 = _require_bool(
        routing.get("eligible_for_state_2"),
        f"{label}.routing.eligible_for_state_2",
    )
    routing_decision = _require_str(
        routing.get("routing_decision"),
        f"{label}.routing.routing_decision",
    )
    target_state = _require_str(
        routing.get("target_state"),
        f"{label}.routing.target_state",
    )
    routing_reasons = _require_list(
        routing.get("routing_reasons"),
        f"{label}.routing.routing_reasons",
    )
    for i, reason in enumerate(routing_reasons):
        _require_str(reason, f"{label}.routing.routing_reasons[{i}]")

    validation = _require_dict(record.get("validation"), f"{label}.validation")
    candidate_for_validation = _require_bool(
        validation.get("candidate_for_validation"),
        f"{label}.validation.candidate_for_validation",
    )
    validation_requested = _require_bool(
        validation.get("validation_requested"),
        f"{label}.validation.validation_requested",
    )
    validation_engine_version = _require_str(
        validation.get("validation_engine_version"),
        f"{label}.validation.validation_engine_version",
    )
    validation_reasons = _require_list(
        validation.get("validation_reasons"),
        f"{label}.validation.validation_reasons",
    )
    for i, reason in enumerate(validation_reasons):
        _require_str(reason, f"{label}.validation.validation_reasons[{i}]")

    lineage = _require_dict(record.get("lineage"), f"{label}.lineage")
    source_signal_ref = _require_str(
        lineage.get("source_signal_ref"),
        f"{label}.lineage.source_signal_ref",
    )
    transformation_id = _require_str(
        lineage.get("transformation_id"),
        f"{label}.lineage.transformation_id",
    )

    timestamp = _require_str(record.get("timestamp"), f"{label}.timestamp")

    if source_signal_id != source_signal_ref:
        raise TrainingPrepError(f"{label}.source_signal_id_must_match_lineage.source_signal_ref")

    return {
        "candidate_id": candidate_id,
        "source_signal_id": source_signal_id,
        "source_state": source_state,
        "target_model_role": role,
        "target_model_parameter_class": parameter_class,
        "transformation_type": transformation_type,
        "input_text": input_text,
        "output_text": output_text,
        "fine_tuning_allowed": fine_tuning_allowed,
        "authorization_status": authorization_status,
        "review_required": review_required,
        "review_status": review_status,
        "eligible_for_state_2": eligible_for_state_2,
        "routing_decision": routing_decision,
        "target_state": target_state,
        "candidate_for_validation": candidate_for_validation,
        "validation_requested": validation_requested,
        "validation_engine_version": validation_engine_version,
        "routing_reason_count": len(routing_reasons),
        "validation_reason_count": len(validation_reasons),
        "transformation_id": transformation_id,
        "timestamp": timestamp,
    }


def _validate_backend_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    backend_profile_version = _require_str(
        profile.get("backend_profile_version"),
        "backend_profile.backend_profile_version",
    )
    backend_profile_id = _require_str(
        profile.get("backend_profile_id") or profile.get("backend_id"),
        "backend_profile.backend_profile_id",
    )
    backend_id = _require_str(
        profile.get("backend_id") or backend_profile_id,
        "backend_profile.backend_id",
    )
    backend_name = _require_str(
        profile.get("backend") or profile.get("backend_name") or backend_id,
        "backend_profile.backend",
    )
    format_name = _validate_enum(profile.get("format"), {"sft_jsonl"}, "backend_profile.format")
    prompt_field = _require_str(profile.get("prompt_field"), "backend_profile.prompt_field")
    completion_field = _require_str(profile.get("completion_field"), "backend_profile.completion_field")
    include_metadata = _require_bool(
        profile.get("include_metadata"),
        "backend_profile.include_metadata",
    )
    validated_profile = dict(profile)
    validated_profile["backend_profile_version"] = backend_profile_version
    validated_profile["backend_profile_id"] = backend_profile_id
    validated_profile["backend_id"] = backend_id
    validated_profile["backend"] = backend_name
    validated_profile["format"] = format_name
    validated_profile["prompt_field"] = prompt_field
    validated_profile["completion_field"] = completion_field
    validated_profile["include_metadata"] = include_metadata
    if validated_profile.get("max_seq_len") is None and isinstance(
        validated_profile.get("backend_config"),
        dict,
    ):
        validated_profile["max_seq_len"] = validated_profile["backend_config"].get("max_seq_len")
    return validated_profile


def _default_backend_profile() -> Dict[str, Any]:
    return {
        "backend_profile_version": "v12.0",
        "backend_profile_id": "local_sft_reference",
        "backend_id": "local_sft_reference",
        "backend": "local_sft",
        "supported_backends": ["local_sft"],
        "format": "sft_jsonl",
        "prompt_field": "prompt",
        "completion_field": "completion",
        "include_metadata": True,
        "max_seq_len": 2048,
        "packing": False,
        "notes": "Default local SFT JSONL export profile for governed STATE_1 training preparation.",
    }


def _build_training_row(
    source_record: Dict[str, Any],
    backend_profile: Dict[str, Any],
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        backend_profile["prompt_field"]: source_record["input_text"],
        backend_profile["completion_field"]: source_record["output_text"],
    }

    if backend_profile["include_metadata"]:
        row["metadata"] = {
            "candidate_id": source_record["candidate_id"],
            "source_signal_id": source_record["source_signal_id"],
            "source_state": source_record["source_state"],
            "target_model_role": source_record["target_model_role"],
            "target_model_parameter_class": source_record["target_model_parameter_class"],
            "transformation_type": source_record["transformation_type"],
            "authorization_status": source_record["authorization_status"],
            "fine_tuning_allowed": source_record["fine_tuning_allowed"],
            "review_status": source_record["review_status"],
            "routing_decision": source_record["routing_decision"],
            "target_state": source_record["target_state"],
            "validation_engine_version": source_record["validation_engine_version"],
            "transformation_id": source_record["transformation_id"],
            "timestamp": source_record["timestamp"],
        }

    return row


def _select_records_for_export(
    validated_records: List[Dict[str, Any]],
    require_fine_tuning_allowed: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    exported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for record in validated_records:
        reasons: List[str] = []

        if record["review_required"] and record["review_status"] != "reviewed":
            reasons.append(f"review_status_not_reviewed:{record['review_status']}")

        if record["routing_decision"] != "SEND_TO_STATE_2_REVIEW":
            reasons.append(f"routing_decision_not_exportable:{record['routing_decision']}")

        if not record["candidate_for_validation"]:
            reasons.append("candidate_for_validation_false")

        if not record["validation_requested"]:
            reasons.append("validation_requested_false")

        if require_fine_tuning_allowed and not record["fine_tuning_allowed"]:
            reasons.append("fine_tuning_not_allowed")

        if reasons:
            skipped.append(
                {
                    "candidate_id": record["candidate_id"],
                    "source_signal_id": record["source_signal_id"],
                    "skip_reasons": reasons,
                }
            )
            continue

        exported.append(record)

    return exported, skipped


def _copy_backend_profile(source_path: Optional[Path], destination_path: Path, profile: Dict[str, Any]) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path and source_path.exists():
        shutil.copyfile(source_path, destination_path)
        return
    _write_json(destination_path, profile)


def _build_manifest(
    entry: Dict[str, Any],
    frozen_manifest_path: Path,
    frozen_manifest: Dict[str, Any],
    dataset_path: Path,
    ingestion_summary_path: Optional[Path],
    output_dir: Path,
    backend_profile: Dict[str, Any],
    exported_records: List[Dict[str, Any]],
    skipped_records: List[Dict[str, Any]],
    preview_count: int,
) -> Dict[str, Any]:
    roles = Counter(r["target_model_role"] for r in exported_records)
    parameter_classes = Counter(r["target_model_parameter_class"] for r in exported_records)
    fine_tuning_allowed_count = sum(1 for r in exported_records if r["fine_tuning_allowed"])

    return {
        "training_manifest_version": "v12.0",
        "generated_at": _utc_now_iso(),
        "dataset_version": entry["dataset_version"],
        "registry_entry_id": entry["registry_entry_id"],
        "registry_state": entry["state"],
        "registered_at": entry["registered_at"],
        "source": {
            "registry_path_role": "state1_dataset_registry",
            "frozen_manifest_path": str(frozen_manifest_path),
            "frozen_dataset_path": str(dataset_path),
            "ingestion_summary_path": str(ingestion_summary_path) if ingestion_summary_path else None,
        },
        "frozen_manifest_summary": {
            "dataset_version": frozen_manifest.get("dataset_version"),
            "state": frozen_manifest.get("state"),
        },
        "output": {
            "output_dir": str(output_dir),
            "train_file": str(output_dir / DEFAULT_TRAIN_FILENAME),
            "backend_profile_file": str(output_dir / DEFAULT_BACKEND_PROFILE_FILENAME),
            "preview_file": str(output_dir / DEFAULT_PREVIEW_FILENAME),
        },
        "backend_profile": backend_profile,
        "record_counts": {
            "exported_record_count": len(exported_records),
            "skipped_record_count": len(skipped_records),
            "fine_tuning_allowed_count": fine_tuning_allowed_count,
            "fine_tuning_disallowed_count": len(exported_records) - fine_tuning_allowed_count,
        },
        "export_profile": {
            "format": backend_profile["format"],
            "preview_count": preview_count,
            "target_model_roles": dict(sorted(roles.items())),
            "target_model_parameter_classes": dict(sorted(parameter_classes.items())),
        },
        "authorization_posture": {
            "training_preparation_only": True,
            "training_not_executed": True,
            "authorization_not_modified": True,
            "require_fine_tuning_allowed_for_export": False,
        },
        "skipped_records": skipped_records,
    }


def _build_preview(
    training_rows: List[Dict[str, Any]],
    preview_count: int,
) -> Dict[str, Any]:
    return {
        "preview_generated_at": _utc_now_iso(),
        "preview_count": min(preview_count, len(training_rows)),
        "records": training_rows[:preview_count],
    }


def _print_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministically prepare a governed STATE_1 dataset for training export."
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=SHARED_REGISTRY_ROOT / "state1_dataset_registry.json",
        help="Path to the state1 dataset registry JSON.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve the latest registered dataset version after optional package-dir filtering.",
    )
    parser.add_argument(
        "--dataset-version",
        type=str,
        help="Resolve an explicit dataset version after optional package-dir filtering.",
    )
    parser.add_argument(
        "--package-dir-contains",
        type=str,
        help="Optional substring filter applied to registry entry package_dir before resolving --latest or --dataset-version.",
    )
    parser.add_argument(
        "--dataset-filename",
        type=str,
        default=DEFAULT_DATASET_FILENAME,
        help="Fallback frozen dataset filename expected under entry.freeze_dir.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where the v12 training package will be written.",
    )
    parser.add_argument(
        "--backend-profile",
        type=Path,
        help="Optional JSON backend profile for SFT export.",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=3,
        help="Number of training rows to write into training_preview.json.",
    )
    parser.add_argument(
        "--require-fine-tuning-allowed",
        action="store_true",
        help="Export only records with authorization.fine_tuning_allowed == true.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize without writing output files.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        if args.preview_count < 0:
            raise TrainingPrepError("preview_count_must_be_non_negative")

        registry = _load_json(args.registry_path)
        entries = _validate_registry(registry)
        entry = _resolve_registry_entry(entries, args.latest, args.dataset_version, args.package_dir_contains)

        frozen_manifest_path, frozen_manifest, dataset_path = _resolve_frozen_manifest_and_dataset(
            entry,
            args.dataset_filename,
        )
        ingestion_summary_path = _resolve_ingestion_summary(dataset_path)

        if ingestion_summary_path:
            ingestion_summary = _load_json(ingestion_summary_path)
            summary_dataset_version = _require_str(
                ingestion_summary.get("dataset_version"),
                "ingestion_summary.dataset_version",
            )
            if summary_dataset_version != entry["dataset_version"]:
                raise TrainingPrepError(
                    f"dataset_version_mismatch_between_registry_and_ingestion_summary:"
                    f"{entry['dataset_version']}!={summary_dataset_version}"
                )

        source_records = _load_jsonl(dataset_path)
        validated_source_records = [
            _validate_source_record(record, idx) for idx, record in enumerate(source_records)
        ]

        backend_profile_source_path: Optional[Path] = None
        if args.backend_profile:
            backend_profile_source_path = args.backend_profile.resolve()
            backend_profile = _validate_backend_profile(_load_json(backend_profile_source_path))
        else:
            backend_profile = _validate_backend_profile(_default_backend_profile())

        exported_source_records, skipped_records = _select_records_for_export(
            validated_source_records,
            require_fine_tuning_allowed=args.require_fine_tuning_allowed,
        )

        if not exported_source_records:
            raise TrainingPrepError("no_records_selected_for_training_export")

        training_rows = [
            _build_training_row(record, backend_profile) for record in exported_source_records
        ]

        output_dir = args.output_root.resolve() / entry["dataset_version"]
        manifest = _build_manifest(
            entry=entry,
            frozen_manifest_path=frozen_manifest_path,
            frozen_manifest=frozen_manifest,
            dataset_path=dataset_path,
            ingestion_summary_path=ingestion_summary_path,
            output_dir=output_dir,
            backend_profile=backend_profile,
            exported_records=exported_source_records,
            skipped_records=skipped_records,
            preview_count=args.preview_count,
        )
        preview_payload = _build_preview(training_rows, args.preview_count)

        train_path = output_dir / DEFAULT_TRAIN_FILENAME
        manifest_path = output_dir / DEFAULT_MANIFEST_FILENAME
        backend_profile_path = output_dir / DEFAULT_BACKEND_PROFILE_FILENAME
        preview_path = output_dir / DEFAULT_PREVIEW_FILENAME

        if not args.dry_run:
            _write_jsonl(train_path, training_rows)
            _write_json(manifest_path, manifest)
            _copy_backend_profile(backend_profile_source_path, backend_profile_path, backend_profile)
            _write_json(preview_path, preview_payload)

        result = {
            "status": "ok",
            "generated_at": _utc_now_iso(),
            "dataset_version": entry["dataset_version"],
            "registry_entry_id": entry["registry_entry_id"],
            "registry_state": entry["state"],
            "dataset_path": str(dataset_path),
            "ingestion_summary_path": str(ingestion_summary_path) if ingestion_summary_path else None,
            "output_dir": str(output_dir),
            "train_path": str(train_path),
            "manifest_path": str(manifest_path),
            "backend_profile_path": str(backend_profile_path),
            "preview_path": str(preview_path),
            "source_record_count": len(validated_source_records),
            "exported_record_count": len(exported_source_records),
            "skipped_record_count": len(skipped_records),
            "require_fine_tuning_allowed": args.require_fine_tuning_allowed,
            "dry_run": args.dry_run,
        }
        _print_json(result)
        return 0

    except TrainingPrepError as exc:
        _print_json(
            {
                "status": "error",
                "error": str(exc),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

