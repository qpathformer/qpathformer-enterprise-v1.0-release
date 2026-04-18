#!/usr/bin/env python3
"""
Build a de-duplicated, source-tagged supervised fine-tuning dataset from:

1) TR structured signals JSONL/JSON
2) Selected README / runbook markdown files
3) Access-Mode governance reference layer JSON/JSONL

The script is preparation-only. It does not mutate source artifacts, update any
registry, authorize training, or execute training.

Outputs:
  <output-root>/train.sft.jsonl
  <output-root>/validation.sft.jsonl
  <output-root>/dataset_manifest.json
  <output-root>/dataset_preview.json
  <output-root>/skipped_records.json
  <output-root>/source_mix_report.json
  <output-root>/reference_layer_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from path_layout import PATH1_SIGNALS_ROOT, PATH1_SOURCE_CORPUS_ROOT, SHARED_SCHEMAS_ROOT


# -----------------------------
# Constants / defaults
# -----------------------------

DEFAULT_ALLOWED_TR = ["TR-006", "TR-007", "TR-008"]
DEFAULT_PREVIEW_COUNT = 20
DEFAULT_TRAIN_RATIO = 0.9
DEFAULT_MAX_EXAMPLES_PER_SOURCE = 200
DEFAULT_DEDUPE_MODE = "semantic"
DEFAULT_MIN_SIGNAL_TYPES = 1
DEFAULT_REFERENCE_MIN_WEIGHT = "low"

SOURCE_FAMILY_TR = "tr_signal"
SOURCE_FAMILY_README = "readme_runbook"
SOURCE_FAMILY_COMMAND = "command_profile"
SOURCE_FAMILY_EXTERNAL = "external_governance"
SOURCE_FAMILY_SYNTHETIC = "synthetic_reference"

TASK_TYPE_PRIORITY = [
    "boundary_explanation",
    "lifecycle_reasoning",
    "phase_responsibility",
    "phase_non_responsibility",
    "script_selection",
    "constraint_explanation",
    "rule_explanation",
    "governance_summary",
    "definition_extraction",
    "naming_convention",
    "source_comparison",
    "command_generation",
]

SOURCE_PRIORITY = {
    SOURCE_FAMILY_TR: 4,
    SOURCE_FAMILY_README: 3,
    SOURCE_FAMILY_COMMAND: 2,
    SOURCE_FAMILY_EXTERNAL: 1,
    SOURCE_FAMILY_SYNTHETIC: 1,
}

TARGET_MIX = {
    SOURCE_FAMILY_TR: 0.70,
    SOURCE_FAMILY_README: 0.25,
    SOURCE_FAMILY_COMMAND: 0.05,
}

README_INCLUDE_DEFAULTS = {
    "main_readme.md",
    "q-pathformer dev — end-to-end lifecycle → fine-tuning runbook.md",
    "readme_v12.md",
    "readme_v13.md",
    "readme_10.md",
    "readme_v10.0.md",
    "readme_v10.1.md",
    "readme_10.2.md",
    "readme_10.3.md",
    "readme_v11.md",
    "readme.md",
}

COMMAND_PROFILE_NAMES = {
    "q-pathformer dev — end-to-end command profile.md",
}

SCRIPT_NAME_PATTERNS = [
    re.compile(r"\b[a-zA-Z0-9_\-]+\.py\b"),
    re.compile(r"\bpy\s+[a-zA-Z0-9_./\\\-]+\.py\b", re.IGNORECASE),
]

WHITESPACE_RE = re.compile(r"\s+")
TOC_HINT_RE = re.compile(r"\b(table of contents|contents|overview)\b", re.IGNORECASE)
PAGE_NOISE_RE = re.compile(r"^\s*(page\s+\d+|page\s*\|\s*\d+|\d+\s*)$", re.IGNORECASE)
TR_ID_RE = re.compile(r"\bTR[-_ ]?(\d{3})\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)

WEIGHT_CLASS_ORDER = {"low": 1, "medium": 2, "high": 3}
REFERENCE_DATASET_ROLE_ALLOWLIST = {
    "teacher_signal",
    "constraint_signal",
    "inspection_signal",
    "derived_training_example",
}
REFERENCE_REASONING_POSTURE_ALLOWLIST = {
    "learning",
    "mixed_controlled",
    "operational",
    "inspection",
}


# -----------------------------
# Data models
# -----------------------------

@dataclass
class SkipRecord:
    source_family: str
    source_path: str
    reason: str
    source_id: Optional[str] = None
    chunk_index: Optional[int] = None
    task_type: Optional[str] = None


@dataclass
class ExampleRecord:
    prompt: str
    completion: str
    metadata: Dict[str, Any]
    source_group: str
    exact_hash: str
    semantic_hash: str


@dataclass
class SectionChunk:
    title: str
    body: str
    chunk_index: int
    relative_path: str
    source_family: str
    section_path: List[str] = field(default_factory=list)


# -----------------------------
# Utilities
# -----------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_space(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return normalize_space(text)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_sort_key(example: ExampleRecord) -> Tuple[str, str, str, str]:
    md = example.metadata
    return (
        str(md.get("source_family", "")),
        str(md.get("relative_path", "")),
        str(md.get("task_type", "")),
        example.semantic_hash,
    )


def sentence_case(text: str) -> str:
    text = normalize_space(text)
    if not text:
        return text
    return text[0].upper() + text[1:]


def clip_text(text: str, max_len: int) -> str:
    text = normalize_space(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def infer_tr_id(*values: str) -> Optional[str]:
    for value in values:
        if not value:
            continue
        match = TR_ID_RE.search(value)
        if match:
            return f"TR-{match.group(1)}"
    return None


def infer_authority_posture(text: str) -> str:
    if re.search(r"\bnon-authoritative\b|\bsignals not decisions\b|\bhuman review required\b", text, re.IGNORECASE):
        return "non_authoritative"
    return "unknown"


def contains_command(text: str) -> bool:
    return any(pat.search(text) for pat in SCRIPT_NAME_PATTERNS)


def is_probable_toc(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if PAGE_NOISE_RE.match(stripped):
        return True

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if not lines:
        return True

    if len(lines) <= 2 and TOC_HINT_RE.search(stripped):
        return True

    toc_like = 0
    heading_like = 0
    numeric_ending = 0
    for line in lines[:25]:
        if re.search(r"\.{2,}\s*\d+$", line):
            toc_like += 1
            numeric_ending += 1
        elif re.search(r"^[A-Z][A-Za-z0-9\s\-_/&()]+\s+\d+$", line):
            toc_like += 1
            numeric_ending += 1
        elif re.search(r"^#+\s+", line):
            heading_like += 1

    return toc_like >= 6 or (numeric_ending >= 4 and len(lines) < 18) or (TOC_HINT_RE.search(stripped) and len(lines) < 10 and heading_like == 0)


def has_semantic_content(text: str, threshold_words: int = 8) -> bool:
    words = re.findall(r"\b\w+\b", text)
    return len(words) >= threshold_words


def is_sparse_naming_only(text: str) -> bool:
    words = re.findall(r"\b\w+\b", text)
    if len(words) < 12 and re.search(r"\b(id|naming|identifier|convention|uuid|schema)\b", text, re.IGNORECASE):
        return True
    return False


def semantic_fingerprint(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[`*_>#\-]", " ", text)
    text = re.sub(r"\b(?:state[_ ]?[123]|tr[-_ ]?\d{3}|v\d+(?:\.\d+)*)\b", " ", text)
    text = re.sub(r"\b[a-z_./\\\-]+\.py\b", " SCRIPT ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    text = normalize_space(text)
    return sha256_text(text)


def exact_fingerprint(prompt: str, completion: str) -> str:
    return sha256_text(normalize_text(prompt) + "\n---\n" + normalize_text(completion))


def choose_source_family_for_doc(filename_lower: str) -> Optional[str]:
    if filename_lower in COMMAND_PROFILE_NAMES:
        return SOURCE_FAMILY_COMMAND
    if filename_lower in README_INCLUDE_DEFAULTS or filename_lower.endswith(".md"):
        return SOURCE_FAMILY_README
    return None


def normalize_doc_name(name: str) -> str:
    return name.strip().lower()


def _reference_weight_passes(value: str, minimum: str) -> bool:
    return WEIGHT_CLASS_ORDER.get(value, 0) >= WEIGHT_CLASS_ORDER.get(minimum, 0)


def _stringify_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(normalize_text(str(v)) for v in value if normalize_text(str(v)))
    if isinstance(value, dict):
        parts: List[str] = []
        for k, v in value.items():
            if isinstance(v, (str, int, float, bool)):
                parts.append(f"{k}: {v}")
            elif isinstance(v, list):
                joined = "; ".join(str(x) for x in v)
                parts.append(f"{k}: {joined}")
        return "\n".join(parts)
    return ""


# -----------------------------
# Signal and reference loading
# -----------------------------

def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc


def load_json_or_jsonl_records(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return list(iter_jsonl(path))
    if suffix != ".json":
        raise ValueError(f"Unsupported JSON structure in {path}")

    payload = json.loads(read_text(path))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("signals", "records", "items", "rows", "references"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError(f"Unsupported JSON structure in {path}")


def load_signal_records(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        return list(iter_jsonl(path))

    if suffix != ".json":
        raise ValueError(f"Unsupported signals file type: {path}")

    payload = json.loads(read_text(path))

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported JSON structure in {path}")

    for key in ("signals", "records", "items", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    documents = payload.get("documents")
    if isinstance(documents, dict):
        extracted: List[Dict[str, Any]] = []
        for family_name, docs in documents.items():
            if not isinstance(docs, list):
                continue
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                nested_signals = doc.get("signals")
                if isinstance(nested_signals, list):
                    for row in nested_signals:
                        if not isinstance(row, dict):
                            continue
                        lifted = dict(row)
                        lifted.setdefault("document_family", family_name)
                        lifted.setdefault("title", doc.get("title") or doc.get("filename") or "")
                        lifted.setdefault("relative_path", doc.get("relative_path") or "")
                        lifted.setdefault("source_path", doc.get("absolute_path") or "")
                        lifted.setdefault("source_tr", infer_tr_id(
                            str(doc.get("title", "")),
                            str(doc.get("filename", "")),
                            str(doc.get("relative_path", "")),
                        ))
                        lineage = lifted.get("lineage")
                        if not isinstance(lineage, dict):
                            lineage = {}
                        lineage.setdefault("source_file_id", doc.get("file_id"))
                        lineage.setdefault("source_relative_path", doc.get("relative_path"))
                        lineage.setdefault("source_sha256", doc.get("sha256"))
                        lineage.setdefault("source_extraction_status", doc.get("extraction_status"))
                        lifted["lineage"] = lineage
                        extracted.append(lifted)
        if extracted:
            return extracted

    documents_list = payload.get("documents")
    if isinstance(documents_list, list):
        extracted: List[Dict[str, Any]] = []
        for doc in documents_list:
            if not isinstance(doc, dict):
                continue
            nested_signals = doc.get("signals")
            if not isinstance(nested_signals, list):
                continue
            for row in nested_signals:
                if not isinstance(row, dict):
                    continue
                lifted = dict(row)
                lifted.setdefault("title", doc.get("title") or doc.get("filename") or "")
                lifted.setdefault("relative_path", doc.get("relative_path") or "")
                lifted.setdefault("source_path", doc.get("absolute_path") or "")
                lifted.setdefault("source_tr", infer_tr_id(
                    str(doc.get("title", "")),
                    str(doc.get("filename", "")),
                    str(doc.get("relative_path", "")),
                ))
                lineage = lifted.get("lineage")
                if not isinstance(lineage, dict):
                    lineage = {}
                lineage.setdefault("source_file_id", doc.get("file_id"))
                lineage.setdefault("source_relative_path", doc.get("relative_path"))
                lineage.setdefault("source_sha256", doc.get("sha256"))
                lineage.setdefault("source_extraction_status", doc.get("extraction_status"))
                lifted["lineage"] = lineage
                extracted.append(lifted)
        if extracted:
            return extracted

    raise ValueError(
        f"Unsupported JSON structure in {path}. "
        f"Expected JSONL rows, a JSON array, or a JSON object containing "
        f"'signals', 'records', 'items', 'rows', or nested document-wrapped signals."
    )


def resolve_signals_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.exists():
        return path

    candidates: List[Path] = []
    if path.suffix.lower() == ".jsonl":
        candidates.append(path.with_suffix(".json"))
    elif path.suffix.lower() == ".json":
        candidates.append(path.with_suffix(".jsonl"))

    parent = path.parent
    candidates.extend([
        parent / "tr_signals.jsonl",
        parent / "tr_signals.json",
        PATH1_SIGNALS_ROOT / "tr_signals.jsonl",
        PATH1_SIGNALS_ROOT / "tr_signals.json",
        PATH1_SOURCE_CORPUS_ROOT / "tr_signals.jsonl",
        PATH1_SOURCE_CORPUS_ROOT / "tr_signals.json",
        PATH1_SOURCE_CORPUS_ROOT / "tr_corpus.json",
        Path("datasets/signals/tr_signals.jsonl"),
        Path("datasets/signals/tr_signals.json"),
        Path("datasets/corpora/tr_signals.jsonl"),
        Path("datasets/corpora/tr_signals.json"),
        Path("datasets/corpora/tr_corpus.json"),
    ])

    seen = set()
    ordered: List[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(candidate)

    for candidate in ordered:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Signals source not found: {path}. "
        f"Tried fallbacks: {', '.join(str(p) for p in ordered)}"
    )


def resolve_reference_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.exists():
        return path

    candidates = [
        path.with_suffix(".json") if path.suffix.lower() == ".jsonl" else path.with_suffix(".jsonl"),
        SHARED_SCHEMAS_ROOT / "access-mode" / "access_mode_training_governance_reference.example.jsonl",
        SHARED_SCHEMAS_ROOT / "access-mode" / "access_mode_training_governance_reference.jsonl",
        SHARED_SCHEMAS_ROOT / "access-mode" / "access_mode_training_governance_reference.example.json",
        SHARED_SCHEMAS_ROOT / "access-mode" / "access_mode_training_governance_reference.json",
    ]

    seen = set()
    ordered: List[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(candidate)

    for candidate in ordered:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Reference layer not found: {path}. "
        f"Tried fallbacks: {', '.join(str(p) for p in ordered)}"
    )


# -----------------------------
# Reference layer
# -----------------------------

def reference_doc_key(relative_path: str, source_tr: Optional[str], section_label: Optional[str], chunk_index: Optional[int]) -> str:
    return "::".join([
        normalize_space(relative_path or "").lower(),
        normalize_space(source_tr or "").lower(),
        normalize_space(section_label or "").lower(),
        "" if chunk_index is None else str(chunk_index),
    ])


def build_reference_index(reference_records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_ref_id: Dict[str, Dict[str, Any]] = {}
    by_doc_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    report = {
        "loaded_records": len(reference_records),
        "by_dataset_role": Counter(),
        "by_reasoning_posture": Counter(),
        "by_source_family": Counter(),
    }

    for ref in reference_records:
        ref_id = str(ref.get("reference_id") or "").strip()
        if ref_id:
            by_ref_id[ref_id] = ref

        source_document = ref.get("source_document") or {}
        access_mode = ref.get("access_mode") or {}
        training_role = ref.get("training_role") or {}

        key = reference_doc_key(
            str(source_document.get("relative_path") or ""),
            str(source_document.get("document_id") or ""),
            str(source_document.get("section_label") or ""),
            source_document.get("chunk_index"),
        )
        by_doc_key[key].append(ref)

        report["by_dataset_role"][str(training_role.get("dataset_role") or "unknown")] += 1
        report["by_reasoning_posture"][str(access_mode.get("reasoning_posture") or "unknown")] += 1
        report["by_source_family"][str(ref.get("source_family") or "unknown")] += 1

    report["by_dataset_role"] = dict(report["by_dataset_role"])
    report["by_reasoning_posture"] = dict(report["by_reasoning_posture"])
    report["by_source_family"] = dict(report["by_source_family"])

    return {
        "by_ref_id": by_ref_id,
        "by_doc_key": by_doc_key,
        "report": report,
    }


def reference_record_allows_training(
    reference_record: Dict[str, Any],
    allowed_reasoning_postures: Sequence[str],
    min_weight_class: str,
) -> Tuple[bool, str]:
    training_role = reference_record.get("training_role") or {}
    access_mode = reference_record.get("access_mode") or {}
    governance_flags = reference_record.get("governance_flags") or {}
    training_controls = reference_record.get("training_controls") or {}

    dataset_role = str(training_role.get("dataset_role") or "")
    training_stage = str(training_role.get("training_stage") or "")
    reasoning_posture = str(access_mode.get("reasoning_posture") or "")
    eligible_for_finetuning = bool(training_role.get("eligible_for_finetuning", False))
    non_authoritative = bool(governance_flags.get("non_authoritative", False))
    signals_not_decisions = bool(governance_flags.get("signals_not_decisions", False))
    weight_class = str(training_controls.get("weight_class") or "low")

    if dataset_role and dataset_role not in REFERENCE_DATASET_ROLE_ALLOWLIST:
        return False, "reference_dataset_role_excluded"
    if training_stage == "excluded":
        return False, "reference_training_stage_excluded"
    if reasoning_posture and allowed_reasoning_postures and reasoning_posture not in set(allowed_reasoning_postures):
        return False, "reference_reasoning_posture_excluded"
    if not _reference_weight_passes(weight_class, min_weight_class):
        return False, "reference_weight_class_below_minimum"
    if not eligible_for_finetuning:
        return False, "reference_not_finetuning_eligible"
    if not non_authoritative:
        return False, "reference_not_non_authoritative"
    if not signals_not_decisions:
        return False, "reference_missing_signals_not_decisions"

    return True, "reference_allowed"


def match_reference_for_signal(signal: Dict[str, Any], ref_index: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    relative_path = str(signal.get("relative_path") or signal.get("source_path") or signal.get("path") or "")
    source_tr = str(signal.get("source_tr") or signal.get("tr_id") or infer_tr_id(relative_path, signal.get("title", ""), signal.get("source_title", "")) or "")
    section_label = str(signal.get("section_label") or signal.get("title") or signal.get("source_title") or "")
    chunk_index = signal.get("chunk_index")
    signal_id = signal.get("signal_id") or signal.get("id") or signal.get("record_id")
    if signal_id:
        for ref in ref_index.get("by_ref_id", {}).values():
            lineage = ref.get("lineage", {})
            if lineage.get("derived_from_signal_id") == signal_id:
                return ref

    candidate_keys = [
        reference_doc_key(relative_path, source_tr, section_label, chunk_index),
        reference_doc_key(relative_path, source_tr, "", chunk_index),
        reference_doc_key(relative_path, source_tr, section_label, None),
        reference_doc_key(relative_path, source_tr, "", None),
    ]

    for key in candidate_keys:
        matches = ref_index["by_doc_key"].get(key) or []
        if matches:
            return matches[0]
    return None


def match_reference_for_doc_chunk(chunk: SectionChunk, ref_index: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_tr = infer_tr_id(chunk.relative_path, chunk.title, chunk.body) or ""
    candidate_keys = [
        reference_doc_key(chunk.relative_path, source_tr, chunk.title, chunk.chunk_index),
        reference_doc_key(chunk.relative_path, source_tr, chunk.title, None),
        reference_doc_key(chunk.relative_path, source_tr, "", None),
    ]
    for key in candidate_keys:
        matches = ref_index["by_doc_key"].get(key) or []
        if matches:
            return matches[0]
    return None


def attach_reference_metadata(metadata: Dict[str, Any], reference_record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not reference_record:
        return metadata

    access_mode = reference_record.get("access_mode") or {}
    training_role = reference_record.get("training_role") or {}
    governance_flags = reference_record.get("governance_flags") or {}
    training_controls = reference_record.get("training_controls") or {}

    attached = dict(metadata)
    attached.update({
        "reference_id": reference_record.get("reference_id"),
        "reference_record_class": reference_record.get("record_class"),
        "reference_reasoning_posture": access_mode.get("reasoning_posture"),
        "reference_primary_mode": access_mode.get("primary_mode"),
        "reference_dataset_role": training_role.get("dataset_role"),
        "reference_training_stage": training_role.get("training_stage"),
        "reference_weight_class": training_controls.get("weight_class"),
        "reference_signals_not_decisions": governance_flags.get("signals_not_decisions"),
        "reference_non_authoritative": governance_flags.get("non_authoritative"),
    })
    return attached


# -----------------------------
# Signal extraction
# -----------------------------

def extract_signal_text_fields(signal: Dict[str, Any]) -> Dict[str, str]:
    fields = {
        "definitions": "",
        "rules": "",
        "constraints": "",
        "lifecycle_logic": "",
        "commands": "",
        "code_or_scripts": "",
        "naming_and_ids": "",
        "structured_summary": "",
        "excerpt": "",
    }

    for key in list(fields.keys()):
        fields[key] = _stringify_value(signal.get(key))

    nested_candidates = [
        signal.get("signal"),
        signal.get("fields"),
        signal.get("payload"),
        signal.get("record"),
        signal.get("data"),
    ]
    for nested in nested_candidates:
        if not isinstance(nested, dict):
            continue
        for key in list(fields.keys()):
            if not normalize_space(fields[key]):
                fields[key] = _stringify_value(nested.get(key))

    joined = normalize_space(" ".join(v for v in fields.values() if v))
    if not joined:
        fallback_keys = [
            "chunk_text", "text", "content", "body", "excerpt",
            "summary", "section_text", "chunk", "raw_text", "source_excerpt",
        ]
        for key in fallback_keys:
            value = signal.get(key)
            if isinstance(value, str) and value.strip():
                fields["excerpt"] = value
                break
        if not normalize_space(fields["excerpt"]):
            for nested in nested_candidates:
                if not isinstance(nested, dict):
                    continue
                for key in fallback_keys:
                    value = nested.get(key)
                    if isinstance(value, str) and value.strip():
                        fields["excerpt"] = value
                        break
                if normalize_space(fields["excerpt"]):
                    break

    return fields


def build_signal_metadata(signal: Dict[str, Any], dataset_version: str) -> Dict[str, Any]:
    relative_path = signal.get("relative_path") or signal.get("source_path") or signal.get("path") or signal.get("file_path") or ""
    source_tr = signal.get("source_tr") or signal.get("tr_id") or infer_tr_id(relative_path, signal.get("title", ""), signal.get("source_title", ""), json.dumps(signal, ensure_ascii=False))
    excerpt = " ".join(v for v in extract_signal_text_fields(signal).values() if v)
    return {
        "dataset_version": dataset_version,
        "source_family": SOURCE_FAMILY_TR,
        "source_tr": source_tr,
        "authority_posture": infer_authority_posture(excerpt),
        "signal_id": signal.get("signal_id") or signal.get("id") or signal.get("record_id"),
        "relative_path": relative_path,
        "source_title": signal.get("title") or signal.get("source_title") or "",
        "chunk_index": signal.get("chunk_index"),
        "signal_types": signal.get("signal_types", []),
    }


def make_example(prompt: str, completion: str, metadata: Dict[str, Any], source_group: str) -> ExampleRecord:
    prompt = sentence_case(prompt)
    completion = normalize_text(completion)
    return ExampleRecord(
        prompt=prompt,
        completion=completion,
        metadata=metadata,
        source_group=source_group,
        exact_hash=exact_fingerprint(prompt, completion),
        semantic_hash=semantic_fingerprint(f"{metadata.get('task_type', '')}\n{completion}"),
    )


def examples_from_signal(
    signal: Dict[str, Any],
    dataset_version: str,
    min_signal_types: int,
    include_command_examples: bool,
    reference_record: Optional[Dict[str, Any]] = None,
) -> Tuple[List[ExampleRecord], List[SkipRecord]]:
    fields = extract_signal_text_fields(signal)

    signal_types = signal.get("signal_types", [])
    if isinstance(signal_types, list) and signal_types:
        non_empty_types = [str(x) for x in signal_types if normalize_space(str(x))]
    else:
        non_empty_types = [k for k, v in fields.items() if normalize_space(v)]

    metadata_base = build_signal_metadata(signal, dataset_version)
    metadata_base = attach_reference_metadata(metadata_base, reference_record)
    relative_path = metadata_base.get("relative_path", "")
    source_id = metadata_base.get("signal_id")
    chunk_index = metadata_base.get("chunk_index")
    skipped: List[SkipRecord] = []

    if len(non_empty_types) < min_signal_types:
        skipped.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "insufficient_signal_types", source_id, chunk_index))
        return [], skipped

    joined_text = "\n".join(v for v in fields.values() if v)
    if is_probable_toc(joined_text) and len(joined_text.split()) < 50:
        skipped.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "toc_noise", source_id, chunk_index))
        return [], skipped

    if not has_semantic_content(joined_text):
        skipped.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "insufficient_semantic_content", source_id, chunk_index))
        return [], skipped

    if is_sparse_naming_only(joined_text):
        skipped.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "naming_only_sparse", source_id, chunk_index))
        return [], skipped

    examples: List[ExampleRecord] = []
    source_group = f"{relative_path}::{chunk_index}::{source_id or ''}"

    def add(task_type: str, prompt: str, completion: str) -> None:
        md = dict(metadata_base)
        md["task_type"] = task_type
        examples.append(make_example(prompt, completion, md, source_group))

    source_tr = metadata_base.get("source_tr") or "this technical report"

    if fields["definitions"]:
        add("definition_extraction", f"Explain the key definition or definitional concept expressed in {source_tr} in plain language.", clip_text(fields["definitions"], 900))
    if fields["rules"]:
        add("rule_explanation", "Explain the governance rule expressed here and why it matters operationally.", clip_text(fields["rules"], 900))
    if fields["constraints"]:
        add("constraint_explanation", "What constraint is being enforced here, and what behavior does it prohibit or limit?", clip_text(fields["constraints"], 900))
    if fields["constraints"] and not fields["constraints"].strip() == fields["rules"].strip():
        add("boundary_explanation", "Explain why these constraints preserve non-authoritative posture.", clip_text(fields["constraints"], 900))
    if fields["lifecycle_logic"]:
        add("lifecycle_reasoning", "What lifecycle principle is being expressed here, and how does it shape valid state transitions?", clip_text(fields["lifecycle_logic"], 900))
    if fields["structured_summary"]:
        add("governance_summary", f"Summarize the governance meaning of this {source_tr} signal without collapsing signals into decisions.", clip_text(fields["structured_summary"], 900))
    if fields["excerpt"] and not examples:
        add("governance_summary", "Summarize the governance boundary expressed in this source excerpt.", clip_text(fields["excerpt"], 900))
    if fields["naming_and_ids"]:
        add("naming_convention", "What naming or identifier convention is being used here, and what does it refer to?", clip_text(fields["naming_and_ids"], 700))

    command_context = "\n".join(x for x in [fields["commands"], fields["code_or_scripts"], fields["constraints"], fields["lifecycle_logic"], fields["excerpt"]] if x)
    if include_command_examples and (fields["commands"] or contains_command(command_context)):
        if contains_command(command_context) and (
            fields["constraints"] or fields["lifecycle_logic"] or re.search(r"\b(posture|boundary|validation|freeze|authorization|state|review|promotion|phase|responsibilit)\b", command_context, re.IGNORECASE)
        ):
            add("script_selection", "Which script should be used for this lifecycle task, and what is its role boundary?", clip_text(command_context, 900))
            add("command_generation", "Explain the command guidance here together with its governance boundary and non-responsibilities.", clip_text(command_context, 900))
        elif fields["commands"]:
            skipped.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "command_without_context", source_id, chunk_index))

    return examples, skipped


# -----------------------------
# Markdown ingestion
# -----------------------------

def split_markdown_sections(text: str, relative_path: str, source_family: str) -> List[SectionChunk]:
    text = text.replace("\r\n", "\n")
    matches = list(HEADING_RE.finditer(text))
    chunks: List[SectionChunk] = []

    if not matches:
        body = normalize_text(text)
        if body:
            stem = Path(relative_path).stem
            chunks.append(SectionChunk(stem, body, 0, relative_path, source_family, [stem]))
        return chunks

    stack: List[Tuple[int, str]] = []
    for idx, match in enumerate(matches):
        level = len(match.group(1))
        title = normalize_text(match.group(2))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = normalize_text(text[start:end])
        if not body:
            continue
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        section_path = [x[1] for x in stack]
        chunks.append(SectionChunk(title, body, len(chunks), relative_path, source_family, section_path))
    return chunks


def classify_doc_section(chunk: SectionChunk) -> str:
    title = chunk.title.lower()
    body = chunk.body.lower()
    joined = f"{title}\n{body}"
    if contains_command(joined):
        return "script_selection"
    if re.search(r"\bnon-responsibilit|must not|does not|out of scope|not responsible\b", joined):
        return "phase_non_responsibility"
    if re.search(r"\bresponsibilit|purpose|objective|role|what .* does\b", joined):
        return "phase_responsibility"
    if re.search(r"\blifecycle|state[_ ]?[123]|transition|promotion|freeze|validation\b", joined):
        return "lifecycle_reasoning"
    if re.search(r"\bboundary|constraint|prohibit|authorization|signals? .* not decisions\b", joined):
        return "boundary_explanation"
    return "governance_summary"


def build_doc_prompt(chunk: SectionChunk, task_type: str) -> str:
    title = chunk.title
    if task_type == "phase_responsibility":
        return f"What is this phase or component responsible for in '{title}'?"
    if task_type == "phase_non_responsibility":
        return f"What must this phase or component not do according to '{title}'?"
    if task_type == "lifecycle_reasoning":
        return f"What lifecycle position or transition rule is described in '{title}'?"
    if task_type == "script_selection":
        return f"Which script or command path is relevant in '{title}', and what is its role boundary?"
    if task_type == "boundary_explanation":
        return f"Explain the governance boundary described in '{title}'."
    return f"Summarize the operational guidance expressed in '{title}'."


def examples_from_doc_chunk(
    chunk: SectionChunk,
    dataset_version: str,
    include_command_examples: bool,
    reference_record: Optional[Dict[str, Any]] = None,
) -> Tuple[List[ExampleRecord], List[SkipRecord]]:
    skipped: List[SkipRecord] = []
    body = chunk.body

    if is_probable_toc(body) and len(body.split()) < 50:
        skipped.append(SkipRecord(chunk.source_family, chunk.relative_path, "toc_noise", chunk_index=chunk.chunk_index))
        return [], skipped
    if not has_semantic_content(body):
        skipped.append(SkipRecord(chunk.source_family, chunk.relative_path, "insufficient_semantic_content", chunk_index=chunk.chunk_index))
        return [], skipped

    has_cmd = contains_command(body)
    if chunk.source_family == SOURCE_FAMILY_COMMAND and not include_command_examples:
        skipped.append(SkipRecord(chunk.source_family, chunk.relative_path, "excluded_by_source_filter", chunk_index=chunk.chunk_index))
        return [], skipped

    if has_cmd and not re.search(r"\b(posture|boundary|state|validation|freeze|authorization|responsibilit|must not|scope|review|promotion|lifecycle)\b", body, re.IGNORECASE):
        skipped.append(SkipRecord(chunk.source_family, chunk.relative_path, "command_without_context", chunk_index=chunk.chunk_index))
        return [], skipped

    task_type = classify_doc_section(chunk)
    metadata = {
        "dataset_version": dataset_version,
        "source_family": chunk.source_family,
        "source_tr": infer_tr_id(chunk.relative_path, chunk.title, body),
        "task_type": task_type,
        "authority_posture": infer_authority_posture(body),
        "signal_id": None,
        "relative_path": chunk.relative_path,
        "section_title": chunk.title,
        "chunk_index": chunk.chunk_index,
        "section_path": chunk.section_path,
    }
    metadata = attach_reference_metadata(metadata, reference_record)

    source_group = f"{chunk.relative_path}::{chunk.chunk_index}"
    prompt = build_doc_prompt(chunk, task_type)
    completion = clip_text(body, 950)
    examples = [make_example(prompt, completion, metadata, source_group)]

    if has_cmd and include_command_examples and task_type != "script_selection":
        metadata2 = dict(metadata)
        metadata2["task_type"] = "script_selection"
        examples.append(make_example(
            f"Which script or command should be selected here, and what boundary limits its use in '{chunk.title}'?",
            completion,
            metadata2,
            source_group,
        ))

    return examples, skipped


def gather_docs(docs_root: Path, include_readme_docs: bool) -> List[Tuple[Path, str]]:
    if not docs_root.exists():
        return []

    results: List[Tuple[Path, str]] = []
    for path in sorted(docs_root.rglob("*.md")):
        source_family = choose_source_family_for_doc(normalize_doc_name(path.name))
        if not source_family:
            continue
        if source_family == SOURCE_FAMILY_README and not include_readme_docs:
            continue
        results.append((path, source_family))
    return results


# -----------------------------
# Dedupe / mix / split
# -----------------------------

def dedupe_examples(examples: Sequence[ExampleRecord], dedupe_mode: str) -> Tuple[List[ExampleRecord], List[SkipRecord]]:
    exact_seen: Dict[str, ExampleRecord] = {}
    semantic_seen: Dict[Tuple[str, str, str], ExampleRecord] = {}
    kept: List[ExampleRecord] = []
    skipped: List[SkipRecord] = []

    for ex in sorted(examples, key=stable_sort_key):
        md = ex.metadata
        sf = md.get("source_family", "")
        sp = md.get("relative_path", "")
        ck = md.get("chunk_index")
        sid = md.get("signal_id")
        tt = md.get("task_type")

        if ex.exact_hash in exact_seen:
            skipped.append(SkipRecord(str(sf), str(sp), "duplicate_exact", sid, ck, tt))
            continue

        if dedupe_mode == "semantic":
            key = (str(tt or ""), str(sf), ex.semantic_hash)
            prev = semantic_seen.get(key)
            if prev is not None:
                current_priority = SOURCE_PRIORITY.get(str(sf), 0)
                previous_priority = SOURCE_PRIORITY.get(str(prev.metadata.get("source_family", "")), 0)
                if current_priority > previous_priority:
                    kept.remove(prev)
                    exact_seen.pop(prev.exact_hash, None)
                    semantic_seen[key] = ex
                    exact_seen[ex.exact_hash] = ex
                    kept.append(ex)
                else:
                    skipped.append(SkipRecord(str(sf), str(sp), "duplicate_semantic", sid, ck, tt))
                continue
            semantic_seen[key] = ex

        exact_seen[ex.exact_hash] = ex
        kept.append(ex)

    return kept, skipped


def cap_per_source(examples: Sequence[ExampleRecord], max_examples_per_source: int) -> Tuple[List[ExampleRecord], List[SkipRecord]]:
    grouped: Dict[str, List[ExampleRecord]] = defaultdict(list)
    for ex in examples:
        grouped[str(ex.metadata.get("relative_path", ""))].append(ex)

    kept: List[ExampleRecord] = []
    skipped: List[SkipRecord] = []
    for source_path, group in grouped.items():
        ordered = sorted(group, key=lambda e: (
            TASK_TYPE_PRIORITY.index(e.metadata.get("task_type")) if e.metadata.get("task_type") in TASK_TYPE_PRIORITY else 999,
            e.prompt,
        ))
        keep_group = ordered[:max_examples_per_source]
        drop_group = ordered[max_examples_per_source:]
        kept.extend(keep_group)
        for ex in drop_group:
            skipped.append(SkipRecord(
                str(ex.metadata.get("source_family", "")),
                source_path,
                "max_examples_per_source_exceeded",
                ex.metadata.get("signal_id"),
                ex.metadata.get("chunk_index"),
                ex.metadata.get("task_type"),
            ))
    return kept, skipped


def apply_mix_policy(examples: Sequence[ExampleRecord]) -> Tuple[List[ExampleRecord], Dict[str, Any], List[SkipRecord]]:
    by_family: Dict[str, List[ExampleRecord]] = defaultdict(list)
    for ex in examples:
        by_family[str(ex.metadata.get("source_family", ""))].append(ex)

    counts = {family: len(group) for family, group in by_family.items()}
    if not counts:
        return [], {"target_mix": TARGET_MIX, "available": {}, "selected": {}}, []

    tr_available = counts.get(SOURCE_FAMILY_TR, 0)
    readme_available = counts.get(SOURCE_FAMILY_README, 0)
    command_available = counts.get(SOURCE_FAMILY_COMMAND, 0)

    selected: List[ExampleRecord] = []
    skipped: List[SkipRecord] = []
    selected_counts: Dict[str, int] = {
        SOURCE_FAMILY_TR: 0,
        SOURCE_FAMILY_README: 0,
        SOURCE_FAMILY_COMMAND: 0,
    }

    target_total = tr_available if tr_available > 0 else sum(counts.values())

    desired_tr = int(round(target_total * TARGET_MIX[SOURCE_FAMILY_TR]))
    desired_readme = int(round(target_total * TARGET_MIX[SOURCE_FAMILY_README]))
    desired_command = int(round(target_total * TARGET_MIX[SOURCE_FAMILY_COMMAND]))

    tr_take = min(tr_available, max(desired_tr, 1 if tr_available > 0 else 0))
    readme_take = min(readme_available, desired_readme)
    command_take = min(command_available, desired_command)

    allocated = tr_take + readme_take + command_take
    desired_total = desired_tr + desired_readme + desired_command
    remainder = max(0, desired_total - allocated)

    extra_tr = min(tr_available - tr_take, remainder)
    tr_take += extra_tr

    family_takes = {
        SOURCE_FAMILY_TR: tr_take,
        SOURCE_FAMILY_README: readme_take,
        SOURCE_FAMILY_COMMAND: command_take,
    }

    for family in (SOURCE_FAMILY_TR, SOURCE_FAMILY_README, SOURCE_FAMILY_COMMAND):
        group = sorted(by_family.get(family, []), key=stable_sort_key)
        take = family_takes[family]
        selected.extend(group[:take])
        selected_counts[family] = take
        for ex in group[take:]:
            skipped.append(SkipRecord(
                family,
                str(ex.metadata.get("relative_path", "")),
                "downsampled_by_mix_policy",
                ex.metadata.get("signal_id"),
                ex.metadata.get("chunk_index"),
                ex.metadata.get("task_type"),
            ))

    report = {
        "target_mix": TARGET_MIX,
        "available": counts,
        "selected": selected_counts,
        "selected_total": len(selected),
        "policy_note": "TR anchored; README secondary; command_profile opportunistic and capped",
    }
    return selected, report, skipped


def grouped_train_validation_split(examples: Sequence[ExampleRecord], train_ratio: float) -> Tuple[List[ExampleRecord], List[ExampleRecord]]:
    groups: Dict[str, List[ExampleRecord]] = defaultdict(list)
    for ex in examples:
        groups[ex.source_group].append(ex)

    group_items = sorted(groups.items(), key=lambda item: item[0])
    total = sum(len(v) for _, v in group_items)
    target_train = int(round(total * train_ratio))

    train: List[ExampleRecord] = []
    val: List[ExampleRecord] = []
    running = 0

    for _, group in group_items:
        if running < target_train:
            train.extend(group)
            running += len(group)
        else:
            val.extend(group)

    if not val and train and group_items:
        last_group_key = group_items[-1][0]
        last_group = groups[last_group_key]
        for item in last_group:
            train.remove(item)
        val.extend(last_group)

    return train, val


# -----------------------------
# CLI
# -----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a checkpoint/LoRA-ready SFT dataset from TR signals, docs, and an access-mode reference layer.")
    parser.add_argument("--signals-jsonl", required=True, help="Path to tr_signals.jsonl or equivalent JSON/JSONL source.")
    parser.add_argument("--docs-root", required=False, help="Optional root containing README/runbook markdown sources.")
    parser.add_argument("--reference-layer", required=False, help="Optional path to access-mode governance reference JSON/JSONL.")
    parser.add_argument("--output-root", required=True, help="Output directory for the generated dataset package.")
    parser.add_argument("--train-ratio", type=float, default=DEFAULT_TRAIN_RATIO)
    parser.add_argument("--max-examples-per-source", type=int, default=DEFAULT_MAX_EXAMPLES_PER_SOURCE)
    parser.add_argument("--include-command-examples", action="store_true")
    parser.add_argument("--include-readme-docs", action="store_true")
    parser.add_argument("--require-reference-match", action="store_true")
    parser.add_argument("--allowed-tr", type=str, default="")
    parser.add_argument("--allowed-reference-postures", type=str, default=",".join(sorted(REFERENCE_REASONING_POSTURE_ALLOWLIST)))
    parser.add_argument("--reference-min-weight", type=str, default=DEFAULT_REFERENCE_MIN_WEIGHT, choices=["low", "medium", "high"])
    parser.add_argument("--exclude-source-path-pattern", action="append", default=[])
    parser.add_argument("--dedupe-mode", choices=["semantic", "exact"], default=DEFAULT_DEDUPE_MODE)
    parser.add_argument("--min-signal-types", type=int, default=DEFAULT_MIN_SIGNAL_TYPES)
    parser.add_argument("--preview-count", type=int, default=DEFAULT_PREVIEW_COUNT)
    parser.add_argument("--dry-run", action="store_true")
    return parser


# -----------------------------
# Main build
# -----------------------------

def should_exclude_path(relative_path: str, patterns: Sequence[str]) -> bool:
    return any(re.search(p, relative_path, re.IGNORECASE) for p in patterns)


def filter_allowed_tr(signal: Dict[str, Any], allowed_tr: Sequence[str]) -> bool:
    if not allowed_tr:
        return True

    explicit = signal.get("source_tr") or signal.get("tr_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip() in set(allowed_tr)

    haystack = " ".join(str(signal.get(k, "")) for k in ("title", "source_title", "relative_path", "source_path", "path"))
    found = infer_tr_id(haystack)
    if found:
        return found in set(allowed_tr)
    return True


def example_to_row(example: ExampleRecord) -> Dict[str, Any]:
    return {
        "prompt": example.prompt,
        "completion": example.completion,
        "metadata": example.metadata,
    }


def build_dataset(args: argparse.Namespace) -> Dict[str, Any]:
    signals_path = resolve_signals_path(args.signals_jsonl)
    docs_root = Path(args.docs_root) if args.docs_root else None
    output_root = Path(args.output_root)
    dataset_version = output_root.name or "checkpoint_v1"

    if docs_root and not docs_root.exists():
        raise FileNotFoundError(f"Docs root not found: {docs_root}")

    allowed_tr = [x.strip() for x in args.allowed_tr.split(",") if x.strip()]
    allowed_reference_postures = [x.strip() for x in args.allowed_reference_postures.split(",") if x.strip()]

    ref_index = None
    reference_layer_path = None
    reference_layer_report: Dict[str, Any] = {
        "enabled": False,
        "loaded_records": 0,
        "matched_signal_records": 0,
        "matched_doc_chunks": 0,
        "reference_allowed_rows": 0,
        "reference_blocked_rows": 0,
        "require_reference_match": bool(args.require_reference_match),
        "allowed_reference_postures": allowed_reference_postures,
        "reference_min_weight": args.reference_min_weight,
    }

    if args.reference_layer:
        reference_layer_path = resolve_reference_path(args.reference_layer)
        reference_records = load_json_or_jsonl_records(reference_layer_path)
        ref_index = build_reference_index(reference_records)
        reference_layer_report["enabled"] = True
        reference_layer_report["loaded_records"] = len(reference_records)
        reference_layer_report["index_report"] = ref_index["report"]

    all_examples: List[ExampleRecord] = []
    all_skips: List[SkipRecord] = []

    signals = load_signal_records(signals_path)
    for signal in signals:
        relative_path = str(signal.get("relative_path") or signal.get("source_path") or signal.get("path") or "")

        if not filter_allowed_tr(signal, allowed_tr):
            all_skips.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "excluded_by_source_filter", signal.get("signal_id") or signal.get("id"), signal.get("chunk_index")))
            continue
        if should_exclude_path(relative_path, args.exclude_source_path_pattern):
            all_skips.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "excluded_by_source_filter", signal.get("signal_id") or signal.get("id"), signal.get("chunk_index")))
            continue

        reference_record = None
        if ref_index is not None:
            reference_record = match_reference_for_signal(signal, ref_index)
            if reference_record:
                reference_layer_report["matched_signal_records"] += 1
                allowed, reason = reference_record_allows_training(reference_record, allowed_reference_postures, args.reference_min_weight)
                if not allowed:
                    reference_layer_report["reference_blocked_rows"] += 1
                    all_skips.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, reason, signal.get("signal_id") or signal.get("id"), signal.get("chunk_index")))
                    continue
            elif args.require_reference_match:
                reference_layer_report["reference_blocked_rows"] += 1
                all_skips.append(SkipRecord(SOURCE_FAMILY_TR, relative_path, "reference_match_required_but_missing", signal.get("signal_id") or signal.get("id"), signal.get("chunk_index")))
                continue

        produced, skipped = examples_from_signal(signal, dataset_version, args.min_signal_types, args.include_command_examples, reference_record)
        if reference_record:
            reference_layer_report["reference_allowed_rows"] += len(produced)
        all_examples.extend(produced)
        all_skips.extend(skipped)

    doc_files = gather_docs(docs_root, args.include_readme_docs) if docs_root else []
    for doc_path, source_family in doc_files:
        relative_path = safe_relative(doc_path, docs_root if docs_root else doc_path.parent)
        if should_exclude_path(relative_path, args.exclude_source_path_pattern):
            all_skips.append(SkipRecord(source_family, relative_path, "excluded_by_source_filter"))
            continue

        content = read_text(doc_path)
        chunks = split_markdown_sections(content, relative_path, source_family)
        for chunk in chunks:
            reference_record = None
            if ref_index is not None:
                reference_record = match_reference_for_doc_chunk(chunk, ref_index)
                if reference_record:
                    reference_layer_report["matched_doc_chunks"] += 1
                    allowed, reason = reference_record_allows_training(reference_record, allowed_reference_postures, args.reference_min_weight)
                    if not allowed:
                        reference_layer_report["reference_blocked_rows"] += 1
                        all_skips.append(SkipRecord(chunk.source_family, chunk.relative_path, reason, chunk_index=chunk.chunk_index))
                        continue
                elif args.require_reference_match:
                    reference_layer_report["reference_blocked_rows"] += 1
                    all_skips.append(SkipRecord(chunk.source_family, chunk.relative_path, "reference_match_required_but_missing", chunk_index=chunk.chunk_index))
                    continue

            produced, skipped = examples_from_doc_chunk(chunk, dataset_version, args.include_command_examples, reference_record)
            if reference_record:
                reference_layer_report["reference_allowed_rows"] += len(produced)
            all_examples.extend(produced)
            all_skips.extend(skipped)

    deduped, dedupe_skips = dedupe_examples(all_examples, args.dedupe_mode)
    all_skips.extend(dedupe_skips)

    capped, cap_skips = cap_per_source(deduped, args.max_examples_per_source)
    all_skips.extend(cap_skips)

    mixed, mix_report, mix_skips = apply_mix_policy(capped)
    all_skips.extend(mix_skips)

    train_examples, validation_examples = grouped_train_validation_split(mixed, args.train_ratio)
    train_rows = [example_to_row(ex) for ex in sorted(train_examples, key=stable_sort_key)]
    validation_rows = [example_to_row(ex) for ex in sorted(validation_examples, key=stable_sort_key)]

    source_counts = Counter(ex.metadata.get("source_family") for ex in mixed)
    task_counts = Counter(ex.metadata.get("task_type") for ex in mixed)
    reference_usage_counts = Counter(ex.metadata.get("reference_id") for ex in mixed if ex.metadata.get("reference_id"))
    posture_counts = Counter(ex.metadata.get("reference_reasoning_posture") for ex in mixed if ex.metadata.get("reference_reasoning_posture"))

    manifest = {
        "dataset_manifest_version": f"v15.x-{dataset_version}",
        "generated_at_utc": utc_now_iso(),
        "input_sources": {
            "signals_jsonl": str(signals_path),
            "docs_root": str(docs_root) if docs_root else None,
            "reference_layer": str(reference_layer_path) if reference_layer_path else None,
        },
        "record_counts": {
            "source_signal_rows": source_counts.get(SOURCE_FAMILY_TR, 0),
            "readme_rows": source_counts.get(SOURCE_FAMILY_README, 0),
            "command_rows": source_counts.get(SOURCE_FAMILY_COMMAND, 0),
            "train_rows": len(train_rows),
            "validation_rows": len(validation_rows),
            "skipped_rows": len(all_skips),
        },
        "mix_policy": {
            "tr_signal_ratio": TARGET_MIX[SOURCE_FAMILY_TR],
            "readme_runbook_ratio": TARGET_MIX[SOURCE_FAMILY_README],
            "command_profile_ratio": TARGET_MIX[SOURCE_FAMILY_COMMAND],
        },
        "filters": {
            "excluded_toc_noise": True,
            "excluded_duplicate_rows": True,
            "excluded_sparse_chunks": True,
            "exclude_source_path_pattern": args.exclude_source_path_pattern,
            "allowed_tr": allowed_tr,
            "dedupe_mode": args.dedupe_mode,
            "max_examples_per_source": args.max_examples_per_source,
            "require_reference_match": bool(args.require_reference_match),
            "allowed_reference_postures": allowed_reference_postures,
            "reference_min_weight": args.reference_min_weight,
        },
        "authority_posture": {
            "non_authoritative": True,
            "training_preparation_only": True,
        },
        "task_type_counts": dict(sorted(task_counts.items())),
        "reference_id_count": len(reference_usage_counts),
        "reference_reasoning_posture_counts": dict(sorted(posture_counts.items())),
    }

    preview_examples = (train_rows + validation_rows)[: args.preview_count]
    dataset_preview = {
        "generated_at_utc": manifest["generated_at_utc"],
        "dataset_version": dataset_version,
        "preview_count": len(preview_examples),
        "examples": preview_examples,
    }

    skipped_records = [asdict(skip) for skip in all_skips]
    source_mix_report = {
        "generated_at_utc": manifest["generated_at_utc"],
        "dataset_version": dataset_version,
        "target_mix": mix_report.get("target_mix", {}),
        "available": mix_report.get("available", {}),
        "selected": mix_report.get("selected", {}),
        "selected_total": mix_report.get("selected_total", 0),
        "train_counts": dict(Counter(row["metadata"].get("source_family") for row in train_rows)),
        "validation_counts": dict(Counter(row["metadata"].get("source_family") for row in validation_rows)),
    }

    result = {
        "status": "ok",
        "dataset_version": dataset_version,
        "output_root": str(output_root),
        "manifest": manifest,
        "preview": dataset_preview,
        "skipped_records": skipped_records,
        "source_mix_report": source_mix_report,
        "reference_layer_report": reference_layer_report,
        "train_rows": train_rows,
        "validation_rows": validation_rows,
    }

    if not args.dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
        write_jsonl(output_root / "train.sft.jsonl", train_rows)
        write_jsonl(output_root / "validation.sft.jsonl", validation_rows)
        write_json(output_root / "dataset_manifest.json", manifest)
        write_json(output_root / "dataset_preview.json", dataset_preview)
        write_json(output_root / "skipped_records.json", skipped_records)
        write_json(output_root / "source_mix_report.json", source_mix_report)
        write_json(output_root / "reference_layer_report.json", reference_layer_report)

    return result


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not 0.0 < args.train_ratio < 1.0:
        raise SystemExit("--train-ratio must be between 0 and 1")
    if args.max_examples_per_source < 1:
        raise SystemExit("--max-examples-per-source must be >= 1")
    if args.min_signal_types < 1:
        raise SystemExit("--min-signal-types must be >= 1")
    if args.preview_count < 1:
        raise SystemExit("--preview-count must be >= 1")

    result = build_dataset(args)
    print(json.dumps({
        "status": result["status"],
        "dataset_version": result["dataset_version"],
        "output_root": result["output_root"],
        "record_counts": result["manifest"]["record_counts"],
        "reference_layer_report": result["reference_layer_report"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
