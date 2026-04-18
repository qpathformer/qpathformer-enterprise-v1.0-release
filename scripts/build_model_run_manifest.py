#!/usr/bin/env python3
"""
scripts/build_model_run_manifest.py

Create a normalized manifest for one Q-Pathformer model run.

Purpose
-------
Define a stable metadata surface for model benchmark and training runs so later
benchmark/evaluation scripts can attach results to a consistent manifest.

Design posture
--------------
- fail-closed
- manifest-first
- idempotent by explicit output path
- role-aware (reference / enterprise / strategic)
- path normalization relative to repo root where possible
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]


class ModelRunManifestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ModelRunManifestError(message)


def resolve_path(raw: Optional[str], base: Path) -> Optional[Path]:
    if raw is None or raw == "":
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (base / p).resolve()


def relativize(path_value: Optional[Path], repo_root: Path) -> Optional[str]:
    if path_value is None:
        return None
    try:
        return str(path_value.resolve().relative_to(repo_root)).replace("\\", "/")
    except Exception:
        return str(path_value).replace("\\", "/")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def resolve_device_label(raw: str) -> str:
    value = (raw or "").strip()
    if value == "" or value.lower() == "auto":
        try:
            import torch  # type: ignore

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a model run manifest for Q-Pathformer benchmarking/training.")

    parser.add_argument("--model-variant", required=True, help="Variant name, e.g. grouped_sparse_e64")
    parser.add_argument(
        "--model-role",
        required=True,
        choices=["reference_baseline", "enterprise_target", "strategic_target"],
        help="Role of this model branch in the current dev plan.",
    )
    parser.add_argument("--source-file", required=True, help="Path to source model file")
    parser.add_argument("--parameter-profile", required=True, help="Parameter/expert profile label, e.g. e64")
    parser.add_argument("--run-kind", required=True, choices=["benchmark", "train", "eval"], help="Run type")

    parser.add_argument(
        "--device",
        default="auto",
        help="Device label, e.g. cpu, cuda, laptop_gpu. Use auto to resolve from the active environment.",
    )
    parser.add_argument("--dtype", default="float32", help="Dtype label")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--dataset-ref", default=None, help="Optional dataset reference")
    parser.add_argument("--notes", default=None, help="Optional note string")

    parser.add_argument("--seq-len", type=int, default=None, help="Sequence length")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size")
    parser.add_argument("--micro-batch-size", type=int, default=None, help="Micro batch size")
    parser.add_argument("--epochs", type=int, default=None, help="Epoch count")
    parser.add_argument("--steps", type=int, default=None, help="Step count")
    parser.add_argument("--lr", type=float, default=None, help="Learning rate")
    parser.add_argument("--weight-decay", type=float, default=None, help="Weight decay")
    parser.add_argument("--top-k", type=int, default=None, help="Top-k routing")
    parser.add_argument("--num-experts", type=int, default=None, help="Number of experts")

    parser.add_argument("--output-root", default="evaluation/model_runs", help="Output root for manifests")
    parser.add_argument("--model-run-id", default=None, help="Optional explicit model_run_id")
    parser.add_argument("--out", default=None, help="Optional explicit output manifest path")

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        source_file = resolve_path(args.source_file, REPO_ROOT)
        ensure(source_file is not None and source_file.exists(), f"Source file not found: {args.source_file}")
        resolved_device = resolve_device_label(args.device)

        model_run_id = args.model_run_id or f"MRUN-{args.model_variant}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

        output_root = resolve_path(args.output_root, REPO_ROOT)
        ensure(output_root is not None, "Unable to resolve output root")

        if args.out:
            out_path = resolve_path(args.out, REPO_ROOT)
            ensure(out_path is not None, "Unable to resolve explicit output path")
        else:
            out_path = output_root / model_run_id / "model_run_manifest.json"

        manifest: Dict[str, Any] = {
            "manifest_version": "qpath_model_run_manifest_v1.0",
            "model_run_id": model_run_id,
            "created_at_utc": utc_now(),
            "repo_root": str(REPO_ROOT),
            "model": {
                "variant": args.model_variant,
                "role": args.model_role,
                "source_file": relativize(source_file, REPO_ROOT),
                "parameter_profile": args.parameter_profile,
            },
            "run": {
                "kind": args.run_kind,
                "device": resolved_device,
                "dtype": args.dtype,
                "seed": args.seed,
                "dataset_ref": args.dataset_ref,
                "notes": args.notes,
            },
            "configuration": {
                "seq_len": args.seq_len,
                "batch_size": args.batch_size,
                "micro_batch_size": args.micro_batch_size,
                "epochs": args.epochs,
                "steps": args.steps,
                "lr": args.lr,
                "weight_decay": args.weight_decay,
                "top_k": args.top_k,
                "num_experts": args.num_experts,
            },
            "output_paths": {
                "manifest_path": relativize(out_path, REPO_ROOT),
                "run_root": relativize(out_path.parent, REPO_ROOT),
            },
            "strategy_alignment": {
                "reference_baseline_variant": "reference_sparse_e08",
                "enterprise_target_variant": "grouped_sparse_e64",
                "strategic_target_variant": "fused_sparse_e144",
            },
            "environment": {
                "python_executable": sys.executable,
                "platform": platform.platform(),
                "hostname": socket.gethostname(),
                "device_resolution": "auto" if (args.device or "").strip().lower() in {"", "auto"} else "explicit",
            },
        }

        write_json(out_path, manifest)

        result = {
            "status": "completed",
            "model_run_id": model_run_id,
            "manifest_path": str(out_path),
            "created_at_utc": manifest["created_at_utc"],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    except ModelRunManifestError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
