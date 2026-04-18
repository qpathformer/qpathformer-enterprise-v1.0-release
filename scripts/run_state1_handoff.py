#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10.3 STATE_1 Handoff Layer

Consumes a reviewed and promotion-approved STATE_2 package and emits a controlled
STATE_1 handoff artifact plus freeze-ready manifest.

Scope:
- load package manifest + dataset + state2 review + promotion decision
- verify promotion approval and package integrity
- emit state1 handoff artifact
- emit freeze-ready manifest
- preserve governance-first posture

Posture:
- ID_2 only
- non-authoritative
- no automatic freeze execution
- no automatic registry mutation
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


DEFAULT_MIN_CANDIDATES = 4
DEFAULT_REQUIRE_APPROVED_REVIEW = True
DEFAULT_REQUIRE_APPROVED_PROMOTION = True
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


def package_is_handoff_ready_structurally(package_dir: Path) -> bool:
    return (
        package_dir.exists()
        and (package_dir / "manifest.json").exists()
        and (package_dir / "dataset.jsonl").exists()
        and (package_dir / "state2_review.json").exists()
        and (package_dir / "state2_promotion_decision.json").exists()
    )


def list_candidate_package_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []

    def package_sort_key(package_dir: Path) -> tuple[float, float]:
        promotion_path = package_dir / "state2_promotion_decision.json"
        promotion_ts = 0.0

        if promotion_path.exists():
            try:
                payload = read_json(promotion_path)
                created_at = str(payload.get("promotion_timestamp") or "")
                if created_at.endswith("Z"):
                    created_at = created_at.replace("Z", "+00:00")
                if created_at:
                    promotion_ts = datetime.fromisoformat(created_at).timestamp()
            except Exception:
                promotion_ts = 0.0

        return (promotion_ts, package_dir.stat().st_mtime)

    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=package_sort_key, reverse=True)
    return dirs


@dataclass(frozen=True)
class HandoffThresholds:
    min_candidates: int = DEFAULT_MIN_CANDIDATES
    require_approved_review: bool = DEFAULT_REQUIRE_APPROVED_REVIEW
    require_approved_promotion: bool = DEFAULT_REQUIRE_APPROVED_PROMOTION
    max_routing_mismatches: int = DEFAULT_MAX_ROUTING_MISMATCHES
    max_missing_content: int = DEFAULT_MAX_MISSING_CONTENT


class HandoffError(RuntimeError):
    pass


class State1HandoffBuilder:
    def __init__(
        self,
        *,
        package_dir: Optional[Path],
        latest_root: Optional[Path],
        min_candidates: int,
        require_approved_review: bool,
        require_approved_promotion: bool,
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
        self.dry_run = dry_run
        self.notes = notes or ""

        self.thresholds = HandoffThresholds(
            min_candidates=min_candidates,
            require_approved_review=require_approved_review,
            require_approved_promotion=require_approved_promotion,
            max_routing_mismatches=max_routing_mismatches,
            max_missing_content=max_missing_content,
        )

    def run(self) -> Dict[str, Any]:
        candidate_dirs: List[Path]

        if self.package_dir is not None:
            candidate_dirs = [self.package_dir]
        else:
            if self.latest_root is None:
                raise HandoffError("Either --package-dir or --latest-root must be provided.")
            candidate_dirs = list_candidate_package_dirs(self.latest_root)

        if not candidate_dirs:
            raise HandoffError("No candidate package directories available for STATE_1 handoff.")

        attempted: List[Dict[str, str]] = []

        for package_dir in candidate_dirs:
            dataset_path = package_dir / "dataset.jsonl"
            manifest_path = package_dir / "manifest.json"
            review_path = package_dir / "state2_review.json"
            promotion_path = package_dir / "state2_promotion_decision.json"
            handoff_path = package_dir / "state1_handoff.json"
            freeze_ready_manifest_path = package_dir / "freeze_ready_manifest.json"

            if not package_is_handoff_ready_structurally(package_dir):
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

            manifest = read_json(manifest_path)
            candidates = read_jsonl(dataset_path)
            review = read_json(review_path)
            promotion = read_json(promotion_path)

            handoff_artifact, freeze_ready_manifest = self._build_handoff_outputs(
                manifest=manifest,
                candidates=candidates,
                review=review,
                promotion=promotion,
            )

            approved = bool((handoff_artifact.get("decision") or {}).get("approved"))
            handoff_artifact["attempted_packages"] = attempted + [
                {
                    "package_dir": str(package_dir),
                    "status": "selected",
                    "reason": "first_handoff_candidate",
                }
            ]

            if approved or self.package_dir is not None:
                if not self.dry_run:
                    if self.handoff_path is not None:
                        self.handoff_path.write_text(
                            json.dumps(handoff_artifact, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        handoff_artifact["handoff_path"] = str(self.handoff_path)

                    if self.freeze_ready_manifest_path is not None:
                        self.freeze_ready_manifest_path.write_text(
                            json.dumps(freeze_ready_manifest, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        handoff_artifact["freeze_ready_manifest_path"] = str(self.freeze_ready_manifest_path)

                handoff_artifact["freeze_ready_manifest"] = freeze_ready_manifest
                return handoff_artifact

            attempted.append(
                {
                    "package_dir": str(package_dir),
                    "status": "skipped",
                    "reason": "handoff_thresholds_not_met",
                }
            )

        raise HandoffError("No STATE_2 package satisfied the configured STATE_1 handoff thresholds.")

    def _build_handoff_outputs(
        self,
        *,
        manifest: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
        review: Dict[str, Any],
        promotion: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        candidate_count = len(candidates)

        review_metrics = review.get("review_metrics") or {}
        review_decision = review.get("decision") or {}
        review_exceptions = review.get("exceptions") or {}

        promotion_metrics = promotion.get("promotion_metrics") or {}
        promotion_decision = promotion.get("decision") or {}

        review_approved = bool(review_decision.get("approved", False))
        promotion_approved = bool(promotion_decision.get("approved", False))

        routing_mismatch_count = int(review_metrics.get("routing_mismatch_count", 0))
        missing_content_count = int(review_metrics.get("missing_content_count", 0))
        review_ready_ratio = float(promotion_metrics.get("review_ready_ratio", review_metrics.get("review_ready_ratio", 0.0)))

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
            decision_reasons.append("all_state1_handoff_thresholds_passed")

        decision = "APPROVE_STATE1_HANDOFF_PACKAGE" if approved else "HOLD_STATE2_PACKAGE_FOR_HANDOFF"

        handoff_id = str(uuid4())
        freeze_ready_manifest_id = str(uuid4())

        handoff_artifact = {
            "handoff_id": handoff_id,
            "handoff_timestamp": utc_now_iso(),
            "handoff_scope": "STATE_1",
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "promotion_path": str(self.promotion_path) if self.promotion_path else None,
            "posture": {
                "access_mode": "ID_2",
                "non_authoritative": True,
                "governance_first": True,
                "automatic_state1_freeze": False,
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
                "review_decision": str(review_decision.get("decision", "")),
                "review_approved": review_approved,
            },
            "promotion_summary": {
                "promotion_id": str(promotion.get("promotion_id", "")),
                "promotion_decision": str(promotion_decision.get("decision", "")),
                "promotion_approved": promotion_approved,
            },
            "thresholds": {
                "min_candidates": self.thresholds.min_candidates,
                "require_approved_review": self.thresholds.require_approved_review,
                "require_approved_promotion": self.thresholds.require_approved_promotion,
                "max_routing_mismatches": self.thresholds.max_routing_mismatches,
                "max_missing_content": self.thresholds.max_missing_content,
            },
            "handoff_metrics": {
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
            "exceptions": {
                "routing_mismatches": review_exceptions.get("routing_mismatches", []),
                "missing_content_candidate_ids": review_exceptions.get("missing_content_candidate_ids", []),
            },
            "notes": self.notes,
            "written": not self.dry_run,
        }

        freeze_ready_manifest = {
            "freeze_ready_manifest_id": freeze_ready_manifest_id,
            "freeze_ready_timestamp": utc_now_iso(),
            "handoff_id": handoff_id,
            "dataset_version": str(manifest.get("dataset_version", "")),
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "promotion_path": str(self.promotion_path) if self.promotion_path else None,
            "freeze_posture": {
                "state_target": "STATE_1",
                "freeze_ready": approved,
                "requires_explicit_freeze_step": True,
                "registry_update_pending": approved,
            },
            "authorization_summary": manifest.get("authorization_summary", {}),
            "routing_profile": manifest.get("routing_profile", {}),
            "handoff_decision": {
                "approved": approved,
                "decision": decision,
                "reasons": decision_reasons,
            },
        }

        return handoff_artifact, freeze_ready_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a promotion-approved STATE_2 package for controlled STATE_1 handoff."
    )
    parser.add_argument(
        "--package-dir",
        required=False,
        help="Path to the dataset package directory containing dataset.jsonl, manifest.json, state2_review.json, and state2_promotion_decision.json.",
    )
    parser.add_argument(
        "--latest-root",
        default=None,
        help="Root directory containing timestamped package directories. Newest handoff-eligible package is selected automatically.",
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
        help="Require the STATE_2 promotion decision to be approved.",
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
        help="Optional handoff notes stored in the handoff artifact.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate the package and print the STATE_1 handoff artifact without writing files.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    builder = State1HandoffBuilder(
        package_dir=Path(args.package_dir).expanduser().resolve() if args.package_dir else None,
        latest_root=Path(args.latest_root).expanduser().resolve() if args.latest_root else None,
        min_candidates=args.min_candidates,
        require_approved_review=args.require_approved_review,
        require_approved_promotion=args.require_approved_promotion,
        max_routing_mismatches=args.max_routing_mismatches,
        max_missing_content=args.max_missing_content,
        dry_run=args.dry_run,
        notes=args.notes,
    )

    try:
        result = builder.run()
    except HandoffError as exc:
        sys.stderr.write(f"[STATE1 HANDOFF FAILED] {exc}\n")
        return 1
    except RuntimeError as exc:
        sys.stderr.write(f"[STATE1 HANDOFF FAILED] {exc}\n")
        return 1

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())