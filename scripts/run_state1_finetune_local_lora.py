#!/usr/bin/env python3
"""
run_state1_finetune.py

Deterministic v14 fine-tuning execution entrypoint for STATE_1 training packages.

Core contract:
- consume only a v12 training package directory
- require exactly:
    train.sft.jsonl
    state1_training_manifest.json
    training_backend_profile.json
- validate package linkage, record counts, and backend compatibility
- emit reproducible run artifacts under artifacts/finetune_runs/<run_id>/

This script does not:
- modify the training package
- update dataset registries
- override authorization flags
- accept raw dataset paths instead of --training-package
- mutate lifecycle state

Design note:
- v14 remains deterministic at the execution boundary.
- It accepts an explicit --training-package only.
- It does not auto-discover or auto-select the latest package.

Backends:
- dry-run validation path
- local stub path (legacy)
- local_lora real adapter-training path using transformers + peft
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import platform
import random
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from path_layout import (
    PATH1_ROOT,
    PATH1_RUNS_ROOT,
    PATH1_RUN_LOGS_ROOT,
    PATH2_ROOT,
    PATH2_RUN_LOGS_ROOT,
)

TRAIN_FILE_NAME = "train.sft.jsonl"
MANIFEST_FILE_NAME = "state1_training_manifest.json"
BACKEND_PROFILE_FILE_NAME = "training_backend_profile.json"
DEFAULT_OUTPUT_ROOT = PATH1_RUNS_ROOT
DEFAULT_BACKEND = "local_lora"
DEFAULT_MODEL_DIR_NAME = "model"
DEFAULT_LOG_FILE_NAME = "training_log.json"
DEFAULT_RUN_MANIFEST_FILE_NAME = "finetune_run_manifest.json"
DEFAULT_PATH1_RUN_LOG_PREFIX = "path1_finetune_run_"
DEFAULT_PATH2_RUN_LOG_PREFIX = "path2_finetune_run_"
DEFAULT_CHECKPOINTS_DIR_NAME = "checkpoints"
DEFAULT_TRAINER_SUMMARY_FILE_NAME = "trainer_summary.json"
ALLOWED_TRAIN_KEYS = {"prompt", "completion", "messages", "input", "output", "text"}
DEFAULT_RANDOM_SEED = 42


class FineTuneExecutionError(RuntimeError):
    """Raised when v14 fine-tune execution cannot proceed safely."""


@dataclass(frozen=True)
class TrainingPackagePaths:
    root: Path
    train_file: Path
    manifest_file: Path
    backend_profile_file: Path


@dataclass(frozen=True)
class RunLogProfile:
    path_id: str
    logs_root: Path
    version_key: str
    output_key: str
    filename_prefix: str


@dataclass(frozen=True)
class EffectiveHyperparameters:
    max_steps: Optional[int]
    learning_rate: Optional[float]
    batch_size: Optional[int]


@dataclass(frozen=True)
class ResolvedBackendConfig:
    backend_name: str
    backend_profile_id: str
    model_base: str
    model_family: Optional[str]
    execution_mode: str
    supported_backends: List[str]
    compatible_package_states: List[str]
    backend_payload: Dict[str, Any]
    format_name: str
    prompt_field: str
    completion_field: str
    include_metadata: bool


@dataclass(frozen=True)
class ManifestSummary:
    dataset_version: str
    lifecycle_state: str
    record_count: int
    training_file_ref: str
    source_registry_state: Optional[str]
    source_registry_entry_id: Optional[str]
    dataset_passport_id: Optional[str]
    target_model: Dict[str, Any]
    authorization_posture: Dict[str, Any]


@dataclass(frozen=True)
class TrainingExample:
    prompt: str
    completion: str
    metadata: Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _normalize_path(path_value: Path | str) -> Path:
    return Path(path_value).expanduser().resolve()


PATH1_RUN_LOG_PROFILE = RunLogProfile(
    path_id="path_1_tr_corpus_reference",
    logs_root=PATH1_RUN_LOGS_ROOT,
    version_key="path1_run_log_version",
    output_key="path1_run_log",
    filename_prefix=DEFAULT_PATH1_RUN_LOG_PREFIX,
)

PATH2_RUN_LOG_PROFILE = RunLogProfile(
    path_id="path_2_access_mode_canonical",
    logs_root=PATH2_RUN_LOGS_ROOT,
    version_key="path2_run_log_version",
    output_key="path2_run_log",
    filename_prefix=DEFAULT_PATH2_RUN_LOG_PREFIX,
)


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as exc:
        raise FineTuneExecutionError(f"json_not_found:{path}") from exc
    except json.JSONDecodeError as exc:
        raise FineTuneExecutionError(f"json_invalid:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise FineTuneExecutionError(f"json_root_must_be_object:{path}")
    return payload


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _write_placeholder_model_artifact(model_dir: Path, payload: Dict[str, Any]) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    placeholder_path = model_dir / "model_stub.json"
    _write_json(placeholder_path, payload)
    return placeholder_path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_run_log_profile(package_root: Path) -> RunLogProfile:
    normalized_root = _normalize_path(package_root)
    if _is_relative_to(normalized_root, PATH1_ROOT):
        return PATH1_RUN_LOG_PROFILE
    if _is_relative_to(normalized_root, PATH2_ROOT):
        return PATH2_RUN_LOG_PROFILE
    raise FineTuneExecutionError(f"unsupported_training_package_path_for_top_level_run_log:{normalized_root}")


def _require_dict(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise FineTuneExecutionError(f"{label}_must_be_object")
    return value


def _require_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise FineTuneExecutionError(f"{label}_must_be_array")
    return value


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FineTuneExecutionError(f"{label}_must_be_non_empty_string")
    return value.strip()


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise FineTuneExecutionError(f"{label}_must_be_boolean")
    return value


def _require_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise FineTuneExecutionError(f"{label}_must_be_integer")
    return value


def _optional_str(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_int(value: Any, label: str) -> Optional[int]:
    if value is None:
        return None
    return _require_int(value, label)


def _optional_float(value: Any, label: str) -> Optional[float]:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FineTuneExecutionError(f"{label}_must_be_number")
    return float(value)


def _safe_token(value: str, fallback: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip())
    safe = safe.strip("-_")
    return safe or fallback


def _resolve_training_package_paths(training_package_root: Path) -> TrainingPackagePaths:
    root = _normalize_path(training_package_root)
    if not root.exists():
        raise FineTuneExecutionError(f"training_package_not_found:{root}")
    if not root.is_dir():
        raise FineTuneExecutionError(f"training_package_must_be_directory:{root}")

    train_file = root / TRAIN_FILE_NAME
    manifest_file = root / MANIFEST_FILE_NAME
    backend_profile_file = root / BACKEND_PROFILE_FILE_NAME

    missing = [
        name
        for name, path in [
            (TRAIN_FILE_NAME, train_file),
            (MANIFEST_FILE_NAME, manifest_file),
            (BACKEND_PROFILE_FILE_NAME, backend_profile_file),
        ]
        if not path.exists()
    ]
    if missing:
        raise FineTuneExecutionError(f"training_package_missing_required_files:{','.join(missing)}")

    return TrainingPackagePaths(
        root=root,
        train_file=train_file.resolve(),
        manifest_file=manifest_file.resolve(),
        backend_profile_file=backend_profile_file.resolve(),
    )


def _count_jsonl_records(path: Path) -> Tuple[int, List[str]]:
    count = 0
    warnings: List[str] = []

    with path.open("r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FineTuneExecutionError(f"train_jsonl_invalid_line:{line_number}:{exc}") from exc
            if not isinstance(row, dict):
                raise FineTuneExecutionError(f"train_jsonl_line_must_be_object:{line_number}")
            if not any(key in row for key in ALLOWED_TRAIN_KEYS):
                warnings.append(f"line_{line_number}_missing_expected_training_keys")
            count += 1

    if count <= 0:
        raise FineTuneExecutionError("train_jsonl_contains_no_records")
    return count, warnings


def _load_training_examples(path: Path, prompt_field: str, completion_field: str) -> List[TrainingExample]:
    examples: List[TrainingExample] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FineTuneExecutionError(f"train_jsonl_invalid_line:{line_number}:{exc}") from exc
            if not isinstance(row, dict):
                raise FineTuneExecutionError(f"train_jsonl_line_must_be_object:{line_number}")
            prompt = row.get(prompt_field)
            completion = row.get(completion_field)
            if not isinstance(prompt, str) or not prompt.strip():
                raise FineTuneExecutionError(f"train_jsonl_missing_prompt_field:{line_number}:{prompt_field}")
            if not isinstance(completion, str) or not completion.strip():
                raise FineTuneExecutionError(f"train_jsonl_missing_completion_field:{line_number}:{completion_field}")
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            examples.append(TrainingExample(prompt=prompt, completion=completion, metadata=metadata))
    if not examples:
        raise FineTuneExecutionError("train_jsonl_contains_no_examples")
    return examples


def _extract_manifest_record_count(manifest: Dict[str, Any]) -> int:
    direct_keys = ("record_count", "training_record_count", "train_record_count")
    for key in direct_keys:
        if manifest.get(key) is not None:
            return _require_int(manifest.get(key), f"manifest.{key}")

    counts = manifest.get("record_counts")
    if isinstance(counts, dict):
        for key in ("exported_record_count", "train", "train_records", "training_records", "sft_records"):
            if counts.get(key) is not None:
                return _require_int(counts.get(key), f"manifest.record_counts.{key}")

    raise FineTuneExecutionError("manifest_record_count_missing")


def _extract_manifest_training_file(manifest: Dict[str, Any]) -> Optional[str]:
    for key in ("train_file", "training_file", "train_dataset_file"):
        value = _optional_str(manifest.get(key))
        if value:
            return value

    output = manifest.get("output")
    if isinstance(output, dict):
        for key in ("train_file", "training_file"):
            value = _optional_str(output.get(key))
            if value:
                return value

    files_block = manifest.get("files")
    if isinstance(files_block, dict):
        for key in ("train", "train_file", "train_sft", "train_sft_jsonl"):
            value = _optional_str(files_block.get(key))
            if value:
                return value
    return None


def _extract_manifest_lifecycle_state(manifest: Dict[str, Any]) -> str:
    direct = _optional_str(manifest.get("lifecycle_state"))
    if direct:
        return direct

    source_registry_state = _optional_str(manifest.get("registry_state"))
    if source_registry_state:
        return source_registry_state

    lifecycle = manifest.get("lifecycle")
    if isinstance(lifecycle, dict):
        state = _optional_str(lifecycle.get("state"))
        if state:
            return state

    frozen_manifest_summary = manifest.get("frozen_manifest_summary")
    if isinstance(frozen_manifest_summary, dict):
        state = _optional_str(frozen_manifest_summary.get("state"))
        if state:
            return state

    return "STATE_1"


def _validate_manifest_contract(manifest: Dict[str, Any], package_paths: TrainingPackagePaths) -> ManifestSummary:
    dataset_version = _require_str(manifest.get("dataset_version"), "manifest.dataset_version")
    record_count = _extract_manifest_record_count(manifest)
    lifecycle_state = _extract_manifest_lifecycle_state(manifest)
    training_file_ref = _extract_manifest_training_file(manifest) or TRAIN_FILE_NAME

    if lifecycle_state != "STATE_1":
        raise FineTuneExecutionError(f"manifest.lifecycle_state_must_be_state1:{lifecycle_state}")

    if Path(training_file_ref.replace("\\", "/")).name != TRAIN_FILE_NAME:
        raise FineTuneExecutionError(f"manifest_training_file_mismatch:{training_file_ref}!={TRAIN_FILE_NAME}")

    target_model = manifest.get("target_model")
    if target_model is None:
        target_model = {}
    target_model = _require_dict(target_model, "manifest.target_model")

    authorization_posture = manifest.get("authorization_posture")
    if authorization_posture is None:
        authorization_posture = {}
    authorization_posture = _require_dict(authorization_posture, "manifest.authorization_posture")

    return ManifestSummary(
        dataset_version=dataset_version,
        lifecycle_state=lifecycle_state,
        record_count=record_count,
        training_file_ref=training_file_ref,
        source_registry_state=_optional_str(manifest.get("registry_state")),
        source_registry_entry_id=_optional_str(manifest.get("registry_entry_id")),
        dataset_passport_id=_optional_str(manifest.get("dataset_passport_id")),
        target_model=target_model,
        authorization_posture=authorization_posture,
    )


def _resolve_backend_config(
    backend_profile: Dict[str, Any],
    requested_backend: str,
    manifest_summary: ManifestSummary,
) -> ResolvedBackendConfig:
    format_name = _require_str(backend_profile.get("format"), "backend_profile.format")
    prompt_field = _require_str(backend_profile.get("prompt_field"), "backend_profile.prompt_field")
    completion_field = _require_str(backend_profile.get("completion_field"), "backend_profile.completion_field")
    include_metadata = _require_bool(backend_profile.get("include_metadata"), "backend_profile.include_metadata")

    backend_profile_id = (
        _optional_str(backend_profile.get("backend_profile_id"))
        or _optional_str(backend_profile.get("profile_id"))
        or _optional_str(backend_profile.get("training_backend_profile_id"))
        or _optional_str(backend_profile.get("backend_id"))
    )
    if not backend_profile_id:
        raise FineTuneExecutionError("backend_profile.identifier_missing")

    declared_backend = (
        _optional_str(backend_profile.get("backend"))
        or _optional_str(backend_profile.get("backend_name"))
        or _optional_str(backend_profile.get("backend_id"))
        or DEFAULT_BACKEND
    )

    supported_backends_raw = backend_profile.get("supported_backends")
    if supported_backends_raw is None:
        supported_backends = [requested_backend] if requested_backend == declared_backend else [declared_backend, requested_backend]
    else:
        supported_backends = [
            _require_str(item, f"backend_profile.supported_backends[{idx}]")
            for idx, item in enumerate(_require_list(supported_backends_raw, "backend_profile.supported_backends"))
        ]

    if requested_backend not in supported_backends:
        raise FineTuneExecutionError(
            f"backend_not_supported:{requested_backend}:supported={','.join(sorted(set(supported_backends)))}"
        )

    compatible_package_states_raw = backend_profile.get("compatible_package_states")
    if compatible_package_states_raw is None:
        compatible_package_states = ["STATE_1"]
    else:
        compatible_package_states = [
            _require_str(item, f"backend_profile.compatible_package_states[{idx}]")
            for idx, item in enumerate(_require_list(compatible_package_states_raw, "backend_profile.compatible_package_states"))
        ]

    model_block = backend_profile.get("model")
    if model_block is None:
        model_block = {}
    model_block = _require_dict(model_block, "backend_profile.model")

    model_base = (
        _optional_str(model_block.get("model_base"))
        or _optional_str(model_block.get("base"))
        or _optional_str(backend_profile.get("model_base"))
        or _optional_str(manifest_summary.target_model.get("model_base"))
        or _optional_str(manifest_summary.target_model.get("parameter_class"))
        or "unspecified_model_base"
    )
    model_family = _optional_str(model_block.get("model_family")) or _optional_str(backend_profile.get("model_family"))
    execution_mode = _optional_str(backend_profile.get("execution_mode")) or _optional_str(backend_profile.get("mode")) or "configured"

    backend_block = backend_profile.get("backend_config")
    if backend_block is None:
        backend_block = backend_profile.get(requested_backend)
    if backend_block is None:
        backend_block = {}
    backend_payload = _require_dict(backend_block, "backend_profile.backend_config")

    return ResolvedBackendConfig(
        backend_name=requested_backend,
        backend_profile_id=backend_profile_id,
        model_base=model_base,
        model_family=model_family,
        execution_mode=execution_mode,
        supported_backends=supported_backends,
        compatible_package_states=compatible_package_states,
        backend_payload=backend_payload,
        format_name=format_name,
        prompt_field=prompt_field,
        completion_field=completion_field,
        include_metadata=include_metadata,
    )


def _build_training_arguments_compatible(training_arguments_cls: Any, **kwargs: Any) -> Any:
    supported = inspect.signature(training_arguments_cls.__init__).parameters
    filtered_kwargs = {key: value for key, value in kwargs.items() if key in supported}
    return training_arguments_cls(**filtered_kwargs)


def _build_trainer_compatible(
    trainer_cls: Any,
    *,
    model: Any,
    args: Any,
    train_dataset: Any,
    data_collator: Any,
    tokenizer: Any,
) -> Any:
    trainer_kwargs: Dict[str, Any] = {
        "model": model,
        "args": args,
        "train_dataset": train_dataset,
        "data_collator": data_collator,
    }
    supported = inspect.signature(trainer_cls.__init__).parameters
    if "tokenizer" in supported:
        trainer_kwargs["tokenizer"] = tokenizer
    elif "processing_class" in supported:
        trainer_kwargs["processing_class"] = tokenizer
    return trainer_cls(**trainer_kwargs)


def _resolve_effective_hyperparameters(
    backend_profile: Dict[str, Any],
    cli_max_steps: Optional[int],
    cli_learning_rate: Optional[float],
    cli_batch_size: Optional[int],
) -> EffectiveHyperparameters:
    defaults_block = backend_profile.get("default_hyperparameters")
    defaults = _require_dict(defaults_block, "backend_profile.default_hyperparameters") if defaults_block is not None else {}

    max_steps = cli_max_steps if cli_max_steps is not None else _optional_int(defaults.get("max_steps"), "backend_profile.default_hyperparameters.max_steps")
    learning_rate = cli_learning_rate if cli_learning_rate is not None else _optional_float(defaults.get("learning_rate"), "backend_profile.default_hyperparameters.learning_rate")
    batch_size = cli_batch_size if cli_batch_size is not None else _optional_int(defaults.get("batch_size"), "backend_profile.default_hyperparameters.batch_size")

    if max_steps is not None and max_steps <= 0:
        raise FineTuneExecutionError("effective_hyperparameters.max_steps_must_be_positive")
    if learning_rate is not None and learning_rate <= 0:
        raise FineTuneExecutionError("effective_hyperparameters.learning_rate_must_be_positive")
    if batch_size is not None and batch_size <= 0:
        raise FineTuneExecutionError("effective_hyperparameters.batch_size_must_be_positive")

    return EffectiveHyperparameters(max_steps=max_steps, learning_rate=learning_rate, batch_size=batch_size)


def _validate_package_linkage(
    package_paths: TrainingPackagePaths,
    manifest_summary: ManifestSummary,
    backend_config: ResolvedBackendConfig,
    actual_record_count: int,
) -> Dict[str, Any]:
    package_folder_name = package_paths.root.name
    allowed_package_names = {manifest_summary.dataset_version}
    if manifest_summary.dataset_passport_id:
        allowed_package_names.add(manifest_summary.dataset_passport_id)
    if package_folder_name not in allowed_package_names:
        raise FineTuneExecutionError(
            f"dataset_version_package_name_mismatch:{package_folder_name}!=one_of:{','.join(sorted(allowed_package_names))}"
        )

    if manifest_summary.record_count != actual_record_count:
        raise FineTuneExecutionError(
            f"record_count_mismatch:manifest={manifest_summary.record_count}:actual={actual_record_count}"
        )

    if manifest_summary.lifecycle_state not in backend_config.compatible_package_states:
        raise FineTuneExecutionError(
            f"backend_incompatible_with_lifecycle_state:{manifest_summary.lifecycle_state}:supported={','.join(backend_config.compatible_package_states)}"
        )

    return {
        "dataset_version": manifest_summary.dataset_version,
        "package_root": str(package_paths.root),
        "manifest_record_count": manifest_summary.record_count,
        "actual_record_count": actual_record_count,
        "lifecycle_state": manifest_summary.lifecycle_state,
        "backend_profile_id": backend_config.backend_profile_id,
        "backend_format": backend_config.format_name,
        "prompt_field": backend_config.prompt_field,
        "completion_field": backend_config.completion_field,
    }


def _resolve_mode_tag(dry_run: bool, backend_name: str) -> str:
    return "dryrun" if dry_run else _safe_token(backend_name, "execution")


def _build_run_id(
    run_label: Optional[str],
    mode_tag: str,
    explicit_run_id: Optional[str],
    run_suffix: Optional[str],
) -> str:
    if explicit_run_id:
        return _safe_token(explicit_run_id, "run")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    label_token = _safe_token(run_label, "run") if run_label else "run"
    parts = ["FTRUN", label_token, _safe_token(mode_tag, "execution"), timestamp]
    if run_suffix:
        parts.append(_safe_token(run_suffix, "tag"))
    parts.append(suffix)
    return "-".join(parts)


def _set_random_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np  # type: ignore

        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch  # type: ignore

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _import_local_lora_stack() -> Dict[str, Any]:
    try:
        import torch  # type: ignore
        from datasets import Dataset  # type: ignore
        from peft import LoraConfig, TaskType, get_peft_model  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForCausalLM,
            AutoTokenizer,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except Exception as exc:
        raise FineTuneExecutionError(
            "local_lora_dependencies_missing:install torch transformers datasets peft accelerate"
        ) from exc

    return {
        "torch": torch,
        "Dataset": Dataset,
        "LoraConfig": LoraConfig,
        "TaskType": TaskType,
        "get_peft_model": get_peft_model,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "DataCollatorForLanguageModeling": DataCollatorForLanguageModeling,
        "Trainer": Trainer,
        "TrainingArguments": TrainingArguments,
    }


def _coerce_int(config: Dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise FineTuneExecutionError(f"backend_payload.{key}_must_be_integer")
    return value


def _coerce_float(config: Dict[str, Any], key: str, default: float) -> float:
    value = config.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FineTuneExecutionError(f"backend_payload.{key}_must_be_number")
    return float(value)


def _coerce_bool(config: Dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise FineTuneExecutionError(f"backend_payload.{key}_must_be_boolean")
    return value


def _select_device(torch_mod: Any, requested_device: str) -> str:
    normalized = requested_device.strip().lower()
    if normalized == "auto":
        return "cuda" if torch_mod.cuda.is_available() else "cpu"
    if normalized == "cuda" and not torch_mod.cuda.is_available():
        raise FineTuneExecutionError("backend_payload.device_cuda_requested_but_unavailable")
    if normalized not in {"cpu", "cuda"}:
        raise FineTuneExecutionError(f"backend_payload.device_unsupported:{requested_device}")
    return normalized


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepare_local_lora_examples(
    package_paths: TrainingPackagePaths,
    backend_config: ResolvedBackendConfig,
) -> List[TrainingExample]:
    return _load_training_examples(
        package_paths.train_file,
        prompt_field=backend_config.prompt_field,
        completion_field=backend_config.completion_field,
    )


def _run_local_lora_training(
    run_dir: Path,
    package_paths: TrainingPackagePaths,
    manifest_summary: ManifestSummary,
    backend_config: ResolvedBackendConfig,
    hyperparameters: EffectiveHyperparameters,
) -> Dict[str, Any]:
    deps = _import_local_lora_stack()
    torch_mod = deps["torch"]
    Dataset = deps["Dataset"]
    LoraConfig = deps["LoraConfig"]
    TaskType = deps["TaskType"]
    get_peft_model = deps["get_peft_model"]
    AutoModelForCausalLM = deps["AutoModelForCausalLM"]
    AutoTokenizer = deps["AutoTokenizer"]
    DataCollatorForLanguageModeling = deps["DataCollatorForLanguageModeling"]
    Trainer = deps["Trainer"]
    TrainingArguments = deps["TrainingArguments"]

    payload = backend_config.backend_payload
    seed = _coerce_int(payload, "seed", DEFAULT_RANDOM_SEED)
    _set_random_seed(seed)

    model_base = backend_config.model_base
    if model_base == "unspecified_model_base":
        raise FineTuneExecutionError("local_lora_requires_explicit_model_base_in_backend_profile")

    max_seq_len = _coerce_int(payload, "max_seq_len", 512)
    gradient_accumulation_steps = _coerce_int(payload, "gradient_accumulation_steps", 1)
    num_train_epochs = _coerce_float(payload, "num_train_epochs", 1.0)
    warmup_steps = _coerce_int(payload, "warmup_steps", 0)
    logging_steps = _coerce_int(payload, "logging_steps", 1)
    save_steps = _coerce_int(payload, "save_steps", 0)
    save_total_limit = _coerce_int(payload, "save_total_limit", 1)
    lora_r = _coerce_int(payload, "lora_r", 8)
    lora_alpha = _coerce_int(payload, "lora_alpha", 16)
    lora_dropout = _coerce_float(payload, "lora_dropout", 0.05)
    use_fp16 = _coerce_bool(payload, "fp16", False)
    use_bf16 = _coerce_bool(payload, "bf16", False)
    trust_remote_code = _coerce_bool(payload, "trust_remote_code", False)
    gradient_checkpointing = _coerce_bool(payload, "gradient_checkpointing", False)
    requested_device = _require_str(payload.get("device", "auto"), "backend_payload.device")
    learning_rate = hyperparameters.learning_rate if hyperparameters.learning_rate is not None else _coerce_float(payload, "learning_rate", 5e-5)
    batch_size = hyperparameters.batch_size if hyperparameters.batch_size is not None else _coerce_int(payload, "per_device_train_batch_size", 1)
    max_steps = hyperparameters.max_steps if hyperparameters.max_steps is not None else _optional_int(payload.get("max_steps"), "backend_payload.max_steps")
    target_modules_raw = payload.get("target_modules", ["q_proj", "v_proj"])
    target_modules = [_require_str(v, f"backend_payload.target_modules[{i}]") for i, v in enumerate(_require_list(target_modules_raw, "backend_payload.target_modules"))]

    device = _select_device(torch_mod, requested_device)
    model_dir = run_dir / DEFAULT_MODEL_DIR_NAME
    checkpoints_dir = run_dir / DEFAULT_CHECKPOINTS_DIR_NAME
    trainer_summary_path = run_dir / DEFAULT_TRAINER_SUMMARY_FILE_NAME

    examples = _prepare_local_lora_examples(package_paths, backend_config)

    tokenizer = AutoTokenizer.from_pretrained(model_base, trust_remote_code=trust_remote_code)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    if tokenizer.pad_token is None:
        raise FineTuneExecutionError("tokenizer_pad_token_unavailable_and_eos_missing")

    model = AutoModelForCausalLM.from_pretrained(model_base, trust_remote_code=trust_remote_code)
    if gradient_checkpointing:
        model.gradient_checkpointing_enable()
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=target_modules,
    )
    model = get_peft_model(model, lora_config)

    if device == "cuda":
        model = model.to("cuda")
    else:
        model = model.to("cpu")

    texts = [f"### Prompt\n{ex.prompt}\n\n### Completion\n{ex.completion}{tokenizer.eos_token or ''}" for ex in examples]
    raw_dataset = Dataset.from_dict({"text": texts})

    def tokenize_batch(batch: Dict[str, List[str]]) -> Dict[str, Any]:
        tokenized = tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_seq_len,
            padding=False,
        )
        tokenized["labels"] = [ids[:] for ids in tokenized["input_ids"]]
        return tokenized

    tokenized_dataset = raw_dataset.map(tokenize_batch, batched=True, remove_columns=["text"])
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    training_args = _build_training_arguments_compatible(
        TrainingArguments,
        output_dir=str(checkpoints_dir),
        overwrite_output_dir=True,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        learning_rate=learning_rate,
        num_train_epochs=num_train_epochs,
        max_steps=max_steps if max_steps is not None else -1,
        warmup_steps=warmup_steps,
        logging_steps=logging_steps,
        save_steps=save_steps if save_steps > 0 else 10**9,
        save_total_limit=save_total_limit,
        report_to=[],
        remove_unused_columns=False,
        fp16=use_fp16,
        bf16=use_bf16,
        dataloader_pin_memory=False,
        seed=seed,
    )

    trainer = _build_trainer_compatible(
        Trainer,
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
        tokenizer=tokenizer,
    )

    train_result = trainer.train()

    model_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(model_dir))
    tokenizer.save_pretrained(str(model_dir))

    train_metrics = dict(train_result.metrics)
    trainer_state = getattr(trainer, "state", None)
    log_history = getattr(trainer_state, "log_history", []) if trainer_state is not None else []
    global_step = int(getattr(trainer_state, "global_step", 0) or 0) if trainer_state is not None else 0
    epochs_completed = float(getattr(trainer_state, "epoch", 0.0) or 0.0) if trainer_state is not None else 0.0

    final_loss = None
    for item in reversed(log_history):
        if isinstance(item, dict) and "loss" in item:
            try:
                final_loss = float(item["loss"])
            except Exception:
                final_loss = None
            break

    trainer_summary = {
        "trainer_family": "transformers_peft",
        "trainer_type": "local_lora",
        "dataset_version": manifest_summary.dataset_version,
        "training_package_path": str(package_paths.root),
        "model_base": model_base,
        "device": device,
        "records_loaded": len(examples),
        "tokenized_records": len(tokenized_dataset),
        "effective_hyperparameters": {
            "max_steps": max_steps,
            "learning_rate": learning_rate,
            "per_device_train_batch_size": batch_size,
            "gradient_accumulation_steps": gradient_accumulation_steps,
            "num_train_epochs": num_train_epochs,
            "max_seq_len": max_seq_len,
        },
        "lora": {
            "r": lora_r,
            "alpha": lora_alpha,
            "dropout": lora_dropout,
            "target_modules": target_modules,
        },
        "train_metrics": train_metrics,
        "global_steps": global_step,
        "epochs_completed": epochs_completed,
        "train_loss_final": final_loss,
        "saved_model_dir": str(model_dir),
        "checkpoints_dir": str(checkpoints_dir),
        "recorded_at_utc": _utc_now_iso(),
    }
    _write_json(trainer_summary_path, trainer_summary)

    command_summary = [
        sys.executable,
        "-m",
        "transformers.trainer",
        f"--model_base={model_base}",
        f"--dataset={package_paths.train_file}",
        f"--output_dir={model_dir}",
    ]
    _write_text(run_dir / "trainer_command_summary.txt", " ".join(command_summary) + "\n")

    return {
        "status": "completed",
        "execution_mode": "local_lora",
        "backend": backend_config.backend_name,
        "trainer_family": "transformers_peft",
        "trainer_type": "local_lora",
        "trainable_strategy": "lora",
        "model_output_path": str(model_dir),
        "checkpoints_dir": str(checkpoints_dir),
        "trainer_summary_path": str(trainer_summary_path),
        "steps_completed": global_step,
        "epochs_completed": epochs_completed,
        "records_loaded": len(examples),
        "train_loss_final": final_loss,
    }


def _execute_backend(
    run_dir: Path,
    package_paths: TrainingPackagePaths,
    manifest_summary: ManifestSummary,
    backend_config: ResolvedBackendConfig,
    hyperparameters: EffectiveHyperparameters,
    dry_run: bool,
) -> Dict[str, Any]:
    model_dir = run_dir / DEFAULT_MODEL_DIR_NAME

    if dry_run:
        stub_path = _write_placeholder_model_artifact(
            model_dir,
            {
                "artifact_type": "dry_run_model_stub",
                "run_id": run_dir.name,
                "dataset_version": manifest_summary.dataset_version,
                "backend_profile_id": backend_config.backend_profile_id,
                "model_base": backend_config.model_base,
                "note": "Dry-run mode validates the training package and emits reproducible execution artifacts without running fine-tuning.",
            },
        )
        return {
            "status": "completed",
            "execution_mode": "dry_run",
            "backend": backend_config.backend_name,
            "model_output_path": str(model_dir),
            "model_artifact_stub": str(stub_path),
            "steps_completed": 0,
        }

    if backend_config.backend_name == "local":
        stub_path = _write_placeholder_model_artifact(
            model_dir,
            {
                "artifact_type": "local_backend_execution_stub",
                "run_id": run_dir.name,
                "dataset_version": manifest_summary.dataset_version,
                "backend_profile_id": backend_config.backend_profile_id,
                "model_base": backend_config.model_base,
                "hyperparameters": {
                    "max_steps": hyperparameters.max_steps,
                    "learning_rate": hyperparameters.learning_rate,
                    "batch_size": hyperparameters.batch_size,
                },
                "note": "Execution scaffold completed. Replace this stub branch with the real trainer invocation when the local backend is connected.",
            },
        )
        return {
            "status": "completed",
            "execution_mode": "local_stub",
            "backend": backend_config.backend_name,
            "model_output_path": str(model_dir),
            "model_artifact_stub": str(stub_path),
            "steps_completed": hyperparameters.max_steps or 0,
        }

    if backend_config.backend_name == "local_lora":
        return _run_local_lora_training(
            run_dir=run_dir,
            package_paths=package_paths,
            manifest_summary=manifest_summary,
            backend_config=backend_config,
            hyperparameters=hyperparameters,
        )

    raise FineTuneExecutionError(f"backend_execution_not_implemented:{backend_config.backend_name}")


def _build_finetune_run_manifest(
    run_id: str,
    run_label: Optional[str],
    run_dir: Path,
    run_log_profile: RunLogProfile,
    path_run_log_path: Path,
    package_paths: TrainingPackagePaths,
    manifest_summary: ManifestSummary,
    backend_config: ResolvedBackendConfig,
    hyperparameters: EffectiveHyperparameters,
    execution_result: Dict[str, Any],
    dry_run: bool,
    run_suffix: Optional[str],
) -> Dict[str, Any]:
    manifest = {
        "finetune_run_manifest_version": "v14.3",
        "run_id": run_id,
        "run_label": run_label,
        "run_suffix": run_suffix,
        "dataset_version": manifest_summary.dataset_version,
        "training_package_path": str(package_paths.root),
        "backend_profile_id": backend_config.backend_profile_id,
        "backend": backend_config.backend_name,
        "model_base": backend_config.model_base,
        "model_family": backend_config.model_family,
        "status": execution_result["status"],
        "dry_run": dry_run,
        "execution_mode": execution_result["execution_mode"],
        "record_count": manifest_summary.record_count,
        "hyperparameters": {
            "max_steps": hyperparameters.max_steps,
            "learning_rate": hyperparameters.learning_rate,
            "batch_size": hyperparameters.batch_size,
        },
        "inputs": {
            "train_file": str(package_paths.train_file),
            "manifest_file": str(package_paths.manifest_file),
            "backend_profile_file": str(package_paths.backend_profile_file),
        },
        "outputs": {
            "run_dir": str(run_dir),
            "training_log": str(run_dir / DEFAULT_LOG_FILE_NAME),
            "finetune_run_manifest": str(run_dir / DEFAULT_RUN_MANIFEST_FILE_NAME),
            "top_level_run_log": str(path_run_log_path),
            run_log_profile.output_key: str(path_run_log_path),
            "model_output_path": execution_result["model_output_path"],
        },
        "governance_boundary": {
            "dataset_modified": False,
            "registry_updated": False,
            "authorization_overridden": False,
            "raw_dataset_inputs_accepted": False,
            "latest_package_autoselection_used": False,
            "lineage_recorded": True,
            "execution_only": True,
        },
        "lineage": {
            "source_dataset_version": manifest_summary.dataset_version,
            "source_training_manifest": str(package_paths.manifest_file),
            "source_backend_profile": str(package_paths.backend_profile_file),
            "source_registry_entry_id": manifest_summary.source_registry_entry_id,
        },
        "timestamps": {
            "recorded_at_utc": _utc_now_iso(),
        },
    }

    for key in ("trainer_family", "trainer_type", "trainable_strategy", "checkpoints_dir", "trainer_summary_path"):
        if key in execution_result:
            manifest[key] = execution_result[key]

    return manifest


def _build_path_run_log_path(run_id: str, run_log_profile: RunLogProfile) -> Path:
    return run_log_profile.logs_root / run_id / f"{run_log_profile.filename_prefix}{_utc_now_slug()}.json"


def _build_path_run_log(
    *,
    run_id: str,
    run_label: Optional[str],
    run_dir: Path,
    run_log_profile: RunLogProfile,
    path_run_log_path: Path,
    package_paths: TrainingPackagePaths,
    manifest_summary: ManifestSummary,
    backend_config: ResolvedBackendConfig,
    execution_result: Dict[str, Any],
    dry_run: bool,
    run_manifest: Dict[str, Any],
    training_log_path: Path,
    run_manifest_path: Path,
) -> Dict[str, Any]:
    payload = {
        run_log_profile.version_key: "v1",
        "path_id": run_log_profile.path_id,
        "run_id": run_id,
        "run_label": run_label,
        "status": execution_result["status"],
        "dry_run": dry_run,
        "execution_mode": execution_result["execution_mode"],
        "dataset_version": manifest_summary.dataset_version,
        "record_count": manifest_summary.record_count,
        "backend": backend_config.backend_name,
        "backend_profile_id": backend_config.backend_profile_id,
        "model_base": backend_config.model_base,
        "training_package": {
            "package_dir": str(package_paths.root),
            "manifest_file": str(package_paths.manifest_file),
            "backend_profile_file": str(package_paths.backend_profile_file),
            "train_file": str(package_paths.train_file),
        },
        "outputs": {
            "run_dir": str(run_dir),
            "training_log": str(training_log_path),
            "finetune_run_manifest": str(run_manifest_path),
            "top_level_run_log": str(path_run_log_path),
            run_log_profile.output_key: str(path_run_log_path),
            "model_output_path": execution_result["model_output_path"],
        },
        "lineage": {
            "source_dataset_version": manifest_summary.dataset_version,
            "source_registry_state": manifest_summary.source_registry_state,
            "source_registry_entry_id": manifest_summary.source_registry_entry_id,
            "dataset_passport_id": manifest_summary.dataset_passport_id,
        },
        "recorded_manifest": {
            "finetune_run_manifest_version": run_manifest.get("finetune_run_manifest_version"),
            "run_id": run_manifest.get("run_id"),
            "status": run_manifest.get("status"),
        },
        "timestamps": {
            "recorded_at_utc": _utc_now_iso(),
        },
    }

    trainer_summary_path = execution_result.get("trainer_summary_path")
    if isinstance(trainer_summary_path, str) and trainer_summary_path:
        payload["outputs"]["trainer_summary"] = trainer_summary_path

    return payload


def _build_training_log_base(
    run_id: str,
    package_paths: TrainingPackagePaths,
    manifest_summary: ManifestSummary,
    backend_config: ResolvedBackendConfig,
    hyperparameters: EffectiveHyperparameters,
    dry_run: bool,
    validation_warnings: List[str],
) -> Dict[str, Any]:
    return {
        "training_log_version": "v14.3",
        "run_id": run_id,
        "timestamp_started_utc": _utc_now_iso(),
        "status": "running",
        "mode": "dry_run" if dry_run else "execution",
        "dataset_version": manifest_summary.dataset_version,
        "training_package_path": str(package_paths.root),
        "backend": backend_config.backend_name,
        "backend_profile_id": backend_config.backend_profile_id,
        "model_base": backend_config.model_base,
        "hyperparameters": {
            "max_steps": hyperparameters.max_steps,
            "learning_rate": hyperparameters.learning_rate,
            "batch_size": hyperparameters.batch_size,
        },
        "events": [
            {
                "timestamp_utc": _utc_now_iso(),
                "event": "package_validated",
                "details": {
                    "manifest_file": str(package_paths.manifest_file),
                    "train_file": str(package_paths.train_file),
                    "backend_profile_file": str(package_paths.backend_profile_file),
                    "validation_warning_count": len(validation_warnings),
                },
            }
        ],
        "warnings": list(validation_warnings),
    }


def _finalize_training_log(training_log: Dict[str, Any], execution_result: Dict[str, Any]) -> Dict[str, Any]:
    finalized = dict(training_log)
    finalized["status"] = execution_result["status"]
    finalized["timestamp_completed_utc"] = _utc_now_iso()
    finalized.setdefault("events", []).append(
        {
            "timestamp_utc": _utc_now_iso(),
            "event": "execution_completed",
            "details": execution_result,
        }
    )
    return finalized


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute the v14 STATE_1 fine-tuning layer from a strict v12 training package."
    )
    parser.add_argument(
        "--training-package",
        required=True,
        type=Path,
        help="Path to datasets/training_packages/<dataset_version>/",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=DEFAULT_BACKEND,
        help="Configured execution backend name. Only backends listed in training_backend_profile.json are allowed.",
    )
    parser.add_argument("--run-label", type=str, help="Optional human-readable run label.")
    parser.add_argument("--run-id", type=str, help="Optional explicit run id / folder name. Must be unique if supplied.")
    parser.add_argument("--run-suffix", type=str, help="Optional extra suffix token added to generated run ids.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root folder for finetune run artifacts.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate package and emit artifacts without real training.")
    parser.add_argument("--max-steps", type=int, help="Optional override for max training steps.")
    parser.add_argument("--learning-rate", type=float, help="Optional override for learning rate.")
    parser.add_argument("--batch-size", type=int, help="Optional override for batch size.")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        if args.max_steps is not None and args.max_steps <= 0:
            raise FineTuneExecutionError("cli.max_steps_must_be_positive")
        if args.learning_rate is not None and args.learning_rate <= 0:
            raise FineTuneExecutionError("cli.learning_rate_must_be_positive")
        if args.batch_size is not None and args.batch_size <= 0:
            raise FineTuneExecutionError("cli.batch_size_must_be_positive")

        package_paths = _resolve_training_package_paths(args.training_package)
        manifest = _load_json(package_paths.manifest_file)
        backend_profile = _load_json(package_paths.backend_profile_file)

        manifest_summary = _validate_manifest_contract(manifest, package_paths)
        actual_record_count, validation_warnings = _count_jsonl_records(package_paths.train_file)
        backend_config = _resolve_backend_config(
            backend_profile=backend_profile,
            requested_backend=args.backend.strip(),
            manifest_summary=manifest_summary,
        )
        hyperparameters = _resolve_effective_hyperparameters(
            backend_profile=backend_profile,
            cli_max_steps=args.max_steps,
            cli_learning_rate=args.learning_rate,
            cli_batch_size=args.batch_size,
        )
        linkage_summary = _validate_package_linkage(
            package_paths=package_paths,
            manifest_summary=manifest_summary,
            backend_config=backend_config,
            actual_record_count=actual_record_count,
        )

        output_root = _normalize_path(args.output_root)
        mode_tag = _resolve_mode_tag(args.dry_run, backend_config.backend_name)
        run_id = _build_run_id(args.run_label, mode_tag, args.run_id, args.run_suffix)
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        run_log_profile = _resolve_run_log_profile(package_paths.root)
        path_run_log_path = _build_path_run_log_path(run_id, run_log_profile)

        training_log = _build_training_log_base(
            run_id=run_id,
            package_paths=package_paths,
            manifest_summary=manifest_summary,
            backend_config=backend_config,
            hyperparameters=hyperparameters,
            dry_run=args.dry_run,
            validation_warnings=validation_warnings,
        )
        training_log["linkage_validation"] = linkage_summary
        training_log["runtime_environment"] = {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": os.getcwd(),
        }
        training_log["run_naming"] = {
            "mode_tag": mode_tag,
            "explicit_run_id_used": bool(args.run_id),
            "run_suffix": args.run_suffix,
        }

        execution_result = _execute_backend(
            run_dir=run_dir,
            package_paths=package_paths,
            manifest_summary=manifest_summary,
            backend_config=backend_config,
            hyperparameters=hyperparameters,
            dry_run=args.dry_run,
        )

        finalized_training_log = _finalize_training_log(training_log, execution_result)
        run_manifest = _build_finetune_run_manifest(
            run_id=run_id,
            run_label=args.run_label,
            run_dir=run_dir,
            run_log_profile=run_log_profile,
            path_run_log_path=path_run_log_path,
            package_paths=package_paths,
            manifest_summary=manifest_summary,
            backend_config=backend_config,
            hyperparameters=hyperparameters,
            execution_result=execution_result,
            dry_run=args.dry_run,
            run_suffix=args.run_suffix,
        )

        training_log_path = run_dir / DEFAULT_LOG_FILE_NAME
        run_manifest_path = run_dir / DEFAULT_RUN_MANIFEST_FILE_NAME
        _write_json(training_log_path, finalized_training_log)
        _write_json(run_manifest_path, run_manifest)
        path_run_log = _build_path_run_log(
            run_id=run_id,
            run_label=args.run_label,
            run_dir=run_dir,
            run_log_profile=run_log_profile,
            path_run_log_path=path_run_log_path,
            package_paths=package_paths,
            manifest_summary=manifest_summary,
            backend_config=backend_config,
            execution_result=execution_result,
            dry_run=args.dry_run,
            run_manifest=run_manifest,
            training_log_path=training_log_path,
            run_manifest_path=run_manifest_path,
        )
        _write_json(path_run_log_path, path_run_log)

        result = {
            "status": "ok",
            "run_id": run_id,
            "dataset_version": manifest_summary.dataset_version,
            "training_package_path": str(package_paths.root),
            "backend": backend_config.backend_name,
            "backend_profile_id": backend_config.backend_profile_id,
            "model_base": backend_config.model_base,
            "dry_run": args.dry_run,
            "record_count": actual_record_count,
            "output_dir": str(run_dir),
            "files": {
                "finetune_run_manifest": str(run_manifest_path),
                "training_log": str(training_log_path),
                "top_level_run_log": str(path_run_log_path),
                run_log_profile.output_key: str(path_run_log_path),
                "model_output_path": execution_result["model_output_path"],
            },
        }
        if execution_result.get("trainer_summary_path"):
            result["files"]["trainer_summary"] = execution_result["trainer_summary_path"]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    except FineTuneExecutionError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
