#!/usr/bin/env python3
"""Check tracked JSON/JSONL syntax without changes or schema-validity claims.

Use UTF-8 without BOM, unique object keys, and no NaN/Infinity literals.
Numbers stay as tokens: syntax is checked, not numeric ranges. JSONL must
contain at least one record, one JSON value per line, with no blank lines.
LF and CRLF work; one final newline is optional.

Historical exception: the exact path and SHA-256 in LEGACY_BLANK_LINES
identify one unchanged published example with blank lines 2 and 4. Only
those blank lines are tolerated; every nonblank record is still parsed.
Moving or changing that file removes the exception. Original bytes are
never rewritten, and new files receive no exception.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


LEGACY_BLANK_LINES = {
    "shared/schemas/access-mode/access_mode_training_governance_reference.example.jsonl":
        "a454bf925a89ce3115c08c3fd6ac07aa7a0232c7305a948e8be8ddd091eb7d9e",
}


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def reject_constant(token: str) -> None:
    raise ValueError(f"{token} is not a JSON number")


def parse_json(text: str) -> None:
    json.loads(
        text,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
        parse_int=str,
        parse_float=str,
    )


def parse_jsonl(text: str, allow_blank_lines: bool = False) -> tuple[int, list[int]]:
    if not text:
        raise ValueError("empty JSONL file; at least one record is required")
    # Split only on LF. Unicode line separators inside JSON strings are data.
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()  # A single final newline does not create a blank record.
    records = 0
    blanks: list[int] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            if allow_blank_lines:
                blanks.append(number)
                continue
            raise ValueError(f"JSONL line {number}: blank lines are not allowed")
        try:
            parse_json(line)
        except (ValueError, RecursionError) as error:
            raise ValueError(f"JSONL line {number}: {error}") from error
        records += 1
    if not records:
        raise ValueError("JSONL file has no records; at least one record is required")
    return records, blanks


def check_file(path: Path, relative_name: str) -> tuple[int, list[int]]:
    data = path.read_bytes()
    text = data.decode("utf-8")
    if text.startswith("\ufeff"):
        raise ValueError("UTF-8 byte-order mark is not allowed; use UTF-8 without BOM")
    if path.suffix.lower() == ".jsonl":
        allow_blanks = LEGACY_BLANK_LINES.get(relative_name) == hashlib.sha256(data).hexdigest()
        return parse_jsonl(text, allow_blank_lines=allow_blanks)
    parse_json(text)
    return 0, []


def tracked_json_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "-z"],
        check=True,
        capture_output=True,
    )
    return sorted(
        {
            name.decode("utf-8")
            for name in completed.stdout.split(b"\0")
            if name and name.lower().endswith((b".json", b".jsonl"))
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2],
        help="repository root (defaults to this script's repository)",
    )
    root = parser.parse_args(argv).root.resolve()
    try:
        paths = tracked_json_files(root)
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        print(f"FAIL: cannot list tracked JSON/JSONL files: {error}", file=sys.stderr)
        return 1
    if not paths:
        print("FAIL: no tracked JSON/JSONL files found", file=sys.stderr)
        return 1

    failures = records = json_files = jsonl_files = 0
    for name in paths:
        if name.lower().endswith(".jsonl"):
            jsonl_files += 1
        else:
            json_files += 1
        try:
            if not (root / name).resolve().is_relative_to(root):
                raise ValueError("JSON path resolves outside the repository")
            count, blanks = check_file(root / name, name)
            records += count
            if blanks:
                print(
                    f"NOTE: preserved historical JSONL blank lines {blanks}: {name} "
                    f"(SHA-256 {LEGACY_BLANK_LINES[name]}); nonblank records checked."
                )
        except (OSError, ValueError, RecursionError) as error:
            failures += 1
            print(f"FAIL: {name}: {error}", file=sys.stderr)
    if failures:
        print(f"FAIL: {failures} of {len(paths)} tracked JSON/JSONL files failed", file=sys.stderr)
        return 1
    print(
        f"PASS: {json_files} tracked JSON files and {jsonl_files} tracked JSONL files "
        f"({records} JSONL records) have valid UTF-8 JSON syntax, "
        "unique object keys, and no NaN/Infinity literals."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
