#!/usr/bin/env python3
"""
scripts/qpathformer_safe_entry_wrapper.py

Safe execution wrapper for Q-Pathformer prototype variants.

Purpose
-------
Provide a controlled, non-CLI-dependent entry surface for prototype model files
that were not originally written as standardized command-line tools.

This wrapper is designed for the stage after:
- ast_check
- import_check

It lets you:
- import the target module safely
- inspect available surfaces
- inspect signatures of key classes/functions
- optionally instantiate the model if constructor arguments are provided
- optionally attempt one forward pass if both constructor args and input shape
  are provided
- optionally time repeated forward passes with lightweight warmup + measured runs

Design posture
--------------
- fail-closed
- wrapper-first, not model-file modification first
- no assumptions about a shared CLI across model files
- conservative defaults
- writes one wrapper summary JSON

Recommended usage order
-----------------------
1. surface_only
2. instantiate_only
3. forward_pass
4. timed_forward

Current default target naming assumptions
-----------------------------------------
The wrapper looks for:
- class: QPathformer
- function: train_qpathformer

Those names can be overridden if needed.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]


class SafeWrapperError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SafeWrapperError(message)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def resolve_path(raw: str, base: Path) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base / candidate).resolve()


def relativize(path_value: Optional[Path], repo_root: Path) -> Optional[str]:
    if path_value is None:
        return None
    try:
        return str(path_value.resolve().relative_to(repo_root)).replace("\\", "/")
    except Exception:
        return str(path_value).replace("\\", "/")


def load_module_from_file(source_file: Path):
    spec = importlib.util.spec_from_file_location("qpathformer_variant_module", source_file)
    ensure(spec is not None, f"Unable to create import spec for: {source_file}")
    ensure(spec.loader is not None, f"Import spec loader missing for: {source_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signature_to_string(obj: Any) -> Optional[str]:
    try:
        return str(inspect.signature(obj))
    except Exception:
        return None


def list_named_surfaces(module: Any) -> Dict[str, Any]:
    classes: Dict[str, Dict[str, Any]] = {}
    functions: Dict[str, Dict[str, Any]] = {}

    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and obj.__module__ == module.__name__:
            classes[name] = {
                "signature": signature_to_string(obj),
                "doc": inspect.getdoc(obj),
            }
        elif inspect.isfunction(obj) and obj.__module__ == module.__name__:
            functions[name] = {
                "signature": signature_to_string(obj),
                "doc": inspect.getdoc(obj),
            }

    return {
        "classes": classes,
        "functions": functions,
    }


def parse_constructor_args(raw: Optional[str]) -> Dict[str, Any]:
    if raw is None or raw.strip() == "":
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SafeWrapperError(f"Invalid JSON for --constructor-json: {exc}") from exc

    ensure(isinstance(payload, dict), "--constructor-json must decode to a JSON object")
    return payload


def parse_forward_input_shape(raw: Optional[str]) -> Optional[List[int]]:
    if raw is None or raw.strip() == "":
        return None
    try:
        values = [int(x.strip()) for x in raw.split(",") if x.strip() != ""]
    except ValueError as exc:
        raise SafeWrapperError("--forward-input-shape must be comma-separated integers, e.g. 2,16,128") from exc
    ensure(len(values) >= 1, "--forward-input-shape must contain at least one integer")
    return values


def summarize_output(output: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "output_type": type(output).__name__,
        "output_shape": None,
    }

    if hasattr(output, "shape"):
        try:
            summary["output_shape"] = list(output.shape)
            return summary
        except Exception:
            try:
                summary["output_shape"] = str(output.shape)
                return summary
            except Exception:
                pass

    if isinstance(output, (list, tuple)):
        summary["output_length"] = len(output)
        item_types: List[str] = []
        item_shapes: List[Any] = []
        for item in output:
            item_types.append(type(item).__name__)
            if hasattr(item, "shape"):
                try:
                    item_shapes.append(list(item.shape))
                except Exception:
                    try:
                        item_shapes.append(str(item.shape))
                    except Exception:
                        item_shapes.append(None)
            else:
                item_shapes.append(None)
        summary["item_types"] = item_types
        summary["item_shapes"] = item_shapes

    return summary


def build_input_tensor(torch: Any, forward_input_shape: List[int], constructor_kwargs: Dict[str, Any], dtype: str, device: str):
    dtype_map = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "int64": torch.int64,
    }

    if dtype == "int64":
        vocab_size = int(constructor_kwargs.get("vocab_size", 1000))
        return torch.randint(
            low=0,
            high=vocab_size,
            size=tuple(forward_input_shape),
            dtype=torch.int64,
            device=device,
        )

    return torch.randn(
        *forward_input_shape,
        dtype=dtype_map[dtype],
        device=device,
    )


def run_single_forward(instance: Any, tensor: Any, torch: Any) -> Any:
    with torch.no_grad():
        return instance(tensor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe execution wrapper for Q-Pathformer prototype variants.")
    parser.add_argument("--manifest", required=True, help="Path to model_run_manifest.json")
    parser.add_argument(
        "--probe-mode",
        required=True,
        choices=["surface_only", "instantiate_only", "forward_pass", "timed_forward"],
        help="Wrapper probe mode",
    )
    parser.add_argument("--summary-out", default=None, help="Optional explicit output path for wrapper_summary.json")
    parser.add_argument("--target-class", default="QPathformer", help="Primary model class name to target")
    parser.add_argument("--target-train-fn", default="train_qpathformer", help="Optional train function name to inspect")
    parser.add_argument(
        "--constructor-json",
        default=None,
        help="JSON object of constructor kwargs for instantiate_only, forward_pass, or timed_forward",
    )
    parser.add_argument(
        "--forward-input-shape",
        default=None,
        help="Comma-separated input tensor shape for forward_pass or timed_forward, e.g. 2,16,128",
    )
    parser.add_argument(
        "--dtype",
        default="float32",
        choices=["float32", "float16", "bfloat16", "int64"],
        help="Tensor dtype for forward_pass or timed_forward",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Torch device string, default cpu",
    )
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=2,
        help="Number of unmeasured warmup runs for timed_forward",
    )
    parser.add_argument(
        "--timed-runs",
        type=int,
        default=5,
        help="Number of measured forward runs for timed_forward",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    started = time.perf_counter()
    started_at_utc = utc_now()
    summary_out: Optional[Path] = None

    try:
        manifest_path = resolve_path(args.manifest, REPO_ROOT)
        ensure(manifest_path.exists(), f"Manifest not found: {manifest_path}")

        manifest = read_json(manifest_path)
        ensure(manifest.get("manifest_version") == "qpath_model_run_manifest_v1.0", "Unexpected manifest_version")

        source_ref = (((manifest.get("model") or {}).get("source_file")) or "").strip()
        ensure(source_ref != "", "Manifest missing model.source_file")

        source_file = resolve_path(source_ref, REPO_ROOT)
        ensure(source_file.exists(), f"Model source file not found: {source_file}")

        run_root_ref = (((manifest.get("output_paths") or {}).get("run_root")) or "").strip()
        run_root = resolve_path(run_root_ref, REPO_ROOT) if run_root_ref else manifest_path.parent
        summary_out = resolve_path(args.summary_out, REPO_ROOT) if args.summary_out else run_root / "wrapper_summary.json"

        constructor_kwargs = parse_constructor_args(args.constructor_json)
        forward_input_shape = parse_forward_input_shape(args.forward_input_shape)

        module = load_module_from_file(source_file)
        surfaces = list_named_surfaces(module)

        target_class = getattr(module, args.target_class, None)
        target_train_fn = getattr(module, args.target_train_fn, None)

        summary: Dict[str, Any] = {
            "wrapper_summary_version": "qpath_safe_wrapper_v1.1",
            "created_at_utc": utc_now(),
            "status": "completed",
            "probe_mode": args.probe_mode,
            "model_run_id": manifest.get("model_run_id"),
            "manifest_path": relativize(manifest_path, REPO_ROOT),
            "model": {
                "variant": (manifest.get("model") or {}).get("variant"),
                "role": (manifest.get("model") or {}).get("role"),
                "source_file": relativize(source_file, REPO_ROOT),
                "parameter_profile": (manifest.get("model") or {}).get("parameter_profile"),
            },
            "targets": {
                "target_class": args.target_class,
                "target_class_found": target_class is not None,
                "target_class_signature": signature_to_string(target_class) if target_class is not None else None,
                "target_train_fn": args.target_train_fn,
                "target_train_fn_found": target_train_fn is not None,
                "target_train_fn_signature": signature_to_string(target_train_fn) if target_train_fn is not None else None,
            },
            "surfaces": surfaces,
            "constructor_kwargs": constructor_kwargs,
            "forward_request": {
                "input_shape": forward_input_shape,
                "dtype": args.dtype,
                "device": args.device,
                "warmup_runs": args.warmup_runs,
                "timed_runs": args.timed_runs,
            },
            "execution": {},
            "artifacts": {
                "summary_path": relativize(summary_out, REPO_ROOT),
            },
            "notes": [
                "This wrapper avoids depending on a shared CLI across prototype model files.",
                "Use surface_only first, then instantiate_only, then forward_pass, then timed_forward.",
            ],
        }

        if args.probe_mode in {"instantiate_only", "forward_pass", "timed_forward"}:
            ensure(target_class is not None, f"Target class not found: {args.target_class}")
            ensure(len(constructor_kwargs) > 0, "--constructor-json is required for instantiate_only, forward_pass, or timed_forward")

            instance = target_class(**constructor_kwargs)
            if hasattr(instance, "eval") and callable(instance.eval):
                instance.eval()

            summary["execution"]["instantiate"] = {
                "status": "completed",
                "instance_type": type(instance).__name__,
            }

            if args.probe_mode in {"forward_pass", "timed_forward"}:
                ensure(forward_input_shape is not None, "--forward-input-shape is required for forward_pass or timed_forward")

                try:
                    import torch
                except ModuleNotFoundError as exc:
                    raise SafeWrapperError("torch is required for forward_pass or timed_forward probe mode") from exc

                ensure(args.warmup_runs >= 0, "--warmup-runs must be >= 0")
                ensure(args.timed_runs >= 1, "--timed-runs must be >= 1")

                tensor = build_input_tensor(torch, forward_input_shape, constructor_kwargs, args.dtype, args.device)

                if args.probe_mode == "forward_pass":
                    output = run_single_forward(instance, tensor, torch)
                    summary["execution"]["forward_pass"] = {
                        "status": "completed",
                        "input_shape": forward_input_shape,
                        **summarize_output(output),
                    }

                elif args.probe_mode == "timed_forward":
                    last_output = None

                    warmup_started = time.perf_counter()
                    for _ in range(args.warmup_runs):
                        last_output = run_single_forward(instance, tensor, torch)
                    warmup_ended = time.perf_counter()

                    latencies: List[float] = []
                    timed_started = time.perf_counter()
                    for _ in range(args.timed_runs):
                        single_start = time.perf_counter()
                        last_output = run_single_forward(instance, tensor, torch)
                        single_end = time.perf_counter()
                        latencies.append(single_end - single_start)
                    timed_ended = time.perf_counter()

                    ensure(last_output is not None, "timed_forward completed without producing an output")

                    summary["execution"]["timed_forward"] = {
                        "status": "completed",
                        "input_shape": forward_input_shape,
                        "warmup_runs": args.warmup_runs,
                        "timed_runs": args.timed_runs,
                        "warmup_total_seconds": round(warmup_ended - warmup_started, 6),
                        "timed_total_seconds": round(timed_ended - timed_started, 6),
                        "latency_seconds": {
                            "avg": round(sum(latencies) / len(latencies), 6),
                            "min": round(min(latencies), 6),
                            "max": round(max(latencies), 6),
                            "runs": [round(x, 6) for x in latencies],
                        },
                        **summarize_output(last_output),
                    }

        ended = time.perf_counter()
        summary["execution"]["started_at_utc"] = started_at_utc
        summary["execution"]["completed_at_utc"] = utc_now()
        summary["execution"]["duration_seconds"] = round(ended - started, 6)

        write_json(summary_out, summary)

        result = {
            "status": summary["status"],
            "probe_mode": summary["probe_mode"],
            "model_run_id": summary["model_run_id"],
            "summary_path": str(summary_out),
            "duration_seconds": summary["execution"]["duration_seconds"],
            "target_class_found": summary["targets"]["target_class_found"],
        }
        if "timed_forward" in summary["execution"]:
            result["timed_forward_avg_seconds"] = summary["execution"]["timed_forward"]["latency_seconds"]["avg"]
            result["timed_forward_min_seconds"] = summary["execution"]["timed_forward"]["latency_seconds"]["min"]
            result["timed_forward_max_seconds"] = summary["execution"]["timed_forward"]["latency_seconds"]["max"]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    except SafeWrapperError as exc:
        ended = time.perf_counter()
        payload = {
            "wrapper_summary_version": "qpath_safe_wrapper_v1.1",
            "created_at_utc": utc_now(),
            "status": "failed",
            "probe_mode": args.probe_mode,
            "error": str(exc),
            "duration_seconds": round(ended - started, 6),
        }
        if summary_out is not None:
            try:
                write_json(summary_out, payload)
                payload["summary_path"] = str(summary_out)
            except Exception:
                pass
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1

    except Exception as exc:
        ended = time.perf_counter()
        payload = {
            "wrapper_summary_version": "qpath_safe_wrapper_v1.1",
            "created_at_utc": utc_now(),
            "status": "failed",
            "probe_mode": args.probe_mode,
            "error": f"Unhandled wrapper error: {exc}",
            "duration_seconds": round(ended - started, 6),
        }
        if summary_out is not None:
            try:
                write_json(summary_out, payload)
                payload["summary_path"] = str(summary_out)
            except Exception:
                pass
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
