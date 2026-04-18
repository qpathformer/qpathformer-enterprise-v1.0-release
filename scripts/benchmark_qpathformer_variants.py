#!/usr/bin/env python3
"""
scripts/benchmark_qpathformer_variants.py

Run controlled benchmarks for Q-Pathformer model variants and write a structured
benchmark summary tied to a model run manifest.

Design posture
--------------
- manifest-first
- fail-closed
- benchmark-oriented, not training-oriented
- variant execution through subprocess for isolation
- supports dependency-free structural triage before runtime imports
- writes one benchmark summary per model run

Benchmark modes
---------------
- ast_check    : parse/analyze Python surface only; no imports executed
- import_check : import the module in an isolated subprocess
- help_check   : run `<model> --help`
- timed_run    : run the model with user-supplied passthrough args

Recommended order
-----------------
1. ast_check
2. import_check
3. help_check
4. timed_run

What this script does
---------------------
1. Reads a model run manifest created by build_model_run_manifest.py
2. Resolves the source model file from the manifest
3. Executes one benchmark mode
4. Captures timing, exit status, stdout/stderr, and line-based output
5. Writes benchmark_summary.json under the run root from the manifest
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SAFE_WRAPPER = REPO_ROOT / "scripts" / "qpathformer_safe_entry_wrapper.py"


class BenchmarkError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkError(message)


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


def analyze_python_surface(source_file: Path) -> Dict[str, Any]:
    text = source_file.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source_file))

    classes: List[str] = []
    functions: List[str] = []
    has_main_guard = False
    imports_torch = False
    imports_argparse = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.If):
            try:
                segment = ast.get_source_segment(text, node.test) or ""
            except Exception:
                segment = ""
            if "__name__" in segment and "__main__" in segment:
                has_main_guard = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "torch" or alias.name.startswith("torch."):
                    imports_torch = True
                if alias.name == "argparse":
                    imports_argparse = True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "torch" or node.module.startswith("torch.")):
                imports_torch = True
            if node.module == "argparse":
                imports_argparse = True

    return {
        "classes": sorted(set(classes)),
        "functions": sorted(set(functions)),
        "has_main_guard": has_main_guard,
        "imports_torch": imports_torch,
        "imports_argparse": imports_argparse,
    }


def run_command(command: List[str], cwd: Path, timeout_seconds: Optional[int]) -> Dict[str, Any]:
    started = time.perf_counter()
    started_at_utc = utc_now()

    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_seconds,
        )
        timed_out = False
        return_code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        return_code = None
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\n[TIMEOUT] Exceeded {timeout_seconds} seconds."

    ended = time.perf_counter()
    ended_at_utc = utc_now()

    return {
        "started_at_utc": started_at_utc,
        "completed_at_utc": ended_at_utc,
        "duration_seconds": round(ended - started, 6),
        "timed_out": timed_out,
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_lines": stdout.splitlines() if stdout else [],
        "stderr_lines": stderr.splitlines() if stderr else [],
    }


def classify_failure(stderr_lines: List[str], python_surface: Dict[str, Any]) -> Dict[str, Any]:
    stderr_joined = "\n".join(stderr_lines)
    if "No module named 'numpy'" in stderr_joined or 'No module named "numpy"' in stderr_joined:
        return {
            "failure_class": "missing_dependency",
            "likely_cause": "numpy_not_installed",
            "recommended_next_step": "Install numpy in the active Python environment, then rerun import_check or timed_forward.",
        }

    if "No module named 'torch'" in stderr_joined or 'No module named "torch"' in stderr_joined:
        return {
            "failure_class": "missing_dependency",
            "likely_cause": "torch_not_installed",
            "recommended_next_step": (
                "Install torch in the active Python environment, then rerun import_check. "
                "Use ast_check first if you only need structural triage."
            ),
        }

    if "SyntaxError" in stderr_joined:
        return {
            "failure_class": "syntax_error",
            "likely_cause": "source_file_parse_or_runtime_syntax_issue",
            "recommended_next_step": "Inspect the model file and correct syntax before deeper benchmarking.",
        }

    if "ModuleNotFoundError" in stderr_joined:
        return {
            "failure_class": "missing_dependency",
            "likely_cause": "other_python_dependency_missing",
            "recommended_next_step": "Inspect stderr_lines to identify the missing module and install it.",
        }

    if python_surface.get("imports_torch"):
        return {
            "failure_class": "runtime_import_failure",
            "likely_cause": "torch_or_runtime_environment_issue",
            "recommended_next_step": "Confirm torch import in the active environment, then rerun import_check.",
        }

    return {
        "failure_class": "unknown_runtime_failure",
        "likely_cause": "unclassified",
        "recommended_next_step": "Inspect stderr_lines and adjust the model/runtime surface before continuing.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Q-Pathformer variants from a model run manifest.")
    parser.add_argument("--manifest", required=True, help="Path to model_run_manifest.json")
    parser.add_argument(
        "--benchmark-mode",
        required=True,
        choices=["ast_check", "import_check", "help_check", "timed_run", "timed_forward"],
        help="Benchmark mode",
    )
    parser.add_argument("--timeout-seconds", type=int, default=120, help="Timeout for subprocess execution")
    parser.add_argument("--summary-out", default=None, help="Optional explicit output path for benchmark_summary.json")
    parser.add_argument("--keep-stdout", action="store_true", help="Keep full stdout/stderr blobs")
    parser.add_argument(
        "--allow-unsafe-raw-run",
        action="store_true",
        help="Allow timed_run to execute a non-CLI prototype __main__ block directly.",
    )
    parser.add_argument(
        "--model-args",
        nargs=argparse.REMAINDER,
        help="Arguments passed through to the model script for timed_run. Prefix with -- to separate.",
    )
    parser.add_argument("--constructor-json", default=None, help="JSON constructor kwargs for timed_forward wrapper mode")
    parser.add_argument("--forward-input-shape", default=None, help="Comma-separated input shape for timed_forward, e.g. 2,64")
    parser.add_argument(
        "--dtype",
        default="int64",
        choices=["float32", "float16", "bfloat16", "int64"],
        help="Tensor dtype for timed_forward wrapper mode",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Torch device for timed_forward wrapper mode. Defaults to manifest.run.device when set, else cpu.",
    )
    parser.add_argument("--warmup-runs", type=int, default=2, help="Warmup runs for timed_forward wrapper mode")
    parser.add_argument("--timed-runs", type=int, default=5, help="Measured runs for timed_forward wrapper mode")
    parser.add_argument("--target-class", default="QPathformer", help="Primary model class name for timed_forward wrapper mode")
    parser.add_argument("--target-train-fn", default="train_qpathformer", help="Training function name for timed_forward wrapper mode")
    return parser


def build_command(mode: str, source_file: Path, model_args: List[str]) -> Optional[List[str]]:
    if mode == "ast_check":
        return None

    if mode == "import_check":
        code = (
            "import sys, importlib.util, pathlib; "
            "p = pathlib.Path(sys.argv[1]); "
            "spec = importlib.util.spec_from_file_location('qpath_variant', p); "
            "mod = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(mod); "
            "print('IMPORT_OK')"
        )
        return [sys.executable, "-c", code, str(source_file)]

    if mode == "help_check":
        return [sys.executable, str(source_file), "--help"]

    if mode == "timed_run":
        return [sys.executable, str(source_file)] + model_args

    raise BenchmarkError(f"Unsupported benchmark mode: {mode}")


def normalize_model_args(raw_args: Optional[List[str]]) -> List[str]:
    if not raw_args:
        return []
    args = list(raw_args)
    if args and args[0] == "--":
        args = args[1:]
    return args


def resolve_runtime_device(args: argparse.Namespace, manifest: Dict[str, Any]) -> str:
    explicit = (args.device or "").strip()
    if explicit != "":
        return explicit
    manifest_device = (((manifest.get("run") or {}).get("device")) or "").strip()
    if manifest_device and manifest_device.lower() != "unknown":
        return manifest_device
    return "cpu"


def build_wrapper_command(args: argparse.Namespace, manifest_path: Path, wrapper_summary_out: Path, device: str) -> List[str]:
    ensure(SAFE_WRAPPER.exists(), f"Safe wrapper not found: {SAFE_WRAPPER}")
    ensure(args.constructor_json is not None and args.constructor_json.strip() != "", "--constructor-json is required for timed_forward")
    ensure(args.forward_input_shape is not None and args.forward_input_shape.strip() != "", "--forward-input-shape is required for timed_forward")
    return [
        sys.executable,
        str(SAFE_WRAPPER),
        "--manifest",
        str(manifest_path),
        "--probe-mode",
        "timed_forward",
        "--summary-out",
        str(wrapper_summary_out),
        "--target-class",
        args.target_class,
        "--target-train-fn",
        args.target_train_fn,
        "--constructor-json",
        args.constructor_json,
        "--forward-input-shape",
        args.forward_input_shape,
        "--dtype",
        args.dtype,
        "--device",
        device,
        "--warmup-runs",
        str(args.warmup_runs),
        "--timed-runs",
        str(args.timed_runs),
    ]


def main() -> int:
    args = build_parser().parse_args()

    try:
        manifest_path = resolve_path(args.manifest, REPO_ROOT)
        ensure(manifest_path.exists(), f"Manifest not found: {manifest_path}")

        manifest = read_json(manifest_path)
        ensure(isinstance(manifest, dict), "Manifest is not a JSON object")
        ensure(manifest.get("manifest_version") == "qpath_model_run_manifest_v1.0", "Unexpected manifest_version")

        source_ref = (((manifest.get("model") or {}).get("source_file")) or "").strip()
        ensure(source_ref != "", "Manifest missing model.source_file")

        source_file = resolve_path(source_ref, REPO_ROOT)
        ensure(source_file.exists(), f"Model source file not found: {source_file}")

        run_root_ref = (((manifest.get("output_paths") or {}).get("run_root")) or "").strip()
        run_root = resolve_path(run_root_ref, REPO_ROOT) if run_root_ref else manifest_path.parent

        summary_out = resolve_path(args.summary_out, REPO_ROOT) if args.summary_out else run_root / "benchmark_summary.json"
        wrapper_summary_out = run_root / "wrapper_summary.json"

        model_args = normalize_model_args(args.model_args)
        if args.benchmark_mode != "timed_run":
            model_args = []

        surface = analyze_python_surface(source_file)
        resolved_device = resolve_runtime_device(args, manifest)
        wrapper_summary: Optional[Dict[str, Any]] = None
        execution_surface = "benchmark_runner"

        if args.benchmark_mode == "timed_run" and not surface.get("imports_argparse") and not args.allow_unsafe_raw_run:
            raise BenchmarkError(
                "timed_run is unsafe for non-CLI prototype variants because it executes the model __main__ block directly. "
                "Use --benchmark-mode timed_forward with wrapper arguments, or pass --allow-unsafe-raw-run if you intentionally want the raw __main__ path."
            )

        if args.benchmark_mode == "ast_check":
            execution = {
                "started_at_utc": utc_now(),
                "completed_at_utc": utc_now(),
                "duration_seconds": 0.0,
                "timed_out": False,
                "return_code": 0,
                "stdout": "AST_CHECK_OK",
                "stderr": "",
                "stdout_lines": ["AST_CHECK_OK"],
                "stderr_lines": [],
            }
            command = ["<ast_check>", str(source_file)]
        elif args.benchmark_mode == "timed_forward":
            execution_surface = "safe_wrapper"
            command = build_wrapper_command(args, manifest_path, wrapper_summary_out, resolved_device)
            execution = run_command(command, cwd=REPO_ROOT, timeout_seconds=args.timeout_seconds)
            if wrapper_summary_out.exists():
                wrapper_summary = read_json(wrapper_summary_out)
        else:
            if args.benchmark_mode == "timed_run":
                execution_surface = "raw_script"
            command = build_command(args.benchmark_mode, source_file, model_args)
            ensure(command is not None, "Command resolution failed")
            execution = run_command(command, cwd=REPO_ROOT, timeout_seconds=args.timeout_seconds)

        status = "completed"
        diagnosis = None
        if execution["timed_out"]:
            status = "failed"
            diagnosis = {
                "failure_class": "timeout",
                "likely_cause": "execution_exceeded_timeout",
                "recommended_next_step": "Increase timeout or reduce workload before rerunning.",
            }
        elif wrapper_summary is not None and wrapper_summary.get("status") != "completed":
            status = "failed"
            diagnosis = {
                "failure_class": "wrapper_probe_failure",
                "likely_cause": "timed_forward_wrapper_failed",
                "recommended_next_step": "Inspect wrapper_summary.json and adjust constructor, shape, dtype, or device before rerunning.",
            }
        elif execution["return_code"] not in (0, None):
            status = "failed"
            diagnosis = classify_failure(execution["stderr_lines"], surface)

        summary: Dict[str, Any] = {
            "benchmark_summary_version": "qpath_variant_benchmark_v1.2",
            "created_at_utc": utc_now(),
            "status": status,
            "benchmark_mode": args.benchmark_mode,
            "execution_surface": execution_surface,
            "model_run_id": manifest.get("model_run_id"),
            "manifest_path": relativize(manifest_path, REPO_ROOT),
            "model": {
                "variant": (manifest.get("model") or {}).get("variant"),
                "role": (manifest.get("model") or {}).get("role"),
                "source_file": relativize(source_file, REPO_ROOT),
                "parameter_profile": (manifest.get("model") or {}).get("parameter_profile"),
            },
            "run": manifest.get("run"),
            "configuration": manifest.get("configuration"),
            "environment": {
                "repo_root": str(REPO_ROOT),
                "manifest_repo_root": manifest.get("repo_root"),
                "manifest_repo_root_matches_current": str(manifest.get("repo_root")) == str(REPO_ROOT),
                "python_executable": sys.executable,
                "resolved_device": resolved_device,
            },
            "python_surface": surface,
            "command": command,
            "execution": {
                "started_at_utc": execution["started_at_utc"],
                "completed_at_utc": execution["completed_at_utc"],
                "duration_seconds": execution["duration_seconds"],
                "timed_out": execution["timed_out"],
                "return_code": execution["return_code"],
                "stdout_lines": execution["stdout_lines"],
                "stderr_lines": execution["stderr_lines"],
            },
            "artifacts": {
                "summary_path": relativize(summary_out, REPO_ROOT),
            },
            "notes": [
                "Benchmark executed from model run manifest.",
                "Use ast_check first for dependency-free structural triage.",
                "Use import_check after the Python environment is prepared.",
                "Use help_check only when CLI compatibility is expected or under test.",
                "Use timed_forward for prototype variants that do not expose a stable CLI benchmark entry.",
                "Use timed_run only after variant CLI/runtime expectations are confirmed.",
            ],
        }

        if wrapper_summary is not None:
            summary["wrapper_probe"] = {
                "summary_path": relativize(wrapper_summary_out, REPO_ROOT),
                "probe_mode": wrapper_summary.get("probe_mode"),
                "forward_request": wrapper_summary.get("forward_request"),
                "targets": wrapper_summary.get("targets"),
                "execution": (wrapper_summary.get("execution") or {}).get("timed_forward"),
            }
            summary["artifacts"]["wrapper_summary_path"] = relativize(wrapper_summary_out, REPO_ROOT)

        if diagnosis is not None:
            summary["diagnosis"] = diagnosis

        if args.keep_stdout:
            summary["execution"]["stdout"] = execution["stdout"]
            summary["execution"]["stderr"] = execution["stderr"]

        write_json(summary_out, summary)

        result = {
            "status": summary["status"],
            "model_run_id": summary["model_run_id"],
            "benchmark_mode": summary["benchmark_mode"],
            "summary_path": str(summary_out),
            "duration_seconds": summary["execution"]["duration_seconds"],
            "return_code": summary["execution"]["return_code"],
            "timed_out": summary["execution"]["timed_out"],
        }
        if diagnosis is not None:
            result["diagnosis"] = diagnosis
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if summary["status"] == "completed" else 1

    except BenchmarkError as exc:
        payload = {
            "status": "failed",
            "error": str(exc),
            "created_at_utc": utc_now(),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
