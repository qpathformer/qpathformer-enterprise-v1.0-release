#!/usr/bin/env python3
"""
run_external_adapter_ingestion.py

Deterministic external artifact onboarding for v13.

Supported template families:
- id3_freeze_bundle
- client_governance_json

Contract:
- accept a bundle directory through --input-root for id3_freeze_bundle
- accept a single structured JSON file through --input-file for client_governance_json
- load adapter profile
- inventory source artifacts
- classify source bundle or source file
- validate required structure
- preserve provenance and containment posture
- initialize lifecycle to STATE_3
- emit normalized onboarding package

This script does not:
- promote lifecycle state
- update registry state
- authorize fine-tuning
- produce final training packages
- perform model training
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from path_layout import PATH3_NORMALIZED_ROOT, PATH3_ONBOARDING_LOGS_ROOT, PATH3_REJECTED_ROOT, SHARED_CONFIGS_ROOT


DEFAULT_OUTPUT_ROOT = PATH3_NORMALIZED_ROOT
DEFAULT_REJECTED_ROOT = PATH3_REJECTED_ROOT
DEFAULT_ONBOARDING_LOG_ROOT = PATH3_ONBOARDING_LOGS_ROOT
DEFAULT_ID3_PROFILE_PATH = SHARED_CONFIGS_ROOT / "adapter_profiles" / "id3_freeze_bundle.profile.json"
DEFAULT_CLIENT_PROFILE_PATH = SHARED_CONFIGS_ROOT / "adapter_profiles" / "client_governance_json.profile.json"

OUTPUT_ONBOARDING_MANIFEST = "onboarding_manifest.json"
OUTPUT_NORMALIZED_JSONL = "normalized_onboarding.jsonl"
OUTPUT_SOURCE_INVENTORY = "source_inventory.json"
OUTPUT_NORMALIZATION_REPORT = "normalization_report.json"
OUTPUT_HASH_VERIFICATION_REPORT = "hash_verification_report.json"
OUTPUT_REJECTION_REPORT = "rejection_report.json"


class AdapterIngestionError(RuntimeError):
    """Raised when deterministic onboarding cannot proceed."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise AdapterIngestionError(f"json_not_found:{path}") from exc
    except json.JSONDecodeError as exc:
        raise AdapterIngestionError(f"json_invalid:{path}:{exc}") from exc

    if not isinstance(data, dict):
        raise AdapterIngestionError(f"json_root_must_be_object:{path}")

    return data


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
        raise AdapterIngestionError(f"{label}_must_be_object")
    return value


def _require_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise AdapterIngestionError(f"{label}_must_be_array")
    return value


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterIngestionError(f"{label}_must_be_non_empty_string")
    return value.strip()


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise AdapterIngestionError(f"{label}_must_be_boolean")
    return value


def _require_int(value: Any, label: str) -> int:
    if not isinstance(value, int):
        raise AdapterIngestionError(f"{label}_must_be_integer")
    return value


def _normalize_path(path_value: Path | str) -> Path:
    return Path(path_value).expanduser().resolve()


def _file_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".md":
        return "markdown"
    if suffix == ".txt":
        return "text"
    return "unknown"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AdapterIngestionError(f"text_not_found:{path}") from exc


def _default_profile_path_for_template(template_family: str) -> Path:
    if template_family == "id3_freeze_bundle":
        return DEFAULT_ID3_PROFILE_PATH
    if template_family == "client_governance_json":
        return DEFAULT_CLIENT_PROFILE_PATH
    raise AdapterIngestionError(f"template_family_not_supported:{template_family}")


def _load_profile(profile_path: Path, expected_template_family: str) -> Dict[str, Any]:
    profile = _load_json(profile_path)

    _require_str(profile.get("profile_version"), "profile.profile_version")
    _require_str(profile.get("profile_id"), "profile.profile_id")
    template_family = _require_str(profile.get("template_family"), "profile.template_family")
    if template_family != expected_template_family:
        raise AdapterIngestionError(
            f"profile.template_family_mismatch:{template_family}!={expected_template_family}"
        )

    if expected_template_family == "id3_freeze_bundle":
        expected_files = _require_dict(profile.get("expected_files"), "profile.expected_files")
        _require_list(expected_files.get("required_module_records"), "profile.expected_files.required_module_records")
        _require_list(expected_files.get("required_session_records"), "profile.expected_files.required_session_records")
        _require_str(expected_files.get("required_freeze_note"), "profile.expected_files.required_freeze_note")
        _require_str(expected_files.get("required_hash_manifest"), "profile.expected_files.required_hash_manifest")
    elif expected_template_family == "client_governance_json":
        validation_rules = _require_dict(profile.get("validation_rules"), "profile.validation_rules")
        _require_bool(validation_rules.get("require_dataset_id"), "profile.validation_rules.require_dataset_id")
        _require_bool(validation_rules.get("require_records_array"), "profile.validation_rules.require_records_array")
        _require_int(validation_rules.get("minimum_record_count"), "profile.validation_rules.minimum_record_count")
        _require_list(validation_rules.get("required_record_fields"), "profile.validation_rules.required_record_fields")

    return profile


def _inventory_source_directory(input_root: Path) -> Dict[str, Any]:
    if not input_root.exists():
        raise AdapterIngestionError(f"input_root_not_found:{input_root}")
    if not input_root.is_dir():
        raise AdapterIngestionError(f"input_root_must_be_directory:{input_root}")

    files = sorted([p for p in input_root.iterdir() if p.is_file()], key=lambda p: p.name.lower())
    if not files:
        raise AdapterIngestionError(f"input_root_contains_no_files:{input_root}")

    inventory_rows: List[Dict[str, Any]] = []
    for sequence, path in enumerate(files, start=1):
        stat = path.stat()
        inventory_rows.append(
            {
                "inventory_order": sequence,
                "file_name": path.name,
                "file_type": _file_type_for_path(path),
                "path": str(path.resolve()),
                "size_bytes": stat.st_size,
                "sha256": _sha256_file(path),
            }
        )

    return {
        "inventory_version": "v13.2",
        "root_path": str(input_root.resolve()),
        "file_count": len(inventory_rows),
        "files": inventory_rows,
    }


def _inventory_single_file(input_file: Path) -> Dict[str, Any]:
    if not input_file.exists():
        raise AdapterIngestionError(f"input_file_not_found:{input_file}")
    if not input_file.is_file():
        raise AdapterIngestionError(f"input_file_must_be_file:{input_file}")

    stat = input_file.stat()
    row = {
        "inventory_order": 1,
        "file_name": input_file.name,
        "file_type": _file_type_for_path(input_file),
        "path": str(input_file.resolve()),
        "size_bytes": stat.st_size,
        "sha256": _sha256_file(input_file),
    }
    return {
        "inventory_version": "v13.2",
        "root_path": str(input_file.parent.resolve()),
        "file_count": 1,
        "files": [row],
    }


def _resolve_required_bundle_paths(input_root: Path, profile: Dict[str, Any]) -> Dict[str, Path]:
    expected_files = _require_dict(profile.get("expected_files"), "profile.expected_files")

    required_module_records = _require_list(
        expected_files.get("required_module_records"),
        "profile.expected_files.required_module_records",
    )
    required_session_records = _require_list(
        expected_files.get("required_session_records"),
        "profile.expected_files.required_session_records",
    )
    required_freeze_note = _require_str(
        expected_files.get("required_freeze_note"),
        "profile.expected_files.required_freeze_note",
    )
    required_hash_manifest = _require_str(
        expected_files.get("required_hash_manifest"),
        "profile.expected_files.required_hash_manifest",
    )

    file_names = list(required_module_records) + list(required_session_records) + [
        required_freeze_note,
        required_hash_manifest,
    ]

    resolved: Dict[str, Path] = {}
    for file_name in file_names:
        path = (input_root / file_name).resolve()
        if not path.exists():
            raise AdapterIngestionError(f"required_file_missing:{file_name}")
        if not path.is_file():
            raise AdapterIngestionError(f"required_path_not_file:{file_name}")
        resolved[file_name] = path

    return resolved


def _validate_module_record(record: Dict[str, Any], file_name: str, required_record_class: str) -> None:
    schema_version = _require_str(record.get("schema_version"), f"{file_name}.schema_version")
    if not schema_version.startswith("id2_records_"):
        raise AdapterIngestionError(f"{file_name}.schema_version_unexpected:{schema_version}")

    record_class = _require_str(record.get("record_class"), f"{file_name}.record_class")
    if record_class != required_record_class:
        raise AdapterIngestionError(f"{file_name}.record_class_mismatch:{record_class}!={required_record_class}")

    access_mode_primary = _require_str(record.get("access_mode_primary"), f"{file_name}.access_mode_primary")
    if access_mode_primary != "ID_2":
        raise AdapterIngestionError(f"{file_name}.access_mode_primary_mismatch:{access_mode_primary}")

    inspection_status = _require_str(record.get("inspection_status"), f"{file_name}.inspection_status")
    if inspection_status != "frozen_under_ID_3":
        raise AdapterIngestionError(f"{file_name}.inspection_status_mismatch:{inspection_status}")

    _require_bool(record.get("human_decision_required"), f"{file_name}.human_decision_required")
    _require_dict(record.get("module"), f"{file_name}.module")
    _require_dict(record.get("inputs"), f"{file_name}.inputs")
    _require_dict(record.get("captures"), f"{file_name}.captures")
    _require_list(record.get("simulation_runs"), f"{file_name}.simulation_runs")


def _validate_session_record(record: Dict[str, Any], file_name: str, required_record_class: str) -> None:
    schema_version = _require_str(record.get("schema_version"), f"{file_name}.schema_version")
    if not schema_version.startswith("id2_records_"):
        raise AdapterIngestionError(f"{file_name}.schema_version_unexpected:{schema_version}")

    record_class = _require_str(record.get("record_class"), f"{file_name}.record_class")
    if record_class != required_record_class:
        raise AdapterIngestionError(f"{file_name}.record_class_mismatch:{record_class}!={required_record_class}")

    access_mode_primary = _require_str(record.get("access_mode_primary"), f"{file_name}.access_mode_primary")
    if access_mode_primary != "ID_2":
        raise AdapterIngestionError(f"{file_name}.access_mode_primary_mismatch:{access_mode_primary}")

    inspection_status = _require_str(record.get("inspection_status"), f"{file_name}.inspection_status")
    if inspection_status != "frozen_under_ID_3":
        raise AdapterIngestionError(f"{file_name}.inspection_status_mismatch:{inspection_status}")

    _require_bool(record.get("human_decision_required"), f"{file_name}.human_decision_required")
    _require_dict(record.get("session"), f"{file_name}.session")
    _require_dict(record.get("run_plan"), f"{file_name}.run_plan")
    _require_dict(record.get("signoff"), f"{file_name}.signoff")


def _parse_hash_manifest(hash_manifest_path: Path) -> Dict[str, str]:
    content = _read_text(hash_manifest_path)
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise AdapterIngestionError(f"hash_manifest_empty:{hash_manifest_path}")

    entries: Dict[str, str] = {}
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            raise AdapterIngestionError(f"hash_manifest_invalid_line:{hash_manifest_path}:{line}")
        sha256 = parts[0].strip()
        file_name = parts[-1].strip()
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise AdapterIngestionError(f"hash_manifest_invalid_sha256:{file_name}:{sha256}")
        entries[file_name] = sha256.lower()

    return entries


def _parse_freeze_note(freeze_note_path: Path) -> Dict[str, Any]:
    text = _read_text(freeze_note_path)

    def extract(pattern: str, label: str) -> str:
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            raise AdapterIngestionError(f"freeze_note_missing_field:{label}")
        return match.group(1).strip()

    package_id = extract(r"^- package_id:\s*(.+)$", "package_id")
    lifecycle_state = extract(r"^- lifecycle_state:\s*(.+)$", "lifecycle_state")
    frozen_at_utc = extract(r"^- frozen_at_utc:\s*(.+)$", "frozen_at_utc")

    if lifecycle_state != "STATE_3":
        raise AdapterIngestionError(f"freeze_note.lifecycle_state_mismatch:{lifecycle_state}")

    legacy_non_claim_markers = [
        "It does **not** mean:",
        "compliant / approved / adequate",
        "audited or regulator-accepted",
        "operationally complete",
    ]
    structured_non_claim_markers = [
        "It does not mean:",
        "- compliant",
        "- approved",
        "- adequate",
        "## Non-Claims",
        "signals are not decisions",
        "freeze does not imply authorization",
        "onboarding does not imply training eligibility",
        "human review remains required",
    ]

    legacy_matches = [marker for marker in legacy_non_claim_markers if marker in text]
    structured_matches = [marker for marker in structured_non_claim_markers if marker in text]
    if len(legacy_matches) != len(legacy_non_claim_markers) and len(structured_matches) != len(
        structured_non_claim_markers
    ):
        missing_marker = next(
            (marker for marker in structured_non_claim_markers if marker not in text),
            legacy_non_claim_markers[0],
        )
        raise AdapterIngestionError(f"freeze_note_missing_non_claim_marker:{missing_marker}")

    return {
        "package_id": package_id,
        "lifecycle_state": lifecycle_state,
        "frozen_at_utc": frozen_at_utc,
        "raw_text": text,
    }


def _classify_bundle(
    package_id: str,
    inventory: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "classification_version": "v13.2",
        "package_id": package_id,
        "artifact_type": "id3_freeze_bundle",
        "record_family": "bundle",
        "source_mode_detected": "ID_2_frozen_under_ID_3",
        "structural_completeness": "complete",
        "template_family": _require_str(profile.get("template_family"), "profile.template_family"),
        "normalization_strategy": "bundle_to_onboarding_rows",
        "source_inventory": {
            "file_count": inventory["file_count"],
            "files": [
                {
                    "inventory_order": row["inventory_order"],
                    "file_name": row["file_name"],
                    "file_type": row["file_type"],
                    "path": row["path"],
                    "sha256": row["sha256"],
                }
                for row in inventory["files"]
            ],
        },
        "classification_notes": [
            "Bundle contains canonical ID_2 records frozen under ID_3.",
            "Freeze bundle remains non-authoritative and lifecycle-contained on intake.",
        ],
        "classification_timestamp": _utc_now_iso(),
    }


def _classify_client_dataset(
    package_id: str,
    inventory: Dict[str, Any],
    profile: Dict[str, Any],
    dataset_payload: Dict[str, Any],
) -> Dict[str, Any]:
    dataset_id = _require_str(dataset_payload.get("dataset_id"), "client_dataset.dataset_id")
    records = _require_list(dataset_payload.get("records"), "client_dataset.records")
    return {
        "classification_version": "v13.2",
        "package_id": package_id,
        "artifact_type": "client_governance_json",
        "record_family": "structured_json",
        "source_mode_detected": "client_external",
        "structural_completeness": "complete",
        "template_family": _require_str(profile.get("template_family"), "profile.template_family"),
        "normalization_strategy": "client_json_to_onboarding_rows",
        "source_inventory": {
            "file_count": inventory["file_count"],
            "files": [
                {
                    "inventory_order": row["inventory_order"],
                    "file_name": row["file_name"],
                    "file_type": row["file_type"],
                    "path": row["path"],
                    "sha256": row["sha256"],
                }
                for row in inventory["files"]
            ],
        },
        "classification_notes": [
            f"Client dataset detected with dataset_id={dataset_id}.",
            f"Structured JSON intake contains {len(records)} client records.",
            "Client-origin dataset remains non-authoritative and lifecycle-contained on intake.",
        ],
        "classification_timestamp": _utc_now_iso(),
    }


def _artifact_role_for_file(profile: Dict[str, Any], file_name: str) -> str:
    normalization_strategy = _require_dict(
        profile.get("normalization_strategy"),
        "profile.normalization_strategy",
    )
    artifact_roles = normalization_strategy.get("artifact_roles")
    if not isinstance(artifact_roles, dict):
        return "unknown"
    role = artifact_roles.get(file_name)
    if not isinstance(role, str) or not role.strip():
        return "unknown"
    return role.strip()


def _record_class_for_role(profile: Dict[str, Any], role: str) -> str:
    normalization_strategy = _require_dict(
        profile.get("normalization_strategy"),
        "profile.normalization_strategy",
    )
    record_class_mapping = _require_dict(
        normalization_strategy.get("record_class_mapping"),
        "profile.normalization_strategy.record_class_mapping",
    )
    record_class = record_class_mapping.get(role)
    if not isinstance(record_class, str) or not record_class.strip():
        raise AdapterIngestionError(f"record_class_mapping_missing_for_role:{role}")
    return record_class.strip()


def _bundle_role_for_artifact_type(artifact_type: str) -> str:
    if artifact_type in {"module_record", "session_record", "client_governance_record"}:
        return "canonical_record"
    if artifact_type == "freeze_note":
        return "evidence"
    if artifact_type == "hash_manifest":
        return "fixity_record"
    return "unknown"


def _default_authorization_context(profile: Dict[str, Any]) -> Dict[str, Any]:
    auth = _require_dict(
        profile.get("default_authorization_context"),
        "profile.default_authorization_context",
    )
    authorization_source = auth.get("authorization_source")
    if not isinstance(authorization_source, str) or not authorization_source.strip():
        authorization_source = "default_restricted_posture"

    return {
        "fine_tuning_allowed": _require_bool(auth.get("fine_tuning_allowed"), "profile.default_authorization_context.fine_tuning_allowed"),
        "external_training_allowed": _require_bool(auth.get("external_training_allowed"), "profile.default_authorization_context.external_training_allowed"),
        "human_review_required": _require_bool(auth.get("human_review_required"), "profile.default_authorization_context.human_review_required"),
        "authorization_inherited": _require_bool(auth.get("authorization_inherited"), "profile.default_authorization_context.authorization_inherited"),
        "authorization_source": authorization_source,
    }


def _default_governance_flags(profile: Dict[str, Any], human_decision_required: bool) -> Dict[str, Any]:
    flags = _require_dict(
        profile.get("default_governance_flags"),
        "profile.default_governance_flags",
    )
    return {
        "signals_not_decisions": _require_bool(flags.get("signals_not_decisions"), "profile.default_governance_flags.signals_not_decisions"),
        "non_certifying": _require_bool(flags.get("non_certifying"), "profile.default_governance_flags.non_certifying"),
        "context_bound": _require_bool(flags.get("context_bound"), "profile.default_governance_flags.context_bound"),
        "containment_required": _require_bool(flags.get("containment_required"), "profile.default_governance_flags.containment_required"),
        "human_decision_required": human_decision_required,
    }


def _default_lifecycle(profile: Dict[str, Any]) -> Dict[str, Any]:
    lifecycle = _require_dict(
        profile.get("default_lifecycle_initialization"),
        "profile.default_lifecycle_initialization",
    )
    return {
        "state": _require_str(lifecycle.get("state"), "profile.default_lifecycle_initialization.state"),
        "eligible_for_state_2": _require_bool(lifecycle.get("eligible_for_state_2"), "profile.default_lifecycle_initialization.eligible_for_state_2"),
        "routing_decision": _require_str(lifecycle.get("routing_decision"), "profile.default_lifecycle_initialization.routing_decision"),
    }


def _hash_status(hash_sha256: Optional[str]) -> str:
    return "match" if hash_sha256 else "not_applicable"


def _build_json_artifact_row(
    profile: Dict[str, Any],
    package_id: str,
    file_name: str,
    path: Path,
    role: str,
    payload: Dict[str, Any],
    freeze_timestamp: str,
    hash_sha256: Optional[str],
    freeze_note_present: bool,
) -> Dict[str, Any]:
    source_mode = "ID_2_frozen_under_ID_3"
    record_class = _record_class_for_role(profile, role)
    human_decision_required = _require_bool(payload.get("human_decision_required"), f"{file_name}.human_decision_required")

    if role in {"module_baseline", "module_variant"}:
        artifact_type = "module_record"
    elif role in {"session_baseline", "session_variant"}:
        artifact_type = "session_record"
    else:
        artifact_type = "module_record"

    return {
        "onboarding_record_version": "v13.2",
        "onboarding_record_id": f"{package_id}::{file_name}",
        "package_id": package_id,
        "artifact_type": artifact_type,
        "bundle_role": _bundle_role_for_artifact_type(artifact_type),
        "source_mode_detected": source_mode,
        "normalization_status": "normalized",
        "source_artifact": {
            "file_name": file_name,
            "file_role": role,
            "source_path": str(path),
        },
        "provenance": {
            "source_package_id": package_id,
            "source_paths": [str(path)],
            "hash_present": hash_sha256 is not None,
            "hash_sha256": hash_sha256,
            "source_hash_status": _hash_status(hash_sha256),
            "freeze_note_present": freeze_note_present,
            "freeze_timestamp": freeze_timestamp,
            "project_local_bundle": True,
        },
        "authorization_context": _default_authorization_context(profile),
        "governance_flags": _default_governance_flags(profile, human_decision_required),
        "lifecycle": _default_lifecycle(profile),
        "normalized_payload": {
            "record_class": record_class,
            "payload": payload,
        },
        "normalization_notes": [
            "Artifact normalized from project-local ID_3 freeze bundle.",
            "Source structure preserved without authorization expansion.",
        ],
        "created_at": _utc_now_iso(),
    }


def _build_freeze_note_row(
    profile: Dict[str, Any],
    package_id: str,
    file_name: str,
    path: Path,
    freeze_note: Dict[str, Any],
) -> Dict[str, Any]:
    role = "freeze_note"
    artifact_type = "freeze_note"
    return {
        "onboarding_record_version": "v13.2",
        "onboarding_record_id": f"{package_id}::{file_name}",
        "package_id": package_id,
        "artifact_type": artifact_type,
        "bundle_role": _bundle_role_for_artifact_type(artifact_type),
        "source_mode_detected": "ID_2_frozen_under_ID_3",
        "normalization_status": "normalized",
        "source_artifact": {
            "file_name": file_name,
            "file_role": role,
            "source_path": str(path),
        },
        "provenance": {
            "source_package_id": package_id,
            "source_paths": [str(path)],
            "hash_present": False,
            "hash_sha256": None,
            "source_hash_status": "not_applicable",
            "freeze_note_present": True,
            "freeze_timestamp": freeze_note["frozen_at_utc"],
            "project_local_bundle": True,
        },
        "authorization_context": _default_authorization_context(profile),
        "governance_flags": _default_governance_flags(profile, True),
        "lifecycle": _default_lifecycle(profile),
        "normalized_payload": {
            "record_class": "freeze_note_record",
            "payload": {
                "package_id": freeze_note["package_id"],
                "lifecycle_state": freeze_note["lifecycle_state"],
                "frozen_at_utc": freeze_note["frozen_at_utc"],
                "raw_text": freeze_note["raw_text"],
            },
        },
        "normalization_notes": [
            "Freeze note preserved as textual packaging and containment evidence.",
            "Freeze note does not imply approval, adequacy, or training eligibility.",
        ],
        "created_at": _utc_now_iso(),
    }


def _build_hash_manifest_row(
    profile: Dict[str, Any],
    package_id: str,
    file_name: str,
    path: Path,
    hash_entries: Dict[str, str],
    freeze_timestamp: str,
) -> Dict[str, Any]:
    role = "hash_manifest"
    artifact_type = "hash_manifest"
    return {
        "onboarding_record_version": "v13.2",
        "onboarding_record_id": f"{package_id}::{file_name}",
        "package_id": package_id,
        "artifact_type": artifact_type,
        "bundle_role": _bundle_role_for_artifact_type(artifact_type),
        "source_mode_detected": "ID_2_frozen_under_ID_3",
        "normalization_status": "normalized",
        "source_artifact": {
            "file_name": file_name,
            "file_role": role,
            "source_path": str(path),
        },
        "provenance": {
            "source_package_id": package_id,
            "source_paths": [str(path)],
            "hash_present": False,
            "hash_sha256": None,
            "source_hash_status": "not_applicable",
            "freeze_note_present": True,
            "freeze_timestamp": freeze_timestamp,
            "project_local_bundle": True,
        },
        "authorization_context": _default_authorization_context(profile),
        "governance_flags": _default_governance_flags(profile, True),
        "lifecycle": _default_lifecycle(profile),
        "normalized_payload": {
            "record_class": "hash_manifest_record",
            "payload": {
                "entries": hash_entries,
            },
        },
        "normalization_notes": [
            "Hash manifest preserved as fixity evidence for canonical bundle artifacts.",
        ],
        "created_at": _utc_now_iso(),
    }


def _build_client_record_row(
    profile: Dict[str, Any],
    package_id: str,
    input_file: Path,
    inventory_sha256: str,
    dataset_id: str,
    dataset_version: str,
    policy_context: Optional[str],
    source_organization: Optional[str],
    client_record: Dict[str, Any],
) -> Dict[str, Any]:
    record_id = _require_str(client_record.get("record_id"), "client_record.record_id")
    input_text = _require_str(client_record.get("input"), f"client_record[{record_id}].input")
    output_text = _require_str(client_record.get("output"), f"client_record[{record_id}].output")
    metadata = client_record.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise AdapterIngestionError(f"client_record[{record_id}].metadata_must_be_object")
    source = client_record.get("source")
    if source is not None and not isinstance(source, dict):
        raise AdapterIngestionError(f"client_record[{record_id}].source_must_be_object")

    artifact_type = "client_governance_record"
    role = "client_dataset"
    record_class = _record_class_for_role(profile, role)

    normalized_payload: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "record_id": record_id,
        "input": input_text,
        "output": output_text,
    }
    if metadata is not None:
        normalized_payload["metadata"] = metadata
    if source is not None:
        normalized_payload["source"] = source
    if policy_context:
        normalized_payload["policy_context"] = policy_context
    if source_organization:
        normalized_payload["source_organization"] = source_organization

    return {
        "onboarding_record_version": "v13.2",
        "onboarding_record_id": f"{package_id}::{record_id}",
        "package_id": package_id,
        "artifact_type": artifact_type,
        "bundle_role": _bundle_role_for_artifact_type(artifact_type),
        "source_mode_detected": "client_external",
        "normalization_status": "normalized",
        "source_artifact": {
            "file_name": input_file.name,
            "file_role": role,
            "source_path": str(input_file),
        },
        "provenance": {
            "source_package_id": dataset_id,
            "source_paths": [str(input_file)],
            "hash_present": True,
            "hash_sha256": inventory_sha256,
            "source_hash_status": "match",
            "freeze_note_present": False,
            "freeze_timestamp": None,
            "project_local_bundle": False,
        },
        "authorization_context": _default_authorization_context(profile),
        "governance_flags": _default_governance_flags(profile, True),
        "lifecycle": _default_lifecycle(profile),
        "normalized_payload": {
            "record_class": record_class,
            "payload": normalized_payload,
        },
        "normalization_notes": [
            "Client-origin record normalized from structured JSON intake.",
            "Restricted authorization posture preserved on onboarding.",
        ],
        "created_at": _utc_now_iso(),
    }


def _verify_hashes(
    required_paths: Dict[str, Path],
    hash_entries: Dict[str, str],
    canonical_file_names: List[str],
    strict_hash_check: bool,
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    missing_entries: List[str] = []
    mismatches: List[str] = []

    for file_name in canonical_file_names:
        expected_hash = hash_entries.get(file_name)
        if expected_hash is None:
            missing_entries.append(file_name)
            results.append(
                {
                    "file_name": file_name,
                    "status": "missing_hash_entry",
                    "expected_sha256": None,
                    "actual_sha256": None,
                }
            )
            continue

        actual_hash = _sha256_file(required_paths[file_name])
        status = "match" if actual_hash == expected_hash else "mismatch"
        if status == "mismatch":
            mismatches.append(file_name)

        results.append(
            {
                "file_name": file_name,
                "status": status,
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
            }
        )

    if strict_hash_check:
        if missing_entries:
            raise AdapterIngestionError(f"hash_entries_missing_for_canonical_files:{','.join(missing_entries)}")
        if mismatches:
            raise AdapterIngestionError(f"hash_mismatch_for_canonical_files:{','.join(mismatches)}")

    overall_status = "ok"
    if missing_entries or mismatches:
        overall_status = "warning" if not strict_hash_check else "error"

    return {
        "hash_verification_version": "v13.2",
        "overall_status": overall_status,
        "verification_mode": "manifest_hash_match",
        "canonical_file_count": len(canonical_file_names),
        "missing_hash_entries": missing_entries,
        "hash_mismatches": mismatches,
        "results": results,
        "verified_at": _utc_now_iso(),
    }


def _build_single_file_hash_report(input_file: Path, sha256: str) -> Dict[str, Any]:
    return {
        "hash_verification_version": "v13.2",
        "overall_status": "ok",
        "verification_mode": "single_file_integrity",
        "file_count": 1,
        "results": [
            {
                "file_name": input_file.name,
                "status": "match",
                "expected_sha256": sha256,
                "actual_sha256": sha256,
                "verification_basis": "computed_at_ingestion",
            }
        ],
        "verified_at": _utc_now_iso(),
    }


def _build_bundle_summary(normalized_rows: List[Dict[str, Any]], hash_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for row in normalized_rows:
        artifact_type = row["artifact_type"]
        counts[artifact_type] = counts.get(artifact_type, 0) + 1

    summary = {
        "module_record_count": counts.get("module_record", 0),
        "session_record_count": counts.get("session_record", 0),
        "freeze_note_count": counts.get("freeze_note", 0),
        "hash_manifest_count": counts.get("hash_manifest", 0),
        "client_governance_record_count": counts.get("client_governance_record", 0),
    }
    summary["hash_verification_status"] = hash_report["overall_status"] if hash_report is not None else "not_applicable"
    return summary


def _build_onboarding_manifest(
    package_id: str,
    input_locator: str,
    output_dir: Path,
    profile: Dict[str, Any],
    profile_path: Path,
    classification: Dict[str, Any],
    inventory: Dict[str, Any],
    normalized_rows: List[Dict[str, Any]],
    hash_report_path: Optional[Path],
    hash_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    output_block = {
        "output_dir": str(output_dir),
        "onboarding_manifest_file": str(output_dir / OUTPUT_ONBOARDING_MANIFEST),
        "normalized_onboarding_file": str(output_dir / OUTPUT_NORMALIZED_JSONL),
        "normalization_report_file": str(output_dir / OUTPUT_NORMALIZATION_REPORT),
    }
    if hash_report_path is not None:
        output_block["hash_verification_report_file"] = str(hash_report_path)

    return {
        "onboarding_manifest_version": "v13.2",
        "generated_at": _utc_now_iso(),
        "package_id": package_id,
        "template_family": _require_str(profile.get("template_family"), "profile.template_family"),
        "profile_id": _require_str(profile.get("profile_id"), "profile.profile_id"),
        "profile_version": _require_str(profile.get("profile_version"), "profile.profile_version"),
        "profile_path": str(profile_path),
        "input": {
            "input_root": input_locator,
            "source_inventory_file": str(output_dir / OUTPUT_SOURCE_INVENTORY),
        },
        "classification": classification,
        "authorization_posture": {
            "fine_tuning_allowed_default": False,
            "external_training_allowed_default": False,
            "human_review_required_default": True,
            "authorization_not_modified": True,
            "authorization_source": "default_restricted_posture",
        },
        "lifecycle_initialization": _default_lifecycle(profile),
        "bundle_summary": _build_bundle_summary(normalized_rows, hash_report),
        "output": output_block,
        "record_counts": {
            "source_file_count": inventory["file_count"],
            "normalized_record_count": len(normalized_rows),
        },
    }


def _build_normalization_report(
    package_id: str,
    inventory: Dict[str, Any],
    normalized_rows: List[Dict[str, Any]],
    hash_report: Optional[Dict[str, Any]],
    preview_count: int,
    extra_defaults_applied: Optional[List[str]] = None,
) -> Dict[str, Any]:
    artifact_type_counts: Dict[str, int] = {}
    for row in normalized_rows:
        artifact_type = row["artifact_type"]
        artifact_type_counts[artifact_type] = artifact_type_counts.get(artifact_type, 0) + 1

    defaults_applied = [
        "authorization defaulted to restricted posture",
        "lifecycle initialized to STATE_3",
        "no training eligibility inferred from structure",
    ]
    if extra_defaults_applied:
        defaults_applied.extend(extra_defaults_applied)

    return {
        "normalization_report_version": "v13.2",
        "generated_at": _utc_now_iso(),
        "package_id": package_id,
        "source_file_count": inventory["file_count"],
        "normalized_record_count": len(normalized_rows),
        "artifact_type_counts": artifact_type_counts,
        "hash_verification_overall_status": hash_report["overall_status"] if hash_report is not None else "not_applicable",
        "warnings": [],
        "defaults_applied": defaults_applied,
        "non_claims_preserved": [
            "adapter ingestion does not imply authorization",
            "adapter ingestion does not imply training eligibility",
            "structured intake does not imply validation or approval",
        ],
        "preview_count": min(preview_count, len(normalized_rows)),
        "preview_records": normalized_rows[:preview_count],
        "notes": [
            "All normalized records remain provisional and lifecycle-contained.",
            "Adapter ingestion does not imply validation, authorization, or training eligibility.",
        ],
    }


def _write_rejection_report(
    rejected_root: Path,
    package_id: str,
    input_locator: str,
    error_message: str,
) -> Path:
    output_dir = rejected_root / package_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_REJECTION_REPORT

    payload = {
        "rejection_report_version": "v13.2",
        "generated_at": _utc_now_iso(),
        "package_id": package_id,
        "input_locator": input_locator,
        "status": "rejected",
        "error": error_message,
    }
    _write_json(output_path, payload)
    return output_path


def _build_onboarding_log_path(package_id: str) -> Path:
    return DEFAULT_ONBOARDING_LOG_ROOT / package_id / f"onboarding_run_{_utc_now_slug()}.json"


def _build_onboarding_log(
    package_id: str,
    template_family: str,
    profile: Dict[str, Any],
    input_locator: str,
    output_dir: Path,
    classification: Dict[str, Any],
    inventory: Dict[str, Any],
    normalized_rows: List[Dict[str, Any]],
    hash_report: Optional[Dict[str, Any]],
    files_payload: Dict[str, Optional[str]],
    dry_run: bool,
) -> Dict[str, Any]:
    return {
        "onboarding_log_version": "v13.2",
        "generated_at": _utc_now_iso(),
        "status": "ok",
        "dry_run": dry_run,
        "package_id": package_id,
        "template_family": template_family,
        "profile_id": _require_str(profile.get("profile_id"), "profile.profile_id"),
        "profile_version": _require_str(profile.get("profile_version"), "profile.profile_version"),
        "input_locator": input_locator,
        "output_dir": str(output_dir),
        "source_file_count": inventory["file_count"],
        "normalized_record_count": len(normalized_rows),
        "hash_verification_status": hash_report["overall_status"] if hash_report is not None else "not_applicable",
        "classification": classification,
        "authorization_posture": {
            "fine_tuning_allowed_default": False,
            "external_training_allowed_default": False,
            "human_review_required_default": True,
            "authorization_not_modified": True,
            "authorization_source": "default_restricted_posture",
        },
        "lifecycle_initialization": _default_lifecycle(profile),
        "bundle_summary": _build_bundle_summary(normalized_rows, hash_report),
        "files": files_payload,
    }


def _validate_client_dataset(dataset_payload: Dict[str, Any], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    dataset_id = _require_str(dataset_payload.get("dataset_id"), "client_dataset.dataset_id")
    _require_str(dataset_payload.get("dataset_version"), "client_dataset.dataset_version")
    source_type = _require_str(dataset_payload.get("source_type"), "client_dataset.source_type")
    if source_type != "client_governance_json":
        raise AdapterIngestionError(f"client_dataset.source_type_mismatch:{source_type}")
    records = _require_list(dataset_payload.get("records"), "client_dataset.records")

    validation_rules = _require_dict(profile.get("validation_rules"), "profile.validation_rules")
    minimum_record_count = _require_int(
        validation_rules.get("minimum_record_count"),
        "profile.validation_rules.minimum_record_count",
    )
    if len(records) < minimum_record_count:
        raise AdapterIngestionError(
            f"client_dataset.record_count_below_minimum:{len(records)}<{minimum_record_count}:{dataset_id}"
        )

    required_record_fields = _require_list(
        validation_rules.get("required_record_fields"),
        "profile.validation_rules.required_record_fields",
    )
    required_record_fields_str = []
    for idx, field_name in enumerate(required_record_fields):
        required_record_fields_str.append(_require_str(field_name, f"profile.validation_rules.required_record_fields[{idx}]"))

    validated_records: List[Dict[str, Any]] = []
    seen_record_ids = set()

    for i, record in enumerate(records):
        label = f"client_dataset.records[{i}]"
        row = _require_dict(record, label)
        for field_name in required_record_fields_str:
            if field_name not in row:
                raise AdapterIngestionError(f"{label}.missing_required_field:{field_name}")

        record_id = _require_str(row.get("record_id"), f"{label}.record_id")
        if record_id in seen_record_ids:
            raise AdapterIngestionError(f"{label}.duplicate_record_id:{record_id}")
        seen_record_ids.add(record_id)

        _require_str(row.get("input"), f"{label}.input")
        _require_str(row.get("output"), f"{label}.output")

        metadata = row.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise AdapterIngestionError(f"{label}.metadata_must_be_object")

        source = row.get("source")
        if source is not None and not isinstance(source, dict):
            raise AdapterIngestionError(f"{label}.source_must_be_object")

        validated_records.append(row)

    return validated_records


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministically onboard external artifacts into a lifecycle-contained v13 package."
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        help="Root directory containing an inbound external bundle.",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="Path to a single structured external input file.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where normalized onboarding packages will be written.",
    )
    parser.add_argument(
        "--template-family",
        type=str,
        default="id3_freeze_bundle",
        help="Supported: id3_freeze_bundle, client_governance_json",
    )
    parser.add_argument(
        "--profile-path",
        type=Path,
        help="Optional explicit path to the adapter profile JSON.",
    )
    parser.add_argument(
        "--package-id",
        type=str,
        help="Optional explicit package id. Defaults to inbound folder name or dataset_id.",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=2,
        help="Number of normalized rows to include in normalization_report preview.",
    )
    parser.add_argument(
        "--strict-hash-check",
        action="store_true",
        help="Fail closed if canonical file hashes are missing or mismatched.",
    )
    parser.add_argument(
        "--write-rejected",
        action="store_true",
        help="Write rejection report on failure.",
    )
    parser.add_argument(
        "--rejected-root",
        type=Path,
        default=DEFAULT_REJECTED_ROOT,
        help="Directory where rejection reports will be written when --write-rejected is enabled.",
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

    if bool(args.input_root) == bool(args.input_file):
        error_payload = {
            "status": "error",
            "error": "choose_exactly_one_of_input_root_or_input_file",
        }
        print(json.dumps(error_payload, indent=2, ensure_ascii=False))
        return 1

    template_family = args.template_family.strip()
    profile_path = _normalize_path(args.profile_path) if args.profile_path else _normalize_path(
        _default_profile_path_for_template(template_family)
    )
    output_root = _normalize_path(args.output_root)
    rejected_root = _normalize_path(args.rejected_root)

    input_locator = ""
    package_id = args.package_id.strip() if args.package_id else ""

    try:
        if args.preview_count < 0:
            raise AdapterIngestionError("preview_count_must_be_non_negative")

        if template_family not in {"id3_freeze_bundle", "client_governance_json"}:
            raise AdapterIngestionError(f"template_family_not_supported:{template_family}")

        profile = _load_profile(profile_path, template_family)

        if template_family == "id3_freeze_bundle":
            if not args.input_root:
                raise AdapterIngestionError("input_root_required_for_id3_freeze_bundle")

            input_root = _normalize_path(args.input_root)
            input_locator = str(input_root)
            if not package_id:
                package_id = input_root.name

            inventory = _inventory_source_directory(input_root)
            required_paths = _resolve_required_bundle_paths(input_root, profile)

            expected_files = _require_dict(profile.get("expected_files"), "profile.expected_files")
            module_record_names = _require_list(
                expected_files.get("required_module_records"),
                "profile.expected_files.required_module_records",
            )
            session_record_names = _require_list(
                expected_files.get("required_session_records"),
                "profile.expected_files.required_session_records",
            )
            freeze_note_name = _require_str(
                expected_files.get("required_freeze_note"),
                "profile.expected_files.required_freeze_note",
            )
            hash_manifest_name = _require_str(
                expected_files.get("required_hash_manifest"),
                "profile.expected_files.required_hash_manifest",
            )

            validation_rules = _require_dict(profile.get("validation_rules"), "profile.validation_rules")
            required_module_record_class = _require_str(
                validation_rules.get("module_record_class_required"),
                "profile.validation_rules.module_record_class_required",
            )
            required_session_record_class = _require_str(
                validation_rules.get("session_record_class_required"),
                "profile.validation_rules.session_record_class_required",
            )

            module_records: Dict[str, Dict[str, Any]] = {}
            for file_name in module_record_names:
                payload = _load_json(required_paths[file_name])
                _validate_module_record(payload, file_name, required_module_record_class)
                module_records[file_name] = payload

            session_records: Dict[str, Dict[str, Any]] = {}
            for file_name in session_record_names:
                payload = _load_json(required_paths[file_name])
                _validate_session_record(payload, file_name, required_session_record_class)
                session_records[file_name] = payload

            freeze_note = _parse_freeze_note(required_paths[freeze_note_name])
            if freeze_note["package_id"] != package_id:
                raise AdapterIngestionError(
                    f"freeze_note.package_id_mismatch:{freeze_note['package_id']}!={package_id}"
                )

            hash_entries = _parse_hash_manifest(required_paths[hash_manifest_name])
            canonical_file_names = list(module_record_names) + list(session_record_names)
            hash_report = _verify_hashes(
                required_paths=required_paths,
                hash_entries=hash_entries,
                canonical_file_names=canonical_file_names,
                strict_hash_check=args.strict_hash_check,
            )

            classification = _classify_bundle(package_id, inventory, profile)

            normalized_rows: List[Dict[str, Any]] = []
            for file_name in module_record_names:
                role = _artifact_role_for_file(profile, file_name)
                normalized_rows.append(
                    _build_json_artifact_row(
                        profile=profile,
                        package_id=package_id,
                        file_name=file_name,
                        path=required_paths[file_name],
                        role=role,
                        payload=module_records[file_name],
                        freeze_timestamp=freeze_note["frozen_at_utc"],
                        hash_sha256=hash_entries.get(file_name),
                        freeze_note_present=True,
                    )
                )

            for file_name in session_record_names:
                role = _artifact_role_for_file(profile, file_name)
                normalized_rows.append(
                    _build_json_artifact_row(
                        profile=profile,
                        package_id=package_id,
                        file_name=file_name,
                        path=required_paths[file_name],
                        role=role,
                        payload=session_records[file_name],
                        freeze_timestamp=freeze_note["frozen_at_utc"],
                        hash_sha256=hash_entries.get(file_name),
                        freeze_note_present=True,
                    )
                )

            normalized_rows.append(
                _build_freeze_note_row(
                    profile=profile,
                    package_id=package_id,
                    file_name=freeze_note_name,
                    path=required_paths[freeze_note_name],
                    freeze_note=freeze_note,
                )
            )

            normalized_rows.append(
                _build_hash_manifest_row(
                    profile=profile,
                    package_id=package_id,
                    file_name=hash_manifest_name,
                    path=required_paths[hash_manifest_name],
                    hash_entries=hash_entries,
                    freeze_timestamp=freeze_note["frozen_at_utc"],
                )
            )

            output_dir = output_root / package_id
            hash_report_path = output_dir / OUTPUT_HASH_VERIFICATION_REPORT
            manifest = _build_onboarding_manifest(
                package_id=package_id,
                input_locator=input_locator,
                output_dir=output_dir,
                profile=profile,
                profile_path=profile_path,
                classification=classification,
                inventory=inventory,
                normalized_rows=normalized_rows,
                hash_report_path=hash_report_path,
                hash_report=hash_report,
            )
            normalization_report = _build_normalization_report(
                package_id=package_id,
                inventory=inventory,
                normalized_rows=normalized_rows,
                hash_report=hash_report,
                preview_count=args.preview_count,
                extra_defaults_applied=None,
            )

        else:
            if not args.input_file:
                raise AdapterIngestionError("input_file_required_for_client_governance_json")

            input_file = _normalize_path(args.input_file)
            input_locator = str(input_file)
            inventory = _inventory_single_file(input_file)
            dataset_payload = _load_json(input_file)
            validated_client_records = _validate_client_dataset(dataset_payload, profile)

            dataset_id = _require_str(dataset_payload.get("dataset_id"), "client_dataset.dataset_id")
            dataset_version = _require_str(dataset_payload.get("dataset_version"), "client_dataset.dataset_version")
            _require_str(dataset_payload.get("source_type"), "client_dataset.source_type")
            source_organization = dataset_payload.get("source_organization")
            if source_organization is not None and not isinstance(source_organization, str):
                raise AdapterIngestionError("client_dataset.source_organization_must_be_string")
            policy_context = dataset_payload.get("policy_context")
            if policy_context is not None and not isinstance(policy_context, str):
                raise AdapterIngestionError("client_dataset.policy_context_must_be_string")

            if not package_id:
                package_id = dataset_id

            classification = _classify_client_dataset(package_id, inventory, profile, dataset_payload)

            source_sha256 = inventory["files"][0]["sha256"]
            normalized_rows = [
                _build_client_record_row(
                    profile=profile,
                    package_id=package_id,
                    input_file=input_file,
                    inventory_sha256=source_sha256,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    policy_context=policy_context,
                    source_organization=source_organization,
                    client_record=row,
                )
                for row in validated_client_records
            ]

            hash_report = _build_single_file_hash_report(input_file, source_sha256)
            output_dir = output_root / package_id
            hash_report_path = output_dir / OUTPUT_HASH_VERIFICATION_REPORT

            manifest = _build_onboarding_manifest(
                package_id=package_id,
                input_locator=input_locator,
                output_dir=output_dir,
                profile=profile,
                profile_path=profile_path,
                classification=classification,
                inventory=inventory,
                normalized_rows=normalized_rows,
                hash_report_path=hash_report_path,
                hash_report=hash_report,
            )
            normalization_report = _build_normalization_report(
                package_id=package_id,
                inventory=inventory,
                normalized_rows=normalized_rows,
                hash_report=hash_report,
                preview_count=args.preview_count,
                extra_defaults_applied=[
                    "client-origin dataset held under structured JSON containment",
                ],
            )

        onboarding_manifest_path = output_dir / OUTPUT_ONBOARDING_MANIFEST
        normalized_jsonl_path = output_dir / OUTPUT_NORMALIZED_JSONL
        source_inventory_path = output_dir / OUTPUT_SOURCE_INVENTORY
        normalization_report_path = output_dir / OUTPUT_NORMALIZATION_REPORT
        hash_report_path_str = str(output_dir / OUTPUT_HASH_VERIFICATION_REPORT) if hash_report is not None else None
        onboarding_log_path = _build_onboarding_log_path(package_id)

        files_payload: Dict[str, Optional[str]] = {
            "onboarding_manifest": str(onboarding_manifest_path),
            "normalized_onboarding": str(normalized_jsonl_path),
            "source_inventory": str(source_inventory_path),
            "normalization_report": str(normalization_report_path),
            "onboarding_log": str(onboarding_log_path),
        }
        if hash_report_path_str is not None:
            files_payload["hash_verification_report"] = hash_report_path_str

        onboarding_log = _build_onboarding_log(
            package_id=package_id,
            template_family=template_family,
            profile=profile,
            input_locator=input_locator,
            output_dir=output_dir,
            classification=classification,
            inventory=inventory,
            normalized_rows=normalized_rows,
            hash_report=hash_report,
            files_payload=files_payload,
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            _write_json(source_inventory_path, inventory)
            if hash_report is not None:
                _write_json(output_dir / OUTPUT_HASH_VERIFICATION_REPORT, hash_report)
            _write_json(onboarding_manifest_path, manifest)
            _write_json(normalization_report_path, normalization_report)
            _write_jsonl(normalized_jsonl_path, normalized_rows)
            _write_json(onboarding_log_path, onboarding_log)

        result = {
            "status": "ok",
            "generated_at": _utc_now_iso(),
            "package_id": package_id,
            "template_family": template_family,
            "profile_id": _require_str(profile.get("profile_id"), "profile.profile_id"),
            "profile_version": _require_str(profile.get("profile_version"), "profile.profile_version"),
            "input_locator": input_locator,
            "output_dir": str(output_dir),
            "source_file_count": inventory["file_count"],
            "normalized_record_count": len(normalized_rows),
            "hash_verification_status": hash_report["overall_status"] if hash_report is not None else "not_applicable",
            "strict_hash_check": args.strict_hash_check,
            "dry_run": args.dry_run,
            "files": files_payload,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    except AdapterIngestionError as exc:
        if not package_id:
            if args.input_root:
                package_id = _normalize_path(args.input_root).name
                input_locator = str(_normalize_path(args.input_root))
            elif args.input_file:
                input_locator = str(_normalize_path(args.input_file))
                package_id = _normalize_path(args.input_file).stem
            else:
                package_id = "UNKNOWN-PACKAGE"

        error_payload = {
            "status": "error",
            "package_id": package_id,
            "error": str(exc),
        }

        rejection_report_path: Optional[Path] = None
        if args.write_rejected:
            rejection_report_path = _write_rejection_report(
                rejected_root=rejected_root,
                package_id=package_id,
                input_locator=input_locator,
                error_message=str(exc),
            )
            error_payload["rejection_report_path"] = str(rejection_report_path)

        print(json.dumps(error_payload, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
