#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10.2 STATE_2 Promotion Layer

Evaluates a reviewed STATE_2 package and emits a promotion decision artifact for
controlled STATE_2 -> STATE_1 eligibility assessment.

Scope:
- load package manifest + dataset + state2 review artifact
- apply deterministic promotion thresholds
- emit promotion decision artifact
- preserve governance-first posture

Posture:
- ID_2 only
- non-authoritative
- promotion eligibility only
- no automatic STATE_1 mutation
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
DEFAULT_MIN_REVIEW_READY_RATIO = 1.0
DEFAULT_REQUIRE_APPROVED_REVIEW = True
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


def package_is_promotion_ready_structurally(package_dir: Path) -> bool:
    return (
        package_dir.exists()
        and (package_dir / "manifest.json").exists()
        and (package_dir / "dataset.jsonl").exists()
        and (package_dir / "state2_review.json").exists()
    )


def list_candidate_package_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []

    def package_sort_key(package_dir: Path) -> tuple[float, float]:
        review_path = package_dir / "state2_review.json"
        review_ts = 0.0

        if review_path.exists():
            try:
                review = read_json(review_path)
                created_at = str(review.get("review_timestamp") or "")
                if created_at.endswith("Z"):
                    created_at = created_at.replace("Z", "+00:00")
                if created_at:
                    review_ts = datetime.fromisoformat(created_at).timestamp()
            except Exception:
                review_ts = 0.0

        return (review_ts, package_dir.stat().st_mtime)

    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=package_sort_key, reverse=True)
    return dirs


@dataclass(frozen=True)
class PromotionThresholds:
    min_candidates: int = DEFAULT_MIN_CANDIDATES
    min_review_ready_ratio: float = DEFAULT_MIN_REVIEW_READY_RATIO
    require_approved_review: bool = DEFAULT_REQUIRE_APPROVED_REVIEW
    max_routing_mismatches: int = DEFAULT_MAX_ROUTING_MISMATCHES
    max_missing_content: int = DEFAULT_MAX_MISSING_CONTENT


class PromotionError(RuntimeError):
    pass


class State2PromotionEvaluator:
    def __init__(
        self,
        *,
        package_dir: Optional[Path],
        latest_root: Optional[Path],
        min_candidates: int,
        min_review_ready_ratio: float,
        require_approved_review: bool,
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
        self.dry_run = dry_run
        self.notes = notes or ""

        self.thresholds = PromotionThresholds(
            min_candidates=min_candidates,
            min_review_ready_ratio=min_review_ready_ratio,
            require_approved_review=require_approved_review,
            max_routing_mismatches=max_routing_mismatches,
            max_missing_content=max_missing_content,
        )

    def run(self) -> Dict[str, Any]:
        candidate_dirs: List[Path]

        if self.package_dir is not None:
            candidate_dirs = [self.package_dir]
        else:
            if self.latest_root is None:
                raise PromotionError("Either --package-dir or --latest-root must be provided.")
            candidate_dirs = list_candidate_package_dirs(self.latest_root)

        if not candidate_dirs:
            raise PromotionError("No candidate package directories available for promotion evaluation.")

        attempted: List[Dict[str, str]] = []

        for package_dir in candidate_dirs:
            dataset_path = package_dir / "dataset.jsonl"
            manifest_path = package_dir / "manifest.json"
            review_path = package_dir / "state2_review.json"
            promotion_path = package_dir / "state2_promotion_decision.json"

            if not package_is_promotion_ready_structurally(package_dir):
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

            manifest = read_json(manifest_path)
            candidates = read_jsonl(dataset_path)
            review = read_json(review_path)

            promotion_artifact = self._build_promotion_artifact(
                manifest=manifest,
                candidates=candidates,
                review=review,
            )

            approved = bool((promotion_artifact.get("decision") or {}).get("approved"))
            promotion_artifact["attempted_packages"] = attempted + [
                {
                    "package_dir": str(package_dir),
                    "status": "selected" if approved or self.package_dir is not None else "evaluated",
                    "reason": "first_promotion_candidate",
                }
            ]

            if approved or self.package_dir is not None:
                if not self.dry_run and self.promotion_path is not None:
                    self.promotion_path.write_text(
                        json.dumps(promotion_artifact, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    promotion_artifact["promotion_path"] = str(self.promotion_path)

                return promotion_artifact

            attempted.append(
                {
                    "package_dir": str(package_dir),
                    "status": "skipped",
                    "reason": "promotion_thresholds_not_met",
                }
            )

        raise PromotionError("No STATE_2 package satisfied the configured promotion thresholds.")

    def _build_promotion_artifact(
        self,
        *,
        manifest: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
        review: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidate_count = len(candidates)

        review_metrics = review.get("review_metrics") or {}
        decision_block = review.get("decision") or {}
        exceptions = review.get("exceptions") or {}

        review_ready_count = int(review_metrics.get("review_ready_count", 0))
        review_ready_ratio = float(review_metrics.get("review_ready_ratio", 0.0))
        routing_mismatch_count = int(review_metrics.get("routing_mismatch_count", 0))
        missing_content_count = int(review_metrics.get("missing_content_count", 0))
        review_approved = bool(decision_block.get("approved", False))

        decision_reasons: List[str] = []
        approved = True

        if candidate_count < self.thresholds.min_candidates:
            approved = False
            decision_reasons.append(
                f"candidate_count_below_threshold:{candidate_count}<{self.thresholds.min_candidates}"
            )

        if review_ready_ratio < self.thresholds.min_review_ready_ratio:
            approved = False
            decision_reasons.append(
                f"review_ready_ratio_below_threshold:{review_ready_ratio:.4f}<{self.thresholds.min_review_ready_ratio:.4f}"
            )

        if self.thresholds.require_approved_review and not review_approved:
            approved = False
            decision_reasons.append("state2_review_not_approved")

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

        if not decision_reasons:
            decision_reasons.append("all_state2_promotion_thresholds_passed")

        decision = "APPROVE_STATE1_PROMOTION_CANDIDATE" if approved else "HOLD_STATE2_PACKAGE"

        artifact = {
            "promotion_id": str(uuid4()),
            "promotion_timestamp": utc_now_iso(),
            "promotion_scope": "STATE_2_TO_STATE_1",
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "posture": {
                "access_mode": "ID_2",
                "non_authoritative": True,
                "governance_first": True,
                "automatic_state1_mutation": False,
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
                "review_timestamp": str(review.get("review_timestamp", "")),
                "review_decision": str(decision_block.get("decision", "")),
                "review_approved": review_approved,
            },
            "thresholds": {
                "min_candidates": self.thresholds.min_candidates,
                "min_review_ready_ratio": self.thresholds.min_review_ready_ratio,
                "require_approved_review": self.thresholds.require_approved_review,
                "max_routing_mismatches": self.thresholds.max_routing_mismatches,
                "max_missing_content": self.thresholds.max_missing_content,
            },
            "promotion_metrics": {
                "candidate_count": candidate_count,
                "review_ready_count": review_ready_count,
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
                "routing_mismatches": exceptions.get("routing_mismatches", []),
                "missing_content_candidate_ids": exceptions.get("missing_content_candidate_ids", []),
            },
            "notes": self.notes,
            "written": not self.dry_run,
        }

        return artifact


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a reviewed STATE_2 package for controlled STATE_2 -> STATE_1 promotion eligibility."
    )
    parser.add_argument(
        "--package-dir",
        required=False,
        help="Path to the dataset package directory containing dataset.jsonl, manifest.json, and state2_review.json.",
    )
    parser.add_argument(
        "--latest-root",
        default=None,
        help="Root directory containing timestamped package directories. Newest promotion-eligible package is selected automatically.",
    )
    parser.add_argument(
        "--min-candidates",
        type=int,
        default=DEFAULT_MIN_CANDIDATES,
        help=f"Minimum candidate count required. Default: {DEFAULT_MIN_CANDIDATES}",
    )
    parser.add_argument(
        "--min-review-ready-ratio",
        type=float,
        default=DEFAULT_MIN_REVIEW_READY_RATIO,
        help=f"Minimum review-ready ratio required. Default: {DEFAULT_MIN_REVIEW_READY_RATIO}",
    )
    parser.add_argument(
        "--require-approved-review",
        action="store_true",
        default=DEFAULT_REQUIRE_APPROVED_REVIEW,
        help="Require the STATE_2 review artifact to be approved.",
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
        help="Optional promotion notes stored in the promotion artifact.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate the package and print the promotion decision without writing state2_promotion_decision.json.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    evaluator = State2PromotionEvaluator(
        package_dir=Path(args.package_dir).expanduser().resolve() if args.package_dir else None,
        latest_root=Path(args.latest_root).expanduser().resolve() if args.latest_root else None,
        min_candidates=args.min_candidates,
        min_review_ready_ratio=args.min_review_ready_ratio,
        require_approved_review=args.require_approved_review,
        max_routing_mismatches=args.max_routing_mismatches,
        max_missing_content=args.max_missing_content,
        dry_run=args.dry_run,
        notes=args.notes,
    )

    try:
        result = evaluator.run()
    except PromotionError as exc:
        sys.stderr.write(f"[STATE2 PROMOTION FAILED] {exc}\n")
        return 1
    except RuntimeError as exc:
        sys.stderr.write(f"[STATE2 PROMOTION FAILED] {exc}\n")
        return 1

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())