#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10.4 STATE_1 Registry Update Layer

Consumes a frozen STATE_1 package and records it into a dataset registry,
completing the governed lifecycle loop.

Scope:
- load frozen manifest + freeze artifact + upstream package artifacts
- verify freeze approval and package integrity
- append a registry entry
- emit a registry update artifact
- preserve governance-first posture

Posture:
- ID_2 only
- non-authoritative
- explicit registry mutation only
- append-only registry behavior
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from path_layout import SHARED_REGISTRY_ROOT


DEFAULT_REQUIRE_APPROVED_FREEZE = True
DEFAULT_REQUIRE_STATE1 = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def package_is_registry_ready_structurally(package_dir: Path) -> bool:
    freeze_dir = package_dir / "freeze"
    return (
        package_dir.exists()
        and (package_dir / "manifest.json").exists()
        and (package_dir / "state2_review.json").exists()
        and (package_dir / "state2_promotion_decision.json").exists()
        and (package_dir / "state1_handoff.json").exists()
        and (package_dir / "freeze_ready_manifest.json").exists()
        and freeze_dir.exists()
        and (freeze_dir / "state1_freeze.json").exists()
        and (freeze_dir / "frozen_manifest.json").exists()
        and (freeze_dir / "frozen_dataset.jsonl").exists()
    )


def list_candidate_package_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []

    def package_sort_key(package_dir: Path) -> tuple[float, float]:
        frozen_manifest_path = package_dir / "freeze" / "frozen_manifest.json"
        frozen_ts = 0.0

        if frozen_manifest_path.exists():
            try:
                payload = read_json(frozen_manifest_path)
                created_at = str(payload.get("frozen_timestamp") or "")
                if created_at.endswith("Z"):
                    created_at = created_at.replace("Z", "+00:00")
                if created_at:
                    frozen_ts = datetime.fromisoformat(created_at).timestamp()
            except Exception:
                frozen_ts = 0.0

        return (frozen_ts, package_dir.stat().st_mtime)

    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=package_sort_key, reverse=True)
    return dirs


@dataclass(frozen=True)
class RegistryThresholds:
    require_approved_freeze: bool = DEFAULT_REQUIRE_APPROVED_FREEZE
    require_state1: bool = DEFAULT_REQUIRE_STATE1


class RegistryError(RuntimeError):
    pass


class State1RegistryUpdater:
    def __init__(
        self,
        *,
        package_dir: Optional[Path],
        latest_root: Optional[Path],
        registry_path: Path,
        require_approved_freeze: bool,
        require_state1: bool,
        dry_run: bool,
        notes: Optional[str],
    ) -> None:
        self.package_dir = package_dir
        self.latest_root = latest_root
        self.registry_path = registry_path
        self.freeze_dir: Optional[Path] = None
        self.freeze_artifact_path: Optional[Path] = None
        self.frozen_manifest_path: Optional[Path] = None
        self.registry_update_path: Optional[Path] = None
        self.dry_run = dry_run
        self.notes = notes or ""

        self.thresholds = RegistryThresholds(
            require_approved_freeze=require_approved_freeze,
            require_state1=require_state1,
        )

    def run(self) -> Dict[str, Any]:
        candidate_dirs: List[Path]

        if self.package_dir is not None:
            candidate_dirs = [self.package_dir]
        else:
            if self.latest_root is None:
                raise RegistryError("Either --package-dir or --latest-root must be provided.")
            candidate_dirs = list_candidate_package_dirs(self.latest_root)

        if not candidate_dirs:
            raise RegistryError("No candidate package directories available for STATE_1 registry update.")

        attempted: List[Dict[str, str]] = []

        for package_dir in candidate_dirs:
            freeze_dir = package_dir / "freeze"
            freeze_artifact_path = freeze_dir / "state1_freeze.json"
            frozen_manifest_path = freeze_dir / "frozen_manifest.json"
            registry_update_path = freeze_dir / "state1_registry_update.json"

            if not package_is_registry_ready_structurally(package_dir):
                attempted.append(
                    {
                        "package_dir": str(package_dir),
                        "status": "skipped",
                        "reason": "missing_required_files",
                    }
                )
                continue

            self.package_dir = package_dir
            self.freeze_dir = freeze_dir
            self.freeze_artifact_path = freeze_artifact_path
            self.frozen_manifest_path = frozen_manifest_path
            self.registry_update_path = registry_update_path

            freeze_artifact = read_json(freeze_artifact_path)
            frozen_manifest = read_json(frozen_manifest_path)
            registry = self._load_registry()

            update_artifact, updated_registry = self._build_registry_outputs(
                freeze_artifact=freeze_artifact,
                frozen_manifest=frozen_manifest,
                registry=registry,
            )

            approved = bool((update_artifact.get("decision") or {}).get("approved"))
            update_artifact["attempted_packages"] = attempted + [
                {
                    "package_dir": str(package_dir),
                    "status": "selected",
                    "reason": "first_registry_candidate",
                }
            ]

            if approved or self.package_dir is not None:
                if not self.dry_run:
                    write_json(self.registry_path, updated_registry)
                    if self.registry_update_path is not None:
                        write_json(self.registry_update_path, update_artifact)
                        update_artifact["registry_update_path"] = str(self.registry_update_path)

                update_artifact["registry_path"] = str(self.registry_path)
                return update_artifact

            attempted.append(
                {
                    "package_dir": str(package_dir),
                    "status": "skipped",
                    "reason": "registry_thresholds_not_met",
                }
            )

        raise RegistryError("No STATE_1 frozen package satisfied the configured registry thresholds.")

    def _load_registry(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "registry_id": str(uuid4()),
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
                "entries": [],
            }

        payload = read_json(self.registry_path)
        if "entries" not in payload or not isinstance(payload["entries"], list):
            raise RegistryError(f"Registry file has invalid format: {self.registry_path}")
        return payload

    def _build_registry_outputs(
        self,
        *,
        freeze_artifact: Dict[str, Any],
        frozen_manifest: Dict[str, Any],
        registry: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        freeze_decision = freeze_artifact.get("decision") or {}
        freeze_summary = freeze_artifact.get("freeze_ready_summary") or {}
        state_value = str(frozen_manifest.get("state", ""))

        freeze_approved = bool(freeze_decision.get("approved", False))
        freeze_decision_name = str(freeze_decision.get("decision", ""))

        decision_reasons: List[str] = []
        approved = True

        if self.thresholds.require_approved_freeze and not freeze_approved:
            approved = False
            decision_reasons.append("state1_freeze_not_approved")

        if self.thresholds.require_state1 and state_value != "STATE_1":
            approved = False
            decision_reasons.append(f"frozen_manifest_state_not_state1:{state_value}")

        if freeze_decision_name != "FREEZE_STATE1_PACKAGE":
            approved = False
            decision_reasons.append(f"unexpected_freeze_decision:{freeze_decision_name}")

        if not decision_reasons:
            decision_reasons.append("all_state1_registry_thresholds_passed")

        dataset_version = str(frozen_manifest.get("dataset_version", ""))
        existing_entries = registry.get("entries", [])

        duplicate_entry = None
        for entry in existing_entries:
            if str(entry.get("dataset_version", "")) == dataset_version:
                duplicate_entry = entry
                break

        if duplicate_entry is not None:
            approved = False
            decision_reasons = [f"dataset_version_already_registered:{dataset_version}"]

        decision = "REGISTER_STATE1_PACKAGE" if approved else "HOLD_STATE1_REGISTRY_UPDATE"

        registry_entry = {
            "registry_entry_id": str(uuid4()),
            "registered_at": utc_now_iso(),
            "state": "STATE_1",
            "dataset_version": dataset_version,
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "freeze_dir": str(self.freeze_dir) if self.freeze_dir else None,
            "frozen_manifest_path": str(self.frozen_manifest_path) if self.frozen_manifest_path else None,
            "freeze_artifact_path": str(self.freeze_artifact_path) if self.freeze_artifact_path else None,
            "freeze_id": str(frozen_manifest.get("freeze_id", "")),
            "candidate_count": int(frozen_manifest.get("candidate_count", 0)),
            "source_record_count": int(frozen_manifest.get("source_record_count", 0)),
            "target_model": frozen_manifest.get("target_model", {}),
            "authorization_summary": frozen_manifest.get("authorization_summary", {}),
            "routing_profile": frozen_manifest.get("routing_profile", {}),
            "registry_posture": {
                "non_authoritative": True,
                "governance_first": True,
                "explicit_update": True,
            },
        }

        updated_registry = {
            **registry,
            "updated_at": utc_now_iso(),
            "entries": existing_entries + ([registry_entry] if approved else []),
        }

        update_artifact = {
            "registry_update_id": str(uuid4()),
            "registry_update_timestamp": utc_now_iso(),
            "registry_scope": "STATE_1",
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "freeze_dir": str(self.freeze_dir) if self.freeze_dir else None,
            "freeze_artifact_path": str(self.freeze_artifact_path) if self.freeze_artifact_path else None,
            "frozen_manifest_path": str(self.frozen_manifest_path) if self.frozen_manifest_path else None,
            "posture": {
                "access_mode": "ID_2",
                "non_authoritative": True,
                "governance_first": True,
                "explicit_registry_mutation": True,
            },
            "freeze_summary": {
                "freeze_id": str(freeze_artifact.get("freeze_id", "")),
                "freeze_decision": freeze_decision_name,
                "freeze_approved": freeze_approved,
                "freeze_ready": bool(freeze_summary.get("freeze_ready", False)),
            },
            "frozen_package_summary": {
                "dataset_version": dataset_version,
                "state": state_value,
                "candidate_count": int(frozen_manifest.get("candidate_count", 0)),
                "source_record_count": int(frozen_manifest.get("source_record_count", 0)),
                "target_model": frozen_manifest.get("target_model", {}),
            },
            "thresholds": {
                "require_approved_freeze": self.thresholds.require_approved_freeze,
                "require_state1": self.thresholds.require_state1,
            },
            "decision": {
                "approved": approved,
                "decision": decision,
                "reasons": decision_reasons,
            },
            "registry_entry_preview": registry_entry if approved else None,
            "notes": self.notes,
            "written": not self.dry_run,
        }

        return update_artifact, updated_registry


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append a frozen STATE_1 package into the dataset registry."
    )
    parser.add_argument(
        "--package-dir",
        required=False,
        help="Path to the frozen STATE_1 package directory.",
    )
    parser.add_argument(
        "--latest-root",
        default=None,
        help="Root directory containing timestamped package directories. Newest registry-eligible package is selected automatically.",
    )
    parser.add_argument(
        "--registry-path",
        default=str(SHARED_REGISTRY_ROOT / "state1_dataset_registry.json"),
        help="Path to the dataset registry JSON file.",
    )
    parser.add_argument(
        "--require-approved-freeze",
        action="store_true",
        default=DEFAULT_REQUIRE_APPROVED_FREEZE,
        help="Require the STATE_1 freeze artifact to be approved.",
    )
    parser.add_argument(
        "--require-state1",
        action="store_true",
        default=DEFAULT_REQUIRE_STATE1,
        help="Require the frozen manifest state to be STATE_1.",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional registry update notes stored in the update artifact.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate the package and print the registry update artifact without writing files.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    updater = State1RegistryUpdater(
        package_dir=Path(args.package_dir).expanduser().resolve() if args.package_dir else None,
        latest_root=Path(args.latest_root).expanduser().resolve() if args.latest_root else None,
        registry_path=Path(args.registry_path).expanduser().resolve(),
        require_approved_freeze=args.require_approved_freeze,
        require_state1=args.require_state1,
        dry_run=args.dry_run,
        notes=args.notes,
    )

    try:
        result = updater.run()
    except RegistryError as exc:
        sys.stderr.write(f"[STATE1 REGISTRY UPDATE FAILED] {exc}\n")
        return 1
    except RuntimeError as exc:
        sys.stderr.write(f"[STATE1 REGISTRY UPDATE FAILED] {exc}\n")
        return 1

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
