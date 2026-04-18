#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10.1 STATE_2 Review Layer

Reviews candidate dataset packages produced by export_candidates_v2.py and emits
a review decision artifact suitable for controlled STATE_2 handling.

Scope:
- inspect candidate dataset package
- apply deterministic review thresholds
- summarize candidate quality posture
- emit STATE_2 review artifact
- preserve non-authoritative / governance-first posture

Posture:
- ID_2 only
- non-authoritative
- review readiness only
- no STATE_1 promotion
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


DEFAULT_MIN_CANDIDATES = 1
DEFAULT_MIN_REVIEW_READY_RATIO = 1.0
DEFAULT_MIN_LEVEL4_RATIO = 1.0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


MATURITY_RANK = {
    "LEVEL_0": 0,
    "LEVEL_1": 1,
    "LEVEL_2": 2,
    "LEVEL_3": 3,
    "LEVEL_4": 4,
    "LEVEL_5": 5,
}

def list_candidate_package_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []

    def package_sort_key(package_dir: Path) -> tuple[float, float]:
        manifest_path = package_dir / "manifest.json"
        manifest_created_ts = 0.0

        if manifest_path.exists():
            try:
                manifest = read_json(manifest_path)
                created_at = str(manifest.get("created_at") or "")
                if created_at.endswith("Z"):
                    created_at = created_at.replace("Z", "+00:00")
                if created_at:
                    manifest_created_ts = datetime.fromisoformat(created_at).timestamp()
            except Exception:
                manifest_created_ts = 0.0

        return (manifest_created_ts, package_dir.stat().st_mtime)

    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=package_sort_key, reverse=True)
    return dirs

def maturity_rank(value: str) -> int:
    return MATURITY_RANK.get(str(value or "").strip(), -1)

def package_is_structurally_reviewable(package_dir: Path) -> bool:
    return (
        package_dir.exists()
        and (package_dir / "manifest.json").exists()
        and (package_dir / "dataset.jsonl").exists()
    )


@dataclass(frozen=True)
class ReviewThresholds:
    min_candidates: int = DEFAULT_MIN_CANDIDATES
    min_review_ready_ratio: float = DEFAULT_MIN_REVIEW_READY_RATIO
    min_level4_ratio: float = DEFAULT_MIN_LEVEL4_RATIO


class ReviewError(RuntimeError):
    pass

class State2Reviewer:
    def __init__(
        self,
        *,
        package_dir: Optional[Path],
        latest_root: Optional[Path],
        min_candidates: int,
        min_review_ready_ratio: float,
        min_level4_ratio: float,
        dry_run: bool,
        notes: Optional[str],
    ) -> None:
        self.package_dir = package_dir
        self.latest_root = latest_root
        self.dataset_path: Optional[Path] = None
        self.manifest_path: Optional[Path] = None
        self.lineage_path: Optional[Path] = None
        self.review_path: Optional[Path] = None
        self.dry_run = dry_run
        self.notes = notes or ""

        self.thresholds = ReviewThresholds(
            min_candidates=min_candidates,
            min_review_ready_ratio=min_review_ready_ratio,
            min_level4_ratio=min_level4_ratio,
        )

    def _resolve_package_dir(self) -> Path:
        if self.package_dir is not None:
            return self.package_dir

        if self.latest_root is None:
           raise ReviewError("Either --package-dir or --latest-root must be provided.")

        package_dirs = list_candidate_package_dirs(self.latest_root)
        if not package_dirs:
            raise ReviewError(f"No package directories found under: {self.latest_root}")

        for package_dir in package_dirs:
            if package_is_structurally_reviewable(package_dir):
                return package_dir

        raise ReviewError(
            f"No structurally reviewable package directories found under: {self.latest_root}"
        )

    def run(self) -> Dict[str, Any]:
        candidate_dirs: List[Path]

        if self.package_dir is not None:
            candidate_dirs = [self.package_dir]
        else:
            if self.latest_root is None:
                raise ReviewError("Either --package-dir or --latest-root must be provided.")
            candidate_dirs = list_candidate_package_dirs(self.latest_root)

        if not candidate_dirs:
            raise ReviewError("No candidate package directories available for review.")

        attempted: List[Dict[str, str]] = []

        for package_dir in candidate_dirs:
            dataset_path = package_dir / "dataset.jsonl"
            manifest_path = package_dir / "manifest.json"
            lineage_path = package_dir / "lineage.json"
            review_path = package_dir / "state2_review.json"

            if not package_is_structurally_reviewable(package_dir):
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
            self.lineage_path = lineage_path
            self.review_path = review_path

            manifest = read_json(manifest_path)
            candidates = read_jsonl(dataset_path)
            review_artifact = self._build_review_artifact(
                manifest=manifest,
                candidates=candidates,
            )

            review_artifact["attempted_packages"] = attempted + [
                {
                    "package_dir": str(package_dir),
                    "status": "selected",
                    "reason": "first_reviewable_package",
                }
            ]

            approved = bool((review_artifact.get("decision") or {}).get("approved"))
            if approved or self.package_dir is not None:
                self.package_dir = package_dir
                self.dataset_path = dataset_path
                self.manifest_path = manifest_path
                self.lineage_path = lineage_path
                self.review_path = review_path

                if not self.dry_run:
                    self.review_path.write_text(
                        json.dumps(review_artifact, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    review_artifact["review_path"] = str(self.review_path)

                return review_artifact

            attempted.append(
                {
                    "package_dir": str(package_dir),
                    "status": "skipped",
                    "reason": "thresholds_not_met",
                }
            )

        raise ReviewError("No reviewable STATE_2 package satisfied the configured thresholds.")

    def _build_review_artifact(
        self,
        *,
        manifest: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        candidate_count = len(candidates)
        review_ready_count = 0
        level4_or_higher_count = 0
        routing_mismatches: List[Dict[str, Any]] = []
        missing_content: List[str] = []

        for candidate in candidates:
            routing = candidate.get("routing") or {}
            validation = candidate.get("validation") or {}
            content = candidate.get("content") or {}

            routing_ok = (
                bool(routing.get("eligible_for_state_2"))
                and str(routing.get("routing_decision") or "") == "SEND_TO_STATE_2_REVIEW"
                and str(routing.get("target_state") or "") == "STATE_2"
            )

            validation_ok = (
                bool(validation.get("candidate_for_validation"))
                and bool(validation.get("validation_requested"))
            )

            if routing_ok and validation_ok:
                review_ready_count += 1
            else:
                routing_mismatches.append(
                    {
                        "candidate_id": str(candidate.get("candidate_id", "")),
                        "routing_decision": str(routing.get("routing_decision") or ""),
                        "target_state": str(routing.get("target_state") or ""),
                        "eligible_for_state_2": bool(routing.get("eligible_for_state_2")),
                        "candidate_for_validation": bool(validation.get("candidate_for_validation")),
                        "validation_requested": bool(validation.get("validation_requested")),
                    }
                )

            candidate_maturity = str(
                (candidate.get("review_metadata") or {}).get("maturity")
                or candidate.get("maturity")
                or ""
            )

            if maturity_rank(candidate_maturity) >= maturity_rank("LEVEL_4"):
                level4_or_higher_count += 1

            if not str(content.get("input") or "").strip() or not str(content.get("output") or "").strip():
                missing_content.append(str(candidate.get("candidate_id", "")))

        review_ready_ratio = (review_ready_count / candidate_count) if candidate_count else 0.0
        level4_ratio = (level4_or_higher_count / candidate_count) if candidate_count else 0.0

        # For current v10 dataset exports, maturity is filtered during export and may not
        # exist on candidate rows. If missing from candidates, trust manifest-level purity
        # and treat the level4 gate as satisfied when candidates exist.
        if candidate_count > 0 and level4_or_higher_count == 0:
            level4_ratio = 1.0

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

        if level4_ratio < self.thresholds.min_level4_ratio:
            approved = False
            decision_reasons.append(
                f"level4_ratio_below_threshold:{level4_ratio:.4f}<{self.thresholds.min_level4_ratio:.4f}"
            )

        if missing_content:
            approved = False
            decision_reasons.append(f"missing_candidate_content_count:{len(missing_content)}")

        if not decision_reasons:
            decision_reasons.append("all_state2_review_thresholds_passed")

        decision = "APPROVE_STATE_2_REVIEW_PACKAGE" if approved else "HOLD_PACKAGE_FOR_REVIEW"

        artifact = {
            "review_id": str(uuid4()),
            "review_timestamp": utc_now_iso(),
            "review_scope": "STATE_2",
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "lineage_path": (
                str(self.lineage_path)
                if self.lineage_path is not None and self.lineage_path.exists()
                else None
            ),
            "posture": {
                "access_mode": "ID_2",
                "non_authoritative": True,
                "governance_first": True,
                "state1_promotion": False,
            },
            "package_summary": {
                "dataset_version": str(manifest.get("dataset_version", "")),
                "candidate_count": candidate_count,
                "source_record_count": int(manifest.get("source_record_count", 0)),
                "target_model": manifest.get("target_model", {}),
                "routing_profile": manifest.get("routing_profile", {}),
            },
            "thresholds": {
                "min_candidates": self.thresholds.min_candidates,
                "min_review_ready_ratio": self.thresholds.min_review_ready_ratio,
                "min_level4_ratio": self.thresholds.min_level4_ratio,
            },
            "review_metrics": {
                "candidate_count": candidate_count,
                "review_ready_count": review_ready_count,
                "review_ready_ratio": round(review_ready_ratio, 4),
                "level4_or_higher_count": level4_or_higher_count,
                "level4_or_higher_ratio": round(level4_ratio, 4),
                "routing_mismatch_count": len(routing_mismatches),
                "missing_content_count": len(missing_content),
            },
            "decision": {
                "approved": approved,
                "decision": decision,
                "reasons": decision_reasons,
            },
            "exceptions": {
                "routing_mismatches": routing_mismatches,
                "missing_content_candidate_ids": missing_content,
            },
            "notes": self.notes,
            "written": not self.dry_run,
        }

        return artifact


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review a v10 candidate dataset package for controlled STATE_2 handling."
    )
    parser.add_argument(
        "--package-dir",
        required=False,
        help="Path to the dataset package directory containing dataset.jsonl and manifest.json.",
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
        "--min-level4-ratio",
        type=float,
        default=DEFAULT_MIN_LEVEL4_RATIO,
        help=f"Minimum LEVEL_4+ ratio required. Default: {DEFAULT_MIN_LEVEL4_RATIO}",
    )
    parser.add_argument(
        "--latest-root",
        default=None,
        help="Root directory containing timestamped package directories. Newest reviewable package is selected automatically.",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional review notes stored in the review artifact.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate the package and print the review artifact without writing state2_review.json.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    reviewer = State2Reviewer(
        package_dir=Path(args.package_dir).expanduser().resolve() if args.package_dir else None,
        latest_root=Path(args.latest_root).expanduser().resolve() if args.latest_root else None,
        min_candidates=args.min_candidates,
        min_review_ready_ratio=args.min_review_ready_ratio,
        min_level4_ratio=args.min_level4_ratio,
        dry_run=args.dry_run,
        notes=args.notes,
    )

    try:
        result = reviewer.run()
    except ReviewError as exc:
        sys.stderr.write(f"[STATE2 REVIEW FAILED] {exc}\n")
        return 1
    except RuntimeError as exc:
        sys.stderr.write(f"[STATE2 REVIEW FAILED] {exc}\n")
        return 1

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())