#!/usr/bin/env python3
"""
Q-Pathformer DEV — Option B Dataset Pipeline Scaling

Builds versioned dataset candidate exports from validated ID_2 signal artifacts.

Scope:
- multi-signal ingestion
- grouping by model.version and session_id
- candidate extraction
- deduplication
- dataset manifest generation
- versioned dataset outputs

Posture:
- ID_2 only
- non-authoritative
- no ID_3 logic
- governance-first preserved

Expected input:
Signal artifacts compatible with the Module 02 / Module 04 / Module 05 posture.
The script is intentionally defensive and tolerates partially populated records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4
from jsonschema import Draft202012Validator

from path_layout import PATH2_ROOT


DEFAULT_EXPORT_SCOPE = "candidate_export"
DEFAULT_SCHEMA_VERSION = "candidate_dataset_manifest_v0.1"
DEFAULT_DATASET_KIND = "enterprise_structuring"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASETS_ROOT = PATH2_ROOT
DEFAULT_CANDIDATES_DIRNAME = str(Path("03_dataset") / "candidates")
DEFAULT_LOGS_DIRNAME = str(Path("07_logs"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "unknown"


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


MATURITY_RANK = {
    "LEVEL_0": 0,
    "LEVEL_1": 1,
    "LEVEL_2": 2,
    "LEVEL_3": 3,
    "LEVEL_4": 4,
    "LEVEL_5": 5,
}


def maturity_rank(value: str) -> int:
    return MATURITY_RANK.get(str(value or "").strip(), -1)
def normalize_llm_signal(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize raw enum-locked LLM JSON into a minimal v0.2-dev signal-compatible record.

    This path is only for raw contract JSON that does not already carry runtime
    validation/routing fields. It preserves STATE_3 posture and does not force
    STATE_2 review readiness.
    """

    if "role" not in record:
        return record  # not raw LLM contract JSON

    primary_function = str(record.get("primary_function", "") or "").strip().rstrip(". ")
    evaluation_focus = record.get("evaluation_focus", []) or []
    focus_text = ", ".join(str(item).strip() for item in evaluation_focus if str(item).strip())

    structured_summary = (
        f"{primary_function}. Evaluation focus: {focus_text}. "
        f"Lifecycle entry remains STATE_3 under provisional runtime containment."
        if focus_text
        else f"{primary_function}. Lifecycle entry remains STATE_3 under provisional runtime containment."
    )

    tags = ["llm_generated", "enum_locked", "normalized_by_exporter"]
    for value in record.get("governance_flags", []) or []:
        normalized = str(value).strip().lower()
        if normalized:
            tags.append(normalized)
    for value in evaluation_focus:
        normalized = str(value).strip().lower().replace(" ", "_")
        if normalized:
            tags.append(normalized)

    deduped_tags: List[str] = []
    seen_tags = set()
    for tag in tags:
        if tag not in seen_tags:
            deduped_tags.append(tag)
            seen_tags.add(tag)

    return {
        "signal_id": record.get("signal_id") or str(uuid4()),
        "timestamp": record.get("timestamp") or utc_now_iso(),
        "access_mode_primary": "ID_2",
        "schema_version": "v0.2-dev",
        "interaction_type": "enterprise_only",
        "session_id": record.get("session_id", "llm-runtime-session"),
        "model": {
            "model_id": "gpt-oss:20b",
            "parameter_class": "20B",
            "role": "enterprise",
            "endpoint_type": "local",
            "invocation_reason": "runtime_structuring",
            "version": record.get("model_version") or "v10-normalized-export-bridge",
        },
        "input": {
            "prompt": primary_function,
        },
        "signal": {
            "raw_output": json.dumps(record, ensure_ascii=False),
            "structured_summary": structured_summary,
            "tags": deduped_tags,
        },
        "metrics": {
            "coherence": 0.0,
            "novelty": 0.0,
            "stability": 0.0,
            "ambiguity": 1.0,
        },
        "maturity": "LEVEL_0",
        "governance_flags": {
            "provisional": True,
            "context_bound": True,
            "requires_validation": True,
            "promotion_blocked": True,
        },
        "authorization": {
            "state2_candidate_allowed": False,
            "fine_tuning_allowed": False,
            "human_review_required": True,
        },
        "validation": {
            "candidate_for_validation": False,
            "validation_requested": False,
            "validation_reasons": ["normalized_raw_llm_record_requires_runtime_validation"],
            "validation_engine_version": "exporter_fallback_v1",
        },
        "lifecycle": {
            "state": "STATE_3",
            "eligible_for_state_2": False,
            "routing_decision": "HOLD_IN_STATE_3",
            "target_state": "STATE_3",
            "routing_reasons": ["normalized_raw_llm_record_not_runtime_routed"],
        },
    }

@dataclass
class CandidateExtractionResult:
    candidate: Optional[Dict[str, Any]]
    exclusion_reason: Optional[str] = None


class ExportError(RuntimeError):
    pass


class CandidateExporter:
    def __init__(
        self,
        *,
        input_paths: Sequence[Path],
        output_root: Path,
        dataset_kind: str,
        export_scope: str,
        allow_state2_only: bool,
        require_validation: bool,
        require_routing_review: bool,
        min_maturity: Optional[str],
        dedup_mode: str,
        version_tag: Optional[str],
        dry_run: bool,
        candidate_schema_path: Optional[Path],
        manifest_schema_path: Optional[Path],
        dataset_passport_path: Optional[Path] = None,
    ) -> None:
        self.input_paths = list(input_paths)
        self.output_root = output_root
        self.candidates_root = self.output_root / DEFAULT_CANDIDATES_DIRNAME
        self.logs_root = self.output_root / DEFAULT_LOGS_DIRNAME
        self.dataset_kind = dataset_kind
        self.require_routing_review = require_routing_review
        self.min_maturity = min_maturity
        self.export_scope = export_scope
        self.allow_state2_only = allow_state2_only
        self.require_validation = require_validation
        self.dedup_mode = dedup_mode
        self.version_tag = version_tag
        self.dry_run = dry_run

        self.ingestion_errors: List[Dict[str, str]] = []
        self.excluded_records: List[Dict[str, str]] = []
        self.dedup_events: List[Dict[str, str]] = []
        self.log_entries: List[Dict[str, Any]] = []

        self.candidate_schema_path = candidate_schema_path
        self.manifest_schema_path = manifest_schema_path
        self.dataset_passport_path = dataset_passport_path
        self.dataset_passport_id = self._load_dataset_passport_id(dataset_passport_path)

        self.candidate_validator = self._load_validator(candidate_schema_path)
        self.manifest_validator = self._load_validator(manifest_schema_path)

    def _load_dataset_passport_id(self, path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None

        payload = read_json(path)
        dataset_passport_id = payload.get("dataset_passport_id")

        if dataset_passport_id is None:
            raise ExportError(
                f"Dataset passport missing required field 'dataset_passport_id': {path}"
            )

        if not isinstance(dataset_passport_id, str) or not dataset_passport_id.strip():
            raise ExportError(
                f"Dataset passport field 'dataset_passport_id' must be a non-empty string: {path}"
            )

        return dataset_passport_id.strip()

    def _build_lineage_record(
        self,
        *,
        dataset_kind: str,
        source_records: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        source_signal_id = source_records[0].get("signal_id", "unknown") if source_records else "unknown"

        return {
            "transformation_id": str(uuid4()),
            "source_signal_id": str(source_signal_id),
            "dataset_id": self.dataset_passport_id,
            "transformation_type": dataset_kind,
            "performed_by": "export_candidates_v2.py",
            "timestamp": utc_now_iso(),
            "notes": "Grouped ID_2 candidate export with manifest-bound dataset emission.",
            "lineage_assertions": {
                "informative_only": True,
                "non_authoritative": True,
                "preserves_provenance": True,
                "non_certifying": True,
            },
        }

    def run(self) -> Dict[str, Any]:
        records = self._ingest_records()
        grouped = self._group_records(records)
        manifests: List[Dict[str, Any]] = []

        for group_key, group_records in grouped.items():
            manifest = self._build_group_export(group_key, group_records)
            if manifest is not None:
                manifests.append(manifest)

        run_summary = {
            "run_id": str(uuid4()),
            "total_written_candidates": sum(
                int(m.get("candidate_count", 0)) for m in manifests if m
            ),
            "total_extracted_candidates": sum(
                int(m.get("extracted_candidate_count", 0)) for m in manifests if m
            ),
            "generated_at_utc": utc_now_iso(),
            "posture": {
                "access_mode": "ID_2",
                "non_authoritative": True,
                "governance_first": True,
                "id3_logic_present": False,
                "authority_claims": False,
            },
            "inputs": [str(p) for p in self.input_paths],
            "dataset_kind": self.dataset_kind,
            "export_scope": self.export_scope,
            "allow_state2_only": self.allow_state2_only,
            "require_validation": self.require_validation,
            "require_routing_review": self.require_routing_review,
            "min_maturity": self.min_maturity,
            "dedup_mode": self.dedup_mode,
            "groups_emitted": len(manifests),
            "ingestion_errors": self.ingestion_errors,
            "excluded_records": self.excluded_records,
            "dedup_events": self.dedup_events,
            "log_entries": self.log_entries,
            "manifests": manifests,
        }

        summary_path = self.logs_root / f"candidate_export_run_{self._timestamp_token()}.json"
        if not self.dry_run:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8")
            run_summary["summary_path"] = str(summary_path)

        return run_summary

    def _timestamp_token(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _load_validator(self, schema_path: Optional[Path]) -> Optional[Draft202012Validator]:
        if schema_path is None:
            return None
        schema = read_json(schema_path)
        return Draft202012Validator(schema)
  
    def _validate_or_raise(
        self,
        *,
        validator: Optional[Draft202012Validator],
        payload: Dict[str, Any],
        payload_name: str,
    ) -> None:
        if validator is None:
            return

        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        if not errors:
            return

        lines = []
        for err in errors:
            path = ".".join(str(p) for p in err.path) or "<root>"
            lines.append(f"{payload_name}: {path}: {err.message}")

        raise ExportError("Schema validation failed:\n" + "\n".join(lines))

    def _iter_candidate_files(self, base_path: Path) -> Iterable[Path]:
        if base_path.is_file() and base_path.suffix.lower() == ".json":
            yield base_path
            return
        if base_path.is_dir():
            for path in sorted(base_path.rglob("*.json")):
                if path.is_file():
                    yield path

    def _is_candidate_like_record(self, record: Dict[str, Any]) -> bool:
        if record.get("schema_version") == "v0.2-dev" and "signal" in record and "input" in record:
            return True

        if "llm_generated" in (((record.get("signal") or {}).get("tags")) or []):
            return True

        return False

    def _ingest_records(self) -> List[Dict[str, Any]]:
        seen_paths: set[str] = set()
        records: List[Dict[str, Any]] = []

        for input_path in self.input_paths:
            for file_path in self._iter_candidate_files(input_path):
                resolved = str(file_path.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)

                try:
                    original_payload = read_json(file_path)
                    normalized_from_llm = "role" in original_payload

                    payload = normalize_llm_signal(original_payload)
                    payload["__source_path"] = resolved

                    if not self._is_candidate_like_record(payload):
                        self.log_entries.append(
                            {
                                "source_path": resolved,
                                "status": "ignored_non_candidate_record",
                                "normalized_from_llm": normalized_from_llm,
                                "timestamp": utc_now_iso(),
                            }
                        )
                        continue

                    records.append(payload)

                    self.log_entries.append(
                        {
                            "source_path": resolved,
                            "signal_id": str(payload.get("signal_id", "")),
                            "session_id": str(payload.get("session_id", "")),
                            "status": "ingested",
                            "normalized_from_llm": normalized_from_llm,
                            "model_version": str(self._get_model_version(payload)),
                            "timestamp": utc_now_iso(),
                        }
                    )

                except Exception as exc:  # pragma: no cover - defensive surface
                    self.ingestion_errors.append(
                        {
                            "path": resolved,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    self.log_entries.append(
                        {
                            "source_path": resolved,
                            "status": "ingestion_error",
                            "error": f"{type(exc).__name__}: {exc}",
                            "timestamp": utc_now_iso(),
                        }
                    )

        return records

    def _group_records(self, records: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for record in records:
            model_version = self._get_model_version(record)
            session_id = self._get_session_id(record)
            grouped[(model_version, session_id)].append(record)
        return dict(sorted(grouped.items(), key=lambda item: item[0]))

    def _get_model_version(self, record: Dict[str, Any]) -> str:
        model_block = record.get("model") or {}

        # 1. Explicit version on signal/evaluation-enriched record
        if model_block.get("version"):
            return str(model_block["version"])

        # 2. Alternate record-level fields
        if record.get("model_version"):
            return str(record["model_version"])

        if record.get("version"):
            return str(record["version"])

        # 3. Evaluation-enriched sub-block, if present later
        evaluation_block = record.get("evaluation") or {}
        evaluation_model = evaluation_block.get("model") or {}
        if evaluation_model.get("version"):
            return str(evaluation_model["version"])

        # 4. Structural fallback (ID_2-safe)
        parameter_class = model_block.get("parameter_class")
        role = model_block.get("role")
        if parameter_class or role:
            return f"{parameter_class or 'unknown'}-{role or 'unknown'}"

        # 5. Final fallback
        return "unknown_version"

    def _get_session_id(self, record: Dict[str, Any]) -> str:
        value = record.get("session_id")
        if value:
            return str(value)
        session_block = record.get("session") or {}
        value = session_block.get("session_id")
        if value:
            return str(value)
        source_block = record.get("source_session") or {}
        value = source_block.get("session_id")
        return str(value or "unknown_session")

    def _build_group_export(
        self,
        group_key: Tuple[str, str],
        records: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        model_version, session_id = group_key
        extracted: List[Dict[str, Any]] = []
        dedup_index: Dict[str, Dict[str, Any]] = {}

        for record in records:
            extraction = self._extract_candidate(record)
            if extraction.candidate is None:

                # NEW — populate excluded_records summary
                self.excluded_records.append(
                    {
                        "source_path": str(record.get("__source_path", "")),
                        "signal_id": str(record.get("signal_id", "")),
                        "session_id": session_id,
                        "reason": extraction.exclusion_reason or "excluded",
                        "model_version": model_version,
                        "timestamp": utc_now_iso(),
                    }
                )

                # existing detailed log entry
                self.log_entries.append(
                    {
                        "source_path": str(record.get("__source_path", "")),
                        "signal_id": str(record.get("signal_id", "")),
                        "session_id": session_id,
                        "status": "excluded",
                        "reason": extraction.exclusion_reason or "excluded",
                        "model_version": model_version,
                        "timestamp": utc_now_iso(),
                    }
                )
                continue

            candidate = extraction.candidate
            self._validate_or_raise(
                validator=self.candidate_validator,
                payload=candidate,
                payload_name=f"candidate:{candidate['candidate_id']}",
            )
            dedup_key = self._build_dedup_key(candidate)
            if dedup_key in dedup_index:
                incumbent = dedup_index[dedup_key]
                winner, loser = self._choose_preferred_candidate(incumbent, candidate)
                dedup_index[dedup_key] = winner
                self.dedup_events.append(
                    {
                        "dedup_key": dedup_key,
                        "kept_candidate_id": winner["candidate_id"],
                        "dropped_candidate_id": loser["candidate_id"],
                        "session_id": session_id,
                        "model_version": model_version,
                    }
                )
            else:
                dedup_index[dedup_key] = candidate
                self.log_entries.append(
                    {
                        "source_path": str(record.get("__source_path", "")),
                        "signal_id": str(record.get("signal_id", "")),
                        "candidate_id": str(candidate.get("candidate_id", "")),
                        "session_id": session_id,
                        "status": "candidate_extracted",
                        "source_state": str(candidate.get("source_state", "")),
                        "target_role": str((candidate.get("target_model") or {}).get("role", "")),
                        "model_version": model_version,
                        "timestamp": utc_now_iso(),
                    }
                )

        extracted = list(dedup_index.values())
        extracted.sort(key=lambda item: (item["timestamp"], item["candidate_id"]))

        if not extracted:
            return None

        dataset_version = self._build_dataset_version(model_version, session_id)
        run_group = f"session-run-{slugify(session_id)}"
        prep_stage = "QPDS-PACKAGE-ID2_PREP"

        export_dir = (
            self.candidates_root
            / run_group
            / prep_stage
            / dataset_version
        )
        dataset_path = export_dir / "dataset.jsonl"
        manifest_path = export_dir / "manifest.json"
        lineage_path = export_dir / "lineage.json"

        written_count = len(extracted)

        if not self.dry_run:
            export_dir.mkdir(parents=True, exist_ok=True)
            written_count = self._write_jsonl(dataset_path, extracted)

        if written_count != len(extracted):
            raise ExportError(
                f"Mismatch between dataset rows and extracted candidates: "
                f"written_count={written_count}, extracted_count={len(extracted)}"
            )

        manifest = self._build_manifest(
            model_version=model_version,
            session_id=session_id,
            dataset_version=dataset_version,
            dataset_path=dataset_path,
            manifest_path=manifest_path,
            lineage_path=lineage_path,
            candidates=extracted,
            source_records=records,
            written_count=written_count,
        )

        if manifest["candidate_count"] != written_count:
            raise ExportError(
                f"Manifest candidate_count mismatch: "
                f"manifest={manifest['candidate_count']}, written_count={written_count}"
            )

        self._validate_or_raise(
            validator=self.manifest_validator,
            payload=manifest,
            payload_name=f"manifest:{dataset_version}",
        )

        if not self.dry_run:
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        if not self.dry_run and self.dataset_passport_id:
            lineage_record = self._build_lineage_record(
                dataset_kind=self.dataset_kind,
                source_records=records,
            )
            lineage_path.write_text(
                json.dumps(lineage_record, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        manifest["written"] = not self.dry_run
        return manifest

    def _build_dataset_version(self, model_version: str, session_id: str) -> str:
        session_slug = slugify(session_id)
        model_slug = slugify(model_version)

        if self.version_tag:
            return f"{session_slug}__{model_slug}__{slugify(self.version_tag)}"

        return f"{session_slug}__{model_slug}__{self._timestamp_token()}"

    def _extract_candidate(self, record: Dict[str, Any]) -> CandidateExtractionResult:
        posture_problem = self._check_posture_constraints(record)
        if posture_problem:
            return CandidateExtractionResult(candidate=None, exclusion_reason=posture_problem)

        source_state = str(
            (record.get("lifecycle") or {}).get("state")
            or record.get("dataset_state")
            or "STATE_3"
        )

        if source_state not in {"STATE_1", "STATE_2", "STATE_3"}:
            source_state = "STATE_3"

        if self.allow_state2_only and source_state != "STATE_2":
            return CandidateExtractionResult(
                candidate=None,
                exclusion_reason=f"source_state_not_state2:{source_state}",
            )

        if self.require_validation:
            validation_ok = self._validation_ready(record)
            if not validation_ok:
                return CandidateExtractionResult(
                    candidate=None,
                    exclusion_reason="validation_not_ready",
                )

        if self.min_maturity is not None:
            record_maturity = str(record.get("maturity") or "")
            if maturity_rank(record_maturity) < maturity_rank(self.min_maturity):
                return CandidateExtractionResult(
                    candidate=None,
                    exclusion_reason=(
                        f"maturity_below_threshold:"
                        f"{record_maturity or 'UNKNOWN'}<{self.min_maturity}"
                    ),
                )

        content = self._extract_content(record)
        if not content["input"] or not content["output"]:
            return CandidateExtractionResult(
                candidate=None,
                exclusion_reason="missing_candidate_content",
            )
 
        signal_id = str(
            record.get("signal_id")
            or sha256_text(str(record.get("__source_path", "unknown")))[:16]
        )
        transformation_id = str(uuid4())
        timestamp = str(record.get("timestamp") or record.get("created_at") or utc_now_iso())

        model = record.get("model") or {}
        target_model = {
            "parameter_class": str(model.get("parameter_class") or "12B-14B"),
            "role": str(model.get("role") or "enterprise"),
        }

        lineage = {
            "source_signal_ref": signal_id,
            "transformation_id": transformation_id,
        }

        candidate = {
            "candidate_id": str(uuid4()),
            "source_signal_id": signal_id,
            "source_state": source_state,
            "target_model": target_model,
            "transformation_type": self.dataset_kind,
            "content": content,
            "authorization": {
                "status": "approved_for_candidate_use",
                "fine_tuning_allowed": False,
            },
            "review": {
                "status": "reviewed",
                "review_required": True,
            },
            "routing": {
                "routing_decision": str((record.get("lifecycle") or {}).get("routing_decision") or ""),
                "eligible_for_state_2": bool((record.get("lifecycle") or {}).get("eligible_for_state_2")),
                "target_state": str((record.get("lifecycle") or {}).get("target_state") or ""),
                "routing_reasons": list((record.get("lifecycle") or {}).get("routing_reasons") or []),
            },
            "validation": {
                "candidate_for_validation": bool((record.get("validation") or {}).get("candidate_for_validation")),
                "validation_requested": bool((record.get("validation") or {}).get("validation_requested")),
                "validation_reasons": list((record.get("validation") or {}).get("validation_reasons") or []),
                "validation_engine_version": str((record.get("validation") or {}).get("validation_engine_version") or ""),
            },
            "lineage": lineage,
            "timestamp": timestamp,
        }
 
        if self.require_routing_review:
            lifecycle = record.get("lifecycle") or {}
            routing_decision = str(lifecycle.get("routing_decision") or "")
            target_state = str(lifecycle.get("target_state") or "")
            eligible_for_state_2 = bool(lifecycle.get("eligible_for_state_2"))

            if not (
                routing_decision == "SEND_TO_STATE_2_REVIEW"
                and target_state == "STATE_2"
                and eligible_for_state_2
            ):
                return CandidateExtractionResult(
                    candidate=None,
                    exclusion_reason="routing_not_state2_review_ready",
                )

        return CandidateExtractionResult(candidate=candidate)

    def _check_posture_constraints(self, record: Dict[str, Any]) -> Optional[str]:
        access_mode = str(record.get("access_mode_primary") or record.get("access_mode") or "ID_2")
        if access_mode != "ID_2":
            return f"access_mode_not_id2:{access_mode}"

        authority_like_fields = [
            record.get("authority"),
            record.get("governance_authority"),
            (record.get("governance_flags") or {}).get("authoritative"),
        ]
        if any(value is True for value in authority_like_fields):
            return "authority_field_detected"

        lifecycle = record.get("lifecycle") or {}
        authorization = record.get("authorization") or {}

        if lifecycle.get("state") == "STATE_1":
            return "state1_not_allowed_in_id2_export"

        if authorization.get("fine_tuning_allowed") is True:
            return "fine_tuning_authority_not_permitted_in_id2_export"

        return None

    def _validation_ready(self, record: Dict[str, Any]) -> bool:
        validation = record.get("validation") or {}
        lifecycle = record.get("lifecycle") or {}

        candidate_for_validation = bool(validation.get("candidate_for_validation"))
        validation_requested = bool(validation.get("validation_requested"))
        eligible_for_state_2 = bool(lifecycle.get("eligible_for_state_2"))
        routing_decision = str(lifecycle.get("routing_decision") or "")

        return (
            candidate_for_validation
            and validation_requested
            and eligible_for_state_2
            and routing_decision == "SEND_TO_STATE_2_REVIEW"
        )

    def _extract_content(self, record: Dict[str, Any]) -> Dict[str, str]:
        input_block = record.get("input") or {}
        signal_block = record.get("signal") or {}

        prompt = input_block.get("prompt")
        if not prompt:
            prompt = record.get("prompt")
        if not prompt:
            prompt = self._fallback_prompt(record)

        output = signal_block.get("structured_summary")
        if not output:
            output = record.get("structured_summary")
        if not output:
            output = signal_block.get("raw_output")
        if not output:
            output = self._fallback_output(record)

        return {
            "input": str(prompt or "").strip(),
            "output": str(output or "").strip(),
        }

    def _fallback_prompt(self, record: Dict[str, Any]) -> str:
        parts: List[str] = []
        if record.get("module"):
            mod = record["module"]
            parts.append(f"Module {mod.get('module_id', '')}: {mod.get('module_title', '')}".strip())
        if record.get("captures") and (record["captures"].get("objective")):
            parts.append(str(record["captures"]["objective"]))
        if record.get("inputs") and (record["inputs"].get("scenario_seeds")):
            seeds = record["inputs"]["scenario_seeds"]
            if isinstance(seeds, list):
                parts.append("Scenario seeds: " + "; ".join(map(str, seeds[:3])))
        return " | ".join(part for part in parts if part)

    def _fallback_output(self, record: Dict[str, Any]) -> str:
        runs = record.get("simulation_runs") or []
        if runs and isinstance(runs, list):
            run = runs[0] or {}
            summary_parts: List[str] = []
            if run.get("scenario_summary"):
                summary_parts.append(str(run["scenario_summary"]))
            if run.get("fragility_points"):
                fragility = run["fragility_points"]
                if isinstance(fragility, list):
                    summary_parts.append("Fragility points: " + "; ".join(map(str, fragility[:5])))
            if run.get("authority_drift_flags"):
                drift = run["authority_drift_flags"]
                if isinstance(drift, list):
                    summary_parts.append("Authority drift flags: " + "; ".join(map(str, drift[:5])))
            return " ".join(summary_parts)
        return ""

    def _content_fingerprint(self, content: Dict[str, str]) -> str:
        return sha256_text(stable_json_dumps(content))

    def _build_dedup_key(self, candidate: Dict[str, Any]) -> str:
        content_fp = self._content_fingerprint(candidate["content"])
 
        if self.dedup_mode == "content":
            return content_fp

        if self.dedup_mode == "source_signal":
            return str(candidate["source_signal_id"])

        if self.dedup_mode == "hybrid":
            return sha256_text(
                stable_json_dumps(
                    {
                        "source_signal_id": candidate["source_signal_id"],
                        "content_fp": content_fp,
                    }
                )
            )

        raise ExportError(f"Unsupported dedup mode: {self.dedup_mode}")

    def _choose_preferred_candidate(
        self,
        incumbent: Dict[str, Any],
        contender: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        def score(item: Dict[str, Any]) -> Tuple[int, str]:
            review = item.get("review") or {}
            review_weight = int(review.get("status") == "reviewed")
            return (review_weight, item.get("timestamp", ""))     

        if score(contender) > score(incumbent):
            return contender, incumbent
        return incumbent, contender

    def _build_manifest(
        self,
        *,
        model_version: str,
        session_id: str,
        dataset_version: str,
        dataset_path: Path,
        manifest_path: Path,
        lineage_path: Path,
        candidates: Sequence[Dict[str, Any]],
        source_records: Sequence[Dict[str, Any]],
        written_count: int,
    ) -> Dict[str, Any]:

        source_signal_ids = sorted({str(item["source_signal_id"]) for item in candidates})
        source_states = sorted({str(item["source_state"]) for item in candidates})

        routing_decisions = sorted({
            str((item.get("routing") or {}).get("routing_decision") or "")
            for item in candidates
            if (item.get("routing") or {}).get("routing_decision")
        })

        target_states = sorted({
            str((item.get("routing") or {}).get("target_state") or "")
            for item in candidates
            if (item.get("routing") or {}).get("target_state")
        })

        model_parameter_class = "12B-14B"
        model_role = "enterprise"

        if candidates:
            target_model = candidates[0].get("target_model") or {}
            model_parameter_class = str(target_model.get("parameter_class") or "12B-14B")
            model_role = str(target_model.get("role") or "enterprise")

        fine_tuning_allowed_count = sum(
            1
            for item in candidates
            if bool((item.get("authorization") or {}).get("fine_tuning_allowed"))
        )
        llm_normalized_count = sum(
            1
            for r in source_records
            if "llm_generated" in (((r.get("signal") or {}).get("tags")) or [])
        )

        native_signal_count = len(source_records) - llm_normalized_count
        if fine_tuning_allowed_count > written_count:
            raise ExportError(
                "authorization_summary.fine_tuning_allowed_count exceeds written candidate count"
            )

        return {
            "manifest_id": str(uuid4()),
            "dataset_version": dataset_version,
            
            "dataset_path": str(dataset_path),
            "package_dir": str(dataset_path.parent),
            "package_manifest_path": str(manifest_path),
            "lineage_path": str(lineage_path),

            "target_model": {
                "parameter_class": model_parameter_class,
                "role": model_role,
            },
            "candidate_count": written_count,
            "source_record_count": len(source_records),
            "extracted_candidate_count": len(candidates),
            "source_states": source_states,
            "source_signal_ids": source_signal_ids,
            "source_record_profile": {
                "llm_normalized_count": llm_normalized_count,
                "native_signal_count": native_signal_count,
            },
            "routing_profile": {
                "routing_decisions": routing_decisions,
                "target_states": target_states,
                "all_candidates_state2_review_ready": all(
                    bool((item.get("routing") or {}).get("eligible_for_state_2"))
                    and str((item.get("routing") or {}).get("routing_decision") or "") == "SEND_TO_STATE_2_REVIEW"
                    for item in candidates
                ),
            },
            "transformations_applied": [
                self.dataset_kind,
                f"dedup:{self.dedup_mode}",
                "id2_candidate_export",
            ],
            "authorization_summary": {
                "all_items_candidate_authorized": all(
                    (item.get("authorization") or {}).get("status") == "approved_for_candidate_use"
                    for item in candidates
                ),
                "fine_tuning_allowed_count": fine_tuning_allowed_count,
                "fine_tuning_globally_allowed": fine_tuning_allowed_count == len(candidates) and len(candidates) > 0,
            },
            "created_at": utc_now_iso(),
        }
    
    def _write_jsonl(self, path: Path, rows: Sequence[Dict[str, Any]]) -> int:
        written_count = 0
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                written_count += 1
        return written_count

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export versioned candidate datasets from ID_2 Q-Pathformer signal artifacts."
    )
    parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        required=True,
        help="Input JSON file or directory. Repeat for multiple roots.",
    )
    parser.add_argument(
        "--require-routing-review",
        action="store_true",
        help="Require lifecycle.routing_decision == SEND_TO_STATE_2_REVIEW and lifecycle.target_state == STATE_2.",
    )
    parser.add_argument(
        "--min-maturity",
        default=None,
        choices=["LEVEL_0", "LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4", "LEVEL_5"],
        help="Optional minimum maturity required for candidate extraction.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_DATASETS_ROOT),
        help="Root datasets workflow directory for candidate exports. Defaults to <repo>/datasets.",
    )
    parser.add_argument(
        "--dataset-kind",
        default=DEFAULT_DATASET_KIND,
        choices=["enterprise_structuring", "strategic_signal", "hybrid_candidate"],
        help="Candidate dataset family.",
    )
    parser.add_argument(
        "--export-scope",
        default=DEFAULT_EXPORT_SCOPE,
        help="Free-text export scope label for manifests.",
    )
    parser.add_argument(
        "--allow-state2-only",
        action="store_true",
        help="Require source lifecycle.state == STATE_2 before extraction.",
    )
    parser.add_argument(
        "--skip-validation-gate",
        action="store_true",
        help="Allow export without validation readiness hints. Use for bootstrap only.",
    )
    parser.add_argument(
        "--dedup-mode",
        default="content",
        choices=["content", "source_signal", "hybrid"],
        help="Deduplication strategy.",
    )
    parser.add_argument(
        "--version-tag",
        default=None,
        help="Optional human-readable version suffix, e.g. batch_001.",
    )
    parser.add_argument(
        "--candidate-schema",
        default=None,
        help="Path to candidate dataset item schema JSON.",
    )
    parser.add_argument(
        "--manifest-schema",
        default=None,
        help="Path to candidate manifest schema JSON.",
    )
    parser.add_argument(
        "--dataset-passport",
        default=None,
        help="Optional dataset passport JSON used to inject dataset_id into lineage output.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build manifests in-memory and print summary without writing files.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_paths = [Path(value).expanduser().resolve() for value in args.inputs]
    output_root = Path(args.output_root).expanduser().resolve()

    exporter = CandidateExporter(
        input_paths=input_paths,
        output_root=output_root,
        dataset_kind=args.dataset_kind,
        export_scope=args.export_scope,
        allow_state2_only=args.allow_state2_only,
        require_validation=not args.skip_validation_gate,
        require_routing_review=args.require_routing_review,
        min_maturity=args.min_maturity,
        dedup_mode=args.dedup_mode,
        version_tag=args.version_tag,
        dry_run=args.dry_run,
        candidate_schema_path=Path(args.candidate_schema).expanduser().resolve() if args.candidate_schema else None,
        manifest_schema_path=Path(args.manifest_schema).expanduser().resolve() if args.manifest_schema else None,
        dataset_passport_path=Path(args.dataset_passport).expanduser().resolve() if args.dataset_passport else None,
    )

    try:
        summary = exporter.run()
    except ExportError as exc:
        sys.stderr.write(f"[EXPORT FAILED] {exc}\n")
        return 1

    json.dump(summary, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
