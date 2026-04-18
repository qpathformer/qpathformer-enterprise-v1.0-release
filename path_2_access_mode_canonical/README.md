# Path 2 — Access-Mode Lifecycle (Canonical)

---

## Purpose

Path 2 implements the **canonical Access-Mode lifecycle execution**:

* `ID_2 → ID_3 → STATE_3 → STATE_2 → STATE_1`

It provides:

* runtime signal generation
* governed lifecycle routing
* candidate dataset formation
* promotion, freeze, and packaging
* primary CSC evidence outputs

This is the **primary execution and evidence-producing path** in the v1.0 release.

---

## Flow

```text
01_source → 02_signals → 03_dataset → 04_state1_package → 05_runs → 06_review → 07_logs
```

---

## Directory Structure

### `01_source/`

Contains **Access-PoD governed source artifacts**.

#### Source Origin

These files are derived from **Access-PoD releases**:

* `v1.1-Access-Mode`
* `ID_2` (operational reasoning)
* `ID_3` (freeze / inspection discipline)

They represent:

* operational session artifacts (ID_2)
* canonical freeze packages (ID_3)

#### Important Note (Release Context)

The source bundle included in this release:

* supports **4 internal session runs** (used to generate candidates in this repo)
* includes **freeze-aligned artifacts under ID_3**

However:

* the **public Access-PoD releases currently provide only 2 session runs**
* these can be used for reproduction
* but **will not produce the required 4-candidate grouping** under the current system rules

#### Access-PoD Working Releases

Mode-specific releases:

**ID_1-core — Learning (published)**
Learning-only reasoning posture (non-operational)
https://github.com/Access-PoD/access-pod-artifacts/releases/tag/ID_1-core

**ID_2-Access — Operational & Runtime Reasoning (published)**
Operational signal reasoning (non-certifying)
https://github.com/Access-PoD/access-pod-artifacts/releases/tag/ID_2-Access

**ID_3-operator — Inspection & Freeze Discipline (published)**
Inspection-facing freeze discipline and canonical packaging
https://github.com/Access-PoD/access-pod-artifacts/releases/tag/ID_3-operator

---

### `02_signals/`

* runtime-generated signals (`runtime_generated/`)
* source-bridged signals (`source_bridge/`)

#### Notes

* runtime signals are generated via `gpt-oss:20b`
* source artifacts are not directly consumed by runtime
* signals are always **STATE_3 (provisional)**

---

### `03_dataset/`

#### `candidates/`

* session-based candidate formation
* grouped signal outputs
* ID_2 lifecycle candidate sets

#### `training_packages/`

* packaged datasets prepared for STATE_1
* versioned dataset outputs

---

### `04_state1_package/`

* controlled STATE_1 dataset packaging
* freeze-ready dataset structures

---

### `05_runs/`

* local LoRA validation runs
* checkpoint outputs and model artifacts

---

### `06_review/`

* lifecycle review outputs
* validation and inspection notes

---

### `07_logs/`

* execution logs
* lifecycle trace logs
* runtime and training logs

---

## Execution Model

Path 2 operates in two modes:

### 1. Source-First (Release Default)

* uses ID_3 freeze artifacts
* deterministic lifecycle progression
* reproducible candidate formation

---

### 2. Runtime Signal Mode

* uses live model (`gpt-oss:20b`)
* generates signals dynamically
* requires candidate grouping for promotion

---

## Lifecycle Position

All artifacts follow:

```text
STATE_3 → STATE_2 → STATE_1
```

### Rules

* all signals originate in STATE_3
* no automatic promotion
* STATE_2 requires explicit validation
* STATE_1 requires controlled packaging

---

## Candidate Formation Constraint (CRITICAL)

Promotion requires:

* **minimum candidate group size = 4**

Implication:

* public Access-PoD releases (2 sessions) → insufficient
* internal release bundle (4 sessions) → valid promotion

---

## Governance Characteristics

* signals are **non-authoritative**
* outputs are **evidence-producing only**
* no compliance or certification claims
* lifecycle progression does not imply approval

---

## Notes

* this path is the **primary CSC evidence generator**
* internal session runs used here will be **published after this release**
* current public Access-PoD artifacts are sufficient for reproduction, not full promotion

---

## Final Position

Path 2 represents:

* the **live operational lifecycle system**
* the **governed routing and promotion layer**
* the **bridge between runtime signals and training datasets**

It is the most critical path for:

* validation
* experimentation
* system understanding

---
