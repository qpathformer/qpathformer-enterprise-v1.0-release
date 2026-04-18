#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10.3 STATE_1 Freeze Layer

Consumes a freeze-ready STATE_1 handoff package and emits a finalized STATE_1
freeze artifact plus frozen dataset outputs.

Scope:
- load package manifest + dataset + review + promotion + handoff + freeze-ready manifest
- verify freeze readiness and package integrity
- emit state1 freeze artifact
- emit frozen manifest
- emit frozen dataset copy
- preserve governance-first posture

Posture:
- ID_2 only
- non-authoritative
- explicit freeze step only
- no automatic registry mutation
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4


DEFAULT_MIN_CANDIDATES = 4
DEFAULT_REQUIRE_APPROVED_REVIEW = True
DEFAULT_REQUIRE_APPROVED_PROMOTION = True
DEFAULT_REQUIRE_APPROVED_HANDOFF = True
DEFAULT_REQUIRE_FREEZE_READY = True
DEFAULT_MAX_ROUTING_MISMATCHES = 0
DEFAULT_MAX_MISSING_CONTENT = 0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL row at line {line_no}: {exc}") from exc
    return rows


def package_is_freeze_ready_structurally(package_dir: Path) -> bool:
    return (
        package_dir.exists()
        and (package_dir / "dataset.jsonl").exists()
        and (package_dir / "manifest.json").exists()
        and (package_dir / "state2_review.json").exists()
        and (package_dir / "state2_promotion_decision.json").exists()
        and (package_dir / "state1_handoff.json").exists()
        and (package_dir / "freeze_ready_manifest.json").exists()
    )


def list_candidate_package_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []

    def package_sort_key(package_dir: Path) -> tuple[float, float]:
        freeze_ready_path = package_dir / "freeze_ready_manifest.json"
        freeze_ts = 0.0

        if freeze_ready_path.exists():
            try:
                payload = read_json(freeze_ready_path)
                created_at = str(payload.get("freeze_ready_timestamp") or "")
                if created_at.endswith("Z"):
                    created_at = created_at.replace("Z", "+00:00")
                if created_at:
                    freeze_ts = datetime.fromisoformat(created_at).timestamp()
            except Exception:
                freeze_ts = 0.0

        return (freeze_ts, package_dir.stat().st_mtime)

    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=package_sort_key, reverse=True)
    return dirs


@dataclass(frozen=True)
class FreezeThresholds:
    min_candidates: int = DEFAULT_MIN_CANDIDATES
    require_approved_review: bool = DEFAULT_REQUIRE_APPROVED_REVIEW
    require_approved_promotion: bool = DEFAULT_REQUIRE_APPROVED_PROMOTION
    require_approved_handoff: bool = DEFAULT_REQUIRE_APPROVED_HANDOFF
    require_freeze_ready: bool = DEFAULT_REQUIRE_FREEZE_READY
    max_routing_mismatches: int = DEFAULT_MAX_ROUTING_MISMATCHES
    max_missing_content: int = DEFAULT_MAX_MISSING_CONTENT


class FreezeError(RuntimeError):
    pass


class State1Freezer:
    def __init__(
        self,
        *,
        package_dir: Optional[Path],
        latest_root: Optional[Path],
        min_candidates: int,
        require_approved_review: bool,
        require_approved_promotion: bool,
        require_approved_handoff: bool,
        require_freeze_ready: bool,
        max_routing_mismatches: int,
        max_missing_content: int,
        dry_run: bool,
        notes: Optional[str],
    ) -> None:
        self.package_dir = package_dir
        self.latest_root = latest_root
        self.dataset_path: Optional[Path] = None
        self.manifest_path: Optional[Path] = None
        self.review_path: Optional[Path] = None
        self.promotion_path: Optional[Path] = None
        self.handoff_path: Optional[Path] = None
        self.freeze_ready_manifest_path: Optional[Path] = None
        self.freeze_dir: Optional[Path] = None
        self.state1_freeze_path: Optional[Path] = None
        self.frozen_manifest_path: Optional[Path] = None
        self.frozen_dataset_path: Optional[Path] = None
        self.dry_run = dry_run
        self.notes = notes or ""

        self.thresholds = FreezeThresholds(
            min_candidates=min_candidates,
            require_approved_review=require_approved_review,
            require_approved_promotion=require_approved_promotion,
            require_approved_handoff=require_approved_handoff,
            require_freeze_ready=require_freeze_ready,
            max_routing_mismatches=max_routing_mismatches,
            max_missing_content=max_missing_content,
        )

    def run(self) -> Dict[str, Any]:
        candidate_dirs: List[Path]

        if self.package_dir is not None:
            candidate_dirs = [self.package_dir]
        else:
            if self.latest_root is None:
                raise FreezeError("Either --package-dir or --latest-root must be provided.")
            candidate_dirs = list_candidate_package_dirs(self.latest_root)

        if not candidate_dirs:
            raise FreezeError("No candidate package directories available for STATE_1 freeze.")

        attempted: List[Dict[str, str]] = []

        for package_dir in candidate_dirs:
            dataset_path = package_dir / "dataset.jsonl"
            manifest_path = package_dir / "manifest.json"
            review_path = package_dir / "state2_review.json"
            promotion_path = package_dir / "state2_promotion_decision.json"
            handoff_path = package_dir / "state1_handoff.json"
            freeze_ready_manifest_path = package_dir / "freeze_ready_manifest.json"

            freeze_dir = package_dir / "freeze"
            state1_freeze_path = freeze_dir / "state1_freeze.json"
            frozen_manifest_path = freeze_dir / "frozen_manifest.json"
            frozen_dataset_path = freeze_dir / "frozen_dataset.jsonl"

            if not package_is_freeze_ready_structurally(package_dir):
                attempted.append(
                    {
                        "package_dir": str(package_dir),
                        "status": "skipped",
                        "reason": "missing_required_files",
                    }
                )
                continue

            self.package_dir = package_dir
            self.dataset_path = dataset_path
            self.manifest_path = manifest_path
            self.review_path = review_path
            self.promotion_path = promotion_path
            self.handoff_path = handoff_path
            self.freeze_ready_manifest_path = freeze_ready_manifest_path
            self.freeze_dir = freeze_dir
            self.state1_freeze_path = state1_freeze_path
            self.frozen_manifest_path = frozen_manifest_path
            self.frozen_dataset_path = frozen_dataset_path

            manifest = read_json(manifest_path)
            candidates = read_jsonl(dataset_path)
            review = read_json(review_path)
            promotion = read_json(promotion_path)
            handoff = read_json(handoff_path)
            freeze_ready_manifest = read_json(freeze_ready_manifest_path)

            freeze_artifact, frozen_manifest = self._build_freeze_outputs(
                manifest=manifest,
                candidates=candidates,
                review=review,
                promotion=promotion,
                handoff=handoff,
                freeze_ready_manifest=freeze_ready_manifest,
            )

            approved = bool((freeze_artifact.get("decision") or {}).get("approved"))
            freeze_artifact["attempted_packages"] = attempted + [
                {
                    "package_dir": str(package_dir),
                    "status": "selected",
                    "reason": "first_freeze_candidate",
                }
            ]

            if approved or self.package_dir is not None:
                if not self.dry_run:
                    assert self.freeze_dir is not None
                    self.freeze_dir.mkdir(parents=True, exist_ok=True)

                    if self.dataset_path is not None and self.frozen_dataset_path is not None:
                        shutil.copyfile(self.dataset_path, self.frozen_dataset_path)

                    if self.state1_freeze_path is not None:
                        self.state1_freeze_path.write_text(
                            json.dumps(freeze_artifact, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        freeze_artifact["state1_freeze_path"] = str(self.state1_freeze_path)

                    if self.frozen_manifest_path is not None:
                        self.frozen_manifest_path.write_text(
                            json.dumps(frozen_manifest, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        freeze_artifact["frozen_manifest_path"] = str(self.frozen_manifest_path)

                    if self.frozen_dataset_path is not None:
                        freeze_artifact["frozen_dataset_path"] = str(self.frozen_dataset_path)

                freeze_artifact["frozen_manifest"] = frozen_manifest
                return freeze_artifact

            attempted.append(
                {
                    "package_dir": str(package_dir),
                    "status": "skipped",
                    "reason": "freeze_thresholds_not_met",
                }
            )

        raise FreezeError("No STATE_1 handoff package satisfied the configured freeze thresholds.")

    def _build_freeze_outputs(
        self,
        *,
        manifest: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
        review: Dict[str, Any],
        promotion: Dict[str, Any],
        handoff: Dict[str, Any],
        freeze_ready_manifest: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        candidate_count = len(candidates)

        review_metrics = review.get("review_metrics") or {}
        review_decision = review.get("decision") or {}

        promotion_decision = promotion.get("decision") or {}
        handoff_decision = handoff.get("decision") or {}

        freeze_posture = freeze_ready_manifest.get("freeze_posture") or {}
        review_approved = bool(review_decision.get("approved", False))
        promotion_approved = bool(promotion_decision.get("approved", False))
        handoff_approved = bool(handoff_decision.get("approved", False))
        freeze_ready = bool(freeze_posture.get("freeze_ready", False))

        routing_mismatch_count = int(review_metrics.get("routing_mismatch_count", 0))
        missing_content_count = int(review_metrics.get("missing_content_count", 0))
        review_ready_ratio = float(review_metrics.get("review_ready_ratio", 0.0))

        decision_reasons: List[str] = []
        approved = True

        if candidate_count < self.thresholds.min_candidates:
            approved = False
            decision_reasons.append(
                f"candidate_count_below_threshold:{candidate_count}<{self.thresholds.min_candidates}"
            )

        if self.thresholds.require_approved_review and not review_approved:
            approved = False
            decision_reasons.append("state2_review_not_approved")

        if self.thresholds.require_approved_promotion and not promotion_approved:
            approved = False
            decision_reasons.append("state2_promotion_not_approved")

        if self.thresholds.require_approved_handoff and not handoff_approved:
            approved = False
            decision_reasons.append("state1_handoff_not_approved")

        if self.thresholds.require_freeze_ready and not freeze_ready:
            approved = False
            decision_reasons.append("freeze_ready_manifest_not_approved")

        if routing_mismatch_count > self.thresholds.max_routing_mismatches:
            approved = False
            decision_reasons.append(
                f"routing_mismatch_count_above_threshold:{routing_mismatch_count}>{self.thresholds.max_routing_mismatches}"
            )

        if missing_content_count > self.thresholds.max_missing_content:
            approved = False
            decision_reasons.append(
                f"missing_content_count_above_threshold:{missing_content_count}>{self.thresholds.max_missing_content}"
            )

        if review_ready_ratio < 1.0:
            approved = False
            decision_reasons.append(
                f"review_ready_ratio_below_required:{review_ready_ratio:.4f}<1.0000"
            )

        if not decision_reasons:
            decision_reasons.append("all_state1_freeze_thresholds_passed")

        decision = "FREEZE_STATE1_PACKAGE" if approved else "HOLD_STATE1_PACKAGE"

        freeze_id = str(uuid4())
        frozen_manifest_id = str(uuid4())

        freeze_artifact = {
            "freeze_id": freeze_id,
            "freeze_timestamp": utc_now_iso(),
            "freeze_scope": "STATE_1",
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "promotion_path": str(self.promotion_path) if self.promotion_path else None,
            "handoff_path": str(self.handoff_path) if self.handoff_path else None,
            "freeze_ready_manifest_path": str(self.freeze_ready_manifest_path) if self.freeze_ready_manifest_path else None,
            "posture": {
                "access_mode": "ID_2",
                "non_authoritative": True,
                "governance_first": True,
                "automatic_registry_mutation": False,
            },
            "package_summary": {
                "dataset_version": str(manifest.get("dataset_version", "")),
                "candidate_count": candidate_count,
                "source_record_count": int(manifest.get("source_record_count", 0)),
                "target_model": manifest.get("target_model", {}),
                "routing_profile": manifest.get("routing_profile", {}),
            },
            "review_summary": {
                "review_id": str(review.get("review_id", "")),
                "review_approved": review_approved,
                "review_decision": str(review_decision.get("decision", "")),
            },
            "promotion_summary": {
                "promotion_id": str(promotion.get("promotion_id", "")),
                "promotion_approved": promotion_approved,
                "promotion_decision": str(promotion_decision.get("decision", "")),
            },
            "handoff_summary": {
                "handoff_id": str(handoff.get("handoff_id", "")),
                "handoff_approved": handoff_approved,
                "handoff_decision": str(handoff_decision.get("decision", "")),
            },
            "freeze_ready_summary": {
                "freeze_ready": freeze_ready,
                "state_target": str(freeze_posture.get("state_target", "")),
                "requires_explicit_freeze_step": bool(freeze_posture.get("requires_explicit_freeze_step", False)),
                "registry_update_pending": bool(freeze_posture.get("registry_update_pending", False)),
            },
            "thresholds": {
                "min_candidates": self.thresholds.min_candidates,
                "require_approved_review": self.thresholds.require_approved_review,
                "require_approved_promotion": self.thresholds.require_approved_promotion,
                "require_approved_handoff": self.thresholds.require_approved_handoff,
                "require_freeze_ready": self.thresholds.require_freeze_ready,
                "max_routing_mismatches": self.thresholds.max_routing_mismatches,
                "max_missing_content": self.thresholds.max_missing_content,
            },
            "freeze_metrics": {
                "candidate_count": candidate_count,
                "review_ready_ratio": round(review_ready_ratio, 4),
                "routing_mismatch_count": routing_mismatch_count,
                "missing_content_count": missing_content_count,
            },
            "decision": {
                "approved": approved,
                "decision": decision,
                "reasons": decision_reasons,
            },
            "notes": self.notes,
            "written": not self.dry_run,
        }

        frozen_manifest = {
            "frozen_manifest_id": frozen_manifest_id,
            "freeze_id": freeze_id,
            "frozen_timestamp": utc_now_iso(),
            "state": "STATE_1",
            "dataset_version": str(manifest.get("dataset_version", "")),
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "freeze_dir": str(self.freeze_dir) if self.freeze_dir else None,
            "source_dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "frozen_dataset_path": str(self.frozen_dataset_path) if self.frozen_dataset_path else None,
            "source_manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "promotion_path": str(self.promotion_path) if self.promotion_path else None,
            "handoff_path": str(self.handoff_path) if self.handoff_path else None,
            "freeze_ready_manifest_path": str(self.freeze_ready_manifest_path) if self.freeze_ready_manifest_path else None,
            "target_model": manifest.get("target_model", {}),
            "candidate_count": candidate_count,
            "source_record_count": int(manifest.get("source_record_count", 0)),
            "authorization_summary": manifest.get("authorization_summary", {}),
            "routing_profile": manifest.get("routing_profile", {}),
            "freeze_decision": {
                "approved": approved,
                "decision": decision,
                "reasons": decision_reasons,
            },
        }

        return freeze_artifact, frozen_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explicitly freeze a promotion-approved STATE_1 handoff package."
    )
    parser.add_argument(
        "--package-dir",
        required=False,
        help="Path to the dataset package directory containing all handoff and freeze-ready artifacts.",
    )
    parser.add_argument(
        "--latest-root",
        default=None,
        help="Root directory containing timestamped package directories. Newest freeze-eligible package is selected automatically.",
    )
    parser.add_argument(
        "--min-candidates",
        type=int,
        default=DEFAULT_MIN_CANDIDATES,
        help=f"Minimum candidate count required. Default: {DEFAULT_MIN_CANDIDATES}",
    )
    parser.add_argument(
        "--require-approved-review",
        action="store_true",
        default=DEFAULT_REQUIRE_APPROVED_REVIEW,
        help="Require the STATE_2 review artifact to be approved.",
    )
    parser.add_argument(
        "--require-approved-promotion",
        action="store_true",
        default=DEFAULT_REQUIRE_APPROVED_PROMOTION,
        help="Require the STATE_2 promotion artifact to be approved.",
    )
    parser.add_argument(
        "--require-approved-handoff",
        action="store_true",
        default=DEFAULT_REQUIRE_APPROVED_HANDOFF,
        help="Require the STATE_1 handoff artifact to be approved.",
    )
    parser.add_argument(
        "--require-freeze-ready",
        action="store_true",
        default=DEFAULT_REQUIRE_FREEZE_READY,
        help="Require freeze_ready_manifest.json to indicate freeze readiness.",
    )
    parser.add_argument(
        "--max-routing-mismatches",
        type=int,
        default=DEFAULT_MAX_ROUTING_MISMATCHES,
        help=f"Maximum routing mismatches allowed. Default: {DEFAULT_MAX_ROUTING_MISMATCHES}",
    )
    parser.add_argument(
        "--max-missing-content",
        type=int,
        default=DEFAULT_MAX_MISSING_CONTENT,
        help=f"Maximum missing-content candidates allowed. Default: {DEFAULT_MAX_MISSING_CONTENT}",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional freeze notes stored in the freeze artifact.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate the package and print the freeze artifact without writing files.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    freezer = State1Freezer(
        package_dir=Path(args.package_dir).expanduser().resolve() if args.package_dir else None,
        latest_root=Path(args.latest_root).expanduser().resolve() if args.latest_root else None,
        min_candidates=args.min_candidates,
        require_approved_review=args.require_approved_review,
        require_approved_promotion=args.require_approved_promotion,
        require_approved_handoff=args.require_approved_handoff,
        require_freeze_ready=args.require_freeze_ready,
        max_routing_mismatches=args.max_routing_mismatches,
        max_missing_content=args.max_missing_content,
        dry_run=args.dry_run,
        notes=args.notes,
    )

    try:
        result = freezer.run()
    except FreezeError as exc:
        sys.stderr.write(f"[STATE1 FREEZE FAILED] {exc}\n")
        return 1
    except RuntimeError as exc:
        sys.stderr.write(f"[STATE1 FREEZE FAILED] {exc}\n")
        return 1

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())