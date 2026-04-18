#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10 Runtime Signal Validation Layer

Deterministic, non-authoritative scoring and validation-readiness assessment
for runtime-emitted signals.

Posture:
- ID_2 only
- diagnostic only
- no approval, certification, or compliance claims
- does not grant authority
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
import re


@dataclass(frozen=True)
class ValidationThresholds:
    min_coherence_for_candidate: float = 0.72
    min_stability_for_candidate: float = 0.68
    max_ambiguity_for_candidate: float = 0.38
    min_summary_characters: int = 40
    min_tag_count: int = 2


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_\-]+", (text or "").lower())


def score_signal(signal_record: Dict[str, Any]) -> Dict[str, float]:
    """
    Heuristic deterministic scoring.
    Metrics are diagnostic only and do not imply correctness or approval.
    """
    signal_block = signal_record.get("signal", {}) or {}
    raw_output = str(signal_block.get("raw_output", "") or "")
    structured_summary = str(signal_block.get("structured_summary", "") or "")
    tags = signal_block.get("tags", []) or []

    raw_tokens = _tokenize(raw_output)
    summary_tokens = _tokenize(structured_summary)

    raw_len = len(raw_tokens)
    summary_len = len(summary_tokens)
    unique_summary = len(set(summary_tokens))
    tag_count = len(tags)

    repetition_penalty = 0.0
    if summary_len > 0:
        repetition_penalty = 1.0 - (unique_summary / max(summary_len, 1))

    coherence = (
        0.35 * min(summary_len / 40.0, 1.0)
        + 0.20 * min(tag_count / 4.0, 1.0)
        + 0.20 * (1.0 if structured_summary.strip().endswith((".", "!", "?")) else 0.65)
        + 0.15 * (1.0 if raw_len > 0 else 0.0)
        + 0.10 * (1.0 - min(repetition_penalty, 1.0))
    )

    summary_set = set(summary_tokens)
    raw_set = set(raw_tokens)
    if not summary_set:
        novelty = 0.0
    else:
        incremental = len(summary_set - raw_set)
        novelty = 0.45 + 0.55 * min(incremental / max(len(summary_set), 1), 1.0)

    stability = (
        0.35 * min(summary_len / 50.0, 1.0)
        + 0.25 * min(tag_count / 4.0, 1.0)
        + 0.20 * (1.0 if 10 <= raw_len <= 500 else 0.7)
        + 0.20 * (1.0 if len(structured_summary) <= 400 else 0.8)
    )

    ambiguity_markers = [
        "maybe",
        "possibly",
        "perhaps",
        "unclear",
        "unknown",
        "might",
        "could",
        "unsure",
        "likely",
        "potentially",
        "appears",
        "suggests",
    ]
    ambiguity_hits = sum(structured_summary.lower().count(marker) for marker in ambiguity_markers)
    ambiguity = (
        0.45 * min(ambiguity_hits / 5.0, 1.0)
        + 0.30 * (0.0 if summary_len >= 12 else 0.85)
        + 0.25 * (0.0 if tag_count >= 2 else 0.8)
    )

    return {
        "coherence": _clamp(coherence),
        "novelty": _clamp(novelty),
        "stability": _clamp(stability),
        "ambiguity": _clamp(ambiguity),
    }


def classify_maturity(metrics: Dict[str, float]) -> str:
    """
    Diagnostic maturity classification only.
    """
    coherence = float(metrics["coherence"])
    stability = float(metrics["stability"])
    ambiguity = float(metrics["ambiguity"])

    if coherence < 0.25:
        return "LEVEL_0"
    if coherence < 0.45:
        return "LEVEL_1"
    if coherence < 0.60 or stability < 0.45:
        return "LEVEL_2"
    if coherence >= 0.84 and stability >= 0.80 and ambiguity <= 0.22:
        return "LEVEL_5"
    if coherence >= 0.74 and stability >= 0.68 and ambiguity <= 0.38:
        return "LEVEL_4"
    return "LEVEL_3"


def evaluate_validation_readiness(
    signal_record: Dict[str, Any],
    thresholds: ValidationThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or ValidationThresholds()
    metrics = score_signal(signal_record)
    maturity = classify_maturity(metrics)

    summary = str(signal_record.get("signal", {}).get("structured_summary", "") or "")
    tags = signal_record.get("signal", {}).get("tags", []) or []

    reasons: List[str] = []
    candidate_for_validation = True

    if len(summary.strip()) < thresholds.min_summary_characters:
        candidate_for_validation = False
        reasons.append("structured_summary_too_short")

    if len(tags) < thresholds.min_tag_count:
        candidate_for_validation = False
        reasons.append("insufficient_tags")

    if metrics["coherence"] < thresholds.min_coherence_for_candidate:
        candidate_for_validation = False
        reasons.append("coherence_below_threshold")

    if metrics["stability"] < thresholds.min_stability_for_candidate:
        candidate_for_validation = False
        reasons.append("stability_below_threshold")

    if metrics["ambiguity"] > thresholds.max_ambiguity_for_candidate:
        candidate_for_validation = False
        reasons.append("ambiguity_above_threshold")

    if maturity not in {"LEVEL_4", "LEVEL_5"}:
        candidate_for_validation = False
        reasons.append("maturity_below_state2_review_threshold")

    validation_block = {
        "candidate_for_validation": candidate_for_validation,
        "validation_requested": candidate_for_validation,
        "validation_reasons": reasons if reasons else ["candidate_ready_for_state2_review"],
        "validation_engine_version": "v10.0",
    }

    return {
        "metrics": metrics,
        "maturity": maturity,
        "validation": validation_block,
    }