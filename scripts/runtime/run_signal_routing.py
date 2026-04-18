#!/usr/bin/env python3
"""
Q-Pathformer DEV — v10 Runtime Signal Routing Layer

Governance-first routing for runtime-emitted signals.

Posture:
- all emitted signals enter STATE_3 first
- STATE_2 is review readiness, not approval
- no direct STATE_3 -> STATE_1 promotion
- conservative hold is default
"""

from __future__ import annotations

from typing import Any, Dict, List


VALID_ROUTING_DECISIONS = {
    "HOLD_IN_STATE_3",
    "SEND_TO_STATE_2_REVIEW",
    "RETURN_TO_STATE_3",
    "REJECT_SIGNAL",
}


def _has_required_top_level_fields(record: Dict[str, Any]) -> bool:
    required = [
        "signal_id",
        "timestamp",
        "session_id",
        "schema_version",
        "interaction_type",
        "model",
        "input",
        "signal",
        "metrics",
        "maturity",
        "governance_flags",
        "authorization",
        "validation",
        "lifecycle",
    ]
    return all(field in record for field in required)


def _encode(
    record: Dict[str, Any],
    *,
    decision: str,
    target_state: str,
    eligible_for_state_2: bool,
    reasons: List[str],
) -> Dict[str, Any]:
    if decision not in VALID_ROUTING_DECISIONS:
        raise ValueError(f"Invalid routing decision: {decision}")

    record.setdefault("lifecycle", {})
    record["lifecycle"]["state"] = "STATE_3"
    record["lifecycle"]["eligible_for_state_2"] = eligible_for_state_2
    record["lifecycle"]["routing_decision"] = decision
    record["lifecycle"]["target_state"] = target_state
    record["lifecycle"]["routing_reasons"] = reasons

    record["routing_trace"] = {
        "engine_version": "v10.0",
        "decision": decision,
        "target_state": target_state,
        "eligible_for_state_2": eligible_for_state_2,
        "reasons": reasons,
    }

    return record


def route_signal(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fixed routing order:
    Gate A - structural admission
    Gate B - governance constraints
    Gate C - authorization check
    Gate D - validation trigger check
    Gate E - maturity / signal quality check
    Gate F - transition encoding
    """

    # Gate A — Structural admission
    if not _has_required_top_level_fields(record):
        return _encode(
            record,
            decision="REJECT_SIGNAL",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["missing_required_fields"],
        )

    lifecycle = record.get("lifecycle", {}) or {}
    if lifecycle.get("state") != "STATE_3":
        return _encode(
            record,
            decision="REJECT_SIGNAL",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["invalid_initial_lifecycle_state"],
        )

    model = record.get("model", {}) or {}
    if not model.get("model_id") or not model.get("parameter_class") or not model.get("role"):
        return _encode(
            record,
            decision="REJECT_SIGNAL",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["missing_model_metadata"],
        )

    # Gate B — Governance constraint check
    governance = record.get("governance_flags", {}) or {}
    governance_failures: List[str] = []

    if not governance:
        governance_failures.append("missing_governance_flags")
    if governance.get("provisional") is not True:
        governance_failures.append("provisional_flag_not_true")
    if governance.get("requires_validation") is not True:
        governance_failures.append("requires_validation_flag_not_true")
    if governance.get("promotion_blocked") is not True:
        governance_failures.append("promotion_blocked_flag_not_true")

    if governance_failures:
        return _encode(
            record,
            decision="HOLD_IN_STATE_3",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=governance_failures,
        )

    # Gate C — Authorization check
    authorization = record.get("authorization", {}) or {}
    if authorization.get("state2_candidate_allowed") is not True:
        return _encode(
            record,
            decision="HOLD_IN_STATE_3",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["authorization_blocks_state2_candidate"],
        )

    # Gate D — Validation trigger check
    validation = record.get("validation", {}) or {}
    if validation.get("candidate_for_validation") is not True:
        return _encode(
            record,
            decision="HOLD_IN_STATE_3",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["not_candidate_for_validation"],
        )

    if validation.get("validation_requested") is not True:
        return _encode(
            record,
            decision="HOLD_IN_STATE_3",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["validation_not_requested"],
        )

    # Gate E — Maturity / signal quality check
    maturity = record.get("maturity")
    metrics = record.get("metrics", {}) or {}

    if maturity not in {"LEVEL_4", "LEVEL_5"}:
        return _encode(
            record,
            decision="HOLD_IN_STATE_3",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["maturity_below_threshold"],
        )

    if float(metrics.get("ambiguity", 1.0)) > 0.38:
        return _encode(
            record,
            decision="HOLD_IN_STATE_3",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["ambiguity_above_threshold"],
        )

    if float(metrics.get("stability", 0.0)) < 0.68:
        return _encode(
            record,
            decision="HOLD_IN_STATE_3",
            target_state="STATE_3",
            eligible_for_state_2=False,
            reasons=["stability_below_threshold"],
        )

    # Gate F — Transition encoding
    return _encode(
        record,
        decision="SEND_TO_STATE_2_REVIEW",
        target_state="STATE_2",
        eligible_for_state_2=True,
        reasons=["all_state2_review_gates_passed"],
    )