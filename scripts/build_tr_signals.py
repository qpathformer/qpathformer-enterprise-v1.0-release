#!/usr/bin/env python3
"""
build_tr_signals.py

Build structured signals from APOD technical reports under docs/TR, including:
- PDF
- DOCX
- MD

Signal extraction targets:
- definitions
- rules
- constraints
- lifecycle logic
- commands section if provided
- code/scripts if provided
- naming & ID conventions if provided

Special handling:
- all Access-Mode materials are grouped under source_tr = "TR-006"
- this includes:
  - docs/TR/access_mode/*
  - APOD-TR-006*
  - APOD-TR-006-E.2*
  - markdown companions related to Access-Mode

Example:
    py scripts\build_tr_signals.py ^
      --input-root docs\TR ^
      --output datasets\signals\tr_signals.json ^
      --jsonl-output datasets\signals\tr_signals.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md"}
ACCESS_MODE_DIRNAME = "access_mode"

CHUNK_TARGET_CHARS = 2200
CHUNK_OVERLAP_CHARS = 250


class SignalBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceDocument:
    file_id: str
    source_tr: str
    document_family: str
    title: str
    relative_path: str
    absolute_path: str
    suffix: str
    size_bytes: int
    modified_utc: str
    sha256: str
    extraction_status: str
    text: str


@dataclass(frozen=True)
class SignalRecord:
    signal_id: str
    source_tr: str
    document_family: str
    title: str
    relative_path: str
    chunk_index: int
    section_label: str
    signal_types: List[str]
    structured_summary: str
    excerpt: str
    definitions: List[str]
    rules: List[str]
    constraints: List[str]
    lifecycle_logic: List[str]
    commands: List[str]
    code_or_scripts: List[str]
    naming_and_ids: List[str]
    governance_flags: Dict[str, Any]
    lifecycle_state: str
    authorization_scope: Dict[str, bool]
    lineage: Dict[str, Any]


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _extract_docx_text(path: Path) -> Tuple[str, str]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            xml_bytes = zf.read("word/document.xml")
    except Exception as exc:
        return "", f"docx_extract_failed:{exc}"

    try:
        root = ET.fromstring(xml_bytes)
    except Exception as exc:
        return "", f"docx_xml_parse_failed:{exc}"

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: List[str] = []
    for para in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in para.findall(".//w:t", namespace)]
        paragraph_text = "".join(texts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)

    return _normalize_whitespace("\n\n".join(paragraphs)), "ok"


def _extract_pdf_text(path: Path) -> Tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        return "", f"pdf_dependency_missing:{exc}"

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        return "", f"pdf_open_failed:{exc}"

    pages: List[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text.strip():
            pages.append(page_text.strip())

    return _normalize_whitespace("\n\n".join(pages)), "ok"


def _extract_md_text(path: Path) -> Tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            return "", f"md_read_failed:{exc}"
    except Exception as exc:
        return "", f"md_read_failed:{exc}"

    return _normalize_whitespace(text), "ok"


def _extract_text(path: Path) -> Tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix == ".md":
        return _extract_md_text(path)
    return "", "unsupported_suffix"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_files(root: Path) -> List[Path]:
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    return sorted(files, key=lambda p: str(p.relative_to(root)).lower())


def _build_file_id(relative_path: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "-", relative_path).strip("-").lower()
    return f"doc-{token}"


def _derive_title(path: Path) -> str:
    stem = path.stem
    stem = stem.replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def _detect_source_tr(path: Path, root: Path) -> Tuple[str, str]:
    rel = str(path.relative_to(root)).replace("\\", "/")
    parts = path.relative_to(root).parts
    name_upper = path.name.upper()
    rel_upper = rel.upper()

    if parts and parts[0].lower() == ACCESS_MODE_DIRNAME:
        return "TR-006", "access_mode"
    if "TR-006" in name_upper or "TR-006" in rel_upper or "ACCESS-MODE" in name_upper or "ACCESS_MODE" in name_upper:
        return "TR-006", "access_mode"

    match = re.search(r"TR-(\d{3})", name_upper)
    if match:
        return f"TR-{match.group(1)}", "tr"

    return "TR-UNKNOWN", "tr"


def _build_source_document(path: Path, root: Path) -> SourceDocument:
    stat = path.stat()
    relative_path = str(path.relative_to(root)).replace("\\", "/")
    text, extraction_status = _extract_text(path)
    modified_utc = (
        datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    source_tr, document_family = _detect_source_tr(path, root)

    return SourceDocument(
        file_id=_build_file_id(relative_path),
        source_tr=source_tr,
        document_family=document_family,
        title=_derive_title(path),
        relative_path=relative_path,
        absolute_path=str(path.resolve()),
        suffix=path.suffix.lower(),
        size_bytes=stat.st_size,
        modified_utc=modified_utc,
        sha256=_sha256_file(path),
        extraction_status=extraction_status,
        text=text,
    )


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _chunk_text(text: str, target_chars: int = CHUNK_TARGET_CHARS, overlap_chars: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    paras = _paragraphs(text)
    if not paras:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paras:
        para_len = len(para)
        if current and current_len + para_len + 2 > target_chars:
            chunk = "\n\n".join(current).strip()
            if chunk:
                chunks.append(chunk)

            if overlap_chars > 0:
                overlap_block: List[str] = []
                overlap_len = 0
                for existing in reversed(current):
                    overlap_block.insert(0, existing)
                    overlap_len += len(existing) + 2
                    if overlap_len >= overlap_chars:
                        break
                current = overlap_block[:]
                current_len = sum(len(x) + 2 for x in current)
            else:
                current = []
                current_len = 0

        current.append(para)
        current_len += para_len + 2

    final_chunk = "\n\n".join(current).strip()
    if final_chunk:
        chunks.append(final_chunk)

    return chunks


def _guess_section_label(chunk: str) -> str:
    first_lines = [line.strip() for line in chunk.splitlines()[:8] if line.strip()]
    for line in first_lines:
        if re.match(r"^(\d+(\.\d+)*|chapter\s+\d+|section\s+\d+)\b", line, flags=re.IGNORECASE):
            return line[:160]
        if len(line) <= 120 and not line.endswith("."):
            return line[:160]
    return "unlabeled_section"


def _extract_definitions(chunk: str) -> List[str]:
    results: List[str] = []

    for line in chunk.splitlines():
        clean = line.strip()
        if re.match(r"^[A-Z][A-Za-z0-9 _/\-\(\)]{2,60}$", clean) and not clean.endswith("."):
            # potential term heading
            continue

        if re.search(r"\b(is defined as|refers to|means|is the)\b", clean, flags=re.IGNORECASE):
            results.append(clean)

        if re.match(r"^[A-Z][A-Za-z0-9 _/\-]{1,40}:\s+", clean):
            results.append(clean)

    return _dedupe_preserve_order(results)


def _extract_rules(chunk: str) -> List[str]:
    results: List[str] = []
    for sentence in _split_sentences(chunk):
        if re.search(r"\b(shall|should|must|required|may not|must not|do not|does not permit|is not permitted)\b", sentence, flags=re.IGNORECASE):
            results.append(sentence)
    return _dedupe_preserve_order(results)


def _extract_constraints(chunk: str) -> List[str]:
    results: List[str] = []
    for sentence in _split_sentences(chunk):
        if re.search(
            r"\b(constraint|constraints|boundary|boundaries|out of scope|not in scope|prohibited|not permitted|cannot|must not|does not imply|non-authoritative|non-normative|exclusive|only)\b",
            sentence,
            flags=re.IGNORECASE,
        ):
            results.append(sentence)
    return _dedupe_preserve_order(results)


def _extract_lifecycle_logic(chunk: str) -> List[str]:
    results: List[str] = []
    for sentence in _split_sentences(chunk):
        if re.search(
            r"\b(lifecycle|state[_ ]?1|state[_ ]?2|state[_ ]?3|promotion|freeze|frozen|draft state|populated state|inspection-ready|routing|onboarding|transition)\b",
            sentence,
            flags=re.IGNORECASE,
        ):
            results.append(sentence)
    return _dedupe_preserve_order(results)


def _extract_commands(chunk: str) -> List[str]:
    results: List[str] = []

    fenced = re.findall(r"```(?:powershell|bash|cmd|shell)?\s*(.*?)```", chunk, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped:
                results.append(stripped)

    for line in chunk.splitlines():
        stripped = line.strip()
        if re.match(r"^(py|python|pip|Copy-Item|Get-ChildItem|Select-String|type|dir|cd)\b", stripped, flags=re.IGNORECASE):
            results.append(stripped)

    return _dedupe_preserve_order(results)


def _extract_code_or_scripts(chunk: str) -> List[str]:
    results: List[str] = []

    fenced = re.findall(r"```(?:python|json|powershell|bash|cmd|yaml|md|text)?\s*(.*?)```", chunk, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        block = block.strip()
        if block:
            results.append(block[:4000])

    for line in chunk.splitlines():
        stripped = line.strip()
        if re.search(r"\.py\b|scripts[\\/]", stripped, flags=re.IGNORECASE):
            results.append(stripped)

    return _dedupe_preserve_order(results)


def _extract_naming_and_ids(chunk: str) -> List[str]:
    results: List[str] = []
    patterns = [
        r"\bAPOD-TR-\d{3}(?:-E\.\d+)?\b",
        r"\bTR-\d{3}\b",
        r"\bID[_ -]?[123]\b",
        r"\bSTATE[_ -]?[123]\b",
        r"\bCSC\b",
        r"\bUGCCMT\b",
        r"\bQ-Pathformer\b",
        r"\bAccess[- ]PoD\b",
        r"\bWorking-PoD\b",
        r"\bdataset_passport_id\b",
        r"\brun_id\b",
        r"\bsignal_id\b",
    ]

    found: List[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, chunk, flags=re.IGNORECASE))

    for line in chunk.splitlines():
        stripped = line.strip()
        if re.search(r"\b(identifier|title|document identifier|phase seal|status)\b", stripped, flags=re.IGNORECASE):
            found.append(stripped)

    return _dedupe_preserve_order(found)


def _split_sentences(text: str) -> List[str]:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[\.\?\!])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        key = item.strip()
        if not key:
            continue
        lowered = key.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        output.append(key)
    return output


def _detect_signal_types(
    definitions: List[str],
    rules: List[str],
    constraints: List[str],
    lifecycle_logic: List[str],
    commands: List[str],
    code_or_scripts: List[str],
    naming_and_ids: List[str],
) -> List[str]:
    mapping = [
        ("definition", definitions),
        ("rule", rules),
        ("constraint", constraints),
        ("lifecycle_logic", lifecycle_logic),
        ("command", commands),
        ("code_or_script", code_or_scripts),
        ("naming_or_id", naming_and_ids),
    ]
    return [name for name, values in mapping if values]


def _build_summary(
    section_label: str,
    definitions: List[str],
    rules: List[str],
    constraints: List[str],
    lifecycle_logic: List[str],
    commands: List[str],
    code_or_scripts: List[str],
    naming_and_ids: List[str],
) -> str:
    parts: List[str] = [f"Section: {section_label}"]

    if definitions:
        parts.append(f"Definitions: {len(definitions)}")
    if rules:
        parts.append(f"Rules: {len(rules)}")
    if constraints:
        parts.append(f"Constraints: {len(constraints)}")
    if lifecycle_logic:
        parts.append(f"Lifecycle logic: {len(lifecycle_logic)}")
    if commands:
        parts.append(f"Commands: {len(commands)}")
    if code_or_scripts:
        parts.append(f"Code/scripts: {len(code_or_scripts)}")
    if naming_and_ids:
        parts.append(f"Naming/IDs: {len(naming_and_ids)}")

    return " | ".join(parts)


def _build_signal_id(doc: SourceDocument, chunk_index: int) -> str:
    base = f"{doc.source_tr}|{doc.relative_path}|{chunk_index}"
    token = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"signal-{token}"


def _governance_flags() -> Dict[str, Any]:
    return {
        "signals_not_decisions": True,
        "non_authoritative": True,
        "non_certifying": True,
        "requires_validation": True,
        "promotion_blocked": True,
        "context_bound": True,
    }


def _authorization_scope() -> Dict[str, bool]:
    return {
        "runtime_reasoning": True,
        "synthetic_generation": True,
        "fine_tuning": False,
        "external_training": False,
    }


def _build_lineage(doc: SourceDocument) -> Dict[str, Any]:
    return {
        "source_file_id": doc.file_id,
        "source_relative_path": doc.relative_path,
        "source_sha256": doc.sha256,
        "source_extraction_status": doc.extraction_status,
    }


def _build_signals_for_document(doc: SourceDocument) -> List[SignalRecord]:
    if not doc.text.strip():
        return []

    chunks = _chunk_text(doc.text)
    signals: List[SignalRecord] = []

    for idx, chunk in enumerate(chunks, start=1):
        section_label = _guess_section_label(chunk)
        definitions = _extract_definitions(chunk)
        rules = _extract_rules(chunk)
        constraints = _extract_constraints(chunk)
        lifecycle_logic = _extract_lifecycle_logic(chunk)
        commands = _extract_commands(chunk)
        code_or_scripts = _extract_code_or_scripts(chunk)
        naming_and_ids = _extract_naming_and_ids(chunk)

        signal_types = _detect_signal_types(
            definitions=definitions,
            rules=rules,
            constraints=constraints,
            lifecycle_logic=lifecycle_logic,
            commands=commands,
            code_or_scripts=code_or_scripts,
            naming_and_ids=naming_and_ids,
        )

        if not signal_types:
            continue

        summary = _build_summary(
            section_label=section_label,
            definitions=definitions,
            rules=rules,
            constraints=constraints,
            lifecycle_logic=lifecycle_logic,
            commands=commands,
            code_or_scripts=code_or_scripts,
            naming_and_ids=naming_and_ids,
        )

        signals.append(
            SignalRecord(
                signal_id=_build_signal_id(doc, idx),
                source_tr=doc.source_tr,
                document_family=doc.document_family,
                title=doc.title,
                relative_path=doc.relative_path,
                chunk_index=idx,
                section_label=section_label,
                signal_types=signal_types,
                structured_summary=summary,
                excerpt=chunk[:2200],
                definitions=definitions[:20],
                rules=rules[:20],
                constraints=constraints[:20],
                lifecycle_logic=lifecycle_logic[:20],
                commands=commands[:20],
                code_or_scripts=code_or_scripts[:10],
                naming_and_ids=naming_and_ids[:30],
                governance_flags=_governance_flags(),
                lifecycle_state="STATE_3",
                authorization_scope=_authorization_scope(),
                lineage=_build_lineage(doc),
            )
        )

    return signals


def build_signal_payload(input_root: Path) -> Dict[str, Any]:
    root = input_root.expanduser().resolve()
    if not root.exists():
        raise SignalBuildError(f"input_root_not_found:{root}")
    if not root.is_dir():
        raise SignalBuildError(f"input_root_must_be_directory:{root}")

    files = _scan_files(root)
    if not files:
        raise SignalBuildError(f"no_supported_files_found:{root}")

    docs = [_build_source_document(path, root) for path in files]
    all_signals: List[SignalRecord] = []

    for doc in docs:
        all_signals.extend(_build_signals_for_document(doc))

    signal_dicts = [asdict(sig) for sig in all_signals]

    by_tr: Dict[str, int] = {}
    for signal in all_signals:
        by_tr[signal.source_tr] = by_tr.get(signal.source_tr, 0) + 1

    extraction_failures = [doc.file_id for doc in docs if doc.extraction_status != "ok"]

    return {
        "signal_corpus_version": "v1.1",
        "generated_at_utc": _utc_now_iso(),
        "input_root": str(root),
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "summary": {
            "document_count": len(docs),
            "signal_count": len(all_signals),
            "signals_by_tr": dict(sorted(by_tr.items())),
            "extraction_failures": extraction_failures,
        },
        "signals": signal_dicts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build structured signals from docs/TR, including access_mode and markdown files."
    )
    parser.add_argument("--input-root", type=Path, required=True, help="Path to docs/TR")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path")
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        required=False,
        help="Optional output JSONL path",
    )
    args = parser.parse_args()

    try:
        payload = build_signal_payload(args.input_root)

        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")

        if args.jsonl_output:
            jsonl_path = args.jsonl_output.expanduser().resolve()
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with jsonl_path.open("w", encoding="utf-8") as handle:
                for signal in payload["signals"]:
                    handle.write(json.dumps(signal, ensure_ascii=False) + "\n")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "output": str(output_path),
                    "jsonl_output": str(args.jsonl_output.expanduser().resolve()) if args.jsonl_output else None,
                    "document_count": payload["summary"]["document_count"],
                    "signal_count": payload["summary"]["signal_count"],
                    "signals_by_tr": payload["summary"]["signals_by_tr"],
                    "extraction_failures": payload["summary"]["extraction_failures"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    except SignalBuildError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())