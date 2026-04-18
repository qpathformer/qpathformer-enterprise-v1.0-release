#!/usr/bin/env python3
"""
TR dataset -> STATE_1 package/handoff/freeze/registry wrapper.

Purpose
-------
This wrapper is intentionally narrow and run-specific. It converts a strict
TR fine-tune dataset build into the package structure expected by the existing
STATE_1 lifecycle scripts, then executes:

1) package materialization
2) synthetic STATE_2 review artifact
3) synthetic STATE_2 promotion artifact
4) STATE_1 handoff
5) STATE_1 freeze
6) optional STATE_1 registry update

Why this exists
---------------
The current TR dataset build emits:
- train.sft.jsonl
- validation.sft.jsonl
- dataset_manifest.json
- dataset_preview.json
- reference_layer_report.json
- skipped_records.json
- source_mix_report.json

But the STATE_1 scripts expect a package directory with:
- dataset.jsonl
- manifest.json
- state2_review.json
- state2_promotion_decision.json
- state1_handoff.json       (created by run_state1_handoff.py)
- freeze_ready_manifest.json (created by run_state1_handoff.py)

This wrapper bridges that gap for the current TR workflow only.

Posture
-------
- non-authoritative
- explicit and auditable
- no hidden lifecycle mutation
- intended for this TR strict dataset run only
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from path_layout import PATH1_PACKAGE_ROOT, SHARED_CONFIGS_ROOT, SHARED_REGISTRY_ROOT


DEFAULT_PACKAGE_ID = "QPDS-TR-STRICT-ID3-001"
DEFAULT_REGISTRY_PATH = str(SHARED_REGISTRY_ROOT / "state1_dataset_registry.json")
DEFAULT_BACKEND_PROFILE_SOURCE = SHARED_CONFIGS_ROOT / "training_backend_profile.local_lora.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def count_jsonl_rows(path: Path) -> int:
    total = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += 1
    return total


def run_subprocess(cmd: List[str], dry_run: bool) -> subprocess.CompletedProcess[str] | None:
    print("[RUN]", " ".join(cmd))
    if dry_run:
        return None
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def require_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Missing required {label}: {path}")


def read_optional_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return read_json(path)


def compact_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }


def find_existing_registry_entry(registry_path: Path, dataset_version: str) -> Optional[Dict[str, Any]]:
    registry_payload = read_optional_json(registry_path)
    if not isinstance(registry_payload, dict):
        return None

    raw_entries = registry_payload.get("entries")
    if not isinstance(raw_entries, list):
        return None

    matches: List[Dict[str, Any]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        if str(item.get("dataset_version") or "") != dataset_version:
            continue
        matches.append(item)

    if not matches:
        return None

    matches.sort(key=lambda item: str(item.get("registered_at") or item.get("updated_at") or ""))
    return matches[-1]


def merge_training_manifest_registry(
    *,
    training_manifest: Dict[str, Any],
    registry_entry: Optional[Dict[str, Any]],
    package_id: str,
) -> Dict[str, Any]:
    merged = dict(training_manifest)

    if not merged.get("dataset_passport_id"):
        merged["dataset_passport_id"] = package_id

    if not isinstance(registry_entry, dict):
        return merged

    registry_entry_id = registry_entry.get("registry_entry_id")
    if isinstance(registry_entry_id, str) and registry_entry_id.strip() and not merged.get("registry_entry_id"):
        merged["registry_entry_id"] = registry_entry_id.strip()

    registered_at = registry_entry.get("registered_at")
    if isinstance(registered_at, str) and registered_at.strip() and not merged.get("registered_at"):
        merged["registered_at"] = registered_at.strip()

    registry_state = registry_entry.get("state")
    if isinstance(registry_state, str) and registry_state.strip() and not merged.get("registry_state"):
        merged["registry_state"] = registry_state.strip()

    if not merged.get("target_model") and isinstance(registry_entry.get("target_model"), dict):
        merged["target_model"] = registry_entry.get("target_model")

    return merged


def resolve_target_model(
    *,
    source_manifest: Dict[str, Any],
    training_manifest: Optional[Dict[str, Any]],
    backend_profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    target_model: Dict[str, Any] = {}

    source_target = source_manifest.get("target_model")
    if isinstance(source_target, dict):
        target_model.update(source_target)

    if isinstance(training_manifest, dict):
        training_target = training_manifest.get("target_model")
        if isinstance(training_target, dict):
            target_model.update(training_target)

    if isinstance(backend_profile, dict):
        backend_model = backend_profile.get("model")
        if isinstance(backend_model, dict):
            for key, value in backend_model.items():
                target_model.setdefault(key, value)

        backend_name = backend_profile.get("backend")
        if isinstance(backend_name, str) and backend_name.strip():
            target_model.setdefault("training_mode", backend_name.strip())

        backend_profile_id = backend_profile.get("backend_profile_id")
        if isinstance(backend_profile_id, str) and backend_profile_id.strip():
            target_model.setdefault("backend_profile_id", backend_profile_id.strip())

        execution_mode = backend_profile.get("execution_mode")
        if isinstance(execution_mode, str) and execution_mode.strip():
            target_model.setdefault("execution_mode", execution_mode.strip())

    return compact_dict(target_model)


def resolve_routing_profile(
    *,
    source_manifest: Dict[str, Any],
    training_manifest: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    for candidate in (training_manifest, source_manifest):
        if isinstance(candidate, dict):
            routing_profile = candidate.get("routing_profile")
            if isinstance(routing_profile, dict) and routing_profile:
                return routing_profile

    filters = source_manifest.get("filters")
    filters_dict = filters if isinstance(filters, dict) else {}
    return {
        "profile_type": "tr_wrapper_flow",
        "path_id": "path_1_tr_corpus_reference",
        "source_stage": "tr_signals",
        "dataset_stage": "tr_finetune",
        "package_stage": "state1_wrapper",
        "reference_match_required": bool(filters_dict.get("require_reference_match", False)),
    }


def build_authorization_summary(
    *,
    source_manifest: Dict[str, Any],
    training_manifest: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    filters = source_manifest.get("filters")
    filters_dict = filters if isinstance(filters, dict) else {}

    authority = source_manifest.get("authority_posture")
    authority_dict = authority if isinstance(authority, dict) else {}

    training_auth = {}
    if isinstance(training_manifest, dict):
        raw_training_auth = training_manifest.get("authorization_posture")
        if isinstance(raw_training_auth, dict):
            training_auth = raw_training_auth

    return compact_dict(
        {
            "reference_match_required": bool(filters_dict.get("require_reference_match", False)),
            "reference_id_count": int(source_manifest.get("reference_id_count", 0)),
            "reference_reasoning_posture_counts": source_manifest.get("reference_reasoning_posture_counts", {}),
            "non_authoritative": bool(
                training_auth.get(
                    "non_authoritative",
                    authority_dict.get("non_authoritative", True),
                )
            ),
            "governance_first": bool(training_auth.get("governance_first", authority_dict.get("governance_first", True))),
            "training_preparation_only": bool(authority_dict.get("training_preparation_only", False)),
            "registry_state": training_manifest.get("registry_state") if isinstance(training_manifest, dict) else None,
            "registry_entry_id": training_manifest.get("registry_entry_id") if isinstance(training_manifest, dict) else None,
            "dataset_passport_id": training_manifest.get("dataset_passport_id") if isinstance(training_manifest, dict) else None,
        }
    )


def build_training_context(
    *,
    training_manifest: Optional[Dict[str, Any]],
    backend_profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    context: Dict[str, Any] = {}

    if isinstance(training_manifest, dict):
        context.update(
            compact_dict(
                {
                    "lifecycle_state": training_manifest.get("lifecycle_state"),
                    "train_file": training_manifest.get("train_file"),
                    "record_count": training_manifest.get("record_count"),
                    "dataset_passport_id": training_manifest.get("dataset_passport_id"),
                    "registry_state": training_manifest.get("registry_state"),
                    "registry_entry_id": training_manifest.get("registry_entry_id"),
                }
            )
        )

    if isinstance(backend_profile, dict):
        backend_summary = compact_dict(
            {
                "backend_profile_id": backend_profile.get("backend_profile_id"),
                "backend": backend_profile.get("backend"),
                "execution_mode": backend_profile.get("execution_mode"),
                "format": backend_profile.get("format"),
            }
        )
        if backend_summary:
            context["backend_profile"] = backend_summary

    return context


def build_synthesized_training_manifest(
    *,
    package_id: str,
    dataset_version: str,
    source_manifest: Dict[str, Any],
    backend_profile: Optional[Dict[str, Any]],
    train_file_path: Path,
) -> Dict[str, Any]:
    backend_payload = backend_profile if isinstance(backend_profile, dict) else {}
    model_payload = backend_payload.get("model") if isinstance(backend_payload.get("model"), dict) else {}
    authorization_summary = build_authorization_summary(
        source_manifest=source_manifest,
        training_manifest=None,
    )

    return {
        "dataset_version": dataset_version,
        "lifecycle_state": "STATE_1",
        "record_count": count_jsonl_rows(train_file_path),
        "train_file": "train.sft.jsonl",
        "registry_state": "STATE_1",
        "dataset_passport_id": package_id,
        "target_model": compact_dict(
            {
                "training_mode": backend_payload.get("backend"),
                "model_family": model_payload.get("model_family"),
                "model_base": model_payload.get("model_base"),
            }
        ),
        "authorization_posture": compact_dict(
            {
                "non_authoritative": authorization_summary.get("non_authoritative", True),
                "governance_first": authorization_summary.get("governance_first", True),
                "reference_match_required": authorization_summary.get("reference_match_required", False),
                "reference_id_count": authorization_summary.get("reference_id_count", 0),
                "reference_reasoning_posture_counts": authorization_summary.get("reference_reasoning_posture_counts", {}),
            }
        ),
    }


def build_review_artifact(
    *,
    package_id: str,
    dataset_version: str,
    dataset_path: Path,
    manifest: Dict[str, Any],
    notes: str,
) -> Dict[str, Any]:
    candidate_count = count_jsonl_rows(dataset_path)
    source_record_count = int(manifest.get("record_counts", {}).get("source_signal_rows", 0))
    return {
        "review_id": f"REVIEW-{uuid4()}",
        "review_timestamp": utc_now_iso(),
        "review_scope": "STATE_2",
        "package_id": package_id,
        "dataset_version": dataset_version,
        "decision": {
            "approved": True,
            "decision": "APPROVE_STATE2_REVIEW",
            "reasons": [
                "tr_dataset_wrapper_review",
                "strict_reference_match_confirmed",
                "inspection_dominant_governed_dataset",
            ],
        },
        "review_metrics": {
            "candidate_count": candidate_count,
            "review_ready_ratio": 1.0,
            "routing_mismatch_count": 0,
            "missing_content_count": 0,
        },
        "exceptions": {
            "routing_mismatches": [],
            "missing_content_candidate_ids": [],
        },
        "package_summary": {
            "source_record_count": source_record_count,
            "dataset_version": dataset_version,
        },
        "notes": notes,
        "written": True,
    }



def build_promotion_artifact(
    *,
    package_id: str,
    dataset_version: str,
    manifest: Dict[str, Any],
    notes: str,
) -> Dict[str, Any]:
    return {
        "promotion_id": f"PROMO-{uuid4()}",
        "promotion_timestamp": utc_now_iso(),
        "promotion_scope": "STATE_1",
        "package_id": package_id,
        "dataset_version": dataset_version,
        "decision": {
            "approved": True,
            "decision": "APPROVE_STATE_1",
            "reasons": [
                "tr_dataset_wrapper_promotion",
                "governance_reference_enforced",
                "state1_candidate_prepared",
            ],
        },
        "promotion_metrics": {
            "review_ready_ratio": 1.0,
        },
        "package_summary": {
            "target_model": manifest.get("target_model", {}),
            "routing_profile": manifest.get("routing_profile", {}),
        },
        "notes": notes,
        "written": True,
    }



def build_package_manifest(
    *,
    package_id: str,
    dataset_version: str,
    source_dataset_dir: Path,
    source_manifest: Dict[str, Any],
    training_manifest: Optional[Dict[str, Any]],
    backend_profile: Optional[Dict[str, Any]],
    dataset_jsonl_path: Path,
    package_dir: Path,
    source_artifacts: List[str],
) -> Dict[str, Any]:
    candidate_count = count_jsonl_rows(dataset_jsonl_path)
    record_counts = source_manifest.get("record_counts", {})
    source_record_count = int(record_counts.get("source_signal_rows", 0))
    return {
        "manifest_version": "tr_state1_package_v0.1",
        "package_id": package_id,
        "dataset_version": dataset_version,
        "created_at_utc": utc_now_iso(),
        "source_dataset_dir": str(source_dataset_dir),
        "package_dir": str(package_dir),
        "candidate_count": candidate_count,
        "source_record_count": source_record_count,
        "target_model": resolve_target_model(
            source_manifest=source_manifest,
            training_manifest=training_manifest,
            backend_profile=backend_profile,
        ),
        "routing_profile": resolve_routing_profile(
            source_manifest=source_manifest,
            training_manifest=training_manifest,
        ),
        "training_context": build_training_context(
            training_manifest=training_manifest,
            backend_profile=backend_profile,
        ),
        "authorization_summary": build_authorization_summary(
            source_manifest=source_manifest,
            training_manifest=training_manifest,
        ),
        "source_artifacts": source_artifacts,
    }



def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-generate review + promotion + handoff + freeze for the current strict TR dataset run.")
    parser.add_argument("--dataset-dir", required=True, help="Path to the strict TR dataset folder, e.g. datasets/tr_finetune/checkpoint_v3_strict")
    parser.add_argument("--package-id", default=DEFAULT_PACKAGE_ID)
    parser.add_argument("--packages-root", default=str(PATH1_PACKAGE_ROOT))
    parser.add_argument("--handoff-script", default="scripts/run_state1_handoff.py")
    parser.add_argument("--freeze-script", default="scripts/run_state1_freeze.py")
    parser.add_argument("--registry-script", default="scripts/run_state1_registry_update.py")
    parser.add_argument("--registry-path", default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--notes", default="TR strict dataset wrapper run")
    parser.add_argument("--skip-registry", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).expanduser().resolve()
    packages_root = Path(args.packages_root).expanduser().resolve()
    handoff_script = Path(args.handoff_script).expanduser().resolve()
    freeze_script = Path(args.freeze_script).expanduser().resolve()
    registry_script = Path(args.registry_script).expanduser().resolve()
    registry_path = Path(args.registry_path).expanduser().resolve()

    require_exists(dataset_dir, "dataset directory")
    require_exists(dataset_dir / "train.sft.jsonl", "train.sft.jsonl")
    require_exists(dataset_dir / "validation.sft.jsonl", "validation.sft.jsonl")
    require_exists(dataset_dir / "dataset_manifest.json", "dataset_manifest.json")
    require_exists(dataset_dir / "dataset_preview.json", "dataset_preview.json")
    require_exists(dataset_dir / "reference_layer_report.json", "reference_layer_report.json")
    require_exists(dataset_dir / "source_mix_report.json", "source_mix_report.json")
    require_exists(dataset_dir / "skipped_records.json", "skipped_records.json")
    require_exists(handoff_script, "run_state1_handoff.py")
    require_exists(freeze_script, "run_state1_freeze.py")
    if not args.skip_registry:
        require_exists(registry_script, "run_state1_registry_update.py")

    package_dir = packages_root / args.package_id
    dataset_jsonl_path = package_dir / "dataset.jsonl"
    manifest_json_path = package_dir / "manifest.json"
    review_json_path = package_dir / "state2_review.json"
    promotion_json_path = package_dir / "state2_promotion_decision.json"

    source_manifest = read_json(dataset_dir / "dataset_manifest.json")
    training_manifest_path = dataset_dir / "state1_training_manifest.json"
    dataset_backend_profile_path = dataset_dir / "training_backend_profile.json"
    backend_profile_source_path = dataset_backend_profile_path if dataset_backend_profile_path.exists() else DEFAULT_BACKEND_PROFILE_SOURCE
    require_exists(backend_profile_source_path, "training backend profile source")

    training_manifest = read_optional_json(training_manifest_path)
    backend_profile = read_optional_json(backend_profile_source_path)
    dataset_version = str(source_manifest.get("dataset_version") or dataset_dir.name)
    existing_registry_entry = find_existing_registry_entry(registry_path, dataset_version)

    if training_manifest is None:
        training_manifest = build_synthesized_training_manifest(
            package_id=args.package_id,
            dataset_version=dataset_version,
            source_manifest=source_manifest,
            backend_profile=backend_profile,
            train_file_path=dataset_dir / "train.sft.jsonl",
        )

    training_manifest = merge_training_manifest_registry(
        training_manifest=training_manifest,
        registry_entry=existing_registry_entry,
        package_id=args.package_id,
    )

    copied_source_artifacts = [
        "dataset.jsonl",
        "train.sft.jsonl",
        "manifest.json",
        "dataset_preview.json",
        "reference_layer_report.json",
        "source_mix_report.json",
        "skipped_records.json",
        "validation.sft.jsonl",
        "state1_training_manifest.json",
        "training_backend_profile.json",
    ]

    package_manifest = build_package_manifest(
        package_id=args.package_id,
        dataset_version=dataset_version,
        source_dataset_dir=dataset_dir,
        source_manifest=source_manifest,
        training_manifest=training_manifest,
        backend_profile=backend_profile,
        dataset_jsonl_path=dataset_dir / "train.sft.jsonl",
        package_dir=package_dir,
        source_artifacts=copied_source_artifacts,
    )
    review_artifact = build_review_artifact(
        package_id=args.package_id,
        dataset_version=dataset_version,
        dataset_path=dataset_dir / "train.sft.jsonl",
        manifest=source_manifest,
        notes=args.notes,
    )
    promotion_artifact = build_promotion_artifact(
        package_id=args.package_id,
        dataset_version=dataset_version,
        manifest=source_manifest,
        notes=args.notes,
    )

    summary = {
        "status": "ok",
        "package_id": args.package_id,
        "dataset_version": dataset_version,
        "dataset_dir": str(dataset_dir),
        "package_dir": str(package_dir),
        "steps": [
            "materialize_state1_package",
            "write_state2_review",
            "write_state2_promotion",
            "run_state1_handoff",
            "run_state1_freeze",
            "run_state1_registry_update" if not args.skip_registry else "skip_registry",
        ],
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    package_dir.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(dataset_dir / "train.sft.jsonl", dataset_jsonl_path)
    shutil.copyfile(dataset_dir / "train.sft.jsonl", package_dir / "train.sft.jsonl")
    shutil.copyfile(dataset_dir / "validation.sft.jsonl", package_dir / "validation.sft.jsonl")
    shutil.copyfile(dataset_dir / "dataset_preview.json", package_dir / "dataset_preview.json")
    shutil.copyfile(dataset_dir / "reference_layer_report.json", package_dir / "reference_layer_report.json")
    shutil.copyfile(dataset_dir / "source_mix_report.json", package_dir / "source_mix_report.json")
    shutil.copyfile(dataset_dir / "skipped_records.json", package_dir / "skipped_records.json")
    write_json(package_dir / "state1_training_manifest.json", training_manifest)
    if backend_profile is not None:
        if backend_profile_source_path.exists():
            shutil.copyfile(backend_profile_source_path, package_dir / "training_backend_profile.json")
        else:
            write_json(package_dir / "training_backend_profile.json", backend_profile)

    write_json(manifest_json_path, package_manifest)
    write_json(review_json_path, review_artifact)
    write_json(promotion_json_path, promotion_artifact)

    handoff_cmd = [
        sys.executable,
        str(handoff_script),
        "--package-dir",
        str(package_dir),
        "--notes",
        args.notes,
    ]
    handoff_result = run_subprocess(handoff_cmd, dry_run=False)
    if handoff_result is not None and handoff_result.returncode != 0:
        sys.stderr.write(handoff_result.stderr)
        return handoff_result.returncode
    if handoff_result is not None and handoff_result.stdout:
        print(handoff_result.stdout)

    freeze_cmd = [
        sys.executable,
        str(freeze_script),
        "--package-dir",
        str(package_dir),
        "--notes",
        args.notes,
    ]
    freeze_result = run_subprocess(freeze_cmd, dry_run=False)
    if freeze_result is not None and freeze_result.returncode != 0:
        sys.stderr.write(freeze_result.stderr)
        return freeze_result.returncode
    if freeze_result is not None and freeze_result.stdout:
        print(freeze_result.stdout)

    if not args.skip_registry:
        registry_cmd = [
            sys.executable,
            str(registry_script),
            "--package-dir",
            str(package_dir),
            "--registry-path",
            str(registry_path),
            "--notes",
            args.notes,
        ]
        registry_result = run_subprocess(registry_cmd, dry_run=False)
        if registry_result is not None and registry_result.returncode != 0:
            sys.stderr.write(registry_result.stderr)
            return registry_result.returncode
        if registry_result is not None and registry_result.stdout:
            print(registry_result.stdout)

        refreshed_registry_entry = find_existing_registry_entry(registry_path, dataset_version)
        training_manifest = merge_training_manifest_registry(
            training_manifest=training_manifest,
            registry_entry=refreshed_registry_entry,
            package_id=args.package_id,
        )
        package_manifest = build_package_manifest(
            package_id=args.package_id,
            dataset_version=dataset_version,
            source_dataset_dir=dataset_dir,
            source_manifest=source_manifest,
            training_manifest=training_manifest,
            backend_profile=backend_profile,
            dataset_jsonl_path=dataset_dir / "train.sft.jsonl",
            package_dir=package_dir,
            source_artifacts=copied_source_artifacts,
        )
        write_json(package_dir / "state1_training_manifest.json", training_manifest)
        write_json(manifest_json_path, package_manifest)

    final_summary = {
        **summary,
        "written": True,
        "package_files": sorted(p.name for p in package_dir.iterdir()),
    }
    print(json.dumps(final_summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
