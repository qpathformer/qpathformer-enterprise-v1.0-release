#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10 Runtime Signal Emitter

Calls a local Ollama-served weighted model, enforces the enum-lock prompt contract,
converts the model response into a v0.2-dev signal record, applies deterministic
validation-readiness scoring, applies governance-first routing, and writes the
runtime signal artifact into artifacts/signals/runtime_generated/.

Purpose:
- remove bridge-mode overrides introduced during v9.9 bridge testing
- preserve STATE_3 non-authoritative runtime capture
- introduce real scoring, validation-readiness, and routing logic for STATE_3 -> STATE_2 review eligibility

Posture:
- ID_2 only
- non-authoritative
- runtime capture only
- no direct lifecycle promotion to STATE_1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))
ROOT_SCRIPTS_DIR = RUNTIME_DIR.parent
if str(ROOT_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_SCRIPTS_DIR))

from run_signal_validation import evaluate_validation_readiness
from run_signal_routing import route_signal
from update_run_registry import RegistryUpdateError, register_run_reference
from path_layout import (
    PATH2_RUNTIME_SIGNALS_ROOT,
    SHARED_RUN_REFERENCES_ROOT,
    SHARED_RUN_REGISTRY_PATH,
    SHARED_SIGNAL_DATASET_PASSPORT_PATH,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SIGNAL_ROOT = PATH2_RUNTIME_SIGNALS_ROOT
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gpt-oss:20b"
DEFAULT_MODEL_VERSION = "v10.0-runtime-routing-validation"
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_WORKFLOW_ID = "path2_runtime_signal_emitter"
DEFAULT_PATH_ID = "path_2_access_mode_canonical"
DEFAULT_RUN_REFERENCE_ROOT = SHARED_RUN_REFERENCES_ROOT
DEFAULT_REGISTRY_PATH = SHARED_RUN_REGISTRY_PATH
DEFAULT_DATASET_PASSPORT_REF = SHARED_SIGNAL_DATASET_PASSPORT_PATH


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def normalize_token(raw: str, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "-", str(raw).strip()).strip("-").lower()
    return token or fallback


def load_dataset_passport_reference(path: Path) -> Dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Dataset passport reference must be a JSON object: {path}")
    return payload


def build_contract_prompt(user_prompt: str) -> str:
    return f"""Return ONLY valid JSON. No text before or after.

Use exactly this schema:
{{
  "role": "Q_PATHFORMER_ENTERPRISE_TIER",
  "primary_function": "string",
  "governance_flags": ["string"],
  "lifecycle_entry_state": "STATE_3",
  "evaluation_focus": ["string"]
}}

Rules:
- role must be exactly "Q_PATHFORMER_ENTERPRISE_TIER"
- lifecycle_entry_state must be exactly "STATE_3"
- governance_flags must be an array of strings
- evaluation_focus must be an array of strings
- governance_flags may only use these values:
  ["PROVISIONAL","CONTEXT_BOUND","REQUIRES_VALIDATION","PROMOTION_BLOCKED"]
- Do not add extra keys
- Do not use markdown
- Do not invent compliance, certification, approval, or trust claims

Context:
Q-Pathformer enterprise tier is the control and structuring layer for runtime reasoning signals.
It is non-authoritative.
It applies governance-aware structuring.
All new runtime signals enter STATE_3 first.
STATE_2 is validation readiness.
STATE_1 is governed dataset integration.

Task:
{user_prompt}
"""


def call_ollama(
    *,
    url: str,
    model: str,
    prompt: str,
    timeout_seconds: int,
) -> Dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to reach Ollama endpoint: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned non-JSON response: {raw}") from exc

    if "response" not in parsed:
        raise RuntimeError(f"Ollama response missing 'response' field: {parsed}")

    return parsed


def parse_model_response_text(response_text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Model response was not valid JSON under the contract prompt."
        ) from exc

    required_keys = {
        "role",
        "primary_function",
        "governance_flags",
        "lifecycle_entry_state",
        "evaluation_focus",
    }
    missing = required_keys - set(parsed.keys())
    if missing:
        raise RuntimeError(f"Model response missing required keys: {sorted(missing)}")

    if parsed["role"] != "Q_PATHFORMER_ENTERPRISE_TIER":
        raise RuntimeError(f"Invalid role value: {parsed['role']}")

    if parsed["lifecycle_entry_state"] != "STATE_3":
        raise RuntimeError(
            f"Invalid lifecycle_entry_state: {parsed['lifecycle_entry_state']}"
        )

    if not isinstance(parsed["governance_flags"], list):
        raise RuntimeError("governance_flags must be an array")

    if not isinstance(parsed["evaluation_focus"], list):
        raise RuntimeError("evaluation_focus must be an array")

    return parsed


def normalize_tags(contract_payload: Dict[str, Any]) -> list[str]:
    tags = ["llm_generated", "enum_locked", "runtime_emitted"]

    governance_flags = contract_payload.get("governance_flags", []) or []
    evaluation_focus = contract_payload.get("evaluation_focus", []) or []

    for value in governance_flags:
        normalized = str(value).strip().lower()
        if normalized:
            tags.append(normalized)

    for value in evaluation_focus:
        normalized = str(value).strip().lower().replace(" ", "_")
        if normalized:
            tags.append(normalized)

    deduped: list[str] = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            deduped.append(tag)
            seen.add(tag)

    return deduped


def build_structured_summary(contract_payload: Dict[str, Any]) -> str:
    primary_function = str(contract_payload.get("primary_function", "") or "").strip()
    primary_function = primary_function.rstrip(". ")
    evaluation_focus = contract_payload.get("evaluation_focus", []) or []

    focus_text = ", ".join(str(item) for item in evaluation_focus if str(item).strip())
    if focus_text:
        return (
            f"{primary_function}. Evaluation focus: {focus_text}. "
            f"Lifecycle entry remains STATE_3 under provisional runtime containment."
        )
    return (
        f"{primary_function}. Lifecycle entry remains STATE_3 "
        f"under provisional runtime containment."
    )


def build_signal_record(
    *,
    contract_payload: Dict[str, Any],
    raw_prompt: str,
    model: str,
    session_id: str,
    model_version: str,
) -> Dict[str, Any]:
    return {
        "signal_id": str(uuid4()),
        "timestamp": utc_now_iso(),
        "access_mode_primary": "ID_2",
        "schema_version": "v0.2-dev",
        "interaction_type": "enterprise_only",
        "session_id": session_id,
        "model": {
            "model_id": model,
            "parameter_class": "20B",
            "role": "enterprise",
            "endpoint_type": "local",
            "invocation_reason": "runtime_structuring",
            "version": model_version,
        },
        "source": {
            "initiator": "enterprise-tier",
            "amplifier": None,
        },
        "input": {
            "prompt": raw_prompt,
        },
        "signal": {
            "raw_output": json.dumps(contract_payload, ensure_ascii=False),
            "structured_summary": build_structured_summary(contract_payload),
            "tags": normalize_tags(contract_payload),
        },
        "metrics": {
            "coherence": 0.0,
            "novelty": 0.0,
            "stability": 0.0,
            "ambiguity": 0.0,
        },
        "maturity": "LEVEL_0",
        "governance_flags": {
            "provisional": True,
            "context_bound": True,
            "requires_validation": True,
            "promotion_blocked": True,
        },
        "authorization": {
            "state2_candidate_allowed": True,
            "fine_tuning_allowed": False,
            "human_review_required": True,
        },
        "validation": {
            "candidate_for_validation": False,
            "validation_requested": False,
        },
        "lifecycle": {
            "state": "STATE_3",
            "eligible_for_state_2": False,
            "routing_decision": "HOLD_IN_STATE_3",
        },
    }


def finalize_signal_record(signal_record: Dict[str, Any]) -> Dict[str, Any]:
    validation_result = evaluate_validation_readiness(signal_record)
    signal_record["metrics"] = validation_result["metrics"]
    signal_record["maturity"] = validation_result["maturity"]
    signal_record["validation"] = validation_result["validation"]

    routed_record = route_signal(signal_record)
    return routed_record


def write_signal(path_root: Path, signal_record: Dict[str, Any]) -> tuple[Path, Path]:
    path_root.mkdir(parents=True, exist_ok=True)

    stem = f"signal_runtime_{timestamp_token()}_{signal_record['signal_id'].split('-')[0]}"
    signal_path = path_root / f"{stem}.json"
    routing_log_path = path_root / f"{stem}.routing.json"

    signal_path.write_text(
        json.dumps(signal_record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    routing_log = {
        "signal_id": signal_record["signal_id"],
        "timestamp": signal_record["timestamp"],
        "source_state": "STATE_3",
        "target_state": signal_record["lifecycle"].get("target_state", "STATE_3"),
        "decision": signal_record["lifecycle"]["routing_decision"],
        "eligible_for_state_2": signal_record["lifecycle"]["eligible_for_state_2"],
        "reasons": signal_record["lifecycle"].get("routing_reasons", []),
        "metrics": signal_record["metrics"],
        "maturity": signal_record["maturity"],
        "model": signal_record["model"],
        "interaction_type": signal_record["interaction_type"],
    }

    routing_log_path.write_text(
        json.dumps(routing_log, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return signal_path, routing_log_path


def build_runtime_run_id(session_id: str, signal_id: str) -> str:
    session_token = normalize_token(session_id, "runtime-session")
    signal_token = normalize_token(signal_id.split("-")[0], "signal")
    return f"RTRUN-{session_token}-{timestamp_token()}-{signal_token}"


def build_runtime_run_status(signal_record: Dict[str, Any]) -> str:
    decision = str(
        signal_record.get("lifecycle", {}).get("routing_decision", "") or ""
    )
    if decision == "SEND_TO_STATE_2_REVIEW":
        return "success"
    return "success_with_findings"


def build_runtime_run_reference(
    *,
    signal_record: Dict[str, Any],
    signal_path: Path,
    routing_log_path: Path,
    dataset_passport_ref: Dict[str, Any],
    workflow_id: str,
    path_id: str,
) -> Dict[str, Any]:
    dataset_passport_id = str(
        dataset_passport_ref.get("dataset_passport_id")
        or dataset_passport_ref.get("dataset_id")
        or ""
    ).strip()
    if not dataset_passport_id:
        raise RuntimeError(
            "Dataset passport reference missing dataset_passport_id or dataset_id."
        )
    routing_ref = str(dataset_passport_ref.get("routing_ref") or "").strip()
    authorization_ref = str(
        dataset_passport_ref.get("authorization_ref") or ""
    ).strip()
    run_id = build_runtime_run_id(
        signal_record["session_id"],
        signal_record["signal_id"],
    )

    return {
        "run_reference_version": "qpds_runtime_signal_run_reference_v1.0",
        "run_id": run_id,
        "run_type": "runtime_signal_emitter",
        "workflow_id": workflow_id,
        "path_id": path_id,
        "signal_id": signal_record["signal_id"],
        "session_id": signal_record["session_id"],
        "dataset_passport_id": dataset_passport_id,
        "routing_ids": [routing_ref] if routing_ref else [],
        "lifecycle_state": signal_record["lifecycle"]["state"],
        "target_state": signal_record["lifecycle"].get(
            "target_state",
            signal_record["lifecycle"]["state"],
        ),
        "run_status": build_runtime_run_status(signal_record),
        "recorded_at_utc": utc_now_iso(),
        "model": {
            "model_id": signal_record["model"]["model_id"],
            "model_version": signal_record["model"]["version"],
            "parameter_class": signal_record["model"]["parameter_class"],
            "endpoint_type": signal_record["model"]["endpoint_type"],
        },
        "source_context": {
            "dataset_passport_ref": dataset_passport_id or None,
            "routing_ref": routing_ref or None,
            "authorization_ref": authorization_ref or None,
        },
        "routing": {
            "decision": signal_record["lifecycle"]["routing_decision"],
            "eligible_for_state_2": signal_record["lifecycle"]["eligible_for_state_2"],
            "reasons": signal_record["lifecycle"].get("routing_reasons", []),
        },
        "validation": signal_record["validation"],
        "maturity": signal_record["maturity"],
        "metrics": signal_record["metrics"],
        "outputs": {
            "signal_path": str(signal_path),
            "routing_log_path": str(routing_log_path),
        },
        "inspection_ready": True,
        "frozen_output_queryable": False,
        "notes": [
            "Live v1.0 Path 2 runtime signal registration.",
            "Signal remains non-authoritative and enters STATE_3 first.",
        ],
    }


def write_run_reference(path_root: Path, run_reference: Dict[str, Any]) -> Path:
    path_root.mkdir(parents=True, exist_ok=True)
    run_reference_path = (
        path_root / f"{run_reference['run_id']}.runtime_signal_run_reference.json"
    )
    write_json(run_reference_path, run_reference)
    return run_reference_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit a runtime-generated Q-Pathformer signal artifact from a local Ollama model."
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="User/runtime task prompt to structure into a signal.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Local Ollama model name. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        help=f"Ollama generate endpoint. Default: {DEFAULT_OLLAMA_URL}",
    )
    parser.add_argument(
        "--signal-root",
        default=str(DEFAULT_SIGNAL_ROOT),
        help=f"Output folder for runtime signal artifacts. Default: {DEFAULT_SIGNAL_ROOT}",
    )
    parser.add_argument(
        "--session-id",
        default="llm-runtime-session",
        help="Session identifier recorded into the signal.",
    )
    parser.add_argument(
        "--dataset-passport-ref",
        default=str(DEFAULT_DATASET_PASSPORT_REF),
        help=(
            "Shared dataset passport reference used for runtime registration. "
            f"Default: {DEFAULT_DATASET_PASSPORT_REF}"
        ),
    )
    parser.add_argument(
        "--run-reference-root",
        default=str(DEFAULT_RUN_REFERENCE_ROOT),
        help=(
            "Output folder for runtime run-reference JSON files. "
            f"Default: {DEFAULT_RUN_REFERENCE_ROOT}"
        ),
    )
    parser.add_argument(
        "--registry-path",
        default=str(DEFAULT_REGISTRY_PATH),
        help=f"Shared run registry JSON path. Default: {DEFAULT_REGISTRY_PATH}",
    )
    parser.add_argument(
        "--workflow-id",
        default=DEFAULT_WORKFLOW_ID,
        help=f"Workflow id recorded into the runtime run reference. Default: {DEFAULT_WORKFLOW_ID}",
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_MODEL_VERSION,
        help=f"Recorded model version label. Default: {DEFAULT_MODEL_VERSION}",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout for Ollama request. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--print-response-only",
        action="store_true",
        help="Print the contract JSON response and exit without writing a signal file.",
    )
    parser.add_argument(
        "--skip-registry-update",
        action="store_true",
        help="Write the run-reference file but skip the shared registry upsert.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    contract_prompt = build_contract_prompt(args.prompt)

    try:
        ollama_result = call_ollama(
            url=args.ollama_url,
            model=args.model,
            prompt=contract_prompt,
            timeout_seconds=args.timeout_seconds,
        )
        contract_payload = parse_model_response_text(ollama_result["response"])
    except RuntimeError as exc:
        sys.stderr.write(f"[RUNTIME EMIT FAILED] {exc}\n")
        return 1

    if args.print_response_only:
        json.dump(contract_payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    try:
        dataset_passport_ref = load_dataset_passport_reference(
            Path(args.dataset_passport_ref).expanduser().resolve()
        )
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        sys.stderr.write(f"[RUNTIME REGISTER FAILED] {exc}\n")
        return 1

    signal_record = build_signal_record(
        contract_payload=contract_payload,
        raw_prompt=args.prompt,
        model=args.model,
        session_id=args.session_id,
        model_version=args.model_version,
    )

    signal_record = finalize_signal_record(signal_record)

    signal_path, routing_log_path = write_signal(
        Path(args.signal_root).expanduser().resolve(),
        signal_record,
    )

    run_reference = build_runtime_run_reference(
        signal_record=signal_record,
        signal_path=signal_path,
        routing_log_path=routing_log_path,
        dataset_passport_ref=dataset_passport_ref,
        workflow_id=args.workflow_id,
        path_id=DEFAULT_PATH_ID,
    )
    run_reference_path = write_run_reference(
        Path(args.run_reference_root).expanduser().resolve(),
        run_reference,
    )

    registry_action = None
    if not args.skip_registry_update:
        try:
            registry_action, _, registry_payload = register_run_reference(
                run_reference,
                run_reference_path=run_reference_path,
                registry_path=Path(args.registry_path).expanduser().resolve(),
            )
        except (OSError, RegistryUpdateError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"[RUNTIME REGISTER FAILED] {exc}\n")
            return 1
        registry_path = Path(args.registry_path).expanduser().resolve()
    else:
        registry_payload = None
        registry_path = Path(args.registry_path).expanduser().resolve()

    result = {
        "status": "completed",
        "run_id": run_reference["run_id"],
        "signal_id": signal_record["signal_id"],
        "output_path": str(signal_path),
        "routing_log_path": str(routing_log_path),
        "run_reference_path": str(run_reference_path),
        "registry_path": str(registry_path),
        "registry_action": registry_action,
        "session_id": signal_record["session_id"],
        "dataset_passport_id": run_reference["dataset_passport_id"],
        "model_id": signal_record["model"]["model_id"],
        "model_version": signal_record["model"]["version"],
        "lifecycle_state": signal_record["lifecycle"]["state"],
        "routing_decision": signal_record["lifecycle"]["routing_decision"],
        "eligible_for_state_2": signal_record["lifecycle"]["eligible_for_state_2"],
        "timestamp": signal_record["timestamp"],
    }
    if registry_payload is not None:
        result["registry_updated_at_utc"] = registry_payload["updated_at_utc"]

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
