# Dataset Lifecycle State Matrix

## Purpose

This document summarizes the lifecycle states used by the Governed Dataset Lifecycle Framework and describes the typical role, authorization posture, and governance controls associated with each state.

---

## Lifecycle Overview

Artifacts → Dataset Passport → Lifecycle Routing

STATE_3 → STATE_2 → STATE_1

Datasets normally enter the lifecycle in **STATE_3** and may later progress through validation before reaching durable training status.

---

## STATE_3 — Runtime / Synthetic Dataset Layer

### Description

STATE_3 datasets represent provisional resources used for:

- runtime reasoning support
- synthetic dataset generation
- contextual signal retention
- exploratory learning signals

These datasets remain under containment.

### Typical Sources

- ID_3 freeze artifacts
- governance reasoning records
- simulation outputs
- operational analysis artifacts

### Authorization Characteristics

| Property | Status |
|--------|-------|
| runtime reasoning | allowed |
| synthetic generation | allowed |
| fine-tuning | not allowed |
| external training | not allowed |
| human review | required |

### Governance Posture

Signals not decisions.

Datasets remain exploratory and must not influence durable model behavior.

---

## STATE_2 — Validation and Convergence Layer

### Description

STATE_2 functions as a validation stage before promotion.

It evaluates dataset readiness through review and convergence analysis.

### Typical Activities

- teacher–student signal convergence review
- provenance verification
- authorization filtering
- lineage validation
- policy review

### Authorization Characteristics

| Property | Status |
|--------|-------|
| runtime reasoning | limited |
| synthetic generation | limited |
| fine-tuning | pending review |
| external training | prohibited |

### Governance Posture

Datasets remain contained while validation occurs.

Promotion decisions may be prepared but not finalized.

---

## STATE_1 — Durable Training Dataset Layer

### Description

STATE_1 datasets are eligible for durable training use.

These datasets form the curated corpus used for refined model training.

### Entry Requirements

- verified provenance
- authorization filtering completed
- lifecycle promotion event
- human review approval
- dataset version issuance

### Authorization Characteristics

| Property | Status |
|--------|-------|
| runtime reasoning | allowed |
| synthetic generation | optional |
| fine-tuning | allowed |
| external training | conditional |
| human review | required for promotion |

### Governance Posture

STATE_1 datasets remain traceable through lineage and version history.

---

## HOLD State

Datasets placed on HOLD require additional review.

Common causes:

- incomplete authorization
- unresolved provenance
- policy conflicts
- unresolved sensitivity issues

---

## EXCLUDED State

Datasets routed to EXCLUDED are removed from lifecycle processing.

Common causes:

- authorization revoked
- provenance invalid
- policy restrictions prohibit use
- security concerns

---

## Lifecycle Transition Summary

| From | To | Trigger |
|----|----|------|
| STATE_3 | STATE_2 | validation required |
| STATE_2 | STATE_1 | promotion authorized |
| STATE_3 | STATE_1 | exceptional promotion |
| Any | HOLD | review required |
| Any | EXCLUDED | policy restriction |

---

## Teacher–Student Signal Interpretation

Lifecycle states interact with the teacher–student signal model:

| State | Teacher Signals | Student Interpretation |
|-----|-----|-----|
| STATE_3 | raw governance signals | exploratory pattern interpretation |
| STATE_2 | evaluated signals | convergence validation |
| STATE_1 | curated signals | stable training patterns |

---

## Summary

The lifecycle matrix ensures that datasets derived from governance artifacts remain contained and traceable while enabling controlled evolution into durable training datasets.
