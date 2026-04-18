#!/usr/bin/env python3
"""
build_tr_corpus_json.py

Build a single JSON corpus from the APOD technical reports under docs/TR,
including nested access_mode content and markdown files.

Primary behavior:
- scans a root directory for PDF, DOCX, and MD files
- groups records into categories: tr and access_mode
- computes stable file metadata (size, modified time, sha256)
- extracts text from PDF, DOCX, and MD files when possible
- emits one combined JSON file for downstream inspection / dataset prep

Example:
    py scripts\build_tr_corpus_json.py ^
      --input-root docs\TR ^
      --output datasets\corpora\tr_corpus.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md"}
ACCESS_MODE_DIRNAME = "access_mode"


class CorpusBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileRecord:
    file_id: str
    category: str
    filename: str
    relative_path: str
    absolute_path: str
    suffix: str
    size_bytes: int
    modified_utc: str
    sha256: str
    title: str
    extraction_status: str
    text: str
    text_char_count: int
    page_count: Optional[int]


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _derive_title(path: Path) -> str:
    stem = path.stem
    stem = stem.replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def _extract_docx_text(path: Path) -> Tuple[str, Optional[int], str]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            xml_bytes = zf.read("word/document.xml")
    except Exception as exc:
        return "", None, f"docx_extract_failed:{exc}"

    try:
        root = ET.fromstring(xml_bytes)
    except Exception as exc:
        return "", None, f"docx_xml_parse_failed:{exc}"

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: List[str] = []
    for para in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in para.findall(".//w:t", namespace)]
        paragraph_text = "".join(texts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)

    text = _normalize_whitespace("\n\n".join(paragraphs))
    return text, None, "ok"


def _extract_pdf_text(path: Path) -> Tuple[str, Optional[int], str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        return "", None, f"pdf_dependency_missing:{exc}"

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        return "", None, f"pdf_open_failed:{exc}"

    pages: List[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text.strip():
            pages.append(page_text.strip())

    text = _normalize_whitespace("\n\n".join(pages))
    return text, len(reader.pages), "ok"


def _extract_md_text(path: Path) -> Tuple[str, Optional[int], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            return "", None, f"md_read_failed:{exc}"
    except Exception as exc:
        return "", None, f"md_read_failed:{exc}"

    return _normalize_whitespace(text), None, "ok"


def _extract_text(path: Path) -> Tuple[str, Optional[int], str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix == ".md":
        return _extract_md_text(path)
    return "", None, "unsupported_suffix"


def _classify(path: Path, root: Path) -> str:
    rel_parts = path.relative_to(root).parts
    if rel_parts and rel_parts[0].lower() == ACCESS_MODE_DIRNAME:
        return "access_mode"

    filename_upper = path.name.upper()
    if "TR-006" in filename_upper or "ACCESS-MODE" in filename_upper or "ACCESS_MODE" in filename_upper:
        return "access_mode"

    return "tr"


def _build_file_id(relative_path: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "-", relative_path).strip("-").lower()
    return f"doc-{token}"


def _scan_files(root: Path) -> List[Path]:
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    return sorted(files, key=lambda p: str(p.relative_to(root)).lower())


def _build_record(path: Path, root: Path) -> FileRecord:
    stat = path.stat()
    relative_path = str(path.relative_to(root)).replace("\\", "/")
    text, page_count, extraction_status = _extract_text(path)
    sha256 = _sha256_file(path)
    modified_utc = (
        datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    return FileRecord(
        file_id=_build_file_id(relative_path),
        category=_classify(path, root),
        filename=path.name,
        relative_path=relative_path,
        absolute_path=str(path.resolve()),
        suffix=path.suffix.lower(),
        size_bytes=stat.st_size,
        modified_utc=modified_utc,
        sha256=sha256,
        title=_derive_title(path),
        extraction_status=extraction_status,
        text=text,
        text_char_count=len(text),
        page_count=page_count,
    )


def build_corpus(input_root: Path) -> Dict[str, Any]:
    root = input_root.expanduser().resolve()
    if not root.exists():
        raise CorpusBuildError(f"input_root_not_found:{root}")
    if not root.is_dir():
        raise CorpusBuildError(f"input_root_must_be_directory:{root}")

    files = _scan_files(root)
    if not files:
        raise CorpusBuildError(f"no_supported_files_found:{root}")

    records = [_build_record(path, root) for path in files]

    grouped: Dict[str, List[Dict[str, Any]]] = {"tr": [], "access_mode": []}
    for record in records:
        grouped.setdefault(record.category, []).append(record.__dict__)

    extraction_failures = [r.file_id for r in records if r.extraction_status != "ok"]

    return {
        "corpus_version": "v1.1",
        "generated_at_utc": _utc_now_iso(),
        "input_root": str(root),
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "summary": {
            "document_count": len(records),
            "tr_count": len(grouped.get("tr", [])),
            "access_mode_count": len(grouped.get("access_mode", [])),
            "extraction_failures": extraction_failures,
            "total_text_characters": sum(r.text_char_count for r in records),
        },
        "documents": grouped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build one JSON corpus from docs/TR, including access_mode and markdown files."
    )
    parser.add_argument("--input-root", type=Path, required=True, help="Path to docs/TR")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path")
    args = parser.parse_args()

    try:
        payload = build_corpus(args.input_root)
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "output": str(output_path),
                    "document_count": payload["summary"]["document_count"],
                    "tr_count": payload["summary"]["tr_count"],
                    "access_mode_count": payload["summary"]["access_mode_count"],
                    "extraction_failures": payload["summary"]["extraction_failures"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    except CorpusBuildError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())